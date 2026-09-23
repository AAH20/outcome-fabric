"""Deterministic plan comparison; never grants real-world authority."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if result < 0 or result != result or result == float("inf"):
        raise ValueError(f"{label} must be finite and nonnegative")
    return result


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an offline case and return an advisory-only, reproducible receipt."""
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    goal = case.get("goal")
    if not isinstance(goal, dict):
        raise ValueError("goal must be an object")
    goal_id = _required_string(goal.get("id"), "goal.id")
    _required_string(goal.get("objective"), "goal.objective")
    currency = _required_string(goal.get("currency"), "goal.currency")
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("goal.currency must be a three-letter code")
    budget = _number(goal.get("annual_budget"), "goal.annual_budget")
    max_days = _number(goal.get("max_delivery_days"), "goal.max_delivery_days")
    min_quality = _number(goal.get("min_quality_score"), "goal.min_quality_score")
    min_availability = _number(goal.get("min_availability_pct"), "goal.min_availability_pct")
    residency = _required_string(goal.get("data_residency"), "goal.data_residency")
    baseline = _number(goal.get("baseline_annual_cost"), "goal.baseline_annual_cost")
    annual_cases = _number(goal.get("annual_cases"), "goal.annual_cases")
    plans = case.get("plans")
    if not isinstance(plans, list) or not plans:
        raise ValueError("plans must be a nonempty array")

    evaluated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("each plan must be an object")
        plan_id = _required_string(plan.get("id"), "plan.id")
        if plan_id in seen:
            raise ValueError(f"duplicate plan id: {plan_id}")
        seen.add(plan_id)
        provider = _required_string(plan.get("provider"), f"{plan_id}.provider")
        plan_residency = _required_string(plan.get("data_residency"), f"{plan_id}.data_residency")
        authorization = plan.get("authorization_evidence")
        if authorization not in ("present", "missing", "unknown"):
            raise ValueError(f"{plan_id}.authorization_evidence must be present, missing, or unknown")
        delivery_days = _number(plan.get("delivery_days"), f"{plan_id}.delivery_days")
        quality = _number(plan.get("quality_score"), f"{plan_id}.quality_score")
        availability = _number(plan.get("availability_pct"), f"{plan_id}.availability_pct")
        costs = plan.get("annual_costs")
        if not isinstance(costs, dict) or not costs:
            raise ValueError(f"{plan_id}.annual_costs must be a nonempty object")
        normalized_costs = {key: _number(value, f"{plan_id}.annual_costs.{key}") for key, value in costs.items() if isinstance(key, str) and key}
        if len(normalized_costs) != len(costs):
            raise ValueError(f"{plan_id}.annual_costs has an invalid key")
        annual_cost = round(sum(normalized_costs.values()), 2)
        constraints = {
            "budget": annual_cost <= budget,
            "delivery": delivery_days <= max_days,
            "quality": quality >= min_quality,
            "availability": availability >= min_availability,
            "residency": plan_residency == residency,
            "authorization_evidence": authorization == "present",
        }
        feasible = all(constraints.values())
        evaluated.append({
            "id": plan_id,
            "provider": provider,
            "feasible": feasible,
            "failed_constraints": [name for name, passed in constraints.items() if not passed],
            "annual_cost": annual_cost,
            "annual_costs": normalized_costs,
            "modeled_annual_savings": round(baseline - annual_cost, 2),
            "modeled_cost_per_case": round(annual_cost / annual_cases, 4) if annual_cases else None,
            "delivery_days": delivery_days,
            "quality_score": quality,
            "availability_pct": availability,
            "data_residency": plan_residency,
            "authorization_evidence": authorization,
        })

    eligible = sorted((plan for plan in evaluated if plan["feasible"]), key=lambda p: (p["annual_cost"], p["delivery_days"], p["id"]))
    cheapest = min(evaluated, key=lambda p: (p["annual_cost"], p["id"]))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {
        "schema_version": "0.1.0",
        "goal_id": goal_id,
        "input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "evidence_class": "SYNTHETIC_OR_USER_SUPPLIED_UNVERIFIED",
        "authority": "ADVISORY_ONLY_NOT_AUTHORIZED",
        "currency": currency.upper(),
        "selected_plan_id": eligible[0]["id"] if eligible else None,
        "baseline_cheapest_plan_id": cheapest["id"],
        "baseline_cheapest_is_feasible": cheapest["feasible"],
        "plans": evaluated,
        "limitations": [
            "Costs and quality are supplied assumptions, not observed outcomes.",
            "An authorization-evidence field is not identity verification or approval.",
            "Modeled savings exclude causal attribution, financing, tax, and unlisted costs.",
        ],
    }
