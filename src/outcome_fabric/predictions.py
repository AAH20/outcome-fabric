"""Framework-neutral prediction-file replay without executing submitter code."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .simulation import run_simulation


def replay_predictions(scenario_path: Path, protocol_path: Path, predictions_path: Path, output_dir: Path) -> dict[str, Any]:
    """Match exactly one prediction per scenario case and arm, then score it."""
    scenario_bytes = Path(scenario_path).read_bytes()
    if len(scenario_bytes) > 10_000_000:
        raise ValueError("scenario file exceeds replay size limit")
    scenario = json.loads(scenario_bytes)
    raw = Path(predictions_path).read_bytes()
    if len(raw) > 10_000_000:
        raise ValueError("prediction file exceeds replay size limit")
    submission = json.loads(raw)
    if not isinstance(submission, dict) or set(submission) != {"schema_version", "scenario_sha256", "arms"}:
        raise ValueError("prediction submission has missing or unexpected fields")
    if submission["schema_version"] != "0.1.0" or submission["scenario_sha256"] != hashlib.sha256(scenario_bytes).hexdigest():
        raise ValueError("prediction submission is not bound to the exact scenario bytes")
    arms = submission["arms"]
    if not isinstance(arms, dict) or set(arms) != {"baseline", "candidate"}:
        raise ValueError("prediction arms must be baseline and candidate")
    if not isinstance(scenario, dict) or not isinstance(scenario.get("cases"), list):
        raise ValueError("scenario must contain a case array")
    if any(not isinstance(case, dict) or not isinstance(case.get("id"), str) for case in scenario["cases"]):
        raise ValueError("scenario case IDs must be text")
    expected_ids = {case["id"] for case in scenario["cases"]}
    if len(expected_ids) != len(scenario["cases"]):
        raise ValueError("scenario case IDs must be unique")
    predictions: dict[str, dict[str, str]] = {}
    for arm in ("baseline", "candidate"):
        rows = arms[arm]
        if not isinstance(rows, list) or len(rows) != len(expected_ids):
            raise ValueError("each arm needs exactly one prediction per case")
        resolved: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"case_id", "resolution_code"}:
                raise ValueError("prediction row needs case_id and resolution_code")
            case_id, code = row["case_id"], row["resolution_code"]
            if not isinstance(case_id, str) or case_id not in expected_ids or case_id in resolved:
                raise ValueError("prediction case IDs must uniquely match the scenario")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", code):
                raise ValueError("resolution_code must be a short safe code")
            resolved[case_id] = code
        if set(resolved) != expected_ids:
            raise ValueError("prediction case IDs must cover the scenario exactly")
        predictions[arm] = resolved

    def baseline(case: dict[str, str]) -> str:
        return predictions["baseline"][case["case_id"]]

    def candidate(case: dict[str, str]) -> str:
        return predictions["candidate"][case["case_id"]]

    receipt = run_simulation(
        scenario_path, protocol_path, output_dir,
        {"baseline": baseline, "candidate": candidate},
        run_scope="SYNTHETIC_PREDICTION_REPLAY_NOT_AGENT_EXECUTION",
    )
    receipt["prediction_file_sha256"] = hashlib.sha256(raw).hexdigest()
    (Path(output_dir) / "run-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt
