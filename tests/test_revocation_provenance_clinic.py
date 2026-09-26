import copy
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.revocation_provenance_clinic import run, verify


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "fixtures/failure-clinic/untrusted-revocation-delta.json"


class RevocationProvenanceClinicTests(unittest.TestCase):
    def test_untrusted_delta_stays_unresolved(self):
        report = run(CASE)
        results = report["verifier_results"]
        self.assertEqual(results["origin_verifier"], "PASS")
        self.assertEqual(results["state_delta_provenance_verifier"], "FAIL")
        self.assertEqual(results["target_outcome_verifier"], "FAIL")
        self.assertEqual(results["authorization_conclusion"], "UNRESOLVED")
        self.assertEqual(results["final_status"], "UNRESOLVED")
        self.assertFalse(results["effect_allowed"])
        self.assertTrue(verify(CASE, report)["valid"])

    def test_tamper_detection(self):
        report = run(CASE)
        altered = copy.deepcopy(report)
        altered["verifier_results"]["authorization_conclusion"] = "REVOKED"
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
