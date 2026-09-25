"""Deterministic synthetic clinic for stale signed agent handoffs.

The case separates proof of origin from current authorization and target-owned
outcome evidence.  It models a valid signature and HTTP 200 transport receipt
whose sender state is stale when the receiver evaluates the effect.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "0.1.0"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _load(case_path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(case_path).read_bytes()
    case = json.loads(raw)
    required = {
        "schema_version",
        "clinic_id",
        "title",
        "evidence_class",
        "claim",
        "scenario",
        "verifier",
        "expected_result",
        "limitations",
    }
    if not isinstance(case, dict) or set(case) != required or case["schema_version"] != VERSION:
        raise ValueError("signed handoff clinic case contract is invalid")
    if case["evidence_class"] != "SYNTHETIC":
        raise ValueError("signed handoff clinic cases must be synthetic")
    if not isinstance(case["clinic_id"], str) or not case["clinic_id"].strip():
        raise ValueError("clinic_id must be nonempty text")
    if not isinstance(case["title"], str) or not case["title"].strip():
        raise ValueError("title must be nonempty text")

    claim = case["claim"]
    if not isinstance(claim, dict) or set(claim) != {"claim_id", "text"} or not all(
        isinstance(claim[key], str) and claim[key].strip() for key in claim
    ):
        raise ValueError("claim contract is invalid")

    scenario = case["scenario"]
    scenario_keys = {
        "task_id",
        "signed_handoff",
        "transport",
        "sender_state",
        "receiver_state",
        "target_observation",
    }
    if not isinstance(scenario, dict) or set(scenario) != scenario_keys:
        raise ValueError("signed handoff scenario contract is invalid")
    if not isinstance(scenario["task_id"], str) or not scenario["task_id"].strip():
        raise ValueError("task_id must be nonempty text")

    handoff = scenario["signed_handoff"]
    if not isinstance(handoff, dict) or set(handoff) != {
        "signature_valid",
        "nonce",
        "sender_policy_epoch",
        "sender_resource_version",
        "expires_at",
    }:
        raise ValueError("signed handoff contract is invalid")
    if handoff["signature_valid"] is not True or not isinstance(handoff["nonce"], str) or not handoff["nonce"].strip():
        raise ValueError("fixture must contain a valid synthetic signature and nonce")
    for key in ("sender_policy_epoch", "sender_resource_version"):
        if isinstance(handoff[key], bool) or not isinstance(handoff[key], int) or handoff[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if not isinstance(handoff["expires_at"], str) or not handoff["expires_at"].strip():
        raise ValueError("expires_at must be nonempty text")

    transport = scenario["transport"]
    if not isinstance(transport, dict) or set(transport) != {"status_code", "response_body"}:
        raise ValueError("transport contract is invalid")
    if transport["status_code"] != 200 or not isinstance(transport["response_body"], str):
        raise ValueError("transport fixture must contain an HTTP 200 and response body")

    for state_key in ("sender_state", "receiver_state"):
        state = scenario[state_key]
        if not isinstance(state, dict) or set(state) != {"policy_epoch", "resource_version", "authorization"}:
            raise ValueError(f"{state_key} contract is invalid")
        for key in ("policy_epoch", "resource_version"):
            if isinstance(state[key], bool) or not isinstance(state[key], int) or state[key] < 0:
                raise ValueError(f"{state_key}.{key} must be a nonnegative integer")
        if state["authorization"] not in {"AUTHORIZED", "REVOKED"}:
            raise ValueError(f"{state_key}.authorization is invalid")

    observation = scenario["target_observation"]
    if not isinstance(observation, dict) or set(observation) != {"revalidated", "event_id", "effect_applied"}:
        raise ValueError("target observation contract is invalid")
    if observation["revalidated"] is not False or observation["event_id"] is not None or observation["effect_applied"] is not False:
        raise ValueError("fixture must model missing independent target outcome evidence")

    verifier = case["verifier"]
    if not isinstance(verifier, dict) or set(verifier) != {
        "origin_checks",
        "legitimacy_checks",
        "outcome_checks",
    }:
        raise ValueError("verifier contract is invalid")
    if verifier["origin_checks"] != ["signature_valid=true"]:
        raise ValueError("origin verifier contract does not match the scenario")
    if verifier["legitimacy_checks"] != [
        "receiver_requeries_policy_epoch",
        "receiver_requeries_resource_version",
        "receiver_checks_authorization",
        "receiver_checks_nonce_and_expiry",
    ]:
        raise ValueError("legitimacy verifier contract does not match the scenario")
    if verifier["outcome_checks"] != ["target_owned_event_id", "effect_applied"]:
        raise ValueError("outcome verifier contract does not match the scenario")
    if not isinstance(case["expected_result"], dict) or not isinstance(case["limitations"], list) or not case["limitations"]:
        raise ValueError("expected result and limitations are required")
    if any(not isinstance(item, str) or not item.strip() for item in case["limitations"]):
        raise ValueError("limitations must be nonempty text")
    return case, _sha(raw)


def run(case_path: Path) -> dict[str, Any]:
    case, case_sha = _load(case_path)
    scenario = case["scenario"]
    handoff = scenario["signed_handoff"]
    sender = scenario["sender_state"]
    receiver = scenario["receiver_state"]
    observation = scenario["target_observation"]

    state_matches = (
        handoff["sender_policy_epoch"] == receiver["policy_epoch"]
        and handoff["sender_resource_version"] == receiver["resource_version"]
    )
    authorization_current = receiver["authorization"] == "AUTHORIZED"
    origin_pass = handoff["signature_valid"]
    legitimacy_pass = state_matches and authorization_current
    outcome_pass = observation["revalidated"] and observation["event_id"] is not None and observation["effect_applied"]

    failure_codes = []
    if not state_matches:
        failure_codes.append("STALE_AUTHORIZATION_STATE")
    if not authorization_current:
        failure_codes.append("CURRENT_AUTHORIZATION_REVOKED")
    if not outcome_pass:
        failure_codes.append("TARGET_OUTCOME_NOT_OBSERVED")

    body = {
        "signed_handoff_clinic_version": VERSION,
        "clinic_id": case["clinic_id"],
        "case_sha256": case_sha,
        "evidence_class": case["evidence_class"],
        "claim": case["claim"],
        "observed": {
            "signature_valid": handoff["signature_valid"],
            "transport_status_code": scenario["transport"]["status_code"],
            "transport_response_body": scenario["transport"]["response_body"],
            "sender_state": sender,
            "receiver_state": receiver,
            "state_matches": state_matches,
            "authorization_current": authorization_current,
            "target_revalidated": observation["revalidated"],
            "target_event_id": observation["event_id"],
            "effect_applied": observation["effect_applied"],
        },
        "verifier_results": {
            "origin_verifier": "PASS" if origin_pass else "FAIL",
            "receiver_legitimacy_verifier": "PASS" if legitimacy_pass else "FAIL",
            "target_outcome_verifier": "PASS" if outcome_pass else "FAIL",
            "failure_codes": failure_codes,
            "final_status": "COMMITTED" if legitimacy_pass and outcome_pass else "UNRESOLVED",
            "effect_allowed": legitimacy_pass and outcome_pass,
        },
        "claim_scope": "LOCAL_SYNTHETIC_VERIFICATION_ONLY_NOT_CRYPTOGRAPHIC_ASSURANCE_OR_PRODUCTION_RESULT",
        "limitations": case["limitations"],
    }
    report = {**body, "report_sha256": _sha(_canonical(body))}
    expected = case["expected_result"]
    checks = {
        "origin_verifier": body["verifier_results"]["origin_verifier"] == expected["origin_verifier"],
        "receiver_legitimacy_verifier": body["verifier_results"]["receiver_legitimacy_verifier"] == expected["receiver_legitimacy_verifier"],
        "target_outcome_verifier": body["verifier_results"]["target_outcome_verifier"] == expected["target_outcome_verifier"],
        "final_status": body["verifier_results"]["final_status"] == expected["final_status"],
        "effect_allowed": body["verifier_results"]["effect_allowed"] == expected["effect_allowed"],
        "failure_codes": body["verifier_results"]["failure_codes"] == expected["failure_codes"],
    }
    if not all(checks.values()):
        raise ValueError(f"case expected-result checks failed: {checks}")
    return report


def verify(case_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    expected = run(case_path)
    if not isinstance(report, dict) or _canonical(report) != _canonical(expected):
        raise ValueError("signed handoff clinic report differs from locked case inputs")
    return {"valid": True, "scope": expected["claim_scope"]}
