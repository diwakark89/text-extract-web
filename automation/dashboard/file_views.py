from __future__ import annotations

import json
import os
import shutil
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

RECENT_URLS_FILE = "dashboard_recent_urls.json"
RECENT_URLS_FILE_ENV = "MCQ_DASHBOARD_RECENT_URLS_PATH"
RECENT_STORE_SCHEMA_VERSION = 1
RECENT_SITES_KEY = "recent_sites"
PROFILE_BY_HOST_KEY = "profile_by_host"
DASHBOARD_SETTINGS_KEY = "dashboard_settings"


def _recent_store_file(output_dir: Path) -> Path:
    configured = str(os.getenv(RECENT_URLS_FILE_ENV, "") or "").strip()
    if configured:
        configured_path = Path(configured)
        if not configured_path.is_absolute():
            configured_path = (output_dir.parent / configured_path).resolve()
        return configured_path

    default_path = output_dir / RECENT_URLS_FILE
    if default_path.exists():
        return default_path

    moved_path = output_dir.parent / RECENT_URLS_FILE
    if moved_path.exists():
        return moved_path

    return default_path


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

    if max_lines > 0:
        raw_lines = deque(maxlen=max_lines)
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw_lines.append(line.rstrip("\n"))
        lines_to_parse = list(raw_lines)
    else:
        with file_path.open("r", encoding="utf-8") as handle:
            lines_to_parse = [line.rstrip("\n") for line in handle]

    parsed: list[dict[str, Any]] = []
    for line in lines_to_parse:
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


def resolve_latest_records_jsonl_path(base_file_path: Path) -> Path:
    if base_file_path.exists():
        return base_file_path

    parent = base_file_path.parent
    if not parent.exists():
        return base_file_path

    stem = base_file_path.stem
    suffix = base_file_path.suffix
    pattern = f"{stem}_*{suffix}"

    latest_path: Path | None = None
    latest_index = -1

    for candidate in parent.glob(pattern):
        if not candidate.is_file():
            continue
        if not candidate.stem.startswith(f"{stem}_"):
            continue

        tail = candidate.stem[len(stem) + 1 :]
        if not tail.isdigit():
            continue

        index = int(tail)
        if index > latest_index:
            latest_index = index
            latest_path = candidate

    return latest_path or base_file_path


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


def _normalize_host(host: str) -> str:
    normalized = (host or "").strip().lower()
    if not normalized:
        return ""
    normalized = normalized.split("@")[-1]
    normalized = normalized.split(":", 1)[0]
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def url_host_key(url: str) -> str:
    stripped = (url or "").strip()
    if not stripped:
        return ""

    parsed = urlparse(stripped)
    if not parsed.netloc and parsed.path and "://" not in stripped:
        parsed = urlparse(f"https://{stripped}")

    if parsed.hostname:
        return _normalize_host(parsed.hostname)

    return ""


def _empty_recent_store() -> dict[str, Any]:
    return {
        "schema_version": RECENT_STORE_SCHEMA_VERSION,
        RECENT_SITES_KEY: [],
        PROFILE_BY_HOST_KEY: {},
        DASHBOARD_SETTINGS_KEY: {},
    }


def _sanitize_dashboard_settings(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        setting_key = str(key).strip()
        if not setting_key:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[setting_key] = value

    return cleaned


def _normalize_recent_store(raw: object, *, max_items: int) -> dict[str, Any]:
    store = _empty_recent_store()

    if isinstance(raw, list):
        seen_hosts: set[str] = set()
        for item in raw:
            url = str(item).strip()
            host = url_host_key(url)
            if not url or not host or host in seen_hosts:
                continue
            seen_hosts.add(host)
            store[RECENT_SITES_KEY].append({"host": host, "last_url": url})

        store[RECENT_SITES_KEY] = store[RECENT_SITES_KEY][:max_items]
        return store

    if not isinstance(raw, dict):
        return store

    recent_items = raw.get(RECENT_SITES_KEY)
    if isinstance(recent_items, list):
        seen_hosts: set[str] = set()
        for item in recent_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("last_url") or "").strip()
            host = _normalize_host(str(item.get("host") or ""))
            if not host:
                host = url_host_key(url)
            if not url or not host or host in seen_hosts:
                continue
            seen_hosts.add(host)
            store[RECENT_SITES_KEY].append({"host": host, "last_url": url})

    profile_map = raw.get(PROFILE_BY_HOST_KEY)
    if isinstance(profile_map, dict):
        cleaned: dict[str, str] = {}
        for host, profile_path in profile_map.items():
            host_key = _normalize_host(str(host))
            profile_value = str(profile_path or "").strip()
            if host_key and profile_value:
                cleaned[host_key] = profile_value
        store[PROFILE_BY_HOST_KEY] = cleaned

    store[DASHBOARD_SETTINGS_KEY] = _sanitize_dashboard_settings(raw.get(DASHBOARD_SETTINGS_KEY))

    store[RECENT_SITES_KEY] = store[RECENT_SITES_KEY][:max_items]
    return store


