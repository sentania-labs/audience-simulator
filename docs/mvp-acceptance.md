# Manual MVP acceptance

**Gate: NOT RUN with real providers.** Credentials unavailable at bootstrap.
Mock mode cannot satisfy any speech-quality or visual-grounding gate below.

Preparation: configure four real adapters, run setup checks, open the app on localhost
or HTTPS, use headphones, prepare a PowerPoint VCF architecture slide and a live
VCF Automation demonstration. Use nonsensitive material approved for these providers.
List actual visible labels and diagram relationships on the slide and demo before
starting; do not accept generic VCF knowledge as evidence of visual understanding.

- [ ] Configure one technically proficient enterprise infrastructure architect,
      including name, role, expertise, conversational style and meeting objective.
- [ ] Review provider hosts and consent. Join with a working microphone. Hear a
      natural introduction in the configured voice, not a tone. Speak a question
      and hear a relevant spoken answer. Confirm speech transcript is accurate.
- [ ] Click Share screen, explicitly choose the PowerPoint window. Verify visible
      share indicator and preview. Discuss its diagram. Confirm the persona asks
      about a specific visible relationship or label from the prepared inventory.
- [ ] Click Switch share and choose live VCF Automation, or share the entire screen
      and switch windows. Confirm a new timestamped observation describes the actual
      changed UI and the persona asks a question grounded in its current visible state.
- [ ] Ask aloud: "Back on the earlier slide, how did those components connect?"
      Confirm the answer accurately references previously observed visual evidence,
      without describing that slide as still on screen.
- [ ] Interrupt the persona mid-sentence with speech. Confirm audible output stops,
      no older speech resumes, and the next response reflects the interruption.
      Repeat using the explicit Interrupt control. Inspect response IDs in download.
- [ ] Stop sharing through the native browser control. Ask about the current view.
      Confirm it admits there is no active view while retaining historical recall.
- [ ] Mute/unmute microphone and output; verify their actual effect. Repeat a few
      exchanges and maintain a ten-minute session without overlapping stale speech.
- [ ] End meeting. Inspect useful transcript, timestamped observations and extractive
      summary; interrupted text is marked. Download JSON with timing and playback events.
- [ ] Record observed STT, dialogue, TTS, first-playback estimate, vision delay and
      interruption metrics using benchmark plan. Record failures and uncertainties.

Fail the gate if the persona only uses subject knowledge, ignores the changed screen,
fabricates unreadable details, loses earlier context or plays cancelled speech.
Do not mark acceptance complete on a 200, mock pass, build or container health alone.

Result record: date/time (America/Chicago), provider profile/model versions, browser,
slide/demo visible evidence, actual persona quotes, metric distributions, issues,
and pass/fail for each step. Real evidence belongs here once the run occurs.

## Bootstrap validation, separate from acceptance

17 automated checks passed (15 backend, two browser-audio unit checks); the paid
provider integration check was skipped. Frontend production build and Compose build
passed. The container was run and the rendered UI inspected in Chrome. Fake browser
media exercised capture, PCM scheduling, share sampling, test turns, interruption,
share stop, export and extractive summary. At 390 px, no horizontal page overflow
was observed. This does not satisfy the PowerPoint/live VCF demonstration gate.

Run `./scripts/acceptance.sh` for the real manual walkthrough. It refuses mock configurations. Hosted credentials are now configured locally.

Real-provider synthetic validation recognized microphone input in Chrome and
scheduled spoken replies. Direct WebSocket checks grounded responses in the
architecture and changed request fixtures, then recalled the earlier host count.
This is partial feasibility evidence, not a passed acceptance checklist. See
[benchmark evidence](benchmark-plan.md) for timings and outstanding reliability checks.

## Next human retest: interruption and screen freshness

- Refresh the page to load the new client and review the observer data-flow disclosure.
- Stay silent while the greeting completes. Speech-start detections alone should
  no longer cancel it. Compare `recognized_words` cancellations with actual speech.
- While Morgan speaks, say "mm-hmm", then separately "Stop, let me clarify".
  The acknowledgment should leave playback running; the deliberate interruption
  should stop stale playback. Also verify the immediate Interrupt button.
- Pause briefly in "Here is information about ... Deepgram". Expect one combined
  turn rather than an answer to the unfinished phrase.
- Switch shared windows and ask what is visible immediately. During processing,
  Morgan should wait briefly or disclose that the changed view is pending.
- End and export. Jev judgments are comparison evidence only, not the controller.

Synthetic tests cannot establish performance with the presenter's room noise,
physical speakers or echo path. Real completion of spoken replies remains a gate.

## Peer preview release gates

These supplement the original visual acceptance scenario.

- Run scripts/check.sh after scripts/install-ci-tools.sh (add .release/tools to PATH).
- Build the image and run scripts/smoke-container.sh IMAGE.
- Run scripts/smoke-kind.sh IMAGE with Docker, kubectl, kind and Helm available.
  It verifies login separation, multi-attendee audio/recap, admin access and PVC
  restart persistence using mock providers and temporary generated passwords.
- In the rendered browser, sign in as a meeting user, configure three attendees,
  address one by name, hear output, end and inspect the recap.
- Open /?admin. The meeting password cannot access statistics. Sign in with the
  separate admin password, inspect the completed session, pause/resume admissions.
- Test two browser meetings concurrently. Their conversation histories must differ.
- Temporarily lower budgets in a test deployment. Verify an 80% warning and a
  limit event followed by a recap, closed media capture and no further paid work.
- Verify unknown endpoint/model pricing refuses admission without an explicit
  cost schedule.
- On external deployment, verify HTTPS, Secure cookies, Origin, WebSocket ingress
  timeout, PVC backup and your chosen storage class. Local kind does not prove
  those cluster-specific settings.
