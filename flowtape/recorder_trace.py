"""Opt-in, value-free Recorder pipeline diagnostics.

No URL, accessible name, input value, DOM snapshot or credential is accepted.
The allowlist is also applied to browser/CDP-originated diagnostics.
"""

import json
import os
from pathlib import Path
from threading import Lock
from time import monotonic
from collections import deque


FIELDS = {'document_id', 'event_seq', 'type', 'action', 'mode', 'trusted',
          'tag', 'input_type', 'count', 'reason', 'step_id', 'queue_size',
          'binding', 'frame_depth', 'session', 'stage', 'trace_seq'}
OBSERVER_STAGES = {'observer_input', 'observer_emit', 'observer_delivery', 'observer_mode', 'observer_filter'}


class RecorderTrace:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = Lock()
        self.error = None
        self.browser_ids = set()
        self.browser_order = deque()

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get('FLOWTAPE_RECORDER_TRACE'))

    @property
    def enabled(self):
        return self.path is not None

    def write(self, stage, **fields):
        if not self.enabled:
            return
        record = {key: value for key, value in fields.items() if key in FIELDS
                  and isinstance(value, (str, int, float, bool, type(None)))}
        record.update(stage=stage, time=monotonic())
        try:
            with self.lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        except OSError as exc:
            self.error = type(exc).__name__

    def event(self, stage, event, **fields):
        self.write(stage, document_id=event.get('document_instance_id'),
                   event_seq=event.get('event_seq'), type=event.get('type'), **fields)

    def browser(self, data):
        """Merge optional CDP and polling diagnostic copies by trace identity."""
        if not self.enabled or not isinstance(data, dict) or data.get('stage') not in OBSERVER_STAGES:
            return
        identity = (data.get('document_id'), data.get('trace_seq'))
        if not isinstance(identity[0], str) or type(identity[1]) is not int:
            return
        with self.lock:
            if identity in self.browser_ids:
                return
            self.browser_ids.add(identity)
            self.browser_order.append(identity)
            if len(self.browser_order) > 10000:
                self.browser_ids.remove(self.browser_order.popleft())
        self.write(data['stage'], **{key: value for key, value in data.items() if key != 'stage'})

    def operation(self, stage, op, **fields):
        self.write(stage, document_id=op.document_id, event_seq=op.event_seq,
                   action=op.action, **fields)
