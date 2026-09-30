"""Actual Qt dialogs and headed Edge: first-use setup and credential authoring."""

import argparse
import json
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch

from PySide6.QtCore import QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from flowtape.desktop_dialogs import SettingsDialog, NewScenarioDialog, CredentialSelectionDialog, PageRegistrationDialog
from flowtape.environment import CredentialStore
from flowtape.ui import FlowTapeWindow


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--driver',required=True)
    parser.add_argument('--artifacts',default='build/authoring-smoke')
    args=parser.parse_args()
    artifacts=Path(args.artifacts).resolve();artifacts.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    checks=[]
    with tempfile.TemporaryDirectory(prefix='flowtape-authoring-') as temporary:
        folder=Path(temporary)
        (folder/'index.html').write_text('<!doctype html><meta charset=utf-8><title>Local login</title><form id=login><label for=username>ユーザーID</label><input id=username autocomplete=username><label for=password>パスワード</label><input id=password type=password autocomplete=current-password><button type=button id=submit>ログイン</button></form>',encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*a,**kw):super().__init__(*a,directory=str(folder),**kw)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}/index.html'
        window=FlowTapeWindow(preferences_path=folder/'environment'/'prefs.json')
        window.show()
        errors=[]
        def answer_dialog(expected,callback):
            def answer():
                dialog=app.activeModalWidget()
                if not isinstance(dialog,expected):
                    errors.append('Unexpected authoring dialog')
                    if dialog:dialog.reject()
                    return
                try:callback(dialog)
                except Exception:
                    errors.append('Authoring dialog automation failed')
                    dialog.reject()
            QTimer.singleShot(0,answer)
        def setup(dialog):
            config_path=folder/'fresh'/'settings'/'config.yaml'
            credential_path=folder/'fresh'/'secrets'/'credentials.yaml'
            assert not config_path.parent.exists() and not credential_path.parent.exists()
            dialog.source.setText(str(config_path))
            dialog.edits['credentials','path'].setText(str(credential_path))
            dialog.edits['driver','path'].setText(str(Path(args.driver).resolve()))
            dialog.edits['paths','scenarios'].setText(str(folder/'scenarios'))
            app.processEvents();dialog.grab().save(str(artifacts/'settings.png'))
            dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()
        def create(name):
            def fill(dialog):
                dialog.name.setText(name)
                app.processEvents();dialog.grab().save(str(artifacts/'new-scenario.png'))
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            answer_dialog(NewScenarioDialog,fill)
            assert window.new_scenario()
        try:
            assert window.config is None and window.scenario is None
            answer_dialog(SettingsDialog,setup)
            window.edit_config()
            assert not errors and window.config_path.exists() and window.driver is not None
            checks.append('first-use Settings dialog creates an external config and starts headed Edge without hand-written YAML')
            browser=window.driver
            browser.get(url)
            create('初回ログイン')
            assert not window.recording
            def choose_new(dialog):
                dialog.new.setChecked(True)
                dialog.name.setText('共通SSO')
                dialog.username.setText('stored-user')
                dialog.password.setText('registered-secret')
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            def choose_existing(dialog):
                dialog.existing.setChecked(True)
                dialog.groups.setCurrentText('共通SSO')
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            def record(callback,cancel_first=False):
                window.start_record()
                browser.find_element('id','username').clear()
                browser.find_element('id','username').send_keys('typed-user')
                browser.find_element('id','password').clear()
                browser.find_element('id','password').send_keys('typed-password-not-captured')
                browser.find_element('id','submit').click()
                window.recording=False
                operations=window.transport.stop()
                secret=next(op for op in operations if (op.data or {}).get('secret'))
                assert secret.value is None
                assert 'typed-password-not-captured' not in json.dumps([op.__dict__ for op in operations],ensure_ascii=False)
                window.operation_queue.extend(operations)
                # Ordinary target/page confirmations are deterministic; credential dialog
                # uses real radio/combo/masked widgets and the production persistence path.
                def register_page(dialog):
                    dialog.name.setText('local');dialog.url.setText(url);dialog.match.setCurrentIndex(dialog.match.findData('equals'))
                    dialog.validate();return dialog.result()
                with patch.object(PageRegistrationDialog,'exec',register_page),patch('flowtape.ui.QInputDialog.getText',side_effect=[('ユーザーID',True),('パスワード',True),('ログイン',True)]), \
                     patch('flowtape.ui.QInputDialog.getMultiLineText',return_value=('url:\n  equals: '+url,True)), \
                     patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
                    # Schedule when the password operation is reached, after ID capture.
                    original=window.resolve_secret_input
                    def resolve():
                        answer_dialog(CredentialSelectionDialog,(lambda dialog: dialog.reject()) if cancel_first else callback)
                        return original()
                    with patch.object(window,'resolve_secret_input',resolve):window._process_operations()
                    if cancel_first:
                        assert window.pending_credential is not None and not window.picking
                        for _ in range(3):window._poll_events()
                        assert not window.picking
                        answer_dialog(CredentialSelectionDialog,callback)
                        window.retry_credential()
                        checks.append('cancelled credential selection stays pending without target reselection; explicit retry succeeds')
                assert not errors and window.pending_operation is None and window.recorder_error is None
                assert [node['value'] for node in window.scenario['steps'] if node['action']=='input']==[
                    '${credential.共通SSO.username}','${credential.共通SSO.password}']
                assert window.save()
                package_text=window.scenario_path.read_text(encoding='utf-8')
                assert 'typed-password-not-captured' not in package_text and 'registered-secret' not in package_text
                assert not (window.scenario_path.parent/'credentials.yaml').exists()
            record(choose_new,cancel_first=True)
            credential_path=Path(window.config['credentials']['path'])
            original=credential_path.read_bytes()
            assert CredentialStore(credential_path).groups['共通SSO']['password']=='registered-secret'
            checks.append('new shared credential registration inserts references and explicitly pairs the ID; browser password is never transported')
            create('別サイトの手順')
            assert window.driver is browser
            record(choose_existing)
            assert credential_path.read_bytes()==original
            checks.append('another scenario reuses the shared group without overwriting its values')
            window.play()
            deadline=monotonic()+15
            while window.worker.isRunning() and monotonic()<deadline:
                app.processEvents();sleep(.01)
            app.processEvents()
            assert not window.worker.isRunning() and window.controller.state=='complete'
            assert browser.find_element('id','username').get_attribute('value')=='stored-user'
            assert browser.find_element('id','password').get_attribute('value')=='registered-secret'
            checks.append('Player resolves shared credential references after recording and performs the login inputs')
            for path in folder.rglob('*.jsonl'):
                assert 'registered-secret' not in path.read_text(encoding='utf-8')
            checks.append('scenario files and run logs contain no password plaintext')
            (artifacts/'report.json').write_text(json.dumps({'checks':checks,'public_sites':[]},ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'checks':checks,'artifacts':str(artifacts)},ensure_ascii=False))
        finally:
            window.dirty=False;window.pending_operation=None;window.operation_queue.clear()
            window.recording=window.picking=False
            window.close();app.processEvents()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            server.shutdown()


if __name__=='__main__':main()
