"""Private, read-only pilot orchestration over Evidence Bridge and OutcomeBench.

Local digests and declarations establish reproducibility, not consent, source
authenticity, independent review, or permission to publish.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .bridge import build as build_bridge
from .outcomebench import run as run_benchmark


VERSION = "0.1.0"
PERMISSION_CLASSES = {
    "SYNTHETIC_NO_CUSTOMER_DATA": "SYNTHETIC",
    "OPERATOR_ASSERTED_PERMISSION_NOT_AUTHENTICATED": "CUSTOMER_SUPPLIED_UNVERIFIED",
}


class PilotIssue(ValueError):
    """A safe, machine-readable pilot hold reason."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _locked_file(root: Path, entry: Any, label: str) -> tuple[Path, str]:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise PilotIssue(f"{label}_LOCK_INVALID")
    relative, expected = entry["path"], entry["sha256"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or Path(relative).suffix != ".json":
        raise PilotIssue(f"{label}_PATH_INVALID")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PilotIssue(f"{label}_PATH_INVALID")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PilotIssue(f"{label}_LOCK_INVALID")
    try:
        actual = _digest(path.read_bytes())
    except OSError as exc:
        raise PilotIssue(f"{label}_FILE_UNAVAILABLE") from exc
    if actual != expected:
        raise PilotIssue(f"{label}_LOCK_MISMATCH")
    return path, actual


def _expected_counts(value: Any, keys: set[str], label: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PilotIssue(f"{label}_INVALID")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value.values()):
        raise PilotIssue(f"{label}_INVALID")
    return value


def _evaluate(pilot_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    pilot_path = Path(pilot_path)
    try:
        raw = pilot_path.read_bytes()
        pilot = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotIssue("PILOT_FILE_INVALID") from exc
    required = {
        "schema_version", "pilot_id", "purpose", "permission_declaration", "publication_policy",
        "manifest", "protocol", "expected_case_counts", "expected_source_rows",
    }
    if not isinstance(pilot, dict) or set(pilot) != required or pilot.get("schema_version") != VERSION:
        raise PilotIssue("PILOT_CONTRACT_INVALID")
    if not isinstance(pilot["pilot_id"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", pilot["pilot_id"]):
        raise PilotIssue("PILOT_ID_INVALID")
    if not isinstance(pilot["purpose"], str) or not pilot["purpose"].strip() or len(pilot["purpose"]) > 500:
        raise PilotIssue("PURPOSE_INVALID")
    permission = pilot["permission_declaration"]
    if not isinstance(permission, str) or permission not in PERMISSION_CLASSES:
        raise PilotIssue("PERMISSION_DECLARATION_REQUIRED")
    if pilot["publication_policy"] != "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT":
        raise PilotIssue("PUBLICATION_POLICY_INVALID")
    expected_cases = _expected_counts(pilot["expected_case_counts"], {"baseline", "candidate"}, "CASE_COUNTS")
    expected_rows = _expected_counts(pilot["expected_source_rows"], {"cases", "decisions", "costs"}, "SOURCE_ROWS")
    manifest_path, manifest_digest = _locked_file(pilot_path.parent, pilot["manifest"], "MANIFEST")
    protocol_path, protocol_digest = _locked_file(pilot_path.parent, pilot["protocol"], "PROTOCOL")

    try:
        package = build_bridge(manifest_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise PilotIssue("SOURCE_RECONCILIATION_FAILED") from exc
    passport = package["passport"]
    if passport["evidence_class"] != PERMISSION_CLASSES[permission]:
        raise PilotIssue("EVIDENCE_CLASS_MISMATCH")
    for name, count in expected_rows.items():
        if package["sources"][name]["row_count"] != count:
            raise PilotIssue("SOURCE_ROW_COUNT_MISMATCH")
    for arm, count in expected_cases.items():
        if passport["metrics"][arm]["eligible_cases"] != count:
            raise PilotIssue("ELIGIBLE_CASE_COUNT_MISMATCH")
    try:
        scorecard = run_benchmark(manifest_path, protocol_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise PilotIssue("PROTOCOL_OR_SCORECARD_FAILED") from exc
    return pilot, package, scorecard, manifest_digest, protocol_digest


def preflight(pilot_path: Path) -> dict[str, Any]:
    """Return a private, identifier-free readiness or hold report."""
    try:
        pilot, package, scorecard, _, _ = _evaluate(pilot_path)
    except PilotIssue as exc:
        return {"status": "HOLD", "issue_codes": [exc.code], "publication_status": "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT"}
    return {
        "status": "READY_FOR_PRIVATE_REVIEW",
        "issue_codes": [],
        "pilot_id": pilot["pilot_id"],
        "evidence_class": package["passport"]["evidence_class"],
        "comparison_status": scorecard["comparison_status"],
        "publication_status": "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT",
    }


def run(pilot_path: Path) -> dict[str, Any]:
    """Build a private aggregate package; no source rows or case IDs are copied."""
    pilot, package, scorecard, manifest_digest, protocol_digest = _evaluate(pilot_path)
    body = {
        "fieldlab_schema_version": VERSION,
        "pilot_id": pilot["pilot_id"],
        "purpose": pilot["purpose"].strip(),
        "permission_declaration": pilot["permission_declaration"],
        "permission_scope": "OPERATOR_DECLARATION_ONLY_NOT_AUTHENTICATED",
        "review_status": "NOT_INDEPENDENTLY_REVIEWED",
        "publication_status": "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT",
        "manifest_sha256": manifest_digest,
        "protocol_sha256": protocol_digest,
        "bridge_package": package,
        "scorecard": scorecard,
        "limitations": [
            "Pilot configuration, consent, baseline lock, and source origin are operator declarations, not authenticated facts.",
            "This package contains aggregate business data and must remain private unless the owner separately authorizes release.",
            "No causal effect, independent review, or production recommendation is established.",
        ],
    }
    return {**body, "fieldlab_sha256": _digest(_canonical(body))}


def verify(pilot_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Recompute every field against the locally locked sources and protocol."""
    if not isinstance(result, dict):
        raise PilotIssue("RESULT_INVALID")
    expected = run(pilot_path)
    if _canonical(result) != _canonical(expected):
        raise PilotIssue("RESULT_DIFFERS_FROM_SOURCES")
    return {
        "valid": True,
        "pilot_id": expected["pilot_id"],
        "scope": "LOCAL_RECOMPUTATION_ONLY_NOT_SOURCE_OR_PERMISSION_AUTHENTICATION",
    }
