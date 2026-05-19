from __future__ import annotations

import json
from datetime import datetime, timezone
import re
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from .browser import BrowserRuntime, options_to_map, parse_answer_letters
from .models import ExtractionCandidate, MCQRecord, RuntimeState
from .storage import JsonlStore
from .validation import validate_record_payload

try:
    from copilot.tools import Tool, ToolInvocation, ToolResult
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "github-copilot-sdk is required. Install dependencies in automation/ first.",
    ) from exc


class OpenUrlArgs(BaseModel):
    url: str


class WaitForChangeArgs(BaseModel):
    previous_fingerprint: str
    timeout_ms: int = 5000


class ScreenshotArgs(BaseModel):
    label: str = "capture"


class SelectorOverridesArgs(BaseModel):
    question_containers: list[str] | None = None
    question: list[str] | None = None
    options: list[str] | None = None
    answer: list[str] | None = None
    show_answer_buttons: list[str] | None = None
    next_buttons: list[str] | None = None


class StopArgs(BaseModel):
    reason: str = "agent_requested_stop"


class SaveRecordArgs(BaseModel):
    question: str | None = None
    options: dict[str, str] | None = None
    correct_answers: list[str] | None = None
    confidence: float | None = None


class PersistSelectorsArgs(BaseModel):
    selectors: dict[str, str]


class DiscoverSelectorsArgs(BaseModel):
    key: str | None = Field(
        default=None,
        description="Optional profile key filter: question/options/answer",
    )


PAGE_CANDIDATE_QUEUE_KEY = "page_candidate_queue"
PAGE_CANDIDATE_SOURCE_URL_KEY = "page_candidate_source_url"
ALLOWED_STOP_REASONS = {
    "verified_no_next_page",
    "navigation_blocked",
    "captcha_blocked",
    "max_records_reached",
    "turn_limit_reached",
    "user_requested_stop",
}


