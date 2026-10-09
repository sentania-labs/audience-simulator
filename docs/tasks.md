# Prioritized task plan and risks

| Priority | Work | Depends on | Exit criterion | State |
| --- | --- | --- | --- | --- |
| P0 | Review spec and choose narrow architecture | None | ADR and risk register | Complete |
| P0 | Speech plus frame feasibility slice | Provider access | Heard exchange grounded in slide and changed demo | Hosted synthetic speech/vision verified; human gate pending |
| P0 | Cancellation and instrumentation | Slice | No stale playback after interruption, measured stage timings | Mock checks and browser receipts implemented |
| P1 | One-persona UI, timeline, summary | Slice live gate | Exact nine-step acceptance and ten-minute session | Candidate built, acceptance pending |
| P1 | Tests, Compose and setup | Candidate | Repeatable mock checks and runnable deployment | 29 tests pass, opt-in test skipped; container and browser mock run verified |
| P2 | Spark comparison | Available Spark services | Concurrent speech/vision load measurements | Deferred, no capacity assumption |

The meeting UI is a small verification harness built for provider validation;
it does not imply the feasibility gate has passed.

| Risk | Impact | Mitigation / gate |
| --- | --- | --- |
| Human acceptance pending | Synthetic tests miss microphone, acoustics and real demo behavior | Run exact manual acceptance and ten-minute session |
| Cascaded latency | Slow conversational turns | Stream text into bounded sentence TTS; measure before tuning |
| Intermittent STT finalization | One synthetic repeated turn stalled; longer-silence rerun passed | Repeat with continuous browser audio, pause/mute transitions and ten-minute session |
| Echo / false barge-in | Persona interrupts itself | Echo cancellation, recognized-word confirmation, acknowledgment handling, explicit interrupt |
| Visual lag and unreadable labels | Incorrect demo claims | Latest queue, uncertainty instruction, capture/observed timestamps |
| Screen injection | Persona follows malicious slide text | Untrusted context boundary, no tools, injection test; not a mathematical guarantee |
| Provider protocol differences | Local endpoint incompatibility | Separate adapters and documented exact wire contracts |
| Memory-only retention | Closing loses review | Explicit download before leaving, no silent disk persistence |
| No authentication | Exposure if port published | Loopback binding; remote use only with authenticated HTTPS proxy |

Next iteration: finish human validation of the hosted profile, tune barge-in and frame cadence from
measurements, then benchmark Spark under simultaneous load. No later roadmap phases
are authorized by this plan.

Validation: non-author review identified five defects (concurrent replies, stale current
view, early context eviction, dropped controls, repeat questions). All five were
corrected; regression tests cover response ownership, failures and retained context.
Dependency audits report no known vulnerabilities. Scott subsequently authorized
initial repository creation and source publication; see publication-authorization.md.
Hosted credentials now work. Exact MVP acceptance remains pending a human presentation.

## Peer preview release plan

1. Access and durable controls: separate role gates, atomic reservation ledger and
   safe cutoff. Exit: denied unauthenticated sockets, isolated role tests and
   concurrent budget tests pass.
2. Audience configuration and admin, depends on 1: one speech lane, named attendee
   selection and shared context. Exit: two independent meetings and browser review.
3. Distribution, depends on 1 and 2: Compose, Helm, existing Secret and CI release.
   Exit: artifact smoke and kind restart persistence, adversarial review and CI.
4. Release, depends on 3: reviewed main, annotated v0.1.0 and immutable GHCR image,
   digest-pinned deployment bundle. Exit: published artifact can be pulled/run.

Follow-ups: calibrated billing reconciliation for speech/Jev, persistent transcript
opt-in with retention policy, native Anthropic adapter, richer persona library.
Do not add distraction or coaching to this release.
