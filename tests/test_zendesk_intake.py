import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.bridge import build as build_bridge
from outcome_fabric.zendesk_intake import run, verify


ROOT = Path(__file__).resolve().parents[1]


def locked(path):
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class ZendeskIntakeTests(unittest.TestCase):
    def setup_case(self, root):
        root = Path(root)
        pages = [
            {"tickets": [{"id": 101, "status": "open", "updated_at": "2026-09-01T00:00:00Z"},
                         {"id": 202, "status": "closed", "updated_at": "2026-09-02T00:00:00Z"},
                         {"id": 303, "status": "solved", "updated_at": "2026-09-02T00:00:00Z"}], "end_of_stream": False},
            {"tickets": [{"id": 101, "status": "solved", "updated_at": "2026-09-03T00:00:00Z"}], "end_of_stream": True},
        ]
        page_paths = []
        for index, page in enumerate(pages):
            path = root / f"page-{index}.json"
            path.write_text(json.dumps(page))
            page_paths.append(path)
        cohort = root / "cohort.csv"
        cohort.write_text("case_id,arm,category\n101,baseline,billing\n202,candidate,billing\n303,candidate,billing\n")
        decisions = root / "decisions.csv"
        decisions.write_text("case_id,accepted\n101,true\n202,true\n303,false\n")
        costs = root / "costs.csv"
        categories = ["inference", "retrieval", "infrastructure", "human_qa", "rework", "operations", "allocated_setup"]
        with costs.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["arm", "category", "amount", "currency"])
            for arm in ("baseline", "candidate"):
                for category in categories:
                    writer.writerow([arm, category, "1.00", "USD"])
        config = {
            "schema_version": "0.1.0", "tenant_id": "pilot-a", "passport_id": "pilot-a-001",
            "subject": {"workload": "AI-assisted customer support", "deployment": "Private export pilot"},
            "protocol": {"id": "support-accepted-resolution", "version": "1.0.0",
                         "acceptance_rule": "Customer-reviewed resolution", "measurement_window": "2026-09", "currency": "USD"},
            "pages": [locked(path) for path in page_paths], "cohort": locked(cohort),
            "decisions": locked(decisions), "costs": locked(costs),
        }
        path = root / "intake.json"
        path.write_text(json.dumps(config))
        return path, config

    def test_private_offline_intake_and_recompute(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, _ = self.setup_case(directory)
            output = Path(directory) / "private-output"
            report = run(config_path, output)
            self.assertEqual(report["eligible_cohort_cases"], 3)
            self.assertTrue(verify(config_path, output)["valid"])
            package = build_bridge(output / "manifest.json")
            self.assertEqual(package["passport"]["evidence_class"], "CUSTOMER_SUPPLIED_UNVERIFIED")
            self.assertEqual(package["passport"]["metrics"]["candidate"]["accepted_cases"], 1)
            self.assertIsNone(package["passport"]["comparison"]["cost_per_accepted_resolution_delta"])
            self.assertNotIn(b"updated_at", (output / "cases.csv").read_bytes())
            with self.assertRaisesRegex(ValueError, "already exists"):
                run(config_path, output)
            (output / "decisions.csv").write_text("case_id,accepted\n101,true\n202,true\n303,true\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify(config_path, output)

    def test_incomplete_stream_and_unresolved_ticket_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, config = self.setup_case(directory)
            page = Path(directory) / "page-1.json"
            payload = json.loads(page.read_text())
            payload["end_of_stream"] = False
            page.write_text(json.dumps(payload))
            config["pages"][1] = locked(page)
            config_path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "final page"):
                run(config_path, Path(directory) / "output")
            self.assertFalse((Path(directory) / "output").exists())
            payload["end_of_stream"] = True
            payload["tickets"][0]["status"] = "open"
            page.write_text(json.dumps(payload))
            config["pages"][1] = locked(page)
            config_path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "not solved"):
                run(config_path, Path(directory) / "output")

    def test_source_digest_and_decision_coverage_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, config = self.setup_case(directory)
            decisions = Path(directory) / "decisions.csv"
            decisions.write_text("case_id,accepted\n101,true\n")
            with self.assertRaisesRegex(ValueError, "locked SHA-256"):
                run(config_path, Path(directory) / "output")
            config["decisions"] = locked(decisions)
            config_path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "every case"):
                run(config_path, Path(directory) / "output")
            self.assertFalse((Path(directory) / "output").exists())


if __name__ == "__main__":
    unittest.main()
