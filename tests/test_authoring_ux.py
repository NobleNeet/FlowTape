import copy
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QDialogButtonBox

from flowtape import schema
from flowtape.desktop_dialogs import (SettingsDialog, NewScenarioDialog, CredentialSelectionDialog,
                                     CredentialEditDialog, CredentialManagerDialog)
from flowtape.environment import CredentialStore, EnvironmentStoreError, credential_reference, snapshot
from flowtape.login_authoring import InputEvidence, username_candidate
from flowtape.recorder import Operation
from flowtape.ui import FlowTapeWindow


@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([])
    value=FlowTapeWindow(preferences_path=tmp_path/'env'/'prefs.json')
    yield value
    value.dirty=False;value.pending_operation=None;value.operation_queue.clear()
    value.recording=value.picking=False;value.recorder_error=None;value.worker=None
    value.close();app.processEvents()


def config_data(tmp_path):
    return {'version':1,'driver':{'path':str(tmp_path/'external-driver')},'credentials':{'path':str(tmp_path/'env'/'credentials.yaml')}}


def configure(window,tmp_path):
    path=tmp_path/'env'/'config.yaml'
    assert window.save_configuration(path,config_data(tmp_path),None)
    return path


def test_first_use_configuration_no_yaml(window,tmp_path):
    def settings(dialog):
        dialog.edits['driver','path'].setText(str(tmp_path/'external-driver'))
        dialog.edits['paths','scenarios'].setText(str(tmp_path/'scenarios'))
        dialog.validate()
        return dialog.result()
    with patch.object(SettingsDialog,'exec',settings),patch.object(window,'open_browser') as browser:
        window.edit_config()
        browser.assert_called_once()
    assert window.config is not None and window.scenario is None
    assert window.config_path.exists()
    assert schema.config(schema.load_yaml(window.config_path),window.config_path)==window.config
    assert window.config['paths']['scenarios']==str(tmp_path/'scenarios')
    assert window.config['credentials']['path']==str(tmp_path/'env'/'credentials.yaml')
    assert not (tmp_path/'env'/'credentials.yaml').exists()
    assert window.preferences.config_path==str(window.config_path)


def test_settings_exposes_all_fields_and_invalid_driver(window,tmp_path):
    dialog=SettingsDialog(window,tmp_path/'config.yaml')
    assert {('browser','executable'),('browser','profile_path'),('driver','path'),('credentials','path'),
            ('paths','scenarios'),('paths','logs'),('paths','downloads'),('paths','outputs')} <= set(dialog.edits)
    with patch('flowtape.desktop_dialogs.QMessageBox.warning'):
        dialog.edits['driver','path'].setText('relative-driver')
        dialog.validate()
    assert dialog.result()!=QDialog.DialogCode.Accepted
    dialog.edits['driver','path'].setText(str(tmp_path/'driver'))
    dialog.edits['timeouts','default'].setText('nonsense')
    with patch('flowtape.desktop_dialogs.QMessageBox.warning'):dialog.validate()
    assert dialog.result()!=QDialog.DialogCode.Accepted
    dialog.reject()


