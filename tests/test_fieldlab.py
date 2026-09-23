import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.fieldlab import PilotIssue, preflight, run, verify


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/fieldlab"
PILOT = FIXTURE / "pilot.json"


class FieldLabTests(unittest.TestCase):
    def test_synthetic_private_pilot_is_reproducible(self):
        readiness = preflight(PILOT)
        self.assertEqual(readiness["status"], "READY_FOR_PRIVATE_REVIEW")
        result = run(PILOT)
        self.assertEqual(result, run(PILOT))
        self.assertTrue(verify(PILOT, result)["valid"])
        self.assertEqual(result["scorecard"]["comparison_status"], "DESCRIPTIVE_COMPARISON_ONLY")
        self.assertEqual(result["scorecard"]["production_recommendation"], "NONE")
        self.assertEqual(result["review_status"], "NOT_INDEPENDENTLY_REVIEWED")
        self.assertEqual(result["publication_status"], "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT")
        self.assertNotIn("case_id", json.dumps(result))
        self.assertNotIn("fixtures/fieldlab", json.dumps(result))

    def test_changed_package_is_rejected(self):
        result = copy.deepcopy(run(PILOT))
        result["scorecard"]["metrics"]["candidate"]["accepted_cases"] -= 1
        with self.assertRaisesRegex(PilotIssue, "RESULT_DIFFERS_FROM_SOURCES"):
            verify(PILOT, result)

    def test_locked_protocol_and_manifest_changes_hold(self):
        with self._copied_fixture() as root:
            pilot = root / "pilot.json"
            for filename, expected in (("protocol.json", "PROTOCOL_LOCK_MISMATCH"), ("manifest.json", "MANIFEST_LOCK_MISMATCH")):
                path = root / filename
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                self.assertEqual(preflight(pilot)["issue_codes"], [expected])
                path.write_bytes(original)

    def test_source_change_and_expected_counts_hold(self):
        with self._copied_fixture() as root:
            pilot = root / "pilot.json"
            path = root / "cases.csv"
            path.write_bytes(path.read_bytes() + b"\n")
            self.assertEqual(preflight(pilot)["issue_codes"], ["SOURCE_RECONCILIATION_FAILED"])
            shutil.copyfile(FIXTURE / "cases.csv", path)
            config = json.loads(pilot.read_text())
            config["expected_case_counts"]["candidate"] = 39
            pilot.write_text(json.dumps(config))
            self.assertEqual(preflight(pilot)["issue_codes"], ["ELIGIBLE_CASE_COUNT_MISMATCH"])
            config["expected_case_counts"]["candidate"] = 40
            config["expected_source_rows"]["decisions"] = 79
            pilot.write_text(json.dumps(config))
            self.assertEqual(preflight(pilot)["issue_codes"], ["SOURCE_ROW_COUNT_MISMATCH"])

    def test_publication_and_path_policy_hold(self):
        with self._copied_fixture() as root:
            pilot = root / "pilot.json"
            config = json.loads(pilot.read_text())
            config["publication_policy"] = "PUBLIC"
            pilot.write_text(json.dumps(config))
            self.assertEqual(preflight(pilot)["issue_codes"], ["PUBLICATION_POLICY_INVALID"])
            config["publication_policy"] = "PRIVATE_ONLY_NO_AUTOMATIC_EXPORT"
            config["manifest"]["path"] = "../bridge/manifest.json"
            pilot.write_text(json.dumps(config))
            self.assertEqual(preflight(pilot)["issue_codes"], ["MANIFEST_PATH_INVALID"])

    def test_declaration_does_not_relabel_synthetic_source(self):
        with self._copied_fixture() as root:
            pilot = root / "pilot.json"
            config = json.loads(pilot.read_text())
            config["permission_declaration"] = "OPERATOR_ASSERTED_PERMISSION_NOT_AUTHENTICATED"
            pilot.write_text(json.dumps(config))
            self.assertEqual(preflight(pilot)["issue_codes"], ["EVIDENCE_CLASS_MISMATCH"])

    def _copied_fixture(self):
        class CopyContext:
            def __init__(self):
                self.temp = tempfile.TemporaryDirectory()

            def __enter__(self):
                root = Path(self.temp.name)
                for path in FIXTURE.iterdir():
                    shutil.copyfile(path, root / path.name)
                return root

            def __exit__(self, *_):
                self.temp.cleanup()

        return CopyContext()


if __name__ == "__main__":
    unittest.main()
