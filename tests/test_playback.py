import copy
from threading import Thread
from time import sleep

import pytest

from flowtape.errors import FlowTapeError, TargetNotFound
from flowtape.playback import PlaybackController
from flowtape.player import Player
from flowtape.schema import config


class Driver:
    window_handles = ["main"]
    current_window_handle = "main"
    def __init__(self):
        self.actions = []
        self.switch_to = self
    def window(self, handle): self.current_window_handle = handle
    def back(self): self.actions.append("back")
    def forward(self): self.actions.append("forward")
    def refresh(self): self.actions.append("refresh")


def make_player(tmp_path, steps):
    cfg = config({"version": 1, "driver": {"path": "/tmp/driver"}}, tmp_path / "config.yaml")
    return Player(Driver(), {"version": 1, "name": "test", "steps": steps}, {"pages": {}}, cfg)


def action(name, identity): return {"action": name, "_meta": {"id": identity}}


def test_step_until_retry_skip_and_edits(tmp_path):
    player = make_player(tmp_path, [{"repeat": {"count": 2, "steps": [action("back", "child")]}, "_meta": {"id": "loop"}}, action("forward", "last")])
    control = PlaybackController(player)
    assert control.execute(max_actions=1) == "paused"
    assert player.driver.actions == ["back"]
    assert control.execute(until_id="last") == "paused"
    assert player.driver.actions == ["back", "back"]
    trial = copy.deepcopy(player.scenario)
    trial["steps"][1]["action"] = "refresh"
    control.replace_scenario(trial)
    assert control.execute() == "complete"
    assert player.driver.actions == ["back", "back", "refresh"]

    player = make_player(tmp_path, [action("back", "fail"), action("forward", "later")])
    original = player.perform
    def fail_once(node): raise TargetNotFound("missing")
    player.perform = fail_once
    control = PlaybackController(player)
    assert control.execute() == "failed"
    assert control.current["_meta"]["id"] == "fail"
    player.perform = original
    assert control.execute() == "complete"
    assert player.driver.actions == ["back", "forward"]


def test_executed_edits_require_explicit_choice(tmp_path):
    player = make_player(tmp_path, [action("back", "past"), action("forward", "future")])
    control = PlaybackController(player)
    control.execute(max_actions=1)
    trial = copy.deepcopy(player.scenario)
    trial["steps"][0]["action"] = "refresh"
    with pytest.raises(FlowTapeError, match="executed steps changed"):
        control.replace_scenario(trial)
    control.replace_scenario(trial, allow_executed=True)
    control.execute()
    assert player.driver.actions == ["back", "forward"]


def test_new_future_steps_execute_and_past_insertions_need_choice(tmp_path):
    player = make_player(tmp_path,[action('back','past'),action('forward','future')])
    control = PlaybackController(player)
    control.execute(max_actions=1)
    trial=copy.deepcopy(player.scenario)
    trial['steps'].insert(1,action('refresh','new'))
    control.replace_scenario(trial)
    control.execute()
    assert player.driver.actions==['back','refresh','forward']
    player=make_player(tmp_path,[action('back','past'),action('forward','future')])
    control=PlaybackController(player)
    control.execute(max_actions=1)
    trial=copy.deepcopy(player.scenario)
    trial['steps'].insert(0,action('refresh','new'))
    with pytest.raises(FlowTapeError,match='before the execution boundary changed'):
        control.replace_scenario(trial)


def test_stop_unwinds_true_while_and_wait_pause(tmp_path):
    player = make_player(tmp_path, [{"while": {"exists": "x", "steps": []}, "_meta": {"id": "loop"}}])
    player.condition = lambda condition: True
    control = PlaybackController(player)
    control.pause()
    control.stop()
    assert control.execute() == "stopped"

    player = make_player(tmp_path, [{"action": "wait", "until": {"exists": "x"}, "timeout": "200ms", "_meta": {"id": "wait"}}])
    ready = False
    player.condition = lambda condition: ready
    control = PlaybackController(player)
    thread = Thread(target=control.execute)
    thread.start()
    sleep(.02)
    control.pause()
    sleep(.3)
    ready = True
    control.resume()
    thread.join(2)
    assert not thread.is_alive() and control.state == "complete"
