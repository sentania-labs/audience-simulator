"""Process-local Prometheus exposition with fixed labels, no meeting identifiers."""
import math
import threading
from collections import Counter

STAGES = frozenset(('dialogue_first_token', 'tts_first_audio', 'tts_complete',
    'response_first_audio_sent', 'response_complete', 'server_cancel',
    'stt_after_browser_silence', 'max_audio_gap', 'tts_terminal_wait', 'vision_request', 'screen_observation_delay',
    'estimated_first_playback_after_silence', 'playback_underrun'))
BUCKETS = (.05, .1, .25, .5, 1, 2, 5, 10, 30, 60, 120)
lock = threading.Lock()
counts, sums, buckets, errors, cancellations = Counter(), Counter(), Counter(), Counter(), Counter()


def observe(event):
    kind, stage = event.get('type'), event.get('stage')
    with lock:
        if kind in ('metric', 'browser_metric', 'tts_stream') and stage in STAGES:
            value = event.get('value_ms')
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 3_600_000:
                value /= 1000
                counts[stage] += 1
                sums[stage] += value
                for bound in BUCKETS:
                    if value <= bound:
                        buckets[stage, bound] += 1
        if kind == 'provider_error' or (kind == 'error' and stage in ('stt', 'vision')):
            errors[stage if stage in ('dialogue', 'tts', 'delivery', 'stt', 'vision') else 'other'] += 1
        if kind == 'cancel':
            source = event.get('source')
            cancellations[source if source in ('new_turn', 'recognized_words', 'presenter', 'share_change', 'session_end') else 'other'] += 1


def render(active):
    lines = ['# HELP audience_active_meetings Currently admitted meetings.', '# TYPE audience_active_meetings gauge', f'audience_active_meetings {active}',
             '# HELP audience_latency_seconds Observed stage latency; browser values are client estimates.', '# TYPE audience_latency_seconds histogram']
    with lock:
        for stage in sorted(STAGES):
            for bound in BUCKETS:
                lines.append(f'audience_latency_seconds_bucket{{stage="{stage}",le="{bound}"}} {buckets[stage, bound]}')
            lines.extend((f'audience_latency_seconds_bucket{{stage="{stage}",le="+Inf"}} {counts[stage]}',
                          f'audience_latency_seconds_sum{{stage="{stage}"}} {sums[stage]}',
                          f'audience_latency_seconds_count{{stage="{stage}"}} {counts[stage]}'))
        for name, values in (('provider_errors', errors), ('cancellations', cancellations)):
            lines.append(f'# TYPE audience_{name}_total counter')
            for label, count in sorted(values.items()):
                lines.append(f'audience_{name}_total{{reason="{label}"}} {count}')
    return '\n'.join(lines)+'\n'
