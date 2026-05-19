from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.storage import JsonlStore


class SelectorDebugStorageTests(unittest.TestCase):
    def test_append_debug_event_writes_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records.jsonl",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            payload = {
                "event": "record_saved",
                "index": 1,
                "used_selectors": {
                    "question": "p.lead",
                    "options": "ol > li",
                    "answer": "div[id^='answerQ'] > p",
                },
            }
            store.append_debug_event(payload)

            lines = (root / "selector_debug.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["event"], "record_saved")
            self.assertEqual(parsed["used_selectors"]["question"], "p.lead")


if __name__ == "__main__":
    unittest.main()
