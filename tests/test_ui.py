import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from flowtape.schema import load_yaml, save_yaml
from flowtape.ui import FlowTapeWindow


def test_editor_wrap_undo_save(tmp_path):
    app = QApplication.instance() or QApplication([])
    scenario_path = tmp_path / "scenario.yaml"
    save_yaml(scenario_path, {"version": 1, "name": "UI", "steps": [
        {"action": "back"}, {"action": "forward"}, {"action": "refresh"}
    ]})
    save_yaml(tmp_path / "elements.yaml", {"version": 1, "pages": {}})
    save_yaml(tmp_path / "config.yaml", {"version": 1, "driver": {"path": "/tmp/msedgedriver"}})
    window = FlowTapeWindow(str(scenario_path), str(tmp_path / "config.yaml"), preferences_path=tmp_path/"preferences.json")
    window.step_list.item(0).setSelected(True)
    window.step_list.item(1).setSelected(True)
    with patch("flowtape.ui.QInputDialog.getInt", return_value=(2, True)):
        window.wrap_repeat()
    assert len(window.scenario["steps"]) == 2
    assert window.scenario["steps"][0]["repeat"]["count"] == 2
    window.undo()
    assert len(window.scenario["steps"]) == 3
    window.redo()
    window.save()
    assert load_yaml(scenario_path)["steps"][0]["repeat"]["count"] == 2
    window.close()


