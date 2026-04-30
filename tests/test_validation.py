# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from no_meta_standing_ledger.models import EventClass, LedgerEvent, canonical_json
from no_meta_standing_ledger.policy import PolicyConfig
from no_meta_standing_ledger.store import append_event, init_ledger
from no_meta_standing_ledger.validation import validate_event_dict, validate_log_file


def test_validate_event_rejects_unknown_event_class() -> None:
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic"},
    ).to_dict()
    event["class"] = "unknown.event"

    findings = validate_event_dict(event)

    assert any(finding.code == "event-class" for finding in findings)


def test_validate_event_rejects_unknown_standing_payload() -> None:
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"initial_standing": "verified"},
    ).to_dict()

    findings = validate_event_dict(event)

    assert any(finding.code == "payload-initial-standing" for finding in findings)


def test_validate_log_file_passes_generated_event(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    init_ledger(root)
    append_event(
        root,
        LedgerEvent.create(
            event_id="e1",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"title": "Synthetic"},
        ),
    )

    findings = validate_log_file(root / ".nmsl" / "public" / "ledger.jsonl")

    assert findings == []


def test_validate_log_file_allows_exact_duplicate_replay_identity(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    paths = init_ledger(root)
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic"},
    )
    line = canonical_json(event.to_dict())
    paths.log_path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    findings = validate_log_file(paths.log_path)

    assert not any(finding.severity == "error" for finding in findings)
    assert any(finding.code == "duplicate-replay-identity" for finding in findings)


def test_validate_log_file_rejects_conflicting_duplicate_replay_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "ledger"
    paths = init_ledger(root)
    first = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "First"},
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
        payload={"title": "Second"},
    )
    paths.log_path.write_text(
        f"{canonical_json(first.to_dict())}\n{canonical_json(second.to_dict())}\n",
        encoding="utf-8",
    )

    findings = validate_log_file(paths.log_path)

    assert any(finding.code == "duplicate-replay-identity-conflict" for finding in findings)


def test_validate_log_file_rejects_undeclared_challenge_kind(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    paths = init_ledger(root)
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CHALLENGE_OPEN,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        obligation_id="o1",
        payload={"kind": "not-declared"},
    )
    paths.log_path.write_text(f"{canonical_json(event.to_dict())}\n", encoding="utf-8")

    findings = validate_log_file(paths.log_path, config=PolicyConfig())

    assert any(finding.code == "policy-challenge-kind-unknown" for finding in findings)


def test_validate_log_file_rejects_undeclared_frontier_bucket(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    paths = init_ledger(root)
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic", "frontier_bucket": "not-declared"},
    )
    paths.log_path.write_text(f"{canonical_json(event.to_dict())}\n", encoding="utf-8")

    findings = validate_log_file(paths.log_path, config=PolicyConfig())

    assert any(finding.code == "policy-frontier-bucket-unknown" for finding in findings)


def test_append_event_rejects_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    event = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c1",
        claim_id="c1",
        lineage_id="c1",
        payload={"title": "Synthetic"},
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

    with pytest.raises(ValueError, match="hash-mismatch"):
        append_event(root, broken)


def test_append_event_rejects_conflicting_duplicate_identity(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    append_event(
        root,
        LedgerEvent.create(
            event_id="e1",
            event_class=EventClass.CLAIM_CREATE,
            epoch=0,
            issuer="tester",
            target="c1",
            claim_id="c1",
            lineage_id="c1",
            payload={"title": "First"},
        ),
    )
    conflicting = LedgerEvent.create(
        event_id="e1",
        event_class=EventClass.CLAIM_CREATE,
        epoch=0,
        issuer="tester",
        target="c2",
        claim_id="c2",
        lineage_id="c2",
        idempotency_key="e1",
        payload={"title": "Second"},
    )

    with pytest.raises(ValueError, match="duplicate-replay-identity-conflict"):
        append_event(root, conflicting)
