"""User-facing commands and end-to-end UI state transitions for docs/14."""
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QToolButton, QDialogButtonBox

from flowtape import schema
from flowtape.ui import FlowTapeWindow
from flowtape.browser_setup import BrowserSetupDialog
from flowtape.desktop_dialogs import NewScenarioDialog, ManualStepDialog, PageRegistrationDialog


@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([])
    w=FlowTapeWindow(preferences_path=tmp_path/'app'/'preferences.json')
    w.show();app.processEvents()
    yield w
    if w.worker and w.worker.isRunning():
        w.controller.stop();w.worker.wait(3000)
    w.controller=w.worker=None;w.recording=w.picking=False
    w.pending_operation=w.pending_credential=None;w.operation_queue.clear();w.recorder_error=None
    w.dirty=False;w.close();app.processEvents()


def ready(w,tmp_path,steps=None):
    source=tmp_path/'config.yaml'
    data={'version':1,'driver':{'path':str(tmp_path/'external-driver')}}
    schema.save_yaml(source,data)
    assert w.load_config(source)
    w.driver=Mock();w.driver.window_handles=['one'];w.driver.current_window_handle='one'
    w.driver.current_url='http://local';w.transport=Mock();w.transport.stop.return_value=[];w.transport.drain.return_value=[]
    w.create_scenario('Scenario',tmp_path/'scenario')
    if steps:
        assert w._commit_edit(dict(w.scenario,steps=steps))
    w.update_actions()


def wait_until(predicate,timeout=5):
    app=QApplication.instance();deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    app.processEvents()
    assert predicate(), 'Qt operation timed out'


def finish(w):
    wait_until(lambda:w.worker is not None and not w.worker.isRunning())


def menu_actions(menu):
    found=[]
    for action in menu.actions():
        found.append(action)
        if action.menu():found.extend(menu_actions(action.menu()))
    return found


def test_idle_surface_five_groups_and_advanced_features_reachable(window,tmp_path):
    ready(window,tmp_path,[{'action':'back'}])
    buttons=[b for b in window.primary_bar.findChildren(QPushButton)+window.primary_bar.findChildren(QToolButton) if b.isVisible()]
    assert len(buttons)==5
    assert {b.text() for b in buttons}=={'● 記録','▶ 再生','▶| 続きを記録','保存','⋯'}
    assert not window.mode_box.isVisible() and not window.pace_box.isVisible()
    assert not window.properties.isVisible()
    context=window.step_context_menu()
    actions=set(menu_actions(window.more_menu)+menu_actions(context))
    for key in ['選択','collection 選択','未登録 target','outputs','read','append','解除','上へ','下へ',
                '戻す','やり直す','条件で囲む','else へ移す','繰り返し','while','for_each','追加']:
        assert window.actions[key] in actions,key
    context.deleteLater()
    assert [a.text() for a in window.play_menu.actions()]==['通常','ゆっくり','1ステップずつ','選択位置まで']


def test_record_button_replaces_start_and_exposes_verification(window,tmp_path):
    ready(window,tmp_path,[{'action':'back'}])
    QTest.mouseClick(window.record_button,Qt.MouseButton.LeftButton)
    assert window.recording and window.record_button.text()=='■ 記録を終了'
    assert not window.play_button.isVisible() and not window.continue_button.isVisible()
    assert not window.more_button.isVisible()
    window._insert_node({'action':'refresh'},recording=True)
    QTest.mouseClick(window.record_button,Qt.MouseButton.LeftButton)
    assert not window.recording and window.record_button.text()=='● 記録'
    assert window.verify_button.isVisible() and '1個' in window.next_hint.text()


@pytest.mark.parametrize('state,text,stop,skip',[
    ('running','⏸ 一時停止',True,False),('paused','▶ 再開',True,False),
    ('failed','↻ 再試行',True,True),('complete','▶ 再生',False,False)])
def test_playback_surface_changes_by_state(window,tmp_path,state,text,stop,skip):
    ready(window,tmp_path,[{'action':'back'}])
    window.controller=SimpleNamespace(state=state,error=RuntimeError('step failed') if state=='failed' else None,
                                       current=window.scenario['steps'][0])
    window.update_actions()
    assert window.play_button.text()==text
    assert window.stop_button.isVisible()==stop and window.skip_button.isVisible()==skip
    assert window.record_button.isVisible()==(state=='complete')
    assert window.failure_details.isVisible()==(state=='failed')
    if state=='failed':assert window.step_list.item(0).toolTip()=='step failed'


