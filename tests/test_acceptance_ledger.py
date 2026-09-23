import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.acceptance_ledger import append_event, evaluate, read_events, verify


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "fixtures/acceptance-ledger-config.json"
DEMO = ROOT / "fixtures/acceptance-ledger/demo-events.jsonl"


class AcceptanceLedgerTests(unittest.TestCase):
    def test_demo_is_reproducible_and_scope_limited(self):
        passport = evaluate(CONFIG, DEMO)
        self.assertEqual(passport, evaluate(CONFIG, DEMO))
        self.assertTrue(verify(CONFIG, DEMO, passport)["valid"])
        self.assertEqual(passport["summary"]["declared_accepted_workpapers"], 4)
        self.assertEqual(passport["summary"]["authenticated_accepted_workpapers"], 0)
        self.assertEqual(passport["summary"]["modeled_cost_per_declared_accepted_workpaper_usd"], "13.27")
        self.assertEqual(passport["summary"]["primary_pair_agreement_rate"], 0.6)
        results = {item["task_id"]: item["outcome"] for item in passport["task_results"]}
        self.assertEqual(results["apple-fy2024"], "ACCEPTED_DECLARED")
        self.assertEqual(results["apple-fy2025"], "REVISION_REQUIRED")
        self.assertEqual(passport["review_mode"], "SIMULATED_FIXTURE")

    def test_tamper_detection_and_offline_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            events.write_bytes(DEMO.read_bytes())
            passport = evaluate(CONFIG, events)
            altered = copy.deepcopy(passport)
            altered["summary"]["declared_accepted_workpapers"] = 5
            with self.assertRaisesRegex(ValueError, "differs"):
                verify(CONFIG, events, altered)
            events.write_text(events.read_text().replace('"minutes":6', '"minutes":7', 1))
            with self.assertRaisesRegex(ValueError, "chain differs"):
                read_events(events)

    def test_two_reviewers_and_conflict_adjudication(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            task = "apple-fy2022"
            append_event(CONFIG, events, task, "reviewer_a", "REVIEW", "ACCEPT", 5, "")
            self.assertEqual(evaluate(CONFIG, events)["summary"]["declared_accepted_workpapers"], 0)
            with self.assertRaisesRegex(ValueError, "already acted"):
                append_event(CONFIG, events, task, "reviewer_a", "REVIEW", "ACCEPT", 5, "")
            append_event(CONFIG, events, task, "reviewer_b", "REVIEW", "REJECT", 8, "Needs a better explanation.")
            result = next(row for row in evaluate(CONFIG, events)["task_results"] if row["task_id"] == task)
            self.assertEqual(result["outcome"], "AWAITING_ADJUDICATION")
            append_event(CONFIG, events, task, "adjudicator", "ADJUDICATE", "ACCEPT", 7, "Reviewed the cited facts.")
            result = next(row for row in evaluate(CONFIG, events)["task_results"] if row["task_id"] == task)
            self.assertEqual(result["outcome"], "ACCEPTED_DECLARED")
            with self.assertRaisesRegex(ValueError, "two primary"):
                append_event(CONFIG, events, task, "reviewer_c", "REVIEW", "ACCEPT", 5, "")

    def test_correction_request_requires_new_version_and_note(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            with self.assertRaisesRegex(ValueError, "need a note"):
                append_event(CONFIG, events, "apple-fy2021", "reviewer_a", "REVIEW", "CORRECTION_REQUIRED", 2, "")
            append_event(CONFIG, events, "apple-fy2021", "reviewer_a", "REVIEW", "ACCEPT", 2, "")
            append_event(CONFIG, events, "apple-fy2021", "reviewer_b", "REVIEW", "CORRECTION_REQUIRED", 4, "Correct the note.",
                         findings=[{"claim_id": "revenue", "severity": "MINOR", "reason": "Correct the note.", "proposed_value": None}])
            result = next(row for row in evaluate(CONFIG, events)["task_results"] if row["task_id"] == "apple-fy2021")
            self.assertEqual(result["outcome"], "REVISION_REQUIRED")
            self.assertEqual(result["finding_count"], 1)

    def test_unknown_finding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            with self.assertRaisesRegex(ValueError, "unknown workpaper claim"):
                append_event(CONFIG, events, "apple-fy2021", "reviewer_a", "REVIEW", "CORRECTION_REQUIRED", 4, "Fix claim.",
                             findings=[{"claim_id": "invented", "severity": "MATERIAL", "reason": "Fix claim.", "proposed_value": None}])

    def test_unlocked_or_falsely_authenticated_config_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = json.loads(CONFIG.read_text())
            config["review_mode"] = "AUTHENTICATED_PROFESSIONAL"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "cannot claim authenticated"):
                evaluate(path, DEMO)


if __name__ == "__main__":
    unittest.main()
