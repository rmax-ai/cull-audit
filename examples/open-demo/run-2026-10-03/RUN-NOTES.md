# Public reference demo run

- Date: 2026-10-03 UTC
- Model: `gemini-3-flash-preview`
- Parameters: `--passes triage,dedicated,face,repeat --finalists 21 --repeat-top 8`
- Provider calls: **67** = 9 triage + 21 dedicated + 21 face + 16 repeat
- Judgment records: 135
- Wall clock: 2026-10-03T11:29:05Z to 2026-10-03T12:03:28Z
- Duration: 2,063 seconds (34 minutes 23 seconds)
- Audit `SOURCE_DATE_EPOCH`: `1791029022`

The photo set was verified locally before the run: 77 assets, 77 verified,
0 missing, and 0 mismatched. The dry-run reported exactly 67 provider calls
and sent no HTTP requests. The live run was one attempt.

## Corrections applied before freeze (2026-10-03)

Two corrections were applied before this freeze; raw evidence is preserved
next to the run (`judgments.pre-normalization.json`, `responses/`, `audit2/`):

1. **Triage usage attribution.** The reference runner attached the full
   contact-sheet call usage to every per-photo record from that sheet (one
   call covers 9 photos), so a naive audit sum counted each sheet call 9x —
   triage estimated $0.6737385 instead of $0.0775845. The frozen
   `judgments.json` keeps the call usage on the first record of each sheet
   group only (68 duplicate attributions removed; no token or value was
   modified). The emission bug is tracked for a runner fix in the repository.
2. **Audit artifact regeneration.** The audit was regenerated from the
   corrected records with the stock CLI so the frozen `audit.json` and
   `report.md` match the published cost schema exactly. No extra keys are
   present in the frozen artifacts.

Resulting frozen audit cost: estimated **$0.273687** total; 67 records carry
attributed usage; the 68 triage sibling records report unknown (they have no
billed call of their own) — known records are zero.

## Exact commands

Commands were run from the repository root. The dry-run and live output paths
were confirmed absent before use; no destructive cleanup command was used.
The API key was loaded into `CULL_AUDIT_GEMINI_API_KEY` at run time from the
operator secret store (`pass`, entry `hermes/gemini/api-key`); the value was
never written to disk or logs (verified by scan).

```bash
.venv-accept/bin/python tools/open_demo_fetch.py verify \
  --manifest examples/open-demo/manifest.json \
  --dir /home/rmax-10/.local/share/cullaudit-opendemo/photos

.venv-accept/bin/cull-audit reference run \
  --photos /home/rmax-10/.local/share/cullaudit-opendemo/photos \
  --output /tmp/ca-t11-dry-check \
  --model gemini-3-flash-preview \
  --passes triage,dedicated,face,repeat \
  --finalists 21 \
  --repeat-top 8 \
  --dry-run

# load CULL_AUDIT_GEMINI_API_KEY from the operator secret store, then:
.venv-accept/bin/cull-audit reference run \
  --photos /home/rmax-10/.local/share/cullaudit-opendemo/photos \
  --output /home/rmax-10/.local/share/cullaudit-opendemo/run \
  --model gemini-3-flash-preview \
  --passes triage,dedicated,face,repeat \
  --finalists 21 \
  --repeat-top 8

.venv-accept/bin/cull-audit validate \
  --judgments /home/rmax-10/.local/share/cullaudit-opendemo/run/judgments.json

.venv-accept/bin/cull-audit audit \
  --judgments /home/rmax-10/.local/share/cullaudit-opendemo/run/judgments.json \
  --baseline-stage triage \
  --decisive-stage dedicated \
  --photos /home/rmax-10/.local/share/cullaudit-opendemo/photos \
  --prices /home/rmax-10/.local/share/cullaudit-opendemo/price-table.json \
  --output /home/rmax-10/.local/share/cullaudit-opendemo/run/audit \
  --source-date-epoch 1791029022
```

For a reproduction, stage the same verified 77-photo directory and pinned
price table, run the dry-run first, and proceed with the live command only
under the same approved provider budget. Use one `SOURCE_DATE_EPOCH` value
for audit reruns; identical inputs reproduce byte-identical `audit.json` and
`report.md` (verified twice for the frozen revision).

## Usage totals (attributed once per provider call)

| Token category | Count |
| --- | ---: |
| input | 80,928 |
| output | 18,559 |
| thinking | 59,182 |

## Cost block from `audit.json`

```json
"cost": {
  "currency": "USD",
  "known_total": 0,
  "estimated_total": 0.273687,
  "unknown_records": 68,
  "by_stage": {
    "dedicated": {
      "known_total": 0,
      "estimated_total": 0.102256,
      "known_records": 0,
      "estimated_records": 21,
      "unknown_records": 0
    },
    "face": {
      "known_total": 0,
      "estimated_total": 0.0537015,
      "known_records": 0,
      "estimated_records": 21,
      "unknown_records": 0
    },
    "repeat": {
      "known_total": 0,
      "estimated_total": 0.040145,
      "known_records": 0,
      "estimated_records": 16,
      "unknown_records": 0
    },
    "triage": {
      "known_total": 0,
      "estimated_total": 0.0775845,
      "known_records": 0,
      "estimated_records": 9,
      "unknown_records": 68
    }
  },
  "token_totals": {
    "input_tokens": 80928,
    "output_tokens": 18559,
    "thinking_tokens": 59182
  }
}
```

The pinned rate basis is
`examples/open-demo/price-table-gemini-3-flash-preview-2026-10.json`:
USD 0.50 per million input tokens, USD 3.00 per million output tokens, and
USD 3.00 per million thinking tokens, effective 2026-10-03. The audit used
local Decimal calculations from this table. 67 records are estimated; known
records are zero; 68 triage sibling records are unknown by attribution.

Event-set demonstration, not a benchmark; no human ground truth claimed; no
provider-price claim beyond the pinned table.
