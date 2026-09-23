"""Assemble a private Zendesk snapshot and declared pilot inputs into a Bridge package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .zendesk_intake import _read_locked, run as run_intake, verify as verify_intake


PAGE_NAME = re.compile(r"page-[0-9]{4}\.json\Z")


def _private(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)


def assemble(collection_dir: Path, pilot_config_path: Path, output_dir: Path) -> dict:
    collection_dir, pilot_config_path, output_dir = Path(collection_dir), Path(pilot_config_path), Path(output_dir)
    receipt = json.loads((collection_dir / "collection-receipt.json").read_text(encoding="utf-8"))
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != "0.1.0"
            or receipt.get("source") != "ZENDESK_OAUTH_BEARER_INCREMENTAL_TICKETS"
            or receipt.get("end_of_stream") is not True or not isinstance(receipt.get("pages"), list)
            or not receipt["pages"] or len(receipt["pages"]) > 1000):
        raise ValueError("collection receipt is invalid or incomplete")
    pilot = json.loads(pilot_config_path.read_text(encoding="utf-8"))
    required = {"schema_version", "tenant_id", "passport_id", "subject", "protocol", "cohort", "decisions", "costs"}
    if not isinstance(pilot, dict) or set(pilot) != required or pilot["schema_version"] != "0.1.0":
        raise ValueError("pilot sidecar configuration is invalid")
    if output_dir.exists():
        raise ValueError("output directory already exists; refusing to overwrite private evidence")
    pages = []
    page_bytes = {}
    for index, entry in enumerate(receipt["pages"]):
        name = f"page-{index:04d}.json"
        if not isinstance(entry, dict) or entry.get("path") != name or not PAGE_NAME.fullmatch(name):
            raise ValueError("collection pages are out of sequence")
        raw = _read_locked(collection_dir, {"path": name, "sha256": entry.get("sha256")}, ".json")
        page_bytes[name] = raw
        pages.append({"path": name, "sha256": entry["sha256"]})
    sidecars = {name: _read_locked(pilot_config_path.parent, pilot[name], ".csv") for name in ("cohort", "decisions", "costs")}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".outcome-pilot-", dir=output_dir.parent))
    try:
        for name, raw in page_bytes.items():
            _private(staging / name, raw)
        for name, raw in sidecars.items():
            _private(staging / f"{name}.csv", raw)
        intake = {key: pilot[key] for key in ("schema_version", "tenant_id", "passport_id", "subject", "protocol")}
        intake["pages"] = pages
        for name, raw in sidecars.items():
            intake[name] = {"path": f"{name}.csv", "sha256": hashlib.sha256(raw).hexdigest()}
        _private(staging / "intake.json", (json.dumps(intake, indent=2, sort_keys=True) + "\n").encode())
        report = run_intake(staging / "intake.json", staging / "derived")
        verify_intake(staging / "intake.json", staging / "derived")
        if output_dir.exists():
            raise ValueError("output directory appeared during pilot assembly")
        staging.rename(output_dir)
        return {"valid_local_recomputation": True, "tenant_id": pilot["tenant_id"],
                "eligible_cohort_cases": report["eligible_cohort_cases"],
                "evidence_class": "CUSTOMER_SUPPLIED_UNVERIFIED",
                "scope": "API_SNAPSHOT_AND_DECLARED_PILOT_INPUTS_NOT_PERMISSION_OR_REVIEW_AUTHENTICATION"}
    except Exception:
        shutil.rmtree(staging)
        raise
