# Contributing

## Development setup

Use Python 3.11 or newer. From a clean checkout, install the package in
editable mode:

```bash
python -m pip install -e .
```

Run both gates before opening a pull request:

```bash
python tools/lint.py
python -m unittest discover -s tests
```

Keep changes narrow and deterministic. Do not add network calls to tests or
the default workflow. Preserve the standard-library implementation and the
Pillow-only runtime dependency policy. Do not commit private photos,
judgment records, credentials, or generated local output.

## Scope

Keep proposals within the audit-not-judge scope. Read
[README §9](README.md#9-limitations-and-roadmap) for the current limitations,
non-goals, and roadmap before opening a larger change.

## Pull requests

1. Open an issue first for a change that affects the contract, metrics, or
   public scope.
2. Make one focused branch and keep unrelated formatting out of the diff.
3. Describe what changed, why it changed, and the evidence from both gate
   commands in the pull request.
4. Check the scope and privacy items in
   [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).
5. Wait for review and green CI before merging.

## Contribution terms

By submitting a contribution, you represent that you have the right to submit
it and agree that it may be distributed under the MIT License included in this
repository. Contributions remain subject to the repository's copyright and
license notices.

Development is AI-assisted with a review-first process: changes are reviewed
before they are merged.
