from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.browser import BrowserRuntime, parse_answer_letters
from mcq_crawler.config import RunConfig
from mcq_crawler.models import RuntimeState
from mcq_crawler.config import DEFAULT_SELECTOR_PROFILE


class BrowserFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.state = RuntimeState(max_records=20, next_index=1)
        self.config = RunConfig(
            start_url="about:blank",
            headless=True,
            max_records=20,
            max_turns=20,
        )
        self.runtime = BrowserRuntime(self.config, DEFAULT_SELECTOR_PROFILE, self.state)
        try:
            await self.runtime.start()
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"Playwright browser unavailable: {exc}")

    async def asyncTearDown(self) -> None:
        await self.runtime.stop()

    async def test_hidden_answer_fixture_reveal_then_extract(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "hidden_content.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        before = await self.runtime.extract_candidate()
        self.assertTrue(before.question)
        self.assertGreaterEqual(len(before.option_texts), 3)
        before_letters = parse_answer_letters(before.answer_text)
        self.assertTrue(before.answer_text == "" or before_letters == ["A"])

        clicked = await self.runtime.reveal_answer()
        self.assertTrue(clicked)

        after = await self.runtime.extract_candidate()
        self.assertIn("Answer(s):", after.answer_text)
        self.assertEqual(parse_answer_letters(after.answer_text), ["A"])

    async def test_multi_answer_fixture_extracts_two_answers(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "multi_answer.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        candidate = await self.runtime.extract_candidate()
        self.assertIn("Choose two", candidate.question)
        self.assertGreaterEqual(len(candidate.option_texts), 5)
        self.assertEqual(parse_answer_letters(candidate.answer_text), ["B", "E"])

    async def test_extract_page_candidates_from_tabpanels(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "multi_question_tabpanels.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        candidates = await self.runtime.extract_page_candidates()

        self.assertEqual(len(candidates), 5)
        self.assertIn("Question one", candidates[0].question)
        self.assertEqual(parse_answer_letters(candidates[1].answer_text), ["A", "B"])
        self.assertGreaterEqual(len(candidates[2].option_texts), 4)

    async def test_extract_page_candidates_respects_max_candidates(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "multi_question_tabpanels.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        candidates = await self.runtime.extract_page_candidates(max_candidates=3)

        self.assertEqual(len(candidates), 3)

    async def test_reveal_answer_deduplicates_overlapping_selectors(self) -> None:
        fixture = (
            PROJECT_ROOT / "tests" / "fixtures" / "reveal_toggle_duplicate_selectors.html"
        ).resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["show_answer_buttons"] = [
            "a.reveal-solution",
            "a[data-toggle='collapse'][href*='answerQ']",
        ]

        clicked = await self.runtime.reveal_answer()
        self.assertTrue(clicked)

        candidate = await self.runtime.extract_candidate()
        self.assertIn("Answer(s):", candidate.answer_text)
        self.assertEqual(parse_answer_letters(candidate.answer_text), ["C"])

    async def test_has_next_page_true_for_site_pagination_link(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "pagination_signals.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.assertTrue(await self.runtime.has_next_page())

    async def test_has_next_page_false_for_question_only_next(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "question_only_next.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.assertFalse(await self.runtime.has_next_page())

    async def test_has_next_page_true_for_next_questions_view_link(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "next_questions_view_link.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.assertTrue(await self.runtime.has_next_page())

    async def test_has_next_page_true_for_numbered_sibling_paths(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "numbered_path_nav" / "1.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.assertTrue(await self.runtime.has_next_page())

    async def test_click_next_prefers_page_navigation_over_next_question(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "pagination_signals.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        clicked = await self.runtime.click_next()
        self.assertTrue(clicked)
        self.assertIn("question_only_next.html?page=3", self.runtime.page.url)

    async def test_click_next_prefers_numbered_sibling_path_over_question_next(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "numbered_path_nav" / "1.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        clicked = await self.runtime.click_next()
        self.assertTrue(clicked)
        self.assertRegex(self.runtime.page.url, r"/numbered_path_nav/(2|3)\.html$")


if __name__ == "__main__":
    unittest.main()
