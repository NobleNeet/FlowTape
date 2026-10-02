import pytest

from flowtape.errors import BrowserContextError
from flowtape.windows import WindowContext


class Driver:
    def __init__(self):
        self.window_handles = ["main"]
        self.current_window_handle = "main"
        self.switch_to = self
    def window(self, handle): self.current_window_handle = handle
    def close(self): self.window_handles.remove(self.current_window_handle)


def test_creation_order_parent_and_auto_return():
    driver = Driver()
    windows = WindowContext(driver)
    driver.window_handles = ["popup", "main"]
    windows.observe(cause="main")
    assert windows.destination("newest") == "popup"
    windows.switch("popup")
    driver.window_handles = ["main"]
    windows.restore()
    assert driver.current_window_handle == "main"
    assert windows.destination("newest") == "main"


def test_unordered_new_windows_and_unknown_parent_fail():
    driver = Driver()
    windows = WindowContext(driver)
    driver.window_handles += ["one", "two"]
    with pytest.raises(BrowserContextError, match="creation order"):
        windows.observe(cause="main")
    driver = Driver()
    windows = WindowContext(driver)
    driver.window_handles = []
    with pytest.raises(BrowserContextError, match="parent"):
        windows.restore()


def test_fresh_context_uses_unique_survivor_after_old_tab_closed():
    driver = Driver()
    driver.current_window_handle = 'closed'
    driver.window_handles = ['blank']
    context = WindowContext(driver)
    assert context.active == driver.current_window_handle == 'blank'
    assert context.order == ['blank'] and context.parents == {}


def test_fresh_context_rejects_ambiguity_and_runtime_does_not_guess_survivor():
    driver = Driver()
    driver.current_window_handle = 'closed'
    driver.window_handles = ['one', 'two']
    with pytest.raises(BrowserContextError, match='unique current window'):
        WindowContext(driver)
    driver = Driver()
    context = WindowContext(driver)
    driver.window_handles = ['unrelated']
    with pytest.raises(BrowserContextError, match='parent'):
        context.restore()
