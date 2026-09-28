"""Qt worker keeps browser execution off the GUI event loop."""

from threading import Event

from PySide6.QtCore import QThread, Signal


class PlaybackWorker(QThread):
    action_completed = Signal(object)
    gate_requested = Signal(object)

    def __init__(self, controller, *, max_actions=None, until_id=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.max_actions = max_actions
        self.until_id = until_id
        self._answer = Event()
        self._accepted = False

    def confirm(self, accepted):
        self._accepted = accepted
        self._answer.set()

    def gate(self, node):
        self._answer.clear()
        self.gate_requested.emit(node)
        while not self._answer.wait(.1):
            if self.controller.player.stop_requested:
                return False
        return self._accepted

    def run(self):
        self.controller.player.before_action = self.gate
        self.controller.player.after_action = self.action_completed.emit
        self.controller.execute(max_actions=self.max_actions, until_id=self.until_id)
