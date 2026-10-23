# GitHub publisher access (no Environment setup)

The ThuHa publisher **does not use a GitHub Environment** or a separate
`THUHA_GO_LIVE_APPROVAL` variable. There is no required-reviewer approval queue.

The publish job reads WordPress credentials from **repository-level GitHub Actions Secrets**:
`THUHA_WP_USER` and `THUHA_WP_APPLICATION_PASSWORD`. Do not paste credentials
in chat or commit them. The normal GitHub Actions token reads the `main` and
`factory-state` branch references and performs the audited ledger transactions.
An optional separate read token may be provided as `THUHA_GITHUB_SECURITY_TOKEN`,
but it is **not required** for the publisher's current branch-reference checks.

`config/release.json` remains the source of the owner's explicit on/off decision.
Keep `enabled=false`, `approved=false`, `paused=true` until WordPress
credentials, adapter deployment and coordination with any other publisher are verified.
The production job still runs fresh QA, checks credentials and adapter access,
uses durable CAS and duplicate/idempotency checks, and is restricted to the
initial two-post pilot. No setting may bypass these safeguards.

No GitHub environment settings or Secrets are mutated by repository code.
