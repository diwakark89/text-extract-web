# Text Extract Web

This repository has two parts:

- `chrome_extension/`: Manifest V3 browser extension for selector-based MCQ extraction from the active tab.
- `automation/`: Python + Playwright + Copilot SDK crawler for automated extraction, validation, and checkpoint-resume runs.

## Chrome Extension Setup

1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `chrome_extension/`.

## Automation Output Location

By default, crawler output is written under `automation/output/`:

- Records: `automation/output/records.jsonl`
- Rejected/Error records: `automation/output/errors.jsonl`
- Checkpoint: `automation/output/checkpoint.json`
- Screenshots: `automation/output/screenshots/`
- Selector debug (when enabled): `automation/output/selector_debug.jsonl`

For large runs, records files split automatically after `300` questions per file
by default (configurable via CLI):

- `automation/output/records_1.jsonl`, `automation/output/records_2.jsonl`, ...
- Matching JSON mirrors: `automation/output/json/records_1.json`, `automation/output/json/records_2.json`, ...

These defaults are configurable through CLI flags in `automation/main.py`.

## Optional Host Auto Login (Crawler)

The crawler can optionally use a local host credential file for login-required sites:

- Example template: `automation/auth/auth_hosts.example.yaml`
- Local file: `automation/auth/auth_hosts.yaml` (gitignored)

When enabled, crawler attempts auto-login first and falls back to manual continue flow if login is not confirmed.

## License

MIT License
