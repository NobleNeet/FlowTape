"""Task-oriented desktop command hierarchy; domain behavior stays in FlowTapeWindow."""

from PySide6.QtCore import Qt, QSize, QRect, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QMenu, QComboBox, QDialog, QDialogButtonBox, QListWidget,
    QSplitter, QTextEdit, QStyledItemDelegate)

from .browser_setup import detect_edge


class StepDelegate(QStyledItemDelegate):
    """Draw step-boundary insertion affordances without adding fake model rows."""
    def sizeHint(self, option, index):
        size = super().sizeHint(option,index)
        return QSize(size.width(), max(58,size.height()+24))

    def paint(self, painter, option, index):
        text_option = type(option)(option)
        text_option.rect = option.rect.adjusted(0,0,0,-22)
        super().paint(painter,text_option,index)
        if self.parent().property('insertionEnabled') is False:return
        gap = QRect(option.rect.left()+20,option.rect.bottom()-21,option.rect.width()-40,22)
        painter.save()
        painter.setPen(QColor('#64748b'))
        painter.drawText(gap,Qt.AlignmentFlag.AlignCenter,'──── ＋ ────')
        painter.restore()


class StepList(QListWidget):
    insertion_requested = Signal(int,object)

    def mouseReleaseEvent(self,event):
        item = self.itemAt(event.position().toPoint())
        if item and self.property('insertionEnabled') is not False and event.button()==Qt.MouseButton.LeftButton:
            rect = self.visualItemRect(item)
            if event.position().y() >= rect.bottom()-22:
                self.insertion_requested.emit(self.row(item),event.globalPosition().toPoint())
                return
        super().mouseReleaseEvent(event)


