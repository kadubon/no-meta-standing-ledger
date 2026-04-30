# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for no-meta-standing-ledger."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import cast

from no_meta_standing_ledger.audit import check_invariants
from no_meta_standing_ledger.demos import DEMO_BUILDERS
from no_meta_standing_ledger.evidence import (
    DEFAULT_MAX_INCLUDE_BYTES,
    evidence_payload_from_file,
    evidence_payload_from_uri,
)
from no_meta_standing_ledger.explain import explain_claim
from no_meta_standing_ledger.models import EventClass, LedgerEvent, canonical_json
from no_meta_standing_ledger.policy import (
    PolicyConfig,
    validate_policy_config,
    validate_policy_dict,
)
from no_meta_standing_ledger.privacy import assert_public_value
from no_meta_standing_ledger.replay import audit_summary, replay_events
from no_meta_standing_ledger.store import (
    append_event,
    export_public_log,
    init_ledger,
    load_config,
    next_logindex,
    read_events,
    read_snapshot,
    write_config,
    write_snapshot,
)
from no_meta_standing_ledger.validation import validate_log_file


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"nmsl: error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nmsl")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="ledger root directory")
    sub = parser.add_subparsers(required=True)

    init_cmd = sub.add_parser("init", help="initialize a local public ledger")
    init_cmd.add_argument("--layer", choices=["lite", "standard", "full"], default="standard")
    init_cmd.set_defaults(func=_cmd_init)

    config_cmd = sub.add_parser("config", help="inspect or update declared replay policy")
    config_sub = config_cmd.add_subparsers(required=True)
    config_show = config_sub.add_parser("show", help="print declared policy config")
    config_show.set_defaults(func=_cmd_config_show)
    config_set = config_sub.add_parser("set", help="set a declared policy config value")
    config_set.add_argument(
        "key", help="top-level key or dotted map key such as reserve_caps.replay"
    )
    config_set.add_argument("value", help="JSON value, integer, float, or string")
    config_set.set_defaults(func=_cmd_config_set)

    claim_cmd = sub.add_parser("claim", help="claim commands")
    claim_sub = claim_cmd.add_subparsers(required=True)
    claim_add = claim_sub.add_parser("add", help="add a public claim")
    claim_add.add_argument("claim_id")
    claim_add.add_argument("--title", default="")
    claim_add.add_argument("--text", default="")
    claim_add.add_argument("--lineage-id")
    claim_add.add_argument("--family-id")
    claim_add.add_argument("--frontier-bucket", default="default")
    claim_add.add_argument("--epoch", type=int, default=0)
    claim_add.add_argument("--issuer", default="public")
    claim_add.add_argument("--initial-standing", default="proposed")
    claim_add.set_defaults(func=_cmd_claim_add)
    claim_retire = claim_sub.add_parser("retire", help="retire a public claim")
    claim_retire.add_argument("claim_id")
    claim_retire.add_argument("--reason", default="")
    claim_retire.add_argument("--epoch", type=int, default=0)
    claim_retire.add_argument("--issuer", default="public")
    claim_retire.set_defaults(func=_cmd_claim_retire)

    evidence_cmd = sub.add_parser("evidence", help="evidence commands")
    evidence_sub = evidence_cmd.add_subparsers(required=True)
    evidence_add = evidence_sub.add_parser("add", help="add public evidence metadata")
    evidence_add.add_argument("claim_id")
    source = evidence_add.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--uri")
    evidence_add.add_argument("--sha256")
    evidence_add.add_argument("--size", type=int)
    evidence_add.add_argument("--content-type")
    evidence_add.add_argument("--include-content", action="store_true")
    evidence_add.add_argument("--max-include-bytes", type=int, default=DEFAULT_MAX_INCLUDE_BYTES)
    evidence_add.add_argument("--no-support", action="store_true")
    evidence_add.add_argument("--epoch", type=int, default=0)
    evidence_add.add_argument("--issuer", default="public")
    evidence_add.set_defaults(func=_cmd_evidence_add)

    challenge_cmd = sub.add_parser("challenge", help="challenge commands")
    challenge_sub = challenge_cmd.add_subparsers(required=True)
    challenge_open = challenge_sub.add_parser("open", help="open a typed public challenge")
    challenge_open.add_argument("claim_id")
    challenge_open.add_argument("--kind", default="replay")
    challenge_open.add_argument("--obligation-id")
    challenge_open.add_argument("--epoch", type=int, default=0)
    challenge_open.add_argument("--issuer", default="public")
    challenge_open.set_defaults(func=_cmd_challenge_open)
    challenge_complete = challenge_sub.add_parser(
        "complete", help="complete typed public challenge service"
    )
    challenge_complete.add_argument("claim_id")
    challenge_complete.add_argument("--kind", action="append")
    challenge_complete.add_argument("--obligation-id")
    challenge_complete.add_argument("--epoch", type=int, default=0)
    challenge_complete.add_argument("--issuer", default="public")
    challenge_complete.set_defaults(func=_cmd_challenge_complete)

    discharge = sub.add_parser("discharge", help="discharge typed challenge classes")
    discharge.add_argument("claim_id")
    discharge.add_argument("--kind", action="append", required=True)
    discharge.add_argument("--epoch", type=int, default=0)
    discharge.add_argument("--issuer", default="public")
    discharge.set_defaults(func=_cmd_discharge)

    edge_cmd = sub.add_parser("edge", help="edge commands")
    edge_sub = edge_cmd.add_subparsers(required=True)
    edge_add = edge_sub.add_parser("add", help="add a declared relation edge")
    edge_add.add_argument("source")
    edge_add.add_argument("target")
    edge_add.add_argument(
        "--label",
        choices=["supports", "attacks", "depends", "refines", "supersedes", "aggregates"],
        default="supports",
    )
    edge_add.add_argument("--binding", default="")
    edge_add.add_argument("--conflict-tag")
    edge_add.add_argument("--epoch", type=int, default=0)
    edge_add.add_argument("--issuer", default="public")
    edge_add.set_defaults(func=_cmd_edge_add)
    edge_revoke = edge_sub.add_parser("revoke", help="revoke a declared relation edge")
    edge_revoke.add_argument("source")
    edge_revoke.add_argument("target")
    edge_revoke.add_argument(
        "--label",
        choices=["supports", "attacks", "depends", "refines", "supersedes", "aggregates"],
        default="supports",
    )
    edge_revoke.add_argument("--binding", default="")
    edge_revoke.add_argument("--conflict-tag")
    edge_revoke.add_argument("--epoch", type=int, default=0)
    edge_revoke.add_argument("--issuer", default="public")
    edge_revoke.set_defaults(func=_cmd_edge_revoke)
    edge_transfer = edge_sub.add_parser("transfer", help="transfer a declared relation edge")
    edge_transfer.add_argument("source")
    edge_transfer.add_argument("target")
    edge_transfer.add_argument("--new-source", required=True)
    edge_transfer.add_argument("--new-target", required=True)
    edge_transfer.add_argument(
        "--label",
        choices=["supports", "attacks", "depends", "refines", "supersedes", "aggregates"],
        default="supports",
    )
    edge_transfer.add_argument("--binding", default="")
    edge_transfer.add_argument("--conflict-tag")
    edge_transfer.add_argument("--epoch", type=int, default=0)
    edge_transfer.add_argument("--issuer", default="public")
    edge_transfer.set_defaults(func=_cmd_edge_transfer)

    lineage_cmd = sub.add_parser("lineage", help="lineage commands")
    lineage_sub = lineage_cmd.add_subparsers(required=True)
    lineage_supersede = lineage_sub.add_parser("supersede", help="supersede a claim lineage")
    lineage_supersede.add_argument("old_claim_id")
    lineage_supersede.add_argument("successor_claim_id")
    lineage_supersede.add_argument("--epoch", type=int, default=0)
    lineage_supersede.add_argument("--issuer", default="public")
    lineage_supersede.set_defaults(func=_cmd_lineage_supersede)

    memory_cmd = sub.add_parser("memory", help="hot restoration memory commands")
    memory_sub = memory_cmd.add_subparsers(required=True)
    memory_forget = memory_sub.add_parser("forget", help="archive a lineage out of hot memory")
    memory_forget.add_argument("claim_id")
    memory_forget.add_argument("--epoch", type=int, default=0)
    memory_forget.add_argument("--issuer", default="public")
    memory_forget.set_defaults(func=_cmd_memory_forget)
    memory_rehydrate = memory_sub.add_parser("rehydrate", help="restore a lineage into hot memory")
    memory_rehydrate.add_argument("claim_id")
    memory_rehydrate.add_argument("--epoch", type=int, default=0)
    memory_rehydrate.add_argument("--issuer", default="public")
    memory_rehydrate.set_defaults(func=_cmd_memory_rehydrate)

    replay_cmd = sub.add_parser("replay", help="replay the public log into a snapshot")
    replay_cmd.set_defaults(func=_cmd_replay)

    state_cmd = sub.add_parser("state", help="print the latest replay snapshot")
    state_cmd.add_argument("--replay", action="store_true", help="replay before printing")
    state_cmd.set_defaults(func=_cmd_state)

    audit_cmd = sub.add_parser("audit", help="print audit counters")
    audit_cmd.set_defaults(func=_cmd_audit)

    explain_cmd = sub.add_parser("explain", help="explain one claim's replayed standing")
    explain_cmd.add_argument("claim_id")
    explain_cmd.set_defaults(func=_cmd_explain)

    validate_cmd = sub.add_parser("validate", help="validate public JSONL ledger safety/schema")
    validate_cmd.set_defaults(func=_cmd_validate)

    doctor_cmd = sub.add_parser("doctor", help="run operational readiness checks")
    doctor_cmd.set_defaults(func=_cmd_doctor)

    export_cmd = sub.add_parser("export", help="export the public JSONL log after privacy checks")
    export_cmd.add_argument("--output", type=Path, required=True)
    export_cmd.set_defaults(func=_cmd_export)

    demo_cmd = sub.add_parser("demo", help="write a synthetic demo ledger")
    demo_cmd.add_argument("--name", choices=sorted(DEMO_BUILDERS), default="three-claim-dependency")
    demo_cmd.add_argument("--layer", choices=["lite", "standard", "full"], default="full")
    demo_cmd.set_defaults(func=_cmd_demo)

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    init_ledger(args.root, config=PolicyConfig.from_dict({"layer": args.layer}))
    print(f"initialized {args.root / '.nmsl' / 'public'}")
    return 0


