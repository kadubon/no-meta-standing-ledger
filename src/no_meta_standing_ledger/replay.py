# SPDX-License-Identifier: Apache-2.0
"""Deterministic replay operator for public standing ledgers."""

from __future__ import annotations

import copy
from collections.abc import Iterable

from no_meta_standing_ledger.models import (
    ClaimRecord,
    EdgeLabel,
    EdgeRecord,
    EdgeState,
    EventClass,
    JsonDict,
    Layer,
    LedgerEvent,
    ObligationRecord,
    ObligationState,
    ReplayState,
    RetCause,
    Standing,
)
from no_meta_standing_ledger.policy import PolicyConfig


def replay_events(events: Iterable[LedgerEvent], config: PolicyConfig | None = None) -> ReplayState:
    """Replay events into a public state using declared deterministic stages."""

    cfg = config or PolicyConfig()
    state = ReplayState()
    collapsed = _collapse_and_sort(events, state)
    epochs = sorted({event.epoch for event in collapsed})
    previous_epoch: int | None = None
    for epoch in epochs:
        delta = 0 if previous_epoch is None else epoch - previous_epoch
        epoch_events = [event for event in collapsed if event.epoch == epoch]
        _apply_epoch(state, epoch_events, cfg, epoch, delta)
        state.service.epoch = epoch
        state.applied_events.extend(event.event_id for event in epoch_events)
        previous_epoch = epoch
    _update_counters_memory_frontier(state, cfg)
    return state


def _collapse_and_sort(events: Iterable[LedgerEvent], state: ReplayState) -> list[LedgerEvent]:
    by_identity: dict[tuple[str, str], LedgerEvent] = {}
    body_by_identity: dict[tuple[str, str], str] = {}
    conflicted: set[tuple[str, str]] = set()
    for event in events:
        if event.hash != event.recomputed_hash():
            state.quarantined_events.append(
                {"event_id": event.event_id, "reason": "hash-mismatch", "event": event.to_dict()}
            )
            continue
        identity = event.replay_identity()
        canonical_body = event.canonical_body()
        previous_body = body_by_identity.get(identity)
        if previous_body is not None and previous_body != canonical_body:
            conflicted.add(identity)
            previous_event = by_identity.pop(identity, None)
            if previous_event is not None:
                state.quarantined_events.append(
                    {
                        "event_id": previous_event.event_id,
                        "reason": "duplicate-replay-identity-conflict",
                        "replay_identity": list(identity),
                        "event": previous_event.to_dict(),
                    }
                )
            state.quarantined_events.append(
                {
                    "event_id": event.event_id,
                    "reason": "duplicate-replay-identity-conflict",
                    "replay_identity": list(identity),
                    "event": event.to_dict(),
                }
            )
            continue
        if identity in conflicted:
            state.quarantined_events.append(
                {
                    "event_id": event.event_id,
                    "reason": "duplicate-replay-identity-conflict",
                    "replay_identity": list(identity),
                    "event": event.to_dict(),
                }
            )
            continue
        body_by_identity[identity] = canonical_body
        current = by_identity.get(identity)
        if current is None or event.sort_key() < current.sort_key():
            by_identity[identity] = event
    return sorted(by_identity.values(), key=lambda item: item.sort_key())


def _apply_epoch(
    state: ReplayState,
    epoch_events: list[LedgerEvent],
    cfg: PolicyConfig,
    epoch: int,
    delta: int,
) -> None:
    counts = _empty_epoch_counts(cfg)
    new_obligation_ids: set[str] = set()
    frontier_expired_claims: set[str] = set()
    _record_stage(state, epoch, "start", delta)
    _stage_1_lineage(state, epoch_events, cfg, counts)
    _record_stage(state, epoch, "lineage", delta)
    _stage_2_edges(state, epoch_events, cfg)
    _record_stage(state, epoch, "edge-admissibility", delta)
    _stage_3_obligations(state, epoch_events, cfg, counts, new_obligation_ids, delta)
    _record_stage(state, epoch, "obligation-queue", delta)
    _stage_4_support_and_timers(state, epoch_events, cfg, delta)
    _record_stage(state, epoch, "support-timers", delta)
    _stage_5_claim_local_kernel(state, epoch_events, cfg, frontier_expired_claims)
    _record_stage(state, epoch, "claim-local-kernel", delta)
    _stage_6_queue_and_memory(state, epoch_events, cfg)
    _set_epoch_counts(state, counts)
    _record_stage(state, epoch, "counters-memory-frontier", delta)
    _stage_7_scheduler(state, cfg, frontier_expired_claims)
    _set_epoch_counts(state, counts)
    _record_stage(state, epoch, "scheduler", delta)
    state.service.epoch = epoch
    state.service_history.append(copy.deepcopy(state.service.to_dict()))


