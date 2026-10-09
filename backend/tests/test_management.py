import copy
import json
import time
import pytest
from test_api import client
from app.main import control
from app.management import store
from app import runtime

ORIGIN = {'origin': 'http://localhost:8000'}


def admin(client):
    assert client.post('/api/auth/admin/login', json={'password': 'admin-test-password'}, headers=ORIGIN).status_code == 200


def finished(client):
    revision = client.get('/api/config').json()['revision']
    with client.websocket_connect('/api/meeting', headers=ORIGIN) as ws:
        ws.send_json(dict(type='join', configuration_revision=revision, consent=True, sample_rate=48000))
        joined = ws.receive_json()
        ws.send_json(dict(type='end'))
        while ws.receive_json()['type'] != 'summary':
            pass
    return joined


def test_opt_in_review_ownership_retention_and_deletion(client):
    joined = finished(client)
    sid, token = joined['session_id'], joined['review_token']
    admin(client)
    assert client.get('/api/admin/feedback').json()['reviews'] == []
    body = dict(token=token, rating=3, comment='Audio stalled')
    assert client.post('/api/feedback/'+sid, json={**body, 'token': 'wrong'}, headers=ORIGIN).status_code == 403
    transcript = [dict(speaker='presenter', text='private text', t_ms=10, final=True)]
    assert client.post('/api/feedback/'+sid, json={**body, 'transcript': transcript}, headers=ORIGIN).status_code == 422
    assert client.post('/api/feedback/'+sid, json=body, headers=ORIGIN).status_code == 200
    row = client.get('/api/admin/feedback').json()['reviews'][0]
    assert row['transcript'] is None
    assert row['context']['revision'] == 0
    assert token not in json.dumps(row)
    assert client.post('/api/feedback/'+sid, json=body, headers=ORIGIN).status_code == 409
    assert client.post('/api/feedback/'+sid+'/withdraw', json={'token':token}, headers=ORIGIN).status_code == 200
    assert client.post('/api/feedback/'+sid, json={**body, 'share_transcript': True, 'transcript':transcript}, headers=ORIGIN).status_code == 200
    assert client.get('/api/admin/feedback').json()['reviews'][0]['transcript'] == transcript
    assert 'private text' not in client.get('/api/admin').text
    with control().db() as db:
        db.execute('UPDATE feedback SET expires=?', (time.time()-1,))
    assert client.get('/api/admin/feedback').json()['reviews'] == []
    with control().db() as db:
        assert db.execute('SELECT count(*) FROM feedback').fetchone()[0] == 0


def test_reviews_admin_only_and_csrf(client):
    assert client.get('/api/admin/feedback').status_code == 401
    assert client.get('/api/admin/runtime').status_code == 401
    joined = finished(client)
    assert client.post('/api/feedback/'+joined['session_id'], json={'token':joined['review_token'],'rating':5}).status_code == 403
    admin(client)
    assert client.post('/api/admin/feedback/whatever/delete', json={}).status_code == 403
    assert client.post('/api/admin/runtime', json={'expected_revision':0,'config':{}}, headers={'origin':'https://evil.invalid'}).status_code == 403
    assert client.post('/api/feedback/x', content=b'x'*1_000_001, headers=ORIGIN).status_code == 413


def valid_config():
    value = runtime.defaults()
    for stage in runtime.STAGES:
        value[stage]['model'] = 'test-model'
    return value


