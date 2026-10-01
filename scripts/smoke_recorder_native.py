"""Recorder acceptance using Linux X11 native input, with no action retries.

Only read-only CDP expressions locate controls/assert browser state. All Edge
input is XTEST pointer/key input. Qt dialogs are answered using real widgets.
Each fresh case records into an empty package through the actual FlowTape UI.
"""

import argparse
import json
import os
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from flowtape import schema
from flowtape.desktop_dialogs import PageRegistrationDialog
from flowtape.ui import FlowTapeWindow
from native_input import NativeInput


BASE = 'https://www.uitestingplayground.com'
CASES = {'click': '/click', 'input': '/textinput', 'checkbox': '/autowait',
         'single_select': '/select', 'multi_select': '/select', 'navigation': '/',
         'radio': 'https://www.selenium.dev/selenium/web/web-form.html', 'address_open': '/'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', required=True)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--artifacts', required=True)
    args = parser.parse_args()
    starting_url = CASES[args.case] if args.case == 'radio' else BASE + CASES[args.case]
    root = Path(args.artifacts).resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['FLOWTAPE_RECORDER_TRACE'] = str(root / 'trace.jsonl')
    source = root / 'scenario.yaml'
    schema.save_yaml(source, {'version': 1, 'name': 'native ' + args.case, 'steps': []})
    schema.save_yaml(root / 'elements.yaml', {'version': 1, 'pages': {}})
    schema.save_yaml(root / 'config.yaml', {'version': 1,
        'driver': {'path': str(Path(args.driver).resolve())},
        'recorder': {'arrange_windows': False},
        'paths': {name: str(root / name) for name in ('scenarios', 'logs', 'downloads', 'outputs')}})
    app = QApplication.instance() or QApplication([])
    window = FlowTapeWindow(str(source), str(root / 'config.yaml'), preferences_path=root / 'preferences.json')
    window.show()
    native = NativeInput()
    errors = []
    expected = []
    completed = []

    def pump(seconds=.6):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            app.processEvents()
            if errors:
                raise AssertionError(errors)
            if window.recorder_error:
                raise AssertionError(window.recorder_error)
            sleep(.01)

    def wait(predicate, timeout=15):
        deadline = monotonic() + timeout
        while not predicate() and monotonic() < deadline:
            pump(.05)
        assert predicate(), f'Transition missing: {window.status.text()}'

    def read(expression):
        result = window.driver.execute_cdp_cmd('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
        assert 'exceptionDetails' not in result, result
        return result['result'].get('value')

    def locate(selector):
        rect = read("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:r.width,height:r.height,viewport:innerHeight,sx:screenX,sy:screenY,chrome:outerHeight-innerHeight};})()")
        assert rect and rect['width'] > 0 and rect['height'] > 0, (selector, rect)
        # Scrolling is OS wheel input. It does not repeat the tested operation.
        while rect['y'] >= rect['viewport'] - 20:
            native.click(1400, 700, button=5)
            pump(.08)
            rect = read("(()=>{const r=document.querySelector(" + json.dumps(selector) + ").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,viewport:innerHeight,sx:screenX,sy:screenY,chrome:outerHeight-innerHeight};})()")
        assert 0 < rect['y'] < rect['viewport'], rect
        return rect['sx'] + rect['x'], rect['sy'] + rect['chrome'] + rect['y']

    def click_control(selector, control=False):
        native.activate_edge()
        x, y = locate(selector)
        native.click(x, y, control=control)

    def answer():
        dialog = app.activeModalWidget()
        if isinstance(dialog, PageRegistrationDialog):
            dialog.validate()
        elif isinstance(dialog, QInputDialog) and dialog.windowTitle() in {'操作の対象', 'Target'}:
            dialog.accept()
        elif isinstance(dialog, QMessageBox):
            errors.append(dialog.windowTitle() + ': ' + dialog.text())
            dialog.accept()

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(answer)
    timer.start()
    report = {'case': args.case, 'count': args.count, 'input_path': 'X11 XTEST', 'retries': 0}
    report['keyboard_engine'] = 'xkb:jp::jpn (original engine restored on exit)'
    try:
        window.open_browser()
        assert window.driver is not None, window.status.text()
        native.activate_edge()
        if args.case != 'address_open':
            native.chord('Control_L', 'l')
            native.type(starting_url)
            native.press('Return')
            wait(lambda: read('location.href') == starting_url, timeout=30)
        if args.case != 'address_open':
            native.press('F11')
        pump(1)
        QTest.mouseClick(window.record_button, Qt.MouseButton.LeftButton)
        assert window.recording
        pump(.2)
        for index in range(args.count):
            before = len(window.scenario['steps'])
            if args.case == 'address_open':
                destination = BASE + ('/' if index % 2 == 0 else '/textinput')
                native.activate_edge()
                native.chord('Control_L', 'l')
                native.type(destination)
                native.press('Return')
                expected.append({'action': 'open', 'url': destination})
            elif args.case == 'click':
                click_control('#badButton')
                expected.append({'action': 'click', 'target': 'Button That Ignores DOM Click Event'})
            elif args.case == 'input':
                click_control('#newButtonName')
                native.chord('Control_L', 'a')
                value = 'native' + str(index)
                native.type(value)
                native.press('Tab')
                expected.append({'action': 'input', 'value': value})
            elif args.case == 'checkbox':
                click_control('#visible' if index % 2 else 'label[for=visible]')
                expected.append({'action': 'click', 'target': 'Visible'})
            elif args.case == 'radio':
                ident = '#my-radio-2' if index % 2 == 0 else '#my-radio-1'
                click_control(ident if index % 2 else 'label:has(' + ident + ')')
                expected.append({'action': 'click', 'target': 'Default radio' if index % 2 == 0 else 'Checked radio'})
            elif args.case == 'single_select':
                click_control('#selectLanguage')
                native.press('Home')
                for _ in range(2 if index % 2 == 0 else 5):
                    native.press('Down')
                native.press('Return')
                expected.append({'action': 'select', 'value': 'Python' if index % 2 == 0 else 'Ruby'})
            elif args.case == 'multi_select':
                click_control('#selectColors option[value=' + ('red' if index % 2 == 0 else 'blue') + ']', control=True)
                expected.append({'action': 'select', 'values': [['Red'], ['Red', 'Blue'], ['Blue'], []][index % 4]})
            elif args.case == 'navigation':
                selector = 'a[href="/textinput"]' if index % 2 == 0 else '.navbar a[href="/"]'
                click_control(selector)
                expected.append({'action': 'click', 'target': 'Text Input' if index % 2 == 0 else 'UITAP'})
            pump(.7)
            if args.case == 'address_open':
                wait(lambda: read('location.href') == destination and read('document.readyState') == 'complete', timeout=30)
            elif args.case == 'navigation':
                destination = BASE + ('/textinput' if index % 2 == 0 else '/')
                wait(lambda: read('location.href') == destination and read('document.readyState') == 'complete')
            elif args.case == 'input':
                assert read("document.querySelector('#newButtonName').value") == expected[-1]['value']
            elif args.case == 'checkbox':
                assert read("document.querySelector('#visible').checked") == bool(index % 2)
            elif args.case == 'radio':
                assert read("document.querySelector(" + json.dumps(ident) + ").checked")
            elif args.case in {'single_select', 'multi_select'}:
                selector = '#selectLanguage' if args.case == 'single_select' else '#selectColors'
                actual = read("[...document.querySelector(" + json.dumps(selector) + ").selectedOptions].map(o=>o.textContent.trim())")
                assert actual == (expected[-1]['values'] if args.case == 'multi_select' else [expected[-1]['value']])
            assert window.recording, f'Recorder stopped: {window.status.text()}'
            assert window.pending_operation is None, f'Pending: {window.status.text()}'
            completed.append(index)
            print(f'{args.case} native input {index+1}/{args.count}', flush=True)
        # Observe completion after the continuous input batch. The action loop
        # never waits for a Step, retries an input, or injects a DOM correction.
        pump(2)
        assert window.recording and window.pending_operation is None, window.status.text()
        relevant = [node for node in window.scenario['steps'] if node.get('action') == expected[0]['action']]
        assert len(relevant) == len(expected), {'expected': expected, 'actual': relevant}
        for wanted, actual in zip(expected, relevant):
            assert all(actual.get(key) == value for key, value in wanted.items()), (wanted, actual)
        if args.case == 'navigation':
            assert not any(node['action'] == 'open' for node in window.scenario['steps']), 'Link navigation recorded twice'
        QTest.mouseClick(window.record_button, Qt.MouseButton.LeftButton)
        assert not window.recorder_error and not window.pending_operation and not window.operation_queue, window.recorder_error or window.status.text()
        window.actions['保存'].trigger()
        schema.validate_package(schema.load_yaml(source), schema.load_yaml(root / 'elements.yaml'))
        rows = [json.loads(line) for line in (root / 'trace.jsonl').read_text().splitlines()]
        def identities(stages):
            return {(row['document_id'], row['event_seq']) for row in rows if row['stage'] in stages
                    and row.get('document_id') and row.get('event_seq') is not None}
        emitted = identities({'observer_emit'})
        stages = {name: identities({name}) for name in ['cdp_binding', 'transport_merged', 'normalizer_receive', 'transport_operation']}
        for stage in ['cdp_binding', 'transport_merged', 'normalizer_receive']:
            assert emitted <= stages[stage], {'missing_stage': stage, 'missing': list(emitted - stages[stage])}
        semantic_emitted = {(row['document_id'], row['event_seq']) for row in rows if row['stage'] == 'observer_emit'
                            and row['type'] in {'click', 'input_commit', 'select', 'key'}}
        assert semantic_emitted <= stages['transport_operation'], {'missing_normalization': list(semantic_emitted - stages['transport_operation'])}
        terminal = identities({'ui_committed', 'ui_ignored'})
        assert stages['transport_operation'] <= terminal, {'missing_ui': list(stages['transport_operation'] - terminal)}
        native_rows = [row for row in rows if row['stage'] == 'observer_input' and row.get('mode') == 'record'
                       and row['type'] in {'click', 'input', 'change', 'keydown'}]
        assert (native_rows or args.case == 'address_open') and all(row['trusted'] for row in native_rows), 'Untrusted input in native acceptance'
        if args.case == 'address_open':
            from flowtape.player import Player
            window.driver.get('about:blank')
            Player(window.driver, schema.load_yaml(source), schema.load_yaml(root / 'elements.yaml'), window.config).run()
            assert read('location.href') == expected[-1]['url']
            report['replayed'] = True
        report.update(passed=True, completed=len(completed), steps=window.scenario['steps'], errors=errors,
                      site=starting_url,
                      native_events=len(native_rows), trusted=True,
                      pipeline={name: len(values) for name, values in stages.items()}, emitted=len(emitted),
                      terminal=len(terminal), missing=0, expected=expected)
    except Exception as exc:
        report.update(passed=False, completed=0, inputs_sent=len(completed), error=str(exc), status=window.status.text(),
                      browser_url=read('location.href'),
                      steps=window.scenario['steps'], errors=errors)
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.grab().save(str(root / 'flowtape.png'))
        app.primaryScreen().grabWindow(0).save(str(root / 'desktop.png'))
        if window.driver:
            window.driver.save_screenshot(str(root / 'edge.png'))
        timer.stop()
        window.timer.stop()
        window.recording = window.picking = False
        window.pending_operation = window.pending_credential = None
        window.operation_queue.clear()
        window.recorder_error = None
        window.dirty = False
        window.close()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        native.close()


if __name__ == '__main__':
    main()