def build_surface(w, layout):
    # Stable action keys remain available to existing integrations and tests.
    commands = [
        ('ブラウザ','ブラウザを起動／再試行',w.open_browser),('URLを開く','URLを開く',w.open_url),
        ('記録開始','記録を開始',w.start_record),('選択後に記録','ここから記録',w.start_insertion_record),
        ('記録停止','記録を終了',w.stop_record),('認証情報の選択を再試行','認証情報の選択を再試行',w.retry_credential),
        ('記録保留を破棄','保留中の記録を破棄',w.discard_pending),
        ('選択','ブラウザから対象を登録',w.start_pick),('collection 選択','繰り返し対象を登録',w.start_collection_pick),
        ('条件で囲む','～の場合',w.wrap_if),('else へ移す','それ以外',w.move_to_else),
        ('繰り返し','指定回数',w.wrap_repeat),('while','条件を満たす間',w.wrap_while),('for_each','各対象について',w.wrap_for_each),
        ('追加','YAMLで操作を追加',w.add_step),('read','値を読み取る',w.author_read),
        ('append','出力へ追加',w.author_append),('outputs','出力設定',w.edit_outputs),
        ('bind / rebind','ブラウザで指定／再指定',w.bind_selected),('未登録 target','未登録の対象を確認',w.bind_missing),
        ('診断','診断を見る',w.diagnose_selected),('上へ','上へ移動',w.move_up),('下へ','下へ移動',w.move_down),
        ('削除','削除',w.delete_steps),('解除','条件・繰り返しを解除',w.unwrap),
        ('名前変更','対象の名前変更',w.rename_registered_target),('戻す','元に戻す',w.undo),
        ('やり直す','やり直す',w.redo),('適用','変更を適用',w.apply_properties),
    ]
    for key,label,method in commands:
        action = QAction(label,w)
        action.triggered.connect(lambda checked=False,callback=method: callback())
        w.actions[key]=action
        if key not in {'ブラウザ','URLを開く'}:w.scenario_actions.add(key)
        if key in {'URLを開く','記録開始','選択後に記録','記録停止','選択','collection 選択',
                   'bind / rebind','未登録 target','診断','read'}:w.browser_actions.add(key)
    w.actions['保存'].setShortcut('Ctrl+S')
    w.actions['戻す'].setShortcut('Ctrl+Z');w.actions['やり直す'].setShortcut('Ctrl+Shift+Z')
    w.addActions([w.actions['戻す'],w.actions['やり直す']])

    w.scenario_heading=QLabel();w.scenario_heading.setStyleSheet('font-size:19px;font-weight:bold;padding:4px 0');layout.addWidget(w.scenario_heading)
    w.primary_bar=QWidget()
    bar=QHBoxLayout(w.primary_bar);bar.setContentsMargins(0,4,0,8)
    w.record_button=QPushButton('● 記録');w.record_button.clicked.connect(w.toggle_record)
    w.play_button=QToolButton();w.play_button.setText('▶ 再生')
    w.play_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
    w.play_menu=QMenu(w.play_button)
    for label,method in [('通常',lambda:w.choose_playback('通常')),('ゆっくり',lambda:w.choose_playback('ゆっくり')),
                         ('1ステップずつ',lambda:w.choose_playback('1ステップずつ')),('選択位置まで',w.play_until_selected)]:
        action=w.play_menu.addAction(label)
        action.triggered.connect(lambda checked=False,callback=method:callback())
    w.play_button.setMenu(w.play_menu);w.play_button.clicked.connect(w.primary_playback)
    w.stop_button=QPushButton('■ 停止');w.stop_button.clicked.connect(w.stop_playback)
    w.skip_button=QPushButton('スキップ');w.skip_button.clicked.connect(w.skip_playback)
    w.continue_button=QPushButton('▶| 続きを記録');w.continue_button.clicked.connect(w.play_then_record)
    w.continue_button.setToolTip('シナリオを先頭から末尾まで再生し、その状態から自動で記録を開始します。')
    for button in [w.record_button,w.play_button,w.skip_button,w.stop_button,w.continue_button]:bar.addWidget(button)
    bar.addStretch()
    save=QToolButton();save.setDefaultAction(w.actions['保存']);bar.addWidget(save)
    w.more_button=QToolButton();w.more_button.setText('⋯');w.more_button.setToolTip('編集・ブラウザ・詳細設定')
    w.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    w.more_menu=QMenu(w.more_button);w.more_button.setMenu(w.more_menu);bar.addWidget(w.more_button)
    layout.addWidget(w.primary_bar)
    w.playback_buttons=[w.play_button,w.skip_button,w.stop_button]
    for heading,keys in [('操作を追加',['追加','read','append']),('シナリオ',['未登録 target','outputs']),
                         ('編集',['戻す','やり直す']),('ブラウザ',['URLを開く','ブラウザ']),
                         ('高度な操作',['選択','collection 選択','認証情報の選択を再試行','記録保留を破棄'])]:
        menu=w.more_menu.addMenu(heading)
        if heading=='操作を追加':menu.addAction('手動でブラウザ操作を追加',lambda:w.manual_add_at(w.step_list.currentRow()))
        for key in keys:menu.addAction(w.actions[key])
    w.more_menu.addAction('再生・実行の詳細設定',w.show_playback_settings)
    w.more_menu.addAction('先頭から再実行',w.restart_playback)
    w.more_menu.addAction('YAML・詳細を編集',w.show_yaml_details)
    w.more_menu.addAction('シナリオを検証',w.validate_scenario)

    w.playback_settings=QDialog(w);w.playback_settings.setWindowTitle('再生・実行の詳細設定')
    options=QVBoxLayout(w.playback_settings)
    options.addWidget(QLabel('実行モードと再生の速さは別の設定です。'))
    w.mode_box=QComboBox();w.mode_box.addItems(['実行','確認','デバッグ']);w.mode_box.currentTextChanged.connect(w.change_mode)
    options.addWidget(QLabel('実行モード'));options.addWidget(w.mode_box)
    w.pace_box=QComboBox()
    for label,value in [('通常','0s'),('1秒','1s'),('2秒','2s'),('5秒','5s'),('ステップ',None)]:w.pace_box.addItem(label,value)
    options.addWidget(QLabel('操作ごとの観察時間'));options.addWidget(w.pace_box)
    options.addWidget(QLabel('「選択位置まで」は、選択した操作の直前で一時停止します。'))
    close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(w.playback_settings.reject);options.addWidget(close)

    w.start_view=QWidget();start=QVBoxLayout(w.start_view);start.setContentsMargins(50,35,50,25)
    title=QLabel('FlowTape');title.setStyleSheet('font-size:28px;font-weight:bold');start.addWidget(title)
    w.start_heading=QLabel();w.start_heading.setStyleSheet('font-size:19px');start.addWidget(w.start_heading)
    found=detect_edge()
    w.setup_hint=QLabel('Microsoft Edge: '+('検出済み — '+found if found else '標準のEdgeまたは実行ファイルを指定')+'\nWebDriver: 接続テストで確認してください。');w.setup_hint.setWordWrap(True);start.addWidget(w.setup_hint)
    w.setup_button=QPushButton('セットアップを開始');w.setup_button.clicked.connect(w.setup_browser);start.addWidget(w.setup_button)
    w.existing_config_button=QPushButton('既存 config.yaml を使用');w.existing_config_button.clicked.connect(w.choose_config);start.addWidget(w.existing_config_button)
    w.new_recording_button=QPushButton('＋ 新しい操作を記録する');w.new_recording_button.clicked.connect(w.new_scenario);start.addWidget(w.new_recording_button)
    w.open_scenario_button=QPushButton('既存シナリオを開く');w.open_scenario_button.clicked.connect(w.choose_scenario);start.addWidget(w.open_scenario_button)
    start.addWidget(QLabel('最近使ったシナリオ（ダブルクリックで開く）'))
    w.recent_list=QListWidget();w.recent_list.itemDoubleClicked.connect(lambda item:w.open_scenario(item.data(256)));start.addWidget(w.recent_list)
    layout.addWidget(w.start_view)

    w.empty_view=QWidget();empty=QVBoxLayout(w.empty_view)
    text=QLabel('まだ操作はありません。\n\n記録を開始して、Edgeを普段どおり操作してください。\nクリックや文字入力をFlowTapeが記録します。')
    text.setWordWrap(True);empty.addWidget(text)
    w.empty_record_button=QPushButton('● 記録を開始');w.empty_record_button.clicked.connect(w.start_record);empty.addWidget(w.empty_record_button)
    w.empty_url_button=QPushButton('開始するページを開く（任意）');w.empty_url_button.clicked.connect(w.open_url);empty.addWidget(w.empty_url_button)
    layout.addWidget(w.empty_view)
    w.editor_splitter=QSplitter();layout.addWidget(w.editor_splitter)
    left=QWidget();left_layout=QVBoxLayout(left);left_layout.setContentsMargins(0,0,8,0)
    left_layout.addWidget(QLabel('操作の順序（選択・右クリックで編集）'))
    w.insert_first_button=QPushButton('＋ 先頭に追加');w.insert_first_button.clicked.connect(lambda:w.show_insertion_menu(-1))
    left_layout.addWidget(w.insert_first_button)
    w.step_list=StepList();w.step_list.setItemDelegate(StepDelegate(w.step_list))
    w.step_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    w.step_list.currentRowChanged.connect(w.show_properties)
    w.step_list.insertion_requested.connect(w.show_insertion_menu)
    w.step_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    w.step_list.customContextMenuRequested.connect(w.show_step_context)
    left_layout.addWidget(w.step_list);w.editor_splitter.addWidget(left)
    right=QWidget();details=QVBoxLayout(right)
    details.addWidget(QLabel('選択項目'))
    w.selection_summary=QLabel('操作を選択すると、内容と対象を確認できます。');w.selection_summary.setWordWrap(True);details.addWidget(w.selection_summary)
    w.target_summary=QLabel();w.target_summary.setWordWrap(True);details.addWidget(w.target_summary)
    w.target_controls=QWidget();targets=QVBoxLayout(w.target_controls);targets.setContentsMargins(0,0,0,0)
    w.target_button=QPushButton('ブラウザで再指定');w.target_button.clicked.connect(w.bind_selected);targets.addWidget(w.target_button)
    w.diagnostic_button=QPushButton('診断を見る');w.diagnostic_button.clicked.connect(w.diagnose_selected);targets.addWidget(w.diagnostic_button)
    rename=QToolButton();rename.setText('対象の詳細');rename.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu=QMenu(rename);menu.addAction(w.actions['名前変更']);rename.setMenu(menu);targets.addWidget(rename)
    details.addWidget(w.target_controls)
    w.failure_details=QLabel();w.failure_details.setWordWrap(True);details.addWidget(w.failure_details)
    w.yaml_button=QPushButton('YAML・詳細を編集');w.yaml_button.clicked.connect(w.show_yaml_details);details.addWidget(w.yaml_button)
    w.properties=QTextEdit();details.addWidget(w.properties);w.properties.hide()
    w.apply_button=QToolButton();w.apply_button.setDefaultAction(w.actions['適用']);details.addWidget(w.apply_button);w.apply_button.hide()
    details.addStretch();w.editor_splitter.addWidget(right);w.editor_splitter.setSizes([570,360])

    w.next_view=QWidget();next_layout=QHBoxLayout(w.next_view)
    w.next_hint=QLabel();next_layout.addWidget(w.next_hint)
    w.verify_button=QPushButton('▶ 動作確認する');w.verify_button.clicked.connect(lambda:w.choose_playback('通常'));next_layout.addWidget(w.verify_button)
    layout.addWidget(w.next_view)
    w.recovery_view=QWidget();recovery=QHBoxLayout(w.recovery_view)
    recovery.addWidget(QLabel('Edgeに接続できません。設定を確認するか、再試行してください。'))
    retry=QPushButton('再試行');retry.clicked.connect(w.open_browser);recovery.addWidget(retry)
    setup=QPushButton('ブラウザ設定');setup.clicked.connect(w.setup_browser);recovery.addWidget(setup)
    layout.addWidget(w.recovery_view)
    w.activity=QLabel();layout.addWidget(w.activity)
    w.browser_status=QLabel('Browser: unavailable — 未接続');w.statusBar().addPermanentWidget(w.browser_status)
    w.status=QLabel('準備完了');w.status.setWordWrap(True);layout.addWidget(w.status)
    layout.setStretchFactor(w.start_view,1);layout.setStretchFactor(w.empty_view,1);layout.setStretchFactor(w.editor_splitter,1)
    w.setStyleSheet('QMainWindow {background: #f8fafc;} QToolButton, QPushButton {padding: 6px 10px;} QListWidget, QTextEdit {background:white; border:1px solid #cbd5e1;} QMenu {background: white;}')
    for button in [w.record_button,w.verify_button,w.empty_record_button]:button.setStyleSheet('background:#1d4ed8;color:white;border-radius:4px;padding:9px 16px;font-weight:bold')


