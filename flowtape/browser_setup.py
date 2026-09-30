"""Guided Edge/WebDriver setup; uses only an explicitly supplied external driver."""

import copy
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QStandardPaths
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget)

from . import schema
from .browser import open_edge
from .desktop_dialogs import path_widget
from .environment import snapshot


def detect_edge():
    for name in ('microsoft-edge','microsoft-edge-stable','msedge'):
        candidate=shutil.which(name)
        if candidate:return str(Path(candidate).absolute())
    if os.name=='nt':
        for variable in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
            root=os.environ.get(variable)
            if root:
                path=Path(root)/'Microsoft'/'Edge'/'Application'/'msedge.exe'
                if path.is_file():return str(path)
    return None


class BrowserProbe(QThread):
    result=Signal(bool,str)

    def __init__(self,config,parent):
        super().__init__(parent);self.config=config

    def run(self):
        browser=None
        try:
            config=copy.deepcopy(self.config)
            config['browser']['profile_path']=None
            browser=open_edge(config)
            browser.get('about:blank')
            version=browser.capabilities.get('browserVersion','')
            driver=browser.capabilities.get('msedge',{}).get('msedgedriverVersion','').split(' ')[0]
            self.result.emit(True,f'✓ Edgeを起動できました。Edge {version} / WebDriver {driver}')
        except Exception as exc:
            self.result.emit(False,f'接続できませんでした。Edge / WebDriverのパスと対応バージョンを確認してください。({type(exc).__name__})')
        finally:
            if browser is not None:
                try:browser.quit()
                except Exception:pass


class BrowserSetupDialog(QDialog):
    def __init__(self,parent,source,current=None):
        super().__init__(parent)
        self.setWindowTitle('Edgeを使えるように設定');self.resize(630,340)
        self.source=Path(source).resolve();self.original=snapshot(self.source)
        if current:
            self.defaults=copy.deepcopy(current)
        else:
            root=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or Path.home())/'FlowTape'
            self.defaults={'version':1,'browser':{'profile_path':None},
                'paths':{name:str(root/name) for name in ('scenarios','logs','downloads','outputs')},
                'credentials':{'path':str(self.source.with_name('credentials.yaml'))}}
        self.probe=None;self.tested_document=None;self.test_success=False
        layout=QVBoxLayout(self);self.heading=QLabel('ブラウザ設定 1 / 2 — Microsoft Edge');layout.addWidget(self.heading)
        self.pages=QStackedWidget();layout.addWidget(self.pages)
        edge_page=QWidget();edge=QVBoxLayout(edge_page)
        edge.addWidget(QLabel('Microsoft Edgeを検出します。必要な場合は実行ファイルを指定してください。'))
        found=detect_edge()
        self.edge_path,row=path_widget(self,(current or {}).get('browser',{}).get('executable') or found or '', 'file')
        edge.addWidget(QLabel('Edge 実行ファイル（空欄なら標準のEdgeを使用）'));edge.addLayout(row)
        self.detected=QLabel('● 検出済み: '+found if found else 'Edgeの実行ファイルを指定するか、標準のEdgeを使用してください。');self.detected.setWordWrap(True);edge.addWidget(self.detected)
        self.pages.addWidget(edge_page)
        driver_page=QWidget();driver=QVBoxLayout(driver_page)
        hint=QLabel('Edgeに対応するMicrosoft Edge WebDriverを指定してください。\nWebDriverは別途用意してください。FlowTapeはダウンロードしません。');hint.setWordWrap(True);driver.addWidget(hint)
        self.driver_path,row=path_widget(self,(current or {}).get('driver',{}).get('path',''),'file')
        driver.addLayout(row)
        self.test_button=QPushButton('接続テスト');self.test_button.clicked.connect(self.test_connection);driver.addWidget(self.test_button)
        self.result_label=QLabel();self.result_label.setWordWrap(True);driver.addWidget(self.result_label)
        self.pages.addWidget(driver_page)
        self.destination=QLabel('設定の保存先: '+str(self.source));self.destination.setWordWrap(True);layout.addWidget(self.destination)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.cancel_button=QPushButton('キャンセル');self.cancel_button.clicked.connect(self.reject);buttons.addWidget(self.cancel_button)
        self.back_button=QPushButton('戻る');self.back_button.clicked.connect(lambda:self.set_page(0));buttons.addWidget(self.back_button)
        buttons.addStretch()
        self.next_button=QPushButton('次へ');self.next_button.clicked.connect(lambda:self.set_page(1));buttons.addWidget(self.next_button)
        self.save_button=QPushButton('設定を保存して開始');self.save_button.clicked.connect(self.save);buttons.addWidget(self.save_button)
        self.edge_path.textChanged.connect(self.invalidate);self.driver_path.textChanged.connect(self.invalidate)
        self.set_page(0)

    def set_page(self,index):
        self.pages.setCurrentIndex(index);self.heading.setText('ブラウザ設定 1 / 2 — Microsoft Edge' if index==0 else 'ブラウザ設定 2 / 2 — WebDriver')
        self.back_button.setVisible(index==1);self.next_button.setVisible(index==0);self.save_button.setVisible(index==1)
        self.save_button.setEnabled(self.test_success)

    def document(self):
        data=copy.deepcopy(self.defaults)
        data['driver']={'path':self.driver_path.text().strip()}
        data.setdefault('browser',{})['executable']=self.edge_path.text().strip() or None
        return schema.config(data,self.source)

    def invalidate(self):
        self.test_success=False;self.tested_document=None;self.save_button.setEnabled(False);self.result_label.clear()

    def test_connection(self):
        if self.probe and self.probe.isRunning():return
        self.invalidate()
        try:self.tested_document=self.document()
        except Exception as exc:
            self.result_label.setText('絶対パスのWebDriverを指定してください。'+str(exc));return
        self.test_button.setEnabled(False);self.cancel_button.setEnabled(False);self.back_button.setEnabled(False)
        self.pages.setEnabled(False)
        self.result_label.setText('Edgeとの接続を確認しています…')
        self.probe=BrowserProbe(self.tested_document,self)
        self.probe.result.connect(self._result)
        self.probe.finished.connect(self._finished)
        self.probe.start()

    def _result(self,success,message):
        self.test_success=success;self.result_label.setText(message)

    def _finished(self):
        self.test_button.setEnabled(True);self.cancel_button.setEnabled(True);self.back_button.setEnabled(True)
        self.pages.setEnabled(True)
        self.save_button.setEnabled(self.test_success)

    def save(self):
        if self.probe and self.probe.isRunning():return
        if self.test_success and self.tested_document==self.document():
            self.result_document=self.tested_document
            self.accept()

    def reject(self):
        if self.probe and self.probe.isRunning():return
        super().reject()