def _stage_1_lineage(
    state: ReplayState,
    events: list[LedgerEvent],
    cfg: PolicyConfig,
    counts: dict[str, dict[str, int]],
) -> None:
    for event in events:
        if event.event_class == EventClass.CLAIM_CREATE:
            claim_id = event.claim_id or event.target
            lineage_id = event.lineage_id or claim_id
            initial = Standing(str(event.payload.get("initial_standing", Standing.PROPOSED.value)))
            state.claims.setdefault(
                claim_id,
                ClaimRecord(
                    claim_id=claim_id,
                    lineage_id=lineage_id,
                    standing=initial,
                    title=str(event.payload.get("title", "")),
                    text=str(event.payload.get("text", "")),
                    family_id=str(event.payload.get("family_id", _default_family_id(claim_id))),
                    frontier_bucket=str(event.payload.get("frontier_bucket", "default")),
                ),
            )
            if event.payload.get("support", False):
                state.claims[claim_id].support_age = 0
                state.claims[claim_id].current_support = True
            _ensure_hot(state, lineage_id, cfg)
        elif event.event_class == EventClass.LINEAGE_SUPERSEDE:
            old_id = event.claim_id or event.target
            old = state.claims.get(old_id)
            successor_id = str(event.payload.get("successor_claim_id", ""))
            successor_lineage = str(event.payload.get("successor_lineage_id", successor_id))
            if old is None:
                continue
            if successor_id and successor_id not in state.claims:
                state.claims[successor_id] = ClaimRecord(
                    claim_id=successor_id,
                    lineage_id=successor_lineage,
                    standing=Standing.PROPOSED,
                    title=str(event.payload.get("successor_title", "")),
                    text=str(event.payload.get("successor_text", "")),
                    family_id=str(
                        event.payload.get(
                            "successor_family_id",
                            old.family_id or _default_family_id(successor_id),
                        )
                    ),
                    frontier_bucket=str(
                        event.payload.get("successor_frontier_bucket", old.frontier_bucket)
                    ),
                )
                _ensure_hot(state, successor_lineage, cfg)
            old.standing = Standing.SUPERSEDED
            old.superseded_by = successor_id or None
            state.hot_memory.discard(old.lineage_id)
            state.cold_archive.discard(old.lineage_id)
            for obligation in state.obligations.values():
                if obligation.lineage_id != old.lineage_id:
                    continue
                if successor_lineage:
                    obligation.lineage_id = successor_lineage
                    obligation.claim_id = successor_id
                elif obligation.state == ObligationState.PENDING:
                    obligation.state = ObligationState.SUPERSEDED
                    obligation.reserve_allocated = False
                    counts["supersession_drops"][obligation.kind] = (
                        counts["supersession_drops"].get(obligation.kind, 0) + 1
                    )


def _stage_2_edges(state: ReplayState, events: list[LedgerEvent], cfg: PolicyConfig) -> None:
    for event in events:
        if event.event_class != EventClass.EDGE_ADD:
            continue
        source = str(event.payload.get("source", event.claim_id or ""))
        target = str(event.payload.get("target", event.target))
        label = EdgeLabel(str(event.payload.get("label", EdgeLabel.SUPPORTS.value)))
        edge_state = EdgeState(str(event.payload.get("state", EdgeState.ACTIVE.value)))
        edge = EdgeRecord(
            edge_id=event.event_id,
            source=source,
            target=target,
            label=label,
            issuer=event.issuer,
            binding=str(event.payload.get("binding", "")),
            state=edge_state,
            conflict_tag=str(event.payload.get("conflict_tag", "")),
            logindex=event.logindex,
            event_hash=event.hash,
        )
        state.edges[edge.edge_id] = edge
    winners = _edge_conflict_winners(state)
    for edge in state.edges.values():
        edge.authority_bearing = (
            edge.edge_id in winners and _is_authority_eligible(edge, state, cfg)
        )


