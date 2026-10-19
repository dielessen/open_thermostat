# v1 shadow-test wire — implementation target

This is the concrete first integrated test profile, not authorization for boiler
or real actuator operation. E32-only feature: existing generic 4MB partition has
insufficient headroom; do not enlarge its partition or silently enable features.
Eight logical zones maximum, 8192 bytes/512 JSON nodes per complete message,
4096 bytes persisted configuration maximum. Native NVS is20KiB: network settings
are bounded to2048bytes separately, leaving space for old/new control blobs and
GC/other native keys; actual maximum-update/powerloss proof remains a bench check.
The existing 128-transition per-zone
limit remains subject to the **total** message budget. Reject oversize, never truncate.

Transport: same broker, official PubSubClient 2.8 API, single modern connection
instead of concurrent legacy MQTT. No dependency patch. QoS0 + application ack;
native loop, bounded retry, reconnect handshake and own monotone timers. Broker
credentials/ACL required for controlled bench; protocol nonces are not auth.
No HA entity IDs/names/services on wire. Wire ASCII, no escapes. Config consists
only of integer numbers, booleans, null, IDs and the existing schedule document.

All topics are `<base>/v1/<suffix>`. Firmware outputs never cause real actuation
in `shadow` mode. `fw/state/zones` explicitly says `boiler_output_enabled:false`
and `actuator_output_enabled:false`; computed demand is **simulated**, not heating.

## Boot and session

`fw/hello` non-retained every 3s: `api:1,controller_id,boot_id,epoch,challenge_id,
config_revision,config_digest,mode:"shadow",lease_ms:15000,grant_ms:10000`.
Controller ID comes from chip MAC; boot/session/challenge from ESP random.
Reconnect increments epoch, invalidates session/samples/overrides/readiness.
Challenge validity is 10000ms on receiver's clock. Rotate on open/expiry.

`ha/open_session` non-retained exact fields: `api,controller_id,boot_id,epoch,
challenge_id,adapter_id,client_nonce,known_revision,known_digest`.
Adapter must match locally provisioned owner; one owner, no implicit takeover.
Known revision/digest mismatch allows diagnosis/config-reconciliation only,
not observations/user commands. Initial empty digest is `""`, revision 0.

`fw/session` non-retained: `api,controller_id,boot_id,epoch,adapter_id,
adapter_session_id,client_nonce,grant_id,grant_sequence,grant_ms:10000,
config_revision,config_digest,mapping_ready`.
Rotate receiver grant every 5s (new ID/increasing sequence), same session and
sequence high-water marks. A repeated exact open request gets the same session
without resetting sequence or lease. A fresh open needs the current challenge;
an active owner session is not silently replaced. Restart waits lease expiry.

Common envelope for admitted messages: `api,controller_id,boot_id,epoch,
adapter_id,adapter_session_id,grant_id,grant_sequence,config_revision,
binding_id,sequence` plus body below. All nonzero counters uint32, IDs `[A-Za-z0-9_-]{1,32}`;
zone IDs exactly 8 lowercase hex. Payload SHA256 binds exact complete message bytes
for duplicate detection. Do not change a retry's bytes or sequence. Retried old
grants may reject; read state, never assume an unacknowledged mutation failed.

- `ha/heartbeat`: binding `adapter`, no extra fields. Only newly admitted sequence
  refreshes adapter lease; no sensor-age refresh. Session starts without lease.
- `ha/config`: binding `config`, extra `expected_revision,config_digest,config`.
  Atomic set/ack, NOT separate prepare/commit. Full immutable HA mapping must be
  durably staged before send. Expected=current and candidate=current+1.
  Config SHA256 = UTF8 `json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=True)`;
  all numbers in config integers, keys lexically sorted recursively. Firmware
  verifies this serialization; no JS floating/ordering ambiguity allowed.
  Firmware uses one NVS blob + native commit, reads back/validates before activation.
  On ambiguity/failure invalidate session, block all normal demand until reboot
  and readback. No partial activation. Successful commit invalidates session and
  all samples/overrides; new hello/session with exact revision+digest required.
- `ha/observations`: binding configured sensor ID, extra `zone_id,
  source_available` bool, `temperature_c` numeric, `source_sample_age_ms` integer,
  `evidence` (`physical_report|validated_integration_report|unverified|restored`).
  Only configured report evidence accepted; add grant elapsed to sample age.
  Cache read/timer retransmission cannot synthesize a new physical observation.
- `ha/user_command`: binding zone ID, extra `mode` (`temporary|off|auto`),
  `temperature_centi_c` integer500..3500, `duration_ms` integer60000..43200000.
  Values still required for off/auto but ignored. Temporary deadline set once.
- `ha/snapshot_request`: binding `snapshot`, no body. Admitted lease required.

`fw/config_result` / `fw/user_command_result` / `fw/observation_result` responses:
`api,boot_id,epoch,adapter_session_id,binding_id,sequence,status,
config_revision,config_digest`. Accepted duplicate has `status:"duplicate"`;
original effect/deadline never reapplied. Config accepted response says `applied`.
Invalid messages have no effect; no echo of arbitrary raw input/secrets.

`fw/config_snapshot`: `api,controller_id,boot_id,config_revision,config_digest,config`.
`fw/state/zones` nonretained every 3s: identity/revision/digest + `mode:"shadow"`,
`adapter_alive`, both output-enabled flags false, and `zones` list with `zone_id,
temperature_centi_c` (nullable), `target_centi_c` (nullable), `sample_age_ms`
(nullable), `sample_state`, `target_source`, `demand` bool, `reason`.
`demand` is hysteresis simulation; stale source, no session, config mismatch,
expired/invalid scheduled time or off gives no normal demand.
No raw firmware/HA actor command topic in shadow profile: HA executor must be
separately explicitly enabled for a later TRV-only bench with no boiler.

## Configuration schema

Exact root keys: `mapping_digest` 64lowercasehex, `mode:"shadow"`, `revision`
nonzero uint32, `schema:1`, `zones` array0..8. Empty array safely removes all zones.
Exact zone keys: `actuator_id` ID or empty, `base_centi_c`500..3500,
`max_age_ms`1000..86400000, `report_evidence` `physical_report|validated_integration_report`,
`schedule` null or existing ScheduleDocument, `sensor_id` ID, `zone_id`8hex.
Sensor, zone and nonempty actuator identities are unique globally. Reject unknown
keys, unsupported modes/profile flags, duplicate IDs, unbounded age or schedule.
`mapping_digest` binds all HA-only entity/profile/source qualification settings.
Temperature is bounded -20..60C in this first **room** profile; outside-source and
full water-supervisor are not smuggled into the same profile.

## Integration acceptance target

GUI create/edit/remove bindings without YAML; preserve zone IDs/legacy writer
exclusion; native lifecycle cleanup; durable mapping/readback conflicts; same
shared fixtures consumed by actual firmware parser and HA client; broker-loop
offline integration smoke; malformed/replay/config-loss/restart/stale-source
checks. Production HA remains unchanged. Physical tests come afterwards.
