# HA 0.4.0b10 — one place for rooms, a clean dashboard and far fewer entities
<!-- user-release-notes:v2:en -->

Companion release for E32 beta18. Install both together.

## New

- **Rooms are set up in Home Assistant**: Settings → Devices & services →
  OpenThermostat → Configure → Rooms. Add, change or remove rooms, choose their
  temperature sources from your Home Assistant entities and the E32's
  Bluetooth sensors, the target, limits and a simple week program such as
  `mon-fri: 06:30 20.5, 22:30 19`. The plan is stored on the E32, so heating
  keeps running without Home Assistant.
- **°F and °C**: with Home Assistant in °F the room editor shows and accepts
  °F; sources in °F or K are converted to °C for the E32.
- **Flow temperature limits** (Configure → Rooms): the lowest and highest flow
  the E32 may ask for, with a warning for floor heating above 50 °C and above
  the boiler's own maximum heating temperature, which always stays the
  ceiling.
- **Heating dashboard**: per room the temperature, target, mode and "off
  until"; the E32 boiler request next to your thermostat's; boiler essentials;
  Bluetooth sensors; heating advice; and a short "How it works" card. English
  or Dutch.
- **Each E32 room and Bluetooth sensor is its own device**, with plain names
  ("Temperature", "Heat demand"). Existing entity IDs and history stay.
- **Shadow comparison sensors**: heating time and burner starts today for the
  E32 and the thermostat, and their agreement. They appear only once a
  thermostat to compare with is seen on the boiler bus.
- **Burner short cycling** warning and burner starts in the last hour.
- **Heating problem**: one yes/no sensor for "is my heating OK?", on only for
  real problems held long enough (a room without measurement for 30 minutes,
  no E32 report for 10 minutes, low or high water pressure, short cycling for
  2 hours). Its attributes list the reasons for your own notifications.
- **Heating advice** sensor (advice only, never changes a setting): short
  cycling, a maximum heating temperature far above what the house needs, a
  return too warm for condensing, the flow your rooms really need, night
  setback, hot-water temperature, water pressure. Each item says what was
  seen, why it matters, what to change and where, with its confidence.
- **Energy and outdoor temperature** (Configure → Energy and outdoor
  temperature): optionally a gas meter (m³ or kWh), a gas price sensor or fixed
  price, the calorific value, an outdoor temperature sensor or weather entity,
  and your boiler power. Without them the advice still works, with rougher
  estimates.
- **Learning per room**: learning status, recommended flow and predicted
  heating start from the E32, plus hot water today.
- Week programs compiled by Home Assistant accept any IANA time zone.
- The E32 address may be a local host name such as `e32.fritz.box`,
  `e32.home.arpa`, `e32.local` or `e32.lan`, as long as it resolves to a local
  address.
- Every setup step and field explains in plain language what it does; all
  boiler values have English and Dutch names; icons for all entities.

## Fixed

- Far fewer entities: boiler values are created only once the boiler really
  reports them, and old duplicate or never-reported entities of this
  integration are removed (history is kept; entities you renamed or changed
  stay).
- Only one room menu is shown when the E32 has a room plan.

## Updating

Install the matching integration package, keep existing entries and restart
HA. Use it with E32 beta18. Entities of other integrations (for example old
EMS-ESP or MQTT devices) are never removed automatically.

## Limitations

The heat request is shadow-only; the advice is advice only. EMS Classic boilers
only; EMS+ is planned. E32 beta18 accepts a maximum flow up to 80 °C, never
above the boiler's own maximum heating temperature. The old HA room records
still exist for existing installations; the E32 heating control uses the E32
room plan.

# HA 0.4.0b9 — E32 rooms and Bluetooth sensors, firmware updates and the heat request
<!-- user-release-notes:v2:en -->

Companion release for E32 beta17. Install both together. HA0.4.0b8 was not
published; its changes are part of this release.

## New

- **Rooms from the E32 in Home Assistant**: per room the measured temperature,
  the active setpoint, the control status with its leading source, and the
  heat demand.
- **Operate rooms from Home Assistant**: room state (active or inactive),
  "inactive until" and the fallback setpoint. HA writes the E32 room plan with
  its revision; when the E32 page changed it in between, HA reads it again and
  applies just your change.
- **Bluetooth sensors of the E32** appear as temperature, humidity and battery
  sensors. They stay paired on the E32, so heating keeps working without HA.
- **E32 firmware updates in Home Assistant**, like ESPHome: an update entity
  checks GitHub every six hours, verifies the download and uploads it to the
  E32 over the local network, then confirms the new version.
- **Heat request** sensor: the flow temperature the E32 calculates (0 when it
  does not ask for heat). In beta17 the E32 only reports it (shadow mode).
- HA forwards the entities the E32 rooms read (for example the tado) to the
  E32, on every change and every five minutes.
- One table for all EMS entities: the thermostat, maintenance and EMS+ values
  arrive over the boiler-fields route and appear as entities.

## Fixed

- The room editor keeps its open advanced and comfort sections when it redraws.
- Unloading a product entry now also unloads its update entity.

## Updating

Install the matching integration package, keep existing entries, storage and
resources, validate the configuration and restart HA. Use it with E32 beta17.
Room operation needs the controller address and password of the connection
step.

## Limitations

The heat request is shadow-only. New rooms and their sources are added on the
E32 page "Rooms and heating"; the HA room editor for TRV rooms is not used by
the E32 heating control yet.

# HA 0.4.0b7 — requested boiler temperature over native MQTT, tidier entities
<!-- user-release-notes:v2:en -->

Companion release for E32 beta10.

## New

- Read **E32 requested flow temperature** from the native firmware topic
  `v1/fw/telemetry/controller_request`, using native availability. A live
  packet also proves the board is online after an HA-only restart.
- Hide boiler fields this boiler never reports: after15 minutes of a valid
  observed-field stream, unreported fields are disabled by the integration.
  Fields that are unreliable by default, or that you disabled yourself, are
  left alone. A field that appears later is enabled again; HA then reloads the
  integration.

## Fixed

- The requested-temperature entity now appears with modern-mode firmware.
  HA0.4.0b6 subscribed to a legacy topic that such firmware never sends.
- A repeated request with the same value (for example50°C every minute) now
  updates the entity's age and sequence instead of looking frozen.
- Legacy hub entities that a modern-mode E32 never feeds (DHW status, boiler
  states, hub connection, RTC temperature) are disabled instead of staying
  unavailable forever. Records are disabled, not deleted, so history is kept.

## Updating

Install the matching integration package, keep existing entries, storage and
resources, validate the configuration and restart HA. Use it with E32 beta10;
older firmware does not publish the native controller-request topic.

## Limitations

The requested temperature is our transmitted command, not boiler readback.
Room temperature source qualification is unchanged, and physical room control
is not accepted. No boiler, valve or setting writes are added.

# HA 0.4.0b6 — requested boiler temperature and plan recovery
<!-- user-release-notes:v2:en -->

Companion correction for E32 beta.8 and beta.9. Native plan recovery also supports beta.6.
The command record was introduced in unpublished candidate beta.7 and is delivered
in beta.8; the HA0.4.0b6 integration source remains frozen at6dbe42f.

## New

- Add read-only **E32 requested flow temperature** for the advertised Ecomline
  trial command record. Preserve every boiler-reported temperature entity.
- Unknown before the first transmission and after a new firmware boot;50C after
  an emitted50C request,0C after an emitted Stop. Attributes identify controller
  origin, original completion time and command age. No measurement statistics
  or restored command value is supplied.
- Reuse the existing EMS status subscription, without extra HTTP polling or
  command publication. Duplicate snapshots keep their original age; retained,
  malformed and reordered packets do not supply a temperature. Offline/expired
  status becomes unavailable.

## Fixed

- Expose **Review or recover room plan** for a running native plan connection.
  A retained staged plan could previously leave the bathroom climate unavailable
  while the recovery handler was missing from every product menu.
- Reuse the existing prepare/review/apply worker, current candidate/session/Store
  checks, separate confirmation and exact E32 readback. Merely reading the menu
  or status does not apply a plan or grant physical control.
- Advanced diagnostics now exposes applied-plan status. Inactive/disconnected
  installations do not show the native plan actions.
- Correct the old connected-menu test helper. CI rejected unpublished0.4.0b5
  because its helper still expected the old menu; that candidate was not installed.

## Updating

Install the matching integration package, preserve existing entry/storage and
resources, validate configuration and restart HA. A normal explicit plan review
resolves the pre-existing accepted6/staged7 horizon recovery; no storage rewrite.
E32 beta.8 supplies the command record. Existing beta.4/6 firmware keeps its other
entities and can use the recovered plan menu.

