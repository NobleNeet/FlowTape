from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from flowtape.browser import Resolver, open_edge
from flowtape.errors import AmbiguousTarget, LoopLimitExceeded, TargetNotFound, UnsupportedOperationError, CredentialOutputForbidden
from flowtape.player import Player
from flowtape.recorder import RecorderTransport, propose_target, propose_collections
from flowtape.schema import config, elements, scenario

DRIVER = Path.home() / ".cache/selenium/msedgedriver/linux64/154.0.4258.37/msedgedriver"
HTML = """<!doctype html><meta charset='utf-8'><title>FlowTape fixture</title><h1>Fixture</h1>
<label for='field'>名前</label><input id='field' name='name'>
<button id='save'>保存</button><button class='duplicate'>重複</button><button class='duplicate'>重複</button>
<table><tr><td data-testid='alice'>Alice</td><td><button>編集</button></td></tr><tr><td data-testid='bob'>Bob</td><td><button>編集</button></td></tr></table>
<input id='secret' type='password'>
<a id='next' href='/next.html'>次へ</a>
<iframe id='inside' srcdoc="<button id='framed'>Frame action</button>"></iframe>
<div id='host'></div><script>
document.querySelector('#host').attachShadow({mode:'open'}).innerHTML='<button id="shadow-button">Shadow action</button>';
document.querySelector('#save').onclick=()=>{document.body.dataset.clicked='yes'};
document.addEventListener('click',e=>{if(e.target.matches('table button')){
  document.body.dataset.rows=(document.body.dataset.rows||'')+e.target.closest('tr').querySelector('td').textContent+',';
  const table=document.querySelector('table');table.outerHTML=table.outerHTML;
}});
</script>"""


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    if not DRIVER.exists():
        pytest.skip("Edge WebDriver not available")
    folder = tmp_path_factory.mktemp("site")
    (folder / "index.html").write_text(HTML, encoding="utf-8")
    (folder / "next.html").write_text("<!doctype html><meta charset='utf-8'><button id='next-button'>Next page</button>", encoding="utf-8")
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(folder), **kwargs)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    cfg = config({"version": 1, "driver": {"path": str(DRIVER)}}, folder / "config.yaml")
    driver = open_edge(cfg, headless=True)
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    driver.get(url)
    yield driver, cfg, url
    driver.quit()
    server.shutdown()


def registry(url):
    return elements({"version": 1, "pages": {"fixture": {"identify": {"url": {"equals": url}}, "elements": {
        "保存": {"kind": "button", "locate": [{"by": "role", "role": "button", "name": "保存"}]},
        "重複": {"kind": "button", "locate": [{"by": "role", "role": "button", "name": "重複"}]},
        "不存在": {"kind": "button", "locate": [{"by": "id", "value": "missing"}]},
        "名前": {"kind": "input", "locate": [{"by": "label", "value": "名前"}]},
        "Frame": {"kind": "button", "context": [{"frame": {"id": "inside"}}], "locate": [{"by": "id", "value": "framed"}]},
        "Shadow": {"kind": "button", "context": [{"shadow": {"css": "#host"}}], "locate": [{"by": "id", "value": "shadow-button"}]},
        "Alice編集": {"kind": "button", "locate": [{"by": "relative", "anchor": {"testid": "alice"}, "relation": "row", "target": {"role": "button", "name": "編集"}}]},
        "重複の特定": {"kind": "button", "locate": [{"by": "role", "role": "button", "name": "重複"}, {"by": "css", "value": "button.duplicate:nth-of-type(2)", "fragile": True}]},
    }, "collections": {"行": {"locate": [{"by": "role", "role": "row"}]}}}}})


def test_resolver_and_context(browser):
    driver, cfg, url = browser
    resolver = Resolver(driver, registry(url))
    assert resolver.identify() == "fixture"
    assert resolver.target("保存").text == "保存"
    with pytest.raises(AmbiguousTarget): resolver.target("重複")
    with pytest.raises(TargetNotFound): resolver.target("不存在")
    assert resolver.target("Frame").text == "Frame action"
    assert resolver.target("Shadow").text == "Shadow action"
    assert resolver.target("Alice編集").text == "編集"
    assert resolver.target("重複の特定").text == "重複"
    assert resolver.diagnostics[0]["count"] == 2


