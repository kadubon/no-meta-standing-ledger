# Theory Mapping

This document maps Takahashi (2026), *Standing-Layer Honest Public Standing
Dynamics for Research Claims under Observable-Only, No-Meta Governance*, to the
code. It is written for maintainers, users, and local agents that need to know
where a theoretical object becomes an executable public interface.

The implementation is an executable standing-layer ledger. It is not a proof
assistant formalization and does not attempt to solve transport consensus,
truth discovery, or policy optimality.

## Layer Mapping

| Paper layer | Code location | Public interface |
| --- | --- | --- |
| Constitutional layer: declared inputs | `PolicyConfig`, policy validation, event schema | `.nmsl/public/config.json` |
| Transport layer: ordered public prefix | `LedgerEvent`, `store.append_event`, `store.read_events`, replay sorting | `.nmsl/public/ledger.jsonl` |
| Exploration layer: replayable frontier | frontier fields in `PolicyConfig`, `_maybe_frontier` | `full` layer replay |
| Standing layer: status update | `replay.py`, `audit.py`, `explain.py` | `nmsl replay`, `nmsl audit`, `nmsl explain` |

## Core Object Mapping

| Paper construct | Implementation |
| --- | --- |
| Public state value | `ReplayState.to_dict()` public snapshot |
| Replay state | `ReplayState` dataclass |
| Declared standing-input projection | Public event payloads plus `PolicyConfig` |
| Standing alphabet | `Standing` enum |
| Typed challenge alphabet | `PolicyConfig.challenge_kinds` |
| Parsed public event coordinates | `EventClass` and CLI event commands |
| Public relation records | `EdgeRecord` and `nmsl edge add` |
| Edge admissibility algebra | conflict tags, `_edge_conflict_winners`, `_is_authority_eligible` |
| Shared ordered prefix | CLI `logindex` assignment, exact duplicate collapse, identity-conflict rejection, `LedgerEvent.sort_key()` |
| Malformed/quarantine discipline | `append_event` validation, `validation.py`, `nmsl validate`, hash and identity-conflict quarantine |
| Replay determinism | `replay_events`, golden tests |
| Typed obligations | `ObligationRecord`; `pending_age` advances by epoch delta |
| Arrival/removal counts | `ServiceState.arrivals`, `completions`, `discharges`, `net_removals` |
| Audit debt | `ServiceState.audit_debt` |
| Active/frontier load | `ServiceState.active_load`, `frontier_load` |
| Frontier bucket occupancy | `ServiceState.frontier_buckets`, `frontier_metadata_load` |
| Contradiction reserve | `occupied_reserve`, `reserve_free`, `reserve_caps` |
| Restoration summary | `retained_summary` keyed by lineage; support/wait age buckets use epoch deltas |
| Hot/cold retained memory | `hot_memory`, `cold_archive`, `memory forget`, `memory rehydrate` |
| Edge stress and potential | `edge_stress`, `ecology_potential` |
| Family token/cooldown state | `frontier_tokens`, `family_inactivity`, claim `family_id`; frontier scheduling prevents simultaneous same-family frontier occupancy |
| Feeder interface | Event schema; external tools emit JSONL events |

## Replay Operator

The paper's seven-stage replay operator is implemented in `_apply_epoch`.
`stage_trace` records a compact public trace for every epoch:

1. `lineage`
2. `edge-admissibility`
3. `obligation-queue`
4. `support-timers`
5. `claim-local-kernel`
6. `counters-memory-frontier`
7. `scheduler`

Agents should inspect `stage_trace` and `service_history` when explaining why a
standing changed. They should not mutate snapshots directly.

CLI replay commands validate the public JSONL file before running the standing
layer. Schema-invalid or malformed lines therefore become explicit validation
failures rather than hidden standing inputs. Exact duplicate replay identities
collapse idempotently. Duplicate replay identities with different canonical
event bodies are validation errors; direct library replay quarantines the
conflicting identity.

The event validator is also policy-aware. Challenge arrivals and class-wise
removals must use kinds declared in `PolicyConfig.challenge_kinds`, and claim
creation must use a `frontier_bucket` declared in `PolicyConfig.frontier_buckets`.
This keeps the finite typed alphabet and frontier taxonomy from becoming hidden
metadata outside the public policy.

For edge conflict tags, the MVP declares a recency-first rule: the latest
`logindex` for the conflict tag wins, and edge-state priority only breaks
same-index ties. This is the repository's public conflict-resolution rule for
append-only CLI operation, so a later public revocation can make an older active
edge non-authority-bearing rather than being defeated by archival order.

The MVP replay operator advances timers by epoch deltas, not by the number of
processed event groups. A jump from epoch `0` to epoch `100` advances retained
support age, pending obligation age, frontier age, and ready wait age by `100`.
New support and newly opened obligations in the current epoch start at age `0`.

## Axiom/Postulate Mapping

| Theory requirement | Runtime support |
| --- | --- |
| Observable closure | Public JSONL events, config, deterministic replay only |
| No-meta sufficiency | Hash-checked/validated events; replay ignores undeclared local metadata |
| Challenge admissibility | `challenge open`, typed obligations, blocking footprints |
| Local damage containment | Authority edges and staged propagation are explicit |
| Lineage honesty | `lineage supersede`, lineage ids, hot/cold memory addresses |
| Budget honesty | active/frontier/memory/reserve caps and invariant checks |
| Non-flooding | active capacity and scheduler gates |
| Non-freeze | discharge/support refresh to `ready`, scheduler reactivation |
| Retirement-restoration duality | retired/contested claims can return through discharge and restoration |
| Restoration-memory sufficiency | retained summary stores standing, cause, footprint, age/wait buckets |

## MVP Simplifications

The software intentionally implements a releaseable standing-layer MVP rather
than every advanced mechanism in the paper. `restoration_lag` and
`duplicate_horizon` remain declared, validated policy coordinates reserved for
future bounded-lag and frontier-cooldown variants. Closed public randomness and
taxonomy revision are represented as schema/policy hooks, not full mechanisms.

## Results-To-Code Map

| Paper result family | Code reflection |
| --- | --- |
| Boundary and no hidden truth convergence | README scope, no truth oracle in models or replay |
| Necessity of challenge and reversible nonactive state | standing enum and challenge/discharge commands |
| Restoration quotient and memory lower-bound intuition | fixed retained summary fields and memory bit load |
| Graph locality and edge-admissible propagation | authority-bearing edges and `_apply_edge_propagation` |
| Constructive policy and invariant preservation | scheduler, counters, `check_invariants` |
| Overload and debt growth | backlog, audit debt, service history |
| Contradiction reserve exhaustion | reserve caps and reserve free counters |
| Institution-gaming visibility | public event log, privacy/export checks, audit output |
| Certification composition | external feeder tools can emit event-schema-compatible JSONL |

## Practical Use

For a claim-level explanation:

```powershell
uv run nmsl explain CLAIM_ID
```

For ecology-level health:

```powershell
uv run nmsl audit
```

For reproducibility:

```powershell
uv run nmsl replay
```

Before publishing:

```powershell
uv run nmsl validate
uv run nmsl doctor
uv run nmsl export --output public-ledger.jsonl
```
