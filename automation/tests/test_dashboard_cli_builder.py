from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.cli_builder import (
    DashboardRunOptions,
    build_crawler_command,
    resolve_records_output_path,
)


class DashboardCommandBuilderTests(unittest.TestCase):
    def test_build_command_with_profile_and_resume(self) -> None:
        options = DashboardRunOptions(
            start_url="https://example.com/questions",
            profile_path=str((PROJECT_ROOT / "profiles" / "examtopics_like.yaml").resolve()),
            resume=True,
            headless=True,
            prompt_for_login_at_start=True,
            enable_auto_login=True,
            auth_file_path="profiles/auth_hosts.yaml",
            auto_login_timeout_seconds=55,
            selector_debug=True,
            require_answers=True,
            stop_on_missing_answers=True,
            auto_learn_profiles=True,
            max_records=150,
            max_turns=500,
            start_index=3,
            min_confidence=0.7,
            min_quality_score=0.8,
            model="gpt-5",
            records_output_name="records.jsonl",
        )

        command = build_crawler_command(PROJECT_ROOT, options)

        self.assertIn(str((PROJECT_ROOT / "main.py").resolve()), command)
        self.assertNotIn("run", command)
        self.assertIn("--start-url", command)
        self.assertIn("https://example.com/questions", command)
        self.assertIn("--profile", command)
        self.assertIn(options.profile_path, command)
        self.assertIn("--resume", command)
        self.assertIn("--headless", command)
        self.assertIn("--prompt-for-login-at-start", command)
        self.assertIn("--auto-login", command)
        self.assertIn("--auth-file", command)
        self.assertIn("profiles/auth_hosts.yaml", command)
        self.assertIn("--auto-login-timeout-seconds", command)
        self.assertIn("55", command)
        self.assertIn("--selector-debug", command)
        self.assertIn("--require-answers", command)
        self.assertIn("--stop-on-missing-answers", command)
        self.assertIn("--auto-learn-profiles", command)
        self.assertIn("--output", command)

        output_value = command[command.index("--output") + 1]
        self.assertEqual(output_value, str(resolve_records_output_path(PROJECT_ROOT, "records.jsonl")))

    def test_build_command_without_profile(self) -> None:
        options = DashboardRunOptions(
            start_url="https://example.com/questions",
            profile_path=None,
            resume=False,
            headless=False,
            prompt_for_login_at_start=False,
            enable_auto_login=False,
            auth_file_path="profiles/auth_hosts.yaml",
            auto_login_timeout_seconds=40,
            selector_debug=False,
            require_answers=False,
            stop_on_missing_answers=False,
            auto_learn_profiles=False,
            records_output_name="records.jsonl",
        )

        command = build_crawler_command(PROJECT_ROOT, options)

        self.assertNotIn("--profile", command)
        self.assertIn("--no-resume", command)
        self.assertIn("--no-headless", command)
        self.assertIn("--no-prompt-for-login-at-start", command)
        self.assertIn("--no-auto-login", command)
        self.assertIn("--auth-file", command)
        self.assertIn("profiles/auth_hosts.yaml", command)
        self.assertIn("--auto-login-timeout-seconds", command)
        self.assertIn("40", command)
        self.assertIn("--no-selector-debug", command)
        self.assertIn("--allow-missing-answers", command)
        self.assertIn("--continue-on-missing-answers", command)
        self.assertIn("--no-auto-learn-profiles", command)

    def test_records_json_name_maps_to_jsonl_output_path(self) -> None:
        resolved = resolve_records_output_path(PROJECT_ROOT, "records.json")
        self.assertTrue(str(resolved).endswith(str(Path("output") / "records.jsonl")))


if __name__ == "__main__":
    unittest.main()