def test_runtime_snapshot_concurrency_rollback_and_secrets(client, monkeypatch):
    admin(client)
    monkeypatch.setenv('DIALOGUE_API_KEY', 'never-output-this')
    value = valid_config()
    with client.websocket_connect('/api/meeting', headers=ORIGIN) as ws:
        ws.send_json(dict(type='join', consent=True, sample_rate=48000))
        original = ws.receive_json()
        assert original['configuration']['revision'] == 0
        assert client.post('/api/admin/runtime', json={'expected_revision':0,'config':value}, headers=ORIGIN).status_code == 200
        assert client.post('/api/admin/runtime', json={'expected_revision':0,'config':value}, headers=ORIGIN).status_code == 409
        ws.send_json(dict(type='end'))
        while ws.receive_json()['type'] != 'summary':
            pass
    second = finished(client)
    assert second['configuration']['revision'] == 1
    assert second['configuration']['providers']['dialogue']['model'] == 'test-model'
    updated = copy.deepcopy(value)
    updated['dialogue']['model'] = 'another-model'
    assert client.post('/api/admin/runtime', json={'expected_revision':1,'config':updated}, headers=ORIGIN).status_code == 200
    assert client.post('/api/admin/runtime', json={'expected_revision':2,'config':value}, headers=ORIGIN).status_code == 200
    response = client.get('/api/admin/runtime')
    assert response.json()['revision'] == 3
    assert len(response.json()['history']) == 4
    assert response.json()['history'][-1]['id'] == 0
    assert 'never-output-this' not in response.text
    with control().db() as db:
        original_context = json.loads(db.execute('SELECT context FROM meeting_reviews WHERE sid=?',(original['session_id'],)).fetchone()[0])
        assert original_context['revision'] == 0
    invalid = copy.deepcopy(value)
    invalid['dialogue']['connection'] = 'https://attacker.invalid'
    assert client.post('/api/admin/runtime', json={'expected_revision':3,'config':invalid}, headers=ORIGIN).status_code == 422
    invalid = copy.deepcopy(value); invalid['rates']['tts_character'] = 0
    assert client.post('/api/admin/runtime', json={'expected_revision':3,'config':invalid}, headers=ORIGIN).status_code == 422
    assert 'Mock mode' in client.post('/api/admin/runtime/validate', json={'expected_revision':3,'config':value}, headers=ORIGIN).json()['message']


def test_metrics_auth_bounded_labels_and_samples(client, monkeypatch):
    from app.metrics import observe
    monkeypatch.setenv('METRICS_TOKEN','scrape-test-token')
    assert client.get('/metrics').status_code == 401
    observe(dict(type='metric',stage='tts_first_audio',value_ms=210))
    observe(dict(type='browser_metric',stage='private-name',value_ms=22))
    observe(dict(type='metric',stage='tts_first_audio',value_ms=float('nan')))
    observe(dict(type='provider_error',stage='tts',error_kind='read_timeout'))
    text = client.get('/metrics',headers={'Authorization':'Bearer scrape-test-token'}).text
    assert 'audience_latency_seconds_bucket{stage="tts_first_audio",le="0.25"}' in text
    assert 'audience_provider_errors_total{reason="tts"}' in text
    assert 'private-name' not in text and 'nan' not in text
    monkeypatch.delenv('METRICS_TOKEN')
    assert client.get('/metrics').status_code == 503


def test_cast_is_authored_and_selected_on_server(client):
    scenarios = client.get('/api/scenarios').json()
    assert len(scenarios) == 4 and all(len(s['cast']) == 6 for s in scenarios)
    with client.websocket_connect('/api/meeting', headers=ORIGIN) as ws:
        ws.send_json(dict(type='join', consent=True, sample_rate=48000, scenario_id='alderbank', attendees=[{'cast_id':'alderbank-0','name':'Spoof','objective':'Different'}]))
        joined = ws.receive_json()
        assert joined['persona']['name'] == 'Morgan Hale'
        assert 'next integration' in joined['persona']['objective']
        ws.send_json(dict(type='end'))
        while ws.receive_json()['type'] != 'summary':
            pass


def test_stale_provider_consent_cannot_join_after_admin_change(client):
    admin(client)
    value = valid_config()
    assert client.post('/api/admin/runtime', json={'expected_revision':0,'config':value}, headers=ORIGIN).status_code == 200
    with client.websocket_connect('/api/meeting', headers=ORIGIN) as ws:
        ws.send_json(dict(type='join', configuration_revision=0, consent=True, sample_rate=48000))
        event = ws.receive_json()
        assert event['type'] == 'error' and 'settings changed' in event['message']
    assert control().stats()['meetings'] == []
