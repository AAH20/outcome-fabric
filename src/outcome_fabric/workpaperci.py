"""Provider-neutral replay and regression gate for recorded finance workpapers.

This evaluates local public-data fixtures. Automated clean results are not
authenticated human acceptance or evidence of a production finance workflow.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .finance_workpaper import COST_CATEGORIES, VERSION, _canonical, _decimal, _locked, _sha, _validate


def _load_task(benchmark_root: Path, entry: Any) -> tuple[str, dict[str, dict[str, Any]], dict[str, str]]:
    task, _ = _locked(benchmark_root, entry, "task")
    if set(task) != {"schema_version", "task_id", "source", "protocol"} or task["schema_version"] != VERSION:
        raise ValueError("task contract is invalid")
    task_id = task["task_id"]
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be nonempty text")
    task_root = benchmark_root / Path(entry["path"]).parent
    source, source_sha = _locked(task_root, task["source"], "source")
    protocol, protocol_sha = _locked(task_root, task["protocol"], "protocol")
    return task_id, {"source": source, "protocol": protocol}, {"source": source_sha, "protocol": protocol_sha}


def _load_submission(root: Path, entry: Any, task_ids: set[str]) -> tuple[str, dict[str, dict[str, Any]]]:
    submission, _ = _locked(root, entry, "submission")
    if set(submission) != {"schema_version", "submission_id", "adapter_kind", "cost_basis", "runs"} or submission["schema_version"] != VERSION:
        raise ValueError("submission contract is invalid")
    if submission["adapter_kind"] != "RECORDED_OUTPUT_NO_CODE_EXECUTION" or submission["cost_basis"] != "SYNTHETIC_ESTIMATE":
        raise ValueError("unsupported adapter or cost evidence class")
    submission_id = submission["submission_id"]
    if not isinstance(submission_id, str) or not submission_id.strip():
        raise ValueError("submission_id must be nonempty text")
    if not isinstance(submission["runs"], list):
        raise ValueError("submission runs must be a list")
    runs: dict[str, dict[str, Any]] = {}
    for row in submission["runs"]:
        if not isinstance(row, dict) or set(row) != {"task_id", "workpaper", "costs"}:
            raise ValueError("run contract is invalid")
        task_id = row["task_id"]
        if not isinstance(task_id, str) or task_id not in task_ids or task_id in runs:
            raise ValueError("run task is unknown or duplicated")
        workpaper, digest = _locked(root, row["workpaper"], "workpaper")
        costs = row["costs"]
        if not isinstance(costs, dict) or set(costs) != COST_CATEGORIES:
            raise ValueError("run costs must contain all six categories")
        amounts = {name: _decimal(value, f"cost.{name}") for name, value in costs.items()}
        if any(value.as_tuple().exponent < -2 for value in amounts.values()):
            raise ValueError("run costs must use at most two decimal places")
        runs[task_id] = {"workpaper": workpaper, "workpaper_sha256": digest, "costs": costs, "total_cost": sum(amounts.values(), Decimal(0))}
    if set(runs) != task_ids:
        raise ValueError("submission must cover every task exactly once")
    return submission_id, runs


def _score_submission(task_order: list[str], tasks: dict[str, dict[str, Any]], runs: dict[str, dict[str, Any]], submission_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    total_cost = Decimal(0)
    for task_id in task_order:
        task, run = tasks[task_id], runs[task_id]
        data = {
            **task["data"],
            "workpaper": run["workpaper"],
            "review": {
                "schema_version": VERSION,
                "review_kind": "SIMULATED_FIXTURE_REVIEW_NOT_AUTHENTICATED",
                "decision": "REJECTED",
                "workpaper_sha256": run["workpaper_sha256"],
                "reviewer_role": "NO_HUMAN_REVIEW",
                "correction_minutes": 0,
            },
            "cost": {"schema_version": VERSION, "currency": "USD", "categories": run["costs"]},
        }
        checks, _ = _validate(data, {**task["digests"], "workpaper": run["workpaper_sha256"]})
        failures = [check for check in checks if check["status"] == "FAIL"]
        total_cost += run["total_cost"]
        rows.append({
            "task_id": task_id,
            "source_sha256": task["digests"]["source"],
            "workpaper_sha256": run["workpaper_sha256"],
            "checks_passed": len(checks) - len(failures),
            "checks_total": len(checks),
            "failed_claims": len(failures),
            "failure_codes": sorted({code for check in failures for code in check["codes"]}),
            "automated_status": "AUTO_CLEAN_NOT_HUMAN_ACCEPTED" if not failures else "AUTO_HOLD",
            "estimated_cost_usd": str(run["total_cost"].quantize(Decimal("0.01"))),
        })
    clean = sum(row["failed_claims"] == 0 for row in rows)
    return {
        "submission_id": submission_id,
        "task_results": rows,
        "summary": {
            "task_count": len(rows),
            "auto_clean_tasks": clean,
            "failed_claims": sum(row["failed_claims"] for row in rows),
            "estimated_total_cost_usd": str(total_cost.quantize(Decimal("0.01"))),
            "estimated_cost_per_auto_clean_task_usd": str((total_cost / clean).quantize(Decimal("0.01"))) if clean else None,
            "human_accepted_workpapers": 0,
        },
    }


def run(benchmark_path: Path) -> dict[str, Any]:
    benchmark_path = Path(benchmark_path)
    raw = benchmark_path.read_bytes()
    benchmark = json.loads(raw)
    if not isinstance(benchmark, dict) or set(benchmark) != {"schema_version", "benchmark_id", "tasks", "baseline", "candidate", "gate"} or benchmark["schema_version"] != VERSION:
        raise ValueError("benchmark contract is invalid")
    if not isinstance(benchmark["benchmark_id"], str) or not benchmark["benchmark_id"].strip():
        raise ValueError("benchmark_id must be nonempty text")
    if not isinstance(benchmark["tasks"], list) or not benchmark["tasks"]:
        raise ValueError("benchmark tasks must be a nonempty list")
    gate = benchmark["gate"]
    if not isinstance(gate, dict) or set(gate) != {"no_new_failed_claims_per_task", "minimum_candidate_clean_tasks"} or gate["no_new_failed_claims_per_task"] is not True:
        raise ValueError("unsupported regression gate")
    minimum = gate["minimum_candidate_clean_tasks"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= len(benchmark["tasks"]):
        raise ValueError("minimum candidate clean tasks is invalid")
    root = benchmark_path.parent
    tasks: dict[str, dict[str, Any]] = {}
    for entry in benchmark["tasks"]:
        task_id, data, digests = _load_task(root, entry)
        if task_id in tasks:
            raise ValueError("benchmark task IDs must be unique")
        tasks[task_id] = {"data": data, "digests": digests}
    baseline_id, baseline_runs = _load_submission(root, benchmark["baseline"], set(tasks))
    candidate_id, candidate_runs = _load_submission(root, benchmark["candidate"], set(tasks))
    if baseline_id == candidate_id:
        raise ValueError("baseline and candidate IDs must differ")
    order = sorted(tasks)
    baseline = _score_submission(order, tasks, baseline_runs, baseline_id)
    candidate = _score_submission(order, tasks, candidate_runs, candidate_id)
    regressions = [
        task_id for task_id, old, new in zip(order, baseline["task_results"], candidate["task_results"])
        if new["failed_claims"] > old["failed_claims"]
    ]
    passed = not regressions and candidate["summary"]["auto_clean_tasks"] >= minimum
    body = {
        "workpaperci_version": VERSION,
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_sha256": _sha(raw),
        "evidence_class": "PUBLIC_SEC_EXCERPTS_AND_SYNTHETIC_COSTS_NO_HUMAN_REVIEW",
        "baseline": baseline,
        "candidate": candidate,
        "gate": {"status": "PASS" if passed else "FAIL", "regression_task_ids": regressions, "minimum_candidate_clean_tasks": minimum},
        "claim_scope": "RECORDED_OUTPUT_AUTOMATED_CHECKS_ONLY_NOT_HUMAN_ACCEPTANCE",
        "limitations": [
            "Public SEC excerpts are locked locally but their retrieval is not independently attested.",
            "No agent code was executed; costs and submissions are recorded synthetic examples.",
            "An automated clean task is not a human-accepted workpaper or investment recommendation.",
        ],
    }
    return {**body, "scorecard_sha256": _sha(_canonical(body))}


def verify(benchmark_path: Path, scorecard: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scorecard, dict) or _canonical(scorecard) != _canonical(run(benchmark_path)):
        raise ValueError("WorkpaperCI scorecard differs from locked inputs")
    return {"valid": True, "scope": "RECORDED_OUTPUT_AUTOMATED_CHECKS_ONLY_NOT_HUMAN_ACCEPTANCE"}
