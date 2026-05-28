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

## Personal Dashboard (Thin UI over CLI)

For personal local use, you can launch the dashboard to trigger runs, tail logs,
inspect output files, view profiles, and forward manual intervention input while
keeping the CLI as the execution engine.

From `automation/`:

```bash
streamlit run dashboard/app.py
```

Dashboard capabilities:

- Start/stop crawler runs using existing CLI options.
- Resume from checkpoint.
- View stdout/stderr logs.
- View `records.jsonl`, `errors.jsonl`, `selector_debug.jsonl`, and checkpoint state.
- Select base and learned domain profiles.
- Send manual prompt input (`c/o/s/q` or selector JSON) to the running process.
- Output is written in both JSONL and parseable JSON array mirrors:
  - `automation/output/records.jsonl` and `automation/output/json/records.json`
  - `automation/output/errors.jsonl` and `automation/output/errors.json`

When records exceed the per-file limit (`--questions-per-file`, default `300`),
records rotate into numbered files using `_1`, `_2`, `_3`, and so on:

- `automation/output/records_1.jsonl`, `automation/output/records_2.jsonl`, ...
- `automation/output/json/records_1.json`, `automation/output/json/records_2.json`, ...

Model note:

- If you see `Model "..." is not available`, choose a model available to your account in the dashboard Model field (for example `gpt-4.1`) and run again.
- If you see `Model "..." is not available`, choose a model available to your account in the dashboard Model field (for example `gpt-5.4`) and run again.

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
- `--questions-per-file` split records into multiple files after N questions (default `300`).
- `--model` Copilot model, default `gpt-5`.
- `--resume` resume from checkpoint file.
- `--checkpoint` set checkpoint file path.
- `--min-quality-score` enforce stronger persistence quality gate.
- `--require-answers/--allow-missing-answers` answer consistency policy.
- `--auto-learn-profiles` persist selector learning into domain profile files.
- `--selector-debug` write per-question selector match logs.
- `--humanize/--no-humanize` enable or disable human-like pacing during crawl navigation.

Ready profile for free-braindumps AWS CCP page:

- `automation/profiles/free_braindumps_aws_ccp_broad.yaml`

Ready profile for Examcademy pages:

- `automation/profiles/examcademy_like.yaml`

Recommended strict run for Examcademy:

```bash
mcq-crawler run \
  --start-url "https://examcademy.com/exams/amazon/aws-certified-cloud-practitioner/1" \
  --profile automation/profiles/examcademy_like.yaml \
  --prompt-for-login-at-start \
  --require-answers \
  --selector-debug
```

## Notes

- No token or Copilot CLI path is required by default.
- The SDK uses local Copilot CLI login (`use_logged_in_user=True`).
- On captcha/low confidence, the runner prompts for user guidance and resumes.
- Domain profiles are saved under `automation/profiles/domains/`.
- Checkpoint state is saved to `automation/output/checkpoint.json` by default.
- Selector debug logs (when enabled) are saved to `automation/output/selector_debug.jsonl`.
