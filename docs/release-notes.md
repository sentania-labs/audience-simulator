A peer preview for private presentation practice, with spoken replies and
shared-screen context.

- Separate meeting and admin passwords with expiring cookies.
- Independent meetings, one to four configurable attendees and consistent voices.
- Shared background context, baseline presets and one speaker at a time.
- Durable estimated spending limits: $1.50 per meeting and $10 per Chicago day.
- Three concurrent meetings, time/idle limits and an admin admissions pause.
- Admin statistics without storing conversation content or raw media.
- Helm chart, Argo example and Docker Compose in the release bundle.

Download the release bundle for the exact image digest and matching deployment
files. Generate credentials outside this repository and reference an existing
Kubernetes Secret. The image contains no credentials.

This is an amd64, single-replica preview. Upgrades interrupt active meetings, so
pause admissions and drain first. Spending is a conservative estimate, not an
invoice guarantee. Native Anthropic and additional local speech adapters,
advanced persona dynamics and coaching remain future work. The exact full
PowerPoint-to-VCF-Automation acceptance scenario remains a manual validation gate.
