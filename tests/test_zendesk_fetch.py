import json
import tempfile
import unittest
from pathlib import Path

from outcome_fabric.zendesk_fetch import collect


class ZendeskFetchTests(unittest.TestCase):
    def test_bounded_read_only_collection_drops_ticket_content(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private"
            calls = []
            def transport(url, token):
                calls.append((url, token))
                if len(calls) == 1:
                    return json.dumps({"tickets": [{"id": 101, "status": "solved", "updated_at": "2026-09-01T00:00:00Z",
                                                     "subject": "Sensitive ticket subject", "description": "Sensitive detail"}],
                                       "end_of_stream": False,
                                       "after_url": "https://demo.zendesk.com/api/v2/incremental/tickets/cursor.json?cursor=abc"}).encode()
                return json.dumps({"tickets": [{"id": 202, "status": "closed", "updated_at": "2026-09-02T00:00:00Z"}],
                                   "end_of_stream": True}).encode()
            receipt = collect("demo", 1, output, "secret-test-token", transport)
            self.assertEqual(len(receipt["pages"]), 2)
            self.assertTrue(receipt["end_of_stream"])
            self.assertEqual(len(calls), 2)
            self.assertEqual({token for _, token in calls}, {"secret-test-token"})
            self.assertNotIn("secret-test-token", (output / "collection-receipt.json").read_text())
            self.assertNotIn("Sensitive", (output / "page-0000.json").read_text())
            self.assertEqual(json.loads((output / "page-0000.json").read_text())["tickets"][0]["id"], 101)
            with self.assertRaisesRegex(ValueError, "already exists"):
                collect("demo", 1, output, "secret-test-token", transport)

    def test_cross_origin_cursor_fails_before_second_request(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private"
            calls = []
            def transport(url, token):
                calls.append(url)
                return json.dumps({"tickets": [], "end_of_stream": False,
                                   "after_url": "https://evil.example/api/v2/incremental/tickets/cursor.json?cursor=abc"}).encode()
            with self.assertRaisesRegex(ValueError, "outside the exact"):
                collect("demo", 1, output, "secret-test-token", transport)
            self.assertEqual(len(calls), 1)
            self.assertFalse(output.exists())

    def test_missing_token_and_incomplete_page_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private"
            with self.assertRaisesRegex(ValueError, "token"):
                collect("demo", 1, output, "")
            def transport(url, token):
                return json.dumps({"tickets": [], "end_of_stream": False}).encode()
            with self.assertRaisesRegex(ValueError, "no next cursor"):
                collect("demo", 1, output, "secret-test-token", transport)
            self.assertFalse(output.exists())

    def test_repeated_cursor_and_oversized_response_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "private"
            def repeated(url, token):
                return json.dumps({"tickets": [], "end_of_stream": False, "after_url": url}).encode()
            with self.assertRaisesRegex(ValueError, "repeated"):
                collect("demo", 1, output, "secret-test-token", repeated)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "bounded"):
                collect("demo", 1, output, "secret-test-token", lambda url, token: b"x" * 10_000_001)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
