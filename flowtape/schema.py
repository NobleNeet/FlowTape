"""Strict v1 persisted document validation. Returns normalized plain domain data."""

from __future__ import annotations

import re
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any

import yaml

from .errors import ScenarioValidationError as Invalid

MISSING = object()
DURATION = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?(?:ms|s|m|h)$")
REFERENCE = re.compile(r"\$\{([^}]+)\}")


class StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try: hash(key)
            except TypeError:
                raise yaml.constructor.ConstructorError(None,None,'unhashable YAML mapping key',key_node.start_mark) from None
            if key in result:
                raise yaml.constructor.ConstructorError(None, None, "duplicate YAML mapping key", key_node.start_mark)
            result[key] = self.construct_object(value_node, deep=deep)
        return result
KINDS = {"button", "input", "textarea", "select", "checkbox", "radio", "link", "menu", "tab", "file", "element"}
ACTIONS = {"open", "back", "forward", "refresh", "click", "double_click", "input", "select", "read", "append", "upload", "key", "hover", "drag_drop", "alert_accept", "alert_dismiss", "alert_input", "wait", "check", "switch_window", "close_window"}
CONDITIONS = {"exists", "not_exists", "visible", "hidden", "enabled", "disabled", "text_equals", "value_equals", "page", "all", "any", "not"}
LOCATORS = {"testid", "id", "name", "role", "label", "text", "placeholder", "attribute", "relative", "css", "xpath"}


def fail(where: str, reason: str) -> None:
    raise Invalid(f"{where}: {reason}")


def mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        fail(where, "mapping required")
    if any(not isinstance(key,str) for key in value):
        fail(where, 'mapping keys must be strings')
    return value


def fields(value: dict, allowed: set[str], required: set[str], where: str) -> None:
    extra = set(value) - allowed
    missing = required - set(value)
    if extra or missing:
        fail(where, f"unknown fields {sorted(extra)}; missing fields {sorted(missing)}")


def omit_null(obj: dict, optional: set[str]) -> None:
    for key in optional:
        if obj.get(key, MISSING) is None:
            obj.pop(key, None)


def string(value: Any, where: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        fail(where, "non-empty string required" if nonempty else "string required")
    return value


def scalar(value: Any, where: str) -> Any:
    if value is not None and not isinstance(value, (str, int, float, bool)):
        fail(where, "scalar required")
    return value


def boolean(value: Any, where: str) -> None:
    if type(value) is not bool:
        fail(where, "boolean required")


def positive(value: Any, where: str) -> None:
    if type(value) is not int or value <= 0:
        fail(where, "positive integer required")


def duration(value: Any, where: str) -> None:
    if not isinstance(value, str) or not DURATION.fullmatch(value):
        fail(where, "duration requires ms/s/m/h unit")


def variable(value: Any, where: str) -> None:
    string(value, where)
    if not value.isidentifier() or value == "credential":
        fail(where, "invalid or reserved variable name")


def reference_syntax(value: Any, where: str) -> None:
    if not isinstance(value, str):
        return
    if value.count("${") != len(REFERENCE.findall(value)):
        fail(where, "malformed variable reference")
    for ref in REFERENCE.findall(value):
        if ref.startswith("credential."):
            if len(ref.split(".")) != 3 or not all(ref.split(".")[1:]):
                fail(where, "invalid credential reference")
        else:
            variable(ref, where)


def load_yaml(path: str | Path) -> Any:
    try:
        return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=StrictLoader)
    except yaml.YAMLError as exc:
        line = exc.problem_mark.line + 1 if getattr(exc, "problem_mark", None) else "unknown"
        raise Invalid(f"{path}: YAML parse failed at line {line}") from None
    except OSError as exc:
        raise Invalid(f"{path}: YAML read failed: {type(exc).__name__}") from None


def save_yaml(path: str | Path, data: dict) -> None:
    if 'steps' in data:
        from copy import deepcopy
        from .editor import walk_nodes
        data = deepcopy(data)
        for node in walk_nodes(data['steps']):
            if node.get('enabled') is True: node.pop('enabled')
    Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, indent=2), encoding="utf-8")


