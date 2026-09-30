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
