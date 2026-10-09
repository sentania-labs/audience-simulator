import json
import httpx
import pytest
from app.config import Endpoint
from app.providers import ChatDialogue, ImageVision, PCMSpeech


@pytest.mark.asyncio
async def test_http_adapters_use_separate_protocols(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/audio/speech'):
            return httpx.Response(200, content=b'\x01\x00'*2400)
        body = json.loads(request.content)
        if body.get('stream'):
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hello."}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={'choices':[{'message':{'content':'Observed visible state, small labels unreadable.'}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    ep=Endpoint('https://provider.invalid/v1','configured-model','secret-value')
    assert ''.join([t async for t in ChatDialogue(ep).stream([{'role':'user','content':'hi'}])])=='Hello.'
    assert 'unreadable' in await ImageVision(ep).observe('/9g=')
    chunks=[chunk async for chunk in PCMSpeech(ep,'fixed-voice').stream('Hello.')]
    assert sum(map(len,chunks))==4800
    vision=json.loads(requests[1].content)
    assert vision['messages'][1]['content'][1]['image_url']['url']=='data:image/jpeg;base64,/9g='
    assert 'untrusted' in vision['messages'][0]['content']
    tts=json.loads(requests[2].content)
    assert tts['voice']=='fixed-voice'
    assert tts['response_format']=='pcm'


@pytest.mark.asyncio
async def test_streamed_recognition_protocol_and_segment_assembly(monkeypatch):
    import asyncio
    from urllib.parse import parse_qs, urlparse
    import websockets
    from app.config import Settings
    from app.providers import DeepgramRecognition
    received = []
    finalized = asyncio.Event()
    async def listen(ws):
        query=parse_qs(urlparse(ws.request.path).query)
        assert query['sample_rate']==['48000']
        assert query['encoding']==['linear16']
        assert ws.request.headers['Authorization']=='Token test-only'
        assert await ws.recv()==b'\x00\x00'*2048
        await ws.send(json.dumps({'type':'SpeechStarted'}))
        await ws.send(json.dumps({'type':'Results','is_final':True,'speech_final':False,
                                  'channel':{'alternatives':[{'transcript':'Earlier slide'}]}}))
        await ws.send(json.dumps({'type':'Results','is_final':True,'speech_final':True,
                                  'channel':{'alternatives':[{'transcript':'showed the workload domain.'}]}}))
        await finalized.wait()
    async def callback(event):
        received.append(event)
        if event['type']=='final':finalized.set()
    async with websockets.serve(listen,'127.0.0.1',0) as server:
        port=server.sockets[0].getsockname()[1]
        monkeypatch.setenv('STT_URL',f'ws://127.0.0.1:{port}/v1/listen')
        monkeypatch.setenv('STT_API_KEY','test-only')
        recognition=DeepgramRecognition(Settings())
        try:
            await recognition.start(48000,callback)
            await recognition.send(b'\x00\x00'*2048)
            await asyncio.wait_for(finalized.wait(),2)
            assert received[0]['type']=='speech_started'
            assert received[-1]=={'type':'final','text':'Earlier slide showed the workload domain.'}
        finally:
            await recognition.close()


@pytest.mark.asyncio
async def test_elevenlabs_stream_events_and_provider_selection(monkeypatch):
    import asyncio
    import base64
    from urllib.parse import parse_qs, urlparse
    import websockets
    from app.config import Settings
    from app.providers import ElevenLabsRecognition, adapters
    events = []
    complete = asyncio.Event()
    async def listen(ws):
        query = parse_qs(urlparse(ws.request.path).query)
        assert query['audio_format'] == ['pcm_48000']
        assert query['commit_strategy'] == ['vad']
        assert ws.request.headers['xi-api-key'] == 'test-only'
        await ws.send(json.dumps({'message_type': 'session_started'}))
        audio = json.loads(await ws.recv())
        assert audio['sample_rate'] == 48000
        assert base64.b64decode(audio['audio_base_64']) == b'\x00\x00' * 2048
        for kind, text in [('partial_transcript', 'Management'),
                           ('partial_transcript', 'Management domain'),
                           ('committed_transcript', 'Management domain.'),
                           ('partial_transcript', 'Workload'),
                           ('committed_transcript', 'Workload domain.')]:
            await ws.send(json.dumps({'message_type': kind, 'text': text}))
        await complete.wait()
    async def callback(event):
        events.append(event)
        if event.get('text') == 'Workload domain.':
            complete.set()
    async with websockets.serve(listen, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setenv('PROVIDER_MODE', 'hosted')
        monkeypatch.setenv('STT_PROVIDER', 'elevenlabs')
        monkeypatch.setenv('STT_URL', f'ws://127.0.0.1:{port}/realtime')
        monkeypatch.setenv('STT_API_KEY', 'test-only')
        recognition, *_ = adapters(Settings())
        assert isinstance(recognition, ElevenLabsRecognition)
        try:
            await recognition.start(48000, callback)
            await recognition.send(b'\x00\x00' * 2048)
            await asyncio.wait_for(complete.wait(), 2)
            assert sum(e['type'] == 'speech_started' for e in events) == 2
            assert [e['text'] for e in events if e['type'] == 'final'] == [
                'Management domain.', 'Workload domain.']
        finally:
            await recognition.close()


@pytest.mark.asyncio
async def test_elevenlabs_rejected_session_is_not_ready(monkeypatch):
    import websockets
    from app.config import Settings
    from app.providers import ElevenLabsRecognition
    async def reject(ws):
        await ws.send(json.dumps({'message_type': 'auth_error', 'error': 'sensitive provider body'}))
    async with websockets.serve(reject, '127.0.0.1', 0) as server:
        monkeypatch.setenv('STT_PROVIDER', 'elevenlabs')
        monkeypatch.setenv('STT_URL', f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/realtime')
        recognition = ElevenLabsRecognition(Settings())
        with pytest.raises(ValueError, match='did not accept') as error:
            await recognition.start(48000, lambda event: None)
        assert 'sensitive provider body' not in str(error.value)
        await recognition.close()


def test_recognition_defaults_follow_selected_provider(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv('PROVIDER_MODE', 'hosted')
    monkeypatch.setenv('STT_URL', '')
    monkeypatch.setenv('STT_MODEL', '')
    monkeypatch.setenv('STT_PROVIDER', 'elevenlabs')
    s = Settings()
    assert s.stt_model == 'scribe_v2_realtime'
    assert 'elevenlabs.io' in s.stt_url
    monkeypatch.setenv('STT_PROVIDER', 'deepgram')
    s = Settings()
    assert s.stt_model == 'nova-3'
    assert 'deepgram.com' in s.stt_url
    monkeypatch.setenv('STT_PROVIDER', 'not-a-provider')
    assert 'STT_PROVIDER' in Settings().missing()[0]
