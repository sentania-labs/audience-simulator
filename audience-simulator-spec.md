# AI Audience Simulator — Product Specification and Roadmap

**Status:** Draft v0.1  
**Product:** Working name, Audience Simulator  
**Goal:** Practice presentations with realistic AI participants in a Zoom-like browser environment.

## Vision

Create a virtual meeting where a presenter can speak, share PowerPoint slides or a live demo, and interact naturally with an AI audience. Each future participant has independent expertise, voice, goals, relationships, influence, and changing engagement. Afterward, the presenter receives evidence-based coaching on content, delivery, and whether the meeting objective was achieved.

**Product principles**
- The audience reacts to what the presenter actually says and shows, not scripted questions.
- Realistic behavior matters more than artificial politeness or constant encouragement.
- The presenter must read the room; hidden persona states are revealed only in coaching.
- Keep model providers and execution locations interchangeable, including DGX Spark and hosted frontier models.
- Build the smallest convincing interactive experience first.

## MVP — One Persona, Live Conversation, Visible Screen

### User story

As a presenter, I open a simulated meeting, configure one AI persona, speak naturally, share a PowerPoint presentation or live software demonstration, and have a realtime spoken conversation with a participant who understands what I say and what is visible on my shared screen.

### In scope

1. Browser-based Zoom-like meeting interface: join/leave, microphone mute, audio output, participant tile, screen-share controls, and clear share status.
2. Configure one persona: name, role, expertise, conversational style, and optional meeting context/objective.
3. Realtime microphone capture, speech recognition, dialogue generation, and natural spoken replies in one consistent voice.
4. Screen/window/tab sharing via browser capture; sample frames and detect meaningful changes.
5. Vision-capable analysis of shared slides and live demo frames; associate observations with transcript and timestamps.
6. Persona can ask relevant questions, respond to follow-ups, refer to previously observed content, and admit uncertainty about unreadable details.
7. Basic turn-taking, interruption/barge-in, and cancellation of outdated speech responses.
8. Session transcript, timestamped visual observation events, and short post-session summary.
9. Configurable inference providers; at least one functional end-to-end profile, with clear seams for local Spark and hosted services.
10. Docker Compose local deployment, configuration examples, structured logs, and basic automated tests.

### Out of scope for MVP

- Multiple simultaneously speaking personas or independent participant agents.
- Animated talking heads, facial expression tracking, or video avatars.
- True Zoom/Teams integration.
- Organization politics, purchasing authority dynamics, or multi-persona influence modeling.
- Sophisticated coaching dashboards, numeric presentation scoring, and engagement timelines.
- Automatic slide ingestion or editing; screen share alone must work.
- Mandatory local-only inference or production-scale multi-tenant hosting.

### MVP demonstration acceptance test

1. Start the app and configure a technically proficient enterprise infrastructure architect.
2. Join the meeting with a working microphone and hear the persona speak with a consistent voice.
3. Share a PowerPoint window showing a VCF architecture slide.
4. Discuss a diagram; the persona asks a question grounded in the slide rather than a generic topic prompt.
5. Switch the share to a live VCF Automation demonstration, or share the whole screen and switch windows.
6. The persona recognizes the visible context has changed and asks a question grounded in the new screen.
7. Refer back to the earlier slide; the persona recalls relevant observed context.
8. Interrupt the persona; its speech stops and the next response reflects the interruption.
9. End the session; view a transcript, observation timeline, and brief summary.

The MVP is not accepted if the participant can converse about the subject but cannot demonstrably use shared-screen content.

## Architecture

```text
Browser meeting client (React / TypeScript)
  ├─ microphone and speaker
  ├─ screen/window/tab capture (getDisplayMedia)
  ├─ participant tile and meeting controls
  └─ realtime transport (WebRTC and/or streaming WebSocket)
                  │
                  ▼
Session orchestrator (Python / FastAPI)
  ├─ turn detection, interruption and audio streaming
  ├─ speech-to-text adapter
  ├─ persona dialogue and memory
  ├─ visual observer (frame sampling / change detection)
  ├─ text-to-speech adapter
  ├─ timestamped session event recorder
  └─ model/provider router
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
  DGX Spark services    Hosted frontier/realtime models
  (LLM, STT, TTS,       (dialogue, vision, speech
   optional vision)      as supported)
```

### Initial stack recommendation

- **Frontend:** React, TypeScript, Vite.
- **Backend:** Python, FastAPI; async event-driven session controller.
- **Audio:** low-latency bidirectional streaming, explicit voice activity/turn handling and interrupt support.
- **Screen:** browser `getDisplayMedia()`, with low-rate frame sampling plus change detection; do not assume continuous video understanding.
- **Storage:** PostgreSQL for sessions, transcript and events; object storage or local filesystem for selected frames if enabled.
- **Deployment:** Docker Compose; no Kubernetes, Redis, or broker unless measurements justify them.
- **Model adapters:** independent STT, TTS, dialogue and vision interfaces. OpenAI-compatible chat completion is not equivalent to a realtime speech protocol.

### Model placement profiles

1. **Hybrid (initial preference):** frontier model for dialogue/vision, Spark for speech components where benchmarks support acceptable latency.
2. **Hosted realtime baseline:** hosted multimodal realtime service for reference quality and latency.
3. **Local-first:** Spark for dialogue, vision, transcription and voice; optional fallback where allowed.

Only one profile must work end-to-end for MVP. Make routing configurable without prematurely implementing all three.

### Realtime requirements and initial targets

