> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# HA-managed native GUI — source increment11785 / performance11778

## Exact retained versus duplicate routes

| UI / route | HA-managed shadow | Legacy/generic |
| --- | --- | --- |
| Rooms/programs/program selection | Hidden; existing /config/rooms, /config/programs/*, /config/program/current non-GET409 guard retained | Kept |
| Temporary room target | No legacy room tile/editor; existing /config/temporary mutation409 guard retained | Kept |
| Boiler/curve editor | Hidden; /config/boiler mutation409 retained | Kept; Chart loaded only when opening curve |
| GPIO/BLE/expander hardware editor | Hidden; /config/hardware409, native E32 GPIO lock retained | Kept |
| Legacy internet-weather editor | Hidden/disabled; saved object preserved; changed /config/device openweather409 AFTER secret-preserving merge | Kept |
| Status/EMS readback | Protected readback kept | Kept |
| Network/MQTT/access/setup | Kept; not gated on /status availability | Kept |
| OTA/update/reboot/recovery | Kept with existing session/CSRF/method/update guards | Kept as before |

Runtime /status.controlMode, NOT a desired unchecked MQTT-mode checkbox, decides
editor visibility. Until explicit legacy, duplicate editors are read-only/hidden;
normal recovery pages remain accessible. No new mode/source default is written.
Legacy weather inputs are disabled while hidden, so irrelevant HTMLvalidation
cannot block network recovery. Network saves preserve the loaded redacted weather
object or its absence, rather than constructing defaults. Server compares after
existing stored APIkey restoration. New/omitted/changed/malformed managed weather
is rejected; unchanged objects need not share key order.

HTML assets/legacy data are not deleted. Direct legacy assets are not an auth
boundary: session/CSRF and server-side writer guards remain authoritative. No
legacy branch on other targets was removed; same-version generic status explicitly
reports legacy. A coordinated mode migration remains separate, never inferred.

## Measured resource reduction, not a latency claim

Before source browser:9startupresources/context,79.2/64.9msDOMContentLoaded in
actual intercepted desktop/mobile Chromium. Those are NOT E32timings.
Root always downloaded/parsed69199compressed bytes of Chart although only curve
uses it. Root now excludes that blocking request and lazy-loads exactly once on
explicit legacy curve navigation. Failed GET can be retried manually; navigation
generations prevent late dependency/poll completion from replacing another form.
No cache/CSRF/CORS policy or statuspoll interval changed; no extra root-modepoll.
Startup expected9→8resources; measured filebyte comparison in MANAGED-GUI-PERFORMANCE.json.
Current actual Chromium repeat is separate MANAGED-GUI-SOURCE-BROWSER.json and
must be run before claiming new browserPASS or before/after milliseconds.
Live authenticated E32time/requestmeasurements still blocked by unavailable valid
test session; no loginspam/reboot to get a benchmark. Public TTFBbaseline remains
22.993/19.161/22.117ms on login/login.js/auth-client.js, not private navigation.

## Verification / open gates

35 actual shippedJS scenarios (8new +27preserved) and21native cases (3new managed
settings +18existing auth/HTTP/AP/network) PASS. Gzip decompression stays solely
at source-preview test boundary, not production asset changes.
No build/release/install/live restart, HAconfig/broker/EMS/Tado action or
physical mode/phone/migration acceptance claim. Distinct patch/rollback and
additive WORKBOARD delta; preserve parent's current canonical headers.

## Independent parent source acceptance —21October

Canonical host compile21nativePASS, actual shippedJS35PASS; actual existing
Chromium desktop/mobileviewport PASS against exact canonical source. Proof:
MANAGED-GUI-PARENT-SOURCE-BROWSER.json,8startupresources each, no initialChart
and exactly1on-demandChartrequest. DCL75.1/56.6ms is intercepted source evidence,
not a device-latency improvement claim. Parent sourcebyte check confirms net65525B
removed from initial payload; no firmware build/install or live actions.
