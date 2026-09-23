"""Local, recorded-export benchmark for accepted customer-support work.

This module ranks no vendors, runs no agents, and makes no causal or real-world
verification claim. It builds on the local Evidence Bridge and Passport.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .bridge import build as build_bridge, verify as verify_bridge


BENCH_VERSION = "0.1.0"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _protocol(path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    required = {"schema_version", "id", "version", "workload", "passport_protocol", "minimum_eligible_cases_per_arm", "minimum_acceptance_rate", "claim_policy"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("benchmark protocol has missing or unexpected fields")
    if value["schema_version"] != BENCH_VERSION or value["claim_policy"] != "DESCRIPTIVE_ONLY":
        raise ValueError("unsupported benchmark protocol or claim policy")
    for key in ("id", "version", "workload"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"protocol.{key} must be nonempty text")
    minimum = value["minimum_eligible_cases_per_arm"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError("minimum_eligible_cases_per_arm must be a positive integer")
    floor = value["minimum_acceptance_rate"]
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not math.isfinite(floor) or not 0 <= floor <= 1:
        raise ValueError("minimum_acceptance_rate must be between zero and one")
    passport_protocol = value["passport_protocol"]
    required_passport = {"id", "version", "acceptance_rule", "measurement_window", "currency"}
    if not isinstance(passport_protocol, dict) or set(passport_protocol) != required_passport:
        raise ValueError("passport_protocol must match the complete Passport protocol contract")
    if any(not isinstance(item, str) or not item.strip() for item in passport_protocol.values()):
        raise ValueError("passport_protocol fields must be nonempty text")
    return value, _digest(raw)


def _wilson(accepted: int, eligible: int) -> list[float]:
    """Approximate 95% Wilson interval for an acceptance proportion."""
    z = 1.96
    p = accepted / eligible
    denominator = 1 + z * z / eligible
    center = (p + z * z / (2 * eligible)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * eligible)) / eligible) / denominator
    return [round(max(0.0, center - half), 6), round(min(1.0, center + half), 6)]


def run(manifest_path: Path, protocol_path: Path) -> dict[str, Any]:
    """Create a scope-limited scorecard from a local Bridge export."""
    protocol, protocol_digest = _protocol(protocol_path)
    package = build_bridge(manifest_path)
    passport = package["passport"]
    supplied = passport["input"]
    if supplied["subject"]["workload"] != protocol["workload"]:
        raise ValueError("workload does not match benchmark protocol")
    if supplied["protocol"] != protocol["passport_protocol"]:
        raise ValueError("Passport protocol differs from locked benchmark protocol")
    metrics = passport["metrics"]
    minimum = protocol["minimum_eligible_cases_per_arm"]
    sample_sufficient = all(arm["eligible_cases"] >= minimum for arm in metrics.values())
    quality_floor_met = metrics["candidate"]["acceptance_rate"] >= protocol["minimum_acceptance_rate"]
    case_mix_identical = passport["comparison"]["case_mix_identical"]
    if not case_mix_identical:
        comparison_status = "NOT_COMPARABLE_CASE_MIX"
    elif not sample_sufficient:
        comparison_status = "DEMO_ONLY_INSUFFICIENT_SAMPLE"
    else:
        comparison_status = "DESCRIPTIVE_COMPARISON_ONLY"
    intervals = {
        name: _wilson(arm["accepted_cases"], arm["eligible_cases"])
        for name, arm in metrics.items()
    }
    body = {
        "benchmark_schema_version": BENCH_VERSION,
        "protocol_id": protocol["id"],
        "protocol_version": protocol["version"],
        "protocol_file_sha256": protocol_digest,
        "bridge_package_sha256": package["package_sha256"],
        "passport_id": passport["passport_id"],
        "evidence_class": passport["evidence_class"],
        "track": "SYNTHETIC" if passport["evidence_class"] == "SYNTHETIC" else "CUSTOMER_SUPPLIED_UNVERIFIED",
        "publication_status": "LOCAL_NOT_SUBMITTED",
        "comparison_status": comparison_status,
        "gates": {
            "minimum_sample_met": sample_sufficient,
            "candidate_quality_floor_met": quality_floor_met,
            "case_mix_identical": case_mix_identical,
        },
        "metrics": metrics,
        "acceptance_rate_wilson_95": intervals,
        "descriptive_cost_per_accepted_resolution_delta": (
            passport["comparison"]["cost_per_accepted_resolution_delta"] if sample_sufficient and case_mix_identical else None
        ),
        "claim_scope": "RECORDED_EXPORT_ARITHMETIC_ONLY_NOT_CAUSAL_OR_SOURCE_AUTHENTICATED",
        "production_recommendation": "NONE",
        "limitations": [
            "The runner reads recorded exports; it does not execute an agent or authenticate a source.",
            "Acceptance intervals describe sample uncertainty only; costs and causal effects have no interval here.",
            "A passing quality or sample gate is not evidence of safety, customer approval, or production readiness.",
        ],
    }
    return {**body, "scorecard_sha256": _digest(_canonical(body))}


def verify(manifest_path: Path, protocol_path: Path, scorecard: dict[str, Any]) -> dict[str, Any]:
    """Recompute scorecard and Bridge package from original local inputs."""
    if not isinstance(scorecard, dict):
        raise ValueError("scorecard must be an object")
    package = build_bridge(manifest_path)
    verify_bridge(manifest_path, package)
    expected = run(manifest_path, protocol_path)
    if _canonical(scorecard) != _canonical(expected):
        raise ValueError("scorecard differs from recomputed protocol and source data")
    return {"valid": True, "scope": expected["claim_scope"], "passport_id": expected["passport_id"]}