def test_player_modes_and_output(browser, tmp_path):
    driver, cfg, url = browser
    cfg["paths"]["outputs"] = str(tmp_path)
    definition = registry(url)
    steps = [{"action": "input", "target": "名前", "value": "太郎"}, {"action": "click", "target": "保存"},
             {"action": "read", "target": "名前", "source": "value", "into": "person"},
             {"action": "append", "output": "log", "values": {"name": "${person}"}}]
    base = {"version": 1, "name": "fixture", "outputs": {"log": {"format": "jsonl", "file": "results.jsonl"}}, "steps": steps}
    check = scenario(base | {"mode": "確認"})
    Player(driver, check, definition, cfg).run()
    assert driver.find_element("id", "field").get_attribute("value") == ""
    assert driver.execute_script("return document.body.dataset.clicked") is None
    assert not list(tmp_path.rglob("*.jsonl"))
    Player(driver, scenario(base), definition, cfg).run()
    assert driver.find_element("id", "field").get_attribute("value") == "太郎"
    assert driver.execute_script("return document.body.dataset.clicked") == "yes"
    assert '"name": "太郎"' in next(tmp_path.rglob("*.jsonl")).read_text()


def test_recorder_record_and_pick(browser):
    driver, _, _ = browser
    transport = RecorderTransport(driver)
    transport.inject("record")
    driver.find_element("id", "save").click()
    ops = transport.stop()
    assert any(x.action == "click" and x.snapshot["name"] == "保存" for x in ops)
    driver.execute_script("delete document.body.dataset.clicked")
    transport.inject("pick")
    driver.find_element("id", "save").click()
    ops = transport.drain()
    assert any(x.action == "pick" for x in ops)
    assert driver.execute_script("return document.body.dataset.clicked") is None
    transport.close()


def test_recorder_input_and_password_privacy(browser):
    driver, _, _ = browser
    transport = RecorderTransport(driver)
    transport.inject("record")
    field = driver.find_element("id", "field")
    field.clear()
    field.send_keys("A", "B", "C")
    field.send_keys("\ue004")  # TAB commits the input
    secret = driver.find_element("id", "secret")
    secret.send_keys("topsecret")
    secret.send_keys("\ue004")
    events = driver.execute_script("return window.__flowtape.drain();")
    inputs = [x for x in events if x["type"] == "input_commit"]
    assert any(x["data"]["value"] == "ABC" for x in inputs)
    assert any(x["data"]["secret"] is True and x["data"]["value"] is None for x in inputs)
    assert "topsecret" not in str(events)
    assert len([x for x in transport.normalizer.consume(events) if x.action == "input"]) == 2
    transport.close()


def test_recorder_frame_and_navigation_reinjection(browser):
    driver, _, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    transport.inject("record")
    driver.switch_to.frame(driver.find_element("id", "inside"))
    driver.find_element("id", "framed").click()
    ops = transport.drain()
    ops += transport.normalizer.flush(force=True)
    assert any(x.action == "click" and x.context == [{"frame": {"id": "inside"}}] for x in ops)
    driver.find_element("id", "next").click()
    ops = transport.drain()
    ops += transport.normalizer.flush(force=True)
    assert any(x.action == "click" and x.snapshot["name"] == "次へ" and x.url == url for x in ops)
    assert driver.execute_script("return window.__flowtape.protocolVersion") == 1
    transport.close()


