"""Exercise the actual desktop and headed Edge against an isolated VM fixture."""

import argparse
import json
import subprocess
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from flowtape.browser import Resolver
from flowtape.recorder import propose_target
from flowtape.schema import save_yaml
from flowtape.ui import FlowTapeWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--driver',required=True)
    parser.add_argument('--executable')
    parser.add_argument('--artifacts',default='build/desktop-smoke')
    args = parser.parse_args()
    artifacts = Path(args.artifacts).resolve()
    artifacts.mkdir(parents=True,exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='flowtape-desktop-') as temporary:
        folder = Path(temporary)
        (folder/'index.html').write_text('<!doctype html><meta charset=utf-8><title>FlowTape local desktop test</title><h1>Local test</h1><label for=name>名前</label><input id=name><button id=submit>送信</button><p id=result></p><script>submit.onclick=()=>{document.body.dataset.count=String(Number(document.body.dataset.count||0)+1);result.textContent="Hello "+document.querySelector("#name").value}</script>',encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*a,**kw): super().__init__(*a,directory=str(folder),**kw)
            def log_message(self,*a): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}/index.html'
        scenario={'version':1,'name':'desktop','outputs':{'result':{'format':'text','file':'result.txt'}},'steps':[
            {'action':'input','target':'名前','value':'FlowTape'},
            {'action':'click','target':'送信'},
            {'action':'read','target':'結果','source':'text','into':'result'},
            {'action':'append','output':'result','value':'${result}'}]}
        registry={'version':1,'pages':{'local':{'identify':{'url':{'equals':url}},'elements':{
            '名前':{'kind':'input','locate':[{'by':'label','value':'名前'}]},
            '送信':{'kind':'button','locate':[{'by':'role','role':'button','name':'送信'}]},
            '結果':{'kind':'element','locate':[{'by':'id','value':'result'}]}}}}}
        cfg={'version':1,'driver':{'path':str(Path(args.driver).resolve())},'paths':{'outputs':str(folder/'outputs')}}
        save_yaml(folder/'scenario.yaml',scenario)
        save_yaml(folder/'elements.yaml',registry)
        save_yaml(folder/'config.yaml',cfg)
        window=FlowTapeWindow(str(folder/'scenario.yaml'),str(folder/'config.yaml'))
        window.show()
        def finish_worker():
            deadline=monotonic()+15
            while window.worker.isRunning() and monotonic()<deadline:
                app.processEvents();sleep(.01)
            app.processEvents()
            assert not window.worker.isRunning(), 'desktop playback timed out'
            assert window.controller.error is None, str(window.controller.error)
        checks=[]
        try:
            with patch('flowtape.ui.QMessageBox.critical'):
                window.open_browser()
            assert window.driver is not None, window.status.text()
            window.driver.get(url)
            window.single_step();finish_worker()
            assert window.controller.state=='paused'
            assert window.driver.find_element('id','name').get_attribute('value')=='FlowTape'
            assert window.driver.execute_script('return document.body.dataset.count') is None
            checks.append('single step pauses before the next browser mutation')
            window.play();finish_worker()
            assert window.controller.state=='complete'
            assert next((folder/'outputs').rglob('result.txt')).read_text()=='Hello FlowTape\n'
            checks.append('desktop worker executes click/read/append and writes the expected output')
            window.transport.inject('pick')
            window.driver.find_element('id','submit').click()
            operation=next(op for op in window.transport.drain() if op.action=='pick')
            generated=propose_target(operation.snapshot,resolver=Resolver(window.driver,registry),
                context=operation.context,document_id=operation.document_id,element_ref=operation.element_ref)
            assert generated['locate']
            assert window.driver.execute_script('return document.body.dataset.count')=='1'
            checks.append('picker suppresses application click and verifies captured target identity')
            window.transport.inject('observe')
            app.processEvents()
            window.grab().save(str(artifacts/'desktop.png'))
            window.driver.save_screenshot(str(artifacts/'edge.png'))
            if args.executable:
                frozen=dict(scenario,steps=[{'action':'open','url':url}]+scenario['steps'])
                save_yaml(folder/'scenario.yaml',frozen)
                subprocess.run([str(Path(args.executable).resolve()),'run',str(folder),'--config',str(folder/'config.yaml'),'--headless'],check=True,timeout=30)
                checks.append('PyInstaller executable performs the localhost scenario with external YAML/config')
                subprocess.run([str(Path(args.executable).resolve()),'doctor','--config',str(folder/'config.yaml'),'--headless'],check=True,timeout=30)
                checks.append('PyInstaller Recorder injects, picks, transports, and verifies a live element on an isolated data fixture')
                gui=subprocess.Popen([str(Path(args.executable).resolve()),'ui',str(folder),'--config',str(folder/'config.yaml')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    sleep(2)
                    assert gui.poll() is None, 'packaged UI failed to start: '+gui.communicate()[1].decode(errors='replace')
                    checks.append('PyInstaller desktop UI starts with packaged Qt and observer resources')
                finally:
                    if gui.poll() is None: gui.terminate()
                    gui.communicate(timeout=10)
            (artifacts/'report.json').write_text(json.dumps({'checks':checks,'public_sites':[]},ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'checks':checks,'artifacts':str(artifacts)},ensure_ascii=False))
        finally:
            window.timer.stop()
            window.dirty=False
            window.close()
            app.processEvents()
            server.shutdown()


if __name__=='__main__': main()