def _cmd_config_show(args: argparse.Namespace) -> int:
    init_ledger(args.root)
    print(json.dumps(load_config(args.root).to_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_config_set(args: argparse.Namespace) -> int:
    init_ledger(args.root)
    raw = load_config(args.root).to_dict()
    _set_config_value(raw, args.key, _parse_config_value(args.value))
    _normalize_policy_maps(raw)
    config = PolicyConfig.from_dict(raw)
    findings = validate_policy_config(config)
    if findings:
        formatted = "\n".join(f"- {item.code}: {item.message}" for item in findings)
        raise ValueError(f"policy config update rejected:\n{formatted}")
    write_config(args.root, config)
    print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_claim_add(args: argparse.Namespace) -> int:
    _ensure_declared_frontier_bucket(args.root, args.frontier_bucket)
    payload = {
        "title": args.title,
        "text": args.text,
        "initial_standing": args.initial_standing,
        "family_id": args.family_id or args.claim_id.split(":", 1)[0],
        "frontier_bucket": args.frontier_bucket,
    }
    assert_public_value(payload, context="claim payload")
    event = _event(
        args,
        event_class=EventClass.CLAIM_CREATE,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.lineage_id or args.claim_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_claim_retire(args: argparse.Namespace) -> int:
    payload = {"reason": args.reason}
    assert_public_value(payload, context="retirement payload")
    event = _event(
        args,
        event_class=EventClass.CLAIM_RETIRE,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_evidence_add(args: argparse.Namespace) -> int:
    if args.file is not None:
        payload = evidence_payload_from_file(
            args.file,
            content_type=args.content_type,
            include_content=args.include_content,
            max_include_bytes=args.max_include_bytes,
            support=not args.no_support,
        )
    else:
        payload = evidence_payload_from_uri(
            args.uri,
            sha256=args.sha256,
            size=args.size,
            content_type=args.content_type,
            support=not args.no_support,
        )
    event = _event(
        args,
        event_class=EventClass.EVIDENCE_ADD,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_challenge_open(args: argparse.Namespace) -> int:
    _ensure_declared_challenge_kinds(args.root, [args.kind])
    obligation_id = args.obligation_id or f"obl-{uuid.uuid4()}"
    payload = {"kind": args.kind}
    event = _event(
        args,
        event_class=EventClass.CHALLENGE_OPEN,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        obligation_id=obligation_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_challenge_complete(args: argparse.Namespace) -> int:
    if not args.kind and args.obligation_id is None:
        raise ValueError("challenge complete requires --kind or --obligation-id")
    if args.kind:
        _ensure_declared_challenge_kinds(args.root, args.kind)
    payload: dict[str, object] = {}
    if args.kind:
        payload["kinds"] = args.kind
    event = _event(
        args,
        event_class=EventClass.CHALLENGE_COMPLETE,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        obligation_id=args.obligation_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_discharge(args: argparse.Namespace) -> int:
    _ensure_declared_challenge_kinds(args.root, args.kind)
    payload = {"kinds": args.kind}
    event = _event(
        args,
        event_class=EventClass.CHALLENGE_DISCHARGE,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_memory_forget(args: argparse.Namespace) -> int:
    event = _event(
        args,
        event_class=EventClass.MEMORY_FORGET,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        payload={"mode": "archive"},
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_memory_rehydrate(args: argparse.Namespace) -> int:
    event = _event(
        args,
        event_class=EventClass.MEMORY_REHYDRATE,
        target=args.claim_id,
        claim_id=args.claim_id,
        lineage_id=args.claim_id,
        payload={"mode": "rehydrate"},
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_edge_add(args: argparse.Namespace) -> int:
    payload = {
        "source": args.source,
        "target": args.target,
        "label": args.label,
        "binding": args.binding,
        "state": "active",
        "conflict_tag": args.conflict_tag
        or _edge_conflict_tag(args.source, args.target, args.label, args.binding),
    }
    assert_public_value(payload, context="edge payload")
    event = _event(
        args,
        event_class=EventClass.EDGE_ADD,
        target=args.target,
        claim_id=args.source,
        lineage_id=args.source,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_edge_revoke(args: argparse.Namespace) -> int:
    payload = {
        "source": args.source,
        "target": args.target,
        "label": args.label,
        "binding": args.binding,
        "state": "revoked",
        "conflict_tag": args.conflict_tag
        or _edge_conflict_tag(args.source, args.target, args.label, args.binding),
    }
    assert_public_value(payload, context="edge revoke payload")
    event = _event(
        args,
        event_class=EventClass.EDGE_ADD,
        target=args.target,
        claim_id=args.source,
        lineage_id=args.source,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_edge_transfer(args: argparse.Namespace) -> int:
    payload = {
        "source": args.new_source,
        "target": args.new_target,
        "previous_source": args.source,
        "previous_target": args.target,
        "label": args.label,
        "binding": args.binding,
        "state": "transferred",
        "conflict_tag": args.conflict_tag
        or _edge_conflict_tag(args.source, args.target, args.label, args.binding),
    }
    assert_public_value(payload, context="edge transfer payload")
    event = _event(
        args,
        event_class=EventClass.EDGE_ADD,
        target=args.new_target,
        claim_id=args.new_source,
        lineage_id=args.new_source,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_lineage_supersede(args: argparse.Namespace) -> int:
    payload = {
        "successor_claim_id": args.successor_claim_id,
        "successor_lineage_id": args.successor_claim_id,
    }
    event = _event(
        args,
        event_class=EventClass.LINEAGE_SUPERSEDE,
        target=args.old_claim_id,
        claim_id=args.old_claim_id,
        lineage_id=args.old_claim_id,
        payload=payload,
    )
    append_event(args.root, event)
    print(event.event_id)
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    snapshot = _replay_snapshot(args.root)
    write_snapshot(args.root, snapshot)
    print(canonical_json({"snapshot": str(args.root / ".nmsl" / "public" / "state.snapshot.json")}))
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    if args.replay:
        snapshot = _replay_snapshot(args.root)
        write_snapshot(args.root, snapshot)
    else:
        snapshot = read_snapshot(args.root) or _replay_snapshot(args.root)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    cfg = _load_valid_config(args.root)
    state = replay_events(_read_valid_events(args.root), cfg)
    summary = audit_summary(state)
    summary["invariant_findings"] = [item.to_dict() for item in check_invariants(state, cfg)]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    cfg = _load_valid_config(args.root)
    state = replay_events(_read_valid_events(args.root), cfg)
    print(json.dumps(explain_claim(state, args.claim_id, cfg), indent=2, sort_keys=True))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    paths = init_ledger(args.root)
    config_dict = _read_config_dict(paths.config_path)
    policy_findings = validate_policy_dict(config_dict)
    config = PolicyConfig.from_dict(config_dict) if not policy_findings else None
    findings = validate_log_file(paths.log_path, config=config)
    result = {
        "ok": not any(item.severity == "error" for item in findings) and not policy_findings,
        "findings": [item.to_dict() for item in findings],
        "policy_findings": [item.to_dict() for item in policy_findings],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    paths = init_ledger(args.root)
    config_dict = _read_config_dict(paths.config_path)
    policy_findings = validate_policy_dict(config_dict)
    snapshot: dict[str, object] | None = None
    invariant_findings: list[dict[str, str]] = []
    config = PolicyConfig.from_dict(config_dict) if not policy_findings else None
    validation_findings = validate_log_file(paths.log_path, config=config)
    validation_errors = [item for item in validation_findings if item.severity == "error"]
    if not validation_errors and not policy_findings:
        if config is None:
            raise ValueError("policy config could not be loaded")
        state = replay_events(read_events(args.root), config)
        snapshot = state.to_dict()
        invariant_findings = [item.to_dict() for item in check_invariants(state, config)]
    result = {
        "ok": not validation_errors and not policy_findings and not invariant_findings,
        "root": str(args.root),
        "ledger": str(paths.log_path),
        "config": config.to_dict() if config is not None else config_dict,
        "event_validation": [item.to_dict() for item in validation_findings],
        "policy_findings": [item.to_dict() for item in policy_findings],
        "invariant_findings": invariant_findings,
        "summary": _doctor_summary(snapshot),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def _cmd_export(args: argparse.Namespace) -> int:
    export_public_log(args.root, args.output)
    print(str(args.output))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    init_ledger(args.root, config=PolicyConfig.from_dict({"layer": args.layer}))
    for event in DEMO_BUILDERS[args.name]():
        append_event(args.root, event)
    snapshot = _replay_snapshot(args.root)
    write_snapshot(args.root, snapshot)
    print(f"wrote demo {args.name}")
    return 0


def _replay_snapshot(root: Path) -> dict[str, object]:
    cfg = _load_valid_config(root)
    state = replay_events(_read_valid_events(root), cfg)
    return state.to_dict()


def _load_valid_config(root: Path) -> PolicyConfig:
    config = load_config(root)
    findings = validate_policy_config(config)
    if findings:
        formatted = "\n".join(f"- {item.code}: {item.message}" for item in findings)
        raise ValueError(f"policy config failed validation:\n{formatted}")
    return config


def _read_valid_events(root: Path) -> list[LedgerEvent]:
    paths = init_ledger(root)
    findings = validate_log_file(paths.log_path, config=_load_valid_config(root))
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        first = errors[0]
        raise ValueError(
            "ledger validation failed before replay; "
            f"first error at {first.location}: {first.code}: {first.message}; "
            "run `nmsl validate` for the full report"
        )
    return read_events(root)


def _event(
    args: argparse.Namespace,
    *,
    event_class: EventClass,
    target: str,
    payload: dict[str, object],
    claim_id: str | None = None,
    lineage_id: str | None = None,
    obligation_id: str | None = None,
) -> LedgerEvent:
    event_id = f"evt-{uuid.uuid4()}"
    return LedgerEvent.create(
        event_id=event_id,
        event_class=event_class,
        epoch=args.epoch,
        issuer=args.issuer,
        target=target,
        claim_id=claim_id,
        lineage_id=lineage_id,
        obligation_id=obligation_id,
        idempotency_key=event_id,
        logindex=next_logindex(args.root),
        payload=payload,
    )


def _parse_config_value(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def _read_config_dict(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config.json must contain a JSON object")
    return cast(dict[str, object], raw)


def _set_config_value(config: dict[str, object], key: str, value: object) -> None:
    parts = key.split(".")
    if len(parts) == 1:
        if parts[0] not in config:
            raise ValueError(f"unknown config key: {key}")
        config[parts[0]] = value
        return
    if len(parts) != 2:
        raise ValueError("config keys may be top-level or one-level dotted map keys")
    parent, child = parts
    if parent not in config or not isinstance(config[parent], dict):
        raise ValueError(f"unknown map config key: {parent}")
    map_value = cast(dict[str, object], config[parent]).copy()
    map_value[child] = value
    config[parent] = map_value


def _normalize_policy_maps(config: dict[str, object]) -> None:
    raw_kinds = config.get("challenge_kinds", [])
    if isinstance(raw_kinds, list):
        kinds = [str(item) for item in raw_kinds]
        config["reserve_caps"] = _normalize_map(config.get("reserve_caps"), kinds, 100)
        config["contested_timeout"] = _normalize_map(config.get("contested_timeout"), kinds, 30)
        config["audit_weights"] = _normalize_map(config.get("audit_weights"), kinds, 1.0)
        blocking = config.get("blocking_kinds", kinds)
        if isinstance(blocking, list):
            config["blocking_kinds"] = [str(item) for item in blocking if str(item) in kinds]
    raw_buckets = config.get("frontier_buckets", [])
    if isinstance(raw_buckets, list):
        buckets = [str(item) for item in raw_buckets]
        config["frontier_reservations"] = _normalize_map(
            config.get("frontier_reservations"), buckets, 20
        )


def _normalize_map(raw: object, keys: list[str], default: object) -> dict[str, object]:
    existing = raw if isinstance(raw, dict) else {}
    return {key: existing.get(key, default) for key in keys}


def _ensure_declared_challenge_kinds(root: Path, kinds: list[str]) -> None:
    config = _load_valid_config(root)
    unknown = sorted(set(kinds) - set(config.challenge_kinds))
    if unknown:
        raise ValueError(
            "challenge kind is not declared in policy: "
            + ", ".join(unknown)
            + "; update challenge_kinds first"
        )


def _ensure_declared_frontier_bucket(root: Path, bucket: str) -> None:
    config = _load_valid_config(root)
    if bucket not in set(config.frontier_buckets):
        raise ValueError(
            "frontier bucket is not declared in policy: "
            f"{bucket}; update frontier_buckets first"
        )


def _edge_conflict_tag(source: str, target: str, label: str, binding: str) -> str:
    return f"edge:{source}:{target}:{label}:{binding}"


def _doctor_summary(snapshot: dict[str, object] | None) -> dict[str, object]:
    if snapshot is None:
        return {}
    claims = snapshot.get("claims", {})
    obligations = snapshot.get("obligations", {})
    service = snapshot.get("service", {})
    return {
        "claims": len(claims) if isinstance(claims, dict) else 0,
        "obligations": len(obligations) if isinstance(obligations, dict) else 0,
        "service": service if isinstance(service, dict) else {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
