# Reproducible benchmark plan

Initial hosted smoke measurements are below. Spark measurements remain pending.
Mock timings are wiring evidence only and must never populate this comparison.

For each run record host type, model versions, service versions, browser/OS,
network path, sampling settings, voice, concurrency and warm/cold state. Record
clock times only in America/Chicago; metrics are elapsed milliseconds.

1. Use the same nonsensitive VCF architecture slide and Automation demo. Manually
   inventory visible diagram edges and labels before testing. Include an unreadable
   label and a slide containing an instruction to ignore the persona policy.
2. Use 20 spoken turns per profile, three runs including one cold start, then a
   ten-minute continuous session. Ask the same question and one earlier-slide recall
   after switching to the demo. Count correct grounding against the visible inventory.
3. Download the session JSON. Group metric events by response ID. Compute median,
   p95, failure count and dropped frames, retaining raw elapsed values locally.
4. Measure STT after browser-detected silence, dialogue first token, TTS first audio,
   response first audio sent, estimated first playback after silence, vision request
   and capture-to-observation delay. The STT number includes transport and endpointing.
   Browser silence is a VAD estimate, not an annotated speech end. First playback
   reports scheduled output; use loopback audio recording to confirm acoustic latency.
5. Interrupt at least ten times while speaking. Measure audible stop with loopback
   capture and confirm zero stale response IDs subsequently play. Server cancellation
   and local source-stop duration are supporting evidence, not audible-stop latency.
6. Test mute/unmute, browser-native stop share, switch share, lost WebSocket, denied
   permissions and provider timeout. Count failures and check review remains useful.
7. Compare hosted baseline with Spark one component at a time. Use the same compatible
   adapter protocol. Record GPU memory, utilization, CPU, first-token/audio latency,
   and error rate under simultaneous vision and speech. Gather host evidence only;
   do not modify infrastructure. Report unsupported services rather than extrapolate.

| Profile | STT p50/p95 | First playback p50/p95 | Vision delay p50/p95 | Audible interruption | Grounding/recall | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| Hosted independent pipeline | Pending | Pending | Pending | Pending | Pending | Pending |
| Spark / hosted hybrid | Pending | Pending | Pending | Pending | Pending | Pending |

Initial target: ideally 1 to 1.5 seconds to first audible response after turn end,
observations within a few seconds, prompt interruption. The targets are not measured
results or guarantees. Decide provider placement only after comparing these outcomes.

## Observed mock wiring run

Measured on this workstation through the built Compose container on October 8,
2026, around 9:59 PM America/Chicago. Twelve mock replies (intro, ten test turns,
one observation-triggered reply), 24 sentence TTS calls. These are synthetic
delays, not performance of an inference model.

| Stage | Samples | Median | Range |
| --- | --- | --- | --- |
| Mock dialogue first token | 12 | 5 ms | 5 to 5 ms |
| Mock TTS first audio | 24 | 11 ms | 11 to 12 ms |
| First server audio chunk | 12 | 22 ms | 22 to 23 ms |
| Full mock response generation | 12 | 132.5 ms | 130 to 135 ms |
| Server cancellation | 14 | 0 ms (rounded) | 0 to 0 ms |

A separate Chrome mock session measured 20 ms vision adapter duration and 22 ms
from browser capture timestamp to recorded observation. Chrome used fake media
devices, not a presenter microphone or PowerPoint window. Browser session export
confirmed playback receipts, one interrupted transcript, one playback-stop receipt,
one distinct view and nine refreshes, then a final summary. No natural STT, real
first-audible-response or acoustically measured interruption result exists.

Reproduce with `PROVIDER_MODE=mock docker compose up --build`, join in Chrome,
send ten mock turns, share a surface, inspect Metrics and download session JSON.
Mock timing varies with scheduling; it is not a latency target for hosted or Spark.

## Initial hosted smoke evidence

Deepgram Nova-3, OpenAI gpt-4.1-mini dialogue/vision and gpt-4o-mini-tts
(coral), local Compose container, Chrome with synthetic microphone input.
These are single-run observations, not p50/p95 or acoustic measurements.

The browser recognized the complete management-network question, scheduled a
spoken reply, and stopped the greeting when input speech began. Measured STT
after browser silence: 150 ms; dialogue first token: 1154 ms; first TTS chunk:
717 ms; first server audio: 2144 ms; estimated first playback after silence:
2337 ms. This exceeds the ideal 1 to 1.5 second target.

A direct application WebSocket run identified Cedar, Alder (8 hosts) and Birch
(4 hosts) from the architecture fixture, recognized the changed request screen
(REQ-042, Awaiting approval), and correctly recalled Birch's four hosts. Inputs
are the rendered HTML fixtures in `backend/tests/fixtures`, not PowerPoint or
a live VCF deployment. The first run stalled waiting for another final turn
after sending only one second of trailing silence; repeated-turn reliability
needs further testing. A rerun with three seconds of trailing silence completed
all four spoken turns, screen switch, earlier-slide recall, cancellation and summary.
That rerun does not prove the cause of the original stall.

An isolated same-recording STT comparison produced first partials at 976 ms
(Deepgram) and 2215 ms (ElevenLabs), with final results 353 ms and 513 ms after
input end respectively. Both authenticated successfully. One sample does not
establish a general provider ranking.

Completed rerun, elapsed milliseconds:

| Stage | Observed values |
| --- | --- |
| STT after test speech-end marker | 478, 268, 1163, 574 |
| Dialogue first token | 536, 510, 499, 501, 486, 669, 570 |
| TTS first chunk | 724, 1018, 801, 1939, 949, 532, 548, 680, 304, 392, 362 |
| First server audio from response start | 1465, 1755, 1489, 1593, 1212, 1207, 1256 |
| Submitted frame to observation | 1696, 1738 |

