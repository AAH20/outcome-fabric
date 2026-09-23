import json
import shutil
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.registry import build_registry, write_registry


ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_checked_in_registry_is_reproducible_and_synthetic_only(self):
        index, markdown = build_registry(ROOT)
        self.assertEqual(index["scope"], "SYNTHETIC_REFERENCE_ONLY_NOT_REAL_CUSTOMER_OUTCOMES")
        self.assertEqual(len(index["results"]), 2)
        self.assertTrue(all(item["track"] == "SYNTHETIC" for item in index["results"]))
        self.assertEqual({item["execution_mode"] for item in index["results"]}, {"PREDICTION_REPLAY", "BUILTIN_ADAPTERS"})
        self.assertEqual(markdown, (ROOT / "registry/RESULTS.md").read_text(encoding="utf-8"))
        self.assertEqual(index, json.loads((ROOT / "registry/results.json").read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as directory:
            write_registry(ROOT, Path(directory))
            self.assertEqual(markdown, (Path(directory) / "RESULTS.md").read_text(encoding="utf-8"))

    def test_rejects_non_synthetic_and_unsafe_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "registry/submissions/support_rules_demo.json",
                "fixtures/simulation/support-rules-40.json",
                "protocols/support-accepted-resolution-v1.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            entry_path = root / "registry/submissions/support_rules_demo.json"
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            entry["track"] = "CUSTOMER_SUPPLIED_UNVERIFIED"
            entry_path.write_text(json.dumps(entry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "synthetic"):
                build_registry(root)
            entry["track"] = "SYNTHETIC"
            entry["scenario"] = "../outside.json"
            entry_path.write_text(json.dumps(entry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes"):
                build_registry(root)
            entry["scenario"] = "fixtures/simulation/support-rules-40.json"
            entry["label"] = "<script>unsafe</script>"
            entry_path.write_text(json.dumps(entry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plain text"):
                build_registry(root)


if __name__ == "__main__":
    unittest.main()
