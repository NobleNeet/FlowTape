"""Edge DevTools transport: keep navigation events in Python memory, never disk.

The protocol queue remains available for polling and de-duplication. A binding
delivers Stage 1 evidence before the source document is destroyed.
"""

import json
from threading import Lock

from selenium.webdriver.common.bidi.cdp import import_devtools
from selenium.webdriver.remote.websocket_connection import WebSocketConnection

from .errors import FlowTapeError


class CaptureBridge:
    def __init__(self, driver, handle, target_id=None):
        # Selenium's version discovery is isolated here; the application still
        # exclusively uses the configured external WebDriver executable.
        version, endpoint = driver._get_cdp_details()
        self.protocol = import_devtools(version.split('.')[0])
        cfg = driver.command_executor.client_config
        self.connection = WebSocketConnection(endpoint, cfg.websocket_timeout, cfg.websocket_interval)
        self.handle = handle
        self.events = []
        self.lock = Lock()
        self.overflow = False
        self.invalid = False
        self.script_id = None
        self.connection.session_id = self.connection.execute(
            self.protocol.target.attach_to_target(self.protocol.target.TargetID(target_id or handle), True))
        self.callback = self.connection.add_callback(self.protocol.runtime.BindingCalled, self.receive)
        self.connection.execute(self.protocol.runtime.enable())
        self.connection.execute(self.protocol.runtime.add_binding('__flowtape_emit'))

    def receive(self, notification):
        if notification.name != '__flowtape_emit': return
        try: event = json.loads(notification.payload)
        except (ValueError, TypeError):
            self.invalid = True
            return
        if not isinstance(event,dict) or event.get('protocol_version')!=1 or not isinstance(event.get('window_context'),dict):
            self.invalid = True
            return
        event.setdefault('window_context', {})['handle'] = self.handle
        with self.lock:
            if len(self.events) >= 1000:
                self.overflow = True
            else:
                self.events.append(event)

    def configure(self, script):
        if self.script_id is not None:
            self.connection.execute(self.protocol.page.remove_script_to_evaluate_on_new_document(self.script_id))
        self.script_id = self.connection.execute(self.protocol.page.add_script_to_evaluate_on_new_document(script))

    def drain(self):
        with self.lock:
            if self.overflow: raise FlowTapeError('Recorder transport overflow; recording desynchronized')
            if self.invalid: raise FlowTapeError('Recorder transport received an invalid protocol event')
            result, self.events = self.events, []
        return result

    def close(self):
        try:
            if self.script_id is not None:
                self.connection.execute(self.protocol.page.remove_script_to_evaluate_on_new_document(self.script_id))
            self.connection.execute(self.protocol.runtime.remove_binding('__flowtape_emit'))
        finally:
            self.connection.remove_callback(self.protocol.runtime.BindingCalled, self.callback)
            self.connection.close()
