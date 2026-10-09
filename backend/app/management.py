"""Authenticated opt-in review and runtime administration routes."""
import asyncio
import secrets
import os
import httpx
from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel, Field, ConfigDict
from . import runtime
from .metrics import render
from .review_store import ReviewStore, RETENTION_DAYS

router = APIRouter()


def dependencies():
    from .main import control, require, same_origin
    return control(), require, same_origin


def store():
    return ReviewStore(dependencies()[0])


def settings():
    revision, value = store().current()
    s = runtime.resolve(value) if value else runtime.Settings()
    s.runtime_snapshot = runtime.snapshot(s, revision)
    return s


@router.get('/metrics')
def metrics(request: Request):
    # Separate bearer token for scraping, never the interactive admin password.
    token = os.getenv('METRICS_TOKEN', '')
    if not token:
        raise HTTPException(503, 'Metrics token not configured')
    if not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer '+token).encode()):
        raise HTTPException(401, 'Metrics authentication required')
    ctl = dependencies()[0]
    with ctl.db() as db:
        active = db.execute("SELECT count(*) FROM meetings WHERE status='active'").fetchone()[0]
    return Response(render(active), media_type='text/plain; version=0.0.4')


class TranscriptLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speaker: str = Field(max_length=80)
    text: str = Field(max_length=4000)
    t_ms: int = Field(ge=0, le=3_600_000)
    final: bool


class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(max_length=100)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default='', max_length=4000)
    share_transcript: bool = False
    transcript: list[TranscriptLine] | None = Field(default=None, max_length=3000)


@router.post('/api/feedback/{sid}')
def feedback(sid: str, body: Feedback, request: Request):
    _, require, origin = dependencies()
    require(request, 'meeting'); origin(request)
    if (body.transcript is not None) != body.share_transcript:
        raise HTTPException(422, 'Transcript requires separate explicit consent')
    try:
        store().submit(sid, body.token, body.rating, body.comment,
                       [line.model_dump() for line in body.transcript] if body.share_transcript else None)
    except PermissionError:
        raise HTTPException(403, 'Review access required')
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {'submitted': True, 'retention_days': RETENTION_DAYS}


class Capability(BaseModel):
    token: str = Field(max_length=100)


@router.post('/api/feedback/{sid}/withdraw')
def withdraw(sid: str, body: Capability, request: Request):
    _, require, origin = dependencies()
    require(request, 'meeting'); origin(request)
    try:
        store().delete(sid, body.token)
    except PermissionError:
        raise HTTPException(403, 'Review access required')
    return {'deleted': True}


@router.get('/api/admin/feedback')
def reviews(request: Request):
    dependencies()[1](request, 'admin')
    return {'reviews': store().list(), 'retention_days': RETENTION_DAYS}


@router.post('/api/admin/feedback/{sid}/delete')
def delete_review(sid: str, request: Request):
    _, require, origin = dependencies()
    require(request, 'admin'); origin(request)
    store().delete(sid)
    return {'deleted': True}


@router.get('/api/admin/runtime')
def get_runtime(request: Request):
    dependencies()[1](request, 'admin')
    revision, value = store().current()
    return {'revision': revision, 'config': value or runtime.defaults(),
            'connections': {stage: list(pool) for stage, pool in runtime.connections().items()},
            'history': store().history()}


class RuntimeChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    config: dict


def resolve(body):
    try:
        return runtime.resolve(body.config)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, 'Invalid configuration. Check models, approved connections, four distinct voices and positive pricing ceilings.')


@router.post('/api/admin/runtime')
def save_runtime(body: RuntimeChange, request: Request):
    _, require, origin = dependencies()
    require(request, 'admin'); origin(request)
    resolve(body)
    try:
        revision = store().save(body.config, body.expected_revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {'revision': revision}


@router.post('/api/admin/runtime/validate')
async def validate_runtime(body: RuntimeChange, request: Request):
    _, require, origin = dependencies()
    require(request, 'admin'); origin(request)
    s = resolve(body)
    if s.mock:
        return {'message': 'Mock mode: structure and pricing validated; no provider connection tested.'}
    # Read-only model discovery verifies credentials and advertised models. It does
    # not assert synthesis quality or incur a generated speech/dialogue request.
    try:
        async with asyncio.timeout(15), httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            for stage in ('dialogue', 'vision', 'tts'):
                endpoint = getattr(s, stage)
                response = await client.get(endpoint.base+'/models', headers={'Authorization': 'Bearer '+endpoint.key})
                response.raise_for_status()
                if endpoint.model not in [m.get('id') for m in response.json().get('data', [])]:
                    raise ValueError('Model not advertised')
        from .providers import adapters
        stt = adapters(s)[0]
        async def ignore(_):
            pass
        try:
            async with asyncio.timeout(8):
                await stt.start(24000, ignore)
        finally:
            await stt.close()
    except Exception:
        raise HTTPException(422, 'Connection check failed. Check credentials, model availability and provider protocol in deployment. No change was saved.')
    return {'message': 'Model discovery and recognition connection passed. Speech quality and model capabilities still require a practice meeting.'}
