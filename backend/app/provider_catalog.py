"""Admin-owned provider credentials and key-specific model discovery."""
import asyncio
import hashlib
import json
import os
import re
import uuid
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from .control import local_time

BASES = {'openai': 'https://api.openai.com/v1', 'anthropic': 'https://api.anthropic.com/v1',
         'gemini': 'https://generativelanguage.googleapis.com/v1beta/openai',
         'deepgram': 'wss://api.deepgram.com/v1/listen',
         'elevenlabs': 'wss://api.elevenlabs.io/v1/speech-to-text/realtime'}
PRICING = [
    {'provider': 'OpenAI', 'url': 'https://developers.openai.com/api/docs/pricing', 'basis': 'Text tokens; speech uses audio tokens or characters depending on model.'},
    {'provider': 'Anthropic', 'url': 'https://platform.claude.com/docs/en/about-claude/pricing', 'basis': 'Input/output tokens, with separate cache and long-context rates.'},
    {'provider': 'Gemini', 'url': 'https://ai.google.dev/gemini-api/docs/pricing', 'basis': 'Model, modality, context length and paid/free tier.'},
    {'provider': 'Deepgram', 'url': 'https://deepgram.com/pricing', 'basis': 'Streaming recognition per minute; plan and model dependent.'},
    {'provider': 'ElevenLabs', 'url': 'https://elevenlabs.io/pricing/api', 'basis': 'Realtime recognition, plan and credit allowance dependent.'},
]
VOICES = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer', 'verse', 'marin', 'cedar']


