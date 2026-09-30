"""Headed Qt/Edge acceptance of the two docs/14 primary workflows."""
import argparse
import json
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch

from PySide6.QtCore import QTimer, Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QDialogButtonBox, QInputDialog,
    QMessageBox, QFileDialog)

from flowtape.ui import FlowTapeWindow
from flowtape.browser_setup import BrowserSetupDialog
from flowtape.desktop_dialogs import NewScenarioDialog, PageRegistrationDialog
from flowtape import schema


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--driver',required=True)
    parser.add_argument('--artifacts',default='build/primary-flow-smoke');args=parser.parse_args()
    artifacts=Path(args.artifacts).resolve();artifacts.mkdir(parents=True,exist_ok=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app=QApplication.instance() or QApplication([])
    checks=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='flowtape-primary-') as temporary:
        root=Path(temporary)
        (root/'index.html').write_text('<!doctype html><meta charset=utf-8><title>操作テスト</title><label for=name>名前</label><input id=name><button id=submit onclick="document.body.dataset.count=String(Number(document.body.dataset.count||0)+1);document.querySelector(\'#result\').textContent=\'こんにちは \'+document.querySelector(\'#name\').value">表示</button><p id=result></p>',encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*a,**kw):super().__init__(*a,directory=str(root),**kw)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}/index.html'
        window=FlowTapeWindow(preferences_path=root/'environment'/'preferences.json');window.show()
        def wait(predicate,timeout=20):
            deadline=monotonic()+timeout
            while not predicate() and monotonic()<deadline:
                app.processEvents();sleep(.01)
            app.processEvents();assert predicate(),'UI/browser transition timed out'
            assert not errors,errors
        def screenshot(name):
            app.processEvents();window.grab().save(str(artifacts/(name+'.png')))
        def automate(expected,callback):
            def answer():
                dialog=app.activeModalWidget()
                if not isinstance(dialog,expected):
                    errors.append('Unexpected modal dialog: '+type(dialog).__name__)
                    if dialog:dialog.reject()
                    return
                try:callback(dialog)
                except Exception as exc:
                    errors.append('Dialog automation failed: '+type(exc).__name__)
                    dialog.reject()
            QTimer.singleShot(0,answer)
        def click(button):QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        # Accept ordinary page/target confirmations using their real Qt widgets.
        def confirm_capture():
            dialog=app.activeModalWidget()
            if isinstance(dialog,PageRegistrationDialog):dialog.validate()
            elif isinstance(dialog,QInputDialog) and dialog.windowTitle() in {'操作の対象','Target'}:dialog.accept()
            elif isinstance(dialog,QMessageBox):
                yes=dialog.button(QMessageBox.StandardButton.Yes)
                if yes:yes.click()
                else:
                    errors.append('Capture warning: '+dialog.text());dialog.accept()
        capture_timer=QTimer();capture_timer.setInterval(50);capture_timer.timeout.connect(confirm_capture)
        try:
            screenshot('01-first-launch')
            assert window.setup_button.isVisible() and not window.primary_bar.isVisible()
            def setup(dialog):
                dialog.next_button.click();dialog.driver_path.setText(str(Path(args.driver).resolve()))
                dialog.test_button.click()
                deadline=monotonic()+20
                def save_after_probe():
                    if dialog.save_button.isEnabled():
                        dialog.grab().save(str(artifacts/'02-browser-setup.png'));dialog.save_button.click()
                    elif monotonic()<deadline:QTimer.singleShot(50,save_after_probe)
                    else:
                        errors.append('Browser connection test failed: '+dialog.result_label.text());dialog.reject()
                QTimer.singleShot(50,save_after_probe)
            automate(BrowserSetupDialog,setup)
            with patch('flowtape.browser_setup.QStandardPaths.writableLocation',return_value=str(root/'documents')):
                click(window.setup_button)
            assert window.driver is not None and window.config_path.exists()
            browser=window.driver
            assert not window.setup_button.isVisible() and window.start_heading.text()=='何をしますか？'
            screenshot('03-purpose-start')
            def create(dialog):
                dialog.name.setText('はじめての記録');dialog.directory.setText(str(root/'scenarios'))
                dialog.grab().save(str(artifacts/'04-create.png'))
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            automate(NewScenarioDialog,create);click(window.new_recording_button)
            assert not window.recording and window.empty_record_button.isVisible()
            screenshot('05-record-ready')
            # The optional URL entry records the existing open action. No YAML is authored.
            automate(QInputDialog,lambda dialog:(dialog.setTextValue(url),dialog.accept()))
            click(window.empty_url_button)
            assert window.scenario['steps'][0]['action']=='open'
            capture_timer.start();click(window.record_button)
            assert window.recording and '記録を終了' in window.record_button.text()
            browser.find_element('id','name').send_keys('初回')
            browser.find_element('id','submit').click()
            wait(lambda:len(window.scenario['steps'])==3)
            screenshot('06-recording');click(window.record_button)
            assert window.verify_button.isVisible();screenshot('07-check-next')
            click(window.verify_button)
            wait(lambda:window.worker is not None and not window.worker.isRunning())
            assert window.controller.state=='complete',str(window.controller.error)
            assert browser.find_element('id','result').text=='こんにちは 初回'
            assert window.driver is browser
            window.actions['保存'].trigger()
            source=window.scenario_path;prefix=schema.load_yaml(source)['steps']
            screenshot('08-playback-complete')
            checks.append('A: real guided Edge/WebDriver connection test and save → New → record open/input/click → finish → primary verification playback → save; no hand-written YAML')
            assert window.close_scenario() and window.driver is browser
            def open_package(dialog):
                dialog.setDirectory(str(source.parent.parent));dialog.selectFile(str(source.parent));dialog.accept()
                watchdog=QTimer(dialog);watchdog.setSingleShot(True)
                watchdog.timeout.connect(dialog.reject);watchdog.start(1000)
            automate(QFileDialog,open_package);click(window.open_scenario_button)
            assert window.scenario_path==source and window.controller is None
            screenshot('09-open-existing')
            click(window.continue_button)
            wait(lambda:window.recording)
            assert window.controller.state=='complete' and window.driver is browser
            assert browser.find_element('id','result').text=='こんにちは 初回'
            assert '続きを記録中' in window.activity.text()
            screenshot('10-auto-recording')
            browser.find_element('id','name').clear();browser.find_element('id','name').send_keys('続き')
            browser.find_element('id','submit').click()
            wait(lambda:len(window.scenario['steps'])==len(prefix)+2)
            click(window.record_button);window.actions['保存'].trigger()
            saved=schema.load_yaml(source)['steps']
            assert saved[:len(prefix)]==prefix and [n['action'] for n in saved[-2:]]==['input','click']
            assert saved[-2]['value']=='続き' and browser.find_element('id','result').text=='こんにちは 続き'
            screenshot('11-continuation-saved');browser.save_screenshot(str(artifacts/'edge.png'))
            checks.append('B: real package chooser → one Continue Recording command → replay from beginning → automatic Recorder transition retaining Edge → input/click appended → finish and save')
            assert not errors
            (artifacts/'report.json').write_text(json.dumps({'checks':checks,'public_sites':[]},ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'checks':checks,'artifacts':str(artifacts)},ensure_ascii=False))
        finally:
            capture_timer.stop();window.timer.stop()
            if window.worker and window.worker.isRunning():window.controller.stop();window.worker.wait(3000)
            window.recording=window.picking=False;window.pending_operation=window.pending_credential=None;window.operation_queue.clear()
            window.dirty=False;window.close();app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            server.shutdown()


if __name__=='__main__':main()
