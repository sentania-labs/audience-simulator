# Peer preview: access, budgets, multiple attendees and distribution

Scott explicitly expanded the single-persona MVP for a small workplace peer
preview. This is not authorization for autonomous audience agents or coaching.

One FastAPI process owns independent WebSocket meetings. A single director picks
an explicitly addressed attendee, otherwise rotates attendees. All attendees
share evidence and history; each has a configured voice. There is one generation
and playback lane, preserving cancellation semantics.

Separate opaque meeting/admin cookies expire after eight hours. Only token hashes
persist. Cookies are HttpOnly, SameSite Strict and Secure by default. Login is
limited to 20 failed attempts per minute per client address and role. Successful
logins do not consume the failure allowance. Mutations and WebSocket connections
require an allowed Origin. Admin credentials grant statistics access, not meeting
access. Shared passwords are suitable for the agreed small trusted group, not
individual accountability. Password changes require restart; revoke existing
cookies by deleting login records during a controlled maintenance operation.

SQLite on a persistent volume stores admission state, session metadata and a
microdollar ledger. Transactions serialize reservations across active meetings.
No raw media, visual text, or transcript enters this database. Metadata currently
persists until the operator removes it; the admin view shows the latest 100
meetings. Exported reviews stay under the presenter's control.

The daily allowance resets at midnight America/Chicago, including daylight saving
changes. Meetings retain their own allowance across midnight. Reservations count
toward both limits before work starts. Text/vision reported usage reconciles
estimates; cancelled or failed work keeps its reservation. The ledger uses a 25%
margin. A provider invoice can still differ. Defaults are conservative admission
estimates, not a contractual billing ceiling.

Default schedule only matches the verified exact endpoint/model profile:
OpenAI gpt-4.1-mini dialogue/vision, gpt-4o-mini-tts, Deepgram nova-3, optional
Jev 1.13.0. Other deployments must explicitly supply all COST_RATES_JSON keys.
Zero rates are an explicit operator choice for local inference. The schedule is:
text input $0.40/million estimated tokens (UTF-8 byte upper estimate plus 1024
overhead), output $1.60/million with 300 tokens reserved; vision $0.01/call;
speech $0.00003/input byte; STT $0.02/minute in ten-second reservations;
Jev $0.001/call. All receive the margin. TTS/STT/Jev reservations are intentionally
not invoice reconciliation. Review the schedule when changing providers or rates.

Reference pricing reviewed October 8, 2026:
[OpenAI text](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[OpenAI speech](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts),
[Deepgram](https://deepgram.com/pricing),
[TypeSafe](https://docs.typesafe.ai/models).
The latter three reservation rates above are intentionally conservative local
estimates rather than copies of a provider price table.

Budget or time exhaustion stops provider work and produces the existing extractive
recap. Defaults: $1.50/meeting, $10/day, three meetings at once, four attendees,
30 minutes, five-minute inactivity timeout. An 80% warning appears in the meeting.

Deploy one replica, one worker, with Recreate upgrades. Pause new admissions and
wait for active meetings before an upgrade. Existing meetings cannot migrate.
Docker Compose remains supported. GitHub-hosted CI runs Docker and kind tests,
then publishes an immutable amd64 image and version-pinned release bundle.
Argo and the deployment repository own rollout, ingress, sealed secrets and DNS.
