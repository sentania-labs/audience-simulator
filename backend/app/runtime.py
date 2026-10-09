"""Versioned runtime choices. Connection locations and keys stay deployment-owned."""
import copy
import json
import os
import re
import hashlib
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlparse

from .config import Settings, Endpoint
from .budget import Budget

STAGES = ('dialogue', 'vision', 'tts', 'stt')
RATE_KEYS = ('input_million', 'output_million', 'vision_call', 'tts_character', 'stt_minute', 'judge_call')


def connections():
    s = Settings()
    result = {stage: {'deployment': ({'base': getattr(s, stage).base, 'key': getattr(s, stage).key, 'allow_anonymous': True}
                                    if stage != 'stt' else {'base': s.stt_url, 'key': s.stt_key, 'provider': s.stt_provider})} for stage in STAGES}
    # Each optional connection names an environment variable containing its secret.
    extra = json.loads(os.getenv('PROVIDER_CONNECTIONS_JSON') or '{}')
    for stage, entries in extra.items():
        if stage not in STAGES:
            raise ValueError('Unknown provider stage')
        for name, entry in entries.items():
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', name) or name == 'deployment':
                raise ValueError('Invalid connection name')
            result[stage][name] = {'base': entry['base'], 'key': os.getenv(entry['key_env'], ''), 'provider': entry.get('provider', 'openai-compatible'), 'allow_anonymous': entry.get('allow_anonymous') is True and stage != 'stt'}
    return result


def defaults(s=None):
    s = s or Settings()
    try:
        rates = Budget(None, '', s, lambda _: None).rates
    except ValueError:
        rates = {key: 0 for key in RATE_KEYS}
    return {**{stage: {'connection': 'deployment', 'model': s.stt_model if stage == 'stt' else getattr(s, stage).model} for stage in STAGES},
            'voices': [v.strip() for v in os.getenv('TTS_VOICES', s.voice+',ash,sage,echo').split(',')], 'rates': rates}


def resolve(value):
    s = Settings()
    pool = connections()
    if set(value) != set(STAGES) | {'voices', 'rates'}:
        raise ValueError('Specify the four providers, voices and pricing')
    for stage in STAGES:
        choice = value[stage]
        if set(choice) != {'connection', 'model'} or not isinstance(choice['model'], str) or not (re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,120}', choice['model']) or (s.mock and choice['model'] == '')):
            raise ValueError('Invalid model identifier')
        conn = pool[stage].get(choice['connection'])
        if not conn:
            raise ValueError('Select a deployment-approved connection')
        if not s.mock and not conn['key'] and not conn.get('allow_anonymous'):
            raise ValueError('Connection credential is not configured')
        if stage == 'stt':
            if conn['provider'] not in ('deepgram', 'elevenlabs'):
                raise ValueError('Unsupported recognition protocol')
            s.stt_provider, s.stt_url, s.stt_key, s.stt_model = conn['provider'], conn['base'], conn['key'], choice['model']
        else:
            setattr(s, stage, Endpoint(conn['base'], choice['model'], conn['key']))
    voices = value['voices']
    if not isinstance(voices, list) or not 4 <= len(voices) <= 8 or len(set(voices)) != len(voices) or any(not isinstance(v, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', v) for v in voices):
        raise ValueError('Provide at least four distinct voice identifiers')
    rates = value['rates']
    if set(rates) != set(RATE_KEYS):
        raise ValueError('All pricing ceilings are required')
    import math
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 or v > 1_000_000 for v in rates.values()):
        raise ValueError('Pricing ceilings must be positive finite numbers')
    s.cost_rates = copy.deepcopy(rates)
    s.runtime_choices = copy.deepcopy(value)
    s.voices = list(voices)
    s.voice = voices[0]
    Budget(None, '', s, lambda _: None)
    return s


@lru_cache(maxsize=1)
def build_id():
    digest = hashlib.sha256()
    files = sorted(Path(__file__).parent.glob('*.py')) + sorted(Path(os.getenv('FRONTEND_DIST', 'frontend/dist')).rglob('*'))
    for path in files:
        if path.is_file():
            digest.update(path.read_bytes())
    return 'build-'+digest.hexdigest()[:12]


def consent_revision(s, revision):
    # Hash resolved destinations, not just editable choices. No credentials are returned.
    flow = {stage: getattr(s, stage).base for stage in ('dialogue', 'vision', 'tts')}
    flow.update(stt=s.stt_url, stt_provider=s.stt_provider, judge=bool(s.jev_shadow and s.jev_key and not s.mock),
                log_transcripts=s.log_transcripts, mock=s.mock, revision=revision)
    return hashlib.sha256(json.dumps(flow, sort_keys=True).encode()).hexdigest()


def snapshot(s, revision):
    return {'revision': revision, 'consent_revision': consent_revision(s, revision),
            'choices': getattr(s, 'runtime_choices', None) or defaults(s),
            'data_flow': {**{stage: urlparse(getattr(s, stage).base).hostname for stage in ('dialogue', 'vision', 'tts')}, 'stt': urlparse(s.stt_url).hostname}, 'providers': {stage: {'model': s.stt_model, 'provider': s.stt_provider} if stage == 'stt' else {'model': getattr(s, stage).model} for stage in STAGES},
            'voices': getattr(s, 'voices', [s.voice]), 'personality_version': 'cast-v1', 'app_version': os.getenv('APP_VERSION') or build_id()}
