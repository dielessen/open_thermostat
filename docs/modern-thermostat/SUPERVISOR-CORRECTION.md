# Supervisor parentreview correction11785

Original CONTROL2285b8e was NOT independently accepted. Parent's own exact
pure-header probe41b8a6... proved two missing cases:
1. fresh readiness but never flow left pump_wait/pumpIntent true after1hour;
2. boilerfault withdrew heat AND immediately dropped the qualified prior
   path/pump intent instead of following an explicit fault/postrun policy.
Original evidence remains CONTROL-PARENT-REVIEW-PROBES.json; do not relabel it PASS.

## Corrected source contract

HydraulicProfile now additionally requires flowWaitDeadlineMs(1–600s) and explicit
withdrawal policy for EVERY cause: normalStop, sourceLost, adapterLost,
unknownSafety, DHWpriority, boilerFault, readinessLost, flowLost, limitTrip,
timingFault. Missing/invalid cause policy keeps advanced profile unqualified.
The current actual api1 default stays unqualified; no wire/schema/driver opt-in.

Policies: withdrawHeatOnly, retainExistingPath, retainExistingPathAndPump.
They describe LOGICAL intent retention, NOT universal close/deenergize/NCNO/
safe pump-position commands. Profile owner must qualify installation behavior,
independent postrun path and physical mapping. No synthetic setting is an
installed-hardware assertion.

- No-flow wait has its own deadline; total pumpwait is bounded by flowwait+
  pumpdelay+minimum-off. A late step timestamps timeout at its actual deadline,
  not detection time, so a1hour gap cannot create a fresh postrun after expiry.
- Heat and water target withdraw immediately on fault. Only a path/pump that
  was ALREADY requested can be retained; a fault never starts a new pump.
  Path type explicitly distinguishes a new qualified-path request from
  retaining an existing path. False/none is no universal valve-close command.
- First withdrawal timestamp bounds ALL repeated/escalated faults. Additional/
  simultaneous loss policies can only restrict retention, never extend or
  resurrect it. Boilerfault, stale readiness, flow/limit/adapter loss are distinct.
- Fault stays latched after inputs recover. verified clear is necessary but
  cannot cancel remaining mandatory postrun/minimum-off or re-use old opening
  feedback; a new opening generation still needs fresh post-command evidence.
- Transport invalidate records adapter-loss withdrawal rather than discarding
  prior reviewed retention. Physical outputs are ALWAYS false.

## Evidence

CONTROL-CORRECTION-NATIVE.json:50actual C++checks (11newcorrection scenarios,
26emitter/regulator/supervisor scenarios and13actual ShadowController runtime).
Counts overlap earlier package checks; do not add them as independent full suites.
Exact parent sequences reproduced with explicit NEW synthetic policy fields in
SUPERVISOR-CORRECTED-PROBE.json:1hour noflow fault/pump0/heat0; boilerfault
heat0/open1/pump1 during the configured bounded qualified postrun.
No generic hardware safe-position/flow/pump claim. Physical commissioning and
normal firmware build/resource/driver/graph integration stay open.

Apply choices: control-correction-only-core.patch after earlier specialist
control+emitter source, OR control-corrected-rollup-core.patch in place of the
unaccepted CONTROL2285b8e. Then emitter-after-control-correction-core.patch for
GroupWaterPolicy/MixerPolicy/updated synthetic fixture without duplicate headerhunk.
Preserve parent's independent F5/GUI/canonical docs. Source only, no live actions.
