import json
import logging

import pytest

from app.diagnostics import record, provider_failure
from app.providers import MockRecognition, MockDialogue, MockVision, MockSpeech
from app.session import Session


@pytest.mark.asyncio
async def test_speech_timeout_identifies_stage_without_leaking_provider_details(caplog):
    import httpx
    caplog.set_level(logging.INFO, logger='audience')
    sent = []
    async def send(event):
        sent.append(event)
    class FailedSpeech:
        async def stream(self, text):
            raise httpx.ReadTimeout('secret provider payload')
            yield b''
    s = Session(send, MockRecognition(), MockDialogue(), MockVision(), FailedSpeech(), {'name': 'Morgan'}, True)
    await s.user_turn('Synthetic diagnostic')
    await s.reply_task
    rows = [json.loads(r.message) for r in caplog.records if r.name == 'audience']
    failure = next(r for r in rows if r['event'] == 'provider_error')
    assert failure['stage'] == 'tts'
    assert failure['error_kind'] == 'read_timeout'
    assert failure['response_id'] == s.generation
    assert 'secret provider payload' not in caplog.text + str(sent)


def test_provider_http_error_exposes_status_only():
    import httpx
    request = httpx.Request('POST', 'https://private.invalid/speech?key=secret',
                            headers={'Authorization': 'Bearer secret'})
    error = httpx.HTTPStatusError('private body', request=request,
                                  response=httpx.Response(429, request=request, text='private body'))
    assert provider_failure(error) == {'error_kind': 'http_status', 'status_code': 429}


def test_metadata_allowlist_and_text_opt_in(caplog):
    caplog.set_level(logging.INFO, logger='audience')
    event = {'type': 'transcript', 'text': 'private spoken words', 'pcm': 'private media',
             'api_key': 'secret-key', 'speaker_role': 'presenter', 'response_id': 4}
    record('session-a', event)
    row = json.loads(caplog.records[-1].message)
    assert row['session_id'] == 'session-a' and row['response_id'] == 4
    assert row['text_length'] == 20
    assert 'private' not in caplog.text and 'secret-key' not in caplog.text
    assert row['time_local'].endswith(('CST', 'CDT'))
    record('session-a', event, transcript=True)
    row = json.loads(caplog.records[-1].message)
    assert row['text'] == 'private spoken words'
    assert 'pcm' not in row and 'api_key' not in row
    record('session-a', {'type': 'observation', 'text': 'private screen'}, transcript=True)
    assert 'text' not in json.loads(caplog.records[-1].message)


@pytest.mark.asyncio
async def test_session_correlates_recognition_audio_playback_and_cancellation(caplog):
    caplog.set_level(logging.INFO, logger='audience')
    sent = []
    async def send(event):
        sent.append(event)
    s = Session(send, MockRecognition(), MockDialogue(), MockVision(), MockSpeech(), {'name': 'Morgan'}, True)
    await s.recognition({'type': 'speech_started'})
    await s.recognition({'type': 'final', 'text': 'private question'})
    await s.turn_task
    await s.reply_task
    await s.emit('audio_state', context_state='running', output_muted=True, gain=0, queued_sources=2)
    await s.emit('playback_started', response_id=s.generation)
    await s.interrupt('presenter')
    rows = [json.loads(r.message) for r in caplog.records if r.name == 'audience']
    assert all(r['session_id'] == s.session_id for r in rows)
    assert {'recognition_speech_started', 'recognition_final', 'audio_sent', 'playback_started', 'cancel'} <= {r['event'] for r in rows}
    assert next(r for r in rows if r['event'] == 'audio_sent')['byte_count'] > 0
    assert next(r for r in rows if r['event'] == 'audio_state')['output_muted'] is True
    assert 'private question' not in caplog.text
    assert all(e['session_id'] == s.session_id for e in s.events)
