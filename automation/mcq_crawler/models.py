from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SelectorProfile(BaseModel):
    question_containers: list[str] = Field(default_factory=list)
    question: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    answer: list[str] = Field(default_factory=list)
    show_answer_buttons: list[str] = Field(default_factory=list)
    next_buttons: list[str] = Field(default_factory=list)


class ExtractionCandidate(BaseModel):
    question: str = ""
    option_texts: list[str] = Field(default_factory=list)
    answer_text: str = ""
    confidence: float = 0.0
    quality_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    used_selectors: dict[str, str] = Field(default_factory=dict)


class MCQRecord(BaseModel):
    index: int
    question: str
    options: dict[str, str]
    correct_answers: list[str] = Field(default_factory=list)
    source_url: str
    confidence: float = 0.0
    quality_score: float = 0.0
    fingerprint: str = ""
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    @field_validator("correct_answers")
    @classmethod
    def normalize_answers(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            letter = (item or "").strip().upper()
            if letter and letter not in normalized:
                normalized.append(letter)
        return normalized


class RunSummary(BaseModel):
    start_url: str
    records_written: int
    rejected_records: int
    duplicate_records: int
    captcha_events: int
    user_interventions: int
    stop_reason: str


@dataclass
class RuntimeState:
    max_records: int
    next_index: int
    records_written: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    tool_calls: int = 0
    consecutive_failures: int = 0
    captcha_events: int = 0
    user_interventions: int = 0
    validation_failures: int = 0
    stop_reason: str = ""
    captcha_detected: bool = False
    last_warning: str = ""
    domain: str = ""
    current_url: str = ""
    current_fingerprint: str = ""
    selector_overrides: dict[str, list[str]] = field(default_factory=dict)
    seen_fingerprints: set[str] = field(default_factory=set)
    selector_success_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    last_candidate: ExtractionCandidate | None = None
    notes: dict[str, Any] = field(default_factory=dict)
    run_started_at_epoch: float = field(default_factory=time.time)
    page_started_at_epoch: float = field(default_factory=time.time)
    current_page_url: str = ""
    current_page_candidates_found: int = 0
    current_page_saved: int = 0
    current_page_skipped: int = 0
    current_page_image_skipped: int = 0
    last_page_candidates_found: int = 0
    last_page_saved: int = 0
    last_page_skipped: int = 0
    last_page_image_skipped: int = 0
    pages_processed: int = 0
    image_based_skipped_total: int = 0
    current_page_extraction_diagnostics: dict[str, Any] = field(default_factory=dict)
    last_page_extraction_diagnostics: dict[str, Any] = field(default_factory=dict)
    navigation_stop_snapshot: dict[str, Any] = field(default_factory=dict)