## Limitations

This is a controller-command history value, not boiler acknowledgement or an
independent water-temperature measurement. It does not replace a boiler's own
selected-flow report. Physical installation acceptance and the complete new
attended50C/600s trial remain open. Automatic boiler/valve outputs stay disabled.

# HA 0.4.0b5 — unpublished recovery candidate

Tagged24fd54b; exact-tag CI rejected an old connected-menu test expectation.
No public package or active installation was made from that candidate.

# HA 0.4.0b4 — integrated room and installation controls
<!-- user-release-notes:v2:en -->

Experimental coordinated release for E32 beta.6. Installation is verified separately.

## New

- Edit the installation name and shared water limits while connected to the E32.
  Linked radiators follow the limits; custom circuit limits are preserved and
  stored curve points stay bounded. Water-limit changes use the normal verified
  apply route and may restart the E32. Name/dashboard changes do not write device
  settings. Unsupported weather controls are omitted from this connected form.

- Show native cached battery percentages and device low-battery flags for the
  saved room sensor and valves under Advanced settings. Reports retain their HA
  timestamp/age, shared devices appear once, and missing or ambiguous sources
  stay unknown. Reload explicitly refreshes the snapshot; no extra subscriptions
  or duplicate entities are created. [Scope](DEVICE-BATTERY-SNAPSHOT.md).

- Select up to eight window and door contacts in the normal room editor or room
  setup wizard. Configure opening/resume delays and maximum report age.
- Contact status distinguishes open, closed, waiting and unavailable/expired
  reports. Re-reading a page does not renew a report. Only explicitly selected
  contacts affect a room.
- Add or remove contacts on an active native plan through the existing save,
  reload and verified controller readback. Older firmware without the contact
  contract is rejected before saving the new active-room intent.
- Bind a built-in Home Assistant temperature Number helper as an extra manual
  room control. A new authenticated user change requests one temporary target
  for one minute to twelve hours; startup values and automations do not apply it.
  The normal programme resumes when the controller's override expires. The
  helper is not written back, and status updates add no polling.
- Configure room comfort modes, away target, temporary duration and an optional
  person in the normal editor or setup wizard. Native person reports retain the
  selected tracker's original age. Unknown/expired presence remains unknown;
  status reads and cached person re-emissions cannot renew it.
- Start/change vacation with an end date in the displayed HA time zone, or
  explicitly return to the programme. Repeated daylight-saving times require
  an offset choice; nonexistent times are rejected. The existing finite comfort
  service checks the expected room scope. Unconfirmed requests are not replayed.

## Fixed

- Validate complete profile storage before interrupting the existing connection.
  Room and installation changes share one apply path. Interrupted or unconfirmed
  changes retain saved intent without rolling back or automatically retrying.

- Contact, extra-target and comfort status share one canonical room identity
  check. Reusing an old entity ID for another room cannot display that room's
  state or a stale override countdown in the editor.
- The initial controller link recognises E32 beta release tags alongside alpha
  tags. Firmware identity, compiled contract, update state and authenticated
  settings checks still apply.
- Contacts can pause an ordinary room without enabling comfort modes or changing
  its temperature bounds, source profile or independent frost policy.
- A new incompatible comfort frost target is rejected before saving. Native
  installations retain their existing 5 °C source target and room-bound checks.
- The editor and wizard share identity validation; deletion/replacement during
  review or compilation cannot silently adopt another device. Removing contacts
  clears their persisted bindings and listeners.
- A new managed editor tag and versioned resource URL load the current editor
  after an update. Saved older card types remain supported.

## Updating

Install with the coordinated E32 beta.6 release using the normal HA update route,
a scoped backup and postcheck. Preserve installation, entity and programme identities.

## Limitations

Software verification does not qualify physical sensors, valves or boiler control.
Installing this package does not authorize physical device commands.
Physical wall controls still require their own original-action/echo profile.
Vacation is session-local: restart, reconnect and room reload clear the selection.

# HA 0.4.0b3 — oorspronkelijke meetdiagnose en veldexport
<!-- user-release-notes:v1 -->

## Nieuw

- Diagnosedownload voor de oorspronkelijke native ketelvelden: ruwe waarde, schaal, eenheid, meetkwaliteit, brontelegram, oorspronkelijke ontvangsttijd en TTL.
- Onderscheid tussen niet ontvangen, ongeldige en verlopen metingen en verlies van de verbinding. Ontbrekende waarden blijven onbekend.

## Opgelost

- Ongeldige kamertemperaturen en foutcodes worden niet als geldige meetwaarden of statistiekpunten aangeboden; ondersteunde echte nulwaarden blijven behouden.
- De veldtoelichting blijft beschikbaar in de diagnose als Home Assistant de kenmerken van een onbeschikbare entiteit weglaat.

## Bijwerken en gebruik

Installeer `OpenThermostat-HA-0.4.0b3.zip` via de bestaande HA-beheerroute met back-up en nacontrole. Deze kandidaat hoort bij E32 beta3; kamers, programma's en entiteitidentiteiten blijven behouden. Het optionele oorspronkelijke Zigbee-ontvangstpakket blijft een afzonderlijke installatie.

Geen fysieke ketel-/kraanvrijgave of automatische verwarming. De bevestigde Ecomline-opstelling heeft geen digitale druksensor; onbekende druk wordt niet door een verzonnen waarde vervangen. Aanpassing van het warmteproefprofiel blijft open.

## English

Adds original native boiler-field diagnostics/export including raw values, quality, source telegrams, original timestamps and expiry. Separates missing/invalid/stale data from connection loss and filters invalid measurements without discarding supported real zeroes.

Install the HA ZIP through the existing administration route with backup and verification; pair with E32 beta3. Rooms, schedules and entity identities are preserved. The optional Zigbee companion remains separate. No physical boiler/valve control is enabled, and no digital pressure reading is invented for the user's boiler without that sensor.

# HA 0.4.0b1 — opstartherstel, maandexport en betrouwbare meetverwerking
<!-- user-release-notes:v1 -->

## Nieuw

- **Historie exporteren per dag, week of maand:** tot 31 dagen uit bestaande Recorder-gegevens, met installatiekeuze en Nederlandse/Engelse uitleg. Ontbrekende historie blijft ontbreken.
- **Duidelijke klokmelding:** een defecte lokale meetklok geeft een installatiegebonden Repairs-melding. Ook raam- en aanwezigheidssignalen worden dan onbekend.
- **Optioneel Zigbee-bronpakket:** de bestaande oorspronkelijke ontvangstextensies komen apart mee in dezelfde release. Een gecontroleerd hulpmiddel bewaart privé apparaatkoppelingen vóór installatie; niets wordt automatisch geïnstalleerd.

## Opgelost

- OpenThermostat start weer op Core **2026.10.4**. Een versiecontrole blokkeerde onbedoeld de weergavegroep ‘Installatie en ketel’. Core .2 en .3 blijven afzonderlijk getest; onbeoordeelde private configuratiewrites blijven geblokkeerd.
- Een schermfout of vervangen sensorprofiel kan geen ingetrokken meting terugbrengen. Ongeldige temperaturen, percentages en extreem grote getallen worden geweigerd.
- CSV-export controleert na wachten opnieuw wie de entiteiten bezit. Gegevens verschijnen niet onder een gewijzigde koppeling.
- De oorspronkelijke Zigbee-ontvangstextensies wachten bij afsluiten niet onbeperkt op MQTT. Een time-out bevestigt geen verzending en start geen nieuwe ontvanger zolang oud SDK-werk nog openstaat.

## Bijwerken en gebruik

Gebruik `OpenThermostat-HA-0.4.0b1.zip` via de bestaande HA-beheerroute. Kamers, programma's, entiteitidentiteiten en koppelingen blijven behouden. Dit is de HA-helft van dezelfde softwarekandidaat als E32 beta1. Het optionele Z2M-bronpakket is geen HA-component; bewaar private pins en volg de meegeleverde NL/EN-instructies.

De E32 biedt daarnaast lokale Bluetoothdiagnose. Deze HA-update kwalificeert die gegevens niet als kamerbron en geeft geen fysieke kraan-/ketelsturing, zelfstandig verwarmen of actieve leerregeling vrij. [Volledig werkbord en resterende voorwaarden](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0b1/docs/modern-thermostat/WORKBOARD.nl.md).

## English

**New:** day/week/month Recorder CSV exports up to 31 days, an installation selector, Dutch/English guidance, entry-scoped clock Repairs, and an optional receive-only Zigbee2MQTT companion with checked private-binding preservation.

