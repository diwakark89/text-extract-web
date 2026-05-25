from __future__ import annotations

import json
from pathlib import Path

from .models import MCQRecord


class JsonlStore:
    def __init__(
        self,
        output_path: Path,
        error_path: Path,
        debug_path: Path | None = None,
    ) -> None:
        self.output_path = output_path
        self.error_path = error_path
        self.debug_path = debug_path
        self.output_json_path = self.output_path.with_suffix(".json")
        self.error_json_path = self.error_path.with_suffix(".json")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.error_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.error_json_path.parent.mkdir(parents=True, exist_ok=True)
        if self.debug_path is not None:
            self.debug_path.parent.mkdir(parents=True, exist_ok=True)

    def append_record(self, record: MCQRecord) -> None:
        payload = record.model_dump(exclude={"source_url", "confidence", "quality_score", "fingerprint", "extracted_at"})
        line = json.dumps(payload, ensure_ascii=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._append_json_array_item(self.output_json_path, payload)

    def append_error(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self.error_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._append_json_array_item(self.error_json_path, payload)

    def append_debug_event(self, payload: dict) -> None:
        if self.debug_path is None:
            return
        line = json.dumps(payload, ensure_ascii=True)
        with self.debug_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _append_json_array_item(self, path: Path, payload: dict) -> None:
        item_text = self._format_array_item(payload)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text(f"[\n{item_text}\n]\n", encoding="utf-8")
            return

        with path.open("r+b") as handle:
            close_idx = self._previous_non_whitespace_index(handle, handle.seek(0, 2) - 1)
            if close_idx is None:
                path.write_text(f"[\n{item_text}\n]\n", encoding="utf-8")
                return

            handle.seek(close_idx)
            close_char = handle.read(1)
            if close_char != b"]":
                path.write_text(f"[\n{item_text}\n]\n", encoding="utf-8")
                return

            previous_idx = self._previous_non_whitespace_index(handle, close_idx - 1)
            if previous_idx is None:
                path.write_text(f"[\n{item_text}\n]\n", encoding="utf-8")
                return

            handle.seek(previous_idx)
            previous_char = handle.read(1)
            if previous_char == b"[":
                insertion = f"\n{item_text}\n]"
            else:
                insertion = f",\n{item_text}\n]"

            handle.seek(close_idx)
            handle.write(insertion.encode("utf-8"))
            handle.truncate()

    def _format_array_item(self, payload: dict) -> str:
        item_json = json.dumps(payload, ensure_ascii=True, indent=2)
        lines = item_json.splitlines()
        return "\n".join(f"  {line}" for line in lines)

    def _previous_non_whitespace_index(self, handle, index: int) -> int | None:
        if index < 0:
            return None

        while index >= 0:
            handle.seek(index)
            value = handle.read(1)
            if value and value not in b" \t\r\n":
                return index
            index -= 1
        return None
