import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.bridge import build, verify


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/bridge"


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("manifest.json", "cases.csv", "decisions.csv", "costs.csv"):
            (self.root / name).write_bytes((FIXTURE / name).read_bytes())
        self.manifest_path = self.root / "manifest.json"

    def _replace_source(self, name, content):
        path = self.root / f"{name}.csv"
        path.write_text(content, encoding="utf-8")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["sources"][name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_reproducible_package_contains_aggregates_not_case_ids(self):
        package = build(self.manifest_path)
        self.assertEqual(package, build(self.manifest_path))
        self.assertTrue(verify(self.manifest_path, package)["valid"])
        self.assertEqual(package["passport"]["metrics"]["baseline"]["cost_per_accepted_resolution"], 40.0)
        self.assertEqual(package["passport"]["metrics"]["candidate"]["cost_per_accepted_resolution"], 26.0)
        self.assertNotIn("B001", json.dumps(package))
        self.assertNotIn("cases.csv", json.dumps(package))
        self.assertEqual(package["passport"]["evidence_class"], "SYNTHETIC")

    def test_tampering_with_package_or_source_is_rejected(self):
        package = build(self.manifest_path)
        changed = copy.deepcopy(package)
        changed["passport"]["metrics"]["candidate"]["accepted_cases"] = 4
        with self.assertRaises(ValueError):
            verify(self.manifest_path, changed)
        with (self.root / "cases.csv").open("a", encoding="utf-8") as handle:
            handle.write("C006,candidate,technical\n")
        with self.assertRaises(ValueError):
            verify(self.manifest_path, package)

    def test_missing_decision_is_rejected_even_with_new_digest(self):
        decisions = (self.root / "decisions.csv").read_text(encoding="utf-8")
        self._replace_source("decisions", decisions.replace("C005,true\n", ""))
        with self.assertRaisesRegex(ValueError, "every case"):
            build(self.manifest_path)

    def test_duplicate_case_is_rejected(self):
        cases = (self.root / "cases.csv").read_text(encoding="utf-8")
        self._replace_source("cases", cases + "B001,baseline,billing\n")
        with self.assertRaisesRegex(ValueError, "unique"):
            build(self.manifest_path)

    def test_missing_cost_category_is_rejected(self):
        costs = (self.root / "costs.csv").read_text(encoding="utf-8")
        self._replace_source("costs", costs.replace("candidate,retrieval,5.00,USD\n", ""))
        with self.assertRaisesRegex(ValueError, "seven cost"):
            build(self.manifest_path)

    def test_path_escape_and_false_evidence_grade_are_rejected(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["sources"]["cases"]["path"] = "../outside.csv"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "escapes"):
            build(self.manifest_path)
        manifest["sources"]["cases"]["path"] = "cases.csv"
        manifest["evidence_class"] = "INDEPENDENTLY_VERIFIED"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "authenticated evidence"):
            build(self.manifest_path)


if __name__ == "__main__":
    unittest.main()
