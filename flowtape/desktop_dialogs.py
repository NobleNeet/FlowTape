"""Application settings, package creation and masked credential authoring dialogs."""

import copy

import yaml
from pathlib import Path, PureWindowsPath

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
    QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QLabel, QMessageBox,
    QComboBox, QCheckBox, QRadioButton, QListWidget, QPlainTextEdit)

from . import schema
from .environment import CredentialStore, credential_reference, snapshot


def path_widget(parent, initial='', kind='directory'):
    edit = QLineEdit(str(initial or ''))
    row = QHBoxLayout()
    row.addWidget(edit)
    button = QPushButton('参照')
    row.addWidget(button)
    def browse():
        if kind == 'directory': value = QFileDialog.getExistingDirectory(parent,'フォルダーを選択',edit.text())
        elif kind == 'save': value = QFileDialog.getSaveFileName(parent,'保存先を選択',edit.text(),'YAML (*.yaml *.yml)')[0]
        else: value = QFileDialog.getOpenFileName(parent,'ファイルを選択',edit.text())[0]
        if value: edit.setText(value)
    button.clicked.connect(browse)
    return edit,row


class NewScenarioDialog(QDialog):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.setWindowTitle('新規シナリオ')
        self.resize(680,260)
        layout = QFormLayout(self)
        self.name = QLineEdit()
        layout.addRow('シナリオ名',self.name)
        self.directory,row = path_widget(self,root)
        layout.addRow('保存する親フォルダー',row)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(90)
        layout.addRow('作成するパッケージ',self.preview)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('作成')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        self.name.textChanged.connect(self.update_preview)
        self.directory.textChanged.connect(self.update_preview)
        self.update_preview()

    def update_preview(self):
        name = self.name.text().strip()
        # A package basename must not escape its chosen parent on either platform.
        valid = bool(name and self.directory.text().strip()) and name not in {'.','..'} and not any(c in name for c in '/\\\x00') and not PureWindowsPath(name).drive
        self.destination = Path(self.directory.text()).expanduser().absolute()/name if valid else None
        self.preview.setPlainText(str(self.destination) if valid else 'シナリオ名と保存先を指定してください')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)


