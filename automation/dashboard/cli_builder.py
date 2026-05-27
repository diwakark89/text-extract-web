from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys


@dataclass(slots=True)
class DashboardRunOptions:
    start_url: str
    profile_path: str | None = None
    orchestration_mode: str = "hybrid_gap_fill"
    resume: bool = False
    headless: bool = False
    max_records: int = 1000
    questions_per_file: int = 300
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


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _python_can_import_typer(python_command: str) -> bool:
    try:
        completed = subprocess.run(
            [python_command, "-c", "import typer"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=4,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return completed.returncode == 0


def resolve_python_executable(automation_dir: Path) -> str:
    """Pick a Python interpreter that has the crawler runtime dependencies."""
    explicit = os.getenv("MCQ_CRAWLER_PYTHON", "").strip()

    candidates: list[str] = []
    if explicit:
        explicit_path = Path(explicit).expanduser()
        candidates.append(str(explicit_path.resolve()) if explicit_path.exists() else explicit)

    candidates.append(str(_venv_python_path(automation_dir / ".venv").resolve()))
    candidates.append(str(_venv_python_path(automation_dir.parent / ".venv").resolve()))

    active_virtual_env = os.getenv("VIRTUAL_ENV", "").strip()
    if active_virtual_env:
        candidates.append(str(_venv_python_path(Path(active_virtual_env).expanduser()).resolve()))

    candidates.append(sys.executable)

    deduped_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower() if os.name == "nt" else candidate
        if key in seen:
            continue
        seen.add(key)
        deduped_candidates.append(candidate)

    for candidate in deduped_candidates:
        if _python_can_import_typer(candidate):
            return candidate

    return deduped_candidates[-1]


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
    python_executable = resolve_python_executable(automation_dir)

    command = [
        python_executable,
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
        "--questions-per-file",
        str(options.questions_per_file),
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
