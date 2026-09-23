"""Offline issuer-workpaper reference: source facts, checks, review, and cost.

This verifies the committed excerpt against a locked local snapshot. It does not
authenticate the SEC response, reviewer identity, or any investment conclusion.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


VERSION = "0.1.0"
COST_CATEGORIES = {"model", "data", "compute", "review", "rework", "allocated_setup"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has missing or unexpected fields")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a decimal string") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def _locked(root: Path, entry: Any, label: str) -> tuple[dict[str, Any], str]:
    entry = _object(entry, {"path", "sha256"}, label)
    relative = Path(_text(entry["path"], f"{label}.path"))
    digest = _text(entry["sha256"], f"{label}.sha256")
    if relative.is_absolute() or relative.suffix.lower() != ".json" or not SHA.fullmatch(digest):
        raise ValueError(f"{label} has invalid path or digest")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"{label} path escapes case directory")
    raw = path.read_bytes()
    if _sha(raw) != digest:
        raise ValueError(f"{label} differs from locked digest")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value, digest


def _load(case_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    case_path = Path(case_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    _object(case, {"schema_version", "case_id", "source", "protocol", "workpaper", "review", "cost"}, "case")
    if case["schema_version"] != VERSION:
        raise ValueError("unsupported finance case version")
    _text(case["case_id"], "case_id")
    loaded: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for name in ("source", "protocol", "workpaper", "review", "cost"):
        loaded[name], digests[name] = _locked(case_path.parent, case[name], name)
    return case, loaded, digests


def _validate(data: dict[str, dict[str, Any]], digests: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source, protocol, workpaper, review, cost = (data[name] for name in ("source", "protocol", "workpaper", "review", "cost"))
    _object(source, {"schema_version", "source_class", "source_url", "entity_name", "cik", "accession", "fiscal_year", "facts"}, "source")
    _object(protocol, {"schema_version", "protocol_id", "required_fact_ids", "derived_claims", "period_end", "source_class", "publication_policy"}, "protocol")
    _object(workpaper, {"schema_version", "workpaper_id", "entity_cik", "accession", "claims"}, "workpaper")
    _object(review, {"schema_version", "review_kind", "decision", "workpaper_sha256", "reviewer_role", "correction_minutes"}, "review")
    _object(cost, {"schema_version", "currency", "categories"}, "cost")
    if any(item["schema_version"] != VERSION for item in data.values()):
        raise ValueError("unsupported finance component version")
    if source["source_class"] != "PUBLIC_SEC_XBRL_EXCERPT_NOT_ATTESTED" or protocol["source_class"] != source["source_class"]:
        raise ValueError("unsupported or mismatched source class")
    if protocol["publication_policy"] != "SYNTHETIC_REVIEW_DEMO_ONLY":
        raise ValueError("unsupported publication policy")
    if not isinstance(source["source_url"], str) or not source["source_url"].startswith("https://data.sec.gov/api/xbrl/companyfacts/"):
        raise ValueError("source URL must identify the SEC XBRL API")
    if not isinstance(protocol["period_end"], str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", protocol["period_end"]):
        raise ValueError("protocol period_end must be an ISO date")
    if not isinstance(source["facts"], list) or not source["facts"]:
        raise ValueError("source facts must be a nonempty list")
    if not isinstance(protocol["required_fact_ids"], list) or not protocol["required_fact_ids"] or not all(isinstance(x, str) and x for x in protocol["required_fact_ids"]):
        raise ValueError("required_fact_ids must be nonempty strings")
    if len(set(protocol["required_fact_ids"])) != len(protocol["required_fact_ids"]):
        raise ValueError("required_fact_ids must be unique")
    derived = _object(protocol["derived_claims"], {"operating_margin_pct"}, "derived_claims")
    margin_rule = _object(derived["operating_margin_pct"], {"formula", "unit", "decimal_places"}, "margin rule")
    if margin_rule != {"formula": "100 * operating_income / revenue", "unit": "percent", "decimal_places": 2}:
        raise ValueError("unsupported derived-claim rule")
    if not isinstance(workpaper["claims"], list):
        raise ValueError("claims must be a list")
    if workpaper["entity_cik"] != source["cik"] or workpaper["accession"] != source["accession"]:
        raise ValueError("workpaper entity or accession differs from source")
    if review["review_kind"] != "SIMULATED_FIXTURE_REVIEW_NOT_AUTHENTICATED":
        raise ValueError("reference review must remain explicitly simulated")
    if review["decision"] not in ("ACCEPTED", "REJECTED") or not isinstance(review["correction_minutes"], int) or isinstance(review["correction_minutes"], bool) or review["correction_minutes"] < 0:
        raise ValueError("review decision or correction time is invalid")
    if review["workpaper_sha256"] != digests["workpaper"]:
        raise ValueError("review is not bound to this workpaper version")
    _text(review["reviewer_role"], "reviewer_role")
    if cost["currency"] != "USD":
        raise ValueError("reference costs must be USD")
    categories = _object(cost["categories"], COST_CATEGORIES, "cost categories")
    amounts = {name: _decimal(value, f"cost.{name}") for name, value in categories.items()}
    facts: dict[str, dict[str, Any]] = {}
    for fact in source["facts"]:
        _object(fact, {"fact_id", "taxonomy", "concept", "unit", "value", "start", "end", "accession", "filed", "form"}, "source fact")
        fact_id = _text(fact["fact_id"], "fact_id")
        if fact_id in facts or fact["accession"] != source["accession"] or fact["form"] != "10-K" or fact["end"] != protocol["period_end"]:
            raise ValueError("duplicate fact or inconsistent source filing or period")
        _decimal(fact["value"], f"fact {fact_id}")
        facts[fact_id] = fact
    if set(facts) != set(protocol["required_fact_ids"]):
        raise ValueError("source facts differ from protocol requirements")
    claims: dict[str, dict[str, Any]] = {}
    for claim in workpaper["claims"]:
        if not isinstance(claim, dict) or "claim_id" not in claim:
            raise ValueError("claim must have an id")
        claim_id = _text(claim["claim_id"], "claim_id")
        if claim_id in claims:
            raise ValueError("claim IDs must be unique")
        claims[claim_id] = claim
    if set(claims) != set(facts) | {"operating_margin_pct"}:
        raise ValueError("workpaper claims differ from protocol requirements")

    checks: list[dict[str, Any]] = []
    for fact_id in protocol["required_fact_ids"]:
        fact, claim = facts[fact_id], claims[fact_id]
        _object(claim, {"claim_id", "fact_id", "value", "unit", "start", "end"}, f"claim {fact_id}")
        codes = []
        if claim["fact_id"] != fact_id:
            codes.append("CITATION_FACT_MISMATCH")
        if claim["unit"] != fact["unit"] or claim["start"] != fact["start"] or claim["end"] != fact["end"]:
            codes.append("UNIT_OR_PERIOD_MISMATCH")
        if _decimal(claim["value"], f"claim {fact_id}") != _decimal(fact["value"], f"fact {fact_id}"):
            codes.append("VALUE_MISMATCH")
        checks.append({"claim_id": fact_id, "source_fact_id": fact_id, "status": "FAIL" if codes else "PASS", "codes": codes})
    margin = claims["operating_margin_pct"]
    _object(margin, {"claim_id", "formula", "value", "unit"}, "margin claim")
    margin_codes = []
    if margin["formula"] != margin_rule["formula"] or margin["unit"] != "percent":
        margin_codes.append("FORMULA_OR_UNIT_MISMATCH")
    revenue = _decimal(facts["revenue"]["value"], "revenue")
    if revenue == 0:
        raise ValueError("cannot calculate margin with zero revenue")
    expected_margin = (Decimal(100) * _decimal(facts["operating_income"]["value"], "operating income") / revenue).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if _decimal(margin["value"], "margin value") != expected_margin:
        margin_codes.append("FORMULA_VALUE_MISMATCH")
    checks.append({"claim_id": "operating_margin_pct", "source_fact_id": None, "status": "FAIL" if margin_codes else "PASS", "codes": margin_codes})
    passed = sum(check["status"] == "PASS" for check in checks)
    accepted = passed == len(checks) and review["decision"] == "ACCEPTED"
    total = sum(amounts.values(), Decimal(0))
    summary = {
        "checks_passed": passed,
        "checks_total": len(checks),
        "simulated_review_decision": review["decision"],
        "correction_minutes": review["correction_minutes"],
        "status": "REFERENCE_ACCEPTED_SIMULATED" if accepted else "HOLD",
        "total_cost_usd": str(total.quantize(Decimal("0.01"))),
        "cost_per_accepted_workpaper_usd": str(total.quantize(Decimal("0.01"))) if accepted else None,
    }
    return checks, summary


def build(case_path: Path) -> dict[str, Any]:
    case, data, digests = _load(case_path)
    checks, summary = _validate(data, digests)
    source, protocol, workpaper = (data[name] for name in ("source", "protocol", "workpaper"))
    body = {
        "finance_passport_version": VERSION,
        "case_id": case["case_id"],
        "workpaper_id": workpaper["workpaper_id"],
        "source_reference": {"url": source["source_url"], "cik": source["cik"], "accession": source["accession"], "fiscal_year": source["fiscal_year"]},
        "protocol_id": protocol["protocol_id"],
        "input_sha256": digests,
        "checks": checks,
        "summary": summary,
        "evidence_class": "PUBLIC_SEC_EXCERPT_WITH_SIMULATED_REVIEW",
        "verification_scope": "LOCKED_LOCAL_RECOMPUTATION_ONLY_NOT_SOURCE_OR_REVIEW_AUTHENTICATION",
        "publication_status": "REFERENCE_DEMO_ONLY",
        "limitations": [
            "The SEC excerpt is a locally captured subset and its retrieval is not independently attested.",
            "The review decision and costs are synthetic; no finance professional accepted this workpaper.",
            "Passing checks do not validate investment conclusions or authorize transactions.",
        ],
    }
    return {**body, "passport_sha256": _sha(_canonical(body))}


def verify(case_path: Path, passport: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(passport, dict) or _canonical(passport) != _canonical(build(case_path)):
        raise ValueError("finance Passport differs from locked local inputs")
    return {"valid": True, "scope": "LOCKED_LOCAL_RECOMPUTATION_ONLY_NOT_SOURCE_OR_REVIEW_AUTHENTICATION"}
