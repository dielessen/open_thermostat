# Window and door contacts

Development target: E32 beta.6 and HA 0.4.0b4. This feature has not been installed
or physically qualified during the development work.

Select up to eight contacts in a room's normal editor or setup wizard. Only
explicitly selected contacts affect demand; discovering a door sensor does not
automatically pause a room. Opening/resume delays and maximum report age are
stored with the same room transaction. An open contact pauses demand. Resuming
requires every selected contact to report closed, within the configured age,
and completion of the closing delay. Unknown/restored/expired states do not
grant a closed baseline. A known open can still inhibit when another contact
is unavailable.

The editor and wizard resolve registry platform/unique-ID identities. Renames
follow the existing identity. Deletion/replacement, disabled entities and changed
device classes are checked again before final save. Removing contacts removes
their persisted bindings; old clients cannot erase fields they do not know.

For an active native plan, the existing authenticated save uses its current
worker, configuration journal, reload and exact controller readback. Logical
contact changes preserve the hardware source profile, mapping and room limits.
They do not enable physical outputs. The old lease must retire before the next
worker owns a session. A failed or ambiguous save retains the intended state
and reports the existing unconfirmed-save result, without automatic replay.

Ordinary rooms use a separate wire `contacts` record containing only
`maximum_age_ms`. It inhibits the existing target without selecting comfort,
away or frost modes. Existing opted-in comfort rooms can instead carry the
aggregate through their `comfort` record's `window_max_age_ms`. The two forms
are mutually exclusive. Both require the advertised `comfort.contacts.v1`
contract. Old graph projections that cannot represent this policy are refused
rather than silently ignoring the contacts. Existing independent frost and
installation policy checks remain in effect.

One owned HA transition timer per room completes an opening/closing delay even
if no new temperature arrives. Its callback forwards the original temperature
observation, with its original age and source ownership; the normal sender
rejects expired or withdrawn measurements. Reopening, rebind, disconnect and
unload cancel the old timer. Late cancelled callbacks cannot resume demand.
The C++ receiver independently expires context using its original received age
plus the existing conservative delivery envelope. A repeated packet cannot
renew a context deadline or clear an open contact.

The HA climate attributes and room card show open, closed, waiting or unknown
contact status. Reading these attributes does not renew reports or arm a new
transition. The new managed editor tag is v42 with a versioned resource URL; saved
older card types remain supported. The resource belongs to HA 0.4.0b4.

Software evidence is kept under `out/room-contacts-20261027/`: native HA setup,
storage, source/registry races, active-plan save/readback and real C++ packet
interop; desktop/mobile Dutch/English browser cases; C++ expiry/replay/config
tests and ASAN/UBSAN. These use isolated services and finite native peers.
Model-specific original-report qualification and real opening/closing,
availability, valve and boiler tests remain separate acceptance work.
