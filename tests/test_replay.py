# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from no_meta_standing_ledger.audit import check_invariants
from no_meta_standing_ledger.demos import three_claim_dependency_trap
from no_meta_standing_ledger.models import EventClass, Layer, LedgerEvent, Standing
from no_meta_standing_ledger.policy import PolicyConfig
from no_meta_standing_ledger.replay import replay_events


def test_replay_is_deterministic_with_duplicate_collapse() -> None:
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic claim", "support": True},
    )

    first = replay_events([event, event]).to_dict()
    second = replay_events([event]).to_dict()

    assert first == second
    assert first["claims"]["c1"]["standing"] == Standing.ACTIVE.value


def test_conflicting_duplicate_replay_identity_is_quarantined() -> None:
    first = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "First", "support": True},
    )
    second = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c2",
        claim_id="c2",
        lineage_id="c2",
        idempotency_key="e1",
        payload={"title": "Second", "support": True},
    )

    state = replay_events([first, second])

    assert not state.claims
    assert {item["reason"] for item in state.quarantined_events} == {
        "duplicate-replay-identity-conflict"
    }


def test_challenge_and_discharge_move_active_claim_through_ready_to_active() -> None:
    events = [
        LedgerEvent.create(
            event_id="create",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
        ),
        LedgerEvent.create(
            event_id="challenge",
            event_class=EventClass.CHALLENGE_OPEN,
            epoch=1,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            obligation_id="o1",
            payload={"kind": "replay"},
        ),
        LedgerEvent.create(
            event_id="discharge",
            event_class=EventClass.CHALLENGE_DISCHARGE,
            epoch=2,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"kinds": ["replay"]},
        ),
        LedgerEvent.create(
            event_id="tick",
            event_class=EventClass.CLAIM_CREATE,
            epoch=3,
            issuer="tester",
            target="tick",
            claim_id="tick",
            lineage_id="tick",
            payload={"title": "Synthetic tick"},
        ),
    ]

    state = replay_events(events)

    assert state.claims["c1"].standing == Standing.ACTIVE
    assert state.obligations["o1"].state.value == "discharged"
    assert state.service.audit_debt == 0


def test_epoch_gap_ages_support_by_epoch_delta() -> None:
    events = [
        LedgerEvent.create(
            event_id="create-c1",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
        ),
        LedgerEvent.create(
            event_id="tick",
            event_class=EventClass.CLAIM_CREATE,
            epoch=100,
            issuer="tester",
            target="tick",
            claim_id="tick",
            lineage_id="tick",
            payload={"title": "Synthetic tick"},
        ),
    ]

    state = replay_events(events, PolicyConfig.from_dict({"support_horizon": 30}))

    assert state.claims["c1"].support_age == 100
    assert state.claims["c1"].standing == Standing.STALE
    assert state.stage_trace[-1]["delta"] == 100


def test_epoch_gap_expires_frontier_by_epoch_delta() -> None:
    events = [
        LedgerEvent.create(
            event_id="create-c1",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True, "family_id": "f1", "frontier_bucket": "default"},
        ),
        LedgerEvent.create(
            event_id="tick",
            event_class=EventClass.CLAIM_CREATE,
            epoch=100,
            issuer="tester",
            target="tick",
            claim_id="tick",
            lineage_id="tick",
            payload={"title": "Synthetic tick"},
        ),
    ]
    cfg = PolicyConfig.from_dict(
        {
            "layer": Layer.FULL.value,
            "active_capacity": 0,
            "frontier_horizon": 10,
            "support_horizon": 1000,
        }
    )

    state = replay_events(events, cfg)

    assert state.claims["c1"].frontier_age == 100
    assert state.claims["c1"].standing == Standing.PROPOSED


