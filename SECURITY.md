# Security policy

## Supported versions

Security fixes are supported for the `0.1.x` release line.

## Report a vulnerability

Report vulnerabilities through
[GitHub Security Advisories](https://github.com/rmax-ai/cull-audit/security/advisories/new).
Do not disclose an unpatched vulnerability in a public issue, pull request, or
discussion.

Never put API keys, tokens, private records, private filenames, or other
secrets in an issue. Use a redacted reproduction and share sensitive material
only through the private advisory workflow.

## Security posture

The project is local-first. The optional provider key is read from the
`CULL_AUDIT_GEMINI_API_KEY` environment variable, not from command-line
arguments or checked-in files. The default validation, audit, and demo paths
make no network requests and send no telemetry. Review provider-run artifacts
before sharing them.

See [README §7](README.md#7-local-first-privacy-and-security) for the complete
privacy and security guidance.