def test_continue_restarts_from_beginning_preserves_browser_and_appends(window,tmp_path):
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'},{'action':'back'}])
    browser=window.driver
    window.single_step();finish(window)
    assert window.controller.state=='paused'
    assert browser.get.call_count==1
    window.record_position=(('root',),0)
    QTest.mouseClick(window.continue_button,Qt.MouseButton.LeftButton) if window.continue_button.isVisible() else window.play_then_record()
    finish(window)
    assert browser.get.call_count==2 and browser.back.call_count==1
    assert window.controller.state=='complete' and window.recording
    assert window.driver is browser and window.record_position is None
    assert '続きを記録中' in window.activity.text()
    assert window._insert_node({'action':'refresh'},recording=True)
    window.toggle_record()
    assert [node['action'] for node in window.scenario['steps']]==['open','back','refresh']
    assert window.save()
    assert schema.load_yaml(window.scenario_path)['steps'][-1]['action']=='refresh'


@pytest.mark.parametrize('outcome',['failed','stopped','startup'])
def test_continue_does_not_record_after_failure_or_stop(window,tmp_path,outcome):
    ready(window,tmp_path,[{'action':'back'}])
    if outcome=='startup':
        window.pending_operation=object();window.play_then_record()
    else:
        window.record_after_play=True
        window.controller=SimpleNamespace(state=outcome,error=RuntimeError('failure') if outcome=='failed' else None,current=None)
        window._playback_finished()
    assert not window.recording and not window.record_after_play
    window.transport.inject.assert_not_called()


def test_actual_worker_failure_never_transitions_to_recording(window,tmp_path):
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'}])
    window.driver.get.side_effect=RuntimeError('browser failed')
    window.play_then_record();finish(window)
    assert window.controller.state=='failed' and not window.recording and not window.record_after_play
    assert window.skip_button.isVisible() and not window.continue_button.isVisible()


def test_insertion_affordance_nested_recording_and_manual_first_step(window,tmp_path):
    ready(window,tmp_path,[{'repeat':{'count':1,'steps':[{'action':'back'},{'action':'forward'}]}},{'action':'refresh'}])
    menu=window.insertion_menu(1)
    assert [a.text() for a in menu.actions()]==['＋ 手動で操作を追加','● ここから記録']
    menu.actions()[1].trigger()
    assert window.recording
    assert window._insert_node({'action':'refresh'},recording=True)
    window.stop_record()
    assert [n['action'] for n in window.scenario['steps'][0]['repeat']['steps']]==['back','refresh','forward']
    assert window.scenario['steps'][1]['action']=='refresh'
    def manual(dialog):
        dialog.action.setCurrentIndex(dialog.action.findData('open'));dialog.value.setText('http://local/first')
        dialog.validate();return dialog.result()
    with patch.object(ManualStepDialog,'exec',manual):window.manual_add_at(-1)
    assert window.scenario['steps'][0]['url']=='http://local/first'
    menu.deleteLater()


def test_gap_click_exposes_insertion_without_fake_step_rows(window,tmp_path):
    ready(window,tmp_path,[{'action':'back'},{'action':'forward'}])
    QApplication.instance().processEvents()
    rect=window.step_list.visualItemRect(window.step_list.item(0))
    point=rect.center();point.setY(rect.bottom()-8)
    with patch.object(window,'show_insertion_menu') as menu:
        # Signal is connected to the production slot, so observe emission directly.
        events=[]
        window.step_list.insertion_requested.disconnect()
        window.step_list.insertion_requested.connect(lambda row,p:events.append(row))
        QTest.mouseClick(window.step_list.viewport(),Qt.MouseButton.LeftButton,pos=point)
    assert events==[0] and window.step_list.count()==2 and len(window.rows)==2


def test_browser_unavailable_start_and_ready_new_recording_flow(window,tmp_path):
    assert window.setup_button.isVisible() and 'ブラウザ' in window.start_heading.text()
    assert not window.primary_bar.isVisible() and window.open_scenario_button.isEnabled()
    with patch.object(BrowserSetupDialog,'exec',return_value=QDialog.DialogCode.Rejected),patch.object(window,'edit_config') as full:
        QTest.mouseClick(window.setup_button,Qt.MouseButton.LeftButton)
        full.assert_not_called()
    ready(window,tmp_path)
    assert window.close_scenario()
    assert window.new_recording_button.isVisible() and not window.setup_button.isVisible()
    assert window.start_heading.text()=='何をしますか？'
    def new(dialog):
        assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).text()=='作成して記録へ'
        dialog.name.setText('New Flow');dialog.directory.setText(str(tmp_path))
        dialog.accept();return dialog.result()
    with patch.object(NewScenarioDialog,'exec',new):QTest.mouseClick(window.new_recording_button,Qt.MouseButton.LeftButton)
    assert window.scenario['steps']==[] and not window.recording
    assert window.empty_view.isVisible() and window.empty_record_button.isEnabled()
    QTest.mouseClick(window.empty_record_button,Qt.MouseButton.LeftButton)
    assert window.recording


