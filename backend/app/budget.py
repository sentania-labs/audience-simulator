"""Provider-independent preflight spending guard. Amounts are estimates, not invoices."""
import json
import math
import os

from .control import LimitReached


class Budget:
    def __init__(self, control, sid, settings, exhausted):
        self.control, self.sid, self.exhausted = control, sid, exhausted
        self.mock = settings.mock
        # Conservative configured ceilings. Unknown endpoint/model pairs require an
        # explicit operator-supplied schedule; they are never treated as free.
        known = (settings.dialogue.base == 'https://api.openai.com/v1' and settings.dialogue.model == 'gpt-4.1-mini'
                 and settings.vision.base == 'https://api.openai.com/v1' and settings.vision.model == 'gpt-4.1-mini'
                 and settings.tts.base == 'https://api.openai.com/v1' and settings.tts.model == 'gpt-4o-mini-tts'
                 and settings.stt_provider == 'deepgram' and settings.stt_model == 'nova-3'
                 and settings.stt_url == 'wss://api.deepgram.com/v1/listen'
                 and (not settings.jev_shadow or settings.jev_model == 'jev-1.13.0'))
        raw = os.getenv('COST_RATES_JSON', '')
        if not self.mock and not known and not raw:
            raise ValueError('Unknown pricing: configure COST_RATES_JSON before joining.')
        self.rates = json.loads(raw) if raw else dict(input_million=.4, output_million=1.6,
            vision_call=.01, tts_character=.00003, stt_minute=.02, judge_call=.001)
        for key in ('input_million', 'output_million', 'vision_call', 'tts_character', 'stt_minute', 'judge_call'):
            if key not in self.rates or not math.isfinite(float(self.rates[key])) or float(self.rates[key]) < 0:
                raise ValueError('Invalid cost schedule')
            self.rates[key] = float(self.rates[key])
        self.margin = 1.25

    def reserve(self, stage, units=1):
        rates = self.rates
        cost = {'dialogue': (units * rates['input_million'] + 300 * rates['output_million'])/1e6,
                'vision': rates['vision_call'], 'tts': units*rates['tts_character'],
                'stt': units*rates['stt_minute']/60, 'judge': rates['judge_call']}[stage]
        try:
            return self.control.reserve(self.sid, stage, 0 if self.mock else cost*self.margin)
        except LimitReached as exc:
            self.exhausted(str(exc))
            raise

    def settle_text(self, charge, usage):
        if self.mock or not isinstance(usage, dict):
            return
        incoming, outgoing = usage.get('prompt_tokens'), usage.get('completion_tokens')
        if isinstance(incoming, int) and isinstance(outgoing, int) and incoming >= 0 and outgoing >= 0:
            self.control.reconcile(charge, self.margin*(incoming*self.rates['input_million'] + outgoing*self.rates['output_million'])/1e6)
