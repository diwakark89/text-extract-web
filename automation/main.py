from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from mcq_crawler import RunConfig, run_crawl

app = typer.Typer(help="Copilot SDK + Playwright MCQ crawler")
console = Console()


@app.command()
def run(
    start_url: str = typer.Option(..., help="Start page URL"),
    profile: Path | None = typer.Option(None, help="Path to selectors profile YAML"),
    domain_profiles_dir: Path = typer.Option(Path("profiles/domains"), help="Per-domain learned profiles directory"),
    output: Path = typer.Option(Path("output/records.jsonl"), help="Output JSONL path"),
    errors: Path = typer.Option(Path("output/errors.jsonl"), help="Error JSONL path"),
    debug_output: Path = typer.Option(Path("output/selector_debug.jsonl"), help="Selector debug JSONL path"),
    checkpoint: Path = typer.Option(Path("output/checkpoint.json"), help="Checkpoint file path"),
    screenshots: Path = typer.Option(Path("output/screenshots"), help="Screenshot directory"),
    model: str = typer.Option("gpt-5", help="Copilot model name"),
    orchestration_mode: str = typer.Option(
        "hybrid_gap_fill",
        "--orchestration-mode",
        help="Execution mode: hybrid_gap_fill | deterministic_only | llm_orchestrator",
    ),
    max_records: int = typer.Option(200, help="Maximum records to save"),
    max_turns: int = typer.Option(800, help="Maximum controller turns"),
    start_index: int = typer.Option(1, help="Start index for saved records"),
    min_confidence: float = typer.Option(0.65, help="Minimum extraction confidence before stricter intervention"),
    min_quality_score: float = typer.Option(0.72, help="Minimum quality score required to persist records"),
    require_answers: bool = typer.Option(True, "--require-answers/--allow-missing-answers", help="Require at least one valid answer per record"),
    stop_on_missing_answers: bool = typer.Option(
        True,
        "--stop-on-missing-answers/--continue-on-missing-answers",
        help="Stop run when answers are required but extraction cannot produce valid answer choices",
    ),
    resume: bool = typer.Option(False, "--resume/--no-resume", help="Resume from checkpoint if available"),
    auto_learn_profiles: bool = typer.Option(True, "--auto-learn-profiles/--no-auto-learn-profiles", help="Persist learned selectors into domain profiles"),
    selector_debug: bool = typer.Option(False, "--selector-debug/--no-selector-debug", help="Write per-question selector match debug logs"),
    max_consecutive_failures: int = typer.Option(3, help="Failures before manual intervention is forced"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser headless"),
    slow_mo_ms: int = typer.Option(0, help="Playwright slow motion delay in ms"),
    prompt_for_login_at_start: bool = typer.Option(
        False,
        "--prompt-for-login-at-start/--no-prompt-for-login-at-start",
        help="Pause after opening URL so you can manually log in before crawling",
    ),
    enable_auto_login: bool = typer.Option(
        False,
        "--auto-login/--no-auto-login",
        help="Attempt host-based auto-login from auth file before manual prompt",
    ),
    auth_file: Path = typer.Option(
        Path("profiles/auth_hosts.yaml"),
        "--auth-file",
        help="Path to host credential and selector config YAML",
    ),
    auto_login_timeout_seconds: int = typer.Option(
        40,
        "--auto-login-timeout-seconds",
        help="Timeout in seconds for auto-login steps",
    ),
) -> None:
    config = RunConfig(
        start_url=start_url,
        profile_path=profile,
        domain_profiles_dir=domain_profiles_dir,
        output_path=output,
        error_path=errors,
        debug_output_path=debug_output,
        checkpoint_path=checkpoint,
        screenshot_dir=screenshots,
        model=model,
        orchestration_mode=orchestration_mode,
        max_records=max_records,
        max_turns=max_turns,
        start_index=start_index,
        min_confidence=min_confidence,
        min_quality_score=min_quality_score,
        require_answers=require_answers,
        stop_on_missing_answers=stop_on_missing_answers,
        resume=resume,
        auto_learn_profiles=auto_learn_profiles,
        selector_debug=selector_debug,
        max_consecutive_failures=max_consecutive_failures,
        headless=headless,
        slow_mo_ms=slow_mo_ms,
        prompt_for_login_at_start=prompt_for_login_at_start,
        enable_auto_login=enable_auto_login,
        auth_file_path=auth_file,
        auto_login_timeout_seconds=auto_login_timeout_seconds,
    )

    summary = asyncio.run(run_crawl(config))

    console.print("\n[bold green]Run complete[/bold green]")
    console.print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
