# Slow curve-knot adaptation — source11785

CurveAdaptation uses GroupWaterProfile/groupWaterTarget, LearningMode and existing
ControlStore; no second target algorithm, MQTT client, service or live factory.
Defaultdisabled/frozen/shadow/reset; modelsQualified defaultfalse, only from SAME
reviewed graph/model owner/binding generation, not API input. No active caller,
profile advertisement/parameter adoption/GUI/NVSkey or physical output.

A fixed2..8 zone/source quorum with distinct declared IDs and exact mapping. Real
binding digest must additionally cover canonical physical entity/provenance identity,
not trust32-bit labels alone. Every contributing room needs NEW admitted report,
fresh bounded source age, verified delivery/readiness and normal automatic operation.
No single stubborn/outlier/missing zone drives the group: bounded inter-zone error
spread and persistent ALL-zone consensus; no global mean room temperature.
Outside has separate admitted report sequence and age: unchanged report/value may
age but never reset its age on a cache read. New room data cannot rejuvenate weather.
DHW/fault/window/manual/gain/limits/tracking/target/config/clock/gap/temperature-jump
loss aborts window, invalidates fresh qualification, preserves replay fences.

Existing groupWaterTarget validates actual expected curve+roomcorrection/floor
sensor/independentcutout. Requested water must equal OWN group target, reported water
must track it within reviewed tolerance: another group dominating water is not
training evidence for this group's curve. No burner/modulation-to-power inference.
Complete >=4h steady qualified windows,16max; >=6windows/6days/14span, >=10C weather
span and>=3comparable periods. After admission/mode reset even frozen mode requires
one complete fresh window; walltime alone never qualifies. No home fortnight claim.

Only ONE observed INTERIOR9point knot moves by reviewed1..25centiC (<=0.25C).
Both neighboring outdoor knot regions must have evidence, all affected comparable
weather periods agree direction. No global offset/slope extrapolated from one
weatherpoint. Reject hard/group/floor/monotonic limit, never clip/adapt past safety.
Old/new arrays, window range and coverage visible in advice. Repeated advice is
idempotent against immutable old curve, cannot accumulate updates. Eventual adoption
must be an atomic NEW reviewed config/model binding with previous approved config
retained; no accept/apply API exists here. This is not automatic deployed adaptation.

CurveModelStore bounded412B, algorithm/binding/EXACT basecurve, real SHA integrity
(not authentication), explicit>=30min checkpoint, exact durable precondition/readback,
ambiguous failure latchesdisabled/no blind retry. Signed error roundtrip tested.
Reset only durable after successful checkpoint; no automatic model key allocation.
All-model/8zone NVS GC/stack/heap budget remains OPEN, no unlimited support advert.

Verification:32actualGCC checks=17newcurve/store+15existinggroup/mixer/hydraulic.
Same32 ASan/UBSan actual model/test TUs PASS (real GTest framework uninstrumented).
Pinned Xtensa/Arduino2.0.17 actual new observe/propose/checkpoint methods compile
to object PASS, real target model1016B/snapshot372B/codecmax412B; per-function
propose224B/checkpoint496B estimates, not full callgraph/8zone/loop/NVS proof.
No full firmware link, real-time historical/baseline replay, broker/device/phone,
physical comfort or savings claim. Parent independent review pending.
Run sequentially: python3 verify-curve-native.py; python3 verify-curve-sanitizer.py;
python3 verify-curve-e32-object.py. Rollback reverse curve-only-core.patch/revert
source commit before deployment. No runtime/HA/broker/EMS/Tado/device action.
