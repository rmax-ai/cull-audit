# Producer adapter template

This directory is a stdlib-only starting point for adapting a producer's own
scores to cull-audit judgment JSON Lines. The adapter does not call a provider,
read photos, calculate a score, or change a verdict. It copies the producer's
observations into the v1 record shape.

The input is JSON Lines with one object per model read. The object must contain
`record_id`, `photo_id`, and `verdict`; it may contain `stage`, `read_kind`,
`composite`, `scores`, `reasons`, `kill_factors`, `usage`, and `observed_at`.
For identical-setting repeats, include all three fields:

```json
{"record_id":"repeat-0001","photo_id":"set-a/IMG_0001.jpg","stage":"repeat","read_kind":"relative","verdict":"accept","composite":82,"repeat_group":"set-a/IMG_0001.jpg","repeat_index":0,"settings_fingerprint":"sha256:replace-with-your-fingerprint"}
```

`repeat_group` must identify one photo, `repeat_index` must start at zero, and
every member must use the same `settings_fingerprint`. Do not use a secret or
private source identifier as a fingerprint.

Convert and validate locally:

```bash
python producer_adapter.py --input scores.jsonl --output judgments.jsonl
python -m cull_audit validate --judgments judgments.jsonl
```

The emitted fields are documented in
[`schemas/judgments-1.0.schema.json`](../../schemas/judgments-1.0.schema.json).
The `validate` CLI is the contract check; this template deliberately does not
duplicate that validation logic.
