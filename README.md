# cull-audit

`cull-audit` is a local-first verification harness for AI photo-culling
judgments: **bring a culler's judgments and get evidence about their
reliability, not a new artistic judge**.

The keyless synthetic demo is intentionally small, but it reports one upward
flip, one downward flip, one lateral material move, and one robust, soft, and
unstable repeat group. It also includes known, estimated, and unknown cost
records, an exclusion, and warnings.

## 1. What this proves, and what it does not

### What this proves

The M1 pipeline can:

- validate provider-neutral JSON or JSON Lines judgment records;
- pair named baseline and decisive stages by stable `photo_id`;
- report verdict flips, direction, material lateral moves, and exclusions;
- classify eligible identical-configuration repeat groups;
- separate explicit known costs, local table-based estimates, and unknowns;
- write deterministic `audit.json` and a Markdown report without reading or
  uploading photos.

The built-in demo proves these mechanics with invented records. It is a
smoke test for installation and pipeline behavior, not a model evaluation.

### What this does not prove

It does not identify the best photograph, establish human ground truth, or
show that a decisive read is objectively correct. A flip is evidence that two
configured reads disagreed. A stability class describes the supplied repeats,
not the universal reliability of a model. Results depend on the producer,
model, prompt, settings, input population, and selected stages.

## 2. Install and run the keyless demo

Use Python 3.11 or newer. The only runtime dependency beyond the standard
library is Pillow, used by optional local photo discovery.

With `pip`:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

With `uv`:

```bash
uv venv
uv pip install -e .
```

Run the image-free demo. The output directory is created when necessary:

```bash
cull-audit demo --output tmp/demo
```

The command writes `tmp/demo/audit.json` and `tmp/demo/report.md`. The same
command is available through the module entry point:

```bash
python -m cull_audit demo --output tmp/demo-module
```

Demo output is byte-identical across runs by default. The demo uses the
documented `DEFAULT_SOURCE_DATE_EPOCH` constant in
`src/cull_audit/demo.py` unless `SOURCE_DATE_EPOCH` is set. Set that
environment variable when you want a different, explicitly pinned
provenance timestamp.

## 3. Audit records from another tool

The primary workflow imports records from an existing culler. The smallest
valid producer document is:

```json
{
  "schema_version": "1.0",
  "records": [
    {
      "record_id": "triage/0001",
      "photo_id": "set-a/IMG_0001.jpg",
      "stage": "triage",
      "read_kind": "relative",
      "verdict": "maybe",
      "source": {"tool": "my-culler"}
    },
    {
      "record_id": "dedicated/0001",
      "photo_id": "set-a/IMG_0001.jpg",
      "stage": "dedicated",
      "read_kind": "absolute",
      "verdict": "accept",
      "source": {"tool": "my-culler"}
    }
  ]
}
```

Save it as `judgments.json`, then validate and audit it:

```bash
cull-audit validate --judgments judgments.json
cull-audit audit \
  --judgments judgments.json \
  --baseline-stage triage \
  --decisive-stage dedicated \
  --output tmp/audit
```

Add `--photos PATH` to discover local `.jpg`, `.jpeg`, `.png`, `.webp`,
`.tif`, or `.tiff` files and report unreadable, duplicate, unreferenced, and
missing inputs. Photo discovery never changes the files. Add `--prices PATH`
only when you have a versioned local price table; there is no live pricing
lookup. `--source-date-epoch UNIX_SECONDS` or `SOURCE_DATE_EPOCH` pins
provenance for reproducible artifacts.

JSON Lines is also accepted when the input path ends in `.jsonl` or `.ndjson`.
Each non-empty line is one judgment record. Records must use safe relative
POSIX photo IDs, and each `record_id` must be unique within the input.

## 4. Reading `audit.json` and `report.md`

`audit.json` is the machine-readable source of truth. `report.md` is a
plain-language rendering of that same object; it does not calculate a second
set of metrics.

### Flip definitions and denominator

For the configured stages, a photo is paired only when it has exactly one
valid record in each stage. Missing or duplicate stage records are excluded
and listed with their observed counts. The flip denominator is
`flips.paired`. A verdict flip is a changed verdict, and
`flips.rate` is `flips.count / flips.paired` (or `null` when there are no
pairs). Verdict order is `reject`, `maybe`, `accept`: a positive move is
`upward`, and a negative move is `downward`.

An unchanged verdict with an absolute composite change greater than 15 is a
`lateral` material move. Lateral moves are reported in
`direction_counts`, but are not counted as verdict flips.

### Stability definitions and denominator

The stability denominator is `stability.eligible_groups`. A group needs at
least two records for one photo and one shared `settings_fingerprint`.
Excluded groups are warnings rather than eligible findings. Profile `v1`
classifies a group as:

- **robust** when all verdicts match and composite spread is at most 5;
- **unstable** when both `accept` and `reject` occur, or spread is greater
  than 15;
- **soft** for every other eligible group.

Spread is the maximum minus minimum available composite. Missing composite
evidence can therefore produce a soft group, but never an invented score.

### Cost definitions

An explicit provider or producer total, or non-overlapping explicit
components, is **known**. A value calculated locally from a matching,
versioned price table is **estimated**. Records without usable cost evidence
are **unknown**. Known and estimated totals stay separate, and missing cost
is never silently treated as zero. Token totals preserve input, output, and
thinking categories separately.

