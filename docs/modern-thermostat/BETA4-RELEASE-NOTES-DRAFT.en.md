# E32 V2 beta4 — draft: session recovery and heating settings overview
<!-- user-release-notes:v2:en -->

Draft only. Not frozen, published or installed. The published beta.3 downloads
are unchanged.

## New

- **Recover access when all four saved sessions are occupied.** Select the
  recovery option on the login page and enter your username and password again
  to sign other browsers out. Device settings are preserved.
- **A boiler illustration even without a model photo.** A local, unbranded
  illustration appears on Home and My boiler when the selected profile has no
  photo or its photo fails to load. Available model photos retain their credits.
- **Heating settings overview on the EMS devices page.** Four prepared Classic
  settings show their received value, status and age, with a mobile layout.
  Missing or expired readings stay blank. Refresh reads the local snapshot;
  it does not query the boiler.

- **Correct pressure requirements for the target boiler.** The Ecomline trial
  profile explains that this installation has no digital pressure sensor. It
  requires review of a separate pressure-check method and a fresh declaration
  for each heat trial. Neither a profile selection nor a checkbox enables control.

## Fixed

- Abandoned web sessions expire after 30 minutes without accepted authenticated
  requests, rather than occupying a slot for seven days. Communicating dashboards
  keep access for up to seven days. Late requests cannot revive an expired session.
- Login messages describe saved sessions instead of currently open browsers.
  Ordinary login does not sign other browsers out; recovery requires a separate choice.
- A failed model image falls back to the generic illustration and clears the
  unavailable photo's credit.

## Updating

After publication, update the E32 through its normal GitHub updater. These
changes require no new HA installation; HA 0.4.0b3 remains unchanged. Verify the
new boot, version and retained settings.

Session recovery is unavailable during a boiler trial, firmware update or
unconfirmed firmware boot. Recovery does not require a factory reset.

## Limitations

Physical boiler and valve control remain disabled. Boiler settings stay
read-only in the standard firmware. The prepared four-setting editor and the
EMS-ESP entity reference do not grant write permission or complete EMS-ESP
write support. The separate pressure-check method for the target installation
still requires physical review.
