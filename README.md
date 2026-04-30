# no-meta-standing-ledger

Local-first public standing ledger for research claims, reproducible evidence,
challenge tracking, audit debt, and finite verification capacity.

`no-meta-standing-ledger` helps individuals, small OSS projects, and local AI
agents put claims into a public, replayable state space without relying on
affiliation, prestige, or hidden evaluators. A claim earns its current
`standing` from declared public evidence, reproducibility signals, challenges,
lineage, queues, capacity, reserve, and restoration memory.

The project implements the standing-layer theory from:

K. Takahashi (2026), *Standing-Layer Honest Public Standing Dynamics for
Research Claims under Observable-Only, No-Meta Governance*.
Zenodo: https://doi.org/10.5281/zenodo.19447443

## What It Is For

Use this when you want to:

- publish research or engineering claims with replayable public evidence;
- track reproducibility and challenge status without hidden adjudication;
- let others or local agents challenge a claim through declared public events;
- see audit debt, backlog, contradiction reserve, and finite verification load;
- keep speculative frontier claims separate from active, challenge-bearing ones;
- make standing updates transparent enough to clone, fork, inspect, and replay.

It is useful for independent researchers, small labs, OSS maintainers, AI-agent
research workflows, benchmark claims, reproducibility notes, and public release
governance.

## What It Is Not

This software does not decide truth. It does not provide legal, medical,
financial, safety, or scientific guarantees. A `standing` value is a replayable
institutional state, not an oracle verdict.

The project also does not solve consensus, Byzantine agreement, peer review, or
optimal scheduling. It assumes a public ordered event log and focuses on the
standing-layer update law.

## One-Minute Demo

```powershell
uv sync
uv run nmsl --root .tmp/demo demo --name three-claim-dependency --layer full
uv run nmsl --root .tmp/demo validate
uv run nmsl --root .tmp/demo doctor
uv run nmsl --root .tmp/demo audit
uv run nmsl --root .tmp/demo explain A
```

The demo creates a synthetic three-claim dependency ecology, replays it, checks
the public ledger, prints ecology-level counters, and explains one claim.

## Start A New Ledger

```powershell
uv run nmsl --root .tmp/my-ledger init --layer standard
uv run nmsl --root .tmp/my-ledger config set active_capacity 20
uv run nmsl --root .tmp/my-ledger config set reserve_caps.replay 10
uv run nmsl --root .tmp/my-ledger claim add c1 --title "Synthetic reproducibility claim" --family-id demo --frontier-bucket default --epoch 0
uv run nmsl --root .tmp/my-ledger evidence add c1 --uri "https://example.org/artifacts/c1.json" --sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" --size 128 --epoch 0
uv run nmsl --root .tmp/my-ledger challenge open c1 --kind replay --epoch 1
uv run nmsl --root .tmp/my-ledger replay
uv run nmsl --root .tmp/my-ledger doctor
uv run nmsl --root .tmp/my-ledger explain c1
```

The public ledger lives at `.nmsl/public/ledger.jsonl`. The snapshot at
`.nmsl/public/state.snapshot.json` is derived from replay and can be regenerated.

## Core Commands

```powershell
nmsl init                  # create .nmsl/public/config.json and ledger.jsonl
nmsl config show           # print declared replay policy
nmsl config set            # update declared capacity/reserve/frontier policy
nmsl claim add             # append a public claim event, with optional family/bucket labels
nmsl claim retire          # retire a claim through a public event
nmsl evidence add          # append evidence metadata, hash-first by default
nmsl challenge open        # create a typed public service obligation
nmsl challenge complete    # record service completion
nmsl discharge             # discharge selected challenge classes
nmsl edge add              # add support/attack/dependency/refinement edges
nmsl edge revoke           # revoke an edge through a later conflict record
nmsl edge transfer         # transfer an edge to new public endpoints
nmsl lineage supersede     # record public lineage/supersession
nmsl memory forget         # move a lineage from hot memory to cold archive
nmsl memory rehydrate      # restore a lineage into hot restoration memory
nmsl replay                # deterministically rebuild the snapshot
nmsl validate              # check schema, hash, ordering, and privacy risks
nmsl doctor                # validate, replay, audit invariants, and summarize readiness
nmsl audit                 # show ecology counters and invariant findings
nmsl explain CLAIM_ID      # explain one claim's standing and public footprint
nmsl export                # export the public JSONL log after privacy checks
```

## Standing States

The standing alphabet is fixed:

- `proposed`: visible claim not yet active;
- `frontier`: speculative, public, replayable, not challenge-bearing active;
- `active`: currently challenge-bearing under declared capacity;
- `contested`: unresolved blocking challenge footprint exists;
- `stale`: retained support has lapsed;
- `superseded`: lineage has moved to a successor;
- `retired`: nonactive but not necessarily terminal;
- `ready`: locally repaired and eligible for scheduler reactivation.

