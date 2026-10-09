# Reproducible benchmark plan

No real-provider speech, vision or Spark measurements are available yet.
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