class SettingsDialog(QDialog):
    PATHS = [('browser','executable','Edge 実行ファイル（空欄=標準）','file'),
             ('browser','profile_path','専用 profile（空欄=一時）','directory'),
             ('driver','path','外部 WebDriver（絶対パス）','file'),
             ('paths','scenarios','シナリオ root','directory'),
             ('paths','logs','ログ','directory'),('paths','downloads','ダウンロード','directory'),
             ('paths','outputs','出力','directory'),('credentials','path','共有 credentials.yaml','save')]
    def __init__(self, parent, source, current=None):
        super().__init__(parent)
        self.setWindowTitle('アプリ設定 — WebDriver は外部で用意してください')
        self.resize(680,650)
        layout = QFormLayout(self)
        self.source,row = path_widget(self,source,'save')
        layout.addRow('アプリ config.yaml の保存先',row)
        load = QPushButton('既存 config.yaml を読み込む')
        load.clicked.connect(self.import_config)
        layout.addRow(load)
        self.edits = {}
        for section,key,label,kind in self.PATHS:
            edit,row = path_widget(self,'',kind)
            self.edits[section,key] = edit
            layout.addRow(label,row)
        for section,key,label in [('timeouts','default','既定の待機'),('timeouts','page_load','ページ読込待機'),
                                  ('loops','timeout','loop timeout'),('playback','observation_delay','再生の観察時間')]:
            edit = QLineEdit()
            self.edits[section,key] = edit
            layout.addRow(label,edit)
        self.loop_max = QLineEdit()
        layout.addRow('loop 上限',self.loop_max)
        self.arrange = QCheckBox('ウィンドウを並べる')
        layout.addRow(self.arrange)
        self.logging = QComboBox();self.logging.addItems(['DEBUG','INFO','WARNING','ERROR','CRITICAL'])
        layout.addRow('ログ level',self.logging)
        self.safety = QComboBox();self.safety.addItems(['always','once_per_run','off'])
        layout.addRow('破壊的操作の確認',self.safety)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.validate)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        defaults={'version':1,'driver':{'path':str(Path(source).absolute().parent/'msedgedriver')}}
        self.fill(current or schema.config(defaults,source))
        if current is None: self.edits['driver','path'].clear()
        self.loaded_source = Path(source).resolve()
        self.original = snapshot(source)

    def fill(self, config):
        for (section,key),edit in self.edits.items(): edit.setText(str(config[section][key] or ''))
        self.loop_max.setText(str(config['loops']['max_iterations']))
        self.arrange.setChecked(config['recorder']['arrange_windows'])
        self.logging.setCurrentText(config['logging']['level'])
        self.safety.setCurrentText(config['safety']['destructive_confirmation'])

    def import_config(self):
        source,_ = QFileDialog.getOpenFileName(self,'既存アプリ設定を選択',self.source.text(),'YAML (*.yaml *.yml)')
        if not source: return
        try:
            original = snapshot(source)
            config = schema.config(yaml.load(original.decode('utf-8'),Loader=schema.StrictLoader),source)
            self.fill(config)
            self.source.setText(source)
            self.loaded_source,self.original = Path(source).resolve(),original
        except Exception as exc: QMessageBox.warning(self,'設定',str(exc))

    def document(self):
        data={'version':1}
        for (section,key),edit in self.edits.items():
            value=edit.text().strip()
            data.setdefault(section,{})[key]=value or None
        data['loops']['max_iterations']=int(self.loop_max.text())
        data['recorder']={'arrange_windows':self.arrange.isChecked()}
        data['logging']={'level':self.logging.currentText()}
        data['safety']={'destructive_confirmation':self.safety.currentText()}
        return data

    def validate(self):
        try:
            if not self.source.text().strip(): raise ValueError('config.yaml の保存先を指定してください')
            data=self.document()
            schema.config(copy.deepcopy(data),self.source.text())
            self.result_document=data
            self.accept()
        except Exception as exc: QMessageBox.warning(self,'設定の検証',str(exc))


class CredentialEditDialog(QDialog):
    def __init__(self,parent,group=None,keys=None):
        super().__init__(parent)
        self.setWindowTitle('認証情報を登録' if group is None else '認証情報を更新')
        layout=QFormLayout(self)
        self.group=QLineEdit(group or '')
        self.group.setReadOnly(group is not None)
        self.entries={}
        for key in dict.fromkeys(list(keys or [])+['username','password']):
            edit=QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            if group is not None:edit.setPlaceholderText('空欄=変更なし')
            self.entries[key]=edit
        self.username,self.password=self.entries['username'],self.entries['password']
        layout.addRow('グループ名',self.group)
        for key,edit in self.entries.items():layout.addRow(key,edit)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.validate);self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        self.new=group is None

    def validate(self):
        try:
            if self.new:credential_reference(self.group.text().strip(),'password')
            else:schema.string(self.group.text(),'credential group')
            if self.new and not self.password.text(): raise ValueError('登録するパスワードを入力してください')
            self.accept()
        except Exception:
            QMessageBox.warning(self,'認証情報','グループ名と登録内容を確認してください。グループ名に . や参照記号は使えません。')


