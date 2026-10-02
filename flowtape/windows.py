"""Deterministic window creation and parent tracking shared by Recorder/Player."""

from .errors import BrowserContextError


class WindowContext:
    def __init__(self, driver):
        self.driver = driver
        self.alive = set(driver.window_handles)
        try:
            self.active = driver.current_window_handle
        except Exception:
            self.active = None
        if self.alive and self.active not in self.alive:
            if len(self.alive) != 1:
                raise BrowserContextError('fresh browser context has no unique current window')
            self.active, = self.alive
            self.driver.switch_to.window(self.active)
        self.order = [self.active] if self.active else []
        self.parents = {}

    def observe(self, cause=None):
        alive = set(self.driver.window_handles)
        new = alive - self.alive
        if len(new) > 1:
            raise BrowserContextError("several windows appeared together; creation order is unknown")
        for handle in new:
            self.order.append(handle)
            if cause is not None and cause in self.alive:
                self.parents[handle] = cause
        self.alive = alive
        return new

    def restore(self):
        self.observe()
        if self.active not in self.alive:
            parent = self.parents.get(self.active)
            if parent not in self.alive:
                raise BrowserContextError("closed window has no known surviving parent")
            self.switch(parent)
        return self.active

    def destination(self, to):
        self.observe()
        if to == "newest":
            candidates = [h for h in self.order if h in self.alive]
            if not candidates:
                raise BrowserContextError("no observed window survives")
            return candidates[-1]
        parent = self.parents.get(self.active)
        if parent not in self.alive:
            raise BrowserContextError("known parent window unavailable")
        return parent

    def switch(self, handle):
        if handle not in self.driver.window_handles:
            raise BrowserContextError("requested window is no longer alive")
        self.driver.switch_to.window(handle)
        self.active = handle

    def close(self):
        current = self.active
        self.driver.close()
        self.observe()
        parent = self.parents.get(current)
        if parent not in self.alive:
            raise BrowserContextError("closed window has no known surviving parent")
        self.switch(parent)
