from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.file_views import (
    list_yaml_profiles,
    load_profile_for_url,
    load_recent_urls,
    read_checkpoint,
    read_jsonl_tail,
    resolve_latest_records_jsonl_path,
    save_profile_for_url,
    save_recent_url,
    url_host_key,
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

    def test_recent_url_save_and_load_collapses_same_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_recent_url(output_dir, "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/")
            save_recent_url(output_dir, "https://examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/2/")
            save_recent_url(output_dir, "https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-2")

            urls = load_recent_urls(output_dir)

            self.assertEqual(len(urls), 2)
            self.assertEqual(
                urls[0],
                "https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-2",
            )
            self.assertEqual(
                urls[1],
                "https://examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/2/",
            )

    def test_profile_mapping_is_reused_for_same_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            profile_path = "C:/profiles/examtopics_like.yaml"
            url_one = "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/"
            url_two = "https://examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/2/"

            save_profile_for_url(output_dir, url_one, profile_path)

            self.assertEqual(load_profile_for_url(output_dir, url_two), profile_path)

            save_profile_for_url(output_dir, url_two, None)
            self.assertIsNone(load_profile_for_url(output_dir, url_one))

    def test_legacy_recent_urls_list_is_migrated_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            file_path = output_dir / "dashboard_recent_urls.json"
            file_path.write_text(
                json.dumps(
                    [
                        "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
                        "https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-2",
                    ],
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            urls = load_recent_urls(output_dir)
            self.assertEqual(len(urls), 2)

            save_profile_for_url(
                output_dir,
                "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
                "C:/profiles/examtopics_like.yaml",
            )

            migrated = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertIsInstance(migrated, dict)
            self.assertIn("recent_sites", migrated)
            self.assertIn("profile_by_host", migrated)
            self.assertEqual(
                migrated["profile_by_host"].get("examtopics.com"),
                "C:/profiles/examtopics_like.yaml",
            )

    def test_moved_recent_urls_file_fallback_from_output_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            moved_file = root / "dashboard_recent_urls.json"
            moved_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "recent_sites": [
                            {
                                "host": "examcademy.com",
                                "last_url": "https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1",
                            }
                        ],
                        "profile_by_host": {},
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            urls = load_recent_urls(output_dir)
            self.assertEqual(
                urls[0],
                "https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1",
            )

    def test_recent_urls_env_override_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            custom_path = root / "custom" / "recent_urls.json"

            with mock.patch.dict(os.environ, {"MCQ_DASHBOARD_RECENT_URLS_PATH": str(custom_path)}):
                save_recent_url(output_dir, "https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1")
                urls = load_recent_urls(output_dir)

            self.assertTrue(custom_path.exists())
            self.assertEqual(
                urls[0],
                "https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1",
            )

    def test_url_host_key_normalization(self) -> None:
        self.assertEqual(url_host_key("https://www.Example.com:8443/path"), "example.com")
        self.assertEqual(url_host_key("example.com/path"), "example.com")
        self.assertEqual(url_host_key("   "), "")

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

    def test_resolve_latest_records_path_prefers_base_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            base_path = output_dir / "records.jsonl"
            base_path.write_text('{"index": 1}\n', encoding="utf-8")
            (output_dir / "records_1.jsonl").write_text('{"index": 1}\n', encoding="utf-8")
            (output_dir / "records_2.jsonl").write_text('{"index": 2}\n', encoding="utf-8")

            resolved = resolve_latest_records_jsonl_path(base_path)

            self.assertEqual(resolved, base_path)

    def test_resolve_latest_records_path_uses_highest_split_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            base_path = output_dir / "records.jsonl"
            (output_dir / "records_1.jsonl").write_text('{"index": 1}\n', encoding="utf-8")
            (output_dir / "records_2.jsonl").write_text('{"index": 2}\n', encoding="utf-8")
            (output_dir / "records_alpha.jsonl").write_text('{"index": 99}\n', encoding="utf-8")

            resolved = resolve_latest_records_jsonl_path(base_path)

            self.assertEqual(resolved, output_dir / "records_2.jsonl")


if __name__ == "__main__":
    unittest.main()
