"""Offline, read-only intake of customer-supplied Zendesk incremental ticket pages.

This module never contacts Zendesk. Ticket status establishes eligibility only;
acceptance decisions are supplied separately and remain unauthenticated.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import build as build_bridge


SHA = re.compile(r"[0-9a-f]{64}\Z")
HEADERS = ["case_id", "arm", "category"]


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_locked(root: Path, entry: dict[str, str], suffix: str) -> bytes:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise ValueError("source requires path and sha256")
    path = Path(entry["path"])
    if path.is_absolute() or path.suffix.lower() != suffix or not SHA.fullmatch(entry["sha256"]):
        raise ValueError("source path or SHA-256 is invalid")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("source path escapes intake directory or does not exist")
    raw = resolved.read_bytes()
    if _digest(raw) != entry["sha256"]:
        raise ValueError("source differs from locked SHA-256")
    return raw


def _csv(raw: bytes, headers: list[str]) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != headers:
            raise ValueError(f"CSV columns must be exactly {headers}")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("source CSV is malformed or not UTF-8") from exc
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("source CSV is empty or has missing or extra fields")
    return rows


def expected(config_path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    fields = {"schema_version", "tenant_id", "passport_id", "subject", "protocol", "pages", "cohort", "decisions", "costs"}
    if not isinstance(config, dict) or set(config) != fields or config["schema_version"] != "0.1.0":
        raise ValueError("Zendesk intake configuration contract is invalid")
    for name in ("tenant_id", "passport_id"):
        if not isinstance(config[name], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", config[name]):
            raise ValueError(f"{name} is invalid")
    if not isinstance(config["subject"], dict) or not isinstance(config["protocol"], dict):
        raise ValueError("subject and protocol must be objects")
    pages = config["pages"]
    if not isinstance(pages, list) or not pages or len(pages) > 1000:
        raise ValueError("pages must be a nonempty bounded list")
    root = config_path.parent
    latest: dict[str, dict[str, Any]] = {}
    page_summaries = []
    for number, entry in enumerate(pages):
        raw = _read_locked(root, entry, ".json")
        page = json.loads(raw)
        if not isinstance(page, dict) or not isinstance(page.get("tickets"), list) or len(page["tickets"]) > 1000 or not isinstance(page.get("end_of_stream"), bool):
            raise ValueError("incremental export page contract is invalid")
        if page["end_of_stream"] != (number == len(pages) - 1):
            raise ValueError("only the final page may end the export stream")
        for ticket in page["tickets"]:
            if not isinstance(ticket, dict) or isinstance(ticket.get("id"), bool) or not isinstance(ticket.get("id"), int) or ticket["id"] < 1:
                raise ValueError("ticket ID is invalid")
            if not isinstance(ticket.get("updated_at"), str) or not ticket["updated_at"] or not isinstance(ticket.get("status"), str):
                raise ValueError("ticket update timestamp or status is missing")
            try:
                updated = datetime.fromisoformat(ticket["updated_at"].replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    raise ValueError("ticket update timestamp needs a timezone")
                updated = updated.astimezone(timezone.utc)
            except ValueError as exc:
                raise ValueError("ticket update timestamp is invalid") from exc
            key = str(ticket["id"])
            prior = latest.get(key)
            if prior and prior["updated_at"] == updated and prior["status"] != ticket["status"]:
                raise ValueError("conflicting ticket snapshots share a timestamp")
            if prior is None or updated > prior["updated_at"]:
                latest[key] = {"updated_at": updated, "status": ticket["status"]}
        page_summaries.append({"sha256": entry["sha256"], "ticket_rows": len(page["tickets"])})
    cohort_raw = _read_locked(root, config["cohort"], ".csv")
    cohort = _csv(cohort_raw, HEADERS)
    seen = set()
    for row in cohort:
        case_id = row["case_id"]
        if not case_id.isdecimal() or case_id in seen or case_id not in latest:
            raise ValueError("cohort case IDs must uniquely match exported tickets")
        if row["arm"] not in ("baseline", "candidate") or not row["category"].strip():
            raise ValueError("cohort arm or category is invalid")
        if latest[case_id]["status"] not in ("solved", "closed"):
            raise ValueError("cohort includes a ticket that is not solved or closed")
        seen.add(case_id)
    decision_raw = _read_locked(root, config["decisions"], ".csv")
    cost_raw = _read_locked(root, config["costs"], ".csv")
    # The Bridge validates exact decision coverage, costs, case mix and protocol.
    rendered = io.StringIO(newline="")
    writer = csv.DictWriter(rendered, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(cohort, key=lambda row: (row["arm"], row["case_id"])))
    outputs = {"cases.csv": rendered.getvalue().encode(), "decisions.csv": decision_raw, "costs.csv": cost_raw}
    manifest = {
        "schema_version": "0.1.0", "passport_id": config["passport_id"],
        "evidence_class": "CUSTOMER_SUPPLIED_UNVERIFIED",
        "permission_status": "DECLARED_BY_OPERATOR_NOT_VERIFIED",
        "baseline_status": "DECLARED_LOCKED_NOT_AUTHENTICATED",
        "subject": config["subject"], "protocol": config["protocol"],
        "sources": {name[:-4]: {"path": name, "sha256": _digest(raw)} for name, raw in outputs.items()},
    }
    outputs["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    report = {
        "schema_version": "0.1.0", "tenant_id": config["tenant_id"],
        "source_system": "ZENDESK_INCREMENTAL_EXPORT_CUSTOMER_SUPPLIED_UNVERIFIED",
        "config_sha256": _digest(config_path.read_bytes()), "pages": page_summaries,
        "unique_exported_tickets": len(latest), "eligible_cohort_cases": len(cohort),
        "output_sha256": {name: _digest(raw) for name, raw in outputs.items()},
        "limitations": ["No Zendesk API authentication or source completeness is established.",
                        "Ticket status is eligibility only; separate decisions are operator supplied.",
                        "Permission, reviewer identity, costs and causal improvement are not verified."],
    }
    outputs["intake-report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    return outputs, report


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    outputs, report = expected(config_path)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("output directory already exists; refusing to overwrite private evidence")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".outcome-intake-", dir=output_dir.parent))
    try:
        for name, raw in outputs.items():
            path = staging / name
            with path.open("xb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(raw)
        build_bridge(staging / "manifest.json")
        if output_dir.exists():
            raise ValueError("output directory appeared during intake")
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging)
        raise
    return report


def verify(config_path: Path, output_dir: Path) -> dict[str, Any]:
    outputs, report = expected(config_path)
    output_dir = Path(output_dir)
    for name, raw in outputs.items():
        if (output_dir / name).read_bytes() != raw:
            raise ValueError(f"{name} differs from recomputed intake output")
    build_bridge(output_dir / "manifest.json")
    return {"valid": True, "scope": "OFFLINE_CUSTOMER_SUPPLIED_EXPORT_RECOMPUTATION_ONLY", "eligible_cohort_cases": report["eligible_cohort_cases"]}
