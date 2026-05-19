from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel
import yaml


class HostAuthConfig(BaseModel):
    host: str
    username: str
    password: str
    username_selector: str
    password_selector: str
    submit_selector: str | None = None
    success_selector: str | None = None
    login_url: str | None = None
    submit_key: str = "Enter"


def normalize_host(host: str) -> str:
    normalized = (host or "").strip().lower()
    if not normalized:
        return ""
    normalized = normalized.split("@")[-1]
    normalized = normalized.split(":", 1)[0]
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def host_from_url(url: str) -> str:
    stripped = (url or "").strip()
    if not stripped:
        return ""

    parsed = urlparse(stripped)
    if parsed.hostname:
        return normalize_host(parsed.hostname)

    if "://" not in stripped:
        parsed = urlparse(f"https://{stripped}")
        if parsed.hostname:
            return normalize_host(parsed.hostname)

    return ""


def load_host_auth_config(auth_file_path: Path, target_url: str) -> HostAuthConfig | None:
    if not auth_file_path.exists():
        return None

    try:
        raw = yaml.safe_load(auth_file_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    entries: list[dict] = []
    if isinstance(raw, list):
        entries = [item for item in raw if isinstance(item, dict)]
    elif isinstance(raw, dict):
        hosts_block = raw.get("hosts")
        if isinstance(hosts_block, list):
            entries = [item for item in hosts_block if isinstance(item, dict)]
        else:
            for host, config in raw.items():
                if isinstance(config, dict):
                    entries.append({"host": str(host), **config})

    if not entries:
        return None

    target_host = host_from_url(target_url)
    if not target_host:
        return None

    for entry in entries:
        try:
            candidate = HostAuthConfig.model_validate(entry)
        except Exception:
            continue

        if normalize_host(candidate.host) == target_host:
            return candidate

    return None
