import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .providers import adapters
from .session import Session

logging.basicConfig(level=logging.INFO, format='%(message)s')
app = FastAPI(title='Audience Simulator')


class Persona(BaseModel):
    name: str = Field(default='Morgan', min_length=1, max_length=80)
    role: str = Field(default='Enterprise infrastructure architect', max_length=300)
    expertise: str = Field(default='VCF, networking, virtualization and platform operations', max_length=600)
    style: str = Field(default='Technically precise, curious and candid', max_length=300)
    objective: str = Field(default='', max_length=1000)


@app.get('/api/config')
def config():
    s = Settings()
    return {'mode': 'mock' if s.mock else 'hosted', 'missing': s.missing(),
            'providers': {'stt': urlparse(s.stt_url).hostname,
                          'dialogue': urlparse(s.dialogue.base).hostname,
                          'vision': urlparse(s.vision.base).hostname,
                          'tts': urlparse(s.tts.base).hostname},
            'retention': 'Server memory for the connection only. No raw audio or frames stored. Export is optional.'}


@app.get('/healthz')
def health():
    return {'status': 'ok', 'provider_ready': not Settings().missing()}


@app.websocket('/api/meeting')
async def meeting(ws: WebSocket):
    s = Settings()
    if ws.headers.get('origin') not in s.origins:
        await ws.close(code=1008)
        return
    await ws.accept()
    session = None
    lock = asyncio.Lock()

    async def send(event):
        async with lock:
            await ws.send_json(event)

    try:
        async with asyncio.timeout(15):
            join = await ws.receive_json()
        rate = join.get('sample_rate')
        if (join.get('type') != 'join' or not join.get('consent') or s.missing()
                or not isinstance(rate, int) or not 8000 <= rate <= 96000):
            await send({'type': 'error', 'stage': 'join', 'message': 'Consent, provider configuration and valid audio rate required.'})
            await ws.close(code=1008)
            return
        persona = Persona.model_validate(join.get('persona', {})).model_dump()
        stt, dialogue, vision, tts = adapters(s)
        session = Session(send, stt, dialogue, vision, tts, persona, s.mock)
        try:
            await stt.start(rate, session.recognition)
        except Exception:
            await send({'type': 'error', 'stage': 'stt', 'message': 'Recognition connection failed. Check server provider configuration.'})
            return
        await session.emit('joined', persona=persona, mode='mock' if s.mock else 'hosted')
        session.begin_reply('Introduce yourself in one short sentence and invite the presenter to begin.')
        while not session.ended:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect':
                break
            if message.get('bytes') is not None:
                pcm = message['bytes']
                if len(pcm) > 32768 or len(pcm) % 2:
                    raise ValueError('invalid PCM')
                await stt.send(pcm)
                continue
            raw = message.get('text', '')
            if len(raw) > 1_500_000:
                raise ValueError('message too large')
            data = json.loads(raw)
            kind = data.get('type')
            if kind == 'interrupt':
                session.speech_active = True
                await session.interrupt()
            elif kind == 'speech_end':
                session.speech_active = False
                session.speech_end = __import__('time').monotonic()
            elif kind == 'share':
                await session.share(bool(data.get('enabled')))
            elif kind == 'frame':
                jpeg = data.get('jpeg', '')
                captured = data.get('captured_ms')
                decoded = base64.b64decode(jpeg, validate=True)
                if not decoded.startswith(b'\xff\xd8') or len(decoded) > 1_000_000:
                    raise ValueError('invalid JPEG')
                if not isinstance(captured, (int, float)) or not 0 <= captured <= session.now() + 3000:
                    raise ValueError('invalid capture timestamp')
                await session.frame(jpeg, round(captured), bool(data.get('changed', True)))
            elif kind == 'mock_turn' and s.mock:
                await session.recognition({'type': 'final', 'text': str(data.get('text', ''))[:4000]})
            elif kind in ('playback_started', 'playback_stopped', 'playback_ended', 'browser_metric', 'mute'):
                # Explicit fields only, no arbitrary client payload in the record.
                await session.emit(kind, response_id=data.get('response_id'),
                                   value_ms=data.get('value_ms'), stage=str(data.get('stage', ''))[:80],
                                   enabled=bool(data.get('enabled')))
            elif kind == 'end':
                await session.end()
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (ValueError, ValidationError, TimeoutError):
        try:
            await send({'type': 'error', 'stage': 'protocol', 'message': 'Invalid meeting message or join timeout.'})
        except RuntimeError:
            pass
    finally:
        if session:
            session.ended = True
            for task in (session.reply_task, session.vision_task):
                if task:
                    task.cancel()
            await asyncio.gather(*(t for t in (session.reply_task, session.vision_task) if t), return_exceptions=True)
            await session.stt.close()
        try:
            await ws.close()
        except RuntimeError:
            pass


static_dir = Path(os.getenv('FRONTEND_DIST', 'frontend/dist'))
if static_dir.exists():
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')
