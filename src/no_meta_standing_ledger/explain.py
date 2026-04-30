# SPDX-License-Identifier: Apache-2.0
"""Human- and agent-readable explanations for replayed standing state."""

from __future__ import annotations

from no_meta_standing_ledger.models import ObligationState, ReplayState
from no_meta_standing_ledger.policy import PolicyConfig


def explain_claim(state: ReplayState, claim_id: str, config: PolicyConfig) -> dict[str, object]:
    claim = state.claims.get(claim_id)
    if claim is None:
        raise KeyError(f"claim not found: {claim_id}")
    pending = [
        obligation
        for obligation in state.obligations.values()
        if obligation.lineage_id == claim.lineage_id
        and obligation.state == ObligationState.PENDING
    ]
    blocking = sorted(
        {
            obligation.kind
            for obligation in pending
            if obligation.kind in config.blocking_kinds
        }
    )
    incoming_edges = [
        edge.to_dict()
        for edge in state.edges.values()
        if edge.target == claim.claim_id and edge.authority_bearing
    ]
    outgoing_edges = [
        edge.to_dict()
        for edge in state.edges.values()
        if edge.source == claim.claim_id and edge.authority_bearing
    ]
    reasons = _standing_reasons(
        standing=claim.standing.value,
        current_support=claim.current_support,
        blocking=blocking,
        pending_count=len(pending),
        in_hot_memory=claim.lineage_id in state.hot_memory,
        in_cold_archive=claim.lineage_id in state.cold_archive,
    )
    return {
        "claim": claim.to_dict(),
        "standing": claim.standing.value,
        "reasons": reasons,
        "blocking_footprint": blocking,
        "pending_obligations": [obligation.to_dict() for obligation in pending],
        "incoming_authority_edges": incoming_edges,
        "outgoing_authority_edges": outgoing_edges,
        "restoration_summary": state.retained_summary.get(claim.lineage_id),
        "memory": {
            "hot": claim.lineage_id in state.hot_memory,
            "cold_archive": claim.lineage_id in state.cold_archive,
        },
        "service": state.service.to_dict(),
    }


def _standing_reasons(
    *,
    standing: str,
    current_support: bool,
    blocking: list[str],
    pending_count: int,
    in_hot_memory: bool,
    in_cold_archive: bool,
) -> list[str]:
    reasons: list[str] = []
    if blocking:
        reasons.append("unresolved blocking challenge footprint is present")
    if pending_count:
        reasons.append("typed public service obligations remain pending")
    if current_support:
        reasons.append("current public support is retained within the declared horizon")
    else:
        reasons.append("no current retained support is visible within the declared horizon")
    if standing in {"ready", "contested", "retired", "stale"} and in_hot_memory:
        reasons.append("restoration-relevant lineage summary is in hot memory")
    if in_cold_archive:
        reasons.append("lineage has been explicitly archived out of hot memory")
    if standing == "active" and not blocking and current_support:
        reasons.append("claim can carry active standing under the current declared policy")
    return reasons
