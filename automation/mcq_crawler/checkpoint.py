from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import RuntimeState


class CheckpointStore:
    def __init__(self, checkpoint_path: Path) -> None:
        self.checkpoint_path = checkpoint_path
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict | None:
        if not self.checkpoint_path.exists():
            return None

        try:
            raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        if not isinstance(raw, dict):
            return None
        return raw

    def save(self, state: RuntimeState, current_url: str) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "current_url": current_url,
            "current_fingerprint": state.current_fingerprint,
            "stop_reason": state.stop_reason,
            "last_warning": state.last_warning,
            "records_written": state.records_written,
            "max_records": state.max_records,
            "rejected_records": state.rejected_records,
            "duplicate_records": state.duplicate_records,
            "next_index": state.next_index,
            "consecutive_failures": state.consecutive_failures,
            "captcha_events": state.captcha_events,
            "user_interventions": state.user_interventions,
            "validation_failures": state.validation_failures,
            "selector_overrides": state.selector_overrides,
            "seen_fingerprints": sorted(state.seen_fingerprints),
            "selector_success_counts": state.selector_success_counts,
            "domain": state.domain,
            "run_started_at_epoch": state.run_started_at_epoch,
            "page_started_at_epoch": state.page_started_at_epoch,
            "current_page_url": state.current_page_url,
            "current_page_candidates_found": state.current_page_candidates_found,
            "current_page_saved": state.current_page_saved,
            "current_page_skipped": state.current_page_skipped,
            "last_page_candidates_found": state.last_page_candidates_found,
            "last_page_saved": state.last_page_saved,
            "last_page_skipped": state.last_page_skipped,
            "pages_processed": state.pages_processed,
        }
        self.checkpoint_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def restore_into(self, state: RuntimeState) -> str | None:
        snapshot = self.load()
        if snapshot is None:
            return None

        state.records_written = int(snapshot.get("records_written", state.records_written))
        state.rejected_records = int(snapshot.get("rejected_records", state.rejected_records))
        state.duplicate_records = int(snapshot.get("duplicate_records", state.duplicate_records))
        state.next_index = int(snapshot.get("next_index", state.next_index))
        state.consecutive_failures = int(snapshot.get("consecutive_failures", state.consecutive_failures))
        state.captcha_events = int(snapshot.get("captcha_events", state.captcha_events))
        state.user_interventions = int(snapshot.get("user_interventions", state.user_interventions))
        state.validation_failures = int(snapshot.get("validation_failures", state.validation_failures))

        run_started_at_epoch = snapshot.get("run_started_at_epoch")
        if isinstance(run_started_at_epoch, (int, float)):
            state.run_started_at_epoch = float(run_started_at_epoch)

        page_started_at_epoch = snapshot.get("page_started_at_epoch")
        if isinstance(page_started_at_epoch, (int, float)):
            state.page_started_at_epoch = float(page_started_at_epoch)

        current_page_url = snapshot.get("current_page_url")
        if isinstance(current_page_url, str):
            state.current_page_url = current_page_url

        state.current_page_candidates_found = int(
            snapshot.get("current_page_candidates_found", state.current_page_candidates_found),
        )
        state.current_page_saved = int(
            snapshot.get("current_page_saved", state.current_page_saved),
        )
        state.current_page_skipped = int(
            snapshot.get("current_page_skipped", state.current_page_skipped),
        )
        state.last_page_candidates_found = int(
            snapshot.get("last_page_candidates_found", state.last_page_candidates_found),
        )
        state.last_page_saved = int(
            snapshot.get("last_page_saved", state.last_page_saved),
        )
        state.last_page_skipped = int(
            snapshot.get("last_page_skipped", state.last_page_skipped),
        )
        state.pages_processed = int(snapshot.get("pages_processed", state.pages_processed))

        selector_overrides = snapshot.get("selector_overrides")
        if isinstance(selector_overrides, dict):
            state.selector_overrides = {
                str(key): [str(item).strip() for item in value if str(item).strip()]
                for key, value in selector_overrides.items()
                if isinstance(value, list)
            }

        seen_fingerprints = snapshot.get("seen_fingerprints")
        if isinstance(seen_fingerprints, list):
            state.seen_fingerprints = {str(item) for item in seen_fingerprints if str(item).strip()}

        selector_success_counts = snapshot.get("selector_success_counts")
        if isinstance(selector_success_counts, dict):
            cleaned: dict[str, dict[str, int]] = {}
            for key, value in selector_success_counts.items():
                if not isinstance(value, dict):
                    continue
                cleaned[str(key)] = {}
                for selector, count in value.items():
                    cleaned[str(key)][str(selector)] = int(count)
            state.selector_success_counts = cleaned

        domain = snapshot.get("domain")
        if isinstance(domain, str) and domain.strip():
            state.domain = domain.strip()

        current_url = snapshot.get("current_url")
        current_fingerprint = snapshot.get("current_fingerprint")
        stop_reason = snapshot.get("stop_reason")
        last_warning = snapshot.get("last_warning")
        if isinstance(current_fingerprint, str):
            state.current_fingerprint = current_fingerprint
        if isinstance(stop_reason, str):
            state.stop_reason = stop_reason
        if isinstance(last_warning, str):
            state.last_warning = last_warning

        if isinstance(current_url, str) and current_url.strip():
            return current_url.strip()

        return None
