# SPDX-License-Identifier: Apache-2.0
"""Public data contracts for no-meta standing ledgers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

SCHEMA_VERSION = "nmsl.event.v1"
DEFAULT_CHALLENGE_KINDS = ("provenance", "replay", "inferential", "lineage", "proof")


class Layer(StrEnum):
    LITE = "lite"
    STANDARD = "standard"
    FULL = "full"


class Standing(StrEnum):
    PROPOSED = "proposed"
    FRONTIER = "frontier"
    ACTIVE = "active"
    CONTESTED = "contested"
    STALE = "stale"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    READY = "ready"


class EventClass(StrEnum):
    CLAIM_CREATE = "claim.create"
    EVIDENCE_ADD = "evidence.add"
    CHALLENGE_OPEN = "challenge.open"
    CHALLENGE_COMPLETE = "challenge.complete"
    CHALLENGE_DISCHARGE = "challenge.discharge"
    EDGE_ADD = "edge.add"
    LINEAGE_SUPERSEDE = "lineage.supersede"
    CLAIM_RETIRE = "claim.retire"
    MEMORY_FORGET = "memory.forget"
    MEMORY_REHYDRATE = "memory.rehydrate"
    TAXONOMY_UPDATE = "taxonomy.update"


class EdgeLabel(StrEnum):
    SUPPORTS = "supports"
    ATTACKS = "attacks"
    DEPENDS = "depends"
    REFINES = "refines"
    SUPERSEDES = "supersedes"
    AGGREGATES = "aggregates"


class EdgeState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    TRANSFERRED = "transferred"


class ObligationState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    DISCHARGED = "discharged"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class RetCause(StrEnum):
    NONE = "none"
    RETIRED_DECLARED = "retired-declared"
    CHALLENGE_OPEN = "challenge-open"
    STALE_SUPPORT = "stale-support"
    REPAIR_EXONERATED = "repair-exonerated"
    REPAIR_SUPPORTED = "repair-supported"


JsonDict = dict[str, Any]


def canonical_json(value: Any) -> str:
    """Return deterministic JSON used by event hashing and snapshots."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    schema_version: str
    epoch: int
    event_class: str
    issuer: str
    target: str
    claim_id: str | None
    lineage_id: str | None
    obligation_id: str | None
    idempotency_key: str
    logindex: int
    hash: str
    payload: JsonDict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        event_class: str | EventClass,
        epoch: int,
        issuer: str,
        target: str,
        payload: JsonDict | None = None,
        claim_id: str | None = None,
        lineage_id: str | None = None,
        obligation_id: str | None = None,
        idempotency_key: str | None = None,
        logindex: int = 0,
        schema_version: str = SCHEMA_VERSION,
    ) -> Self:
        payload = payload or {}
        event_class_value = str(event_class)
        idem = idempotency_key or event_id
        body = {
            "event_id": event_id,
            "schema_version": schema_version,
            "epoch": epoch,
            "class": event_class_value,
            "issuer": issuer,
            "target": target,
            "claim_id": claim_id,
            "lineage_id": lineage_id,
            "obligation_id": obligation_id,
            "idempotency_key": idem,
            "logindex": logindex,
            "payload": payload,
        }
        return cls(
            event_id=event_id,
            schema_version=schema_version,
            epoch=epoch,
            event_class=event_class_value,
            issuer=issuer,
            target=target,
            claim_id=claim_id,
            lineage_id=lineage_id,
            obligation_id=obligation_id,
            idempotency_key=idem,
            logindex=logindex,
            hash=sha256_text(canonical_json(body)),
            payload=payload,
        )

    @classmethod
    def from_dict(cls, value: JsonDict) -> Self:
        event_class = value.get("class", value.get("event_class"))
        if not isinstance(event_class, str):
            raise ValueError("event class is required")
        return cls(
            event_id=str(value["event_id"]),
            schema_version=str(value["schema_version"]),
            epoch=int(value["epoch"]),
            event_class=event_class,
            issuer=str(value["issuer"]),
            target=str(value["target"]),
            claim_id=_optional_str(value.get("claim_id")),
            lineage_id=_optional_str(value.get("lineage_id")),
            obligation_id=_optional_str(value.get("obligation_id")),
            idempotency_key=str(value["idempotency_key"]),
            logindex=int(value["logindex"]),
            hash=str(value["hash"]),
            payload=dict(value.get("payload", {})),
        )

    def to_dict(self) -> JsonDict:
        return {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "epoch": self.epoch,
            "class": self.event_class,
            "issuer": self.issuer,
            "target": self.target,
            "claim_id": self.claim_id,
            "lineage_id": self.lineage_id,
            "obligation_id": self.obligation_id,
            "idempotency_key": self.idempotency_key,
            "logindex": self.logindex,
            "hash": self.hash,
            "payload": self.payload,
        }

    def replay_identity(self) -> tuple[str, str]:
        return (self.event_id, self.idempotency_key)

    def canonical_body(self) -> str:
        body = self.to_dict()
        body.pop("hash")
        return canonical_json(body)

    def sort_key(self) -> tuple[int, str, str, str, int, str]:
        return (self.epoch, self.event_class, self.issuer, self.target, self.logindex, self.hash)

    def recomputed_hash(self) -> str:
        return sha256_text(self.canonical_body())


