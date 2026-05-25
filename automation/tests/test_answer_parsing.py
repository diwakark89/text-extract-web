from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.browser import parse_answer_letters, _select_single_question_option_block


class MultiAnswerParsingTests(unittest.TestCase):
    def test_parse_comma_separated_answers(self) -> None:
        self.assertEqual(parse_answer_letters("Answer(s): B,E"), ["B", "E"])

    def test_parse_compact_answers(self) -> None:
        self.assertEqual(parse_answer_letters("Correct Answer: AE"), ["A", "E"])

    def test_parse_and_connector(self) -> None:
        self.assertEqual(parse_answer_letters("B and D"), ["B", "D"])

    def test_parse_leading_option_label_from_full_option_text(self) -> None:
        self.assertEqual(parse_answer_letters("D All upfront payment"), ["D"])

    def test_select_single_question_option_block_from_over_collected_list(self) -> None:
        over_collected = [
            "A. Compute",
            "B. Storage",
            "C. Database",
            "D. Networking",
            "A. Red",
            "B. Green",
            "C. Blue",
            "D. Yellow",
        ]
        self.assertEqual(
            _select_single_question_option_block(over_collected),
            [
                "A. Compute",
                "B. Storage",
                "C. Database",
                "D. Networking",
            ],
        )

    def test_select_single_question_option_block_returns_empty_when_unstructured(self) -> None:
        noisy = [f"Option {idx}" for idx in range(1, 20)]
        self.assertEqual(_select_single_question_option_block(noisy), [])


if __name__ == "__main__":
    unittest.main()
