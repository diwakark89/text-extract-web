from __future__ import annotations

import asyncio
import hashlib
import random
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from .config import RunConfig
from .models import ExtractionCandidate, RuntimeState, SelectorProfile


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def options_to_map(option_texts: list[str]) -> dict[str, str]:
    labels = [chr(code) for code in range(ord("A"), ord("Z") + 1)]
    mapped: dict[str, str] = {}
    for idx, raw in enumerate(option_texts):
        if idx >= len(labels):
            break
        cleaned = re.sub(r"^[A-Za-z0-9][\.):\s-]+", "", _clean_text(raw))
        mapped[labels[idx]] = cleaned or _clean_text(raw)
    return mapped


def parse_answer_letters(answer_text: str) -> list[str]:
    text = _clean_text(answer_text).upper()
    if not text:
        return []

    text = re.sub(r"ANSWER\(S\)\s*:\s*", "", text)
    text = re.sub(r"CORRECT\s*ANSWER\s*:\s*", "", text)
    text = text.replace(" AND ", ",").replace("&", ",")

    letters: list[str] = []

    for part in [item.strip() for item in text.split(",") if item.strip()]:
        single = re.match(r"^([A-J])[\.):\s]*$", part)
        if single:
            letter = single.group(1)
            if letter not in letters:
                letters.append(letter)
            continue

        # Support selectors that capture full option text like "D All upfront payment".
        leading_label = re.match(r"^([A-J])[\).:\s-]+.+$", part)
        if leading_label:
            letter = leading_label.group(1)
            if letter not in letters:
                letters.append(letter)
            continue

        compact = re.sub(r"[^A-J]", "", part)
        if compact and len(compact) <= 5:
            for letter in compact:
                if letter not in letters:
                    letters.append(letter)

    return letters


MAX_OPTIONS_PER_QUESTION = 8
DEFAULT_MAX_PAGE_CANDIDATES = 80
_OPTION_LABEL_RE = re.compile(r"^\s*([A-J])[\).:\s-]+")