def _edge_conflict_winners(state: ReplayState) -> set[str]:
    groups: dict[str, list[EdgeRecord]] = {}
    for edge in state.edges.values():
        key = f"tag:{edge.conflict_tag}" if edge.conflict_tag else f"edge:{edge.edge_id}"
        groups.setdefault(key, []).append(edge)
    winners: set[str] = set()
    for edges in groups.values():
        winner = min(edges, key=_edge_conflict_key)
        if winner.state != EdgeState.REVOKED:
            winners.add(winner.edge_id)
    return winners


def _edge_conflict_key(edge: EdgeRecord) -> tuple[int, int, str]:
    priority = {
        EdgeState.ACTIVE: 0,
        EdgeState.TRANSFERRED: 1,
        EdgeState.REVOKED: 2,
    }
    return (-edge.logindex, priority[edge.state], edge.event_hash)


def _is_authority_eligible(edge: EdgeRecord, state: ReplayState, cfg: PolicyConfig) -> bool:
    if cfg.layer == Layer.LITE:
        return False
    if edge.state not in {EdgeState.ACTIVE, EdgeState.TRANSFERRED}:
        return False
    source = state.claims.get(edge.source)
    target = state.claims.get(edge.target)
    if source is None or target is None:
        return False
    if source.standing == Standing.FRONTIER or target.standing == Standing.FRONTIER:
        return False
    return source.standing != Standing.SUPERSEDED and target.standing != Standing.SUPERSEDED


def _stage_3_obligations(
    state: ReplayState,
    events: list[LedgerEvent],
    cfg: PolicyConfig,
    counts: dict[str, dict[str, int]],
    new_obligation_ids: set[str],
    delta: int,
) -> None:
    for event in events:
        if event.event_class == EventClass.CHALLENGE_OPEN:
            claim_id = event.claim_id or event.target
            claim = state.claims.get(claim_id)
            if claim is None:
                continue
            _ensure_hot(state, claim.lineage_id, cfg)
            kind = str(event.payload.get("kind", "replay"))
            obligation_id = event.obligation_id or f"{event.event_id}:{kind}"
            if obligation_id not in state.obligations:
                state.obligations[obligation_id] = ObligationRecord(
                    obligation_id=obligation_id,
                    kind=kind,
                    claim_id=claim_id,
                    lineage_id=claim.lineage_id,
                )
                new_obligation_ids.add(obligation_id)
                counts["arrivals"][kind] = counts["arrivals"].get(kind, 0) + 1
        elif event.event_class == EventClass.CHALLENGE_COMPLETE:
            _remove_obligations(
                state,
                event,
                cfg,
                destination=ObligationState.COMPLETED,
                count_bucket=counts["completions"],
            )
        elif event.event_class == EventClass.CHALLENGE_DISCHARGE:
            _remove_obligations(
                state,
                event,
                cfg,
                destination=ObligationState.DISCHARGED,
                count_bucket=counts["discharges"],
            )
        elif event.event_class == EventClass.CLAIM_RETIRE:
            claim_id = event.claim_id or event.target
            claim = state.claims.get(claim_id)
            if claim is None:
                continue
            _ensure_hot(state, claim.lineage_id, cfg)
            for obligation in state.obligations.values():
                if (
                    obligation.lineage_id == claim.lineage_id
                    and obligation.state == ObligationState.PENDING
                ):
                    obligation.state = ObligationState.RETIRED
                    obligation.reserve_allocated = False
                    counts["retirement_drops"][obligation.kind] = (
                    counts["retirement_drops"].get(obligation.kind, 0) + 1
                    )
    for obligation in state.obligations.values():
        if (
            obligation.state == ObligationState.PENDING
            and obligation.obligation_id not in new_obligation_ids
        ):
            obligation.pending_age += delta