**Fixed:** Core 2026.10.4 startup, interrupted measurement withdrawal, old-profile callbacks, invalid numbers, ownership changes during export and unbounded original-report extension shutdown. Actual Core .2/.3/.4 compatibility is checked separately.

**Updating:** use the HA ZIP through the existing administration method. Rooms, schedules and entity identities are preserved. E32 beta1 and the optional Z2M companion are separate downloads from the same candidate. No automatic companion installation or boiler/valve/learning authority is introduced. Physical acceptance and qualified room-source work remain open.

# HA 0.4.0.dev48 — betrouwbaarder afsluiten en herladen
<!-- user-release-notes:v1 -->

## Nieuw

Deze onderhoudsupdate richt zich op betrouwbaarheid; er zijn geen nieuwe instellingen of bedieningsopties.

## Opgelost

- Bij het stoppen of herladen van de integratie worden achtergrondtaken beter opgeruimd. Ook als één onderdeel een fout geeft, gaat het opruimen van de overige onderdelen door.

## Bijwerken en gebruik

Je kamers, weekprogramma's, koppelingen en dashboardkaarten blijven behouden. Deze versie is samen met E32 alpha36 gecontroleerd.

Dit is een testversie. Directe Bluetooth-koppeling met Shelly- en Xiaomi-apparaten is nog in ontwikkeling. De ketelaansturing is nog niet vrijgegeven.

## English

**New:** this maintenance release focuses on reliability and adds no new settings.

**Fixed:** stopping or reloading the integration continues cleaning up background tasks even if one component reports an error.

**Updating:** rooms, weekly programs, connections and dashboard cards are retained. Verified with E32 alpha36. Direct Shelly/Xiaomi Bluetooth pairing is still in development; boiler control remains disabled.

# HA 0.4.0.dev47 — robuuste opstart en gezamenlijke updaterdiagnose

Gezamenlijke bundel met E32 alpha34. Alle 23 voorbereide onderdelen en 31 eisen blijven behouden, inclusief eerdere ontvangstdiagnostiek en verzendcontroles.

- Eén native opstarteigenaar over programma-, Store- en MQTT-leesgrenzen. Afsluiten/annuleren kan geen oude worker, listener of timer later opnieuw starten.
- Dubbele start vervangt de eerste verbinding niet. Late unsubscribe-handles worden direct opgeruimd; een andere ontvanger blijft behouden.
- De optionele oorspronkelijke temperatuurdiagnose deelt één aanmeldbudget van één seconde; een diagnosefout laat de bestaande besturingsverbinding beschikbaar. Geen nieuwe abonnementen, workers, routes of retries.
- De gezamenlijke firmware bewaart vier gerichte checkpoints vóór checksum, imagevalidatie, flash-readback en bootselectie. De bestaande statuspagina verklaart die in Nederlands en Engels.
- Tien nieuwe HA-grensgevallen falen aantoonbaar vóór herstel; 2.349 volledige HA-gevallen per ondersteunde Core slagen lokaal. Native firmware: 782 gevallen, waaronder 40 updatergevallen ook onder ASan/UBSan; 24 updaterbrowsergevallen.
- Frontend dev41/v41 met v38/v35-aliases blijft bytegelijk. Geen kaart-, instellingen-, bron- of fysieke autorisatiemigratie.

HA47 blijft compatibel met de waargenomen E32 alpha31. Een oorspronkelijke TV02-workerontvangst is passief geobserveerd maar stale en ongekwalificeerd; dit is geen causale kraan-ACK. Geschikte kamerbron, product-SOURCE-fabriek, fysieke stop-/uitvalkwalificatie en eerdere E32-herstelroute blijven open. Tado blijft de actieve regelaar; deze bundel geeft geen fysieke uitvoer vrij.

Publicatie/HA-uitrol vereist exacte bevroren bron, volledige CI, onafhankelijke daadwerkelijke pakketreview, verse actuele HA46-back-up en afzonderlijke nacontrole. Geen blinde E32-flashherhaling of claim dat de eerdere watchdog/HTTPS/pendeloorzaak is opgelost.

English: native HA startup retains one owner across asynchronous configuration, journal and subscription boundaries. Closing/cancelling cannot revive a worker/listener/timer; duplicate startup cannot replace the first owner. Original-temperature diagnostics have one bounded optional subscription wait. The combined firmware adds four persisted pre-verification checkpoints with EN/NL explanations. Existing cards/settings and alpha31 compatibility are preserved; source/valve feedback, physical stop qualification and updater recovery remain separate open gates.

# HA 0.4.0.dev46 — oorspronkelijke ontvangstdiagnostiek en gezamenlijke verzendcontrole

Gezamenlijke voorbereidingsrelease met E32 alpha33. Alle 23 voorbereide onderdelen en bestaande instellingen, programma's en kaarten blijven behouden.

- De bestaande HA-diagnostiekdownload toont begrensde RAM-tellers voor oorspronkelijke temperatuur- en TV02-ontvangst: callbacks, plaatsing, vroege drops en workeracceptatie/-afwijzing/-fouten.
- Twee vaste groepen zonder topics, apparaat-ID's, berichtinhoud of exceptionteksten. Tellers zijn per verbindingseigenaar, niet per apparaat of blijvend. Geen teller of snapshot kwalificeert een meetbron of kraan-ACK.
- De bestaande queue en halve-queue-reservering blijven leidend. Een mislukte timestampregistratie wordt als drop zichtbaar en kan de MQTT-callback niet laten vastlopen op die exception.
- De gezamenlijke E32-bundel bewaakt herintrede op de laatste overdrachtsgrens én op beschikbaarheids-/klokcallbacks tijdens kanaaltoelating. De bestaande socketproef bevestigt dat geweigerde herintrede geen byte overdraagt.
- Bestaande kamer- en firmwareberichten blijven bytecontractueel gelijk. Frontend dev41/v41 en v38/v35-aliases blijven behouden; er is geen kaart- of instellingenmigratie.

HA46 blijft compatibel met de waargenomen alpha31 en de eerdere alpha28; de optionele voorbereide kanaalroute vereist minimaal HA45. Ontvangsttellers lossen een onbekende externe producent- of bindingsfout niet op en geven geen geschikte kamermeting, fysieke feedback of regelbevoegdheid. Product-SOURCE blijft gesloten; Tado blijft actief.

Publicatie/uitrol vereist exacte bron-, CI-, pakket- en downloadcontrole, verse actuele HA-back-up en afzonderlijke nacontrole via de bestaande HA-agent. Eerdere E32-uploaderwatchdog, native HTTPS-fout en pendeloorzaak blijven open; geen blinde firmwareherhaling.

English: bounded original-ingress counters in the existing HA diagnostics download distinguish callback drops from worker outcomes without payloads or identifiers. Counter scope is the connection owner's RAM lifetime, not per-device traffic or control authority. The combined firmware bundle closes handoff/availability/clock callback recursion. Existing frontend aliases and alpha31 compatibility remain. Physical feedback, ambient qualification and E32 updater recovery are separate open gates.

# HA 0.4.0.dev45 — oorspronkelijke grantcorrelatie en grotere firmwarebundel

Gezamenlijke voorbereidingsrelease met E32 alpha32; bestaande functies, programma's en alle 23 voorbereide onderdelen blijven behouden.

- De bestaande native worker antwoordt met het oorspronkelijke aanvraagvolgnummer. Vertraagde grants kunnen geen nieuw firmwarevenster lenen.
- Een nog ongebruikt grant blijft bij zijn oorspronkelijke aanvraag; een hoger aanvraagvolgnummer kan het niet herlabelen. Een verkorte ontvangerdeadline blijft ook na zo'n geweigerde aanvraag bewaard.
- De echte C++-aanvraag/grant/opdracht gaat door de native HA-worker naar de bewaakte serviceadapter, inclusief duplicaat- en uitvalproeven. Serviceacceptatie blijft geen oorspronkelijke kraanecho of regelbevoegdheid.
- De ACK-zonder-snapshotproef bereikt nu eerst de echte ACK-fase voordat haar echte asyncio-timeout afloopt. Vertraagde voorbereiding is apart getoetst; de productie-timeout van 90 seconden blijft ongewijzigd. De oudere incidentele CI-kameroorzaak blijft afzonderlijk onbekend.
- Frontend dev41/v41 met v38/v35-compatibiliteit blijft bytegelijk; geen kaartmigratie, automatische sensorwissel of nieuwe productfabriek. Instellingen en identiteiten behouden.

