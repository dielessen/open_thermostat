# One-time beta.3 evidence exception — proposal only

Status: **DRAFT, NOT APPROVED**. This proposal does not publish a release or
change the active development branch. Beta.1 remains the last formally accepted
installation; beta.3 remains pending and its evidence remains incomplete.

The versioned beta.4 candidate in PR #2 passed all nine validation jobs and
2,240 independent package checks at `daf01fc`. Those checks establish software
and package results. Original beta.3 preflight, backup and installation receipts
have not been recovered; the stored E32 session returned HTTP 401. New status
exports can establish present identity and boot state, while historical records
are still required for complete installation acceptance.

## Proposed decision and limits

The owner could explicitly approve **one GitHub beta.4 prerelease publication**
using beta.1 as the last real accepted basis and retaining beta.3 as INCOMPLETE.
This grants no device installation, login/session recovery or physical boiler
trial. Automatic control and persistent boiler-setting writes remain disabled.

The record in `BETA3-PUBLICATION-EXCEPTION-PROPOSAL.json` is unsigned and inactive:
its status is `DRAFT_NOT_APPROVED`, its approval is null, and the policy's
`publication_exception` is null. General requests to continue release work do
not populate an approval record.

## Proposed validation

The publication check requires a candidate plan naming the exact candidate and
last published E32 release. Merely changing `pending_tag` or clearing it cannot
substitute an older accepted release for that predecessor.

Normal publication uses the accepted previous release. The optional exception
path additionally requires all of the following:

- A hash-bound record with status APPROVED, an explicit owner decision, the
  original approval statement and a valid UTC approval time.
- Exactly the planned beta prerelease, its unaccepted predecessor and the real
  accepted basis receipt identity; the record cannot authorize another release.
- A hash-bound INCOMPLETE gap report. The thirteen checks and receipt hash of
  the real accepted basis still apply; beta.3 is never marked PASS by this path.
- Publication-only scope, with device installation and boiler trial permissions
  explicitly false. Stable and RC releases cannot use this exception.

This host-side record follows the existing repository audit model: the policy
binds reviewed record bytes by SHA256. It is not a cryptographic owner signature.

## Activation after an explicit owner decision

Only after that decision would the coordinator preserve its exact statement,
UTC time and publication-only decision in an APPROVED record. Its SHA256 would
be referenced by `publication_exception`, and `pending_tag` would move to
`v0.1.0-e32v2-beta.4`. The accepted beta.1 receipt remains byte-identical.
The existing mandatory gate remains enabled. A draft record or an absent,
changed or mismatched approval keeps publication blocked.

The final source/tag must then pass the complete existing CI and independent
package checks. Device installation and the attended boiler trial remain
separate actions. Capture the original preflight, backup and native installation
receipts prospectively before installing beta.4; a publication exception does
not accept that later installation or authorize a subsequent exception.

If original beta.3 evidence is recovered instead, complete normal acceptance
and use the regular publication path without an exception.
