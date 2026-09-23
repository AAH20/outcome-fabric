import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.outcomebench import verify as verify_scorecard
from outcome_fabric.simulation import baseline_adapter, candidate_adapter, run_simulation


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "fixtures/simulation/support-rules-40.json"
PROTOCOL = ROOT / "protocols/support-accepted-resolution-v1.json"


class SimulationTests(unittest.TestCase):
    def test_executable_run_produces_scope_limited_scorecard(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            receipt = run_simulation(SCENARIO, PROTOCOL, output)
            scorecard = json.loads((output / "scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(scorecard["comparison_status"], "DESCRIPTIVE_COMPARISON_ONLY")
            self.assertEqual(scorecard["metrics"]["baseline"]["accepted_cases"], 20)
            self.assertEqual(scorecard["metrics"]["candidate"]["accepted_cases"], 40)
            self.assertEqual(receipt["scope"], "SYNTHETIC_LOCAL_ADAPTER_RUN_NOT_SANDBOXED")
            self.assertEqual(scorecard["production_recommendation"], "NONE")
            self.assertIsNone(scorecard["acceptance_rate_wilson_95"])
            self.assertEqual(scorecard["interval_status"], "NOT_REPORTED_INDEPENDENCE_NOT_ESTABLISHED")
            self.assertTrue(verify_scorecard(output / "manifest.json", PROTOCOL, scorecard)["valid"])
            self.assertNotIn("wrong invoice", (output / "cases.csv").read_text(encoding="utf-8"))

    def test_adapter_receives_no_expected_answer_and_output_cannot_overwrite(self):
        seen = []

        def baseline(case):
            self.assertEqual(set(case), {"category", "prompt"})
            seen.append(case["prompt"])
            return baseline_adapter(case)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run_simulation(SCENARIO, PROTOCOL, output, {"baseline": baseline, "candidate": candidate_adapter})
            self.assertEqual(len(seen), 40)
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                run_simulation(SCENARIO, PROTOCOL, output)

    def test_invalid_cost_and_duplicate_case_fail_before_writing(self):
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "scenario.json"
            bad = copy.deepcopy(scenario)
            bad["costs"]["candidate"]["inference"] = "-1.00"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonnegative"):
                run_simulation(path, PROTOCOL, root / "bad-cost")
            self.assertFalse((root / "bad-cost").exists())
            bad = copy.deepcopy(scenario)
            bad["cases"].append(copy.deepcopy(bad["cases"][0]))
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                run_simulation(path, PROTOCOL, root / "duplicate")
            self.assertFalse((root / "duplicate").exists())
            bad = copy.deepcopy(scenario)
            bad["cases"][0]["id"] = "bad\nrow"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "safe identifier"):
                run_simulation(path, PROTOCOL, root / "bad-id")
            self.assertFalse((root / "bad-id").exists())


if __name__ == "__main__":
    unittest.main()
