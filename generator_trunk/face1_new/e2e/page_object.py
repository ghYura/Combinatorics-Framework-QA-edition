"""Selenium Page Object for every interactive Face 1 new surface.

The object deliberately exposes domain operations (tab, field, grid cell,
template, dialog) instead of scattering XPath strings through tests. Human
labels and structural CSS live in ``selectors.toml``.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Iterator, Sequence

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .selectors import DEFAULT_SELECTORS, SelectorRegistry


def _normalized(text: str) -> str:
    return " ".join((text or "").split())


def _matches(actual: str, expected: str) -> bool:
    actual, expected = _normalized(actual).casefold(), _normalized(expected).casefold()
    return actual == expected or expected in actual


def _displayed(elements: Sequence[WebElement]) -> list[WebElement]:
    found: list[WebElement] = []
    for element in elements:
        try:
            if element.is_displayed():
                found.append(element)
        except StaleElementReferenceException:
            continue
    return found


def _binary(*names: str) -> str | None:
    return next((path for name in names if (path := shutil.which(name))), None)


@contextmanager
def browser_session(
    browser: str,
    download_dir: Path,
    viewport: tuple[int, int],
    *,
    headless: bool = True,
) -> Iterator[WebDriver]:
    """Create a collision-free local browser/driver session.

    Every candidate gets a unique profile and download directory. ChromeDriver
    and GeckoDriver select free service/debug ports themselves, so parallel
    Bundle candidates never share a browser port or profile lock.
    """
    download_dir = Path(download_dir).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = Path(__file__).resolve().parents[1] / "browser_runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    session_root = Path(tempfile.mkdtemp(prefix=f"{browser}-", dir=runtime_root))
    profile = session_root / "profile"
    profile.mkdir()
    browser_download_dir = session_root / "downloads"
    browser_download_dir.mkdir()
    driver: WebDriver | None = None
    try:
        if browser == "chromium":
            executable = os.environ.get("CHROMEDRIVER") or _binary("chromedriver")
            configured_binary = os.environ.get("CHROMIUM_BINARY")
            binary = configured_binary or _binary(
                "chromium", "chromium-browser", "google-chrome", "google-chrome-stable"
            )
            snap_binary = Path("/snap/chromium/current/usr/lib/chromium-browser/chrome")
            if not configured_binary and binary == "/snap/bin/chromium" and snap_binary.is_file():
                binary = str(snap_binary)
            if not executable or not binary:
                raise RuntimeError("Chromium backend requires chromium and chromedriver")
            options = ChromeOptions()
            options.binary_location = binary
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-background-networking")
            options.add_argument("--no-first-run")
            options.add_argument(f"--user-data-dir={profile}")
            options.add_argument(f"--window-size={viewport[0]},{viewport[1]}")
            options.add_experimental_option("prefs", {
                "download.default_directory": str(browser_download_dir),
                "download.prompt_for_download": False,
                "safebrowsing.enabled": True,
            })
            driver = webdriver.Chrome(
                service=ChromeService(
                    executable,
                    service_args=["--verbose"],
                    log_output=str(browser_download_dir / "chromedriver.log"),
                ),
                options=options,
            )
        elif browser == "firefox":
            executable = os.environ.get("GECKODRIVER") or _binary("geckodriver")
            binary = os.environ.get("FIREFOX_BINARY") or _binary("firefox")
            if not executable:
                raise RuntimeError(
                    "Firefox backend requires geckodriver; place it at "
                    "/usr/local/bin/geckodriver or set GECKODRIVER"
                )
            if not binary:
                raise RuntimeError("Firefox backend requires firefox")
            options = FirefoxOptions()
            options.binary_location = binary
            if headless:
                options.add_argument("-headless")
            options.set_preference("browser.download.folderList", 2)
            options.set_preference("browser.download.dir", str(browser_download_dir))
            options.set_preference(
                "browser.helperApps.neverAsk.saveToDisk",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/json,text/csv",
            )
            options.set_preference("browser.download.useDownloadDir", True)
            driver = webdriver.Firefox(
                service=FirefoxService(executable, log_output=os.devnull), options=options
            )
            driver.set_window_size(*viewport)
        else:
            raise ValueError(f"unsupported browser {browser!r}; expected chromium or firefox")
        setattr(driver, "_face1_download_dir", browser_download_dir)
        yield driver
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        for artifact in browser_download_dir.iterdir():
            if artifact.is_file():
                try:
                    shutil.copy2(artifact, download_dir / artifact.name)
                except OSError:
                    pass
        shutil.rmtree(session_root, ignore_errors=True)


class Face1Page:
    """Semantic Page Object backed by the external selector registry."""

    def __init__(
        self,
        driver: WebDriver,
        base_url: str,
        *,
        selectors: SelectorRegistry = DEFAULT_SELECTORS,
        timeout: float = 15.0,
        download_dir: Path | None = None,
    ) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/") + "/"
        self.selectors = selectors
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        effective_download_dir = getattr(driver, "_face1_download_dir", download_dir)
        self.download_dir = Path(effective_download_dir) if effective_download_dir else None

    def open(self) -> "Face1Page":
        self.driver.get(self.base_url)
        expected_title = self.selectors.value("page", "title")
        ready = self.selectors.value("page", "ready_text")
        self.wait.until(lambda d: expected_title in d.title)
        self.wait.until(lambda d: ready in d.find_element(By.TAG_NAME, "body").text)
        self.wait.until(
            lambda d: len(_displayed(d.find_elements(By.CSS_SELECTOR, "[role=tab]")))
            == int(self.selectors.section("expected")["tab_count"])
        )
        return self

    @property
    def body_text(self) -> str:
        return self.driver.find_element(By.TAG_NAME, "body").text

    def wait_text(self, text: str, *, absent: bool = False) -> None:
        if absent:
            self.wait.until(lambda _d: text not in self.body_text)
        else:
            self.wait.until(lambda _d: text in self.body_text)

    def wait_notification(self, text: str) -> WebElement:
        css = self.selectors.value("page", "notification_css")

        def locate(driver: WebDriver) -> WebElement | bool:
            for item in _displayed(driver.find_elements(By.CSS_SELECTOR, css)):
                try:
                    if text in item.text:
                        return item
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def result_counts(self) -> dict[str, int]:
        """Read the semantic label/value pairs from the real-run result strip."""
        labels = ("Processed", "Pass", "Domain fail", "Broken", "Timeout", "Infra fail")

        def locate(driver: WebDriver) -> dict[str, int] | bool:
            found: dict[str, int] = {}
            for cell in _displayed(driver.find_elements(By.CSS_SELECTOR, ".result-cell")):
                try:
                    text = _normalized(cell.text)
                except StaleElementReferenceException:
                    continue
                for label in labels:
                    if label.casefold() in text.casefold():
                        numbers = re.findall(r"-?\d+", text)
                        if numbers:
                            found[label] = int(numbers[-1])
                        break
            return found if len(found) == len(labels) else False

        return self.wait.until(locate)

    def _scope(self, scope: WebElement | None) -> WebElement | WebDriver:
        return scope if scope is not None else self.driver

    def _by_text(
        self,
        css: str,
        text: str,
        *,
        scope: WebElement | None = None,
        exact: bool = True,
    ) -> WebElement:
        root = self._scope(scope)

        def locate(_driver: WebDriver) -> WebElement | bool:
            try:
                candidates = _displayed(root.find_elements(By.CSS_SELECTOR, css))
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False
            for candidate in candidates:
                try:
                    actual = _normalized(candidate.text)
                except StaleElementReferenceException:
                    continue
                if (exact and _matches(actual, text)) or (not exact and text in actual):
                    return candidate
            return False

        return self.wait.until(locate)

    def tab(self, name: str) -> WebElement:
        return self._by_text("[role=tab]", self.selectors.value("tabs", name))

    def open_tab(self, name: str) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                element = self.tab(name)
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                element.click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)
        self.wait.until(lambda _d: self.tab(name).get_attribute("aria-selected") == "true")

    def button(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        return self._by_text("button", self.selectors.value("buttons", name), scope=scope)

    def click_button(self, name: str, *, scope: WebElement | None = None) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                button = self.button(name, scope=scope)
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
                if not button.is_enabled():
                    return False
                button.click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)

    def field_root(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        label = self.selectors.value("fields", name)
        root = self._scope(scope)

        def locate(_driver: WebDriver) -> WebElement | bool:
            try:
                fields = _displayed(root.find_elements(By.CSS_SELECTOR, ".q-field"))
            except StaleElementReferenceException:
                return False
            for field in fields:
                try:
                    labels = field.find_elements(By.CSS_SELECTOR, ".q-field__label")
                    if any(_normalized(item.text) == label for item in labels):
                        return field
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def field(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        def locate(_driver: WebDriver) -> WebElement | bool:
            try:
                root = self.field_root(name, scope=scope)
                candidates = root.find_elements(By.CSS_SELECTOR, "input,textarea")
                return candidates[0] if candidates else False
            except StaleElementReferenceException:
                return False

        return self.wait.until(locate)

    def field_value(self, name: str, *, scope: WebElement | None = None) -> str:
        def read(_driver: WebDriver) -> tuple[bool, str] | bool:
            try:
                return True, str(self.field(name, scope=scope).get_attribute("value") or "")
            except StaleElementReferenceException:
                return False

        return self.wait.until(read)[1]

    def css_field(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        css = self.selectors.value("field_css", name)
        root = self._scope(scope)
        return self.wait.until(lambda _d: next(iter(_displayed(root.find_elements(By.CSS_SELECTOR, css))), False))

    def set_field(self, name: str, value: object, *, scope: WebElement | None = None) -> None:
        field = self.field(name, scope=scope)
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
        field.click()
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(Keys.BACKSPACE)
        if str(value):
            field.send_keys(str(value))
        field.send_keys(Keys.TAB)
        self.wait.until(lambda _d: self.field_value(name, scope=scope) == str(value))

    def set_css_field(self, name: str, value: object, *, scope: WebElement | None = None) -> None:
        field = self.css_field(name, scope=scope)
        field.click()
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(str(value), Keys.TAB)

    def select_option(self, name: str, option: str, *, scope: WebElement | None = None) -> None:
        root = self.field_root(name, scope=scope)
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", root)
        root.click()
        choice = self._by_text(".q-menu .q-item, [role=option]", option)
        choice.click()
        self.wait.until(lambda _d: option in _normalized(self.field_root(name, scope=scope).text))

    def checkbox(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        return self._by_text(".q-checkbox", self.selectors.value("checkboxes", name), scope=scope)

    def checkbox_value(self, name: str, *, scope: WebElement | None = None) -> bool:
        checkbox = self.checkbox(name, scope=scope)
        return checkbox.get_attribute("aria-checked") == "true" or "q-checkbox--truthy" in checkbox.get_attribute("class")

    def set_checkbox(self, name: str, value: bool, *, scope: WebElement | None = None) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                if self.checkbox_value(name, scope=scope) != bool(value):
                    self.checkbox(name, scope=scope).click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)
        self.wait.until(lambda _d: self.checkbox_value(name, scope=scope) == bool(value))

    def expansion(self, name: str, *, scope: WebElement | None = None) -> WebElement:
        text = self.selectors.value("expansions", name)
        root = self._scope(scope)
        return self._by_text(".q-expansion-item > .q-expansion-item__container > .q-item", text, scope=root)

    def open_expansion(self, name: str, *, scope: WebElement | None = None) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                header = self.expansion(name, scope=scope)
                if header.get_attribute("aria-expanded") == "true":
                    return True
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", header
                )
                header.click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)
        self.wait.until(
            lambda _d: self.expansion(name, scope=scope).get_attribute("aria-expanded") == "true"
        )

    def visible_dialog(self, name: str | None = None) -> WebElement:
        heading = self.selectors.value("dialogs", name) if name else ""
        css = self.selectors.value("page", "visible_dialog_css")

        def locate(driver: WebDriver) -> WebElement | bool:
            dialogs = _displayed(driver.find_elements(By.CSS_SELECTOR, css))
            if not heading:
                return dialogs[-1] if dialogs else False
            for dialog in reversed(dialogs):
                try:
                    if heading in _normalized(dialog.text):
                        return dialog
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def wait_dialog_closed(self, dialog: WebElement) -> None:
        self.wait.until(lambda _d: not dialog.is_displayed())

    def grid(self) -> WebElement:
        css = self.selectors.value("patterns", "grid_css")
        return self.wait.until(
            lambda d: next(iter(_displayed(d.find_elements(By.CSS_SELECTOR, css))), False)
        )

    def _grid_snapshot(self) -> tuple[WebElement, list[WebElement], int, list[WebElement]]:
        def locate(_driver: WebDriver):
            try:
                grid = self.grid()
                rows = _displayed(grid.find_elements(
                    By.CSS_SELECTOR, self.selectors.value("patterns", "grid_row_css")
                ))
                cells = _displayed(grid.find_elements(
                    By.CSS_SELECTOR, self.selectors.value("patterns", "grid_cell_css")
                ))
                if not rows or len(cells) % len(rows):
                    return False
                return grid, rows, len(cells) // len(rows), cells
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        return self.wait.until(locate)

    def grid_dimensions(self) -> tuple[int, int]:
        _grid, rows, columns, _cells = self._grid_snapshot()
        return len(rows), columns

    def grid_cell(self, row: int, column: int) -> WebElement:
        if row < 1 or column < 0:
            raise ValueError("grid row is 1-based and column is 0-based")
        _grid, rows, columns, cells = self._grid_snapshot()
        if row > len(rows) or column >= columns:
            raise IndexError(f"cell r{row} c{column} outside {len(rows)}x{columns} grid")
        return cells[(row - 1) * columns + column]

    def click_cell(self, row: int, column: int, *, double: bool = False) -> WebElement:
        def activate(_driver: WebDriver) -> WebElement | bool:
            try:
                cell = self.grid_cell(row, column)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',inline:'center'});", cell
                )
                if double:
                    ActionChains(self.driver).double_click(cell).perform()
                else:
                    cell.click()
                return cell
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        return self.wait.until(activate)

    def visible_control_cells(self) -> list[WebElement]:
        css = self.selectors.value("patterns", "control_cell_css")
        return _displayed(self.driver.find_elements(By.CSS_SELECTOR, css))

    def control_cell(self, text: str, *, exact: bool = False) -> WebElement:
        def locate(_driver: WebDriver) -> WebElement | bool:
            for cell in self.visible_control_cells():
                try:
                    actual = _normalized(cell.text)
                    if (exact and actual == _normalized(text)) or (not exact and text in actual):
                        return cell
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def double_click_control_text(self, text: str, *, exact: bool = False) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                ActionChains(self.driver).double_click(self.control_cell(text, exact=exact)).perform()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)

    def double_click_control_cell(self, index: int) -> None:
        cells = self.visible_control_cells()
        ActionChains(self.driver).double_click(cells[index]).perform()

    def row_icon_button(self, row: int, icon_name: str) -> WebElement:
        icon = self.selectors.value("icons", icon_name)

        def locate(_driver: WebDriver) -> WebElement | bool:
            try:
                _grid, rows, _columns, _cells = self._grid_snapshot()
                for button in rows[row - 1].find_elements(By.CSS_SELECTOR, "button"):
                    text = button.get_attribute("textContent") or button.text
                    if icon in _normalized(text):
                        return button
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False
            return False

        return self.wait.until(locate)

    def click_row_icon(self, row: int, icon_name: str) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                self.row_icon_button(row, icon_name).click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)

    def template(self, title: str) -> WebElement:
        tile_css = self.selectors.value("patterns", "template_css")
        title_css = self.selectors.value("patterns", "template_title_css")
        def locate(_driver: WebDriver) -> WebElement | bool:
            for tile in _displayed(self.driver.find_elements(By.CSS_SELECTOR, tile_css)):
                try:
                    labels = tile.find_elements(By.CSS_SELECTOR, title_css)
                    if labels and _normalized(labels[0].text) == _normalized(title):
                        return tile
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def drag_template(self, title: str, row: int, column: int) -> None:
        source = self.template(title)
        target = self.grid_cell(row, column)
        self.driver.execute_script(
            """
            const source = arguments[0], target = arguments[1];
            const data = new DataTransfer();
            source.dispatchEvent(new DragEvent('dragstart', {bubbles:true, cancelable:true, dataTransfer:data}));
            target.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:data}));
            target.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:data}));
            source.dispatchEvent(new DragEvent('dragend', {bubbles:true, cancelable:true, dataTransfer:data}));
            """,
            source,
            target,
        )
        time.sleep(0.15)

    def advanced_field(self, flag: str) -> WebElement:
        suffix = self.selectors.format("patterns", "advanced_label_suffix", flag=flag)

        def locate(_driver: WebDriver) -> WebElement | bool:
            for field in _displayed(self.driver.find_elements(By.CSS_SELECTOR, ".q-field")):
                try:
                    labels = field.find_elements(By.CSS_SELECTOR, ".q-field__label")
                    if any(_normalized(label.text).endswith(_normalized(suffix)) for label in labels):
                        controls = field.find_elements(By.CSS_SELECTOR, "input,textarea")
                        return controls[0] if controls else False
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait.until(locate)

    def advanced_checkbox(self, flag: str) -> WebElement:
        suffix = self.selectors.format("patterns", "advanced_label_suffix", flag=flag)
        return self.wait.until(
            lambda d: next(
                (item for item in _displayed(d.find_elements(By.CSS_SELECTOR, ".q-checkbox"))
                 if _normalized(item.text).endswith(_normalized(suffix))),
                False,
            )
        )

    def advanced_checkbox_value(self, flag: str) -> bool:
        control = self.advanced_checkbox(flag)
        return (
            control.get_attribute("aria-checked") == "true"
            or "q-checkbox--truthy" in control.get_attribute("class")
        )

    def set_advanced_checkbox(self, flag: str, value: bool) -> None:
        def activate(_driver: WebDriver) -> bool:
            try:
                if self.advanced_checkbox_value(flag) != bool(value):
                    self.advanced_checkbox(flag).click()
                return True
            except (ElementClickInterceptedException, StaleElementReferenceException):
                return False

        self.wait.until(activate)
        self.wait.until(lambda _d: self.advanced_checkbox_value(flag) == bool(value))

    def advanced_field_value(self, flag: str) -> str:
        def read(_driver: WebDriver) -> tuple[bool, str] | bool:
            try:
                return True, str(self.advanced_field(flag).get_attribute("value") or "")
            except StaleElementReferenceException:
                return False

        return self.wait.until(read)[1]

    def set_advanced_field(self, flag: str, value: object) -> None:
        expected = str(value)

        def edit(_driver: WebDriver) -> bool:
            try:
                field = self.advanced_field(flag)
                field.click()
                field.send_keys(Keys.CONTROL, "a")
                field.send_keys(Keys.BACKSPACE)
                if expected:
                    field.send_keys(expected)
                field.send_keys(Keys.TAB)
                return True
            except StaleElementReferenceException:
                return False

        self.wait.until(edit)
        self.wait.until(lambda _d: self.advanced_field_value(flag) == expected)

    def command_text(self) -> str:
        return self.field_value("command_preview")

    def upload(self, path: Path) -> None:
        dialog = self.visible_dialog("upload")
        css = self.selectors.value("field_css", "upload_file")
        upload = self.wait.until(
            lambda _d: next(iter(dialog.find_elements(By.CSS_SELECTOR, css)), False)
        )
        upload.send_keys(str(Path(path).resolve()))

    def wait_download(self, suffix: str, *, since: float | None = None) -> Path:
        if self.download_dir is None:
            raise RuntimeError("Page Object has no download directory")
        started = since or 0.0

        def locate(_driver: WebDriver) -> Path | bool:
            matches = [
                path for path in self.download_dir.glob(f"*{suffix}")
                if path.is_file() and path.stat().st_mtime >= started
                and not path.name.endswith((".crdownload", ".part"))
            ]
            return max(matches, key=lambda path: path.stat().st_mtime) if matches else False

        return self.wait.until(locate)

    def assert_no_browser_errors(self) -> None:
        try:
            logs = self.driver.get_log("browser")
        except Exception:
            return
        severe = [item for item in logs if str(item.get("level", "")).upper() == "SEVERE"]
        if severe:
            raise AssertionError(f"browser console has severe entries: {severe[-5:]}")


def wait_until_reachable(url: str, timeout: float = 20.0) -> None:
    """Small HTTP readiness probe shared by the multi-instance dispatcher.

    The composed root page is intentionally large and can take longer than a
    one-second socket timeout to render. Probe the lightweight favicon route so
    retries cannot queue expensive page builds and starve the app event loop.
    """
    from urllib.error import URLError
    from urllib.request import urlopen

    probe_url = url.rstrip("/") + "/favicon.ico"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(probe_url, timeout=2.0) as response:  # noqa: S310 - explicit local test URL
                if response.status == 200:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise TimeoutException(f"Face 1 server did not become ready at {url}: {last_error}")
