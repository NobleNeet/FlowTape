"""Desktop lifecycle and authoring orchestration; command hierarchy lives in ui_surface."""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from PySide6.QtCore import QTimer, QStandardPaths, Qt
from PySide6.QtWidgets import (QApplication, QInputDialog, QMainWindow, QMessageBox,
    QVBoxLayout, QWidget, QFileDialog, QDialog, QMenu)

from . import schema
from .browser import Resolver, open_edge, seconds
from .cli import package
from .errors import AmbiguousPage, UnknownPage
from .errors import FlowTapeError
from .editor import node_map, sequences, walk_nodes, own_content, rename_target, RenameAmbiguity
from .persistence import save_package, journal_path, recover_package
from .player import Player
from .playback import PlaybackController
from .qt_playback import PlaybackWorker
from .recorder import RecorderTransport, propose_target, propose_collections
from .identity import ulid
from .authoring import referenced_targets
from .lifecycle import Preferences, create_package
from .environment import CredentialStore, atomic_yaml, snapshot, credential_reference
from .desktop_dialogs import (NewScenarioDialog, SettingsDialog, CredentialSelectionDialog,
                              CredentialManagerDialog, ManualStepDialog, PageRegistrationDialog)
from .login_authoring import InputEvidence, username_candidate
from .ui_surface import build_surface, update_surface
from .browser_setup import BrowserSetupDialog


def recorder_boundary(method):
    def guarded(self):
        try: return method(self)
        except Exception as exc:
            self.recording=self.picking=False
            self.recorder_error=str(exc) if isinstance(exc,FlowTapeError) else f'Recorder failed ({type(exc).__name__})'
            self.status.setText('記録停止: '+self.recorder_error)
    return guarded

def lifecycle_boundary(method):
    def guarded(self, *args, **kwargs):
        if self.lifecycle_busy: return False
        self.lifecycle_busy = True
        try: return method(self, *args, **kwargs)
        finally: self.lifecycle_busy = False
    return guarded


