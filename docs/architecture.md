# MVP architecture

Status: implemented candidate, real-provider feasibility gate pending credentials.

```text
React browser
  microphone -> AudioWorklet PCM16 -> WebSocket -> STT streaming adapter
  screen -> explicit capture -> resize/change filter -> latest frame worker
  speaker <- PCM24kHz chunks <- TTS adapter <- sentence buffer <- dialogue SSE
                    FastAPI session controller
         monotonic event timeline, turn IDs, cancellation, visual history
                    independent vision HTTP adapter
```

The first profile separates Deepgram streaming recognition from HTTP chat dialogue,
vision and PCM speech synthesis. Each component has its own endpoint, model and key.
No inference runs on the development workstation except deterministic test doubles.
Spark is an optional session endpoint after benchmarking its services.

Browser and server synchronize on session elapsed milliseconds, not wall clocks. Browser offset is estimated from the join receipt, so remote
network delay can skew cross-boundary timing; acoustic benchmarks are still required.
Frames carry capture time; observations carry completion time. Transcript records
recognition receipt and response generation separately from browser playback receipts.
Provider timing and browser timing are distinct measurements.

Only the latest waiting frame is processed; one vision request runs at a time.
Sharing stops invalidate pending observations. Earlier observations remain in memory,
identified as historical. A new response takes a bounded snapshot of transcript and
visual observations. Visible content is always untrusted evidence in user context,
never system instructions. Models have no tools or privileged actions.

Interruptions stop browser sources immediately, advance generation ID, cancel provider
requests and reject stale audio. Echo cancellation and headphones are recommended.
Browser energy detection provides fast barge-in; STT speech events provide backup.

No raw audio or frames are stored. Timeline and summary are browser/session memory
only, with explicit JSON download. Disconnect destroys backend state. A single
process serves frontend and WebSocket, behind localhost by default. Remote use needs
HTTPS and an authenticated reverse proxy; this is not a multi-tenant service.
