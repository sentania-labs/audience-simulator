# Meeting recovery maintenance authorization

Scott's October 9, 2026 instruction, preserved verbatim before publication:

> do some investigation and let's do it.
>
> also: once in a meeting or "authed" with the generic password: under Audience/simulator - put a link to the github issues page to open a new issue under the link heading Feedback - maybe even link directly to "Open an issue"/new issue.
>
> proceed

Scope: investigate reconnect and speech stalls, implement verified recovery fixes
and the authenticated Feedback link, validate the running artifact, and submit
the maintenance changes through the SDLC review and PR process. Preserve unresolved
failure evidence in an issue without transcript text or credentials. This does
not authorize changes to the external cluster or public DNS.

## Next sprint authorization

Scott's October 9, 2026 instruction, preserved verbatim:

> 1> so the dashboard can be created by me - so just make sure the metrics endpoint is there.
>
> otherwise proceed.

Scope: metrics endpoint and audio instrumentation (no dashboard), optional rated
feedback and explicit transcript submission, admin review with retention/deletion,
admin runtime provider/model settings with validation/history/rollback, and the
fictional cast and conversation behavior improvements discussed in this session.
Validate and deliver through SDLC. No external deployment or release is requested.

## Admin simplification and release authorization

Scott's October 9, 2026 instructions, preserved verbatim:

> okay we overrotated on persona.  FOr now let's just have a cast of six random peeps that we insert.  less backstory focused and more general.  I want to share this and start getting feedback to dial in.
>
> admin: revamp the admin page so it's not a single scroll - give me some tabs.
>
> Also: Models and providers: populate the model based on the provider connection and the key.
>
> Let me select multiple providers:
> gpt, anthropic, gemini, openAI compactible (make me provide a URL and key).
>
> also check the logs for any errors/diagnostic problems we should address and include that.
>
> target = 0.2.1
>
> this means the helm chart should shift keys out of secrets and shift them into the app
>
> FYI I put in gpt-6-luna as the dialoge model and when I load the meeting I get a timeout

Scope: implement and validate these changes, use the SDLC review and PR pipeline,
and publish the requested release. Record relevant diagnostic findings without
private transcript text or keys. Provider credentials become app-owned encrypted
records; the encryption key and access credentials remain deployment-owned. No
external infrastructure changes or public DNS changes are authorized here.
