# cull-audit build and launch plan

Status: proposed build plan for P1 (`cull-audit`) and P2 ("The Flip Table")  
Runtime target: Python 3.11+  
License: MIT  
Core dependency policy: Python standard library plus Pillow only

## 1. Positioning

### Problem statement

AI photo-culling products usually expose a verdict, score, or ranking as if it were a stable property of a photograph. The measured 121-photo run shows why that is unsafe: 28 of 33 contact-sheet triage verdicts changed when the same finalists received dedicated 1536 px reads, almost all downward, and the initial number-one pick became a reject. Repeating an identical read on the top eight then produced five robust and three unstable results; the rank-two selection moved `maybe → reject → maybe`. A shortlist without this evidence can conceal both context bias and model variance.

`cull-audit` is an open-source verification harness for those judgments: **evals for photo culling**. It does not try to make the best artistic selection. It measures whether another system's selection survives a more decisive view, repeated identical reads, and honest cost accounting. It can audit records exported by any culler without sending a photo anywhere, or optionally run a documented reference multi-pass with the user's Gemini API key.

### Why now

The mid-2026 open-source market already has many local-first judges—standalone cullers, Lightroom integrations, agent skills, and academic MLLM judging work. Shipping one more opinionated judge would enter a crowded category. The unserved layer is verification: no surveyed tool publishes flip evidence, repeat-read variance classes, and provider-usage cost in one reproducible artifact. At the same time, low-cost multimodal calls make repeated evaluation practical: the measured full four-pass program cost about $0.60 for 121 photos, and the first triage cost about $0.0004/photo. The marginal cost of skepticism is now small enough to become a normal pipeline stage.

### Audit-not-judge angle

The product promise is: **bring judgments; get evidence about their reliability**. Importing generic records is the primary path. The reference runner is an inspectable adapter and demonstration path, not the product's claim to superior taste. Reports discuss flips, disagreement, spread, missing data, and cost; they do not crown a universally “correct” aesthetic result. A decisive-read verdict is a comparison target, not ground truth.

### Target users

- Photographers already using an AI culler who want to know which picks deserve manual review.
- AI engineers building vision-ranking pipelines who need regression artifacts and provider-neutral evaluation contracts.
- Agent-tooling users who want a deterministic CLI that coding agents can run, test, and inspect locally.

### Name and description

**Recommended repository name:** `cull-audit` (keep the default; short, searchable, and accurately scoped).  
**One-line repository description:** “A local-first verification harness that measures flips, repeat-read stability, and cost in AI photo-culling pipelines.”

## 2. v1 scope

### M1 feature set (exact)

1. Discover a local photo folder, assign stable relative-path photo IDs, and report supported, unreadable, duplicate, and unreferenced inputs without altering them.
2. Import one JSON document or JSON Lines file containing provider-neutral judgment records conforming to contract version `1.0`.
3. Validate records with stdlib code: required fields, types, ranges, enums, unique record IDs, referenced photo IDs, and comparison/repeat grouping integrity. Emit path-addressed errors and a nonzero exit status.
4. Compare one named cheap/relative stage with one named decisive/absolute stage by photo ID; compute coverage, flip count/rate, upward/downward/lateral direction, and transition counts.
5. Group identical-configuration repeat reads, calculate verdict sequence and normalized composite spread, and classify each eligible group as robust, soft, or unstable with the fixed v1 thresholds below.
6. Parse explicit cost and token usage metadata without contacting a pricing service; preserve unknown cost rather than guessing.
7. Produce deterministic `audit.json` and a plain-language `report.md`, including a flip table, stability summary, per-photo cards, cost table, warnings, and provenance.
8. Provide the `cull-audit validate`, `audit`, and `demo` CLI subcommands; `demo` runs a small synthetic, image-free fixture so installation can be checked without a key or network.
9. Supply unit/fixture tests, reproducibility rules, MIT licensing, a task-oriented README, and minimal GitHub Actions CI for lint and tests on pushes and pull requests.

### Explicit non-goals for v1

