"""Prepare E32 1.0.0-rc.3 / HA 1.0.0rc3 in the integration worktree (argv[1])."""
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
def rd(p): return (root / p).read_text(encoding='utf-8')
def wr(p, s): (root / p).write_bytes(s.encode('utf-8'))
def sha(p): return hashlib.sha256((root / p).read_bytes()).hexdigest()
def sub(p, pairs):
    s = rd(p)
    for a, b in pairs:
        assert s.count(a) == 1, (p, a[:70]); s = s.replace(a, b)
    wr(p, s)

E32 = """# E32 V2 1.0.0-rc.3 — the third 1.0 candidate: away per room, smart warm-up on by default and one boiler test
<!-- user-release-notes:v2:en -->

The third 1.0 candidate. A room can have its own away temperature, the E32
warms rooms up on time and follows the outdoor temperature by default, and
there is one boiler test that it remembers. If it runs 14 days without
problems with the E32 controlling the boiler, the same code becomes 1.0.0.
Install it with HA 1.0.0rc3.

## New

- **Away per room:** a room can have its own away temperature. It is used
  when all persons linked to that room are away, even if others are still
  home, so a bedroom cools down while the living room stays warm. When
  everyone is away, or the house is set to Away or Holiday, every room uses
  the house away temperature. A room without persons, or without its own
  value, follows the house.
- **Smart warm-up, on by default:** a time in the week program means "warm
  at that time". The E32 learns how long each room takes and starts early,
  with the coolest water that still makes it: "starts at 07:20 so it is
  21 °C at 09:00". Until a room is learned it starts at the program time and
  says so. You can switch it off under Home → Heating settings → Advanced.
- **Heating curve, on by default:** the water temperature follows the
  outdoor temperature, with the room correction on top. It starts with a
  standard curve and switches to one learned for your house after 6 steady
  periods; the page shows which one it uses. Without an outdoor temperature
  the water temperature follows the rooms only. A setting you switched off
  yourself stays off.
- **One boiler test** (Rooms): the guided test is the only boiler test and
  its result is kept over restarts and updates ("passed on 1 Nov 2026,
  21:12"). "I have already done this test" records your own mark; an E32
  that controlled this boiler before shows the test as not needed. The
  Boiler page shows the last result and an installer check without heat.
- **No old thermostat assumed:** texts mention an old thermostat only when
  the E32 heard one on the boiler bus.
- **Which rooms want heat:** the Overview names the rooms that want heat,
  each with its temperature and target.
- **Boiler settings explained:** each setting EMS-ESP can change has a short
  "About this setting": what it does, what to expect and the risk. The E32
  still only reads them.

## Fixed

- The Overview showed Home Assistant as "last connected 3 min ago" in orange
  between its 5-minute refreshes; it now stays connected until two refreshes
  are missed.

## Updating

From 1.0.0-rc.2, while someone is home. First install HA 1.0.0rc3 (HACS)
and restart Home Assistant, then press Install on the E32's Firmware entity.
Then confirm the takeover again: a firmware change clears it, and until then
the E32 keeps only frost protection. Repair "Confirm again that the E32 may
control the boiler", or Rooms on the E32.

- Smart warm-up and the heating curve switch on with this update, unless
  you switched them off in rc.3. Settings, rooms, programs, sensors, valves
  and learning are kept.

## Limitations

Radiator valve control is not yet verified on real valves. Behind an EMS
adapter that leaves byte 7 of telegram 0x18 empty (such as the Bosch
EasyControl Adapter) the three-way valve position cannot be seen. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
Pairing Bluetooth sensors is done on the E32. Charts are lost on a restart.
"""

