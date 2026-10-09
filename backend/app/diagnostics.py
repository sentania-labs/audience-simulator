"""Bounded, allowlisted diagnostics, independent of session media and provider bodies."""
import json
import logging
import math
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger('audience')


def record(session_id, event, transcript=False):
    row = {'time_local': datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S %Z'),
           'session_id': session_id, 'event': event['type']}
    # Never serialize arbitrary event fields or exception/provider payloads.
    for key in ('t_ms', 'response_id', 'next_id', 'value_ms', 'sample_rate', 'text_length',
                'queued_sources', 'gain', 'confidence', 'chunk_count', 'byte_count'):
        value = event.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            row[key] = value
    for key in ('stage', 'source', 'mode', 'context_state', 'delivery', 'outcome'):
        value = event.get(key)
        if isinstance(value, str):
            row[key] = value[:80]
    for key in ('enabled', 'final', 'output_muted'):
        if isinstance(event.get(key), bool):
            row[key] = event[key]
    if event['type'] in ('transcript', 'observation'):
        row['text_length'] = len(event.get('text', ''))
    if event['type'] == 'transcript':
        row['speaker_role'] = event.get('speaker_role', 'unknown')
        if transcript:
            row['text'] = event.get('text', '')[:4000]
    logger.info(json.dumps(row, ensure_ascii=True))
