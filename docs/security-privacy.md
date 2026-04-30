# Security And Privacy Notes

The project is designed for public ledgers. A public ledger should not contain
secrets, private local paths, private evidence payloads, or accidental personal
data.

## Safe Defaults

- `evidence add --file` stores hash, size, content type, and artifact id. It does
  not store the source path.
- `evidence add --include-content` is explicit because embedded content may
  expose third-party text or private data. It is also bounded by
  `--max-include-bytes`; large evidence should be referenced by hash metadata
  and public URI instead of embedded.
- `validate` checks event schema, hashes, policy configuration,
  event-to-policy compatibility, and common leak patterns.
- `doctor` combines validation, replay, and invariant checks for pre-publication
  readiness.
- `export` runs validation and privacy checks before writing a public JSONL copy.
- The CLI does not require credentials or network access.

## Limits

The scanner is a safeguard, not a proof of safety. It catches common path and
secret patterns but cannot determine whether a research claim, evidence URI, or
embedded payload is legally publishable. Operators should review public exports
before publishing them.

## GitHub Settings

For a public repository, enable:

- secret scanning and push protection;
- branch protection on `main`;
- required PR review and required CI;
- private vulnerability reporting;
- least-privilege Actions permissions.
