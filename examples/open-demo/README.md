# Open demo

This directory contains the authoritative manifest for a reproducible,
licensed photo set. The image bytes are fetched locally and are deliberately
not committed to this repository.

## Acquisition

Use Python 3.11+ from the repository root. The commands below create a fresh
directory, download every manifest row sequentially, and verify each
downloaded byte stream before accepting it:

```bash
python tools/open_demo_fetch.py report --manifest examples/open-demo/manifest.json
python tools/open_demo_fetch.py fetch --manifest examples/open-demo/manifest.json --out /tmp/cull-audit-open-demo
python tools/open_demo_fetch.py verify --manifest examples/open-demo/manifest.json --dir /tmp/cull-audit-open-demo
```

## How to verify

Use `fetch --limit 2` for a smoke run. The fetcher uses a polite user agent,
HTTPS, a small delay between requests, and a 25 MiB per-file limit. It exits
nonzero if any row fails. The `verify` command is offline and checks both the
recorded byte count and SHA-256 digest.

## License and provenance policy

The manifest permits only CC0, Public Domain, CC BY 2.0–4.0, and
CC BY-SA 2.0–4.0. These licenses permit the demo's local acquisition and
reuse while retaining the creator's attribution requirements; NC and ND
licenses are excluded because they do not provide the needed reuse rights.
Every row must have a traceable Wikimedia Commons file page, creator,
license, license URL, attribution string, download URL, byte count, and
SHA-256 digest. An unclear, incomplete, or ambiguous asset is excluded.

Attribution follows this form:

```text
Creator, "File title", via Wikimedia Commons, LICENSE
```

Keep the attribution from the manifest with any local copy or derived demo
output. The manifest is the authority for the selected set, provenance, and
checksums. `redistribution` is `false` by default: this repository supplies
metadata and tooling, not image bytes. Recheck the individual Commons page
before public redistribution because source metadata and page availability
can change.
