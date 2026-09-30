import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from flowtape import schema
from flowtape.cli import main, package
from flowtape.lifecycle import Preferences, create_package
from flowtape.persistence import journal_path, save_package
from flowtape.ui import FlowTapeWindow


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    value = FlowTapeWindow(preferences_path=tmp_path/'prefs.json')
    yield value
    value.dirty = False
    value.recording = value.picking = False
    value.pending_operation = None
    value.operation_queue.clear()
    value.recorder_error = None
    value.worker = None
    value.close()
    app.processEvents()


def config(tmp_path, name='config.yaml'):
    source = tmp_path/name
    schema.save_yaml(source, {'version':1, 'driver':{'path':'/tmp/nonexistent-msedgedriver'}})
    return source


def test_neutral_cli_and_editor_without_browser(window, tmp_path):
    assert window.scenario is None and window.config is None
    assert window.actions['新規シナリオ'].isEnabled()
    assert window.actions['シナリオを開く'].isEnabled()
    for label in window.scenario_actions:
        assert not window.actions[label].isEnabled(), label
    assert all(not button.isEnabled() for button in window.playback_buttons)
    with patch('flowtape.ui.launch', return_value=0) as launch:
        assert main(['ui']) == 0
        launch.assert_called_once_with(None, None)
    assert window.create_scenario('新しい手順', tmp_path/'new')
    assert not window.recording
    assert window.actions['追加'].isEnabled()
    assert not window.actions['記録開始'].isEnabled()
    assert window.config is None
    assert package(tmp_path/'new')[0] == {'version':1,'name':'新しい手順','mode':'実行','steps':[]}
    window._insert_node({'action':'back'})
    assert window.save()
    assert package(tmp_path/'new')[0]['steps'][0]['action'] == 'back'
    assert window.close_scenario()
    assert window.scenario is None


def test_browser_failure_retry_and_survival(window, tmp_path):
    assert window.load_config(config(tmp_path))
    with patch('flowtape.ui.open_edge', side_effect=RuntimeError('driver failed')):
        window.open_browser()
    assert window.driver is None
    assert 'unavailable' in window.browser_status.text()
    assert window.create_scenario('First', tmp_path/'first')
    browser, transport = Mock(), Mock()
    with patch('flowtape.ui.open_edge', return_value=browser), patch('flowtape.ui.RecorderTransport', return_value=transport):
        window.open_browser()
    assert 'ready' in window.browser_status.text()
    assert window.actions['記録開始'].isEnabled()
    transport.inject.assert_called_once_with('observe')
    window.undo_stack.append('old');window.record_position=('old', 1)
    window.controller = Mock()
    assert window.create_scenario('Second', tmp_path/'second')
    assert window.controller is None and not window.undo_stack and window.record_position is None
    assert window.driver is browser
    assert window.close_scenario()
    assert window.driver is browser
    browser.quit.assert_not_called()
    assert not window.actions['選択'].isEnabled()
    window.close()
    browser.quit.assert_called_once()
    transport.close.assert_called_once()


def test_creation_failure_exclusive_and_rollback(window, tmp_path):
    existing = create_package('Existing', tmp_path/'existing')
    original = existing.read_bytes()
    assert window.open_scenario(existing)
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.create_scenario('Overwrite', tmp_path/'existing')
    assert existing.read_bytes() == original
    assert window.scenario['name'] == 'Existing'
    from flowtape import lifecycle
    original_replace = lifecycle.os.replace
    def failing_move(source, destination):
        if Path(destination).parent == tmp_path/'failed': raise OSError('disk failure')
        return original_replace(source, destination)
    with patch('flowtape.lifecycle.os.replace', side_effect=failing_move):
        with pytest.raises(OSError): create_package('Failed', tmp_path/'failed')
    assert not (tmp_path/'failed').exists()
    assert not list(tmp_path.glob('.flowtape-new-*'))
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.open_scenario(tmp_path/'missing')
        bad = tmp_path/'invalid';bad.mkdir()
        (bad/'scenario.yaml').write_text('version: 1\nname: invalid\nsteps: [', encoding='utf-8')
        assert not window.open_scenario(bad)
    assert window.scenario['name'] == 'Existing'


@pytest.mark.parametrize('choice,proceeds,saved', [
    ('キャンセル',False,False), ('変更を破棄して続行',True,False), ('保存して続行',True,True)])
def test_unsaved_switch(window, tmp_path, choice, proceeds, saved):
    assert window.create_scenario('First',tmp_path/'first')
    window._insert_node({'action':'back'})
    source = window.scenario_path
    second = create_package('Second',tmp_path/'second')
    with patch('flowtape.ui.QInputDialog.getItem', return_value=(choice,True)):
        assert window.open_scenario(second) == proceeds
    assert bool(package(source)[0]['steps']) == saved
    assert window.scenario['name'] == ('Second' if proceeds else 'First')
    if proceeds: assert not window.dirty and not window.undo_stack