def test_direct_navigation_open_boundaries_and_link_deduplication(browser):
    driver, _, url = browser
    driver.get('about:blank')
    transport = RecorderTransport(driver)
    try:
        transport.inject('observe')
        driver.get(url)
        assert transport.drain() == []
        transport.inject('record')
        # Entering recording alone does not invent an initial open.
        assert transport.drain() == []
        driver.get(url.replace('index.html', 'next.html'))
        opened, = transport.drain()
        assert opened.action == 'open' and opened.data['url'].endswith('/next.html')
        driver.get(url)
        opened, = transport.drain()
        assert opened.action == 'open' and opened.data['url'] == url
        driver.find_element('id', 'next').click()
        ops = transport.drain(force=True)
        assert [op.action for op in ops] == ['click']
        transport.navigate(url)
        assert transport.drain() == []  # The GUI command inserts its own open.
        driver.execute_script("location.href='/next.html'")
        from selenium.webdriver.support.ui import WebDriverWait
        WebDriverWait(driver, 10).until(lambda d: d.current_url.endswith('/next.html'))
        assert transport.drain() == []  # Script navigation is not a direct URL entry.
        transport.stop()
        driver.get(url)
        transport.inject('record')
        assert transport.drain() == []
    finally:
        transport.close()


def test_address_focus_keys_flush_input_without_persisting_browser_shortcuts(browser):
    driver, _, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    try:
        transport.inject('record')
        driver.execute_script("""
            const field=document.querySelector('#field');field.value='pending';
            field.dispatchEvent(new Event('input',{bubbles:true}));
            field.dispatchEvent(new KeyboardEvent('keydown',{key:'l',ctrlKey:true,bubbles:true}));
            field.dispatchEvent(new KeyboardEvent('keydown',{key:'d',altKey:true,bubbles:true}));
            field.dispatchEvent(new KeyboardEvent('keydown',{key:'a',ctrlKey:true,bubbles:true}));
        """)
        operations = transport.stop()
        assert [(op.action, op.value) for op in operations] == [('input', 'pending'), ('key', 'a')]
    finally:
        transport.close()


def test_destroyed_cross_origin_frame_can_stop_without_losing_captured_click(browser):
    driver, _, url = browser
    driver.get(url)
    source = url.replace('127.0.0.1', 'localhost')
    driver.execute_script("document.querySelector('#inside').removeAttribute('srcdoc');document.querySelector('#inside').src=arguments[0]", source)
    transport = RecorderTransport(driver)
    try:
        transport.inject('record')
        assert any(bridge.handle is None for bridge in transport.bridges.values())
        driver.switch_to.frame(driver.find_element('id', 'inside'))
        driver.find_element('id', 'save').click()
        driver.switch_to.default_content()
        driver.execute_script("document.querySelector('#inside').remove()")
        operations = transport.stop()
        assert any(op.action == 'click' and op.url == source and op.context == [{'frame': {'id': 'inside'}}] for op in operations)
        assert not any(op.action == 'open' for op in operations)
    finally:
        transport.close()


def test_fresh_playback_uses_only_blank_surviving_tab_and_replaces_recorder_boundary(browser):
    driver, cfg, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    try:
        transport.inject('observe')
        old = driver.current_window_handle
        driver.switch_to.new_window('tab')
        blank = driver.current_window_handle
        driver.get('about:blank')
        driver.switch_to.window(old)
        driver.close()
        transport.prepare_playback()
        assert driver.current_window_handle == transport.windows.active == blank
        assert old not in transport.bridges and blank in transport.bridges
        document = scenario({'version': 1, 'name': 'fresh blank start', 'steps': [
            {'action': 'open', 'url': url}, {'action': 'click', 'target': '保存'}]})
        result = Player(driver, document, registry(url), cfg).run()
        assert result.state == 'complete'
        assert driver.execute_script('return document.body.dataset.clicked') == 'yes'
    finally:
        transport.close()