def condition(data: Any, where: str, download: bool = False) -> None:
    obj = mapping(data, where)
    keys = set(obj)
    if len(keys) != 1 or not keys <= (CONDITIONS | ({"download_complete"} if download else set())):
        fail(where, "exactly one supported condition operator required")
    op, val = next(iter(obj.items()))
    if op in {"exists", "not_exists", "visible", "hidden", "enabled", "disabled", "page", "download_complete"}:
        string(val, where + "." + op)
    elif op in {"text_equals", "value_equals"}:
        val = mapping(val, where)
        fields(val, {"target", "value"}, {"target", "value"}, where)
        string(val["target"], where + ".target")
        scalar(val["value"], where + ".value")
        reference_syntax(val["value"], where)
    elif op in {"all", "any"}:
        if not isinstance(val, list) or not val:
            fail(where, "non-empty condition list required")
        for i, child in enumerate(val):
            condition(child, f"{where}.{op}[{i}]")
    else:
        condition(val, where + ".not")


def selector(data: Any, where: str) -> None:
    obj = mapping(data, where)
    fields(obj, {"role", "name", "text", "label", "testid", "id"}, set(), where)
    if not obj:
        fail(where, "selector cannot be empty")
    for key, value in obj.items():
        string(value, where + "." + key)


def locator(data: Any, where: str) -> None:
    obj = mapping(data, where)
    omit_null(obj, {"fragile", "index", "exact", "name"})
    by = obj.get("by")
    if not isinstance(by, str) or by not in LOCATORS:
        fail(where, "unsupported locator family")
    spec = {
        "role": ({"role", "name"}, {"role"}),
        "text": ({"value", "exact"}, {"value"}),
        "attribute": ({"name", "value"}, {"name", "value"}),
        "relative": ({"anchor", "relation", "target"}, {"anchor", "relation", "target"}),
    }
    allowed, required = spec.get(by, ({"value"}, {"value"}))
    fields(obj, {"by", "fragile", "index"} | allowed, {"by"} | required, where)
    for key in {"value", "role", "name"} & set(obj):
        string(obj[key], where + "." + key)
    for key in {"fragile", "exact"} & set(obj):
        boolean(obj[key], where + "." + key)
    if "index" in obj:
        if type(obj["index"]) is not int or obj["index"] < 0 or obj.get("fragile") is not True:
            fail(where, "index requires non-negative integer and fragile: true")
    if by == "relative":
        if not isinstance(obj['relation'],str) or obj["relation"] not in {"descendant", "row", "dialog", "form"}:
            fail(where, "unsupported v1 relative relation")
        selector(obj["anchor"], where + ".anchor")
        selector(obj["target"], where + ".target")


def expectation(data: Any, where: str) -> None:
    obj = mapping(data, where)
    omit_null(obj, {"tag", "role", "input_type", "visible", "enabled", "editable", "attributes"})
    fields(obj, {"tag", "role", "input_type", "visible", "enabled", "editable", "attributes"}, set(), where)
    for key in {"tag", "role", "input_type"} & set(obj):
        string(obj[key], where + "." + key)
    for key in {"visible", "enabled", "editable"} & set(obj):
        boolean(obj[key], where + "." + key)
    if "attributes" in obj:
        for key, val in mapping(obj["attributes"], where + ".attributes").items():
            string(key, where)
            string(val, where, False)


def target_definition(data: Any, where: str, collection: bool = False) -> None:
    obj = mapping(data, where)
    omit_null(obj, {"context", "expect", "fingerprint"})
    allowed = {"context", "locate", "expect", "fingerprint"} | (set() if collection else {"kind"})
    fields(obj, allowed, {"locate"} | (set() if collection else {"kind"}), where)
    if not collection and (not isinstance(obj['kind'],str) or obj["kind"] not in KINDS):
        fail(where + ".kind", "unsupported target kind")
    locations = obj["locate"]
    if not isinstance(locations, list) or not locations:
        fail(where + ".locate", "non-empty locator list required")
    for i, item in enumerate(locations):
        locator(item, f"{where}.locate[{i}]")
    if "context" in obj:
        if not isinstance(obj["context"], list):
            fail(where + ".context", "list required")
        for i, item in enumerate(obj["context"]):
            item = mapping(item, f"{where}.context[{i}]")
            if set(item) == {"frame"}:
                frame = mapping(item["frame"], where)
                if len(frame) != 1 or not set(frame) <= {"id", "name", "css"}:
                    fail(where, "frame requires exactly one id/name/css")
                string(next(iter(frame.values())), where)
            elif set(item) == {"shadow"}:
                shadow = mapping(item["shadow"], where)
                fields(shadow, {"css"}, {"css"}, where)
                string(shadow["css"], where)
            else:
                fail(where, "context step requires exactly one frame/shadow")
    if "expect" in obj:
        expectation(obj["expect"], where + ".expect")
    if "fingerprint" in obj:
        fp = mapping(obj["fingerprint"], where)
        fields(fp, {"text", "nearby_text", "attributes"}, set(), where)
        if "text" in fp:
            string(fp["text"], where, False)
        if "nearby_text" in fp:
            if not isinstance(fp["nearby_text"], list):
                fail(where, "nearby_text list required")
            for v in fp["nearby_text"]:
                string(v, where, False)
        if "attributes" in fp:
            for k, v in mapping(fp["attributes"], where).items():
                string(k, where)
                string(v, where, False)


