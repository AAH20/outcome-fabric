"""Synthetic support benchmark runner with a framework-neutral Python adapter API.

This is a deterministic local demonstration, not an isolated code sandbox or a
customer-data evaluator. Only explicitly supplied Python callables are invoked.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from .outcomebench import _protocol, run as run_benchmark, verify as verify_benchmark
from .passport import COST_KEYS


Adapter = Callable[[dict[str, str]], str]
ARMS = ("baseline", "candidate")


def baseline_adapter(case: dict[str, str]) -> str:
    prompt = case["prompt"].lower()
    if "refund" in prompt:
        return "refund"
    if "invoice" in prompt:
        return "invoice_copy"
    if "password" in prompt:
        return "password_reset"
    if "delivery" in prompt:
        return "tracking"
    return "escalate"


def candidate_adapter(case: dict[str, str]) -> str:
    prompt = case["prompt"].lower()
    if "wrong invoice" in prompt:
        return "invoice_correction"
    if "duplicate charge" in prompt:
        return "refund"
    if "account locked" in prompt:
        return "unlock"
    if "late delivery" in prompt:
        return "delivery_update"
    return baseline_adapter(case)


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> str:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_simulation(
    scenario_path: Path,
    protocol_path: Path,
    output_dir: Path,
    adapters: dict[str, Adapter] | None = None,
    run_scope: str = "SYNTHETIC_LOCAL_ADAPTER_RUN_NOT_SANDBOXED",
) -> dict[str, Any]:
    """Execute adapters on synthetic prompts and materialize a verified run.

    Callers providing custom adapters are responsible for running only trusted
    local code. The CLI uses the two built-in deterministic adapters.
    """
    scenario_path = Path(scenario_path)
    protocol, protocol_digest = _protocol(protocol_path)
    scenario_bytes = scenario_path.read_bytes()
    scenario = json.loads(scenario_bytes)
    if not isinstance(scenario, dict) or set(scenario) != {"schema_version", "id", "protocol_id", "currency", "cases", "costs"}:
        raise ValueError("scenario has missing or unexpected fields")
    if scenario["schema_version"] != "0.1.0" or scenario["protocol_id"] != protocol["id"]:
        raise ValueError("scenario and protocol versions do not match")
    if not isinstance(scenario["id"], str) or not scenario["id"].strip():
        raise ValueError("scenario.id must be nonempty text")
    if scenario["currency"] != protocol["passport_protocol"]["currency"]:
        raise ValueError("scenario currency does not match protocol")
    cases = scenario["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10000:
        raise ValueError("scenario cases must contain 1 to 10000 entries")
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "category", "prompt", "expected_resolution"}:
            raise ValueError("scenario case has missing or unexpected fields")
        if any(not isinstance(value, str) or not value.strip() for value in case.values()):
            raise ValueError("scenario case fields must be nonempty text")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", case["id"]):
            raise ValueError("scenario case ID must be a short safe identifier")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", case["category"]):
            raise ValueError("scenario category must be a short safe identifier")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", case["expected_resolution"]):
            raise ValueError("expected resolution must be a short safe code")
        if len(case["prompt"]) > 4096:
            raise ValueError("scenario prompt exceeds length limit")
        if case["id"] in seen:
            raise ValueError("scenario case IDs must be unique")
        seen.add(case["id"])
        validated.append(case)
    costs = scenario["costs"]
    if not isinstance(costs, dict) or set(costs) != set(ARMS):
        raise ValueError("scenario costs must contain baseline and candidate")
    for arm in ARMS:
        if not isinstance(costs[arm], dict) or set(costs[arm]) != COST_KEYS:
            raise ValueError("each arm needs seven modeled cost categories")
        for category in COST_KEYS:
            amount = costs[arm][category]
            if not isinstance(amount, str):
                raise ValueError("modeled cost amounts must be decimal strings")
            try:
                parsed = Decimal(amount)
            except InvalidOperation as exc:
                raise ValueError("modeled cost amounts must be decimal strings") from exc
            if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -2:
                raise ValueError("modeled costs must be finite, nonnegative, and have at most two decimals")
    selected = adapters if adapters is not None else {"baseline": baseline_adapter, "candidate": candidate_adapter}
    if set(selected) != set(ARMS) or any(not callable(adapter) for adapter in selected.values()):
        raise ValueError("adapters must provide callable baseline and candidate entries")
    if run_scope not in ("SYNTHETIC_LOCAL_ADAPTER_RUN_NOT_SANDBOXED", "SYNTHETIC_PREDICTION_REPLAY_NOT_AGENT_EXECUTION"):
        raise ValueError("unsupported run scope")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("output directory must not already exist")

    case_rows: list[dict[str, str]] = []
    decision_rows: list[dict[str, str]] = []
    for arm in ARMS:
        for case in validated:
            # Expected resolution is withheld from the adapter call.
            adapter_input = {"case_id": case["id"], "category": case["category"], "prompt": case["prompt"]}
            response = selected[arm](adapter_input)
            if not isinstance(response, str) or not response.strip():
                raise ValueError("adapter must return a nonempty resolution code")
            run_case_id = f"{arm}:{case['id']}"
            case_rows.append({"case_id": run_case_id, "arm": arm, "category": case["category"]})
            decision_rows.append({"case_id": run_case_id, "accepted": str(response == case["expected_resolution"]).lower()})
    cost_rows = [
        {"arm": arm, "category": category, "amount": str(costs[arm][category]), "currency": scenario["currency"]}
        for arm in ARMS for category in sorted(COST_KEYS)
    ]
    output_dir.mkdir(parents=True)
    hashes = {
        "cases": _write_csv(output_dir / "cases.csv", ["case_id", "arm", "category"], case_rows),
        "decisions": _write_csv(output_dir / "decisions.csv", ["case_id", "accepted"], decision_rows),
        "costs": _write_csv(output_dir / "costs.csv", ["arm", "category", "amount", "currency"], cost_rows),
    }
    manifest = {
        "schema_version": "0.1.0",
        "passport_id": f"synthetic-{scenario['id']}",
        "evidence_class": "SYNTHETIC",
        "permission_status": "DECLARED_BY_OPERATOR_NOT_VERIFIED",
        "baseline_status": "DECLARED_LOCKED_NOT_AUTHENTICATED",
        "subject": {"workload": protocol["workload"], "deployment": "Local synthetic adapter simulation"},
        "protocol": protocol["passport_protocol"],
        "sources": {name: {"path": f"{name}.csv", "sha256": digest} for name, digest in hashes.items()},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scorecard = run_benchmark(manifest_path, protocol_path)
    scorecard_path = output_dir / "scorecard.json"
    scorecard_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_benchmark(manifest_path, protocol_path, scorecard)
    receipt = {
        "scenario_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
        "protocol_sha256": protocol_digest,
        "scorecard_sha256": scorecard["scorecard_sha256"],
        "adapter_names": {arm: getattr(selected[arm], "__name__", "callable") for arm in ARMS},
        "scope": run_scope,
        "result": scorecard["comparison_status"],
    }
    (output_dir / "run-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt
