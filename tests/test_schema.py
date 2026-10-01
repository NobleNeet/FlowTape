import pytest

from flowtape import schema
from flowtape.errors import ScenarioValidationError
from flowtape.recorder import EventNormalizer, propose_target
from flowtape.player import OutputManager, Player, Value
from flowtape.errors import CredentialOutputForbidden, OutputSchemaMismatch


def test_strict_schema_and_clarifications(tmp_path):
    valid = {"version": 1, "name": "確認", "steps": [{"action": "click", "target": "保存"}]}
    assert schema.scenario(valid) == valid
    with pytest.raises(ScenarioValidationError, match="unknown fields"):
        schema.scenario({**valid, "typo": True})
    with pytest.raises(ScenarioValidationError, match="unsupported v1 relative relation"):
        schema.elements({"version": 1, "pages": {"p": {
            "identify": {"url": {"contains": "x"}},
            "elements": {"x": {"kind": "button", "locate": [{"by": "relative", "anchor": {"text": "x"}, "relation": "section", "target": {"role": "button"}}]}}
        }}})
    with pytest.raises(ScenarioValidationError, match="output file must stay"):
        schema.scenario({"version": 1, "name": "x", "outputs": {"o": {"format": "text", "file": "../outside"}}, "steps": []})
    with pytest.raises(ScenarioValidationError, match="frame requires exactly one"):
        schema.elements({"version": 1, "pages": {"p": {
            "identify": {"url": {"contains": "x"}},
            "elements": {"x": {"kind": "button", "context": [{"frame": {"id": "x", "name": "y"}}], "locate": [{"by": "id", "value": "x"}]}}
        }}})


def test_recorder_normalization_and_dynamic_id():
    normalizer = EventNormalizer()
    base = {"protocol_version": 1, "document_instance_id": "doc", "target": {"snapshot": {"tag": "button"}}}
    assert normalizer.consume([{**base, "event_seq": 1, "type": "click"}], now=0) == []
    assert normalizer.consume([{**base, "event_seq": 2, "type": "dblclick"}], now=.1)[0].action == "double_click"
    assert normalizer.flush(now=1) == []
    singles = EventNormalizer()
    assert singles.consume([{**base, "event_seq": 1, "type": "click"}, {**base, "event_seq": 2, "type": "click"}], now=0) == []
    assert [x.action for x in singles.flush(now=1)] == ["click", "click"]
    snap = {"tag": "button", "role": "button", "name": "保存", "attributes": {"id": "99999999", "data-testid": "save"}}
    locators = propose_target(snap)["locate"]
    assert locators[0] == {"by": "testid", "value": "save"}
    assert not any(x["by"] == "id" for x in locators)


def test_config_defaults_and_variable_types(tmp_path):
    cfg = schema.config({"version": 1, "driver": {"path": "/tmp/msedgedriver"}}, tmp_path / "config.yaml")
    assert cfg["safety"]["destructive_confirmation"] == "always"
    assert cfg["paths"]["outputs"] == str(tmp_path / "outputs")
    with pytest.raises(ScenarioValidationError):
        schema.scenario({"version": 1, "name": "x", "variables": {"foo-bar": 1}, "steps": []})


def test_output_lifecycle_types_and_secret(tmp_path):
    definition = {"version": 1, "name": "結果", "outputs": {
        "csv": {"format": "csv", "file": "results.csv", "existing": "append", "columns": ["a", "b"]},
        "json": {"format": "jsonl", "file": "records.jsonl"},
    }, "steps": []}
    writer = OutputManager(definition, tmp_path, write=True)
    writer.append("csv", {"a": Value(3), "b": Value(None)})
    writer.append("json", {"a": Value(3), "b": Value(True)})
    assert (tmp_path / "results.csv").read_text().splitlines() == ["a,b", "3,"]
    assert '"a": 3, "b": true' in next(tmp_path.rglob("records.jsonl")).read_text()
    with pytest.raises(CredentialOutputForbidden):
        writer.append("json", {"password": Value("secret", True)})
    (tmp_path / "results.csv").write_text("wrong\n", encoding="utf-8")
    with pytest.raises(OutputSchemaMismatch):
        writer.append("csv", {"a": Value(1), "b": Value(2)})


