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


if __name__ == "__main__":
    unittest.main()
