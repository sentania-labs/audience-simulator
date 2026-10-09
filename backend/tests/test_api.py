from fastapi.testclient import TestClient
import pytest
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('PROVIDER_MODE', 'mock')
    monkeypatch.setenv('DATA_PATH', str(tmp_path/'control.db'))
    monkeypatch.setenv('MEETING_PASSWORD', 'meeting-test-password')
    monkeypatch.setenv('ADMIN_PASSWORD', 'admin-test-password')
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    client = TestClient(app)
    assert client.post('/api/auth/meeting/login', json={'password':'meeting-test-password'}, headers={'origin':'http://localhost:8000'}).status_code == 200
    return client


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


def test_auth_enforcement_and_separate_admin(client):
    from starlette.websockets import WebSocketDisconnect
    assert client.get('/api/admin').status_code == 401
    assert client.post('/api/auth/admin/login',json={'password':'admin-test-password'},headers={'origin':'http://evil.invalid'}).status_code == 403
    assert client.post('/api/auth/admin/login',json={'password':'admin-test-password'},headers={'origin':'http://localhost:8000'}).status_code == 200
    assert client.get('/api/admin').status_code == 200
    client.post('/api/auth/meeting/logout',json={},headers={'origin':'http://localhost:8000'})
    assert client.get('/api/config').status_code == 401
    assert client.get('/api/admin').status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}):
            pass


def test_two_meetings_are_isolated_and_named_speaker(client):
    headers={'origin':'http://localhost:8000'}
    with client.websocket_connect('/api/meeting',headers=headers) as first:
        first.send_json(dict(type='join',consent=True,sample_rate=48000,attendees=[{'name':'Morgan'},{'name':'Riley'}]))
        a=first.receive_json()
        with client.websocket_connect('/api/meeting',headers=headers) as second:
            second.send_json(dict(type='join',consent=True,sample_rate=48000))
            b=second.receive_json()
            assert a['session_id'] != b['session_id']
            first.send_json(dict(type='mock_turn',text='Riley, discuss the secret cedar plan'))
            events=[]
            while not any(e['type']=='transcript' and e.get('speaker')=='Riley' for e in events):
                events.append(first.receive_json())
            second.send_json(dict(type='end'))
            while True:
                event=second.receive_json()
                if event['type']=='summary':
                    assert event['topics']==[]
                    break
            first.send_json(dict(type='end'))
            while first.receive_json()['type']!='summary':
                pass


def test_time_limit_ends_cleanly_with_summary(client, monkeypatch):
    from app.main import control
    control().max_seconds=.1
    with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}) as ws:
        ws.send_json(dict(type='join',consent=True,sample_rate=48000))
        events=[]
        while not any(e['type']=='summary' for e in events):
            events.append(ws.receive_json())
        assert any(e['type']=='limit' for e in events)


def test_budget_cutoff_stops_before_paid_dialogue_and_preserves_recap(client, monkeypatch):
    import app.main as main
    from app.providers import MockRecognition, MockVision, MockSpeech
    from app.config import Settings
    class ExpensiveDialogue:
        calls=0
        async def stream(self, messages):
            self.budget.reserve('dialogue', 1_000_000)
            self.calls += 1
            yield 'Must never run'
    dialogue=ExpensiveDialogue()
    monkeypatch.setenv('PROVIDER_MODE','hosted')
    monkeypatch.setenv('STT_API_KEY','fake-test-only')
    for component in ('DIALOGUE','VISION'):
        monkeypatch.setenv(component+'_MODEL','gpt-4.1-mini')
    monkeypatch.setenv('TTS_MODEL','gpt-4o-mini-tts')
    main.control().meeting_limit=10_000
    monkeypatch.setattr(main,'adapters',lambda settings:(MockRecognition(),dialogue,MockVision(),MockSpeech()))
    with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}) as ws:
        ws.send_json(dict(type='join',consent=True,sample_rate=48000))
        events=[]
        while not any(e['type']=='summary' for e in events):
            events.append(ws.receive_json())
        assert any(e['type']=='limit' for e in events)
        assert dialogue.calls==0
    assert main.control().stats()['meetings'][0]['status']=='limited'


def test_initial_stt_reservation_cutoff_has_single_shutdown(client, monkeypatch):
    import app.main as main
    from app.providers import MockRecognition, MockDialogue, MockVision, MockSpeech
    monkeypatch.setenv('PROVIDER_MODE','hosted')
    monkeypatch.setenv('STT_API_KEY','fake-test-only')
    for component in ('DIALOGUE','VISION'):
        monkeypatch.setenv(component+'_MODEL','gpt-4.1-mini')
    monkeypatch.setenv('TTS_MODEL','gpt-4o-mini-tts')
    main.control().meeting_limit=1
    monkeypatch.setattr(main,'adapters',lambda settings:(MockRecognition(),MockDialogue(),MockVision(),MockSpeech()))
    with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}) as ws:
        ws.send_json(dict(type='join',consent=True,sample_rate=48000))
        events=[]
        while not any(e['type']=='summary' for e in events):
            events.append(ws.receive_json())
        assert sum(e['type']=='limit' for e in events)==1


def test_first_attendee_voice_is_used_for_greeting(client, monkeypatch):
    import app.main as main
    from app.providers import MockRecognition, MockDialogue, MockVision, MockSpeech
    class Speech(MockSpeech):
        voice='alloy'
        used=[]
        async def stream(self, text):
            self.used.append(self.voice)
            async for chunk in super().stream(text):
                yield chunk
    speech=Speech()
    monkeypatch.setenv('TTS_VOICE','alloy')
    monkeypatch.setenv('TTS_VOICES',' coral , ash ')
    monkeypatch.setattr(main,'adapters',lambda settings:(MockRecognition(),MockDialogue(),MockVision(),speech))
    with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}) as ws:
        ws.send_json(dict(type='join',consent=True,sample_rate=48000,attendees=[{'name':'Morgan'},{'name':'Riley'}]))
        while ws.receive_json()['type']!='response_done':
            pass
        assert speech.used and set(speech.used)=={'coral'}
        ws.send_json(dict(type='end'))
        while ws.receive_json()['type']!='summary':
            pass


def test_interrupt_then_silence_allows_visual_followup(client):
    with client.websocket_connect('/api/meeting',headers={'origin':'http://localhost:8000'}) as ws:
        ws.send_json(dict(type='join',consent=True,sample_rate=48000))
        assert ws.receive_json()['type']=='joined'
        ws.send_json(dict(type='interrupt'))
        ws.send_json(dict(type='speech_end'))
        ws.send_json(dict(type='share',enabled=True))
        ws.send_json(dict(type='frame',jpeg='/9g=',captured_ms=0))
        while ws.receive_json()['type']!='observation':
            pass
        while ws.receive_json()['type']!='response_done':
            pass
        ws.send_json(dict(type='end'))
        while ws.receive_json()['type']!='summary':
            pass