- A new aesthetic model, “best photo” oracle, Lightroom replacement, gallery UI, DAM, face-recognition system, or SaaS service.
- Training, fine-tuning, benchmark-leaderboard claims, or declaring a decisive read to be human ground truth.
- Automatic deletion, movement, renaming, rating, or EXIF mutation of source photos.
- Provider support beyond the optional Gemini reference adapter; imported records remain provider-neutral.
- Live provider pricing lookup or inferred dollar totals based on unpinned/current prices.
- RAW decoding, video, burst alignment, perceptual duplicate detection, identity recognition, or multi-person face-quality attribution.
- Publishing any private-shoot image, crop, filename, prompt response, or per-photo record.
- A web dashboard, database, plugin system, distributed execution, or telemetry.

## 3. Data contracts and metrics

Contracts are committed as JSON Schema documents for documentation and ecosystem reuse, but runtime validation is implemented with the standard library; JSON Schema is not added as a dependency. Unknown fields are retained when round-tripping and ignored for v1 metrics, enabling forward-compatible producer metadata.

### Generic judgment record contract (`judgments.schema.json`, version 1.0)

An input is either `{ "schema_version": "1.0", "records": [...] }` or JSON Lines containing one record per line. JSON Lines support borrows the append-friendly, streamable interface used by mature Unix data tools. The top-level document form is canonical for fixtures and hashing.

