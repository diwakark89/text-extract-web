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
        payload = record.model_dump()
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
        existing: list[dict] = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    existing = [item for item in loaded if isinstance(item, dict)]
            except json.JSONDecodeError:
                existing = []

        existing.append(payload)
        path.write_text(
            json.dumps(existing, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
