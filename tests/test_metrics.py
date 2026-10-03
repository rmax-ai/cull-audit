import copy
import json
import unittest

from cull_audit.contracts import Context, JudgmentRecord, Source
from cull_audit.metrics import (
    calculate_metrics,
    compute_flip_metrics,
    compute_stability_metrics,
    pair_records,
)


VERDICTS = ("reject", "maybe", "accept")


def _record(
    record_id: str,
    photo_id: str,
    stage: str,
    verdict: str,
    composite: float | int | None = None,
    *,
    repeat_group: str | None = None,
    repeat_index: int | None = None,
    settings_fingerprint: str | None = None,
) -> JudgmentRecord:
    context = None
    if (
        repeat_group is not None
        or repeat_index is not None
        or settings_fingerprint is not None
    ):
        context = Context(
            repeat_group=repeat_group,
            repeat_index=repeat_index,
            settings_fingerprint=settings_fingerprint,
        )
    return JudgmentRecord(
        record_id=record_id,
        photo_id=photo_id,
        stage=stage,
        read_kind="relative",
        verdict=verdict,
        source=Source("test"),
        composite=composite,
        context=context,
    )


class FlipMetricTests(unittest.TestCase):
    def test_all_nine_transitions_and_direction_mapping(self) -> None:
        expected_direction = {
            ("reject", "reject"): None,
            ("reject", "maybe"): "upward",
            ("reject", "accept"): "upward",
            ("maybe", "reject"): "downward",
            ("maybe", "maybe"): None,
            ("maybe", "accept"): "upward",
            ("accept", "reject"): "downward",
            ("accept", "maybe"): "downward",
            ("accept", "accept"): None,
        }
        records = []
        for index, baseline_verdict in enumerate(VERDICTS):
            for offset, decisive_verdict in enumerate(VERDICTS):
                photo_id = f"photo-{index}-{offset}.jpg"
                records.extend(
                    (
                        _record(
                            f"b-{index}-{offset}",
                            photo_id,
                            "baseline",
                            baseline_verdict,
                            50,
                        ),
                        _record(
                            f"d-{index}-{offset}",
                            photo_id,
                            "decisive",
                            decisive_verdict,
                            50,
                        ),
                    )
                )

        result = compute_flip_metrics(records, "baseline", "decisive")

        self.assertEqual(result.paired, 9)
        self.assertEqual(result.count, 6)
        self.assertEqual(result.direction_counts, {
            "upward": 3,
            "downward": 3,
            "lateral": 0,
        })
        self.assertEqual(len(result.transitions), 9)
        for item in result.items:
            pair = (item.baseline_verdict, item.decisive_verdict)
            self.assertEqual(
                item.direction,
                expected_direction[pair],
                pair,
            )
            self.assertEqual(
                result.transitions[f"{pair[0]}->{pair[1]}"],
                1,
            )

    def test_duplicate_stage_records_are_excluded_and_zero_pairs_are_null(self) -> None:
        records = [
            _record("b-1", "duplicate.jpg", "baseline", "accept", 80),
            _record("b-2", "duplicate.jpg", "baseline", "maybe", 70),
            _record("d-1", "duplicate.jpg", "decisive", "accept", 80),
        ]

        result = compute_flip_metrics(records, "baseline", "decisive")

        self.assertEqual(result.paired, 0)
        self.assertEqual(result.rate, None)
        self.assertEqual(result.coverage.baseline_unique_photos, 1)
        self.assertEqual(result.coverage.decisive_unique_photos, 1)
        self.assertEqual(len(result.coverage.exclusions), 1)
        exclusion = result.coverage.exclusions[0]
        self.assertEqual(exclusion.reason, "duplicate_baseline")
        self.assertEqual(
            exclusion.observed_stage_counts,
            {"baseline": 2, "decisive": 1},
        )

    def test_lateral_boundary_is_not_a_flip_and_flip_ignores_composites(self) -> None:
        boundary_records = [
            _record("b-boundary", "boundary.jpg", "baseline", "maybe", 50),
            _record("d-boundary", "boundary.jpg", "decisive", "maybe", 65),
            _record("b-material", "material.jpg", "baseline", "maybe", 50),
            _record("d-material", "material.jpg", "decisive", "maybe", 65.01),
            _record("b-flip", "flip.jpg", "baseline", "accept", None),
            _record("d-flip", "flip.jpg", "decisive", "reject", 0),
        ]

        result = compute_flip_metrics(
            boundary_records, "baseline", "decisive"
        )
        by_photo = {item.photo_id: item for item in result.items}

        self.assertIsNone(by_photo["boundary.jpg"].direction)
        self.assertEqual(by_photo["boundary.jpg"].composite_delta, 15)
        self.assertEqual(by_photo["material.jpg"].direction, "lateral")
        self.assertGreater(by_photo["material.jpg"].composite_delta, 15)
        self.assertEqual(by_photo["flip.jpg"].direction, "downward")
        self.assertIsNone(by_photo["flip.jpg"].composite_delta)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.direction_counts["lateral"], 1)

    def test_pair_items_are_sorted_by_photo_id(self) -> None:
        records = [
            _record("b-z", "z.jpg", "baseline", "maybe"),
            _record("d-z", "z.jpg", "decisive", "maybe"),
            _record("b-a", "a.jpg", "baseline", "maybe"),
            _record("d-a", "a.jpg", "decisive", "maybe"),
        ]
        result = pair_records(records, "baseline", "decisive")
        flips = compute_flip_metrics(records, "baseline", "decisive")

        self.assertEqual(
            [pair.photo_id for pair in result.pairs],
            ["a.jpg", "z.jpg"],
        )
        self.assertEqual(
            [item.photo_id for item in flips.items],
            ["a.jpg", "z.jpg"],
        )


