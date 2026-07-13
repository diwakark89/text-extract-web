# MCQ Crawler (Playwright)

This folder contains a fresh implementation for automated MCQ extraction.

## Goals

- Multi-site extraction with adaptive selectors.
- Deterministic browser-driven extraction and validation.
- Local-only execution with Playwright automation.
- Numbered JSON chunk output with validation and checkpoint-friendly run state.
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

If you see websocket keepalive errors during browser shutdown, reinstall the pinned dependency set so the compatible `websockets<15` version is used:

```bash
pip install --upgrade --force-reinstall "websockets<15"
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
- View record chunk JSON files, `errors.jsonl`, `selector_debug.jsonl`, and checkpoint state.
- Select base and learned domain profiles.
- Send manual prompt input (`c/o/s/q` or selector JSON) to the running process.
- Records are written as numbered JSON array chunks from the first saved record:
  - `automation/output/records/records_01.json`
  - `automation/output/records/records_02.json`
- Error output remains:
  - `automation/output/errors.jsonl` and `automation/output/errors.json`

`--output` defines the base JSON path used to derive the chunk folder/basename.
For example, `automation/output/aws/aws.json` produces:

- `automation/output/aws/aws_01.json`
- `automation/output/aws/aws_02.json`

Detailed step-by-step guide:

- `automation/GUIDE.md`

## Tests

Run automated tests (fixture extraction + parsing + checkpoint restore):

```bash
python -m unittest discover -s automation/tests -v
```

Useful options:

- `--profile` path to YAML selectors profile.
- `--output` base JSON path used to derive numbered chunk files.
- `--headless/--no-headless` browser mode.
- `--max-records` extraction cap.
- `--questions-per-file` split records into multiple files after N questions (default `300`).
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

- On captcha/low confidence, the runner prompts for user guidance and resumes.
- Domain profiles are saved under `automation/profiles/domains/`.
- Checkpoint state is saved to `automation/output/checkpoint.json` by default.
- Selector debug logs (when enabled) are saved to `automation/output/selector_debug.jsonl`.
