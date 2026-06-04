from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.checkpoint import CheckpointStore
from mcq_crawler.models import RuntimeState


class CheckpointResumeTests(unittest.TestCase):
    def test_save_and_restore_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = Path(temp_dir) / "checkpoint.json"
            store = CheckpointStore(checkpoint_path)

            state = RuntimeState(max_records=50, next_index=11)
            state.records_written = 10
            state.rejected_records = 3
            state.duplicate_records = 2
            state.consecutive_failures = 1
            state.captcha_events = 4
            state.user_interventions = 5
            state.validation_failures = 6
            state.current_fingerprint = "abc123"
            state.stop_reason = "verified_no_next_page"
            state.last_warning = "ignored_stop_request:next_page_available"
            state.domain = "example.com"
            state.run_started_at_epoch = 12345.0
            state.page_started_at_epoch = 12399.5
            state.current_page_url = "https://example.com/start"
            state.current_page_candidates_found = 5
            state.current_page_saved = 4
            state.current_page_skipped = 1
            state.current_page_image_skipped = 1
            state.current_page_llm_assists = 1
            state.last_page_candidates_found = 5
            state.last_page_saved = 5
            state.last_page_skipped = 0
            state.last_page_image_skipped = 2
            state.last_page_llm_assists = 2
            state.pages_processed = 3
            state.image_based_skipped_total = 6
            state.llm_assist_attempts_total = 7
            state.llm_assist_saved_count = 3
            state.llm_assist_last_trigger_reason = "low_confidence"
            state.current_page_extraction_diagnostics = {
                "root_selector": ".exam-row",
                "raw_payload_count": 4,
            }
            state.last_page_extraction_diagnostics = {
                "root_selector": ".exam-row",
                "raw_payload_count": 5,
            }
            state.navigation_stop_snapshot = {
                "stop_reason": "verified_no_next_page",
                "last_navigation_decision": {"has_next_page": False},
            }
            state.selector_overrides = {"question": [".lead"]}
            state.seen_fingerprints = {"f1", "f2"}
            state.selector_success_counts = {
                "question": {"p.lead": 7},
            }

            store.save(state, "https://example.com/start")

            restored = RuntimeState(max_records=50, next_index=1)
            restored_url = store.restore_into(restored)

            self.assertEqual(restored_url, "https://example.com/start")
            self.assertEqual(restored.records_written, 10)
            self.assertEqual(restored.rejected_records, 3)
            self.assertEqual(restored.duplicate_records, 2)
            self.assertEqual(restored.next_index, 11)
            self.assertEqual(restored.consecutive_failures, 1)
            self.assertEqual(restored.captcha_events, 4)
            self.assertEqual(restored.user_interventions, 5)
            self.assertEqual(restored.validation_failures, 6)
            self.assertEqual(restored.current_fingerprint, "abc123")
            self.assertEqual(restored.stop_reason, "verified_no_next_page")
            self.assertEqual(restored.last_warning, "ignored_stop_request:next_page_available")
            self.assertEqual(restored.domain, "example.com")
            self.assertEqual(restored.run_started_at_epoch, 12345.0)
            self.assertEqual(restored.page_started_at_epoch, 12399.5)
            self.assertEqual(restored.current_page_url, "https://example.com/start")
            self.assertEqual(restored.current_page_candidates_found, 5)
            self.assertEqual(restored.current_page_saved, 4)
            self.assertEqual(restored.current_page_skipped, 1)
            self.assertEqual(restored.current_page_image_skipped, 1)
            self.assertEqual(restored.current_page_llm_assists, 1)
            self.assertEqual(restored.last_page_candidates_found, 5)
            self.assertEqual(restored.last_page_saved, 5)
            self.assertEqual(restored.last_page_skipped, 0)
            self.assertEqual(restored.last_page_image_skipped, 2)
            self.assertEqual(restored.last_page_llm_assists, 2)
            self.assertEqual(restored.pages_processed, 3)
            self.assertEqual(restored.image_based_skipped_total, 6)
            self.assertEqual(restored.llm_assist_attempts_total, 7)
            self.assertEqual(restored.llm_assist_saved_count, 3)
            self.assertEqual(restored.llm_assist_last_trigger_reason, "low_confidence")
            self.assertEqual(restored.current_page_extraction_diagnostics["raw_payload_count"], 4)
            self.assertEqual(restored.last_page_extraction_diagnostics["raw_payload_count"], 5)
            self.assertEqual(
                restored.navigation_stop_snapshot["last_navigation_decision"]["has_next_page"],
                False,
            )
            self.assertEqual(restored.selector_overrides["question"], [".lead"])
            self.assertIn("f1", restored.seen_fingerprints)
            self.assertEqual(restored.selector_success_counts["question"]["p.lead"], 7)


if __name__ == "__main__":
    unittest.main()