def test_target_controls_are_contextual_and_use_user_terms(window,tmp_path):
    ready(window,tmp_path,[{'action':'click','target':'保存'}])
    window.step_list.setCurrentRow(0)
    assert window.target_button.text()=='ブラウザで指定'
    assert window.target_controls.isVisible()
    assert '未登録' in window.target_summary.text()
    window.registry['pages']={'local':{'identify':{'url':{'equals':'http://local'}},'elements':{'保存':{'kind':'button','locate':[{'by':'id','value':'save'}]}}}}
    window.show_properties(0)
    assert window.target_button.text()=='ブラウザで再指定'
    assert window.diagnostic_button.text()=='診断を見る'


def test_guided_setup_connection_required_defaults_save_and_invalidated_inputs(window,tmp_path):
    source=tmp_path/'new'/'config.yaml'
    dialog=BrowserSetupDialog(window,source)
    assert dialog.pages.currentIndex()==0 and not dialog.save_button.isEnabled()
    dialog.next_button.click();assert dialog.pages.currentIndex()==1
    dialog.driver_path.setText(str(tmp_path/'external-driver'))
    browser=Mock();browser.capabilities={'browserVersion':'154','msedge':{'msedgedriverVersion':'154 test'}}
    with patch('flowtape.browser_setup.open_edge',return_value=browser):
        dialog.test_connection();wait_until(lambda:not dialog.probe.isRunning());wait_until(lambda:dialog.save_button.isEnabled())
    browser.get.assert_called_once_with('about:blank');browser.quit.assert_called_once()
    assert not source.exists()
    assert dialog.tested_document['credentials']['path']==str(source.with_name('credentials.yaml'))
    assert dialog.tested_document['timeouts']['default']=='10s'
    dialog.driver_path.setText(str(tmp_path/'other-driver'))
    assert not dialog.save_button.isEnabled() and dialog.tested_document is None
    with patch('flowtape.browser_setup.open_edge',side_effect=RuntimeError('sensitive detail')):
        dialog.test_connection();wait_until(lambda:not dialog.probe.isRunning())
    assert not dialog.test_success and 'sensitive detail' not in dialog.result_label.text()
    dialog.reject()


def test_onboarding_saves_only_after_success_and_keeps_full_settings(window,tmp_path):
    browser=Mock();browser.capabilities={'browserVersion':'154'}
    def setup(dialog):
        dialog.driver_path.setText(str(tmp_path/'external-driver'));dialog.set_page(1)
        dialog.test_connection();wait_until(lambda:not dialog.probe.isRunning());wait_until(lambda:dialog.save_button.isEnabled())
        dialog.save_button.click();return dialog.result()
    with patch('flowtape.browser_setup.open_edge',return_value=browser),patch('flowtape.ui.open_edge',return_value=Mock()),patch('flowtape.ui.RecorderTransport',return_value=Mock()):
        with patch.object(BrowserSetupDialog,'exec',setup):window.setup_browser()
    assert window.config_path.exists() and window.config and window.driver
    assert window.scenario is None and window.start_heading.text()=='何をしますか？'
    assert any(a.text()=='アプリ設定を作成・編集' for menu in window.menuBar().actions() if menu.menu() for a in menu.menu().actions())


def test_page_registration_default_and_advanced_conditions():
    app=QApplication.instance() or QApplication([])
    dialog=PageRegistrationDialog(None,'Login',{'url':{'equals':'http://local'}})
    assert not dialog.yaml.isVisible()
    dialog.validate();assert dialog.identify=={'url':{'equals':'http://local'}}
    dialog=PageRegistrationDialog(None,'Login',{'url':{'equals':'http://local'}})
    dialog.advanced.setChecked(True);dialog.yaml.setPlainText('all:\n- url: {contains: local}\n- exists: {id: form}')
    dialog.validate();assert 'all' in dialog.identify
    dialog.close()


@pytest.mark.parametrize('choice,state,get_count,back_count',[
    ('通常','complete',1,1),('1ステップずつ','paused',1,0),('選択位置まで','paused',1,0)])
def test_dropdown_uses_existing_playback_boundaries(window,tmp_path,choice,state,get_count,back_count):
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'},{'action':'back'}])
    window.step_list.setCurrentRow(1)
    next(action for action in window.play_menu.actions() if action.text()==choice).trigger()
    finish(window)
    assert window.controller.state==state
    assert window.driver.get.call_count==get_count and window.driver.back.call_count==back_count
    if choice=='選択位置まで':assert window.controller.current is window.scenario['steps'][1]


def test_slow_choice_keeps_configured_observation_delay(window,tmp_path):
    ready(window,tmp_path,[{'action':'back'}])
    window.config['playback']['observation_delay']='2s'
    with patch.object(window,'_start_playback') as start:
        next(action for action in window.play_menu.actions() if action.text()=='ゆっくり').trigger()
    assert window.pace_box.currentData()=='2s'
    start.assert_called_once_with(max_actions=None)