@dataclass
class ClaimRecord:
    claim_id: str
    lineage_id: str
    standing: Standing = Standing.PROPOSED
    title: str = ""
    text: str = ""
    support_age: int | None = None
    current_support: bool = False
    frontier_age: int = 0
    wait_age: int = 0
    family_id: str = ""
    frontier_bucket: str = "default"
    retcause: RetCause = RetCause.NONE
    evidence: list[JsonDict] = field(default_factory=list)
    superseded_by: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "claim_id": self.claim_id,
            "lineage_id": self.lineage_id,
            "standing": self.standing.value,
            "title": self.title,
            "text": self.text,
            "support_age": self.support_age,
            "current_support": self.current_support,
            "frontier_age": self.frontier_age,
            "wait_age": self.wait_age,
            "family_id": self.family_id,
            "frontier_bucket": self.frontier_bucket,
            "retcause": self.retcause.value,
            "evidence": self.evidence,
            "superseded_by": self.superseded_by,
        }


@dataclass
class ObligationRecord:
    obligation_id: str
    kind: str
    claim_id: str
    lineage_id: str
    state: ObligationState = ObligationState.PENDING
    pending_age: int = 0
    reserve_allocated: bool = False

    def to_dict(self) -> JsonDict:
        return {
            "obligation_id": self.obligation_id,
            "kind": self.kind,
            "claim_id": self.claim_id,
            "lineage_id": self.lineage_id,
            "state": self.state.value,
            "pending_age": self.pending_age,
            "reserve_allocated": self.reserve_allocated,
        }


@dataclass
class EdgeRecord:
    edge_id: str
    source: str
    target: str
    label: EdgeLabel
    issuer: str
    binding: str
    state: EdgeState = EdgeState.ACTIVE
    conflict_tag: str = ""
    authority_bearing: bool = False
    logindex: int = 0
    event_hash: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "edge_id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "label": self.label.value,
            "issuer": self.issuer,
            "binding": self.binding,
            "state": self.state.value,
            "conflict_tag": self.conflict_tag,
            "authority_bearing": self.authority_bearing,
            "logindex": self.logindex,
            "event_hash": self.event_hash,
        }


@dataclass
class ServiceState:
    epoch: int = 0
    arrivals: dict[str, int] = field(default_factory=dict)
    completions: dict[str, int] = field(default_factory=dict)
    discharges: dict[str, int] = field(default_factory=dict)
    supersession_drops: dict[str, int] = field(default_factory=dict)
    retirement_drops: dict[str, int] = field(default_factory=dict)
    service_removals: dict[str, int] = field(default_factory=dict)
    administrative_removals: dict[str, int] = field(default_factory=dict)
    net_removals: dict[str, int] = field(default_factory=dict)
    backlog: dict[str, int] = field(default_factory=dict)
    occupied_reserve: dict[str, int] = field(default_factory=dict)
    reserve_free: dict[str, int] = field(default_factory=dict)
    audit_debt: float = 0.0
    edge_stress: int = 0
    ecology_potential: float = 0.0
    active_load: int = 0
    frontier_load: int = 0
    frontier_buckets: dict[str, int] = field(default_factory=dict)
    frontier_metadata_load: int = 0
    memory_load: int = 0

    def to_dict(self) -> JsonDict:
        return {
            "epoch": self.epoch,
            "arrivals": self.arrivals,
            "completions": self.completions,
            "discharges": self.discharges,
            "supersession_drops": self.supersession_drops,
            "retirement_drops": self.retirement_drops,
            "service_removals": self.service_removals,
            "administrative_removals": self.administrative_removals,
            "net_removals": self.net_removals,
            "backlog": self.backlog,
            "occupied_reserve": self.occupied_reserve,
            "reserve_free": self.reserve_free,
            "audit_debt": self.audit_debt,
            "edge_stress": self.edge_stress,
            "ecology_potential": self.ecology_potential,
            "active_load": self.active_load,
            "frontier_load": self.frontier_load,
            "frontier_buckets": self.frontier_buckets,
            "frontier_metadata_load": self.frontier_metadata_load,
            "memory_load": self.memory_load,
        }


@dataclass
class ReplayState:
    claims: dict[str, ClaimRecord] = field(default_factory=dict)
    obligations: dict[str, ObligationRecord] = field(default_factory=dict)
    edges: dict[str, EdgeRecord] = field(default_factory=dict)
    service: ServiceState = field(default_factory=ServiceState)
    service_history: list[JsonDict] = field(default_factory=list)
    retained_summary: dict[str, JsonDict] = field(default_factory=dict)
    hot_memory: set[str] = field(default_factory=set)
    cold_archive: set[str] = field(default_factory=set)
    frontier_tokens: dict[str, int] = field(default_factory=dict)
    family_inactivity: dict[str, int] = field(default_factory=dict)
    quarantined_events: list[JsonDict] = field(default_factory=list)
    applied_events: list[str] = field(default_factory=list)
    stage_trace: list[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "claims": {key: claim.to_dict() for key, claim in sorted(self.claims.items())},
            "obligations": {
                key: obligation.to_dict()
                for key, obligation in sorted(self.obligations.items())
            },
            "edges": {key: edge.to_dict() for key, edge in sorted(self.edges.items())},
            "service": self.service.to_dict(),
            "service_history": self.service_history,
            "retained_summary": dict(sorted(self.retained_summary.items())),
            "hot_memory": sorted(self.hot_memory),
            "cold_archive": sorted(self.cold_archive),
            "frontier_tokens": dict(sorted(self.frontier_tokens.items())),
            "family_inactivity": dict(sorted(self.family_inactivity.items())),
            "quarantined_events": self.quarantined_events,
            "applied_events": self.applied_events,
            "stage_trace": self.stage_trace,
        }


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
