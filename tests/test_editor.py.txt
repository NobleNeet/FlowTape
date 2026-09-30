from unittest.mock import patch

import pytest

from flowtape.editor import rename_target, RenameAmbiguity
from flowtape.persistence import save_package
from flowtape.schema import load_yaml, save_yaml


def test_rename_only_confirmed_page_references():
    target = {"kind": "button", "locate": [{"by": "id", "value": "save"}]}
    registry = {"version": 1, "pages": {
        "a": {"identify": {"url": {"equals": "https://site/a"}}, "elements": {"保存": target}},
        "b": {"identify": {"url": {"equals": "https://site/b"}}, "elements": {"保存": target}},
    }}
    doc = {"version": 1, "name": "rename", "steps": [
        {"action": "open", "url": "https://site/a"},
        {"action": "click", "target": "保存"},
        {"action": "click", "target": "保存"},
        {"action": "wait", "until": {"page": "b"}},
        {"action": "click", "target": "保存"},
    ]}
    with pytest.raises(RenameAmbiguity) as exc:
        rename_target(doc, registry, "a", "保存", "保存A")
    assert exc.value.locations == [("steps", 2, "target")]
    assert "保存A" not in registry["pages"]["a"]["elements"]
    changed, knowledge = rename_target(doc, registry, "a", "保存", "保存A", {("steps", 2, "target"): False})
    assert [changed["steps"][i]["target"] for i in (1, 2, 4)] == ["保存A", "保存", "保存"]
    assert "保存A" in knowledge["pages"]["a"]["elements"]
    assert "保存" in knowledge["pages"]["b"]["elements"]


def test_two_file_save_rolls_back_on_replace_failure(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    registry = tmp_path / "elements.yaml"
    save_yaml(scenario, {"old": "scenario"})
    save_yaml(registry, {"old": "registry"})
    import os
    real_replace = os.replace
    calls = 0
    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 3: raise OSError("injected failure")
        real_replace(source, destination)
    with patch("flowtape.persistence.os.replace", side_effect=fail_second):
        with pytest.raises(OSError): save_package(scenario, {"new": "scenario"}, {"new": "registry"})
    assert load_yaml(scenario) == {"old": "scenario"}
    assert load_yaml(registry) == {"old": "registry"}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize('choice',['rollback','complete'])
def test_interrupted_save_requires_explicit_recovery(tmp_path,choice):
    from flowtape.cli import package
    from flowtape.persistence import recover_package, PendingSaveRecovery, journal_path
    source=tmp_path/'scenario.yaml'
    original={'version':1,'name':'original','steps':[{'action':'back'}]}
    updated={'version':1,'name':'updated','steps':[{'action':'forward'}]}
    registry={'version':1,'pages':{}}
    updated_registry={'version':1,'pages':{'new':{'identify':{'url':{'equals':'http://localhost/new'}},'elements':{}}}}
    save_package(source,original,registry)
    import os
    real_replace=os.replace
    def interrupt(source,destination):
        if str(destination).endswith('elements.yaml'): raise KeyboardInterrupt()
        return real_replace(source,destination)
    with patch('flowtape.persistence.os.replace',side_effect=interrupt):
        with pytest.raises(KeyboardInterrupt):save_package(source,updated,updated_registry)
    assert journal_path(source).exists()
    with pytest.raises(PendingSaveRecovery):package(str(source))
    recover_package(source,choice)
    recovered=package(str(source))
    assert recovered[0]['name']==('original' if choice=='rollback' else 'updated')
    assert recovered[1]==(registry if choice=='rollback' else updated_registry)
    assert not journal_path(source).exists()


def test_package_rejects_a_concurrent_writer(tmp_path):
    from flowtape.persistence import writer_lock, PackageBusy
    source=tmp_path/'scenario.yaml'
    with writer_lock(source):
        with pytest.raises(PackageBusy):
            save_package(source,{'version':1,'name':'blocked','steps':[]},{'version':1,'pages':{}})
    save_package(source,{'version':1,'name':'saved','steps':[]},{'version':1,'pages':{}})
    assert load_yaml(source)['name']=='saved'


def test_loop_rename_requires_confirmation_when_iterations_change_page():
    registry = {'version':1,'pages':{'a':{'identify':{'url':{'equals':'https://site/a'}},'elements':{'保存':{'kind':'button','locate':[{'by':'id','value':'save'}]}}}}}
    doc = {'version':1,'name':'loop','steps':[
        {'action':'open','url':'https://site/a'},
        {'repeat':{'count':2,'steps':[{'action':'click','target':'保存'}]}}
    ]}
    with pytest.raises(RenameAmbiguity) as exc:
        rename_target(doc,registry,'a','保存','保存A')
    assert exc.value.locations == [('steps',1,'repeat','steps',0,'target')]
