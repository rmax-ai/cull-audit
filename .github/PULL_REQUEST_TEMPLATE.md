## What

<!-- State the smallest concrete change made by this pull request. -->

## Why

<!-- Explain the problem, contract requirement, or user need. -->

## Evidence

<!-- Paste the relevant tail or summary from each command. -->

- [ ] `python tools/lint.py`
- [ ] `python -m unittest discover -s tests`
- [ ] `python tools/release_check.py` for release-facing changes

## Scope and safety

- [ ] This change stays within the audit-not-judge scope in README §9.
- [ ] This change keeps the default workflow local-first and adds no telemetry.
- [ ] I did not include secrets, private photos, private records, or local
      filesystem paths.
- [ ] I kept unrelated formatting and generated output out of the diff.
