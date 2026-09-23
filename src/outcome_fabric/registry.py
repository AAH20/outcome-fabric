"""Deterministic, synthetic-only public results index for OutcomeBench."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .simulation import run_simulation


def _local_json_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or not relative.endswith(".json"):
        raise ValueError("submission paths must be relative JSON paths")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("submission path escapes repository root")
    return path


def build_registry(root: Path) -> tuple[dict[str, Any], str]:
    """Re-run every registered synthetic scenario before publishing aggregates."""
    root = Path(root).resolve()
    entries = sorted((root / "registry/submissions").glob("*.json"))
    if not entries:
        raise ValueError("registry needs at least one synthetic submission")
    results = []
    ids: set[str] = set()
    for entry_path in entries:
        if entry_path.is_symlink() or not entry_path.resolve().is_relative_to(root):
            raise ValueError("registry submission must be a regular file within the repository")
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        if not isinstance(entry, dict) or set(entry) != {"id", "label", "track", "scenario", "protocol"}:
            raise ValueError(f"invalid registry submission: {entry_path.name}")
        if entry["track"] != "SYNTHETIC":
            raise ValueError("public registry accepts synthetic submissions only")
        submission_id, label = entry["id"], entry["label"]
        if not isinstance(submission_id, str) or not submission_id.isidentifier() or submission_id in ids:
            raise ValueError("submission ID must be unique and identifier-safe")
        if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", label):
            raise ValueError("submission label must be short plain text")
        ids.add(submission_id)
        scenario = _local_json_path(root, entry["scenario"])
        protocol = _local_json_path(root, entry["protocol"])
        with tempfile.TemporaryDirectory() as directory:
            run_simulation(scenario, protocol, Path(directory) / "run")
            scorecard = json.loads((Path(directory) / "run/scorecard.json").read_text(encoding="utf-8"))
        if scorecard["track"] != "SYNTHETIC":
            raise ValueError("submission produced a non-synthetic scorecard")
        results.append({
            "id": submission_id,
            "label": label.strip(),
            "track": scorecard["track"],
            "protocol_id": scorecard["protocol_id"],
            "protocol_version": scorecard["protocol_version"],
            "comparison_status": scorecard["comparison_status"],
            "baseline": scorecard["metrics"]["baseline"],
            "candidate": scorecard["metrics"]["candidate"],
            "descriptive_cost_delta": scorecard["descriptive_cost_per_accepted_resolution_delta"],
            "scorecard_sha256": scorecard["scorecard_sha256"],
        })
    index = {
        "schema_version": "0.1.0",
        "scope": "SYNTHETIC_REFERENCE_ONLY_NOT_REAL_CUSTOMER_OUTCOMES",
        "ranking_policy": "NO_CROSS_PROTOCOL_OR_EVIDENCE_GRADE_RANKING",
        "results": results,
    }
    lines = [
        "# OutcomeBench synthetic results",
        "",
        "Every result below is a reproducible **synthetic reference** with invented cases and costs. "
        "The table is not a vendor ranking, customer outcome, causal effect, or production recommendation.",
        "",
        "| Run | Protocol | Baseline accepted | Candidate accepted | Baseline cost / accepted | Candidate cost / accepted | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in results:
        baseline, candidate = item["baseline"], item["candidate"]
        lines.append(
            f"| {item['label']} | {item['protocol_id']} {item['protocol_version']} | "
            f"{baseline['accepted_cases']}/{baseline['eligible_cases']} | "
            f"{candidate['accepted_cases']}/{candidate['eligible_cases']} | "
            f"{baseline['cost_per_accepted_resolution']:.4f} | "
            f"{candidate['cost_per_accepted_resolution']:.4f} | {item['comparison_status']} |"
        )
    lines.extend(["", "Results are regenerated from the registered scenario and protocol in CI. "
                  "The underlying fixture is deliberately simple and can be gamed; it demonstrates the harness, not real-world generalization.", ""])
    return index, "\n".join(lines)


def write_registry(root: Path, output_dir: Path) -> None:
    index, markdown = build_registry(root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "RESULTS.md").write_text(markdown, encoding="utf-8")
