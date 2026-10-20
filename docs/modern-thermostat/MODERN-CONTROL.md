# Modern control — bounded source increment11785

Pure ZoneRegulator and HydraulicSupervisor, no hardware/network callbacks.
Actual existing ShadowController uses the regulator in baseline hysteresis mode
and reports unqualified hydraulic inhibition. All physical output flags stay false.
Current api1 config has NO way to self-qualify or enable the other profiles.

## Zone policy

Hysteresis/local-TRV retain the existing ±0.2C baseline (configurable in the pure
profile). Local-TRV mode is not a second direct-valve PI loop.
Direct PI retains fractional integral between ticks, clamps/antiwindup at both
saturation limits. Stale/missing source, unavailable delivery (including DHW
inhibit supplied by owner), control-generation change, backwards/long clock gap
reset control memory. Targets5..35C and finite integer input bounds are enforced.
Slow binary PI requires10–60min cycle and >=2min on/off; short pulses are suppressed,
not rounded into a minimum demand. Source/off inhibition always beats minimum-on.
Future owner must rotate generation on source/override/model discontinuity.

## Hydraulic shadow policy

Caller-owned reviewed profile requires independent limits and validated postrun
path, bounded opening/feedback/pump/postrun/minoff timers and water limits. Default
profile is unqualified. It cannot be enabled by observed valve position or a GUI
checkbox. No NC/NO/polarity/safe-actuation assumptions are selected.

An opening command generation needs fresh matching-command readiness after open.
Readiness is NOT independent flow confirmation. Both fresh evidence paths,
pump delay and minimum-off must hold before heatIntent. This is a logical shadow
intent, never a permitted EMS/GPIO/service command. Invalid water target, stop,
DHW/unknown DHW, source/adapter/fault-state/limits unknown immediately withdraw heat.
Only a qualified postrun-path intent may remain bounded. Opening timeout,
lost ready/flow, explicit limit trip/boiler/actuator fault latch; recovery is explicit
after verified cause clearance. Backwards time latches; reconnect invalidates.
Actual hardware stop/pump/valve behavior is still an independent commissioning gate,
not universally implied by a pumpIntent/openPathIntent from synthetic scenarios.

ShadowController keeps the same actual source/session/lease/revision checks,
never advertises api2 or new wire output capabilities. Existing zone demand
is unchanged in its baseline band; reconnect also resets regulator memory.
A new additive supervisor status explains hydraulic_profile_unqualified separately
from requested_heat. No claimed flow/readiness or accepted safety evidence.

## Acceptance

CONTROL-NATIVE.json contains actual pinned cJSON + actual ShadowController and
new deterministic zone/supervisor scenarios. API1 cross-language receiver tolerates
the additive status; physical output fields remain false. No ESP32 ABI/resource/
timing/build/install, supported physical profile, actuator path or heating GO.
Regulator/qualified hydraulic configurations are source test profiles only;
future reviewed graph/wire/profile integration must explicitly select them.

Still open within F4/F6/F8: group weather aggregation and limits, actual profile
qualification/admission, floor/mixer controllers and feedback, installation-
specific frost/failure policy, physical stop/minimum-flow/powerloss acceptance.
