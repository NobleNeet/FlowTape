"""Scenario identity and edit analysis independent of Qt and Selenium."""

import copy
from .errors import FlowTapeError


def walk_nodes(steps):
    for node in steps:
        yield node
        if "if" in node:
            yield from walk_nodes(node["then"])
            yield from walk_nodes(node.get("else", []))
        for key in ("repeat", "while", "for_each"):
            if key in node:
                yield from walk_nodes(node[key]["steps"])


def node_map(document):
    return {n.get("_meta", {}).get("id"): n for n in walk_nodes(document["steps"]) if n.get("_meta", {}).get("id")}


def sequences(document):
    result = {("root",): document["steps"]}
    for node in walk_nodes(document["steps"]):
        identity = node.get("_meta", {}).get("id")
        if "if" in node:
            result[(identity, "then")] = node["then"]
            if "else" in node:
                result[(identity, "else")] = node["else"]
        for key in ("repeat", "while", "for_each"):
            if key in node:
                result[(identity, key)] = node[key]["steps"]
    return result


def own_content(node):
    result = copy.deepcopy(node)
    result.pop("then", None)
    result.pop("else", None)
    for key in ("repeat", "while", "for_each"):
        if key in result:
            result[key].pop("steps", None)
    return result


def _url_evidence(condition, url):
    op, value = next(iter(condition.items()))
    if op == "url":
        kind, expected = next(iter(value.items()))
        return url == expected if kind == "equals" else expected in url if kind == "contains" else url.startswith(expected)
    if op == "exists": return None
    if op == "not":
        child = _url_evidence(value, url)
        return None if child is None else not child
    children = [_url_evidence(c, url) for c in value]
    if op == "all":
        return False if False in children else None if None in children else True
    return True if True in children else None if None in children else False


def target_references(document, registry, name):
    """Conservative page attribution; browser mutations invalidate inferred scope."""
    references = []
    def condition_refs(condition, scope, path):
        op, value = next(iter(condition.items()))
        if op in {"all", "any"}:
            for i, child in enumerate(value): condition_refs(child, scope, path + (op, i))
        elif op == "not": condition_refs(value, scope, path + (op,))
        elif op in {"text_equals", "value_equals"}:
            if value["target"] == name: references.append((path + (op, "target"), scope))
        elif op in {"exists", "not_exists", "visible", "hidden", "enabled", "disabled"} and value == name:
            references.append((path + (op,), scope))
    def walk(steps, scope, path):
        for i, node in enumerate(steps):
            here = path + (i,)
            if "action" in node:
                action = node["action"]
                for field in ("target", "from", "to"):
                    if action != "switch_window" and node.get(field) == name:
                        references.append((here + (field,), scope))
                if action in {"check", "wait"}:
                    field = "condition" if action == "check" else "until"
                    condition_refs(node[field], scope, here + (field,))
                    if node.get("enabled", True) and set(node[field]) == {"page"}:
                        scope = node[field]["page"]
                elif node.get("enabled", True):
                    if action == "open" and "${" not in node["url"]:
                        results = {page: _url_evidence(definition["identify"], node["url"]) for page, definition in registry["pages"].items()}
                        possible = [page for page, result in results.items() if result is not False]
                        scope = possible[0] if len(possible) == 1 and results[possible[0]] is True else None
                    elif action not in {"read", "append"}:
                        scope = None
            elif "if" in node:
                condition_refs(node["if"], scope, here + ("if",))
                then_scope = node["if"].get("page", scope)
                left = walk(node["then"], then_scope, here + ("then",))
                right = walk(node.get("else", []), scope, here + ("else",))
                if node.get("enabled", True): scope = left if left == right else None
            else:
                kind = next(k for k in ("repeat", "while", "for_each") if k in node)
                body = node[kind]
                ref_start = len(references)
                if kind == "while":
                    condition_refs({k:v for k,v in body.items() if k not in {"steps", "timeout", "max_iterations"}}, scope, here + (kind,))
                end_scope = walk(body["steps"], scope, here + (kind, "steps"))
                repeats = kind != 'repeat' or body['count'] > 1
                if repeats and end_scope != scope:
                    # A later iteration may begin on a different page. Re-run
                    # attribution from unknown scope; explicit page checks in
                    # the body can still establish their own proven scope.
                    del references[ref_start:]
                    if kind == 'while':
                        condition_refs({k:v for k,v in body.items() if k not in {'steps','timeout','max_iterations'}}, None, here + (kind,))
                    walk(body['steps'], None, here + (kind,'steps'))
                if node.get("enabled", True) and end_scope != scope: scope = None
        return scope
    walk(document["steps"], None, ("steps",))
    return references


class RenameAmbiguity(FlowTapeError):
    def __init__(self, locations):
        self.locations = locations
        super().__init__("page scope must be confirmed for: " + ", ".join(str(p) for p in locations))


def rename_target(document, registry, page_id, old, new, decisions=None):
    decisions = decisions or {}
    targets = registry["pages"][page_id].get("elements", {})
    if old not in targets or not new or (new != old and new in targets):
        raise FlowTapeError("rename source missing or new name already exists")
    refs = target_references(document, registry, old)
    ambiguous = [path for path, scope in refs if scope is None and path not in decisions]
    if ambiguous:
        raise RenameAmbiguity(ambiguous)
    trial, knowledge = copy.deepcopy(document), copy.deepcopy(registry)
    renamed = knowledge["pages"][page_id]["elements"]
    renamed[new] = renamed.pop(old)
    for path, scope in refs:
        if scope != page_id and not (scope is None and decisions[path]): continue
        parent = trial
        for key in path[:-1]: parent = parent[key]
        parent[path[-1]] = new
    return trial, knowledge