def cipher():
    try:
        return Fernet(os.environ['PROVIDER_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError):
        raise ValueError('Set PROVIDER_ENCRYPTION_KEY in the app Secret before saving provider keys') from None


def validate(kind, base, key):
    if kind not in (*BASES, 'compatible'):
        raise ValueError('Unknown provider type')
    if not key.strip() or len(key) > 4096 or any(c.isspace() for c in key):
        raise ValueError('An API key without whitespace is required')
    if kind != 'compatible':
        return BASES[kind]
    parsed = urlparse(base)
    # Admin-only local servers are intentional. Reject credential-bearing URLs,
    # metadata/link-local destinations and redirects; never relay cookies.
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Provide an http(s) API base URL without credentials, query or fragment')
    import ipaddress
    try:
        addr = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        addr = None
    if (addr and (addr.is_link_local or addr.is_multicast or addr.is_unspecified)) or parsed.hostname in ('metadata.google.internal', 'instance-data'):
        raise ValueError('Metadata and link-local destinations are not provider endpoints')
    return base.rstrip('/')


def model_stages(kind, mid):
    lower = mid.lower()
    if kind == 'anthropic':
        return ['dialogue', 'vision']
    if kind == 'gemini':
        return ['dialogue', 'vision'] if lower.startswith('gemini-') and not any(x in lower for x in ('tts', 'live', 'audio', 'embedding', 'image', 'robotics')) else []
    if kind == 'openai':
        if lower.startswith(('tts-', 'gpt-4o-mini-tts')):
            return ['tts']
        if lower.startswith(('gpt-', 'chatgpt-', 'o1', 'o3', 'o4')) and not any(x in lower for x in ('tts', 'transcribe', 'realtime', 'audio', 'image', 'codex', 'search', 'deep-research', '-pro')):
            return ['dialogue', 'vision']
        return []
    # Compatible /models has no standard modality metadata. The UI labels these
    # as advertised candidates, never as a successful generation test.
    return ['dialogue', 'vision', 'tts']


def voices(kind, model):
    if kind == 'openai':
        return VOICES if model.startswith('gpt-4o-mini-tts') else ['alloy', 'ash', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer'] if model in ('tts-1', 'tts-1-hd') else []
    return []


async def discover(kind, base, key):
    """Return bounded discovery metadata, never upstream error bodies or keys."""
    if kind in ('deepgram', 'elevenlabs'):
        from .config import Settings
        from .providers import DeepgramRecognition, ElevenLabsRecognition
        s = Settings()
        s.stt_provider, s.stt_url, s.stt_key = kind, base, key
        s.stt_model = 'nova-3' if kind == 'deepgram' else 'scribe_v2_realtime'
        adapter = (DeepgramRecognition if kind == 'deepgram' else ElevenLabsRecognition)(s)
        async def ignore(_): pass
        try:
            async with asyncio.timeout(10):
                await adapter.start(24000, ignore)
        finally:
            await adapter.close()
        return [{'id': s.stt_model, 'stages': ['stt']}], 'Realtime connection checked. This adapter supports the listed recognition model.'
    headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'} if kind == 'anthropic' else ({'Authorization': 'Bearer '+key} if key else {})
    models = []
    params = {}
    async with asyncio.timeout(20), httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        for _ in range(20):
            response = await client.get(base+'/models', headers=headers, params=params)
            response.raise_for_status()
            body = response.json()
            for item in body.get('data', []):
                mid = item.get('id', '').removeprefix('models/')
                if re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,120}', mid):
                    stages = model_stages(kind, mid)
                    if stages:
                        models.append({'id': mid, 'stages': stages})
            if not body.get('has_more'):
                break
            last = body.get('last_id') or (body.get('data') or [{}])[-1].get('id')
            if not last or params.get('after_id') == last:
                raise ValueError('Incomplete model discovery')
            params = {'after_id' if kind == 'anthropic' else 'after': last, 'limit': 100}
        else:
            raise ValueError('Model catalog exceeds discovery limit')
    if not models:
        raise ValueError('No models supported by this app were advertised')
    return sorted({m['id']:m for m in models}.values(), key=lambda m:m['id']), 'Models advertised for this key. Availability, quota and modality still require a practice meeting.'


class ProviderStore:
    def __init__(self, ctl):
        self.ctl = ctl
        with ctl.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, base TEXT NOT NULL,
                credential TEXT NOT NULL, catalog TEXT NOT NULL, verified TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS provider_discovery (id TEXT PRIMARY KEY, fingerprint TEXT, catalog TEXT, verified TEXT);''')

    def save(self, name, kind, base, key, models):
        encrypted = cipher().encrypt(key.encode()).decode()
        pid = 'app-'+uuid.uuid4().hex[:16]
        with self.ctl.db() as db:
            db.execute('INSERT INTO providers VALUES (?,?,?,?,?,?,?)', (pid, name, kind, base, encrypted, json.dumps(models), local_time()))
        return pid

    def rows(self):
        with self.ctl.db() as db:
            return [dict(r) for r in db.execute('SELECT id,name,kind,base,catalog,verified FROM providers ORDER BY rowid')]

    def connection(self, pid):
        with self.ctl.db() as db:
            r = db.execute('SELECT * FROM providers WHERE id=?', (pid,)).fetchone()
        if not r:
            raise ValueError('Provider connection not found')
        try:
            key = cipher().decrypt(r['credential'].encode()).decode()
        except InvalidToken:
            raise ValueError('Provider keys cannot be unlocked. Restore the original encryption key.') from None
        return {'base': r['base'], 'key': key, 'provider': r['kind'], 'models': json.loads(r['catalog'])}

    def refresh(self, pid, conn, models):
        stamp = local_time()
        with self.ctl.db() as db:
            if pid.startswith('app-'):
                db.execute('UPDATE providers SET catalog=?,verified=? WHERE id=?', (json.dumps(models),stamp,pid))
            else:
                fingerprint = hashlib.sha256(json.dumps(conn, sort_keys=True).encode()).hexdigest()
                db.execute('INSERT OR REPLACE INTO provider_discovery VALUES (?,?,?,?)', (pid,fingerprint,json.dumps(models),stamp))

    def cached(self, pid, conn):
        fingerprint = hashlib.sha256(json.dumps(conn, sort_keys=True).encode()).hexdigest()
        with self.ctl.db() as db:
            row = db.execute('SELECT * FROM provider_discovery WHERE id=? AND fingerprint=?', (pid,fingerprint)).fetchone()
        return (json.loads(row['catalog']), row['verified']) if row else ([], '')
