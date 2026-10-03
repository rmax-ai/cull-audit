# v0.1.0 release checklist

Run the commands from the repository root. Stop on the first failed check.
Use a fresh checkout for the clean-clone rehearsal. Do not place private
tokens in this file, shell history, issues, or release notes.

## 1. Gates

- [ ] Run the lint gate:

  ```bash
  .venv/bin/python tools/lint.py
  ```

- [ ] Run the unittest gate:

  ```bash
  .venv/bin/python -m unittest discover -s tests
  ```

- [ ] Run the tree release scan:

  ```bash
  .venv/bin/python tools/release_check.py
  ```

- [ ] Run the bounded history release scan:

  ```bash
  .venv/bin/python tools/release_check.py --history
  ```

## 2. Privacy, license, and dependency audits

- [ ] Inventory the release tree. The scan uses the same tracked-plus-new-file
  set:

  ```bash
  git ls-files --cached --others --exclude-standard
  ```

- [ ] Run the generic secret and release-file scan again immediately before
  the visibility change:

  ```bash
  .venv/bin/python tools/release_check.py
  ```

- [ ] If the operator has private markers to check, create a patterns file
  outside the repository with one regular expression per line and `#` comments
  as needed. Do not put private token values in the repository or this
  checklist. Pass that external path to the scan:

  ```bash
  .venv/bin/python tools/release_check.py --extra-patterns /path/outside/repo/patterns.txt
  ```

- [ ] Confirm the license file is MIT:

  ```bash
  grep -n "MIT License" LICENSE
  ```

- [ ] Confirm the open-demo manifest has no missing license metadata:

  ```bash
  .venv/bin/python tools/open_demo_fetch.py report --manifest examples/open-demo/manifest.json
  ```

- [ ] Confirm the dependency policy through the repository lint audit:

  ```bash
  .venv/bin/python tools/lint.py
  ```

- [ ] Confirm the declared runtime dependency set is Pillow only:

  ```bash
  .venv/bin/python -c "import tomllib; p=tomllib.load(open('pyproject.toml','rb'))['project']; assert p['dependencies'] == ['Pillow']; print(p['dependencies'])"
  ```

- [ ] Review the scan output and the tracked file inventory for private
  photos, records, filenames, local paths, credentials, and unlicensed demo
  material. The generic scan does not replace this human review.

## 3. Version and clean-clone rehearsal

- [ ] Check the package version:

  ```bash
  .venv/bin/python -c "from cull_audit import __version__; assert __version__ == '0.1.0'; print(__version__)"
  ```

- [ ] After the release commit is available, rehearse from a clean clone:

  ```bash
  git clone --branch v0.1.0 https://github.com/rmax-ai/cull-audit.git cull-audit-release-check
  cd cull-audit-release-check
  python -m pip install -e .
  python -m cull_audit --version
  python -m cull_audit demo --output /tmp/cull-audit-release-demo
  test -s /tmp/cull-audit-release-demo/audit.json
  test -s /tmp/cull-audit-release-demo/report.md
  ```

  The version command must print `0.1.0`; the demo must produce non-empty
  `audit.json` and `report.md`.

## 4. Operator approval for the visibility switch

This section is a manual approval record. The operator must complete it before
changing repository visibility. The implementation agent does not approve or
perform the switch.

- [x] I reviewed the tree and bounded history scan results.
- [x] I reviewed privacy, license, dependency, and clean-clone results.
- [x] I confirmed that the release commit and all new files are safe to
      publish.
- [x] I approve changing the repository visibility to public.

**Operator:** R Max Espinoza (rmax-ai)
**UTC approval timestamp:** 2026-10-03T17:21Z
**Release commit:** `1eaf8fa` (tag `v0.1.0`); this approval record is committed
immediately after the release commit and before the visibility switch.
**Notes or exceptions:** Approval given via operator directive. Tree + bounded
history scans clean; license MIT; clean-clone rehearsal passed; visibility
switch executed immediately after this record.

## 5. Tag and publish the release

After the approval record is complete:

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

Create the GitHub Release for tag `v0.1.0` using
[`docs/release-notes-v0.1.0.md`](release-notes-v0.1.0.md). Do not publish until
the visibility approval above is recorded.

## 6. Post-public follow-ups

- [ ] Verify the public repository, tag, README links, issue forms, and
  security-advisory link.
- [ ] Repeat the clean-clone quick start against the public tag.
- [ ] Confirm that the GitHub Release contains the intended notes and no
  private material.
- [ ] Open narrowly scoped follow-up issues for provider adapters, datasets,
  metric critique, or documentation gaps.
- [ ] Record any release defect separately from requests that conflict with
  the audit-not-judge scope.
