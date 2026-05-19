from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Iterable

from playwright.async_api import (
    Browser,
    BrowserContext,
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

        for selector in self._selector_chain("show_answer_buttons"):
            try:
                locator = self.page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.click(timeout=1000)
                return True
            except Exception:
                continue
        return False

    async def click_next(self) -> bool:
        if self.page is None:
            raise RuntimeError("Browser page not initialized")

        for selector in self._selector_chain("next_buttons"):
            try:
                locator = self.page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.click(timeout=1500)
                return True
            except Exception:
                continue

        fallback = [
            "a:has-text('Next Question')",
            "a:has-text('Next')",
            "button:has-text('Next')",
        ]
        for selector in fallback:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.click(timeout=1500)
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
                  .split(/\s+/)
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

                items: list[str] = []
                for index in range(count):
                    text = await locator.nth(index).inner_text(timeout=1000)
                    cleaned = _clean_text(text)
                    if cleaned and cleaned not in items:
                        items.append(cleaned)

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
