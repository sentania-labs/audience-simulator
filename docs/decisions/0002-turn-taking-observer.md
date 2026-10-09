# Turn confirmation and optional decision observation

Status: implemented for human retest, October 8, 2026.

Evidence: human sessions repeatedly cancelled on speech-start detections, including
with speaker gain zero. Finalized recognition split unfinished phrases into separate
replies. An older vision completion could restore a stale current view while a new
frame was pending. Regression tests reproduced these cases before implementation.

Decision: browser energy and recognition speech-start events are telemetry only.
Recognized multiword speech or explicit stop/wait/pause/no confirms an interruption;
common brief acknowledgments are excluded during active generation or playback.
Explicit Interrupt remains immediate. Finalized segments have a 700 ms continuation
window, extended to two seconds after unfinished phrases; new partials postpone it.
These lexical rules are a baseline, not a semantic or acoustic echo classifier.

Changed-frame timestamps prevent older completions from becoming the current view.
Replies wait up to 1.5 seconds for pending analysis, then disclose pending context.
Historical observations remain available for recall.

Jev is optional and observation-only. Bounded conversation excerpts go to TypeSafe
with join-screen disclosure. One concurrent request per session, two-second timeout,
validated labels, sanitized failure record and cancellation on session close. Its
results never gate speech or cancellation. Reply evaluation happens after generation.
Raw audio and images are not sent to the observer. Model and key are deployment
settings; the speech, dialogue and vision providers stay independent.

Tradeoffs: speech recognition latency now affects automatic interruption; additional
silence buffering increases response latency. Background speech or echo that produces
words can still interrupt. Jev confidence is not verified correctness. Human room
noise, acoustic output and deliberate barge-in remain acceptance gates.
