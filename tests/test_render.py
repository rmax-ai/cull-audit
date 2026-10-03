import unittest

from cull_audit.render import render_report


class RenderTests(unittest.TestCase):
    def test_fixed_sections_and_escaped_imported_text(self) -> None:
        audit = {
            "schema_version": "1.0",
            "tool": {"name": "cull-audit", "version": "test"},
            "run": {
                "baseline_stage": "base_[x]",
                "decisive_stage": "dec",
                "photo_root": None,
                "input_sha256": "abc",
                "generated_at": "1970-01-01T00:00:00Z",
            },
            "coverage": {
                "photos_discovered": 0,
                "baseline_unique_photos": 0,
                "decisive_unique_photos": 0,
                "paired_photos": 0,
                "excluded_photos": [],
            },
            "flips": {
                "paired": 0,
                "count": 0,
                "rate": None,
                "direction_counts": {"upward": 0, "downward": 0, "lateral": 0},
                "transitions": {},
                "items": [],
            },
            "stability": {
                "threshold_profile": "v1",
                "eligible_groups": 0,
                "class_counts": {"robust": 0, "soft": 0, "unstable": 0},
                "items": [],
                "exclusions": [],
            },
            "cost": {
                "currency": "USD",
                "known_total": 0,
                "estimated_total": 0,
                "unknown_records": 0,
                "by_stage": {},
                "token_totals": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "thinking_tokens": 0,
                },
            },
            "photos": [{
                "photo_id": "bad_[photo].jpg",
                "discovered": False,
                "record_ids": ["r_[1]"],
                "judgments": [{
                    "record_id": "r_[1]",
                    "stage": "base",
                    "verdict": "maybe",
                    "composite": None,
                    "reasons": ["<unsafe>"],
                    "kill_factors": ["*blur*"],
                }],
                "costs": [],
                "flip": None,
                "stability": [],
            }],
            "warnings": ["warning_[x]"],
        }
        report = render_report(audit)
        for heading in (
            "Summary",
            "Coverage and exclusions",
            "Flip table",
            "Stability",
            "Per-photo cards",
            "Cost",
            "Warnings",
            "Method",
            "Provenance",
        ):
            self.assertIn(f"## {heading}", report)
        self.assertIn(r"bad\_\[photo\].jpg", report)
        self.assertIn(r"\<unsafe\>", report)
        self.assertIn(r"\*blur\*", report)
        self.assertIn("—", report)


if __name__ == "__main__":
    unittest.main()
