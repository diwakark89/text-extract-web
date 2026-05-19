from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field

from .models import SelectorProfile


DEFAULT_SELECTOR_PROFILE = SelectorProfile(
    question_containers=[
        "[role='tabpanel']",
        ".tab-pane.active",
        ".panel-body",
    ],
    question=[
        "p.lead",
        ".question",
        ".question-text",
        "[class*='question'] p",
    ],
    options=[
        "ol.ui-selectable > li",
        "ol.rounded-list > li",
        "ol.rounded-list-multi > li",
        "ul > li",
        ".option",
        ".ui-selectee",
    ],
    answer=[
        "div[id^='answerQ'] > p",
        ".answer",
        ".correct-answer",
        "[class*='answer'] p",
    ],
    show_answer_buttons=[
        "a[data-toggle='collapse'][href*='answerQ']",
        "button[data-toggle='collapse'][data-target*='answerQ']",
        "button.show-answer",
        "a.show-answer",
    ],
    next_buttons=[
        "a[href*='collapse_']",
        "button[aria-controls*='collapse_']",
        "a:has-text('Next Question')",
        "button:has-text('Next')",
        "a:has-text('Next')",
    ],
)


class RunConfig(BaseModel):
    start_url: str
    profile_path: Path | None = None
    domain_profiles_dir: Path = Path("automation/profiles/domains")
    output_path: Path = Path("automation/output/records.jsonl")
    error_path: Path = Path("automation/output/errors.jsonl")
    debug_output_path: Path = Path("automation/output/selector_debug.jsonl")
    checkpoint_path: Path = Path("automation/output/checkpoint.json")
    screenshot_dir: Path = Path("automation/output/screenshots")
    workspace_dir: Path = Path("automation")
    model: str = "gpt-5"
    orchestration_mode: Literal["hybrid_gap_fill", "llm_orchestrator", "deterministic_only"] = "hybrid_gap_fill"
    max_records: int = 200
    max_turns: int = 800
    start_index: int = 1
    min_confidence: float = 0.65
    min_quality_score: float = 0.72
    require_answers: bool = True
    resume: bool = False
    auto_learn_profiles: bool = True
    max_consecutive_failures: int = 3
    navigation_retry_limit: int = 2
    max_llm_assists_per_page: int = 1
    selector_debug: bool = False
    headless: bool = False
    slow_mo_ms: int = 0
    prompt_for_login_at_start: bool = False


def domain_from_url(url: str) -> str:
    netloc = (urlparse(url).netloc or "").strip().lower()
    if not netloc:
        return "default"
    return netloc.replace(":", "_")


def load_selector_profile(profile_path: Path | None) -> SelectorProfile:
    if profile_path is None:
        return SelectorProfile.model_validate(DEFAULT_SELECTOR_PROFILE.model_dump())

    if not profile_path.exists():
        raise FileNotFoundError(f"Selector profile not found: {profile_path}")

    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    merged = DEFAULT_SELECTOR_PROFILE.model_dump()
    for key in merged:
        if key in raw and raw[key] is not None:
            value = raw[key]
            if isinstance(value, str):
                merged[key] = [value]
            elif isinstance(value, list):
                merged[key] = [str(item).strip() for item in value if str(item).strip()]

    return SelectorProfile.model_validate(merged)
