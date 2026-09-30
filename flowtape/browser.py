"""Selenium Edge adapter and conservative page/target resolution."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import os
from time import monotonic, sleep

from selenium.webdriver.edge.webdriver import WebDriver as EdgeDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.common.exceptions import WebDriverException

from .errors import AmbiguousPage, AmbiguousTarget, BrowserStartupError, CollectionContextUnavailable, DriverConfigurationError, FlowTapeError, TargetContextError, TargetNotFound, UnknownPage

DOM_JS = files("flowtape").joinpath("dom.js").read_text(encoding="utf-8")


def seconds(value: str) -> float:
    if value.endswith("ms"):
        return float(value[:-2]) / 1000
    return float(value[:-1]) * {"s": 1, "m": 60, "h": 3600}[value[-1]]


def open_edge(config: dict, *, headless: bool = False):
    driver_path = Path(config["driver"]["path"])
    if not driver_path.is_file():
        raise DriverConfigurationError(f"configured Edge WebDriver does not exist: {driver_path}")
    if not os.access(driver_path,os.X_OK):
        raise DriverConfigurationError('configured Edge WebDriver is not executable')
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-default-apps")
    options.add_argument("--ignore-certificate-errors")
    options.set_capability("acceptInsecureCerts", True)
    if config["browser"]["executable"]:
        options.binary_location = config["browser"]["executable"]
    if config["browser"]["profile_path"]:
        options.add_argument("--user-data-dir=" + config["browser"]["profile_path"])
    download_dir = Path(config["paths"]["downloads"])
    download_dir.mkdir(parents=True, exist_ok=True)
    options.add_experimental_option("prefs", {"download.default_directory": str(download_dir.resolve()), "download.prompt_for_download": False})
    try: driver = EdgeDriver(service=Service(str(driver_path)), options=options)
    except WebDriverException as exc:
        raise BrowserStartupError(f'Edge/WebDriver startup failed ({type(exc).__name__}); verify the configured path and browser/driver compatibility') from None
    driver.set_page_load_timeout(seconds(config["timeouts"]["page_load"]))
    return driver


class Resolver:
    def __init__(self, driver, registry: dict):
        self.driver = driver
        self.pages = registry["pages"]
        self.diagnostics: list[dict] = []
        self.checkpoint = lambda: 0

    def js(self, code: str, *args):
        return self.driver.execute_script(DOM_JS + "\n" + code, *args)

    def selector(self, scope, selector: dict):
        return self.js("return FT.semantic(arguments[0] || document, arguments[1]);", scope, selector)

    def identify(self) -> str:
        self.driver.switch_to.default_content()
        matches = [name for name, page in self.pages.items() if self._page_condition(page["identify"])]
        if not matches:
            raise UnknownPage("current page matches no PageDefinition")
        if len(matches) > 1:
            raise AmbiguousPage(f"current page matches multiple PageDefinitions: {', '.join(matches)}")
        return matches[0]

    def _page_condition(self, condition: dict) -> bool:
        op, val = next(iter(condition.items()))
        if op == "url":
            mode, expected = next(iter(val.items()))
            actual = self.driver.current_url
            return actual == expected if mode == "equals" else (expected in actual if mode == "contains" else actual.startswith(expected))
        if op == "exists":
            return bool(self.selector(None, val))
        if op == "all":
            return all(self._page_condition(x) for x in val)
        if op == "any":
            return any(self._page_condition(x) for x in val)
        return not self._page_condition(val)

    def _context(self, definition: dict):
        self.driver.switch_to.default_content()
        scope = None
        for step in definition.get("context", []):
            if "frame" in step:
                frame = step["frame"]
                key, value = next(iter(frame.items()))
                found = self.js("return [...(arguments[0] || document).querySelectorAll(arguments[2]==='css'?arguments[1]:'iframe,frame')].filter(e=>arguments[2]==='css'||e.getAttribute(arguments[2])===arguments[1]);", scope, value, key)
                if len(found) != 1:
                    raise TargetContextError(f"frame {key}={value}: expected one, found {len(found)}")
                self.driver.switch_to.frame(found[0])
                scope = None
            else:
                css = step["shadow"]["css"]
                found = self.js("return [...(arguments[0] || document).querySelectorAll(arguments[1])];", scope, css)
                if len(found) != 1:
                    raise TargetContextError(f"shadow host {css}: expected one, found {len(found)}")
                scope = self.js("return arguments[0].shadowRoot;", found[0])
                if scope is None:
                    raise TargetContextError(f"shadow host {css} has no open root")
        return scope

    def _candidate(self, scope, loc: dict, expect: dict, action: str, kind: str = ''):
        result = self.js("const r=FT.locate(arguments[0] || document,arguments[1]); if(r.ambiguous)return {ambiguous:true}; return {elements:r.filter(e=>FT.accepts(e,arguments[2],arguments[3],arguments[4]))};", scope, loc, expect, action, kind)
        if result.get("ambiguous"):
            return None
        matches = result["elements"]
        if "index" in loc:
            return [matches[loc["index"]]] if loc["index"] < len(matches) else []
        return matches

    def _resolve(self, definition: dict, action: str = "", within=None, multiple: bool = False):
        scope = self._context(definition)
        if within is not None:
            try:
                compatible=self.js('return arguments[0].ownerDocument===document;',within)
            except WebDriverException:
                raise CollectionContextUnavailable('within member is unavailable in the target frame context') from None
            if not compatible: raise CollectionContextUnavailable('within member belongs to a different document')
            scope = within
        self.diagnostics = []
        ambiguous = False
        for i, loc in enumerate(definition["locate"]):
            try:
                matches = self._candidate(scope, loc, definition.get("expect", {}), action, definition.get('kind',''))
            except Exception as exc:
                self.diagnostics.append({"candidate": i, 'locator':loc, "by": loc["by"], "error": type(exc).__name__})
                continue
            count = None if matches is None else len(matches)
            self.diagnostics.append({"candidate": i, 'locator':loc, "by": loc["by"], "count": count,
                                     'reason':'anchor ambiguous' if matches is None else 'unique' if count==1 else 'no acceptable matches' if count==0 else 'multiple matches'})
            if matches is None or (not multiple and count > 1):
                ambiguous = True
                continue
            if multiple or count == 1:
                return matches if multiple else matches[0]
        if ambiguous:
            raise AmbiguousTarget(f"target ambiguous; candidates={self.diagnostics}")
        if multiple:
            return []
        raise TargetNotFound(f"target not found; candidates={self.diagnostics}")

    def target(self, name: str, action: str = "", within=None, timeout: float = 0):
        deadline = monotonic() + timeout
        while True:
            deadline += self.checkpoint()
            try:
                current_within = within() if callable(within) else within
                page = self.identify()
                definition = self.pages[page].get("elements", {}).get(name)
                if definition is None:
                    raise TargetNotFound(f"page {page}: undefined target {name}")
                return self._resolve(definition, action, current_within)
            except (TargetNotFound, AmbiguousTarget, TargetContextError):
                if monotonic() >= deadline:
                    raise
                sleep(min(.1, max(0, deadline - monotonic())))

    def collection(self, name: str):
        page = self.identify()
        definition = self.pages[page].get("collections", {}).get(name)
        if definition is None:
            raise TargetNotFound(f"page {page}: undefined collection {name}")
        return self._resolve(definition, multiple=True)
