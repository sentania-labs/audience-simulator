import asyncio
import base64
import json
import logging
import os
import time
from functools import lru_cache
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .providers import adapters
from .session import Session
from .judge import JevObserver
from .control import Control, LimitReached
from .budget import Budget

logging.basicConfig(level=logging.INFO, format='%(message)s')
# HTTP client logs can contain endpoint query credentials. Use our bounded events.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            review_store().prune()
            await asyncio.sleep(3600)
    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title='Audience Simulator', lifespan=lifespan)
from .management import router, settings as runtime_settings, store as review_store
app.include_router(router)


@lru_cache(maxsize=4)
def control_at(path):
    return Control(path)


def control():
    return control_at(os.getenv('DATA_PATH', 'data/control.sqlite3'))


def require(request, role):
    if not control().authorized(request.cookies.get('audience_'+role), role):
        raise HTTPException(401, 'Login required')


def same_origin(request):
    if request.headers.get('origin') not in Settings().origins:
        raise HTTPException(403, 'Origin rejected')


class Login(BaseModel):
    password: str = Field(max_length=256)


@app.post('/api/auth/{role}/login')
async def login(role: str, body: Login, request: Request, response: Response):
    if role not in ('meeting', 'admin'):
        raise HTTPException(404)
    same_origin(request)
    try:
        token = control().login(role, body.password, request.client.host if request.client else 'unknown')
    except LimitReached as exc:
        raise HTTPException(429, str(exc))
    if not token:
        raise HTTPException(401, 'Incorrect password or login not configured')
    response.set_cookie('audience_'+role, token, httponly=True, samesite='strict',
                        secure=os.getenv('COOKIE_SECURE', 'true').lower()=='true', max_age=28800, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True}


@app.post('/api/auth/{role}/logout')
def logout(role: str, request: Request, response: Response):
    if role not in ('meeting', 'admin'):
        raise HTTPException(404)
    same_origin(request)
    control().logout(request.cookies.get('audience_'+role))
    response.delete_cookie('audience_'+role, path='/')
    return {'authenticated': False}


@app.get('/api/admin')
def admin(request: Request):
    require(request, 'admin')
    return control().stats()


class Admission(BaseModel):
    paused: bool


@app.post('/api/admin/admission')
def admission(body: Admission, request: Request):
    require(request, 'admin')
    same_origin(request)
    control().pause(body.paused)
    return {'paused': body.paused}


