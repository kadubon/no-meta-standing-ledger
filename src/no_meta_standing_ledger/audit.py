# SPDX-License-Identifier: Apache-2.0
"""Invariant checks for public standing replay states."""

from __future__ import annotations

from dataclasses import dataclass

from no_meta_standing_ledger.models import EdgeState, ObligationState, ReplayState, Standing
from no_meta_standing_ledger.policy import PolicyConfig


@dataclass(frozen=True)
class InvariantFinding:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def check_invariants(state: ReplayState, config: PolicyConfig) -> list[InvariantFinding]:
    findings: list[InvariantFinding] = []
    if state.service.active_load > config.active_capacity:
        findings.append(
            InvariantFinding(
                "active-capacity",
                f"active load {state.service.active_load} exceeds cap {config.active_capacity}",
            )
        )
    if state.service.frontier_load > config.frontier_capacity:
        findings.append(
            InvariantFinding(
                "frontier-capacity",
                "frontier load "
                f"{state.service.frontier_load} exceeds cap {config.frontier_capacity}",
            )
        )
    if state.service.frontier_metadata_load > config.frontier_metadata_capacity_bits:
        findings.append(
            InvariantFinding(
                "frontier-metadata-capacity",
                "frontier metadata load "
                f"{state.service.frontier_metadata_load} exceeds cap "
                f"{config.frontier_metadata_capacity_bits}",
            )
        )
    if state.service.memory_load > config.hot_memory_capacity_bits:
        findings.append(
            InvariantFinding(
                "hot-memory-capacity",
                "hot restoration memory load "
                f"{state.service.memory_load} exceeds cap {config.hot_memory_capacity_bits}",
            )
        )
    for kind, occupied in state.service.occupied_reserve.items():
        cap = config.reserve_caps.get(kind, 0)
        if occupied > cap:
            findings.append(
                InvariantFinding(
                    "reserve-capacity",
                    f"class {kind} occupied reserve {occupied} exceeds cap {cap}",
                )
            )
    for obligation in state.obligations.values():
        if obligation.state != ObligationState.PENDING:
            continue
        if obligation.claim_id not in state.claims:
            findings.append(
                InvariantFinding(
                    "pending-obligation-claim",
                    f"pending obligation {obligation.obligation_id} references missing claim",
                )
            )
        claim = state.claims.get(obligation.claim_id)
        if claim is not None and claim.lineage_id != obligation.lineage_id:
            findings.append(
                InvariantFinding(
                    "pending-obligation-lineage",
                    f"pending obligation {obligation.obligation_id} is not on exposed lineage",
                )
            )
    for claim in state.claims.values():
        footprint = _blocking_footprint(state, claim.lineage_id, config)
        if claim.standing == Standing.ACTIVE and footprint:
            findings.append(
                InvariantFinding(
                    "active-blocking-footprint",
                    f"active claim {claim.claim_id} carries unresolved blocking footprint",
                )
            )
        if (
            claim.standing in {Standing.CONTESTED, Standing.RETIRED, Standing.STALE, Standing.READY}
            and claim.lineage_id not in state.hot_memory
            and claim.lineage_id not in state.cold_archive
        ):
            findings.append(
                InvariantFinding(
                    "restoration-memory-address",
                    f"nonactive/repair lineage {claim.lineage_id} has no memory address",
                )
            )
    for edge in state.edges.values():
        if (
            edge.state not in {EdgeState.ACTIVE, EdgeState.TRANSFERRED}
            or not edge.authority_bearing
        ):
            continue
        source = state.claims.get(edge.source)
        target = state.claims.get(edge.target)
        if source is None or target is None:
            findings.append(
                InvariantFinding("edge-endpoint", f"edge {edge.edge_id} has a missing endpoint")
            )
            continue
        if source.standing == Standing.FRONTIER or target.standing == Standing.FRONTIER:
            findings.append(
                InvariantFinding(
                    "frontier-authority",
                    f"edge {edge.edge_id} is authority-bearing with a frontier endpoint",
                )
            )
    return findings


def _blocking_footprint(state: ReplayState, lineage_id: str, config: PolicyConfig) -> set[str]:
    return {
        obligation.kind
        for obligation in state.obligations.values()
        if obligation.lineage_id == lineage_id
        and obligation.state == ObligationState.PENDING
        and obligation.kind in config.blocking_kinds
    }
