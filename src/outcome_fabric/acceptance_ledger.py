"""Local, append-only review events bound to recorded WorkpaperCI submissions.

Aliases and timestamps are operator supplied; hashes detect changes relative to a
trusted head but do not authenticate reviewers or establish real-world consent.
"""

from __future__ import annotations

import fcntl
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .finance_workpaper import VERSION, _canonical, _decimal, _locked, _sha
from .workpaperci import _load_submission, _load_task, run as run_benchmark


ZERO = "0" * 64
ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
DECISIONS = {"ACCEPT", "REJECT", "CORRECTION_REQUIRED"}


def context(config_path: Path) -> dict[str, Any]:
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    required = {"schema_version", "ledger_id", "benchmark", "candidate_submission_id", "rubric_version", "review_mode", "reviewer_hourly_rate_usd"}
    if not isinstance(config, dict) or set(config) != required or config["schema_version"] != VERSION:
        raise ValueError("review configuration contract is invalid")
    for key in ("ledger_id", "candidate_submission_id", "rubric_version"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"{key} must be nonempty text")
    if config["review_mode"] not in ("SIMULATED_FIXTURE", "OPERATOR_DECLARED_UNAUTHENTICATED"):
        raise ValueError("review mode cannot claim authenticated identity")
    rate = _decimal(config["reviewer_hourly_rate_usd"], "reviewer_hourly_rate_usd")
    if rate.as_tuple().exponent < -2:
        raise ValueError("reviewer hourly rate supports two decimal places")
    benchmark, benchmark_sha = _locked(config_path.parent, config["benchmark"], "benchmark")
    root = (config_path.parent / config["benchmark"]["path"]).resolve().parent
    if not isinstance(benchmark.get("tasks"), list):
        raise ValueError("benchmark tasks are invalid")
    tasks: dict[str, dict[str, Any]] = {}
    for entry in benchmark["tasks"]:
        task_id, data, digests = _load_task(root, entry)
        if task_id in tasks:
            raise ValueError("duplicate task ID")
        tasks[task_id] = {"source": data["source"], "protocol": data["protocol"], "digests": digests}
    submission_id, runs = _load_submission(root, benchmark["candidate"], set(tasks))
    if submission_id != config["candidate_submission_id"]:
        raise ValueError("configured candidate differs from benchmark candidate")
    benchmark_path = root / Path(config["benchmark"]["path"]).name
    scorecard = run_benchmark(benchmark_path)
    return {"config": config, "benchmark_sha256": benchmark_sha, "tasks": tasks, "runs": runs, "scorecard": scorecard, "rate": rate}


def _event_body(task_id: str, workpaper_sha256: str, reviewer_alias: str, action: str, decision: str,
                minutes: int, note: str, findings: list[dict[str, Any]], prior_hash: str, timestamp: str) -> dict[str, Any]:
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task ID is required")
    if not isinstance(workpaper_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", workpaper_sha256):
        raise ValueError("workpaper digest is invalid")
    if not isinstance(reviewer_alias, str) or not ALIAS.fullmatch(reviewer_alias):
        raise ValueError("reviewer alias is invalid")
    if action not in ("REVIEW", "ADJUDICATE"):
        raise ValueError("action must be REVIEW or ADJUDICATE")
    if decision not in DECISIONS or (action == "ADJUDICATE" and decision == "CORRECTION_REQUIRED"):
        raise ValueError("decision is invalid for action")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0 or minutes > 1440:
        raise ValueError("review minutes must be an integer from 0 to 1440")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("note must be text under 2000 characters")
    if decision != "ACCEPT" and not note.strip():
        raise ValueError("rejections and correction requests need a note")
    if not isinstance(findings, list) or len(findings) > 25:
        raise ValueError("findings must be a list of at most 25 entries")
    if decision == "CORRECTION_REQUIRED" and not findings:
        raise ValueError("correction requests need a claim-level finding")
    seen_claims = set()
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"claim_id", "severity", "reason", "proposed_value"}:
            raise ValueError("finding contract is invalid")
        claim_id = finding["claim_id"]
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen_claims:
            raise ValueError("finding claim IDs must be unique nonempty text")
        seen_claims.add(claim_id)
        if finding["severity"] not in ("MATERIAL", "MINOR") or not isinstance(finding["reason"], str) or not finding["reason"].strip() or len(finding["reason"]) > 1000:
            raise ValueError("finding severity or reason is invalid")
        if finding["proposed_value"] is not None and (not isinstance(finding["proposed_value"], str) or len(finding["proposed_value"]) > 200):
            raise ValueError("finding proposed_value must be short text or null")
    if not isinstance(prior_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", prior_hash):
        raise ValueError("prior hash is invalid")
    if not isinstance(timestamp, str):
        raise ValueError("timestamp is invalid")
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is invalid") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return {
        "schema_version": VERSION,
        "task_id": task_id,
        "workpaper_sha256": workpaper_sha256,
        "reviewer_alias": reviewer_alias,
        "action": action,
        "decision": decision,
        "minutes": minutes,
        "note": note,
        "findings": findings,
        "prior_hash": prior_hash,
        "timestamp": timestamp,
    }