def test_cross_file_validation():
    registry = schema.elements({"version": 1, "pages": {"p": {"identify": {"url": {"contains": "site"}},
        "elements": {"保存": {"kind": "button", "locate": [{"by": "id", "value": "save"}]}}}}})
    doc = schema.scenario({"version": 1, "name": "x", "steps": [{"action": "input", "target": "保存", "value": "x"}]})
    with pytest.raises(ScenarioValidationError, match="incompatible"):
        schema.validate_package(doc, registry)


def test_optional_null_and_secret_variable_propagation(tmp_path):
    doc = schema.scenario({"version": 1, "name": "x", "mode": None,
        "variables": {"password_copy": "${credential.group.password}"}, "steps": []})
    assert "mode" not in doc
    class Driver:
        window_handles = []
    cfg = schema.config({"version": 1, "driver": {"path": "/tmp/msedgedriver"},
                         "paths": {"outputs": str(tmp_path), "downloads": str(tmp_path)}}, tmp_path / "config.yaml")
    player = Player(Driver(), doc, {"version": 1, "pages": {}}, cfg,
                    {"credentials": {"group": {"password": "private"}}})
    expanded = player.expand("prefix-${password_copy}")
    assert expanded.secret and expanded.data == "prefix-private"
    with pytest.raises(CredentialOutputForbidden):
        OutputManager({"name": "x", "outputs": {"log": {"format": "text", "file": "x"}}}, tmp_path, write=False).append("log", expanded)


def test_duplicate_yaml_keys_are_rejected_without_values(tmp_path):
    path = tmp_path / "credentials.yaml"
    path.write_text("version: 1\ncredentials:\n  group:\n    password: private\n    password: other\n", encoding="utf-8")
    with pytest.raises(ScenarioValidationError, match="YAML parse failed at line 5") as exc:
        schema.load_yaml(path)
    assert "private" not in str(exc.value)
    assert "other" not in str(exc.value)


def test_node_identity_and_loop_namespace_validation():
    from flowtape.identity import ulid
    identity=ulid()
    base={'version':1,'name':'identity','steps':[{'action':'back','_meta':{'id':identity}}]}
    schema.scenario(base)
    with pytest.raises(ScenarioValidationError,match='duplicate node identity'):
        schema.scenario(dict(base,steps=base['steps']*2))
    with pytest.raises(ScenarioValidationError,match='canonical ULID'):
        schema.scenario(dict(base,steps=[{'action':'back','_meta':{'id':'not-a-ulid'}}]))
    with pytest.raises(ScenarioValidationError,match='collides'):
        schema.scenario({'version':1,'name':'scope','steps':[{'for_each':{'target':'rows','as':'row','steps':[{'action':'read','target':'cell','source':'text','into':'row'}]}}]})
    with pytest.raises(ScenarioValidationError,match='unsupported mode'):
        schema.scenario(dict(base,mode=[]))


def test_recorder_requires_contiguous_event_sequences():
    from flowtape.errors import FlowTapeError
    normalizer=EventNormalizer()
    event={'protocol_version':1,'document_instance_id':'doc','event_seq':1,'type':'history','target':None}
    normalizer.consume([event])
    with pytest.raises(FlowTapeError,match='sequence gap'):
        normalizer.consume([dict(event,event_seq=3)])


def test_diagnostic_logs_obey_level_and_redact_credentials(tmp_path):
    from flowtape.runlog import RunLog
    cfg=schema.config({'version':1,'driver':{'path':'/tmp/driver'},'logging':{'level':'INFO'}},tmp_path/'config.yaml')
    outputs=OutputManager({'name':'diagnostics','outputs':{}},tmp_path/'outputs',write=False)
    log=RunLog(cfg,outputs,{'group':{'password':'private-value'}})
    log.write('DEBUG','target_resolution',target='hidden debug record')
    assert not log.path.exists()
    log.write('ERROR','step_failed',reason='private-value must be hidden')
    text=log.path.read_text()
    assert 'private-value' not in text and '[REDACTED]' in text
    assert 'hidden debug record' not in text


