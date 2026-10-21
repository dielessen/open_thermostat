# Modern read-only metrics delivery / source11785

Same MQTT client, queue and modern shadow session: existing EmsMetrics provider is
now carried as fw/telemetry/ems_metrics, at most one <=2048B attempt every30s.
Only an admitted mapped live session may obtain/publish the fixed24-member V2
snapshot. Optional read_only_capabilities advertises metrics.observation_total.v2;
old peers omit it, no metrics entities. No extra connection, subscription, worker,
service or poller. Invalid/oversized/provider exceptions fail read-only, not control.

HA checks current boot/epoch/controller/config/binding/adapter/session/grant,
uint32 sequence/no retained/replay, exact schema and finite values. Foreign frames
are ignored; malformed current frames clear only metrics. A duplicate may not renew
receipt age or revive an expired value. Local45s snapshot expiry uses the EXISTING
2s runtime notification; unchanged polls don't rewrite native metric states.
This receipt age is NOT physical observation freshness. Metrics never renew
last_rx, grant, lease, sources or model qualification; control_qualified=false.

Native sensors reuse V2 IDs/decoder and same-entry-owned unavailable old aliases.
The existing optional dashboard is created only if opted in; disabled runtime has
no new listener/entities. Setup/unload failures clean up through existing lifecycle,
including when optional dashboard shutdown itself fails. Diagnostics contain only
support/availability/quality metadata, no raw session/grant/config/credentials.

## Verification and limits

28 actual C++ checks (4new +13wire +11admission),10 actual parser/metrics checks,
84 actual HA2026.10.2 checks (5 dependency deprecations, no skips),16 finite real
C++/native HA interop checks (2new+14preserved). Counts overlap previous stages.
Actual current main.cpp, ModernTransport, MQTT and controller type-check against
pinned Xtensa Arduino2.0.17/libraries PASS. Reused cached generated web assets for
that TYPE CHECK only; no current app link/image/asset build or board proof.
No HA frontend pixels, broker delivery/latency, phone, live EMS or performance claim.
Boot scope/estimates NOT meter totals. Raw boiler/requested-water/return/Classic
qualification and active graph/model/source/ESP resource gates stay OPEN.

## Independent pre-existing protocol finding — OPEN

GRANT-JITTER-PROBE.json reproduces readiness expiry with real C++/HA and ZERO
metric frames/provider: repeated2s firmware steps rotate5s grants at6s intervals,
while safe HA lower-bound extrapolation advances only5s. Old/current issuance and
HA deadline formula are byte-identical to93228ff. This is a pre-existing fail-closed
availability limitation, not excused as harness failure. Normal independent FW1s /
HA2s cadence tests pass, but no long-jitter acceptance is claimed. Next bounded
correction must use fresh request-nonce send-time proof; never receipt+10 renewal.

Rollback: reverse modern-metrics-only-core.patch/revert source commit before any
future deployment. No firmware/HA/broker/config/credential/EMS/Tado/actuator action.