def page_condition(data: Any, where: str) -> None:
    obj = mapping(data, where)
    if len(obj) != 1 or not set(obj) <= {"url", "exists", "all", "any", "not"}:
        fail(where, "one page condition required")
    op, val = next(iter(obj.items()))
    if op == "url":
        val = mapping(val, where)
        if len(val) != 1 or not set(val) <= {"equals", "contains", "starts_with"}:
            fail(where, "one URL operator required")
        string(next(iter(val.values())), where)
    elif op == "exists":
        selector(val, where)
    elif op in {"all", "any"}:
        if not isinstance(val, list) or not val:
            fail(where, "non-empty list required")
        for i, child in enumerate(val):
            page_condition(child, f"{where}[{i}]")
    else:
        page_condition(val, where + ".not")


def elements(data: Any) -> dict:
    obj = mapping(data, "elements")
    fields(obj, {"version", "pages"}, {"version", "pages"}, "elements")
    if type(obj["version"]) is not int or obj["version"] != 1:
        fail("elements.version", "version 1 required")
    for page_id, page in mapping(obj["pages"], "elements.pages").items():
        string(page_id, "page id")
        page = mapping(page, f"page {page_id}")
        omit_null(page, {"elements", "collections"})
        fields(page, {"identify", "elements", "collections"}, {"identify"}, f"page {page_id}")
        page_condition(page["identify"], f"page {page_id}.identify")
        for group, collection in (("elements", False), ("collections", True)):
            for name, definition in mapping(page.get(group, {}), f"page {page_id}.{group}").items():
                string(name, f"page {page_id}.{group} name")
                target_definition(definition, f"page {page_id}.{group}.{name}", collection)
    return obj


def output_path(value: Any, where: str) -> None:
    string(value, where)
    p = PurePath(value)
    w = PureWindowsPath(value)
    if p.is_absolute() or w.is_absolute() or w.drive or ".." in p.parts or ".." in w.parts:
        fail(where, "output file must stay inside output root")


def outputs(data: Any) -> dict:
    result = mapping(data, "outputs")
    for name, item in result.items():
        string(name, "output name")
        item = mapping(item, f"output {name}")
        omit_null(item, {"existing"})
        fmt = item.get("format")
        if not isinstance(fmt,str) or fmt not in {"csv", "jsonl", "text"}:
            fail(f"output {name}", "unsupported format")
        fields(item, {"format", "file", "existing"} | ({"columns"} if fmt == "csv" else set()), {"format", "file"} | ({"columns"} if fmt == "csv" else set()), f"output {name}")
        output_path(item["file"], f"output {name}.file")
        if not isinstance(item.get('existing','new'),str) or item.get("existing", "new") not in {"new", "append", "overwrite"}:
            fail(f"output {name}.existing", "unsupported policy")
        if fmt == "csv":
            cols = item["columns"]
            if not isinstance(cols, list) or not cols:
                fail(f"output {name}.columns", "unique non-empty column list required")
            for col in cols:
                string(col, f"output {name}.column")
            if len(set(cols)) != len(cols):
                fail(f"output {name}.columns", "unique non-empty column list required")
    return result