```json
{
  "schema_version": "1.0",
  "records": [
    {
      "record_id": "triage/000042",
      "photo_id": "set-a/IMG_0042.jpg",
      "stage": "triage",
      "read_kind": "relative",
      "verdict": "maybe",
      "composite": 72.5,
      "scores": {"technical": 70.0, "composition": 75.0},
      "reasons": ["clean silhouette"],
      "kill_factors": [],
      "context": {
        "comparison_group": "sheet-05",
        "repeat_group": null,
        "repeat_index": null,
        "input_max_edge_px": 768,
        "prompt_id": "triage-v1",
        "model": "provider-model-name",
        "settings_fingerprint": "sha256:..."
      },
      "usage": {
        "input_tokens": 1000,
        "output_tokens": 120,
        "thinking_tokens": 80,
        "calls": 1,
        "cost": {"currency": "USD", "total": 0.0042, "source": "provider"}
      },
      "source": {"tool": "example-culler", "tool_version": "1.2.0"},
      "observed_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Required record fields are `record_id`, `photo_id`, `stage`, `read_kind`, `verdict`, and `source.tool`. IDs and stages are non-empty strings; `record_id` is unique in a run. `photo_id` is the POSIX-style path relative to the declared photo root, never an absolute path. `read_kind` is `relative`, `absolute`, `face_crop`, or `other`; `verdict` is exactly `accept`, `maybe`, or `reject`. `composite` and every `scores` value, when present, are finite numbers normalized to `[0,100]`. `reasons` and `kill_factors` are arrays of strings.

`context.comparison_group` identifies shared relative-read context and is informational for flip computation. `context.repeat_group` identifies reads made with identical photo bytes, crop, model, prompt, and generation settings; producers MUST also provide the same `settings_fingerprint` for every record in a repeat group. `repeat_index` is a zero-based integer unique within that group. The validator rejects mixed photo IDs or fingerprints within a repeat group.

Usage counters are non-negative integers and may be absent. `thinking_tokens` is separate only when the provider reports it separately; a producer MUST NOT duplicate thinking tokens already included in `output_tokens`. `usage.calls` defaults to one when a record represents a single response, otherwise it is required. Timestamps are provenance only and are excluded from deterministic metric comparisons.

### Audit command manifest

The `audit` command also receives a small manifest, either flags or JSON, that names `baseline_stage` and `decisive_stage`, input record paths, photo root, output directory, and optional pinned price table. The canonical configuration is embedded in `audit.json`. No stage is inferred from array order.

### Audit output contract (`audit.json`, version 1.0)

```json
{
  "schema_version": "1.0",
  "tool": {"name": "cull-audit", "version": "..."},
  "run": {
    "baseline_stage": "triage",
    "decisive_stage": "dedicated",
    "photo_root": ".",
    "input_sha256": "...",
    "generated_at": "..."
  },
  "coverage": {
    "photos_discovered": 0,
    "baseline_unique_photos": 0,
    "decisive_unique_photos": 0,
    "paired_photos": 0,
    "excluded_photos": []
  },
  "flips": {
    "paired": 0,
    "count": 0,
    "rate": null,
    "direction_counts": {"upward": 0, "downward": 0, "lateral": 0},
    "transitions": {},
    "items": []
  },
  "stability": {
    "threshold_profile": "v1",
    "eligible_groups": 0,
    "class_counts": {"robust": 0, "soft": 0, "unstable": 0},
    "items": []
  },
  "cost": {
    "currency": "USD",
    "known_total": 0.0,
    "estimated_total": 0.0,
    "unknown_records": 0,
    "by_stage": {},
    "token_totals": {}
  },
  "photos": [],
  "warnings": []
}
```

Each `flips.items` entry contains photo ID, both record IDs, both verdicts/composites, direction, and composite delta when both scores exist. Each `stability.items` entry contains photo ID, repeat group, ordered record IDs/verdicts/composites, repeat count, composite min/max/spread (or null), class, and machine-readable class reasons. Each `photos` entry joins all relevant findings for generation of a per-photo card. Arrays are sorted by photo ID then record/repeat ID, object keys are emitted in a fixed order, UTF-8 is used, and numeric output uses JSON numbers without display rounding. `generated_at` can be fixed via `SOURCE_DATE_EPOCH`; semantic reproducibility tests compare output after removing only that field.

`report.md` is a rendering of the same object, never a second metrics implementation. Its fixed sections are Summary, Coverage and exclusions, Flip table, Stability, Per-photo cards, Cost, Warnings, Method, and Provenance. Markdown escapes imported strings and uses `—` for unavailable values.

### Precise v1 metrics

**Pair selection.** A photo is eligible for flip analysis only when it has exactly one valid baseline record and exactly one valid decisive record for the configured stages. Duplicates are excluded with a warning rather than silently resolved. Coverage reports all exclusions.

**Flip.** Map verdicts to the ordinal `reject=0`, `maybe=1`, `accept=2`. A flip occurs when paired verdict strings differ. `flip_rate = flip_count / paired_photos`; it is JSON `null` when there are no pairs. A positive ordinal change is upward and a negative change is downward. “Lateral” is reserved for unchanged verdict with a material score movement and therefore is **not a flip**; in v1, material means `abs(decisive composite - baseline composite) > 15` when both composites exist. Transition counts use keys such as `maybe->reject`. The headline measured example is 28/33 verdict flips, not a generalized expected rate.

**Composite delta and spread.** A paired delta is `decisive - baseline`. For a repeat group, `composite_spread = max(composite) - min(composite)` across available normalized composites. Spread is null if fewer than two records contain composites. Values are calculated from unrounded inputs and displayed to one decimal in Markdown.

**Stability eligibility.** A repeat group needs at least two valid records, one photo ID, and one settings fingerprint shared by all records. Otherwise it is excluded and explained. With eligible verdicts and spread, rules are applied in this order, making classes exhaustive:

1. `unstable` if both `accept` and `reject` occur, **or** composite spread is greater than 15.
2. `robust` if every verdict is identical and composite spread is non-null and at most 5.
3. `soft` for every other eligible group, including adjacent verdict movement, identical verdicts with spread `(5,15]`, or missing score evidence.

The fixed thresholds are published as profile `v1`. A future configurable profile must receive a different name and be printed prominently; it may not silently change `v1`. Counts and percentages always state their eligible-group denominator.

**Cost parsing.** For each record, precedence is: (1) explicit `usage.cost.total` with source `provider` or `producer`; (2) sum explicit non-overlapping cost components supplied by the producer; (3) local calculation from token/call counters only when the user supplies a versioned price-table file whose model, currency, unit, and effective label match; (4) unknown. Explicit totals are `known`; table-derived values are `estimated` and never merged into the known subtotal. No network lookup occurs. Decimal strings from price tables are computed with `decimal.Decimal` and serialized as decimal JSON numbers. Cost summaries expose known, estimated, and unknown-record counts by stage; they never turn missing values into zero. Token summaries keep input, output, and thinking categories separate and carry a warning when provider semantics could overlap. This makes the measured observation that output tokens including thinking were about 80% of cost reportable without encoding it as a universal assumption.

## 4. Architecture and repository design

### Borrowed interface ideas

- **SARIF's run/result separation:** borrow the mature static-analysis pattern of one run-level provenance/configuration object plus many addressable findings. Here, photos and flip/stability items play the role of results. The format is deliberately smaller than SARIF and is not claimed to be SARIF-compatible.
- **Git's porcelain/plumbing distinction:** the human `report.md` and friendly CLI are stable “porcelain”; normalized JSON and pure metric functions are composable “plumbing.” JSON goes to files and diagnostics to stderr.
- **PyPA CLI conventions:** use `pyproject.toml`, a console-script entry point, `--version`, `--help`, explicit exit codes, and `python -m cull_audit` parity.
- **Unix/NDJSON conventions:** accept stdin with `-`, JSON Lines for streaming, stdout only when explicitly selected, and deterministic nonzero statuses rather than prose-only failures.

### Module layout

```text
src/cull_audit/
  __init__.py          version only
  __main__.py          python -m entry
  cli.py               argparse surface and exit codes
  contracts.py         validation and normalized dataclasses
  discover.py          safe photo discovery and Pillow checks
  ingest.py            JSON/document/JSONL readers
  metrics.py           pure flip and stability calculations
  costs.py             usage parsing and pinned price tables
  audit.py             orchestration and output model
  render.py            audit.json -> report.md only
  reference/
    gemini.py           urllib transport, retries, response capture
    passes.py           triage/dedicated/face/repeat orchestration
    images.py           contact sheets, resize, bbox crop
