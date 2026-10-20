# Explicit metric-definition V2 cutover —11785 SOURCE correction

## Why same-ID schema checks were insufficient

Pinned HA2026.10.2 sensor/recorder.py732–742 takes a statistic ID's prior state/sum
as starting point,806–824 adds deltas. New counter meanings at that same ID do
not start a clean series. Stage10 only hid charts/raised Repairs; that did NOT
isolate background sums. This is a real source design-gap correction.
No actual home-history contamination was queried or claimed; neither source
package was installed. There is no DB repair/erase disguised as a migration.

## Definition boundary in BOTH producers and consumers

New numeric JSON names append V2, native HA/Discovery unique IDs append _v2,
names explicitly say definitionv2. Require metricsSchema integer2 and exact
counterDefinition observation-total-v2. Old fields are explicitlynull forever,
not missing (maintained retained Discovery falls back to0 when a field is
missing!), not aliases to new totals. Real native HA Template+MQTTSensor null
conversion tested: retained old template -> None/unknown, new realzero ->0.

Fields: totalEnergyUsedKwhV2, heatingEnergyUsedKwhV2,
warmWaterEnergyUsedKwhV2, unattributedEnergyUsedKwhV2, warmWaterUsageV2,
warmWaterAvgFlowV2, warmWaterFlowV2, observedBurnerSecondsV2.
Source/counter scope and estimate labels unchanged; Plus only, no independent
flame/heat/gas meter. Outdoor and raw boiler status identity unchanged.
Actual firmware JSON test parses all old names asnull, checks new independently
expected totals/flow and explicit metric payload<1024bytes.

Custom integration creates new versioned sensors. ONLY existing legacy registry
IDs owned by this same config entry get unavailable/no-statistics diagnostic
aliases; existing IDs/history are not deleted/reassigned. Fresh setup creates
no legacy aliases. Native persistent migration guidance tells users how to
select the clearly named new entities in their own cards. User dashboards are
not edited; no history is backfilled/rewritten/retained-old-Discovery deleted.
An explicit future user entity rename to a historical statistic ID is not an
automatic migration and must still respect historical definitions.

All counter aggregate charts use registered _v2 IDs only, with separate energy,
volume and reported-flame-time unit charts. CSV labels distinguish new isolated
definition from unversioned history. Native old-schema receipt guidance remains,
but no absent receipt is called clean historical data. Device classes/units and
realzero/nonfinite/negative/unknown protections are retained.

## Compatibility / deployment / rollback

New HA source with old firmware gives unknown V2metrics, never relabeled old
deltas; room/status/outdoor behavior remains separate. New firmware old consumers
see explicitnull old counters, not a cumulative total misread as a delta.
New source on both ends yields versioned counters. No release/update or actual
production config/device/broker/DB action occurs in this increment.

Rollback is SOURCE-only reverse metrics-v2-only-core.patch before deployment.
After any future real deployment, numeric-definition history MUST NOT be
silently collapsed into old IDs; preserve both namespaces/history and follow a
separate reviewed compatibility/cutover decision. No factory/config reset.
No legacy data rollback is necessary here because no runtime data changed.

## Evidence / open product gates

verify-metrics-v2-native.py:actual parser/EmsMetrics JSON and preserved integration/
GET/TTL/flow tests. verify-metrics-v2-ha.py:actual native registry/HubMetric handler,
migration/foreign-entry fences, native Template+MQTT null method, native cards,
admin export/Repairs and actual temporary diskSQLite old/new histories.
MQTT subscription and entity-add boundary are deliberately intercepted for handler
tests; finite source tests, NOT live broker/installed device/visual proof.
Original stage10 source2fb independently reproduced in stage10-frozen checkout;
V2 has distinct METRICS-V2-* evidence and source manifests.

Open: independent parent review, exact firmware/native/full CI target matrix,
active shadow telemetry/platform owner, actual Lovelace/phone visual and real
retention/DBgrowth/timing/counter commissioning. No performance/heating claim.
