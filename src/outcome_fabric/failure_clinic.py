"""Small, deterministic failure clinics for agent outcome claims.

The first clinic separates an agent's apparent completion signal from human
acceptance and the evidence required by the acceptance rubric.  It is a local
synthetic scenario: the verifier checks the fixture's internal consistency,
not a real agent, customer system, reviewer identity, or production outcome.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


VERSION = "0.1.0"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a decimal") from exc
    if not result.is_finite() or result < 0 or result.as_tuple().exponent < -2:
        raise ValueError(f"{name} must be finite, nonnegative, and use at most two decimal places")
    return result


def _load(case_path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(case_path).read_bytes()
    case = json.loads(raw)
    required = {"schema_version", "clinic_id", "title", "evidence_class", "claim", "scenario", "verifier", "expected_result", "limitations"}
    if not isinstance(case, dict) or set(case) != required or case["schema_version"] != VERSION:
        raise ValueError("failure clinic case contract is invalid")
    if case["evidence_class"] != "SYNTHETIC":
        raise ValueError("failure clinic cases must be synthetic")
    if not isinstance(case["clinic_id"], str) or not case["clinic_id"].strip():
        raise ValueError("clinic_id must be nonempty text")
    if not isinstance(case["title"], str) or not case["title"].strip():
        raise ValueError("title must be nonempty text")
    claim = case["claim"]
    if not isinstance(claim, dict) or set(claim) != {"claim_id", "text"} or not all(isinstance(claim[key], str) and claim[key].strip() for key in claim):
        raise ValueError("claim contract is invalid")
    scenario = case["scenario"]
    if not isinstance(scenario, dict) or set(scenario) != {"task_id", "requested_outcome", "agent_status", "artifact_exists", "evidence", "acceptance", "costs"}:
        raise ValueError("scenario contract is invalid")
    if not isinstance(scenario["task_id"], str) or not scenario["task_id"].strip() or not isinstance(scenario["requested_outcome"], str) or not scenario["requested_outcome"].strip():
        raise ValueError("scenario task and requested outcome are required")
    if scenario["agent_status"] not in {"COMPLETED", "FAILED"} or not isinstance(scenario["artifact_exists"], bool):
        raise ValueError("scenario completion signals are invalid")

    evidence = scenario["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"required", "observed"} or not all(isinstance(evidence[key], list) for key in evidence):
        raise ValueError("evidence contract is invalid")
    if not evidence["required"] or len(set(evidence["required"])) != len(evidence["required"]):
        raise ValueError("required evidence must be unique and nonempty")
    if any(not isinstance(item, str) or not item.strip() for item in evidence["required"] + evidence["observed"]):
        raise ValueError("evidence fields must be nonempty text")

    acceptance = scenario["acceptance"]
    acceptance_keys = {"initial_decision", "initial_reason", "initial_review_minutes", "followup_decision", "followup_review_minutes", "reviewer_hourly_rate_usd", "rework_cost_usd"}
    if not isinstance(acceptance, dict) or set(acceptance) != acceptance_keys:
        raise ValueError("acceptance contract is invalid")
    if acceptance["initial_decision"] not in {"ACCEPT", "CORRECTION_REQUIRED", "REJECT"} or acceptance["followup_decision"] not in {"ACCEPT", "CORRECTION_REQUIRED", "REJECT"}:
        raise ValueError("acceptance decisions are invalid")
    if not isinstance(acceptance["initial_reason"], str) or not acceptance["initial_reason"].strip():
        raise ValueError("initial acceptance reason is required")
    for key in ("initial_review_minutes", "followup_review_minutes"):
        if isinstance(acceptance[key], bool) or not isinstance(acceptance[key], int) or acceptance[key] < 0 or acceptance[key] > 1440:
            raise ValueError(f"{key} must be an integer from 0 to 1440")
    _decimal(acceptance["reviewer_hourly_rate_usd"], "reviewer_hourly_rate_usd")
    _decimal(acceptance["rework_cost_usd"], "rework_cost_usd")

    costs = scenario["costs"]
    cost_keys = {"inference", "retrieval", "compute", "allocated_setup"}
    if not isinstance(costs, dict) or set(costs) != cost_keys:
        raise ValueError("scenario costs must contain the four execution categories")
    for key, value in costs.items():
        _decimal(value, f"costs.{key}")

    verifier = case["verifier"]
    verifier_keys = {"completion_signals", "required_acceptance", "required_evidence"}
    if not isinstance(verifier, dict) or set(verifier) != verifier_keys:
        raise ValueError("verifier contract is invalid")
    if verifier["completion_signals"] != ["agent_status=COMPLETED", "artifact_exists=true"] or verifier["required_acceptance"] != "ACCEPT" or verifier["required_evidence"] != evidence["required"]:
        raise ValueError("verifier contract does not match the scenario")
    if not isinstance(case["expected_result"], dict) or not isinstance(case["limitations"], list) or not case["limitations"]:
        raise ValueError("expected result and limitations are required")
    if any(not isinstance(item, str) or not item.strip() for item in case["limitations"]):
        raise ValueError("limitations must be nonempty text")
    return case, _sha(raw)


def run(case_path: Path) -> dict[str, Any]:
    case, case_sha = _load(case_path)
    scenario = case["scenario"]
    evidence = scenario["evidence"]
    acceptance = scenario["acceptance"]
    missing_evidence = sorted(set(evidence["required"]) - set(evidence["observed"]))
    apparent_completion = scenario["agent_status"] == "COMPLETED" and scenario["artifact_exists"]
    initial_acceptance = acceptance["initial_decision"] == "ACCEPT"
    evidence_complete = not missing_evidence
    independent_pass = apparent_completion and initial_acceptance and evidence_complete

    execution_cost = sum((_decimal(value, f"costs.{key}") for key, value in scenario["costs"].items()), Decimal(0))
    hourly_rate = _decimal(acceptance["reviewer_hourly_rate_usd"], "reviewer_hourly_rate_usd")
    initial_review_cost = hourly_rate * Decimal(acceptance["initial_review_minutes"]) / Decimal(60)
    followup_review_cost = hourly_rate * Decimal(acceptance["followup_review_minutes"]) / Decimal(60)
    rework_cost = _decimal(acceptance["rework_cost_usd"], "rework_cost_usd")
    total_after_rework = execution_cost + initial_review_cost + rework_cost + followup_review_cost
    failure_codes = []
    if not initial_acceptance:
        failure_codes.append("HUMAN_ACCEPTANCE_NOT_ESTABLISHED")
    if missing_evidence:
        failure_codes.append("REQUIRED_EVIDENCE_GAP")

    body = {
        "failure_clinic_version": VERSION,
        "clinic_id": case["clinic_id"],
        "case_sha256": case_sha,
        "evidence_class": case["evidence_class"],
        "claim": case["claim"],
        "observed": {
            "agent_status": scenario["agent_status"],
            "artifact_exists": scenario["artifact_exists"],
            "apparent_completion": apparent_completion,
            "initial_human_decision": acceptance["initial_decision"],
            "initial_reason": acceptance["initial_reason"],
            "required_evidence": evidence["required"],
            "observed_evidence": evidence["observed"],
            "missing_evidence": missing_evidence,
        },
        "verifier_results": {
            "completion_only_verifier": "PASS" if apparent_completion else "FAIL",
            "independent_acceptance_verifier": "PASS" if independent_pass else "FAIL",
            "failure_codes": failure_codes,
            "rework_required": bool(failure_codes),
            "post_rework_status": "ACCEPTED_AFTER_REWORK" if acceptance["followup_decision"] == "ACCEPT" and failure_codes else "NOT_ACCEPTED",
        },
        "costs": {
            "initial_execution_usd": str(execution_cost.quantize(Decimal("0.01"))),
            "initial_review_usd": str(initial_review_cost.quantize(Decimal("0.01"))),
            "rework_usd": str(rework_cost.quantize(Decimal("0.01"))),
            "followup_review_usd": str(followup_review_cost.quantize(Decimal("0.01"))),
            "total_after_rework_usd": str(total_after_rework.quantize(Decimal("0.01"))),
            "cost_basis": "SYNTHETIC_ESTIMATE_NOT_OBSERVED_UNIT_ECONOMICS",
        },
        "claim_scope": "LOCAL_SYNTHETIC_VERIFICATION_ONLY_NOT_CUSTOMER_EVIDENCE_OR_PRODUCTION_RESULT",
        "limitations": case["limitations"],
    }
    report = {**body, "report_sha256": _sha(_canonical(body))}
    expected = case["expected_result"]
    checks = {
        "naive_verifier": body["verifier_results"]["completion_only_verifier"] == expected["naive_verifier"],
        "independent_verifier": body["verifier_results"]["independent_acceptance_verifier"] == expected["independent_verifier"],
        "failure_code": expected["failure_code"] in failure_codes,
        "rework_required": body["verifier_results"]["rework_required"] == expected["rework_required"],
        "total_cost_after_rework_usd": body["costs"]["total_after_rework_usd"] == expected["total_cost_after_rework_usd"],
    }
    if not all(checks.values()):
        raise ValueError(f"case expected-result checks failed: {checks}")
    return report


def verify(case_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    expected = run(case_path)
    if not isinstance(report, dict) or _canonical(report) != _canonical(expected):
        raise ValueError("failure clinic report differs from locked case inputs")
    return {"valid": True, "scope": expected["claim_scope"]}
