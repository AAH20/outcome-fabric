"""Deterministic reference kernel for a Laya-compatible outcome exchange.

This module is intentionally small and local.  It models a typed routing
decision, a replayable swarm run, evaluation/evolution gates, and per-job unit
economics.  It does not connect to Laya, execute tools, hire people, move
money, or authenticate a reviewer.  The bundled fixture is synthetic only.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


VERSION = "0.1.0"
_MONEY = Decimal("0.01")
_RATIO = Decimal("0.0001")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _decimal(value: Any, name: str, *, places: int = 2) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a decimal") from exc
    if not result.is_finite() or result < 0 or result.as_tuple().exponent < -places:
        raise ValueError(f"{name} must be finite, nonnegative, and use at most {places} decimal places")
    return result


def _money(value: Any, name: str) -> Decimal:
    return _decimal(value, name).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _require_keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} contract is invalid")
    return value


def _load(spec_path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(spec_path).read_bytes()
    spec = json.loads(raw)
    top = _require_keys(
        spec,
        {"schema_version", "evidence_class", "job", "decision", "swarm", "economics", "evolution", "evaluation", "expected_result", "limitations"},
        "outcome exchange",
    )
    if top["schema_version"] != VERSION or top["evidence_class"] != "SYNTHETIC":
        raise ValueError("outcome exchange fixtures must use the locked synthetic schema")

    job = _require_keys(top["job"], {"job_id", "title", "objective", "budget_usd", "acceptance_criteria", "worker_policy"}, "job")
    for key in ("job_id", "title", "objective"):
        if not isinstance(job[key], str) or not job[key].strip():
            raise ValueError(f"job.{key} must be nonempty text")
    _money(job["budget_usd"], "job.budget_usd")
    criteria = job["acceptance_criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("job.acceptance_criteria must be nonempty")
    criterion_ids: list[str] = []
    for criterion in criteria:
        item = _require_keys(criterion, {"id", "description", "required"}, "acceptance criterion")
        if not isinstance(item["id"], str) or not item["id"].strip() or item["id"] in criterion_ids:
            raise ValueError("acceptance criterion ids must be unique nonempty text")
        if not isinstance(item["description"], str) or not item["description"].strip() or not isinstance(item["required"], bool):
            raise ValueError("acceptance criterion fields are invalid")
        criterion_ids.append(item["id"])
    policy = _require_keys(job["worker_policy"], {"allowed_worker_types", "requires_independent_verifier"}, "worker policy")
    if not isinstance(policy["allowed_worker_types"], list) or not policy["allowed_worker_types"] or not isinstance(policy["requires_independent_verifier"], bool):
        raise ValueError("worker policy is invalid")
    if any(worker_type not in {"human", "agent", "swarm"} for worker_type in policy["allowed_worker_types"]):
        raise ValueError("worker policy contains an unsupported worker type")

    decision = _require_keys(top["decision"], {"model", "type", "question", "options", "selected", "probabilities"}, "decision")
    if not all(isinstance(decision[key], str) and decision[key].strip() for key in ("model", "type", "question", "selected")):
        raise ValueError("decision text fields are invalid")
    if decision["type"] != "choice" or not isinstance(decision["options"], list) or not decision["options"]:
        raise ValueError("the reference decision must be a nonempty choice")
    if len(set(decision["options"])) != len(decision["options"]):
        raise ValueError("decision options must be unique")
    if decision["selected"] not in decision["options"] or decision["selected"] not in policy["allowed_worker_types"]:
        raise ValueError("selected worker type is not allowed")
    probabilities = decision["probabilities"]
    if not isinstance(probabilities, dict) or set(probabilities) != set(decision["options"]):
        raise ValueError("decision probabilities must match options")
    probability_sum = Decimal(0)
    for option, value in probabilities.items():
        probability = _decimal(value, f"decision.probabilities.{option}", places=6)
        if probability > 1:
            raise ValueError("decision probabilities must be between zero and one")
        probability_sum += probability
    if abs(probability_sum - Decimal(1)) > _RATIO:
        raise ValueError("decision probabilities must sum to one")

    swarm = _require_keys(top["swarm"], {"members", "tasks", "observed_evidence", "human_acceptance", "rework_cost_usd", "elapsed_seconds"}, "swarm")
    if not isinstance(swarm["members"], list) or not swarm["members"] or not isinstance(swarm["tasks"], list) or not swarm["tasks"]:
        raise ValueError("swarm members and tasks must be nonempty")
    member_ids: set[str] = set()
    for member in swarm["members"]:
        item = _require_keys(member, {"id", "worker_type", "role", "capabilities"}, "swarm member")
        if not isinstance(item["id"], str) or not item["id"].strip() or item["id"] in member_ids:
            raise ValueError("swarm member ids must be unique nonempty text")
        if item["worker_type"] not in {"human", "agent", "swarm"} or not isinstance(item["role"], str) or not item["role"].strip() or not isinstance(item["capabilities"], list):
            raise ValueError("swarm member fields are invalid")
        member_ids.add(item["id"])
    task_ids: set[str] = set()
    for task in swarm["tasks"]:
        item = _require_keys(task, {"id", "role", "status", "evidence"}, "swarm task")
        if not isinstance(item["id"], str) or not item["id"].strip() or item["id"] in task_ids:
            raise ValueError("swarm task ids must be unique nonempty text")
        if item["status"] not in {"COMPLETED", "PENDING", "FAILED"} or not isinstance(item["role"], str) or not item["role"].strip() or not isinstance(item["evidence"], list):
            raise ValueError("swarm task fields are invalid")
        task_ids.add(item["id"])
    if not isinstance(swarm["observed_evidence"], list) or any(not isinstance(item, str) or not item.strip() for item in swarm["observed_evidence"]):
        raise ValueError("swarm observed evidence is invalid")
    if swarm["human_acceptance"] not in {"ACCEPTED", "REJECTED", "NOT_RECORDED"}:
        raise ValueError("swarm human acceptance is invalid")
    _money(swarm["rework_cost_usd"], "swarm.rework_cost_usd")
    if isinstance(swarm["elapsed_seconds"], bool) or not isinstance(swarm["elapsed_seconds"], int) or swarm["elapsed_seconds"] < 0:
        raise ValueError("swarm.elapsed_seconds must be a nonnegative integer")

    economics = _require_keys(top["economics"], {"customer_price_usd", "worker_payout_usd", "model_cost_usd", "compute_cost_usd", "human_review_cost_usd", "payment_fee_usd", "support_reserve_usd", "rework_reserve_usd"}, "economics")
    for key in economics:
        _money(economics[key], f"economics.{key}")

    evolution = _require_keys(top["evolution"], {"candidate_version", "parent_version", "change_type", "benchmark_suite", "holdout_required", "promotion_gates"}, "evolution")
    if not isinstance(evolution["candidate_version"], str) or not evolution["candidate_version"].strip() or evolution["parent_version"] is not None and not isinstance(evolution["parent_version"], str):
        raise ValueError("evolution versions are invalid")
    if not isinstance(evolution["change_type"], str) or not evolution["change_type"].strip() or not isinstance(evolution["benchmark_suite"], list) or not evolution["benchmark_suite"] or not isinstance(evolution["holdout_required"], bool):
        raise ValueError("evolution contract is invalid")
    gates = _require_keys(evolution["promotion_gates"], {"min_first_pass_acceptance", "max_rework_rate", "max_cost_per_accepted_outcome_usd"}, "promotion gates")
    _decimal(gates["min_first_pass_acceptance"], "promotion_gates.min_first_pass_acceptance", places=4)
    _decimal(gates["max_rework_rate"], "promotion_gates.max_rework_rate", places=4)
    _money(gates["max_cost_per_accepted_outcome_usd"], "promotion_gates.max_cost_per_accepted_outcome_usd")

    evaluation = _require_keys(top["evaluation"], {"reviewer_count", "required_metric_names"}, "evaluation")
    if isinstance(evaluation["reviewer_count"], bool) or not isinstance(evaluation["reviewer_count"], int) or evaluation["reviewer_count"] < 0:
        raise ValueError("evaluation.reviewer_count must be a nonnegative integer")
    if not isinstance(evaluation["required_metric_names"], list) or not evaluation["required_metric_names"]:
        raise ValueError("evaluation.required_metric_names must be nonempty")

    expected = _require_keys(top["expected_result"], {"route", "outcome", "accepted", "failure_codes", "total_cost_usd", "contribution_margin_usd", "contribution_margin_pct", "promotion_decision"}, "expected result")
    if not isinstance(expected["failure_codes"], list) or any(not isinstance(code, str) for code in expected["failure_codes"]):
        raise ValueError("expected failure codes are invalid")
    _money(expected["total_cost_usd"], "expected_result.total_cost_usd")
    _money(expected["contribution_margin_usd"], "expected_result.contribution_margin_usd")
    _decimal(expected["contribution_margin_pct"], "expected_result.contribution_margin_pct", places=4)
    if not isinstance(top["limitations"], list) or not top["limitations"] or any(not isinstance(item, str) or not item.strip() for item in top["limitations"]):
        raise ValueError("limitations must be nonempty text")
    return top, _sha(raw)


def run(spec_path: Path) -> dict[str, Any]:
    spec, spec_sha = _load(spec_path)
    job = spec["job"]
    decision = spec["decision"]
    swarm = spec["swarm"]
    required_evidence = [item["id"] for item in job["acceptance_criteria"] if item["required"]]
    observed_evidence = set(swarm["observed_evidence"])
    missing_evidence = sorted(set(required_evidence) - observed_evidence)
    completed_tasks = [task["id"] for task in swarm["tasks"] if task["status"] == "COMPLETED"]
    execution_completed = len(completed_tasks) == len(swarm["tasks"])
    failure_codes: list[str] = []
    if not execution_completed:
        failure_codes.append("SWARM_TASK_NOT_COMPLETED")
    if "HUMAN_ACCEPTANCE" in missing_evidence or swarm["human_acceptance"] == "NOT_RECORDED":
        failure_codes.append("HUMAN_ACCEPTANCE_NOT_ESTABLISHED")
    if missing_evidence:
        failure_codes.append("REQUIRED_EVIDENCE_GAP")
    accepted = execution_completed and not failure_codes
    outcome = "ACCEPTED" if accepted else "UNRESOLVED"

    economics = spec["economics"]
    cost_keys = ("worker_payout_usd", "model_cost_usd", "compute_cost_usd", "human_review_cost_usd", "payment_fee_usd", "support_reserve_usd", "rework_reserve_usd")
    total_cost = sum((_money(economics[key], f"economics.{key}") for key in cost_keys), Decimal(0)).quantize(_MONEY)
    price = _money(economics["customer_price_usd"], "economics.customer_price_usd")
    contribution = (price - total_cost).quantize(_MONEY)
    contribution_pct = (contribution / price * Decimal(100)).quantize(Decimal("0.0001")) if price else Decimal(0)
    evidence_completeness = (Decimal(len(set(required_evidence) & observed_evidence)) / Decimal(len(required_evidence))).quantize(Decimal("0.0001"))
    rework_rate = Decimal(1) if failure_codes else Decimal(0)
    gates = spec["evolution"]["promotion_gates"]
    promotion_checks = {
        "first_pass_acceptance": Decimal(1) if accepted else Decimal(0),
        "rework_rate": rework_rate,
        "cost_per_accepted_outcome": None if not accepted else total_cost,
    }
    promotion_decision = "PROMOTE" if accepted and promotion_checks["first_pass_acceptance"] >= _decimal(gates["min_first_pass_acceptance"], "min_first_pass_acceptance", places=4) and rework_rate <= _decimal(gates["max_rework_rate"], "max_rework_rate", places=4) and total_cost <= _money(gates["max_cost_per_accepted_outcome_usd"], "max_cost_per_accepted_outcome_usd") else "BLOCKED"
    body = {
        "schema_version": VERSION,
        "spec_sha256": spec_sha,
        "evidence_class": "SYNTHETIC",
        "job": {"job_id": job["job_id"], "route": decision["selected"], "candidate_version": spec["evolution"]["candidate_version"]},
        "laya_compatible_decision": {"model": decision["model"], "type": decision["type"], "selected": decision["selected"], "probabilities": decision["probabilities"]},
        "swarm_replay": {"completed_task_ids": completed_tasks, "execution_completed": execution_completed, "required_evidence": required_evidence, "observed_evidence": sorted(observed_evidence), "missing_evidence": missing_evidence, "human_acceptance": swarm["human_acceptance"], "outcome": outcome, "accepted": accepted, "failure_codes": failure_codes, "elapsed_seconds": swarm["elapsed_seconds"], "rework_cost_usd": str(_money(swarm["rework_cost_usd"], "swarm.rework_cost_usd"))},
        "evaluation": {"first_pass_acceptance": accepted, "evidence_completeness": str(evidence_completeness), "reviewer_agreement": None if spec["evaluation"]["reviewer_count"] < 2 else "NOT_IMPLEMENTED", "rework_rate": str(rework_rate), "cost_per_accepted_outcome_usd": None if not accepted else str(total_cost), "metric_scope": "ONE_SYNTHETIC_RUN_NOT_A_BENCHMARK"},
        "evolution_gate": {"candidate_version": spec["evolution"]["candidate_version"], "parent_version": spec["evolution"]["parent_version"], "holdout_required": spec["evolution"]["holdout_required"], "promotion_checks": {key: (None if value is None else str(value)) for key, value in promotion_checks.items()}, "decision": promotion_decision},
        "unit_economics": {"customer_price_usd": str(price), "total_cost_usd": str(total_cost), "contribution_margin_usd": str(contribution), "contribution_margin_pct": str(contribution_pct), "cost_basis": "SYNTHETIC_ESTIMATE_NOT_OBSERVED_UNIT_ECONOMICS"},
        "claim_scope": "LOCAL_SYNTHETIC_REFERENCE_KERNEL_ONLY_NOT_A_MARKETPLACE_NOT_CUSTOMER_EVIDENCE",
        "limitations": spec["limitations"],
    }
    report = {**body, "report_sha256": _sha(_canonical(body))}
    expected = spec["expected_result"]
    checks = {
        "route": report["job"]["route"] == expected["route"],
        "outcome": report["swarm_replay"]["outcome"] == expected["outcome"],
        "accepted": report["swarm_replay"]["accepted"] == expected["accepted"],
        "failure_codes": report["swarm_replay"]["failure_codes"] == expected["failure_codes"],
        "total_cost_usd": report["unit_economics"]["total_cost_usd"] == str(_money(expected["total_cost_usd"], "expected_result.total_cost_usd")),
        "contribution_margin_usd": report["unit_economics"]["contribution_margin_usd"] == str(_money(expected["contribution_margin_usd"], "expected_result.contribution_margin_usd")),
        "contribution_margin_pct": report["unit_economics"]["contribution_margin_pct"] == str(_decimal(expected["contribution_margin_pct"], "expected_result.contribution_margin_pct", places=4)),
        "promotion_decision": report["evolution_gate"]["decision"] == expected["promotion_decision"],
    }
    if not all(checks.values()):
        raise ValueError(f"outcome exchange expected-result checks failed: {checks}")
    return report


def verify(spec_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    expected = run(spec_path)
    if not isinstance(report, dict) or _canonical(report) != _canonical(expected):
        raise ValueError("outcome exchange report differs from locked specification")
    return {"valid": True, "scope": expected["claim_scope"]}