def node(data: Any, where: str, declared_outputs: dict, scenario_vars: set[str]) -> None:
    obj = mapping(data, where)
    omit_null(obj, {"enabled", "description", "_meta", "risk", "within", "timeout", "else", "max_iterations"})
    common = {"enabled", "description", "_meta"}
    if "enabled" in obj:
        boolean(obj["enabled"], where + ".enabled")
    if "description" in obj:
        string(obj["description"], where + ".description", False)
    if "_meta" in obj:
        meta = mapping(obj["_meta"], where)
        fields(meta, {"id"}, {"id"}, where + "._meta")
        identity = string(meta["id"], where + "._meta.id")
        if not re.fullmatch(r'[0-7][0-9A-HJKMNP-TV-Z]{25}',identity):
            fail(where + '._meta.id', 'canonical ULID required')
    kind = set(obj) & {"action", "if", "repeat", "while", "for_each"}
    if len(kind) != 1:
        fail(where, "exactly one node kind required")
    kind = kind.pop()
    if kind == "action":
        action = obj["action"]
        if not isinstance(action, str) or action not in ACTIONS:
            fail(where, "unsupported action")
        spec = {
            "open": ({"url"}, {"url"}), "click": ({"target", "within"}, {"target"}),
            "double_click": ({"target", "within"}, {"target"}), "input": ({"target", "value", "within"}, {"target", "value"}),
            "select": ({"target", "value", "within"}, {"target", "value"}), "read": ({"target", "source", "into", "within"}, {"target", "source", "into"}),
            "append": ({"output", "values", "value"}, {"output"}), "upload": ({"target", "path", "within"}, {"target", "path"}),
            "key": ({"key", "keys", "target", "within"}, set()), "hover": ({"target", "within"}, {"target"}),
            "drag_drop": ({"from", "to"}, {"from", "to"}), "alert_input": ({"value"}, {"value"}),
            "wait": ({"until", "timeout"}, {"until"}), "check": ({"condition"}, {"condition"}),
            "switch_window": ({"to"}, {"to"}),
        }
        allowed, required = spec.get(action, (set(), set()))
        fields(obj, common | {"action", "risk"} | allowed, {"action"} | required, where)
        if "risk" in obj and (not isinstance(obj['risk'],str) or obj["risk"] not in {"安全", "更新", "破壊的"}):
            fail(where + ".risk", "unsupported risk")
        for key in {"target", "from", "to", "output", "url", "path", "within"} & set(obj):
            string(obj[key], where + "." + key)
        for key in {"url", "path", "value", "within"} & set(obj):
            reference_syntax(obj[key], where + "." + key)
        if action in {"input", "select", "alert_input"}:
            scalar(obj["value"], where + ".value")
        if action == "read":
            src = obj["source"]
            valid_source = src in {"text", "value"} if isinstance(src, str) else (isinstance(src, dict) and set(src) == {"attribute"} and isinstance(src["attribute"], str) and bool(src["attribute"]))
            if not valid_source:
                fail(where + ".source", "invalid read source")
            variable(obj["into"], where + ".into")
            if obj["into"] in scenario_vars:
                fail(where + ".into", "runtime variable collides with scenario variable")
        if action == "append":
            output = declared_outputs.get(obj["output"])
            if output is None:
                fail(where, "undefined output")
            if ("value" in obj) == ("values" in obj):
                fail(where, "exactly one of value/values required")
            if output["format"] == "text":
                if "value" not in obj:
                    fail(where, "text output requires value")
                scalar(obj["value"], where)
                values = [obj["value"]]
            else:
                if "values" not in obj or not mapping(obj["values"], where):
                    fail(where, "structured output requires non-empty values")
                if output["format"] == "csv" and set(obj["values"]) != set(output["columns"]):
                    fail(where, "CSV keys must exactly match columns")
                values = list(obj["values"].values())
                for k, v in obj["values"].items():
                    string(k, where)
                    scalar(v, where)
            for v in values:
                reference_syntax(v, where)
                if isinstance(v, str) and "${credential." in v:
                    fail(where, "credential reference forbidden in output")
        if action == "key":
            if ("key" in obj) == ("keys" in obj):
                fail(where, "exactly one of key/keys required")
            if "within" in obj and "target" not in obj:
                fail(where, "within requires target")
            if "key" in obj:
                string(obj["key"], where)
                reference_syntax(obj['key'],where)
            else:
                if not isinstance(obj["keys"], list) or not obj["keys"]:
                    fail(where, "non-empty keys required")
                for v in obj["keys"]:
                    string(v, where)
                    reference_syntax(v,where)
        if action == "wait":
            condition(obj["until"], where + ".until", True)
            if "timeout" in obj:
                duration(obj["timeout"], where + ".timeout")
        if action == "check":
            condition(obj["condition"], where + ".condition")
        if action == "switch_window" and obj["to"] not in {"newest", "parent"}:
            fail(where, "switch_window.to must be newest or parent")
    else:
        fields(obj, common | {kind} | ({"then", "else"} if kind == "if" else set()), {kind} | ({"then"} if kind == "if" else set()), where)
        if kind == "if":
            condition(obj["if"], where + ".if")
            children = [obj["then"], obj.get("else", [])]
        elif kind == "repeat":
            body = mapping(obj[kind], where)
            fields(body, {"count", "steps"}, {"count", "steps"}, where)
            positive(body["count"], where + ".count")
            children = [body["steps"]]
        elif kind == "while":
            body = mapping(obj[kind], where)
            omit_null(body, {"max_iterations", "timeout"})
            cond = {k: v for k, v in body.items() if k in CONDITIONS}
            fields(body, CONDITIONS | {"max_iterations", "timeout", "steps"}, {"steps"}, where)
            condition(cond, where + ".while")
            if "max_iterations" in body:
                positive(body["max_iterations"], where)
            if "timeout" in body:
                duration(body["timeout"], where)
            children = [body["steps"]]
        else:
            body = mapping(obj[kind], where)
            fields(body, {"target", "as", "steps"}, {"target", "as", "steps"}, where)
            string(body["target"], where)
            variable(body["as"], where)
            if body["as"] in scenario_vars:
                fail(where, "loop variable collides with scenario variable")
            children = [body["steps"]]
        for ci, group in enumerate(children):
            if not isinstance(group, list):
                fail(where, "steps list required")
            for i, child in enumerate(group):
                child_vars = scenario_vars | {body['as']} if kind == 'for_each' else scenario_vars
                node(child, f"{where}.{kind}[{ci}][{i}]", declared_outputs, child_vars)


