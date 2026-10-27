# Selected device batteries in the room editor

Prepared for HA 0.4.0b4 / E32 beta.6. Open **Advanced settings → Batteries when
loaded** in the normal room editor. The view groups the saved temperature sensor
and valves by their native Home Assistant device and shows each device once.

The percentage and the device's low-battery binary sensor are separate values.
A percentage does not override the device's own flag or imply a universal warning
threshold. Each usable value includes the original HA report timestamp in UTC
and its age when the room was loaded. Reports at least 24 hours old remain
visible with an explicit old-report label. Missing, disabled, ambiguous, restored,
unavailable, invalid and future-dated values remain unknown. A genuine zero is
shown as zero. Voltage is never converted into an invented percentage.

This is a snapshot of HA's cached state, using `State.last_reported`. An upstream
integration can report an unchanged cached value; that is not proof of a new
hardware acquisition. These fields never establish measurement qualification,
actuator readiness, a target, a grant or any physical control authority. No
notification, replacement claim or automatic action is inferred from them.

Use **Reload** for a new snapshot. Changing the selected sensor or valves hides
the old device readout until those changes are saved or discarded. Ordinary HA
state updates do not replace values in the frozen snapshot, trigger another
request, or rebuild its unchanged DOM. Existing views remain usable with an
older backend that lacks this optional data.

The backend resolves saved platform/unique identities, including native entity
renames. Reusing an old entity ID does not adopt another device. Battery candidates
must belong to the selected native device and the selected integration/config
entry owner. Friendly names do not associate sources. Multiple enabled candidates
of the same kind are ambiguous; disabled alternatives do not replace an enabled
source. The view creates no duplicate HA entities, MQTT subscriptions, tasks,
Store entries or hardware requests. One registry pass produces at most nine
device rows with bounded candidate storage. Reading does not alter the room,
programme, source descriptor or HA report timestamp.

Native HA tests cover identities, ownership, duplicate devices, unknown/zero,
units, ages, disabled entities, raw-attribute exclusion and normal room-model
purity. Browser fixtures cover English/Dutch at 1280, 390 and 320 pixels, native
state updates without refresh/rebuild, explicit reload, draft binding changes,
invalid optional payloads and literal rendering of device labels. Fixtures do
not establish physical battery reporting. Model-specific source qualification,
low-battery notifications and real-device acceptance remain separate work.
