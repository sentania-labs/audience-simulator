# MVP architecture

Status: hosted speech and synthetic visual grounding verified; peer-preview controls implemented. Exact full human acceptance remains pending.

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
Browser energy and STT speech-start events report activity only. Recognized words
confirm automatic interruption, with common acknowledgments excluded during playback.
A continuation timer merges nearby finalized recognition segments. Explicit interrupt
remains immediate. Optional Jev judgments run independently for observation only.

No raw audio or frames are stored. Timeline and summary are browser/session memory
only, with explicit JSON download. Disconnect destroys backend conversation state;
budget and session metadata persist as described below. A single process serves
frontend and WebSocket, behind localhost by default. Remote use requires HTTPS;
the app provides shared-password access for a small trusted peer group.

## Peer preview distribution and controls

Browser login gates meeting setup and the WebSocket. A separate admin cookie
gates the statistics and admissions API. Each accepted connection owns an
independent Session and one director for up to four attendees.

Browser -> role gate -> admission transaction -> Session -> budget reservation
-> independent provider adapters -> reconciliation -> SQLite on persistent volume.

SQLite contains opaque login hashes, session metadata, and estimated charges.
Transcript and visual content stay in connection memory. Compose and Helm both
run one process with writable data storage and an otherwise read-only filesystem.
CI builds and exercises the image and chart before registry publication. Argo
consumes the published version; application CI does not deploy to the lab.