class StabilityMetricTests(unittest.TestCase):
    def _repeat(
        self,
        group: str,
        photo_id: str,
        verdicts: tuple[str, ...],
        composites: tuple[float | int | None, ...],
        *,
        fingerprint: str | None = "same-settings",
    ) -> list[JudgmentRecord]:
        return [
            _record(
                f"{group}-{index}",
                photo_id,
                "repeat",
                verdict,
                composites[index],
                repeat_group=group,
                repeat_index=index,
                settings_fingerprint=fingerprint,
            )
            for index, verdict in enumerate(verdicts)
        ]

    def test_spread_boundaries_and_accept_reject_override(self) -> None:
        records = []
        cases = (
            ("robust-edge", "a.jpg", ("maybe", "maybe"), (50, 55), "robust"),
            ("soft-over-five", "b.jpg", ("maybe", "maybe"), (50, 55.01), "soft"),
            ("soft-at-fifteen", "c.jpg", ("maybe", "maybe"), (50, 65), "soft"),
            ("unstable-over-fifteen", "d.jpg", ("maybe", "maybe"), (50, 65.01), "unstable"),
            ("accept-reject", "e.jpg", ("accept", "reject"), (50, 50), "unstable"),
        )
        for group, photo_id, verdicts, composites, expected in cases:
            records.extend(self._repeat(group, photo_id, verdicts, composites))

        result = compute_stability_metrics(records)
        items = {item.repeat_group: item for item in result.items}

        self.assertEqual(
            {group: item.stability_class for group, item in items.items()},
            {case[0]: case[4] for case in cases},
        )
        self.assertEqual(
            result.class_counts,
            {"robust": 1, "soft": 2, "unstable": 2},
        )
        self.assertEqual(result.eligible_groups, len(result.items))
        self.assertEqual(items["robust-edge"].composite_spread, 5)
        self.assertEqual(items["soft-at-fifteen"].composite_spread, 15)

    def test_missing_composites_are_soft_with_missing_evidence_reason(self) -> None:
        result = compute_stability_metrics(
            self._repeat(
                "missing",
                "missing.jpg",
                ("maybe", "maybe"),
                (None, None),
            )
        )
        item = result.items[0]

        self.assertEqual(item.stability_class, "soft")
        self.assertIsNone(item.composite_min)
        self.assertIsNone(item.composite_max)
        self.assertIsNone(item.composite_spread)
        self.assertIn("missing_composite_evidence", item.class_reasons)

    def test_repeat_exclusions_and_denominators_are_explicit(self) -> None:
        records = self._repeat(
            "eligible",
            "z.jpg",
            ("maybe", "maybe"),
            (40, 40),
        )
        records.extend(
            self._repeat(
                "one-record",
                "one.jpg",
                ("maybe",),
                (40,),
            )
        )
        records.extend(
            self._repeat(
                "mixed",
                "a.jpg",
                ("maybe", "maybe"),
                (40, 40),
                fingerprint="fingerprint-a",
            )
        )
        records[-1] = _record(
            "mixed-1",
            "b.jpg",
            "repeat",
            "maybe",
            40,
            repeat_group="mixed",
            repeat_index=1,
            settings_fingerprint="fingerprint-b",
        )

        result = compute_stability_metrics(records)

        self.assertEqual(result.eligible_groups, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.exclusions), 2)
        self.assertEqual(
            {item.repeat_group for item in result.exclusions},
            {"one-record", "mixed"},
        )
        self.assertTrue(all(item.reason for item in result.exclusions))
        self.assertEqual(
            result.class_counts["robust"]
            + result.class_counts["soft"]
            + result.class_counts["unstable"],
            len(result.items),
        )


class CombinedMetricTests(unittest.TestCase):
    def test_synthetic_twenty_eight_of_thirty_three_rate_is_precise(self) -> None:
        records = []
        for index in range(33):
            baseline = "maybe"
            decisive = "reject" if index < 28 else "maybe"
            photo_id = f"photo-{index:02d}.jpg"
            records.extend(
                (
                    _record(f"b-{index}", photo_id, "baseline", baseline),
                    _record(f"d-{index}", photo_id, "decisive", decisive),
                )
            )

        result = compute_flip_metrics(records, "baseline", "decisive")

        self.assertEqual(result.count, 28)
        self.assertEqual(result.paired, 33)
        self.assertEqual(result.rate, 28 / 33)

    def test_metrics_do_not_mutate_input_records(self) -> None:
        records = [
            *_recorded_pair(),
            *_repeat_records(),
        ]
        before = copy.deepcopy(records)

        result = calculate_metrics(records, "baseline", "decisive")

        self.assertIsNotNone(result.to_dict())
        self.assertEqual(records, before)
        json.dumps(result.to_dict())


def _recorded_pair() -> tuple[JudgmentRecord, ...]:
    return (
        _record("b", "photo.jpg", "baseline", "maybe", 50),
        _record("d", "photo.jpg", "decisive", "accept", 60),
    )


def _repeat_records() -> tuple[JudgmentRecord, ...]:
    return (
        _record(
            "r0",
            "repeat.jpg",
            "repeat",
            "maybe",
            60,
            repeat_group="group",
            repeat_index=0,
            settings_fingerprint="settings",
        ),
        _record(
            "r1",
            "repeat.jpg",
            "repeat",
            "maybe",
            61,
            repeat_group="group",
            repeat_index=1,
            settings_fingerprint="settings",
        ),
    )


if __name__ == "__main__":
    unittest.main()
