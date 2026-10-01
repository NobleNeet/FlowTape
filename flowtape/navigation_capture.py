"""Classify committed browser-initiated navigation, independent of page DOM.

Notifications are supplied in WebSocket wire order. Renderer requests (links,
forms, scripts) explain their own navigation and must not become extra opens.
URLs live in memory until they become an ordinary semantic scenario field.
"""

from threading import Lock
from time import time
from uuid import uuid4

from .errors import FlowTapeError


class NavigationCapture:
    def __init__(self, handle, trace):
        self.handle = handle
        self.trace = trace
        self.frame_id = None
        self.mode = 'observe'
        self.suppressed = False
        self.requested_url = None
        self.pending = None
        self.events = []
        self.overflow = False
        self.lock = Lock()

    def set_mode(self, mode):
        with self.lock:
            if mode != self.mode:
                self.pending = self.requested_url = None
            self.mode = mode

    def receive(self, method, data):
        with self.lock:
            frame = data.get('frame', {})
            identity = frame.get('id') if method == 'Page.frameNavigated' else data.get('frameId')
            if not self.handle or identity != self.frame_id:
                return
            if method == 'Page.frameRequestedNavigation':
                self.requested_url = data.get('url')
            elif method == 'Page.frameStartedNavigating':
                renderer = self.requested_url == data.get('url')
                self.requested_url = None
                if self.pending and self.pending['loader'] == data.get('loaderId'):
                    return  # Redirects retain the original entered URL.
                self.pending = {'loader': data.get('loaderId'), 'url': data.get('url'),
                                'type': data.get('navigationType'), 'renderer': renderer,
                                'record': self.mode == 'record' and not self.suppressed}
                self.trace.write('navigation_started', type=self.pending['type'], mode=self.mode,
                                 reason='renderer' if renderer else 'browser')
            elif method == 'Page.frameNavigated':
                pending, self.pending = self.pending, None
                if not pending or pending['loader'] != frame.get('loaderId') or not pending['record']:
                    return
                if pending['renderer']:
                    self.trace.write('navigation_ignored', reason='renderer_navigation')
                    return
                if pending['type'] != 'differentDocument':
                    self.trace.write('navigation_ignored', reason='unclassified_navigation', type=pending['type'])
                    return
                if not pending['url'] or frame.get('unreachableUrl'):
                    self.trace.write('navigation_ignored', reason='failed_navigation')
                    return
                if len(self.events) >= 1000:
                    self.overflow = True
                    return
                event = {'protocol_version': 1, 'document_instance_id': 'navigation-' + uuid4().hex,
                         'event_seq': 1, 'timestamp': time() * 1000, 'type': 'navigation',
                         'window_context': {'handle': self.handle, 'frame_path': []},
                         'document': {'url': frame.get('url')}, 'target': None,
                         'data': {'action': 'open', 'url': pending['url']}}
                self.events.append(event)
                self.trace.event('navigation_committed', event, action='open')

    def drain(self):
        with self.lock:
            if self.overflow:
                raise FlowTapeError('Recorder navigation queue overflow; recording desynchronized')
            events, self.events = self.events, []
            return events

    def reset(self):
        with self.lock:
            self.events.clear()
            self.pending = self.requested_url = None
            self.overflow = False