def _stage_4_support_and_timers(
    state: ReplayState, events: list[LedgerEvent], cfg: PolicyConfig, delta: int
) -> None:
    support_arrivals: set[str] = set()
    for event in events:
        claim_id = event.claim_id or event.target
        if event.event_class == EventClass.CLAIM_CREATE and event.payload.get("support", False):
            support_arrivals.add(claim_id)
            continue
        if event.event_class == EventClass.EVIDENCE_ADD:
            claim = state.claims.get(claim_id)
            if claim is None:
                continue
            _ensure_hot(state, claim.lineage_id, cfg)
            claim.evidence.append(dict(event.payload))
            if bool(event.payload.get("support", True)):
                support_arrivals.add(claim_id)
    for claim in state.claims.values():
        if claim.standing == Standing.SUPERSEDED:
            continue
        if claim.claim_id in support_arrivals:
            claim.support_age = 0
        elif claim.support_age is not None:
            claim.support_age += delta
        claim.current_support = (
            claim.support_age is not None and claim.support_age <= cfg.support_horizon
        )
        claim.frontier_age = (
            claim.frontier_age + delta if claim.standing == Standing.FRONTIER else 0
        )
        claim.wait_age = claim.wait_age + delta if claim.standing == Standing.READY else 0


def _stage_5_claim_local_kernel(
    state: ReplayState,
    events: list[LedgerEvent],
    cfg: PolicyConfig,
    frontier_expired_claims: set[str],
) -> None:
    superseded = {
        event.claim_id or event.target
        for event in events
        if event.event_class == EventClass.LINEAGE_SUPERSEDE
    }
    retired = {
        event.claim_id or event.target
        for event in events
        if event.event_class == EventClass.CLAIM_RETIRE
    }
    exonerated = {
        event.claim_id or event.target
        for event in events
        if event.event_class == EventClass.CHALLENGE_DISCHARGE
    }
    for claim in sorted(state.claims.values(), key=lambda item: item.claim_id):
        if claim.standing == Standing.SUPERSEDED:
            continue
        if claim.claim_id in superseded:
            claim.standing = Standing.SUPERSEDED
            claim.retcause = RetCause.NONE
            continue
        blocking = _blocking_footprint(state, claim, cfg)
        if claim.claim_id in exonerated:
            if claim.standing in {Standing.CONTESTED, Standing.RETIRED} and not blocking:
                claim.standing = Standing.READY
                claim.wait_age = 0
                claim.retcause = RetCause.REPAIR_EXONERATED
            elif claim.standing == Standing.READY:
                claim.retcause = RetCause.REPAIR_EXONERATED
            continue
        if claim.claim_id in retired or _contested_timeout(state, claim, cfg):
            claim.standing = Standing.RETIRED
            claim.retcause = RetCause.RETIRED_DECLARED
            continue
        if blocking and claim.standing in {Standing.ACTIVE, Standing.READY}:
            claim.standing = Standing.CONTESTED
            claim.retcause = RetCause.CHALLENGE_OPEN
            continue
        if claim.standing == Standing.FRONTIER and claim.frontier_age >= cfg.frontier_horizon:
            claim.standing = Standing.PROPOSED
            frontier_expired_claims.add(claim.claim_id)
            claim.retcause = RetCause.NONE
            continue
        if claim.standing == Standing.STALE and claim.current_support and not blocking:
            claim.standing = Standing.READY
            claim.wait_age = 0
            claim.retcause = RetCause.REPAIR_SUPPORTED
            continue
        if claim.standing in {Standing.ACTIVE, Standing.READY} and not claim.current_support:
            claim.standing = Standing.STALE
            claim.retcause = RetCause.STALE_SUPPORT
    if cfg.layer == Layer.FULL:
        _apply_edge_propagation(state)


