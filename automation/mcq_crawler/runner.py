from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urldefrag, urlparse

from rich.console import Console

from .auth import load_host_auth_config
from .browser import BrowserRuntime, options_to_map, parse_answer_letters
from .checkpoint import CheckpointStore
from .config import RunConfig, domain_from_url, load_selector_profile
from .copilot_controller import CopilotToolbox
from .models import ExtractionCandidate, RunSummary, RuntimeState
from .profile_store import SelectorProfileStore
from .storage import JsonlStore

try:
    from copilot import CopilotClient, SubprocessConfig
    from copilot.generated.session_events import AssistantMessageData, SessionIdleData
    from copilot.session import PermissionHandler
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "github-copilot-sdk is required. Install dependencies in automation/ first.",
    ) from exc


SYSTEM_PROMPT = """
You are an MCQ extraction controller operating browser tools.

Objectives:
1) Extract all high-quality MCQ records visible on the current page.
2) Save valid records via save_current_record.
3) Skip ambiguous or low-quality candidates and continue.
4) Navigate to the next page and continue until limits are reached.

Rules:
- Always start by checking captcha status and page context when uncertain.
- Use reveal_answer before extracting if answers are hidden.
- If some candidates are ambiguous, keep saving valid ones instead of stopping.
- If extraction confidence is low for the whole page or validation fails repeatedly, ask for selector overrides.
- Do not stop because a certain record count feels sufficient; only stop on true terminal conditions.
- Before calling stop_run for end-of-pagination, call has_next_page and stop only when it returns false.
- Do not invent question/answer content. Use tool results only.
""".strip()

INITIAL_WAIT_TIMEOUT_SECONDS = 120
TURN_WAIT_TIMEOUT_SECONDS = 90
DEFAULT_AUTH_FILE_PATH = Path("auth/auth_hosts.yaml")
LEGACY_AUTH_FILE_PATH = Path("profiles/auth_hosts.yaml")


class SessionWaiter:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.done = asyncio.Event()
        self.last_message = ""

    def reset(self) -> None:
        self.done = asyncio.Event()

    def on_event(self, event: Any) -> None:
        match event.data:
            case AssistantMessageData() as data:
                self.last_message = data.content or ""
                if self.last_message.strip():
                    preview = self.last_message.strip()
                    if len(preview) > 600:
                        preview = preview[:600] + " ..."
                    self.console.print(f"[cyan]assistant[/cyan] {preview}")
            case SessionIdleData():
                self.done.set()


async def _async_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


