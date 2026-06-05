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


def _records_json_path(root: Path, name: str) -> Path:
    return root / "records" / name


def _build_record(index: int) -> MCQRecord:
    return MCQRecord(
        index=index,
        question=f"Q{index}",
        options={"A": "Option A", "B": "Option B"},
        correct_answers=["A"],
        source_url=f"https://example.com/q{index}",
        confidence=0.9,
        quality_score=0.9,
        fingerprint=f"fp-{index}",
    )


class SelectorDebugStorageTests(unittest.TestCase):
    def test_append_debug_event_writes_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
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

    def test_records_and_errors_json_outputs_are_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
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

            records_json = json.loads(_records_json_path(root, "records_01.json").read_text(encoding="utf-8"))
            errors_json = json.loads((root / "errors.json").read_text(encoding="utf-8"))

            self.assertIsInstance(records_json, list)
            self.assertEqual(records_json[0]["question"], "Which service is object storage?")
            self.assertIsInstance(errors_json, list)
            self.assertEqual(errors_json[0]["reason"], "validation_failed")

    def test_records_chunk_appends_multiple_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            store.append_record(_build_record(1))
            store.append_record(_build_record(2))

            records_json = json.loads(_records_json_path(root, "records_01.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records_json), 2)
            self.assertEqual(records_json[0]["question"], "Q1")
            self.assertEqual(records_json[1]["question"], "Q2")

    def test_error_json_mirror_recovers_from_invalid_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
            )

            (root / "errors.json").write_text("not-valid-json", encoding="utf-8")
            store.append_error({"reason": "timeout"})

            errors_json = json.loads((root / "errors.json").read_text(encoding="utf-8"))
            self.assertEqual(len(errors_json), 1)
            self.assertEqual(errors_json[0]["reason"], "timeout")

    def test_legacy_base_records_json_is_migrated_to_first_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            records_dir = root / "records"
            records_dir.mkdir(parents=True, exist_ok=True)
            (records_dir / "records.json").write_text(
                json.dumps([{"index": 1, "question": "Legacy Q1"}], ensure_ascii=True),
                encoding="utf-8",
            )

            store = JsonlStore(
                output_path=records_dir / "records.json",
                error_path=root / "errors.jsonl",
            )
            store.append_record(_build_record(2))

            self.assertFalse((records_dir / "records.json").exists())
            migrated = json.loads(_records_json_path(root, "records_01.json").read_text(encoding="utf-8"))
            self.assertEqual(len(migrated), 2)
            self.assertEqual(migrated[0]["question"], "Legacy Q1")
            self.assertEqual(migrated[1]["question"], "Q2")


class SplitRecordsStorageTests(unittest.TestCase):
    def test_under_limit_writes_first_numbered_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
                questions_per_file=3,
            )

            for index in range(1, 4):
                store.append_record(_build_record(index))

            self.assertTrue(_records_json_path(root, "records_01.json").exists())
            self.assertFalse(_records_json_path(root, "records.json").exists())
            self.assertFalse(_records_json_path(root, "records_02.json").exists())

            records_json = json.loads(_records_json_path(root, "records_01.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records_json), 3)

    def test_crossing_limit_creates_numbered_records_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
                error_path=root / "errors.jsonl",
                debug_path=root / "selector_debug.jsonl",
                questions_per_file=3,
            )

            for index in range(1, 6):
                store.append_record(_build_record(index))

            self.assertFalse(_records_json_path(root, "records.json").exists())
            self.assertTrue(_records_json_path(root, "records_01.json").exists())
            self.assertTrue(_records_json_path(root, "records_02.json").exists())

            first_json = json.loads(_records_json_path(root, "records_01.json").read_text(encoding="utf-8"))
            second_json = json.loads(_records_json_path(root, "records_02.json").read_text(encoding="utf-8"))
            self.assertEqual(len(first_json), 3)
            self.assertEqual(len(second_json), 2)

    def test_resume_offset_continues_writing_in_expected_split_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_path = root / "records" / "records.json"
            error_path = root / "errors.jsonl"

            initial_store = JsonlStore(
                output_path=output_path,
                error_path=error_path,
                questions_per_file=3,
            )
            for index in range(1, 6):
                initial_store.append_record(_build_record(index))

            resumed_store = JsonlStore(
                output_path=output_path,
                error_path=error_path,
                questions_per_file=3,
                records_written=5,
            )
            resumed_store.append_record(_build_record(6))
            resumed_store.append_record(_build_record(7))

            second_json = json.loads(_records_json_path(root, "records_02.json").read_text(encoding="utf-8"))
            third_json = json.loads(_records_json_path(root, "records_03.json").read_text(encoding="utf-8"))
            self.assertEqual(len(second_json), 3)
            self.assertEqual(len(third_json), 1)

    def test_errors_remain_unsplit_when_records_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JsonlStore(
                output_path=root / "records" / "records.json",
                error_path=root / "errors.jsonl",
                questions_per_file=2,
            )

            for index in range(1, 4):
                store.append_record(_build_record(index))

            store.append_error({"reason": "validation_failed", "index": 1})
            store.append_error({"reason": "parse_error", "index": 2})

            self.assertTrue(_records_json_path(root, "records_01.json").exists())
            self.assertTrue(_records_json_path(root, "records_02.json").exists())
            self.assertTrue((root / "errors.jsonl").exists())
            self.assertFalse((root / "errors_1.jsonl").exists())

            errors_json = json.loads((root / "errors.json").read_text(encoding="utf-8"))
            self.assertEqual(len(errors_json), 2)


if __name__ == "__main__":
    unittest.main()