HA dev45 blijft compatibel met E32 alpha28 en de vers waargenomen alpha31; de nieuwe voorbereide firmwarekanaalroute vereist dev45. Product-SOURCE-selectie, geschikte oorspronkelijke meetbron, causale kraanecho en fysieke acceptatie blijven open. Dit is geen actieve ketelbèta: Tado blijft regelen en fysieke uitgangen blijven geblokkeerd.

Uitrol vereist exacte CI-/pakketcontrole, verse actuele back-up en onafhankelijke nacontrole. De eerdere E32-uploaderwatchdog, native HTTPS-fout en gemeld pendelen worden niet als gerepareerd voorgesteld.

English: original request-sequence correlation on the existing worker; unconsumed grants cannot be relabelled or regain a shortened deadline. Actual C++/worker/service and disconnect regressions preserve one-use ownership. Existing cards and alpha28 compatibility remain; product actuation, original physical feedback and E32 recovery are still unqualified.

# HA 0.4.0.dev44 — native kraanroute en gezamenlijke ontvangstcontrole

Gezamenlijke prerelease met E32 alpha31; alle bestaande functies, instellingen en 23 voorbereide onderdelen blijven behouden.

- Grantaanvragen en kraanopdrachten gebruiken de bestaande native MQTT-worker en verbinding, zonder extra clients, timers, opslag of wachtrijen. De productfabriek blijft standaard gesloten.
- Lokale controller-/sessie-/config-/bindingcontrole en oorspronkelijke ontvangst-/leasedeadlines begrenzen opdrachten. Eén grant laat één nieuwe opdracht toe; duplicaten vernieuwen geen venster of serviceaanroep.
- Firmware-offline of gewijzigde scope trekt een bestaande eigenaar direct vóór de workerqueue in, ook als die op de servicelock wacht. De adapter controleert de context opnieuw vóór en na de oorspronkelijke bronautorisatie.
- Uitgeschakeld, ingetrokken of overmatig optioneel kraanverkeer kan de shadow-sessie niet via de gedeelde queue resetten. Normale periodieke hello-berichten verlengen geen kraangrant.
- Alle eerdere ESP-/EMS-diagnose, bronkeuze-uitleg en EN/NL-bediening blijven behouden. Frontend dev41/v41 met v38/v35-compatibiliteit blijft bytegelijk; geen automatische bronwissel of nieuwe fysieke autorisatie.

Dit pakket kan met de laatst geverifieerde E32alpha28 blijven werken: het veronderstelt geen nieuwe firmwarefunctie. Een daadwerkelijk gekwalificeerde product-SOURCE-fabriek, normale firmware-MQTT-zendroute, oorspronkelijke causale Tuya-echo en fysieke acceptatie blijven open. Serviceacceptatie is geen kraan-ACK of bewezen afgiftepad. Dit is geen actieve ketelbèta; Tado blijft regelen en fysieke uitgangen blijven geblokkeerd.

E32-updateherstel is afzonderlijk geblokkeerd door de eerdere onverklaarde watchdogreset. HA-installatie vereist het exact geteste pakket, verse back-up, één normale herstart en onafhankelijke nacontrole. Geen claims over opgelost pendelen, native HTTPS-herstel of nieuwe Shelly-/Xiaomi-drivers.

English: native-worker actuator grant/command handling with default-denied product authority, original receiver deadlines, one-use grants, immediate scope/offline fencing and optional-queue isolation. Configuration and frontend remain compatible with installed alpha28. Service acceptance is not a physical valve acknowledgement; active heating and E32 recovery remain separate acceptance gates.

# HA 0.4.0.dev43 — duidelijke temperatuurbronkeuze en M2-ontvangertoelating

Grotere onderhoudskandidaat met behoud van alle bestaande functies en instellingen.

- De kamereditor waarschuwt direct in Nederlands/Engels wanneer de gekozen bron interne apparaattemperatuur is. Diagnostische sensoren krijgen een herkenbaar label; geen verborgen automatische bronwissel of kwalificatie van een gewone cachewaarde.
- Ontbrekende/corrupte optionele native MQTT-metadata verhindert het laden van de kamer niet. De waarschuwing volgt de actuele conceptkeuze en blijft niet aan een vervangende sensor plakken.
- Frontend dev41/v41 met expliciete v38/v35-compatibiliteit; bestaande handmatige kaarten blijven werken. Alleen eigen gegenereerde kaart-/resourceverwijzingen mogen bij de update meegaan.
- Nieuwe voorbereide M2-ontvangerkern: standaard gesloten, exact lokaal bron-/sessie-/config-/bindingbezit, vijf seconden geldigheid op de HA-klok, één lopende opdracht en geen verlenging bij ontvangst. Duplicates zijn alleen historisch; onzekere of geannuleerde acties worden niet herhaald. Callback-intrekking en hergebruik van dezelfde adapter kunnen de eigenaar niet omzeilen.

De ontvangerkern wordt niet door de productie-fabriek geselecteerd. Normale
FW→HA-bedrading, actuele leasebinding, causale oorspronkelijke kraanecho en fysieke
kwalificatie blijven open. Dit is geen actieve bèta of vrijgave van kraan-/keteluitvoer.

59 nieuwe basisgevallen plus vier aanvullende eigenaarsgrensregressies,
een extra afrondingsgrensgeval en een opstartverliesregressie.
Een extra regressie toetst vertraagde eerste kamerberichten. De testopstelling
begint de minimum-uit-wachttijd pas na beide werkelijke firmwaremetingen;
de 120-secondenregel en alle oorspronkelijke vraag-/stopasserties blijven behouden.
De vijfseconden-grens wordt vanuit het oorspronkelijke klokanker getest,
zodat optellen van kommagetallen geen vals testresultaat oplevert. De kamertest
loopt achtmaal per Core-versie met afzonderlijke naspeelbare, kunstmatige
berichtenreeksen. De eerdere intermitterende kamerassertie is hiermee onderzocht;
de opstartverliesregressie bewijst op zichzelf niet de oorspronkelijke CI-oorzaak. Gerichte
HA- en koude browserproeven op desktop/mobiel in beide talen slagen; volledige
Core 2026.10.2/2026.10.3- en exacte tag-CI blijven afzonderlijke leveringsvoorwaarden.

Entiteits-ID’s, eenheden, statistieken, SOURCE/journal en instellingenformaat blijven
behouden. E32-runtimecode is niet gewijzigd: firmwaredownload alpha30 blijft staan,
de module blijft alpha28 totdat de onbekende uploader-watchdogoorzaak en een
onderbouwde herstelroute zijn vastgesteld. Geen blinde upload/herstart/rollback.
Bluetoothondersteuning, fysieke bron-/kraan-/ketelproeven en langdurige stabiliteit
worden niet als afgevinkt voorgesteld.

English: room setup now explains internal/diagnostic temperature sources immediately,
without new broker traffic or source replacement. Missing optional native metadata
cannot break the editor. Frontend v41 retains v38/v35 compatibility. A default-deny
M2 receiver admission kernel is prepared with receiver-owned grants, bounded input,
strict ownership and no uncertain retry; it is not wired into production actuation.
Test warmup now waits for both actual firmware measurements before counting
the unchanged minimum-off interval; a lost-startup-report regression covers this.
E32 firmware and physical output blocks remain unchanged.

