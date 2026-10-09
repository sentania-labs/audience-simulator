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

Run `./scripts/acceptance.sh` for the real manual walkthrough. It correctly refuses
the current mock configuration. No provider credentials were available.
