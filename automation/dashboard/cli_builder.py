from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(slots=True)
class DashboardRunOptions:
    start_url: str
    profile_path: str | None = None
    orchestration_mode: str = "hybrid_gap_fill"
    resume: bool = False
    headless: bool = False
    max_records: int = 1000
    max_turns: int = 800
    start_index: int = 1
    min_confidence: float = 0.65
    min_quality_score: float = 0.72
    require_answers: bool = True
    stop_on_missing_answers: bool = False
    auto_learn_profiles: bool = True
    selector_debug: bool = False
    model: str = "gpt-5"
    prompt_for_login_at_start: bool = False
    enable_auto_login: bool = False
    auth_file_path: str = "auth/auth_hosts.yaml"
    auto_login_timeout_seconds: int = 40
    humanize: bool = False
    records_output_name: str = "records.jsonl"


def normalize_records_output_name(name: str) -> str:
    base_name = Path((name or "").strip()).name
    if not base_name:
        return "records.jsonl"

    candidate = Path(base_name)
    suffix = candidate.suffix.lower()
    if suffix == ".jsonl":
        return candidate.name
    if suffix == ".json":
        return candidate.with_suffix(".jsonl").name
    if suffix:
        return candidate.with_suffix(".jsonl").name
    return f"{candidate.name}.jsonl"


def resolve_records_output_path(automation_dir: Path, name: str) -> Path:
    normalized = normalize_records_output_name(name)
    return (automation_dir / "output" / normalized).resolve()


def build_crawler_command(automation_dir: Path, options: DashboardRunOptions) -> list[str]:
    """Build the CLI command while keeping main.py as the execution engine."""
    records_output_path = resolve_records_output_path(automation_dir, options.records_output_name)

    command = [
        sys.executable,
        str((automation_dir / "main.py").resolve()),
        "--start-url",
        options.start_url,
        "--output",
        str(records_output_path),
        "--model",
        options.model,
        "--orchestration-mode",
        options.orchestration_mode,
        "--max-records",
        str(options.max_records),
        "--max-turns",
        str(options.max_turns),
        "--start-index",
        str(options.start_index),
        "--min-confidence",
        str(options.min_confidence),
        "--min-quality-score",
        str(options.min_quality_score),
        "--headless" if options.headless else "--no-headless",
        "--resume" if options.resume else "--no-resume",
        (
            "--prompt-for-login-at-start"
            if options.prompt_for_login_at_start
            else "--no-prompt-for-login-at-start"
        ),
        "--auto-login" if options.enable_auto_login else "--no-auto-login",
        "--auth-file",
        options.auth_file_path,
        "--auto-login-timeout-seconds",
        str(options.auto_login_timeout_seconds),
        "--humanize" if options.humanize else "--no-humanize",
        "--require-answers" if options.require_answers else "--allow-missing-answers",
        (
            "--stop-on-missing-answers"
            if options.stop_on_missing_answers
            else "--continue-on-missing-answers"
        ),
        "--auto-learn-profiles" if options.auto_learn_profiles else "--no-auto-learn-profiles",
        "--selector-debug" if options.selector_debug else "--no-selector-debug",
    ]

    if options.profile_path:
        command.extend(["--profile", options.profile_path])

    return command
