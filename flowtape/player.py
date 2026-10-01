"""Scenario execution. Browser mutations occur only in 実行 mode."""

from __future__ import annotations

import csv
import fnmatch
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep

from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from .browser import Resolver, seconds
from .errors import (ActionCompatibilityError, CredentialOutputForbidden,
                     CollectionContextUnavailable, CollectionMemberAmbiguous,
                     CollectionMemberNotFound, FlowTapeError, LoopLimitExceeded,
                     OutputSchemaMismatch, OutputWriteError, TargetNotFound, WaitTimeout)
from .schema import REFERENCE
from .windows import WindowContext
from .runlog import RunLog


@dataclass(frozen=True)
class Value:
    data: object
    secret: bool = False


@dataclass(frozen=True)
class MemberRef:
    collection: str
    page: str
    snapshot: dict


def as_text(value: object) -> str:
    if value is None:
        raise ActionCompatibilityError("required text value is null")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class OutputManager:
    def __init__(self, scenario: dict, root: str | Path, *, write: bool):
        self.definitions = scenario.get("outputs", {})
        self.root = Path(root)
        safe_name = re.sub(r"[^\w.-]+", "_", scenario["name"]).strip("._") or "scenario"
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.run_dir = self.root / safe_name / run_id
        self.write = write
        self.paths = {}
        for name, definition in self.definitions.items():
            policy = definition.get("existing", "new")
            base = self.run_dir if policy == "new" else self.root
            path = (base / definition["file"]).resolve()
            if not path.is_relative_to(base.resolve()):
                raise OutputSchemaMismatch(f"output {name}: path escapes output root")
            self.paths[name] = path
            if write and policy == "overwrite":
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("w", encoding="utf-8", newline="") as handle:
                        if definition["format"] == "csv":
                            csv.writer(handle).writerow(definition["columns"])
                except OSError:
                    raise OutputWriteError(f"output {name}: initialization failed") from None

    def append(self, name: str, values: dict[str, Value] | Value):
        definition = self.definitions[name]
        payload = list(values.values()) if isinstance(values, dict) else [values]
        if any(v.secret for v in payload):
            raise CredentialOutputForbidden(f"output {name}: secret-derived value forbidden")
        if any(v.data is not None and not isinstance(v.data, (str, int, float, bool)) for v in payload):
            raise OutputSchemaMismatch(f"output {name}: scalar value required")
        fmt = definition["format"]
        if fmt == "csv" and set(values) != set(definition["columns"]):
            raise OutputSchemaMismatch(f"output {name}: CSV columns differ")
        if not self.write:
            return
        path = self.paths[name]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise OutputWriteError(f"output {name}: output directory unavailable") from None
        if fmt == "csv" and path.exists() and path.stat().st_size:
            with path.open(encoding="utf-8", newline="") as handle:
                if next(csv.reader(handle), None) != definition["columns"]:
                    raise OutputSchemaMismatch(f"output {name}: CSV header differs")
        try:
            with path.open("a", encoding="utf-8", newline="") as handle:
                if fmt == "csv":
                    writer = csv.writer(handle)
                    if path.stat().st_size == 0:
                        writer.writerow(definition["columns"])
                    writer.writerow(["" if values[k].data is None else as_text(values[k].data) for k in definition["columns"]])
                elif fmt == "jsonl":
                    handle.write(json.dumps({k: v.data for k, v in values.items()}, ensure_ascii=False) + "\n")
                else:
                    handle.write(("" if values.data is None else as_text(values.data)) + "\n")
                handle.flush()
        except OSError:
            raise OutputWriteError(f"output {name}: write failed") from None


