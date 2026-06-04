# AGENTS.md

## Project Overview

This repository contains:

- A Chrome Extension (Manifest V3) for extracting MCQ content from web pages using CSS selectors.
- A standalone `automation/` crawler for Playwright-based extraction.

Core capabilities:

- Extract question, options, and answer content from the active tab.
- Optionally include hidden text.
- Remove unwanted text/selectors from extracted output.
- Copy extracted JSON output.
- Send extracted data to a configured API endpoint.

Primary technologies:

- Plain JavaScript (no bundler)
- HTML/CSS
- Chrome Extension APIs (`chrome.tabs`, `chrome.scripting`, `chrome.storage`, `chrome.runtime`)

## Repository Layout

- `chrome_extension/manifest.json`: Extension metadata, permissions, service worker, content scripts.
- `chrome_extension/popup.html`, `chrome_extension/popup.js`, `chrome_extension/popup.css`: Main extension popup UI and behavior.
- `chrome_extension/options.html`, `chrome_extension/options.js`, `chrome_extension/options.css`: Extension settings page.
- `chrome_extension/content-script.js`: Main DOM extraction logic.
- `chrome_extension/content-reveal.js`: Helpers to simulate reveal interactions on pages.
- `chrome_extension/background.js`: Service worker and API call fallback.
- `chrome_extension/tests.md`: Manual hidden-content test scenarios.
- `automation/`: Standalone Python crawler and profiles.
- `README.md`: Top-level repo overview and output location notes.

## Setup Commands

No package manager or build step is configured in this repository.

### Local setup

1. Open Chrome/Edge extensions page (`chrome://extensions` or `edge://extensions`).
2. Enable Developer mode.
3. Load unpacked extension from `chrome_extension/`.

### Quick validation (PowerShell)

Use these before creating a PR:

```powershell
# Validate manifest JSON
Get-Content chrome_extension/manifest.json -Raw | ConvertFrom-Json | Out-Null

# Validate JS syntax (requires Node.js)
node --check chrome_extension/background.js
node --check chrome_extension/content-script.js
node --check chrome_extension/content-reveal.js
node --check chrome_extension/options.js
node --check chrome_extension/popup.js
```

## Development Workflow

1. Edit extension files directly (no transpilation/build).
2. Reload the unpacked extension in browser after changes.
3. Open popup and test against real pages.
4. Re-run validation commands before commit.

Notes:

- `chrome_extension/popup.js` injects/executes content extraction in active tab.
- `chrome_extension/content-script.js` is responsible for selector-driven extraction and JSON formatting.
- `chrome_extension/background.js` includes API-call fallback messaging.

## Testing Instructions

This project currently uses manual testing (no automated unit/integration test framework configured).

### Baseline manual checks

- Load extension and open popup.
- Enter all three selectors (question/options/answer).
- Run extraction and verify JSON output shape.
- Verify Copy button behavior.
- Verify Send-to-API flow and response status rendering.
- Verify values are persisted via `chrome.storage.sync` between popup opens.

### Hidden-content scenarios

Use the checklist in `chrome_extension/tests.md`:

- Hidden elements (`display: none`)
- Reveal button interaction
- Nested hidden content
- Dynamic loading
- Accordion/collapsed sections

### Minimum pre-PR quality bar

- Manifest JSON parses successfully.
- JS syntax checks pass for modified files.
- Manual extraction flow validated on at least one target page.

## Code Style Guidelines

Repository conventions (inferred from existing code):

- Use plain ES6+ JavaScript and browser/Chrome APIs directly.
- Prefer `const` for immutable bindings, `let` otherwise.
- Use semicolons consistently.
- Keep storage keys grouped as constants (see `STORAGE_KEYS`).
- Use descriptive function names (`extractTextFromSelectors`, `sendToAPI`).
- Wrap Chrome API usage with runtime error checks where appropriate.
- Keep user-visible errors actionable in popup UI.

When editing existing files:

- Preserve current style in that file (quote style and formatting may differ by file).
- Avoid introducing build tooling unless explicitly requested.

## Build and Deployment

There is no CI/CD or packaging pipeline configured in this repository.

### Create a distributable package manually

From repo root:

```powershell
Compress-Archive -Path chrome_extension\* -DestinationPath text-extract-web-extension.zip -Force
```

Before packaging, ensure temporary/local-only files are excluded as needed.

## Security Considerations

- Extension currently requests broad host access (`"<all_urls>"`). Keep this as limited as possible for new features.
- Do not hardcode secrets or auth tokens in source.
- API URL is configurable and defaults to localhost; validate endpoint trust before sending data.
- Be cautious with extracted page content; it may include sensitive information.

## Pull Request Guidelines

Recommended PR title format:

- `[extension] Short imperative summary`

Before opening PR:

1. Run manifest and JS syntax validation commands.
2. Reload extension and manually verify changed behavior.
3. Update `README.md` and/or `chrome_extension/tests.md` if user-visible behavior or testing flow changed.

In PR description, include:

- What changed
- How it was tested (exact pages/scenarios)
- Any permission/storage/API implications

## Debugging and Troubleshooting

- If popup cannot talk to page: refresh target tab, then retry extraction.
- If extraction is empty: verify selectors in DevTools and test with simpler selectors first.
- If API send fails: inspect popup status text and check service worker logs/background console.
- If hidden text is missing: verify hidden mechanism (`display`, dynamic rendering, interaction needed) and use scenarios from `chrome_extension/tests.md`.

## Agent Notes

- Prefer minimal, focused changes.
- Do not add new dependencies/tooling unless explicitly requested.
- If introducing new commands/workflows, ensure they are runnable from this repo and document them in this file.
