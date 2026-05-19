from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Iterable

from playwright.async_api import (
    Browser,
    BrowserContext,
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

        compact = re.sub(r"[^A-J]", "", part)
        if compact and len(compact) <= 5:
            for letter in compact:
                if letter not in letters:
                    letters.append(letter)

    return letters


MAX_OPTIONS_PER_QUESTION = 8
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


async def _extract_page_candidates_impl(runtime: "BrowserRuntime", max_candidates: int = 20) -> list[ExtractionCandidate]:
        if runtime.page is None:
                raise RuntimeError("Browser page not initialized")

        raw = await runtime.page.evaluate(
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

                    if (roots.length < 2) {
                        const panelRoots = Array.from(document.querySelectorAll("[role='tabpanel']"))
                            .filter((node) => clean(node.innerText).length > 0);
                        roots.splice(0, roots.length, ...panelRoots);
                    }

                    if (roots.length < 2) {
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
                        "containerSelectors": runtime._selector_chain("question_containers"),
                        "questionSelectors": runtime._selector_chain("question"),
                        "optionSelectors": runtime._selector_chain("options"),
                        "answerSelectors": runtime._selector_chain("answer"),
                        "maxCandidates": max_candidates,
                },
        )

        candidates: list[ExtractionCandidate] = []
        if not isinstance(raw, list):
                return candidates

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

    async def reveal_answer(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        seen_controls: set[str] = set()
        clicked_count = 0

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
            except Exception:
                continue

        if clicked_count > 0:
            await self._wait_for_answer_reveal(timeout_ms=1800)

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
                if await self._click_ranked_next_candidates(locator):
                    return True
            except Exception:
                continue

        return False

    async def has_next_page(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        raw = await self.page.evaluate(
            """
            ({ configuredSelectors }) => {
              const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") return false;
                return true;
              };

              const selectors = [
                ...(configuredSelectors || []),
                "a[rel='next']",
                "a[href*='/page-']",
                "a[href*='page=']",
                ".pagination a",
                ".pager a",
                "a",
                "button",
              ];

              const seen = new Set();
              for (const selector of selectors) {
                let nodes = [];
                try {
                  nodes = Array.from(document.querySelectorAll(selector));
                } catch {
                  continue;
                }

                for (const node of nodes) {
                  if (!node || seen.has(node)) continue;
                  seen.add(node);

                  if (!isVisible(node)) continue;
                  if (node.hasAttribute("disabled")) continue;
                  const ariaDisabled = String(node.getAttribute("aria-disabled") || "").toLowerCase();
                  if (ariaDisabled === "true") continue;

                  const text = String(node.innerText || "").replace(/\\s+/g, " ").trim().toLowerCase();
                  const href = String(node.getAttribute("href") || "").trim().toLowerCase();
                  const rel = String(node.getAttribute("rel") || "").trim().toLowerCase();
                  const ariaLabel = String(node.getAttribute("aria-label") || "").trim().toLowerCase();

                  const pageSignal =
                    href.includes("/page-") ||
                    href.includes("page=") ||
                    text.includes("next page") ||
                    ariaLabel.includes("next page") ||
                    rel.includes("next");

                  const questionSignal =
                    text.includes("next question") ||
                    href.includes("collapse_") ||
                    href.includes("answerq");

                  if (pageSignal && !questionSignal) {
                    return true;
                  }
                }
              }

              return false;
            }
            """,
            {
                "configuredSelectors": self._selector_chain("next_buttons"),
            },
        )

        return bool(raw)

    async def _click_ranked_next_candidates(self, locator: Locator, *, min_score: int = -999) -> bool:
        count = await locator.count()
        if count == 0:
            return False

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
                href = ((await candidate.get_attribute("href")) or "").strip().lower()
                rel = ((await candidate.get_attribute("rel")) or "").strip().lower()
            except Exception:
                href = ""
                rel = ""

            score = 0
            if "/page-" in href or "page=" in href:
                score += 7
            if "next page" in text:
                score += 5
            if "next" in rel:
                score += 4
            if text == "next" or text.startswith("next "):
                score += 2
            if "next question" in text:
                score -= 6
            if "collapse_" in href or "answerq" in href:
                score -= 6

            ranked.append((score, index))

        if not ranked:
            return False

        ranked.sort(reverse=True)
        for score, index in ranked:
            if score < min_score:
                continue
            candidate = locator.nth(index)
            try:
                await candidate.click(timeout=1500)
                return True
            except Exception:
                continue

        return False

    async def current_fingerprint(self) -> str:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        question, _ = await self._first_text(self._selector_chain("question"))
        options, _ = await self._collect_options(self._selector_chain("options"))
        answer, _ = await self._first_text(self._selector_chain("answer"))

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
        timeout_ms: int = 5000,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            current = await self.current_fingerprint()
            if current != previous_fingerprint:
                return True
            await asyncio.sleep(0.2)
        return False

    async def _wait_for_answer_reveal(self, timeout_ms: int = 1500) -> None:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        answer_selectors = self._selector_chain("answer")

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
        answer_chain = self._selector_chain("answer")

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
                .filter((el) => /answer\(s\)|correct answer|answer\s*:/i.test((el.innerText || "").trim()))
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


BrowserRuntime.extract_page_candidates = _extract_page_candidates_impl
