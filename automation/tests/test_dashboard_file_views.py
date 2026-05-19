from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.file_views import (
    list_yaml_profiles,
    load_recent_urls,
    read_checkpoint,
    read_jsonl_tail,
    save_recent_url,
)


class DashboardFileViewTests(unittest.TestCase):
    def test_read_jsonl_tail_handles_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"index": 1, "question": "Q1"}),
                        "{bad-json",
                        json.dumps({"index": 2, "question": "Q2"}),
                    ],
                ),
                encoding="utf-8",
            )

            rows = read_jsonl_tail(path, max_lines=10)

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["index"], 1)
            self.assertEqual(rows[1]["_parse_error"], "invalid_jsonl")
            self.assertEqual(rows[2]["index"], 2)

    def test_checkpoint_reader_handles_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "checkpoint.json"
            path.write_text("not-json", encoding="utf-8")

            checkpoint = read_checkpoint(path)

            self.assertEqual(checkpoint.get("_parse_error"), "invalid_json")

    def test_recent_url_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_recent_url(output_dir, "https://one.example")
            save_recent_url(output_dir, "https://two.example")
            save_recent_url(output_dir, "https://one.example")

            urls = load_recent_urls(output_dir)

            self.assertEqual(urls[0], "https://one.example")
            self.assertEqual(urls[1], "https://two.example")

    def test_list_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "profiles"
            learned = base / "domains"
            base.mkdir(parents=True, exist_ok=True)
            learned.mkdir(parents=True, exist_ok=True)

            (base / "default.yaml").write_text("question: []\n", encoding="utf-8")
            (learned / "example.com.yaml").write_text("question: []\n", encoding="utf-8")

            base_profiles, learned_profiles = list_yaml_profiles(
                base,
                learned,
                workspace_root=root,
            )

            self.assertEqual(len(base_profiles), 1)
            self.assertEqual(len(learned_profiles), 1)
            self.assertIsInstance(base_profiles[0], Path)
            self.assertIsInstance(learned_profiles[0], Path)


if __name__ == "__main__":
    unittest.main()
