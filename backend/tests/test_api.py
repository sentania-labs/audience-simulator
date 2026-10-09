from fastapi.testclient import TestClient
import pytest
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PROVIDER_MODE', 'mock')
    return TestClient(app)


def test_no_secret_in_config(client, monkeypatch):
    monkeypatch.setenv('STT_API_KEY', 'private-test-key')
    result = client.get('/api/config')
    assert result.status_code == 200
    assert result.json()['mode'] == 'mock'
    assert 'private-test-key' not in result.text


def test_consent_required(client):
    with client.websocket_connect('/api/meeting', headers={'origin': 'http://localhost:8000'}) as ws:
        ws.send_json({'type': 'join', 'consent': False, 'sample_rate': 48000})
        assert ws.receive_json()['stage'] == 'join'


def test_origin_rejected(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/meeting', headers={'origin': 'http://evil.invalid'}):
            pass


def test_websocket_meeting_end_to_end(client):
    with client.websocket_connect('/api/meeting', headers={'origin': 'http://localhost:8000'}) as ws:
        ws.send_json({'type': 'join', 'consent': True, 'sample_rate': 48000, 'persona': {'name': 'Morgan'}})
        assert ws.receive_json()['type'] == 'joined'
        ws.send_bytes(b'\x00\x00' * 2048)
        ws.send_json({'type': 'mock_turn', 'text': 'Describe the screen.'})
        received = []
        while not any(e['type'] == 'response_done' for e in received):
            received.append(ws.receive_json())
        assert any(e['type'] == 'audio' for e in received)
        assert any(e['type'] == 'transcript' and e['speaker'] == 'presenter' for e in received)
        ws.send_json({'type': 'share', 'enabled': True})
        ws.send_json({'type': 'frame', 'jpeg': '/9g=', 'captured_ms': 0})
        while not any(e['type'] == 'observation' for e in received):
            received.append(ws.receive_json())
        ws.send_json({'type': 'end'})
        while not any(e['type'] == 'summary' for e in received):
            received.append(ws.receive_json())
        assert received[-1]['topics'] == ['Describe the screen.']


def test_bad_frame_rejected(client):
    with client.websocket_connect('/api/meeting', headers={'origin': 'http://localhost:8000'}) as ws:
        ws.send_json({'type':'join','consent':True,'sample_rate':48000})
        assert ws.receive_json()['type'] == 'joined'
        ws.send_json({'type':'frame','jpeg':'not an image','captured_ms':0})
        while True:
            event=ws.receive_json()
            if event['type']=='error':
                assert event['stage']=='protocol'
                break