class CrawlRunner:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.console = Console()

    async def run(self) -> RunSummary:
        base_selector_profile = load_selector_profile(self.config.profile_path)
        profile_store = SelectorProfileStore(self.config.domain_profiles_dir)

        state = RuntimeState(
            max_records=self.config.max_records,
            next_index=self.config.start_index,
        )

        checkpoint_store = CheckpointStore(self.config.checkpoint_path)
        target_url = self.config.start_url
        if self.config.resume:
            restored_url = checkpoint_store.restore_into(state)
            if restored_url:
                target_url = restored_url

        state.domain = domain_from_url(target_url)
        state.current_url = target_url
        state.notes["crawl_scope_host"] = self._crawl_scope_host(target_url)
        state.notes["crawl_scope_path_prefix"] = self._crawl_scope_path_prefix(target_url)

        selector_profile = profile_store.merge_with_domain(
            base_selector_profile,
            state.domain,
        )

        store = JsonlStore(
            self.config.output_path,
            self.config.error_path,
            debug_path=(self.config.debug_output_path if self.config.selector_debug else None),
            questions_per_file=self.config.questions_per_file,
            records_written=state.records_written,
        )

        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)

        async with BrowserRuntime(self.config, selector_profile, state) as browser:
            await browser.open_url(target_url)

            auto_login_attempted = False
            auto_login_succeeded = False
            if self.config.enable_auto_login:
                auto_login_attempted, auto_login_succeeded = await self._attempt_auto_login(browser, state)

            requires_manual_prompt = self.config.prompt_for_login_at_start
            if self.config.enable_auto_login and auto_login_attempted and not auto_login_succeeded:
                requires_manual_prompt = True

            if requires_manual_prompt:
                if self.config.headless:
                    state.stop_reason = "login_required"
                    state.last_warning = state.last_warning or "login_required"
                    self.console.print(
                        "[yellow]Login is required but run is headless. Stopping before extraction.[/yellow]",
                    )
                    await self._save_checkpoint(browser, state, checkpoint_store)
                else:
                    continue_run = await self._prompt_for_login_at_start(browser, state)
                    if not continue_run:
                        await self._save_checkpoint(browser, state, checkpoint_store)

            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=self.config.screenshot_dir,
                min_confidence=self.config.min_confidence,
                min_quality_score=self.config.min_quality_score,
                require_answers=self.config.require_answers,
                stop_on_missing_answers=self.config.stop_on_missing_answers,
                selector_debug=self.config.selector_debug,
                on_selector_learn=(
                    lambda key, selector: profile_store.record_selector_success(
                        state.domain,
                        key,
                        selector,
                    )
                )
                if self.config.auto_learn_profiles
                else None,
            )

            if not state.stop_reason:
                if self.config.orchestration_mode == "llm_orchestrator":
                    await self._run_llm_orchestrated_loop(
                        browser=browser,
                        state=state,
                        profile_store=profile_store,
                        checkpoint_store=checkpoint_store,
                        toolbox=toolbox,
                    )
                else:
                    await self._run_deterministic_loop(
                        browser=browser,
                        state=state,
                        profile_store=profile_store,
                        checkpoint_store=checkpoint_store,
                        toolbox=toolbox,
                    )

        summary = RunSummary(
            start_url=target_url,
            records_written=state.records_written,
            rejected_records=state.rejected_records,
            duplicate_records=state.duplicate_records,
            captcha_events=state.captcha_events,
            user_interventions=state.user_interventions,
            stop_reason=state.stop_reason,
        )
        return summary

    async def _run_llm_orchestrated_loop(
        self,
        *,
        browser: BrowserRuntime,
        state: RuntimeState,
        profile_store: SelectorProfileStore,
        checkpoint_store: CheckpointStore,
        toolbox: CopilotToolbox,
    ) -> None:
        client_config = SubprocessConfig(
            cwd=str(self.config.workspace_dir),
            use_logged_in_user=True,
        )

        async with CopilotClient(client_config) as client:
            async with await client.create_session(
                model=self.config.model,
                on_permission_request=PermissionHandler.approve_all,
                on_user_input_request=self._on_user_input_request,
                tools=toolbox.build_tools(),
                streaming=False,
                infinite_sessions={"enabled": True},
            ) as session:
                waiter = SessionWaiter(self.console)
                session.on(waiter.on_event)

                try:
                    await self._send_and_wait(
                        session,
                        waiter,
                        SYSTEM_PROMPT,
                        timeout_seconds=INITIAL_WAIT_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    state.last_warning = "initial_controller_timeout"
                    self.console.print(
                        "[yellow]Initial controller wait timed out; continuing with turn loop.[/yellow]",
                    )

                stale_turns = 0
                previous_written = state.records_written

                for turn in range(1, self.config.max_turns + 1):
                    if state.stop_reason:
                        break
                    if state.records_written >= state.max_records:
                        state.stop_reason = "max_records_reached"
                        break

                    if state.captcha_detected or state.consecutive_failures >= self.config.max_consecutive_failures:
                        await self._manual_intervention(browser, state, profile_store)
                        if state.stop_reason:
                            break

                    prompt = self._build_turn_prompt(turn, state)
                    try:
                        await self._send_and_wait(
                            session,
                            waiter,
                            prompt,
                            timeout_seconds=TURN_WAIT_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        state.consecutive_failures += 1
                        state.last_warning = "controller_timeout"
                        await self._manual_intervention(browser, state, profile_store)
                        if state.stop_reason:
                            break

                    if state.records_written == previous_written:
                        stale_turns += 1
                    else:
                        stale_turns = 0
                        previous_written = state.records_written

                    if stale_turns >= 4:
                        self.console.print(
                            "[yellow]No extraction progress after 4 turns. Requesting feedback.[/yellow]",
                        )
                        await self._manual_intervention(browser, state, profile_store)
                        stale_turns = 0

                    await self._save_checkpoint(browser, state, checkpoint_store)

                if not state.stop_reason:
                    state.stop_reason = "turn_limit_reached"

                await self._save_checkpoint(browser, state, checkpoint_store)

    async def _run_deterministic_loop(
        self,
        *,
        browser: BrowserRuntime,
        state: RuntimeState,
        profile_store: SelectorProfileStore,
        checkpoint_store: CheckpointStore,
        toolbox: CopilotToolbox,
    ) -> None:
        stale_turns = 0
        previous_written = state.records_written

        scope_seed_url = state.current_url or self.config.start_url
        if not state.notes.get("crawl_scope_host"):
            state.notes["crawl_scope_host"] = self._crawl_scope_host(scope_seed_url)
        if not state.notes.get("crawl_scope_path_prefix"):
            state.notes["crawl_scope_path_prefix"] = self._crawl_scope_path_prefix(scope_seed_url)

        for turn in range(1, self.config.max_turns + 1):
            if state.stop_reason:
                break
            if state.records_written >= state.max_records:
                state.stop_reason = "max_records_reached"
                break

            detected = await browser.detect_captcha()
            if detected:
                state.captcha_detected = True
                state.captcha_events += 1

            if state.captcha_detected or state.consecutive_failures >= self.config.max_consecutive_failures:
                await self._manual_intervention(browser, state, profile_store)
                if state.stop_reason:
                    break

            if self.config.humanize:
                await browser.maybe_human_delay(reason="turn_start")

            await browser.wait_for_exam_content_ready(timeout_ms=2500)
            await browser.ensure_browse_mode_ready()
            await browser.wait_for_exam_content_ready(timeout_ms=1000)
            if self.config.humanize:
                await browser.maybe_human_read_pause(reason="content_ready")
            await browser.reveal_answer()
            if self.config.humanize:
                await browser.maybe_human_delay(reason="post_reveal_extract")

            current_url = browser.page.url if browser.page else state.current_url
            toolbox._start_page_tracking(current_url)

            candidates = await browser.extract_page_candidates(
                max_candidates=self.config.max_page_candidates,
            )
            if not candidates:
                await browser.ensure_browse_mode_ready()
                await browser.wait_for_exam_content_ready(timeout_ms=3500)
                candidates = await browser.extract_page_candidates(
                    max_candidates=self.config.max_page_candidates,
                )

            candidates = await self._retry_low_coverage_candidate_extraction(
                browser=browser,
                state=state,
                candidates=candidates,
            )

            if not candidates:
                single_candidate = await browser.extract_candidate()
                candidates = [single_candidate]

            state.current_page_candidates_found = max(
                state.current_page_candidates_found,
                len(candidates),
            )

            for candidate in candidates:
                if state.stop_reason:
                    break
                if state.records_written >= state.max_records:
                    state.stop_reason = "max_records_reached"
                    break

                await self._attempt_save_candidate(toolbox, candidate)

            if state.records_written == previous_written:
                stale_turns += 1
            else:
                stale_turns = 0
                previous_written = state.records_written

            if stale_turns >= 4:
                if self.config.headless:
                    self.console.print(
                        "[yellow]No extraction progress after 4 deterministic turns. Auto-advancing in headless mode.[/yellow]",
                    )
                    auto_advanced = await self._auto_advance_after_stale_progress(browser, state)
                    stale_turns = 0
                    if state.stop_reason:
                        await self._save_checkpoint(browser, state, checkpoint_store)
                        break
                    if auto_advanced:
                        await self._save_checkpoint(browser, state, checkpoint_store)
                        continue
                else:
                    self.console.print(
                        "[yellow]No extraction progress after 4 deterministic turns. Requesting feedback.[/yellow]",
                    )
                    await self._manual_intervention(browser, state, profile_store)
                    stale_turns = 0

            await self._save_checkpoint(browser, state, checkpoint_store)

            if state.stop_reason:
                break
            if state.records_written >= state.max_records:
                state.stop_reason = "max_records_reached"
                break

            has_next = await browser.has_next_page()
            previous_url = self._normalized_url(browser.page.url if browser.page else state.current_url)

            prev_fingerprint = ""
            try:
                prev_fingerprint = await browser.current_fingerprint()
            except Exception:
                prev_fingerprint = ""

            moved = False
            last_clicked = False
            last_fingerprint_changed = False
            last_url_changed = False
            for _ in range(max(1, self.config.navigation_retry_limit)):
                if self.config.humanize:
                    await browser.maybe_human_delay(reason="before_next_click")
                clicked = await browser.click_next()
                last_clicked = clicked
                if not clicked:
                    continue
                if not prev_fingerprint:
                    moved = True
                    break
                changed = await browser.wait_for_fingerprint_change(
                    previous_fingerprint=prev_fingerprint,
                    timeout_ms=3000,
                )
                last_fingerprint_changed = changed
                current_url = self._normalized_url(browser.page.url if browser.page else state.current_url)
                url_changed = bool(current_url and current_url != previous_url)
                last_url_changed = url_changed
                if changed or url_changed:
                    moved = True
                    break

            state.notes["last_navigation_decision"] = {
                "has_next_page": has_next,
                "clicked": last_clicked,
                "fingerprint_changed": last_fingerprint_changed,
                "url_changed": last_url_changed,
                "out_of_scope": False,
            }

            if not moved:
                if not has_next:
                    state.stop_reason = "verified_no_next_page"
                    state.navigation_stop_snapshot = self._build_navigation_stop_snapshot(state)
                    break
                state.consecutive_failures += 1
                state.last_warning = "navigation_no_change"
            else:
                next_url = self._normalized_url(browser.page.url if browser.page else state.current_url)
                out_of_scope = bool(next_url) and (not self._is_within_crawl_scope(next_url, state))
                state.notes["last_navigation_decision"]["out_of_scope"] = out_of_scope
                if out_of_scope:
                    state.stop_reason = "navigation_out_of_scope"
                    state.last_warning = "navigation_out_of_scope"
                    state.current_url = next_url
                    state.navigation_stop_snapshot = self._build_navigation_stop_snapshot(state)
                    break

                state.consecutive_failures = 0
                state.last_warning = ""
                state.page_started_at_epoch = time.time()
                if browser.page and browser.page.url:
                    state.current_url = browser.page.url
                if self.config.humanize:
                    await browser.maybe_human_read_pause(reason="post_navigation")

        if not state.stop_reason:
            state.stop_reason = "turn_limit_reached"

        await self._save_checkpoint(browser, state, checkpoint_store)

    async def _retry_low_coverage_candidate_extraction(
        self,
        *,
        browser: BrowserRuntime,
        state: RuntimeState,
        candidates: list[ExtractionCandidate],
    ) -> list[ExtractionCandidate]:
        if not candidates:
            return candidates

        baseline_count = len(candidates)
        previous_page_count = max(0, int(state.last_page_candidates_found))
        if previous_page_count < 8:
            return candidates

        low_coverage_threshold = max(6, int(previous_page_count * 0.65))
        if baseline_count >= low_coverage_threshold:
            return candidates

        await browser.ensure_browse_mode_ready()
        await browser.wait_for_exam_content_ready(timeout_ms=1800)
        refreshed = await browser.extract_page_candidates(
            max_candidates=self.config.max_page_candidates,
        )
        if not refreshed:
            state.notes["last_low_coverage_retry"] = {
                "baseline_count": baseline_count,
                "refreshed_count": 0,
                "merged_count": baseline_count,
                "previous_page_count": previous_page_count,
                "threshold": low_coverage_threshold,
            }
            return candidates

        merged: list[ExtractionCandidate] = []
        seen: set[str] = set()
        for candidate in [*candidates, *refreshed]:
            signature = self._candidate_signature(candidate)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(candidate)

        state.notes["last_low_coverage_retry"] = {
            "baseline_count": baseline_count,
            "refreshed_count": len(refreshed),
            "merged_count": len(merged),
            "previous_page_count": previous_page_count,
            "threshold": low_coverage_threshold,
        }
        return merged

    def _candidate_signature(self, candidate: ExtractionCandidate) -> str:
        question = " ".join((candidate.question or "").split()).strip().lower()
        options = [" ".join((option or "").split()).strip().lower() for option in candidate.option_texts]
        return f"{question}|{'|'.join(options)}"

    def _build_navigation_stop_snapshot(self, state: RuntimeState) -> dict[str, Any]:
        return {
            "stop_reason": state.stop_reason,
            "current_url": state.current_url,
            "last_warning": state.last_warning,
            "last_navigation_decision": state.notes.get("last_navigation_decision", {}),
            "last_next_candidates": state.notes.get("last_next_candidates", {}),
            "last_low_coverage_retry": state.notes.get("last_low_coverage_retry", {}),
            "current_page_extraction_diagnostics": state.current_page_extraction_diagnostics,
            "last_page_extraction_diagnostics": state.last_page_extraction_diagnostics,
        }

    async def _attempt_save_candidate(self, toolbox: CopilotToolbox, candidate: ExtractionCandidate) -> None:
        options = options_to_map(candidate.option_texts)
        answers = parse_answer_letters(candidate.answer_text)
        state = toolbox.state
        state.last_candidate = candidate

        saved, _, _ = toolbox._save_candidate_record(
            question=candidate.question,
            options=options,
            answers=answers,
            extracted_answer_text=candidate.answer_text,
            confidence_value=float(candidate.confidence or 0.0),
            used_selectors=candidate.used_selectors,
        )
        if saved:
            return

        if state.stop_reason:
            return

        if self.config.orchestration_mode != "hybrid_gap_fill":
            return

        assist_reason = self._assist_trigger_reason(candidate, state)
        if not assist_reason:
            return

        page_assist_key = f"assist_attempts::{state.current_page_url or state.current_url}"
        current_attempts = int(state.notes.get(page_assist_key, 0))
        if current_attempts >= self.config.max_llm_assists_per_page:
            return

        state.notes[page_assist_key] = current_attempts + 1
        state.llm_assist_attempts_total += 1
        state.current_page_llm_assists += 1
        state.llm_assist_last_trigger_reason = assist_reason

        assisted = await self._run_gap_fill_assist(toolbox, state)
        if not assisted:
            return

        retried = await toolbox.browser.extract_candidate()
        retry_saved, _, _ = toolbox._save_candidate_record(
            question=retried.question,
            options=options_to_map(retried.option_texts),
            answers=parse_answer_letters(retried.answer_text),
            extracted_answer_text=retried.answer_text,
            confidence_value=float(retried.confidence or 0.0),
            used_selectors=retried.used_selectors,
        )
        if retry_saved:
            state.llm_assist_saved_count += 1

    def _assist_trigger_reason(self, candidate: ExtractionCandidate, state: RuntimeState) -> str:
        if candidate.confidence < self.config.min_confidence:
            return "low_confidence"

        candidate_warnings = set(candidate.warnings)
        if "question_missing" in candidate_warnings or "insufficient_options" in candidate_warnings:
            return "missing_core_fields"

        if state.last_warning.startswith("ignored_stop_request"):
            return ""

        return ""

    async def _run_gap_fill_assist(self, toolbox: CopilotToolbox, state: RuntimeState) -> bool:
        client_config = SubprocessConfig(
            cwd=str(self.config.workspace_dir),
            use_logged_in_user=True,
        )

        try:
            async with CopilotClient(client_config) as client:
                async with await client.create_session(
                    model=self.config.model,
                    on_permission_request=PermissionHandler.approve_all,
                    on_user_input_request=self._on_user_input_request,
                    tools=toolbox.build_gap_fill_tools(),
                    streaming=False,
                    infinite_sessions={"enabled": True},
                ) as session:
                    waiter = SessionWaiter(self.console)
                    session.on(waiter.on_event)
                    await self._send_and_wait(
                        session,
                        waiter,
                        self._build_gap_fill_prompt(state),
                        timeout_seconds=90,
                    )
                    return True
        except TimeoutError:
            state.last_warning = "gap_fill_timeout"
            return False
        except Exception:
            state.last_warning = "gap_fill_error"
            return False

    def _build_gap_fill_prompt(self, state: RuntimeState) -> str:
        snapshot = {
            "current_page_url": state.current_page_url,
            "records_written": state.records_written,
            "consecutive_failures": state.consecutive_failures,
            "last_warning": state.last_warning,
            "selector_overrides": state.selector_overrides,
        }

        return (
            "You are in gap-fill mode for the current page only. "
            "Do not navigate pages and do not attempt to stop the run. "
            "Try to recover extraction quality by discovering/selecting better selectors, "
            "then extract and save one valid record if possible. "
            "Use only the provided tools.\n\n"
            f"State:\n{json.dumps(snapshot, ensure_ascii=True)}"
        )

    async def _send_and_wait(
        self,
        session: Any,
        waiter: SessionWaiter,
        prompt: str,
        *,
        timeout_seconds: int,
    ) -> None:
        waiter.reset()
        await session.send(prompt)
        await asyncio.wait_for(waiter.done.wait(), timeout=timeout_seconds)

    def _build_turn_prompt(self, turn: int, state: RuntimeState) -> str:
        state_snapshot = {
            "turn": turn,
            "records_written": state.records_written,
            "rejected_records": state.rejected_records,
            "next_index": state.next_index,
            "current_page_url": state.current_page_url,
            "current_page_candidates_found": state.current_page_candidates_found,
            "current_page_saved": state.current_page_saved,
            "current_page_skipped": state.current_page_skipped,
            "last_page_candidates_found": state.last_page_candidates_found,
            "last_page_saved": state.last_page_saved,
            "last_page_skipped": state.last_page_skipped,
            "pages_processed": state.pages_processed,
            "consecutive_failures": state.consecutive_failures,
            "validation_failures": state.validation_failures,
            "seen_fingerprints": len(state.seen_fingerprints),
            "captcha_detected": state.captcha_detected,
            "last_warning": state.last_warning,
            "selector_overrides": state.selector_overrides,
        }

        return (
            "Execute exactly one page extraction cycle."
            " Capture page context, detect captcha if needed, reveal answers,"
            " extract current candidate and save records for the full visible page."
            " Skip ambiguous items and continue. After page extraction, navigate next and wait for change."
            " If blocked for the full page, request selector overrides."
            " Call stop_run only for terminal conditions."
            " For end-of-pagination, call has_next_page first and only stop when has_next_page=false.\n\n"
            f"State:\n{json.dumps(state_snapshot, ensure_ascii=True)}"
        )

    async def _on_user_input_request(self, request: dict, invocation: dict) -> dict:
        question = request.get("question", "Provide input:")
        choices = request.get("choices") or []

        self.console.print(f"[magenta]copilot asks[/magenta] {question}")
        if choices:
            for idx, choice in enumerate(choices, start=1):
                self.console.print(f"  {idx}. {choice}")

        answer = await _async_input("> ")
        return {
            "answer": answer,
            "wasFreeform": True,
        }

    async def _prompt_for_login_at_start(self, browser: BrowserRuntime, state: RuntimeState) -> bool:
        self.console.print("[yellow]Manual login prompt enabled.[/yellow]")
        self.console.print("Complete login/challenge in the opened browser tab before crawling starts.")
        self.console.print("Options: continue (c), quit (q)")

        while True:
            decision = (await _async_input("Choose action (c/q): ")).strip().lower() or "c"

            if decision in {"c", "continue"}:
                state.captcha_detected = False
                state.consecutive_failures = 0
                state.last_warning = ""
                state.page_started_at_epoch = time.time()
                if browser.page and browser.page.url:
                    state.current_url = browser.page.url
                self.console.print("[green]Continuing crawl after manual login.[/green]")
                return True

            if decision in {"q", "quit"}:
                state.stop_reason = "user_requested_stop"
                self.console.print("[yellow]Run stopped before extraction.[/yellow]")
                return False

            self.console.print("[red]Invalid choice. Enter c or q.[/red]")

    async def _attempt_auto_login(self, browser: BrowserRuntime, state: RuntimeState) -> tuple[bool, bool]:
        if browser.page is None:
            return True, False

        target_after_login = self._normalized_url(state.current_url or self.config.start_url)

        auth_path = self._resolve_auth_file_path()

        host_auth = load_host_auth_config(auth_path, browser.page.url or state.current_url)
        if host_auth is None:
            self.console.print(
                "[yellow]Auto-login enabled but no matching host credentials were found. Falling back to manual continue.[/yellow]",
            )
            state.last_warning = "auto_login_not_configured"
            return True, False

        timeout_ms = max(5, int(self.config.auto_login_timeout_seconds)) * 1000
        state.notes["auto_login_host"] = host_auth.host

        try:
            if host_auth.login_url:
                await browser.open_url(host_auth.login_url)

            page = browser.page
            if page is None:
                state.last_warning = "auto_login_no_page"
                return True, False

            username_input = page.locator(host_auth.username_selector).first
            password_input = page.locator(host_auth.password_selector).first

            await username_input.wait_for(state="visible", timeout=timeout_ms)
            await username_input.fill(host_auth.username, timeout=timeout_ms)
            await password_input.fill(host_auth.password, timeout=timeout_ms)

            before_submit_url = self._normalized_url(page.url)
            submitted = False
            if host_auth.submit_selector:
                try:
                    submitted = bool(
                        await username_input.evaluate(
                            """
                            (el, selector) => {
                              const form = el && el.closest ? el.closest("form") : null;
                              const scope = form || document;
                              const button = scope.querySelector(selector);
                              if (!button) return false;
                              button.click();
                              return true;
                            }
                            """,
                            host_auth.submit_selector,
                        ),
                    )
                except Exception:
                    submitted = False

                if not submitted:
                    submit_button = page.locator(host_auth.submit_selector).first
                    await submit_button.click(timeout=timeout_ms)
                    submitted = True

            if not submitted:
                await password_input.press(host_auth.submit_key or "Enter")

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass

            success = False
            if host_auth.success_selector:
                try:
                    await page.locator(host_auth.success_selector).first.wait_for(
                        state="visible",
                        timeout=timeout_ms,
                    )
                    success = True
                except Exception:
                    success = await self._is_selector_visible(page, host_auth.success_selector)

            login_link_visible = await self._is_selector_visible(
                page,
                "a.login-btn, a[href*='/auth/login']",
            )

            if success and login_link_visible:
                success = False

            if not success and not host_auth.success_selector:
                after_submit_url = self._normalized_url(page.url)
                login_url_norm = self._normalized_url(host_auth.login_url or "")
                username_still_visible = await self._is_selector_visible(page, host_auth.username_selector)
                password_still_visible = await self._is_selector_visible(page, host_auth.password_selector)
                login_link_visible = await self._is_selector_visible(
                    page,
                    "a.login-btn, a[href*='/auth/login']",
                )

                success = (
                    bool(after_submit_url)
                    and after_submit_url != before_submit_url
                    and (not login_url_norm or after_submit_url != login_url_norm)
                ) or (not username_still_visible and not password_still_visible and not login_link_visible)

            if not success and page is not None and not self._is_auth_route(page.url):
                try:
                    success = await browser.wait_for_exam_content_ready(
                        timeout_ms=min(timeout_ms, 4500),
                    )
                except Exception:
                    success = False

            if not success and self._is_auth_route(page.url if page else "") and target_after_login:
                try:
                    await browser.open_url(target_after_login)
                    page = browser.page
                except Exception:
                    page = browser.page

                if page is not None:
                    login_link_visible = await self._is_selector_visible(
                        page,
                        "a.login-btn, a[href*='/auth/login']",
                    )
                    if host_auth.success_selector:
                        success = await self._is_selector_visible(page, host_auth.success_selector)
                        if success and login_link_visible:
                            success = False
                    else:
                        username_still_visible = await self._is_selector_visible(page, host_auth.username_selector)
                        password_still_visible = await self._is_selector_visible(page, host_auth.password_selector)
                        success = not username_still_visible and not password_still_visible and not login_link_visible

            if success:
                current_after_login = self._normalized_url(page.url if page else "")
                if target_after_login and current_after_login != target_after_login:
                    try:
                        await browser.open_url(target_after_login)
                        page = browser.page
                    except Exception:
                        pass

                if page.url:
                    state.current_url = page.url
                state.last_warning = ""
                state.notes["auto_login_succeeded"] = True
                self.console.print("[green]Auto-login succeeded.[/green]")
                return True, True

            state.notes["auto_login_succeeded"] = False
            state.last_warning = "auto_login_failed"
            self.console.print("[yellow]Auto-login could not verify success. Falling back to manual continue.[/yellow]")
            return True, False
        except Exception:
            state.notes["auto_login_succeeded"] = False
            state.last_warning = "auto_login_error"
            self.console.print("[yellow]Auto-login failed due to runtime error. Falling back to manual continue.[/yellow]")
            return True, False

    def _resolve_auth_file_path(self) -> Path:
        auth_path = self.config.auth_file_path
        if not auth_path.is_absolute():
            auth_path = (self.config.workspace_dir / auth_path).resolve()

        if auth_path.exists():
            return auth_path

        configured_path = Path(self.config.auth_file_path)
        if configured_path == DEFAULT_AUTH_FILE_PATH:
            legacy_path = (self.config.workspace_dir / LEGACY_AUTH_FILE_PATH).resolve()
            if legacy_path.exists():
                self.console.print(
                    "[yellow]Using legacy auth file path profiles/auth_hosts.yaml; migrate to auth/auth_hosts.yaml.[/yellow]",
                )
                return legacy_path

        return auth_path

    async def _is_selector_visible(self, page: Any, selector: str) -> bool:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                return False
            return await locator.is_visible()
        except Exception:
            return False

    def _normalized_url(self, url: str) -> str:
        stripped = (url or "").strip()
        if not stripped:
            return ""
        return urldefrag(stripped)[0]

    def _is_auth_route(self, url: str) -> bool:
        normalized = self._normalized_url(url).lower()
        if not normalized:
            return True
        return "/auth/login" in normalized or "/auth/callback" in normalized

    def _crawl_scope_host(self, url: str) -> str:
        normalized = self._normalized_url(url)
        if not normalized:
            return ""
        return (urlparse(normalized).netloc or "").strip().lower()

    def _crawl_scope_path_prefix(self, url: str) -> str:
        normalized = self._normalized_url(url)
        if not normalized:
            return "/"

        path = (urlparse(normalized).path or "").rstrip("/")
        if not path:
            return "/"

        segments = [segment for segment in path.split("/") if segment]
        if segments and re.search(r"\.[a-z0-9]+$", segments[-1], re.IGNORECASE):
            segments = segments[:-1]
        while segments and (
            re.fullmatch(r"\d+", segments[-1])
            or re.fullmatch(r"page-\d+", segments[-1], re.IGNORECASE)
        ):
            segments = segments[:-1]

        if not segments:
            return "/"

        return f"/{'/'.join(segments)}"

    def _is_within_crawl_scope(self, url: str, state: RuntimeState) -> bool:
        normalized = self._normalized_url(url)
        if not normalized:
            return True

        parsed = urlparse(normalized)
        target_host = (parsed.netloc or "").strip().lower()
        target_path = (parsed.path or "").rstrip("/") or "/"

        scope_host = str(state.notes.get("crawl_scope_host") or "").strip().lower()
        if scope_host and target_host and target_host != scope_host:
            return False

        scope_prefix = str(state.notes.get("crawl_scope_path_prefix") or "").strip()
        if not scope_prefix or scope_prefix == "/":
            return True

        normalized_prefix = scope_prefix.rstrip("/").lower() or "/"
        normalized_path = target_path.lower()
        return (
            normalized_path == normalized_prefix
            or normalized_path.startswith(f"{normalized_prefix}/")
        )

    async def _auto_advance_after_stale_progress(
        self,
        browser: BrowserRuntime,
        state: RuntimeState,
    ) -> bool:
        has_next = await browser.has_next_page()
        if not has_next:
            state.stop_reason = "verified_no_next_page"
            state.last_warning = "stale_auto_no_next_page"
            state.notes["last_stale_action"] = {
                "mode": "auto_headless",
                "clicked": False,
                "has_next_page": False,
            }
            return False

        previous_url = self._normalized_url(browser.page.url if browser.page else state.current_url)

        previous_fingerprint = ""
        try:
            previous_fingerprint = await browser.current_fingerprint()
        except Exception:
            previous_fingerprint = ""

        if self.config.humanize:
            await browser.maybe_human_delay(reason="stale_auto_before_next")

        clicked = await browser.click_next()
        if not clicked:
            state.consecutive_failures += 1
            state.last_warning = "stale_auto_navigation_failed"
            state.notes["last_stale_action"] = {
                "mode": "auto_headless",
                "clicked": False,
                "has_next_page": has_next,
            }
            return False

        moved = False
        if not previous_fingerprint:
            moved = True
        else:
            fingerprint_changed = await browser.wait_for_fingerprint_change(
                previous_fingerprint=previous_fingerprint,
                timeout_ms=3000,
            )
            current_url = self._normalized_url(browser.page.url if browser.page else state.current_url)
            moved = bool(fingerprint_changed or (current_url and current_url != previous_url))

        state.notes["last_stale_action"] = {
            "mode": "auto_headless",
            "clicked": True,
            "moved": moved,
        }

        if moved:
            next_url = self._normalized_url(browser.page.url if browser.page else state.current_url)
            out_of_scope = bool(next_url) and (not self._is_within_crawl_scope(next_url, state))
            state.notes["last_stale_action"]["out_of_scope"] = out_of_scope
            if out_of_scope:
                state.stop_reason = "navigation_out_of_scope"
                state.last_warning = "navigation_out_of_scope"
                state.current_url = next_url
                return False

            state.consecutive_failures = 0
            state.last_warning = "stale_auto_skip"
            state.page_started_at_epoch = time.time()
            if browser.page and browser.page.url:
                state.current_url = browser.page.url
            if self.config.humanize:
                await browser.maybe_human_read_pause(reason="stale_auto_post_navigation")
            return True

        state.consecutive_failures += 1
        state.last_warning = "stale_auto_no_change"
        return False

    async def _manual_intervention(
        self,
        browser: BrowserRuntime,
        state: RuntimeState,
        profile_store: SelectorProfileStore,
    ) -> None:
        state.user_interventions += 1

        screenshot = self.config.screenshot_dir / f"manual_{state.user_interventions:03d}.png"
        await browser.screenshot(str(screenshot))

        self.console.print("[yellow]Manual intervention required.[/yellow]")
        self.console.print(f"Screenshot: {screenshot}")
        self.console.print("Options: continue (c), override selectors (o), skip to next (s), quit (q)")

        decision = (await _async_input("Choose action (c/o/s/q): ")).strip().lower() or "c"

        if decision == "q":
            state.stop_reason = "user_requested_stop"
            return

        if decision == "s":
            await browser.click_next()
            state.page_started_at_epoch = time.time()
            state.captcha_detected = False
            state.consecutive_failures = 0
            return

        if decision == "o":
            raw = await _async_input(
                "Paste selector overrides JSON (keys: question_containers/question/options/answer/show_answer_buttons/next_buttons): ",
            )
            try:
                overrides = json.loads(raw)
                if isinstance(overrides, dict):
                    sanitized: dict[str, list[str]] = {}
                    for key, value in overrides.items():
                        if isinstance(value, str):
                            sanitized[key] = [value.strip()]
                        elif isinstance(value, list):
                            sanitized[key] = [str(item).strip() for item in value if str(item).strip()]
                    state.selector_overrides = {
                        **state.selector_overrides,
                        **sanitized,
                    }
                    if self.config.auto_learn_profiles:
                        profile_store.save_overrides(state.domain, sanitized)
            except json.JSONDecodeError:
                self.console.print("[red]Invalid JSON. Keeping previous selectors.[/red]")

        state.captcha_detected = False
        state.consecutive_failures = 0

    async def _save_checkpoint(
        self,
        browser: BrowserRuntime,
        state: RuntimeState,
        checkpoint_store: CheckpointStore,
    ) -> None:
        current_url = browser.page.url if browser.page else state.current_url
        if current_url:
            state.current_url = current_url

        try:
            if browser.page:
                state.current_fingerprint = await browser.current_fingerprint()
        except Exception:
            state.current_fingerprint = ""

        checkpoint_store.save(state, state.current_url)


async def run_crawl(config: RunConfig) -> RunSummary:
    runner = CrawlRunner(config)
    return await runner.run()