def test_unavailable_browser_keeps_open_and_recovery_available(window,tmp_path):
    ready(window,tmp_path)
    assert window.close_scenario()
    window.shutdown_browser()
    window.update_actions()
    assert window.scenario is None and window.recovery_view.isVisible()
    assert window.setup_button.isVisible() and window.open_scenario_button.isEnabled()
    assert not window.primary_bar.isVisible()


def test_pending_recording_keeps_its_original_insertion_position(window,tmp_path):
    ready(window,tmp_path,[{'action':'back'},{'action':'forward'}])
    window.pending_operation=object();window.record_position=(('root',),1)
    menu=window.insertion_menu(0)
    assert not menu.actions()[1].isEnabled()
    window.record_at(-1)
    assert window.record_position==(('root',),1) and not window.recording
    menu.deleteLater()


@pytest.mark.parametrize('case', ['closed_polled', 'closed_before_poll', 'continue_closed'])
def test_fresh_playback_starts_browser_from_config_after_closure(window,tmp_path,case):
    from flowtape.recorder import RecorderTransport
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'}])
    old = window.driver
    if case == 'closed_before_poll': old.window_handles = []
    else: window.shutdown_browser()
    window.update_actions()
    assert window.play_button.isEnabled() and window.continue_button.isEnabled()
    fresh = Mock()
    fresh.window_handles = ['fresh']
    fresh.current_window_handle = 'fresh'
    with patch('flowtape.ui.open_edge', return_value=fresh) as launch, patch.object(RecorderTransport, 'inject'):
        QTest.mouseClick(window.continue_button if case == 'continue_closed' else window.play_button, Qt.MouseButton.LeftButton)
        finish(window)
    launch.assert_called_once()
    fresh.get.assert_called_once_with('http://local/start')
    old.quit.assert_called_once()
    assert window.controller.state == 'complete' and window.driver is fresh
    assert window.recording == (case == 'continue_closed')


def test_unresolved_capture_blocks_browser_relaunch_for_playback(window,tmp_path):
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'}])
    window.shutdown_browser()
    window.recorder_error = 'capture interval uncertain'
    window.update_actions()
    assert not window.play_button.isEnabled()
    with patch('flowtape.ui.open_edge') as launch:
        assert not window._new_playback()
    launch.assert_not_called()


@pytest.mark.parametrize('closed_detected', [True, False])
@pytest.mark.parametrize('button', ['record_button', 'empty_record_button'])
def test_new_empty_recording_starts_edge_after_previous_playback(window,tmp_path,closed_detected,button):
    from flowtape.recorder import RecorderTransport
    ready(window,tmp_path,[{'action':'open','url':'http://local/start'}])
    assert window.save()
    window.play();finish(window)
    assert window.controller.state == 'complete'
    old = window.driver
    old.window_handles = []
    if closed_detected:
        window.last_browser_check = 0
        window.poll()
    assert window.create_scenario('Next recording', tmp_path/'next')
    assert window.scenario['steps'] == [] and not window.recording
    assert window.record_button.isEnabled() and window.empty_record_button.isEnabled()
    assert window.actions['記録開始'].isEnabled() and window.empty_url_button.isEnabled()
    fresh = Mock()
    fresh.window_handles = ['fresh']
    fresh.current_window_handle = 'fresh'
    with patch('flowtape.ui.open_edge', return_value=fresh) as launch, patch.object(RecorderTransport, 'inject') as inject:
        QTest.mouseClick(getattr(window, button), Qt.MouseButton.LeftButton)
    launch.assert_called_once()
    old.quit.assert_called_once()
    assert window.recording and window.driver is fresh and window.scenario['steps'] == []
    assert [call.args[0] for call in inject.call_args_list] == ['observe', 'record']


def test_record_startup_failure_stays_idle_and_available_for_retry(window,tmp_path):
    ready(window,tmp_path)
    window.shutdown_browser()
    with patch('flowtape.ui.open_edge', side_effect=RuntimeError('driver unavailable')):
        QTest.mouseClick(window.empty_record_button, Qt.MouseButton.LeftButton)
    assert not window.recording and window.driver is None and not window.recorder_error
    assert window.empty_record_button.isEnabled()
    assert 'Edge 起動失敗' in window.status.text()


def test_pending_capture_disables_record_launch_and_preserves_evidence(window,tmp_path):
    ready(window,tmp_path)
    window.shutdown_browser()
    pending = object()
    window.pending_operation = pending
    window.update_actions()
    assert not window.record_button.isEnabled() and not window.empty_record_button.isEnabled()
    assert not window.actions['記録開始'].isEnabled()
    with patch('flowtape.ui.open_edge') as launch:
        window.start_record()
    launch.assert_not_called()
    assert window.pending_operation is pending and not window.recording