def test_epoch_gap_ages_pending_obligation_by_epoch_delta() -> None:
    events = [
        LedgerEvent.create(
            event_id="create-c1",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
        ),
        LedgerEvent.create(
            event_id="challenge",
            event_class=EventClass.CHALLENGE_OPEN,
            epoch=1,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            obligation_id="o1",
            payload={"kind": "replay"},
        ),
        LedgerEvent.create(
            event_id="tick",
            event_class=EventClass.CLAIM_CREATE,
            epoch=100,
            issuer="tester",
            target="tick",
            claim_id="tick",
            lineage_id="tick",
            payload={"title": "Synthetic tick"},
        ),
    ]

    state = replay_events(events, PolicyConfig.from_dict({"contested_timeout": {"replay": 10}}))

    assert state.obligations["o1"].pending_age == 99
    assert state.claims["c1"].standing == Standing.RETIRED


def test_full_layer_dependency_trap_matches_expected_degradation() -> None:
    state = replay_events(
        three_claim_dependency_trap(),
        PolicyConfig.from_dict({"layer": Layer.FULL.value, "active_capacity": 10}),
    )

    assert state.claims["A"].standing == Standing.ACTIVE
    assert state.claims["B"].standing == Standing.ACTIVE
    assert state.claims["C"].standing == Standing.ACTIVE
    assert state.service.audit_debt == 0


def test_hash_mismatch_is_quarantined() -> None:
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic claim"},
    )
    broken = LedgerEvent(
        event_id=event.event_id,
        schema_version=event.schema_version,
        epoch=event.epoch,
        event_class=event.event_class,
        issuer=event.issuer,
        target=event.target,
        claim_id=event.claim_id,
        lineage_id=event.lineage_id,
        obligation_id=event.obligation_id,
        idempotency_key=event.idempotency_key,
        logindex=event.logindex,
        hash="bad",
        payload=event.payload,
    )

    state = replay_events([broken])

    assert not state.claims
    assert state.quarantined_events[0]["reason"] == "hash-mismatch"


def test_challenge_completion_records_service_counts() -> None:
    events = [
        LedgerEvent.create(
            event_id="create",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
        ),
        LedgerEvent.create(
            event_id="challenge",
            event_class=EventClass.CHALLENGE_OPEN,
            epoch=1,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            obligation_id="o1",
            payload={"kind": "proof"},
        ),
        LedgerEvent.create(
            event_id="complete",
            event_class=EventClass.CHALLENGE_COMPLETE,
            epoch=2,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            obligation_id="o1",
            payload={},
        ),
    ]

    state = replay_events(events)

    assert state.service.completions["proof"] == 1
    assert state.service.service_removals["proof"] == 1
    assert state.service.backlog["proof"] == 0


def test_hot_memory_forget_and_rehydrate_are_public_events() -> None:
    events = [
        LedgerEvent.create(
            event_id="create",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"support": True},
        ),
        LedgerEvent.create(
            event_id="forget",
            event_class=EventClass.MEMORY_FORGET,
            epoch=1,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"mode": "archive"},
        ),
        LedgerEvent.create(
            event_id="support-refresh",
            event_class=EventClass.EVIDENCE_ADD,
            epoch=2,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={
                "artifact_id": "sha256:" + "c" * 64,
                "sha256": "c" * 64,
                "support": True,
            },
        ),
    ]

    state = replay_events(events)

    assert "c1" in state.hot_memory
    assert "c1" not in state.cold_archive
    assert state.retained_summary["c1"]["standing"] == Standing.ACTIVE.value


def test_invariant_audit_reports_active_capacity_violation() -> None:
    events = [
        LedgerEvent.create(
            event_id=f"create-{claim_id}",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target=claim_id,
            claim_id=claim_id,
            lineage_id=claim_id,
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
        )
        for claim_id in ("c1", "c2")
    ]
    cfg = PolicyConfig.from_dict({"active_capacity": 1})

    state = replay_events(events, cfg)
    findings = check_invariants(state, cfg)

    assert any(finding.code == "active-capacity" for finding in findings)


