import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.workpaperci import run, verify


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/workpaperci"
BENCHMARK = FIXTURE / "benchmark.json"


class WorkpaperCITests(unittest.TestCase):
    def test_five_task_reference_and_offline_verification(self):
        scorecard = run(BENCHMARK)
        self.assertEqual(scorecard, run(BENCHMARK))
        self.assertTrue(verify(BENCHMARK, scorecard)["valid"])
        self.assertEqual(scorecard["baseline"]["summary"]["failed_claims"], 1)
        self.assertEqual(scorecard["candidate"]["summary"]["auto_clean_tasks"], 5)
        self.assertEqual(scorecard["candidate"]["summary"]["human_accepted_workpapers"], 0)
        self.assertEqual(scorecard["gate"]["status"], "PASS")
        self.assertEqual(scorecard["candidate"]["summary"]["estimated_cost_per_auto_clean_task_usd"], "3.05")

    def test_scorecard_tampering_fails_verification(self):
        scorecard = copy.deepcopy(run(BENCHMARK))
        scorecard["candidate"]["summary"]["auto_clean_tasks"] = 4
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(BENCHMARK, scorecard)

    def test_candidate_regression_fails_gate(self):
        with self._copy() as root:
            workpaper_path = root / "submissions/candidate/apple-2024.json"
            workpaper = json.loads(workpaper_path.read_text())
            workpaper["claims"][0]["value"] = "1"
            self._write(workpaper_path, workpaper)
            submission_path = root / "submissions/candidate.json"
            submission = json.loads(submission_path.read_text())
            affected = next(item for item in submission["runs"] if item["task_id"] == "apple-fy2024")
            affected["workpaper"]["sha256"] = self._digest(workpaper_path)
            self._write(submission_path, submission)
            benchmark_path = root / "benchmark.json"
            benchmark = json.loads(benchmark_path.read_text())
            benchmark["candidate"]["sha256"] = self._digest(submission_path)
            self._write(benchmark_path, benchmark)
            result = run(benchmark_path)
            self.assertEqual(result["gate"]["status"], "FAIL")
            self.assertEqual(result["gate"]["regression_task_ids"], ["apple-fy2024"])

    def test_missing_task_and_false_cost_class_are_rejected(self):
        with self._copy() as root:
            submission_path = root / "submissions/candidate.json"
            submission = json.loads(submission_path.read_text())
            submission["runs"].pop()
            self._write(submission_path, submission)
            self._relock_submission(root, submission_path)
            with self.assertRaisesRegex(ValueError, "cover every task"):
                run(root / "benchmark.json")
            submission = json.loads((FIXTURE / "submissions/candidate.json").read_text())
            submission["cost_basis"] = "MEASURED_VERIFIED"
            self._write(submission_path, submission)
            self._relock_submission(root, submission_path)
            with self.assertRaisesRegex(ValueError, "unsupported adapter or cost"):
                run(root / "benchmark.json")

    def test_changed_task_source_breaks_lock(self):
        with self._copy() as root:
            source = root / "tasks/apple-2025/source.json"
            source.write_bytes(source.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "source differs"):
                run(root / "benchmark.json")

    @staticmethod
    def _digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _write(path, value):
        path.write_text(json.dumps(value, sort_keys=True) + "\n")

    @classmethod
    def _relock_submission(cls, root, submission_path):
        benchmark_path = root / "benchmark.json"
        benchmark = json.loads(benchmark_path.read_text())
        benchmark["candidate"]["sha256"] = cls._digest(submission_path)
        cls._write(benchmark_path, benchmark)

    @staticmethod
    def _copy():
        class FixtureCopy:
            def __init__(self):
                self.temp = tempfile.TemporaryDirectory()

            def __enter__(self):
                root = Path(self.temp.name)
                shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
                return root

            def __exit__(self, *_):
                self.temp.cleanup()

        return FixtureCopy()


if __name__ == "__main__":
    unittest.main()