## Layers

- Lite: claims, evidence, challenges, standing labels, deterministic replay,
  duplicate collapse, basic audit debt.
- Standard: typed queues, blocking footprints, support age, active capacity,
  contradiction reserve, class-wise discharge, stale/ready/reactivation.
- Full: edge admissibility and conflict tags, lineage remap hooks, hot/cold
  restoration memory, reserve-aware scheduling, frontier buckets, family
  cooldown/token state, and replayable public randomness hooks.

All layers use the same event contract, so an operator can start light and later
replay the same history under a richer declared policy.

## Event Contract

Every public event is a JSON object written as one JSONL line:

```json
{
  "event_id": "...",
  "schema_version": "nmsl.event.v1",
  "epoch": 0,
  "class": "claim.create",
  "issuer": "public",
  "target": "c1",
  "claim_id": "c1",
  "lineage_id": "c1",
  "obligation_id": null,
  "idempotency_key": "...",
  "logindex": 0,
  "hash": "...",
  "payload": {}
}
```

Replay collapses exact duplicate `(event_id, idempotency_key)` pairs and sorts
by `(epoch, class, issuer, target, logindex, hash)`.
The same replay identity with a different canonical event body is a validation
error and is quarantined by direct replay.
CLI-created events receive a monotone local `logindex`; imported events should
preserve their declared `epoch`, `logindex`, and `hash`.
Full-layer frontier scheduling uses public `family_id` and `frontier_bucket`
payload fields to expose token consumption and bucket occupancy.
Timer and horizon fields use epoch deltas. If epoch `0` is followed by epoch
`100`, support age, pending age, frontier age, and ready wait age advance by
`100`, while newly created or newly supported records in epoch `100` start at
age `0`.

## Security And Privacy

The CLI is local-first and does not require network access or credentials.

Evidence content is not embedded by default. File evidence is recorded as a
SHA-256 hash, size, content type, and public artifact id. Use
`--include-content` only for intentionally public, rights-cleared text. Embedded
content is size-limited by default; use `--max-include-bytes` only when the
larger payload is intentionally public and rights-cleared.

`nmsl validate` and `nmsl export` check schema, hash, declared-policy
compatibility, and common accidental leaks:

- local absolute paths;
- private key material;
- secret-like environment assignments;
- API keys, tokens, passwords, and credentials;
- local file URIs;
- malformed JSONL events and hash mismatches.
- undeclared challenge kinds and undeclared frontier buckets.

These checks reduce risk but are not a proof of publishability. Review public
logs before publishing them.

## MVP Limitations

- This records replayable public standing, not global truth.
- It is local-first and does not provide decentralized consensus.
- It does not replace peer review or domain expert judgment.
- Claims require observable public evidence or declared public challenge events.
- Non-replayable or malformed inputs fail validation, remain pending through
  unresolved obligations, or are quarantined depending on the interface path.
- Some advanced dynamics in the paper are simplified for the MVP. In particular,
  `restoration_lag`, `duplicate_horizon`, closed public randomness, and taxonomy
  revision hooks are reserved policy coordinates rather than complete mechanisms.

## Theory-To-Code Map

See [docs/theory-mapping.md](docs/theory-mapping.md) for a detailed mapping from
the paper to the implementation, including:

- constitutional / transport / exploration / standing layers;
- public state and replay state;
- typed challenge obligations and audit debt;
- edge admissibility and graph propagation;
- restoration summary and hot/cold memory;
- finite capacity, reserve, and invariant checks.

For external tools and local agents, the public event contract is also available
as [docs/event-schema.json](docs/event-schema.json).

For routine operation, see [docs/operations.md](docs/operations.md).

## For Local Agents

Agents should append events and replay. They should not edit snapshots directly.

```powershell
uv run nmsl --root .tmp/agent-ledger claim add c1 --title "Synthetic claim"
uv run nmsl --root .tmp/agent-ledger evidence add c1 --uri "https://example.org/evidence.json" --sha256 "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" --size 64
uv run nmsl --root .tmp/agent-ledger replay
uv run nmsl --root .tmp/agent-ledger doctor
uv run nmsl --root .tmp/agent-ledger explain c1
```

## Development

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy
uv run bandit -q -r src
uv run pip-audit
uv run python scripts/check_licenses.py
uv run python scripts/scan_secrets.py
```

## Forking And Reuse

This project is intentionally easy to clone, fork, modify, and run locally. It
does not add extra contribution process for casual use. Keep public ledgers
replayable, avoid private data in examples, and preserve the Apache-2.0 license
when redistributing.

## License

Apache License, Version 2.0. See `LICENSE`.
