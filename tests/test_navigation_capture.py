from flowtape.navigation_capture import NavigationCapture
from flowtape.recorder import EventNormalizer
from flowtape.recorder_trace import RecorderTrace


def capture():
    result = NavigationCapture('window', RecorderTrace())
    result.frame_id = 'root'
    result.set_mode('record')
    return result


def start(recorder, url='https://test/start', loader='loader', kind='differentDocument', frame='root'):
    recorder.receive('Page.frameStartedNavigating', {'frameId': frame, 'loaderId': loader,
                                                    'url': url, 'navigationType': kind})


def commit(recorder, url='https://test/start', loader='loader', frame='root', **extra):
    recorder.receive('Page.frameNavigated', {'frame': {'id': frame, 'loaderId': loader, 'url': url, **extra}})


def test_address_navigation_records_entered_url_once_after_commit():
    recorder = capture()
    start(recorder)
    assert recorder.drain() == []
    # A server redirect is part of the original open, not another operation.
    start(recorder, url='https://test/redirected')
    commit(recorder, url='https://test/redirected')
    commit(recorder, url='https://test/redirected')
    events = recorder.drain()
    assert len(events) == 1
    op, = EventNormalizer().consume(events)
    assert op.action == 'open' and op.data['url'] == 'https://test/start'
    assert op.url == 'https://test/redirected' and op.handle == 'window'


def test_renderer_navigation_never_adds_duplicate_open():
    recorder = capture()
    recorder.receive('Page.frameRequestedNavigation', {'frameId': 'root', 'url': 'https://test/start'})
    start(recorder)
    commit(recorder)
    assert recorder.drain() == []
    start(recorder, loader='direct')
    commit(recorder, loader='direct')
    assert len(recorder.drain()) == 1


def test_navigation_boundaries_cancellation_and_unknown_actions():
    recorder = capture()
    start(recorder)
    recorder.set_mode('observe')
    commit(recorder)
    start(recorder)
    recorder.set_mode('record')
    commit(recorder)
    start(recorder, frame='iframe')
    commit(recorder, frame='iframe')
    start(recorder, loader='cancelled')
    commit(recorder, loader='other')
    for kind in ['historyDifferentDocument', 'reload', 'sameDocument', 'unknown']:
        start(recorder, kind=kind)
        commit(recorder)
    start(recorder)
    commit(recorder, unreachableUrl='https://test/start')
    assert recorder.drain() == []


def test_application_url_command_suppression_and_reset():
    recorder = capture()
    recorder.suppressed = True
    start(recorder)
    recorder.suppressed = False
    commit(recorder)
    assert recorder.drain() == []
    start(recorder)
    commit(recorder)
    recorder.reset()
    assert recorder.drain() == []


def test_navigation_flushes_prior_click_before_open():
    normalizer = EventNormalizer()
    click = {'protocol_version': 1, 'document_instance_id': 'source', 'event_seq': 1,
             'type': 'click', 'target': None, 'document': {'url': 'https://test/old'}}
    assert normalizer.consume([click], now=0) == []
    recorder = capture()
    start(recorder)
    commit(recorder)
    assert [op.action for op in normalizer.consume(recorder.drain(), now=.1)] == ['click', 'open']


def test_configure_accepts_destroyed_frame_but_propagates_live_target_failure():
    from types import SimpleNamespace
    from unittest.mock import Mock
    import pytest
    from selenium.common.exceptions import WebDriverException
    from flowtape.recorder import RecorderTransport
    recorder = object.__new__(RecorderTransport)
    recorder.mode = 'observe'
    recorder.page_conditions = {}
    recorder.trace = RecorderTrace()
    recorder.driver = Mock()
    recorder.driver.execute_cdp_cmd.return_value = {'targetInfos': []}
    frame = SimpleNamespace(handle=None, target_id='gone', navigation=Mock(),
                            configure=Mock(side_effect=WebDriverException('session lost')),
                            connection=SimpleNamespace(detached=False))
    recorder._configure_bridge(frame)
    assert frame.connection.detached
    recorder.driver.execute_cdp_cmd.return_value = {'targetInfos': [{'targetId': 'gone'}]}
    with pytest.raises(WebDriverException):
        recorder._configure_bridge(frame)


def test_source_binding_is_ingested_before_following_browser_commit():
    import json
    from unittest.mock import patch
    from selenium.webdriver.remote.websocket_connection import WebSocketConnection
    from flowtape.capture_bridge import CaptureConnection
    recorder = capture()
    connection = object.__new__(CaptureConnection)
    connection.navigation = recorder
    connection.session_id = 'session'
    received = []
    connection.binding_receiver = lambda data: received.append(json.loads(data['payload']))
    click = {'protocol_version': 1, 'document_instance_id': 'source', 'event_seq': 1,
             'type': 'click', 'target': None, 'document': {'url': 'https://test/source'}}
    with patch.object(WebSocketConnection, '_process_message') as asynchronous_dispatch:
        connection._process_message(json.dumps({'method': 'Runtime.bindingCalled', 'params': {
            'name': '__flowtape_emit', 'payload': json.dumps(click)}}))
        asynchronous_dispatch.assert_not_called()
        connection._process_message(json.dumps({'method': 'Page.frameStartedNavigating', 'params': {
            'frameId': 'root', 'loaderId': 'loader', 'url': 'https://test/start', 'navigationType': 'differentDocument'}}))
        connection._process_message(json.dumps({'method': 'Page.frameNavigated', 'params': {
            'frame': {'id': 'root', 'loaderId': 'loader', 'url': 'https://test/start'}}}))
    received.extend(recorder.drain())
    assert [op.action for op in EventNormalizer().consume(received)] == ['click', 'open']