Cancellation took 0 to 1 ms at server timer resolution. No audio for cancelled
response 12 arrived after the cancellation acknowledgement. The next answer
correctly reported request 42 as Awaiting approval. These numbers exclude physical
speaker latency; direct frame submission also excludes browser sampling delay.

## Jev decision-model smoke test

On October 8, 2026, called TypeSafe `/v1/systemone` using `jev-latest`,
which resolved to `jev-1.13.0`. Twelve hand-authored text cases, two sequential
passes, one reused HTTP client, two independent questions per request. No raw
audio, screenshots, private dashboard identifiers or credentials were sent as
evaluation content. This was an isolated experiment; live meeting behavior is
unchanged.

Across 24 requests, wall-clock latency including network was median 130 ms,
range 107 to 222 ms. This excludes STT, waiting for enough words, generation,
any revision, and TTS. No request failed.

| Case | Expected decision | Observed over two passes |
| --- | --- | --- |
| Stop, let me clarify | Interrupt | Both interrupt |
| Wait, that is incorrect. There are four hosts | Interrupt | Both interrupt |
| Mm-hmm | Acknowledgment | Both acknowledgment |
| Right, makes sense | Acknowledgment | Both acknowledgment |
| Speech-start signal without words | Uncertain | Both uncertain |
| And | Uncertain | Both uncertain |
| Wait | Interrupt | Interrupt, then uncertain |
| Recognized words identical to current persona speech | Uncertain | Both uncertain |
| Requested small talk, reply pivots to hybrid-cloud strategy | Revise | Both revise |
| Requested small talk, reply asks how the day has been | Send | Both send |
| Weekend question, reply pivots to VCF optimization interview | Revise | Both revise |
| Earlier balance question, direct answer matching supplied evidence | Send | Both send |

Interruption inputs supplied current persona speech, presenter partial, a
speech-start flag and an explicit statement that speaker identity/audio were
unverified. The rubric distinguished intentional floor-taking, acknowledgments
and insufficient evidence, including possible echo. Reply checks supplied the
user request, candidate reply and relevant prior context; the rubric penalized
unsupported assumptions and forced technical pivots. Companion yes/no questions
checked explicit stop intent or forced technical redirection.

23 of 24 top choices matched the intended labels. These are easy, hand-selected
examples with subjective labels, not an independent accuracy estimate. The
one-word Wait case changed its top choice, with interruption probability 0.52
then 0.45. Confidence must not be treated as measured correctness. Identical
text was marked uncertain, which does not establish acoustic echo detection.

Recommendation: evaluate in observation mode against real turn boundaries before
giving it authority to cancel speech. Keep provider timeout and uncertain results
from disrupting playback. Explicit interrupt controls remain deterministic.
Reference: https://docs.typesafe.ai/api and https://docs.typesafe.ai/primitives.

## Turn-taking iteration verification

October 8, 2026, local Compose, same hosted speech/vision profile and synthetic
fixtures, Jev observation mode enabled. All four spoken turns, changed screen,
earlier-slide recall, explicit cancellation and summary completed. No cancelled
response audio arrived after the acknowledgement. Direct capture-to-observation
delays were 2273 and 1444 ms, excluding browser sampling. First server-audio times
from response start were 2265, 1895, 876, 1035, 1057, 1089 and 1492 ms. These
exclude the newly added continuation window and are not first-audible latency.

Chrome's synthetic microphone check cancelled the greeting after recognized words
(at 6114 ms session elapsed), not on its earlier raw activity detections. The next
reply reported playback start at 15918 ms and completion at 35539 ms without another
cancellation. Jev judgments were present in browser export and server logs; observed
examples took 145 to 191 ms. Neither scheduled playback nor completion proves sound
at the presenter's physical output device.

29 automated checks passed (27 backend and two browser-audio checks); the standalone
opt-in provider test remained skipped, while the hosted application exercise above
ran separately. Regression checks cover noise-only detection, acknowledgment,
recognized interruption, continuation, stale vision completion, waiting for current
evidence, observer failure isolation and observer HTTP result validation.

## Peer preview hosted regression, October 8, 2026

A 78-second synthetic session exercised two attendees through authenticated
WebSocket transport using the verified hosted profile and optional Jev observer.
Both attendee names appeared in generated transcripts with PCM output. The
synthetic architecture slide and changed request demo were observed; recall
correctly returned four Birch hosts. Explicit cancellation after first PCM
prevented further chunks from that response. This verifies server transport,
not acoustic echo handling or physical speaker output.

Observed first-audio-sent latency for seven responses: 2972, 2181, 1424, 1651,
1456, 1862, 1065 ms. Vision capture-to-observation: 1583 and 1506 ms. STT after
browser silence: 475, 272, 1168, 574 ms. Server cancellation: 0-1 ms. These
are individual samples, not a performance guarantee.

The durable ledger recorded $0.121654 estimated spend with no provider errors:
dialogue $0.006941, vision $0.001810, TTS $0.062067, STT $0.033336, Jev $0.017500.
These include conservative reservations and margin, not provider invoices.
The run also exposed spoken name prefixes; the system prompt now explicitly
requests no name/role prefix. Natural-language adherence still requires listening.

Local release checks: 43 backend tests passed, one opt-in provider test skipped;
two browser audio unit tests passed. The separate hosted run above used real
providers. Container and kind smoke tests exercised login separation, two
attendees, PCM, summary, admin admission control and PVC restart persistence.
The browser was inspected with three attendees and the admin statistics page.
The original exact PowerPoint-to-live-VCF-Automation acceptance remains pending.
