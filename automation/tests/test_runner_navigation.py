from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.checkpoint import CheckpointStore
from mcq_crawler.config import RunConfig
from mcq_crawler.copilot_controller import CopilotToolbox
from mcq_crawler.models import ExtractionCandidate, RuntimeState
from mcq_crawler.profile_store import SelectorProfileStore
from mcq_crawler.runner import CrawlRunner
from mcq_crawler.storage import JsonlStore


def _sample_candidate() -> ExtractionCandidate:
    return ExtractionCandidate(
        question="Which service provides object storage?",
        option_texts=[
            "A. Amazon EC2",
            "B. Amazon EBS",
            "C. Amazon S3",
            "D. Amazon RDS",
        ],
        answer_text="Answer(s): C",
        confidence=0.95,
        quality_score=0.95,
        warnings=[],
        used_selectors={},
    )


class _StubBrowser:
    def __init__(
        self,
        *,
        has_next_page: bool,
        click_next_result: bool,
        fingerprint_changed: bool,
        next_url_after_click: str = "",
    ) -> None:
        self.page = SimpleNamespace(
            url="https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
        )
        self._has_next_page = has_next_page
        self._click_next_result = click_next_result
        self._fingerprint_changed = fingerprint_changed
        self._next_url_after_click = next_url_after_click
        self.click_calls = 0
        self.human_delay_calls = 0
        self.human_read_pause_calls = 0
        self.human_idle_break_calls = 0

    async def detect_captcha(self) -> bool:
        return False

    async def ensure_browse_mode_ready(self) -> bool:
        return False

    async def wait_for_exam_content_ready(self, timeout_ms: int = 4500) -> bool:
        return True

    async def reveal_answer(self) -> bool:
        return True

    async def extract_page_candidates(self, max_candidates: int = 20) -> list[ExtractionCandidate]:
        return [_sample_candidate()]

    async def extract_candidate(self) -> ExtractionCandidate:
        return _sample_candidate()

    async def has_next_page(self) -> bool:
        return self._has_next_page

    async def current_fingerprint(self) -> str:
        return "fingerprint-before-next"

    async def click_next(self) -> bool:
        self.click_calls += 1
        if self._click_next_result and self._next_url_after_click:
            self.page.url = self._next_url_after_click
        return self._click_next_result

    async def wait_for_fingerprint_change(self, previous_fingerprint: str, timeout_ms: int = 7000) -> bool:
        return self._fingerprint_changed

    async def screenshot(self, path: str) -> str:
        return path

    async def maybe_human_delay(self, reason: str = "action") -> None:
        self.human_delay_calls += 1

    async def maybe_human_read_pause(self, reason: str = "read_pause") -> None:
        self.human_read_pause_calls += 1

    async def maybe_human_idle_break(self, reason: str = "idle_break") -> None:
        self.human_idle_break_calls += 1


class _StubAuthLocator:
    def __init__(
        self,
        *,
        visible: bool = True,
        count: int = 1,
        evaluate_result: bool = False,
    ) -> None:
        self._visible = visible
        self._count = count
        self._evaluate_result = evaluate_result
        self.fill_calls: list[str] = []
        self.clicked = False

    @property
    def first(self) -> "_StubAuthLocator":
        return self

    async def wait_for(self, *, state: str = "visible", timeout: int = 0) -> None:
        return None

    async def fill(self, value: str, timeout: int = 0) -> None:
        self.fill_calls.append(value)

    async def evaluate(self, script: str, selector: str) -> bool:
        return self._evaluate_result

    async def click(self, timeout: int = 0) -> None:
        self.clicked = True

    async def press(self, key: str) -> None:
        self.clicked = True

    async def count(self) -> int:
        return self._count

    async def is_visible(self) -> bool:
        return self._visible


class _StubAuthPage:
    def __init__(self, url: str) -> None:
        self.url = url
        self._locators: dict[str, _StubAuthLocator] = {}

    def set_locator(self, selector: str, locator: _StubAuthLocator) -> None:
        self._locators[selector] = locator

    def locator(self, selector: str) -> _StubAuthLocator:
        return self._locators.get(selector, _StubAuthLocator(visible=False, count=0))

    async def wait_for_load_state(self, state: str = "domcontentloaded", timeout: int = 0) -> None:
        return None


