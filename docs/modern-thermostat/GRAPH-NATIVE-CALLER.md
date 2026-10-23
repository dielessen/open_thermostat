> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Native reviewed graph -> SOURCE controller caller

This source-only increment completes the initial, explicitly SOURCE-selected
one-room handoff through the existing native HA entry/runtime/connection/client.
Normal graph options/review, native graph Store, exact accepted graph tuple,
current saved draft and registry bindings must all match a typed immutable SOURCE
bundle. The existing firmware GraphControlStoreView reads the same durable graph
key; the finite real C++ peer switches from graph owner to the EXISTING controller
without rewriting its durable bytes or running two owners.

The existing native control journal is only STAGED. ACK/graph_ready never admit
control; a fresh exact actual firmware snapshot must reconcile it. An unknown or
conflicting accepted journal/remote configuration is never overwritten/adopted.
Graph/config/registry drift across Store awaits rejects connection. Registry or
schedule changes fence the session and latch review-required across reconnect.
The normal proposal helper cannot publish API1 configuration in this read-only
SOURCE route. Default SOURCE tuples remain empty. No GUI flag creates authority.

Real native HA setup, one existing MQTT worker, native Store, climate commands,
unload/reload and the freshly compiled actual finite C++ owner/controller are
tested together. MQTT delivery/clock, platform forwarding and declared SOURCE
safety/report producers are test boundaries, NOT real broker/producer/hardware
qualification. A target within reviewed bounds changes logical intent; stop,
DHW, expired source and old replayed observations remain failclosed. All physical
outputs are false. Original graph durable bytes remain unchanged.

## Explicit remaining functional gaps

This is initial immutable reviewed configuration, NOT arbitrary graph editing
while controlling. Base/schedule/topology revision evolution must explicitly
replace reviewed SOURCE pins and reconcile an older accepted control journal.
The current implementation rejects mismatches instead of silently adopting them.
Mark11944 allows necessary bounded internal replacement for that next functional
step; old internal APIs/upstream compatibility are not preservation goals.
No restart of the project or parallel controller is intended.

The graph remains one-room; central/weather/group/mixer DATA is validated and
hash-pinned, not executed by the room projection. Two-zone SOURCE controller
tests are not multiroom graph execution. Actual supported report/safety producer,
factory binding and installation qualification remain absent/default NONE.
Normal user-selectable graph DATA does not select SOURCE, control, model, readiness
or actuator authority. Model/backend defaults remain disabled, all14 enabled F9
assessments remain rejected/insufficient.

## Evidence and next product work

74 native HA checks PASS:19new composed cases and55 affected regressions.
The same19new cases pass against fully ASan/UBSan/leak-instrumented actual finite
C++ peer and cJSON. External dynamic OpenSSL SHA provider is uninstrumented.
No GTest is used by this finite peer. No old61/83/85 suites repeated. Production
C++ is unchanged from Stage47; the newly compiled C++ delta is the finite peer.

Failed-before evidence preserves registry-loss reconnect reopening and forbidden
API1 proposal under this read-only SOURCE route. Both have targeted regressions.
Earlier fixture assumption17C vs stored21C and empty-native-Store normalization
failures are retained and distinguished from product faults.

Next: existing GUI polish with real browser source evidence, then bounded
reviewed config evolution and actual producer/factory integration as contracts
permit. Conditional engineering estimates (not a release commitment): GUI source
defect repair/check roughly2-4h if existing browser is available; reviewed revision
evolution/migration roughly4-8h after pin-ownership decision. Producer integration
cannot be estimated from synthetic fixtures before a supported contract exists.

No current full firmware image, actual NVS/heap/callgraph/8zone/GC/72h/physical
acceptance is proved. Saved source8b364f2 images and published alpha6 are not this
candidate. License/source-offer/production dependency closure remains BLOCKED;
generic-size has a separate exclusive owner and does not block E32 source work.
No live HA, device, broker, login, flash, configuration, EMS/TX/actuator or
publication action. Parent owns canonical PLAN/WORKBOARD. Whole PLAN in_progress.

## Reproduction / rollback

Use GRAPH-NATIVE-CALLER-RESULT.json and frozen source archive.
Run verify-graph-native-caller.py (default builds peers, --reuse-peers only after
hash checks), with the six tests listed in the result, and
verify-graph-native-caller-san.py. Independent source root can be selected with
OPENTHERMOSTAT_REVIEW_SOURCE. Package verifier checks patch/archive/evidence hashes.

Before dependents, reverse only this bounded commit/patch. Never delete or migrate
graph/control/config/model/Recorder/history data to make rollback pass. Reject
conflicting journals safely; preserve parent fixes, notices and canonical docs.
