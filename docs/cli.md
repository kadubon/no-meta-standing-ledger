# CLI Reference

All commands are local-first and operate on `--root`, defaulting to the current
directory.

```powershell
nmsl init --layer standard
nmsl config show
nmsl config set active_capacity 20
nmsl config set reserve_caps.replay 10
nmsl config set challenge_kinds '["provenance","replay","proof"]'
nmsl claim add CLAIM_ID --title "..." --family-id FAMILY --frontier-bucket default
nmsl claim retire CLAIM_ID --reason "superseded by later public work"
nmsl evidence add CLAIM_ID --uri https://example.org/evidence.json --sha256 <hex> --size 128
nmsl evidence add CLAIM_ID --file public-note.txt --include-content --max-include-bytes 4096
nmsl challenge open CLAIM_ID --kind replay
nmsl challenge complete CLAIM_ID --obligation-id OBLIGATION_ID
nmsl discharge CLAIM_ID --kind replay
nmsl edge add SOURCE TARGET --label supports
nmsl edge revoke SOURCE TARGET --label supports
nmsl edge transfer SOURCE TARGET --new-source NEW_SOURCE --new-target NEW_TARGET
nmsl lineage supersede OLD_CLAIM SUCCESSOR_CLAIM
nmsl memory forget CLAIM_ID
nmsl memory rehydrate CLAIM_ID
nmsl replay
nmsl state
nmsl audit
nmsl explain CLAIM_ID
nmsl validate
nmsl doctor
nmsl export --output public-ledger.jsonl
```

`evidence add --file` records hash metadata by default. Use
`--include-content` only for intentionally public, rights-cleared text. Embedded
content is limited by `--max-include-bytes`; large artifacts should be referenced
by hash metadata and public URI instead of embedded.

`claim add --family-id` and `--frontier-bucket` are optional. They are public
coordinates used by the full frontier scheduler for family-token accounting and
reserved-bucket occupancy. When omitted, the claim id prefix before `:` is used
as the family and `default` is used as the bucket.

`claim retire` writes a public `claim.retire` event. Retirement is a standing
state, not deletion; later admissible exoneration or support can still create a
public restoration path under the declared policy.

`edge revoke` and `edge transfer` write later `edge.add` records with the same
conflict tag. For a conflict tag, the latest `logindex` wins; state priority
only breaks same-index ties. This prevents an older active edge from silently
overriding a later public revocation.

`explain` is intended for humans and local agents. It reports the standing,
blocking footprint, pending obligations, authority-bearing edges, restoration
summary, and memory status for one claim without requiring the caller to inspect
the full snapshot manually.

`validate` checks schema shape, event class names, non-negative ordering fields,
hash consistency, duplicate replay identity conflicts, and common privacy/secret
leaks before publication. It also checks event payloads against the declared
policy, including configured challenge kinds and frontier buckets. Exact
duplicate replay identities are accepted as idempotent duplicates; conflicting
duplicate bodies are errors.

`doctor` is the operational readiness command. It validates the event log,
validates policy configuration, replays the ledger when possible, runs invariant
checks, and prints a compact machine-readable summary.

`config set` accepts top-level keys and one-level dotted map keys. When
`challenge_kinds` or `frontier_buckets` are replaced, related maps are normalized
so operators do not have to manually rewrite every reserve, timeout, weight, or
bucket reservation entry.
