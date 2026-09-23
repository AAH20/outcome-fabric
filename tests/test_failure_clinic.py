import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.failure_clinic import run, verify


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "fixtures/failure-clinic/apparent-completion.json"


class FailureClinicTests(unittest.TestCase):
    def test_case_exposes_completion_acceptance_gap_and_rework_cost(self):
        report = run(CASE)
        self.assertEqual(report["verifier_results"]["completion_only_verifier"], "PASS")
        self.assertEqual(report["verifier_results"]["independent_acceptance_verifier"], "FAIL")
        self.assertEqual(report["verifier_results"]["failure_codes"], ["HUMAN_ACCEPTANCE_NOT_ESTABLISHED", "REQUIRED_EVIDENCE_GAP"])
        self.assertEqual(report["verifier_results"]["post_rework_status"], "ACCEPTED_AFTER_REWORK")
        self.assertEqual(report["costs"]["total_after_rework_usd"], "21.35")
        self.assertTrue(verify(CASE, report)["valid"])

    def test_tamper_detection(self):
        report = run(CASE)
        altered = copy.deepcopy(report)
        altered["costs"]["total_after_rework_usd"] = "2.35"
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(CASE, altered)

    def test_case_rejects_unlabeled_non_synthetic_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            case = json.loads(CASE.read_text(encoding="utf-8"))
            case["evidence_class"] = "INDEPENDENTLY_VERIFIED"
            path.write_text(json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be synthetic"):
                run(path)


if __name__ == "__main__":
    unittest.main()
