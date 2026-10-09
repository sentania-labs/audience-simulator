A simpler audience and provider setup for collecting useful meeting feedback.

- Six general IT colleagues replace the industry scenarios and detailed backstories.
- Admin tabs separate overview, feedback, providers, models, voices, costs and history.
- Add and verify multiple OpenAI, Anthropic, Gemini, compatible/local, Deepgram or ElevenLabs connections. Select advertised models from the verified connection.
- Provider API keys are encrypted in the app database. Helm keeps only access credentials, the metrics token and the stable provider encryption key. Legacy environment connections remain available during migration.
- OpenAI voice choices follow the speech model's documented built-in voices. Compatible servers support manual identifiers. Pricing references explain billing units alongside explicit spending ceilings.
- GPT-6 Luna request compatibility is fixed. Provider rejection, authentication, quota and timeout messages are now distinct.
- A 200 ms initial playback cushion addresses short arrival gaps without adding a delay per chunk. Longer provider stalls remain under investigation in #2.

Upgrade: add PROVIDER_ENCRYPTION_KEY (a Fernet key) to the existing Secret through your deployment pipeline. Keep it stable and backed up separately. Enter provider keys in Admin, verify them, select models/voices, review costs and save. Keep legacy keys until the new configuration passes a practice meeting. No deployment changes are made by this release.

Still an amd64, single-replica peer preview. Pause admissions and drain before upgrading. Model discovery does not guarantee modality support, available quota or speech quality. Anthropic and Gemini provide dialogue/vision here; speech output uses the OpenAI PCM contract, and recognition uses Deepgram or ElevenLabs. Jev remains an optional advisory observer.
