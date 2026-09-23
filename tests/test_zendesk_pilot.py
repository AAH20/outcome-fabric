import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.bridge import build as build_bridge
from outcome_fabric.zendesk_fetch import collect
from outcome_fabric.zendesk_intake import verify as verify_intake
from outcome_fabric.zendesk_pilot import assemble


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/zendesk-intake"


class ZendeskPilotTests(unittest.TestCase):
    def setup_case(self, directory):
        root = Path(directory)
        collection = root / "collection"
        responses = [(FIXTURE / "page-0.json").read_bytes(), (FIXTURE / "page-1.json").read_bytes()]
        def transport(url, token):
            return responses.pop(0)
        # The first saved fixture page needs a cursor for the live collector.
        first = json.loads(responses[0])
        first["after_url"] = "https://demo.zendesk.com/api/v2/incremental/tickets/cursor.json?cursor=next"
        responses[0] = json.dumps(first).encode()
        collect("demo", 1, collection, "test-token", transport)
        sidecars = root / "sidecars"
        sidecars.mkdir()
        original = json.loads((FIXTURE / "intake.json").read_text())
        pilot = {key: original[key] for key in ("schema_version", "tenant_id", "passport_id", "subject", "protocol")}
        for name in ("cohort", "decisions", "costs"):
            path = sidecars / f"{name}.csv"
            path.write_bytes((FIXTURE / f"{name}.csv").read_bytes())
            pilot[name] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        config = sidecars / "pilot.json"
        config.write_text(json.dumps(pilot))
        return collection, config

    def test_live_snapshot_to_offline_bridge_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            collection, config = self.setup_case(directory)
            output = Path(directory) / "pilot"
            result = assemble(collection, config, output)
            self.assertEqual(result["evidence_class"], "CUSTOMER_SUPPLIED_UNVERIFIED")
            self.assertEqual(result["eligible_cohort_cases"], 3)
            self.assertTrue(verify_intake(output / "intake.json", output / "derived")["valid"])
            package = build_bridge(output / "derived/manifest.json")
            self.assertEqual(package["passport"]["metrics"]["candidate"]["accepted_cases"], 1)
            self.assertNotIn("Synthetic billing question", (output / "page-0000.json").read_text())
            with self.assertRaisesRegex(ValueError, "already exists"):
                assemble(collection, config, output)

    def test_collection_tampering_blocks_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            collection, config = self.setup_case(directory)
            (collection / "page-0000.json").write_text("{}")
            output = Path(directory) / "pilot"
            with self.assertRaisesRegex(ValueError, "locked SHA-256"):
                assemble(collection, config, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
