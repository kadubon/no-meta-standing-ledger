# Operations

This page is a short runbook for people or local agents operating a public
standing ledger.

## Bootstrap

```powershell
uv sync
uv run nmsl --root .tmp/ledger init --layer standard
uv run nmsl --root .tmp/ledger config show
```

Use `standard` for normal claim/evidence/challenge operation. Use `full` when
you need authority-bearing edges, frontier buckets, family-token state, and
hot/cold restoration memory.

## Declare Policy

Policy is public state. Set capacity and reserve values before interpreting a
ledger operationally:

```powershell
uv run nmsl --root .tmp/ledger config set active_capacity 20
uv run nmsl --root .tmp/ledger config set reserve_caps.replay 10
uv run nmsl --root .tmp/ledger config set frontier_capacity 5
```

Changing `challenge_kinds` or `frontier_buckets` normalizes the related maps so
the config remains coherent.

MVP reserved fields:

- `restoration_lag` is retained as a public policy coordinate for future
  bounded-lag scheduler variants. The MVP scheduler restores eligible ready
  claims as soon as active capacity and feasibility screens allow.
- `duplicate_horizon` is retained for future replay-visible frontier
  cooldown/novelty mechanisms. Current duplicate protection is identity-level:
  exact duplicate replay identities collapse, conflicting duplicate identities
  fail validation or are quarantined.

## Daily Use

```powershell
uv run nmsl --root .tmp/ledger claim add claim:1 --title "Synthetic claim"
uv run nmsl --root .tmp/ledger evidence add claim:1 --uri "https://example.org/artifact.json" --sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" --size 64
uv run nmsl --root .tmp/ledger challenge open claim:1 --kind replay
uv run nmsl --root .tmp/ledger replay
uv run nmsl --root .tmp/ledger explain claim:1
```

Snapshots are derived. If in doubt, delete `state.snapshot.json` and run
`replay` again.

## Publish Checklist

```powershell
uv run nmsl --root .tmp/ledger validate
uv run nmsl --root .tmp/ledger doctor
uv run nmsl --root .tmp/ledger export --output public-ledger.jsonl
```

Review the exported JSONL before publishing. The scanner reduces common leak
risk but cannot prove that every payload or public URI is legally publishable.

## Local Cleanup

The repository ignores `.venv/`, `.tmp/`, Python caches, test caches, and build
outputs. Before making a release branch, inspect ignored files:

```powershell
git status --ignored -s
Get-ChildItem -Force -Recurse -Directory -Include __pycache__,.pytest_cache,.mypy_cache,.ruff_cache,.venv,.tmp
Get-ChildItem -Force -Recurse -File -Include *.pyc
```

Do not add ignored local artifacts to Git.
