# Cull audit report

## Summary

- Baseline stage: triage
- Decisive stage: dedicated
- Paired photos: 3
- Verdict flips: 2 / 3 (rate 0.6666666666666666; 66.7%)

## Coverage and exclusions

- Photos discovered: 0
- Baseline unique photos: 4
- Decisive unique photos: 4
- Paired photos: 3

| Photo | Exclusion | Observed stage counts |
| --- | --- | --- |
| duplicate.jpg | duplicate\_decisive | \{'triage': 1, 'dedicated': 2\} |

## Flip table

| Photo | Baseline | Decisive | Baseline composite | Decisive composite | Direction | Composite delta |
| --- | --- | --- | --- | --- | --- | --- |
| a.jpg | reject | maybe | 20.0 | 40.0 | upward | 20.0 |
| b.jpg | accept | reject | 80.0 | 20.0 | downward | -60.0 |
| c.jpg | maybe | maybe | 20.0 | 40.0 | lateral | 20.0 |

- Upward: 1
- Downward: 1
- Lateral: 1

| Transition | Count |
| --- | --- |
| accept\-\>reject | 1 |
| maybe\-\>maybe | 1 |
| reject\-\>maybe | 1 |

## Stability

- Threshold profile: v1
- Eligible groups: 3
- Robust: 1
- Soft: 1
- Unstable: 1

| Photo | Repeat group | Verdicts | Spread | Class |
| --- | --- | --- | --- | --- |
| robust.jpg | robust | maybe, maybe | 3.0 | robust |
| soft.jpg | soft | maybe, maybe | 10.0 | soft |
| unstable.jpg | unstable | accept, reject | 0.0 | unstable |

## Per-photo cards

### a.jpg

- Discovered: False
- Records: base/a, dec/a
- base/a composite: 20.0
- dec/a composite: 40.0
- Cost base/a: known, 0.1
- Cost dec/a: unknown, —
- Flip: reject → maybe; upward; delta 20.0
- Stability: —

### b.jpg

- Discovered: False
- Records: base/b, dec/b
- base/b composite: 80.0
- dec/b composite: 20.0
- Cost base/b: unknown, —
- Cost dec/b: unknown, —
- Flip: accept → reject; downward; delta -60.0
- Stability: —

### c.jpg

- Discovered: False
- Records: base/c, dec/c
- base/c composite: 20.0
- dec/c composite: 40.0
- dec/c reasons: clean silhouette
- dec/c kill factors: soft focus
- Cost base/c: unknown, —
- Cost dec/c: unknown, —
- Flip: maybe → maybe; lateral; delta 20.0
- Stability: —

### duplicate.jpg

- Discovered: False
- Records: base/duplicate, dec/duplicate, dec/duplicate\-2
- base/duplicate composite: 50.0
- dec/duplicate composite: 30.0
- dec/duplicate\-2 composite: 70.0
- Cost base/duplicate: unknown, —
- Cost dec/duplicate: unknown, —
- Cost dec/duplicate\-2: unknown, —
- Flip: —
- Stability: —

### estimated.jpg

- Discovered: False
- Records: estimated/one
- estimated/one composite: —
- Cost estimated/one: estimated, 0.2
- Flip: —
- Stability: —

### robust.jpg

- Discovered: False
- Records: repeat/robust\-0, repeat/robust\-1
- repeat/robust\-0 composite: 50.0
- repeat/robust\-1 composite: 53.0
- Cost repeat/robust\-0: unknown, —
- Cost repeat/robust\-1: unknown, —
- Flip: —
- Stability robust: robust, spread 3.0

### soft.jpg

- Discovered: False
- Records: repeat/soft\-0, repeat/soft\-1
- repeat/soft\-0 composite: 40.0
- repeat/soft\-1 composite: 50.0
- Cost repeat/soft\-0: unknown, —
- Cost repeat/soft\-1: unknown, —
- Flip: —
- Stability soft: soft, spread 10.0

### unknown.jpg

- Discovered: False
- Records: unknown/one
- unknown/one composite: —
- Cost unknown/one: unknown, —
- Flip: —
- Stability: —

### unstable.jpg

- Discovered: False
- Records: repeat/unstable\-0, repeat/unstable\-1
- repeat/unstable\-0 composite: 50.0
- repeat/unstable\-1 composite: 50.0
- Cost repeat/unstable\-0: unknown, —
- Cost repeat/unstable\-1: unknown, —
- Flip: —
- Stability unstable: unstable, spread 0.0

## Cost

- Currency: USD
- Known total: 0.1
- Estimated total: 0.2
- Unknown records: 15

| Stage | Known | Estimated | Unknown records |
| --- | --- | --- | --- |
| dedicated | 0 | 0 | 5 |
| estimated | 0 | 0.2 | 0 |
| repeat | 0 | 0 | 6 |
| triage | 0.1 | 0 | 3 |
| unknown | 0 | 0 | 1 |

| Token category | Count |
| --- | --- |
| input\_tokens | 1000000 |
| output\_tokens | 0 |
| thinking\_tokens | 0 |

## Warnings

- base/b: missing currency metadata
- base/b: missing model metadata
- base/c: missing currency metadata
- base/c: missing model metadata
- base/duplicate: missing currency metadata
- base/duplicate: missing model metadata
- dec/a: missing currency metadata
- dec/a: missing model metadata
- dec/b: missing currency metadata
- dec/b: missing model metadata
- dec/c: missing currency metadata
- dec/c: missing model metadata
- dec/duplicate\-2: missing currency metadata
- dec/duplicate\-2: missing model metadata
- dec/duplicate: missing currency metadata
- dec/duplicate: missing model metadata
- photo duplicate.jpg excluded from pairing: duplicate\_decisive
- repeat/robust\-0: missing currency metadata
- repeat/robust\-0: missing model metadata
- repeat/robust\-1: missing currency metadata
- repeat/robust\-1: missing model metadata
- repeat/soft\-0: missing currency metadata
- repeat/soft\-0: missing model metadata
- repeat/soft\-1: missing currency metadata
- repeat/soft\-1: missing model metadata
- repeat/unstable\-0: missing currency metadata
- repeat/unstable\-0: missing model metadata
- repeat/unstable\-1: missing currency metadata
- repeat/unstable\-1: missing model metadata
- unknown/one: missing currency metadata
- unknown/one: missing model metadata

## Method

Pairs require exactly one baseline and one decisive record per photo.
Verdict order is reject, maybe, accept; lateral means an unchanged verdict with a material composite movement.
Repeat stability uses profile v1: unstable for accept/reject disagreement or high spread, robust for identical verdicts with tight spread, and soft otherwise.

## Provenance

- Schema version: 1.0
- Tool: cull\-audit 0.1.0.dev0
- Input SHA-256: e10884fc7b7cb7a8d9adc5daaafc609da7c4c4b28ea64cd23e0059c7656fd0b9
- Generated at: 2023\-11\-14T22:13:20Z
- Photo root: —
