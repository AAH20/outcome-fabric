import copy
import json
import unittest
from pathlib import Path

from outcome_fabric.engine import evaluate


CASE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/ai-support-service.json").read_text())


class EngineTests(unittest.TestCase):
    def test_selects_feasible_plan_over_cheapest(self):
        result = evaluate(CASE)
        self.assertEqual(result["selected_plan_id"], "local-private")
        self.assertEqual(result["baseline_cheapest_plan_id"], "cheapest-global")
        self.assertFalse(result["baseline_cheapest_is_feasible"])
        self.assertEqual(result["authority"], "ADVISORY_ONLY_NOT_AUTHORIZED")

    def test_missing_approval_evidence_fails_closed(self):
        case = copy.deepcopy(CASE)
        case["plans"][1]["authorization_evidence"] = "unknown"
        self.assertIsNone(evaluate(case)["selected_plan_id"])

    def test_reproducible_digest_and_invalid_cost_rejected(self):
        first = evaluate(CASE)
        self.assertEqual(first["input_sha256"], evaluate(CASE)["input_sha256"])
        case = copy.deepcopy(CASE)
        case["plans"][0]["annual_costs"]["compute"] = -1
        with self.assertRaises(ValueError):
            evaluate(case)


if __name__ == "__main__":
    unittest.main()
