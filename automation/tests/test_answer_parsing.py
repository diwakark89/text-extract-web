from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.browser import parse_answer_letters


class MultiAnswerParsingTests(unittest.TestCase):
    def test_parse_comma_separated_answers(self) -> None:
        self.assertEqual(parse_answer_letters("Answer(s): B,E"), ["B", "E"])

    def test_parse_compact_answers(self) -> None:
        self.assertEqual(parse_answer_letters("Correct Answer: AE"), ["A", "E"])

    def test_parse_and_connector(self) -> None:
        self.assertEqual(parse_answer_letters("B and D"), ["B", "D"])


if __name__ == "__main__":
    unittest.main()
