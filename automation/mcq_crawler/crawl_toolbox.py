from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Callable

from .models import MCQRecord, RuntimeState
from .storage import JsonlStore
from .validation import validate_record_payload


class CrawlToolbox:
    def __init__(
        self,
        browser,
        store: JsonlStore,
        state: RuntimeState,
        *,
        min_confidence: float,
        min_quality_score: float,
        require_answers: bool,
        selector_debug: bool,
        stop_on_missing_answers: bool = False,
        on_selector_learn: Callable[[str, str], None] | None = None,
    ) -> None:
        self.browser = browser
        self.store = store
        self.state = state
        self.min_confidence = min_confidence
        self.min_quality_score = min_quality_score
        self.require_answers = require_answers
        self.selector_debug = selector_debug
        self.stop_on_missing_answers = stop_on_missing_answers
        self.on_selector_learn = on_selector_learn

    def _current_page_image_skip_count(self) -> int:
        diagnostics = self.state.current_page_extraction_diagnostics
        if not isinstance(diagnostics, dict):
            return 0

        value = diagnostics.get("image_based_skipped_candidates", 0)
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            return max(0, int(value))
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
        return 0

    def _start_page_tracking(self, current_url: str) -> None:
        if not current_url:
            return

        if self.state.current_page_url == current_url:
            return

        if self.state.current_page_url:
            self.state.last_page_candidates_found = self.state.current_page_candidates_found
            self.state.last_page_saved = self.state.current_page_saved
            self.state.last_page_skipped = self.state.current_page_skipped
            self.state.last_page_image_skipped = self.state.current_page_image_skipped
            self.state.last_page_extraction_diagnostics = dict(self.state.current_page_extraction_diagnostics)
            self.state.image_based_skipped_total += self.state.current_page_image_skipped
            self.state.pages_processed += 1

        self.state.current_page_url = current_url
        self.state.current_page_candidates_found = 0
        self.state.current_page_saved = 0
        self.state.current_page_skipped = 0
        self.state.current_page_image_skipped = 0
        self.state.current_page_extraction_diagnostics = {}

    def _save_candidate_record(
        self,
        *,
        question: str,
        options: dict[str, str],
        answers: list[str],
        confidence_value: float,
        extracted_answer_text: str = "",
        used_selectors: dict[str, str],
    ) -> tuple[bool, str, dict]:
        missing_fields: list[str] = []
        normalized_question = (question or "").strip()
        if not normalized_question:
            missing_fields.append("question")
        if len(options) < 2:
            missing_fields.append("options")
        if not answers:
            missing_fields.append("answer")

        non_question_candidate = self._looks_like_non_question_candidate(
            question,
            options,
            used_selectors,
        )

        if missing_fields:
            payload = {
                "reason": "missing_extraction_fields",
                "stage": "save_candidate_record",
                "missing_fields": missing_fields,
                "question": question,
                "options": options,
                "answers": answers,
                "answer_text": extracted_answer_text,
                "url": self.browser.page.url if self.browser.page else "",
                "used_selectors": used_selectors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_error(payload)
            if self.selector_debug:
                self.store.append_debug_event(
                    {
                        "event": "record_missing_fields",
                        "timestamp": payload["timestamp"],
                        "url": payload["url"],
                        "missing_fields": missing_fields,
                        "question_preview": question[:180],
                        "options_count": len(options),
                        "answers_count": len(answers),
                        "used_selectors": used_selectors,
                    },
                )

            if non_question_candidate:
                self.state.rejected_records += 1
                self.state.validation_failures += 1
                self.state.consecutive_failures += 1
                self.state.current_page_skipped += 1
                self.state.last_warning = "non_question_candidate"
                return False, "Non-question candidate skipped.", payload

            if self.stop_on_missing_answers and self.require_answers and "answer" in missing_fields:
                self.state.rejected_records += 1
                self.state.validation_failures += 1
                self.state.consecutive_failures += 1
                self.state.current_page_skipped += 1
                self.state.last_warning = "answer_missing"
                self.state.stop_reason = "answer_extraction_failed"
                if self.selector_debug:
                    self.store.append_debug_event(
                        {
                            "event": "run_stopped",
                            "timestamp": payload["timestamp"],
                            "reason": "answer_extraction_failed",
                            "url": payload["url"],
                            "question_preview": question[:180],
                            "used_selectors": used_selectors,
                        },
                    )
                return False, "Run stopped: required answers could not be extracted.", payload

        if not question or len(options) < 2:
            payload = {
                "reason": "validation_failed",
                "question": question,
                "options": options,
                "answers": answers,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_error(payload)
            if self.selector_debug:
                self.store.append_debug_event(
                    {
                        "event": "record_rejected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": "validation_failed",
                        "url": self.browser.page.url if self.browser.page else "",
                        "question_preview": question[:180],
                        "options_count": len(options),
                        "used_selectors": used_selectors,
                    },
                )
            self.state.rejected_records += 1
            self.state.validation_failures += 1
            self.state.consecutive_failures += 1
            self.state.current_page_skipped += 1
            return False, "Record validation failed: question/options are incomplete.", payload

        validation = validate_record_payload(
            question=question,
            options=options,
            answers=answers,
            confidence=confidence_value,
            require_answers=self.require_answers,
            min_quality_score=self.min_quality_score,
        )

        if validation.fingerprint in self.state.seen_fingerprints:
            payload = {
                "reason": "duplicate_record",
                "fingerprint": validation.fingerprint,
                "question": question,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_error(payload)
            if self.selector_debug:
                self.store.append_debug_event(
                    {
                        "event": "record_rejected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": "duplicate_record",
                        "url": self.browser.page.url if self.browser.page else "",
                        "fingerprint": validation.fingerprint,
                        "question_preview": question[:180],
                        "used_selectors": used_selectors,
                    },
                )
            self.state.rejected_records += 1
            self.state.duplicate_records += 1
            self.state.current_page_skipped += 1
            return False, "Duplicate record rejected by fingerprint gate.", payload

        if not validation.valid:
            payload = {
                "reason": "quality_gate_failed",
                "errors": validation.errors,
                "warnings": validation.warnings,
                "quality_score": validation.quality_score,
                "question": question,
                "options": options,
                "answers": answers,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_error(payload)
            if self.selector_debug:
                self.store.append_debug_event(
                    {
                        "event": "record_rejected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": "quality_gate_failed",
                        "url": self.browser.page.url if self.browser.page else "",
                        "errors": validation.errors,
                        "warnings": validation.warnings,
                        "quality_score": validation.quality_score,
                        "question_preview": question[:180],
                        "used_selectors": used_selectors,
                    },
                )
            if self.stop_on_missing_answers and self.require_answers and "answers_required" in validation.errors:
                self.state.last_warning = "answer_missing"
                self.state.stop_reason = "answer_extraction_failed"
            self.state.rejected_records += 1
            self.state.validation_failures += 1
            self.state.consecutive_failures += 1
            self.state.current_page_skipped += 1
            return (
                False,
                "Record rejected by quality gate: " + ",".join(validation.errors),
                payload,
            )

        normalized_answers = validation.normalized_answers

        record = MCQRecord(
            index=self.state.next_index,
            question=question,
            options=options,
            correct_answers=normalized_answers,
            source_url=self.browser.page.url if self.browser.page else "",
            confidence=confidence_value,
            quality_score=validation.quality_score,
            fingerprint=validation.fingerprint,
        )

        self.store.append_record(record)
        if self.selector_debug:
            self.store.append_debug_event(
                {
                    "event": "record_saved",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": record.source_url,
                    "index": record.index,
                    "fingerprint": record.fingerprint,
                    "confidence": record.confidence,
                    "quality_score": record.quality_score,
                    "correct_answers": record.correct_answers,
                    "used_selectors": used_selectors,
                    "question_preview": record.question[:180],
                },
            )

        self.state.seen_fingerprints.add(validation.fingerprint)
        self.state.records_written += 1
        self.state.next_index += 1
        self.state.current_page_saved += 1
        self.state.page_started_at_epoch = time.time()
        self.state.consecutive_failures = 0

        for key, selector in used_selectors.items():
            if key not in self.state.selector_success_counts:
                self.state.selector_success_counts[key] = {}
            current = self.state.selector_success_counts[key].get(selector, 0)
            self.state.selector_success_counts[key][selector] = current + 1
            if self.on_selector_learn is not None:
                self.on_selector_learn(key, selector)

        if self.state.records_written >= self.state.max_records:
            self.state.stop_reason = "max_records_reached"

        return True, "record saved", record.model_dump()

    def _looks_like_non_question_candidate(
        self,
        question: str,
        options: dict[str, str],
        used_selectors: dict[str, str],
    ) -> bool:
        question_text = (question or "").strip().lower()
        non_empty_options = [str(value or "").strip() for value in options.values() if str(value or "").strip()]

        if not question_text and not non_empty_options:
            return True

        if "choose how you want to study this exam" in question_text:
            return True
        if "about study modes" in question_text:
            return True

        question_selector = str(used_selectors.get("question") or "").strip().lower()
        options_selector = str(used_selectors.get("options") or "").strip().lower()
        if "mode-switcher" in question_selector:
            return True
        if "breadcrumb" in question_selector or "breadcrumb" in options_selector:
            return True

        option_values = [value.lower() for value in non_empty_options]
        slashy_options = [value for value in option_values if value and "/" in value]
        if len(slashy_options) >= 2:
            return True

        return False