[Werkbord en resterende voorwaarden](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev43/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev40 — blijvende klokbewaking van de M2-kraanadapter

Onderhoudsrelease met alle eerdere functies en de voorbereide B05/M2-reparatie.
De E32-firmware heeft geen nieuwe runtimewijzigingen; alpha30 blijft de actuele
firmwaredownload. Geen overbodige nieuwe firmwaretag of E32-installatie.

- Een teruggaande, ongeldige of niet-eindige monotone klok trekt de bestaande kraanadapter blijvend in. Herstelde tijd, een nieuw doel of herstelde autorisatie kan oude bevoegdheid niet herstellen.
- De controle omvat wachten, iedere autorisatiecallback, de laatste controle vóór verzending en de terugkeer van de HA-service. Ook een weigering of exception kan klokverlies niet verbergen.
- Klokverlies tijdens een mogelijk verzonden opdracht houdt de fysieke uitkomst onbekend en verhindert herhaling. Een exacte duplicate blijft uitsluitend een historisch service-acceptatiereceipt, zonder nieuwe IO of kraanbevestiging.
- Geen wijziging aan entiteits-ID’s, statistieken, instellingen, MQTT-contracten of frontend v38/v35-compatibiliteit.

14 nieuwe regressiegevallen; 13 faalden op de oude bron. Alle 141 gerichte gevallen
slagen op echte Core 2026.10.2 en 2026.10.3; onafhankelijke bronreview geslaagd.
Definitieve tag-CI en pakketcontrole blijven afzonderlijke leveringsvoorwaarden.

Passieve onderhoudsrelease. De M2-adapter heeft nog geen normale FW→HA-zendroute
of gekwalificeerde fysieke terugmelding; ketel-/kraanuitgangen blijven geblokkeerd.
De geïnstalleerde E32 blijft alpha28 zolang de eerdere watchdogoorzaak/herstelroute
onbekend is. Geen actieve bèta-, Bluetooth-, pendel- of updaterreparatieclaim.

English: preserves every existing feature and adds latched monotonic-clock
validation throughout the prepared M2 actuator adapter. Invalid/reversed time
cannot revive an old command budget; uncertain dispatch is never retried.
Historical duplicates remain acceptance-only. No physical actuation is enabled;
E32 alpha30 remains the latest firmware release, with alpha28 still installed.

[Actueel werkbord](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev40/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev39 — betrouwbare ketelwaarden na fouten en intrekking

Gezamenlijke passieve onderhoudsbundel met E32 alpha30; alle eerdere functies en frontend v38 blijven behouden.

- Een transportfout trekt de eerder opgeslagen acquisities van ketelwaarden in. Een geldig bericht voor een andere veldgroep maakt die oude waarden niet opnieuw beschikbaar.
- Een expliciete ongeldige waarde mag dezelfde acquisitie intrekken; een herhaalde oude numerieke waarde kan die intrekking niet ongedaan maken. Alleen aantoonbaar nieuwe ontvangst herstelt beschikbaarheid.
- Firmware verwerkt telegrammen per oorspronkelijke veldtijd, behoudt recente waarden bij vertraagde ontvangst en trekt tegenstrijdige gelijktijdige waarden in.
- Bestaande entiteitsidentiteiten, eenheden, statistieken, instellingen en MQTT-contracten blijven behouden.

Lokaal getest op echte Core 2026.10.2 en 2026.10.3: 2195 testgevallen per versie, zonder fouten of skips; de gezamenlijke firmwarebasis heeft 689 geslaagde tests. Release-CI en onafhankelijke pakketcontrole zijn afzonderlijke leveringsvoorwaarden.

Geen fysieke regelvrijgave. De geïnstalleerde E32 kan achterblijven op alpha28 zolang de eerdere task-watchdogreset geen onderbouwde herstelroute heeft; HA-installatie en E32-installatie worden afzonderlijk gecontroleerd. Nieuwe Bluetoothdrivers en M2/start-/stopkwalificatie blijven open.

English: retires boiler field acquisitions across invalid transport frames and explicit withdrawal. Unrelated valid groups or cached replay cannot revive them; strictly newer original readings are required. Entity IDs and storage contracts are preserved; passive operation remains enforced.

[Actueel werkbord](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev39/docs/modern-thermostat/WORKBOARD.nl.md).

# HA 0.4.0.dev38 — oorspronkelijke rapporten en compatibele bediening

Onderdeel van de gezamenlijke onderhoudsbundel met E32 alpha29 op bron
`d131c503f42e6b834a0815db8384983a7fc1b46f`.

- TV02-diagnose kan wachten op late MQTT-discovery met vooraf vastgelegde apparaatidentiteit; geen automatische bronvervanging.
- Native registrywijzigingen trekken oorspronkelijke temperatuurdiagnose in, ook wanneer instellingen daarna worden teruggezet. Gewone naamswijzigingen blijven werken.
- EN/NL-meldingen voor ontbrekende metadata en niet-beschikbare ontvangst; geen oude waarden bij fout-/wachtstatus.
- Frontend dev38/v38 met compatibiliteitsalias voor bestaande v35-kaarten, gecontroleerd bij koude browserlading.

Getest op echte Home Assistant Core 2026.10.2 en 2026.10.3: 2189 gevallen per versie zonder fouten/skips. Browserregressies en upgradeproef geslaagd. Geen fysieke regelvrijgave of automatische sensorwissel. Shelly-/Xiaomi-Bluetoothondersteuning blijft gepland; M2 en fysieke ketel-/kraanproeven blijven open.

English: restores optional original-report diagnostics safely, retires changed sensor identities, and adds clear reception states while preserving existing v35 room cards. Passive operation remains enforced.

[Wijzigingen en resterende voorwaarden in de bron](https://github.com/dielessen/open_thermostat/blob/ha-v0.4.0.dev38/docs/modern-thermostat/WORKBOARD.nl.md). Het aparte historiebestand in deze bron bevat de eerdere releasegeschiedenis.

# HA 0.4.0.dev37 — sessies, wachtrij en betrouwbaar opstarten

Gezamenlijke uitgave met E32 alpha28; alle eerdere functies en fixes blijven behouden.

- Ongeldige/teruggaande monotone klok trekt sessie, grants en wachtende opdrachten in; reconnect herstelt geen oude bevoegdheid.
- Retries controleren na iedere wachtende verzending opnieuw de actuele lease/deadline, SOURCE en de oorspronkelijke opdrachtregistratie. Ingetrokken/vervangen opdrachten worden niet opnieuw aangeboden; geen heartbeat op een verlopen sessie.
- Opstartfouten en annulering ruimen ook vroeg aangemaakte resources op; oude cleanup kan een nieuwe eigenaar niet verwijderen.
- Te grote numerieke kraanmetadata wordt als onbruikbare capability afgewezen zonder editorcrash.

Ondersteunde native Core-versies blijven 2026.10.2 en 2026.10.3, met volledige tests op beide echte runtimes. Geen frontendwijziging: module dev35/v35 blijft byte-identiek. Kamers, programma's, SOURCE, registry, ontvangstpins en producent blijven behouden.

Geen automatische kraan-/ketelopdrachten of nieuwe ontvangergrant-route. Een ontvangen TV02-temperatuurbericht is geen causale kraanbevestiging. Tado blijft regelen; actieve M2-/ketelacceptatie blijft open.

**English:** Combined with E32 alpha28. Retires session evidence on invalid/backward monotonic time, rechecks queue ownership and original deadlines after awaited publishes, fixes failed/cancelled HA setup cleanup and oversized target metadata. Supports actual Core2026.10.2/2026.10.3; unchanged frontend and preserved configuration. Boiler/valve actuation stays disabled.

# HA 0.4.0.dev36 — Core 2026.10.3 en gezamenlijke E32 alpha27-bundel

Neemt alle wijzigingen uit dev35 mee en herstelt de opstartblokkade na een Core-update naar 2026.10.3. De expliciete ondersteunde versies zijn nu 2026.10.2 en 2026.10.3; andere versies blijven geweigerd voor de native configuratietransactie. Alle vijf versiecontroles gebruiken dezelfde lijst. De volledige suite draait op beide echte Core-versies; er wordt geen versienummer of HA-API nagebootst. Instellingen en registry worden niet opnieuw aangemaakt.

Gezamenlijke passieve uitgave met E32 alpha27; geen nieuwe firmwarevariant nodig. De eerder gepubliceerde dev35 blijft historisch behouden en wordt niet geïnstalleerd. Dit is geen vrijgave voor kraan- of ketelopdrachten.

# HA 0.4.0.dev35 — gezamenlijke diagnose- en veiligheidsbundel

Bundelt alle voorbereide HA-wijzigingen sinds dev34, samen met E32 alpha27.

- Frontend dev35/v35 met duidelijkere EN/NL-status voor verouderde TV02-ontvangst, zonder oude waarden als actuele kraanbevestiging te presenteren.
- Strengere binding en levensduur van kraanopdrachten: herhaalde opdrachten delen één serviceaanroep en oorspronkelijke deadline; annulering of onzekere uitvoering veroorzaakt geen automatische herhaling.
- Verlies van eigenaar, koppeling of kraanmodus tijdens een serviceaanroep blokkeert automatische vervolgacties.
- Aanvullende supervisordiagnose voor ongeldige feedbackklokken.

De opdrachtadapter is voorbereid, maar nog niet aangesloten als normale firmware-naar-HA-zendroute. Een HA-servicebevestiging bewijst geen kraanbeweging. Bestaande kamers, programma's, SOURCE, registry, ontvangstpins en producent blijven behouden. Geen automatische bronkwalificatie of apparaatopdrachten. Tado blijft regelen; dit is een passieve prerelease, geen actieve ketelbèta.

# HA 0.4.0.dev34 — diagnose en duidelijke bediening afgerond

Bundelt alle eerdere HA-correcties en de native ESP-diagnose met de EN/NL-uitleg van instellingen en controles. Hoort bij E32 alpha26; die firmware hoeft hiervoor niet opnieuw geflasht te worden.

- Ontvangstouderdom van de alleen-lezen supervisordiagnose vergelijkt direct met de vervaldeadline. Daarmee blijft een exact verlopen rapport niet zichtbaar door afronding bij het aftrekken van twee klokwaarden.
- Een deterministische proef met een fractioneel klokbegin toont de oorspronkelijke fout en het herstel. Regelbevoegdheid, opdrachten, leases, bronkwalificatie en fysieke uitgangen veranderen niet.

# HA 0.4.0.dev33 — ESP-eigen diagnose via native MQTT

Herstelt vrije/minimaal vrije heap, grootste vrije blok, CPU-temperatuur en uptime samen met E32 alpha25. Bestaande entity unique IDs en geschiedenis blijven behouden. De HA-entiteiten bestaan ook vóór het eerste rapport. Live rapporten zijn elke 15 seconden beschikbaar; na 45 seconden zonder geldig rapport of bij offline wordt beschikbaarheid ingetrokken. Een HA-only herstart vereist geen E32-herstart. Uitgeschakelde RTC-temperatuur blijft onbekend. Legacy modus blijft intact.

Instellingen en status maken in Engels en Nederlands duidelijk dat schaduwmodus alleen uitleest en berekent. Een bevestigde configuratie en passende kraandoelen worden apart uitgelegd; zij worden niet gepresenteerd als bewijs van kraanbeweging of veilig ketelstoppen.

Dit gebruikt dezelfde native verbinding en bestaande HA-runtime voor verval; er worden geen kraan- of ketelopdrachten toegevoegd. Alle functies en correcties uit dev32 zijn meegenomen. Zonder bijbehorende E32 alpha25 blijven deze native diagnosewaarden niet beschikbaar.

# HA 0.4.0.dev32 — rapportlevensduur en verklaarbare transportafwijzingen

Bundelt alle HA-correcties sinds dev31. E32 alpha24 blijft staan; deze uitgave
verleent geen fysieke meet-, kraan- of ketelkwalificatie.

- Oorspronkelijke temperatuur- en TV02-rapporten blijven gebonden aan de gekozen
  maximale rapportleeftijd. Een policywijziging trekt de oude ontvanger in;
  terugzetten hergebruikt geen oude rapporten. Een nieuwe eigenaar begint leeg.
- Ongeldige klokwaarden en overlopende tijdsdelta's worden veilig afgehandeld.
- De bestaande ontvanger bewaart maximaal één historische afwijzing voor een
  actuele, aangevraagde reply. HA-diagnostiek toont alleen vaste stroom-, status-
  en redencodes met ontvangstouderdom. Onbekende peer-tekst wordt niet uitgevoerd
  of geëxporteerd. Een latere gezonde status maakt dit geen actuele storing.
  Een sessiewissel of geconstateerde klokfout verwijdert deze diagnose.
- Native configuratieafwijzingen met het optionele `rejection_reason`-veld worden
  correct als afwijzing verwerkt; zij verdwijnen niet door een te strikt schema.
  Succes blijft uitsluitend via de bestaande readback-/SOURCE-controles geldig.

Kamers, programma's, koppelingen, accepted SOURCE/journal, registry, dashboard,
privé TV02-pins en ontvangende producent blijven behouden. Geen extra client,
watcher, automatische retry of apparaatopdracht. De frontendbytes en bestaande
dev28/v28-kaartidentiteit blijven gelijk. Natuurlijke TV02-ontvangst, causale
opdrachtbevestiging en fysieke acceptaties blijven afzonderlijke open checks.

# HA 0.4.0.dev31 — TV02-ontvangst voor native installatiekamers

Herstelt de oorspronkelijke TV02-ontvanger voor kamers waarvan de gekozen kraan
in de centrale installatieconfiguratie staat. De ontvanger valideert dezelfde
native configuratie-eigenaar als de kamereditor. Ontbrekende, dubbele, gewijzigde
of ongeldige koppelingen worden afgewezen; een ingetrokken bron herleeft niet
vanzelf. Identiteits-, ouderdoms- en replaycontroles blijven behouden.

Deze gerichte vervolgupdate maakt ontvangstacceptatie mogelijk na de gezamenlijke
alpha24/dev30-bundel. E32 alpha24 blijft staan. Geen apparaatopdracht, automatische
kraanmoduswijziging of bronkwalificatie. De al geplaatste privé ontvangstpins en
ontvangende Zigbee2MQTT-extension blijven behouden; het pakket bevat geen privé
pins. Kamers, programma's, SOURCE, registry en historie blijven behouden.
Frontendbytes en dev28/v28-kaartidentiteit blijven gelijk.

# HA 0.4.0.dev30 — supervisor, eindige kraandoelen en privé ontvangstpins

Gezamenlijke kandidaat met E32 alpha24; bundelt alle HA-wijzigingen sinds dev29.
De standaard fysieke uitvoer blijft geblokkeerd. Dit is geen actieve ketelbèta.

- Read-only supervisordiagnose toont gemelde fase en regelintenties met beperkte
  ontvangstouderdom. Verlopen, ontbrekende of ongeldige status wordt ingetrokken;
  diagnose verleent geen bevoegdheid en verwerpt geen geldige kamerbeslissingen.
- De voorbereide kraanadapter begrenst wachttijd én serviceaanroep binnen dezelfde
  actiedeadline. Een nieuwer wachtend doel vervangt een ouder. Een onzekere afloop
  na dispatch blokkeert vervolgacties binnen dezelfde adapter, zonder retry.
- Oorspronkelijke TV02-ontvangstpins kunnen uit het privébestand
  `.openthermostat-original-tv02.json` op de HA-configroot worden gelezen bij
  normale native opstart. Strikt schema, privérechten, identiteitsbinding en
  foutisolatie; geen Store, watcher, extra MQTT-client of apparaatopdracht.
  Ontbrekend/ongeldig bestand laat normale controlleropstart werken.

De update installeert geen Zigbee2MQTT-producent, verandert geen meetselectie of
kraanmodus en kent geen bron-/flow-/klepkwalificatie toe. Werkelijke originele
ontvangst vereist afzonderlijk beoordeelde private pins en producentinstallatie.
Kamers, programma's, SOURCE, registry-identiteiten en historie blijven behouden.
De frontendbytes veranderen niet: de bestaande dev28/v28-resource-/kaartidentiteit
blijft geldig en wordt niet op basis van het manifestnummer vervangen.

# HA 0.4.0.dev29 — oorspronkelijke TV02-ontvangst zichtbaar

Bundelt de voorbereide oorspronkelijke TV02-datapointontvangst via de bestaande
native MQTT-verbinding en registry-lifecycle. Ontvangst is begrensd, controleert
de expliciet vastgelegde apparaatidentiteit en bronleeftijd en maakt verouderde,
retained, herhaalde of verkeerd gekoppelde rapporten niet opnieuw actueel.
De standaard bronpinlijst blijft leeg. Productiebronpins, Zigbee2MQTT-extension
installatie en echte oorspronkelijke rapportontvangst moeten apart beoordeeld
worden; de update schakelt deze niet automatisch in.

De kamereditor toont beschikbare oorspronkelijke rapporten in Nederlands of
Engels: gemeld doel, eigen kraantemperatuur, programma, verwarmingsstop en
vorstbeveiliging. De ontvangstouderdom geldt bij laden. Ontvangst is geen
opdrachtbevestiging, klepstand, bewezen warmteafgifte of aansturingsvrijgave.
Verlopen, onderbroken of ongeldige rapporten tonen geen oude datapointwaarden.
Conceptwijzigingen gebruiken niet de diagnose van een oude opgeslagen koppeling.

De gewijzigde editor heeft de eigen dev28/v28-cache-/kaartidentiteit; dev29
behoudt diezelfde frontendbytes en voegt complete pakketnotities toe.
Bestaande handmatige kaarten blijven compatibel. Er is geen extra polling,
MQTT-client, automatische kraanmodusreparatie of setpointopdracht toegevoegd.
Bestaande meetentiteiten, historie, kamers, weekprogramma's, SOURCE en apparaat-
identiteiten blijven behouden. Dit is de gezamenlijke passieve testbatch met
E32 alpha23 (logging/syslog en stabiele dashboardverversing). Fysieke
ketel-/kraanuitgangen blijven geblokkeerd en de actieve bèta blijft open.

Dev28 bleef een ongepubliceerde pakketkandidaat; de bestaande tag blijft
behouden. Dev29 bevat de volledige bijgewerkte Nederlandstalige pakketnotities.

# HA 0.4.0.dev27 — actuele ketelvelden zichtbaar in het overzicht

Het beheerde keteloverzicht gebruikt nu de native ketelsensoren die met
alpha20/dev26 beschikbaar zijn gekomen. Aanvoer, retour, gerapporteerde
modulatie en tapwatertemperaturen krijgen eigen historiekaarten. Alle
beschikbare velddefinities worden via de geregistreerde entiteits-ID opgenomen;
hernoemen, uitschakelen en installatie-eigendom blijven gerespecteerd.
Gerapporteerde velden en afgeleide activiteit staan afzonderlijk. Ingeschakelde
onbetrouwbare ruwe diagnostiek blijft bij Diagnostics en wordt geen vlam- of
pompbewijs. Er worden geen oude statistieken samengevoegd of counters aangevuld.

Dit rondt de HA-presentatie van de uitleesupdate af; E32 alpha20 blijft staan.
Geen SOURCE-, kamer-, programma-, regelaar- of uitgangswijzigingen. De bestaande
kamereditor en zijn dev25-cache-identiteit veranderen niet.

# HA 0.4.0.dev26 — native meetkoppeling voor de productinstallatie

Bundelt alle voorbereide dev25-functies met de correctie voor bestaande v2-
meetentiteiten. De productinstallatie gebruikt nu dezelfde gevalideerde native
MQTT-cache als de native sensorplatformtests. Eén eigenaar per meetidentiteit
voorkomt dubbele sensoren door legacy-berichten. Entiteitsidentiteiten,
statistiekdefinities en installatiegroep blijven behouden; verlopen of niet
ondersteunde waarden blijven onbeschikbaar. De frontend blijft op dezelfde
reeds vernieuwde dev25-kaartversie omdat de frontendbytes niet veranderen.

Samen met E32 alpha20 worden beschikbare Classic-ketelvelden zichtbaar.
Uitgangen blijven geblokkeerd; geen wijziging van SOURCE, kamers of programma’s.

# HA 0.4.0.dev25 — actuele ketelvelden en consistente EN/NL-bediening

Samen met E32 alpha19 worden beschikbare Classic-ketelvelden via de bestaande
native MQTT-sessie als leessensoren op de bestaande installatie aangeboden.
De bronleeftijd, kwaliteit, eenheid en geldigheid blijven zichtbaar. Dit herstelt
het ontbrekende moderne uitleespad; oude legacy-aliassen en hun historie worden
behouden en worden niet met nieuwe meetdefinities samengevoegd. Niet door de
ketel geleverde waarden blijven onbekend; onbetrouwbare diagnostiek blijft
standaard uitgeschakeld.

De volledige EN/NL-formuliercatalogi zijn aangevuld. De kamereditor volgt de
HA-profieltaal, met nieuwe cache-/kaartidentiteit en behoud van oudere kaarten.
Opgeslagen native dashboardteksten gebruiken de afgesproken Engelse terugval.
Alle voorbereide apparaat-/meetdiagnostiek, weekplanner- en opslagcorrecties
blijven meegenomen. Er worden geen kamerkoppelingen, programma’s, kraanmodi of
verwarmingsvrijgaven gewijzigd. Fysieke uitgangen blijven geblokkeerd.

# HA 0.4.0.dev24 — gezamenlijke bron- en apparaatcontroles

Deze release bundelt de voorbereide bronwijzigingen met E32 alpha18. Meetkwalificatie wordt ingetrokken bij vervanging van een observer of wijziging/uitschakeling van de native sensor of het apparaat. Wachtende metingen worden opnieuw gecontroleerd vóór overdracht; cache en herregistratie maken een oude meting niet vers.

De kraanadapter controleert identiteit en actuele temperatuurcapaciteit vlak vóór dispatch. TV02 auto-/vakantie-/uit-/onbekende modus wordt als conflict getoond en verleent geen doelautorisatie. De apparaatcontrole toont expliciet gemelde Zigbee2MQTT- en converterpakketversies. De frontend krijgt een nieuwe cache- en kaartidentiteit.

Programma, kameridentiteiten, bindings en SOURCE blijven behouden. Deze installatie wijzigt geen profiel, kraanmodus of fysieke uitgang. Het productiemeetprofiel en fysieke kraan-/ketelacceptatie blijven open; ontbrekende kwalificatie blijft zichtbaar. Alle eerdere planner-, koude-start-, inrichting- en verbindingsfixes blijven behouden.

# HA 0.4.0.dev23 — gebundelde kamer- en verbindingsverbeteringen

Deze release hoort bij de gezamenlijke testbatch met E32 alpha17.

- De kamerpagina wacht bij opstarten op het HA-hoofdelement. Zo blijft de kaart geregistreerd nadat HA zijn custom-elementregister heeft ingericht; herhaald verversen hoort niet nodig te zijn.
- Bij een normaal gekoppelde native regelaar kunnen de temperatuursensor, radiatorknop en kamergrenzen via de kamerpagina worden gewijzigd. Het complete toekomstige plan wordt vooraf gecontroleerd; kamer, graph en nieuw profiel worden samen opgeslagen en via de bestaande beveiligde controllerverbinding toegepast.
- Als toepassing niet kan worden bevestigd, blijven de opgeslagen instellingen behouden. De pagina blokkeert verdere wijzigingen en biedt een expliciete knop om precies die opgeslagen instellingen opnieuw toe te passen. Er is geen automatische herhaling of terugzetten van een oud profiel.
- De bestaande native heartbeat kan begrensde UTF-8-kamernamen aan een ondersteunende E32 doorgeven. Oude firmware blijft compatibel.
- De oude tijdelijke bronbench wordt geweigerd bij een door SOURCE beheerd regelplan, voordat hij configuratie, timers of eigendom kan wijzigen.

Bestaande kameridentiteiten, programma's en bindings worden bij de update behouden. Apparaatwijzigingen gebeuren alleen na expliciet opslaan. Eén radiatorknop per native kamer blijft de huidige contractgrens; programmabronwissels blijven een afzonderlijke inrichting. Beschikbaarheid van een HA-entiteit bewijst geen gekwalificeerde temperatuurmeting. Een ontbrekend meetprofiel blijft zichtbaar en krijgt door deze update geen automatische kwalificatie of verwarmingsvrijgave.

Verificatie omvat native HA-opslag/herlaadcycli, de normale controller-provisioning met gecontroleerde externe HTTP-antwoorden, echte MQTT-pakketuitwisseling met de C++-controller en desktop/mobiele browserregressies. Fysieke apparaatacceptatie staat daar los van.

# HA 0.4.0.dev22 — meetstatus in de kamerbediening

Bij de gekoppelde sensor staat nu afzonderlijk of de regeling een gekwalificeerde meting heeft, op een nog ontbrekend meetprofiel wacht, of een onbevestigde/verlopen meting heeft. De status is een momentopname bij laden. Hij verandert geen sensorinstellingen en schrijft geen programma of actuatoropdrachten.

Beschikbaarheid in Home Assistant en meetactualiteit blijven afzonderlijk. Een leesactie vernieuwt nooit de leeftijd van een meting. Rapport-ID's en andere bronpayloads worden niet in deze samenvatting opgenomen. De bestaande planner- en koude-startcorrecties blijven behouden.

# HA 0.4.0.dev21 — korte weekblokken betrouwbaar verplaatsen

Een kort temperatuurblok wordt op een aanraakscherm bij slepen nu als geheel verplaatst, met behoud van duur en temperatuur. De vaste randzone kon voorheen het hele blok innemen en daardoor onbedoeld de begintijd wijzigen. Op muisbediening houdt ieder blok een middengebied om te verplaatsen; grotere blokken blijven aan de randen te verlengen of in te korten. Exacte tijden blijven in de velden onder de planner instelbaar.

De browserregressie gebruikt echte Chromium-aanraakgebeurtenissen op 320, 390 en 1440px, Nederlands en Engels. Deze controleert korte blokken, muisbediening, tijdvelden, overlap, daggrenzen, annuleren en afwezigheid van automatisch opslaan. Dit is schermemulatie, geen fysieke telefoonacceptatie.

De koude-startoplossing uit dev20 blijft behouden. Deze HA-update bevat geen firmware en verandert geen opgeslagen kamerprogramma of apparaatbindingen.

# Home Assistant 0.4.0.dev20 — room page registration on direct opening

The room editor previously waited for ha-card before registering its own custom
element. A direct room URL can load before that built-in component, leaving the
editor unregistered and showing a Lovelace Configuration error. The editor
extends HTMLElement and has no dependency on the ha-card definition.

Register immediately; a nested ha-card can upgrade later. The frontend module URL
and managed card type advance to dev20/v20 to refresh cached dev19 clients.
Eight desktop/mobile NL/EN browser cases now exercise both cold and preloaded
HA shells, including preserving a draft when ha-card registers later. Four
existing device-metadata cases remain covered. The regression failed against
the original script and passed after removing the unnecessary wait.

No room settings, schedule, SOURCE, sensor bindings or controller admission
rules are changed. No firmware is included. Browser fixtures use simulated
admin WebSocket responses; live deployment and the user's exact browser
session are separate verification steps.

# OpenThermostat Home Assistant 0.4.0.dev19 — testrelease

Dev19 herstelt opslaan na langer geopende kamerinstellingen. Een verse
kamerstatus bewijst niet dat de eerdere configuratie-uitlezing nog actueel is.
Bij Alles opslaan vraagt de bestaande verbinding zo nodig eerst een nieuwe
configuratiebevestiging op. Pas daarna wordt de ruimte opgeslagen en het
gewijzigde plan via dezelfde regelaar bevestigd. De bestaande leeftijdsgrens
blijft gelden; er worden geen bevoegdheden of bronkwalificaties gefabriceerd.
Als die uitlezing ontbreekt, blijft het concept zichtbaar en wordt niets
opgeslagen. Geen automatische herhaling van een wijziging. De live dev18-proef
werd vóór opslaan geweigerd; 21°C en revisie1 bleven daarbij behouden.

Bij een verbonden regelaar kun je nu de **naam, basistemperatuur en lokale
weekblokken** direct in het kamerscherm wijzigen. Alles opslaan bewaart de
ruimte, wacht op de normale HA-herlaadcyclus en bevestigt het werkelijke E32-plan
via de bestaande MQTT-worker. Een ACK alleen geldt niet als voltooiing. Bij
gewijzigde temperaturen/blokken vervalt een tijdelijke temperatuur wanneer het
nieuwe programma wordt toegepast. Apparaatkoppelingen en profielgrenzen blijven
bij een actieve regeling voorlopig zichtbaar maar vergrendeld; hun volledige
profielmigratie is nog open.

Als toepassing niet kan worden bevestigd, blijft het concept behouden en wordt
geen automatische opdracht herhaald. Na opnieuw laden kan de gebruiker het
opgeslagen programma expliciet opnieuw toepassen. De bestaande SOURCE,
credentials, kranen en fysieke bevoegdheden worden niet vervangen. Dit pad
fabriceert geen gekwalificeerde temperatuurbron of fysieke werking. De eerdere
afwijzing van een losse tijdelijke22°C-opdracht blijft afzonderlijk open;
deze versie verklaart of verhelpt die nog niet.

Eén installatie met centrale instellingen en kamers. Nieuwe kamers gebruiken
een wizard; bestaande kamers hebben één direct configuratiescherm met gekoppelde
apparaten, temperaturen en een grafisch weekprogramma met temperatuurblokken.
Apparaatidentiteit, beschikbaarheid en kraangrenzen worden bij de kamer getoond.
Deze versie herkent de officiële Home Assistant-featureflags van een klimaatapparaat
correct; geldige temperatuurgrenzen hoeven daardoor niet onbekend te lijken.

Dev17 herkent Zigbee2MQTT-klimaatapparaten zonder algemeen `state_topic`.
De prefix wordt uitsluitend afgeleid uit zowel de gepubliceerde bridge- als
de exacte apparaatbeschikbaarheid, gekoppeld aan de bestaande apparaatidentiteit.
Ontbrekende, ongeldige en tegenstrijdige gegevens blijven geweigerd. Deze versie
verandert geen apparaatinstellingen of fysieke aansturing.

Dev16 herstelt de uitlezing voor Home Assistants eigen `MQTTDiscoveryPayload`-
object. De regressietest gebruikt nu dat echte native object, ook samen met de
werkelijke HA-MQTT-client en een lokale testbroker. De eerdere dev15-tag en
bestanden blijven behouden; gebruik dev19 voor de actuele apparaatcontrole.

Aanwezig sinds dev15: in het kamerscherm staat onder **Geavanceerde instellingen**
**Apparaatinformatie controleren**. Dit leest uitsluitend op verzoek de laatst
gemelde Zigbee2MQTT-definities voor de opgeslagen sensor en kranen. Doeltemperatuur,
externe temperatuurinvoer, klepstand en converteropties worden apart getoond.
Ontbrekende informatie blijft onbekend. Een diagnostische apparaattemperatuur
krijgt een duidelijke toelichting; die is niet automatisch een gekwalificeerde
kamermeting. Dit is informatie over apparaatmogelijkheden, geen geslaagde fysieke
kraanproef. Er worden geen instellingen, interviews of verwarmingscommando’s verstuurd.
Deze uitlezing gebruikt de bestaande HA-MQTT-verbinding, twee exacte topics en
een korte wachttijd. Andere apparaten en ruwe discovery-/brokergegevens worden
niet naar het scherm gestuurd. Andere apparaatbronnen blijven normaal gekoppeld;
ze kunnen deze specifieke Zigbee2MQTT-uitlezing niet altijd aanbieden.

Ook aanwezig sinds dev14: kies **E32 verbinden** in de centrale integratie-instellingen.
Vul het lokale webadres en beheerderswachtwoord in. De integratie controleert de
werkelijke E32, bewaart de bestaande netwerkinstellingen en synchroniseert het
kamerprogramma via de bestaande verbinding. Alleen ontvangst van een opdracht
is geen succes: de E32 moet de juiste configuratie en actuele kamerstatus teruggeven.
Een eerste koppeling kan de E32 eenmaal herstarten. E32-alpha.9 of nieuwere
compatibele firmware is nodig; het huidige profiel ondersteunt één of twee kamers.
Het beheerderswachtwoord wordt in de bestaande HA-integratie bewaard; cookies en
controlecodes blijven tijdelijk. Gewone kamerschermen en diagnoses exporteren
het wachtwoord niet. Bij een onderbroken koppeling wordt geen bevestigde uitvoering
voorgewend; controleer de installatiestatus voordat je opnieuw probeert.

Dit is een ontwikkelrelease. De normale HA→E32-configuratieketen is met dev14
live bevestigd; de fysieke sensor-/kraan-/ketelproef en verwarmingsvrijgave
zijn nog niet afgerond. Naam, basistemperatuur en lokale weekblokken zijn in
dev18 bij een actieve koppeling bewerkbaar. Apparaten en profielgrenzen wijzigen,
de optionele externe kamerdoelbron, raamcontact en meerdere gekwalificeerde
kraanprofielen blijven vervolgwerk.
De nieuwe E32-firmware wordt afzonderlijk getest en uitgebracht; deze release
bevat uitsluitend de Home Assistant-integratie. Een opgeslagen instelling is
nog geen bevestigde uitvoering op de E32.

Download `OpenThermostat-HA-0.4.0.dev19.zip` en controleer de SHA256 met
`HA-SHA256SUMS.txt`. Maak vóór installatie een back-up van de bestaande
integratie/configuratie. Kopieer `custom_components/open_thermostat` uit de ZIP
naar de Home Assistant-configuratiemap, controleer de configuratie en herstart
Home Assistant. Bestaande gebruikers hoeven de integratie niet opnieuw toe te
voegen. Controleer na herstart versie, kamers, apparaatkoppelingen en programma.
Behoud het vorige pakket als terugvalmogelijkheid.

Dev14 behoudt de bestaande dagelijkse bediening en neemt de eerdere klokcorrectie mee. Voor reproduceerbare proeven
hebben ontvangst, wachtrij en protocol nu één expliciete monotone klokbron;
standaard blijft dat de bestaande HA-loopklok. De tests gebruiken dezelfde
virtuele klok als hun C++-peer, onafhankelijk van hoe lang de testmachine draait.
De proef bewaakt ook dat vertraagde metingen hun echte leeftijd behouden en
op de ingestelde leeftijdsgrens worden geweigerd. Versheidscontroles blijven staan.

De pipeline bouwt beide benodigde C++-testprobes in een schone CI-omgeving.
De mislukte `ha-v0.4.0.dev11`- en `ha-v0.4.0.dev12`-tags blijven behouden;
daarvan is geen release gepubliceerd. Bestaande instellingen en apparaatkoppelingen
blijven bij deze update behouden.
Het pakket bevat `SOURCE.json`, oorspronkelijke projectlicentie en checksums.
Geen live HA-opslag, firmware, ketelvrijgave of apparaatcommando's zijn inbegrepen.
