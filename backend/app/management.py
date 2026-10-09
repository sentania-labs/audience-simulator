"""Authenticated opt-in review and runtime administration routes."""
import asyncio
import json
import secrets
import os
import httpx
from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel, Field, ConfigDict
from . import runtime
from . import provider_catalog as catalog
from .metrics import render
from .review_store import ReviewStore, RETENTION_DAYS

router = APIRouter()


def dependencies():
    from .main import control, require, same_origin
    return control(), require, same_origin


def store():
    return ReviewStore(dependencies()[0])


def provider_store():
    return catalog.ProviderStore(dependencies()[0])


def settings():
    revision, value = store().current()
    s = runtime.resolve(value, check_catalog=False) if value else runtime.Settings()
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
        async with asyncio.timeout(65):
            for stage in ('dialogue', 'vision', 'tts'):
                endpoint = getattr(s, stage)
                models, _ = await catalog.discover(endpoint.protocol if endpoint.protocol in catalog.BASES else 'compatible', endpoint.base, endpoint.key)
                if endpoint.model not in [m['id'] for m in models]:
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


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=60)
    kind: str = Field(max_length=30)
    base: str = Field(default='', max_length=500)
    key: str = Field(min_length=1, max_length=4096, repr=False)


def provider_connection(pid):
    if pid.startswith('app-'):
        return provider_store().connection(pid)
    stage, name = pid.split(':', 1)
    conn = runtime.connections()[stage][name].copy()
    conn['provider'] = conn.get('provider') or ('openai' if conn['base'] == catalog.BASES['openai'] else 'compatible')
    return conn


@router.get('/api/admin/providers')
def list_providers(request: Request):
    dependencies()[1](request, 'admin')
    ps = provider_store()
    result = []
    for r in ps.rows():
        result.append(dict(id=r['id'], name=r['name'], kind=r['kind'], base=r['base'], models=json.loads(r['catalog']), verified=r['verified'], source='app'))
    for stage, pool in runtime.connections().items():
        for name, conn in pool.items():
            if conn.get('stored_id'):
                continue
            pid = stage+':'+name
            conn = provider_connection(pid)
            models, verified = ps.cached(pid, conn)
            result.append(dict(id=pid, name=f'{stage}: {name}', kind=conn['provider'], base=conn['base'], models=models, verified=verified, source='deployment', stage=stage, connection=name))
    try:
        catalog.cipher()
        ready = True
    except ValueError:
        ready = False
    return {'providers': result, 'storage_ready': ready, 'pricing': catalog.PRICING}


@router.post('/api/admin/providers')
async def add_provider(body: ProviderInput, request: Request):
    _, require, origin = dependencies()
    require(request, 'admin'); origin(request)
    try:
        catalog.cipher()
        base = catalog.validate(body.kind, body.base, body.key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        models, message = await catalog.discover(body.kind, base, body.key)
    except Exception:
        raise HTTPException(422, 'Provider verification failed. Check the key, API URL, account access and network route. Nothing was saved.') from None
    pid = provider_store().save(body.name.strip(), body.kind, base, body.key, models)
    return {'id': pid, 'message': message}


@router.post('/api/admin/providers/{pid}/verify')
async def verify_provider(pid: str, request: Request):
    _, require, origin = dependencies()
    require(request, 'admin'); origin(request)
    try:
        conn = provider_connection(pid)
        models, message = await catalog.discover(conn['provider'], conn['base'], conn['key'])
        provider_store().refresh(pid, conn, models)
    except Exception:
        raise HTTPException(422, 'Provider verification failed. Check credentials and connectivity. Previous catalog retained; availability is not confirmed.') from None
    return {'message': message}


@router.get('/api/admin/voices')
def get_voices(request: Request, provider: str, model: str):
    dependencies()[1](request, 'admin')
    try:
        conn = provider_connection(provider)
    except (ValueError, KeyError):
        raise HTTPException(404, 'Provider not found') from None
    values = catalog.voices(conn['provider'], model)
    return {'voices': values, 'source': 'Documented built-in voices for this model' if values else 'No standard voice-discovery API for this connection. Enter voice identifiers from your provider.'}