def _unique_preserve(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _select_single_question_option_block(option_texts: list[str]) -> list[str]:
    """Best-effort isolation of one MCQ option block from over-collected option lists."""
    cleaned_items = [_clean_text(item) for item in option_texts if _clean_text(item)]

    labels_in_order: list[str] = []
    labeled_count = 0
    for item in cleaned_items:
        match = _OPTION_LABEL_RE.match(item)
        if match:
            labeled_count += 1
            labels_in_order.append(match.group(1))

    repeated_labels = len(set(labels_in_order)) < len(labels_in_order) if labels_in_order else False
    should_segment = (
        len(cleaned_items) > MAX_OPTIONS_PER_QUESTION
        or (labeled_count >= 4 and repeated_labels)
    )

    if not should_segment:
        return _unique_preserve(cleaned_items)

    blocks: list[list[str]] = []
    current: list[str] = []
    seen_labels: set[str] = set()
    last_label: str = ""

    for item in cleaned_items:
        match = _OPTION_LABEL_RE.match(item)
        if not match:
            if current:
                current.append(item)
            continue

        label = match.group(1)
        new_block = label in seen_labels or (last_label and label < last_label)
        if new_block:
            if len(current) >= 2:
                blocks.append(_unique_preserve(current))
            current = []
            seen_labels = set()
            last_label = ""

        current.append(item)
        seen_labels.add(label)
        last_label = label

    if len(current) >= 2:
        blocks.append(_unique_preserve(current))

    preferred = [block for block in blocks if 3 <= len(block) <= 6]
    if preferred:
        return preferred[0]

    bounded = [block for block in blocks if 2 <= len(block) <= MAX_OPTIONS_PER_QUESTION]
    if bounded:
        return bounded[0]

    if len(cleaned_items) <= MAX_OPTIONS_PER_QUESTION:
        return _unique_preserve(cleaned_items)

    return []


def _is_transient_page_evaluate_error(exc: Exception) -> bool:
    message = str(exc).lower()
    transient_markers = (
        "execution context was destroyed",
        "cannot find context with specified id",
        "most likely because of a navigation",
        "frame was detached",
        "target closed",
        "session closed",
    )

    return isinstance(exc, PlaywrightError) and any(marker in message for marker in transient_markers)


async def _extract_page_candidates_impl(
    runtime: "BrowserRuntime",
    max_candidates: int = DEFAULT_MAX_PAGE_CANDIDATES,
) -> list[ExtractionCandidate]:
    if runtime.page is None:
        raise RuntimeError("Browser page not initialized")

    normalized_limit = max(1, int(max_candidates or DEFAULT_MAX_PAGE_CANDIDATES))
    try:
        await runtime._materialize_question_containers(max_candidates=normalized_limit)
    except Exception:
        # Extraction must still proceed even when materialization is not supported by a page.
        runtime.state.notes["last_candidate_materialization"] = {
            "error": "materialization_failed",
            "target_count": normalized_limit,
        }

    container_selectors = runtime._selector_chain("question_containers")
    question_selectors = runtime._selector_chain("question")
    option_selectors = runtime._selector_chain("options")
    answer_selectors = runtime._answer_selector_chain()
    show_answer_selectors = runtime._selector_chain("show_answer_buttons")

    async def _extract_from_root(root: Locator) -> dict[str, object]:
        return await root.evaluate(
            """
            (el, { questionSelectors, optionSelectors, answerSelectors }) => {
              const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
              const uniq = (items) => {
                const out = [];
                for (const item of items) {
                  if (item && !out.includes(item)) out.push(item);
                }
                return out;
              };

              const firstText = (selectors) => {
                for (const selector of selectors || []) {
                  let nodes = [];
                  try {
                    nodes = Array.from(el.querySelectorAll(selector));
                  } catch {
                    continue;
                  }

                  for (const node of nodes) {
                    const text = clean(node.innerText);
                    if (text) {
                      return { text, selector };
                    }
                  }
                }
                return { text: "", selector: "" };
              };

              const collectOptions = (selectors) => {
                for (const selector of selectors || []) {
                  let nodes = [];
                  try {
                    nodes = Array.from(el.querySelectorAll(selector));
                  } catch {
                    continue;
                  }

                  const options = [];
                  for (const node of nodes) {
                    if (node.matches("li")) {
                      const text = clean(node.innerText);
                      if (text) options.push(text);
                      continue;
                    }

                    const listItems = Array.from(node.querySelectorAll(":scope > li"));
                    if (listItems.length > 0) {
                      for (const li of listItems) {
                        const text = clean(li.innerText);
                        if (text) options.push(text);
                      }
                      continue;
                    }

                    const text = clean(node.innerText);
                    if (text) options.push(text);
                  }

                  const deduped = uniq(options);
                  if (deduped.length >= 2) {
                    return { items: deduped, selector };
                  }
                }

                return { items: [], selector: "" };
              };

              const question = firstText(questionSelectors);
              const options = collectOptions(optionSelectors);
              const answer = firstText(answerSelectors);

              return {
                question: question.text,
                option_texts: options.items,
                answer_text: answer.text,
                used_selectors: {
                  question: question.selector,
                  options: options.selector,
                  answer: answer.selector,
                },
              };
            }
            """,
            {
                "questionSelectors": question_selectors,
                "optionSelectors": option_selectors,
                "answerSelectors": answer_selectors,
            },
        )

    raw: list[dict[str, object]] = []
    best_root_selector = ""
    best_root_count = 0
    for selector in container_selectors:
        try:
            count = await runtime.page.locator(selector).count()
        except Exception:
            continue
        if count > best_root_count:
            best_root_count = count
            best_root_selector = selector

    if best_root_selector and best_root_count > 0:
        root_locator = runtime.page.locator(best_root_selector)
        initial_root_count = best_root_count
        observed_root_count = best_root_count
        scanned_roots = 0
        stagnant_rounds = 0
        index = 0

        while index < normalized_limit:
            try:
                current_root_count = await root_locator.count()
            except Exception:
                break

            observed_root_count = max(observed_root_count, current_root_count)
            if index >= current_root_count:
                stagnant_rounds += 1
                if stagnant_rounds >= 4:
                    break
                await asyncio.sleep(0.12)
                continue

            stagnant_rounds = 0
            root = root_locator.nth(index)
            scanned_roots += 1

            try:
                await root.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

            if show_answer_selectors:
                for show_selector in show_answer_selectors:
                    try:
                        toggle = root.locator(show_selector).first
                        if await toggle.count() == 0:
                            continue
                        if not await toggle.is_visible():
                            continue

                        try:
                            toggle_text = _clean_text(await toggle.inner_text(timeout=350)).lower()
                        except Exception:
                            toggle_text = ""
                        if "hide answer" in toggle_text:
                            break

                        await toggle.click(timeout=900)
                        await asyncio.sleep(0.06)
                        break
                    except Exception:
                        continue

            payload: dict[str, object] | None = None
            for attempt in range(3):
                try:
                    candidate_payload = await _extract_from_root(root)
                except Exception:
                    candidate_payload = None

                if isinstance(candidate_payload, dict):
                    question_value = _clean_text(str(candidate_payload.get("question", "")))
                    option_values = candidate_payload.get("option_texts")
                    if isinstance(option_values, list):
                        cleaned_options = [
                            _clean_text(str(value))
                            for value in option_values
                            if _clean_text(str(value))
                        ]
                    else:
                        cleaned_options = []

                    if question_value and len(cleaned_options) >= 2:
                        payload = {
                            **candidate_payload,
                            "question": question_value,
                            "option_texts": cleaned_options,
                        }
                        break

                if attempt < 2:
                    await asyncio.sleep(0.18 * (attempt + 1))

            if payload is not None:
                raw.append(payload)

            index += 1

        runtime.state.notes["last_page_candidate_scan"] = {
            "root_selector": best_root_selector,
            "root_count": observed_root_count,
            "payload_count": len(raw),
            "limit": normalized_limit,
            "scanned_roots": scanned_roots,
            "initial_root_count": initial_root_count,
        }

    if not raw:
        raw_fallback = await runtime.page.evaluate(
            """
            ({ containerSelectors, questionSelectors, optionSelectors, answerSelectors, maxCandidates }) => {
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const uniq = (items) => {
                    const out = [];
                    for (const item of items) {
                        if (item && !out.includes(item)) out.push(item);
                    }
                    return out;
                };

                const firstText = (root, selectors) => {
                    for (const selector of selectors) {
                        let nodes = [];
                        try {
                            nodes = Array.from(root.querySelectorAll(selector));
                        } catch {
                            continue;
                        }
                        for (const node of nodes) {
                            const text = clean(node.innerText);
                            if (text) {
                                return { text, selector };
                            }
                        }
                    }
                    return { text: "", selector: "" };
                };

                const collectOptions = (root, selectors) => {
                    for (const selector of selectors) {
                        let nodes = [];
                        try {
                            nodes = Array.from(root.querySelectorAll(selector));
                        } catch {
                            continue;
                        }

                        const options = [];
                        for (const node of nodes) {
                            if (node.matches("li")) {
                                const text = clean(node.innerText);
                                if (text) options.push(text);
                                continue;
                            }

                            const listItems = Array.from(node.querySelectorAll(":scope > li"));
                            if (listItems.length > 0) {
                                for (const li of listItems) {
                                    const text = clean(li.innerText);
                                    if (text) options.push(text);
                                }
                                continue;
                            }

                            const text = clean(node.innerText);
                            if (text) options.push(text);
                        }

                        const deduped = uniq(options);
                        if (deduped.length >= 2) {
                            return { items: deduped, selector };
                        }
                    }
                    return { items: [], selector: "" };
                };

                const roots = [];
                const seen = new Set();

                for (const selector of containerSelectors || []) {
                    try {
                        const nodes = Array.from(document.querySelectorAll(selector));
                        for (const node of nodes) {
                            if (!node || seen.has(node)) continue;
                            seen.add(node);
                            if (clean(node.innerText).length > 0) {
                                roots.push(node);
                            }
                        }
                    } catch {
                        continue;
                    }
                }

                if (roots.length === 0) {
                    const panelRoots = Array.from(document.querySelectorAll("[role='tabpanel']"))
                        .filter((node) => clean(node.innerText).length > 0);
                    roots.splice(0, roots.length, ...panelRoots);
                }

                if (roots.length === 0) {
                    const fallbackRoots = Array.from(document.querySelectorAll(".tab-pane, .panel-body, article, section"))
                        .filter((node) => node.querySelectorAll("li").length >= 2 && clean(node.innerText).includes("?"));
                    roots.splice(0, roots.length, ...fallbackRoots);
                }

                const results = [];
                for (const root of roots.slice(0, Math.max(1, maxCandidates))) {
                    const question = firstText(root, questionSelectors);
                    const options = collectOptions(root, optionSelectors);
                    const answer = firstText(root, answerSelectors);

                    if (!question.text || options.items.length < 2) {
                        continue;
                    }

                    results.push({
                        question: question.text,
                        option_texts: options.items,
                        answer_text: answer.text,
                        used_selectors: {
                            question: question.selector,
                            options: options.selector,
                            answer: answer.selector,
                        },
                    });
                }

                return results;
            }
            """,
            {
                "containerSelectors": container_selectors,
                "questionSelectors": question_selectors,
                "optionSelectors": option_selectors,
                "answerSelectors": answer_selectors,
                "maxCandidates": normalized_limit,
            },
        )
        if isinstance(raw_fallback, list):
            raw = [item for item in raw_fallback if isinstance(item, dict)]

    candidates: list[ExtractionCandidate] = []
    if not isinstance(raw, list):
        return candidates

    seen_payloads: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue

        question = _clean_text(str(item.get("question", "")))
        option_values = item.get("option_texts")
        if not isinstance(option_values, list):
            continue

        option_texts = [_clean_text(str(value)) for value in option_values if _clean_text(str(value))]
        if len(option_texts) < 2:
            continue

        candidate_key = f"{question}\n{'|'.join(option_texts)}"
        if candidate_key in seen_payloads:
            continue
        seen_payloads.add(candidate_key)

        answer_text = _clean_text(str(item.get("answer_text", "")))
        used_selectors_raw = item.get("used_selectors")
        used_selectors: dict[str, str] = {}
        if isinstance(used_selectors_raw, dict):
            for key in ("question", "options", "answer"):
                value = used_selectors_raw.get(key)
                if isinstance(value, str) and value.strip():
                    used_selectors[key] = value.strip()

        warnings: list[str] = []
        score = 0.0
        if question:
            score += 0.45
        else:
            warnings.append("question_missing")

        if len(option_texts) >= 2:
            score += 0.35
        else:
            warnings.append("insufficient_options")

        if answer_text:
            score += 0.2
        else:
            warnings.append("answer_missing")

        quality_score = score
        if len(option_texts) >= 4:
            quality_score += 0.05
        if question and len(question) >= 20:
            quality_score += 0.03
        quality_score = min(1.0, round(quality_score, 3))

        candidates.append(
            ExtractionCandidate(
                question=question,
                option_texts=option_texts,
                answer_text=answer_text,
                confidence=round(score, 3),
                quality_score=quality_score,
                warnings=warnings,
                used_selectors=used_selectors,
            ),
        )

    return candidates


class BrowserRuntime:
    def __init__(
        self,
        config: RunConfig,
        selector_profile: SelectorProfile,
        state: RuntimeState,
    ) -> None:
        self.config = config
        self.selector_profile = selector_profile
        self.state = state
        self._rng = random.Random()

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserRuntime":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo_ms,
        )
        self._context = await self._browser.new_context()
        self.page = await self._context.new_page()
        self._ensure_humanization_notes()

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def open_url(self, url: str) -> str:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.maybe_human_delay(reason="open_url_settle")
        return self.page.url

    async def page_context(self) -> dict:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        title = await self.page.title()
        visible_text = await self.page.evaluate(
            "() => document.body ? document.body.innerText.slice(0, 5000) : ''",
        )
        fingerprint = await self.current_fingerprint()

        return {
            "url": self.page.url,
            "title": title,
            "fingerprint": fingerprint,
            "visible_text_preview": _clean_text(visible_text)[:1200],
        }

    async def detect_captcha(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "div.g-recaptcha",
            "#captcha",
            "[class*='captcha']",
        ]

        for selector in selectors:
            try:
                if await self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        text = await self.page.evaluate(
            "() => document.body ? document.body.innerText.toLowerCase() : ''",
        )
        return "captcha" in text or "i am not a robot" in text

    async def ensure_browse_mode_ready(self) -> bool:
                if self.page is None:
                        raise RuntimeError("Browser page not initialized")

                result = await self.page.evaluate(
                        """
                        ({ containerSelectors }) => {
                            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                            const isVisible = (node) => {
                                if (!node) return false;
                                const style = window.getComputedStyle(node);
                                if (style.display === "none" || style.visibility === "hidden") {
                                    return false;
                                }
                                const rect = node.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            };

                            const hasQuestionContainers = () => {
                                for (const selector of containerSelectors || []) {
                                    let nodes = [];
                                    try {
                                        nodes = Array.from(document.querySelectorAll(selector));
                                    } catch {
                                        continue;
                                    }

                                    for (const node of nodes) {
                                        if (!isVisible(node)) continue;
                                        const text = clean(node.innerText);
                                        if (text.length < 20) continue;

                                        const hasOptions = node.querySelectorAll("li").length >= 2;
                                        const hasQuestionSignal = text.includes("?") || /\\bquestion\\b/i.test(text);
                                        if (hasOptions && hasQuestionSignal) {
                                            return true;
                                        }
                                    }
                                }

                                return false;
                            };

                            const modeSubtitle = document.querySelector("p.mode-switcher-subtitle");
                            const questionsPresent = hasQuestionContainers();
                            if (!modeSubtitle) {
                                return {
                                    clicked: false,
                                    reason: "no_mode_switcher",
                                    questionsPresent,
                                };
                            }

                            if (questionsPresent) {
                                return {
                                    clicked: false,
                                    reason: "questions_present",
                                    questionsPresent,
                                };
                            }

                            const candidates = Array.from(document.querySelectorAll("button.mode-btn, button"));
                            const browseButton = candidates.find((node) => {
                                const text = clean(node.innerText).toLowerCase();
                                return text === "browse" || text === "browse mode" || text.startsWith("browse ");
                            });

                            if (!browseButton || !isVisible(browseButton)) {
                                return {
                                    clicked: false,
                                    reason: "browse_missing",
                                    questionsPresent,
                                };
                            }

                            if (browseButton.hasAttribute("disabled")) {
                                return {
                                    clicked: false,
                                    reason: "browse_disabled",
                                    questionsPresent,
                                };
                            }

                            const ariaDisabled = String(browseButton.getAttribute("aria-disabled") || "").toLowerCase();
                            if (ariaDisabled === "true") {
                                return {
                                    clicked: false,
                                    reason: "browse_disabled",
                                    questionsPresent,
                                };
                            }

                            const wasActive =
                                browseButton.classList.contains("active") ||
                                String(browseButton.getAttribute("aria-pressed") || "").toLowerCase() === "true";

                            browseButton.click();

                            return {
                                clicked: true,
                                reason: wasActive ? "browse_reclicked" : "browse_clicked",
                                questionsPresent,
                                wasActive,
                            };
                        }
                        """,
                        {
                                "containerSelectors": self._selector_chain("question_containers"),
                        },
                )

                if isinstance(result, dict):
                        self.state.notes["last_mode_activation"] = result

                clicked = bool(isinstance(result, dict) and result.get("clicked"))
                if clicked:
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=1000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)

                return clicked

    async def wait_for_exam_content_ready(self, timeout_ms: int = 2500) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        deadline = asyncio.get_running_loop().time() + (max(250, timeout_ms) / 1000)
        latest_snapshot: dict[str, int] = {
            "question_count": 0,
            "option_count": 0,
            "answer_button_count": 0,
            "mode_subtitle_count": 0,
        }
        transient_errors = 0

        while asyncio.get_running_loop().time() < deadline:
            try:
                snapshot = await self.page.evaluate(
                    """
                    ({ questionSelectors, optionSelectors }) => {
                        const safeQuery = (selector) => {
                            try {
                                return Array.from(document.querySelectorAll(selector));
                            } catch {
                                return [];
                            }
                        };

                        const questionNodes = [];
                        for (const selector of questionSelectors || []) {
                            questionNodes.push(...safeQuery(selector));
                        }

                        const optionNodes = [];
                        for (const selector of optionSelectors || []) {
                            optionNodes.push(...safeQuery(selector));
                        }

                        const answerButtons = Array.from(document.querySelectorAll("button")).filter((node) => {
                            const text = String(node.innerText || "").trim().toLowerCase();
                            return text === "show answer" || text === "hide answer";
                        });

                        return {
                            question_count: questionNodes.length,
                            option_count: optionNodes.length,
                            answer_button_count: answerButtons.length,
                            mode_subtitle_count: document.querySelectorAll("p.mode-switcher-subtitle").length,
                        };
                    }
                    """,
                    {
                        "questionSelectors": self._selector_chain("question"),
                        "optionSelectors": self._selector_chain("options"),
                    },
                )
            except Exception as exc:
                if _is_transient_page_evaluate_error(exc):
                    transient_errors += 1
                    await asyncio.sleep(0.15)
                    continue
                raise

            if isinstance(snapshot, dict):
                latest_snapshot = {
                    "question_count": int(snapshot.get("question_count", 0) or 0),
                    "option_count": int(snapshot.get("option_count", 0) or 0),
                    "answer_button_count": int(snapshot.get("answer_button_count", 0) or 0),
                    "mode_subtitle_count": int(snapshot.get("mode_subtitle_count", 0) or 0),
                }

            has_questions = latest_snapshot["question_count"] >= 1 and latest_snapshot["option_count"] >= 2
            has_answer_controls = latest_snapshot["answer_button_count"] >= 1
            if has_questions and has_answer_controls:
                self.state.notes["last_content_wait"] = {
                    **latest_snapshot,
                    "ready": True,
                }
                return True

            await asyncio.sleep(0.2)

        self.state.notes["last_content_wait"] = {
            **latest_snapshot,
            "ready": False,
            "transient_errors": transient_errors,
        }
        return False

    async def reveal_answer(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        seen_controls: set[str] = set()
        clicked_count = 0
        reveal_targets: list[str] = []

        for selector in self._selector_chain("show_answer_buttons"):
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
                if count == 0:
                    continue

                for index in range(count):
                    candidate = locator.nth(index)

                    try:
                        handle = await candidate.element_handle()
                        if handle is None:
                            continue
                    except Exception:
                        continue

                    try:
                        control_key = await handle.evaluate(
                            """
                            (el) => {
                              const tag = String(el.tagName || "").toLowerCase();
                              const id = String(el.id || "");
                              const classes = String(el.className || "")
                                .trim()
                                .split(/\\s+/)
                                .filter(Boolean)
                                .slice(0, 3)
                                .join(".");
                              const href = String(el.getAttribute("href") || "");
                              const dataTarget = String(el.getAttribute("data-target") || "");
                              const ariaControls = String(el.getAttribute("aria-controls") || "");

                              let depth = 0;
                              let cursor = el;
                              const path = [];
                              while (cursor && depth < 7) {
                                let part = String(cursor.tagName || "").toLowerCase();
                                if (!part) {
                                  break;
                                }
                                if (cursor.id) {
                                  part += `#${cursor.id}`;
                                  path.unshift(part);
                                  break;
                                }

                                const sib = cursor.parentElement
                                  ? Array.from(cursor.parentElement.children)
                                      .filter((node) => node.tagName === cursor.tagName)
                                      .indexOf(cursor) + 1
                                  : 1;
                                part += `:nth-of-type(${sib})`;
                                path.unshift(part);
                                cursor = cursor.parentElement;
                                depth += 1;
                              }

                              return [
                                tag,
                                id,
                                classes,
                                href,
                                dataTarget,
                                ariaControls,
                                path.join(">"),
                              ].join("|");
                            }
                            """,
                        )
                    except Exception:
                        continue

                    if control_key in seen_controls:
                        continue
                    seen_controls.add(control_key)

                    target_selector = ""
                    try:
                        target_selector = (
                            await handle.evaluate(
                                """
                                (el) => {
                                  const rawTarget = String(
                                    el.getAttribute("data-target") || el.getAttribute("aria-controls") || "",
                                  ).trim();
                                  if (rawTarget) {
                                    return rawTarget.startsWith("#")
                                      ? rawTarget
                                      : `#${rawTarget.replace(/^#/, "")}`;
                                  }

                                  const href = String(el.getAttribute("href") || "").trim();
                                  if (!href) {
                                    return "";
                                  }
                                  if (href.startsWith("#")) {
                                    return href;
                                  }
                                  const hashIndex = href.indexOf("#");
                                  if (hashIndex >= 0) {
                                    return href.slice(hashIndex);
                                  }
                                  return "";
                                }
                                """,
                            )
                        ).strip()
                    except Exception:
                        target_selector = ""
                    try:
                        should_click = await handle.evaluate(
                            """
                            (el) => {
                              const isVisible = (node) => {
                                if (!node) return false;
                                const style = window.getComputedStyle(node);
                                if (style.display === "none" || style.visibility === "hidden") {
                                  return false;
                                }
                                const rect = node.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                              };

                              if (!isVisible(el)) {
                                return false;
                              }

                              if (el.hasAttribute("disabled")) {
                                return false;
                              }

                              const ariaDisabled = String(el.getAttribute("aria-disabled") || "").toLowerCase();
                              if (ariaDisabled === "true") {
                                return false;
                              }

                              const ariaExpanded = String(el.getAttribute("aria-expanded") || "").toLowerCase();
                              if (ariaExpanded === "true") {
                                return false;
                              }

                              const directTarget = String(
                                el.getAttribute("data-target") || el.getAttribute("aria-controls") || "",
                              ).trim();
                              let targetSelector = "";
                              if (directTarget) {
                                targetSelector = directTarget.startsWith("#")
                                  ? directTarget
                                  : `#${directTarget.replace(/^#/, "")}`;
                              } else {
                                const href = String(el.getAttribute("href") || "").trim();
                                if (href.startsWith("#")) {
                                  targetSelector = href;
                                } else {
                                  const hashIndex = href.indexOf("#");
                                  if (hashIndex >= 0) {
                                    targetSelector = href.slice(hashIndex);
                                  }
                                }
                              }

                              if (targetSelector) {
                                try {
                                  const target = document.querySelector(targetSelector);
                                  if (target && isVisible(target)) {
                                    return false;
                                  }
                                } catch {
                                  // ignore invalid selector derived from attribute value
                                }
                              }

                              return true;
                            }
                            """,
                        )
                    except Exception:
                        should_click = True

                    if not should_click:
                        continue

                    try:
                        await candidate.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass

                    await self._maybe_humanize_locator_before_click(
                        candidate,
                        reason="reveal_answer",
                    )

                    clicked = False
                    try:
                        await candidate.click(timeout=1500)
                        clicked = True
                    except Exception:
                        try:
                            await handle.evaluate("(el) => el.click()")
                            clicked = True
                        except Exception:
                            clicked = False

                    if clicked:
                        clicked_count += 1
                        if target_selector and target_selector not in reveal_targets:
                            reveal_targets.append(target_selector)
            except Exception:
                continue

        self.state.notes["last_reveal_clicked_count"] = clicked_count
        self.state.notes["last_reveal_targets"] = reveal_targets

        if clicked_count > 0:
            await self._wait_for_answer_reveal(
                timeout_ms=2800,
                target_selectors=reveal_targets,
            )

        return clicked_count > 0

    async def click_next(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        selectors = self._merge_selector_chains(
            self._selector_chain("next_buttons"),
            [
                "a[rel='next']",
                "a[href*='/page-']",
                "a[href*='page=']",
                ".pagination a",
                "a:has-text('Next Page')",
                "a:has-text('Next Question')",
                "a:has-text('Next')",
                "button:has-text('Next')",
            ],
        )

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if await self._click_ranked_next_candidates(locator, min_score=1):
                    return True
            except Exception:
                continue

        # As a last resort, allow weaker next-controls when no page-navigation signal was found.
        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if await self._click_ranked_next_candidates(locator, min_score=0):
                    return True
            except Exception:
                continue

        return False

    async def has_next_page(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        selectors = self._merge_selector_chains(
            self._selector_chain("next_buttons"),
            [
                "a[rel='next']",
                "a[href*='/page-']",
                "a[href*='page=']",
                ".pagination a",
                ".pager a",
                "a",
                "button",
            ],
        )

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if await self._click_ranked_next_candidates(locator, min_score=1, dry_run=True):
                    return True
            except Exception:
                continue

        return False

    async def _click_ranked_next_candidates(
        self,
        locator: Locator,
        *,
        min_score: int = -999,
        dry_run: bool = False,
    ) -> bool:
        count = await locator.count()
        if count == 0:
            return False

        current_url = self.page.url if self.page else ""
        current_path = (urlparse(current_url).path or "").rstrip("/").lower()
        current_match = re.match(r"^(.*)/(\d+)(?:\.[a-z0-9]+)?$", current_path) if current_path else None
        scope_host = self._scope_host()
        scope_prefix = self._scope_path_prefix().lower()

        def _resolved_path(raw_href: str) -> str:
            if not raw_href:
                return ""
            try:
                resolved = urljoin(current_url, raw_href)
                return (urlparse(resolved).path or "").rstrip("/").lower()
            except Exception:
                return ""

        def _resolved_url(raw_href: str) -> str:
            if not raw_href:
                return ""
            try:
                return urljoin(current_url, raw_href)
            except Exception:
                return ""

        ranked: list[tuple[int, int]] = []
        upper_bound = min(count, 30)

        for index in range(upper_bound):
            candidate = locator.nth(index)

            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue

            try:
                disabled_attr = await candidate.get_attribute("disabled")
                aria_disabled = (await candidate.get_attribute("aria-disabled") or "").strip().lower()
                if disabled_attr is not None or aria_disabled == "true":
                    continue
            except Exception:
                continue

            try:
                text = _clean_text(await candidate.inner_text(timeout=500)).lower()
            except Exception:
                text = ""

            try:
                href_raw = ((await candidate.get_attribute("href")) or "").strip()
                href = href_raw.lower()
                rel = ((await candidate.get_attribute("rel")) or "").strip().lower()
            except Exception:
                href_raw = ""
                href = ""
                rel = ""

            resolved_url = _resolved_url(href_raw)
            resolved = urlparse(resolved_url) if resolved_url else None
            target_host = ((resolved.netloc if resolved else "") or "").strip().lower()

            target_path = _resolved_path(href_raw)
            target_match = re.match(r"^(.*)/(\d+)(?:\.[a-z0-9]+)?$", target_path) if target_path else None
            sibling_direction = 0
            if current_match and target_match and current_match.group(1) == target_match.group(1):
                try:
                    sibling_direction = int(target_match.group(2)) - int(current_match.group(2))
                except ValueError:
                    sibling_direction = 0

            score = 0
            if re.search(r"/view/\d+/?$", href):
                score += 10
            if "/page-" in href or "page=" in href:
                score += 7
            if sibling_direction > 0:
                score += 10
                if sibling_direction == 1:
                    score += 3
            elif sibling_direction < 0:
                score -= 10
            elif current_match and target_match and current_match.group(1) == target_match.group(1):
                if target_path == current_path:
                    score -= 8
                else:
                    score += 4
            if "next questions" in text:
                score += 6
            if "next page" in text:
                score += 5
            if "next" in rel:
                score += 4
            if text == "next" or text.startswith("next "):
                score += 2
            if "previous" in text or text == "prev" or text.startswith("prev "):
                score -= 8
            if "prev" in rel:
                score -= 8
            if re.search(r"\bnext question\b", text):
                score -= 6
            if "collapse_" in href or "answerq" in href:
                score -= 6

            out_of_scope = False
            if resolved_url and scope_host and target_host and target_host != scope_host:
                out_of_scope = True

            if resolved_url and scope_prefix and scope_prefix != "/":
                normalized_target_path = target_path or "/"
                in_scope_path = (
                    normalized_target_path == scope_prefix
                    or normalized_target_path.startswith(f"{scope_prefix}/")
                )
                if in_scope_path:
                    score += 3
                else:
                    out_of_scope = True

            if "/features/" in target_path:
                out_of_scope = True

            if out_of_scope:
                continue

            ranked.append((score, index))

        if not ranked:
            return False

        ranked.sort(reverse=True)
        for score, index in ranked:
            if score < min_score:
                continue
            if dry_run:
                return True
            candidate = locator.nth(index)
            try:
                await self._maybe_humanize_locator_before_click(
                    candidate,
                    reason="next_navigation",
                )
                await candidate.click(timeout=1500)
                return True
            except Exception:
                continue

        return False

    def _scope_host(self) -> str:
        configured_host = str(self.state.notes.get("crawl_scope_host") or "").strip().lower()
        return configured_host

    def _scope_path_prefix(self) -> str:
        configured_prefix = str(self.state.notes.get("crawl_scope_path_prefix") or "").strip()
        if configured_prefix:
            normalized = configured_prefix.rstrip("/")
            return normalized or "/"

        return "/"

    async def _materialize_question_containers(self, *, max_candidates: int) -> None:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        target_count = max(1, int(max_candidates or DEFAULT_MAX_PAGE_CANDIDATES))
        max_passes = 8
        stable_rounds = 0
        previous_counts: tuple[int, int] | None = None
        best_visible = 0
        best_total = 0
        last_snapshot: dict[str, int | bool] = {
            "rootCount": 0,
            "visibleRootCount": 0,
            "didScroll": False,
            "scrollY": 0,
        }

        for _ in range(max_passes):
            try:
                snapshot = await self.page.evaluate(
                    """
                    ({ containerSelectors, fallbackSelectors }) => {
                      const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                      const isVisible = (node) => {
                        if (!node) return false;
                        const style = window.getComputedStyle(node);
                        if (style.display === "none" || style.visibility === "hidden") return false;
                        const rect = node.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                      };

                      const collectRoots = (selectors) => {
                        const roots = [];
                        const seen = new Set();
                        for (const selector of selectors || []) {
                          let nodes = [];
                          try {
                            nodes = Array.from(document.querySelectorAll(selector));
                          } catch {
                            continue;
                          }

                          for (const node of nodes) {
                            if (!node || seen.has(node)) continue;
                            seen.add(node);
                            if (clean(node.innerText).length > 0) {
                              roots.push(node);
                            }
                          }
                        }
                        return roots;
                      };

                      let roots = collectRoots(containerSelectors);
                      if (roots.length === 0) {
                        roots = collectRoots(fallbackSelectors);
                      }

                      const visibleRoots = roots.filter(isVisible);

                      const beforeY = window.scrollY || 0;
                      let didScroll = false;
                      if (roots.length > 0) {
                        const nextIndex = Math.min(
                          roots.length - 1,
                          Math.max(0, visibleRoots.length - 1),
                        );
                        const target = roots[nextIndex] || roots[roots.length - 1];
                        if (target && typeof target.scrollIntoView === "function") {
                          target.scrollIntoView({ block: "end", inline: "nearest" });
                          didScroll = true;
                        }
                      } else {
                        const delta = Math.max(300, Math.round(window.innerHeight * 0.75));
                        window.scrollBy(0, delta);
                        didScroll = true;
                      }

                      const afterY = window.scrollY || 0;

                      return {
                        rootCount: roots.length,
                        visibleRootCount: visibleRoots.length,
                        didScroll,
                        scrollY: afterY,
                        scrollDelta: Math.abs(afterY - beforeY),
                      };
                    }
                    """,
                    {
                        "containerSelectors": self._selector_chain("question_containers"),
                        "fallbackSelectors": ["[role='tabpanel']", ".tab-pane", ".panel-body", "article", "section"],
                    },
                )
            except Exception as exc:
                if _is_transient_page_evaluate_error(exc):
                    await asyncio.sleep(0.2)
                    continue
                raise

            if isinstance(snapshot, dict):
                root_count = int(snapshot.get("rootCount", 0) or 0)
                visible_count = int(snapshot.get("visibleRootCount", 0) or 0)
                did_scroll = bool(snapshot.get("didScroll", False))
                scroll_y = int(snapshot.get("scrollY", 0) or 0)
                scroll_delta = int(snapshot.get("scrollDelta", 0) or 0)
            else:
                root_count = 0
                visible_count = 0
                did_scroll = False
                scroll_y = 0
                scroll_delta = 0

            last_snapshot = {
                "rootCount": root_count,
                "visibleRootCount": visible_count,
                "didScroll": did_scroll,
                "scrollY": scroll_y,
                "scrollDelta": scroll_delta,
            }

            best_visible = max(best_visible, visible_count)
            best_total = max(best_total, root_count)

            if visible_count >= target_count or root_count >= target_count:
                break

            current_counts = (root_count, visible_count)
            if previous_counts == current_counts:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_counts = current_counts

            if stable_rounds >= 2:
                break

            if not did_scroll and scroll_delta == 0 and root_count == 0:
                break

            if self.config.humanize:
                await self._human_pause(
                    min_ms=max(60, self.config.human_delay_min_ms),
                    max_ms=max(140, self.config.human_delay_max_ms),
                    reason="materialize_scroll",
                )
            else:
                await asyncio.sleep(0.18)

        self.state.notes["last_candidate_materialization"] = {
            "target_count": target_count,
            "best_visible_roots": best_visible,
            "best_total_roots": best_total,
            "final_snapshot": last_snapshot,
        }

    async def current_fingerprint(self) -> str:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        question, _ = await self._first_text(self._selector_chain("question"))
        options, _ = await self._collect_options(self._selector_chain("options"))
        answer, _ = await self._first_text(self._answer_selector_chain())

        material = "|".join([
            _clean_text(question),
            "::".join(_clean_text(item) for item in options[:6]),
            _clean_text(answer),
        ])

        digest = hashlib.sha1(material.encode("utf-8")).hexdigest()
        return digest

    async def wait_for_fingerprint_change(
        self,
        previous_fingerprint: str,
        timeout_ms: int = 3000,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            current = await self.current_fingerprint()
            if current != previous_fingerprint:
                return True
            await asyncio.sleep(0.2)
        return False

    async def _wait_for_answer_reveal(
        self,
        timeout_ms: int = 800,
        target_selectors: list[str] | None = None,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        answer_selectors = self._answer_selector_chain(target_selectors=target_selectors)

        while asyncio.get_running_loop().time() < deadline:
            answer_text, _ = await self._first_text(answer_selectors)
            if _clean_text(answer_text):
                return
            await asyncio.sleep(0.15)

    async def screenshot(self, path: str) -> str:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")
        await self.page.screenshot(path=path, full_page=True)
        return path

    async def extract_candidate(self) -> ExtractionCandidate:
        question_chain = self._selector_chain("question")
        options_chain = self._selector_chain("options")
        answer_chain = self._answer_selector_chain()

        question, question_selector = await self._first_text(question_chain)
        options, options_selector = await self._collect_options(options_chain)
        answer_text, answer_selector = await self._first_text(answer_chain)

        if not question or len(options) < 2:
            discovered = await self.discover_selector_candidates()
            question_chain = self._merge_selector_chains(
                question_chain,
                discovered.get("question", []),
            )
            options_chain = self._merge_selector_chains(
                options_chain,
                discovered.get("options", []),
            )
            answer_chain = self._merge_selector_chains(
                answer_chain,
                discovered.get("answer", []),
            )

            question, question_selector = await self._first_text(question_chain)
            options, options_selector = await self._collect_options(options_chain)
            answer_text, answer_selector = await self._first_text(answer_chain)

            self.state.notes["last_discovered_selectors"] = discovered

        warnings: list[str] = []
        score = 0.0

        if question:
            score += 0.45
        else:
            warnings.append("question_missing")

        if len(options) >= 2:
            score += 0.35
        else:
            warnings.append("insufficient_options")

        if answer_text:
            score += 0.2
        else:
            warnings.append("answer_missing")

        quality_score = score
        if len(options) >= 4:
            quality_score += 0.05
        if question and len(question) >= 20:
            quality_score += 0.03
        quality_score = min(1.0, round(quality_score, 3))

        used_selectors = {}
        if question_selector:
            used_selectors["question"] = question_selector
        if options_selector:
            used_selectors["options"] = options_selector
        if answer_selector:
            used_selectors["answer"] = answer_selector

        return ExtractionCandidate(
            question=_clean_text(question),
            option_texts=[_clean_text(item) for item in options],
            answer_text=_clean_text(answer_text),
            confidence=round(score, 3),
            quality_score=quality_score,
            warnings=warnings,
            used_selectors=used_selectors,
        )

    async def discover_selector_candidates(self) -> dict[str, list[str]]:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        raw = await self.page.evaluate(
            """
            () => {
              const toSelector = (el) => {
                if (!el) return "";
                if (el.id) return `#${el.id}`;
                const cls = (el.className || "")
                  .split(/\\s+/)
                  .filter(Boolean)
                  .slice(0, 3)
                  .join(".");
                if (cls) return `${el.tagName.toLowerCase()}.${cls}`;
                return el.tagName.toLowerCase();
              };

              const uniq = (items) => Array.from(new Set(items.filter(Boolean))).slice(0, 12);

              const questionEls = Array.from(document.querySelectorAll("p, h1, h2, h3, h4, .question, .question-text"))
                .filter((el) => {
                  const text = (el.innerText || "").trim();
                  return text.length > 20 && (text.includes("?") || /choose|which|what/i.test(text));
                })
                .slice(0, 10);

              const optionEls = [];
              Array.from(document.querySelectorAll("ol, ul")).forEach((list) => {
                const children = list.querySelectorAll(":scope > li");
                if (children.length >= 2) {
                  optionEls.push(...Array.from(children));
                }
              });
              optionEls.push(...Array.from(document.querySelectorAll(".option, .ui-selectee")));

              const answerEls = Array.from(document.querySelectorAll("p, div, span"))
                                .filter((el) => /answer\\(s\\)|correct answer|answer\\s*:/i.test((el.innerText || "").trim()))
                .slice(0, 12);

              return {
                question: uniq(questionEls.map(toSelector)),
                options: uniq(optionEls.map(toSelector)),
                answer: uniq(answerEls.map(toSelector)),
              };
            }
            """,
        )

        result: dict[str, list[str]] = {"question": [], "options": [], "answer": []}
        if isinstance(raw, dict):
            for key in result:
                values = raw.get(key)
                if isinstance(values, list):
                    result[key] = [str(item).strip() for item in values if str(item).strip()]
        return result

    async def _first_text(self, selectors: Iterable[str]) -> tuple[str, str]:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() == 0:
                    continue
                text = await locator.inner_text(timeout=1000)
                cleaned = _clean_text(text)
                if cleaned:
                    return cleaned, selector
            except Exception:
                continue

        return "", ""

    async def _collect_options(self, selectors: Iterable[str]) -> tuple[list[str], str]:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
                if count == 0:
                    continue

                raw_items: list[str] = []
                for index in range(count):
                    text = await locator.nth(index).inner_text(timeout=1000)
                    cleaned = _clean_text(text)
                    if cleaned:
                        raw_items.append(cleaned)

                if len(raw_items) > MAX_OPTIONS_PER_QUESTION:
                    block = _select_single_question_option_block(raw_items)
                    if len(block) >= 2:
                        return block, selector
                    continue

                items = _unique_preserve(raw_items)

                if len(items) >= 2:
                    return items, selector
            except Exception:
                continue

        return [], ""

    def _recent_reveal_targets(self) -> list[str]:
        stored = self.state.notes.get("last_reveal_targets")
        if not isinstance(stored, list):
            return []

        targets: list[str] = []
        for value in stored:
            selector = str(value).strip()
            if selector and selector not in targets:
                targets.append(selector)
        return targets

    def _target_answer_chain(self, target_selectors: list[str]) -> list[str]:
        chain: list[str] = []
        for selector in target_selectors:
            stripped = (selector or "").strip()
            if not stripped:
                continue

            candidates = [
                stripped,
                f"{stripped} p.question-answer",
                f"{stripped} .correct-answer-box",
                f"{stripped} p",
                f"{stripped} [class*='answer']",
            ]
            for candidate in candidates:
                if candidate not in chain:
                    chain.append(candidate)
        return chain

    def _answer_selector_chain(self, *, target_selectors: list[str] | None = None) -> list[str]:
        if target_selectors is None:
            target_selectors = self._recent_reveal_targets()
        target_chain = self._target_answer_chain(target_selectors)
        return self._merge_selector_chains(target_chain, self._selector_chain("answer"))

    def _selector_chain(self, key: str) -> list[str]:
        profile_values = list(getattr(self.selector_profile, key, []))
        override_values = self.state.selector_overrides.get(key, [])

        chain: list[str] = []
        for selector in [*override_values, *profile_values]:
            stripped = (selector or "").strip()
            if stripped and stripped not in chain:
                chain.append(stripped)
        return chain

    def _merge_selector_chains(self, primary: list[str], fallback: list[str]) -> list[str]:
        merged: list[str] = []
        for selector in [*primary, *fallback]:
            stripped = (selector or "").strip()
            if stripped and stripped not in merged:
                merged.append(stripped)
        return merged

    def _ensure_humanization_notes(self) -> dict[str, Any]:
        current = self.state.notes.get("humanization")
        if not isinstance(current, dict):
            current = {}

        current["enabled"] = bool(self.config.humanize)
        current.setdefault("pause_count", 0)
        current.setdefault("total_pause_ms", 0)
        current.setdefault("idle_breaks", 0)
        current.setdefault("mouse_moves", 0)
        current.setdefault("last_reason", "")
        self.state.notes["humanization"] = current
        return current

    def _pause_window(self, *, min_ms: int, max_ms: int) -> tuple[int, int]:
        lower = max(0, int(min_ms))
        upper = max(lower, int(max_ms))
        return lower, upper

    async def _human_pause(self, *, min_ms: int, max_ms: int, reason: str) -> int:
        lower, upper = self._pause_window(min_ms=min_ms, max_ms=max_ms)
        if upper <= 0:
            return 0

        delay_ms = self._rng.randint(lower, upper)
        if delay_ms <= 0:
            return 0

        await asyncio.sleep(delay_ms / 1000)

        notes = self._ensure_humanization_notes()
        notes["pause_count"] = int(notes.get("pause_count", 0) or 0) + 1
        notes["total_pause_ms"] = int(notes.get("total_pause_ms", 0) or 0) + delay_ms
        notes["last_reason"] = str(reason or "")
        return delay_ms

    async def maybe_human_delay(self, reason: str = "action") -> None:
        if not self.config.humanize:
            return

        await self._human_pause(
            min_ms=self.config.human_delay_min_ms,
            max_ms=self.config.human_delay_max_ms,
            reason=reason,
        )

    async def maybe_human_idle_break(self, reason: str = "idle_break") -> None:
        if not self.config.humanize:
            return

        chance = min(1.0, max(0.0, float(self.config.human_idle_break_chance)))
        if chance <= 0 or self._rng.random() >= chance:
            return

        notes = self._ensure_humanization_notes()
        notes["idle_breaks"] = int(notes.get("idle_breaks", 0) or 0) + 1
        await self._human_pause(
            min_ms=self.config.human_idle_break_min_ms,
            max_ms=self.config.human_idle_break_max_ms,
            reason=reason,
        )

    async def maybe_human_read_pause(self, reason: str = "read_pause") -> None:
        if not self.config.humanize:
            return

        await self._human_pause(
            min_ms=self.config.human_read_pause_min_ms,
            max_ms=self.config.human_read_pause_max_ms,
            reason=reason,
        )
        await self.maybe_human_idle_break(reason=f"{reason}_idle")

    async def _maybe_humanize_locator_before_click(self, locator: Locator, *, reason: str) -> None:
        if not self.config.humanize or self.page is None:
            return

        if self.config.human_mouse_move:
            try:
                box = await locator.bounding_box()
            except Exception:
                box = None

            if box:
                try:
                    x = float(box["x"]) + float(box["width"]) * self._rng.uniform(0.25, 0.75)
                    y = float(box["y"]) + float(box["height"]) * self._rng.uniform(0.25, 0.75)
                    steps = self._rng.randint(8, 20)
                    await self.page.mouse.move(x, y, steps=steps)
                    notes = self._ensure_humanization_notes()
                    notes["mouse_moves"] = int(notes.get("mouse_moves", 0) or 0) + 1
                    await self._human_pause(min_ms=20, max_ms=90, reason=f"{reason}_mouse_settle")
                except Exception:
                    pass

        await self._human_pause(min_ms=45, max_ms=150, reason=f"{reason}_pre_click")


BrowserRuntime.extract_page_candidates = _extract_page_candidates_impl