def update_surface(w):
    active=w.scenario is not None
    ready=w.driver is not None and w.config is not None
    state=w.controller.state if w.controller else 'idle'
    running=bool(w.worker and getattr(w.worker,'isRunning',lambda:False)())
    busy=running or state in {'running','paused','failed'}
    playable=ready or (w.config is not None and not busy)
    pending=bool(w.pending_operation or w.operation_queue or w.recorder_error)
    for label,action in w.actions.items():
        enabled=active if label in w.scenario_actions or label in {'シナリオを閉じる','保存'} else True
        if label in w.browser_actions:enabled=enabled and ready
        if w.recording and label in w.scenario_actions and label not in {'記録停止','記録保留を破棄','認証情報の選択を再試行'}:enabled=False
        action.setEnabled(enabled)
    w.scenario_heading.setVisible(active)
    if active:w.scenario_heading.setText(w.scenario['name']+('  • 未保存' if w.dirty else ''))
    w.primary_bar.setVisible(active)
    w.record_button.setVisible(not busy)
    w.record_button.setText('■ 記録を終了' if w.recording else '● 記録')
    w.record_button.setEnabled(active and ready and (w.recording or not pending))
    playback_visible=active and not w.recording
    w.play_button.setVisible(playback_visible)
    text={'running':'⏸ 一時停止','paused':'▶ 再開','failed':'↻ 再試行'}.get(state,'▶ 再生')
    if running and state not in {'paused','failed'}:text='⏸ 一時停止'
    w.play_button.setText(text);w.play_button.setEnabled(active and playable and not pending and bool(w.scenario['steps'] if active else []))
    w.play_button.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup if busy else QToolButton.ToolButtonPopupMode.MenuButtonPopup)
    for action in w.play_menu.actions():action.setEnabled(active and playable and not w.recording and state!='failed')
    w.stop_button.setVisible(playback_visible and busy);w.stop_button.setEnabled(active and ready)
    w.skip_button.setVisible(playback_visible and state=='failed');w.skip_button.setEnabled(active and ready)
    w.continue_button.setVisible(not w.recording and not busy)
    w.continue_button.setEnabled(active and playable and not pending and bool(w.scenario['steps'] if active else []))
    w.mode_box.setEnabled(active and not busy)
    w.pace_box.setEnabled(active and playable and not busy)
    w.start_view.setVisible(not active)
    w.start_heading.setText(('Edgeとの接続を確認してください' if w.config else 'ブラウザを使えるように設定します') if not ready else '何をしますか？')
    w.setup_button.setVisible(not ready);w.existing_config_button.setVisible(not ready);w.setup_hint.setVisible(not ready)
    w.setup_button.setStyleSheet('background:#1d4ed8;color:white;border-radius:4px;padding:12px;font-size:17px')
    w.new_recording_button.setStyleSheet('font-size:18px;padding:12px;background:#1d4ed8;color:white;border-radius:4px' if ready else '')
    empty=active and not w.scenario['steps']
    w.empty_view.setVisible(empty and not w.recording)
    w.empty_record_button.setEnabled(ready and not busy and not pending)
    w.empty_url_button.setEnabled(ready and not busy and not pending)
    w.editor_splitter.setVisible(active and not empty)
    w.next_view.setVisible(active and w.just_recorded and not w.recording and not busy and not pending)
    if active:w.next_hint.setText(f'{w.last_recorded_count}個の操作を記録しました。再生して動作を確認できます。')
    w.verify_button.setEnabled(playable and not pending)
    w.recovery_view.setVisible(not ready and (active or w.config is not None))
    w.more_button.setVisible(not w.recording)
    w.insert_first_button.setVisible(not w.recording and not running)
    w.step_list.setEnabled(not w.recording)
    w.step_list.setProperty('insertionEnabled',not w.recording and not running)
    w.target_button.setEnabled(ready and not running and not w.recording)
    w.diagnostic_button.setEnabled(ready and not running and not w.recording)
    w.yaml_button.setVisible(not w.recording)
    if w.recording:
        w.properties.hide();w.apply_button.hide();w.target_controls.hide()
    if w.recording:
        message='● 続きを記録中 — Edgeで続きを操作してください。' if w.continuation_recording else '● 記録中 — Edgeを操作してください。'
    elif busy:
        message={'paused':'⏸ 一時停止中','failed':'再生に失敗しました — 選択した操作を確認してください。'}.get(state,'▶ 末尾まで再生中 → 完了後に録画を開始します。' if w.record_after_play else '▶ 再生中')
    elif w.pending_credential:message='認証情報の選択待ち — ⋯ から認証情報の選択を再試行できます。'
    elif pending:message='未確定の記録があります — ⋯ から確定または破棄してください。'
    elif not ready and active and playable:message='再生するとEdgeを起動して、先頭から実行します。'
    elif not ready:message='ブラウザのセットアップまたは再試行で、Edgeに接続してください。'
    elif not active:message='新しい操作を記録するか、既存シナリオを開いてください。'
    else:message='準備完了'
    w.status.setVisible(w.status.text()!=message)
    w.activity.setText(message)
    w.activity.setStyleSheet('color:'+('#b91c1c' if w.recording or state=='failed' else '#334155')+';padding:4px 0')
    failure=str(w.controller.error) if state=='failed' and w.controller.error else ''
    w.failure_details.setText(failure);w.failure_details.setVisible(bool(failure))
    if failure:
        current=w.controller.current or {}
        for row,(node,*_) in enumerate(w.rows):
            if node.get('_meta',{}).get('id')==current.get('_meta',{}).get('id'):
                item=w.step_list.item(row)
                item.setBackground(QColor('#fee2e2'));item.setToolTip(failure)
    else:
        for row in range(w.step_list.count()):w.step_list.item(row).setBackground(QColor('transparent'))