def test_capture_generation_verifies_identity_and_relative_context(browser):
    driver, _, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    transport.inject('pick')
    driver.find_elements('css selector', 'table button')[0].click()
    op = next(op for op in transport.drain() if op.action == 'pick')
    diagnostic = []
    generated = propose_target(op.snapshot, resolver=Resolver(driver, registry(url)), context=op.context,
                               document_id=op.document_id, element_ref=op.element_ref, diagnostics=diagnostic)
    assert generated['locate'][0]['by'] == 'relative'
    assert generated['locate'][0]['anchor'] == {'text':'Alice'}
    assert any(d['count'] == 2 and d['locator']['by'] == 'role' for d in diagnostic)
    assert 'score' not in str(generated)
    changed = registry(url)
    changed['pages']['fixture']['elements']['Captured'] = generated
    assert Resolver(driver, changed).target('Captured').id == driver.find_elements('css selector','table button')[0].id
    # A syntactically plausible but wrong ID must not become a locator.
    op.snapshot['attributes']['id'] = 'save'
    bad = propose_target(op.snapshot, resolver=Resolver(driver, changed), context=op.context,
                         document_id=op.document_id, element_ref=op.element_ref)
    assert not any(loc.get('value') == 'save' for loc in bad['locate'])
    transport.close()


def test_player_keyboard_chord_and_contenteditable_semantics(browser):
    driver, cfg, url = browser
    driver.get(url)
    doc = scenario({'version':1,'name':'keyboard','steps':[
        {'action':'input','target':'名前','value':'before'},
        {'action':'key','target':'名前','keys':['CONTROL','a']},
        {'action':'key','target':'名前','key':'after'}]})
    Player(driver,doc,registry(url),cfg).run()
    assert driver.find_element('id','field').get_attribute('value') == 'after'
    resolver = Resolver(driver, registry(url))
    driver.execute_script("document.body.insertAdjacentHTML('beforeend','<input id=noneditable type=button><div id=editor contenteditable=true>old</div>')")
    assert not resolver.js("return FT.editable(document.querySelector('#noneditable'));")
    assert resolver.js("return FT.editable(document.querySelector('#editor'));")
    definition = registry(url)
    definition['pages']['fixture']['elements']['編集欄'] = {'kind':'element','locate':[{'by':'id','value':'editor'}], 'expect':{'editable':True}}
    elements(definition)
    doc = scenario({'version':1,'name':'editable','steps':[{'action':'input','target':'編集欄','value':'new plain text'}]})
    Player(driver,doc,definition,cfg).run()
    assert driver.find_element('id','editor').text == 'new plain text'


def test_recorder_cross_origin_navigation_keeps_stage_one_in_memory(browser):
    driver, _, url = browser
    driver.get(url)
    # localhost and 127.0.0.1 are distinct origins on the same VM server.
    destination = url.replace('127.0.0.1','localhost').replace('/index.html','/next.html')
    driver.execute_script("document.querySelector('#next').href=arguments[0]", destination)
    transport = RecorderTransport(driver)
    transport.inject('record')
    driver.find_element('id','next').click()
    operations = transport.stop()
    assert driver.current_url == destination
    assert any(op.action == 'click' and op.url == url and op.snapshot['name'] == '次へ' for op in operations)
    assert driver.execute_script("return sessionStorage.getItem('__flowtape_pending_v1')") is None
    transport.close()


def test_collection_picker_preview_and_window_recording(browser):
    driver, _, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    transport.inject('collection_pick')
    driver.find_elements('css selector','table button')[0].click()
    op = next(op for op in transport.drain() if op.action == 'pick')
    choices = propose_collections(op, Resolver(driver,registry(url)))
    assert choices[0][0]['locate'] == [{'by':'role','role':'row'}]
    assert len(choices[0][1]) == 2
    driver.execute_script('window.__flowtape.highlight(arguments[0])',choices[0][1])
    assert len(driver.find_elements('css selector','[data-flowtape-overlay]')) == 2
    driver.execute_script('window.__flowtape.clearHighlights()')
    root = driver.current_window_handle
    driver.execute_script("document.querySelector('#save').onclick=()=>window.open('/next.html','_blank')")
    transport.inject('record')
    driver.find_element('id','save').click()
    transport.drain()  # discover, associate, and inject the popup
    popup = next(handle for handle in driver.window_handles if handle != root)
    driver.switch_to.window(popup)
    driver.find_element('id','next-button').click()
    ops = transport.stop()
    assert any(op.action == 'switch_window' and op.data['to'] == 'newest' for op in ops)
    assert any(op.action == 'click' and op.snapshot['name'] == 'Next page' for op in ops)
    transport.inject('record')
    driver.switch_to.window(root)
    driver.execute_script("document.querySelector('#save').onclick=null")
    driver.find_element('id','save').click()
    ops = transport.stop()
    assert any(op.action == 'switch_window' and op.data['to'] == 'parent' for op in ops)
    transport.close()
    driver.switch_to.window(popup)
    driver.close()
    driver.switch_to.window(root)


