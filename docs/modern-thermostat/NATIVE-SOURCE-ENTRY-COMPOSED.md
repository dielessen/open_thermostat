# Native HA entry and SOURCE policy pairing — source candidate, not deployment

## Existing product route

The existing Home Assistant shadow integration entry and zone-subentry forms,
native ConfigEntries Store, NativeShadowConnection worker, ShadowClient journal,
firmware ShadowController/ControlStore and seasonal supervisor are reused.
There is no second scheduler, transport worker or policy controller.

The opt-in ControllerPolicySourceProfile is selected only by reviewed integration
SOURCE code. The default profile tuple is empty. A remote hello, config option,
GUI action or telemetry flag cannot select a profile. Its public logical digest
is an exact reviewed policy revision identifier, not an automatically calculated
attestation, authentication credential or physical capability.

A named firmware SeasonalControllerSource publishes its logical profile, owner,
config pin and explicit false physical/frost flags in hello and state. A selected
HA entry checks all these fields before opening or consuming state; the firmware
also checks the two profile/config echoes in the existing open_session request.
Missing, anonymous old SOURCE, unknown schema, wrong owner/controller/profile/pin
or physical-right claim cannot be upgraded into a matched session. Ordinary
API1 and anonymous old SOURCE retain their old request shape.

The selected config pin is checked before HA staging or sending a config and
again on exact fresh firmware readback. ACK alone is not apply/admission.
The existing grant/session/revision/mapping/lease/readback checks remain required.
Reconnect and a new boot require a new scoped session; cached observations or
old grants do not restore demand. The SOURCE identity is not a safety freshness
report and does not extend leases, temperatures or readiness.

The finite composed test uses two ordinary native zone subentries with different
targets (21 and 19 degrees C), native HA Store writes, the real worker/client,
and a freshly compiled actual C++ controller and real cJSON. Both bindings are
TRV C_unverified fixtures, NOT evidence for a floor valve, hydraulic profile,
hardware producer or installation. MQTT public IO and a bounded receiver clock
are test boundaries; platform forwarding is intercepted. No real broker, device,
HA deployment, NVS, flash, hardware feedback or physical outputs are tested.

Climate attributes expose transport_status and controller_policy_status, not
tokens or full source-profile digests. The states distinguish default_api1,
source_identity_unverified and source_identity_verified_shadow_only; the last is
logical identity matching only, never actuation admission.

## Important remaining product gaps

* Graph API2 is still DATA-only. A graph draft/apply/readback does not automatically
  become API1 control, a SOURCE controller profile or hydraulic permission.
  Graph DATA and controller-policy selection on the same transport are rejected.
* The actual E32 MQTT factory currently constructs ModernTransport with null
  SOURCE/profile arguments. Its existing constructor supports the reviewed
  seasonal route, but this candidate does NOT add a fictitious qualified
  installation bundle or safety producer and does NOT enable that route live.
  A real reviewed factory/provider selection and producer contract remain OPEN.
* A selected SOURCE uses the pre-existing exact immutable config pin. Unlike
  ordinary API1 reconfigure/reload (tested to revision 2), changed selected
  configurations, changing schedule snapshots or mappings need a newly reviewed
  matching pin. This restriction is not silently removed to make a GUI PASS.
* Two-room SOURCE control fixtures do not expand the currently distinct API2
  graph DATA contract, payload limits or eight-zone heap/NVS qualification.
* All physical flags remain false, defaults unselected, hydraulics unqualified.
  All fourteen enabled model candidates remain rejected/insufficient. No model
  benefit, floor/frost protection, hardware performance or physical acceptance
  is inferred from these tests.
* This source snapshot has not been built into a new normal release image.
  Preserved E32/S3 build receipts identify the older source 8b364f2, not this
  candidate. No released alpha.6 identity is relabelled.

Planning estimates, not commitments: once an actual reviewed producer contract
exists, bounded SOURCE factory/provider binding plus composed negatives is
roughly 2–4 engineering hours. A coherent multiroom API2 DATA-to-explicit-control
contract, lifecycle/migration/resource tests is roughly 4–8 hours, with material
uncertainty; profile pin/schedule evolution needs a separate bounded protocol
decision. Physical source qualification, actual feedback and heap/NVS/72-hour
evidence cannot be estimated or certified from this source harness.

## Native validator audit correction

Home Assistant 2026.10.2 actually requires probatio==0.13.0 and uses it for native
flow/config validation. The three existing imports are therefore retained.
No import alias, stub, injector, new dependency installation or manifest
requirement was added. Native legacy/shadow GUI serialization and actual
entry lifecycle tests run with the real installed distribution.

docs/third-party/native-ha-validator.json records the actual installed
distribution METADATA/RECORD hashes; the original MIT license is retained.
The audit only qualifies this exact pinned native test platform and fails closed
on missing/conflicting evidence or license bytes. Mark's installed production HA
resolution remains unknown. The earlier frozen Stage45 report is historical and
not rewritten: its 'unqualified probatio' item reflected missing audit evidence,
not a demonstrated bad import or live HA failure. Other SDK/source-offer/CA and
distribution gates remain BLOCKED.

## Review and rollback

Use the Stage46 immutable patch, archive, result and hash manifest in the shared
11774 dossier. Parent alone integrates canonical WORKBOARD/PLAN and performs the
independent normal image/resource review. Run the recorded finite native/HA
commands against the exact candidate; audit fixtures are not runtime evidence.
The sanitizer verifier may reuse the original hash-verified fully instrumented
GTest framework objects; changed controller/policy/cJSON are compiled anew.
--fresh-framework recompiles that unchanged framework on a suitable host.

Before dependent source changes, reverse only this bounded source commit/patch.
Do not reset any journal/config/model/Recorder data, credentials, live NVS or
device settings. No release, install, login, restart, physical output or heating
GO is included.
