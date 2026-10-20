# Group water / floor / mixer — bounded SOURCE policy11785

No transport/pins/services/actuator enable. These policies are not yet selected
by api1 or advertised by graph-shadow. Qualified test profiles are synthetic,
not statements about installed floor/mixer/relay hardware.

## Group water target

GroupWaterPolicy accepts qualified independent limits, optional explicit fallback,
fresh admitted outdoor and room error, and emitter-specific bounds. Interpolation
keeps centi-degree curve precision; bounded room correction is applied inside
group limits. The aggregate is the HIGHEST valid requesting group, not mean
temperature or estimated burner power. No demand yields null, not a permanent
minimum-water request. Unknown source/delivery/required correction produces none.

All configured floor profiles are checked, including a currently closed/inactive
floor valve. High central maximum requires qualified mixing, or a reviewed
shared-safe low maximum for the whole circuit. Independent floor/high cutouts and
required fresh floor sensor cannot be invented. A safety-inhibited group blocks
aggregate proposal; physically available alternative zones are not assumed to
provide a safe path. Conservative test capacity<=8groups is NOT E32capacity proof;
graph validator's existing one-floor subset/4096byte budget is unchanged.

WaterWriteBudget separates setpoint proposal from burner enable. Deadband,
minimum positive write interval and bounded centiC/min slew; stop/null bypasses
the positive budget. Backwards clock withdraws positive intent. No boiler protocol
encoder, physical flow or manufacturer safety is changed by a proposed target.

## Mixer reference and closed-loop intents

MixerPolicy source supports three-point and analog0–10V endpoint-calibrated
logical intents. Requires reviewed cold direction, travel/deadtime/write/feedback
budgets and independent limits. Reference movement additionally requires explicit
current reference-safe confirmation; it is NOT automatic onboarding on unknown
hardware. Fresh supply is required even during reference. End-switch feedback
must belong to the newly issued reference command and be strictly later.
A timed reference is only accepted for an explicitly validated timed profile;
its reason stays timed_reference, never physical end-switch proof.

Three-point warmer/colder intents never overlap. Reversal first emits neither,
waits configured deadtime, then the opposite intent. Maximum continuous travel
latches fault. Stale supply/adapter/limits withdraw; overtemperature/trip/backwards
time faults. No blind emergency cold/close action for an unknown installation.

Analog needs fresh qualified absolute-position feedback; endpoint voltages may
be inverted only via the reviewed profile. Rate/write bounds and one pending
position intent: no progression until later matching-command feedback within the
declared resolution. Missing ACK/position times out rather than assuming motion.
Reconnect invalidates reference/pending state. No default safe NC/NO/polarity.

These are INTENTS, not a guarantee an already in-flight remote service is
cancelled. Native actuator owner must still serialize, fence epochs/leases and
reconcile late completion before any physical readiness/boiler release.

## Evidence / remaining gates

26actual C++scenario tests PASS:15newgroup/mixer/strict post-command evidence
cases +11existingregulator/supervisor cases. Synthetic profiles/clock only.
Existing HydraulicSupervisor now also rejects same-tick/pre-command readiness
and flow, preserving physicalOutputsEnabled=false.

Still open: graph/profile/wire integration, actual device/controller/pump voltage
and NCNO/feedback qualification, E32 ABI/heap/NVS/timing/build and physical minimum
flow/powerloss/mixing/high-limit/floor commissioning. Existing generic legacy
heating curve was not rewritten. No active hardware/API2 capability added.