def _blocking_footprint(state: ReplayState, claim: ClaimRecord, cfg: PolicyConfig) -> set[str]:
    return {
        obligation.kind
        for obligation in state.obligations.values()
        if obligation.lineage_id == claim.lineage_id
        and obligation.state == ObligationState.PENDING
        and obligation.kind in cfg.blocking_kinds
    }


def _contested_timeout(state: ReplayState, claim: ClaimRecord, cfg: PolicyConfig) -> bool:
    if claim.standing != Standing.CONTESTED:
        return False
    for obligation in state.obligations.values():
        if obligation.lineage_id != claim.lineage_id or obligation.state != ObligationState.PENDING:
            continue
        if obligation.pending_age > cfg.contested_timeout.get(obligation.kind, cfg.support_horizon):
            return True
    return False


def _apply_edge_propagation(state: ReplayState) -> None:
    changed = True
    while changed:
        changed = False
        for edge in sorted(state.edges.values(), key=lambda item: item.edge_id):
            if not edge.authority_bearing:
                continue
            source = state.claims.get(edge.source)
            target = state.claims.get(edge.target)
            if source is None or target is None or target.standing != Standing.ACTIVE:
                continue
            if source.standing not in {Standing.CONTESTED, Standing.RETIRED, Standing.SUPERSEDED}:
                continue
            if edge.label == EdgeLabel.SUPPORTS:
                target.standing = Standing.CONTESTED
                target.retcause = RetCause.CHALLENGE_OPEN
                changed = True
            elif edge.label in {EdgeLabel.DEPENDS, EdgeLabel.REFINES}:
                target.standing = Standing.STALE
                target.retcause = RetCause.STALE_SUPPORT
                changed = True
            elif edge.label == EdgeLabel.ATTACKS:
                target.standing = Standing.CONTESTED
                target.retcause = RetCause.CHALLENGE_OPEN
                changed = True


def _stage_6_queue_and_memory(
    state: ReplayState, events: list[LedgerEvent], cfg: PolicyConfig
) -> None:
    for event in events:
        if event.event_class == EventClass.MEMORY_FORGET:
            _forget_memory(state, event)
        elif event.event_class == EventClass.MEMORY_REHYDRATE:
            claim = state.claims.get(event.claim_id or event.target)
            if claim is not None:
                _ensure_hot(state, claim.lineage_id, cfg)
    _update_counters_memory_frontier(state, cfg)


def _stage_7_scheduler(
    state: ReplayState, cfg: PolicyConfig, frontier_excluded_claims: set[str]
) -> None:
    if cfg.layer == Layer.LITE:
        return
    free_active = cfg.active_capacity - sum(
        1 for claim in state.claims.values() if claim.standing == Standing.ACTIVE
    )
    if free_active <= 0:
        _maybe_frontier(state, cfg, frontier_excluded_claims)
        return

    restoration_candidates = sorted(
        (
            claim
            for claim in state.claims.values()
            if claim.standing == Standing.READY
            and claim.current_support
            and not _blocking_footprint(state, claim, cfg)
            and _memory_feasible(state, cfg, extra_lineages=1)
            and _reserve_feasible(state, cfg)
        ),
        key=lambda claim: (-claim.wait_age, claim.support_age or 0, claim.claim_id),
    )
    if restoration_candidates:
        _ensure_hot(state, restoration_candidates[0].lineage_id, cfg)
        restoration_candidates[0].standing = Standing.ACTIVE
        restoration_candidates[0].wait_age = 0
        free_active -= 1

    for claim in sorted(state.claims.values(), key=lambda item: item.claim_id):
        if free_active <= 0:
            break
        if claim.standing not in {Standing.PROPOSED, Standing.FRONTIER}:
            continue
        if not claim.current_support or _blocking_footprint(state, claim, cfg):
            continue
        if not _memory_feasible(state, cfg, extra_lineages=1) or not _reserve_feasible(state, cfg):
            continue
        _ensure_hot(state, claim.lineage_id, cfg)
        claim.standing = Standing.ACTIVE
        claim.wait_age = 0
        free_active -= 1

    _maybe_frontier(state, cfg, frontier_excluded_claims)
    _update_counters_memory_frontier(state, cfg)