@app.middleware('http')
async def security_headers(request, call_next):
    if request.method == 'POST':
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                return Response('Request too large', status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self'; frame-ancestors 'none'"
    return response


from .cast import SCENARIOS, find_person


@app.get('/api/scenarios')
def scenarios(request: Request):
    require(request, 'meeting')
    return SCENARIOS


class Persona(BaseModel):
    cast_id: str = Field(default='', max_length=80)
    name: str = Field(default='Morgan', min_length=1, max_length=80)
    role: str = Field(default='Enterprise infrastructure architect', max_length=300)
    expertise: str = Field(default='Networking, recovery, virtualization and platform operations', max_length=600)
    style: str = Field(default='Technically precise, curious and candid', max_length=300)
    objective: str = Field(default='', max_length=1000)


@app.get('/api/config')
def config(request: Request):
    require(request, 'meeting')
    try:
        s = runtime_settings()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Runtime provider configuration needs administrator attention')
    missing = s.missing()
    try:
        Budget(control(), '', s, lambda _: None)
    except (ValueError, TypeError):
        missing.append('COST_RATES_JSON: valid pricing required for configured providers')
    return {'revision': s.runtime_snapshot['revision'], 'mode': 'mock' if s.mock else 'hosted', 'missing': missing, 'limits': control().limits(),
            'providers': {'stt': urlparse(s.stt_url).hostname,
                          'dialogue': urlparse(s.dialogue.base).hostname,
                          'vision': urlparse(s.vision.base).hostname,
                          'judge': 'api.typesafe.ai' if s.jev_shadow and s.jev_key and not s.mock else None,
                          'tts': urlparse(s.tts.base).hostname},
            'retention': ('Session review is held in memory. Usage estimates and session statistics persist on the server. Transcripts are saved only if you explicitly submit them with feedback, retained for 30 days. Feedback can be withdrawn in this tab or deleted by an administrator. No images are saved. Server diagnostic metadata is logged. '
                          + ('Transcript text is also logged for troubleshooting. ' if s.log_transcripts else 'Transcript text is not logged. ')
                          + 'No raw audio or frames stored. Export is optional. Container logs rotate at 3 files of 10 MB.')}


@app.get('/healthz')
def health():
    return {'status': 'ok', 'provider_ready': not Settings().missing()}


@app.websocket('/api/meeting')
async def meeting(ws: WebSocket):
    try:
        s = runtime_settings()
    except (ValueError, KeyError, TypeError):
        await ws.close(code=1013)
        return
    ctl = control()
    if (ws.headers.get('origin') not in s.origins
            or not ctl.authorized(ws.cookies.get('audience_meeting'), 'meeting')):
        await ws.close(code=1008)
        return
    await ws.accept()
    session = None
    watchdog = None
    cutoff_task = None
    end_reason = 'disconnected'
    lock = asyncio.Lock()

    async def send(event):
        if session:
            ctl.event(session.session_id, event)
            if event['type'] == 'summary':
                # The review is actionable as soon as the browser receives it.
                ctl.finish(session.session_id, session.now(), end_reason)
                review_store().finish(session.session_id, session.measurements)
        async with lock:
            await ws.send_json(event)

    try:
        async with asyncio.timeout(15):
            join = await ws.receive_json()
        if join.get('configuration_revision', 0) != s.runtime_snapshot['revision']:
            await send({'type': 'error', 'stage': 'join', 'message': 'Meeting settings changed. Reload the page, review the provider data flow and join again.'})
            await ws.close(code=1008)
            return
        rate = join.get('sample_rate')
        if (join.get('type') != 'join' or not join.get('consent') or s.missing()
                or not isinstance(rate, int) or not 8000 <= rate <= 96000):
            await send({'type': 'error', 'stage': 'join', 'message': 'Consent, provider configuration and valid audio rate required.'})
            await ws.close(code=1008)
            return
        raw_attendees = join.get('attendees', [join.get('persona', {})])
        if not isinstance(raw_attendees, list) or not 1 <= len(raw_attendees) <= ctl.max_attendees:
            raise ValueError('invalid attendee count')
        attendees = [Persona.model_validate(p).model_dump() for p in raw_attendees]
        for p in attendees:
            if p['cast_id']:
                canonical = find_person(p['cast_id'])
                if canonical is None:
                    raise ValueError('Unknown cast member')
                p.update({key: value for key, value in canonical.items() if key != 'id'})
        if len({p['name'].strip().casefold() for p in attendees}) != len(attendees):
            raise ValueError('Attendee names must be distinct')
        voices = getattr(s, 'voices', None) or [voice.strip() for voice in os.getenv('TTS_VOICES', s.voice+',ash,sage,echo').split(',')]
        if any(not v for v in voices) or len(voices) < len(attendees) or len(set(voices[:len(attendees)])) != len(attendees):
            raise ValueError('Configure distinct TTS_VOICES')
        for p, voice in zip(attendees, voices):
            p['voice'] = voice.strip()
        persona = attendees[0]
        stt, dialogue, vision, tts = adapters(s)
        if hasattr(tts, 'voice'):
            tts.voice = persona['voice']
        judge = JevObserver(s.jev_key, s.jev_model) if s.jev_shadow and s.jev_key and not s.mock else None
        session = Session(send, stt, dialogue, vision, tts, persona, s.mock, s.log_transcripts, judge)
        session.attendees = attendees
        scenario_id = join.get('scenario_id', '')
        scenario = next((v for v in SCENARIOS if v['id'] == scenario_id), None)
        if scenario_id and scenario is None:
            raise ValueError('Unknown scenario')
        session.scenario = scenario['background'] if scenario else ''
        session.background = str(join.get('background', ''))[:4000]
        ctl.admit(session.session_id, len(attendees))
        s.runtime_snapshot.update(voices=voices, scenario_id=scenario_id, cast_ids=[p['cast_id'] for p in attendees])
        review_token = review_store().register(session.session_id, s.runtime_snapshot)

        async def stop_for_limit(reason):
            nonlocal end_reason
            end_reason = 'limited'
            await session.emit('limit', message=reason)
            await session.end()
            await ws.close()

        def exhausted(reason):
            nonlocal cutoff_task
            if cutoff_task is None:
                cutoff_task = asyncio.create_task(stop_for_limit(reason))

        budget = Budget(ctl, session.session_id, s, exhausted)
        for adapter in (dialogue, vision, tts, judge):
            if adapter is not None:
                adapter.budget = budget
        budget.reserve('stt', 10)
        paid_seconds = 10
        audio_seconds = 0

        async def guard():
            nonlocal paid_seconds
            while not session.ended:
                await asyncio.sleep(1)
                elapsed = time.monotonic()-session.start
                if not ctl.authorized(ws.cookies.get('audience_meeting'), 'meeting'):
                    exhausted('Login expired. Sign in again to start a new meeting.')
                    return
                if elapsed >= ctl.max_seconds or time.monotonic()-session.last_activity >= ctl.idle_seconds:
                    exhausted('Meeting time or idle limit reached. Your review is available.')
                    return
                if elapsed >= paid_seconds-1:
                    budget.reserve('stt', 10)
                    paid_seconds += 10
                usage = ctl.usage(session.session_id)
                await session.emit('usage', **usage)
                if usage['meeting_usd'] >= ctl.meeting_limit/1e6 or usage['daily_usd'] >= ctl.daily_limit/1e6:
                    exhausted('Spending allowance reached. Your review is available.')
                    return

        watchdog = asyncio.create_task(guard())
        session.diagnostic('session_open', sample_rate=rate, mode='mock' if s.mock else 'hosted')
        try:
            await stt.start(rate, session.recognition)
        except Exception:
            await session.emit('error', stage='stt', message='Recognition connection failed.')
            return
        await session.emit('joined', persona=persona, attendees=attendees, limits=ctl.limits(), mode='mock' if s.mock else 'hosted', review_token=review_token, configuration=s.runtime_snapshot)
        session.begin_reply('Introduce yourself in one short sentence and invite the presenter to begin.')
        while not session.ended:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect':
                break
            if message.get('bytes') is not None:
                pcm = message['bytes']
                if len(pcm) > 32768 or len(pcm) % 2:
                    raise ValueError('invalid PCM')
                audio_seconds += len(pcm)/(rate*2)
                if audio_seconds > time.monotonic()-session.start+3:
                    raise ValueError('Audio sent faster than realtime')
                while audio_seconds > paid_seconds:
                    budget.reserve('stt', 10)
                    paid_seconds += 10
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
            elif kind == 'speech_activity':
                session.diagnostic('speech_activity', source='browser')
            elif kind == 'speech_end':
                session.diagnostic('speech_end', source='browser')
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
            elif kind in ('playback_started', 'playback_stopped', 'playback_ended', 'browser_metric', 'mute', 'audio_state'):
                if kind == 'playback_started' and data.get('response_id') == session.generation:
                    session.playing_id = session.generation
                elif kind in ('playback_stopped', 'playback_ended') and data.get('response_id') == session.playing_id:
                    session.playing_id = None
                # Explicit fields only, no arbitrary client payload in the record.
                await session.emit(kind, response_id=data.get('response_id'),
                                   value_ms=data.get('value_ms'), stage=str(data.get('stage', ''))[:80],
                                   enabled=bool(data.get('enabled')),
                                   context_state=str(data.get('context_state', ''))[:24],
                                   output_muted=data.get('output_muted') if isinstance(data.get('output_muted'), bool) else None,
                                   gain=data.get('gain') if isinstance(data.get('gain'), (int, float)) else None,
                                   queued_sources=data.get('queued_sources') if isinstance(data.get('queued_sources'), int) else None)
            elif kind == 'end':
                end_reason = 'ended'
                await session.end()
                break
    except LimitReached as exc:
        if cutoff_task:
            await cutoff_task
        else:
            end_reason = 'limited'
            await send({'type': 'limit', 'message': str(exc)})
            if session:
                await session.end()
    except (WebSocketDisconnect, RuntimeError):
        if session:
            session.diagnostic('connection_closed', outcome='disconnect_or_transport_error')
    except (ValueError, ValidationError, TimeoutError):
        if session:
            session.diagnostic('error', stage='protocol')
        try:
            await send({'type': 'error', 'stage': 'protocol', 'message': 'Invalid meeting message or join timeout.'})
        except RuntimeError:
            pass
    finally:
        if watchdog:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        if cutoff_task:
            await asyncio.gather(cutoff_task, return_exceptions=True)
        if session:
            ctl.finish(session.session_id, session.now(), end_reason)
            review_store().finish(session.session_id, session.measurements)
            session.diagnostic('session_closed', outcome='ended' if session.ended else 'disconnected')
            session.ended = True
            await session.close_background()
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
