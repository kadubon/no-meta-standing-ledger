# SPDX-License-Identifier: Apache-2.0
"""Declared policy parameters for replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from no_meta_standing_ledger.models import DEFAULT_CHALLENGE_KINDS, JsonDict, Layer


@dataclass(frozen=True)
class PolicyFinding:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class PolicyConfig:
    layer: Layer = Layer.STANDARD
    challenge_kinds: tuple[str, ...] = DEFAULT_CHALLENGE_KINDS
    blocking_kinds: frozenset[str] = field(
        default_factory=lambda: frozenset(DEFAULT_CHALLENGE_KINDS)
    )
    active_capacity: int = 100
    frontier_capacity: int = 20
    hot_memory_capacity_bits: int = 4096
    frontier_metadata_capacity_bits: int = 2048
    retained_summary_slot_bits: int = 64
    frontier_metadata_slot_bits: int = 32
    family_token_cap: int = 3
    support_horizon: int = 30
    restoration_lag: int = 1
    frontier_horizon: int = 10
    duplicate_horizon: int = 10
    family_horizon: int = 10
    reserve_caps: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(DEFAULT_CHALLENGE_KINDS, 100)
    )
    contested_timeout: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(DEFAULT_CHALLENGE_KINDS, 30)
    )
    audit_weights: dict[str, float] = field(
        default_factory=lambda: dict.fromkeys(DEFAULT_CHALLENGE_KINDS, 1.0)
    )
    frontier_buckets: tuple[str, ...] = ("default",)
    frontier_reservations: dict[str, int] = field(default_factory=lambda: {"default": 20})

    @classmethod
    def from_dict(cls, value: JsonDict) -> Self:
        kinds = _str_tuple(value.get("challenge_kinds", DEFAULT_CHALLENGE_KINDS), "challenge_kinds")
        frontier_buckets = _str_tuple(
            value.get("frontier_buckets", ("default",)), "frontier_buckets"
        )
        return cls(
            layer=Layer(str(value.get("layer", Layer.STANDARD.value))),
            challenge_kinds=kinds,
            blocking_kinds=frozenset(
                _str_tuple(value.get("blocking_kinds", kinds), "blocking_kinds")
            ),
            active_capacity=int(value.get("active_capacity", 100)),
            frontier_capacity=int(value.get("frontier_capacity", 20)),
            hot_memory_capacity_bits=int(value.get("hot_memory_capacity_bits", 4096)),
            frontier_metadata_capacity_bits=int(
                value.get("frontier_metadata_capacity_bits", 2048)
            ),
            retained_summary_slot_bits=int(value.get("retained_summary_slot_bits", 64)),
            frontier_metadata_slot_bits=int(value.get("frontier_metadata_slot_bits", 32)),
            family_token_cap=int(value.get("family_token_cap", 3)),
            support_horizon=int(value.get("support_horizon", 30)),
            restoration_lag=int(value.get("restoration_lag", 1)),
            frontier_horizon=int(value.get("frontier_horizon", 10)),
            duplicate_horizon=int(value.get("duplicate_horizon", 10)),
            family_horizon=int(value.get("family_horizon", 10)),
            reserve_caps=_int_dict(value.get("reserve_caps", dict.fromkeys(kinds, 100))),
            contested_timeout=_int_dict(
                value.get("contested_timeout", dict.fromkeys(kinds, 30))
            ),
            audit_weights=_float_dict(value.get("audit_weights", dict.fromkeys(kinds, 1.0))),
            frontier_buckets=frontier_buckets,
            frontier_reservations=_int_dict(value.get("frontier_reservations", {"default": 20})),
        )

    def to_dict(self) -> JsonDict:
        return {
            "layer": self.layer.value,
            "challenge_kinds": list(self.challenge_kinds),
            "blocking_kinds": sorted(self.blocking_kinds),
            "active_capacity": self.active_capacity,
            "frontier_capacity": self.frontier_capacity,
            "hot_memory_capacity_bits": self.hot_memory_capacity_bits,
            "frontier_metadata_capacity_bits": self.frontier_metadata_capacity_bits,
            "retained_summary_slot_bits": self.retained_summary_slot_bits,
            "frontier_metadata_slot_bits": self.frontier_metadata_slot_bits,
            "family_token_cap": self.family_token_cap,
            "support_horizon": self.support_horizon,
            "restoration_lag": self.restoration_lag,
            "frontier_horizon": self.frontier_horizon,
            "duplicate_horizon": self.duplicate_horizon,
            "family_horizon": self.family_horizon,
            "reserve_caps": self.reserve_caps,
            "contested_timeout": self.contested_timeout,
            "audit_weights": self.audit_weights,
            "frontier_buckets": list(self.frontier_buckets),
            "frontier_reservations": self.frontier_reservations,
        }


def validate_policy_config(config: PolicyConfig) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    if not config.challenge_kinds:
        findings.append(
            PolicyFinding("challenge-kinds-empty", "at least one challenge kind is required")
        )
    if not config.frontier_buckets:
        findings.append(
            PolicyFinding("frontier-buckets-empty", "at least one frontier bucket is required")
        )
    if not set(config.blocking_kinds).issubset(set(config.challenge_kinds)):
        findings.append(
            PolicyFinding(
                "blocking-kind-unknown",
                "blocking_kinds must be a subset of challenge_kinds",
            )
        )
    for name in (
        "active_capacity",
        "frontier_capacity",
        "hot_memory_capacity_bits",
        "frontier_metadata_capacity_bits",
        "retained_summary_slot_bits",
        "frontier_metadata_slot_bits",
        "family_token_cap",
        "support_horizon",
        "restoration_lag",
        "frontier_horizon",
        "duplicate_horizon",
        "family_horizon",
    ):
        value = int(getattr(config, name))
        if value < 0:
            findings.append(PolicyFinding(f"{name}-negative", f"{name} must be non-negative"))
    for name in ("retained_summary_slot_bits", "frontier_metadata_slot_bits"):
        if int(getattr(config, name)) <= 0:
            findings.append(PolicyFinding(f"{name}-zero", f"{name} must be positive"))
    findings.extend(_validate_int_map(config.reserve_caps, "reserve_caps"))
    findings.extend(_validate_int_map(config.contested_timeout, "contested_timeout"))
    findings.extend(_validate_float_map(config.audit_weights, "audit_weights"))
    findings.extend(_validate_int_map(config.frontier_reservations, "frontier_reservations"))
    unknown_reserve = sorted(set(config.reserve_caps) - set(config.challenge_kinds))
    if unknown_reserve:
        findings.append(
            PolicyFinding(
                "reserve-kind-unknown",
                f"reserve_caps contains unknown challenge kinds: {', '.join(unknown_reserve)}",
            )
        )
    unknown_timeout = sorted(set(config.contested_timeout) - set(config.challenge_kinds))
    if unknown_timeout:
        findings.append(
            PolicyFinding(
                "timeout-kind-unknown",
                f"contested_timeout contains unknown challenge kinds: {', '.join(unknown_timeout)}",
            )
        )
    unknown_weight = sorted(set(config.audit_weights) - set(config.challenge_kinds))
    if unknown_weight:
        findings.append(
            PolicyFinding(
                "audit-weight-kind-unknown",
                f"audit_weights contains unknown challenge kinds: {', '.join(unknown_weight)}",
            )
        )
    for map_name, map_value in (
        ("reserve_caps", config.reserve_caps),
        ("contested_timeout", config.contested_timeout),
        ("audit_weights", config.audit_weights),
    ):
        missing = sorted(set(config.challenge_kinds) - set(map_value))
        if missing:
            findings.append(
                PolicyFinding(
                    f"{map_name}-kind-missing",
                    f"{map_name} is missing declared challenge kinds: {', '.join(missing)}",
                )
            )
    unknown_bucket = sorted(set(config.frontier_reservations) - set(config.frontier_buckets))
    if unknown_bucket:
        findings.append(
            PolicyFinding(
                "frontier-bucket-unknown",
                "frontier_reservations contains buckets not declared in frontier_buckets: "
                + ", ".join(unknown_bucket),
            )
        )
    missing_bucket = sorted(set(config.frontier_buckets) - set(config.frontier_reservations))
    if missing_bucket:
        findings.append(
            PolicyFinding(
                "frontier-reservation-bucket-missing",
                "frontier_reservations is missing declared buckets: "
                + ", ".join(missing_bucket),
            )
        )
    return findings


def validate_policy_dict(value: JsonDict) -> list[PolicyFinding]:
    try:
        return validate_policy_config(PolicyConfig.from_dict(value))
    except (TypeError, ValueError) as exc:
        return [PolicyFinding("config-parse", str(exc))]


def _str_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list | tuple | set | frozenset):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(str(item) for item in value)


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("integer policy maps must be objects")
    return {str(key): int(raw) for key, raw in value.items()}


def _float_dict(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("float policy maps must be objects")
    return {str(key): float(raw) for key, raw in value.items()}


def _validate_int_map(value: dict[str, int], name: str) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for key, item in value.items():
        if item < 0:
            findings.append(
                PolicyFinding(f"{name}.{key}-negative", f"{name}.{key} must be non-negative")
            )
    return findings


def _validate_float_map(value: dict[str, float], name: str) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for key, item in value.items():
        if item < 0:
            findings.append(
                PolicyFinding(f"{name}.{key}-negative", f"{name}.{key} must be non-negative")
            )
    return findings
