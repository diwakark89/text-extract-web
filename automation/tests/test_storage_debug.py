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
from mcq_crawler.models import MCQRecord


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

    def test_records_and_errors_json_mirrors_are_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records.jsonl",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            record = MCQRecord(
                index=1,
                question="Which service is object storage?",
                options={
                    "A": "Amazon EBS",
                    "B": "Amazon S3",
                    "C": "Amazon EFS",
                    "D": "Amazon RDS",
                },
                correct_answers=["B"],
                source_url="https://example.com/q1",
                confidence=0.9,
                quality_score=0.95,
                fingerprint="abc123",
            )
            store.append_record(record)
            store.append_error({"reason": "validation_failed", "question": "bad"})

            records_json = json.loads((root / "records.json").read_text(encoding="utf-8"))
            errors_json = json.loads((root / "errors.json").read_text(encoding="utf-8"))

            self.assertIsInstance(records_json, list)
            self.assertEqual(records_json[0]["question"], "Which service is object storage?")
            self.assertIsInstance(errors_json, list)
            self.assertEqual(errors_json[0]["reason"], "validation_failed")

    def test_records_json_mirror_appends_multiple_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records.jsonl",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            first_record = MCQRecord(
                index=1,
                question="Q1",
                options={"A": "A1", "B": "B1"},
                correct_answers=["A"],
                source_url="https://example.com/q1",
                confidence=0.9,
                quality_score=0.9,
                fingerprint="fp1",
            )
            second_record = MCQRecord(
                index=2,
                question="Q2",
                options={"A": "A2", "B": "B2"},
                correct_answers=["B"],
                source_url="https://example.com/q2",
                confidence=0.9,
                quality_score=0.9,
                fingerprint="fp2",
            )

            store.append_record(first_record)
            store.append_record(second_record)

            records_json = json.loads((root / "records.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records_json), 2)
            self.assertEqual(records_json[0]["question"], "Q1")
            self.assertEqual(records_json[1]["question"], "Q2")

    def test_error_json_mirror_recovers_from_invalid_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records.jsonl",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            (root / "errors.json").write_text("not-valid-json", encoding="utf-8")
            store.append_error({"reason": "timeout"})

            errors_json = json.loads((root / "errors.json").read_text(encoding="utf-8"))
            self.assertEqual(len(errors_json), 1)
            self.assertEqual(errors_json[0]["reason"], "timeout")


if __name__ == "__main__":
    unittest.main()