def test_failed_save_blocks_switch_and_exit(window, tmp_path):
    window.create_scenario('First',tmp_path/'first')
    window._insert_node({'action':'back'})
    with patch('flowtape.ui.QInputDialog.getItem', return_value=('保存して続行', True)), \
         patch('flowtape.ui.save_package', side_effect=OSError('disk')), patch('flowtape.ui.QMessageBox.warning'):
        assert not window.create_scenario('Second',tmp_path/'second')
        assert not window.close_scenario()
        event=Mock();window.closeEvent(event);event.ignore.assert_called_once()
    assert window.dirty and window.scenario['name']=='First'
    assert not (tmp_path/'second').exists()


def test_recording_pending_and_picker_boundaries(window, tmp_path):
    window.create_scenario('First', tmp_path/'first')
    transport=Mock();window.transport=transport
    transport.stop.return_value=[]
    window.recording=True
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
        assert not window.close_scenario()
    assert window.recording
    window.pending_operation=object()
    with patch('flowtape.ui.QMessageBox.question',side_effect=[QMessageBox.StandardButton.Yes,QMessageBox.StandardButton.No]):
        assert not window.close_scenario()
    assert not window.recording and window.pending_operation is not None
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert window.close_scenario()
    assert not window.operation_queue and window.pending_operation is None
    assert window.create_scenario('Second',tmp_path/'second')
    window.picking=True
    window.binding_name='Old target';window.pending_read={'into':'old'}
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert window.close_scenario()
    assert window.binding_name is None and window.pending_read is None
    assert transport.stop.call_count==2


def test_playback_boundary_waits_and_cancels(window,tmp_path):
    window.create_scenario('First',tmp_path/'first')
    worker=Mock();worker.isRunning.return_value=True
    worker.wait.return_value=False
    window.worker=worker;controller=Mock();window.controller=controller
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
        assert not window.close_scenario()
    controller.stop.assert_not_called()
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert not window.close_scenario()
        assert window.scenario is not None
        worker.wait.return_value=True
        assert window.close_scenario()
    assert window.controller is None and window.worker is None
    worker.confirm.assert_called_with(False)


def test_recovery_on_open_not_startup(window,tmp_path):
    source=create_package('First',tmp_path/'first')
    from flowtape import persistence
    original=persistence.os.replace
    def interrupted(src,dst):
        if Path(dst).name=='elements.yaml':raise KeyboardInterrupt()
        return original(src,dst)
    with patch('flowtape.persistence.os.replace',side_effect=interrupted):
        with pytest.raises(KeyboardInterrupt):
            save_package(source,{'version':1,'name':'Staged','steps':[]},{'version':1,'pages':{}})
    assert journal_path(source).exists()
    assert window.scenario is None
    with patch('flowtape.ui.QInputDialog.getItem',return_value=('キャンセル',True)):
        assert not window.open_scenario(source)
    assert window.scenario is None and journal_path(source).exists()
    with patch('flowtape.ui.QInputDialog.getItem',return_value=('保存を完了する',True)):
        assert window.open_scenario(source)
    assert window.scenario['name']=='Staged' and not journal_path(source).exists()


def test_preferences_recent_validation_and_stale_removal(window,tmp_path):
    assert window.create_scenario('First',tmp_path/'first')
    source=window.scenario_path
    assert window.close_scenario()
    reloaded=Preferences(window.preferences.path)
    assert reloaded.recent==[str(source)]
    assert 'recent' not in schema.load_yaml(source)
    source.unlink()
    with patch('flowtape.ui.QMessageBox.warning'),patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert not window.open_scenario(source)
    assert window.scenario is None and window.preferences.recent==[]
    window.preferences.path.write_text('broken',encoding='utf-8')
    assert Preferences(window.preferences.path).error is not None


def test_configuration_change_explicit_restart_and_remember(window,tmp_path):
    source=config(tmp_path)
    assert window.load_config(source)
    assert Preferences(window.preferences.path).config_path==str(source)
    browser,transport=Mock(),Mock();window.driver=browser;window.transport=transport
    other=config(tmp_path,'other.yaml')
    schema.save_yaml(other, {'version':1,'driver':{'path':'/tmp/other-msedgedriver'}})
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
        assert not window.load_config(other)
    assert window.driver is browser and window.config_path==source
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert window.load_config(other)
    browser.quit.assert_called_once()
    assert window.driver is None and window.config_path==other
    bad=tmp_path/'bad.yaml';bad.write_text('version: nope',encoding='utf-8')
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.load_config(bad)
    assert window.config_path==other


def test_startup_invalid_package_usable_and_launch_browser_attempt(tmp_path):
    app=QApplication.instance() or QApplication([])
    with patch('flowtape.ui.QMessageBox.warning'):
        value=FlowTapeWindow(tmp_path/'missing',preferences_path=tmp_path/'prefs.json')
    assert value.scenario is None and value.actions['新規シナリオ'].isEnabled()
    value.close()
    with patch('flowtape.ui.QApplication.instance',return_value=Mock()), \
         patch('flowtape.ui.FlowTapeWindow') as constructor, patch('flowtape.ui.QTimer.singleShot') as schedule:
        from flowtape.ui import launch
        launch()
        constructor.assert_called_once_with(None,None)
        schedule.assert_called_once_with(0,constructor.return_value.open_browser)


