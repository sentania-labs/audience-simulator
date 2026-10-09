# Audience Simulator

One to four configurable AI attendees for spoken presentation rehearsal with shared-screen
context. Separate browser connections create separate meetings. React/TypeScript browser, Python/FastAPI session controller, independent
speech recognition, dialogue, vision and speech synthesis adapters.

**Status: peer preview.** The hosted profile has completed real speech and visual-grounding checks using
synthetic input fixtures. Human microphone quality, acoustic interruption and
the ten-minute presentation gate still need validation. The exact PowerPoint/VCF Automation
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
PROVIDER_MODE=mock COOKIE_SECURE=false .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --ws-max-size 1500000
```

Set separate MEETING_PASSWORD and ADMIN_PASSWORD environment variables (at least 12 characters each) before starting.
Open http://localhost:8000 and sign in. Mock mode uses a synthetic tone, a test-turn input and
fixed screen descriptions. It deliberately performs no recognition or vision.
Allow microphone access, check consent, join, send a mock turn, share a browser
window, interrupt, end and inspect the recap. Headphones help avoid false barge-in.

For development, run `npm run dev --prefix frontend` alongside the backend and open
http://localhost:5173. Vite proxies the meeting WebSocket.

For a downloaded release bundle, use docker compose --env-file /path/to/private.env up -d.
The bundle pulls the exact published digest. A source checkout supports --build for iteration.

## Real provider configuration

Copy `.env.example` to `.env` only if you do not already have a `.env` file. Configure access passwords, a stable `PROVIDER_ENCRYPTION_KEY`, and
`PROVIDER_MODE=hosted`. Use authenticated Admin to add provider keys, verify
connections and select models. Keys are encrypted in the app database. Never put
keys in a command-line argument, issue or screenshot. Models and approved provider connections are administrator choices, not meeting-user choices. Deployment values seed the initial configuration; saved admin revisions take precedence for new meetings.

```sh
npm run build --prefix frontend
.venv/bin/uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000 --ws-max-size 1500000
```

`PROVIDER_MODE=hosted` selects actual providers. The name denotes the initial profile,
not a guarantee all configured endpoints are external. The following environment
settings remain supported as legacy seeds; new connections are managed in Admin:

| Component | Contract | Configuration |
| --- | --- | --- |
| STT | Deepgram Listen v1 or ElevenLabs Scribe realtime WebSocket, mono PCM16, interim/final recognition | `STT_PROVIDER`, `STT_URL`, `STT_MODEL`, `STT_API_KEY` |
| Dialogue | OpenAI-compatible chat streaming, native Anthropic Messages, or Gemini compatibility API | `DIALOGUE_BASE_URL`, `DIALOGUE_MODEL`, `DIALOGUE_API_KEY` |
| Vision | `/chat/completions` image URL input, text observations | `VISION_BASE_URL`, `VISION_MODEL`, `VISION_API_KEY` |
| TTS | `/audio/speech`, streamed raw signed PCM16 little-endian mono 24 kHz | `TTS_BASE_URL`, `TTS_MODEL`, `TTS_API_KEY`, `TTS_VOICE` |

The initial verified profile uses Deepgram `nova-3`, OpenAI `gpt-4.1-mini` for
dialogue and vision, and `gpt-4o-mini-tts` with voice `coral`. Set
`STT_PROVIDER=elevenlabs` to select Scribe; leave `STT_URL` and `STT_MODEL` blank
to use provider defaults, and supply that provider's key. Browser capture uses
48 kHz PCM. Deepgram and ElevenLabs are separate services. Other local speech
protocols need additional independent adapters.

Legacy local dialogue/vision/TTS endpoints may omit keys when unauthenticated.
New compatible connections in Admin require a URL and key. Discovery confirms
that a connection advertises a model, not every modality or available quota. Unsupported streaming, image input or PCM formats require another
adapter. An OpenAI-compatible text endpoint alone does not provide realtime audio.
See verified protocol references: [speech](https://developers.openai.com/api/docs/guides/text-to-speech),
[chat](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Deepgram live recognition](https://developers.deepgram.com/reference/speech-to-text/listen-streaming).

Spark is optional during sessions. Point compatible dialogue/vision endpoints to it
only after testing, with separate speech services or adapters as required. Nothing
assumes its GPU can handle concurrent speech, language and vision workloads.

## Release deployment: Helm and Docker Compose

Download the release bundle from GitHub Releases. It contains a version-pinned
Compose file, Helm package, image digest, release values and Argo Application
example. The published image is linux/amd64. No provider keys or passwords are
included. Defaults in this source tree track latest; pin the release digest in
your deployment repository.

For Kubernetes, generate two distinct passwords, a metrics token and a stable
`PROVIDER_ENCRYPTION_KEY` (Fernet key), seal them in your deployment repository,
and create the Secret named by existingSecret. Provider API keys are entered
through the authenticated admin UI and encrypted in the persistent app database.
See deploy/secret.example.yaml for key names. Do not put credentials in Helm
values. Install the bundled chart with values-release.yaml plus your site values,
or pin the supplied Argo Application to the release tag.

From an extracted release bundle, a direct Helm install looks like:

```sh
helm upgrade --install audience ./audience-simulator-*.tgz \
  --namespace audience-simulator --create-namespace \
  -f values-release.yaml -f site-values.yaml
