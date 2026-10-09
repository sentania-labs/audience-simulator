# Audience Simulator

One configurable AI participant for spoken presentation rehearsal with shared-screen
context. React/TypeScript browser, Python/FastAPI session controller, independent
speech recognition, dialogue, vision and speech synthesis adapters.

**Status: feasibility candidate, not an accepted MVP.** No live provider credentials
were available during bootstrap. Mock checks prove wiring, not natural voice,
visual understanding or latency targets. The exact PowerPoint/VCF Automation
acceptance run remains pending. See [acceptance](docs/mvp-acceptance.md),
[architecture](docs/architecture.md), [decisions](docs/decisions/0001-mvp-pipeline.md),
[task plan and risks](docs/tasks.md), and [benchmarks](docs/benchmark-plan.md).

## Local setup

Requirements: Python 3.12, Node 22, npm. `uv` is optional.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
PROVIDER_MODE=mock .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --ws-max-size 1500000
```

Open http://localhost:8000. Mock mode uses a synthetic tone, a test-turn input and
fixed screen descriptions. It deliberately performs no recognition or vision.
Allow microphone access, check consent, join, send a mock turn, share a browser
window, interrupt, end and inspect the recap. Headphones help avoid false barge-in.

For development, run `npm run dev --prefix frontend` alongside the backend and open
http://localhost:5173. Vite proxies the meeting WebSocket.

## Real provider configuration

Copy `.env.example` to `.env` only if you do not already have a `.env` file. Fill
server-side keys, supported model identifiers and endpoint URLs. Never paste keys
into the browser, a command-line argument, issue or screenshot. The frontend only
shows endpoint hostnames. Models are deployment settings, not user-facing choices.

```sh
npm run build --prefix frontend
.venv/bin/uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000 --ws-max-size 1500000
```

`PROVIDER_MODE=hosted` selects actual providers. The name denotes the initial profile,
not a guarantee all configured endpoints are external. It requires:

| Component | Contract | Configuration |
| --- | --- | --- |
| STT | Deepgram Listen v1 WebSocket, raw mono PCM16 at negotiated browser rate, interim/final recognition, VAD | `STT_URL`, `STT_MODEL`, `STT_API_KEY` |
| Dialogue | `/chat/completions` SSE `choices[].delta.content`, `max_tokens` | `DIALOGUE_BASE_URL`, `DIALOGUE_MODEL`, `DIALOGUE_API_KEY` |
| Vision | `/chat/completions` image URL input, text observations | `VISION_BASE_URL`, `VISION_MODEL`, `VISION_API_KEY` |
| TTS | `/audio/speech`, streamed raw signed PCM16 little-endian mono 24 kHz | `TTS_BASE_URL`, `TTS_MODEL`, `TTS_API_KEY`, `TTS_VOICE` |

Keys can be omitted on local dialogue/vision/TTS endpoints that need no authentication.
Provider readiness checks required configuration, not account authorization or model
availability. Unsupported streaming, image input or PCM formats require another
adapter. An OpenAI-compatible text endpoint alone does not provide realtime audio.
See verified protocol references: [speech](https://developers.openai.com/api/docs/guides/text-to-speech),
[chat](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Deepgram live recognition](https://developers.deepgram.com/reference/speech-to-text/listen-streaming).

Spark is optional during sessions. Point compatible dialogue/vision endpoints to it
only after testing, with separate speech services or adapters as required. Nothing
assumes its GPU can handle concurrent speech, language and vision workloads.

## Docker Compose

```sh
docker compose up --build
# Or without credentials, wiring only:
PROVIDER_MODE=mock docker compose up --build
```

Open http://localhost:8000. Compose binds loopback, runs as a non-root user, and
stores no session volumes. Port 8000 must be free. Stop the local dev server first.
For remote browser use, provide HTTPS and authentication at your reverse proxy,
then set `ALLOWED_ORIGINS` to the exact browser origin. No public DNS changes are
included. This MVP candidate has no multi-tenant authentication or persistence.

## Privacy and session operation

Before joining, review displayed provider hosts and consent to data processing.
Audio is sent to STT; dialogue sees transcripts and observations; vision sees sampled
shared-screen JPEGs; TTS sees generated reply text. Browser capture additionally
requires an explicit Share action and permission picker, has a visible indicator,
and can be stopped using either app controls or the browser's native stop control.
Mute disables microphone tracks and transmission. Webcam and screen audio are unused.

No raw audio or frames are written to disk. Transcript, observations, timing events
and extractive recap remain in connection/page memory. Download is explicit and may
contain sensitive presentation text. Closing the page loses review; disconnect clears
backend session state. Provider-side retention is governed by provider agreements,
not by this app. Use approved endpoints and nonsensitive material for initial tests.
Logs record stage names and timing only, not provider bodies or media.

Screen descriptions are untrusted evidence, excluded from system instructions.
The persona has no tools or privileged actions. Prompt boundaries mitigate screen
injection but cannot guarantee every model ignores malicious visible instructions.

Sampling is every two seconds, changed views first, with a ten-second refresh.
One vision call runs while the latest waiting frame replaces older pending frames.
Small labels, rapid changes and cursor movements can be missed. Previous views
remain timestamped evidence after sharing stops; current view is cleared.

Interruption stops scheduled browser sources, cancels generation and drops older
response IDs. Automatic energy-based barge-in is approximate; the Interrupt button
is the fallback. Transcript reflects generated text, with interrupted/unheard
annotations and playback events in downloaded data, not word-level delivery alignment.

## Checks and demonstration

```sh
./scripts/check.sh
```

Tests use mock providers and HTTP mock transports: speech chunks, turn cancellation,
visual history, latest-frame queues, share-stop invalidation, provider failures,
consent and origin checks, and endpoint wire formats. This script is the reusable
local/CI definition. No Git repository, remote or existing CI was present at kickoff.
The initial source repository is `sentania-labs/audience-simulator`; no release or
GitHub workflow is included in this bootstrap.

Follow [the exact manual acceptance run](docs/mvp-acceptance.md). Session Metrics and
JSON download expose stage timings. First playback is a browser scheduling estimate,
not an acoustic measurement. No hosted or Spark performance claims are made.

The basic summary extracts presenter turns, participant questions and visual moments.
It is not coaching. Recommended next work: validate one real profile, tune from
measurements, then compare Spark under concurrent load. Multiple personas and
advanced coaching remain outside this scope.

`./scripts/acceptance.sh` walks through the manual gate and refuses mock mode.
For opt-in paid adapter integration checks, load the configured environment securely,
set `RUN_LIVE_PROVIDER_TESTS=1`, and provide `APPROVED_TEST_JPEG` and
`APPROVED_TEST_PCM` paths (mono signed PCM16 at `TEST_PCM_SAMPLE_RATE`, default
48000). Run `.venv/bin/pytest backend/tests/test_live.py -q`. Those inputs are sent
to configured providers; use only approved material. This protocol smoke test still
requires a human to assess grounding and audible quality in the full acceptance run.

License: [MIT](LICENSE).
