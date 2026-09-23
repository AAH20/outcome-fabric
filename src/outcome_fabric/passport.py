"""Offline, deterministic Outcome Passport generation and verification.

A valid digest proves internal consistency, not the truth of supplied evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


VERSION = "0.1.0"
EVIDENCE_CLASSES = {"SYNTHETIC", "CUSTOMER_SUPPLIED_UNVERIFIED"}
COST_KEYS = {"inference", "retrieval", "infrastructure", "human_qa", "rework", "operations", "allocated_setup"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _money(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return float(value)


def _arm(value: Any, label: str) -> dict[str, Any]:
    arm = _object(value, label)
    if set(arm) != {"eligible_cases", "accepted_cases", "costs", "case_mix"}:
        raise ValueError(f"{label} must contain eligible_cases, accepted_cases, costs, and case_mix only")
    eligible = _count(arm["eligible_cases"], f"{label}.eligible_cases")
    accepted = _count(arm["accepted_cases"], f"{label}.accepted_cases")
    if not eligible or not accepted or accepted > eligible:
        raise ValueError(f"{label} needs positive eligible and accepted counts with accepted <= eligible")
    costs = _object(arm["costs"], f"{label}.costs")
    if set(costs) != COST_KEYS:
        raise ValueError(f"{label}.costs must contain the seven defined cost categories")
    normalized_costs = {key: _money(costs[key], f"{label}.costs.{key}") for key in sorted(COST_KEYS)}
    case_mix = _object(arm["case_mix"], f"{label}.case_mix")
    if not case_mix or any(not isinstance(key, str) or not key.strip() for key in case_mix):
        raise ValueError(f"{label}.case_mix needs nonempty category names")
    normalized_mix = {key: _count(value, f"{label}.case_mix.{key}") for key, value in case_mix.items()}
    if sum(normalized_mix.values()) != eligible:
        raise ValueError(f"{label}.case_mix must sum to eligible_cases")
    return {"eligible_cases": eligible, "accepted_cases": accepted, "costs": normalized_costs, "case_mix": normalized_mix}


def generate(case: dict[str, Any]) -> dict[str, Any]:
    """Calculate a portable passport from supplied counts, cost, and protocol."""
    case = _object(case, "case")
    if set(case) != {"passport_id", "evidence_class", "subject", "protocol", "baseline", "candidate"}:
        raise ValueError("case has missing or unexpected top-level fields")
    passport_id = _text(case["passport_id"], "passport_id")
    evidence_class = case["evidence_class"]
    if not isinstance(evidence_class, str) or evidence_class not in EVIDENCE_CLASSES:
        raise ValueError("unsupported evidence_class")
    subject = _object(case["subject"], "subject")
    if set(subject) != {"workload", "deployment"}:
        raise ValueError("subject needs workload and deployment only")
    normalized_subject = {key: _text(subject[key], f"subject.{key}") for key in sorted(subject)}
    protocol = _object(case["protocol"], "protocol")
    if set(protocol) != {"id", "version", "acceptance_rule", "measurement_window", "currency"}:
        raise ValueError("protocol needs id, version, acceptance_rule, measurement_window, currency")
    normalized_protocol = {key: _text(protocol[key], f"protocol.{key}") for key in sorted(protocol)}
    if len(normalized_protocol["currency"]) != 3 or not normalized_protocol["currency"].isalpha():
        raise ValueError("protocol.currency must be a three-letter code")
    normalized_protocol["currency"] = normalized_protocol["currency"].upper()
    baseline = _arm(case["baseline"], "baseline")
    candidate = _arm(case["candidate"], "candidate")
    if set(baseline["case_mix"]) != set(candidate["case_mix"]):
        raise ValueError("baseline and candidate case_mix categories must match")

    normalized_case = {
        "passport_id": passport_id,
        "evidence_class": evidence_class,
        "subject": normalized_subject,
        "protocol": normalized_protocol,
        "baseline": baseline,
        "candidate": candidate,
    }

    def metrics(arm: dict[str, Any]) -> dict[str, Any]:
        total = sum(arm["costs"].values())
        return {
            "eligible_cases": arm["eligible_cases"],
            "accepted_cases": arm["accepted_cases"],
            "acceptance_rate": round(arm["accepted_cases"] / arm["eligible_cases"], 6),
            "total_attributable_cost": round(total, 2),
            "cost_per_accepted_resolution": round(total / arm["accepted_cases"], 4),
        }

    base_metrics = metrics(baseline)
    candidate_metrics = metrics(candidate)
    comparable_mix = baseline["case_mix"] == candidate["case_mix"]
    delta = round(base_metrics["cost_per_accepted_resolution"] - candidate_metrics["cost_per_accepted_resolution"], 4)
    body = {
        "schema_version": VERSION,
        "passport_id": passport_id,
        "evidence_class": evidence_class,
        "verification_scope": "ARITHMETIC_AND_INTEGRITY_ONLY_NOT_SOURCE_AUTHENTICATED",
        "publication_status": "LOCAL_UNAPPROVED",
        "input": normalized_case,
        "input_sha256": _digest(normalized_case),
        "metrics": {"baseline": base_metrics, "candidate": candidate_metrics},
        "comparison": {
            "case_mix_identical": comparable_mix,
            "cost_per_accepted_resolution_delta": delta if comparable_mix else None,
            "causal_lift_claimed": False,
        },
        "limitations": [
            "Source identity, consent, and customer acceptance are not authenticated.",
            "Matching case-mix totals do not prove cases have equal difficulty.",
            "Cost difference is descriptive, not an independently verified causal effect.",
        ],
    }
    return {**body, "passport_sha256": _digest(body)}


def verify(passport: dict[str, Any]) -> dict[str, Any]:
    """Recalculate every field; never interpret validity as real-world verification."""
    passport = _object(passport, "passport")
    required = {"schema_version", "passport_id", "evidence_class", "verification_scope", "publication_status", "input", "input_sha256", "metrics", "comparison", "limitations", "passport_sha256"}
    if set(passport) != required:
        raise ValueError("passport has missing or unexpected fields")
    if passport["schema_version"] != VERSION:
        raise ValueError("unsupported passport schema version")
    expected = generate(passport["input"])
    if _canonical(passport) != _canonical(expected):
        raise ValueError("passport differs from recomputed output")
    return {"valid": True, "scope": expected["verification_scope"], "passport_id": expected["passport_id"]}
