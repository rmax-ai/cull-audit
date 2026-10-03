"""Deterministic Markdown rendering for an already-computed audit object."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _escape(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    for character in (
        "\\",
        "`",
        "*",
        "_",
        "{",
        "}",
        "[",
        "]",
        "<",
        ">",
        "#",
        "|",
        "(",
        ")",
        "!",
        "+",
        "-",
    ):
        text = text.replace(character, "\\" + character)
    return text


def _value(value: Any) -> str:
    return _escape(value)


def _one_decimal(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return _escape(value)


def _number(value: Any) -> str:
    if value is None:
        return "—"
    return _escape(value)


def _rate(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return _escape(value)


def render_report(audit: Mapping[str, Any]) -> str:
    """Render Markdown from audit JSON values only.

    No metric is derived here.  Aggregate values and per-photo findings are
    read from the supplied object, which keeps the Markdown a presentation of
    ``audit.json`` rather than a second source of truth.
    """
    run = audit["run"]
    coverage = audit["coverage"]
    flips = audit["flips"]
    stability = audit["stability"]
    cost = audit["cost"]
    photos = audit["photos"]
    warnings = audit["warnings"]
    lines = [
        "# Cull audit report",
        "",
        "## Summary",
        "",
        f"- Baseline stage: {_value(run['baseline_stage'])}",
        f"- Decisive stage: {_value(run['decisive_stage'])}",
        f"- Paired photos: {_value(coverage['paired_photos'])}",
        f"- Verdict flips: {_value(flips['count'])} / {_value(flips['paired'])} "
        f"(rate {_number(flips['rate'])}; {_rate(flips['rate'])})",
        "",
        "## Coverage and exclusions",
        "",
        f"- Photos discovered: {_value(coverage['photos_discovered'])}",
        f"- Baseline unique photos: {_value(coverage['baseline_unique_photos'])}",
        f"- Decisive unique photos: {_value(coverage['decisive_unique_photos'])}",
        f"- Paired photos: {_value(coverage['paired_photos'])}",
        "",
        "| Photo | Exclusion | Observed stage counts |",
        "| --- | --- | --- |",
    ]
    exclusions = coverage["excluded_photos"]
    if exclusions:
        lines.extend(
            f"| {_value(item['photo_id'])} | {_value(item['reason'])} | "
            f"{_value(item['observed_stage_counts'])} |"
            for item in exclusions
        )
    else:
        lines.append("| — | — | — |")

    lines.extend(
        [
            "",
            "## Flip table",
            "",
            "| Photo | Baseline | Decisive | Baseline composite | Decisive composite | Direction | Composite delta |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if flips["items"]:
        lines.extend(
            f"| {_value(item['photo_id'])} | "
            f"{_value(item['baseline_verdict'])} | {_value(item['decisive_verdict'])} | "
            f"{_one_decimal(item['baseline_composite'])} | "
            f"{_one_decimal(item['decisive_composite'])} | "
            f"{_value(item['direction'])} | {_one_decimal(item['composite_delta'])} |"
            for item in flips["items"]
        )
    else:
        lines.append("| — | — | — | — | — | — | — |")
    lines.extend(
        [
            "",
            f"- Upward: {_value(flips['direction_counts']['upward'])}",
            f"- Downward: {_value(flips['direction_counts']['downward'])}",
            f"- Lateral: {_value(flips['direction_counts']['lateral'])}",
            "",
            "| Transition | Count |",
            "| --- | --- |",
        ]
    )
    if flips["transitions"]:
        lines.extend(
            f"| {_value(transition)} | {_value(count)} |"
            for transition, count in flips["transitions"].items()
        )
    else:
        lines.append("| — | — |")

    lines.extend(
        [
            "",
            "## Stability",
            "",
            f"- Threshold profile: {_value(stability['threshold_profile'])}",
            f"- Eligible groups: {_value(stability['eligible_groups'])}",
            f"- Robust: {_value(stability['class_counts']['robust'])}",
            f"- Soft: {_value(stability['class_counts']['soft'])}",
            f"- Unstable: {_value(stability['class_counts']['unstable'])}",
            "",
            "| Photo | Repeat group | Verdicts | Spread | Class |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if stability["items"]:
        lines.extend(
            f"| {_value(item['photo_id'])} | {_value(item['repeat_group'])} | "
            f"{_value(', '.join(map(str, item['verdicts'])))} | "
            f"{_one_decimal(item['composite_spread'])} | {_value(item['class'])} |"
            for item in stability["items"]
        )
    else:
        lines.append("| — | — | — | — | — |")

    lines.extend(["", "## Per-photo cards", ""])
    if photos:
        for photo in photos:
            lines.extend(
                [
                    f"### {_value(photo['photo_id'])}",
                    "",
                    f"- Discovered: {_value(photo['discovered'])}",
                    f"- Records: {_value(', '.join(photo['record_ids']) if photo['record_ids'] else None)}",
                ]
            )
            for judgment in photo.get("judgments", []):
                lines.append(
                    f"- {_value(judgment['record_id'])} composite: "
                    f"{_one_decimal(judgment.get('composite'))}"
                )
                reasons = judgment.get("reasons", [])
                kill_factors = judgment.get("kill_factors", [])
                if reasons:
                    lines.append(
                        f"- {_value(judgment['record_id'])} reasons: "
                        f"{_value('; '.join(map(str, reasons)))}"
                    )
                if kill_factors:
                    lines.append(
                        f"- {_value(judgment['record_id'])} kill factors: "
                        f"{_value('; '.join(map(str, kill_factors)))}"
                    )
            for cost_item in photo.get("costs", []):
                lines.append(
                    f"- Cost {_value(cost_item['record_id'])}: "
                    f"{_value(cost_item['classification'])}, "
                    f"{_number(cost_item.get('total'))}"
                )
            flip = photo["flip"]
            if flip is None:
                lines.append("- Flip: —")
            else:
                lines.append(
                    f"- Flip: {_value(flip['baseline_verdict'])} → "
                    f"{_value(flip['decisive_verdict'])}; "
                    f"{_value(flip['direction'])}; delta {_one_decimal(flip['composite_delta'])}"
                )
            if photo["stability"]:
                for item in photo["stability"]:
                    lines.append(
                        f"- Stability {_value(item['repeat_group'])}: "
                        f"{_value(item['class'])}, spread {_one_decimal(item['composite_spread'])}"
                    )
            else:
                lines.append("- Stability: —")
            lines.append("")
    else:
        lines.append("—")
        lines.append("")

    lines.extend(
        [
            "## Cost",
            "",
            f"- Currency: {_value(cost['currency'])}",
            f"- Known total: {_number(cost['known_total'])}",
            f"- Estimated total: {_number(cost['estimated_total'])}",
            f"- Unknown records: {_value(cost['unknown_records'])}",
            "",
            "| Stage | Known | Estimated | Unknown records |",
            "| --- | --- | --- | --- |",
        ]
    )
    if cost["by_stage"]:
        lines.extend(
            f"| {_value(stage)} | {_number(item['known_total'])} | "
            f"{_number(item['estimated_total'])} | {_value(item['unknown_records'])} |"
            for stage, item in cost["by_stage"].items()
        )
    else:
        lines.append("| — | — | — | — |")
    lines.extend(
        [
            "",
            "| Token category | Count |",
            "| --- | --- |",
        ]
    )
    token_totals = cost.get("token_totals", {})
    if token_totals:
        lines.extend(
            f"| {_value(category)} | {_value(count)} |"
            for category, count in token_totals.items()
        )
    else:
        lines.append("| — | — |")

    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {_value(warning)}" for warning in warnings) if warnings else lines.append("—")
    lines.extend(
        [
            "",
            "## Method",
            "",
            "Pairs require exactly one baseline and one decisive record per photo.",
            "Verdict order is reject, maybe, accept; lateral means an unchanged verdict with a material composite movement.",
            "Repeat stability uses profile v1: unstable for accept/reject disagreement or high spread, robust for identical verdicts with tight spread, and soft otherwise.",
            "",
            "## Provenance",
            "",
            f"- Schema version: {_value(audit['schema_version'])}",
            f"- Tool: {_value(audit['tool']['name'])} {_value(audit['tool']['version'])}",
            f"- Input SHA-256: {_value(run['input_sha256'])}",
            f"- Generated at: {_value(run['generated_at'])}",
            f"- Photo root: {_value(run['photo_root'])}",
            "",
        ]
    )
    return "\n".join(lines)


render = render_report