## 5. Optional reference image runner

The reference runner is an opt-in Gemini workflow. It prepares deterministic
contact sheets and reads, then writes generic judgment records that can be
validated and audited like records from any other culler. Use your own key;
the runner never accepts an API key as a command-line argument:

```bash
export CULL_AUDIT_GEMINI_API_KEY='your-key'
cull-audit reference run \
  --photos path/to/photos \
  --output tmp/reference \
  --model gemini-2.5-flash \
  --passes triage,dedicated,face,repeat \
  --finalists 12 \
  --repeat-top 3
```

Run the plan first without a key or network request:

```bash
cull-audit reference run \
  --photos path/to/photos \
  --output tmp/reference-plan \
  --model gemini-2.5-flash \
  --dry-run
```

The command writes `judgments.json`, deterministic prepared inputs under
`prepared/`, and redacted raw provider response attempts under `responses/`.
`--finalists` selects the highest triage composites with photo-ID tie-breaks;
`--repeat-top` selects the highest dedicated composites. `validate` uses the
same judgment contract validation as the runner.

Only a non-dry `reference run` contacts Gemini. `validate`, `audit`, `demo`,
photo discovery, and local image preparation make no network requests or
telemetry calls. The reference run sends the selected photos to the provider,
so review the output and privacy implications before sharing it.

There are no pricing claims or live price lookups. The API usage reported by
Gemini is retained in each judgment record when supplied; any provider charge
is the user's responsibility under the user's own key.

## 6. Data contracts and producer integration

The version 1 judgment contract is documented in
[`schemas/judgments-1.0.schema.json`](schemas/judgments-1.0.schema.json).
The runtime validator uses the Python standard library rather than a JSON
Schema package. Unknown fields are retained for round-tripping and ignored by
the M1 metrics.

A producer integration should:

1. emit one record per model read;
2. assign a stable, unique `record_id`;
3. use a POSIX-style `photo_id` relative to the declared photo root;
4. name each pass with `stage` and choose the matching `read_kind`;
5. emit exactly `accept`, `maybe`, or `reject` as `verdict`;
6. include `source.tool`, and include model, prompt, and settings provenance
   when available;
7. use the same `settings_fingerprint` and zero-based `repeat_index` inside
   each identical-configuration `context.repeat_group`;
8. preserve provider usage and explicit cost metadata without duplicating
   thinking tokens into `output_tokens`.

The audit configuration names the baseline and decisive stages explicitly.
No stage is inferred from record order.

The repository's build plan contains the full contract and metric rationale:
[`PLAN.md`](PLAN.md). The committed schema directory is
[`schemas/`](schemas/).

## 7. Local-first privacy and security

M1 is local-first:

- `validate`, `audit`, and `demo` make no network requests or telemetry calls;
  only the opt-in non-dry `reference run` contacts Gemini;
- `demo` is image-free and keyless;
- photos are opened read-only when local discovery is requested;
- source files are not moved, renamed, deleted, rated, or rewritten;
- API keys are not accepted by any M1 command, stored in artifacts, or
  printed by the tool;
- input records and reports stay in the output locations chosen by the user.

Treat judgment records, filenames, reasons, and reports as potentially
sensitive. Review artifacts before sharing them. Use a temporary output
directory when working with private shoots, and do not commit private
records or photos. Review reference-run artifacts separately before sharing
them with anyone.

## 8. Open demo

The open-photo demo is a coherent Wikimedia Commons event set; its manifest is the authority and images are not committed. See [`examples/open-demo/README.md`](examples/open-demo/README.md) for licensing, attribution, and reproducible acquisition.
```bash
python tools/open_demo_fetch.py report --manifest examples/open-demo/manifest.json
python tools/open_demo_fetch.py fetch --manifest examples/open-demo/manifest.json --out /tmp/cull-audit-open-demo
python tools/open_demo_fetch.py verify --manifest examples/open-demo/manifest.json --dir /tmp/cull-audit-open-demo
```

## 9. Limitations and roadmap

Current limitations include no RAW decoding, video or burst alignment,
perceptual duplicate detection, face identity attribution, web dashboard,
database, telemetry, live provider pricing, or automatic source-photo
mutation. The metrics are provider-neutral but not provider-independent:
different producers can encode different prompts, settings, scores, and
populations. The v1 stability thresholds are fixed and should not be read as
scientific truth.

The roadmap is recorded in [`PLAN.md`](PLAN.md):

- **M1, current:** contracts, local discovery, imported-record validation,
  flip/stability/cost metrics, deterministic audit artifacts, and the
  keyless demo;
- **M2, planned:** an opt-in reference adapter, a licensed open-photo demo,
  and reproducibility documentation;
- **M3, planned:** release and community integration work.

## 10. Contributing and MIT license

Contributions should stay within the audit-not-judge scope. Useful additions
include producer adapters, contract fixtures, metric tests, privacy reviews,
and documentation improvements. Keep changes deterministic, local-first, and
covered by the stdlib `unittest` suite. Before submitting a change, run:

```bash
python tools/lint.py
python -m unittest discover -s tests -v
```

This project is distributed under the MIT License. See
[`LICENSE`](LICENSE). The demo data is synthetic and does not derive from a
private photo shoot.