def _maybe_frontier(
    state: ReplayState, cfg: PolicyConfig, frontier_excluded_claims: set[str]
) -> None:
    if cfg.layer != Layer.FULL:
        return
    frontier_count = sum(
        1 for claim in state.claims.values() if claim.standing == Standing.FRONTIER
    )
    if frontier_count >= cfg.frontier_capacity:
        return
    metadata_load = frontier_count * cfg.frontier_metadata_slot_bits
    if metadata_load + cfg.frontier_metadata_slot_bits > cfg.frontier_metadata_capacity_bits:
        return
    bucket_occupancy = _frontier_bucket_occupancy(state)
    underfilled_buckets = {
        bucket
        for bucket, reservation in cfg.frontier_reservations.items()
        if bucket_occupancy.get(bucket, 0) < reservation
    }
    occupied_families = {
        claim.family_id or _default_family_id(claim.claim_id)
        for claim in state.claims.values()
        if claim.standing == Standing.FRONTIER
    }
    for claim in sorted(state.claims.values(), key=lambda item: item.claim_id):
        if claim.standing != Standing.PROPOSED or not claim.current_support:
            continue
        if claim.claim_id in frontier_excluded_claims:
            continue
        if underfilled_buckets and claim.frontier_bucket not in underfilled_buckets:
            continue
        family = claim.family_id or _default_family_id(claim.claim_id)
        if family in occupied_families:
            continue
        state.frontier_tokens.setdefault(family, cfg.family_token_cap)
        if state.frontier_tokens[family] <= 0:
            continue
        claim.standing = Standing.FRONTIER
        claim.frontier_age = 0
        state.frontier_tokens[family] -= 1
        state.family_inactivity[family] = 0
        return


def _memory_feasible(state: ReplayState, cfg: PolicyConfig, *, extra_lineages: int) -> bool:
    current = len(state.hot_memory) * cfg.retained_summary_slot_bits
    return current + extra_lineages * cfg.retained_summary_slot_bits <= cfg.hot_memory_capacity_bits


def _reserve_feasible(state: ReplayState, cfg: PolicyConfig) -> bool:
    for kind, cap in cfg.reserve_caps.items():
        occupied = sum(
            1
            for obligation in state.obligations.values()
            if obligation.kind == kind
            and obligation.state == ObligationState.PENDING
            and obligation.reserve_allocated
        )
        if occupied > cap:
            return False
    return True


def _empty_epoch_counts(cfg: PolicyConfig) -> dict[str, dict[str, int]]:
    return {
        "arrivals": dict.fromkeys(cfg.challenge_kinds, 0),
        "completions": dict.fromkeys(cfg.challenge_kinds, 0),
        "discharges": dict.fromkeys(cfg.challenge_kinds, 0),
        "supersession_drops": dict.fromkeys(cfg.challenge_kinds, 0),
        "retirement_drops": dict.fromkeys(cfg.challenge_kinds, 0),
    }


def _set_epoch_counts(state: ReplayState, counts: dict[str, dict[str, int]]) -> None:
    service_removals = {
        kind: counts["completions"].get(kind, 0) + counts["discharges"].get(kind, 0)
        for kind in set(counts["completions"]) | set(counts["discharges"])
    }
    administrative_removals = {
        kind: counts["supersession_drops"].get(kind, 0) + counts["retirement_drops"].get(kind, 0)
        for kind in set(counts["supersession_drops"]) | set(counts["retirement_drops"])
    }
    net_removals = {
        kind: service_removals.get(kind, 0) + administrative_removals.get(kind, 0)
        for kind in set(service_removals) | set(administrative_removals)
    }
    state.service.arrivals = counts["arrivals"]
    state.service.completions = counts["completions"]
    state.service.discharges = counts["discharges"]
    state.service.supersession_drops = counts["supersession_drops"]
    state.service.retirement_drops = counts["retirement_drops"]
    state.service.service_removals = service_removals
    state.service.administrative_removals = administrative_removals
    state.service.net_removals = net_removals