```

Your site-values.yaml sets existingSecret, ingress, storage class and allowed
origin. For Argo, commit the supplied pinned Application plus your sealed Secret
and site settings to your deployment repository.

Configure ALLOWED_ORIGINS to your exact HTTPS URL, COOKIE_SECURE=true, ingress
class/host/TLS secret, and a persistent storage class. Login throttling uses the client address and role. Set FORWARDED_ALLOW_IPS to your
trusted ingress proxy addresses/CIDRs if you need original client addresses; do
not trust arbitrary internet clients to supply forwarded headers. The ingress must support
WebSocket upgrade and a read timeout longer than the meeting limit. No DNS record
is created by this project. The admin page is /?admin and uses its own password.

Run one replica and one worker. The PVC stores SQLite spending and session
metadata. Upgrades use Recreate and disconnect active meetings: pause admissions
in admin, wait for the active count to reach zero, then sync Argo. Back up the PVC;
losing it loses budget history. Stats persist until manually removed. Explicitly submitted feedback and transcripts also live on the PVC for 30 days; no images are stored. Include backup retention in your privacy policy: deleting a live submission cannot remove copies from external backups.

Default controls are configurable environment variables:

| Setting | Default |
| --- | --- |
| MEETING_BUDGET_USD | 1.50 |
| DAILY_BUDGET_USD | 10.00 |
| MAX_CONCURRENT_MEETINGS | 3 |
| MAX_ATTENDEES | 4 |
| MAX_MEETING_MINUTES | 30 |
| IDLE_TIMEOUT_MINUTES | 5 |

The daily budget uses America/Chicago midnight and survives restart. Every paid
operation reserves estimated cost first. At 80% the meeting warns; exhaustion
ends work and preserves the recap. Cancelled operations retain reservations.
Figures include a safety margin and can exceed invoices; they are not an exact
provider-side cap. Keep provider account limits as an independent backstop.

Unknown model/endpoint combinations require explicit COST_RATES_JSON configuration;
they cannot silently bypass budgets. See [the cost schedule and tradeoffs](docs/decisions/0003-peer-preview.md).
Use TTS_VOICES to configure distinct supported voices in attendee order. Address
an attendee by name to select them; otherwise the director rotates speakers.
Everyone shares the same meeting context, without independent agents.

## Docker Compose

```sh
docker compose --env-file ~/.secrets/audience-simulator.env up --build
# Or load a private configuration outside the checkout:
docker compose --env-file ~/.secrets/audience-simulator.env up --build
# Or without credentials, wiring only:
PROVIDER_MODE=mock docker compose up --build
```

Open http://localhost:8000. Compose binds loopback, runs as a non-root user, and
uses a persistent data volume. Port 8000 must be free. Stop the local dev server first.
For remote browser use, provide HTTPS and authentication at your reverse proxy,
then set `ALLOWED_ORIGINS` to the exact browser origin. No public DNS changes are
included. This peer preview uses shared passwords, not individual accounts.

## Privacy and session operation

Before joining, review displayed provider hosts and consent to data processing.
Audio is sent to STT; dialogue sees transcripts and observations; vision sees sampled
shared-screen JPEGs; TTS sees generated reply text. Browser capture additionally
requires an explicit Share action and permission picker, has a visible indicator,
and can be stopped using either app controls or the browser's native stop control.
Mute disables microphone tracks and transmission. Webcam and screen audio are unused.

No raw audio or frames are written to disk. By default the session review remains in
connection/page memory. After ending, users may submit a rating and comment, with a separate unchecked transcript consent option. The exact transcript is previewed before submission; audio, images, screen observations and background are excluded. Feedback expires after 30 days, is hidden immediately at expiry and purged at least hourly while the app runs (also on startup/access). Users can withdraw while the review remains open; administrators can delete submissions in the review queue. Nothing is automatically used for training. Server diagnostic metadata is logged; transcript text
is included only when `LOG_TRANSCRIPTS=true`, disclosed before joining. Download is explicit and may
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
response IDs. Automatic barge-in uses recognized words; raw energy and speech-start detections
only record activity. Common short acknowledgments do not interrupt an active reply.
The Interrupt button remains immediate. Transcript reflects generated text, with interrupted/unheard
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

## Server troubleshooting logs

Structured JSON records include a session ID (also present in downloaded events),
America/Chicago clock time, elapsed session time and response IDs. Recognition
activity, speech-end signals, cancellations and their source, provider stage timings,
audio byte/chunk totals, browser playback reports, share events, errors and session
closure are recorded. Browser audio state reports include context state, speaker
mute, gain and queued sources. They do not prove audible sound or identify the OS
output device. Provider response bodies, credentials, raw media and visual text
are excluded. Recognition partials log length only.

```sh
docker compose logs --since 10m audience
# For the named local feasibility deployment:
docker compose -p audience-feasibility logs --since 10m audience
```

Filter JSON records by `session_id` to follow a meeting across concurrent sessions.
Set `LOG_TRANSCRIPTS=true` in the private deployment environment and recreate the
container only when text logging is needed. This retains spoken user and persona
text, including interrupted generated replies, and may capture sensitive statements.
The join screen discloses the setting. Existing sessions cannot be recovered
retroactively. Disable the option after troubleshooting. It never enables raw media
or screen-observation text logging.

Compose rotates container logs at 10 MB per file, three files per container, with
no age guarantee. Logs survive application process restarts but are not a durable
archive across container removal. Other deployments must configure equivalent
rotation and access control.

## Turn-taking iteration and optional Jev observer

The server waits 700 ms after finalized recognition for continuation, or two
seconds after an unfinished phrase. New partial words postpone that decision.
Recognized multiword speech or stop/wait/pause/no can cancel an active reply; this
is a conservative lexical rule, not an acoustic echo classifier. Background speech
can still trigger it. Browser volume detection alone cannot cancel a response.

A reply waits at most 1.5 seconds for already-pending visual analysis. Older frame
results remain historical evidence but cannot replace a newer pending current view.
If analysis is still pending, the dialogue receives that state and must acknowledge
uncertainty. This does not eliminate the delay before the browser samples a change.

`JEV_SHADOW=true` with `JEV_API_KEY` enables the optional TypeSafe observer.
`JEV_MODEL` defaults to the tested `jev-1.13.0`. It receives bounded conversation
excerpts, disclosed before joining, and logs `judge_observation` decisions,
confidence and elapsed latency. One request per session can run at a time, with
a two-second timeout. Results never control cancellation or block speech. Reply
quality is checked after generation, not used as a pre-speech approval gate.
No extra service is needed when the observer is disabled.

## Metrics endpoint

Set `METRICS_TOKEN` in the existing Secret (or private Compose environment).
Prometheus scrapes `GET /metrics` on port 8000 using `Authorization: Bearer <token>`.
Use a dedicated token, not either login password. Unconfigured scraping returns
503, missing/wrong credentials return 401. No dashboard or ServiceMonitor is installed.

Metrics use Prometheus text format 0.0.4:

- `audience_active_meetings`: current admitted meetings.
- `audience_latency_seconds`: histogram labeled by fixed `stage`. Includes first
  dialogue token, first speech audio, response completion, recognition delay,
  maximum inter-chunk TTS gap, browser-estimated first playback and playback underrun.
- `audience_provider_errors_total`: counter labeled by bounded failure stage (`reason`).
- `audience_cancellations_total`: counter labeled by bounded cancellation source (`reason`).

Histograms/counters reset on process restart. No session IDs, transcript text,
model names or persona names appear as labels. Browser timings are untrusted
client estimates, not acoustic measurements. An underrun measures a late chunk
arriving after previously scheduled audio ran out; initial buffering and deliberate
cancellation are excluded. No resumed chunk means no measured underrun duration.
Maximum completed inter-chunk TTS gap is recorded even when a stream fails or is cancelled. `tts_terminal_wait` separately measures the outstanding wait on a failed/cancelled stream, including failure before any audio. Use separate
cluster metrics to correlate CPU throttling/restarts; these metrics do not establish
that a stall is caused by Kubernetes.

## Administrator settings and review

`/?admin` contains saved feedback and runtime configuration. An immutable revision
is created on save; loading a historical revision and saving creates a rollback
revision. Concurrent stale saves are rejected. Existing meetings retain their
provider objects, prices and revision. Join consent includes a fingerprint of resolved provider destinations and logging mode, so deployment-level changes also require reviewing the new data flow. Reviews show that snapshot and timing totals.
`APP_VERSION` may identify the release; otherwise a source/asset fingerprint is used.
Configuration and history persist on the existing SQLite volume.

Admin has Overview, Models and providers, and Feedback sections. Provider settings
have Providers, Models, Voices, Cost and History tabs.

Add named OpenAI, Anthropic, Gemini, OpenAI-compatible/local, Deepgram or ElevenLabs
connections on Providers. Compatible connections require an API base URL and key.
Verification uses key-authenticated model discovery, or a short realtime recognition
handshake for the supported Deepgram nova-3 / ElevenLabs scribe_v2_realtime adapter.
Only verified connections appear as new choices on Models. Catalog entries are
advertised candidates, not proof of quota or all modality support. Run a practice
meeting after changing settings. Native Anthropic Messages and Google's OpenAI
compatibility API support dialogue and vision; speech output uses the OpenAI PCM
interface. Recognition is currently Deepgram or ElevenLabs, not OpenAI Realtime.

OpenAI built-in voices are populated from the documented model-specific list;
compatible speech servers retain manual voice identifiers. Cost provides official
provider pricing links and billing units. Set conservative ceilings explicitly;
model discovery does not expose your contracted billing rates. Spending and time
limits remain deployment-owned. GPT-6 Luna/Sol use max_completion_tokens and no
reasoning for short spoken replies, keeping their small token budget for speech.

Set `PROVIDER_ENCRYPTION_KEY` before saving provider keys. Generate it outside the
repository with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Keep that key stable in the deployment Secret and back it up separately from the
SQLite volume. Losing it makes stored provider keys unusable. Keys never appear in
API responses, snapshots, exports, logs or configuration history. Admins may add
local URLs; the admin password grants authority to connect the app to those hosts.
Do not expose admin access to meeting users. Redirects are not followed.

Existing environment connections and `PROVIDER_CONNECTIONS_JSON` remain supported
for upgrades. To migrate: add/verify app connections, select their models and voices,
review costs, save a runtime revision, and test a meeting. Only then remove legacy
provider keys from the deployment Secret through its normal pipeline. Existing
meetings retain their starting objects. To rotate an app key, add a replacement
connection and save a new revision. Old connections remain for rollback; revoked
keys cannot be restored by rolling back settings. Backups contain encrypted keys
and optionally submitted feedback, and require your own retention controls.

The setup screen now draws from six general IT colleagues: CIO, CISO, applications
director, platform operator, systems administrator and infrastructure engineer.
The initial participant and added participants are randomly selected without
repetition, with up to four in a meeting. Choose members or supply custom meeting
context; there are no industry scenarios or invented personal histories. Brief
rapport is encouraged and speaker labels are removed before synthesis. These are
behavioral instructions, not a guarantee about every model response.
