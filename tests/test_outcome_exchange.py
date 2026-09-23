import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.outcome_exchange import run, verify


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "fixtures/laya-outcome-exchange/synthetic-job.json"


class OutcomeExchangeTests(unittest.TestCase):
    def test_synthetic_exchange_replays_and_blocks_promotion(self):
        report = run(SPEC)
        self.assertEqual(report["job"]["route"], "swarm")
        self.assertEqual(report["swarm_replay"]["outcome"], "UNRESOLVED")
        self.assertEqual(report["swarm_replay"]["failure_codes"], ["HUMAN_ACCEPTANCE_NOT_ESTABLISHED", "REQUIRED_EVIDENCE_GAP"])
        self.assertEqual(report["unit_economics"]["total_cost_usd"], "61.50")
        self.assertEqual(report["unit_economics"]["contribution_margin_usd"], "13.50")
        self.assertEqual(report["evolution_gate"]["decision"], "BLOCKED")
        self.assertTrue(verify(SPEC, report)["valid"])

    def test_tamper_detection(self):
        report = run(SPEC)
        altered = copy.deepcopy(report)
        altered["unit_economics"]["contribution_margin_usd"] = "99.00"
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(SPEC, altered)

    def test_non_synthetic_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            spec = json.loads(SPEC.read_text(encoding="utf-8"))
            spec["evidence_class"] = "CUSTOMER_SUPPLIED_UNVERIFIED"
            path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "synthetic"):
                run(path)


if __name__ == "__main__":
    unittest.main()