def test_config_cancel_restart_and_failure_keep_disk_and_browser(window,tmp_path):
    source=configure(window,tmp_path)
    original=source.read_bytes();browser=Mock();window.driver=browser;window.transport=Mock()
    changed=config_data(tmp_path);changed['driver']['path']=str(tmp_path/'another-driver')
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
        assert not window.save_configuration(source,changed,original)
    assert source.read_bytes()==original and window.driver is browser
    browser.quit.assert_not_called()
    with patch('flowtape.ui.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes), \
         patch('flowtape.environment.os.replace',side_effect=OSError('secret-value-must-not-appear')), \
         patch('flowtape.ui.QMessageBox.warning') as warning:
        assert not window.save_configuration(source,changed,original)
    assert source.read_bytes()==original and window.driver is browser
    assert 'secret-value' not in str(warning.call_args)
    assert not list(source.parent.glob('.flowtape-env-*'))


def test_config_external_edit_and_runtime_only_update(window,tmp_path):
    source=configure(window,tmp_path);original=source.read_bytes()
    browser=Mock();window.driver=browser;window.transport=Mock()
    changed=config_data(tmp_path)|{'logging':{'level':'DEBUG'}}
    source.write_text('external',encoding='utf-8')
    with patch('flowtape.ui.QMessageBox.warning'):
        assert not window.save_configuration(source,changed,original)
    assert source.read_text()=='external' and window.driver is browser
    source.write_bytes(original)
    assert window.save_configuration(source,changed,original)
    browser.quit.assert_not_called()
    assert window.config['logging']['level']=='DEBUG'


def test_new_dialog_parent_preview_and_directory_open(window,tmp_path):
    dialog=NewScenarioDialog(window,tmp_path)
    dialog.name.setText('日本語 手順')
    assert dialog.destination==tmp_path/'日本語 手順'
    assert str(dialog.destination)==dialog.preview.toPlainText()
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    for name in ['../escape','nested/name','C:\\escape','..','']:
        dialog.name.setText(name)
        assert dialog.destination is None
    dialog.reject()
    window.create_scenario('First',tmp_path/'First');window.close_scenario()
    with patch('flowtape.ui.QFileDialog.getExistingDirectory',return_value=str(tmp_path/'First')) as chooser:
        window.choose_scenario()
    assert chooser.called and window.scenario['name']=='First'


def test_credential_store_shared_add_conflict_update_remove_and_permissions(tmp_path):
    source=tmp_path/'env'/'credentials.yaml'
    store=CredentialStore(source)
    assert store.groups=={}
    store.add('社内SSO','shared-user','shared-password')
    original=source.read_bytes()
    assert schema.credentials(schema.load_yaml(source))==store.document
    if os.name!='nt':assert source.stat().st_mode & 0o777==0o600
    with pytest.raises(EnvironmentStoreError):store.add('社内SSO','other','other')
    assert source.read_bytes()==original
    store.update('社内SSO',{'domain':'CORP','password':'updated'})
    assert store.groups['社内SSO']['username']=='shared-user'
    assert store.groups['社内SSO']['domain']=='CORP'
    fresh=CredentialStore(source)
    store.update('社内SSO',{'username':'new-user'})
    with pytest.raises(EnvironmentStoreError):fresh.update('社内SSO',{'password':'stale'})
    fresh.reload();fresh.remove('社内SSO')
    assert CredentialStore(source).groups=={}


def test_credential_write_failure_safe_no_values_in_error(tmp_path):
    source=tmp_path/'credentials.yaml';store=CredentialStore(source)
    store.add('SSO','user','password');original=source.read_bytes()
    with patch('flowtape.environment.os.replace',side_effect=OSError('password')):
        with pytest.raises(EnvironmentStoreError) as failure:store.update('SSO',{'password':'plaintext-secret'})
    assert 'plaintext-secret' not in str(failure.value) and 'password' not in str(failure.value)
    assert source.read_bytes()==original and store.groups['SSO']['password']=='password'
    assert not list(tmp_path.glob('.flowtape-env-*'))
    source.write_text('version: 1\ncredentials:\n  SSO:\n    password: [plaintext-secret]',encoding='utf-8')
    with pytest.raises(EnvironmentStoreError) as failure:CredentialStore(source)
    assert 'plaintext-secret' not in str(failure.value)


def select_existing(dialog):
    dialog.existing.setChecked(True)
    dialog.groups.setCurrentText('社内SSO')
    dialog.validate()
    return dialog.result()


def register_new(dialog):
    dialog.new.setChecked(True)
    dialog.name.setText('社内SSO');dialog.username.setText('shared-user');dialog.password.setText('shared-password')
    dialog.validate();return dialog.result()


def test_resolution_registration_reuse_no_overwrite_and_cancel(window,tmp_path):
    configure(window,tmp_path)
    with patch.object(CredentialSelectionDialog,'exec',register_new):
        reference,group,entry=window.resolve_secret_input()
    assert reference=='${credential.社内SSO.password}' and entry['username']=='shared-user'
    source=Path(window.config['credentials']['path']);original=source.read_bytes()
    with patch.object(CredentialSelectionDialog,'exec',select_existing):
        assert window.resolve_secret_input()[0]==reference
    assert source.read_bytes()==original
    assert window.scenario is None
    with patch.object(CredentialSelectionDialog,'exec',return_value=QDialog.DialogCode.Rejected):
        assert window.resolve_secret_input() is None
    assert source.read_bytes()==original
    with patch.object(CredentialSelectionDialog,'exec',register_new),patch('flowtape.desktop_dialogs.QMessageBox.warning'):
        assert window.resolve_secret_input() is None
    assert source.read_bytes()==original


def test_new_registration_failure_does_not_finalize(window,tmp_path):
    configure(window,tmp_path)
    with patch.object(CredentialSelectionDialog,'exec',register_new), \
         patch('flowtape.environment.os.replace',side_effect=OSError('shared-password')), \
         patch('flowtape.ui.QMessageBox.warning') as warning:
        assert window.resolve_secret_input() is None
    assert 'shared-password' not in str(warning.call_args)
    assert not Path(window.config['credentials']['path']).exists()


def test_custom_credential_keys_and_masked_manager(window,tmp_path):
    configure(window,tmp_path)
    path=window.config['credentials']['path']
    store=CredentialStore(path);store.add('SSO','private-user','private-password')
    store.update('SSO',{'pin':'001234','domain':'CORP'})
    chooser=CredentialSelectionDialog(window,store)
    assert chooser.keys.currentText()=='password'
    chooser.keys.setCurrentText('pin');chooser.validate()
    assert chooser.selection==('SSO','pin')
    assert chooser.password.echoMode()==QLineEdit.EchoMode.Password
    assert not chooser.password.text()
    chooser.reject()
    manager=CredentialManagerDialog(window,store);manager.groups.setCurrentRow(0)
    edit=CredentialEditDialog(manager,'SSO',list(store.groups['SSO']))
    assert set(edit.entries)==set(store.groups['SSO'])
    assert all(field.echoMode()==QLineEdit.EchoMode.Password and field.text()=='' for field in edit.entries.values())
    edit.reject()
    def update(dialog):
        dialog.entries['pin'].setText('987654');dialog.validate();return dialog.result()
    with patch.object(CredentialEditDialog,'exec',update),patch('flowtape.desktop_dialogs.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
        manager.edit()
    assert store.groups['SSO']['pin']=='987654' and store.groups['SSO']['password']=='private-password'
    manager.groups.setCurrentRow(0)
    with patch('flowtape.desktop_dialogs.QMessageBox.question',return_value=QMessageBox.StandardButton.No):manager.remove()
    assert 'SSO' in store.groups
    with patch('flowtape.desktop_dialogs.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):manager.remove()
    assert store.groups=={}
    manager.reject()


def test_username_pairing_conservative_context_and_edits():
    username=Operation('input',snapshot={'type':'text','label':'ユーザーID','relations':[{'relation':'form','anchor':{'id':'login'}}]},value='recorded-user',document_id='doc',url='http://local/login',context=[],handle='window')
    secret=Operation('input',snapshot={'type':'password','relations':[{'relation':'form','anchor':{'id':'login'}}]},data={'secret':True},document_id='doc',url='http://local/login',context=[],handle='window')
    node={'action':'input','target':'ユーザーID','value':'recorded-user','_meta':{'id':'one'}}
    evidence={'one':InputEvidence(username,node['target'],node['value'])}
    assert username_candidate([node],1,evidence,secret) is node
    for key,value in [('document_id','other'),('url','http://other'),('handle','other'),('context',[{'frame':{'id':'other'}}])]:
        trial=copy.deepcopy(secret);setattr(trial,key,value)
        assert username_candidate([node],1,evidence,trial) is None
    username.snapshot['label']='検索';username.snapshot['type']='search'
    assert username_candidate([node],1,evidence,secret) is None
    username.snapshot['label']='ユーザーID';username.snapshot['type']='text'
    secret.snapshot['relations'][0]['anchor']={'id':'another-form'}
    assert username_candidate([node],1,evidence,secret) is None
    secret.snapshot['relations']=[]
    node['value']='manually-edited'
    assert username_candidate([node],1,evidence,secret) is None
    assert username_candidate([node,{'action':'click'}],2,evidence,secret) is None


def test_credential_management_without_scenario(window,tmp_path):
    configure(window,tmp_path)
    def add_group(dialog):
        dialog.store.add('Management','user','pw')
        return QDialog.DialogCode.Rejected
    with patch.object(CredentialManagerDialog,'exec',add_group):window.manage_credentials()
    assert window.scenario is None and 'Management' in window.credentials['credentials']
    assert not (tmp_path/'scenario.yaml').exists()


@pytest.mark.parametrize('decision',[QMessageBox.StandardButton.Yes,QMessageBox.StandardButton.No])
def test_recorded_secret_step_and_explicit_pairing(window,tmp_path,decision):
    from types import SimpleNamespace
    configure(window,tmp_path)
    window.create_scenario('Recorded',tmp_path/'package')
    trial={'version':1,'name':'Recorded','steps':[{'action':'input','target':'ユーザーID','value':'recorded-user'}]}
    registry={'version':1,'pages':{'local':{'identify':{'url':{'equals':'http://local/login'}},'elements':{
        'ユーザーID':{'kind':'input','locate':[{'by':'id','value':'username'}]}}}}}
    assert window._commit_edit(trial,registry)
    username=Operation('input',snapshot={'label':'ユーザーID','type':'text'},value='recorded-user',document_id='doc',url='http://local/login',context=[],handle='one')
    prior=window.scenario['steps'][0]
    window.input_evidence[prior['_meta']['id']]=InputEvidence(username,'ユーザーID','recorded-user')
    op=Operation('input',snapshot={'tag':'input','type':'password'},data={'secret':True},document_id='doc',url=username.url,context=[],handle='one')
    window.driver=Mock();window.driver.current_url=username.url;window.transport=Mock()
    class Resolver:
        def __init__(self,*args):pass
        def _context(self,*args):return None
        def _candidate(self,*args):return [SimpleNamespace(id='password')]
        def target(self,name):return SimpleNamespace(id='username')
    definition={'kind':'input','locate':[{'by':'id','value':'password'}]}
    with patch('flowtape.ui.Resolver',Resolver),patch('flowtape.ui.propose_target',return_value=definition), \
         patch.object(window,'_page',return_value='local'),patch('flowtape.ui.QInputDialog.getText',return_value=('パスワード',True)), \
         patch.object(CredentialSelectionDialog,'exec',register_new),patch('flowtape.ui.QMessageBox.question',return_value=decision):
        window._operation(op)
    assert window.pending_operation is None
    assert window.scenario['steps'][1]['value']=='${credential.社内SSO.password}'
    assert window.scenario['steps'][0]['value']==('${credential.社内SSO.username}' if decision==QMessageBox.StandardButton.Yes else 'recorded-user')
    assert window.save()
    assert 'shared-password' not in window.scenario_path.read_text()
    assert not (window.scenario_path.parent/'credentials.yaml').exists()


def test_cancelled_secret_operation_stays_pending(window,tmp_path):
    from types import SimpleNamespace
    configure(window,tmp_path);window.create_scenario('Pending',tmp_path/'package')
    window.registry={'version':1,'pages':{'local':{'identify':{'url':{'equals':'http://local'}},'elements':{}}}}
    window.driver=Mock();window.driver.current_url='http://local';window.transport=Mock();window.recording=True
    resolver=Mock();resolver._candidate.return_value=[SimpleNamespace(id='password')]
    op=Operation('input',snapshot={'tag':'input','type':'password'},url='http://local',data={'secret':True})
    with patch('flowtape.ui.Resolver',return_value=resolver), \
         patch('flowtape.ui.propose_target',return_value={'kind':'input','locate':[{'by':'id','value':'password'}]}), \
         patch.object(window,'_page',return_value='local'),patch('flowtape.ui.QInputDialog.getText',return_value=('パスワード',True)), \
         patch.object(CredentialSelectionDialog,'exec',return_value=QDialog.DialogCode.Rejected):
        window._operation(op)
    assert window.pending_operation is op
    assert window.scenario['steps']==[] and not window.recording
    assert window.registry['pages']['local']['elements']=={}
    assert window.save()
    assert 'password' not in window.scenario_path.read_text()


def test_missing_credential_key_does_not_guess(window,tmp_path):
    from flowtape.player import Player
    from flowtape.errors import FlowTapeError
    configure(window,tmp_path)
    driver=Mock();driver.window_handles=['one'];driver.current_window_handle='one'
    player=Player(driver,{'version':1,'name':'Manual','steps':[]},{'version':1,'pages':{}},window.config,
                  {'version':1,'credentials':{'SSO':{'username':'user','pin':'1234'}}})
    with pytest.raises(FlowTapeError,match='credential reference unavailable'):player.expand('${credential.SSO.password}')
    assert player.expand('${credential.SSO.pin}').secret


def test_cancel_settings_and_new_scenario_preserves_state(window,tmp_path):
    with patch.object(SettingsDialog,'exec',return_value=QDialog.DialogCode.Rejected):window.edit_config()
    assert window.config is None and not window.preferences.path.with_name('config.yaml').exists()
    with patch.object(NewScenarioDialog,'exec',return_value=QDialog.DialogCode.Rejected):assert not window.new_scenario()
    assert window.scenario is None and not window.lifecycle_busy


def test_update_cancelled_and_deleted_group_keeps_scenario(window,tmp_path):
    configure(window,tmp_path);window.create_scenario('Manual',tmp_path/'package')
    store=CredentialStore(window.config['credentials']['path']);store.add('SSO','user','original')
    original=store.path.read_bytes()
    scenario=copy.deepcopy(window.scenario)
    manager=CredentialManagerDialog(window,store);manager.groups.setCurrentRow(0)
    def edit(dialog):
        dialog.password.setText('different');dialog.validate();return dialog.result()
    with patch.object(CredentialEditDialog,'exec',edit),patch('flowtape.desktop_dialogs.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
        manager.edit()
    assert store.path.read_bytes()==original
    assert all(field.text()=='' for dialog in manager.findChildren(CredentialEditDialog) for field in dialog.entries.values())
    with patch('flowtape.desktop_dialogs.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):manager.remove()
    assert window.scenario==scenario
    manager.reject()
