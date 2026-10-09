# Prioritized task plan and risks

| Priority | Work | Depends on | Exit criterion | State |
| --- | --- | --- | --- | --- |
| P0 | Review spec and choose narrow architecture | None | ADR and risk register | Complete |
| P0 | Speech plus frame feasibility slice | Provider access | Heard exchange grounded in slide and changed demo | Implemented, live gate blocked |
| P0 | Cancellation and instrumentation | Slice | No stale playback after interruption, measured stage timings | Mock checks and browser receipts implemented |
| P1 | One-persona UI, timeline, summary | Slice live gate | Exact nine-step acceptance and ten-minute session | Candidate built, acceptance pending |
| P1 | Tests, Compose and setup | Candidate | Repeatable mock checks and runnable deployment | 17 tests pass, live test skipped; container and browser mock run verified |
| P2 | Spark comparison | Available Spark services | Concurrent speech/vision load measurements | Deferred, no capacity assumption |

The meeting UI is a small verification harness built while provider access is blocked;
it does not imply the feasibility gate has passed.

| Risk | Impact | Mitigation / gate |
| --- | --- | --- |
| No credentials | Cannot demonstrate natural voice or actual vision | Supply providers, run manual acceptance; never substitute mock claims |
| Cascaded latency | Slow conversational turns | Stream text into bounded sentence TTS; measure before tuning |
| Echo / false barge-in | Persona interrupts itself | Echo cancellation, headphones, sustained energy threshold, explicit interrupt |
| Visual lag and unreadable labels | Incorrect demo claims | Latest queue, uncertainty instruction, capture/observed timestamps |
| Screen injection | Persona follows malicious slide text | Untrusted context boundary, no tools, injection test; not a mathematical guarantee |
| Provider protocol differences | Local endpoint incompatibility | Separate adapters and documented exact wire contracts |
| Memory-only retention | Closing loses review | Explicit download before leaving, no silent disk persistence |
| No authentication | Exposure if port published | Loopback binding; remote use only with authenticated HTTPS proxy |

Next iteration: validate one paid profile, tune actual barge-in and frame cadence from
measurements, then benchmark Spark under simultaneous load. No later roadmap phases
are authorized by this plan.

Validation: non-author review identified five defects (concurrent replies, stale current
view, early context eviction, dropped controls, repeat questions). All five were
corrected; regression tests cover response ownership, failures and retained context.
Dependency audits report no known vulnerabilities. Scott subsequently authorized
initial repository creation and source publication; see publication-authorization.md.
Paid protocol checks and exact MVP acceptance remain blocked by credentials.
