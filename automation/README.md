# MCQ Crawler (Copilot SDK + Playwright)

This folder contains a fresh implementation for automated MCQ extraction.

## Goals

- Multi-site extraction with adaptive selectors.
- Copilot SDK as active page controller.
- Local-only execution using already logged-in Copilot CLI.
- JSONL output with validation and checkpoint-friendly run state.
- Human feedback loop for captcha/extraction failures.
- Checkpoint-resume so interrupted runs can continue.
- Per-domain selector learning from successful runs and user overrides.
- Stronger quality gates with duplicate detection.

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
pip install -e .
playwright install chromium
```

## Run

```bash
mcq-crawler run --start-url "https://example.com/questions"
```

Detailed step-by-step guide:

- `automation/GUIDE.md`

## Tests

Run automated tests (fixture extraction + parsing + checkpoint restore):

```bash
python -m unittest discover -s automation/tests -v
```

Useful options:

- `--profile` path to YAML selectors profile.
- `--output` path to JSONL output.
- `--headless/--no-headless` browser mode.
- `--max-records` extraction cap.
- `--model` Copilot model, default `gpt-5`.
- `--resume` resume from checkpoint file.
- `--checkpoint` set checkpoint file path.
- `--min-quality-score` enforce stronger persistence quality gate.
- `--require-answers/--allow-missing-answers` answer consistency policy.
- `--auto-learn-profiles` persist selector learning into domain profile files.
- `--selector-debug` write per-question selector match logs.

Ready profile for free-braindumps AWS CCP page:

- `automation/profiles/free_braindumps_aws_ccp.yaml`
- `automation/profiles/free_braindumps_aws_ccp_strict.yaml`
- `automation/profiles/free_braindumps_aws_ccp_broad.yaml`

## Notes

- No token or Copilot CLI path is required by default.
- The SDK uses local Copilot CLI login (`use_logged_in_user=True`).
- On captcha/low confidence, the runner prompts for user guidance and resumes.
- Domain profiles are saved under `automation/profiles/domains/`.
- Checkpoint state is saved to `automation/output/checkpoint.json` by default.
- Selector debug logs (when enabled) are saved to `automation/output/selector_debug.jsonl`.
