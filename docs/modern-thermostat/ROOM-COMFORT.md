# Room comfort and native presence reports

Development target: E32 beta.6 and HA 0.4.0b4. Not installed or physically
qualified during this work.

The normal room editor and room wizard's advanced section can enable comfort
modes, set the away target and default temporary duration, and select an optional
HA person. The room climate entity exposes its existing Automatic, Boost, Away,
Frost and Off controls. Enabling a profile does not issue a mode/temperature
command. A room without automatic presence can still use manual comfort modes.

Comfort targets must fit the room bounds. The existing native installation
source fixes its independent frost target at **5 °C**. A new normal comfort profile
therefore retains 5 °C and must allow that target in the room limits. The editor
reports this constraint instead of persisting an incompatible new profile or
waiting for the controller to reject it. Existing unchanged legacy profiles are
preserved; they do not replace the native source's protection policy.

On an active native plan, logical comfort/presence changes use the same current
source, worker, save/reload and exact durable readback as programme/contact edits.
Missing firmware support is rejected before saving. The source mapping, ordinary
room bounds and physical output permissions do not change through this route.
Changing those room bounds remains the separate existing profile transaction.

The editor and wizard pin the selected person's registry identity and check it
again after compilation/review. Explicitly disabling comfort removes its stored
presence/window fields. Independently selected window and door contacts remain
active. A legacy window must first be represented by the explicit contact list;
an older client cannot silently discard it when disabling comfort. Clients that
do not know the new settings preserve the existing profile.

For the built-in HA `person` platform, a reviewed logical report adapter consumes
native `state_changed` and `state_reported` events. It does not create evidence
from startup state or status reads. Only `home` and `not_home` map to presence;
unknown, unavailable, restored and other named locations remain unknown.

Each accepted report also checks the person's selected `device_tracker` source:
current registry identity, availability, restore status and original native
report timestamp. Source timestamps cannot lie after the person report. A later
person re-emission from the same cached tracker retains that tracker's original
age, measured against the owned monotonic clock. Partial wall-clock changes,
temperature updates and repeated status reads cannot reset it. Rebind/disconnect
withdraw usable proof and retain bounded replay/source-age watermarks. A new
report from a retired cached source cannot resume control.

The existing presence contract expires after **two minutes**. The chosen person
and tracker must deliver appropriate fresh native reports within that interval.
The actual HA person integration is tested with an isolated tracker update that
causes a new person report even while Home stays unchanged. This proves the HA
logical event path, not a physical GPS/router observation or a device-specific
reporting interval. Such physical source qualification remains separate.

The C++ effective-target policy retains its existing priorities. Window/contact
inhibition still applies to ordinary and temporary demand. A temporary manual
target is not cancelled by a presence change. Unknown/expired presence does not
invent Away. The controller reports the effective target and reason, which the
editor projects from the existing climate entity without additional polling.
The backend supplies the expected installation/room identity. The editor checks
that identity against the climate state for contacts, manual targets and comfort
together. A missing or reused entity ID cannot substitute another room's status;
an explicit reload follows a legitimate renamed canonical entity.

Software evidence is retained under `out/room-comfort-20261027/`: real HA
editor/wizard storage and identity races, original native person/source-age
events, actual built-in person lifecycle, the real C++ native plan/readback and
Home/Away/unknown targets, and English/Dutch desktop/mobile browser cases.
Physical opening/closing, presence reporting, valves, boiler behavior and
independent frost protection remain acceptance work. The same development bundle
adds the [normal vacation end-date flow](ROOM-VACATION.md) over the existing
finite core policy and entity service.
