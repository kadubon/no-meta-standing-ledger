# Architecture

`no-meta-standing-ledger` separates the theory into public, replayable modules.

## Public Log As Source Of Truth

The append-only JSONL ledger is the source of truth. Snapshots are derived by
deterministic replay and may be deleted and regenerated.

CLI writes validate event schema, privacy rules, canonical hashes, and declared
policy compatibility before appending. Replay-facing CLI commands validate the
JSONL file before the standing layer reads it.

Replay performs:

1. exact duplicate collapse by `(event_id, idempotency_key)`;
2. total ordering by `(epoch, class, issuer, target, logindex, hash)`, with CLI
   writes assigning a monotone local `logindex`;
3. deterministic staged transition.

If the same replay identity appears with different canonical event bodies,
validation fails before CLI replay. Direct library replay quarantines the
conflicting identity so it cannot silently alter standing.

Timer and horizon counters use actual epoch deltas. If the ordered log jumps
from epoch `0` to epoch `100`, support age, pending age, frontier age, and ready
wait age advance by `100`. New support or newly opened obligations in the
current epoch start at age `0`.

## Staged Transition

The implementation follows the standing-layer order:

1. lineage and supersession update;
2. edge admissibility;
3. typed obligation queue creation/discharge/removal and pending-age update;
4. support-age and timer refresh;
5. claim-local standing kernel;
6. backlog, reserve, memory, and frontier counters;
7. restoration, fresh admission, and frontier scheduling.

## Layer Profiles

- Lite disables authority-bearing graph effects and scheduler admission. It is
  suitable for replaying basic claim/evidence/challenge paths.
- Standard enables typed queue, support, reserve, active capacity, and
  ready-to-active restoration.
- Full enables edge propagation and frontier admission hooks.
  It records family-token state, family inactivity, frontier bucket occupancy,
  and frontier metadata load in the replayed public state.

The profiles share the same event schema. This is intentional: operators can
begin with Lite and later replay the same public history under a richer declared
policy.

## Agent Use

Agents should prefer the public CLI and JSON snapshot rather than importing
private internals:

```powershell
uv run nmsl replay
uv run nmsl validate
uv run nmsl audit
uv run nmsl state
uv run nmsl explain CLAIM_ID
```

When an agent proposes a standing change, it should write a public event first
and rely on replay to produce the resulting state. Direct snapshot mutation is
not part of the declared interface.
