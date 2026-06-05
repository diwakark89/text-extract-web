from __future__ import annotations

from pathlib import Path
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
    domain_profiles_dir: Path = Path("profiles/domains")
    output_path: Path = Path("output/records.jsonl")
    error_path: Path = Path("output/errors.jsonl")
    debug_output_path: Path = Path("output/selector_debug.jsonl")
    checkpoint_path: Path = Path("output/checkpoint.json")
    screenshot_dir: Path = Path("output/screenshots")
    workspace_dir: Path = Path(".")
    max_records: int = 1000
    expected_count: int | None = Field(default=None, ge=1)
    max_turns: int = 800
    max_page_candidates: int = 80
    start_index: int = 1
    min_confidence: float = 0.65
    min_quality_score: float = 0.72
    require_answers: bool = True
    stop_on_missing_answers: bool = False
    resume: bool = False
    auto_learn_profiles: bool = True
    max_consecutive_failures: int = 3
    navigation_retry_limit: int = 2
    questions_per_file: int = Field(default=300, ge=1)
    selector_debug: bool = False
    headless: bool = False
    slow_mo_ms: int = 0
    prompt_for_login_at_start: bool = False
    enable_auto_login: bool = False
    auth_file_path: Path = Path("auth/auth_hosts.yaml")
    auto_login_timeout_seconds: int = 40
    humanize: bool = False
    human_delay_min_ms: int = 80
    human_delay_max_ms: int = 360
    human_read_pause_min_ms: int = 220
    human_read_pause_max_ms: int = 850
    human_idle_break_chance: float = 0.06
    human_idle_break_min_ms: int = 650
    human_idle_break_max_ms: int = 1500
    human_mouse_move: bool = True


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