class _StubAutoLoginBrowser:
    def __init__(self, initial_url: str) -> None:
        self.page = _StubAuthPage(initial_url)
        self.opened_urls: list[str] = []

    async def open_url(self, url: str) -> str:
        self.opened_urls.append(url)
        self.page.url = url
        return url


class RunnerNavigationTests(unittest.IsolatedAsyncioTestCase):
    def test_is_auth_route_detects_callback_and_login_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = RunConfig(
                start_url="https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
            )

            runner = CrawlRunner(config)

            self.assertTrue(runner._is_auth_route("https://examcademy.com/auth/login?returnTo=/x"))
            self.assertTrue(runner._is_auth_route("https://examcademy.com/auth/callback?code=abc"))
            self.assertFalse(runner._is_auth_route("https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1"))

    async def test_attempt_auto_login_redirects_back_to_start_url_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            start_url = "https://examcademy.com/exams/amazon/aws-certified-solutions-architect-associate-saa-c03/1"
            config = RunConfig(
                start_url=start_url,
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
            )

            runner = CrawlRunner(config)
            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.current_url = start_url

            browser = _StubAutoLoginBrowser(start_url)

            username_selector = "input[name='username']"
            password_selector = "input[name='password']"
            success_selector = "a[href*='/logout']"
            login_link_selector = "a.login-btn, a[href*='/auth/login']"

            browser.page.set_locator(username_selector, _StubAuthLocator(evaluate_result=True))
            browser.page.set_locator(password_selector, _StubAuthLocator())
            browser.page.set_locator(success_selector, _StubAuthLocator())
            browser.page.set_locator(login_link_selector, _StubAuthLocator(visible=False, count=0))

            host_auth = SimpleNamespace(
                host="examcademy.com",
                login_url="https://examcademy.com/auth/login",
                username_selector=username_selector,
                password_selector=password_selector,
                submit_selector="button[type='submit']",
                success_selector=success_selector,
                username="test-user",
                password="test-pass",
                submit_key="Enter",
            )

            with patch("mcq_crawler.runner.load_host_auth_config", return_value=host_auth):
                attempted, succeeded = await runner._attempt_auto_login(browser, state)

            self.assertTrue(attempted)
            self.assertTrue(succeeded)
            self.assertEqual(browser.opened_urls, ["https://examcademy.com/auth/login", start_url])
            self.assertEqual(state.current_url, start_url)
            self.assertTrue(state.notes.get("auto_login_succeeded"))

    async def _run_once(
        self,
        *,
        has_next_page: bool,
        click_next_result: bool,
        fingerprint_changed: bool,
        humanize: bool = False,
        next_url_after_click: str = "",
    ) -> tuple[RuntimeState, _StubBrowser]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            config = RunConfig(
                start_url="https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
                max_records=50,
                max_turns=1,
                navigation_retry_limit=1,
                humanize=humanize,
                selector_debug=False,
            )

            runner = CrawlRunner(config)
            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.domain = "www.examtopics.com"
            state.current_url = config.start_url

            browser = _StubBrowser(
                has_next_page=has_next_page,
                click_next_result=click_next_result,
                fingerprint_changed=fingerprint_changed,
                next_url_after_click=next_url_after_click,
            )

            store = JsonlStore(config.output_path, config.error_path)
            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=config.screenshot_dir,
                min_confidence=config.min_confidence,
                min_quality_score=config.min_quality_score,
                require_answers=config.require_answers,
                selector_debug=config.selector_debug,
            )
            profile_store = SelectorProfileStore(config.domain_profiles_dir)
            checkpoint_store = CheckpointStore(config.checkpoint_path)

            await runner._run_deterministic_loop(
                browser=browser,
                state=state,
                profile_store=profile_store,
                checkpoint_store=checkpoint_store,
                toolbox=toolbox,
            )

            return state, browser

    async def test_fallback_click_next_allows_progress_when_has_next_page_is_false(self) -> None:
        state, browser = await self._run_once(
            has_next_page=False,
            click_next_result=True,
            fingerprint_changed=True,
        )

        self.assertEqual(browser.click_calls, 1)
        self.assertEqual(state.records_written, 1)
        self.assertEqual(state.stop_reason, "turn_limit_reached")

    async def test_verified_no_next_page_when_no_pagination_and_no_navigation_movement(self) -> None:
        state, browser = await self._run_once(
            has_next_page=False,
            click_next_result=False,
            fingerprint_changed=False,
        )

        self.assertEqual(browser.click_calls, 1)
        self.assertEqual(state.records_written, 1)
        self.assertEqual(state.stop_reason, "verified_no_next_page")

    async def test_navigation_url_change_counts_as_success(self) -> None:
        state, browser = await self._run_once(
            has_next_page=False,
            click_next_result=True,
            fingerprint_changed=False,
            next_url_after_click=(
                "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/2/"
            ),
        )

        self.assertEqual(browser.click_calls, 1)
        self.assertEqual(state.records_written, 1)
        self.assertEqual(state.stop_reason, "turn_limit_reached")

    async def test_navigation_out_of_scope_stops_run(self) -> None:
        state, browser = await self._run_once(
            has_next_page=False,
            click_next_result=True,
            fingerprint_changed=True,
            next_url_after_click="https://www.examtopics.com/features/modes",
        )

        self.assertEqual(browser.click_calls, 1)
        self.assertEqual(state.records_written, 1)
        self.assertEqual(state.stop_reason, "navigation_out_of_scope")
        self.assertEqual(state.current_url, "https://www.examtopics.com/features/modes")
        self.assertTrue(state.notes.get("last_navigation_decision", {}).get("out_of_scope"))

    async def test_humanize_mode_invokes_browser_pacing_hooks(self) -> None:
        state, browser = await self._run_once(
            has_next_page=False,
            click_next_result=True,
            fingerprint_changed=True,
            humanize=True,
        )

        self.assertEqual(state.stop_reason, "turn_limit_reached")
        self.assertGreater(browser.human_delay_calls, 0)
        self.assertGreater(browser.human_read_pause_calls, 0)

    async def test_attempt_save_candidate_skips_hybrid_assist_when_stop_reason_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            config = RunConfig(
                start_url="https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
                max_records=50,
                max_turns=1,
                orchestration_mode="hybrid_gap_fill",
                selector_debug=False,
            )

            runner = CrawlRunner(config)
            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.current_page_url = config.start_url
            state.current_url = config.start_url

            class _StopToolbox:
                def __init__(self, runtime_state: RuntimeState) -> None:
                    self.state = runtime_state

                def _save_candidate_record(self, **_: object) -> tuple[bool, str, dict[str, object]]:
                    self.state.stop_reason = "answer_extraction_failed"
                    return False, "stopped", {}

            toolbox = _StopToolbox(state)

            await runner._attempt_save_candidate(toolbox, _sample_candidate())

            self.assertEqual(state.stop_reason, "answer_extraction_failed")
            self.assertEqual(state.llm_assist_attempts_total, 0)
            self.assertEqual(state.current_page_llm_assists, 0)

    async def test_headless_mode_auto_handles_stale_progress_without_manual_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            config = RunConfig(
                start_url="https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
                max_records=50,
                max_turns=5,
                navigation_retry_limit=1,
                headless=True,
                selector_debug=False,
            )

            runner = CrawlRunner(config)
            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.domain = "www.examtopics.com"
            state.current_url = config.start_url

            browser = _StubBrowser(
                has_next_page=True,
                click_next_result=True,
                fingerprint_changed=True,
            )

            store = JsonlStore(config.output_path, config.error_path)
            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=config.screenshot_dir,
                min_confidence=config.min_confidence,
                min_quality_score=config.min_quality_score,
                require_answers=config.require_answers,
                selector_debug=config.selector_debug,
            )
            profile_store = SelectorProfileStore(config.domain_profiles_dir)
            checkpoint_store = CheckpointStore(config.checkpoint_path)

            async def _fail_manual_intervention(*_: object, **__: object) -> None:
                raise AssertionError("manual intervention should not run in headless stale handling")

            runner._manual_intervention = _fail_manual_intervention  # type: ignore[method-assign]

            await runner._run_deterministic_loop(
                browser=browser,
                state=state,
                profile_store=profile_store,
                checkpoint_store=checkpoint_store,
                toolbox=toolbox,
            )

            self.assertEqual(state.user_interventions, 0)
            self.assertEqual(state.stop_reason, "turn_limit_reached")
            self.assertEqual(state.last_warning, "stale_auto_skip")
            self.assertEqual(state.notes.get("last_stale_action", {}).get("mode"), "auto_headless")

    async def test_non_question_mode_switcher_candidate_is_skipped_without_strict_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            config = RunConfig(
                start_url="https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/2",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
                stop_on_missing_answers=True,
                require_answers=True,
            )

            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.current_url = config.start_url

            browser = _StubBrowser(
                has_next_page=True,
                click_next_result=True,
                fingerprint_changed=True,
            )
            browser.page.url = config.start_url

            store = JsonlStore(config.output_path, config.error_path)
            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=config.screenshot_dir,
                min_confidence=config.min_confidence,
                min_quality_score=config.min_quality_score,
                require_answers=config.require_answers,
                stop_on_missing_answers=config.stop_on_missing_answers,
                selector_debug=config.selector_debug,
            )

            saved, message, _ = toolbox._save_candidate_record(
                question="Choose how you want to study this exam. About study modes →",
                options={
                    "A": "Exams /",
                    "B": "Amazon /",
                    "C": "AWS Certified Cloud Practitioner",
                },
                answers=[],
                extracted_answer_text="",
                confidence_value=0.8,
                used_selectors={
                    "question": "p.mode-switcher-subtitle",
                    "options": "li.Breadcrumb_item__ZND9U",
                },
            )

            self.assertFalse(saved)
            self.assertEqual(message, "Non-question candidate skipped.")
            self.assertEqual(state.stop_reason, "")
            self.assertEqual(state.last_warning, "non_question_candidate")

    async def test_empty_candidate_is_skipped_without_strict_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            config = RunConfig(
                start_url="https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/2",
                domain_profiles_dir=tmp_dir / "profiles" / "domains",
                output_path=tmp_dir / "output" / "records.jsonl",
                error_path=tmp_dir / "output" / "errors.jsonl",
                checkpoint_path=tmp_dir / "output" / "checkpoint.json",
                screenshot_dir=tmp_dir / "output" / "screenshots",
                workspace_dir=tmp_dir,
                stop_on_missing_answers=True,
                require_answers=True,
            )

            state = RuntimeState(max_records=config.max_records, next_index=1)
            state.current_url = config.start_url

            browser = _StubBrowser(
                has_next_page=True,
                click_next_result=True,
                fingerprint_changed=True,
            )
            browser.page.url = config.start_url

            store = JsonlStore(config.output_path, config.error_path)
            toolbox = CopilotToolbox(
                browser=browser,
                store=store,
                state=state,
                screenshot_dir=config.screenshot_dir,
                min_confidence=config.min_confidence,
                min_quality_score=config.min_quality_score,
                require_answers=config.require_answers,
                stop_on_missing_answers=config.stop_on_missing_answers,
                selector_debug=config.selector_debug,
            )

            saved, message, _ = toolbox._save_candidate_record(
                question="",
                options={},
                answers=[],
                extracted_answer_text="",
                confidence_value=0.0,
                used_selectors={},
            )

            self.assertFalse(saved)
            self.assertEqual(message, "Non-question candidate skipped.")
            self.assertEqual(state.stop_reason, "")
            self.assertEqual(state.last_warning, "non_question_candidate")



if __name__ == "__main__":
    unittest.main()