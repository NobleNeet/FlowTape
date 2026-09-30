"""Resumable execution cursor and cooperative playback controls."""

from dataclasses import dataclass
from threading import Condition
from time import monotonic

from .errors import ActionCompatibilityError, FlowTapeError, LoopLimitExceeded, PlaybackStopped


@dataclass
class Sequence:
    steps: list
    index: int = 0
    cleanup: object = None


@dataclass
class Loop:
    node: dict
    kind: str
    count: int = 0
    deadline: float | None = None
    refs: list | None = None


class PlaybackController:
    def __init__(self, player):
        self.player = player
        self.stack = [Sequence(player.scenario["steps"])]
        self.current = None
        self.error = None
        self.state = "ready"
        self.executed_ids = set()
        self._condition = Condition()
        self._paused = False
        self._stopped = False
        self.action_budget = None
        self.until_id = None
        self.in_action = False
        player.checkpoint = self.checkpoint
        player.resolver.checkpoint = self.checkpoint

    def pause(self):
        with self._condition:
            self._paused = True

    def resume(self):
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def stop(self):
        with self._condition:
            self._stopped = True
            self.player.stop_requested = True
            self.state = "stopped"
            self._condition.notify_all()

    def checkpoint(self):
        start = monotonic()
        paused = False
        with self._condition:
            while self._paused and not self._stopped:
                paused = True
                self.state = "paused"
                self._condition.wait(.1)
            if self._stopped:
                raise PlaybackStopped("playback stopped")
        elapsed = monotonic() - start if paused else 0
        for frame in self.stack:
            if isinstance(frame, Loop) and frame.deadline is not None:
                frame.deadline += elapsed
        if paused:
            self.state = "running"
        return elapsed

    def _next(self):
        while self.stack:
            self.checkpoint()
            frame = self.stack[-1]
            if isinstance(frame, Sequence):
                if frame.index >= len(frame.steps):
                    self.stack.pop()
                    if frame.cleanup:
                        frame.cleanup()
                    continue
                node = frame.steps[frame.index]
                if node.get("enabled", True) is False:
                    frame.index += 1
                    continue
                self.current = node
                return node
            node, kind = frame.node, frame.kind
            self.current = node
            body = node[kind]
            if kind == "repeat":
                active = frame.count < body["count"]
            elif kind == "while":
                cond = {k: v for k, v in body.items() if k not in {"steps", "timeout", "max_iterations"}}
                active = self.player.condition(cond)
                if active and (frame.count >= body.get("max_iterations", self.player.config["loops"]["max_iterations"]) or monotonic() >= frame.deadline):
                    raise LoopLimitExceeded("while safety limit reached")
            else:
                active = frame.count < len(frame.refs)
            if not active:
                self.stack.pop()
                self.current = None
                continue
            cleanup = None
            if kind == "for_each":
                from .player import Value
                name = body["as"]
                ref = frame.refs[frame.count]
                self.player._member(ref)
                if name in self.player.variables or name in self.player.runtime or name in self.player.loop_vars:
                    raise FlowTapeError(f"loop variable {name} collides with an existing variable")
                self.player.loop_vars[name] = Value(ref)
                cleanup = lambda name=name: self.player.loop_vars.pop(name, None)
            frame.count += 1
            self.stack.append(Sequence(body["steps"], cleanup=cleanup))
        self.current = None
        return None

    def _enter(self, node):
        from .browser import seconds
        from .player import MemberRef
        frame = self.stack[-1]
        if "if" in node:
            children = node["then"] if self.player.condition(node["if"]) else node.get("else", [])
            new_frame = Sequence(children)
        else:
            kind = next(k for k in ("repeat", "while", "for_each") if k in node)
            body = node[kind]
            new_frame = Loop(node, kind)
            if kind == "while":
                new_frame.deadline = monotonic() + seconds(body.get("timeout", self.player.config["loops"]["timeout"]))
            elif kind == "for_each":
                page = self.player.resolver.identify()
                members = self.player.resolver.collection(body["target"])
                new_frame.refs = [MemberRef(body["target"], page, self.player.resolver.js("return FT.snapshot(arguments[0]);", el)) for el in members]
        frame.index += 1
        self.stack.append(new_frame)
        self.current = None
        identity = node.get("_meta", {}).get("id")
        if identity:
            self.executed_ids.add(identity)

    def replace_scenario(self, document, *, allow_executed=False):
        from .editor import node_map, own_content, sequences
        if self.state not in {"paused", "failed", "ready"}:
            raise FlowTapeError("pause playback before editing")
        for field in ('mode','variables','outputs'):
            if document.get(field) != self.player.scenario.get(field):
                raise FlowTapeError(f'{field} changed; restart playback to initialize the run')
        old_nodes = node_map(self.player.scenario)
        new_nodes = node_map(document)
        if self.in_action and self.current is not None:
            identity = self.current.get('_meta',{}).get('id')
            if identity not in new_nodes or own_content(self.current) != own_content(new_nodes[identity]):
                raise FlowTapeError('the current action is still in progress; stop and restart before changing it')
        modified = [identity for identity in self.executed_ids if identity not in new_nodes or own_content(old_nodes[identity]) != own_content(new_nodes[identity])]
        if modified and not allow_executed:
            raise FlowTapeError("executed steps changed; restart or explicitly continue from current browser state")
        old_sequences = sequences(self.player.scenario)
        new_sequences = sequences(document)
        replacements = []
        for frame in self.stack:
            if isinstance(frame, Sequence):
                key = next((key for key, steps in old_sequences.items() if steps is frame.steps), None)
                if key not in new_sequences:
                    raise FlowTapeError("active block removed; restart playback")
                steps = new_sequences[key]
                if frame.index:
                    previous_id = frame.steps[frame.index-1].get('_meta',{}).get('id')
                    indices = [i for i,node in enumerate(steps) if node.get('_meta',{}).get('id')==previous_id]
                    if len(indices) != 1:
                        raise FlowTapeError('execution boundary removed or moved out of its block; restart playback')
                    index = indices[0]+1
                    old_prefix = [node.get('_meta',{}).get('id') for node in frame.steps[:frame.index]]
                    new_prefix = [node.get('_meta',{}).get('id') for node in steps[:index]]
                    if old_prefix != new_prefix and not allow_executed:
                        raise FlowTapeError('steps before the execution boundary changed; restart or explicitly continue from current browser state')
                else:
                    index = 0
                if self.in_action and frame is self.stack[-1]:
                    current_id = self.current.get('_meta',{}).get('id')
                    if index >= len(steps) or steps[index].get('_meta',{}).get('id') != current_id:
                        raise FlowTapeError('the current action is still in progress; restart before inserting ahead of it')
                replacements.append((frame, steps, index))
            elif frame.node.get("_meta", {}).get("id") not in new_nodes:
                raise FlowTapeError("active loop removed; restart playback")
        for frame, steps, index in replacements:
            frame.steps, frame.index = steps, index
        for frame in self.stack:
            if isinstance(frame, Loop):
                frame.node = new_nodes[frame.node["_meta"]["id"]]
        if self.current is not None:
            top = self.stack[-1] if self.stack else None
            self.current = (top.steps[top.index] if top.index < len(top.steps) else None) if isinstance(top,Sequence) else new_nodes[self.current['_meta']['id']]
        self.player.scenario = document

    def execute(self, *, max_actions=None, until_id=None):
        """Continue the same run; max_actions counts enabled action nodes only."""
        if self.state in {"stopped", "complete"}:
            return self.state
        self.resume()
        self.state = "running"
        self.error = None
        self.action_budget = max_actions
        self.until_id = until_id
        try:
            while True:
                self.checkpoint()
                node = (self.current if self.stack and isinstance(self.stack[-1], Sequence) else None) or self._next()
                if node is None:
                    self.state = "complete"
                    self.player.log.write('INFO','run_complete')
                    return self.state
                self.player.current_node = node
                identity = node.get("_meta", {}).get("id")
                if self.until_id is not None and identity == self.until_id:
                    self.state = "paused"
                    return self.state
                if "action" not in node:
                    self._enter(node)
                    continue
                self.in_action = True
                try: completed = self.player.perform(node)
                finally: self.in_action = False
                if not completed:
                    self.state = "paused"
                    return self.state
                self.stack[-1].index += 1
                self.current = None
                if identity:
                    self.executed_ids.add(identity)
                if self.action_budget is not None:
                    self.action_budget -= 1
                if self.action_budget == 0:
                    self.state = "paused"
                    return self.state
        except PlaybackStopped:
            self.state = "stopped"
            self.player.log.write('INFO','run_stopped')
        except Exception as exc:
            node = self.current or self.player.current_node or {}
            identity = node.get("_meta", {}).get("id", "?")
            action = node.get("action", "structure")
            if isinstance(exc, FlowTapeError):
                self.error = type(exc)(f"step {identity} {action} {node.get('target', '')}: {exc}")
            else:
                self.error = ActionCompatibilityError(f"step {identity} {action}: operation failed ({type(exc).__name__})")
            self.state = "failed"
            self.player.log.write('ERROR','step_failed',step=identity,action=action,category=type(self.error).__name__,reason=str(self.error))
        return self.state

    def skip(self):
        if self.state != "failed" or self.current is None:
            raise FlowTapeError("skip requires a failed node")
        top = self.stack[-1]
        if isinstance(top, Sequence):
            top.index += 1
        else:
            self.stack.pop()
        self.current = None
        self.error = None
        self.state = "paused"