def _remove_obligations(
    state: ReplayState,
    event: LedgerEvent,
    cfg: PolicyConfig,
    *,
    destination: ObligationState,
    count_bucket: dict[str, int],
) -> None:
    claim_id = event.claim_id or event.target
    claim = state.claims.get(claim_id)
    if claim is None:
        return
    _ensure_hot(state, claim.lineage_id, cfg)
    kinds = {str(kind) for kind in event.payload.get("kinds", [])}
    for obligation in state.obligations.values():
        if obligation.state != ObligationState.PENDING:
            continue
        if event.obligation_id is not None and obligation.obligation_id != event.obligation_id:
            continue
        if event.obligation_id is None and obligation.lineage_id != claim.lineage_id:
            continue
        if kinds and obligation.kind not in kinds:
            continue
        if not kinds and event.obligation_id is None:
            continue
        obligation.state = destination
        obligation.reserve_allocated = False
        count_bucket[obligation.kind] = count_bucket.get(obligation.kind, 0) + 1


def _ensure_hot(state: ReplayState, lineage_id: str, cfg: PolicyConfig) -> bool:
    if lineage_id in state.hot_memory:
        return True
    if not _memory_feasible(state, cfg, extra_lineages=1):
        return False
    state.hot_memory.add(lineage_id)
    state.cold_archive.discard(lineage_id)
    return True


def _forget_memory(state: ReplayState, event: LedgerEvent) -> None:
    claim = state.claims.get(event.claim_id or event.target)
    if claim is None:
        return
    has_pending = any(
        obligation.lineage_id == claim.lineage_id and obligation.state == ObligationState.PENDING
        for obligation in state.obligations.values()
    )
    if has_pending or claim.standing == Standing.READY:
        state.quarantined_events.append(
            {
                "event_id": event.event_id,
                "reason": "memory-forget-protected-lineage",
                "lineage_id": claim.lineage_id,
            }
        )
        return
    state.hot_memory.discard(claim.lineage_id)
    state.cold_archive.add(claim.lineage_id)
    state.retained_summary.pop(claim.lineage_id, None)


def _edge_stress(state: ReplayState) -> int:
    stressed = 0
    for edge in state.edges.values():
        if not edge.authority_bearing:
            continue
        source = state.claims.get(edge.source)
        target = state.claims.get(edge.target)
        if source is None or target is None:
            continue
        if source.standing in {Standing.CONTESTED, Standing.RETIRED, Standing.SUPERSEDED}:
            stressed += 1
    return stressed


def _record_stage(state: ReplayState, epoch: int, stage: str, delta: int) -> None:
    state.stage_trace.append(
        {
            "epoch": epoch,
            "delta": delta,
            "stage": stage,
            "claims": len(state.claims),
            "pending_obligations": sum(
                1
                for obligation in state.obligations.values()
                if obligation.state == ObligationState.PENDING
            ),
            "active_load": sum(
                1 for claim in state.claims.values() if claim.standing == Standing.ACTIVE
            ),
            "frontier_load": sum(
                1 for claim in state.claims.values() if claim.standing == Standing.FRONTIER
            ),
            "hot_memory": len(state.hot_memory),
        }
    )