tests/
  fixtures/            tiny generated images and static records
  test_*.py             unittest suite
schemas/
  judgments-1.0.schema.json
  audit-1.0.schema.json
examples/
  synthetic/            keyless demo records and expected outputs
  open-demo/             manifest, licenses, acquisition instructions
tools/lint.py            dependency-free repository checks
.github/workflows/ci.yml
README.md
LICENSE
CONTRIBUTING.md
SECURITY.md
CHANGELOG.md
pyproject.toml
```

### CLI surface

```text
cull-audit validate --judgments PATH [--photos DIR] [--format text|json]
cull-audit audit --photos DIR --judgments PATH --baseline-stage NAME
                 --decisive-stage NAME --output DIR [--prices PATH]
                 [--source-date-epoch UNIX_SECONDS] [--strict]
cull-audit demo --output DIR
cull-audit reference run --photos DIR --output DIR --model NAME
                         [--passes triage,dedicated,face,repeat]
                         [--finalists N] [--repeat-top N] [--dry-run]
```

Exit codes are `0` success, `2` CLI misuse, `3` contract/coverage failure, `4` local I/O/image failure, and `5` provider failure. API keys come only from a documented environment variable, are never accepted as flags, logged, written to artifacts, or included in error bodies. `reference run` is M2; M1 help may omit it entirely rather than expose a stub.

Photo discovery permits `.jpg`, `.jpeg`, `.png`, `.webp`, and `.tif/.tiff` that Pillow can decode. It does not follow symlinked directories, sorts normalized relative paths, hashes bytes with SHA-256 in chunks, and opens images read-only. Duplicate bytes are reported but not removed.

### README sketch

1. One-sentence audit-not-judge promise and a compact sample flip/stability summary.
2. “What this proves / what it does not prove.”
3. Install on Python 3.11+, then a keyless `cull-audit demo` quick start.
4. Audit records from another tool, with the smallest valid producer example.
5. Read `audit.json` and `report.md`; definitions and denominators.
6. Optional Gemini reference run, privacy warning, expected network/cost behavior, and dry-run.
7. Data contracts and producer integration guide.
8. Local-first/privacy/security statement; no telemetry.
9. Reproducing the open demo and verifying licenses.
10. Limitations, roadmap, contributing, citation, and MIT license.

### CI and quality gate

GitHub Actions runs on pushes and pull requests using Python 3.11 and the newest supported stable Python. It installs the package with Pillow, runs `python tools/lint.py` (compile checks, trailing whitespace, schema/example JSON parsing, forbidden dependency scan), `python -m unittest discover -s tests -v`, and the keyless demo twice with semantic output comparison. Networked/provider tests are excluded from CI. No formatter or test framework is added as a runtime or development dependency.

## 5. Milestones and task breakdown

Tasks below are issue-ready, independently assignable after their dependencies, and deliberately keep an agent's edit surface narrow. Sizes: S is roughly up to 3 agent-hours, M is 3–6, and L is 6–10 including tests and review.

| ID | Milestone | Task / size | Scope | Deterministic acceptance criteria | Dependencies |
|---|---|---|---|---|---|
| T01 | M1 | Scaffold packaging and quality gate / S | Create the `src/` package, `pyproject.toml`, console entry point, stdlib lint script, unittest layout, and push/PR CI. Pin Python `>=3.11` and allow only Pillow as a third-party dependency. Add `python -m` parity and documented exit constants. | `python -m pip install -e .` succeeds in a clean 3.11+ environment; `cull-audit --version` equals `python -m cull_audit --version`; `python tools/lint.py` and `python -m unittest discover -s tests -v` exit 0; a dependency scan finds no third-party requirement except Pillow. | None |
| T02 | M1 | Specify and validate judgment records / M | Commit both versioned schema documents, Python normalization types, JSON and JSONL ingestion, path-addressed validation errors, stdin support, and the `validate` subcommand. Preserve unknown fields while enforcing the v1 invariants and safe relative photo IDs. | Golden valid document and JSONL fixtures exit 0 and normalize identically; fixtures for duplicate IDs, absolute/escaping paths, NaN/out-of-range scores, bad enums, mixed repeat fingerprints, and malformed JSON each exit 3 and match checked-in JSON diagnostics; all contract tests pass without a JSON-schema library. | T01 |
| T03 | M1 | Add deterministic photo discovery / S | Implement supported-extension discovery, Pillow decode verification, byte hashing, symlink policy, and duplicate/unreadable/unreferenced reporting. Do not mutate images or metadata. | A generated fixture tree produces the checked-in ordered manifest on Linux; symlinked directories are not traversed; identical-byte files are flagged; corrupt supported files are reported; before/after hashes and mtimes of all fixture inputs match. | T01 |
| T04 | M1 | Implement flip and stability metrics / M | Build pure functions for stage pairing, exclusions, verdict transitions/directions, material lateral moves, repeat eligibility, composite spread, and the fixed v1 robust/soft/unstable rules. Include denominator fields and machine-readable reasons. | Table-driven tests cover every transition, boundary spreads `5`, just over `5`, `15`, and just over `15`, accept/reject override, null scores, duplicate stage records, zero pairs, sorting, and the synthetic `28/33` calculation; mutation of input objects is rejected by an equality test. | T02 |
| T05 | M1 | Implement auditable cost parsing / M | Normalize provider/producer totals, explicit components, token counters, and optional Decimal-based pinned price tables. Keep known and estimated subtotals separate, preserve unknowns, and warn about ambiguous thinking-token semantics. | Fixtures exercise each precedence branch, currency/model mismatch, missing usage, component overlap rejection, decimal arithmetic, and thinking-token warnings; no test makes a network request; `0` explicit cost remains known while absent cost remains unknown. | T02 |
| T06 | M1 | Assemble audit output and Markdown report / L | Join discovery, normalized records, metrics, and costs into deterministic `audit.json`; render all required `report.md` sections from that JSON only, including flip table, stability summary, kill factors, per-photo cards, cost, warnings, method, and provenance. Wire the `audit` subcommand and atomic output writes. | End-to-end fixture output matches checked-in golden JSON and Markdown; reruns with fixed `SOURCE_DATE_EPOCH` are byte-identical; report numbers are cross-checked against JSON by tests; invalid input leaves no partial final outputs; CLI exit codes match the specification. | T03, T04, T05 |
| T07 | M1 | Ship keyless demo and M1 user documentation / M | Create an image-free synthetic demo representing upward/downward flips, all stability classes, known/estimated/unknown cost, and exclusions. Write the M1 README sections, producer guide, privacy model, limitations, MIT notice, and a copy/paste quick start. | In a fresh environment, the documented commands run `cull-audit demo --output TMP`, produce nonempty valid `audit.json` and `report.md`, and pass a scripted assertion for at least one item of every intended class; README link checker finds no broken relative links; no fixture resembles or derives from the private shoot. | T06 |
| T08 | M2 | Build safe Gemini transport and usage capture / M | Using `urllib` only, implement request construction, timeouts, bounded retry for retryable status codes, redacted errors, response retention, usage parsing, dry-run estimates, and an injectable transport for offline tests. The API key is environment-only. | Mock-server tests verify payloads, timeout, retry cap, non-retryable failure, usage capture, response parsing, and that a sentinel key never appears in stdout, stderr, exceptions, or artifacts; `--dry-run` sends zero HTTP requests. | T02, T05 |
| T09 | M2 | Implement reference image passes / L | Add deterministic contact sheets of nine, dedicated 1536 px reads, bbox validation plus 40%-margin clamped face crops, and identical-setting repeat reads. Emit only generic judgment records and explicit pass provenance. Finalist and repeat selection are deterministic and configurable; prompts are versioned files. | Generated-image tests verify nine-up order, 1536 px maximum-edge behavior, crop clamping and exact 40% margin where unclamped, stable settings fingerprints, deterministic finalist order, repeat-group invariants, and byte-identical prepared inputs across reruns; mocked end-to-end run emits schema-valid records. | T03, T08 |
| T10 | M2 | Curate and license an open-photo demo set / M | Select roughly 60–120 openly licensed photos from the approved candidate sources, retain source URL/creator/license/attribution per asset, document acquisition and checksum verification, and keep redistribution decisions explicit. Do not mix private-shoot artifacts into the repository or article. | Manifest schema validates; every asset row has a source URL, creator when supplied, license identifier, attribution text, SHA-256, and redistribution flag; a script reports zero missing license fields and verifies downloaded checksums; reviewer can trace every redistributed file to its source record. | T01 |
| T11 | M2 | Run and freeze the public reference demo / M | Run the multi-pass reference pipeline with a user-owned key on the licensed set, preserve raw generic records and usage metadata, then generate the public audit and a reproducibility note. Treat results as a demonstration, not a universal benchmark. | `validate` passes all records; `audit` reruns to the committed semantic golden output; the report contains paired flip coverage, direction counts, all observed stability classes, composite spread, known/estimated/unknown cost, and no secret; secret-pattern and private-filename scans exit 0. | T07, T09, T10 |
| T12 | M3 | Prepare public repository release and community hooks / M | Finish security/contribution guidance, issue and pull-request templates, producer-adapter template, changelog, citation metadata, release checklist, and `v0.1.0` notes. Audit dependency, privacy, license, and repository history before changing visibility; the operator performs the actual public switch. | CI is green on the release commit; clean-clone quick start passes; `LICENSE` is MIT; package metadata and docs say `v0.1.0`; repository scan finds no key/private-shoot marker; templates render; release checklist records operator approval for visibility change. | T11 |
| T13 | M3 | Write “The Flip Table” launch article / M | Draft the dense rmax.ai article from aggregate verified measurements and abstract diagrams only. Include cost and method tables, explain audit-not-judge positioning, link to the release, and explicitly bound the n=1 evidence. Use the existing Codex-driven `rmax-ai.github.io` PR workflow only after the repo URL is public. | Source contains every receipt in the outline below; automated scan finds no image embed, private filename, photo ID, face/crop asset, or raw per-photo record; all arithmetic assertions pass; preview build succeeds in the publishing repo; human privacy review is checked off. | T11, T12 |
| T14 | M3 | Coordinate launch and post-launch intake / S | Publish in order, verify public install/docs links, open labeled issues for provider adapters and datasets, and create a bounded support/triage cadence. Capture bugs separately from requests that turn the project into a culler. | Public release checksum/tag resolves; article links return success; a clean install runs the demo; issue labels/templates exist for `adapter`, `dataset`, `metrics`, and `scope/non-goal`; launch checklist timestamps repo-public before article-public. | T12, T13 |

### Milestone exit gates

**M1 — usable imported-record audit + first synthetic demo.** T01–T07 complete; a new user can install, validate generic records, audit a folder, and inspect deterministic JSON and Markdown without a network connection. The demo proves mechanics, not model quality.

**M2 — reference multi-pass + licensed public demo.** T08–T11 complete; a user can opt into Gemini calls with their own key, and maintainers can reproduce a public, licensed demonstration with cost provenance. Network behavior stays outside default CI.

**M3 — public launch + article + community intake.** T12–T14 complete; repository privacy review passes before visibility changes, `v0.1.0` is public, then the article is merged and published, then community requests are triaged against the non-goals.

## 6. Public demo plan

Target roughly 60–120 photos, large enough to expose disagreement while remaining inspectable and close to the measured program's scale. Candidate sources, subject to per-asset verification:

1. **Wikimedia Commons**, filtering to files with clear CC0, CC BY, or CC BY-SA pages and preserving each file's attribution/license metadata.
2. **Flickr Commons / Flickr Creative Commons**, only where the individual asset page exposes a compatible license and stable author/source record; avoid “all rights reserved” and ambiguous status.
3. **Unsplash**, preferably acquisition-by-script with source links rather than repository redistribution, because its custom license and API/hotlink terms need explicit review even though use is broadly permitted.

Prefer one coherent, burst-like or event-like set from Wikimedia/Flickr over a random stock collage: flips are more meaningful when frames compete. If no single set supplies enough frames, document subsets and never imply they came from one shoot. The manifest is the authority; any unclear asset is excluded.

Budget **approximately $0.30–$0.50 in API usage** for the open demo, deliberately stated as an estimate rather than derived from unpublished pricing. Run `--dry-run` first, use the same documented model/settings within repeat groups, save provider usage, and stop at a configured call ceiling. This estimate is plausible relative to the verified ~$0.60/121-photo full program but is not a guarantee.

The demo audit must prove that the tool can: ingest and pair stages; reveal whether relative reads flip under dedicated reads and in which direction; separate robust, soft, and unstable repeat groups; show per-photo verdict/composite spread; account for known, estimated, and unknown cost honestly; disclose exclusions; reproduce aggregate outputs; and do all this without presenting the decisive pass as human truth. It need not reproduce 28/33 or 5/3; those are private-run receipts, not acceptance targets.

## 7. P2 article: “The Flip Table”

### Outline and receipts

1. **The number-one pick became a reject.** Open with the single concrete reversal, then frame the thesis: a single AI culling score is a sample, not a fact. Receipt: triage number-one to dedicated-read reject; no photo or record shown.
2. **What was actually run.** Abstract four-pass diagram: 121 photos → 14 nine-photo contact sheets → 33 dedicated finalists → 21 face enrichments → repeat reads on top eight. Receipt: pass shapes and model name for triage, with no private imagery.
3. **The flip table.** Aggregate transition diagram/table for the headline 28 of 33 changed verdicts, almost all downward. Explain relative versus absolute reads and the flattering-context hypothesis as an inference, not proven causality.
4. **Ranking is not stability.** Show an abstract sequence `maybe → reject → maybe` and class counts `5 robust / 3 unstable` for the top eight. Receipt: rank-two behavior and measured counts; define spread/classes while distinguishing the harness's published v1 thresholds from historical labels if necessary.
5. **Skepticism was cheap.** Cost table: triage about $0.0004/photo; dedicated reads $0.16261 for 33; face enrichment $0.128 for 21 photos/42 calls; stability $0.0614/12 calls; whole 121-photo program about $0.60. Receipt: output tokens including thinking about 80% of cost. Do not fabricate unmeasured pass subtotals.
6. **The missing product is an audit.** Summarize the already-completed market scan: many OSS judges, none in the scan shipping flip evidence + repeat variance + transparent cost. Avoid exhaustive superiority claims; date the observation to mid-2026.
7. **The contract, not another oracle.** Explain generic imported judgments, `audit.json`, `report.md`, provider-neutral metrics, local-first operation, and optional bring-your-own-key reference run. Include an abstract data-flow diagram.
8. **What this evidence cannot say.** State n=1 shoot/model/prompt limits, no human-ground-truth claim, provider drift, aesthetic subjectivity, and why the public demo is demonstration rather than benchmark.
9. **Run it, inspect it, challenge it.** Link the public `v0.1.0` repository, keyless demo, schemas, open-demo manifest, contribution guide, and narrowly scoped calls for adapters/datasets/metric critique.

### Article constraints

Use only the verified aggregate numbers in this plan. Include no private-shoot image, contact sheet, crop, thumbnail, filename, prompt response, record excerpt, identifying metadata, or per-photo card. Diagrams must be newly drawn abstract boxes/arrows with invented non-photo identifiers, never transformations of private assets. The article may link to per-photo records from the separately licensed public demo only if they are clearly labeled as that demo; the safer v1 default is aggregate public-demo output. No provider-price claim beyond recorded usage metadata. No claim that the 121-photo result generalizes statistically.

### Launch sequence

1. Freeze M2 demo records and aggregate receipts; complete privacy/license review.
2. Complete T12, make the repository public, tag `v0.1.0`, and verify its clean-clone path.
3. Update the article's links to immutable tag/schema/demo URLs and run the no-private-material scan.
4. Open a PR through the existing `rmax-ai.github.io` Codex publish workflow; review the built preview.
5. Publish the article only after the repository is reachable, then perform T14 link/install checks.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Stability metrics are gameable through convenient thresholds, repeat selection, or changed settings. | Freeze and version the v1 thresholds; disclose denominators and selected population; require identical settings fingerprints; show raw verdict sequences/spreads; label non-v1 profiles. |
| API/model variance changes results or breaks the reference runner. | Record exact model/prompt/settings and response usage, retain generic raw records, isolate transport adapters, use offline contract tests, and describe reruns as new runs rather than overwriting history. |
| Scope creeps into “build a better culler.” | Keep import/audit as the primary workflow, isolate the reference runner, enforce explicit non-goals in issue templates, and label aesthetic-ranking requests `scope/non-goal`. |
| Open-demo licensing or attribution is incomplete. | Maintain a per-asset manifest and checksums, prefer clearly licensed Commons assets, acquire rather than redistribute where needed, require human license review, and remove any ambiguous asset before launch. |
| The n=1 private result is mistaken for general evidence. | State its sample/model/prompt boundaries beside every headline number; make no accuracy claim; publish reproducible methods and a separate licensed demo; invite independent datasets. |
| Maintainer burden expands across providers and formats. | Stabilize one small contract, require fixture-backed community adapters, support only Gemini in core v1, automate compatibility tests, and publish a bounded triage cadence. |

## 9. Cost and effort estimates

Agent-hours are planning ranges including implementation, tests, docs, and one review pass; operator time for decisions, credentials, licensing judgment, repository visibility, and publication approval is separate. API dollars cover planned development/demo runs, not CI (which stays offline) or community use.

| Milestone | Included tasks | Agent-hours | API dollars | Notes |
|---|---|---:|---:|---|
| M1 | T01–T07 | 30–44 | $0 | Synthetic/keyless fixtures only; no provider calls needed. |
| M2 | T08–T11 | 24–36 | ~$0.30–$0.50 primary demo; cap total iteration budget at $2 | Mock transport for development, then one licensed-set run plus limited corrections. The cap is operational, not a predicted spend. |
| M3 | T12–T14 | 14–22 | $0–$0.50 | Reuse frozen receipts; allowance only if one explicitly approved verification rerun is necessary. |
| **Total** | T01–T14 | **68–102** | **expected ~$0.30–$1.00; hard planned cap $2.50** | Excludes the already measured private run and hosting, which uses the existing site workflow. |

The large effort range reflects provider integration and license review more than algorithmic complexity. If schedule pressure appears, preserve M1 contract/metrics/report quality and defer face-crop support in the reference runner; do not weaken cost provenance or privacy checks.

## 10. Open questions for the operator

1. **Should v0.1 accept redistributed demo images or download them from sources?** Recommended default: commit only a license/source/checksum manifest and an acquisition script unless every selected asset has an unambiguous redistribution grant; commit generated tiny test fixtures separately.
2. **Which exact Gemini model should the public reference runner default to?** Recommended default: require an explicit `--model` for real runs and document the measured `gemini-3-flash-preview` triage provenance; add a default only after the operator pins a tested model at release time.
3. **Should decisive and repeat-read prompts from the private pipeline be published verbatim?** Recommended default: publish new, versioned reference prompts that express the method without copying private-skill content, and disclose that they are not necessarily the historical prompts.
4. **Should the public demo include its generic per-photo records?** Recommended default: yes, only for the independently licensed demo, after metadata/privacy review; keep the article itself aggregate-first and never include private-run records.
5. **What is the minimum release bar if the open demo shows few or no flips?** Recommended default: publish the valid result unchanged if the harness demonstrates coverage, repeats, spread, and cost; never tune the dataset or thresholds to manufacture a dramatic flip rate.

## Definition of launch-ready

Launch is ready when all milestone gates pass, the public demo is reproducible and fully licensed, CI is green, known versus estimated versus unknown cost remains distinguishable, the repository contains no private-shoot material or secret, an operator has approved the public visibility change, and the article preview passes both receipt verification and the explicit no-private-images/no-private-records review. The success criterion is a trustworthy verification layer—not a flattering benchmark result.
