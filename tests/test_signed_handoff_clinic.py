import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.signed_handoff_clinic import run, verify


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "fixtures/failure-clinic/signed-handoff-stale-world.json"


class SignedHandoffClinicTests(unittest.TestCase):
    def test_valid_signature_does_not_authorize_stale_world(self):
        report = run(CASE)
        results = report["verifier_results"]
        self.assertEqual(results["origin_verifier"], "PASS")
        self.assertEqual(results["receiver_legitimacy_verifier"], "FAIL")
        self.assertEqual(results["target_outcome_verifier"], "FAIL")
        self.assertEqual(results["final_status"], "UNRESOLVED")
        self.assertFalse(results["effect_allowed"])
        self.assertEqual(
            results["failure_codes"],
            ["STALE_AUTHORIZATION_STATE", "CURRENT_AUTHORIZATION_REVOKED", "TARGET_OUTCOME_NOT_OBSERVED"],
        )
        self.assertTrue(verify(CASE, report)["valid"])

    def test_tamper_detection(self):
        report = run(CASE)
        altered = copy.deepcopy(report)
        altered["verifier_results"]["final_status"] = "COMMITTED"
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(CASE, altered)

    def test_case_rejects_non_synthetic_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            case = json.loads(CASE.read_text(encoding="utf-8"))
            case["evidence_class"] = "INDEPENDENTLY_VERIFIED"
            path.write_text(json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be synthetic"):
                run(path)


if __name__ == "__main__":
    unittest.main()
