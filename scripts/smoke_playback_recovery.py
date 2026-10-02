"""Replay an unchanged scenario copy through the GUI after tab/browser closure."""

import argparse
import hashlib
import json
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from flowtape import schema
from flowtape.ui import FlowTapeWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--driver', required=True)
    parser.add_argument('--case', required=True, choices=['blank', 'replacement_blank', 'closed', 'closed_polled'])
    parser.add_argument('--artifacts', required=True)
    args = parser.parse_args()
    original = Path(args.scenario).expanduser().resolve()
    if original.is_dir(): original /= 'scenario.yaml'
    source_bytes = original.read_bytes()
    registry_bytes = original.with_name('elements.yaml').read_bytes()
    root = Path(args.artifacts).resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'scenario.yaml'
    source.write_bytes(source_bytes)
    source.with_name('elements.yaml').write_bytes(registry_bytes)
    config = root / 'config.yaml'
    schema.save_yaml(config, {'version': 1, 'driver': {'path': str(Path(args.driver).resolve())},
        'recorder': {'arrange_windows': False},
        'credentials': {'path': str(root / 'credentials.yaml')},
        'paths': {name: str(root / name) for name in ('scenarios', 'logs', 'downloads', 'outputs')}})
    app = QApplication.instance() or QApplication([])
    window = FlowTapeWindow(str(source), str(config), preferences_path=root / 'preferences.json')
    window.show()
    report = {'case': args.case, 'source_sha256': hashlib.sha256(source_bytes).hexdigest(), 'passed': False}
    try:
        window.open_browser()
        assert window.driver is not None, window.status.text()
        driver = window.driver
        if args.case == 'blank':
            driver.get('about:blank')
        elif args.case == 'replacement_blank':
            old = driver.current_window_handle
            driver.switch_to.new_window('tab')
            driver.get('about:blank')
            driver.switch_to.window(old)
            driver.close()  # Leave WebDriver referring to the closed original tab.
        else:
            driver.quit()  # External browser closure, not application shutdown.
            if args.case == 'closed_polled': window.poll()
        window.update_actions()
        report['play_enabled'] = window.play_button.isEnabled()
        assert report['play_enabled'], 'Playback disabled after browser closure'
        QTest.mouseClick(window.play_button, Qt.MouseButton.LeftButton)
        assert window.worker is not None, window.status.text()
        deadline = monotonic() + 60
        while window.worker.isRunning() and monotonic() < deadline:
            app.processEvents()
            sleep(.01)
        app.processEvents()
        assert not window.worker.isRunning(), 'Playback did not finish'
        assert window.controller.state == 'complete', str(window.controller.error) or window.status.text()
        report['executed_steps'] = len(window.controller.executed_ids)
        assert report['executed_steps'] == len(window.scenario['steps'])
        report['browser_url'] = window.driver.current_url
        # Read final select state where the supplied scenario contains selects.
        if any(node.get('action') == 'select' for node in window.scenario['steps']):
            report['select_state'] = window.driver.execute_script("return Object.fromEntries([...document.querySelectorAll('select')].map(e=>[e.id,[...e.selectedOptions].map(o=>o.textContent.trim())]));")
            from flowtape.browser import Resolver
            resolver = Resolver(window.driver, window.registry)
            final_selections = {node['target']: node for node in window.scenario['steps'] if node.get('action') == 'select'}
            for target, node in final_selections.items():
                control = resolver.target(target)
                selected = resolver.js('return [...arguments[0].selectedOptions].map(o=>FT.norm(o.textContent));', control)
                assert selected == node.get('values', [node.get('value')]), (target, selected)
        assert original.read_bytes() == source_bytes and original.with_name('elements.yaml').read_bytes() == registry_bytes
        assert source.read_bytes() == source_bytes and source.with_name('elements.yaml').read_bytes() == registry_bytes
        report.update(passed=True, state=window.controller.state, original_unchanged=True,
                      browser_restarted=window.driver is not driver)
    except Exception as exc:
        report.update(error=str(exc), status=window.status.text(),
                      state=window.controller.state if window.controller else None)
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.grab().save(str(root / 'flowtape.png'))
        if window.worker and window.worker.isRunning():
            window.controller.stop()
            window.worker.wait(5000)
        window.timer.stop()
        window.recording = window.picking = window.dirty = False
        window.pending_operation = window.pending_credential = window.recorder_error = None
        window.operation_queue.clear()
        window.close()
        app.processEvents()


if __name__ == '__main__': main()