def test_shadow_select_and_ime_commit(browser):
    driver, _, url = browser
    driver.get(url)
    driver.execute_script("document.querySelector('#host').shadowRoot.innerHTML='<label for=ime>日本語</label><input id=ime><select id=choice><option>A</option><option>B</option></select>'")
    transport = RecorderTransport(driver)
    transport.inject('record')
    driver.execute_script("""
      const root=document.querySelector('#host').shadowRoot, input=root.querySelector('input');
      input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,composed:true}));
      input.value='に';input.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,isComposing:true}));
      input.value='日本語';input.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,isComposing:true}));
      input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,composed:true,data:'日本語'}));
      input.dispatchEvent(new FocusEvent('focusout',{bubbles:true,composed:true}));
      const select=root.querySelector('select');select.value='B';select.dispatchEvent(new Event('change',{bubbles:true,composed:false}));
    """)
    operations = transport.stop()
    inputs=[op for op in operations if op.action=='input']
    assert len(inputs)==1 and inputs[0].value=='日本語'
    assert inputs[0].context==[{'shadow':{'css':'#host'}}]
    assert any(op.action=='select' and op.value=='B' for op in operations)
    transport.close()


def test_closed_shadow_capture_is_explicitly_unsupported(browser):
    driver, _, url=browser
    driver.get(url)
    transport=RecorderTransport(driver)
    transport.inject('record')
    driver.execute_script("""
      const host=document.createElement('div');host.id='closed-host';document.body.append(host);
      const root=host.attachShadow({mode:'closed'});root.innerHTML='<button>Closed action</button>';
      root.querySelector('button').click();
    """)
    with pytest.raises(UnsupportedOperationError,match='closed_shadow'):
        transport.stop()
    transport.close()


def test_recorder_explicit_recovery_after_queue_overflow(browser):
    from flowtape.errors import FlowTapeError
    driver,_,url=browser
    driver.get(url)
    transport=RecorderTransport(driver)
    transport.inject('record')
    driver.execute_script('window.__flowtape.overflow=true')
    with pytest.raises(FlowTapeError,match='overflow'):
        transport.drain()
    transport.reset()
    transport.inject('record')
    driver.find_element('id','save').click()
    operations=transport.stop()
    assert any(op.action=='click' and op.snapshot['name']=='保存' for op in operations)
    transport.close()


def test_password_read_taint_blocks_output_without_leaking_value(browser,tmp_path):
    driver,cfg,url=browser
    driver.get(url)
    driver.execute_script("document.querySelector('#secret').value='local-only-secret'")
    definition=registry(url)
    definition['pages']['fixture']['elements']['Password']={'kind':'input','locate':[{'by':'id','value':'secret'}]}
    document=scenario({'version':1,'name':'privacy','mode':'確認','outputs':{'result':{'format':'text','file':'result.txt'}},'steps':[
        {'action':'read','target':'Password','source':'value','into':'password_copy'},
        {'action':'append','output':'result','value':'prefix-${password_copy}'}]})
    cfg=dict(cfg,paths=dict(cfg['paths'],outputs=str(tmp_path)))
    with pytest.raises(CredentialOutputForbidden) as exc:Player(driver,document,definition,cfg).run()
    assert 'local-only-secret' not in str(exc.value)
    assert not list(tmp_path.rglob('result.txt'))


