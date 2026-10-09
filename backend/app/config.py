import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    base: str
    model: str
    key: str

    @classmethod
    def load(cls, prefix: str):
        return cls(os.getenv(f'{prefix}_BASE_URL', 'https://api.openai.com/v1').rstrip('/'),
                   os.getenv(f'{prefix}_MODEL', ''), os.getenv(f'{prefix}_API_KEY', ''))


class Settings:
    def __init__(self):
        self.jev_shadow = os.getenv('JEV_SHADOW', 'false').lower() == 'true'
        self.jev_key = os.getenv('JEV_API_KEY', '')
        self.jev_model = os.getenv('JEV_MODEL', 'jev-1.13.0')
        self.log_transcripts = os.getenv('LOG_TRANSCRIPTS', 'false').lower() == 'true'
        self.mock = os.getenv('PROVIDER_MODE', 'hosted') == 'mock'
        self.dialogue = Endpoint.load('DIALOGUE')
        self.vision = Endpoint.load('VISION')
        self.tts = Endpoint.load('TTS')
        self.voice = os.getenv('TTS_VOICE', 'alloy')
        self.stt_provider = os.getenv('STT_PROVIDER', 'deepgram')
        stt_defaults = {
            'deepgram': ('wss://api.deepgram.com/v1/listen', 'nova-3'),
            'elevenlabs': ('wss://api.elevenlabs.io/v1/speech-to-text/realtime', 'scribe_v2_realtime'),
        }
        default_url, default_model = stt_defaults.get(self.stt_provider, ('', ''))
        self.stt_url = os.getenv('STT_URL') or default_url
        self.stt_key = os.getenv('STT_API_KEY', '')
        self.stt_model = os.getenv('STT_MODEL') or default_model
        self.origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173').split(',')

    def missing(self):
        if self.mock:
            return []
        if self.stt_provider not in ('deepgram', 'elevenlabs'):
            return ['STT_PROVIDER must be deepgram or elevenlabs']
        return [name for name, value in {
            'STT_API_KEY': self.stt_key, 'DIALOGUE_MODEL': self.dialogue.model,
            'VISION_MODEL': self.vision.model, 'TTS_MODEL': self.tts.model,
        }.items() if not value]