@pytest.mark.parametrize('fields', [
    {'value': 'Red'}, {'values': ['Red', 'Blue']}, {'values': []},
    {'values': ['${choice}', 2, True]},
])
def test_select_schema_compatible_scalar_and_complete_set(fields):
    schema.scenario({'version': 1, 'name': 'select', 'steps': [
        {'action': 'select', 'target': '色', **fields}]})


@pytest.mark.parametrize('fields', [
    {}, {'value': 'Red', 'values': ['Blue']}, {'values': 'Red'},
    {'values': [None]}, {'values': [['Red']]}, {'values': ['${bad-name}']},
    {'value': ['Red', 'Blue']},
])
def test_select_schema_rejects_invalid_selection(fields):
    with pytest.raises(ScenarioValidationError):
        schema.scenario({'version': 1, 'name': 'select', 'steps': [
            {'action': 'select', 'target': '色', **fields}]})


def test_event_normalizer_keeps_each_source_identity_with_identical_snapshots():
    snap = {'tag': 'select', 'shadow_path': []}
    base = {'protocol_version': 1, 'document_instance_id': 'doc', 'type': 'select',
            'document': {'url': 'https://test/'}, 'window_context': {'handle': 'window', 'frame_path': []}}
    events = [base | {'event_seq': index, 'target': {'snapshot': snap, 'element_ref': index},
                      'data': {'text': value}} for index, value in enumerate(['A', 'B'], 1)]
    operations = EventNormalizer().consume(events)
    assert [(op.value, op.document_id, op.element_ref, op.event_seq) for op in operations] == [
        ('A', 'doc', 1, 1), ('B', 'doc', 2, 2)]


def test_recorder_trace_never_persists_capture_payload(tmp_path):
    import json
    from flowtape.recorder_trace import RecorderTrace
    trace = RecorderTrace(tmp_path / 'trace.jsonl')
    trace.write('observer_input', tag='input', input_type='password', trusted=True,
                value='secret', snapshot={'value': 'secret'}, url='https://private/', name='secret')
    trace.event('transport_merged', {'document_instance_id': 'doc', 'event_seq': 1, 'type': 'input_commit',
                                   'target': {'snapshot': {'name': 'secret'}}, 'data': {'value': 'secret'}})
    content = trace.path.read_text()
    assert 'secret' not in content and 'private' not in content
    rows = [json.loads(line) for line in content.splitlines()]
    assert rows[0]['trusted'] is True and rows[1]['event_seq'] == 1
    assert RecorderTrace().write('disabled') is None


def test_source_capture_requires_stable_proven_candidate_and_matching_document():
    from flowtape.recorder import Operation, captured_target
    snapshot = {'tag': 'a', 'role': 'link', 'name': '次へ', 'attributes': {'id': '99999999'},
                'capture': {'document_id': 'source', 'locate': [{'by': 'id', 'value': '99999999'}]}}
    op = Operation('click', snapshot=snapshot, document_id='source')
    assert captured_target(op) is None  # Source uniqueness does not make dynamic IDs stable.
    snapshot['capture']['locate'].append({'by': 'role', 'role': 'link', 'name': '次へ'})
    assert captured_target(op)['locate'] == [{'by': 'role', 'role': 'link', 'name': '次へ'}]
    op.document_id = 'other'
    assert captured_target(op) is None
    op.document_id = 'source'
    op.context = [{'shadow': {'css': '#unverified'}}]
    assert captured_target(op) is None


def test_recorder_trace_merges_browser_delivery_copies(tmp_path):
    from flowtape.recorder_trace import RecorderTrace
    trace = RecorderTrace(tmp_path / 'trace.jsonl')
    data = {'stage': 'observer_input', 'document_id': 'doc', 'trace_seq': 1, 'event_seq': 0,
            'type': 'input', 'trusted': True, 'value': 'secret'}
    trace.browser(data)
    trace.browser(data)
    assert len(trace.path.read_text().splitlines()) == 1
    assert 'secret' not in trace.path.read_text()
    trace.browser(data | {'stage': 'invalid'})
    assert len(trace.path.read_text().splitlines()) == 1