def test_upload_select_dialogs_hover_and_download_wait(browser,tmp_path):
    driver,cfg,url=browser
    driver.get(url)
    driver.execute_script("""
      document.body.insertAdjacentHTML('beforeend','<input id=upload type=file hidden><select id=choice><option>A</option><option>B</option></select><button id=disabled disabled>Disabled hover</button>');
      document.querySelector('#save').onclick=()=>{document.body.dataset.reply=prompt('local test prompt')};
    """)
    definition=registry(url)
    definition['pages']['fixture']['elements'].update({
        'Upload':{'kind':'file','locate':[{'by':'id','value':'upload'}]},
        'Choice':{'kind':'select','locate':[{'by':'id','value':'choice'}]},
        'Disabled':{'kind':'button','locate':[{'by':'id','value':'disabled'}]}})
    upload=tmp_path/'upload.txt';upload.write_text('local fixture only')
    doc=scenario({'version':1,'name':'native DOM actions','steps':[
        {'action':'upload','target':'Upload','path':str(upload)},
        {'action':'select','target':'Choice','value':'B'},
        {'action':'hover','target':'Disabled'},
        {'action':'click','target':'保存'},
        {'action':'alert_input','value':'local answer'},
        {'action':'alert_accept'}]})
    player=Player(driver,doc,definition,cfg)
    player.run()
    assert driver.execute_script("return document.querySelector('#upload').files[0].name")=='upload.txt'
    assert driver.find_element('id','choice').get_attribute('value')=='B'
    assert driver.execute_script('return document.body.dataset.reply')=='local answer'
    download_dir=Path(cfg['paths']['downloads'])
    download_dir.mkdir(parents=True,exist_ok=True)
    wait=Player(driver,scenario({'version':1,'name':'downloads','steps':[{'action':'wait','until':{'download_complete':'report.txt'},'timeout':'2s'}]}),definition,cfg)
    (download_dir/'report.txt').write_text('completed local fixture download')
    wait.run()


def test_cross_origin_frame_navigation_keeps_event_context(browser):
    driver,_,url=browser
    driver.get(url)
    source=url.replace('127.0.0.1','localhost')
    driver.execute_script("document.querySelector('#inside').removeAttribute('srcdoc');document.querySelector('#inside').src=arguments[0]",source)
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(driver,5).until(lambda d:d.execute_script("return document.querySelector('#inside').contentWindow!==null"))
    transport=RecorderTransport(driver)
    transport.inject('record')
    driver.switch_to.frame(driver.find_element('id','inside'))
    driver.find_element('id','next').click()
    operations=transport.stop()
    assert any(op.action=='click' and op.url==source and op.context==[{'frame':{'id':'inside'}}] for op in operations)
    transport.close()


def test_player_popup_auto_returns_to_known_parent(browser):
    driver,cfg,url=browser
    driver.get(url)
    driver.execute_script("document.querySelector('#save').onclick=()=>window.open('/next.html','_blank')")
    definition=registry(url)
    definition['pages']['popup']={'identify':{'url':{'equals':url.replace('/index.html','/next.html')}},'elements':{
        'Close':{'kind':'button','locate':[{'by':'id','value':'next-button'}]}}}
    doc=scenario({'version':1,'name':'popup','steps':[
        {'action':'click','target':'保存'},{'action':'switch_window','to':'newest'},
        {'action':'click','target':'Close'},{'action':'check','condition':{'page':'fixture'}}]})
    player=Player(driver,doc,definition,cfg)
    from flowtape.playback import PlaybackController
    controller=PlaybackController(player)
    parent=driver.current_window_handle
    controller.execute(max_actions=2)
    assert controller.state=='paused'
    assert driver.current_window_handle!=parent
    driver.execute_script("document.querySelector('#next-button').onclick=()=>window.close()")
    controller.execute()
    assert controller.state=='complete', str(controller.error)
    assert driver.current_window_handle==parent
    assert driver.window_handles==[parent]


def test_for_each_reidentifies_after_dom_replacement(browser):
    driver, cfg, url = browser
    driver.get(url)
    definition = registry(url)
    definition["pages"]["fixture"]["elements"]["編集"] = {"kind": "button", "locate": [{"by": "role", "role": "button", "name": "編集"}]}
    doc = scenario({"version": 1, "name": "rows", "steps": [{"for_each": {"target": "行", "as": "row", "steps": [
        {"action": "click", "target": "編集", "within": "${row}"}
    ]}}]})
    Player(driver, doc, definition, cfg).run()
    assert driver.execute_script("return document.body.dataset.rows") == "Alice,Bob,"