def _load_recent_store(output_dir: Path, *, max_items: int = 20) -> dict[str, Any]:
    file_path = _recent_store_file(output_dir)
    if not file_path.exists():
        return _empty_recent_store()

    try:
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_recent_store()

    return _normalize_recent_store(loaded, max_items=max_items)


def _write_recent_store(output_dir: Path, store: dict[str, Any], *, max_items: int = 20) -> None:
    normalized = _normalize_recent_store(store, max_items=max_items)
    file_path = _recent_store_file(output_dir)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(normalized, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def load_recent_urls(output_dir: Path, *, max_items: int = 20) -> list[str]:
    store = _load_recent_store(output_dir, max_items=max_items)
    recent_sites = store.get(RECENT_SITES_KEY, [])
    if not isinstance(recent_sites, list):
        return []
    return [
        str(item.get("last_url") or "").strip()
        for item in recent_sites
        if isinstance(item, dict) and str(item.get("last_url") or "").strip()
    ][:max_items]


def save_recent_url(output_dir: Path, url: str, *, max_items: int = 20) -> None:
    stripped = url.strip()
    if not stripped:
        return

    host = url_host_key(stripped)
    if not host:
        return

    store = _load_recent_store(output_dir, max_items=max_items)
    existing_sites = store.get(RECENT_SITES_KEY, [])
    if not isinstance(existing_sites, list):
        existing_sites = []

    next_sites = [{"host": host, "last_url": stripped}]
    for item in existing_sites:
        if not isinstance(item, dict):
            continue
        existing_host = _normalize_host(str(item.get("host") or ""))
        existing_url = str(item.get("last_url") or "").strip()
        if not existing_host or not existing_url:
            continue
        if existing_host != host:
            next_sites.append({"host": existing_host, "last_url": existing_url})

    store[RECENT_SITES_KEY] = next_sites[:max_items]
    _write_recent_store(output_dir, store, max_items=max_items)


def load_profile_for_url(output_dir: Path, url: str, *, max_items: int = 20) -> str | None:
    host = url_host_key(url)
    if not host:
        return None

    store = _load_recent_store(output_dir, max_items=max_items)
    profile_map = store.get(PROFILE_BY_HOST_KEY, {})
    if not isinstance(profile_map, dict):
        return None

    value = str(profile_map.get(host) or "").strip()
    return value or None


def save_profile_for_url(
    output_dir: Path,
    url: str,
    profile_path: str | None,
    *,
    max_items: int = 20,
) -> None:
    host = url_host_key(url)
    if not host:
        return

    store = _load_recent_store(output_dir, max_items=max_items)
    profile_map = store.get(PROFILE_BY_HOST_KEY, {})
    if not isinstance(profile_map, dict):
        profile_map = {}

    normalized_value = str(profile_path or "").strip()
    if normalized_value:
        profile_map[host] = normalized_value
    else:
        profile_map.pop(host, None)

    store[PROFILE_BY_HOST_KEY] = profile_map
    _write_recent_store(output_dir, store, max_items=max_items)


def load_dashboard_settings(output_dir: Path, *, max_items: int = 20) -> dict[str, Any]:
    store = _load_recent_store(output_dir, max_items=max_items)
    return _sanitize_dashboard_settings(store.get(DASHBOARD_SETTINGS_KEY))


def save_dashboard_settings(
    output_dir: Path,
    settings: dict[str, Any],
    *,
    max_items: int = 20,
) -> None:
    store = _load_recent_store(output_dir, max_items=max_items)
    store[DASHBOARD_SETTINGS_KEY] = _sanitize_dashboard_settings(settings)
    _write_recent_store(output_dir, store, max_items=max_items)


def clean_output_directory_for_run(output_dir: Path) -> tuple[int, int]:
    """Remove generated output artifacts while preserving dashboard metadata store."""
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    preserved: set[Path] = set()
    recent_store_path = _recent_store_file(output_root)
    try:
        preserved.add(recent_store_path.resolve())
    except FileNotFoundError:
        pass

    removed_files = 0
    removed_dirs = 0
    for child in output_root.iterdir():
        resolved_child = child.resolve()
        if resolved_child in preserved:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=False)
            removed_dirs += 1
        else:
            child.unlink(missing_ok=True)
            removed_files += 1

    return removed_files, removed_dirs
