from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.cli_builder import DashboardRunOptions, build_crawler_command


class DashboardCommandBuilderTests(unittest.TestCase):
    def test_build_command_with_profile_and_resume(self) -> None:
        options = DashboardRunOptions(
            start_url="https://example.com/questions",
            profile_path=str((PROJECT_ROOT / "profiles" / "examtopics_like.yaml").resolve()),
            resume=True,
            headless=True,
            prompt_for_login_at_start=True,
            selector_debug=True,
            require_answers=True,
            auto_learn_profiles=True,
            max_records=150,
            max_turns=500,
            start_index=3,
            min_confidence=0.7,
            min_quality_score=0.8,
            model="gpt-5",
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
        self.assertIn("--selector-debug", command)
        self.assertIn("--require-answers", command)
        self.assertIn("--auto-learn-profiles", command)

    def test_build_command_without_profile(self) -> None:
        options = DashboardRunOptions(
            start_url="https://example.com/questions",
            profile_path=None,
            resume=False,
            headless=False,
            prompt_for_login_at_start=False,
            selector_debug=False,
            require_answers=False,
            auto_learn_profiles=False,
        )

        command = build_crawler_command(PROJECT_ROOT, options)

        self.assertNotIn("--profile", command)
        self.assertIn("--no-resume", command)
        self.assertIn("--no-headless", command)
        self.assertIn("--no-prompt-for-login-at-start", command)
        self.assertIn("--no-selector-debug", command)
        self.assertIn("--allow-missing-answers", command)
        self.assertIn("--no-auto-learn-profiles", command)


if __name__ == "__main__":
    unittest.main()