def test_structural_if_repeat_while_limit(browser):
    driver, cfg, url = browser
    driver.get(url)
    doc = scenario({"version": 1, "name": "structure", "steps": [
        {"if": {"exists": "保存"}, "then": [{"repeat": {"count": 2, "steps": [{"action": "check", "condition": {"exists": "保存"}}]}}]},
        {"while": {"not_exists": "不存在", "max_iterations": 1, "steps": [{"action": "check", "condition": {"exists": "保存"}}]}}
    ]})
    with pytest.raises(LoopLimitExceeded):
        Player(driver, doc, registry(url), cfg).run()


def test_record_and_replay_complete_multiselect_state(browser):
    from selenium.webdriver.support.ui import Select
    driver, cfg, url = browser
    driver.get(url)
    driver.execute_script("""
      document.body.insertAdjacentHTML('beforeend', '<label for=choices>選択</label><select id=choices multiple><option selected>Old</option><option>Red</option><option>Blue</option></select><label for=city>都市</label><select id=city><option>None</option><option>New&nbsp;York</option></select>');
    """)
    transport = RecorderTransport(driver)
    transport.inject('record')
    choices = Select(driver.find_element('id', 'choices'))
    choices.deselect_all()
    choices.select_by_visible_text('Red')
    choices.select_by_visible_text('Blue')
    city = Select(driver.find_element('id', 'city'))
    city.select_by_visible_text('New York')
    operations = transport.drain()
    multi = [op for op in operations if op.action == 'select' and (op.data or {}).get('multiple')]
    assert [op.data['texts'] for op in multi] == [[], ['Red'], ['Red', 'Blue']]
    assert any(op.action == 'select' and op.value == 'New York' for op in operations)
    assert not any(op.action in {'click', 'double_click'} for op in operations + transport.normalizer.flush(force=True))
    definition = registry(url)
    definition['pages']['fixture']['elements'].update({
        '選択': {'kind': 'select', 'locate': [{'by': 'label', 'value': '選択'}]},
        '都市': {'kind': 'select', 'locate': [{'by': 'label', 'value': '都市'}]},
    })
    choices.select_by_visible_text('Old')
    steps = [{'action': 'select', 'target': '選択', 'values': ['${color}', 'Blue']},
             {'action': 'select', 'target': '都市', 'value': 'New\u00a0York'}]
    doc = scenario({'version': 1, 'name': 'sets', 'variables': {'color': 'Red'}, 'steps': steps})
    for mode in ('確認', 'デバッグ'):
        Player(driver, doc | {'mode': mode}, definition, cfg).run()
        assert {o.text for o in choices.all_selected_options} == {'Old', 'Red', 'Blue'}
    for _ in range(2):
        Player(driver, doc, definition, cfg).run()
        assert [o.text for o in choices.all_selected_options] == ['Red', 'Blue']
    Player(driver, scenario({'version': 1, 'name': 'scalar', 'steps': [
        {'action': 'select', 'target': '選択', 'value': 'Red'}]}), definition, cfg).run()
    assert [o.text for o in choices.all_selected_options] == ['Red', 'Blue']
    Player(driver, scenario({'version': 1, 'name': 'clear', 'steps': [
        {'action': 'select', 'target': '選択', 'values': []}]}), definition, cfg).run()
    assert choices.all_selected_options == []