def test_nested_insertion_and_external_reload_preserve_undo(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path/'scenario.yaml'
    save_yaml(source, {'version':1,'name':'UI','steps':[{'repeat':{'count':2,'steps':[{'action':'back'},{'action':'forward'}]}},{'action':'refresh'}]})
    save_yaml(tmp_path/'elements.yaml',{'version':1,'pages':{}})
    save_yaml(tmp_path/'config.yaml',{'version':1,'driver':{'path':'/tmp/msedgedriver'}})
    window = FlowTapeWindow(str(source),str(tmp_path/'config.yaml'), preferences_path=tmp_path/'preferences.json')
    window.step_list.setCurrentRow(1)
    parent = window.rows[1][1]
    from flowtape.editor import sequences
    key = next(key for key,steps in sequences(window.scenario).items() if steps is parent)
    window.record_position = (key,1)
    assert window._insert_node({'action':'refresh'},recording=True)
    assert [node['action'] for node in window.scenario['steps'][0]['repeat']['steps']] == ['back','refresh','forward']
    assert window.scenario['steps'][1]['action'] == 'refresh'
    external = {'version':1,'name':'Externally edited','steps':[{'action':'refresh'}]}
    save_yaml(source,external)
    with patch('flowtape.ui.QInputDialog.getItem',return_value=('外部ファイルを再読込',True)):
        window.reconcile_external()
    assert window.scenario['name'] == 'Externally edited'
    assert not window.dirty
    window.undo()
    assert window.scenario['name'] == 'UI'
    assert len(window.scenario['steps'][0]['repeat']['steps']) == 3
    window.dirty = False
    window.close()


def test_destructive_confirmation_policy_and_cancel(tmp_path):
    app=QApplication.instance() or QApplication([])
    source=tmp_path/'scenario.yaml'
    save_yaml(source,{'version':1,'name':'gate','steps':[]})
    save_yaml(tmp_path/'elements.yaml',{'version':1,'pages':{}})
    save_yaml(tmp_path/'config.yaml',{'version':1,'driver':{'path':'/tmp/msedgedriver'}})
    window=FlowTapeWindow(str(source),str(tmp_path/'config.yaml'), preferences_path=tmp_path/'preferences.json')
    from PySide6.QtWidgets import QMessageBox
    class Worker:
        answers=[]
        def confirm(self,value):self.answers.append(value)
    window.worker=Worker()
    node={'action':'click','target':'Delete','risk':'破壊的'}
    window.config['safety']['destructive_confirmation']='once_per_run'
    with patch('flowtape.ui.QMessageBox.question',side_effect=[QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes]) as question:
        window._confirm_action(node)
        window._confirm_action(node)
        window._confirm_action(node)
        assert question.call_count==2
    assert window.worker.answers==[False,True,True]
    window.config['safety']['destructive_confirmation']='off'
    with patch('flowtape.ui.QMessageBox.question') as question:
        window._confirm_action(node)
        question.assert_not_called()
    window.worker=None
    window.close()


def test_navigation_click_commits_source_proof_without_destination_lookup(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PySide6.QtWidgets import QDialog
    from flowtape.desktop_dialogs import PageRegistrationDialog
    from flowtape.recorder import Operation
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'scenario.yaml'
    save_yaml(source, {'version': 1, 'name': 'source', 'steps': []})
    save_yaml(tmp_path / 'elements.yaml', {'version': 1, 'pages': {}})
    window = FlowTapeWindow(str(source), preferences_path=tmp_path / 'preferences.json')
    window.driver = SimpleNamespace(current_url='https://test/destination',
                                    execute_script=Mock(side_effect=AssertionError('destination DOM must not be used')))
    window.transport = Mock()
    window.recording = True
    snapshot = {'tag': 'a', 'role': 'link', 'name': '次へ', 'attributes': {}, 'capture': {
        'document_id': 'old', 'locate': [{'by': 'role', 'role': 'link', 'name': '次へ'}],
        'page_conditions': {}, 'pages': []}}
    op = Operation('click', snapshot=snapshot, url='https://test/source', document_id='old')
    def register(dialog):
        dialog.validate()
        return QDialog.DialogCode.Accepted
    try:
        with patch.object(PageRegistrationDialog, 'exec', register), patch('flowtape.ui.QInputDialog.getText', return_value=('次へ', True)):
            window._operation(op)
        assert window.recording and window.pending_operation is None
        assert window.scenario['steps'][0]['target'] == '次へ'
        assert window.registry['pages']['source']['identify'] == {'url': {'equals': 'https://test/source'}}
        assert window.registry['pages']['source']['elements']['次へ']['locate'] == snapshot['capture']['locate']
        window._operation(op)
        assert len(window.scenario['steps']) == 2
        window.driver.execute_script.assert_not_called()
        # A newly introduced DOM-dependent source condition cannot be guessed.
        window.registry['pages']['unconfirmed'] = {'identify': {'exists': {'id': 'missing'}}, 'elements': {}}
        with patch('flowtape.ui.QMessageBox.warning'):
            window._operation(op)
        assert not window.recording and window.pending_operation is op
        assert len(window.scenario['steps']) == 2
    finally:
        window.driver = None
        window.transport = None
        window.pending_operation = None
        window.recording = False
        window.dirty = False
        window.close()


def test_cancel_source_registration_retains_click_without_reprompt(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PySide6.QtWidgets import QDialog
    from flowtape.desktop_dialogs import PageRegistrationDialog
    from flowtape.recorder import Operation
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'scenario.yaml'
    save_yaml(source, {'version': 1, 'name': 'cancel', 'steps': []})
    save_yaml(tmp_path / 'elements.yaml', {'version': 1, 'pages': {}})
    window = FlowTapeWindow(str(source), preferences_path=tmp_path / 'preferences.json')
    window.driver = SimpleNamespace(current_url='https://test/source')
    window.transport = Mock()
    window.recording = True
    snapshot = {'tag': 'a', 'role': 'link', 'name': '次へ', 'attributes': {}, 'capture': {
        'document_id': 'source', 'locate': [{'by': 'role', 'role': 'link', 'name': '次へ'}],
        'page_conditions': {}, 'pages': []}}
    op = Operation('click', snapshot=snapshot, url=window.driver.current_url, document_id='source')
    try:
        with patch.object(PageRegistrationDialog, 'exec', return_value=QDialog.DialogCode.Rejected) as dialog, \
             patch('flowtape.ui.QInputDialog.getText') as name:
            window._operation(op)
        dialog.assert_called_once()
        name.assert_not_called()
        assert not window.recording and window.pending_operation is op
        assert window.scenario['steps'] == [] and window.registry['pages'] == {}
        window.transport.inject.assert_called_once_with('observe')
    finally:
        window.driver = window.transport = None
        window.pending_operation = None
        window.recording = window.dirty = False
        window.close()


def test_direct_open_records_without_target_registration_and_survives_save(tmp_path):
    from flowtape.recorder import Operation
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'scenario.yaml'
    save_yaml(source, {'version': 1, 'name': 'navigation', 'steps': []})
    save_yaml(tmp_path / 'elements.yaml', {'version': 1, 'pages': {}})
    window = FlowTapeWindow(str(source), preferences_path=tmp_path / 'preferences.json')
    try:
        with patch.object(window, '_page', side_effect=AssertionError('open has no DOM target')):
            window._operation(Operation('open', data={'url': 'https://www.uitestingplayground.com/'}))
        assert window.scenario['steps'][0]['action'] == 'open'
        assert window.scenario['steps'][0]['url'] == 'https://www.uitestingplayground.com/'
        window.save()
        assert load_yaml(source)['steps'] == window.scenario['steps']
        assert window.registry['pages'] == {}
    finally:
        window.dirty = False
        window.close()


def test_application_open_flushes_prior_recording_and_owns_single_open(tmp_path):
    from unittest.mock import Mock
    from types import SimpleNamespace
    from flowtape.recorder import Operation, RecorderTransport
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'scenario.yaml'
    save_yaml(source, {'version': 1, 'name': 'URL command', 'steps': []})
    save_yaml(tmp_path / 'elements.yaml', {'version': 1, 'pages': {}})
    window = FlowTapeWindow(str(source), preferences_path=tmp_path / 'preferences.json')
    window.driver = SimpleNamespace(get=Mock())
    window.transport = object.__new__(RecorderTransport)
    window.transport.drain = Mock(return_value=[Operation('key', value='Tab')])
    window.transport.navigate = Mock()
    window.transport.set_pages = Mock()
    window.recording = True
    try:
        with patch('flowtape.ui.QInputDialog.getText', return_value=('https://test/', True)):
            window.open_url()
        assert [node['action'] for node in window.scenario['steps']] == ['key', 'open']
        window.transport.drain.assert_called_once_with(force=True)
        window.transport.navigate.assert_called_once_with('https://test/')
        window.driver.get.assert_not_called()
    finally:
        window.driver = window.transport = None
        window.recording = window.dirty = False
        window.recorder_error = None
        window.close()
