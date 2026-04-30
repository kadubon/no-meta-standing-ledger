# SPDX-License-Identifier: Apache-2.0
"""Synthetic demo ledgers used by CLI and tests."""

from __future__ import annotations

from no_meta_standing_ledger.models import EventClass, LedgerEvent, Standing


def three_claim_dependency_trap() -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    for index, claim_id in enumerate(("A", "B", "C")):
        events.append(
            LedgerEvent.create(
                event_id=f"demo-create-{claim_id}",
                event_class=EventClass.CLAIM_CREATE,
                epoch=0,
                issuer="demo",
                target=claim_id,
                claim_id=claim_id,
                lineage_id=claim_id,
                logindex=index,
                payload={
                    "title": f"Synthetic claim {claim_id}",
                    "initial_standing": Standing.ACTIVE.value,
                    "support": True,
                },
            )
        )
    events.extend(
        [
            LedgerEvent.create(
                event_id="demo-edge-a-b",
                event_class=EventClass.EDGE_ADD,
                epoch=0,
                issuer="demo",
                target="B",
                claim_id="A",
                lineage_id="A",
                logindex=10,
                payload={"source": "A", "target": "B", "label": "supports"},
            ),
            LedgerEvent.create(
                event_id="demo-edge-b-c",
                event_class=EventClass.EDGE_ADD,
                epoch=0,
                issuer="demo",
                target="C",
                claim_id="B",
                lineage_id="B",
                logindex=11,
                payload={"source": "B", "target": "C", "label": "depends"},
            ),
            LedgerEvent.create(
                event_id="demo-challenge-a",
                event_class=EventClass.CHALLENGE_OPEN,
                epoch=1,
                issuer="demo",
                target="A",
                claim_id="A",
                lineage_id="A",
                obligation_id="demo-obligation-a-replay",
                logindex=20,
                payload={"kind": "replay"},
            ),
            LedgerEvent.create(
                event_id="demo-discharge-a",
                event_class=EventClass.CHALLENGE_DISCHARGE,
                epoch=3,
                issuer="demo",
                target="A",
                claim_id="A",
                lineage_id="A",
                logindex=30,
                payload={"kinds": ["replay"]},
            ),
            LedgerEvent.create(
                event_id="demo-exonerate-b",
                event_class=EventClass.CHALLENGE_DISCHARGE,
                epoch=4,
                issuer="demo",
                target="B",
                claim_id="B",
                lineage_id="B",
                logindex=40,
                payload={"kinds": []},
            ),
            LedgerEvent.create(
                event_id="demo-support-c",
                event_class=EventClass.EVIDENCE_ADD,
                epoch=5,
                issuer="demo",
                target="C",
                claim_id="C",
                lineage_id="C",
                logindex=50,
                payload={
                    "artifact_id": "sha256:" + "b" * 64,
                    "sha256": "b" * 64,
                    "size": 64,
                    "content_type": "application/json",
                    "support": True,
                },
            ),
        ]
    )
    return events


def acceptance_flood() -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    logindex = 0
    for epoch in range(5):
        for slot in range(2):
            claim_id = f"F{epoch}-{slot}"
            events.append(
                LedgerEvent.create(
                    event_id=f"flood-create-{claim_id}",
                    event_class=EventClass.CLAIM_CREATE,
                    epoch=epoch,
                    issuer="demo",
                    target=claim_id,
                    claim_id=claim_id,
                    lineage_id=claim_id,
                    logindex=logindex,
                    payload={
                        "title": f"Synthetic flood claim {claim_id}",
                        "initial_standing": Standing.ACTIVE.value,
                        "support": True,
                    },
                )
            )
            logindex += 1
            if epoch > 0:
                events.append(
                    LedgerEvent.create(
                        event_id=f"flood-challenge-{claim_id}",
                        event_class=EventClass.CHALLENGE_OPEN,
                        epoch=epoch,
                        issuer="demo",
                        target=claim_id,
                        claim_id=claim_id,
                        lineage_id=claim_id,
                        obligation_id=f"flood-obligation-{claim_id}",
                        logindex=logindex,
                        payload={"kind": "inferential"},
                    )
                )
                logindex += 1
    return events


DEMO_BUILDERS = {
    "three-claim-dependency": three_claim_dependency_trap,
    "acceptance-flood": acceptance_flood,
}
