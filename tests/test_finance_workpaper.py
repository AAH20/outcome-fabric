import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.finance_workpaper import build, verify


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/finance-workpaper"
CASE = FIXTURE / "case.json"


class FinanceWorkpaperTests(unittest.TestCase):
    def test_public_excerpt_reference_is_reproducible_and_scope_limited(self):
        passport = build(CASE)
        self.assertEqual(passport, build(CASE))
        self.assertTrue(verify(CASE, passport)["valid"])
        self.assertEqual(passport["summary"]["checks_passed"], 9)
        self.assertEqual(passport["summary"]["cost_per_accepted_workpaper_usd"], "4.85")
        self.assertEqual(passport["summary"]["status"], "REFERENCE_ACCEPTED_SIMULATED")
        self.assertEqual(passport["publication_status"], "REFERENCE_DEMO_ONLY")
        self.assertNotIn("REVIEWED_BY_PROFESSIONAL", json.dumps(passport))

    def test_altered_passport_does_not_verify(self):
        passport = copy.deepcopy(build(CASE))
        passport["summary"]["total_cost_usd"] = "1.00"
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(CASE, passport)

    def test_changed_source_breaks_case_lock(self):
        with self._copy() as root:
            path = root / "source.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "source differs"):
                build(root / "case.json")

    def test_wrong_value_period_and_citation_hold(self):
        for mutation, expected in (
            (lambda x: x["claims"][0].update(value="1"), "VALUE_MISMATCH"),
            (lambda x: x["claims"][0].update(end="2024-09-28"), "UNIT_OR_PERIOD_MISMATCH"),
            (lambda x: x["claims"][0].update(fact_id="net_income"), "CITATION_FACT_MISMATCH"),
            (lambda x: x["claims"][-1].update(value="50.00"), "FORMULA_VALUE_MISMATCH"),
        ):
            with self.subTest(expected=expected), self._copy() as root:
                workpaper = json.loads((root / "workpaper.json").read_text())
                mutation(workpaper)
                self._write_and_lock(root, "workpaper.json", workpaper)
                review = json.loads((root / "review.json").read_text())
                review["workpaper_sha256"] = self._digest(root / "workpaper.json")
                self._write_and_lock(root, "review.json", review)
                passport = build(root / "case.json")
                self.assertEqual(passport["summary"]["status"], "HOLD")
                self.assertIsNone(passport["summary"]["cost_per_accepted_workpaper_usd"])
                self.assertIn(expected, [code for item in passport["checks"] for code in item["codes"]])

    def test_review_cannot_accept_new_workpaper_version(self):
        with self._copy() as root:
            workpaper = json.loads((root / "workpaper.json").read_text())
            workpaper["workpaper_id"] = "revised-version"
            self._write_and_lock(root, "workpaper.json", workpaper)
            with self.assertRaisesRegex(ValueError, "review is not bound"):
                build(root / "case.json")

    def test_rejected_workpaper_has_no_accepted_unit_cost(self):
        with self._copy() as root:
            review = json.loads((root / "review.json").read_text())
            review["decision"] = "REJECTED"
            self._write_and_lock(root, "review.json", review)
            self.assertEqual(build(root / "case.json")["summary"]["status"], "HOLD")

    def test_case_path_must_not_escape(self):
        with self._copy() as root:
            case = json.loads((root / "case.json").read_text())
            case["source"]["path"] = "../source.json"
            (root / "case.json").write_text(json.dumps(case))
            with self.assertRaisesRegex(ValueError, "escapes"):
                build(root / "case.json")

    @staticmethod
    def _digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _write_and_lock(cls, root, filename, value):
        (root / filename).write_text(json.dumps(value, sort_keys=True) + "\n")
        case = json.loads((root / "case.json").read_text())
        case[filename.removesuffix(".json")]["sha256"] = cls._digest(root / filename)
        (root / "case.json").write_text(json.dumps(case))

    @staticmethod
    def _copy():
        class FixtureCopy:
            def __init__(self):
                self.temp = tempfile.TemporaryDirectory()

            def __enter__(self):
                root = Path(self.temp.name)
                for path in FIXTURE.iterdir():
                    shutil.copyfile(path, root / path.name)
                return root

            def __exit__(self, *_):
                self.temp.cleanup()

        return FixtureCopy()


if __name__ == "__main__":
    unittest.main()
