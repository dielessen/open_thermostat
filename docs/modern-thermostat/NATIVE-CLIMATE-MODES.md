# Native HA room HEAT/OFF — same shadow controller

The existing climate entity now advertises HEAT/OFF and native turn-on/turn-off
features. A normal climate.set_hvac_mode service dispatches through the existing
runtime, single worker/ShadowClient, owned command Future and actual controller.
No second action service, local mode latch, stored command or device output.

OFF selects the existing off policy for only that room; HEAT sends existing auto,
returning to the configured automatic/schedule target, NOT resurrecting an old
temporary override/boost. Explicitly configured comfort uses its already
negotiated off/auto route and retains window/source/owner/limit constraints.
A missing comfort capability never falls back to the legacy command shape.

For non-comfort API1 the existing wire requires temperature/duration even for
off/auto. The valid configured base and60000ms placeholder satisfy that unchanged
shape; the controller ignores these fields for off/auto. No target/expiry or
minimum-on/off limit is reduced. SOURCE2 and default physical-output locks stay
unchanged; DATA-only graph support does not make these controls available.

HVAC mode is derived only from admitted firmware state. Before a state exists
it is unknown/unavailable, not an invented HEAT confirmation. ACK alone never
changes the displayed mode. HVACAction remains IDLE in shadow mode even when
simulated demand is true. HEAT can still be inhibited by a room window, missing
source, safety condition, min-off or owner loss; it is not a physical heating GO.

Two-room finite replay uses native HA2026.10.2 climate EntityPlatform/services
and the unchanged real C++ SOURCE2 controller peer. A/B/all-off/selected resume,
invalid mode, offline, actual ACK-withheld-state and boot-no-command-replay are
checked. Its existing immutable review is still preloaded by a SOURCE fixture:
this does not close the missing two-room API2 DATA writer/provisioning/GUI-apply.
The default SOURCE factory is still NONE. No actual producer or profile is
qualified by entity creation or successful synthetic replay.

The first prechange test fails because only HEAT was offered. The first real
service harness waited for all HA tasks before delivering the pending ACK and
was interrupted: fixed only by driving the same finite queues. The first offline
fixture disconnected only firmware, not the native HA MQTT callback; the latter
is now explicitly driven. Both failed/incomplete evidence sets are retained,
not reclassified as product failures or PASS.

Actual desktop/mobile frontend screenshots remain OPEN: this environment has
no Node/Chromium/hass_frontend/browser tool. Native service/entity proof is not
a source-browser or installed-HA/physical/performance acceptance claim.
Current-source composed image/license closure/resource/8zone/NVS-GC/duration
and all physical acceptance gates remain separate. No deployment/publication.

Reproduction: NATIVE-CLIMATE-MODES-RESULT.json binds source/evidence/patch.
verify-native-climate-modes.py uses only an exact-hash unchanged finite peer,
native and fully instrumented ASan/UBSan variants. External dynamic OpenSSL SHA
provider is not instrumented; cJSON/core/peer are, no GTest in this peer.
verify-native-climate-comfort.py rebuilds the current actual legacy/comfort peer
with strict host compiler for targeted compatibility cases, not a firmware image.

Rollback only this bounded source/doc/test commit before dependents. No
persistent configuration/journal/model/Recorder/history mutation or erase.
Parent alone integrates canonical WORKBOARD/PLAN; no physical commands performed.
