# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

from no_meta_standing_ledger.cli import main


def test_cli_init_add_replay_state(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "claim", "add", "c1", "--title", "Synthetic"]) == 0
    assert (
        main(
            [
                "--root",
                str(root),
                "evidence",
                "add",
                "c1",
                "--uri",
                "https://example.org/evidence.json",
                "--sha256",
                "a" * 64,
                "--size",
                "10",
            ]
        )
        == 0
    )
    assert main(["--root", str(root), "replay"]) == 0
    assert main(["--root", str(root), "explain", "c1"]) == 0
    assert main(["--root", str(root), "validate"]) == 0

    events = [
        json.loads(line)
        for line in (root / ".nmsl" / "public" / "ledger.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [event["logindex"] for event in events] == [0, 1]

    snapshot = json.loads((root / ".nmsl" / "public" / "state.snapshot.json").read_text())
    assert snapshot["claims"]["c1"]["standing"] == "active"
    assert "https://example.org/evidence.json" in json.dumps(snapshot)


def test_cli_replay_refuses_malformed_public_log(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    (root / ".nmsl" / "public" / "ledger.jsonl").write_text("{not-json}\n", encoding="utf-8")

    assert main(["--root", str(root), "replay"]) == 2
    assert main(["--root", str(root), "validate"]) == 1
    assert main(["--root", str(root), "export", "--output", str(tmp_path / "public.jsonl")]) == 2


def test_cli_config_set_and_doctor(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init", "--layer", "full"]) == 0
    assert main(["--root", str(root), "config", "set", "active_capacity", "2"]) == 0
    assert main(["--root", str(root), "config", "set", "reserve_caps.replay", "1"]) == 0
    assert main(["--root", str(root), "doctor"]) == 0

    config = json.loads((root / ".nmsl" / "public" / "config.json").read_text())
    assert config["layer"] == "full"
    assert config["active_capacity"] == 2
    assert config["reserve_caps"]["replay"] == 1


def test_cli_config_set_challenge_kinds_normalizes_policy_maps(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "config", "set", "challenge_kinds", '["replay"]']) == 0

    config = json.loads((root / ".nmsl" / "public" / "config.json").read_text())
    assert config["challenge_kinds"] == ["replay"]
    assert config["blocking_kinds"] == ["replay"]
    assert set(config["reserve_caps"]) == {"replay"}
    assert set(config["contested_timeout"]) == {"replay"}
    assert set(config["audit_weights"]) == {"replay"}


def test_cli_rejects_undeclared_challenge_kind(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "config", "set", "challenge_kinds", '["proof"]']) == 0
    assert main(["--root", str(root), "claim", "add", "c1"]) == 0

    assert main(["--root", str(root), "challenge", "open", "c1", "--kind", "replay"]) == 2


def test_cli_rejects_undeclared_frontier_bucket(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "config", "set", "frontier_buckets", '["novel"]']) == 0

    assert main(["--root", str(root), "claim", "add", "c1"]) == 2
    assert (
        main(["--root", str(root), "claim", "add", "c1", "--frontier-bucket", "novel"])
        == 0
    )


def test_cli_claim_retire_records_retired_standing(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    assert (
        main(
            [
                "--root",
                str(root),
                "claim",
                "add",
                "c1",
                "--initial-standing",
                "active",
            ]
        )
        == 0
    )
    assert main(["--root", str(root), "claim", "retire", "c1", "--epoch", "1"]) == 0
    assert main(["--root", str(root), "replay"]) == 0

    snapshot = json.loads((root / ".nmsl" / "public" / "state.snapshot.json").read_text())
    assert snapshot["claims"]["c1"]["standing"] == "retired"


def test_cli_edge_revoke_uses_later_conflict_record(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init", "--layer", "full"]) == 0
    assert main(["--root", str(root), "claim", "add", "a", "--initial-standing", "active"]) == 0
    assert main(["--root", str(root), "claim", "add", "b", "--initial-standing", "active"]) == 0
    assert main(["--root", str(root), "edge", "add", "a", "b", "--epoch", "1"]) == 0
    assert main(["--root", str(root), "edge", "revoke", "a", "b", "--epoch", "2"]) == 0
    assert main(["--root", str(root), "replay"]) == 0

    snapshot = json.loads((root / ".nmsl" / "public" / "state.snapshot.json").read_text())
    assert not any(edge["authority_bearing"] for edge in snapshot["edges"].values())


def test_cli_evidence_include_content_rejects_over_limit_file(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    evidence = tmp_path / "large.txt"
    evidence.write_text("x" * 10, encoding="utf-8")
    assert main(["--root", str(root), "init"]) == 0
    assert main(["--root", str(root), "claim", "add", "c1"]) == 0
    assert (
        main(
            [
                "--root",
                str(root),
                "evidence",
                "add",
                "c1",
                "--file",
                str(evidence),
                "--include-content",
                "--max-include-bytes",
                "4",
            ]
        )
        == 2
    )


def test_cli_validate_reports_invalid_policy_config(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    config_path = root / ".nmsl" / "public" / "config.json"
    config = json.loads(config_path.read_text())
    config["active_capacity"] = -1
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert main(["--root", str(root), "validate"]) == 1
    assert main(["--root", str(root), "doctor"]) == 1
    assert main(["--root", str(root), "replay"]) == 2


def test_cli_validate_reports_unparseable_policy_config(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0
    config_path = root / ".nmsl" / "public" / "config.json"
    config = json.loads(config_path.read_text())
    config["layer"] = "invalid"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert main(["--root", str(root), "validate"]) == 1
    assert main(["--root", str(root), "doctor"]) == 1


def test_cli_config_set_rejects_string_challenge_kinds(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    assert main(["--root", str(root), "init"]) == 0

    assert main(["--root", str(root), "config", "set", "challenge_kinds", "replay"]) == 2
