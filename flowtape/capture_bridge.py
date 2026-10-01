"""Edge DevTools transport: keep navigation events in Python memory, never disk.

The protocol queue remains available for polling and de-duplication. A binding
delivers Stage 1 evidence before the source document is destroyed.
"""

import json
from threading import Lock

from selenium.webdriver.common.bidi.cdp import import_devtools
from selenium.webdriver.remote.websocket_connection import WebSocketConnection

from .errors import FlowTapeError
from .recorder_trace import RecorderTrace
from .navigation_capture import NavigationCapture


class CaptureConnection(WebSocketConnection):
    """Keep navigation lifecycle order before Selenium dispatches callbacks.

    Selenium dispatches each callback on its own thread. Lifecycle causality
    cannot rely on those threads completing in notification order. This sink
    never executes CDP commands or Selenium calls from the receiving thread.
    """
    def __init__(self, *args, navigation, **kwargs):
        self.navigation = navigation
        self.binding_receiver = None
        self.detached = False
        super().__init__(*args, **kwargs)

    def _process_message(self, message):
        notification = json.loads(message)
        method = notification.get('method')
        if method == 'Runtime.bindingCalled' and self.binding_receiver is not None and notification['params'].get('name') in {'__flowtape_emit', '__flowtape_trace'}:
            # A source-document event must be ingested before the following
            # navigation commit, rather than scheduled on an independent thread.
            self.binding_receiver(notification['params'])
            return
        if method == 'Target.detachedFromTarget' and notification['params'].get('sessionId') == self.session_id:
            self.detached = True
        if method in {'Page.frameRequestedNavigation', 'Page.frameStartedNavigating', 'Page.frameNavigated'}:
            self.navigation.receive(method, notification['params'])
        super()._process_message(message)


class CaptureBridge:
    def __init__(self, driver, handle, target_id=None, trace=None):
        self.trace = trace or RecorderTrace()
        # Selenium's version discovery is isolated here; the application still
        # exclusively uses the configured external WebDriver executable.
        version, endpoint = driver._get_cdp_details()
        self.protocol = import_devtools(version.split('.')[0])
        cfg = driver.command_executor.client_config
        self.navigation = NavigationCapture(handle, self.trace)
        self.connection = CaptureConnection(endpoint, cfg.websocket_timeout, cfg.websocket_interval, navigation=self.navigation)
        self.handle = handle
        self.target_id = target_id or handle
        self.events = []
        self.lock = Lock()
        self.overflow = False
        self.invalid = False
        self.script_id = None
        self.connection.session_id = self.connection.execute(
            self.protocol.target.attach_to_target(self.protocol.target.TargetID(target_id or handle), True))
        self.connection.execute(self.protocol.page.enable())
        tree = self.connection.execute(self.protocol.page.get_frame_tree())
        self.navigation.frame_id = str(tree.frame.id_)
        self.callback = self.connection.add_callback(self.protocol.runtime.BindingCalled, self.receive)
        self.connection.binding_receiver = lambda data: self.receive(self.protocol.runtime.BindingCalled.from_json(data))
        self.connection.execute(self.protocol.runtime.enable())
        self.connection.execute(self.protocol.runtime.add_binding('__flowtape_emit'))
        if self.trace.enabled:
            self.connection.execute(self.protocol.runtime.add_binding('__flowtape_trace'))

    def receive(self, notification):
        if notification.name == '__flowtape_trace':
            try:
                data = json.loads(notification.payload)
                self.trace.browser(data)
            except (ValueError, TypeError, KeyError, AttributeError):
                self.trace.write('trace_invalid')
            return
        if notification.name != '__flowtape_emit': return
        try: event = json.loads(notification.payload)
        except (ValueError, TypeError):
            self.invalid = True
            return
        if not isinstance(event,dict) or event.get('protocol_version')!=1 or not isinstance(event.get('window_context'),dict):
            self.invalid = True
            return
        event.setdefault('window_context', {})['handle'] = self.handle
        self.trace.event('cdp_binding', event)
        with self.lock:
            if len(self.events) >= 1000:
                self.overflow = True
            else:
                self.events.append(event)

    def configure(self, script):
        if self.connection.detached: return
        if self.script_id is not None:
            self.connection.execute(self.protocol.page.remove_script_to_evaluate_on_new_document(self.script_id))
        self.script_id = self.connection.execute(self.protocol.page.add_script_to_evaluate_on_new_document(script))

    def drain(self):
        with self.lock:
            if self.overflow: raise FlowTapeError('Recorder transport overflow; recording desynchronized')
            if self.invalid: raise FlowTapeError('Recorder transport received an invalid protocol event')
            result, self.events = self.events, []
        result.extend(self.navigation.drain())
        for event in result:
            self.trace.event('cdp_drain', event)
        return result

    def close(self):
        try:
            if self.script_id is not None and not self.connection.detached:
                self.connection.execute(self.protocol.page.remove_script_to_evaluate_on_new_document(self.script_id))
            if not self.connection.detached:
                self.connection.execute(self.protocol.runtime.remove_binding('__flowtape_emit'))
                if self.trace.enabled:
                    self.connection.execute(self.protocol.runtime.remove_binding('__flowtape_trace'))
        finally:
            self.connection.remove_callback(self.protocol.runtime.BindingCalled, self.callback)
            self.connection.close()
