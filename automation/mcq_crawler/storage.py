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
        *,
        questions_per_file: int = 300,
        records_written: int = 0,
    ) -> None:
        self.base_output_path = self._normalize_records_output_path(output_path)
        self.error_path = error_path
        self.debug_path = debug_path
        self.error_json_path = self.error_path.with_suffix(".json")
        self.questions_per_file = max(1, int(questions_per_file))
        self.records_written = max(0, int(records_written))

        self.base_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.error_path.parent.mkdir(parents=True, exist_ok=True)
        self.error_json_path.parent.mkdir(parents=True, exist_ok=True)
        if self.debug_path is not None:
            self.debug_path.parent.mkdir(parents=True, exist_ok=True)

        self._migrate_legacy_base_record_file()

    def _normalize_records_output_path(self, output_path: Path) -> Path:
        suffix = output_path.suffix.lower()
        if suffix == ".json":
            return output_path
        if suffix:
            return output_path.with_suffix(".json")
        return output_path.with_name(f"{output_path.name}.json")

    def _chunk_output_path(self, index: int) -> Path:
        suffix = f"{index:02d}"
        return self.base_output_path.with_name(f"{self.base_output_path.stem}_{suffix}.json")

    def _legacy_base_paths(self) -> tuple[Path, Path]:
        return (
            self.base_output_path,
            self.base_output_path.with_suffix(".jsonl"),
        )

    def _migrate_legacy_base_record_file(self) -> None:
        first_chunk_path = self._chunk_output_path(1)
        if first_chunk_path.exists():
            return

        for legacy_path in self._legacy_base_paths():
            if not legacy_path.exists():
                continue
            first_chunk_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.replace(first_chunk_path)
            return

    def _output_path_for_next_record(self) -> Path:
        next_record_total = self.records_written + 1
        chunk_index = ((next_record_total - 1) // self.questions_per_file) + 1
        return self._chunk_output_path(chunk_index)

    def append_record(self, record: MCQRecord) -> None:
        payload = record.model_dump(exclude={"source_url", "confidence", "quality_score", "fingerprint", "extracted_at"})
        self._append_json_array_item(self._output_path_for_next_record(), payload)

        self.records_written += 1

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
