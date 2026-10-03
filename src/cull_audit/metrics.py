"""Deterministic flip and repeat-read stability metrics.

The functions in this module operate only on normalized
:class:`~cull_audit.contracts.JudgmentRecord` values.  They deliberately do
not read files, inspect images, use timestamps, or print diagnostics.  The
returned dataclasses are frozen; their ``to_dict`` methods convert tuples to
JSON-friendly lists for the audit output layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .contracts import JudgmentRecord


VERDICT_ORDINALS: Mapping[str, int] = {
    "reject": 0,
    "maybe": 1,
    "accept": 2,
}
"""The fixed v1 ordering used for flip direction."""

MATERIAL_COMPOSITE_DELTA = 15
ROBUST_COMPOSITE_SPREAD = 5
UNSTABLE_COMPOSITE_SPREAD = 15
THRESHOLD_PROFILE = "v1"


@dataclass(frozen=True, slots=True)
class PairingExclusion:
    """A photo that could not be paired without choosing between records."""

    photo_id: str
    reason: str
    observed_stage_counts: Mapping[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "reason": self.reason,
            "observed_stage_counts": dict(self.observed_stage_counts),
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class PairingCoverage:
    """Coverage and exclusions produced while selecting stage pairs."""

    baseline_unique_photos: int
    decisive_unique_photos: int
    paired_photos: int
    exclusions: tuple[PairingExclusion, ...] = ()

    @property
    def excluded_photos(self) -> tuple[PairingExclusion, ...]:
        """Alias matching the audit JSON field name."""
        return self.exclusions

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_unique_photos": self.baseline_unique_photos,
            "decisive_unique_photos": self.decisive_unique_photos,
            "paired_photos": self.paired_photos,
            "excluded_photos": [item.to_dict() for item in self.exclusions],
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class PairedRecord:
    """The two normalized records selected for one photo."""

    photo_id: str
    baseline: JudgmentRecord
    decisive: JudgmentRecord

    @property
    def baseline_record_id(self) -> str:
        return self.baseline.record_id

    @property
    def decisive_record_id(self) -> str:
        return self.decisive.record_id

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "baseline_record_id": self.baseline.record_id,
            "decisive_record_id": self.decisive.record_id,
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class PairingResult:
    """Selected pairs plus the coverage needed to interpret their metrics."""

    coverage: PairingCoverage
    pairs: tuple[PairedRecord, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.to_dict(),
            "pairs": [pair.to_dict() for pair in self.pairs],
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class FlipItem:
    """One deterministic baseline/decisive comparison."""

    photo_id: str
    baseline_record_id: str
    decisive_record_id: str
    baseline_verdict: str
    decisive_verdict: str
    baseline_composite: float | int | None
    decisive_composite: float | int | None
    direction: str | None
    composite_delta: float | int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "baseline_record_id": self.baseline_record_id,
            "decisive_record_id": self.decisive_record_id,
            "baseline_verdict": self.baseline_verdict,
            "decisive_verdict": self.decisive_verdict,
            "baseline_composite": self.baseline_composite,
            "decisive_composite": self.decisive_composite,
            "direction": self.direction,
            "composite_delta": self.composite_delta,
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class FlipMetrics:
    """Aggregate flip metrics for one configured stage comparison."""

    paired: int
    count: int
    rate: float | None
    direction_counts: Mapping[str, int]
    transitions: Mapping[str, int]
    items: tuple[FlipItem, ...]
    coverage: PairingCoverage | None = None

    @property
    def paired_photos(self) -> int:
        """Alias for callers that use the coverage terminology."""
        return self.paired

    @property
    def flip_count(self) -> int:
        return self.count

    @property
    def flip_rate(self) -> float | None:
        return self.rate

    def to_dict(self) -> dict[str, object]:
        return {
            "paired": self.paired,
            "count": self.count,
            "rate": self.rate,
            "direction_counts": dict(self.direction_counts),
            "transitions": dict(self.transitions),
            "items": [item.to_dict() for item in self.items],
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class StabilityExclusion:
    """A repeat group excluded from the stability denominator."""

    repeat_group: str
    reason: str
    observed_record_count: int
    observed_photo_ids: tuple[str, ...] = ()
    observed_settings_fingerprints: tuple[str | None, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "repeat_group": self.repeat_group,
            "reason": self.reason,
            "observed_record_count": self.observed_record_count,
            "observed_photo_ids": list(self.observed_photo_ids),
            "observed_settings_fingerprints": list(
                self.observed_settings_fingerprints
            ),
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class StabilityItem:
    """One eligible repeat group and its v1 stability classification."""

    photo_id: str
    repeat_group: str
    record_ids: tuple[str, ...]
    verdicts: tuple[str, ...]
    composites: tuple[float | int | None, ...]
    repeat_count: int
    composite_min: float | int | None
    composite_max: float | int | None
    composite_spread: float | int | None
    stability_class: str
    class_reasons: tuple[str, ...]

    @property
    def classification(self) -> str:
        """Alias for the serialized ``class`` field."""
        return self.stability_class

    @property
    def class_name(self) -> str:
        return self.stability_class

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.class_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "repeat_group": self.repeat_group,
            "record_ids": list(self.record_ids),
            "verdicts": list(self.verdicts),
            "composites": list(self.composites),
            "repeat_count": self.repeat_count,
            "composite_min": self.composite_min,
            "composite_max": self.composite_max,
            "composite_spread": self.composite_spread,
            "class": self.stability_class,
            "class_reasons": list(self.class_reasons),
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class StabilityMetrics:
    """Aggregate v1 stability metrics with an honest denominator."""

    threshold_profile: str
    eligible_groups: int
    class_counts: Mapping[str, int]
    items: tuple[StabilityItem, ...]
    exclusions: tuple[StabilityExclusion, ...] = ()

    @property
    def excluded_groups(self) -> tuple[StabilityExclusion, ...]:
        return self.exclusions

    def to_dict(self) -> dict[str, object]:
        return {
            "threshold_profile": self.threshold_profile,
            "eligible_groups": self.eligible_groups,
            "class_counts": dict(self.class_counts),
            "items": [item.to_dict() for item in self.items],
            "exclusions": [item.to_dict() for item in self.exclusions],
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class MetricsResult:
    """Combined output used by the future audit orchestration layer."""

    coverage: PairingCoverage
    flips: FlipMetrics
    stability: StabilityMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.to_dict(),
            "flips": self.flips.to_dict(),
            "stability": self.stability.to_dict(),
        }

    as_dict = to_dict


# A descriptive alias for callers that prefer the audit terminology.
AuditMetrics = MetricsResult


def _validate_stage_names(baseline_stage: str, decisive_stage: str) -> None:
    if not isinstance(baseline_stage, str) or not baseline_stage:
        raise ValueError("baseline_stage must be a non-empty string")
    if not isinstance(decisive_stage, str) or not decisive_stage:
        raise ValueError("decisive_stage must be a non-empty string")
    if baseline_stage == decisive_stage:
        raise ValueError("baseline_stage and decisive_stage must differ")


def pair_records(
    records: Sequence[JudgmentRecord],
    baseline_stage: str,
    decisive_stage: str,
) -> PairingResult:
    """Pair exactly one record per configured stage, grouped by photo ID.

    A record is never selected over another record from the same stage.  Any
    missing or duplicate stage is represented in ``coverage.exclusions``.
    The input sequence and the records it contains are only read.
    """

    _validate_stage_names(baseline_stage, decisive_stage)
    baseline_by_photo: dict[str, list[JudgmentRecord]] = {}
    decisive_by_photo: dict[str, list[JudgmentRecord]] = {}
    for record in records:
        if record.stage == baseline_stage:
            baseline_by_photo.setdefault(record.photo_id, []).append(record)
        if record.stage == decisive_stage:
            decisive_by_photo.setdefault(record.photo_id, []).append(record)

    pairs: list[PairedRecord] = []
    exclusions: list[PairingExclusion] = []
    photo_ids = sorted(set(baseline_by_photo) | set(decisive_by_photo))
    for photo_id in photo_ids:
        baseline_records = baseline_by_photo.get(photo_id, [])
        decisive_records = decisive_by_photo.get(photo_id, [])
        counts = {
            baseline_stage: len(baseline_records),
            decisive_stage: len(decisive_records),
        }
        if len(baseline_records) == 1 and len(decisive_records) == 1:
            pairs.append(
                PairedRecord(
                    photo_id=photo_id,
                    baseline=baseline_records[0],
                    decisive=decisive_records[0],
                )
            )
            continue
        exclusions.append(
            PairingExclusion(
                photo_id=photo_id,
                reason=_pairing_exclusion_reason(
                    len(baseline_records), len(decisive_records)
                ),
                observed_stage_counts=counts,
            )
        )

    coverage = PairingCoverage(
        baseline_unique_photos=len(baseline_by_photo),
        decisive_unique_photos=len(decisive_by_photo),
        paired_photos=len(pairs),
        exclusions=tuple(exclusions),
    )
    return PairingResult(coverage=coverage, pairs=tuple(pairs))


def _pairing_exclusion_reason(
    baseline_count: int, decisive_count: int
) -> str:
    duplicate_baseline = baseline_count > 1
    duplicate_decisive = decisive_count > 1
    missing_baseline = baseline_count == 0
    missing_decisive = decisive_count == 0

    if duplicate_baseline and duplicate_decisive:
        return "duplicate_baseline_and_decisive"
    if duplicate_baseline:
        return "duplicate_baseline"
    if duplicate_decisive:
        return "duplicate_decisive"
    if missing_baseline and missing_decisive:
        return "missing_baseline_and_decisive"
    if missing_baseline:
        return "missing_baseline"
    if missing_decisive:
        return "missing_decisive"
    # This branch is unreachable for non-negative integer counts, but keeping
    # a stable fallback makes the diagnostic total if the selection rule is
    # extended later.
    return "not_exactly_one_record_per_stage"


def _composite_delta(
    baseline: float | int | None, decisive: float | int | None
) -> float | int | None:
    if baseline is None or decisive is None:
        return None
    return decisive - baseline


def _flip_direction(pair: PairedRecord) -> tuple[str | None, float | int | None]:
    delta = _composite_delta(pair.baseline.composite, pair.decisive.composite)
    if pair.baseline.verdict != pair.decisive.verdict:
        ordinal_change = (
            VERDICT_ORDINALS[pair.decisive.verdict]
            - VERDICT_ORDINALS[pair.baseline.verdict]
        )
        return ("upward" if ordinal_change > 0 else "downward"), delta
    if delta is not None and abs(delta) > MATERIAL_COMPOSITE_DELTA:
        return "lateral", delta
    return None, delta


def _build_flip_metrics(pairing: PairingResult) -> FlipMetrics:
    items: list[FlipItem] = []
    direction_counts = {"upward": 0, "downward": 0, "lateral": 0}
    transitions: dict[str, int] = {}
    flip_count = 0

    for pair in pairing.pairs:
        transition = f"{pair.baseline.verdict}->{pair.decisive.verdict}"
        transitions[transition] = transitions.get(transition, 0) + 1
        direction, composite_delta = _flip_direction(pair)
        if direction is not None:
            direction_counts[direction] += 1
        if pair.baseline.verdict != pair.decisive.verdict:
            flip_count += 1
        items.append(
            FlipItem(
                photo_id=pair.photo_id,
                baseline_record_id=pair.baseline.record_id,
                decisive_record_id=pair.decisive.record_id,
                baseline_verdict=pair.baseline.verdict,
                decisive_verdict=pair.decisive.verdict,
                baseline_composite=pair.baseline.composite,
                decisive_composite=pair.decisive.composite,
                direction=direction,
                composite_delta=composite_delta,
            )
        )

    paired = len(pairing.pairs)
    return FlipMetrics(
        paired=paired,
        count=flip_count,
        rate=None if paired == 0 else flip_count / paired,
        direction_counts=direction_counts,
        transitions=dict(sorted(transitions.items())),
        items=tuple(items),
        coverage=pairing.coverage,
    )


def compute_flip_metrics(
    records: Sequence[JudgmentRecord],
    baseline_stage: str,
    decisive_stage: str,
) -> FlipMetrics:
    """Compute pairing and flip metrics for two named stages."""

    return _build_flip_metrics(
        pair_records(records, baseline_stage, decisive_stage)
    )


def _repeat_sort_key(record: JudgmentRecord) -> tuple[int, int, str]:
    context = record.context
    if context is None or context.repeat_index is None:
        return (1, 0, record.record_id)
    return (0, context.repeat_index, record.record_id)


def _fingerprint_sort_key(value: str | None) -> tuple[int, str]:
    return (value is None, "" if value is None else value)


def _stability_exclusion_reasons(
    group_records: Sequence[JudgmentRecord],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if len(group_records) < 2:
        reasons.append("fewer_than_two_records")

    photo_ids = {record.photo_id for record in group_records}
    if len(photo_ids) != 1:
        reasons.append("multiple_photo_ids")

    fingerprints = {
        record.context.settings_fingerprint
        if record.context is not None
        else None
        for record in group_records
    }
    if None in fingerprints:
        if len(fingerprints) > 1:
            reasons.append("missing_or_mixed_settings_fingerprint")
        else:
            reasons.append("missing_settings_fingerprint")
    elif len(fingerprints) > 1:
        reasons.append("mixed_settings_fingerprint")
    return tuple(reasons)


def _classify_stability(
    verdicts: Sequence[str], spread: float | int | None
) -> tuple[str, tuple[str, ...]]:
    verdict_set = set(verdicts)
    reasons: list[str] = []
    if {"accept", "reject"} <= verdict_set:
        reasons.append("accept_and_reject")
    if spread is not None and spread > UNSTABLE_COMPOSITE_SPREAD:
        reasons.append("composite_spread_gt_15")
    if reasons:
        return "unstable", tuple(reasons)

    if len(verdict_set) == 1 and spread is not None and spread <= ROBUST_COMPOSITE_SPREAD:
        return "robust", ("identical_verdicts", "composite_spread_lte_5")

    if len(verdict_set) > 1:
        reasons.append("verdict_movement")
    if spread is None:
        reasons.append("missing_composite_evidence")
    elif spread > ROBUST_COMPOSITE_SPREAD:
        reasons.append("composite_spread_gt_5")
    return "soft", tuple(reasons)


def compute_stability_metrics(
    records: Sequence[JudgmentRecord],
) -> StabilityMetrics:
    """Group repeat records and apply the fixed v1 stability classes.

    Records without a ``context.repeat_group`` are outside the repeat-group
    population and therefore do not affect either the eligible or excluded
    denominator.
    """

    groups: dict[str, list[JudgmentRecord]] = {}
    for record in records:
        if record.context is not None and record.context.repeat_group is not None:
            groups.setdefault(record.context.repeat_group, []).append(record)

    items: list[StabilityItem] = []
    exclusions: list[StabilityExclusion] = []
    class_counts = {"robust": 0, "soft": 0, "unstable": 0}

    for repeat_group in sorted(groups):
        group_records = groups[repeat_group]
        ordered_records = tuple(sorted(group_records, key=_repeat_sort_key))
        exclusion_reasons = _stability_exclusion_reasons(group_records)
        if exclusion_reasons:
            photo_ids = tuple(sorted({record.photo_id for record in group_records}))
            fingerprints = tuple(
                sorted(
                    {
                        record.context.settings_fingerprint
                        if record.context is not None
                        else None
                        for record in group_records
                    },
                    key=_fingerprint_sort_key,
                )
            )
            exclusions.append(
                StabilityExclusion(
                    repeat_group=repeat_group,
                    reason=exclusion_reasons[0],
                    observed_record_count=len(group_records),
                    observed_photo_ids=photo_ids,
                    observed_settings_fingerprints=fingerprints,
                )
            )
            continue

        composites = tuple(record.composite for record in ordered_records)
        available_composites = tuple(
            composite for composite in composites if composite is not None
        )
        if available_composites:
            composite_min = min(available_composites)
            composite_max = max(available_composites)
            composite_spread = (
                None
                if len(available_composites) < 2
                else composite_max - composite_min
            )
        else:
            composite_min = None
            composite_max = None
            composite_spread = None

        verdicts = tuple(record.verdict for record in ordered_records)
        stability_class, class_reasons = _classify_stability(
            verdicts, composite_spread
        )
        class_counts[stability_class] += 1
        items.append(
            StabilityItem(
                photo_id=ordered_records[0].photo_id,
                repeat_group=repeat_group,
                record_ids=tuple(record.record_id for record in ordered_records),
                verdicts=verdicts,
                composites=composites,
                repeat_count=len(ordered_records),
                composite_min=composite_min,
                composite_max=composite_max,
                composite_spread=composite_spread,
                stability_class=stability_class,
                class_reasons=class_reasons,
            )
        )

    items.sort(key=lambda item: (item.photo_id, item.repeat_group))
    exclusions.sort(key=lambda item: item.repeat_group)
    return StabilityMetrics(
        threshold_profile=THRESHOLD_PROFILE,
        eligible_groups=len(items),
        class_counts=class_counts,
        items=tuple(items),
        exclusions=tuple(exclusions),
    )


def compute_metrics(
    records: Sequence[JudgmentRecord],
    baseline_stage: str,
    decisive_stage: str,
) -> MetricsResult:
    """Compute coverage, flip, and stability metrics in one pure call."""

    pairing = pair_records(records, baseline_stage, decisive_stage)
    flips = _build_flip_metrics(pairing)
    stability = compute_stability_metrics(records)
    return MetricsResult(
        coverage=pairing.coverage,
        flips=flips,
        stability=stability,
    )


# Keep the public vocabulary broad enough for callers using either
# ``calculate`` or ``compute`` without introducing a second implementation.
calculate_flip_metrics = compute_flip_metrics
calculate_stability_metrics = compute_stability_metrics
calculate_metrics = compute_metrics
analyze_metrics = compute_metrics
