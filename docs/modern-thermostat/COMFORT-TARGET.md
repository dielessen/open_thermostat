# Effective target owner —11785 source increment

Existing api1 automatic/base/schedule, monotonic temporary override and OFF
selection now use one pure EffectiveTarget::api1 function in real ShadowController.
No existing command envelope, target source string, API capability, writer,
schema/off/expiry semantics or physical output protection is expanded.

Separate profile-qualified interfaces implement bounded boost, away/vacation,
optional presence and explicit window policy for the NEXT reviewed contract.
These modes are NOT currently advertised or accepted over api1, and no HA GUI
feature is claimed installed. Default profile unreviewed -> no new target.

Priority: owner availability / monotonic fault -> OFF -> required known fresh
window / open window -> bounded manual temporary/boost -> explicit away/vacation
-> optional required fresh presence -> valid automatic target.
Manual boost can override presence-away but cannot override window unknown/open.
Unknown configured inputs are not assumed home/closed. Features not configured
do not require invented presence/contact hardware. No freeze-temperature actuator
fallback or universal safe valve position is introduced.

Temporary/boost use bounded monotonic deadlines and reject overflow; expiry
mutates state so a later backward wall clock cannot replay a boost. Vacation
requires trusted bounded future UTC, blocks reversed/invalid time and expires
state permanently once its end is observed. A required contact cannot defer
processing of expiry. Owner loss drops runtime overrides; reconnect cannot
restore them. Forward monotonic evaluation after reversal stays blocked until a
new valid owner command/reset; commands themselves reject backward timestamps.

Learning allowed here only means pure automatic-target selection: source,
delivery, schedule, profile and supervisory qualification STILL must independently
pass before any model update. A target is never readiness or output permission.
No anti-seize, DHW-write, boiler reset, arbitrary HA action or new endpoint exists.

verify-comfort-target.py:9pure conflict/expiry negatives +13actual ShadowController
wire cases, real-cJSON/GTest/strict C++17. No source browser check needed for this
non-GUI increment, no device action. Revert comfort-target-only-core.patch to
restore prior selection. Active graph/wire/UI/feature acceptance, human phone,
DHW capability mapping and complete F10 product acceptance remain OPEN.
