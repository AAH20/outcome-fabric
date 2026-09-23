import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.outcomebench import verify as verify_scorecard
from outcome_fabric.predictions import replay_predictions


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "fixtures/simulation/support-rules-40.json"
PROTOCOL = ROOT / "protocols/support-accepted-resolution-v1.json"
PREDICTIONS = ROOT / "fixtures/simulation/support-rules-40-predictions.json"


class PredictionReplayTests(unittest.TestCase):
    def test_replay_scores_external_predictions_without_agent_code(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            receipt = replay_predictions(SCENARIO, PROTOCOL, PREDICTIONS, output)
            scorecard = json.loads((output / "scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["scope"], "SYNTHETIC_PREDICTION_REPLAY_NOT_AGENT_EXECUTION")
            self.assertEqual(scorecard["metrics"]["candidate"]["accepted_cases"], 36)
            self.assertTrue(verify_scorecard(output / "manifest.json", PROTOCOL, scorecard)["valid"])

    def test_missing_duplicate_or_rebound_predictions_are_rejected(self):
        original = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "predictions.json"
            bad = copy.deepcopy(original)
            bad["arms"]["candidate"].pop()
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly one prediction"):
                replay_predictions(SCENARIO, PROTOCOL, path, root / "missing")
            bad = copy.deepcopy(original)
            bad["arms"]["candidate"][1]["case_id"] = bad["arms"]["candidate"][0]["case_id"]
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "uniquely"):
                replay_predictions(SCENARIO, PROTOCOL, path, root / "duplicate")
            bad = copy.deepcopy(original)
            bad["scenario_sha256"] = "0" * 64
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact scenario"):
                replay_predictions(SCENARIO, PROTOCOL, path, root / "rebound")
            self.assertFalse((root / "missing").exists())
            self.assertFalse((root / "duplicate").exists())
            self.assertFalse((root / "rebound").exists())


if __name__ == "__main__":
    unittest.main()
