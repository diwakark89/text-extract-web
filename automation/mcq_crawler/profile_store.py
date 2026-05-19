from __future__ import annotations

from pathlib import Path

import yaml

from .models import SelectorProfile

PROFILE_KEYS = [
    "question",
    "options",
    "answer",
    "show_answer_buttons",
    "next_buttons",
]


class SelectorProfileStore:
    def __init__(self, domain_profiles_dir: Path) -> None:
        self.domain_profiles_dir = domain_profiles_dir
        self.domain_profiles_dir.mkdir(parents=True, exist_ok=True)

    def merge_with_domain(self, base_profile: SelectorProfile, domain: str) -> SelectorProfile:
        domain_profile = self._load_profile_map(domain)
        merged = base_profile.model_dump()
        for key in PROFILE_KEYS:
            values = domain_profile.get(key)
            if isinstance(values, list) and values:
                combined: list[str] = []
                for selector in [*values, *merged.get(key, [])]:
                    stripped = str(selector).strip()
                    if stripped and stripped not in combined:
                        combined.append(stripped)
                merged[key] = combined
        return SelectorProfile.model_validate(merged)

    def save_overrides(self, domain: str, overrides: dict[str, list[str]]) -> None:
        profile_map = self._load_profile_map(domain)
        for key in PROFILE_KEYS:
            incoming = overrides.get(key, [])
            if not incoming:
                continue
            current = profile_map.get(key, []) if isinstance(profile_map.get(key), list) else []
            merged: list[str] = []
            for selector in [*incoming, *current]:
                stripped = str(selector).strip()
                if stripped and stripped not in merged:
                    merged.append(stripped)
            profile_map[key] = merged
        self._write_profile_map(domain, profile_map)

    def record_selector_success(self, domain: str, key: str, selector: str) -> None:
        if key not in PROFILE_KEYS:
            return

        stripped = (selector or "").strip()
        if not stripped:
            return

        profile_map = self._load_profile_map(domain)
        current = profile_map.get(key, []) if isinstance(profile_map.get(key), list) else []

        merged: list[str] = [stripped]
        for existing in current:
            existing_str = str(existing).strip()
            if existing_str and existing_str not in merged:
                merged.append(existing_str)

        profile_map[key] = merged

        meta = profile_map.get("_meta") if isinstance(profile_map.get("_meta"), dict) else {}
        counts = meta.get("selector_success_counts") if isinstance(meta.get("selector_success_counts"), dict) else {}
        key_counts = counts.get(key) if isinstance(counts.get(key), dict) else {}
        key_counts[stripped] = int(key_counts.get(stripped, 0)) + 1
        counts[key] = key_counts
        meta["selector_success_counts"] = counts
        profile_map["_meta"] = meta

        self._write_profile_map(domain, profile_map)

    def _domain_file(self, domain: str) -> Path:
        safe_name = (domain or "default").replace("/", "_").replace("\\", "_")
        return self.domain_profiles_dir / f"{safe_name}.yaml"

    def _load_profile_map(self, domain: str) -> dict:
        file_path = self._domain_file(domain)
        if not file_path.exists():
            return {}

        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    def _write_profile_map(self, domain: str, profile_map: dict) -> None:
        file_path = self._domain_file(domain)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            yaml.safe_dump(profile_map, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
