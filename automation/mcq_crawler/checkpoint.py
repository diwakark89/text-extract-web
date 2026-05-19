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
            "records_written": state.records_written,
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
        if isinstance(current_fingerprint, str):
            state.current_fingerprint = current_fingerprint

        if isinstance(current_url, str) and current_url.strip():
            return current_url.strip()

        return None