- First audible response ideally begins ~1–1.5 seconds after a completed user turn; benchmark rather than assume.
- Interruption promptly cancels playback and stale generation.
- New screen observations become available within a few seconds of a meaningful change.
- Persona remembers relevant prior statements and observations, with bounded context and summarization.
- Audio, transcript and visual observations use a common monotonic session timeline.
- Model failure degrades gracefully without corrupting the session.
- Explicit user control over whether frames, audio or transcripts are persisted or sent to hosted providers.

### Visual grounding design

- Capture frames from the shared surface, not necessarily the presenter's webcam.
- Sample at a modest configurable rate and on meaningful visual changes; suppress near-duplicates.
- Use a vision-capable model to extract visible text, diagrams, interface state and uncertainty.
- Maintain `current_view` plus timestamped prior observations linked to spoken turns.
- Do not claim to see cursor movement or fine details unless sampling and resolution support it.
- Allow persona questions about the current view and references to earlier slides.
- Keep capture, frame processing and model calls asynchronous so screen analysis does not block speech.

### Session and persona data (conceptual)

- `Persona`: id, name, role, expertise, speaking style, voice ID, optional goals.
- `Session`: id, persona, objective, provider configuration, start/end, status.
- `TranscriptTurn`: speaker, start/end timestamps, text, partial/final state.
- `VisualObservation`: timestamp, source frame reference, description, confidence/limitations, detected change.
- `SessionEvent`: join, share started/stopped, mute, interruption, model error, question, response.
- `SessionSummary`: key topics, questions, observed presentation moments, uncertainties, suggested improvements.

## Product Roadmap

### Phase 0 — Feasibility spike

**Outcome:** Prove low-latency two-way audio and grounded visual questions before building polished UI.

- Benchmark one hosted realtime or hybrid conversation loop.
- Test browser microphone, speaker and screen capture.
- Compare speech recognition, dialogue, TTS and end-to-end response latency.
- Test vision grounding on PowerPoint and live-demo screenshots.
- Measure DGX Spark throughput, memory contention and first-audio latency with candidate services.
- Document provider tradeoffs and select MVP execution profile.

**Exit gate:** One coherent spoken exchange referring accurately to a shared slide and a changed demo screen.

### Phase 1 — MVP meeting simulator

Build the complete single-persona experience and acceptance test above. Prioritize reliability, audio turn-taking, and visual grounding over polish. Include session transcript and simple summary.

**Exit gate:** A repeatable ten-minute presentation session with one persona and working screen awareness.

### Phase 2 — Coaching foundation

- Presentation objectives and success criteria.
- Feedback on clarity, pacing, relevance, unanswered questions and visual/verbal alignment.
- Timeline of evidence-backed coaching moments with transcript and screen references.
- Replay or review of selected moments.
- Distinguish observed behavior from model interpretation.

**Exit gate:** Feedback is specific, timestamped and actionable rather than generic praise.

### Phase 3 — Multi-persona audience

- Multiple participant tiles, distinct voices and independent persona state.
- Shared meeting timeline with private participant memories and motivations.
- Turn scheduling, interruptions, follow-up questions and cross-persona disagreement.
- Meeting director that coordinates dynamics without generating every persona turn continuously.
- Optional audience profiles and saved scenarios.

**Exit gate:** Three personas participate coherently without voice confusion or contradictory context.

### Phase 4 — Realistic room dynamics

- Buying influence, organizational roles, relationships, competing objectives and hidden agendas.
- Engagement, trust, frustration and interest evolving over the session.
- Natural behavior: enthusiasm, skepticism, monopolizing, disengagement, strategic challenges.
- Presenter must redirect the conversation appropriately; avoid artificially revealing hidden states during the meeting.
- Post-session persona interviews and outcome-based coaching.

**Exit gate:** The simulator can reproduce the 'enthusiastic admin monopolizes time while CIO disengages' scenario and explain it afterward with evidence.

### Phase 5 — Advanced simulation and deployment

- Scenario library: sales pitch, technical architecture review, executive briefing, training class, conference talk.
- Adaptive difficulty, repeatable seeds and benchmark sessions.
- More realistic nonverbal signals or avatars, if useful.
- Optional Zoom/Teams integration, enterprise security and multi-user operation.
- Model routing and local-first optimization for larger audiences.

## Quality, Security and Reliability

- Treat shared screens as sensitive: explicit capture indicators, configurable retention, deletion and hosted-provider consent.
- Do not send credentials, secrets or private demo content to hosted models without user awareness and appropriate safeguards.
- Sanitize logs; do not log raw audio or frames by default.
- Defend against prompt injection in visible slide/demo text; screen content is untrusted input, not instructions.
- Make model timeouts, cancellation, retry and fallback explicit.
- Instrument STT latency, LLM time-to-first-token, TTS time-to-first-audio, end-to-end latency, interruption delay, dropped frames and failure rate.
- Include deterministic mock providers for tests and integration tests for real providers behind opt-in credentials.
- Keep the meeting functional when screen sharing is disabled; the persona must not pretend it sees content.

## Key Open Decisions

1. Which hosted realtime and/or frontier providers can be used, and what are their billing and streaming constraints?
2. Which local models and speech stacks meet latency targets on the Spark under simultaneous load?
3. Is the MVP's first transport WebRTC or WebSocket-based audio, and why?
4. How much visual sampling is necessary to follow a live software demonstration?
5. Should camera video be captured at all in MVP? It is optional, not needed for visual grounding of slides.
6. What session retention and privacy defaults best support demos containing sensitive enterprise information?

## Delivery Principles

- Build a working vertical slice first: browser audio → persona → voice reply → shared screen grounding.
- Avoid premature multi-agent orchestration and complex distributed infrastructure.
- Maintain a documented, provider-neutral adapter contract.
- Validate claims with benchmarks and end-to-end demonstrations.
- Track scope changes separately from the MVP acceptance gate.

