from __future__ import annotations

import unittest
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.browser import BrowserRuntime, options_to_map, parse_answer_letters
from mcq_crawler.config import RunConfig
from mcq_crawler.models import RuntimeState
from mcq_crawler.config import DEFAULT_SELECTOR_PROFILE
from mcq_crawler.profile_store import SelectorProfileStore


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

    async def test_extract_page_candidates_materializes_lazy_loaded_questions(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "lazy_loaded_25_questions.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        candidates = await self.runtime.extract_page_candidates()

        self.assertEqual(len(candidates), 25)
        self.assertIn("Lazy fixture question 25", candidates[-1].question)

    async def test_extract_page_candidates_scans_virtualized_rows(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "virtualized_exam_rows.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [".question-content > p"]
        self.runtime.state.selector_overrides["options"] = [".question-content .mc-question > ul > li.mc-option"]
        self.runtime.state.selector_overrides["answer"] = [".question-content .mc-question .correct-answer"]

        candidates = await self.runtime.extract_page_candidates(max_candidates=40)

        self.assertEqual(len(candidates), 25)
        self.assertIn("Virtualized question 25", candidates[-1].question)

    async def test_extract_page_candidates_scans_rows_added_mid_scan(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "rows_added_during_scan.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [".question-content > p"]
        self.runtime.state.selector_overrides["options"] = [".question-content .mc-question > ul > li.mc-option"]
        self.runtime.state.selector_overrides["answer"] = [".question-content .mc-question .correct-answer"]

        candidates = await self.runtime.extract_page_candidates(max_candidates=40)

        self.assertEqual(len(candidates), 25)
        self.assertIn("Deferred row question 25", candidates[-1].question)

    async def test_extract_page_candidates_waits_for_delayed_bottom_growth(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "delayed_bottom_growth.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [".question-content > p"]
        self.runtime.state.selector_overrides["options"] = [".question-content .mc-question > ul > li.mc-option"]
        self.runtime.state.selector_overrides["answer"] = [".question-content .mc-question .correct-answer"]

        candidates = await self.runtime.extract_page_candidates(max_candidates=40)

        self.assertEqual(len(candidates), 25)
        self.assertIn("Delayed growth question 25", candidates[-1].question)

    async def test_extract_page_candidates_waits_for_slow_delayed_bottom_growth(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "slow_delayed_bottom_growth.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [".question-content > p"]
        self.runtime.state.selector_overrides["options"] = [".question-content .mc-question > ul > li.mc-option"]
        self.runtime.state.selector_overrides["answer"] = [".question-content .mc-question .correct-answer"]

        candidates = await self.runtime.extract_page_candidates(max_candidates=40)

        self.assertEqual(len(candidates), 25)
        self.assertIn("Slow delayed growth question 25", candidates[-1].question)

    async def test_extract_page_candidates_keeps_single_valid_container(self) -> None:
        fixture = (
            PROJECT_ROOT / "tests" / "fixtures" / "single_question_container_with_noise.html"
        ).resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [
            ".question-content > p",
            "p.mode-switcher-subtitle",
        ]
        self.runtime.state.selector_overrides["options"] = [
            ".question-content .mc-question > ul > li.mc-option",
            "li.Breadcrumb_item__ZND9U",
        ]
        self.runtime.state.selector_overrides["answer"] = [
            ".question-content .mc-question li.mc-option.mc-option-missed",
        ]

        candidates = await self.runtime.extract_page_candidates(max_candidates=3)

        self.assertEqual(len(candidates), 1)
        self.assertIn("stores files as objects", candidates[0].question)
        self.assertEqual(
            candidates[0].used_selectors.get("question"),
            ".question-content > p",
        )
        self.assertEqual(
            candidates[0].used_selectors.get("options"),
            ".question-content .mc-question > ul > li.mc-option",
        )

    async def test_extract_page_candidates_handles_examcademy_current_markup(self) -> None:
        fixture = (
            PROJECT_ROOT / "tests" / "fixtures" / "examcademy_current_markup.html"
        ).resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [
            "[class*='question']",
            ".question-content > p",
        ]
        self.runtime.state.selector_overrides["options"] = [
            "[class*='option']",
            ".question-content .mc-question > ul > li.mc-option",
        ]
        self.runtime.state.selector_overrides["answer"] = [
            "strong",
            ".question-content .mc-question > ul > li.mc-option.mc-option-missed",
        ]

        candidates = await self.runtime.extract_page_candidates(max_candidates=10)

        self.assertEqual(len(candidates), 3)
        expected_option_counts = [5, 6, 5]
        for candidate, expected_count in zip(candidates, expected_option_counts):
            joined_options = " ".join(candidate.option_texts)
            self.assertEqual(len(candidate.option_texts), expected_count)
            self.assertNotIn("Report a problem", joined_options)
            self.assertNotIn("Save question", joined_options)
            self.assertNotIn("Ask AstroTutor", joined_options)
            for option in candidate.option_texts:
                self.assertNotIn("\n", option)

        first = candidates[0]
        first_options = options_to_map(first.option_texts)
        self.assertIn("hybrid IT setup", first.question)
        self.assertIn("Which combination of steps", first.question)
        self.assertIn("\n\nWhich combination of steps", first.question)
        self.assertNotIn("Save question", first.question)
        self.assertEqual(
            first_options["A"],
            "Create a new Site-to-Site VPN tunnel for the IPv6 traffic.",
        )
        self.assertEqual(first_options["D"], "Add a new IPv6 peer in the existing VIF.")
        self.assertEqual(parse_answer_letters(first.answer_text), ["A", "D"])

        self.assertEqual(parse_answer_letters(candidates[1].answer_text), ["A", "B", "E"])
        self.assertEqual(parse_answer_letters(candidates[2].answer_text), ["B", "E"])

    async def test_extract_page_candidates_tracks_image_based_skip_counts(self) -> None:
        fixture = (
            PROJECT_ROOT / "tests" / "fixtures" / "image_only_question_with_valid_sibling.html"
        ).resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.runtime.state.selector_overrides["question_containers"] = ["div.exam-row"]
        self.runtime.state.selector_overrides["question"] = [".question-content > p"]
        self.runtime.state.selector_overrides["options"] = [".question-content .mc-question > li.mc-option"]
        self.runtime.state.selector_overrides["answer"] = [".question-content .correct-answer"]

        candidates = await self.runtime.extract_page_candidates(max_candidates=5)

        self.assertEqual(len(candidates), 1)
        diagnostics = self.runtime.state.current_page_extraction_diagnostics
        skip_reasons = diagnostics.get("scanned_root_skip_reasons", {})
        self.assertEqual(skip_reasons.get("image_based_question"), 1)
        self.assertEqual(skip_reasons.get("image_based_options"), None)
        self.assertEqual(diagnostics.get("image_based_question_skipped_candidates"), 1)
        self.assertEqual(diagnostics.get("image_based_options_skipped_candidates"), 0)
        self.assertEqual(diagnostics.get("image_based_skipped_candidates"), 1)

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

    async def test_has_next_page_false_for_numbered_previous_only(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "numbered_path_nav" / "3.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        self.assertFalse(await self.runtime.has_next_page())

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

    async def test_click_next_ignores_numbered_previous_only_links(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "numbered_path_nav" / "3.html").resolve().as_uri()
        await self.runtime.open_url(fixture)

        clicked = await self.runtime.click_next()
        self.assertFalse(clicked)
        self.assertRegex(self.runtime.page.url, r"/numbered_path_nav/3\.html$")

    async def test_click_next_ignores_off_scope_arrow_link(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "off_scope_only_next_arrow.html").resolve().as_uri()
        await self.runtime.open_url(fixture)
        self.runtime.state.notes["crawl_scope_path_prefix"] = "/exams/amazon/aws-certified-solutions-architect-associate-saa-c03"

        clicked = await self.runtime.click_next()

        self.assertFalse(clicked)
        self.assertRegex(self.runtime.page.url, r"/off_scope_only_next_arrow\.html$")

    async def test_has_next_page_records_skipped_candidate_details(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "fixtures" / "off_scope_only_next_arrow.html").resolve().as_uri()
        await self.runtime.open_url(fixture)
        self.runtime.state.notes["crawl_scope_path_prefix"] = "/exams/amazon/aws-certified-solutions-architect-associate-saa-c03"

        has_next = await self.runtime.has_next_page()

        self.assertFalse(has_next)
        snapshot = self.runtime.state.notes.get("last_next_candidates", {})
        top_skipped = snapshot.get("top_skipped", [])
        self.assertTrue(top_skipped)
        self.assertEqual(top_skipped[0].get("reason"), "out_of_scope")


class SelectorProfileStoreTests(unittest.TestCase):
    def test_record_selector_success_ignores_broad_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SelectorProfileStore(Path(temp_dir))

            store.record_selector_success("examcademy.com", "question", "[class*='question']")
            store.record_selector_success("examcademy.com", "options", "[class*='option']")
            store.record_selector_success("examcademy.com", "answer", "strong")
            store.record_selector_success("examcademy.com", "question", ".question-content > p")

            profile = store._load_profile_map("examcademy.com")

            self.assertEqual(profile.get("question"), [".question-content > p"])
            self.assertNotIn("options", profile)
            self.assertNotIn("answer", profile)


if __name__ == "__main__":
    unittest.main()
