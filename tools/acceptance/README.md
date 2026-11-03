# Acceptance kit

`rc2-kit/` is the attended-install acceptance kit as used for E32 rc.2 (Home Assistant route),
moved here from a session scratchpad on 3 November 2026 so the next installation (rc.4) can
reuse it. It is rc.2-specific in its names and version checks and must be generalised before
use: see `docs/modern-thermostat/RC4-PLAN.nl.md`, work package A1.

Rules: the HA token lives in `ha-token.txt` next to the scripts and is git-ignored; the E32
password and the MQTT login are typed by the owner (getpass / stdin), never stored. Every
script is read-only towards the E32 and Home Assistant. Offline tests: `test_rc2_receipt.py`
and `test_rc2_capture_smoke.py` (run with `python -I -m unittest` from this folder).

Not included: `mqtt_creds.py` (it read the MQTT login from Home Assistant's storage over the share). The
generalised kit must ask the owner for the MQTT login on stdin, like `mqtt_listen_rc2.py` does; `rc2_acc.py`
line ~408 is the call to replace.
