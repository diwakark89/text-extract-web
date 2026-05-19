from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from rich.console import Console

from .browser import BrowserRuntime
from .checkpoint import CheckpointStore
from .config import RunConfig, domain_from_url, load_selector_profile
from .copilot_controller import CopilotToolbox
from .models import RunSummary, RuntimeState
from .profile_store import SelectorProfileStore
from .storage import JsonlStore

try:
    from copilot import CopilotClient, SubprocessConfig
    from copilot.generated.session_events import AssistantMessageData, SessionIdleData
    from copilot.session import PermissionHandler
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "copilot-sdk is required. Install dependencies in automation/ first.",
    ) from exc


SYSTEM_PROMPT = """
You are an MCQ extraction controller operating browser tools.

Objectives:
1) Extract one high-quality MCQ record at a time.
2) Save valid records via save_current_record.
3) Navigate to next item and continue.
4) Stop if blocked, low confidence persists, or max records reached.

Rules:
- Always start by checking captcha status and page context when uncertain.
- Use reveal_answer before extracting if answer is hidden.
- If extraction confidence is low or validation fails repeatedly, ask for selector overrides or stop.
- Do not invent question/answer content. Use tool results only.
""".strip()


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

        selector_profile = profile_store.merge_with_domain(
            base_selector_profile,
            state.domain,
        )

        store = JsonlStore(
            self.config.output_path,
            self.config.error_path,
            debug_path=(self.config.debug_output_path if self.config.selector_debug else None),
        )

        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)

        async with BrowserRuntime(self.config, selector_profile, state) as browser:
            await browser.open_url(target_url)

            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=self.config.screenshot_dir,
                min_confidence=self.config.min_confidence,
                min_quality_score=self.config.min_quality_score,
                require_answers=self.config.require_answers,
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

                    await self._send_and_wait(session, waiter, SYSTEM_PROMPT)

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
                            await self._send_and_wait(session, waiter, prompt)
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

    async def _send_and_wait(self, session: Any, waiter: SessionWaiter, prompt: str) -> None:
        waiter.reset()
        await session.send(prompt)
        await asyncio.wait_for(waiter.done.wait(), timeout=120)

    def _build_turn_prompt(self, turn: int, state: RuntimeState) -> str:
        state_snapshot = {
            "turn": turn,
            "records_written": state.records_written,
            "rejected_records": state.rejected_records,
            "next_index": state.next_index,
            "consecutive_failures": state.consecutive_failures,
            "validation_failures": state.validation_failures,
            "seen_fingerprints": len(state.seen_fingerprints),
            "captcha_detected": state.captcha_detected,
            "last_warning": state.last_warning,
            "selector_overrides": state.selector_overrides,
        }

        return (
            "Execute exactly one extraction cycle."
            " Capture page context, detect captcha if needed, reveal answer if needed,"
            " extract candidate, save valid record, navigate next, and wait for change."
            " If blocked, request selector overrides or call stop_run.\n\n"
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
        self.console.print("Options: [c]aptcha solved, [o]verride selectors, [s]kip to next, [q]uit")

        decision = (await _async_input("Choose action [c/o/s/q]: ")).strip().lower() or "c"

        if decision == "q":
            state.stop_reason = "user_requested_stop"
            return

        if decision == "s":
            await browser.click_next()
            state.captcha_detected = False
            state.consecutive_failures = 0
            return

        if decision == "o":
            raw = await _async_input(
                "Paste selector overrides JSON (keys: question/options/answer/show_answer_buttons/next_buttons): ",
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
