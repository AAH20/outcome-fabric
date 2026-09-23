import copy
import json
import unittest
from pathlib import Path

from outcome_fabric.passport import generate, verify


CASE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/support-passport-synthetic.json").read_text())


class PassportTests(unittest.TestCase):
    def test_synthetic_passport_is_reproducible_and_verifiable(self):
        passport = generate(CASE)
        self.assertEqual(passport, generate(CASE))
        self.assertTrue(verify(passport)["valid"])
        self.assertEqual(passport["metrics"]["baseline"]["cost_per_accepted_resolution"], 35.0)
        self.assertEqual(passport["metrics"]["candidate"]["cost_per_accepted_resolution"], 28.1176)
        self.assertEqual(passport["verification_scope"], "ARITHMETIC_AND_INTEGRITY_ONLY_NOT_SOURCE_AUTHENTICATED")
        self.assertFalse(passport["comparison"]["causal_lift_claimed"])

    def test_tampered_metric_or_evidence_class_is_rejected(self):
        passport = generate(CASE)
        altered = copy.deepcopy(passport)
        altered["metrics"]["candidate"]["accepted_cases"] += 1
        with self.assertRaises(ValueError):
            verify(altered)
        altered = copy.deepcopy(passport)
        altered["evidence_class"] = "INDEPENDENTLY_VERIFIED"
        with self.assertRaises(ValueError):
            verify(altered)

    def test_invalid_counts_costs_and_case_mix_are_rejected(self):
        for change in (
            lambda case: case["candidate"].update(accepted_cases=1001),
            lambda case: case["candidate"]["costs"].update(inference=-1),
            lambda case: case["candidate"]["case_mix"].update(billing=399),
        ):
            with self.subTest(change=change):
                case = copy.deepcopy(CASE)
                change(case)
                with self.assertRaises(ValueError):
                    generate(case)

    def test_nonidentical_case_mix_suppresses_comparison_delta(self):
        case = copy.deepcopy(CASE)
        case["candidate"]["case_mix"] = {"billing": 500, "technical": 300, "general": 200}
        comparison = generate(case)["comparison"]
        self.assertFalse(comparison["case_mix_identical"])
        self.assertIsNone(comparison["cost_per_accepted_resolution_delta"])


if __name__ == "__main__":
    unittest.main()