def test_browser_loss_disables_capture_but_preserves_editing(window,tmp_path):
    window.create_scenario('First',tmp_path/'first')
    window.load_config(config(tmp_path))
    browser=Mock();browser.window_handles=[]
    window.driver=browser;window.transport=Mock();window.recording=True
    window.poll()
    assert window.driver is None and not window.recording
    assert window.recorder_error is not None
    assert not window.actions['記録開始'].isEnabled()
    assert window.actions['追加'].isEnabled()
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        assert window.close_scenario()


def test_cli_requested_invalid_package_does_not_exit(tmp_path):
    from flowtape.ui import launch
    app=QApplication.instance() or QApplication([])
    with patch('flowtape.ui.QMessageBox.warning'), patch('flowtape.ui.QApplication.instance',return_value=Mock()) as instance, \
         patch('flowtape.ui.QTimer.singleShot') as schedule:
        launch(str(tmp_path/'missing'))
        assert instance.return_value.exec.called
        window=schedule.call_args.args[1].__self__
        assert window.scenario is None
        window.close()


def test_runtime_config_change_preserves_browser(window,tmp_path):
    source=config(tmp_path)
    window.load_config(source)
    browser,transport=Mock(),Mock();window.driver=browser;window.transport=transport
    schema.save_yaml(source,{'version':1,'driver':{'path':'/tmp/nonexistent-msedgedriver'},'timeouts':{'page_load':'20s'},'logging':{'level':'DEBUG'}})
    with patch('flowtape.ui.QMessageBox.question') as question:
        assert window.load_config(source)
        question.assert_not_called()
    assert window.driver is browser
    browser.quit.assert_not_called()
    browser.set_page_load_timeout.assert_called_with(20)
    assert window.config['logging']['level']=='DEBUG'


def test_recent_entry_revalidates_package(window,tmp_path):
    window.create_scenario('First',tmp_path/'first')
    source=window.scenario_path
    window.close_scenario()
    source.write_text('invalid: true',encoding='utf-8')
    action=window.recent_menu.actions()[0]
    with patch('flowtape.ui.QMessageBox.warning') as warning:
        action.trigger()
    assert warning.called and window.scenario is None


def test_missing_scenario_with_journal_recovery(window,tmp_path):
    source=create_package('First',tmp_path/'first')
    import base64
    data={'version':1,'scenario_file':'scenario.yaml','originals':[None,None],
          'staged':[base64.b64encode(source.read_bytes()).decode(),base64.b64encode(source.with_name('elements.yaml').read_bytes()).decode()]}
    source.unlink()
    journal_path(source).write_text(json.dumps(data),encoding='utf-8')
    with patch('flowtape.ui.QInputDialog.getItem',return_value=('保存を完了する',True)):
        assert window.open_scenario(source.parent)
    assert window.scenario['name']=='First'


def test_modal_switch_blocks_recorder_poll_and_nested_switch(window,tmp_path):
    window.create_scenario('First',tmp_path/'first')
    window._insert_node({'action':'back'})
    def decision(*args,**kwargs):
        assert not window.create_scenario('Nested',tmp_path/'nested')
        with patch.object(window,'_poll_events') as poll:
            window.poll()
            poll.assert_not_called()
        return ('キャンセル',True)
    with patch('flowtape.ui.QInputDialog.getItem',side_effect=decision):
        assert not window.close_scenario()
    assert not window.lifecycle_busy and not (tmp_path/'nested').exists()


def test_new_open_menu_commands(window,tmp_path):
    from flowtape.desktop_dialogs import NewScenarioDialog
    def accept(dialog):
        dialog.name.setText('Created via menu')
        dialog.directory.setText(str(tmp_path))
        return QDialog.DialogCode.Accepted
    with patch.object(NewScenarioDialog,'exec',accept):
        window.actions['新規シナリオ'].trigger()
    assert window.scenario['name']=='Created via menu'
    window.actions['シナリオを閉じる'].trigger()
    assert window.scenario is None
    with patch('flowtape.ui.QFileDialog.getExistingDirectory',return_value=str(tmp_path/'Created via menu')):
        window.actions['シナリオを開く'].trigger()
    assert window.scenario['name']=='Created via menu'


def test_invalid_registry_and_crossfile_keep_previous(window,tmp_path):
    window.create_scenario('First',tmp_path/'first')
    source=create_package('Invalid',tmp_path/'invalid')
    schema.save_yaml(source.with_name('elements.yaml'), {'version':2,'pages':{}})
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.open_scenario(source)
    assert window.scenario['name']=='First'
    schema.save_yaml(source.with_name('elements.yaml'), {'version':1,'pages':{}})
    schema.save_yaml(source,{'version':1,'name':'Cross-file invalid','steps':[{'action':'check','condition':{'page':'undefined'}}]})
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.open_scenario(source)
    assert window.scenario['name']=='First'