class CredentialSelectionDialog(QDialog):
    def __init__(self,parent,store):
        super().__init__(parent)
        self.setWindowTitle('認証情報を選択・登録')
        layout=QFormLayout(self)
        self.existing=QRadioButton('既存の認証情報を使用')
        self.new=QRadioButton('新規グループを登録して使用')
        self.groups=QComboBox();self.groups.addItems(list(store.groups))
        self.keys=QComboBox()
        layout.addRow(self.existing)
        layout.addRow('グループ',self.groups);layout.addRow('キー',self.keys)
        layout.addRow(self.new)
        self.name=QLineEdit();self.username=QLineEdit();self.password=QLineEdit()
        self.username.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for label,edit in [('新規グループ名',self.name),('ユーザーID',self.username),('パスワード（再入力）',self.password)]:layout.addRow(label,edit)
        layout.addRow(QLabel('ブラウザで入力したパスワードは取得しません。登録は共有 credentials.yaml に明示保存します。'))
        self.store=store
        self.groups.currentTextChanged.connect(self.update_keys)
        self.existing.toggled.connect(self.update_mode)
        self.new.toggled.connect(self.update_mode)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('選択／登録して続行')
        self.buttons.accepted.connect(self.validate);self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        self.existing.setEnabled(bool(store.groups))
        (self.existing if store.groups else self.new).setChecked(True)
        self.update_keys();self.update_mode()

    def update_keys(self):
        self.keys.clear()
        self.keys.addItems(list(self.store.groups.get(self.groups.currentText(),{})))
        if self.keys.findText('password')>=0:self.keys.setCurrentText('password')

    def update_mode(self):
        self.groups.setEnabled(self.existing.isChecked());self.keys.setEnabled(self.existing.isChecked())
        for edit in [self.name,self.username,self.password]:edit.setEnabled(self.new.isChecked())

    def validate(self):
        try:
            group=self.name.text().strip() if self.new.isChecked() else self.groups.currentText()
            key='password' if self.new.isChecked() else self.keys.currentText()
            credential_reference(group,key)
            if self.new.isChecked():
                if group in self.store.groups: raise ValueError()
                if not self.password.text(): raise ValueError()
            elif key not in self.store.groups.get(group,{}):raise ValueError()
            self.selection=(group,key)
            self.accept()
        except Exception: QMessageBox.warning(self,'認証情報','使用するグループとキーを選ぶか、別名で新規登録してください。')


class CredentialManagerDialog(QDialog):
    def __init__(self,parent,store):
        super().__init__(parent)
        self.store=store
        self.setWindowTitle('共有認証情報 — グループ管理')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel(str(store.path)))
        self.groups=QListWidget();layout.addWidget(self.groups)
        row=QHBoxLayout();layout.addLayout(row)
        for label,method in [('追加',self.add),('明示的に更新',self.edit),('削除',self.remove),('再読込',self.reload)]:
            button=QPushButton(label);button.clicked.connect(method);row.addWidget(button)
        done=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        done.rejected.connect(self.reject);layout.addWidget(done)
        self.refresh()

    def refresh(self):
        self.groups.clear();self.groups.addItems(list(self.store.groups))

    def reload(self):
        try:self.store.reload();self.refresh()
        except Exception as exc:QMessageBox.warning(self,'認証情報',str(exc))

    def add(self):
        dialog=CredentialEditDialog(self)
        try:
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            self.store.add(dialog.group.text().strip(),dialog.username.text(),dialog.password.text())
            self.refresh()
        except Exception as exc:QMessageBox.warning(self,'認証情報',str(exc))
        finally:
            for edit in dialog.entries.values():edit.clear()

    def edit(self):
        item=self.groups.currentItem()
        if item is None:return
        group=item.text()
        dialog=CredentialEditDialog(self,group,list(self.store.groups[group]))
        try:
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            if QMessageBox.question(self,'認証情報の更新','この共有グループを明示的に更新しますか？他のシナリオでも使われます。')!=QMessageBox.StandardButton.Yes:return
            changes={key:edit.text() for key,edit in dialog.entries.items() if edit.text()}
            self.store.update(group,changes)
            self.refresh()
        except Exception as exc:QMessageBox.warning(self,'認証情報',str(exc))
        finally:
            for edit in dialog.entries.values():edit.clear()

    def remove(self):
        item=self.groups.currentItem()
        if item is None:return
        if QMessageBox.question(self,'認証情報の削除','共有グループを削除すると既存の参照が解決できなくなります。シナリオは書き換えません。削除しますか？')!=QMessageBox.StandardButton.Yes:return
        try:self.store.remove(item.text());self.refresh()
        except Exception as exc:QMessageBox.warning(self,'認証情報',str(exc))
