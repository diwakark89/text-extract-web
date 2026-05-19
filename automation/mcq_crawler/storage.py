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
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.error_path.parent.mkdir(parents=True, exist_ok=True)
        if self.debug_path is not None:
            self.debug_path.parent.mkdir(parents=True, exist_ok=True)

    def append_record(self, record: MCQRecord) -> None:
        line = json.dumps(record.model_dump(), ensure_ascii=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def append_error(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self.error_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def append_debug_event(self, payload: dict) -> None:
        if self.debug_path is None:
            return
        line = json.dumps(payload, ensure_ascii=True)
        with self.debug_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
