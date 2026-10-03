# Triage reference read

Prompt version: triage-v1

Review the supplied contact sheet as a relative comparison. Return JSON only,
with one object per supplied position. Each object must contain `photo_id`,
`verdict` (`accept`, `maybe`, or `reject`), `composite` from 0 to 100,
`scores`, `reasons`, and `kill_factors`.

Judge only visible image qualities and the comparison represented by this
sheet. Do not claim human ground truth. Keep the output generic and
machine-readable.
