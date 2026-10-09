# ADR 0001: explicit streaming pipeline

Decision: use React/TypeScript and FastAPI, one WebSocket per meeting, PCM16 mono
microphone audio at the browser's actual sample rate, and PCM16 mono 24 kHz replies.
STT, dialogue, vision and TTS have independent contracts and configuration.

Reason: gives observable and cancellable stages without coupling local text endpoints
to a proprietary realtime audio protocol. WebRTC is deferred until measurements show
network conditions require it. Sentence-level TTS overlaps dialogue generation with
playback; it is not a single multimodal realtime model.

Tradeoffs: browser energy VAD is approximate, TCP can stall, and separate calls may
miss the 1 to 1.5 second target. Mock mode emits clearly labeled synthetic tones and
fixed descriptions, never represents a functional audience.

Defaults: Deepgram Listen v1 STT, configurable chat-completions SSE dialogue,
chat-completions image input vision, HTTP /audio/speech PCM TTS. Only endpoints
implementing those protocols work. Local Spark speech requires compatible services
or another adapter; text compatibility is not audio compatibility.

Vision: sample every 2 seconds, maximum width 1280, compare downsampled pixel deltas,
refresh every 10 seconds, latest-frame queue. Retain at most 40 distinct observations (eight early anchors and 32 recent views) and
80 dialogue messages in model context. Timeline is bounded to 3000 events.

Storage: deliberately replace recommended PostgreSQL with session memory and explicit
local download for this feasibility/MVP candidate. This minimizes sensitive retention
and deployment dependencies. Durable saved sessions are a separate decision.

Deployment: one container, one process, localhost Compose port. No camera, broker,
Kubernetes, multi-persona agent or avatar. Consent is required before connecting real
providers. Capture additionally requires browser permission and visible controls.

Repository default: MIT license with contributor attribution. No repository remote,
publication, contributor identity or release is inferred from the bootstrap request.
