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
    max_records: int = 200
    max_turns: int = 800
    start_index: int = 1
    min_confidence: float = 0.65
    min_quality_score: float = 0.72
    require_answers: bool = True
    auto_learn_profiles: bool = True
    selector_debug: bool = False
    model: str = "gpt-5"


def build_crawler_command(automation_dir: Path, options: DashboardRunOptions) -> list[str]:
    """Build the CLI command while keeping main.py as the execution engine."""
    command = [
        sys.executable,
        str((automation_dir / "main.py").resolve()),
        "--start-url",
        options.start_url,
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
        "--require-answers" if options.require_answers else "--allow-missing-answers",
        "--auto-learn-profiles" if options.auto_learn_profiles else "--no-auto-learn-profiles",
        "--selector-debug" if options.selector_debug else "--no-selector-debug",
    ]

    if options.profile_path:
        command.extend(["--profile", options.profile_path])

    return command
