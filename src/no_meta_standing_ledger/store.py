# SPDX-License-Identifier: Apache-2.0
"""Filesystem storage for public ledgers."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from no_meta_standing_ledger.models import LedgerEvent, canonical_json
from no_meta_standing_ledger.policy import PolicyConfig, validate_policy_config
from no_meta_standing_ledger.privacy import assert_public_value, scan_jsonl_file
from no_meta_standing_ledger.validation import (
    ValidationFinding,
    validate_event_dict,
    validate_event_policy,
    validate_log_file,
)


@dataclass(frozen=True)
class LedgerPaths:
    root: Path

    @property
    def meta_dir(self) -> Path:
        return self.root / ".nmsl"

    @property
    def public_dir(self) -> Path:
        return self.meta_dir / "public"

    @property
    def config_path(self) -> Path:
        return self.public_dir / "config.json"

    @property
    def log_path(self) -> Path:
        return self.public_dir / "ledger.jsonl"

    @property
    def snapshot_path(self) -> Path:
        return self.public_dir / "state.snapshot.json"


def init_ledger(root: Path, *, config: PolicyConfig | None = None) -> LedgerPaths:
    paths = LedgerPaths(root=root)
    paths.public_dir.mkdir(parents=True, exist_ok=True)
    paths.log_path.touch(exist_ok=True)
    if not paths.config_path.exists():
        policy = config or PolicyConfig()
        _raise_policy_errors(policy)
        write_json(paths.config_path, policy.to_dict())
    return paths


def load_config(root: Path) -> PolicyConfig:
    paths = LedgerPaths(root=root)
    if not paths.config_path.exists():
        return PolicyConfig()
    raw = json.loads(paths.config_path.read_text(encoding="utf-8"))
    return PolicyConfig.from_dict(raw)


def write_config(root: Path, config: PolicyConfig) -> None:
    _raise_policy_errors(config)
    write_json(LedgerPaths(root=root).config_path, config.to_dict())


def append_event(root: Path, event: LedgerEvent) -> None:
    paths = init_ledger(root)
    config = load_config(root)
    _raise_validation_errors(
        validate_log_file(paths.log_path, config=config), context="existing ledger"
    )
    event_dict = event.to_dict()
    assert_public_value(event_dict, context="ledger event")
    _raise_validation_errors(
        validate_event_dict(event_dict) + validate_event_policy(event, config),
        context="ledger event",
    )
    _raise_duplicate_identity_conflict(paths.log_path, event)
    with paths.log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(event_dict))
        handle.write("\n")


def next_logindex(root: Path) -> int:
    paths = init_ledger(root)
    return sum(
        1 for line in paths.log_path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def read_events(root: Path) -> list[LedgerEvent]:
    paths = LedgerPaths(root=root)
    if not paths.log_path.exists():
        return []
    events: list[LedgerEvent] = []
    for line in paths.log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(LedgerEvent.from_dict(json.loads(line)))
    return events


def write_snapshot(root: Path, value: dict[str, object]) -> None:
    paths = init_ledger(root)
    write_json(paths.snapshot_path, value)


def read_snapshot(root: Path) -> dict[str, object] | None:
    path = LedgerPaths(root=root).snapshot_path
    if not path.exists():
        return None
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def export_public_log(root: Path, output: Path) -> None:
    paths = LedgerPaths(root=root)
    _raise_validation_errors(
        validate_log_file(paths.log_path, config=load_config(root)), context="public export"
    )
    findings = scan_jsonl_file(paths.log_path)
    if findings:
        formatted = "\n".join(f"- {item.path}: {item.rule}: {item.message}" for item in findings)
        raise ValueError(f"public export blocked by privacy findings:\n{formatted}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.log_path, output)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _raise_policy_errors(config: PolicyConfig) -> None:
    findings = validate_policy_config(config)
    if findings:
        formatted = "\n".join(f"- {item.code}: {item.message}" for item in findings)
        raise ValueError(f"policy config failed validation:\n{formatted}")


def _raise_duplicate_identity_conflict(path: Path, event: LedgerEvent) -> None:
    if not path.exists():
        return
    identity = event.replay_identity()
    canonical_body = event.canonical_body()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        existing = LedgerEvent.from_dict(json.loads(line))
        if existing.replay_identity() != identity:
            continue
        if existing.canonical_body() != canonical_body:
            raise ValueError(
                "ledger event failed validation:\n"
                f"- {path}:{line_number}: duplicate-replay-identity-conflict: "
                "same (event_id, idempotency_key) already exists with a different "
                "canonical event body"
            )


def _raise_validation_errors(findings: list[ValidationFinding], *, context: str) -> None:
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        formatted = "\n".join(
            f"- {item.location}: {item.code}: {item.message}" for item in errors
        )
        raise ValueError(f"{context} failed validation:\n{formatted}")