def test_full_layer_frontier_respects_family_occupancy_and_tokens() -> None:
    events = [
        LedgerEvent.create(
            event_id=f"create-{claim_id}",
            event_class=EventClass.CLAIM_CREATE,
            epoch=index,
            issuer="tester",
            target=claim_id,
            claim_id=claim_id,
            lineage_id=claim_id,
            payload={
                "support": True,
                "family_id": "same-family",
                "frontier_bucket": "default",
            },
            logindex=index,
        )
        for index, claim_id in enumerate(("c1", "c2"))
    ]
    cfg = PolicyConfig.from_dict(
        {
            "layer": Layer.FULL.value,
            "active_capacity": 0,
            "family_token_cap": 2,
            "frontier_capacity": 10,
            "frontier_reservations": {"default": 10},
        }
    )

    state = replay_events(events, cfg)

    assert sum(1 for claim in state.claims.values() if claim.standing == Standing.FRONTIER) == 1
    assert state.frontier_tokens["same-family"] == 1
    assert state.service.frontier_buckets["default"] == 1


def test_edge_conflict_tag_selects_single_authority_bearing_record() -> None:
    events = [
        LedgerEvent.create(
            event_id="create-a",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="a",
            claim_id="a",
            lineage_id="a",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
            logindex=0,
        ),
        LedgerEvent.create(
            event_id="create-b",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="b",
            claim_id="b",
            lineage_id="b",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
            logindex=1,
        ),
        LedgerEvent.create(
            event_id="revoked-edge",
            event_class=EventClass.EDGE_ADD,
            epoch=1,
            issuer="tester",
            target="b",
            claim_id="a",
            lineage_id="a",
            payload={
                "source": "a",
                "target": "b",
                "label": "supports",
                "conflict_tag": "edge-conflict",
                "state": "revoked",
            },
            logindex=0,
        ),
        LedgerEvent.create(
            event_id="active-edge",
            event_class=EventClass.EDGE_ADD,
            epoch=1,
            issuer="tester",
            target="b",
            claim_id="a",
            lineage_id="a",
            payload={
                "source": "a",
                "target": "b",
                "label": "supports",
                "conflict_tag": "edge-conflict",
                "state": "active",
            },
            logindex=1,
        ),
    ]

    state = replay_events(events, PolicyConfig.from_dict({"layer": Layer.FULL.value}))

    assert state.edges["active-edge"].authority_bearing
    assert not state.edges["revoked-edge"].authority_bearing


def test_later_revoked_edge_record_wins_same_conflict_tag() -> None:
    events = [
        LedgerEvent.create(
            event_id="create-a",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="a",
            claim_id="a",
            lineage_id="a",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
            logindex=0,
        ),
        LedgerEvent.create(
            event_id="create-b",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="b",
            claim_id="b",
            lineage_id="b",
            payload={"support": True, "initial_standing": Standing.ACTIVE.value},
            logindex=1,
        ),
        LedgerEvent.create(
            event_id="active-edge",
            event_class=EventClass.EDGE_ADD,
            epoch=1,
            issuer="tester",
            target="b",
            claim_id="a",
            lineage_id="a",
            payload={
                "source": "a",
                "target": "b",
                "label": "supports",
                "conflict_tag": "edge-conflict",
                "state": "active",
            },
            logindex=0,
        ),
        LedgerEvent.create(
            event_id="revoked-edge",
            event_class=EventClass.EDGE_ADD,
            epoch=1,
            issuer="tester",
            target="b",
            claim_id="a",
            lineage_id="a",
            payload={
                "source": "a",
                "target": "b",
                "label": "supports",
                "conflict_tag": "edge-conflict",
                "state": "revoked",
            },
            logindex=1,
        ),
    ]

    state = replay_events(events, PolicyConfig.from_dict({"layer": Layer.FULL.value}))

    assert not state.edges["active-edge"].authority_bearing
    assert not state.edges["revoked-edge"].authority_bearing
