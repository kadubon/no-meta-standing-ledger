# SPDX-License-Identifier: Apache-2.0
"""Public ledger validation before replay or export."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from no_meta_standing_ledger.models import (
    SCHEMA_VERSION,
    EdgeLabel,
    EdgeState,
    EventClass,
    LedgerEvent,
    Standing,
)
from no_meta_standing_ledger.policy import PolicyConfig
from no_meta_standing_ledger.privacy import scan_value


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    code: str
    message: str
    location: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "location": self.location,
        }


REQUIRED_FIELDS = {
    "event_id",
    "schema_version",
    "epoch",
    "class",
    "issuer",
    "target",
    "claim_id",
    "lineage_id",
    "obligation_id",
    "idempotency_key",
    "logindex",
    "hash",
    "payload",
}


def validate_log_file(
    path: Path, *, config: PolicyConfig | None = None
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not path.exists():
        return [
            ValidationFinding(
                severity="error",
                code="log-missing",
                message="public ledger JSONL file does not exist",
                location=str(path),
            )
        ]
    seen_identities: dict[tuple[str, str], str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        location = f"{path}:{line_number}"
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="json-invalid",
                    message=str(exc),
                    location=location,
                )
            )
            continue
        if not isinstance(raw, dict):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="event-not-object",
                    message="each JSONL line must be an object",
                    location=location,
                )
            )
            continue
        event_findings = validate_event_dict(raw, location=location)
        findings.extend(event_findings)
        event_id = str(raw.get("event_id", ""))
        idem = str(raw.get("idempotency_key", ""))
        identity = (event_id, idem)
        if event_id and idem:
            if any(item.severity == "error" for item in event_findings):
                continue
            event = LedgerEvent.from_dict(raw)
            if config is not None:
                findings.extend(validate_event_policy(event, config, location=location))
            canonical_body = event.canonical_body()
            previous = seen_identities.get(identity)
            if previous is not None and previous != canonical_body:
                findings.append(
                    ValidationFinding(
                        severity="error",
                        code="duplicate-replay-identity-conflict",
                        message=(
                            "same (event_id, idempotency_key) appears with different "
                            "canonical event bodies"
                        ),
                        location=location,
                    )
                )
            elif previous is not None:
                findings.append(
                    ValidationFinding(
                        severity="warning",
                        code="duplicate-replay-identity",
                        message="exact duplicate replay identity will collapse during replay",
                        location=location,
                    )
                )
            else:
                seen_identities[identity] = canonical_body
    return findings


def validate_events_against_policy(
    events: Iterable[LedgerEvent], config: PolicyConfig
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for index, event in enumerate(events):
        findings.extend(validate_event_policy(event, config, location=f"event[{index}]"))
    return findings


def validate_event_policy(
    event: LedgerEvent, config: PolicyConfig, *, location: str = "$"
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    declared_kinds = set(config.challenge_kinds)
    if event.event_class == EventClass.CHALLENGE_OPEN.value:
        kind = event.payload.get("kind", "replay")
        if not isinstance(kind, str):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="payload-kind-type",
                    message="challenge kind must be a string",
                    location=f"{location}.payload.kind",
                )
            )
        elif kind not in declared_kinds:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="policy-challenge-kind-unknown",
                    message=f"challenge kind is not declared in policy: {kind}",
                    location=f"{location}.payload.kind",
                )
            )
    if event.event_class in {
        EventClass.CHALLENGE_COMPLETE.value,
        EventClass.CHALLENGE_DISCHARGE.value,
    }:
        findings.extend(
            _validate_declared_kind_list(
                event.payload.get("kinds"),
                declared_kinds=declared_kinds,
                location=f"{location}.payload.kinds",
            )
        )
    if event.event_class == EventClass.CLAIM_CREATE.value:
        bucket = event.payload.get("frontier_bucket", "default")
        if not isinstance(bucket, str):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="payload-frontier-bucket-type",
                    message="frontier_bucket must be a string",
                    location=f"{location}.payload.frontier_bucket",
                )
            )
        elif bucket not in set(config.frontier_buckets):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="policy-frontier-bucket-unknown",
                    message=f"frontier bucket is not declared in policy: {bucket}",
                    location=f"{location}.payload.frontier_bucket",
                )
            )
    return findings


def validate_event_dict(value: dict[str, Any], *, location: str = "$") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    missing = sorted(REQUIRED_FIELDS - set(value))
    for field_name in missing:
        findings.append(
            ValidationFinding(
                severity="error",
                code="field-missing",
                message=f"missing required field: {field_name}",
                location=location,
            )
        )
    if missing:
        return findings
    if value.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            ValidationFinding(
                severity="error",
                code="schema-version",
                message=f"unsupported schema_version: {value.get('schema_version')}",
                location=location,
            )
        )
    if value.get("class") not in {item.value for item in EventClass}:
        findings.append(
            ValidationFinding(
                severity="error",
                code="event-class",
                message=f"unknown event class: {value.get('class')}",
                location=location,
            )
        )
    if not isinstance(value.get("payload"), dict):
        findings.append(
            ValidationFinding(
                severity="error",
                code="payload-type",
                message="payload must be an object",
                location=location,
            )
        )
    else:
        findings.extend(_validate_payload_enums(value, location=location))
    for integer_field in ("epoch", "logindex"):
        try:
            integer_value = int(value[integer_field])
        except (TypeError, ValueError):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code=f"{integer_field}-type",
                    message=f"{integer_field} must be an integer",
                    location=location,
                )
            )
            continue
        if integer_value < 0:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code=f"{integer_field}-negative",
                    message=f"{integer_field} must be non-negative",
                    location=location,
                )
            )
    for text_field in ("event_id", "issuer", "target", "idempotency_key", "hash"):
        if not str(value.get(text_field, "")).strip():
            findings.append(
                ValidationFinding(
                    severity="error",
                    code=f"{text_field}-empty",
                    message=f"{text_field} must be non-empty",
                    location=location,
                )
            )
    for item in scan_value(value, path=location):
        findings.append(
            ValidationFinding(
                severity="error",
                code=f"privacy-{item.rule}",
                message=item.message,
                location=item.path,
            )
        )
    if not any(finding.severity == "error" for finding in findings):
        event = LedgerEvent.from_dict(value)
        if event.hash != event.recomputed_hash():
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="hash-mismatch",
                    message="event hash does not match canonical event content",
                    location=location,
                )
            )
    return findings


def _validate_declared_kind_list(
    raw_kinds: Any, *, declared_kinds: set[str], location: str
) -> list[ValidationFinding]:
    if raw_kinds is None:
        return []
    if not isinstance(raw_kinds, list):
        return [
            ValidationFinding(
                severity="error",
                code="payload-kinds-type",
                message="challenge kinds must be a list of strings",
                location=location,
            )
        ]
    findings: list[ValidationFinding] = []
    for index, raw_kind in enumerate(raw_kinds):
        if not isinstance(raw_kind, str):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="payload-kind-type",
                    message="challenge kind must be a string",
                    location=f"{location}[{index}]",
                )
            )
        elif raw_kind not in declared_kinds:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="policy-challenge-kind-unknown",
                    message=f"challenge kind is not declared in policy: {raw_kind}",
                    location=f"{location}[{index}]",
                )
            )
    return findings


def _validate_payload_enums(
    value: dict[str, Any], *, location: str
) -> list[ValidationFinding]:
    payload = value["payload"]
    findings: list[ValidationFinding] = []
    event_class = value.get("class")
    if (
        event_class == EventClass.CLAIM_CREATE.value
        and "initial_standing" in payload
        and payload["initial_standing"] not in {item.value for item in Standing}
    ):
        findings.append(
            ValidationFinding(
                severity="error",
                code="payload-initial-standing",
                message=f"unknown standing: {payload['initial_standing']}",
                location=f"{location}.payload.initial_standing",
            )
        )
    if event_class == EventClass.EDGE_ADD.value:
        if payload.get("label", EdgeLabel.SUPPORTS.value) not in {item.value for item in EdgeLabel}:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="payload-edge-label",
                    message=f"unknown edge label: {payload.get('label')}",
                    location=f"{location}.payload.label",
                )
            )
        if payload.get("state", EdgeState.ACTIVE.value) not in {item.value for item in EdgeState}:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="payload-edge-state",
                    message=f"unknown edge state: {payload.get('state')}",
                    location=f"{location}.payload.state",
                )
            )
    return findings