def scenario(data: Any) -> dict:
    obj = mapping(data, "scenario")
    omit_null(obj, {"description", "mode", "variables", "outputs"})
    fields(obj, {"version", "name", "description", "mode", "variables", "outputs", "steps"}, {"version", "name", "steps"}, "scenario")
    if type(obj["version"]) is not int or obj["version"] != 1:
        fail("scenario.version", "version 1 required")
    string(obj["name"], "scenario.name")
    if "description" in obj:
        string(obj["description"], "scenario.description", False)
    if not isinstance(obj.get('mode','実行'),str) or obj.get("mode", "実行") not in {"実行", "確認", "デバッグ"}:
        fail("scenario.mode", "unsupported mode")
    variables = mapping(obj.get("variables", {}), "scenario.variables")
    for name, value in variables.items():
        variable(name, "scenario.variable")
        scalar(value, f"scenario.variables.{name}")
    declared = outputs(obj.get("outputs", {}))
    if not isinstance(obj["steps"], list):
        fail("scenario.steps", "list required")
    for i, step in enumerate(obj["steps"]):
        node(step, f"step[{i + 1}]", declared, set(variables))
    from .editor import walk_nodes
    identities = [n['_meta']['id'] for n in walk_nodes(obj['steps']) if '_meta' in n]
    if len(identities) != len(set(identities)): fail('scenario.steps','duplicate node identity')
    return obj


def credentials(data: Any) -> dict:
    obj = mapping(data, "credentials")
    fields(obj, {"version", "credentials"}, {"version", "credentials"}, "credentials")
    if type(obj["version"]) is not int or obj["version"] != 1:
        fail("credentials.version", "version 1 required")
    for group, entries in mapping(obj["credentials"], "credentials.credentials").items():
        string(group, "credential group")
        for key, value in mapping(entries, f"credential {group}").items():
            string(key, "credential key")
            string(value, "credential value", False)
    return obj


