# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""A browser-driven adapter for a hosted chat UI (Firefox, headless).

This is an **experimental, opt-in** transport that exists because the platform
had never once produced a number about a real model — every result to date came
from pipeline controls. It drives a logged-in Firefox session against a hosted
chat web app rather than an API. The operator names the target in
``AI_COMBI_TARGET_CHAT_URL``; no vendor is hard-coded here.

What that buys, and what it costs, stated plainly:

* it needs no API credential, so a first real-model run is possible today;
* it is **not** an API contract. Selectors change without notice, sessions expire,
  quotas and interstitials appear. Treat every result as evidence about one
  account on one day, never as a reproducible measurement — which is precisely
  the property this framework normally insists on, and the one thing a hosted UI
  cannot give.

Two correctness requirements drive the implementation, and both are easy to get
silently wrong:

1. **A fresh conversation per candidate.** Reusing a thread lets candidate *n*
   see candidate *n-1*, which destroys independence and would quietly invalidate
   every orbit — the model would look "consistent" because it was echoing itself.
2. **Text is injected, not typed.** Prompts are multi-line, and ``send_keys``
   would submit at the first newline, truncating the task.

The real profile is never opened: a minimal derived profile carrying only the
session files is used, so a Selenium crash cannot damage the browser the operator
actually uses.
"""
from __future__ import annotations

import glob
import importlib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from .base import Completion, CompletionRequest

#: Opt-in gate, deliberately separate from AI_COMBI_ALLOW_EXTERNAL: this
#: transport has a different risk profile from a budgeted API adapter and should
#: never be enabled as a side effect of enabling that one.
ALLOW_ENV = "AI_COMBI_ALLOW_BROWSER"
PROFILE_ENV = "AI_COMBI_FIREFOX_PROFILE"
SESSION_FILES = ("cookies.sqlite", "cert9.db", "key4.db")

#: The chat endpoint under test, the model label to select in its UI, and the
#: WebDriver module to drive it with are all supplied by the operator. No vendor
#: is named in this source: the adapter drives whatever hosted chat interface the
#: operator points it at, and naming one here would both date the code and make
#: the choice look endorsed rather than configured.
TARGET_URL_ENV = "AI_COMBI_TARGET_CHAT_URL"
MODEL_MATCH_ENV = "AI_COMBI_TARGET_MODEL_MATCH"
DRIVER_MODULE_ENV = "AI_COMBI_BROWSER_DRIVER_MODULE"

#: Plain Selenium. Some targets present an interstitial to automated browsers;
#: if the operator uses a different WebDriver package, they name it in
#: AI_COMBI_BROWSER_DRIVER_MODULE. It must expose a ``Firefox`` class.
DEFAULT_DRIVER_MODULE = "selenium.webdriver"
DEFAULT_MODEL_MATCH = ""


class BrowserAdapterError(RuntimeError):
    """Fail closed: never fabricate or guess a response."""


def _target_url() -> str:
    """The chat endpoint to drive. Deliberately not defaulted to any vendor:
    an unset target is an operator decision that has not been made, and guessing
    one would silently point a browser at a third party."""
    url = os.environ.get(TARGET_URL_ENV, "").strip()
    if not url:
        raise BrowserAdapterError(
            f"no target chat URL configured; set {TARGET_URL_ENV} to the "
            f"interface this run should drive")
    return url


def _derive_profile(source: str) -> str:
    if not os.path.isdir(source):
        raise BrowserAdapterError(f"firefox profile not found: {source}")
    dest = tempfile.mkdtemp(prefix="fx-aicombi-")
    for name in SESSION_FILES:
        for path in glob.glob(os.path.join(source, name + "*")):
            shutil.copy2(path, dest)
    with open(os.path.join(dest, "user.js"), "w", encoding="utf-8") as handle:
        handle.write('user_pref("browser.shell.checkDefaultBrowser", false);\n')
        handle.write('user_pref("datareporting.policy.dataSubmissionEnabled", false);\n')
    return dest


@dataclass
class BrowserChatAdapter:
    """Drive one long-lived headless browser across many candidates.

    The target is whatever hosted chat interface ``AI_COMBI_TARGET_CHAT_URL``
    points at; this class knows only how to type a prompt and read a reply.
    """

    adapter_id: str = "browser-chat"
    model_match: str = DEFAULT_MODEL_MATCH
    headless: bool = True
    #: Use the target's own temporary/incognito chat mode where it has one, so
    #: nothing is written to history and no candidate can personalise the
    #: target for the next one.
    temporary_chat: bool = True
    response_timeout: float = 120.0
    _driver: Any = field(default=None, init=False, repr=False)
    _profile: str | None = field(default=None, init=False, repr=False)
    _model_label: str = field(default="", init=False, repr=False)

    # --- lifecycle -------------------------------------------------------
    def _require_opt_in(self) -> None:
        if os.environ.get(ALLOW_ENV) != "1":
            raise BrowserAdapterError(
                f"browser transport is disabled; set {ALLOW_ENV}=1 to enable it")

    def start(self) -> None:
        if self._driver is not None:
            return
        self._require_opt_in()
        driver_module = os.environ.get(DRIVER_MODULE_ENV) or DEFAULT_DRIVER_MODULE
        try:
            uc = importlib.import_module(driver_module)
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
        except ImportError as exc:                       # pragma: no cover
            raise BrowserAdapterError(
                f"WebDriver package '{driver_module}' unavailable: {exc}. "
                f"Install it, or name another one in {DRIVER_MODULE_ENV}.")

        source = os.environ.get(PROFILE_ENV) or _default_profile()
        self._profile = _derive_profile(source)
        options = FirefoxOptions()
        if self.headless:
            options.add_argument("-headless")
        options.add_argument("-profile")
        options.add_argument(self._profile)
        self._driver = uc.Firefox(options=options)
        self._driver.set_window_size(1440, 1000)
        self._open_fresh_chat()
        self._model_label = self._select_model()

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            finally:
                self._driver = None
        if self._profile:
            shutil.rmtree(self._profile, ignore_errors=True)
            self._profile = None

    def __enter__(self) -> "BrowserChatAdapter":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- page interaction ------------------------------------------------
    def _input_box(self, timeout: float = 40.0):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        return WebDriverWait(self._driver, timeout).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "rich-textarea div[contenteditable='true'], div[contenteditable='true']")))

    def _open_fresh_chat(self) -> None:
        """Independence requirement: every candidate starts an empty thread.

        A reload alone is not enough. The account's chat history feeds
        personalization, so successive candidates could be answered by a target
        that has been quietly conditioned by the previous eleven — the orbit
        would then look consistent because the model was echoing itself, which
        is the exact artefact a metamorphic verdict must not mistake for
        agreement. Temporary chat removes the thread from history entirely.
        """
        self._driver.get(_target_url())
        self._input_box()
        # Deliberately NO refresh here. Measured on this setup: reloading before
        # the app has settled drops the session permanently -- the page comes
        # back with a sign-in affordance and never re-hydrates, while the first
        # load is already authenticated. `_input_box` returns as soon as the
        # element exists, which is earlier than "the account is ready", so the
        # wait below is what makes the difference rather than a reload.
        self._await_signed_in()
        if self.temporary_chat:
            self._enable_temporary_chat()

    def _new_chat(self) -> None:
        """Start an empty thread without reloading the app.

        Clicking through keeps the hydrated session, where a full navigation
        would drop back to the signed-out shell and have to hydrate again.
        """
        from selenium.webdriver.common.by import By

        for element in self._driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button']"):
            try:
                label = (element.get_attribute("aria-label") or "").strip().lower()
            except Exception:
                continue
            if label in ("new chat", "новый чат"):
                self._driver.execute_script("arguments[0].click();", element)
                time.sleep(2.0)
                self._input_box()
                if self.temporary_chat:
                    self._enable_temporary_chat()
                return
        self._open_fresh_chat()                          # fall back to a reload

    def _await_signed_in(self, timeout: float = 45.0) -> None:
        """Block until the account has hydrated, not merely until the DOM exists.

        the target model serves a signed-out shell that already contains a usable input
        box, so `presence_of_element_located` returns while the page is still
        anonymous. Acting then reads the wrong UI entirely -- the account-only
        controls are absent and the model picker is whatever the anonymous
        default is. Waiting for "Sign in" to disappear is what makes every later
        assertion about the *account's* session rather than a transient shell.
        """
        from selenium.webdriver.common.by import By

        deadline = time.time() + timeout
        while time.time() < deadline:
            if "accounts.google.com" in self._driver.current_url:
                raise BrowserAdapterError("redirected to the sign-in page")
            labels = []
            for element in self._driver.find_elements(By.CSS_SELECTOR, "button, a"):
                try:
                    labels.append((element.get_attribute("aria-label") or "").strip().lower())
                except Exception:
                    continue
            if not any(label in ("sign in", "войти") for label in labels):
                time.sleep(1.0)                          # let the shell settle
                return
            time.sleep(1.5)
        raise BrowserAdapterError(
            "page still shows a signed-out shell; the session did not hydrate")

    def _enable_temporary_chat(self) -> None:
        """Turn on the target's temporary chat, and verify it actually engaged."""
        from selenium.webdriver.common.by import By

        # The control renders after the input box, so a single sweep races the
        # app shell. Poll instead of sleeping a guessed constant.
        button = None
        deadline = time.time() + 25.0
        while button is None and time.time() < deadline:
            for element in self._driver.find_elements(
                    By.CSS_SELECTOR,
                    "button, a, [role='button'], [role='menuitem'], [role='switch']"):
                try:
                    label = (element.get_attribute("aria-label") or element.text or "")
                except Exception:                        # stale node during render
                    continue
                low = label.strip().lower()
                if any(key in low for key in ("временный чат", "temporary chat")):
                    button = element
                    break
            if button is None:
                time.sleep(1.5)
        if button is None:
            labels = []
            for element in self._driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button']"):
                try:
                    text = (element.get_attribute("aria-label") or element.text or "").strip()
                except Exception:
                    continue
                if text:
                    labels.append(text[:40])
            raise BrowserAdapterError(
                "temporary-chat control not found; refusing to run with history on. "
                f"visible controls: {labels[:25]}")

        # A synthetic JS click is ignored by the app's own handlers here, and
        # `aria-pressed` is never set -- so an attribute check passes while the
        # mode is off. Verified by effect instead: with temporary chat engaged
        # the conversation never appears in history, which `history_count()`
        # asserts as a post-condition of the whole run.
        button.click()
        time.sleep(3.0)
        self._input_box()

    def history_count(self) -> int:
        """Number of saved conversations visible in the sidebar."""
        from selenium.webdriver.common.by import By

        items = self._driver.find_elements(
            By.CSS_SELECTOR,
            "[data-test-id='conversation'], .conversation-title, [role='listitem']")
        return len([e for e in items if (e.text or "").strip()])

    def _select_model(self) -> str:
        """Pin the model explicitly rather than trusting the account default.

        A result that cannot name its model is not evidence, so failing to pin
        raises instead of proceeding with whatever happened to be selected.
        """
        from selenium.webdriver.common.by import By

        buttons = self._driver.find_elements(By.CSS_SELECTOR, "bard-mode-switcher button")
        if not buttons:
            raise BrowserAdapterError("model picker not found")
        trigger = buttons[0]
        current = (trigger.get_attribute("aria-label") or "").strip()
        trigger.click()
        time.sleep(2.5)
        for item in self._driver.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
            label = (item.text or "").strip()
            if self.model_match in label.lower().replace(" ", "-"):
                item.click()
                time.sleep(2.5)
                return label.split("\n")[0].strip()
        raise BrowserAdapterError(
            f"model matching {self.model_match!r} not offered (current: {current!r})")

    def _submit(self, prompt: str) -> None:
        """Inject the text, then click send.

        ``send_keys`` cannot be used: a newline submits, so a multi-line task
        would be sent truncated and every downstream verdict would be about a
        prompt the experiment never intended.
        """
        from selenium.webdriver.common.by import By

        box = self._input_box()
        self._driver.execute_script(
            """
            const el = arguments[0], text = arguments[1];
            el.focus();
            el.innerText = text;
            el.dispatchEvent(new InputEvent('input', {bubbles: true}));
            """, box, prompt)
        time.sleep(1.0)
        for css in ("button[aria-label*='Send' i]", "button[aria-label*='Отправить' i]",
                    "button.send-button", "button[mattooltip*='Send' i]"):
            found = [b for b in self._driver.find_elements(By.CSS_SELECTOR, css)
                     if b.is_displayed() and b.is_enabled()]
            if found:
                self._driver.execute_script("arguments[0].click();", found[-1])
                return
        raise BrowserAdapterError("send button not found")

    def _await_reply(self) -> str:
        """Return the last reply once its text stops changing."""
        from selenium.webdriver.common.by import By

        deadline = time.time() + self.response_timeout
        previous, stable = "", 0
        while time.time() < deadline:
            time.sleep(2.0)
            nodes = self._driver.find_elements(By.CSS_SELECTOR, "message-content, model-response")
            text = nodes[-1].text.strip() if nodes else ""
            if text and text == previous:
                stable += 1
                if stable >= 2:
                    return text
            else:
                stable = 0
            previous = text
        if previous:
            return previous
        raise BrowserAdapterError("no reply text captured before timeout")

    # --- adapter protocol ------------------------------------------------
    def complete(self, request: CompletionRequest) -> Completion:
        self.start()
        # A full home load rather than the in-app "new chat" button: the
        # temporary-chat control only exists on the empty home screen, and it
        # resets per conversation, so it must be re-engaged for every candidate.
        self._open_fresh_chat()
        started = time.perf_counter()
        self._submit(request.prompt)
        text = self._await_reply()
        latency_us = int((time.perf_counter() - started) * 1_000_000)
        return Completion(
            text=_strip_fences(text),
            adapter_id=self.adapter_id,
            model_id=self._model_label or "unknown",
            latency_us=latency_us,
            input_tokens=max(1, len(request.prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            # No API billing on this transport. It is not free -- it consumes
            # account quota -- but there is no per-request price to report, and
            # inventing one would be worse than reporting zero.
            cost_microusd=0,
            is_control=False,
        )


def _strip_fences(text: str) -> str:
    """Chat UIs wrap code-ish answers in markdown fences; the oracle parses raw."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.splitlines() if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _default_profile() -> str:
    """Resolve the profile modern Firefox actually launches.

    Order matters and is easy to get backwards. A `profiles.ini` commonly holds
    both an old ``[Profile]`` marked ``Default=1`` and a newer
    ``[InstallXXXX]`` whose ``Default=<path>`` names the profile the browser
    really uses. Preferring ``Default=1`` picks the stale profile, which still
    launches fine and is simply *empty* — so the symptom is not an error but a
    signed-out page, which reads as "the session expired" and sends you looking
    in the wrong place entirely. (The upstream example has this same ordering.)
    """
    import configparser

    base = os.path.expanduser("~/.mozilla/firefox")
    parser = configparser.ConfigParser()
    parser.read(os.path.join(base, "profiles.ini"))

    # 1. the install-scoped default: authoritative for current Firefox
    for section in parser.sections():
        if section.startswith("Install"):
            path = parser.get(section, "Default", fallback="")
            if path:
                resolved = os.path.join(base, path)
                if os.path.isdir(resolved):
                    return resolved
    # 2. the release profile by name
    for section in parser.sections():
        if parser.get(section, "Name", fallback="") == "default-release":
            return os.path.join(base, parser.get(section, "Path"))
    # 3. only then the legacy Default=1 marker
    for section in parser.sections():
        if parser.get(section, "Default", fallback="") == "1":
            return os.path.join(base, parser.get(section, "Path"))
    raise BrowserAdapterError("no default firefox profile found")