HA = """# HA 1.0.0rc3 — the third 1.0 candidate: everything from Home Assistant, away per room and which rooms want heat
<!-- user-release-notes:v2:en -->

Companion release for the E32 1.0.0-rc.3. Needs Home Assistant 2026.10.0 or
newer.

## New

- **Set it all up in Home Assistant:** what you can set on the E32 can now
  also be set under Configure, except pairing Bluetooth sensors, Wi-Fi, MQTT
  and passwords:
  - Home → Presence: the house away temperature.
  - Rooms → a room: its radiator valves (just pick their climate entities;
    a known Zigbee2MQTT valve is driven by the E32 directly, so it keeps
    working without Home Assistant) and the room's own away temperature.
  - Home → Comfort and boiler care: each setting automatic or set by you.
  - Home → Heating and boiler → Boiler model.
  - Advanced and diagnostics: Bluetooth sensor names, the E32 system log and
    the E32 time zone (with a repair when it differs from Home Assistant's).
- **Away per room:** the room's climate shows why it is cooler (its own
  persons are away, everyone is away, or the house mode).
- **Smart warm-up:** the switch "Warm on time with the coolest water" is now
  called Smart warm-up and is on by default (same entity ID). The room's
  climate says when it starts: "starts at 07:20 so it is 21 °C at 09:00".
- **Which rooms want heat:** a card under Now on the dashboard: how many
  rooms want heat, which, and the boiler request.
- **Boiler device name** from the model chosen on the E32, or a neutral
  "Nefit boiler (product 206)" when none is chosen.
- **The comparison with a thermostat** only appears in a trial run with a
  thermostat on the boiler bus. Once the E32 controls the boiler, the
  comparison entities you did not change are removed (history is kept).
- **No old thermostat assumed** in setup, repairs and advice.

## Updating

1. Install HA 1.0.0rc3 with HACS (or the release ZIP) and restart Home
   Assistant.
2. Update the E32 with its Firmware entity, while someone is home.
3. Then fix the repair "Confirm again that the E32 may control the boiler".

Entity IDs and history are kept. Most new features need E32 1.0.0-rc.3.

## Limitations

Radiator valve control is not yet verified on real valves. EMS Classic
boilers only; EMS+ comes in 1.1. Writing boiler settings comes after 1.0.
Pairing Bluetooth sensors is done on the E32. HACS lists OpenThermostat as a
custom repository, not yet in the default HACS list.
"""

link = '\n\n[Full release notes and history](https://github.com/dielessen/open_thermostat/blob/main/docs/modern-thermostat/RELEASE-NOTES.md)\n'
for name, sec, f in (('E32', E32, 'RELEASE-NOTES.md'), ('HA', HA, 'HA-RELEASE-NOTES.md')):
    n = len((sec.rstrip('\n') + link).encode()); print(name, 'bytes', n); assert n <= 6000
    p = f'docs/modern-thermostat/{f}'; wr(p, sec + '\n' + rd(p))

sub('release.json', [('"version": "v1.0.0-e32v2-rc.2"', '"version": "v1.0.0-e32v2-rc.3"')])
sub('ha/config/custom_components/open_thermostat/manifest.json', [('"version": "1.0.0rc2"', '"version": "1.0.0rc3"')])
for p in ('ha/config/custom_components/open_thermostat/e32_week.py', 'ha/config/custom_components/open_thermostat/frontend/e32-week-card.js',
          'ha/config/custom_components/open_thermostat/week_planner.py', 'test/week-editor-browser.cjs'):
    s = rd(p); n = len(re.findall(r'-1\.0\.0rc2\.js', s)); assert n >= 1, p
    wr(p, s.replace('-1.0.0rc2.js', '-1.0.0rc3.js')); print(p, n)

