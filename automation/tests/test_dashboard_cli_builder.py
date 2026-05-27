from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
import sys
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.cli_builder import (
    DashboardRunOptions,
    build_crawler_command,
    resolve_python_executable,
    resolve_records_output_path,
)


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


class DashboardCommandBuilderTests(unittest.TestCase):
    def test_build_command_uses_resolved_python_executable(self) -> None:
        options = DashboardRunOptions(start_url="https://example.com/questions")

        with mock.patch("dashboard.cli_builder.resolve_python_executable", return_value="python-custom"):
            command = build_crawler_command(PROJECT_ROOT, options)

        self.assertEqual(command[0], "python-custom")

    def test_build_command_with_profile_and_resume(self) -> None:
        options = DashboardRunOptions(
            start_url="https://example.com/questions",
            profile_path=str((PROJECT_ROOT / "profiles" / "examtopics_like.yaml").resolve()),
            resume=True,
            headless=True,
            prompt_for_login_at_start=True,
            enable_auto_login=True,
            auth_file_path="auth/auth_hosts.yaml",
            auto_login_timeout_seconds=55,
            humanize=True,
            selector_debug=True,
            require_answers=True,
            stop_on_missing_answers=True,
            auto_learn_profiles=True,
            max_records=150,
            questions_per_file=250,
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
        self.assertIn("auth/auth_hosts.yaml", command)
        self.assertIn("--auto-login-timeout-seconds", command)
        self.assertIn("55", command)
        self.assertIn("--humanize", command)
        self.assertIn("--selector-debug", command)
        self.assertIn("--require-answers", command)
        self.assertIn("--stop-on-missing-answers", command)
        self.assertIn("--auto-learn-profiles", command)
        self.assertIn("--output", command)
        self.assertIn("--questions-per-file", command)
        self.assertIn("250", command)

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
            auth_file_path="auth/auth_hosts.yaml",
            auto_login_timeout_seconds=40,
            humanize=False,
            selector_debug=False,
            require_answers=False,
            stop_on_missing_answers=False,
            auto_learn_profiles=False,
            records_output_name="records.jsonl",
            questions_per_file=300,
        )

        command = build_crawler_command(PROJECT_ROOT, options)

        self.assertNotIn("--profile", command)
        self.assertIn("--no-resume", command)
        self.assertIn("--no-headless", command)
        self.assertIn("--no-prompt-for-login-at-start", command)
        self.assertIn("--no-auto-login", command)
        self.assertIn("--auth-file", command)
        self.assertIn("auth/auth_hosts.yaml", command)
        self.assertIn("--auto-login-timeout-seconds", command)
        self.assertIn("40", command)
        self.assertIn("--no-humanize", command)
        self.assertIn("--no-selector-debug", command)
        self.assertIn("--allow-missing-answers", command)
        self.assertIn("--continue-on-missing-answers", command)
        self.assertIn("--no-auto-learn-profiles", command)
        self.assertIn("--questions-per-file", command)
        self.assertIn("300", command)

    def test_records_json_name_maps_to_jsonl_output_path(self) -> None:
        resolved = resolve_records_output_path(PROJECT_ROOT, "records.json")
        self.assertTrue(str(resolved).endswith(str(Path("output") / "records.jsonl")))

    def test_resolve_python_executable_prefers_workspace_repo_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            automation_dir = workspace_root / "automation"
            automation_dir.mkdir(parents=True)

            repo_venv_python = _venv_python_path(workspace_root / ".venv")
            repo_venv_python.parent.mkdir(parents=True)
            repo_venv_python.write_text("", encoding="utf-8")

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "dashboard.cli_builder._python_can_import_typer",
                    side_effect=lambda candidate: candidate == str(repo_venv_python.resolve()),
                ):
                    resolved = resolve_python_executable(automation_dir)

        self.assertEqual(resolved, str(repo_venv_python.resolve()))

    def test_resolve_python_executable_honors_explicit_override(self) -> None:
        with mock.patch.dict(os.environ, {"MCQ_CRAWLER_PYTHON": "python-override"}, clear=True):
            with mock.patch(
                "dashboard.cli_builder._python_can_import_typer",
                side_effect=lambda candidate: candidate == "python-override",
            ):
                resolved = resolve_python_executable(PROJECT_ROOT)

        self.assertEqual(resolved, "python-override")


if __name__ == "__main__":
    unittest.main()
