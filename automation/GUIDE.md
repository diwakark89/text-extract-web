# MCQ Crawler Usage Guide

This guide explains how to run the crawler and create per-website extraction logic.

## 1) One-time setup

From the repository root:

```bash
cd automation
pip install -e .
playwright install chromium
```

## 2) Basic run

```bash
mcq-crawler run --start-url "https://example.com/questions"
```

## 2b) Personal dashboard run

If you want a thin UI for triggering runs and inspecting logs/output while still
using CLI behavior underneath:

```bash
streamlit run dashboard/app.py
```

Dashboard notes:

- The dashboard launches `main.py run` as a subprocess.
- Only one active run is supported (single-user personal workflow).
- Use the manual input panel to answer intervention prompts.
- Run output remains in `automation/output/` and is shared with CLI runs.

Output files:

- Records: `automation/output/records.jsonl`
- Records (parseable JSON array): `automation/output/records.json`
- Rejected records: `automation/output/errors.jsonl`
- Rejected records (parseable JSON array): `automation/output/errors.json`
- Checkpoint: `automation/output/checkpoint.json`
- Screenshots: `automation/output/screenshots/`
- Selector debug log (optional): `automation/output/selector_debug.jsonl`

## 3) Use ready-made profiles

This project includes two ready templates:

- `automation/profiles/examtopics_like.yaml`
- `automation/profiles/generic_panel_mcq.yaml`

Domain-specific profile for your target page:

- `automation/profiles/free_braindumps_aws_ccp.yaml`
- `automation/profiles/free_braindumps_aws_ccp_strict.yaml`
- `automation/profiles/free_braindumps_aws_ccp_broad.yaml`

Target URL:

- <https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-14>

Recommended run command for this domain:

```bash
mcq-crawler run \
  --start-url "https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-14" \
  --profile automation/profiles/free_braindumps_aws_ccp_strict.yaml \
  --min-quality-score 0.80 \
  --require-answers
```

If the strict profile misses data because the page layout shifts, use broad mode:

```bash
mcq-crawler run \
  --start-url "https://free-braindumps.com/amazon/free-aws-certified-cloud-practitioner-braindumps/page-14" \
  --profile automation/profiles/free_braindumps_aws_ccp_broad.yaml \
  --min-quality-score 0.75 \
  --require-answers
```

Example run with a profile:

```bash
mcq-crawler run \
  --start-url "https://example.com/questions" \
  --profile automation/profiles/examtopics_like.yaml
```

## 4) Resume interrupted runs

```bash
mcq-crawler run \
  --start-url "https://example.com/questions" \
  --profile automation/profiles/examtopics_like.yaml \
  --resume
```

## 5) Quality and validation controls

Recommended stricter run:

```bash
mcq-crawler run \
  --start-url "https://example.com/questions" \
  --profile automation/profiles/examtopics_like.yaml \
  --min-quality-score 0.82 \
  --require-answers
```

Useful flags:

- `--min-confidence`: triggers stricter intervention when extraction confidence is low.
- `--min-quality-score`: minimum score required to persist a record.
- `--require-answers / --allow-missing-answers`: enforce answer presence.
- `--prompt-for-login-at-start / --no-prompt-for-login-at-start`: pause before crawl so you can log in manually.
- `--max-consecutive-failures`: intervention threshold.
- `--selector-debug`: write selector match details per extracted question.

Enable selector debug mode:

```bash
mcq-crawler run \
  --start-url "https://example.com/questions" \
  --profile automation/profiles/generic_panel_mcq.yaml \
  --selector-debug
```

## 6) Per-website extraction logic (best practice)

Use this 3-layer model:

1. Base profile (global defaults)

  Start with `automation/profiles/default.yaml`.

1. Website profile (manual)

  Create a file under `automation/profiles/` for each website.

  Example: `automation/profiles/my_site.yaml`

1. Learned domain profile (automatic)

  Keep `--auto-learn-profiles` enabled (default).

  Successful selectors and manual overrides are saved under `automation/profiles/domains/<domain>.yaml`.

At runtime, domain selectors are prioritized before base selectors.

## 7) Create a new website profile

Create a new YAML with these keys:

- `question`
- `options`
- `answer`
- `show_answer_buttons`
- `next_buttons`

Example starter:

```yaml
question:
  - ".panel-body > p.lead"

options:
  - ".panel-body ol > li"

answer:
  - "div[id^='answerQ'] > p"

show_answer_buttons:
  - "a[data-toggle='collapse'][href*='answerQ']"

next_buttons:
  - "a:has-text('Next Question')"
```

Then run:

```bash
mcq-crawler run \
  --start-url "https://your-site.example/path" \
  --profile automation/profiles/my_site.yaml
```

## 8) Human-in-the-loop corrections

When blocked (captcha or repeated failures), the runner prompts for action:

- Solve captcha and continue.
- Provide selector override JSON.
- Skip to next question.
- Stop run.

If `--auto-learn-profiles` is enabled, manual selector overrides are saved into the domain profile.

Dashboard equivalent:

- When intervention is requested, send your response from the dashboard manual input box.
- Quick actions map to common responses: `c`, `o`, `s`, `q`.

## 9) Suggested workflow for each new website

1. Run with `generic_panel_mcq.yaml` first.
2. If quality is low, build a website-specific profile.
3. Keep auto-learn enabled for 1-2 sessions.
4. Review `automation/profiles/domains/<domain>.yaml`.
5. Promote stable selectors into your manual website profile.
6. Run strict quality gate mode for production captures.

## 10) Troubleshooting

- Empty extraction: Check selectors in browser DevTools. Start with broader selectors, then narrow.

- Wrong options count: Prefer list item selectors (for example `ol > li`) instead of container selectors.

- Answers missing: Add/adjust `show_answer_buttons` selectors. Lower `--min-quality-score` temporarily while tuning.

- Repeated records: This is usually blocked by duplicate fingerprint checks; inspect `errors.jsonl` for duplicate entries.
