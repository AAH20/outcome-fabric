"""Read-only, local-file bridge from support exports to an Outcome Passport.

The bridge checks file integrity and internal consistency. It does not authenticate
the exporter, permission statement, acceptance reviewer, or business outcome.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .passport import COST_KEYS, generate, verify as verify_passport


SOURCE_NAMES = {"cases", "decisions", "costs"}
HEADERS = {
    "cases": ["case_id", "arm", "category"],
    "decisions": ["case_id", "accepted"],
    "costs": ["arm", "category", "amount", "currency"],
}
ARMS = {"baseline", "candidate"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def _source_path(root: Path, relative: str) -> Path:
    path = Path(_text(relative, "source path"))
    if path.is_absolute() or path.suffix.lower() != ".csv":
        raise ValueError("source path must be a relative CSV path")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("source path escapes the manifest directory")
    return resolved


def _rows(raw: bytes, name: str) -> list[dict[str, str]]:
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
    if reader.fieldnames != HEADERS[name]:
        raise ValueError(f"{name} columns must be exactly {HEADERS[name]}")
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"{name} has malformed CSV") from exc
    if not rows:
        raise ValueError(f"{name} must contain data rows")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{name} has missing or extra columns")
    return rows


def _amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("cost amount must be decimal") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError("cost amount must be finite, nonnegative, and have at most two decimal places")
    return amount


def build(manifest_path: Path) -> dict[str, Any]:
    """Build a redacted aggregate evidence package from local CSV exports."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "passport_id", "evidence_class", "subject", "protocol",
        "permission_status", "baseline_status", "sources",
    }:
        raise ValueError("manifest has missing or unexpected fields")
    if manifest["schema_version"] != "0.1.0":
        raise ValueError("unsupported bridge manifest version")
    if manifest["evidence_class"] not in ("SYNTHETIC", "CUSTOMER_SUPPLIED_UNVERIFIED"):
        raise ValueError("bridge cannot issue authenticated evidence classes")
    if manifest["permission_status"] != "DECLARED_BY_OPERATOR_NOT_VERIFIED":
        raise ValueError("permission status must remain explicitly unverified")
    if manifest["baseline_status"] != "DECLARED_LOCKED_NOT_AUTHENTICATED":
        raise ValueError("baseline lock cannot claim authentication")
    sources = manifest["sources"]
    if not isinstance(sources, dict) or set(sources) != SOURCE_NAMES:
        raise ValueError("sources must contain cases, decisions, and costs")

    parsed: dict[str, list[dict[str, str]]] = {}
    source_summary: dict[str, dict[str, Any]] = {}
    for name in sorted(SOURCE_NAMES):
        entry = sources[name]
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError(f"{name} source needs path and sha256")
        expected_digest = _text(entry["sha256"], f"{name}.sha256")
        if len(expected_digest) != 64 or any(char not in "0123456789abcdef" for char in expected_digest):
            raise ValueError(f"{name}.sha256 must be lowercase hexadecimal SHA-256")
        path = _source_path(manifest_path.parent, entry["path"])
        raw = path.read_bytes()
        digest = _sha256(raw)
        if digest != expected_digest:
            raise ValueError(f"{name} file differs from manifest digest")
        parsed[name] = _rows(raw, name)
        source_summary[name] = {"sha256": digest, "row_count": len(parsed[name])}

    cases: dict[str, tuple[str, str]] = {}
    mixes: dict[str, dict[str, int]] = {arm: {} for arm in ARMS}
    for row in parsed["cases"]:
        case_id = _text(row["case_id"], "case_id")
        arm = row["arm"]
        category = _text(row["category"], "case category")
        if arm not in ARMS or case_id in cases:
            raise ValueError("case arm must be baseline/candidate and case_id must be unique")
        cases[case_id] = (arm, category)
        mixes[arm][category] = mixes[arm].get(category, 0) + 1

    decisions: dict[str, bool] = {}
    for row in parsed["decisions"]:
        case_id = _text(row["case_id"], "decision case_id")
        if case_id not in cases or case_id in decisions or row["accepted"] not in ("true", "false"):
            raise ValueError("decisions must uniquely match a known case and use true/false")
        decisions[case_id] = row["accepted"] == "true"
    if set(decisions) != set(cases):
        raise ValueError("every case must have exactly one acceptance decision")

    protocol = manifest["protocol"]
    if not isinstance(protocol, dict):
        raise ValueError("protocol must be an object")
    currency = _text(protocol.get("currency"), "protocol.currency").upper()
    costs: dict[str, dict[str, Decimal]] = {arm: {key: Decimal("0") for key in COST_KEYS} for arm in ARMS}
    observed: dict[str, set[str]] = {arm: set() for arm in ARMS}
    for row in parsed["costs"]:
        arm, category = row["arm"], row["category"]
        if arm not in ARMS or category not in COST_KEYS or row["currency"].upper() != currency:
            raise ValueError("cost arm, category, or currency is invalid")
        costs[arm][category] += _amount(row["amount"])
        observed[arm].add(category)
    if any(observed[arm] != COST_KEYS for arm in ARMS):
        raise ValueError("each arm must explicitly include all seven cost categories")

    arms = {}
    for arm in sorted(ARMS):
        accepted = sum(1 for case_id, (case_arm, _) in cases.items() if case_arm == arm and decisions[case_id])
        arms[arm] = {
            "eligible_cases": sum(mixes[arm].values()),
            "accepted_cases": accepted,
            "case_mix": mixes[arm],
            "costs": {key: float(costs[arm][key]) for key in sorted(COST_KEYS)},
        }
    passport = generate({
        "passport_id": manifest["passport_id"],
        "evidence_class": manifest["evidence_class"],
        "subject": manifest["subject"],
        "protocol": protocol,
        "baseline": arms["baseline"],
        "candidate": arms["candidate"],
    })
    body = {
        "bridge_schema_version": "0.1.0",
        "verification_scope": "LOCAL_FILE_INTEGRITY_AND_INTERNAL_CONSISTENCY_ONLY",
        "permission_status": manifest["permission_status"],
        "baseline_status": manifest["baseline_status"],
        "manifest_sha256": _sha256(manifest_path.read_bytes()),
        "sources": source_summary,
        "passport": passport,
        "limitations": [
            "Export origin, completeness, operator permission, and baseline lock are not authenticated.",
            "Case IDs and source rows are excluded from this package; keep raw exports private.",
            "A valid package does not establish causality or independent review.",
        ],
    }
    return {**body, "package_sha256": _sha256(_canonical(body))}


def verify(manifest_path: Path, package: dict[str, Any]) -> dict[str, Any]:
    """Re-read the source files and reject altered packages or exports."""
    if not isinstance(package, dict):
        raise ValueError("package must be an object")
    expected = build(manifest_path)
    if _canonical(package) != _canonical(expected):
        raise ValueError("package differs from recomputed source data")
    verify_passport(package["passport"])
    return {"valid": True, "scope": expected["verification_scope"], "passport_id": expected["passport"]["passport_id"]}