def _update_counters_memory_frontier(state: ReplayState, cfg: PolicyConfig) -> None:
    backlog: dict[str, int] = dict.fromkeys(cfg.challenge_kinds, 0)
    for obligation in state.obligations.values():
        if obligation.state == ObligationState.PENDING:
            backlog[obligation.kind] = backlog.get(obligation.kind, 0) + 1
    occupied: dict[str, int] = dict.fromkeys(cfg.challenge_kinds, 0)
    for kind, cap in cfg.reserve_caps.items():
        pending = sorted(
            (
                obligation
                for obligation in state.obligations.values()
                if obligation.kind == kind and obligation.state == ObligationState.PENDING
            ),
            key=lambda item: (-item.pending_age, item.obligation_id),
        )
        for index, obligation in enumerate(pending):
            obligation.reserve_allocated = index < cap
        occupied[kind] = sum(1 for obligation in pending if obligation.reserve_allocated)
    state.service.backlog = backlog
    state.service.occupied_reserve = occupied
    state.service.reserve_free = {
        kind: max(0, cfg.reserve_caps.get(kind, 0) - occupied.get(kind, 0))
        for kind in cfg.challenge_kinds
    }
    state.service.audit_debt = sum(
        cfg.audit_weights.get(kind, 1.0) * count for kind, count in backlog.items()
    )
    state.service.edge_stress = _edge_stress(state)
    reserve_shortfall = sum(
        max(0, backlog.get(kind, 0) - cfg.reserve_caps.get(kind, 0))
        for kind in cfg.challenge_kinds
    )
    state.service.ecology_potential = (
        state.service.audit_debt + state.service.edge_stress + reserve_shortfall
    )
    state.service.active_load = sum(
        1 for claim in state.claims.values() if claim.standing == Standing.ACTIVE
    )
    state.service.frontier_load = sum(
        1 for claim in state.claims.values() if claim.standing == Standing.FRONTIER
    )
    state.service.frontier_buckets = _frontier_bucket_occupancy(state)
    state.service.frontier_metadata_load = (
        state.service.frontier_load * cfg.frontier_metadata_slot_bits
    )
    state.service.memory_load = len(state.hot_memory) * cfg.retained_summary_slot_bits
    _update_family_tokens(state, cfg)
    state.retained_summary = {
        claim.lineage_id: {
            "standing": claim.standing.value,
            "retcause": claim.retcause.value,
            "footprint": sorted(_blocking_footprint(state, claim, cfg)),
            "age_bucket": _age_bucket(claim.support_age),
            "wait_bucket": _wait_bucket(claim.wait_age),
        }
        for claim in state.claims.values()
        if claim.standing != Standing.SUPERSEDED and claim.lineage_id in state.hot_memory
    }


def _age_bucket(age: int | None) -> str:
    if age is None:
        return "none"
    if age <= 0:
        return "fresh"
    if age <= 7:
        return "recent"
    if age <= 30:
        return "aging"
    return "old"


def _wait_bucket(wait: int) -> str:
    if wait <= 0:
        return "none"
    if wait <= 2:
        return "short"
    if wait <= 10:
        return "medium"
    return "long"


def _frontier_bucket_occupancy(state: ReplayState) -> dict[str, int]:
    occupancy: dict[str, int] = {}
    for claim in state.claims.values():
        if claim.standing != Standing.FRONTIER:
            continue
        occupancy[claim.frontier_bucket] = occupancy.get(claim.frontier_bucket, 0) + 1
    return occupancy


def _update_family_tokens(state: ReplayState, cfg: PolicyConfig) -> None:
    if cfg.layer != Layer.FULL:
        return
    families = {
        claim.family_id or _default_family_id(claim.claim_id)
        for claim in state.claims.values()
        if claim.standing != Standing.SUPERSEDED
    }
    frontier_families = {
        claim.family_id or _default_family_id(claim.claim_id)
        for claim in state.claims.values()
        if claim.standing == Standing.FRONTIER
    }
    for family in sorted(families):
        state.frontier_tokens.setdefault(family, cfg.family_token_cap)
        if family in frontier_families:
            state.family_inactivity[family] = 0
            continue
        inactivity = state.family_inactivity.get(family, 0) + 1
        if inactivity >= cfg.family_horizon:
            state.frontier_tokens[family] = min(
                cfg.family_token_cap, state.frontier_tokens[family] + 1
            )
            inactivity = 0
        state.family_inactivity[family] = inactivity


def _default_family_id(claim_id: str) -> str:
    return claim_id.split(":", 1)[0]


def audit_summary(state: ReplayState) -> JsonDict:
    return {
        "claims": len(state.claims),
        "obligations": len(state.obligations),
        "edges": len(state.edges),
        "service": state.service.to_dict(),
        "service_history": state.service_history,
        "standing_counts": {
            standing.value: sum(1 for claim in state.claims.values() if claim.standing == standing)
            for standing in Standing
        },
        "quarantined_events": len(state.quarantined_events),
    }
