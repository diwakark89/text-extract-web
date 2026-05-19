from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RECENT_URLS_FILE = "dashboard_recent_urls.json"


def _is_within_workspace(path: Path, workspace_root: Path) -> bool:
    resolved = path.resolve()
    root = workspace_root.resolve()
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def list_yaml_profiles(
    base_profiles_dir: Path,
    learned_profiles_dir: Path,
    *,
    workspace_root: Path,
) -> tuple[list[Path], list[Path]]:
    base_profiles = sorted(
        path.resolve()
        for path in base_profiles_dir.glob("*.yaml")
        if _is_within_workspace(path, workspace_root)
    )
    learned_profiles = sorted(
        path.resolve()
        for path in learned_profiles_dir.glob("*.yaml")
        if _is_within_workspace(path, workspace_root)
    )
    return base_profiles, learned_profiles


def read_jsonl_tail(file_path: Path, *, max_lines: int = 100) -> list[dict[str, Any]]:
    if not file_path.exists():
        return []

    raw_lines = file_path.read_text(encoding="utf-8").splitlines()
    if max_lines > 0:
        raw_lines = raw_lines[-max_lines:]

    parsed: list[dict[str, Any]] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                parsed.append(data)
            else:
                parsed.append({"value": data})
        except json.JSONDecodeError:
            parsed.append({"_parse_error": "invalid_jsonl", "raw": stripped})
    return parsed


def read_checkpoint(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {}

    try:
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": "invalid_json"}

    if not isinstance(loaded, dict):
        return {"_parse_error": "checkpoint_not_object", "value": loaded}
    return loaded


def load_recent_urls(output_dir: Path, *, max_items: int = 20) -> list[str]:
    file_path = output_dir / RECENT_URLS_FILE
    if not file_path.exists():
        return []

    try:
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(loaded, list):
        return []

    urls = [str(item).strip() for item in loaded if str(item).strip()]
    return urls[:max_items]


def save_recent_url(output_dir: Path, url: str, *, max_items: int = 20) -> None:
    stripped = url.strip()
    if not stripped:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    existing = load_recent_urls(output_dir, max_items=max_items)

    next_urls = [stripped]
    for item in existing:
        if item != stripped:
            next_urls.append(item)

    file_path = output_dir / RECENT_URLS_FILE
    file_path.write_text(
        json.dumps(next_urls[:max_items], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
