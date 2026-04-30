# AGENTS.md

## Project Intent

`no-meta-standing-ledger` treats research claims through public evidence,
replayability, challengeability, and finite verification capacity rather than
affiliation, prestige, or hidden authority.

## Agent Rules

- Change standing by appending declared public events, then run replay.
- Do not edit `.nmsl/public/state.snapshot.json` directly.
- Do not add private evidence, local paths, secrets, real personal data, or
  third-party copyrighted payloads to examples or tests.
- Preserve deterministic replay: identical public logs must produce identical
  snapshots.
- Keep runtime dependencies minimal and permissively licensed.
- Keep the project easy to clone, fork, and run without contributor bureaucracy.

## Common Commands

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check
uv run mypy
uv run bandit -q -r src
uv run python scripts/check_licenses.py
uv run python scripts/scan_secrets.py
```

## Public Ledger Workflow

```powershell
uv run nmsl claim add c1 --title "Synthetic claim"
uv run nmsl evidence add c1 --uri https://example.org/evidence.json --sha256 <hex> --size 128
uv run nmsl challenge open c1 --kind replay
uv run nmsl replay
uv run nmsl validate
uv run nmsl audit
uv run nmsl explain c1
```
