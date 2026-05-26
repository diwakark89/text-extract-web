from __future__ import annotations

import unittest
from pathlib import Path
import sys

from playwright.async_api import Error as PlaywrightError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.browser import _is_transient_page_evaluate_error


class BrowserRuntimeErrorTests(unittest.TestCase):
    def test_detects_navigation_context_destroyed_error(self) -> None:
        exc = PlaywrightError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        self.assertTrue(_is_transient_page_evaluate_error(exc))

    def test_ignores_non_transient_playwright_error(self) -> None:
        exc = PlaywrightError("Page.evaluate: Unexpected token ')' while parsing")
        self.assertFalse(_is_transient_page_evaluate_error(exc))

    def test_ignores_non_playwright_error_even_with_matching_text(self) -> None:
        exc = RuntimeError("Execution context was destroyed")
        self.assertFalse(_is_transient_page_evaluate_error(exc))


if __name__ == "__main__":
    unittest.main()