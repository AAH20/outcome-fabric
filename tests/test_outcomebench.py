import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.outcomebench import run, verify


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "fixtures/bridge/manifest.json"
PROTOCOL = ROOT / "protocols/support-accepted-resolution-v1.json"


class OutcomeBenchTests(unittest.TestCase):
    def test_demo_is_reproducible_and_scope_limited(self):
        scorecard = run(MANIFEST, PROTOCOL)
        self.assertEqual(scorecard, run(MANIFEST, PROTOCOL))
        self.assertTrue(verify(MANIFEST, PROTOCOL, scorecard)["valid"])
        self.assertEqual(scorecard["comparison_status"], "DEMO_ONLY_INSUFFICIENT_SAMPLE")
        self.assertIsNone(scorecard["descriptive_cost_per_accepted_resolution_delta"])
        self.assertEqual(scorecard["production_recommendation"], "NONE")
        self.assertEqual(scorecard["track"], "SYNTHETIC")

    def test_tampered_scorecard_is_rejected(self):
        altered = copy.deepcopy(run(MANIFEST, PROTOCOL))
        altered["metrics"]["candidate"]["accepted_cases"] += 1
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(MANIFEST, PROTOCOL, altered)

    def test_protocol_change_invalidates_result(self):
        scorecard = run(MANIFEST, PROTOCOL)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
            protocol["minimum_eligible_cases_per_arm"] = 3
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify(MANIFEST, path, scorecard)
            protocol["passport_protocol"]["acceptance_rule"] = "A different rule"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from locked"):
                run(MANIFEST, path)

    def test_invalid_protocol_claim_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
            protocol["claim_policy"] = "CAUSAL_VERIFIED"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                run(MANIFEST, path)

    def test_sufficient_synthetic_sample_allows_descriptive_delta_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = MANIFEST.parent
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            cases = list(csv.DictReader(io.StringIO((source / "cases.csv").read_text(encoding="utf-8"))))
            decisions = list(csv.DictReader(io.StringIO((source / "decisions.csv").read_text(encoding="utf-8"))))
            for name, rows, fields in (
                ("cases", cases, ["case_id", "arm", "category"]),
                ("decisions", decisions, ["case_id", "accepted"]),
            ):
                with (root / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    for repeat in range(6):
                        for row in rows:
                            writer.writerow({**row, "case_id": f"{row['case_id']}-{repeat}"})
            (root / "costs.csv").write_bytes((source / "costs.csv").read_bytes())
            for name in ("cases", "decisions", "costs"):
                manifest["sources"][name]["sha256"] = hashlib.sha256((root / f"{name}.csv").read_bytes()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            scorecard = run(manifest_path, PROTOCOL)
            self.assertEqual(scorecard["comparison_status"], "DESCRIPTIVE_COMPARISON_ONLY")
            self.assertTrue(scorecard["gates"]["minimum_sample_met"])
            self.assertIsNotNone(scorecard["descriptive_cost_per_accepted_resolution_delta"])
            self.assertEqual(scorecard["production_recommendation"], "NONE")
            self.assertTrue(verify(manifest_path, PROTOCOL, scorecard)["valid"])

    def test_changed_case_mix_blocks_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = MANIFEST.parent
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            changed = (source / "cases.csv").read_text(encoding="utf-8").replace(
                "C005,candidate,technical", "C005,candidate,billing"
            )
            (root / "cases.csv").write_text(changed, encoding="utf-8")
            for name in ("decisions", "costs"):
                (root / f"{name}.csv").write_bytes((source / f"{name}.csv").read_bytes())
            manifest["sources"]["cases"]["sha256"] = hashlib.sha256((root / "cases.csv").read_bytes()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            scorecard = run(manifest_path, PROTOCOL)
            self.assertEqual(scorecard["comparison_status"], "NOT_COMPARABLE_CASE_MIX")
            self.assertIsNone(scorecard["descriptive_cost_per_accepted_resolution_delta"])


if __name__ == "__main__":
    unittest.main()
