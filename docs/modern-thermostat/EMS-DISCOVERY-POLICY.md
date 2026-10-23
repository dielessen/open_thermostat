# EMS discovery and boiler profiles / EMS-uitlezing en ketelprofielen

## English

Read policy: **all available boiler data, independent of the selected model**.
Choosing a boiler changes its presentation and records observed capabilities; it
must never restrict reception, decoding or discovery to that model's field list.
A replacement boiler may expose additional fields. Those fields must remain
eligible for decoding and publication without first editing its display profile.

The current implementation has 69 fixed Classic field definitions and a separate
legacy Plus decoder. This is the current decoder coverage, not an upper limit on
what EMS boilers can expose. Existing field IDs, units, scaling and freshness
contracts remain stable; new families/fields need explicit decoder and transport
support. We cannot claim every possible EMS entity is decoded today.

All received boiler-report types enter the passive message inventory, including
unknown types. That inventory is bounded and currently retains metadata, not raw
payloads; overflow is reported. Unknown messages stay identifiable as undecoded,
not silently converted into invented sensors. Decoding continues even when the
inventory is full. Missing observations do not prove a field is unsupported.

A model profile records evidence for each field: reported, derived, unreliable,
stale or not yet observed, with unit, source, observation window and quality.
Explicitly observed zero is valid. Cached HA availability or an unchanged state
alone does not prove a new physical sample. Profiles do not turn inferred/raw
signals into independently verified flame, flow or delivered heat.

Receiving and actively querying are separate. A read query still transmits onto
the bus; no automatic polling, new bus owner or write is enabled by model choice
or by this monitoring request. Passive observation continues alongside the
existing thermostat. The current transmit restrictions stay in force.

The control layer should expose common heating functions (demand, water target,
stop), with family/device-specific telegram adapters and qualification. The
current Classic and Plus implementations already use different telegram formats.
Receiving fields is not evidence that identical commands work on every boiler.
Previously observed capabilities are scoped to the actual installation and
observation window; connecting another boiler must not inherit control approval.

## Nederlands

**Alle beschikbare ketelgegevens uitlezen, onafhankelijk van het gekozen model.**
Een ketelprofiel beschrijft de waargenomen mogelijkheden en de weergave; het is
geen filter voor ontvangst, decodering of nieuwe entiteiten. Een andere ketel
kan extra velden leveren. De huidige 69 Classic-definities zijn decoderdekking,
geen maximum voor toekomstige ketels. Bestaande veld-ID’s blijven behouden.

Onbekende berichttypen blijven zichtbaar in het begrensde berichtoverzicht;
volloop wordt gemeld en stopt de decodering niet. De huidige inventaris bewaart
metadata, geen ruwe payloads. Zonder decoder wordt geen sensorwaarde verzonnen.
Niet waargenomen betekent niet automatisch niet ondersteund. Waarden worden per
veld beoordeeld op bron, eenheid, versheid en kwaliteit. Een gemeten nul blijft
nul; afgeleide/onbetrouwbare signalen blijven als zodanig herkenbaar.

Passief ontvangen en actief opvragen blijven apart: ook een leesverzoek zendt
op de bus. De modelkeuze of monitoring schakelt geen polling of ketelaansturing
in. De hoofdfuncties voor regeling zijn gemeenschappelijk; de telegramvertaling
en bewezen ondersteuning horen bij de EMS-variant en installatie. Een andere
ketel krijgt nooit automatisch de regelvrijgave van de vorige ketel.

The current observation assignment and its local receipts are tracked in
`out/ecomline-observation-20261024/`; private installation data stays outside the
public repository. Future observations can extend the personal profile without
changing the model-independent read policy.