def config(data: Any, source: str | Path) -> dict:
    obj = mapping(data, "config")
    defaults = {
        "browser": {"type": "edge", "executable": None, "profile_path": None},
        "credentials": {"path": "./credentials.yaml"},
        "timeouts": {"default": "10s", "page_load": "30s"},
        "paths": {"scenarios": "./scenarios", "logs": "./logs", "downloads": "./downloads", "outputs": "./outputs"},
        "loops": {"max_iterations": 1000, "timeout": "10m"},
        "recorder": {"arrange_windows": True},
        "playback": {"observation_delay": "0s"},
        "logging": {"level": "INFO"},
        "safety": {"destructive_confirmation": "always"},
    }
    omit_null(obj, set(defaults))
    fields(obj, {"version", "driver"} | set(defaults), {"version", "driver"}, "config")
    if type(obj["version"]) is not int or obj["version"] != 1:
        fail("config.version", "version 1 required")
    driver = mapping(obj["driver"], "config.driver")
    fields(driver, {"path"}, {"path"}, "config.driver")
    driver_path = string(driver["path"], "config.driver.path")
    if not (Path(driver_path).is_absolute() or PureWindowsPath(driver_path).is_absolute()):
        fail("config.driver.path", "absolute path required")
    result = {"version": 1, "driver": {"path": driver_path}}
    for section, dflt in defaults.items():
        supplied = mapping(obj.get(section, {}), f"config.{section}")
        omit_null(supplied, set(dflt))
        fields(supplied, set(dflt), set(), f"config.{section}")
        result[section] = dflt | supplied
    if result["browser"]["type"] != "edge":
        fail("config.browser.type", "only edge is supported")
    for section, keys in (("browser", ("executable", "profile_path")), ("credentials", ("path",)), ("paths", tuple(defaults["paths"]))):
        for key in keys:
            val = result[section][key]
            if val is not None:
                string(val, f"config.{section}.{key}")
    for section, keys in (("timeouts", ("default", "page_load")), ("loops", ("timeout",)), ("playback", ("observation_delay",))):
        for key in keys:
            duration(result[section][key], f"config.{section}.{key}")
    positive(result["loops"]["max_iterations"], "config.loops.max_iterations")
    boolean(result["recorder"]["arrange_windows"], "config.recorder.arrange_windows")
    if not isinstance(result['logging']['level'],str) or result["logging"]["level"] not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        fail("config.logging.level", "invalid level")
    if not isinstance(result['safety']['destructive_confirmation'],str) or result["safety"]["destructive_confirmation"] not in {"always", "once_per_run", "off"}:
        fail("config.safety.destructive_confirmation", "invalid policy")
    root = Path(source).resolve().parent
    for section, keys in (("browser", ("profile_path", "executable")), ("credentials", ("path",)), ("paths", tuple(defaults["paths"]))):
        for key in keys:
            val = result[section][key]
            if val is not None:
                result[section][key] = str((root / val).resolve()) if not (Path(val).is_absolute() or PureWindowsPath(val).is_absolute()) else val
    return result


def validate_package(scenario_doc: dict, registry_doc: dict) -> None:
    """Validate cross-file facts that do not require a live page."""
    pages = registry_doc["pages"]
    def namespaces(steps, defined):
        defined = set(defined)
        for item in steps:
            if item.get('enabled',True) is False: continue
            if item.get('action')=='read': defined.add(item['into'])
            elif 'if' in item:
                left=namespaces(item['then'],defined)
                right=namespaces(item.get('else',[]),defined)
                defined = left & right
            elif 'repeat' in item:
                defined=namespaces(item['repeat']['steps'],defined)
            elif 'while' in item:
                namespaces(item['while']['steps'],defined)
            elif 'for_each' in item:
                name=item['for_each']['as']
                if name in defined:
                    fail('for_each', f'loop variable {name} collides with a preceding runtime variable')
                namespaces(item['for_each']['steps'],defined)
        return defined
    namespaces(scenario_doc['steps'],set())
    incompatible = {
        "input": {"button", "link", "checkbox", "radio", "select", "file", "tab", "menu"},
        "select": KINDS - {"select", "element"},
        "upload": KINDS - {"file", "element"},
    }
    def check_condition(data: dict, where: str):
        op, val = next(iter(data.items()))
        if op == "page" and val not in pages:
            fail(where, f"undefined page {val}")
        if op in {"all", "any"}:
            for i, child in enumerate(val):
                check_condition(child, f"{where}[{i}]")
        if op == "not":
            check_condition(val, where + ".not")
    def walk(steps: list, where: str):
        for i, step in enumerate(steps):
            path = f"{where}[{i + 1}]"
            if "action" in step:
                act = step["action"]
                if "target" in step:
                    name = step["target"]
                    known = [page.get("elements", {})[name] for page in pages.values() if name in page.get("elements", {})]
                    if known and all(d["kind"] in incompatible.get(act, set()) for d in known):
                        fail(path, f"target {name} kind incompatible with {act}")
                if act in {"check", "wait"}:
                    check_condition(step["condition" if act == "check" else "until"], path)
            elif "if" in step:
                check_condition(step["if"], path)
                walk(step["then"], path + ".then")
                walk(step.get("else", []), path + ".else")
            elif "for_each" in step:
                name = step["for_each"]["target"]
                if not any(name in page.get("collections", {}) for page in pages.values()):
                    fail(path, f"undefined collection {name}")
                walk(step["for_each"]["steps"], path + ".for_each")
            else:
                key = "repeat" if "repeat" in step else "while"
                if key == "while":
                    check_condition({k: v for k, v in step[key].items() if k in CONDITIONS}, path)
                walk(step[key]["steps"], path + "." + key)
    walk(scenario_doc["steps"], "step")
