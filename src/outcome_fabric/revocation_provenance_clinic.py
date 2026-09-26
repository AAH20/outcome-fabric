"""Synthetic clinic for untrusted authorization-state deltas.

The fixture shows why a receiver must not turn an unauthenticated revocation
signal into a confident authorization decision.  The state delta is visible,
but its provenance is not independently established, so the verifier fails
closed to UNRESOLVED.
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
    required = {"schema_version", "clinic_id", "title", "evidence_class", "claim", "scenario", "verifier", "expected_result", "limitations"}
    if not isinstance(case, dict) or set(case) != required or case["schema_version"] != VERSION:
        raise ValueError("revocation provenance clinic case contract is invalid")
    if case["evidence_class"] != "SYNTHETIC":
        raise ValueError("revocation provenance clinic cases must be synthetic")
    if not isinstance(case["clinic_id"], str) or not case["clinic_id"].strip():
        raise ValueError("clinic_id must be nonempty text")
    if not isinstance(case["title"], str) or not case["title"].strip():
        raise ValueError("title must be nonempty text")

    claim = case["claim"]
    if not isinstance(claim, dict) or set(claim) != {"claim_id", "text"} or not all(isinstance(value, str) and value.strip() for value in claim.values()):
        raise ValueError("claim contract is invalid")

    scenario = case["scenario"]
    if not isinstance(scenario, dict) or set(scenario) != {"task_id", "signed_handoff", "receiver_observation", "revocation_event", "target_outcome"}:
        raise ValueError("scenario contract is invalid")
    if not isinstance(scenario["task_id"], str) or not scenario["task_id"].strip():
        raise ValueError("task_id must be nonempty text")

    handoff = scenario["signed_handoff"]
    if not isinstance(handoff, dict) or set(handoff) != {"signature_valid", "sender_policy_epoch", "sender_resource_version"}:
        raise ValueError("signed handoff contract is invalid")
    if handoff["signature_valid"] is not True:
        raise ValueError("fixture must contain a valid synthetic signature")
    for key in ("sender_policy_epoch", "sender_resource_version"):
        if isinstance(handoff[key], bool) or not isinstance(handoff[key], int) or handoff[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")

    receiver = scenario["receiver_observation"]
    if not isinstance(receiver, dict) or set(receiver) != {"policy_epoch", "resource_version", "authorization"}:
        raise ValueError("receiver observation contract is invalid")
    for key in ("policy_epoch", "resource_version"):
        if isinstance(receiver[key], bool) or not isinstance(receiver[key], int) or receiver[key] < 0:
            raise ValueError(f"receiver_observation.{key} must be a nonnegative integer")
    if receiver["authorization"] not in {"AUTHORIZED", "REVOKED"}:
        raise ValueError("receiver authorization is invalid")

    revocation = scenario["revocation_event"]
    revocation_keys = {"event_id", "source", "source_attested", "independently_retrieved", "source_revision", "payload_hash"}
    if not isinstance(revocation, dict) or set(revocation) != revocation_keys:
        raise ValueError("revocation event contract is invalid")
    if any(not isinstance(revocation[key], str) or not revocation[key].strip() for key in ("event_id", "source", "source_revision", "payload_hash")):
        raise ValueError("revocation event text fields are required")
    if revocation["source_attested"] is not False or revocation["independently_retrieved"] is not False:
        raise ValueError("fixture must model an unattested, non-independent revocation event")

    outcome = scenario["target_outcome"]
    if not isinstance(outcome, dict) or set(outcome) != {"event_id", "effect_applied"} or outcome["event_id"] is not None or outcome["effect_applied"] is not False:
        raise ValueError("target outcome must be unobserved in this fixture")

    verifier = case["verifier"]
    if not isinstance(verifier, dict) or set(verifier) != {"origin_checks", "delta_checks", "outcome_checks"}:
        raise ValueError("verifier contract is invalid")
    if verifier["origin_checks"] != ["signature_valid=true"]:
        raise ValueError("origin verifier contract does not match the scenario")
    if verifier["delta_checks"] != ["source_attested=true", "independently_retrieved=true", "source_revision_present"]:
        raise ValueError("delta verifier contract does not match the scenario")
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
    receiver = scenario["receiver_observation"]
    revocation = scenario["revocation_event"]
    outcome = scenario["target_outcome"]

    state_delta_visible = (
        handoff["sender_policy_epoch"] != receiver["policy_epoch"]
        or handoff["sender_resource_version"] != receiver["resource_version"]
    )
    delta_provenance_pass = revocation["source_attested"] and revocation["independently_retrieved"] and bool(revocation["source_revision"])
    target_outcome_pass = outcome["event_id"] is not None and outcome["effect_applied"]
    failure_codes = []
    if state_delta_visible and not delta_provenance_pass:
        failure_codes.append("STATE_DELTA_NOT_INDEPENDENTLY_ATTESTED")
    if not target_outcome_pass:
        failure_codes.append("TARGET_OUTCOME_NOT_OBSERVED")

    body = {
        "revocation_provenance_clinic_version": VERSION,
        "clinic_id": case["clinic_id"],
        "case_sha256": case_sha,
        "evidence_class": case["evidence_class"],
        "claim": case["claim"],
        "observed": {
            "signature_valid": handoff["signature_valid"],
            "sender_policy_epoch": handoff["sender_policy_epoch"],
            "receiver_policy_epoch": receiver["policy_epoch"],
            "sender_resource_version": handoff["sender_resource_version"],
            "receiver_resource_version": receiver["resource_version"],
            "state_delta_visible": state_delta_visible,
            "receiver_authorization": receiver["authorization"],
            "revocation_event": revocation,
            "target_event_id": outcome["event_id"],
            "effect_applied": outcome["effect_applied"],
        },
        "verifier_results": {
            "origin_verifier": "PASS" if handoff["signature_valid"] else "FAIL",
            "state_delta_provenance_verifier": "PASS" if delta_provenance_pass else "FAIL",
            "target_outcome_verifier": "PASS" if target_outcome_pass else "FAIL",
            "failure_codes": failure_codes,
            "authorization_conclusion": "REVOKED" if delta_provenance_pass and receiver["authorization"] == "REVOKED" else "UNRESOLVED",
            "final_status": "COMMITTED" if delta_provenance_pass and target_outcome_pass else "UNRESOLVED",
            "effect_allowed": delta_provenance_pass and target_outcome_pass,
        },
        "claim_scope": "LOCAL_SYNTHETIC_VERIFICATION_ONLY_NOT_PROVENANCE_ASSURANCE_OR_PRODUCTION_RESULT",
        "limitations": case["limitations"],
    }
    report = {**body, "report_sha256": _sha(_canonical(body))}
    expected = case["expected_result"]
    checks = {
        key: body["verifier_results"][key] == expected[key]
        for key in ("origin_verifier", "state_delta_provenance_verifier", "target_outcome_verifier", "authorization_conclusion", "final_status", "effect_allowed", "failure_codes")
    }
    if not all(checks.values()):
        raise ValueError(f"case expected-result checks failed: {checks}")
    return report


def verify(case_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    expected = run(case_path)
    if not isinstance(report, dict) or _canonical(report) != _canonical(expected):
        raise ValueError("revocation provenance clinic report differs from locked case inputs")
    return {"valid": True, "scope": expected["claim_scope"]}