# Gate: rc.2 is installed but has no acceptance receipt -> evidence gap + the owner's one-time exception.
gap_p = 'docs/modern-thermostat/RC2-UPDATE-GAP-20261103.json'
wr(gap_p, json.dumps({
    "schema": 1, "date": "2026-11-03", "status": "INCOMPLETE",
    "scope": "rc.2 update evidence gap; do not replace the accepted beta.22 basis",
    "candidate_tag": "v1.0.0-e32v2-rc.2", "published": True, "installed_tag": "v1.0.0-e32v2-rc.2",
    "install_route": "home_assistant_update_entity", "native_install_commands": 1, "manual_upload_commands": 0,
    "manual_result": "Installed by the owner on 3 Nov 2026 about 07:34 local (HA update entity from beta.22, HA 1.0.0rc2 via HACS), takeover confirmed again at 07:38, active control running without warnings. No pre-install capture was made, so there is no acceptance receipt.",
    "acceptance_receipt": None, "acceptance_receipt_status": "NOT_CAPTURED",
    "last_accepted": "v0.1.0-e32v2-beta.22"}, indent=2, ensure_ascii=False) + '\n')
basis = json.loads(rd('docs/modern-thermostat/E32-UPDATE-GATE.json'))['accepted']
exc_p = 'docs/modern-thermostat/RC3-PUBLICATION-EXCEPTION-20261103.json'
wr(exc_p, json.dumps({
    "schema": 1, "status": "APPROVED", "scope": "one_prerelease_publication",
    "candidate_tag": "v1.0.0-e32v2-rc.3", "unaccepted_predecessor": "v1.0.0-e32v2-rc.2",
    "accepted_basis_tag": basis['tag'], "accepted_basis_receipt_sha256": basis['sha256'],
    "predecessor_acceptance_status": "INCOMPLETE", "gap_report": gap_p, "gap_report_sha256": sha(gap_p),
    "reason": "rc.2 is installed and runs active control without warnings, but no acceptance receipt was captured. Publish this one rc.3 pre-release after a green check and exact-tag CI, with beta.22 as the last accepted basis. The rc.3 installation is captured as its acceptance (pre- and post-install, Home Assistant route); v1.0.0 still needs an accepted rc.3 update and a 14-day PASS readiness report.",
    "device_installation_authorized": False, "boiler_trial_authorized": False,
    "approval": {"actor": "repository_owner", "method": "explicit_user_instruction",
                 "decision": "approve_one_prerelease_publication",
                 "statement": "Owner, answer to \"De publicatiecontrole van rc.3 wil een 'acceptatiebewijs' van rc.2 ... Hoe wil je rc.3 laten publiceren?\": \"Eenmalige uitzondering (Aanbevolen)\" (record that rc.2 is installed without a receipt, publish rc.3 as a pre-release; the rc.3 installation is captured as its acceptance).",
                 "at_utc": "2026-11-03T10:15:08Z"},
    "separate_installation_instruction": "docs/modern-thermostat/RC3-OWNER-INSTRUCTION-20261103.json"},
    indent=2, ensure_ascii=False) + '\n')
