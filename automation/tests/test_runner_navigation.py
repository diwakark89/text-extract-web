from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace

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

    async def detect_captcha(self) -> bool:
        return False

    async def reveal_answer(self) -> bool:
        return True

    async def extract_page_candidates(self) -> list[ExtractionCandidate]:
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


class RunnerNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def _run_once(
        self,
        *,
        has_next_page: bool,
        click_next_result: bool,
        fingerprint_changed: bool,
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


if __name__ == "__main__":
    unittest.main()