class CopilotToolbox:
    def __init__(
        self,
        browser: BrowserRuntime,
        store: JsonlStore,
        state: RuntimeState,
        screenshot_dir: Path,
        *,
        min_confidence: float,
        min_quality_score: float,
        require_answers: bool,
        selector_debug: bool,
        on_selector_learn: Callable[[str, str], None] | None = None,
    ) -> None:
        self.browser = browser
        self.store = store
        self.state = state
        self.screenshot_dir = screenshot_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.min_confidence = min_confidence
        self.min_quality_score = min_quality_score
        self.require_answers = require_answers
        self.selector_debug = selector_debug
        self.on_selector_learn = on_selector_learn

    def build_tools(self) -> list[Tool]:
        return [
            Tool(
                name="open_url",
                description="Navigate to a URL in the active browser page",
                parameters=OpenUrlArgs.model_json_schema(),
                handler=self._open_url,
            ),
            Tool(
                name="get_page_context",
                description="Read current URL, title, text preview and fingerprint",
                parameters={"type": "object", "properties": {}},
                handler=self._get_page_context,
            ),
            Tool(
                name="detect_captcha",
                description="Detect whether a captcha is visible on the current page",
                parameters={"type": "object", "properties": {}},
                handler=self._detect_captcha,
            ),
            Tool(
                name="reveal_answer",
                description="Click likely show-answer controls on the current page",
                parameters={"type": "object", "properties": {}},
                handler=self._reveal_answer,
            ),
            Tool(
                name="extract_current_mcq",
                description="Extract question, options, answer and confidence from the page",
                parameters={"type": "object", "properties": {}},
                handler=self._extract_current_mcq,
            ),
            Tool(
                name="discover_selectors",
                description="Discover potential question/options/answer selectors from the current page",
                parameters=DiscoverSelectorsArgs.model_json_schema(),
                handler=self._discover_selectors,
            ),
            Tool(
                name="save_current_record",
                description="Validate and persist the extracted MCQ into JSONL",
                parameters=SaveRecordArgs.model_json_schema(),
                handler=self._save_current_record,
            ),
            Tool(
                name="click_next",
                description="Click likely next question or pagination controls",
                parameters={"type": "object", "properties": {}},
                handler=self._click_next,
            ),
            Tool(
                name="has_next_page",
                description="Check if site-level pagination to another page is still available",
                parameters={"type": "object", "properties": {}},
                handler=self._has_next_page,
            ),
            Tool(
                name="wait_for_change",
                description="Wait for page content to change after navigation",
                parameters=WaitForChangeArgs.model_json_schema(),
                handler=self._wait_for_change,
            ),
            Tool(
                name="update_selector_overrides",
                description="Update runtime selector overrides for extraction/navigation",
                parameters=SelectorOverridesArgs.model_json_schema(),
                handler=self._update_selector_overrides,
            ),
            Tool(
                name="persist_selector_learning",
                description="Persist explicit selector learning into domain profile",
                parameters=PersistSelectorsArgs.model_json_schema(),
                handler=self._persist_selector_learning,
            ),
            Tool(
                name="take_screenshot",
                description="Capture current page screenshot for debugging/review",
                parameters=ScreenshotArgs.model_json_schema(),
                handler=self._take_screenshot,
            ),
            Tool(
                name="stop_run",
                description="Request the orchestrator to stop the crawl",
                parameters=StopArgs.model_json_schema(),
                handler=self._stop_run,
            ),
        ]

    def build_gap_fill_tools(self) -> list[Tool]:
        return [
            Tool(
                name="get_page_context",
                description="Read current URL, title, text preview and fingerprint",
                parameters={"type": "object", "properties": {}},
                handler=self._get_page_context,
            ),
            Tool(
                name="reveal_answer",
                description="Click likely show-answer controls on the current page",
                parameters={"type": "object", "properties": {}},
                handler=self._reveal_answer,
            ),
            Tool(
                name="extract_current_mcq",
                description="Extract question, options, answer and confidence from the page",
                parameters={"type": "object", "properties": {}},
                handler=self._extract_current_mcq,
            ),
            Tool(
                name="discover_selectors",
                description="Discover potential question/options/answer selectors from the current page",
                parameters=DiscoverSelectorsArgs.model_json_schema(),
                handler=self._discover_selectors,
            ),
            Tool(
                name="update_selector_overrides",
                description="Update runtime selector overrides for extraction/navigation",
                parameters=SelectorOverridesArgs.model_json_schema(),
                handler=self._update_selector_overrides,
            ),
            Tool(
                name="persist_selector_learning",
                description="Persist explicit selector learning into domain profile",
                parameters=PersistSelectorsArgs.model_json_schema(),
                handler=self._persist_selector_learning,
            ),
            Tool(
                name="save_current_record",
                description="Validate and persist the extracted MCQ into JSONL",
                parameters=SaveRecordArgs.model_json_schema(),
                handler=self._save_current_record,
            ),
            Tool(
                name="take_screenshot",
                description="Capture current page screenshot for debugging/review",
                parameters=ScreenshotArgs.model_json_schema(),
                handler=self._take_screenshot,
            ),
        ]

    def _load_page_candidate_queue(self, current_url: str) -> list[ExtractionCandidate]:
        source_url = self.state.notes.get(PAGE_CANDIDATE_SOURCE_URL_KEY, "")
        if source_url != current_url:
            return []

        raw_queue = self.state.notes.get(PAGE_CANDIDATE_QUEUE_KEY)
        if not isinstance(raw_queue, list):
            return []

        queue: list[ExtractionCandidate] = []
        for item in raw_queue:
            if not isinstance(item, dict):
                continue
            try:
                queue.append(ExtractionCandidate.model_validate(item))
            except ValidationError:
                continue
        return queue

    def _store_page_candidate_queue(self, current_url: str, queue: list[ExtractionCandidate]) -> None:
        self.state.notes[PAGE_CANDIDATE_SOURCE_URL_KEY] = current_url
        self.state.notes[PAGE_CANDIDATE_QUEUE_KEY] = [item.model_dump() for item in queue]

    def _start_page_tracking(self, current_url: str) -> None:
        if not current_url:
            return

        if self.state.current_page_url == current_url:
            return

        if self.state.current_page_url:
            self.state.last_page_candidates_found = self.state.current_page_candidates_found
            self.state.last_page_saved = self.state.current_page_saved
            self.state.last_page_skipped = self.state.current_page_skipped
            self.state.last_page_llm_assists = self.state.current_page_llm_assists
            self.state.pages_processed += 1

        self.state.current_page_url = current_url
        self.state.current_page_candidates_found = 0
        self.state.current_page_saved = 0
        self.state.current_page_skipped = 0
        self.state.current_page_llm_assists = 0

    def _save_candidate_record(
        self,
        *,
        question: str,
        options: dict[str, str],
        answers: list[str],
        confidence_value: float,
        used_selectors: dict[str, str],
    ) -> tuple[bool, str, dict]:
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

    async def _open_url(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(OpenUrlArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        final_url = await self.browser.open_url(args.url)
        return _success({"url": final_url}, f"opened {final_url}")

    async def _get_page_context(self, invocation: ToolInvocation) -> ToolResult:
        context = await self.browser.page_context()
        return _success(context, "fetched page context")

    async def _detect_captcha(self, invocation: ToolInvocation) -> ToolResult:
        detected = await self.browser.detect_captcha()
        if detected:
            self.state.captcha_detected = True
            self.state.captcha_events += 1
        return _success({"captcha_detected": detected}, "captcha check complete")

    async def _reveal_answer(self, invocation: ToolInvocation) -> ToolResult:
        clicked = await self.browser.reveal_answer()
        return _success({"clicked": clicked}, "reveal action attempted")

    async def _extract_current_mcq(self, invocation: ToolInvocation) -> ToolResult:
        current_url = self.browser.page.url if self.browser.page else ""
        self._start_page_tracking(current_url)

        queue = self._load_page_candidate_queue(current_url)

        if not queue:
            page_candidates = await self.browser.extract_page_candidates()
            if len(page_candidates) >= 2:
                queue = page_candidates
                self.state.current_page_candidates_found = max(
                    self.state.current_page_candidates_found,
                    len(page_candidates),
                )

        extraction_mode = "single"
        if queue:
            candidate = queue.pop(0)
            self._store_page_candidate_queue(current_url, queue)
            extraction_mode = "page_batch"
        else:
            candidate = await self.browser.extract_candidate()
            if candidate.question:
                self.state.current_page_candidates_found = max(
                    self.state.current_page_candidates_found,
                    1,
                )

        self.state.last_candidate = candidate
        self.state.notes["last_used_selectors"] = candidate.used_selectors

        if self.selector_debug:
            self.store.append_debug_event(
                {
                    "event": "candidate_extracted",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": self.browser.page.url if self.browser.page else "",
                    "question_preview": candidate.question[:180],
                    "options_count": len(candidate.option_texts),
                    "answer_preview": candidate.answer_text[:80],
                    "confidence": candidate.confidence,
                    "quality_score": candidate.quality_score,
                    "warnings": candidate.warnings,
                    "used_selectors": candidate.used_selectors,
                },
            )

        if candidate.confidence < self.min_confidence:
            self.state.consecutive_failures += 1
            self.state.last_warning = ",".join(candidate.warnings)
        else:
            self.state.last_warning = ""

        result_payload = candidate.model_dump()
        result_payload["remaining_candidates_on_page"] = len(queue)
        result_payload["extraction_mode"] = extraction_mode
        result_payload["page_candidates_found"] = self.state.current_page_candidates_found
        result_payload["page_saved"] = self.state.current_page_saved
        result_payload["page_skipped"] = self.state.current_page_skipped

        return _success(result_payload, "candidate extracted")

    async def _save_current_record(self, invocation: ToolInvocation) -> ToolResult:
        parsed = _parse_args(SaveRecordArgs, invocation.arguments)
        if isinstance(parsed, ToolResult):
            return parsed

        if self.state.last_candidate is None and parsed.question is None:
            return _error("No candidate available. Run extract_current_mcq first.")

        question = (parsed.question or (self.state.last_candidate.question if self.state.last_candidate else "")).strip()

        if parsed.options is not None:
            options = {k.strip().upper(): v.strip() for k, v in parsed.options.items() if k.strip() and v.strip()}
        else:
            option_texts = self.state.last_candidate.option_texts if self.state.last_candidate else []
            options = options_to_map(option_texts)

        if parsed.correct_answers is not None:
            answers = [item.strip().upper() for item in parsed.correct_answers if item.strip()]
        else:
            answer_text = self.state.last_candidate.answer_text if self.state.last_candidate else ""
            answers = parse_answer_letters(answer_text)

        confidence = parsed.confidence
        if confidence is None and self.state.last_candidate is not None:
            confidence = self.state.last_candidate.confidence
        confidence_value = float(confidence or 0.0)
        used_selectors = (
            self.state.last_candidate.used_selectors
            if self.state.last_candidate is not None
            else {}
        )

        saved, message, payload = self._save_candidate_record(
            question=question,
            options=options,
            answers=answers,
            confidence_value=confidence_value,
            used_selectors=used_selectors,
        )
        if not saved:
            return _error(message)

        total_saved = 1
        total_skipped = 0

        current_url = self.browser.page.url if self.browser.page else ""
        queue = self._load_page_candidate_queue(current_url)
        can_auto_save_page_candidates = all(
            value is None
            for value in [
                parsed.question,
                parsed.options,
                parsed.correct_answers,
                parsed.confidence,
            ]
        )

        if can_auto_save_page_candidates and queue:
            for candidate in queue:
                if self.state.stop_reason:
                    break

                queue_options = options_to_map(candidate.option_texts)
                queue_answers = parse_answer_letters(candidate.answer_text)
                queue_confidence = float(candidate.confidence or 0.0)

                queue_saved, _, _ = self._save_candidate_record(
                    question=candidate.question,
                    options=queue_options,
                    answers=queue_answers,
                    confidence_value=queue_confidence,
                    used_selectors=candidate.used_selectors,
                )

                if queue_saved:
                    total_saved += 1
                else:
                    total_skipped += 1

            self._store_page_candidate_queue(current_url, [])

        if total_saved == 1 and total_skipped == 0:
            return _success(payload, "record saved")

        return _success(
            {
                "primary_record": payload,
                "saved_count": total_saved,
                "skipped_count": total_skipped,
            },
            f"saved {total_saved} records ({total_skipped} skipped)",
        )

    async def _click_next(self, invocation: ToolInvocation) -> ToolResult:
        clicked = await self.browser.click_next()
        return _success({"clicked": clicked}, "next navigation attempted")

    async def _has_next_page(self, invocation: ToolInvocation) -> ToolResult:
        has_next = await self.browser.has_next_page()
        return _success({"has_next_page": has_next}, "next-page check complete")

    async def _wait_for_change(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(WaitForChangeArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        changed = await self.browser.wait_for_fingerprint_change(
            previous_fingerprint=args.previous_fingerprint,
            timeout_ms=args.timeout_ms,
        )
        return _success({"changed": changed}, "wait for content change complete")

    async def _update_selector_overrides(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(SelectorOverridesArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        merged = self.state.selector_overrides.copy()
        for field_name in [
            "question_containers",
            "question",
            "options",
            "answer",
            "show_answer_buttons",
            "next_buttons",
        ]:
            value = getattr(args, field_name)
            if value:
                merged[field_name] = [item.strip() for item in value if item.strip()]

        self.state.selector_overrides = merged
        return _success({"selector_overrides": merged}, "selector overrides updated")

    async def _persist_selector_learning(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(PersistSelectorsArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        applied: dict[str, str] = {}
        for key, selector in args.selectors.items():
            key_str = (key or "").strip()
            selector_str = (selector or "").strip()
            if key_str not in {
                "question_containers",
                "question",
                "options",
                "answer",
                "show_answer_buttons",
                "next_buttons",
            }:
                continue
            if not selector_str:
                continue
            if self.on_selector_learn is not None:
                self.on_selector_learn(key_str, selector_str)
            applied[key_str] = selector_str

        return _success({"applied": applied}, "selector learning persisted")

    async def _discover_selectors(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(DiscoverSelectorsArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        discovered = await self.browser.discover_selector_candidates()
        if args.key:
            key = re.sub(r"\s+", "", args.key.strip())
            filtered = {key: discovered.get(key, [])}
            return _success(filtered, "selector candidates discovered")

        return _success(discovered, "selector candidates discovered")

    async def _take_screenshot(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(ScreenshotArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}_{args.label}.png"
        path = self.screenshot_dir / filename
        final_path = await self.browser.screenshot(str(path))
        return _success({"screenshot": final_path}, "screenshot captured")

    async def _stop_run(self, invocation: ToolInvocation) -> ToolResult:
        args = _parse_args(StopArgs, invocation.arguments)
        if isinstance(args, ToolResult):
            return args

        requested_reason = re.sub(r"\s+", "_", (args.reason or "").strip().lower())
        if not requested_reason:
            requested_reason = "agent_requested_stop"

        self.state.notes["last_stop_request"] = {
            "requested_reason": requested_reason,
            "records_written": self.state.records_written,
            "current_url": self.browser.page.url if self.browser.page else self.state.current_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if requested_reason not in ALLOWED_STOP_REASONS:
            self.state.last_warning = f"ignored_stop_request:{requested_reason}"
            return _success(
                {
                    "applied": False,
                    "requested_reason": requested_reason,
                    "allowed_reasons": sorted(ALLOWED_STOP_REASONS),
                },
                "stop request ignored",
            )

        if requested_reason == "verified_no_next_page":
            has_next = await self.browser.has_next_page()
            if has_next:
                self.state.last_warning = "ignored_stop_request:next_page_available"
                return _success(
                    {
                        "applied": False,
                        "requested_reason": requested_reason,
                        "has_next_page": True,
                    },
                    "stop request ignored",
                )

        self.state.stop_reason = requested_reason
        return _success(
            {
                "applied": True,
                "stop_reason": self.state.stop_reason,
            },
            "run stop requested",
        )


def _parse_args(schema: type[BaseModel], payload: Any) -> BaseModel | ToolResult:
    data = payload or {}
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        return _error(f"Invalid arguments: {exc}")


def _success(payload: dict, message: str) -> ToolResult:
    return ToolResult(
        text_result_for_llm=json.dumps(payload, ensure_ascii=True),
        result_type="success",
        session_log=message,
    )


def _error(message: str) -> ToolResult:
    return ToolResult(
        text_result_for_llm=message,
        result_type="error",
        session_log=message,
    )