class Player:
    def __init__(self, driver, scenario: dict, registry: dict, config: dict, credentials: dict | None = None, before_action=None, after_action=None):
        from .identity import ensure_ids
        ensure_ids(scenario)
        self.driver = driver
        self.scenario = scenario
        self.config = config
        self.credentials = (credentials or {}).get("credentials", {})
        self.resolver = Resolver(driver, registry)
        self.mode = scenario.get("mode", "実行")
        self.variables = {k: Value(v) for k, v in scenario.get("variables", {}).items()}
        self.runtime: dict[str, Value] = {}
        self.loop_vars: dict[str, Value] = {}
        self.outputs = OutputManager(scenario, config["paths"]["outputs"], write=self.mode == "実行")
        self.log=RunLog(config,self.outputs,self.credentials)
        self.log.write('INFO','run_start',mode=self.mode)
        self.current_node = None
        self.stop_requested = False
        self.windows = WindowContext(driver)
        self.before_action = before_action
        self.after_action = after_action
        self.secret_targets: set[str] = set()
        self.download_baseline = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in Path(config["paths"]["downloads"]).glob("*") if p.is_file()}

    def expand(self, raw: object) -> Value:
        return self._expand(raw, set())

    def _expand(self, raw: object, stack: set[str]) -> Value:
        if not isinstance(raw, str):
            return Value(raw)
        refs = REFERENCE.findall(raw)
        if not refs:
            return Value(raw)
        def get(name: str) -> Value:
            if name.startswith("credential."):
                _, group, key = name.split(".")
                try:
                    return Value(self.credentials[group][key], True)
                except KeyError:
                    raise FlowTapeError("credential reference unavailable") from None
            if name in self.loop_vars:
                return self.loop_vars[name]
            if name in self.runtime:
                return self.runtime[name]
            if name in self.variables:
                if name in stack:
                    raise FlowTapeError(f"variable reference cycle at {name}")
                value = self.variables[name]
                if isinstance(value.data, str) and "${" in value.data:
                    return self._expand(value.data, stack | {name})
                return value
            raise FlowTapeError(f"undefined variable {name}")
        if raw == "${" + refs[0] + "}" and len(refs) == 1:
            return get(refs[0])
        secret = False
        def replace(match):
            nonlocal secret
            val = get(match.group(1))
            secret |= val.secret
            return "" if val.data is None else as_text(val.data)
        return Value(REFERENCE.sub(replace, raw), secret)

    def _target(self, name, action="", within=None, wait=True):
        target=self.resolver.target(name, action, within=within, timeout=seconds(self.config["timeouts"]["default"]) if wait else 0)
        self.log.write('DEBUG','target_resolution',target=name,candidates=self.resolver.diagnostics)
        if self.mode=='デバッグ':
            from .recorder import OBSERVER_JS
            self.resolver.js(OBSERVER_JS+"\nwindow.__flowtape.highlight([arguments[0]]);",target)
        return target

    def _within(self, node):
        if "within" not in node:
            return None
        ref = node["within"]
        if not isinstance(ref, str) or not ref.startswith("${") or not ref.endswith("}"):
            raise FlowTapeError("within requires a loop context reference")
        name = ref[2:-1]
        if name not in self.loop_vars:
            raise FlowTapeError(f"within context {name} unavailable")
        ref = self.loop_vars[name].data
        if not isinstance(ref, MemberRef):
            raise CollectionContextUnavailable(f"within context {name} is not a collection member")
        return lambda: self._member(ref)

    @staticmethod
    def _member_signature(snapshot):
        attrs = snapshot["attributes"]
        def stable_value(value):
            return value and not re.search(r"(?:[a-f0-9]{8}-[a-f0-9-]{20,}|\d{6,})", value, re.I)
        stable = tuple((k, attrs.get(k)) for k in ("data-testid", "data-test", "id", "href", "name") if stable_value(attrs.get(k)))
        return stable or (snapshot["role"], snapshot["name"], snapshot["text"])

    def _member(self, ref: MemberRef):
        try:
            if self.resolver.identify() != ref.page:
                raise CollectionContextUnavailable(f"collection {ref.collection} page unavailable")
            current = self.resolver.collection(ref.collection)
        except TargetNotFound:
            raise CollectionContextUnavailable(f"collection {ref.collection} unavailable") from None
        matches = [el for el in current if self._member_signature(self.resolver.js("return FT.snapshot(arguments[0]);", el)) == self._member_signature(ref.snapshot)]
        if not matches:
            raise CollectionMemberNotFound(f"collection {ref.collection} member disappeared")
        if len(matches) > 1:
            raise CollectionMemberAmbiguous(f"collection {ref.collection} member ambiguous")
        return matches[0]

    def condition(self, cond: dict) -> bool:
        op, val = next(iter(cond.items()))
        if op == "all":
            return all(self.condition(x) for x in val)
        if op == "any":
            return any(self.condition(x) for x in val)
        if op == "not":
            return not self.condition(val)
        if op == "page":
            return self.resolver.identify() == val
        if op in {"exists", "not_exists", "visible", "hidden", "enabled", "disabled"}:
            try:
                el = self._target(val, wait=False)
            except TargetNotFound:
                return op == "not_exists"
            if op == "exists": return True
            if op == "not_exists": return False
            if op in {'visible','hidden'}:
                visible=self.resolver.js('return FT.visible(arguments[0]);',el)
                return visible if op=='visible' else not visible
            enabled=self.resolver.js('return FT.enabled(arguments[0]);',el)
            return enabled if op=='enabled' else not enabled
        if op in {"text_equals", "value_equals"}:
            el = self._target(val["target"], wait=False)
            actual = self.resolver.js("return arguments[0].value;", el) if op == "value_equals" else self.resolver.js("return FT.norm(arguments[0].innerText || arguments[0].textContent);", el)
            return actual == self.expand(val["value"]).data
        raise FlowTapeError(f"unsupported condition {op}")

    def _wait(self, condition: dict, timeout: str):
        deadline = monotonic() + seconds(timeout)
        last = None
        while True:
            deadline += self.checkpoint()
            try:
                ready = self._download_complete(condition) if "download_complete" in condition else self.condition(condition)
                if ready:
                    return
            except FlowTapeError as exc:
                last = exc
            if monotonic() >= deadline:
                raise WaitTimeout(f"wait expired; final reason: {type(last).__name__ if last else 'condition false'}")
            sleep(.1)

    def _download_complete(self, condition: dict) -> bool:
        pattern = condition["download_complete"]
        directory = Path(self.config["paths"]["downloads"])
        for path in directory.glob("*"):
            if not path.is_file() or not fnmatch.fnmatch(path.name, pattern) or path.suffix in {".crdownload", ".tmp", ".part"}:
                continue
            stat = path.stat()
            if self.download_baseline.get(path) == (stat.st_mtime_ns, stat.st_size):
                continue
            if (directory / (path.name + ".crdownload")).exists():
                continue
            before = stat.st_size
            sleep(.1)
            if path.exists() and path.stat().st_size == before:
                return True
        return False

    def checkpoint(self):
        if self.stop_requested:
            from .errors import PlaybackStopped
            raise PlaybackStopped("playback stopped")
        return 0

    def run(self):
        from .playback import PlaybackController
        controller = PlaybackController(self)
        controller.execute()
        if controller.error:
            raise controller.error
        return controller

    def perform(self, node):
        self.checkpoint()
        self.windows.restore()
        source = self.windows.active
        if self.before_action and self.mode == "実行" and not self.before_action(node):
            return False
        self._action(node)
        self.windows.observe(cause=source)
        self.log.write('INFO','action_completed',step=node.get('_meta',{}).get('id'),action=node['action'],target=node.get('target'))
        if self.after_action:
            self.after_action(node)
        if self.mode == "実行":
            deadline = monotonic() + seconds(self.config["playback"]["observation_delay"])
            while monotonic() < deadline:
                deadline += self.checkpoint()
                sleep(min(.05, max(0, deadline - monotonic())))
        return True

    def _select(self, el, node, run):
        from selenium.webdriver.support.ui import Select

        control = Select(el)
        exact_set = 'values' in node
        if exact_set and not control.is_multiple:
            raise ActionCompatibilityError(f"select target {node['target']}: values requires a multiple select")
        raw_values = node['values'] if exact_set else [node['value']]
        expanded_texts = [as_text(self.expand(value).data) for value in raw_values]
        texts = self.resolver.js('return arguments[0].map(value=>FT.norm(value));', expanded_texts)
        if len(set(texts)) != len(texts):
            raise ActionCompatibilityError(f"select target {node['target']}: duplicate option text")
        options = control.options
        labels = self.resolver.js('return arguments[0].map(o=>FT.norm(o.textContent));', options)
        desired = []
        for text in texts:
            matches = [option for option, label in zip(options, labels) if label == text]
            if len(matches) != 1:
                raise ActionCompatibilityError(f"select target {node['target']}: option count {len(matches)}")
            option = matches[0]
            if not option.is_enabled():
                raise ActionCompatibilityError(f"select target {node['target']}: option disabled")
            desired.append(option)
        if not run:
            return
        desired_ids = {option.id for option in desired}
        if exact_set:
            for option in options:
                if option.is_selected() and option.id not in desired_ids:
                    control.deselect_by_index(int(option.get_attribute('index')))
        for option in desired:
            if not option.is_selected():
                option.click()
        selected_ids = {option.id for option in control.all_selected_options}
        if ((exact_set or not control.is_multiple) and selected_ids != desired_ids) or not desired_ids <= selected_ids:
            raise ActionCompatibilityError(f"select target {node['target']}: selection verification failed")

    def _action(self, n):
        action = n["action"]
        run = self.mode == "実行"
        if action == "open":
            url = as_text(self.expand(n["url"]).data)
            if run: self.driver.get(url)
        elif action in {"back", "forward", "refresh"}:
            if run: {"back": self.driver.back, "forward": self.driver.forward, "refresh": self.driver.refresh}[action]()
        elif action in {"click", "double_click", "input", "select", "read", "upload", "hover"}:
            el = self._target(n["target"], action, within=self._within(n))
            if action == "click" and run: el.click()
            elif action == "double_click" and run: ActionChains(self.driver).double_click(el).perform()
            elif action == "input":
                expanded = self.expand(n["value"])
                value = as_text(expanded.data)
                if run:
                    el.clear()
                    el.send_keys(value)
                    if expanded.secret:
                        self.secret_targets.add(n["target"])
                    actual = self.resolver.js('return arguments[0].isContentEditable ? arguments[0].innerText : arguments[0].value;', el)
                    if actual != value:
                        raise ActionCompatibilityError('input value verification failed')
            elif action == "select":
                self._select(el, n, run)
            elif action == "read":
                if n['into'] in self.variables or n['into'] in self.loop_vars:
                    raise FlowTapeError(f"runtime variable {n['into']} collides with scenario or loop variable")
                src = n["source"]
                data = (self.resolver.js("return FT.norm(arguments[0].innerText || arguments[0].textContent);", el) if src == "text" else
                        self.resolver.js("return arguments[0].value;", el) if src == "value" else el.get_dom_attribute(src["attribute"]))
                password = self.resolver.js("return arguments[0].matches('input[type=password]');", el)
                self.runtime[n["into"]] = Value(data, password or n["target"] in self.secret_targets)
            elif action == "upload":
                path = Path(as_text(self.expand(n["path"]).data))
                if run: el.send_keys(str(path))
            elif action == "hover" and run: ActionChains(self.driver).move_to_element(el).perform()
        elif action == "append":
            data = {k: self.expand(v) for k, v in n["values"].items()} if "values" in n else self.expand(n["value"])
            self.outputs.append(n["output"], data)
        elif action == "check":
            if not self.condition(n["condition"]): raise FlowTapeError("check condition false")
        elif action == "wait":
            self._wait(n["until"], n.get("timeout", self.config["timeouts"]["default"]))
        elif action == "key":
            keys = [n["key"]] if "key" in n else n["keys"]
            keys = [as_text(self.expand(token).data) for token in keys]
            tokens = [getattr(Keys, x.upper(), x) for x in keys]
            el = self._target(n["target"], 'key', within=self._within(n)) if "target" in n else self.driver.switch_to.active_element
            if run:
                el.send_keys(*tokens, Keys.NULL)
        elif action == "drag_drop":
            src = self._target(n["from"])
            dst = self._target(n["to"])
            if run: ActionChains(self.driver).drag_and_drop(src, dst).perform()
        elif action in {"alert_accept", "alert_dismiss", "alert_input"}:
            try:
                alert = self.driver.switch_to.alert
                _ = alert.text
            except NoAlertPresentException:
                raise ActionCompatibilityError("no JavaScript dialog") from None
            if run:
                if action == "alert_accept": alert.accept()
                elif action == "alert_dismiss": alert.dismiss()
                else: alert.send_keys(as_text(self.expand(n["value"]).data))
        elif action == "switch_window":
            target = self.windows.destination(n["to"])
            if run: self.windows.switch(target)
        elif action == "close_window":
            if run: self.windows.close()
            else: self.windows.destination("parent")
        else:
            raise FlowTapeError(f"unsupported action {action}")
