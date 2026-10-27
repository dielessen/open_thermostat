# Manual room target helper

Prepared for E32 beta.6 and HA 0.4.0b4; not published or installed.

Select an existing Home Assistant **Number helper** (`input_number`) with an
explicit °C or °F unit in the room editor or the room wizard's advanced options.
Choose an override duration from one minute to twelve hours. Saving binds its
registry identity; it does not apply the helper's current value. An active native
installation uses the existing save/reload/controller-readback transaction.

A subsequent direct authenticated user change requests one temporary room target.
The room's temperature observation remains independent. The controller applies its
existing bounds, window/contact inhibition and finite override policy. Its state
reports the remaining override duration; the helper is never written back.
When the duration ends, the normal programme resumes even if the helper still
shows the last manually chosen value.

Only the built-in Home Assistant `input_number` platform is supported by this
route. A native state-change event must carry a direct user context without an
automation parent, match the current state and selected registry identity, and be
less than five seconds old. Startup/restored values, cached reads, numeric-format
echoes, automated changes and repeated event contexts cannot create or renew an
override. Celsius values must have centidegree precision; Fahrenheit values use
explicit conversion. Values outside the room's configured bounds are rejected,
not clipped.

Each room owns one task and one latest unsent intent. New manual changes may
replace an unsent intent while an earlier command is awaiting its result. Registry
identity, owner generation, transport, original age and current state are checked
again immediately before dispatch. Offline, withdrawn or uncertain requests are
not replayed when the connection returns. The existing wire client retains its
bounded identical-byte retry and controller admission/deduplication contract.

One helper may belong to one room only. A missing helper does not withdraw the
room temperature or silently replace the ordinary room programme. Removing a
binding cancels its listeners and pending task during the normal reload. Older
editor clients preserve bindings they cannot edit. Older firmware without
`control.manual_target.v1` is rejected before saving a new active helper binding
or sending a configuration for an already-bound helper.

The room status distinguishes awaiting a manual change, pending, accepted,
unconfirmed, withdrawn and unavailable. “Accepted” means the controller protocol
accepted the request; it does not confirm a physical valve or boiler action.
The displayed countdown comes from controller state, not a new browser timer or
polling endpoint. Unavailable controller state does not display a stale countdown.

Native Home Assistant tests include an actual built-in helper service call with
an authenticated user. Separate interoperability tests exercise the real C++
controller's expiry, replay rejection, contact inhibition, capability check and
native source/readback preservation. Browser fixtures use the shipped editor in
English and Dutch at desktop and mobile widths. None connects to the live E32,
boiler, valves or Home Assistant installation.

This helper is a distinct manual UI source. Physical Zigbee/Wi-Fi wall controls
still need model-specific original-action provenance and echo classification;
they are not qualified by a cached entity value or by this helper feature.