c = json.loads(rd('docs/modern-thermostat/RC2-KANDIDAAT.json'))
c.update({
    "planned_tag": "v1.0.0-e32v2-rc.3", "previous_published_tag": "v1.0.0-e32v2-rc.2", "ha_tag": "ha-v1.0.0rc3",
    "install_order": [
        "ha-v1.0.0rc3 (HACS, then a Home Assistant restart)",
        "v1.0.0-e32v2-rc.3 (Home Assistant Firmware update entity, one Install press), attended, with the owner at home, with pre- and post-install capture as the acceptance receipt",
        "confirm the takeover again right after the update (Repairs, or Rooms on the E32); until then the E32 keeps only frost protection",
    ],
    "observed_installed_ha": "1.0.0rc2",
    "owner_instruction": "docs/modern-thermostat/RC3-OWNER-INSTRUCTION-20261103.json",
    "planned_acceptance": {"method": "home_assistant", "checklist": "docs/modern-thermostat/HA-UPDATE-ACCEPTANCE-BETA19.md",
                           "receipt": "docs/modern-thermostat/update-acceptance/e32-rc3-<YYYYMMDD>.json"},
    "release_notes": {"e32": "docs/modern-thermostat/RELEASE-NOTES.md (# E32 V2 1.0.0-rc.3)", "ha": "docs/modern-thermostat/HA-RELEASE-NOTES.md (# HA 1.0.0rc3)"},
    "changes": [
        "rc.2 is installed (3 Nov) without an acceptance receipt; rc.3 replaces it as the 1.0 candidate (release-1.0)",
        "Away per room (plan.room_away.v1): a room's own away temperature while all its persons are away; the house value when everyone is away or in Away/Holiday",
        "Smart warm-up (apply_learned) and the heating curve (weather_curve) on by default; records without version 2 read both as on; status texts say what is used",
        "One boiler test (Rooms), its result kept in the takeover_test note; mark as done; not needed after earlier control; the attended heat test on the Boiler page is closed",
        "No old thermostat assumed unless one was heard on the bus (active.thermostat_seen)",
        "HA parity: away temperature, valves in the room form (route per entity), comfort and boiler care, boiler model, Bluetooth sensor names, system log, time zone",
        "HA: boiler device named after the chosen model; comparison only in a trial run with a thermostat; rooms-wanting-heat card",
        "E32 pages: rooms that want heat named on the Overview; HA stays connected between its 5-minute refreshes; EMS setting help",
        "final_check.sh: opt-in --lanes/--copy (default unchanged)",
    ],
    "not_included": [
        "v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)",
        "radiator valve control verified on real valves",
        "EMS+ boilers (1.1)", "writable EMS boiler settings (after 1.0)",
        "Bluetooth sensor pairing from Home Assistant (later release)",
        "the per-room overview (1.1)", "a read-only API key for assistants (later release)",
        "automatic activation (active control still needs the owner's confirmed takeover)",
    ],
})
wr('docs/modern-thermostat/RC3-KANDIDAAT.json', json.dumps(c, indent=2, ensure_ascii=False) + '\n')
wr('docs/modern-thermostat/RC3-OWNER-INSTRUCTION-20261103.json', json.dumps({
    "schema": 1, "recorded_at_utc": "2026-11-03T10:15:08Z",
    "requests": ["Owner, 3 Nov 2026: \"zet alle agents in voor de volgende rc3\" and \"zorg dat RC3 een stuk completer is\": per-room away by the owner's presence rules, everything configurable on the E32 also from HA (except Bluetooth pairing, Wi-Fi, MQTT, passwords), valves by entity inside the room form, away temperature in Configure, boiler named after the chosen model, one remembered boiler test with an already-done mark, no existing thermostat assumed, smart warm-up and the heating curve on by default with the E32 deciding when its data is good enough, which rooms want heat on both dashboards."],
    "scope": "1.0 candidate rc.3: E32 v1.0.0-e32v2-rc.3 + HA ha-v1.0.0rc3 from release-1.0. Publish after a green check and exact-tag CI. Installing is a separate, attended step with pre- and post-install capture.",
    "not_included": ["installation (a separate, attended step)", "v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)"],
    "publication_approval_reply": None, "publication_approval_at_utc": None, "installation_approval_reply": None},
    indent=2, ensure_ascii=False) + '\n')
sub('docs/modern-thermostat/E32-UPDATE-GATE.json', [
    ('"pending_tag": "v1.0.0-e32v2-rc.2"', '"pending_tag": "v1.0.0-e32v2-rc.3"'),
    ('"candidate_plan": "docs/modern-thermostat/RC2-KANDIDAAT.json"', '"candidate_plan": "docs/modern-thermostat/RC3-KANDIDAAT.json"')])
g = json.loads(rd('docs/modern-thermostat/E32-UPDATE-GATE.json'))
g['publication_exception'] = {"receipt": exc_p, "sha256": sha(exc_p)}
wr('docs/modern-thermostat/E32-UPDATE-GATE.json', json.dumps(g, indent=2, ensure_ascii=False) + '\n')
print('ok')
