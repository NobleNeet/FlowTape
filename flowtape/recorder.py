"""Recorder event transport, normalization, and semantic locator proposals."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from importlib.resources import files
from time import monotonic
from selenium.common.exceptions import WebDriverException, JavascriptException

from .browser import DOM_JS
from .browser import Resolver
from .capture_bridge import CaptureBridge
from .windows import WindowContext
from .errors import FlowTapeError, UnsupportedOperationError
from .recorder_trace import RecorderTrace

OBSERVER_JS = files("flowtape").joinpath("observer.js").read_text(encoding="utf-8")
DYNAMIC_ID = re.compile(r"(?:[a-f0-9]{8}-[a-f0-9-]{20,}|[a-f0-9]{12,}|\d{6,}|(?:css|mui|react|ember)[-_][a-f0-9]{5,}|:r\d+:)", re.I)


@dataclass
class Operation:
    action: str
    snapshot: dict | None = None
    value: str | None = None
    data: dict | None = None
    context: list[dict] | None = None
    url: str | None = None
    document_id: str | None = None
    element_ref: int | None = None
    handle: str | None = None
    event_seq: int | None = None


class EventNormalizer:
    def __init__(self, double_click_window: float = .35, trace=None):
        self.trace = trace or RecorderTrace()
        self.last_seq: dict[str, int] = {}
        self.pending_clicks: list[tuple[float, dict]] = []
        self.window = double_click_window

    @staticmethod
    def operation(event, action, value=None, data=None):
        target = event.get('target') or {}
        snapshot = target.get('snapshot')
        return Operation(action, snapshot, value, data,
                         (event.get('window_context', {}).get('frame_path') or []) + (snapshot or {}).get('shadow_path', []),
                         event.get('document', {}).get('url'), event.get('document_instance_id'),
                         target.get('element_ref'), event.get('window_context', {}).get('handle'), event.get('event_seq'))

    def consume(self, events: list[dict], now: float | None = None) -> list[Operation]:
        now = monotonic() if now is None else now
        out = []
        for event in events:
            self.trace.event('normalizer_receive', event)
            if event.get("protocol_version") != 1:
                raise FlowTapeError("Recorder protocol version mismatch")
            doc = event["document_instance_id"]
            seq = event["event_seq"]
            if doc not in self.last_seq and seq != 1:
                raise FlowTapeError('Recorder event sequence has no established start boundary')
            if seq <= self.last_seq.get(doc, 0):
                self.trace.event('normalizer_duplicate', event)
                continue
            if doc in self.last_seq and seq != self.last_seq[doc] + 1:
                raise FlowTapeError("Recorder event sequence gap")
            self.last_seq[doc] = seq
            typ = event["type"]
            if typ=='unsupported':
                raise UnsupportedOperationError('Recorder operation unsupported: ' + event.get('data',{}).get('reason','unknown'))
            snap = (event.get("target") or {}).get("snapshot")
            if typ == "click":
                out.extend(self.flush(now))
                self.pending_clicks.append((now, event))
            elif typ == "dblclick":
                def same_target(prior):
                    target, other = event.get('target') or {}, prior.get('target') or {}
                    if target.get('element_ref') is not None and other.get('element_ref') is not None:
                        return event['document_instance_id'] == prior['document_instance_id'] and target['element_ref'] == other['element_ref']
                    return event['document_instance_id'] == prior['document_instance_id'] and other.get('snapshot') == snap
                unrelated = [(stamp, prior) for stamp, prior in self.pending_clicks if not same_target(prior)]
                self.pending_clicks = unrelated
                out.extend(self.flush(now, force=True))
                self.pending_clicks.clear()
                out.append(self.operation(event, 'double_click'))
            elif typ == "input_commit":
                out.extend(self.flush(now, force=True))
                data = event.get("data", {})
                out.append(self.operation(event, 'input', None if data.get('secret') else data.get('value'), data))
            elif typ == "select":
                out.extend(self.flush(now, force=True))
                out.append(self.operation(event, 'select', event.get('data', {}).get('text'), event.get('data')))
            elif typ == "key":
                out.extend(self.flush(now, force=True))
                out.append(self.operation(event, 'key', event.get('data', {}).get('key'), event.get('data')))
            elif typ == "pick":
                out.append(self.operation(event, 'pick'))
            elif typ == 'picker_cancel': out.append(self.operation(event, 'picker_cancel'))
            elif typ == 'navigation':
                out.extend(self.flush(now, force=True))
                out.append(self.operation(event, 'open', data=event['data']))
        for op in out:
            self.trace.operation('normalizer_operation', op)
        return out

    def flush(self, now: float | None = None, force: bool = False) -> list[Operation]:
        now = monotonic() if now is None else now
        ready = []
        while self.pending_clicks and (force or now - self.pending_clicks[0][0] >= self.window):
            _, event = self.pending_clicks.pop(0)
            op = self.operation(event, 'click')
            ready.append(op)
            self.trace.operation('normalizer_click_flush', op)
        return ready


def propose_target(snapshot: dict, *, resolver: Resolver | None = None, context=None,
                   document_id=None, element_ref=None, diagnostics=None) -> dict:
    """Produce stable semantic candidates; live uniqueness is checked by caller."""
    attrs = snapshot.get("attributes", {})
    candidates = []
    for key in ('data-testid', 'data-test', 'data-cy', 'data-qa'):
        testid = attrs.get(key)
        if testid and not DYNAMIC_ID.search(testid):
            candidates.append({'by': 'testid', 'value': testid})
    ident = attrs.get("id")
    if ident and not DYNAMIC_ID.search(ident):
        candidates.append({"by": "id", "value": ident})
    if snapshot.get("role") and snapshot.get("name"):
        candidates.append({"by": "role", "role": snapshot["role"], "name": snapshot["name"]})
    if snapshot.get("label"):
        candidates.append({"by": "label", "value": snapshot["label"]})
    if attrs.get("name") and not DYNAMIC_ID.search(attrs["name"]):
        candidates.append({"by": "name", "value": attrs["name"]})
    if attrs.get("placeholder"):
        candidates.append({"by": "placeholder", "value": attrs["placeholder"]})
    if snapshot.get("text") and len(snapshot["text"]) < 80:
        candidates.append({"by": "text", "value": snapshot["text"], "exact": True})
    for key in ('data-action', 'href'):
        value = attrs.get(key)
        if value and not DYNAMIC_ID.search(value) and not (key == 'href' and ('?' in value or '#' in value)):
            candidates.append({'by':'attribute', 'name':key, 'value':value})
    target = ({'role':snapshot['role'], 'name':snapshot['name']} if snapshot.get('role') and snapshot.get('name') else
              {'label':snapshot['label']} if snapshot.get('label') else None)
    if target:
        for relation in snapshot.get('relations', []):
            candidates.append({'by':'relative', **relation, 'target':target})
    tag = snapshot.get("tag")
    role = snapshot.get("role")
    kind = ("file" if attrs.get("type") == "file" else attrs.get("type") if tag == "input" and attrs.get("type") in {"checkbox", "radio"} else "input" if tag == "input" else tag if tag in {"textarea", "select"} else role if role in {"button", "link", "checkbox", "radio", "tab"} else "element")
    if tag == 'input' and role == 'button' and attrs.get('type') != 'file': kind = 'button'
    expect = {"tag": tag} if tag else {}
    if kind in {"button", "link", "checkbox", "radio", "tab"}:
        expect = {"role": role}
    if kind in {"input", "textarea"} or snapshot.get('editable'):
        expect["editable"] = True
    if kind == 'input' and attrs.get('type'):
        expect['input_type'] = attrs['type']
    definition = {'kind':kind, 'locate':[], 'expect':expect}
    if context: definition['context'] = context
    if resolver is None:
        definition['locate'] = candidates[:3]
        return definition
    scope = resolver._context(definition)
    captured = resolver.js("return window.__flowtape?.documentInstanceId===arguments[0] ? window.__flowtape.refs.get(arguments[1])?.deref() || null : null;", document_id, element_ref)
    if captured is None:
        raise FlowTapeError('captured element is no longer available; pick it again to verify its identity')
    # Short purposeful CSS is the final fallback; never invent a positional path.
    tag = snapshot.get('tag')
    for cls in attrs.get('class', '').split():
        if re.fullmatch(r'[a-zA-Z][a-zA-Z_-]*', cls) and '-' in cls and not cls.startswith(('Mui','css-', 'text-', 'bg-', 'px-', 'py-')):
            candidates.append({'by':'css', 'value':f'{tag}.{cls}'})
    ranked = []
    weights = {'testid':(35,20,10), 'id':(32,18,10), 'role':(30,20,9),
               'label':(32,20,10), 'name':(29,16,10), 'placeholder':(23,14,10),
               'text':(22,17,10), 'attribute':(26,16,9), 'relative':(29,20,7), 'css':(18,7,8)}
    for loc in candidates:
        try:
            matches = resolver._candidate(scope, loc, expect, '',kind)
            count = None if matches is None else len(matches)
            reproduced = matches is not None and any(el.id == captured.id for el in matches)
        except WebDriverException:
            count, reproduced = None, False
        stability, semantic, simplicity = weights[loc['by']]
        unique = 25 if count == 1 else 12 if count == 2 else 5 if count and count <= 5 else 0
        score = stability + semantic + simplicity + unique + 10
        if diagnostics is not None: diagnostics.append({'locator':loc, 'count':count, 'captured_match':reproduced, 'score':score})
        if reproduced and count == 1: ranked.append((score, loc))
    if not ranked:
        css = resolver.js("""
          const parts=[];let el=arguments[0];
          while(el && el.nodeType===Node.ELEMENT_NODE) {
            const siblings=el.parentElement?[...el.parentElement.children].filter(x=>x.localName===el.localName):[];
            parts.unshift(el.localName+(siblings.length>1?':nth-of-type('+(siblings.indexOf(el)+1)+')':''));
            el=el.parentElement;
          }
          return parts.join(' > ');
        """, captured)
        emergency={'by':'css','value':css,'fragile':True}
        matches=resolver._candidate(scope,emergency,expect,'',kind)
        if matches and len(matches)==1 and matches[0].id==captured.id:
            ranked.append((35,emergency))
            if diagnostics is not None: diagnostics.append({'locator':emergency,'count':1,'captured_match':True,'score':35})
    seen = set()
    for score, loc in sorted(ranked, key=lambda pair:pair[0], reverse=True):
        # role/name/text often derive from the same label or control text.
        evidence = 'accessible_text' if loc['by'] in {'role','label','text'} else (loc['by'], str(loc.get('value', loc)))
        if evidence in seen: continue
        seen.add(evidence)
        definition['locate'].append(loc)
        if len(definition['locate']) == 3: break
    return definition


def captured_target(operation):
    """Accept only candidates proven unique at the original event boundary.

    Stage 1 evidence can survive navigation; it never proves anything about
    the destination DOM. Frame/shadow captures still require live verification.
    """
    evidence = (operation.snapshot or {}).get('capture', {})
    if operation.context or evidence.get('document_id') != operation.document_id:
        return None
    definition = propose_target(operation.snapshot)
    definition['locate'] = [loc for loc in definition['locate'] if loc in evidence.get('locate', [])]
    return definition if definition['locate'] else None


def propose_collections(operation, resolver):
    definition = {'context':operation.context or []}
    scope = resolver._context(definition)
    captured = resolver.js("return window.__flowtape?.documentInstanceId===arguments[0] ? window.__flowtape.refs.get(arguments[1])?.deref() || null : null;", operation.document_id, operation.element_ref)
    if captured is None: raise FlowTapeError('collection representative is no longer available')
    representative = resolver.js("return arguments[0].closest('tr,[role=row],li,[role=listitem]') || arguments[0];", captured)
    snapshot = resolver.js('return FT.snapshot(arguments[0]);', representative)
    candidates = []
    if snapshot.get('role'): candidates.append({'by':'role','role':snapshot['role']})
    tag = snapshot['tag']
    if tag in {'tr','li','article','option'}: candidates.append({'by':'css','value':tag})
    for cls in snapshot['attributes'].get('class','').split():
        if re.fullmatch(r'[a-zA-Z][a-zA-Z_-]*',cls) and not cls.startswith(('css-', 'Mui')):
            candidates.append({'by':'css','value':tag+'.'+cls})
    result=[]
    for locator in candidates:
        expect={'tag':tag}
        found=resolver._candidate(scope,locator,expect,'')
        if found and any(el.id==representative.id for el in found):
            item={'locate':[locator], 'expect':expect}
            if operation.context: item['context']=operation.context
            result.append((item,found))
    return result


class RecorderTransport:
    def __init__(self, driver):
        self.driver = driver
        self.trace = RecorderTrace.from_environment()
        self.normalizer = EventNormalizer(trace=self.trace)
        self.mode = "observe"
        self.bridges = {}
        self.documents = {}
        self.windows = WindowContext(driver)
        self.page_conditions = {}

    def set_pages(self, pages):
        conditions = {name: page['identify'] for name, page in pages.items()}
        if conditions == self.page_conditions:
            return
        self.page_conditions = conditions
        for bridge in self.bridges.values():
            self._configure_bridge(bridge)

    def _visit(self, collect: bool = False, flush: bool = False, boundary: bool = False, reset: bool = False):
        events = []
        def traverse(path: list[dict]):
            try:
                baseline = self.driver.execute_script(DOM_JS + "\n" + OBSERVER_JS + "\nconst boundary={id:window.__flowtape.documentInstanceId,seq:window.__flowtape.sequence};window.__flowtape.traceEnabled=arguments[2];window.__flowtape.pageConditions=arguments[3];window.__flowtape.setMode(arguments[0]);window.__flowtape.framePath=arguments[1];return boundary;", self.mode, path, self.trace.enabled, self.page_conditions)
                self.trace.write('transport_document', document_id=baseline['id'], event_seq=baseline['seq'], mode=self.mode, frame_depth=len(path))
                if boundary: self.normalizer.last_seq[baseline['id']] = baseline['seq']
                self.documents[baseline['id']] = {'frame_path':path, 'handle':self.driver.current_window_handle}
                if reset:
                    self.driver.execute_script("window.__flowtape.events=[];window.__flowtape.overflow=false;window.__flowtape.pendingInput=null;window.__flowtape.setMode('observe');")
                if flush:
                    self.driver.execute_script("window.__flowtape.flushInput();window.__flowtape.setMode('observe');")
                if collect:
                    if self.trace.enabled:
                        for record in self.driver.execute_script('return window.__flowtape.drainTraces();'):
                            self.trace.browser(record)
                        if self.driver.execute_script('return window.__flowtape.traceOverflow;'):
                            self.trace.write('trace_overflow', reason='diagnostic_queue_overflow')
                    batch = self.driver.execute_script("return window.__flowtape.drain();")
                    if self.driver.execute_script("return !!window.__flowtape.overflow;"):
                        raise FlowTapeError("Recorder queue overflow; recording desynchronized")
                    for event in batch:
                        self.trace.event('transport_poll', event)
                        event['window_context'] = {'frame_path':path, 'handle':self.driver.current_window_handle}
                    events.extend(batch)
                frames = self.driver.execute_script(DOM_JS + '\nreturn FT.frames();')
            except JavascriptException:
                raise FlowTapeError('Recorder injection/protocol failure; recording desynchronized') from None
            except WebDriverException:
                return
            for frame in frames:
                try:
                    ident = frame.get_attribute("id")
                    name = frame.get_attribute("name")
                    shadow = self.driver.execute_script(DOM_JS + '\nreturn FT.shadowPath(arguments[0]);', frame)
                    css = self.driver.execute_script(DOM_JS + '\nreturn FT.hostSelector(arguments[0]);', frame)
                    step = {"frame": {"id": ident}} if ident else ({"frame": {"name": name}} if name else {'frame':{'css':css}})
                    self.driver.switch_to.frame(frame)
                    traverse(path + shadow + [step])
                except WebDriverException:
                    pass
                finally:
                    try: self.driver.switch_to.parent_frame()
                    except WebDriverException: self.driver.switch_to.default_content()
        try: original = self.driver.current_window_handle
        except WebDriverException: original = self.windows.restore()
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if handle not in self.bridges:
                self.bridges[handle] = CaptureBridge(self.driver, handle, trace=self.trace)
                self._configure_bridge(self.bridges[handle])
            self._attach_frames(self.bridges[handle])
            self.driver.switch_to.default_content()
            traverse([])
        if original in self.driver.window_handles:
            self.driver.switch_to.window(original)
        self.driver.switch_to.default_content()
        if collect:
            by_identity = {(e['document_instance_id'], e['event_seq']): e for e in events}
            for bridge in self.bridges.values():
                for event in bridge.drain():
                    known = self.documents.get(event['document_instance_id'])
                    if known: event['window_context'] = known.copy()
                    by_identity.setdefault((event['document_instance_id'],event['event_seq']), event)
            events = sorted(by_identity.values(), key=lambda e:(e['timestamp'], e['event_seq']))
            for event in events:
                self.trace.event('transport_merged', event)
            if any(e.get('window_context',{}).get('frame_path') is None for e in events):
                raise FlowTapeError('frame navigation event has no verified frame path; recording desynchronized')
        return events

    def _attach_frames(self, root_bridge):
        # Chromium isolates cross-origin frames into separate CDP targets.
        # Bind before traversal enables record mode in those documents, too.
        targets = root_bridge.connection.execute(root_bridge.protocol.target.get_targets())
        for target in targets:
            identity = str(target.target_id)
            if target.type_=='iframe' and identity not in self.bridges:
                bridge=CaptureBridge(self.driver,None,target_id=identity,trace=self.trace)
                self.bridges[identity]=bridge
                self._configure_bridge(bridge)

    def _configure_bridge(self, bridge):
        bridge.navigation.set_mode(self.mode)
        try:
            bridge.configure('(()=>{' + DOM_JS + '\n' + OBSERVER_JS + '\nwindow.__flowtape.traceEnabled=' + str(self.trace.enabled).lower() + ';window.__flowtape.pageConditions=' + json.dumps(self.page_conditions) + ';window.__flowtape.setMode(' + repr(self.mode) + ');})();')
        except WebDriverException:
            targets = self.driver.execute_cdp_cmd('Target.getTargets', {})['targetInfos']
            if bridge.handle is not None or any(target['targetId'] == str(bridge.target_id) for target in targets):
                raise
            bridge.connection.detached = True
            self.trace.write('transport_frame_detached')

    def navigate(self, url):
        """Application URL command owns its explicit open, avoiding duplicates."""
        bridges = list(self.bridges.values())
        for bridge in bridges:
            bridge.navigation.suppressed = True
        try:
            self.driver.get(url)
        finally:
            for bridge in bridges:
                bridge.navigation.suppressed = False

    def inject(self, mode: str = "record"):
        self.trace.write('recorder_boundary', mode=mode)
        self.mode = mode
        for bridge in self.bridges.values(): self._configure_bridge(bridge)
        self._visit(boundary=True)

    def drain(self, *, force=False):
        result = self._visit(collect=True)
        return self._operations(result, force=force)

    def _operations(self, events, force=False):
        causal = [e.get('window_context', {}).get('handle') for e in events if e['type'] in {'click','dblclick','key'} and e.get('window_context',{}).get('handle') in self.windows.alive]
        sources=set(causal)
        self.windows.observe(cause=next(iter(sources)) if len(sources)==1 else None)
        operations = self.normalizer.consume(events) + self.normalizer.flush(force=force)
        result = []
        for op in operations:
            handle = op.handle
            if handle and handle != self.windows.active:
                if op.action == 'pick':
                    self.driver.switch_to.window(handle)
                elif self.windows.active not in self.windows.alive and self.windows.parents.get(self.windows.active)==handle:
                    pass  # Player returns automatically after that popup closes.
                elif self.windows.parents.get(self.windows.active) == handle:
                    result.append(Operation('switch_window', data={'to':'parent'}, handle=handle))
                elif self.windows.order and self.windows.order[-1] == handle:
                    result.append(Operation('switch_window', data={'to':'newest'}, handle=handle))
                else:
                    raise UnsupportedOperationError('window switch cannot be represented as newest or parent')
                self.windows.active = handle
            result.append(op)
            self.trace.operation('transport_operation', op)
        return result

    def stop(self):
        result = self._visit(collect=True, flush=True)
        self.mode = "observe"
        for bridge in self.bridges.values(): self._configure_bridge(bridge)
        return self._operations(result, force=True)

    def close(self):
        for bridge in self.bridges.values():
            try: bridge.close()
            except Exception: pass
        self.bridges.clear()

    def reset(self):
        """Explicitly discard an uncertain interval before a new start boundary."""
        self.mode='observe'
        self._visit(reset=True)
        for bridge in self.bridges.values():
            bridge.navigation.reset()
            with bridge.lock:
                bridge.events=[];bridge.overflow=False;bridge.invalid=False
            self._configure_bridge(bridge)
        self.normalizer=EventNormalizer()
        self.windows=WindowContext(self.driver)