@pytest.mark.parametrize('field, expected', [
    ({'values': ['Missing']}, 'option count 0'),
    ({'values': ['Red', 'Red']}, 'duplicate'),
    ({'values': ['Red', 'Duplicate']}, 'option count 2'),
    ({'values': ['Red', 'Disabled']}, 'option disabled'),
])
def test_multiselect_validates_all_options_before_mutation(browser, field, expected):
    from flowtape.errors import ActionCompatibilityError
    driver, cfg, url = browser
    driver.get(url)
    driver.execute_script("document.body.insertAdjacentHTML('beforeend','<select id=choices multiple><option selected>Old</option><option>Red</option><option>Duplicate</option><option>Duplicate</option><option disabled>Disabled</option></select>')")
    definition = registry(url)
    definition['pages']['fixture']['elements']['選択'] = {'kind': 'select', 'locate': [{'by': 'id', 'value': 'choices'}]}
    doc = scenario({'version': 1, 'name': 'validation', 'steps': [{'action': 'select', 'target': '選択', **field}]})
    with pytest.raises(ActionCompatibilityError, match=expected):
        Player(driver, doc, definition, cfg).run()
    assert driver.execute_script("return [...document.querySelector('#choices').selectedOptions].map(o=>o.text)") == ['Old']
    driver.execute_script("document.querySelector('#choices').multiple=false")
    with pytest.raises(ActionCompatibilityError, match='requires a multiple select'):
        Player(driver, doc, definition, cfg).run()


def test_navigation_source_evidence_is_unique_and_never_persisted(browser):
    from flowtape.recorder import captured_target
    driver, _, url = browser
    driver.get(url)
    transport = RecorderTransport(driver)
    transport.set_pages(registry(url)['pages'])
    try:
        transport.inject('record')
        driver.find_element('id', 'next').click()  # Local fixture integration, not native acceptance.
        operations = transport.stop()
        click = next(op for op in operations if op.action == 'click')
        assert click.snapshot['capture']['pages'] == ['fixture']
        assert click.snapshot['capture']['document_id'] == click.document_id
        definition = captured_target(click)
        assert definition and set(definition) == {'kind', 'locate', 'expect'}
        assert any(loc.get('value') == 'next' for loc in definition['locate'])
        elements({'version': 1, 'pages': {'fixture': {'identify': {'url': {'equals': url}},
                   'elements': {'次へ': definition}}}})
        # Dynamic IDs and duplicated role/text cannot qualify as source proof.
        driver.get(url)
        driver.execute_script("document.querySelector('#next').id='99999999';document.querySelector('body').insertAdjacentHTML('beforeend','<a href=/next.html>次へ</a>')")
        transport.reset()
        transport.inject('record')
        driver.find_element('id', '99999999').click()
        click = next(op for op in transport.stop() if op.action == 'click')
        assert captured_target(click) is None
    finally:
        transport.close()


def test_observer_diagnostics_have_polling_fallback_without_values(browser, tmp_path, monkeypatch):
    import json
    driver, _, url = browser
    monkeypatch.setenv('FLOWTAPE_RECORDER_TRACE', str(tmp_path / 'trace.jsonl'))
    driver.get(url)
    transport = RecorderTransport(driver)
    try:
        transport.inject('record')
        # A missing diagnostic binding must not hide observer admission. The
        # regular event binding still transports raw capture in memory.
        driver.execute_script('delete window.__flowtape_trace')
        driver.find_element('id', 'field').send_keys('fixture-private-value')
        driver.find_element('id', 'save').click()
        transport.stop()
        content = (tmp_path / 'trace.jsonl').read_text()
        assert 'fixture-private-value' not in content and url not in content
        rows = [json.loads(line) for line in content.splitlines()]
        assert any(row['stage'] == 'observer_input' and row.get('type') == 'input' for row in rows)
        assert any(row['stage'] == 'observer_emit' and row.get('type') == 'input_commit' for row in rows)
        observer_ids = [(row['document_id'], row['trace_seq']) for row in rows if 'trace_seq' in row]
        assert len(observer_ids) == len(set(observer_ids))
    finally:
        transport.close()


def test_source_proof_uses_the_generated_editability_expectation(browser):
    from flowtape.recorder import captured_target
    driver, _, url = browser
    driver.get(url)
    driver.execute_script("document.querySelector('#field').readOnly=true")
    transport = RecorderTransport(driver)
    try:
        transport.inject('record')
        driver.find_element('id', 'field').click()
        click = next(op for op in transport.stop() if op.action == 'click')
        assert click.snapshot['editable'] is False
        assert captured_target(click) is None
    finally:
        transport.close()