def read_events(events_path: Path) -> list[dict[str, Any]]:
    path = Path(events_path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    prior = ZERO
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise ValueError("event log contains a blank line")
        event = json.loads(line)
        if not isinstance(event, dict) or set(event) != {"schema_version", "task_id", "workpaper_sha256", "reviewer_alias", "action", "decision", "minutes", "note", "findings", "prior_hash", "timestamp", "event_hash"}:
            raise ValueError("review event contract is invalid")
        body = _event_body(*(event[key] for key in ("task_id", "workpaper_sha256", "reviewer_alias", "action", "decision", "minutes", "note", "findings", "prior_hash", "timestamp")))
        if event["prior_hash"] != prior or event["event_hash"] != _sha(_canonical(body)):
            raise ValueError("review event chain differs from recorded hashes")
        prior = event["event_hash"]
        events.append(event)
    return events


def append_event(config_path: Path, events_path: Path, task_id: str, reviewer_alias: str,
                 action: str, decision: str, minutes: int, note: str, timestamp: str | None = None,
                 findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ctx = context(config_path)
    if task_id not in ctx["tasks"]:
        raise ValueError("unknown review task")
    findings = findings or []
    allowed_claims = {claim["claim_id"] for claim in ctx["runs"][task_id]["workpaper"]["claims"]}
    if any(not isinstance(finding, dict) or finding.get("claim_id") not in allowed_claims for finding in findings):
        raise ValueError("finding references unknown workpaper claim")
    path = Path(events_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / f"{path.name}.lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        events = read_events(path)
        workpaper_sha = ctx["runs"][task_id]["workpaper_sha256"]
        relevant = [event for event in events if event["task_id"] == task_id and event["workpaper_sha256"] == workpaper_sha]
        if any(event["reviewer_alias"] == reviewer_alias for event in relevant):
            raise ValueError("reviewer alias already acted on this workpaper version")
        if action == "REVIEW" and sum(event["action"] == "REVIEW" for event in relevant) >= 2:
            raise ValueError("two primary reviews already exist")
        if action == "ADJUDICATE":
            primary = [event for event in relevant if event["action"] == "REVIEW"]
            if len(primary) != 2 or {event["decision"] for event in primary} != {"ACCEPT", "REJECT"} or any(event["action"] == "ADJUDICATE" for event in relevant):
                raise ValueError("adjudication requires exactly two conflicting primary decisions")
        body = _event_body(task_id, workpaper_sha, reviewer_alias, action, decision, minutes, note, findings,
                           events[-1]["event_hash"] if events else ZERO,
                           timestamp or datetime.now(timezone.utc).isoformat())
        event = {**body, "event_hash": _sha(_canonical(body))}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return event


def evaluate(config_path: Path, events_path: Path) -> dict[str, Any]:
    ctx = context(config_path)
    events = read_events(events_path)
    if any(event["task_id"] not in ctx["tasks"] for event in events):
        raise ValueError("event references unknown task")
    for event in events:
        allowed_claims = {claim["claim_id"] for claim in ctx["runs"][event["task_id"]]["workpaper"]["claims"]}
        if event["workpaper_sha256"] == ctx["runs"][event["task_id"]]["workpaper_sha256"] and any(finding["claim_id"] not in allowed_claims for finding in event["findings"]):
            raise ValueError("event finding references unknown workpaper claim")
    results = {row["task_id"]: row for row in ctx["scorecard"]["candidate"]["task_results"]}
    items = []
    total_minutes = 0
    total_cost = Decimal(0)
    stale_count = 0
    paired_reviews = 0
    agreeing_pairs = 0
    for task_id in sorted(ctx["tasks"]):
        run = ctx["runs"][task_id]
        matching = [event for event in events if event["task_id"] == task_id and event["workpaper_sha256"] == run["workpaper_sha256"]]
        stale_count += sum(event["task_id"] == task_id and event["workpaper_sha256"] != run["workpaper_sha256"] for event in events)
        primary = [event for event in matching if event["action"] == "REVIEW"]
        adjudication = [event for event in matching if event["action"] == "ADJUDICATE"]
        if len(primary) > 2 or len(adjudication) > 1 or len({event["reviewer_alias"] for event in matching}) != len(matching):
            raise ValueError("reviewer independence or event cardinality is invalid")
        if adjudication and (len(primary) != 2 or {event["decision"] for event in primary} != {"ACCEPT", "REJECT"}):
            raise ValueError("adjudication has no conflicting primary decisions")
        decisions = [event["decision"] for event in primary]
        if len(decisions) == 2:
            paired_reviews += 1
            agreeing_pairs += decisions[0] == decisions[1]
        if len(decisions) < 2:
            outcome = "AWAITING_TWO_REVIEWS"
        elif "CORRECTION_REQUIRED" in decisions:
            outcome = "REVISION_REQUIRED"
        elif decisions == ["ACCEPT", "ACCEPT"]:
            outcome = "ACCEPTED_DECLARED"
        elif decisions == ["REJECT", "REJECT"]:
            outcome = "REJECTED_DECLARED"
        elif adjudication:
            outcome = "ACCEPTED_DECLARED" if adjudication[0]["decision"] == "ACCEPT" else "REJECTED_DECLARED"
        else:
            outcome = "AWAITING_ADJUDICATION"
        if results[task_id]["failed_claims"] and outcome == "ACCEPTED_DECLARED":
            outcome = "AUTO_CHECK_HOLD"
        minutes = sum(event["minutes"] for event in matching)
        total_minutes += minutes
        non_review = sum(_decimal(run["costs"][key], key) for key in ("model", "data", "compute", "allocated_setup"))
        task_cost = non_review + ctx["rate"] * Decimal(minutes) / Decimal(60)
        total_cost += task_cost
        items.append({"task_id": task_id, "workpaper_sha256": run["workpaper_sha256"],
                      "automated_status": results[task_id]["automated_status"],
                      "primary_reviews": len(primary), "adjudications": len(adjudication),
                      "review_minutes": minutes, "outcome": outcome,
                      "finding_count": sum(len(event["findings"]) for event in matching),
                      "modeled_cost_usd": str(task_cost.quantize(Decimal("0.01")))})
    accepted = sum(item["outcome"] == "ACCEPTED_DECLARED" for item in items)
    body = {
        "acceptance_ledger_version": VERSION,
        "ledger_id": ctx["config"]["ledger_id"],
        "benchmark_sha256": ctx["benchmark_sha256"],
        "candidate_scorecard_sha256": ctx["scorecard"]["scorecard_sha256"],
        "review_mode": ctx["config"]["review_mode"],
        "identity_status": "REVIEWER_ALIAS_NOT_AUTHENTICATED",
        "event_count": len(events),
        "event_chain_head": events[-1]["event_hash"] if events else ZERO,
        "stale_event_count": stale_count,
        "task_results": items,
        "summary": {"declared_accepted_workpapers": accepted, "authenticated_accepted_workpapers": 0,
                    "review_minutes": total_minutes,
                    "paired_reviews": paired_reviews,
                    "primary_pair_agreement_rate": round(agreeing_pairs / paired_reviews, 6) if paired_reviews else None,
                    "modeled_total_cost_usd": str(total_cost.quantize(Decimal("0.01"))),
                    "modeled_cost_per_declared_accepted_workpaper_usd": str((total_cost / accepted).quantize(Decimal("0.01"))) if accepted else None},
        "verification_scope": "LOCKED_LOCAL_RECOMPUTATION_ONLY_NOT_REVIEWER_IDENTITY_OR_SOURCE_AUTHENTICATION",
        "publication_status": "PRIVATE_REVIEW_REFERENCE_NO_AUTOMATIC_PUBLICATION",
        "limitations": [
            "Reviewer aliases and timestamps are not authenticated; simulated mode is a demo only.",
            "Source snapshots are not independently attested and agent costs are estimates.",
            "Modeled cost per declared acceptance is not measured commercial unit economics or investment advice.",
        ],
    }
    return {**body, "ledger_passport_sha256": _sha(_canonical(body))}


def verify(config_path: Path, events_path: Path, passport: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(passport, dict) or _canonical(passport) != _canonical(evaluate(config_path, events_path)):
        raise ValueError("Acceptance Ledger Passport differs from local inputs")
    return {"valid": True, "scope": "LOCKED_LOCAL_RECOMPUTATION_ONLY_NOT_REVIEWER_IDENTITY_OR_SOURCE_AUTHENTICATION"}