class FlowTapeWindow(QMainWindow):
    def __init__(self, scenario_path=None, config_path=None, *, preferences_path=None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        preferences_path = preferences_path or (Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation)) / 'FlowTape' / 'preferences.json')
        self.preferences = Preferences(preferences_path)
        self.scenario_path = self.registry_path = None
        self.scenario = self.registry = None
        self.config_path = None
        self.config = self.credentials = None
        self.saved_mtimes = None
        self.deferred_mtimes = None
        self.lifecycle_busy = False
        self.last_browser_check = 0
        self.processing_events = False
        self.dirty = False
        self.driver = None
        self.transport = None
        self.recording = False
        self.picking = False
        self.collection_picking = False
        self.pending_operation = None
        self.pending_credential = None
        self.operation_queue = []
        self.input_evidence = {}
        self.recorder_error = None
        self.record_position = None
        self.binding_name = None
        self.pending_read = None
        self.undo_stack = []
        self.redo_stack = []
        self.confirmed_destructive = False
        self.controller = None
        self.worker = None
        self.pending_close = False
        self.record_after_play = False
        self.continuation_recording = False
        self.just_recorded = False
        self.last_recorded_count = 0
        self.record_start_count = 0
        self.actions = {}
        self.browser_actions = set()
        self.scenario_actions = set()
        self.setWindowTitle("FlowTape")
        self.resize(1050, 650)
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QVBoxLayout(outer)
        file_menu = self.menuBar().addMenu('ファイル')
        for label, method in [('新規シナリオ', self.new_scenario), ('シナリオを開く', self.choose_scenario),
                              ('シナリオを閉じる', self.close_scenario), ('保存', self.save), ('終了', self.close)]:
            action = file_menu.addAction(label)
            action.triggered.connect(lambda checked=False, callback=method: callback())
            self.actions[label] = action
        self.recent_menu = file_menu.addMenu('最近のシナリオ')
        settings_menu = self.menuBar().addMenu('設定')
        for label, method in [('アプリ設定を作成・編集',self.edit_config),('既存 config.yaml を選択',self.choose_config),
                              ('共有認証情報を管理',self.manage_credentials)]:
            action = settings_menu.addAction(label)
            action.triggered.connect(lambda checked=False, callback=method: callback())
        build_surface(self, layout)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.refresh()
        candidate = config_path or self.preferences.config_path
        if candidate: self.load_config(candidate)
        if scenario_path: self.open_scenario(scenario_path)
        elif self.preferences.error: self.status.setText(self.preferences.error)
        self.timer.start()

    def update_actions(self):
        update_surface(self)

    def toggle_record(self):
        if self.recording: self.stop_record()
        else:
            self.continuation_recording = False
            self.record_position = None
            self.start_record()

    def primary_playback(self):
        state = self.controller.state if self.controller else 'idle'
        if state == 'failed': self.retry_playback()
        elif state == 'running' or (self.worker and self.worker.isRunning() and state != 'paused'):
            self.pause_playback()
        else: self.play()

    def choose_playback(self, choice):
        if choice == '1ステップずつ': self.pace_box.setCurrentText('ステップ')
        elif choice == 'ゆっくり':
            delay = self.config['playback']['observation_delay'] if self.config else '1s'
            if seconds(delay) <= 0: delay = '1s'
            index = self.pace_box.findData(delay)
            if index < 0:
                self.pace_box.addItem('ゆっくり ('+delay+')',delay)
                index = self.pace_box.count()-1
            self.pace_box.setCurrentIndex(index)
        else: self.pace_box.setCurrentText('通常')
        if self.controller and self.controller.state == 'paused':
            self.controller.player.config['playback']['observation_delay'] = self.pace_box.currentData() or '0s'
        self.play()

    def show_playback_settings(self): self.playback_settings.exec()

    def show_yaml_details(self):
        self.properties.setVisible(not self.properties.isVisible())
        self.apply_button.setVisible(self.properties.isVisible())

    def validate_scenario(self):
        if self.scenario is None: return
        try:
            schema.scenario(self.scenario);schema.elements(self.registry)
            schema.validate_package(self.scenario,self.registry)
            self.status.setText('シナリオの検証に成功しました')
        except Exception as exc: QMessageBox.warning(self,'シナリオの検証',str(exc))

    def insertion_location(self, row):
        if row < 0: return ('root',),0
        _,parent,index,_ = self.rows[row]
        key = next(key for key,steps in sequences(self.scenario).items() if steps is parent)
        return key,index+1

    def record_at(self, row):
        if self.recording or (self.worker and self.worker.isRunning()): return
        if self.pending_operation or self.operation_queue or self.recorder_error:
            self.status.setText('保留中の記録を確定または破棄してください');return
        self.continuation_recording = False
        self.record_position = self.insertion_location(row)
        self.start_record()
        self.update_actions()

    def manual_add_at(self, row):
        if self.scenario is None: return
        position = self.insertion_location(row)
        names = sorted({name for page in self.registry['pages'].values() for name in page.get('elements',{})})
        dialog = ManualStepDialog(self,names)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            trial = copy.deepcopy(self.scenario)
            key,index = position
            sequences(trial)[key].insert(index,dialog.node)
            self._commit_edit(trial)

    def insertion_menu(self,row):
        menu = QMenu(self)
        action = menu.addAction('＋ 手動で操作を追加')
        action.triggered.connect(lambda:self.manual_add_at(row))
        action.setEnabled(not self.recording and not (self.worker and self.worker.isRunning()))
        action = menu.addAction('● ここから記録')
        action.triggered.connect(lambda:self.record_at(row))
        action.setEnabled(self.driver is not None and not self.recording and not self.pending_operation and not self.operation_queue and not self.recorder_error and not (self.worker and self.worker.isRunning()))
        return menu

    def show_insertion_menu(self,row,position=None):
        if self.scenario is None: return
        menu = self.insertion_menu(row)
        menu.exec(position or self.insert_first_button.mapToGlobal(self.insert_first_button.rect().bottomLeft()))
        menu.deleteLater()

    def step_context_menu(self):
        menu = QMenu(self)
        for key in ('上へ','下へ','削除'):menu.addAction(self.actions[key])
        conditional = menu.addMenu('条件付きにする')
        for key in ('条件で囲む','else へ移す'):conditional.addAction(self.actions[key])
        loops = menu.addMenu('繰り返しにする')
        for key in ('繰り返し','while','for_each'):loops.addAction(self.actions[key])
        menu.addAction(self.actions['解除'])
        menu.addSeparator()
        menu.addAction('この位置の後に追加',lambda:self.show_insertion_menu(self.step_list.currentRow()))
        menu.addAction('YAML・詳細を編集',self.show_yaml_details)
        return menu

    def show_step_context(self,position):
        if self.scenario is None or self.recording: return
        item = self.step_list.itemAt(position)
        if item is not None and not item.isSelected(): self.step_list.setCurrentItem(item)
        menu = self.step_context_menu()
        menu.exec(self.step_list.viewport().mapToGlobal(position));menu.deleteLater()

    def setup_browser(self):
        if self.lifecycle_busy: return
        if not self.resolve_boundary(include_unsaved=False): return
        source = self.config_path or self.preferences.path.with_name('config.yaml')
        try: dialog = BrowserSetupDialog(self,source,self.config)
        except Exception as exc:
            QMessageBox.warning(self,'ブラウザ設定',str(exc));return
        self.lifecycle_busy = True
        try: accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally: self.lifecycle_busy = False
        if accepted and self.save_configuration(dialog.source,dialog.result_document,dialog.original):
            self.open_browser()
        dialog.deleteLater()

    def update_recent(self):
        self.recent_menu.clear()
        self.recent_list.clear()
        for source in self.preferences.recent:
            label = str(Path(source).parent)
            action = self.recent_menu.addAction(label)
            action.triggered.connect(lambda checked=False, p=source: self.open_scenario(p))
            self.recent_list.addItem(label)
            self.recent_list.item(self.recent_list.count()-1).setData(256, source)
        self.recent_menu.setEnabled(bool(self.preferences.recent))

    def shutdown_browser(self):
        for resource, method in [(self.transport, 'close'), (self.driver, 'quit')]:
            if resource is not None:
                try: getattr(resource, method)()
                except Exception: pass
        self.driver = self.transport = None
        self.browser_status.setText('Browser: unavailable')
        self.update_actions()

    @lifecycle_boundary
    def load_config(self, path):
        try:
            source = Path(path).resolve()
            config = schema.config(schema.load_yaml(source), source)
            credential_path = Path(config['credentials']['path'])
            credentials = schema.credentials(schema.load_yaml(credential_path)) if credential_path.exists() else None
        except Exception as exc:
            self.status.setText('設定エラー: '+str(exc))
            if self.driver is None:
                self.browser_status.setText('Browser: unavailable — 設定を確認してください')
            QMessageBox.warning(self, '設定エラー', str(exc))
            return False
        if config == self.config and source == self.config_path and credentials == self.credentials: return True
        restart_required = self._config_restart_required(config)
        if not self._config_boundary(restart_required): return False
        self._install_config(source,config,credentials,restart_required)
        return True

    def _config_restart_required(self,config):
        return self.config is None or any(config[key] != self.config[key] for key in ('browser','driver')) or (
            config['paths']['downloads'] != self.config['paths']['downloads'])

    def _config_boundary(self,restart_required):
        if self.driver is not None and restart_required:
            if QMessageBox.question(self,'設定の変更',
                '設定の変更にはブラウザの再起動が必要です。現在のブラウザ状態を失います。再起動しますか？') != QMessageBox.StandardButton.Yes: return False
        return self.resolve_boundary(include_unsaved=False)

    def _install_config(self,source,config,credentials,restart_required):
        if restart_required: self.shutdown_browser()
        elif self.driver is not None:
            try: self.driver.set_page_load_timeout(seconds(config['timeouts']['page_load']))
            except Exception: self.shutdown_browser()
        self.controller = self.worker = None
        self.config_path,self.config,self.credentials = source,config,credentials
        self.preferences.config_path = str(source)
        self.preferences.save()
        self.status.setText(self.preferences.error or 'アプリ設定を読み込みました')

    @lifecycle_boundary
    def save_configuration(self,path,document,expected):
        try:
            source=Path(path).resolve()
            persisted=copy.deepcopy(document)
            config=schema.config(persisted,source)
            credentials=CredentialStore(config['credentials']['path']).document
            restart_required=self._config_restart_required(config)
            if not self._config_boundary(restart_required): return False
            # Persist only after the user permits any required restart/safe boundary.
            atomic_yaml(source,persisted,expected)
            self._install_config(source,config,credentials,restart_required)
            self.status.setText(self.preferences.error or 'アプリ設定を保存しました')
            return True
        except Exception as exc:
            QMessageBox.warning(self,'設定の保存',str(exc))
            return False

    def edit_config(self):
        if self.lifecycle_busy: return
        source=self.config_path or self.preferences.path.with_name('config.yaml')
        try: dialog=SettingsDialog(self,source,self.config)
        except Exception as exc:
            QMessageBox.warning(self,'アプリ設定',str(exc));return
        self.lifecycle_busy=True
        try: accepted=dialog.exec()==QDialog.DialogCode.Accepted
        finally:self.lifecycle_busy=False
        if not accepted:return
        source=Path(dialog.source.text()).resolve()
        expected=dialog.original if source==dialog.loaded_source else snapshot(source)
        if source!=dialog.loaded_source and expected is not None:
            if QMessageBox.question(self,'設定の保存','選択した既存 config を更新しますか？')!=QMessageBox.StandardButton.Yes:return
        if self.save_configuration(source,dialog.result_document,expected):self.open_browser()

    @lifecycle_boundary
    def manage_credentials(self):
        if self.config is None:
            self.status.setText('先にアプリ設定で共有 credentials.yaml の保存先を指定してください');return
        if not self.resolve_boundary(include_unsaved=False):return
        try:
            store=CredentialStore(self.config['credentials']['path'])
            dialog=CredentialManagerDialog(self,store)
            dialog.exec()
            self.credentials=store.document
            # Updated store is used by the next fresh playback; never rewrite scenarios.
            self.controller=self.worker=None
        except Exception as exc:QMessageBox.warning(self,'認証情報',str(exc))

    def resolve_secret_input(self):
        if self.config is None:
            self.status.setText('アプリ設定で共有認証情報の保存先を指定してください');return None
        previous=self.processing_events
        self.processing_events=True
        dialog=None
        try:
            store=CredentialStore(self.config['credentials']['path'])
            dialog=CredentialSelectionDialog(self,store)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return None
            group,key=dialog.selection
            if dialog.new.isChecked():
                store.add(group,dialog.username.text(),dialog.password.text())
            else:
                store.reload()
                if key not in store.groups.get(group,{}):
                    raise FlowTapeError('認証情報のキーが見つかりません。選び直してください。')
            reference=credential_reference(group,key)
            self.credentials=store.document
            return reference,group,store.groups[group]
        except Exception as exc:
            QMessageBox.warning(self,'認証情報',str(exc));return None
        finally:
            if dialog is not None:dialog.username.clear();dialog.password.clear()
            self.processing_events=previous

    def choose_config(self):
        source, _ = QFileDialog.getOpenFileName(self, 'アプリ設定を選択',
            str(self.config_path or Path.cwd()), 'YAML (*.yaml *.yml)')
        if source and self.load_config(source): self.open_browser()

    def resolve_boundary(self, *, include_unsaved=True):
        """Resolve activity and unsaved state before relinquishing its package."""
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, '再生中', '再生を停止して続行しますか？') != QMessageBox.StandardButton.Yes:
                return False
            self.record_after_play = False
            self.controller.stop()
            self.worker.confirm(False)
            if not self.worker.wait(3000):
                self.status.setText('再生の停止を待っています。停止後にもう一度操作してください')
                return False
        if self.recording or self.picking:
            if QMessageBox.question(self, '記録・選択中', '記録・選択を停止して続行しますか？') != QMessageBox.StandardButton.Yes:
                return False
            if self.recording:
                self.stop_record()
            else:
                try:
                    self.picking = self.collection_picking = False
                    self.operation_queue.extend(self.transport.stop())
                    self._process_operations()
                except Exception as exc: self.recorder_error = str(exc)
        if self.pending_operation or self.operation_queue or self.recorder_error:
            if QMessageBox.question(self, '未確定の記録',
                '未確定の記録を破棄して続行しますか？（いいえで戻って確定できます）') != QMessageBox.StandardButton.Yes:
                return False
            try:
                if self.transport: self.transport.reset()
            except Exception as exc:
                self.status.setText('記録のリセットに失敗しました: '+str(exc))
                return False
            self.pending_operation = None
            self.pending_credential = None
            self.operation_queue.clear()
            self.recorder_error = None
        if include_unsaved and self.dirty:
            choice, ok = QInputDialog.getItem(self, '未保存の変更', '現在のシナリオに未保存の変更があります',
                ['保存して続行', '変更を破棄して続行', 'キャンセル'], editable=False)
            if not ok or choice == 'キャンセル': return False
            if choice == '保存して続行' and not self.save(): return False
        return True

    def unload_scenario(self):
        # Stop observing raw events at an explicit boundary; retain the Edge session.
        if self.transport:
            try: self.transport.reset()
            except Exception:
                # Browser loss cannot make package inspection/editing unavailable.
                self.shutdown_browser()
        self.scenario = self.registry = None
        self.scenario_path = self.registry_path = None
        self.controller = self.worker = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.recording = self.picking = self.collection_picking = False
        self.pending_operation = self.pending_credential = self.record_position = self.binding_name = self.pending_read = None
        self.operation_queue.clear()
        self.input_evidence.clear()
        self.recorder_error = None
        self.confirmed_destructive = self.record_after_play = self.pending_close = False
        self.continuation_recording = self.just_recorded = False
        self.dirty = False
        self.saved_mtimes = self.deferred_mtimes = None
        self.refresh()

    @lifecycle_boundary
    def close_scenario(self):
        if self.scenario is None: return True
        if not self.resolve_boundary(): return False
        try: self.unload_scenario()
        except Exception as exc:
            QMessageBox.warning(self, 'シナリオを閉じる', str(exc))
            return False
        self.status.setText('シナリオを閉じました')
        return True

    def _activate(self, source, scenario, registry):
        self.unload_scenario()
        self.scenario_path = Path(source).resolve()
        self.registry_path = self.scenario_path.with_name('elements.yaml')
        self.scenario, self.registry = scenario, registry
        self._ensure_ids(self.scenario['steps'])
        self.saved_mtimes = self._mtimes()
        self.preferences.remember(self.scenario_path)
        self.refresh()
        self.status.setText(self.preferences.error or 'シナリオを開きました')

    @lifecycle_boundary
    def open_scenario(self, path):
        source = Path(path).resolve()
        if source.is_dir(): source /= 'scenario.yaml'
        if not source.exists() and not journal_path(source).exists():
            QMessageBox.warning(self, 'シナリオを開く', f'シナリオが見つかりません: {source}')
            if str(source) in self.preferences.recent:
                if QMessageBox.question(self, '最近のシナリオ', '存在しない項目を一覧から削除しますか？') == QMessageBox.StandardButton.Yes:
                    self.preferences.forget(source)
                    self.update_recent()
            return False
        if not self.resolve_boundary(): return False
        try:
            if journal_path(source).exists():
                choice, ok = QInputDialog.getItem(self, '保存の復旧', '中断した保存を検出しました。復旧を選択してください',
                    ['保存前に戻す', '保存を完了する', 'キャンセル'], editable=False)
                if not ok or choice == 'キャンセル': return False
                recover_package(source, 'rollback' if choice == '保存前に戻す' else 'complete')
            scenario, registry = package(str(source))
            self._activate(source, scenario, registry)
            return True
        except Exception as exc:
            QMessageBox.warning(self, 'シナリオを開く', str(exc))
            return False

    def choose_scenario(self):
        source=QFileDialog.getExistingDirectory(self,'シナリオパッケージを開く',
            self.config['paths']['scenarios'] if self.config else str(Path.cwd()))
        if source:self.open_scenario(source)

    def new_scenario(self):
        if self.lifecycle_busy:return
        dialog=NewScenarioDialog(self,self.config['paths']['scenarios'] if self.config else Path.cwd())
        self.lifecycle_busy=True
        try:accepted=dialog.exec()==QDialog.DialogCode.Accepted
        finally:self.lifecycle_busy=False
        if accepted:return self.create_scenario(dialog.name.text().strip(),dialog.destination)
        return False

    @lifecycle_boundary
    def create_scenario(self, name, destination):
        if not self.resolve_boundary(): return False
        try:
            source = create_package(name, destination)
            scenario, registry = package(str(source))
            self._activate(source, scenario, registry)
            return True
        except Exception as exc:
            QMessageBox.warning(self, '新規シナリオ', str(exc))
            return False

    def _mtimes(self):
        if self.scenario_path is None: return None
        return tuple(p.stat().st_mtime_ns if p.exists() else None for p in (self.scenario_path, self.registry_path))

    def _ensure_ids(self, steps):
        for node in steps:
            node.setdefault("_meta", {"id": ulid()})
            if "if" in node:
                self._ensure_ids(node["then"])
                self._ensure_ids(node.get("else", []))
            for key in ("repeat", "while", "for_each"):
                if key in node:
                    self._ensure_ids(node[key]["steps"])

    def _browser_available(self):
        if self.worker and self.worker.isRunning():
            self.status.setText("再生を停止してからブラウザを編集してください")
            return False
        return True

    def _checkpoint(self):
        self.undo_stack.append((copy.deepcopy(self.scenario), copy.deepcopy(self.registry)))
        self.redo_stack.clear()

    def _changed(self):
        self.dirty = True
        self.refresh()

    def refresh(self):
        self.update_actions()
        self.update_recent()
        if self.scenario is None:
            self.rows = []
            self.step_list.clear()
            self.properties.clear()
            self.setWindowTitle('FlowTape — シナリオなし')
            return
        self.mode_box.blockSignals(True)
        self.mode_box.setCurrentText(self.scenario.get('mode','実行'))
        self.mode_box.blockSignals(False)
        current_id = None
        row = self.step_list.currentRow()
        if hasattr(self, "rows") and 0 <= row < len(self.rows):
            current_id = self.rows[row][0]["_meta"]["id"]
        self.step_list.clear()
        self.rows = []
        def add(steps, depth=0, branch=''):
            for index, node in enumerate(steps):
                label = node.get("action", next((k for k in ("if", "repeat", "while", "for_each") if k in node), "?"))
                detail = node.get("target", node.get("description", ""))
                if 'description' in node: summary = node['description']
                elif label in {'click','double_click','hover','input','select','upload'}:
                    summary = detail + ' を ' + {'click':'クリック','double_click':'ダブルクリック','hover':'ポイント','input':'入力','select':'選択','upload':'アップロード'}[label]
                elif label == 'open': summary = node['url']+' を開く'
                elif label in {'back','forward','refresh','close_window'}:summary={'back':'前のページへ戻る','forward':'次のページへ進む','refresh':'ページを再読み込み','close_window':'現在のタブを閉じる'}[label]
                elif label == 'if':summary=str(node['if'].get('exists',node.get('description','条件')))+' の場合'
                elif label == 'while':summary=str(node['while'].get('exists','条件を満たす'))+' 間、繰り返す'
                elif label == 'read': summary = f"{detail} から {node['into']} へ取得"
                elif label == 'append': summary = f"{node['output']} に出力"
                elif label == 'repeat': summary = f"{node['repeat']['count']} 回繰り返す"
                elif label == 'for_each': summary = f"{node['for_each']['target']} の各対象について"
                else: summary = f'{label} {detail}'.strip()
                if node.get('enabled') is False: summary = '[無効] ' + summary
                if node.get('risk') == '破壊的': summary = '[破壊的] ' + summary
                self.rows.append((node, steps, index, depth))
                self.step_list.addItem(f"{len(self.rows):02d}  {'│   ' * depth}{branch}{summary}")
                if node["_meta"]["id"] == current_id:
                    self.step_list.setCurrentRow(len(self.rows) - 1)
                if "if" in node:
                    add(node["then"], depth + 1, 'then: ')
                    add(node.get("else", []), depth + 1, 'else: ')
                for kind in ("repeat", "while", "for_each"):
                    if kind in node: add(node[kind]["steps"], depth + 1)
        add(self.scenario["steps"])
        if self.rows and self.step_list.currentRow()<0:self.step_list.setCurrentRow(0)
        self.setWindowTitle(f"FlowTape — {self.scenario['name']}{' *' if self.dirty else ''}")
        self.update_actions()
        self.show_properties(self.step_list.currentRow())

    def show_properties(self, row):
        selected = 0 <= row < len(getattr(self,'rows',[]))
        node = self.rows[row][0] if selected else None
        self.properties.setPlainText(yaml.safe_dump(node,allow_unicode=True,sort_keys=False) if selected else '')
        self.selection_summary.setText(self.step_list.item(row).text().strip() if selected else '操作を選択すると、内容と対象を確認できます。')
        names = sorted(referenced_targets({'steps':[node]})) if selected else []
        known = {name for page in self.registry['pages'].values() for name in page.get('elements',{})} if self.registry else set()
        missing = set(names)-known
        self.target_summary.setText(('対象: '+ '、'.join(names)+'\n'+('未登録 — ブラウザで指定してください' if missing else '登録済み — 実際の解決結果は診断で確認できます')) if names else '')
        self.target_controls.setVisible(bool(names) and not self.recording)
        self.target_button.setText('ブラウザで指定' if missing else 'ブラウザで再指定')
        self.yaml_button.setEnabled(selected)

    def _validate_edit(self, trial, registry):
        self._ensure_ids(trial["steps"])
        schema.scenario(trial)
        schema.elements(registry)
        schema.validate_package(trial, registry)
        if self.controller and self.controller.state not in {"complete", "stopped"}:
            try:
                if registry != self.registry and self.controller.executed_ids:
                    changed_names = set()
                    identification_changed = False
                    for page in self.registry['pages'].keys() | registry['pages'].keys():
                        old, new = self.registry['pages'].get(page,{}), registry['pages'].get(page,{})
                        identification_changed |= old.get('identify') != new.get('identify')
                        for kind in ('elements','collections'):
                            for name in old.get(kind,{}).keys() | new.get(kind,{}).keys():
                                if old.get(kind,{}).get(name) != new.get(kind,{}).get(name): changed_names.add(name)
                    def contains_changed(value):
                        if isinstance(value,dict): return any(contains_changed(v) for v in value.values())
                        if isinstance(value,list): return any(contains_changed(v) for v in value)
                        return isinstance(value,str) and value in changed_names
                    executed = node_map(self.scenario)
                    if identification_changed or any(contains_changed(own_content(executed[i])) for i in self.controller.executed_ids if i in executed):
                        raise RuntimeError('実行済み Step の DOM 定義が変更されました。ブラウザは旧定義で操作された状態です')
                self.controller.replace_scenario(trial)
            except Exception as exc:
                if self.worker and self.worker.isRunning() and self.controller.state != "paused":
                    raise RuntimeError("再生を一時停止してから編集してください")
                choice, accepted = QInputDialog.getItem(self, "実行済みの変更", str(exc), ["最初から再実行", "現在の状態で続行", "キャンセル"], editable=False)
                if not accepted or choice == "キャンセル": return False
                if choice == "最初から再実行": self.controller.stop()
                else: self.controller.replace_scenario(trial, allow_executed=True)
        return True

    def _commit_edit(self, trial, registry=None):
        registry = self.registry if registry is None else registry
        try:
            if not self._validate_edit(trial, registry): return False
        except Exception as exc:
            QMessageBox.warning(self, "検証エラー", str(exc))
            return False
        self._checkpoint()
        self.scenario, self.registry = trial, registry
        if self.controller: self.controller.player.resolver.pages = registry["pages"]
        self._changed()
        return True

    def _insert_node(self, node, *, recording=False):
        trial = copy.deepcopy(self.scenario)
        if recording and self.record_position:
            key, index = self.record_position
        else:
            row = self.step_list.currentRow()
            if not recording and 0 <= row < len(self.rows):
                _, parent, index, _ = self.rows[row]
                key = next(key for key, steps in sequences(self.scenario).items() if steps is parent)
                index += 1
            else: key, index = ('root',), len(trial['steps'])
        steps = sequences(trial).get(key)
        if steps is None:
            QMessageBox.warning(self, '挿入位置', '記録開始位置のブロックがありません')
            return False
        steps.insert(index, dict(node, _meta={'id':ulid()}))
        result = self._commit_edit(trial)
        if result and recording and self.record_position: self.record_position = (key,index+1)
        return result

    def author_read(self):
        names = sorted({name for page in self.registry['pages'].values() for name in page.get('elements',{})})
        target, ok = QInputDialog.getItem(self, 'read', 'target', names+['ブラウザから選択'], editable=False)
        if not ok: return
        source, ok = QInputDialog.getItem(self, 'read', '取得元', ['text','value','attribute'], editable=False)
        if not ok: return
        if source == 'attribute':
            attr, ok = QInputDialog.getText(self, 'read', '属性名')
            if not ok or not attr: return
            source = {'attribute':attr}
        into, ok = QInputDialog.getText(self, 'read', '保存する変数名')
        if not ok: return
        if target == 'ブラウザから選択':
            self.start_pick()
            if self.picking: self.pending_read={'action':'read','source':source,'into':into}
        else: self._insert_node({'action':'read','target':target,'source':source,'into':into})

    def edit_outputs(self):
        text, ok = QInputDialog.getMultiLineText(self, 'outputs', '出力定義 (YAML)', yaml.safe_dump(self.scenario.get('outputs',{}), allow_unicode=True, sort_keys=False))
        if not ok: return
        try:
            trial = copy.deepcopy(self.scenario)
            trial['outputs'] = yaml.safe_load(text)
            self._commit_edit(trial)
        except Exception as exc: QMessageBox.warning(self, 'outputs', str(exc))

    def author_append(self):
        outputs = self.scenario.get('outputs',{})
        if not outputs:
            self.status.setText('outputs から出力先を定義してください')
            return
        name, ok = QInputDialog.getItem(self, 'append', '出力先', list(outputs), editable=False)
        if not ok: return
        spec = outputs[name]
        node = {'action':'append','output':name}
        if spec['format'] == 'csv':
            example = {column:'${'+column+'}' for column in spec['columns']}
            text, ok = QInputDialog.getMultiLineText(self,'append','列の値 (YAML)',yaml.safe_dump(example,allow_unicode=True,sort_keys=False))
            if not ok: return
            try: node['values'] = yaml.safe_load(text)
            except Exception as exc:
                QMessageBox.warning(self,'append',str(exc));return
        else:
            text, ok = QInputDialog.getMultiLineText(self,'append','value または values を YAML で指定', 'value: ${result}')
            if not ok: return
            try: node.update(yaml.safe_load(text))
            except Exception as exc:
                QMessageBox.warning(self,'append',str(exc));return
        self._insert_node(node)

    def bind_selected(self):
        row = self.step_list.currentRow()
        if not 0 <= row < len(self.rows): return
        node = self.rows[row][0]
        targets = sorted(referenced_targets({'steps':[node]}))
        if not targets:
            self.status.setText('target を参照する Step を選択してください')
            return
        target = targets[0]
        if len(targets)>1:
            target, ok = QInputDialog.getItem(self,'対象を指定','対象の名前',targets,editable=False)
            if not ok:return
        self.start_pick()
        if self.picking:
            self.binding_name = target
            self.transport.inject('rebind')
            self.status.setText(f'{target} に対応する対象を選択してください')

    def bind_missing(self):
        known = {name for page in self.registry['pages'].values() for name in page.get('elements',{})}
        missing = sorted(referenced_targets(self.scenario)-known)
        if not missing:
            self.status.setText('すべての論理名に定義があります。ページ別の解決は診断で確認できます')
            return
        target, ok = QInputDialog.getItem(self,'未登録 target',f'{len(missing)} 件の未登録 target',missing,editable=False)
        if not ok:return
        self.start_pick()
        if self.picking:
            self.binding_name=target
            self.transport.inject('rebind')

    def diagnose_selected(self):
        if not self._browser_available() or not self.driver: return
        row = self.step_list.currentRow()
        if not 0 <= row < len(self.rows): return
        node = self.rows[row][0]
        target = node.get('target') or node.get('for_each',{}).get('target')
        if not target: return
        resolver = Resolver(self.driver,self.registry)
        reason = '一意に解決しました'
        try:
            if 'for_each' in node: resolver.collection(node['for_each']['target'])
            else: resolver.target(target,node.get('action',''))
        except Exception as exc: reason = str(exc)
        QMessageBox.information(self, 'DOM 診断', reason + '\n' + yaml.safe_dump(resolver.diagnostics, allow_unicode=True, sort_keys=False))

    def _move(self, offset):
        span = self._selection()
        if not span: return
        key, start, end = span
        trial = copy.deepcopy(self.scenario)
        steps = sequences(trial)[key]
        destination = start + offset
        if destination < 0 or end + offset > len(steps): return
        children = steps[start:end]
        del steps[start:end]
        steps[destination:destination] = children
        self._commit_edit(trial)

    def move_up(self): self._move(-1)
    def move_down(self): self._move(1)

    def apply_properties(self):
        row = self.step_list.currentRow()
        if row < 0: return
        try:
            old = self.rows[row][0]
            node = yaml.safe_load(self.properties.toPlainText())
            if not isinstance(node, dict): raise ValueError("Step は YAML mapping で指定してください")
            node["_meta"] = copy.deepcopy(old["_meta"])
            trial = copy.deepcopy(self.scenario)
            dest = node_map(trial)[old["_meta"]["id"]]
            dest.clear()
            dest.update(node)
            self._commit_edit(trial)
        except Exception as exc:
            QMessageBox.warning(self, "検証エラー", str(exc))

    def _selection(self):
        rows = sorted({index.row() for index in self.step_list.selectedIndexes()})
        selected = []
        covered = set()
        for row in rows:
            item = self.rows[row]
            if item[0]["_meta"]["id"] in covered: continue
            selected.append(item)
            covered.update(n["_meta"]["id"] for n in walk_nodes([item[0]]) if n is not item[0])
        if not selected:
            QMessageBox.warning(self, "範囲", "連続した Step を選択してください")
            return None
        parent = selected[0][1]
        indices = [item[2] for item in selected]
        if any(item[1] is not parent for item in selected) or indices != list(range(indices[0], indices[-1] + 1)):
            QMessageBox.warning(self, "範囲", "同じブロック内の連続した Step を選択してください")
            return None
        key = next(key for key, steps in sequences(self.scenario).items() if steps is parent)
        return key, indices[0], indices[-1] + 1

    def _wrap(self, kind, options):
        span = self._selection()
        if not span: return
        key, start, end = span
        trial = copy.deepcopy(self.scenario)
        steps = sequences(trial)[key]
        children = steps[start:end]
        node = {"if": options, "then": children} if kind == "if" else {kind: dict(options, steps=children)}
        node["_meta"] = {"id": ulid()}
        steps[start:end] = [node]
        self._commit_edit(trial)

    def wrap_if(self):
        target, ok = QInputDialog.getText(self, "条件", "存在する target 名")
        if ok and target: self._wrap("if", {"exists": target})

    def move_to_else(self):
        span=self._selection()
        if not span:return
        key,start,end=span
        trial=copy.deepcopy(self.scenario)
        steps=sequences(trial)[key]
        if start==0 or 'if' not in steps[start-1]:
            self.status.setText('直前に if がある連続範囲を選択してください')
            return
        steps[start-1].setdefault('else',[]).extend(steps[start:end])
        del steps[start:end]
        self._commit_edit(trial)

    def wrap_repeat(self):
        count, ok = QInputDialog.getInt(self, "繰り返し", "回数", 2, 1, 100000)
        if ok: self._wrap("repeat", {"count": count})

    def wrap_while(self):
        target, ok = QInputDialog.getText(self, "条件を満たす間", "存在する target 名")
        if ok and target: self._wrap("while", {"exists": target})

    def wrap_for_each(self):
        choices = sorted({name for page in self.registry["pages"].values() for name in page.get("collections", {})})
        if not choices:
            QMessageBox.warning(self, "繰り返し対象", "collection を登録してください")
            return
        target, ok = QInputDialog.getItem(self, "各対象について", "collection", choices, editable=False)
        if not ok: return
        name, ok = QInputDialog.getText(self, "各対象について", "ループ変数名", text="row")
        if ok: self._wrap("for_each", {"target": target, "as": name})

    def add_step(self):
        text, ok = QInputDialog.getMultiLineText(self, "Step追加", "Step (YAML)", "action: click\ntarget: 対象\n")
        if not ok: return
        try:
            node = yaml.safe_load(text)
            trial = copy.deepcopy(self.scenario)
            row = self.step_list.currentRow()
            if row >= 0:
                _, parent, index, _ = self.rows[row]
                key = next(key for key, steps in sequences(self.scenario).items() if steps is parent)
                sequences(trial)[key].insert(index + 1, node)
            else: trial["steps"].append(node)
            self._commit_edit(trial)
        except Exception as exc: QMessageBox.warning(self, "Step", str(exc))

    def delete_steps(self):
        span = self._selection()
        if not span: return
        key, start, end = span
        trial = copy.deepcopy(self.scenario)
        del sequences(trial)[key][start:end]
        self._commit_edit(trial)

    def unwrap(self):
        row = self.step_list.currentRow()
        if row < 0: return
        node, parent, index, _ = self.rows[row]
        if "action" in node: return
        if "if" in node and node.get("else"):
            branch, ok = QInputDialog.getItem(self, "条件解除", "残すブランチ", ["then", "else", "両方"], editable=False)
            if not ok: return
            children = node["then"] + node["else"] if branch == "両方" else node[branch]
        elif "if" in node: children = node["then"]
        else:
            kind = next(k for k in ("repeat", "while", "for_each") if k in node)
            children = node[kind]["steps"]
        key = next(key for key, steps in sequences(self.scenario).items() if steps is parent)
        trial = copy.deepcopy(self.scenario)
        sequences(trial)[key][index:index+1] = copy.deepcopy(children)
        self._commit_edit(trial)

    def rename_registered_target(self):
        pages = list(self.registry["pages"])
        if not pages: return
        page, ok = QInputDialog.getItem(self, "名前変更", "page", pages, editable=False)
        if not ok: return
        names = list(self.registry["pages"][page].get("elements", {}))
        if not names: return
        old, ok = QInputDialog.getItem(self, "名前変更", "target", names, editable=False)
        if not ok: return
        new, ok = QInputDialog.getText(self, "名前変更", "新しい名前", text=old)
        if not ok or new == old: return
        decisions = {}
        try:
            try: trial, registry = rename_target(self.scenario, self.registry, page, old, new)
            except RenameAmbiguity as exc:
                for location in exc.locations:
                    answer = QMessageBox.question(self, "参照ページ確認", f"{location} の {old} は page {page} の target ですか？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                    if answer == QMessageBox.StandardButton.Cancel: return
                    decisions[location] = answer == QMessageBox.StandardButton.Yes
                trial, registry = rename_target(self.scenario, self.registry, page, old, new, decisions)
            self._commit_edit(trial, registry)
        except Exception as exc: QMessageBox.warning(self, "名前変更", str(exc))

    def undo(self):
        if not self.undo_stack: return
        scenario, registry = copy.deepcopy(self.undo_stack[-1])
        try:
            if not self._validate_edit(scenario, registry): return
        except Exception as exc:
            QMessageBox.warning(self,'戻す',str(exc));return
        self.redo_stack.append((copy.deepcopy(self.scenario), copy.deepcopy(self.registry)))
        self.undo_stack.pop()
        self.scenario, self.registry = scenario, registry
        if self.controller: self.controller.player.resolver.pages = registry['pages']
        self._changed()

    def redo(self):
        if not self.redo_stack: return
        scenario, registry = copy.deepcopy(self.redo_stack[-1])
        try:
            if not self._validate_edit(scenario, registry): return
        except Exception as exc:
            QMessageBox.warning(self,'やり直す',str(exc));return
        self.undo_stack.append((copy.deepcopy(self.scenario), copy.deepcopy(self.registry)))
        self.redo_stack.pop()
        self.scenario, self.registry = scenario, registry
        if self.controller: self.controller.player.resolver.pages = registry['pages']
        self._changed()

    def open_browser(self):
        if not self._browser_available(): return
        if self.driver: return
        if self.config is None:
            self.browser_status.setText('Browser: unavailable — セットアップからEdgeに接続してください')
            return
        try:
            self.driver = open_edge(self.config)
            self.transport = RecorderTransport(self.driver)
            self.transport.inject('observe')
            self.controller = None
            self.confirmed_destructive = self.record_after_play = False
            self.timer.start()
            self.status.setText("Edge 起動済み")
            self.browser_status.setText("Browser: ready — Edge 接続済み")
        except Exception as exc:
            self.shutdown_browser()
            self.status.setText('Edge 起動失敗: '+str(exc))
            self.browser_status.setText('Browser: unavailable — '+str(exc)+'（ブラウザから再試行／設定から変更）')
        self.update_actions()

    def open_url(self):
        if not self._browser_available(): return
        self.open_browser()
        if not self.driver: return
        url, ok = QInputDialog.getText(self, "URL", "URL")
        if not ok or not url: return
        self.driver.get(url)
        if self.scenario is not None: self._insert_node({'action':'open','url':url},recording=True)

    @recorder_boundary
    def start_record(self):
        if self.scenario is None or self.driver is None: return
        if not self._browser_available(): return
        if self.recorder_error:
            if QMessageBox.question(self,'記録の同期回復','不確かな区間の未確定イベントを破棄し、新しい記録境界から開始しますか？') != QMessageBox.StandardButton.Yes: return
            self.transport.reset()
            self.pending_operation=None
            self.pending_credential=None
            self.operation_queue.clear()
            self.recorder_error=None
        if self.pending_operation or self.operation_queue:
            self.status.setText('保留中の記録を確定または破棄してから記録を開始してください')
            return
        self.open_browser()
        if not self.driver: return
        self.record_start_count = sum(1 for node in walk_nodes(self.scenario["steps"]) if "action" in node)
        self.just_recorded = False
        self.recording = True
        self.picking = False
        self.transport.inject("record")
        self.status.setText("記録中 — Edgeを操作してください")
        self.update_actions()

    def start_insertion_record(self):
        row = self.step_list.currentRow()
        if not 0 <= row < len(self.rows): return
        _, parent, index, _ = self.rows[row]
        key = next(key for key, steps in sequences(self.scenario).items() if steps is parent)
        self.record_position = (key,index+1)
        self.start_record()

    @recorder_boundary
    def stop_record(self):
        if not self.recording or not self.transport: return
        self.recording = False
        self.operation_queue.extend(self.transport.stop())
        self._process_operations()
        if not self.pending_operation and not self.operation_queue: self.record_position = None
        self.last_recorded_count = max(0,sum(1 for node in walk_nodes(self.scenario["steps"]) if "action" in node)-self.record_start_count)
        self.just_recorded = not self.pending_operation and not self.operation_queue
        self.continuation_recording = False
        self.status.setText("記録を終了しました。再生して動作を確認できます。")
        self.show_properties(self.step_list.currentRow())
        self.update_actions()

    def _process_operations(self):
        while self.operation_queue and self.pending_operation is None:
            self._operation(self.operation_queue.pop(0))
        if not self.recording and not self.operation_queue and not self.pending_operation:
            self.record_position = None

    def discard_pending(self):
        if not self.pending_operation and not self.operation_queue and not self.recorder_error: return
        if QMessageBox.question(self,'未確定の記録','未確定の操作を破棄しますか？') != QMessageBox.StandardButton.Yes: return
        self.pending_operation = None
        self.pending_credential = None
        self.operation_queue.clear()
        self.record_position = None
        if self.recorder_error:
            self.transport.reset()
            self.recorder_error=None
        self.status.setText('未確定の記録を破棄しました')

    @recorder_boundary
    def start_pick(self):
        if self.scenario is None or self.driver is None: return
        if not self._browser_available(): return
        self.open_browser()
        if not self.driver: return
        self.picking = True
        self.collection_picking = False
        self.binding_name = None
        self.recording = False
        self.transport.inject("pick")
        self.status.setText("ブラウザで対象を選択してください")

    def start_collection_pick(self):
        self.start_pick()
        if self.picking:
            self.collection_picking = True
            self.transport.inject('collection_pick')
            self.status.setText('繰り返し対象の代表行・項目を選択してください')

    def _collection_operation(self, op):
        page = self._page()
        if not page: return
        resolver = Resolver(self.driver, self.registry)
        try:
            choices = propose_collections(op, resolver)
            if not choices: raise ValueError('collection 候補がありません。代表行・項目を選び直してください')
            labels = [f"{len(members)} 件: {definition['locate'][0]}" for definition, members in choices]
            label, ok = QInputDialog.getItem(self, 'collection 候補', '件数と locator を確認', labels, editable=False)
            if not ok: return
            definition, members = choices[labels.index(label)]
            resolver.js('window.__flowtape.highlight(arguments[0]);', members)
            preview = '\n'.join(resolver.js('return FT.norm(arguments[0].innerText || arguments[0].textContent).slice(0,80);', el) for el in members[:5])
            if QMessageBox.question(self, 'collection 確認', f'{len(members)} 件\n{preview}\nこの集合を登録しますか？') != QMessageBox.StandardButton.Yes: return
            name, ok = QInputDialog.getText(self, 'collection 名', '論理名', text='行' if definition['expect']['tag']=='tr' else '項目')
            if not ok or not name: return
            trial = copy.deepcopy(self.registry)
            existing = trial['pages'][page].get('collections',{}).get(name)
            if existing and QMessageBox.question(self, 'collection', '既存定義を置き換えますか？') != QMessageBox.StandardButton.Yes: return
            trial['pages'][page].setdefault('collections',{})[name] = definition
            self._commit_edit(copy.deepcopy(self.scenario), trial)
        except Exception as exc:
            QMessageBox.warning(self, 'collection', str(exc))
        finally:
            try: resolver.js('window.__flowtape?.clearHighlights();')
            except Exception: pass

    def poll(self):
        if self.worker and self.worker.isRunning():
            self.update_actions()
            return
        if self.processing_events or self.lifecycle_busy: return
        self.processing_events = True
        try:
            if self.driver is not None and time.monotonic()-self.last_browser_check >= 1:
                self.last_browser_check = time.monotonic()
                try:
                    if not self.driver.window_handles: raise RuntimeError('制御ブラウザが閉じられました')
                except Exception:
                    if self.recording or self.picking:
                        self.recorder_error = 'ブラウザとの接続が失われました。未確定の記録を確認してください'
                    self.recording = self.picking = False
                    self.shutdown_browser()
                    self.browser_status.setText('Browser: unavailable — 接続が失われました。ブラウザから再試行してください')
            self._poll_events()
        finally:
            self.processing_events = False
            self.update_actions()

    def _poll_events(self):
        if self.scenario is None: return
        changed = self._mtimes()
        if changed != self.saved_mtimes and changed != self.deferred_mtimes:
            self.reconcile_external()
        if self.pending_operation and self.pending_credential is None and not self.picking and self.driver and self.driver.current_url == self.pending_operation.url:
            self.picking = True
            self.transport.inject('rebind')
            self.status.setText('遷移前に操作した対象を再選択してください。元の操作へ紐付けます')
        self._process_operations()
        if not (self.recording or self.picking): return
        try:
            for op in self.transport.drain():
                if op.action in {'pick','picker_cancel'}: self._operation(op)
                else: self.operation_queue.append(op)
            self._process_operations()
        except Exception as exc:
            self.recording = self.picking = False
            self.recorder_error = str(exc)
            self.status.setText("記録停止: " + str(exc))

    def reconcile_external(self):
        changed = self._mtimes()
        if changed == self.saved_mtimes: return True
        choice, ok = QInputDialog.getItem(self, '外部変更',
            'scenario / elements が外部で変更されました。未保存の GUI 変更も考慮して選択してください',
            ['外部ファイルを再読込','GUI の内容を保持し、次回保存で上書き','今回保留'], editable=False)
        if not ok or choice == '今回保留':
            self.deferred_mtimes = changed
            self.status.setText('外部変更があります。保存前に再確認します')
            return False
        if choice == '外部ファイルを再読込':
            try:
                trial, registry = package(str(self.scenario_path))
                if not self._commit_edit(trial, registry): return False
                self.dirty = False
                self.saved_mtimes = changed
                self.deferred_mtimes = None
                self.refresh()
                self.status.setText('外部ファイルを再読込しました。戻す操作で GUI の編集を復元できます')
            except Exception as exc:
                QMessageBox.warning(self,'外部変更',str(exc))
            return False
        self.saved_mtimes = changed
        self.deferred_mtimes = None
        self.dirty = True
        self.refresh()
        return True

    def _page(self):
        try:
            return Resolver(self.driver, self.registry).identify()
        except AmbiguousPage as exc:
            QMessageBox.warning(self, "PageDefinition", str(exc))
            return None
        except UnknownPage:
            parsed = urlsplit(self.driver.current_url)
            proposed = (Path(parsed.path).stem or self.driver.title or "page").replace(" ", "_")
            path = parsed.path or "/"
            suggestion = {"url": {"contains": path}} if path != "/" else {"url": {"equals": self.driver.current_url}}
            dialog = PageRegistrationDialog(self,proposed,suggestion)
            if dialog.exec() != QDialog.DialogCode.Accepted: return None
            page_id,suggestion = dialog.name.text().strip(),dialog.identify
            trial = copy.deepcopy(self.registry)
            if page_id in trial["pages"]:
                QMessageBox.warning(self, "PageDefinition", "既存の page ID です")
                return None
            trial["pages"][page_id] = {"identify": suggestion, "elements": {}}
            schema.elements(trial)
            try:
                if Resolver(self.driver, trial).identify() != page_id:
                    raise AmbiguousPage("proposed page is not unique")
            except (AmbiguousPage, UnknownPage) as exc:
                QMessageBox.warning(self, "PageDefinition", str(exc))
                return None
            if not self._commit_edit(copy.deepcopy(self.scenario),trial): return None
            return page_id

    def _operation(self, op):
        if op.action == 'picker_cancel':
            self.picking = False
            self.collection_picking = False
            self.binding_name = None
            self.pending_read = None
            self.transport.inject('observe')
            self.status.setText('選択を取り消しました')
            return
        if op.action == 'switch_window':
            self.driver.switch_to.window(op.handle)
            trial = copy.deepcopy(self.scenario)
            self._insert_node({'action':'switch_window','to':op.data['to']}, recording=True)
            return
        if op.action == "pick":
            self.picking = False
            self.transport.inject("observe")
            if self.collection_picking:
                self.collection_picking = False
                self._collection_operation(op)
                return
            if self.pending_operation and self.pending_credential is None and self.pending_operation.url == op.url:
                original = self.pending_operation
                self.pending_operation = None
                original.snapshot, original.context = op.snapshot, op.context
                original.document_id, original.element_ref = op.document_id, op.element_ref
                op = original
        if op.action == 'key':
            aliases = {'Escape':'ESCAPE', 'ArrowUp':'ARROW_UP', 'ArrowDown':'ARROW_DOWN', 'ArrowLeft':'ARROW_LEFT', 'ArrowRight':'ARROW_RIGHT', 'Enter':'ENTER', 'Tab':'TAB'}
            key = aliases.get(op.value, op.value)
            modifiers = [name for field, name in [('ctrl','CONTROL'),('alt','ALT'),('meta','META'),('shift','SHIFT')] if (op.data or {}).get(field)]
            if key in {'Control', 'Alt', 'Meta', 'Shift'}: return
            node = {'action':'key', '_meta':{'id':ulid()}}
            if modifiers: node['keys'] = modifiers + [key]
            else: node['key'] = key
            self._insert_node(node, recording=True)
            return
        if op.action not in {"click", "double_click", "input", "select", "pick"}: return
        if op.action != 'pick': self.pending_operation = op
        if op.url and self.driver.current_url != op.url:
            self.pending_operation = op
            self.recording = False
            self.transport.inject('observe')
            self.status.setText("操作前ページの再表示待ち: " + op.url)
            return
        page_id = self._page()
        if not page_id:
            self.status.setText("ページ登録待ちで停止")
            self.recording = False
            self.transport.inject('observe')
            return
        proposed = op.snapshot.get("label") or op.snapshot.get("name") or op.snapshot.get("text") or "対象"
        requested_name, self.binding_name = self.binding_name, None
        if any('unsupported_frame' in step for step in (op.context or [])):
            QMessageBox.warning(self, 'Frame', '安定した id/name のない iframe は現在登録できません')
            return
        try:
            definition = propose_target(op.snapshot, resolver=Resolver(self.driver, self.registry), context=op.context,
                                        document_id=op.document_id, element_ref=op.element_ref)
        except Exception as exc:
            QMessageBox.warning(self, 'Target', str(exc))
            return
        if op.context:
            if any("unsupported_frame" in step for step in op.context):
                QMessageBox.warning(self, "Frame", "安定した id/name のない iframe は現在登録できません")
                return
            definition["context"] = op.context
        if not definition["locate"]:
            QMessageBox.warning(self, "Target", "再現できる locator がありません。選択をやり直してください")
            return
        candidate = Resolver(self.driver, self.registry)
        valid = []
        for loc in definition["locate"]:
            try:
                scope = candidate._context(definition)
                found = candidate._candidate(scope, loc, definition.get("expect", {}), "")
                if found is not None and len(found) == 1: valid.append(loc)
            except Exception:
                pass
        if not valid:
            QMessageBox.warning(self, "Target", "一意に再現できる locator がありません。選択をやり直してください")
            return
        definition["locate"] = valid[:3]
        if any(loc.get('fragile') for loc in definition['locate']):
            if QMessageBox.question(self,'脆弱な locator','安定した証拠がありません。DOM 位置に依存する fragile な locator を登録しますか？') != QMessageBox.StandardButton.Yes: return
        candidate._context(definition)
        captured = candidate._candidate(candidate._context(definition),valid[0],definition.get('expect',{}),'')[0]
        reusable = []
        for logical_name in self.registry['pages'][page_id].get('elements',{}):
            try:
                if Resolver(self.driver,self.registry).target(logical_name).id == captured.id:
                    reusable.append(logical_name)
            except Exception: pass
        reuse = False
        if requested_name:
            name, ok = requested_name, True
        elif len(reusable) == 1:
            name, ok, reuse = reusable[0], True, True
        elif reusable:
            name, ok = QInputDialog.getItem(self,'Target','同じ要素に対応する名前を選択',reusable+['新規登録'],editable=False)
            if name == '新規登録': name, ok = QInputDialog.getText(self,'操作の対象','対象の名前',text=proposed)
            else: reuse = True
        else:
            name, ok = QInputDialog.getText(self,'操作の対象','対象の名前',text=proposed)
        if not ok or not name: return
        existing = self.registry["pages"][page_id].get("elements", {}).get(name)
        if reuse: definition = copy.deepcopy(existing)
        if existing is not None:
            try:
                old = Resolver(self.driver, self.registry).target(name)
                scope = candidate._context(definition)
                new = candidate._candidate(scope, valid[0], definition.get("expect", {}), "")[0]
                if old.id != new.id and QMessageBox.question(self, "Target", "同じ名前の別 target があります。再登録しますか？") != QMessageBox.StandardButton.Yes:
                    return
            except Exception:
                if QMessageBox.question(self, "Target", "既存 target を再登録しますか？") != QMessageBox.StandardButton.Yes:
                    return
        self._commit_recorded_operation(op, page_id, name, definition)

    @recorder_boundary
    def retry_credential(self):
        if self.pending_credential is None: return
        op, page_id, name, definition = self.pending_credential
        self._commit_recorded_operation(op, page_id, name, definition)
        if self.pending_credential is None: self._process_operations()

    def _commit_recorded_operation(self, op, page_id, name, definition):
        trial, registry = copy.deepcopy(self.scenario), copy.deepcopy(self.registry)
        registry['pages'][page_id].setdefault('elements',{})[name] = definition
        if op.action != "pick":
            node = {"action": op.action, "target": name, "_meta": {"id": ulid()}}
            if op.action in {"input", "select"}:
                if op.data and op.data.get("secret"):
                    self.pending_credential=(op,page_id,name,copy.deepcopy(definition))
                    selection=self.resolve_secret_input()
                    if selection is None:
                        self.recording=False
                        self.transport.inject('observe')
                        self.status.setText('パスワード操作は認証情報の選択／登録待ちです')
                        return
                    ref,group,entry=selection
                    node['value']=ref
                    preceding=sequences(trial)[self.record_position[0]] if self.record_position else trial['steps']
                    insertion=self.record_position[1] if self.record_position else len(preceding)
                    username=username_candidate(preceding,insertion,self.input_evidence,op)
                    if username is not None and isinstance(entry.get('username'), str) and entry['username'].strip():
                        if QMessageBox.question(self,'ユーザーIDとの関連',
                            f'直前の入力「{username["target"]}」にも {group}.username を使用しますか？')==QMessageBox.StandardButton.Yes:
                            username['value']=credential_reference(group,'username')
                else:
                    node["value"] = op.value
            if self.record_position:
                key, index = self.record_position
                sequences(trial)[key].insert(index,node)
            else: trial['steps'].append(node)
        if not self._commit_edit(trial,registry): return
        if op.action=='input' and not (op.data or {}).get('secret'):
            self.input_evidence[node['_meta']['id']]=InputEvidence(op,name,op.value)
        if op.action != 'pick' and self.record_position:
            self.record_position = (key,index+1)
        if self.pending_operation is op:
            self.pending_operation = None
            self.pending_credential = None
        if op.action=='pick' and self.pending_read:
            node, self.pending_read = self.pending_read, None
            self._insert_node(dict(node,target=name))

    def save(self):
        if self.scenario is None: return False
        try:
            schema.scenario(self.scenario)
            schema.elements(self.registry)
            schema.validate_package(self.scenario, self.registry)
            if self._mtimes() != self.saved_mtimes:
                if not self.reconcile_external(): return
            save_package(self.scenario_path, self.scenario, self.registry)
            self.saved_mtimes = self._mtimes()
            self.dirty = False
            self.refresh()
            self.status.setText("保存しました")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))
            return False

    def _new_playback(self):
        if self.scenario is None or self.driver is None or self.config is None: return False
        self.stop_record()
        if self.pending_operation or self.operation_queue or self.recorder_error:
            self.status.setText('保留中の記録を確定または破棄してから再生してください')
            return False
        self.picking = False
        self.open_browser()
        if not self.driver:
            return False
        self.transport.inject('observe')
        schema.scenario(self.scenario)
        schema.validate_package(self.scenario, self.registry)
        self.confirmed_destructive = False
        self.credentials=CredentialStore(self.config['credentials']['path']).document
        config = copy.deepcopy(self.config)
        config['playback']['observation_delay'] = self.pace_box.currentData() or '0s'
        self.controller = PlaybackController(Player(self.driver, self.scenario, self.registry, config, self.credentials))
        return True

    def change_mode(self, mode):
        if self.scenario is None: return
        if self.controller and self.controller.state not in {'complete','stopped'}:
            self.mode_box.blockSignals(True)
            self.mode_box.setCurrentText(self.scenario.get('mode','実行'))
            self.mode_box.blockSignals(False)
            self.status.setText('モードの変更は再生を停止してから行ってください')
            return
        trial = copy.deepcopy(self.scenario)
        trial['mode'] = mode
        self._commit_edit(trial)

    def play_then_record(self):
        # This user intent always establishes the scenario from its beginning.
        if self.worker and self.worker.isRunning(): return
        self.record_after_play = False
        if self.recording or self.pending_operation or self.operation_queue or self.recorder_error:
            self.status.setText('記録を終了し、保留中の操作を確定または破棄してください');return
        self.controller = None
        self.record_position = None
        self.just_recorded = False
        self.record_after_play = True
        if not self._start_playback(): self.record_after_play = False
        self.update_actions()

    def _start_playback(self, *, max_actions=None, until_id=None, retry=False):
        try:
            if self.controller and self.controller.state=='failed' and not retry:
                self.status.setText('失敗した Step は再試行またはスキップを選択してください')
                return False
            if self.worker and self.worker.isRunning():
                self.controller.action_budget = max_actions
                self.controller.until_id = until_id
                self.controller.resume()
                self.update_actions()
                return True
            if self.controller is None or self.controller.state in {"complete", "stopped"}:
                if not self._new_playback(): return False
            self.worker = PlaybackWorker(self.controller, max_actions=max_actions, until_id=until_id, parent=self)
            worker = self.worker
            worker.gate_requested.connect(self._worker_gate)
            worker.action_completed.connect(self._worker_completed)
            worker.finished.connect(self._worker_finished)
            self.worker.start()
            self.just_recorded = False
            self.status.setText("再生中")
            self.update_actions()
            return True
        except Exception as exc:
            self.status.setText("再生停止: " + str(exc))
            self.update_actions()
            return False

    def play(self):
        self._start_playback(max_actions=1 if self.pace_box.currentData() is None else None)

    def restart_playback(self):
        if self.worker and self.worker.isRunning():
            self.stop_playback()
            self.status.setText("停止後、最初から実行できます")
            return
        self.controller = None
        self._start_playback()

    def single_step(self):
        self._start_playback(max_actions=1)

    def play_until_selected(self):
        row = self.step_list.currentRow()
        if row < 0: return
        self._start_playback(until_id=self.rows[row][0]["_meta"]["id"])

    def pause_playback(self):
        if self.controller:
            self.controller.pause()
            self.status.setText("安全な境界で一時停止します")

    def stop_playback(self):
        if self.controller:
            self.record_after_play = False
            self.controller.stop()
            self.status.setText("停止要求済み")
            self.update_actions()

    def retry_playback(self):
        if not self.controller or self.controller.state != "failed": return
        node = self.controller.current or {}
        if node.get("action") in {"append", "click", "input", "select", "key", "upload", "drag_drop", "alert_accept", "alert_input"}:
            if QMessageBox.question(self, "再試行", "既に副作用が発生している可能性があります。再試行しますか？") != QMessageBox.StandardButton.Yes:
                return
        self._start_playback(retry=True)

    def skip_playback(self):
        if not self.controller or self.controller.state != "failed": return
        if QMessageBox.question(self, "スキップ", "後続のブラウザ状態が合わなくなる可能性があります。スキップしますか？") != QMessageBox.StandardButton.Yes:
            return
        self.controller.skip()
        self.status.setText("失敗した Step をスキップしました。再開できます")
        self.update_actions()

    def _worker_gate(self, node):
        if self.sender() is self.worker: self._confirm_action(node)

    def _worker_completed(self, node):
        if self.sender() is self.worker: self._action_completed(node)

    def _worker_finished(self):
        if self.sender() is self.worker: self._playback_finished()

    def _confirm_action(self, node):
        policy = self.config["safety"]["destructive_confirmation"]
        accepted = True
        if node.get("risk") == "破壊的" and policy != "off" and not (policy == "once_per_run" and self.confirmed_destructive):
            accepted = QMessageBox.question(self, "破壊的操作", f"{node.get('action')} {node.get('target', '')} を実行しますか？") == QMessageBox.StandardButton.Yes
            self.confirmed_destructive |= accepted
        if self.worker:
            self.worker.confirm(accepted)

    def _action_completed(self, node):
        for row, (step, _, _, _) in enumerate(self.rows):
            if step.get("_meta", {}).get("id") == node.get("_meta", {}).get("id"):
                self.step_list.setCurrentRow(row)
                break
        self.status.setText("完了: " + node.get("action", ""))
        if self.controller and self.controller.player.log.error:
            self.status.setText(self.status.text()+' / '+self.controller.player.log.error)

    def _playback_finished(self):
        if self.controller is None: return
        state = self.controller.state
        if state == "failed":
            self.status.setText(str(self.controller.error))
            if self.controller.current:
                self._action_completed(self.controller.current)
                self.status.setText(str(self.controller.error))
        else:
            self.status.setText({"complete": "再生完了", "paused": "一時停止・再開できます", "stopped": "停止しました"}.get(state, state))
        if self.pending_close:
            self.close()
        elif state == 'complete' and self.record_after_play:
            self.record_after_play = False
            self.record_position = None
            self.continuation_recording = True
            self.start_record()
            if self.recording:self.status.setText("末尾まで再生しました。Edgeで続きを操作してください。")
        elif state in {'failed','stopped'}:
            self.record_after_play = False
        self.update_actions()

    def closeEvent(self, event):
        if self.lifecycle_busy:
            event.ignore()
            return
        self.lifecycle_busy = True
        try: ready = self.resolve_boundary()
        finally: self.lifecycle_busy = False
        if not ready:
            event.ignore()
            return
        self.timer.stop()
        self.shutdown_browser()
        event.accept()


def launch(scenario_path=None, config_path=None) -> int:
    app = QApplication.instance() or QApplication([])
    window = FlowTapeWindow(scenario_path, config_path)
    window.show()
    QTimer.singleShot(0, window.open_browser)
    return app.exec()
