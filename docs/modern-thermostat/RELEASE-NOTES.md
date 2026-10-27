# E32 V2 beta6 — integrated room and installation controls
<!-- user-release-notes:v2:en -->

Development bundle. Not frozen, published or installed. Physical boiler and valve
acceptance is separate; beta.5 installation recovery remains deferred.

## New

- One boiler page with an explicit **Read settings → Prepare → Start → Stop**
  workflow. The setup uses one two-minute confirmation covering the read and
  preparation; starting heating remains a separate explicit action.
- One entity table per observed device, identified from its received product
  report. Read-only values and configurable settings are distinguished in the
  same table. The unrelated all-model catalogue and duplicate settings/value
  lists have been removed from the page.
- An explicit **Read device identity** action requests one bounded version
  report when the boiler model is unknown. Opening or refreshing the page never
  sends this bus request. Identity reading is optional for the heating workflow.
- A closed trial shows its restart requirement directly and offers the existing
  confirmed, update-aware restart action. No heating resumes automatically.

- Room **Details** on the E32 dashboard explains the effective target source,
  selected comfort mode, reported temporary duration and explicit UTC vacation end.
  Window/door and presence pauses have clear reasons. It uses the existing
  control snapshot and does not add polling or a second countdown clock.

## Fixed

- Compress larger UI files at build time and serve them directly from flash.
  Private ETags revalidate cached UI bytes after authentication; live readings,
  credentials, operation outcomes and errors remain uncached.
- Load page-specific scripts only when needed. The device panel uses a compact
  model/field metadata file instead of downloading the complete telegram library.
- Reuse a bounded PSRAM buffer for large telemetry JSON responses; allocation
  failure or overflow returns a complete error without partial JSON.
- Share one bounded telemetry GET/poll between boiler controls and device values.
  Leaving the page cancels its subscriptions and pending reads.
- Derive Classic Home/About values directly from the same aged monitor used by
  telemetry and control, retaining the existing JSON units and suppressing stale
  or unreliable values. Generic-board and existing Plus paths remain separate.

- Bound ordinary native MQTT socket writes to one 100 ms total budget, closing
  partial or late frames on the same connection. Existing actuator handoff
  guards remain separate.
- Resolve native MQTT broker hostnames asynchronously on the existing lwIP
  thread. DNS waits no longer hold the HTTP/main loop; retired lookups retain
  bounded callback storage until completion. TCP opening also progresses between
  loop passes with its original deadline, and transfers the same socket into
  MQTT. A peer disappearing at handoff cannot trigger a synchronous reconnect.
  CONNACK/read timing remains separate; firmware-update HTTPS uses a different path.
- Show main-loop interval counters under **System log → Loop timing**, using
  the existing log-status response. These distinguish observed loop delays from
  page-load time. Hidden log pages stop polling; submitted settings writes are
  retained through navigation without automatic replay.
- Avoid building disabled log messages. Web/syslog levels and source selections
  remain independent of serial output; enabled messages retain redaction and
  bounded storage. The periodic route refresh also fails fast if its native
  network mailbox is full.
- Suspend updater status reads while the page is hidden and release them on
  navigation. Submitted install/check commands are not aborted or replayed.

## Updating

A coordinated E32 and HA candidate will be prepared. Publication requires the
existing update acceptance gate; no device update is performed during this work.

## Limitations

No live boiler or valve test, device restart or physical qualification is implied.
Prepared capabilities retain their explicit installation and source requirements.

# E32 V2 beta5 — longer attended boiler trial and clearer diagnostics
<!-- user-release-notes:v2:en -->

Adds an attended ten-minute boiler demand and clearer entity/update controls.
Firmware installation and physical boiler commissioning are verified separately.

## New

- **Ten-minute attended demand.** Prepare 50 °C for 600 seconds to allow time for
  boiler startup. The Classic trial supports 40–50 °C, repeated setpoints and a
  separate 5–<60 °C measured-water cutoff. Fresh setup/gauge checks precede start;
  their declarations remain valid for that finite run. A five-second supervision
  lease, separate Start/Stop actions and later stop feedback remain required.
- **One boiler page.** Boiler test now also contains the settings, received
  devices and values, and telegram reference. The separate EMS devices menu
  entry is removed; existing page links open Boiler test.
- **Visible entity access.** Read-only values, configurable settings and
  commands have distinct labels and filters. The complete pinned EMS-ESP
  boiler catalogue includes all 258 model-dependent definitions, with types,
  options, bounds and E32 implementation status. Catalogue entries do not
  grant write permission or assert support by the connected boiler.
- Boiler-test read and zero-test buttons explain missing setup confirmations,
  unavailable feedback and hot-water operation. Confirmations still apply to
  one read or trial and must be repeated afterwards.
- A blocked heat trial shows the measured flow temperature beside the existing
  trial window. Automatic heating and persistent settings writes remain disabled.
## Fixed

- Update errors distinguish a failed release check from a failed installation.
  Advanced diagnostics separate HTTP responses from local connection, TLS and
  interrupted-transfer errors. Only the allowlisted download host and numeric
  codes are exposed; signed redirect paths and query strings are excluded.

## Updating

No new HA package is required for these E32 changes.

## Limitations

This release does not prove
that the observed GitHub connection failure is fixed, qualify a physical boiler
trial or enable automatic heating, valve control or persistent boiler writes.
No new retries, firmware installation or test command is performed by the UI.

# E32 V2 beta4 — attended boiler trial and Bluetooth discovery
<!-- user-release-notes:v2:en -->

Beta.4 adds attended boiler commissioning and a larger Bluetooth discovery list.
The earlier beta.3 downloads remain available.

## New

- **Scrollable Bluetooth discovery.** Browse up to 128 received devices, including
  unnamed devices and unsupported profiles. The list shows its count, keeps its
  scroll position during polling and warns when full. The eight saved sensor
  bindings remain separate; discovery does not establish profile support.
- **An attended Ecomline Classic commissioning trial.** Read the boiler settings,
  confirm exclusive ownership and a local stop, then prove a zero-demand baseline.
  Starting heat requires a separate action, an open heat path and a new boiler-gauge
  reading of 1.1–2.5 bar. Demand is bounded to 40–45 °C and at most 60 seconds,
  with a five-second supervision lease and an explicit Stop action.

- **Recover access when all four saved sessions are occupied.** Select the
  recovery option on the login page and enter your username and password again
  to sign other browsers out. Device settings are preserved.
- **A boiler illustration even without a model photo.** A local, unbranded
  illustration appears on Home and My boiler when the selected profile has no
  photo or its photo fails to load. Available model photos retain their credits.
- **Heating settings overview on the EMS devices page.** Four prepared Classic
  settings show their received value, status and age, with a mobile layout.
  Missing or expired readings stay blank. Refresh reads the local snapshot;
  it does not query the boiler.

- **Correct pressure requirements for the target boiler.** The Ecomline trial
  profile explains that this installation has no digital pressure sensor. It
  uses a fresh operator-entered mechanical gauge reading for each heat trial,
  valid for at most two minutes. This remains separate from reported telemetry
  and completed physical installation acceptance.

## Fixed

- Abandoned web sessions expire after 30 minutes without accepted authenticated
  requests, rather than occupying a slot for seven days. Communicating dashboards
  keep access for up to seven days. Late requests cannot revive an expired session.
- Login messages describe saved sessions instead of currently open browsers.
  Ordinary login does not sign other browsers out; recovery requires a separate choice.
- A failed model image falls back to the generic illustration and clears the
  unavailable photo's credit.
- Prepared manual boiler diagnostics only count a bus exchange as completed
  when its acknowledgement finishes within the reply window and the transport
  remains available. Delayed processing cannot turn an old reply into a new one.
- Prepared manual tests and settings readback prevent repeated bus completion
  during nested timing or permission checks. A nested call cannot replace the
  current exchange; exceptions release its guard without retrying completion.
- The prepared settings path guards timing and permission checks as part of
  each send, preventing nested processing from sending the same write or read
  request twice. Exceptions release the guard without retrying the request.

- **Prepared boiler diagnostics:** queued settings-read requests are cancelled
  when the operator logs out or the web session expires or is replaced. An
  already-sent read retains its bounded response window, without confirming a
  cancelled acquisition or retrying automatically. The page labels cancellation
  in English and Dutch, clears earlier setup confirmations and keeps new reads
  blocked until the current request finishes. Late status cannot retract a
  known cancellation for the same request. Pressure confirmation appears only
  for test profiles that require it.

## Updating

Update the E32 through its normal GitHub updater. These
changes require no new HA installation; HA 0.4.0b3 remains unchanged. Verify the
new boot, version and retained settings.

Session recovery is unavailable during a boiler trial, firmware update or
unconfirmed firmware boot. Recovery does not require a factory reset.

## Limitations

Automatic boiler and valve control remain disabled. The only enabled boiler
command path is the attended commissioning trial and its one-shot configuration
read. Persistent boiler settings stay read-only in the standard firmware. The prepared four-setting editor and the
EMS-ESP entity reference do not grant write permission or complete EMS-ESP
write support. The trial does not complete physical installation acceptance; its actual
results and the independent stop still need to be recorded on site.

# E32 V2 beta3 — bediening, diagnose en updateherstel
<!-- user-release-notes:v1 -->

## Nieuw

- Alfabetische ketelkeuze op merk/model en een uitgebreidere EMS-apparatenpagina met zoeken in apparaten, entiteiten en telegrammen.
- Bluetoothapparaten zoeken en toevoegen met behoud van conceptinvoer; herkenning van reeds opgeslagen apparaten.
- Duidelijkere ESP-/EMS-systeemlogging en Nederlandse/Engelse uitleg.
- Voorbereide eenmalige CV-configuratie-uitlezing en afzonderlijke afsluiting van handmatige buswisselingen. Deze routes blijven fysiek geblokkeerd.

## Opgelost

- Bluetoothinstellingen bevestigen opslag pas na overeenkomende uitlezing; privésleutels worden niet teruggelezen.
- Updatecontrole probeert een mislukte lijstcontrole na een halfuur opnieuw. Installatie en herstart worden niet automatisch herhaald. Bediening vereist verse status.
- Strengere EMS-berichtcontrole, correcte productversies en kleinere gecomprimeerde telegramreferentie.
- Een actieve ketelproef stelt achtergrond-updatecontrole uit.

## Bijwerken en gebruik

Gezamenlijke kandidaat met HA 0.4.0b3. Werk bij via de bestaande GitHub-updater; controleer na de nieuwe boot versie, bron en instellingenbehoud. Publicatie alleen bewijst geen installatie.

Dit is een passieve bèta: fysieke ketel-/kraansturing en automatische verwarming blijven geblokkeerd. De gebruiker bevestigt dat zijn Ecomline Classic HRC 22H geen digitale druksensor heeft. De huidige warmteproefguard vereist digitale druk nog wel; de modelgebonden aanpassing en passende afzonderlijke drukcontrole zijn nog open. Er wordt geen fictieve drukmeting toegevoegd. Ook zender-, installatie- en stopkwalificatie blijven open.

## English

Adds alphabetical boiler selection, searchable EMS devices/reference, Bluetooth discovery and clearer logs. Fixes verified Bluetooth storage, update retry/status handling and EMS decoding. Prepares bounded configuration reading and manual bus-transaction closure; physical transmission stays disabled.

Pair with HA 0.4.0b3 and verify the new boot and preserved settings. This release does not enable boiler/valve control or automatic heating. The user's boiler has no digital pressure sensor; adapting the existing heat-trial guard and recording an appropriate separate pressure check remain open work.

# E32 V2 beta1 — grote bundel voor ontvangst, bediening en herstel
<!-- user-release-notes:v1 -->

## Nieuw

- **Bluetooth onder Instellingen:** Shelly BLU H&T Display, Xiaomi Monitor 3 en Shelly BLU TRV hebben een eigen diagnoseprofiel. Ontvangst werkt lokaal op de E32. De TRV toont gemeld doel, berekende temperatuur en eventuele externe temperatuur apart.
- **Verborgen sleutels:** bindkeys blijven in aparte privéopslag en worden niet teruggestuurd. Invoer en open details blijven staan tijdens verversen. Uitleg en fouten zijn Nederlands en Engels.
- **Automatische updatecontrole:** iedere twaalf uur, met een dashboardmelding. Een geslaagde controle blijft vijf minuten beschikbaar; installeren blijft een aparte actie.

## Opgelost

- Ongeldige meetwaarden en ontbrekende vochtigheid/gemiddelden worden geen verzonnen nulwaarden. Namen met aanhalingstekens of regeleinden breken de kamerbediening en JSON niet meer.
- De oudere kamerregeling pauzeert netjes als apparaattijd ontbreekt. De klokaanvraag gebruikt een SDK-time-out van 100 ms in plaats van vijf seconden per kamer.
- Bluetooth herstelt na een mislukte scan. Een volle ontdeklijst blokkeert ingestelde sensoren niet; wijziging van een conceptbron toont geen metingen van de oude bron.
- Opslaan bewaakt ruimte voor regelinstellingen en leermodellen. Geheugentekort tijdens laden sluit de opslag netjes af. Een extreme tijdsprong veroorzaakt geen rekenoverloop in het opwarmmodel.

## Bijwerken en gebruik

Dit is één gezamenlijke **softwarekandidaat**, samen met HA 0.4.0b1. Gebruik voor E32 uitsluitend de gewone firmware-updater met `firmware.bin`; instellingen en programma's blijven behouden. De bètabundel controleert ook het updatepad vanaf alpha36 met het echte eindbestand. HA heeft zijn eigen download; optionele oorspronkelijke Zigbee-rapporten krijgen een afzonderlijk bronpakket binnen dezelfde release.

Bluetoothwaarden zijn diagnose, geen gekwalificeerde verwarmingsbron. Pairing, kraanbediening, zelfstandig regelen en de fysieke ketelproef zijn nog niet vrijgegeven. Alle voorbereide regel-/leeronderdelen blijven behouden. [Actuele voorwaarden en voortgang](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-beta.1/docs/modern-thermostat/WORKBOARD.nl.md).

## English

**New:** local diagnostic profiles for Shelly BLU H&T Display, Xiaomi Monitor 3 and Shelly BLU TRV, write-only private bindkeys, preserved form/details, Dutch/English messages, and automatic update checks with a dashboard notice. TRV target, calculated and optional external temperature remain separate.

**Fixed:** invalid/unknown values, quoted room names, unavailable device time, BLE scan recovery, stale draft readings, shared storage reservations, allocation cleanup and extreme model clock arithmetic.

**Updating:** this joint software candidate pairs with HA 0.4.0b1. Use normal app-only E32 OTA; HA and the optional receive-only Zigbee companion are separate downloads. The exact final package must pass alpha36 discovery/image compatibility. Physical boiler/valve control, qualified Bluetooth heating inputs and standalone regulation remain unavailable pending their acceptance. Source preparation does not constitute a physical test.

# E32 V2 alpha37 — ongepubliceerde voorbereiding, opgenomen in beta1
<!-- user-release-notes:v1 -->

## Nieuw

- **De E32 controleert zelf op updates:** iedere twaalf uur, vanaf vijf minuten na opstarten. Downloaden en installeren doe je nog steeds zelf.
- **Update zichtbaar op het dashboard:** bij een nieuwere compatibele versie verschijnt een melding met een knop naar de updatepagina.
- **Sneller opnieuw controleren:** een geslaagde controle wordt vijf minuten hergebruikt. Het dashboard leest de lokale status en vraagt niet zelf GitHub op.

## Opgelost

- Voorbereide Zigbee-ontvangers ruimen fouten bij starten en stoppen beter op. Een herstart kan geen oude en nieuwe ontvanger door elkaar laten lopen.
- Gelijktijdige ontvangst kan geen dubbele publicatie starten. Stoppen wacht ook bij opruimfouten op de lopende publicatie.
- Een automatische updatecontrole wacht zolang een ketelproef actief is.

## Bijwerken en gebruik

Werk bij via de firmware-updatepagina van de E32. Je netwerk, kamers, programma's en loginstellingen blijven behouden. Home Assistant dev48 hoeft niet opnieuw geïnstalleerd te worden.

Dit is een testversie. De ontvangstfixes voegen geen nieuwe sensorkoppeling toe en schakelen geen ketel- of kraansturing in. Na een mislukte automatische controle wordt niet voortdurend opnieuw geprobeerd; handmatig controleren blijft mogelijk.

## English

**New:** automatic release checks every twelve hours after a five-minute startup delay, a dashboard update notice, and a five-minute cache for successful checks. Installation remains manual.

**Fixed:** prepared Zigbee receivers clean up failed startup/shutdown safely and prevent overlapping publications or mixed owners. Background release checks wait during an active boiler test.

**Updating:** use the E32 update page. Settings, rooms, programs and logging preferences are retained; HA dev48 needs no reinstall. This test release does not enable new sensor pairing or physical heating control.

# E32 V2 alpha36 — meer ketelkeuze en betere logging
<!-- user-release-notes:v1 -->

## Nieuw

- **Meer ketelkeuze:** 60 modellen en modelgroepen onder **Instellingen → Mijn ketel**.
- **Ketelafbeeldingen:** bij enkele modellen verschijnt een originele afbeelding met een bronlink. De keuze blijft ook zonder internet beschikbaar.
- **Overzichtelijk systeemlog:** kies alleen E32-meldingen, alleen EMS-berichten van de ketel of beide.
- **Logs langer bewaren:** kies apart welke E32- en EMS-meldingen je naar je eigen logserver (syslog) stuurt.
- **Over sneller bereikbaar:** staat nu direct rechts naast Instellingen.

## Opgelost

- Opslaan vanuit een oudere, nog geopende logpagina zet je nieuwe logkeuzes niet meer terug.

## Bijwerken en gebruik

Werk bij via de firmware-updatepagina van de E32. Je netwerk, kamers en programma's blijven behouden. Home Assistant dev48 hoeft hiervoor niet opnieuw geïnstalleerd te worden.

Dit is een testversie. Een ketelmodel kiezen past de weergave aan; de ketelaansturing is nog niet vrijgegeven. Niet ieder model heeft al een eigen foto; die ontbreekt ook nog voor de Ecomline Classic HRC22H.

## English

**New:** 60 boiler/model-group choices, original images for selected models, separate E32/EMS log views and syslog options, and About directly after Settings.

**Fixed:** saving from an older open log page preserves the new log-source choices.

**Updating:** use the E32 firmware-update page. Network settings, rooms and programs are retained; HA dev48 does not need reinstalling. This is a test release; boiler control remains disabled. Images are not available for every model.

# E32 V2 alpha35 — gezamenlijke HA48-bundel en sensorvoorbereiding

Deze passieve voorbereidingsrelease bundelt alle eerdere functies met HA0.4.0.dev48 en de geteste Shelly SBHT-103C-decoderbasis.

- Pure BTHomev2-parser voor temperatuur, vochtigheid, batterij, licht en afzonderlijke identificatie-/knopvelden. Afgebroken, dubbele, ongeordende, onbekende of ongeldige objecten leveren geen gedeeltelijke meetwaarde op.
- Versleutelde frames leveren alleen een key_required-formaatstatus; geen ontsleuteling, authenticatie of meetwaarden. Broadcastmodelinformatie en pakketteller zijn geen vertrouwde identiteit of nieuwe acquisitie.
- Geen veldcache, dynamische parserallocatie of selectie door de huidige BLE-reader. Settings/onboarding, apparaatsleutels, bron-/replaykwalificatie, Xiaomi Monitor3 en BLUTRV blijven open.
-798native tests,16afzonderlijke decoder-sanitizergevallen en echteESP32-toolchain-syntaxcontrole slagen lokaal. Volledige bevroren builds/CI en werkelijke pakketreviews blijven vereist. De gezamenlijke HA bevat de cleanupcorrectie en de gevalideerde klokfixture.
- Alle23voorbereide onderdelen/31eisen behouden. Bestaande updatercheckpoints, EN/NL-uitleg, bron-/sessie-/deadlinepoorten blijven behouden; productfabriek, ketel-/kraanuitvoer en EMS-TX blijven gesloten.

Geen actieve bèta, fysieke sensor-/kraankwalificatie, opgelost pendelen of gerepareerde oude upload-watchdog claimen. Publicatie is geen installatiebewijs; firmware-update alleen via aantoonbaar beoordeelde herstelbare route.

English: shared HA48/alpha35 maintenance bundle with a strict passive SBHT-103C decoder foundation. The current BLE reader does not select it; encrypted bytes never become measurements, and model/counter declarations never grant physical freshness or authority. Existing updater, settings and output blocks remain. Pairing, keys, physical tests and recovery are separate gates.

# E32 V2 alpha34 — gerichte updaterdiagnose en robuuste HA-opstart

Gezamenlijke bundel met Home Assistant dev47, met behoud van alle 23 voorbereide onderdelen en 31 producteisen. Passieve voorbereidingsrelease; actieve bèta blijft NOT_READY.

- De bestaande begrensde updatejournal bewaart nu vóór checksumcontrole, native imagevalidatie, onafhankelijk flash-readback en bootselectie een afzonderlijke fase.
- De bestaande EN/NL-statuspagina maakt duidelijk dat een opgeslagen "vóór"-fase geen uitgevoerde bewerking, geslaagde installatie of resetoorzaak bewijst. Schema 1 / 164 bytes en oude stagenummers 1–5 blijven behouden; geen chunklogging of nieuwe worker/route/retry.
- Alle verificatiepoorten blijven in dezelfde volgorde verplicht. Een fout, exception of callbackherintrede bereikt geen volgende overdracht of bootselectie. 40 updatergevallen slagen ook onder strikte ASan/UBSan.
- HA dev47 sluit laat herlevende opstarttaken en listeners bij afsluiten/annuleren en beschermt tegen dubbele start. Programma-, Store- en optionele diagnosegrenzen zijn op echte native HA-runtimes getoetst.
- 782 native firmwaregevallen, 24 updaterbrowsergevallen en 2.349 HA-gevallen per ondersteunde Core slagen lokaal. De definitieve exacte CI-/bron-/pakketreviews blijven afzonderlijke releasepoorten.

EMS-TX, forwarding en fysieke uitgangen blijven geblokkeerd. Geschikte oorspronkelijke kamermetingen, causale kraanecho en fysieke start-/stop-/uitvalacceptatie blijven open. Bluetoothdrivers, actieve PID-/leerkwalificatie en overige roadmapdoelen worden niet als voltooid voorgesteld.

Installatiegrens: gerichte checkpoints leveren toekomstig onderzoeksmateriaal, geen herstelbewijs voor de eerdere geïnstalleerde uploaderwatchdog of native HTTPS-afwijking. Handmatige uploads worden niet door deze journal vastgelegd. De eerder waargenomen alpha31-installatiemethode is onbekend; geen blinde nieuwe upload/reboot/HTTPS-proef door deze releaseopdracht. HA kan afzonderlijk worden bijgewerkt met verse back-up en onafhankelijke nacontrole.

English: four bounded persisted pre-operation checkpoints distinguish checksum, image validation, independent flash readback and boot-slot selection. They preserve verification gates and do not imply completion or reset causation. HA dev47 adds single-owner asynchronous startup and bounded optional original-temperature diagnostics. Existing features/settings remain intact. No physical boiler/valve qualification or proven installed-updater recovery is claimed.

# E32 V2 alpha33 — bewaakte callbackgrenzen en oorspronkelijke ontvangstdiagnostiek

Gezamenlijke voorbereidingsrelease met HA dev46; alle 23 voorbereide onderdelen, 31 producteisen en bestaande instellingen blijven behouden.

- De laatste nonblocking overdrachtscontrole heeft een eigen herintredebewaking. Beschikbaarheid en klok bewaken ook hun eigen callbackgrens, zodat dezelfde controle niet via gewone kanaaltoelating kan worden omzeild.
- Geneste callbacks trekken alle betrokken kanaaleigenaren blijvend in. Beschikbaarheidscallbacks kunnen geen extra eigenaar aanmaken. Normale laatste controle binnen de bestaande zendcallback blijft mogelijk.
- Zes nieuwe kanaalgevallen en een aanvullende echte lokale socketproef dekken de herintredepaden. De oude code verstuurt in die socketproef een byte; de gecorrigeerde grens houdt dezelfde socket leeg.
- De meegeleverde HA46-companion voegt begrensde oorspronkelijke ontvangsttellers toe aan de bestaande HA-diagnostiekdownload, zonder extra MQTT-abonnement, worker, opslag of apparaatopdracht.
- Eerdere oorspronkelijke aanvraagcorrelatie, eenmalige grants, gedeelde klok en oorspronkelijke deadlines blijven behouden. Fysieke productautoriteit blijft standaard gesloten.

De firmwareketen is voorbereid, niet fysiek gekwalificeerd. Geschikte oorspronkelijke kamermeting, causale kraanecho, veiligheidsproducenten en fysieke stop-/uitvalproeven blijven open. Serviceacceptatie en ontvangsttellers zijn geen fysieke ACK. Tado blijft regelen; EMS-TX, forwarding en fysieke uitvoer blijven geblokkeerd. De optionele kanaalroute vereist minimaal HA45, de diagnostiekdownloadfunctie HA46.

De eerdere uploaderwatchdog, HTTPS-afwijking en pendeloorzaak worden niet als opgelost voorgesteld. Alpha33-publicatie bewijst geen installatie of herstel van de eerder mislukte route. Geen blinde firmwareherhaling. Shelly/Xiaomi-drivers en volledige PID-/leerkwalificatie blijven roadmapwerk.

English: independent guards at final handoff, availability and shared-clock callback boundaries retire all channel owners on recursion, including reentry from normal admission. A real local socket regression confirms zero-byte refusal. The included HA46 companion adds bounded receive diagnostics without control authority. Product-source/physical feedback qualification and earlier E32 updater recovery remain open; publication is not installation.

# E32 V2 alpha32 — oorspronkelijke kraanaanvraag en bewaakte socketoverdracht

Grotere gezamenlijke voorbereidingsrelease met HA dev45. Alle 23 voorbereide onderdelen, 31 producteisen en bestaande instellingen blijven behouden.

- Complete voorbereide aanvraag/grant/opdrachtketen: eigen aanvraagvolgnummer, oorspronkelijke lokale begintijd, exacte sessie/config/binding en eenmalig grant. Een vertraagd antwoord krijgt geen nieuw tijdvenster.
- Optionele kanaalbedrading op dezelfde MQTT-client en loop. Maximaal acht eigenaren; callbackherintrede, SOURCE-wissel en disconnect trekken in zonder heropbouw of automatische retry. Dit kwalificeert geen achtzone-installatie.
- Eén gedeeld monotone-klokwatermerk en blijvend kleiner deadlineplafond, ook op context- en socketgrenzen. De actuele lokale netwerkstatus telt mee wanneer TCP nog verbonden lijkt.
- Tijdens uitsluitend de expliciete actuatorpublish gebruikt dezelfde socket een nonblocking write zonder SDK-wacht/retry. Partiële, late of mislukte IO trekt eerst alle eigenaren in en sluit de bestaande socket zonder extra MQTT-write. Gewoon shadowverkeer behoudt zijn SDK-pad.
- Native kern, echte C++/HA-workeruitwisseling, strikte sanitizer-/iteratorcontroles en vier echte lokale socketproeven; exacte bron-/tag-CI en pakketcontrole blijven publicatievoorwaarden.

De product-SOURCE-fabriek blijft gesloten. Dit pakket geeft geen kraan-/ketelbevoegdheid, fysieke ACK, afgiftepad of bewezen stopgarantie. Tado blijft regelen. Geschikte oorspronkelijke kamermeting, causale kraanecho, veiligheidsproducenten en fysieke kwalificatie blijven open. De nieuwe aanvraagroute vereist de bijbehorende HA dev45.

De eerdere alpha28-uploaderwatchdog en native HTTPS-fout zijn niet als opgelost geclaimd. Alpha32-publicatie bewijst geen installatie; geen blinde uploadherhaling. Shelly/Xiaomi-drivers en actieve PID-/leerkwalificatie blijven roadmapwerk.

English: combined preparation release with HA dev45: correlated original requests, single-use grants, bounded channel ownership, a shared lifetime clock and nonblocking writes on the existing MQTT socket. Partial/late/failed IO is never retried. Default product authority remains denied; physical feedback/stop qualification and E32 update recovery remain open.

# E32 V2 alpha31 — gezamenlijke M2-bron-, sessie- en transportbundel

Gezamenlijke passieve prerelease met Home Assistant dev44. Behoudt alle 23 voorbereide onderdelen en bestaande instellingen; geen actieve ketelbèta.

- Voorbereide C++-kraanencoder en verzendcontrole bewaken exacte bron/sessie/config/binding, oorspronkelijke aanvraagdeadline en actuele lease. Kortere deadlines kunnen later niet opnieuw groeien; onzekere overdracht krijgt geen automatische retry.
- De echte lokale controller levert een begrensde sessiecontext zonder rechten te vernieuwen of fysieke bevoegdheid te verlenen. Geheugenfouten en intrekking sluiten de eigenaar blijvend.
- HA dev44 verbindt grantaanvragen en opdrachten aan de bestaande native worker en bewaakt ook scope-/offlineverlies vóór de wachtrij. Serviceacceptatie blijft geen kraan-ACK.
- Strikte sanitizerpoorten en echte C++→HA-interoperabiliteit controleren de voorbereide keten; alle eerdere diagnose-, EMS-, UI-, bronkeuze- en uploadcontroles blijven behouden.

De productfabriek selecteert geen fysieke kraaneigenaar. Firmware-MQTT-zendbedrading, geschikte kamerbron, causale oorspronkelijke kraanecho, installatiekwalificatie en fysieke stop-/uitvalproeven blijven open. EMS-TX, forwarding en fysieke uitgangen blijven geblokkeerd; Tado blijft regelen. Nieuwe Shelly-/Xiaomi-Bluetoothdrivers zijn niet als gereed aangemerkt.

Installatiegrens: de eerdere upload via de geïnstalleerde alpha28 gaf een task-watchdogreset waarvan taak/oorzaak nog onbekend is. Alpha31 bewijst geen herstel van die draaiende uploader. Geen blinde OTA-herhaling; behoud instellingen en bepaal eerst een onderbouwde herstelroute. Het eerdere pendelen en de native HTTPS-updaterfout zijn niet als opgelost geclaimd.

English: combined passive prerelease with HA dev44, preserving prepared features and configuration. Adds source/session/deadline fences and native-worker actuator message handling with default-denied physical authority. No active boiler qualification, original valve ACK, new Bluetooth drivers or proven alpha28 uploader recovery. Do not blindly retry the failed installed upload route.

# E32 V2 alpha30 — ketelrapporten, veiligheidsfeiten en uploadcontrole

Gezamenlijke passieve onderhoudsbundel met Home Assistant dev39; alle eerder voorbereide functies blijven behouden.

- Ketelwaarden volgen de oorspronkelijke ontvangstvolgorde per veld. Oudere telegrammen overschrijven geen nieuwe waarden; tegenstrijdige waarden van dezelfde acquisitie blijven onbruikbaar tot een nieuwe meting.
- Veiligheids- en hydraulische feiten herleven niet door herhaling, klokterugloop of het verstrijken van een eerder ongeldige toekomsttijd. Een geldige acquisitie bij uptime nul blijft ondersteund.
- Handmatige app-upload controleert exacte bestandsgrootte, afgebroken overdracht en volledige multipart-afhandeling voordat de opstartpartitie wordt gekozen. Native OTA-handles worden eenmaal afgesloten.
- HA trekt ongeldig geworden ketelwaarden blijvend in tot oorspronkelijke nieuwe ontvangst, ook na een transportfout of update van een andere veldgroep.

Lokaal gecontroleerd: 689 firmwaretests, 11 REST-uploadscenario's en 2195 HA-testgevallen per Core 2026.10.2/2026.10.3. De verplichte release-CI controleert de bevroren bron en pakketten afzonderlijk.

Installatiegrens: de eerdere alpha29-upload eindigde op de geïnstalleerde alpha28 met een task-watchdogreset; de oorzaak is onbekend. Deze bronwijzigingen bewijzen geen herstel van die al draaiende uploader. Geen blinde OTA-herhaling; installatie vereist een onderbouwde herstelroute en controle van de echte bootidentiteit.

EMS-TX, forwarding en fysieke uitgangen blijven geblokkeerd. Actieve bèta, fysieke start-/stopproeven en de nieuwe Shelly-/Xiaomi-Bluetoothdrivers blijven open. Pendelen en native HTTPS-updater zijn niet als opgelost aangemerkt.

English: passive combined maintenance release with ordered boiler field acquisition, persistent retirement of rejected safety facts and HA cached values, and transactional manual upload validation. Existing alpha28 upload watchdog recovery remains unproven; no automatic retry or active heating qualification.

[Actueel werkbord](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-alpha.30/docs/modern-thermostat/WORKBOARD.nl.md).

# E32 V2 alpha29 — gezamenlijke diagnose- en onderhoudsbundel

Bundelt alle voorbereide software met Home Assistant dev38 op bron
`d131c503f42e6b834a0815db8384983a7fc1b46f`.

- Herstel van TV02-ontvangstdiagnose bij laat beschikbare MQTT-metadata.
- Oorspronkelijke sensordiagnose wordt ingetrokken bij gewijzigde/uitgeschakelde native apparaatidentiteit; oude informatie herleeft niet.
- Duidelijke EN/NL-ontvangstmeldingen; frontend v38 behoudt bestaande v35-kaarten.
- Alle 23 voorbereide onderdelen blijven behouden. Geen wijzigingen aan instellingen of opslaglayout.

Passieve onderhoudsrelease: EMS-TX, forwarding en fysieke ketel-/kraanuitvoer blijven geblokkeerd. Actieve bèta, Shelly-/Xiaomi-Bluetoothdrivers en fysieke stop-/uitvalproeven zijn nog niet gereed. Het eerdere pendelen en de native HTTPS-updaterafwijking zijn niet als opgelost aangemerkt.

Alle zeven softwarepoorten zijn geslaagd; 2189 HA-testgevallen per ondersteunde Core-versie, zonder fouten/skips. Installeer alleen het passende app-only firmwarebestand via de bestaande herstelbare route; behoud instellingen en controleer de echte bootidentiteit.

English: combined passive maintenance bundle with HA dev38. Fixes diagnostic source lifetime/startup and preserves older room cards. No active heating or Bluetooth device support is enabled.

[Wijzigingen en resterende voorwaarden in de bron](https://github.com/dielessen/open_thermostat/blob/v0.1.0-e32v2-alpha.29/docs/modern-thermostat/WORKBOARD.nl.md). Het aparte historiebestand in deze bron bevat de eerdere releasegeschiedenis.

# E32 V2 alpha28 + Home Assistant dev37 — stabiele bediening en EMS-apparaten

Gezamenlijke passieve prerelease met alle geteste fixes sinds alpha27/dev36.

- Settings → EMS-apparaten toont werkelijk ontvangen afzenders, product/versie indien bekend en entiteiten met kwaliteit/ouderdom. Nederlands/Engels, zoekfilter en openklapstatus blijven bij vernieuwen behouden. Geen actieve scan.
- Verlopen E32- en HA-sessierechten herleven niet na een teruggaande klok. HA trekt bij een ongeldige monotone klok de sessie en wachtende opdrachten in; herstel vereist een nieuwe transportinstantie.
- Iedere HA-herhaling controleert na wachten opnieuw tijd, lease, SOURCE en de oorspronkelijke wachtrijregistratie. Geen oude opdracht na intrekking of vervanging; oorspronkelijke bytes en deadlines blijven behouden.
- HA-opstart en annulering ruimen eigen resources op zonder een vervangende eigenaar te verwijderen. Te grote numerieke kraanmetadata veroorzaakt geen editorcrash.
- Vertraagde webantwoorden kunnen een nieuwere pagina niet overschrijven of oude scripts uitvoeren. De EMS-tabel hergebruikt rijen en controleert waarden en volgorde.
- Het actuele plan scheidt geïnstalleerd, voorbereid en fysieke acceptatie; de toekomstige stop-/zend-/uitvalproef is concreet beschreven.

Partities en instellingenformaat blijven gelijk. E32-installatie is app-only; HA heeft een apart pakket. Bestaande instellingen, programma's, SOURCE/journal, registry en ontvangstproducent blijven behouden. Frontend dev35/v35 blijft dezelfde versie met dezelfde bytes.

EMS-TX, forwarder en fysieke kraan-/keteluitvoer blijven geblokkeerd; Tado blijft de actieve regelaar. De normale M2-kraanzendroute, geschikte kamerbron en fysieke stop-/uitvalkwalificatie zijn nog open. Het eerdere pendelen en de native HTTPS-updaterafwijking worden niet als gerepareerd geclaimd. Geen blinde herhaling van die HTTPS-route.

**English:** Combined passive maintenance release: EMS device inventory under Settings with EN/NL display, stable filtering/expanded rows, monotonic session fences, current-owner/deadline checks after awaited MQTT sends, reliable HA setup cleanup, metadata validation and stale-navigation protection. Configuration is preserved; boiler/valve transmission remains disabled. No active heating qualification or claimed cycling/HTTPS-updater repair.

# E32 V2 alpha27 + Home Assistant dev35 — gebundelde failsafe en bediening

Bundelt alle voorbereide wijzigingen sinds alpha26/dev34 in één passieve prerelease.

- HA-heartbeat en begrensde naloop bij verbindingsverlies; onbruikbare of verouderde bronmetingen kunnen niet opnieuw geldig worden door herhaalde verwerking.
- Strengere hydraulische feedback: ongeldige deelbewijzen verliezen hun geldigheid; beperkende foutsignalen blijven behouden. Een klokterugloop blokkeert positieve vrijgave.
- Begrensde ketelproeven bewaken stopbevestigingen en vragen opnieuw bewijs na verlopen of tegenstrijdige feedback.
- Persistente, begrensde updatercontrolepunten ondersteunen toekomstige foutdiagnose. De eerdere HTTPS-updatefout is hiermee niet als opgelost aangetoond.
- Logging verwerkt complete gevalideerde pagina's; onzekere opslag blokkeert een automatische herhaling. Ketelinstellingen worden na opslaan onafhankelijk teruggelezen.
- EN/NL-bediening en HA frontend dev35/v35, met duidelijkere verouderde TV02-ontvangst en voorbereide opdrachtcontroles.

Alle geïnventariseerde voorbereide functies blijven meegenomen. Partities en instellingenformaat blijven gelijk; firmware-installatie is app-only. Bestaande configuratie, programma's, SOURCE en ontvangstpins blijven behouden. De normale kraanzendroute en fysieke acceptatie zijn nog open. EMS-TX, forwarder en fysieke uitgangen blijven geblokkeerd, Tado blijft regelen. Geen automatische zendproef of vrijgave voor actieve ketelregeling.

# E32 V2 alpha26 — ESP-diagnose en duidelijke instellingen

Herstelt de ESP-eigen diagnose in de native MQTT-modus, samen met HA dev33.
Alle bestaande voorbereide functies uit alpha24 en de HA-correcties blijven behouden.

- Vrije/minimaal vrije interne heap, grootste vrije geheugenblok, CPU-temperatuur en uptime worden elke 15 seconden via dezelfde MQTT-verbinding verstuurd. De uitgeschakelde RTC-temperatuur blijft onbekend.
- HA dev33 behoudt de bestaande diagnose-identiteiten en trekt de beschikbaarheid na 45 seconden zonder geldige meting in. Een HA-herstart vereist geen E32-herstart.
- De E32-instellingen en het dashboard leggen schaduwmodus in Engels en Nederlands uit: gegevens uitlezen en warmtevraag berekenen, zonder kraan- of ketelopdrachten. EMS-ontvangst en het installatieprofiel zijn geen vrijgave voor fysieke aansturing.
- HA dev33 legt configuratiebevestiging, kraandoelcontroles en berekeningen afzonderlijk uit. Betrouwbare bronmetingen, bevestigde opdrachten en veilig stopgedrag moeten nog afzonderlijk worden afgetekend.

De normale HTTPS-update blijft app-only met dezelfde partities en instellingen.
Home Assistant blijft een apart pakket; de bestaande dev28/v28-kamerkaart blijft gelijk.
De ketelontvangst blijft passief, Tado blijft regelen en alle fysieke uitgangen blijven geblokkeerd.

# E32 V2 alpha24 + Home Assistant dev30 — gebundelde controle- en ontvangstbasis

Bundelt alle voorbereide wijzigingen sinds alpha23/dev29 in één gezamenlijke
passieve kandidaat. Dit is geen actieve ketelbèta of vrijgave van fysieke uitvoer.

- Eindige ketelproeven bewaken te late basis-/stopbevestigingen en behouden hun
  oorspronkelijke deadline bij leaseverlies of fasewisseling.
- De shadow-controller is gekoppeld aan de hydraulische supervisor met afzonderlijke
  bronleeftijden en boot-/eigenaar-/sessiebinding. Een fout hervat niet vanzelf.
  De concrete productiebronnen blijven standaard ongeconfigureerd.
- Logredactie beschermt ook opmaakcodes en lange regels vóór beide logsinks.
  De EMS-encoder weigert te grote frames en ongeldige READ-payloads.
- HA dev30 voegt read-only supervisordiagnose, strengere levensduur van wachtende
  kraandoelen en privé installatiepins voor oorspronkelijke TV02-ontvangst toe.
  Onzekere gedispatchte kraanacties krijgen geen automatische vervolgopdracht.
- Het Ecomline-profiel bewaart de actuele passieve veldreview en afzonderlijke
  Recorder-waarneming. Drie variërende temperatuurvelden zijn kandidaten voor
  verdere validatie; geen claim van gekalibreerde meting of continu zes uur bewijs.
- Het installatiedraaiboek bevat back-up, versiecompatibiliteit, bronpins,
  afzonderlijke Z2M-producentinstallatie, ontvangstacceptatie en beperkte terugval.

Bestaande dashboardverversing, logging/syslog, EN/NL-bediening, modelkeuze,
69 ketelvelddefinities, weekplanner en instellingen blijven meegenomen.
Instellingenformaat en partitie-indeling blijven gelijk; de normale HTTPS-update
is app-only. HA blijft een apart pakket met dezelfde dev28/v28-frontendbytes.

De openbare bronlijsten blijven leeg. Een privébestand of extension installeren
verleent geen meet-/flow-/klep-/aansturingskwalificatie. De update wisselt geen
sensor, kraanmodus, programma, SOURCE-eigenaar of syslogbestemming. EMS-TX,
forwarder en fysieke uitgangen blijven geblokkeerd; Tado blijft de actieve regelaar.

# E32 V2 alpha23 + Home Assistant dev29 — logging en stabiele bediening

Alpha22 bleef een niet-gepubliceerde kandidaat: de openbare native loggertest
vereiste een expliciete cstdint-header bij de vendorcompilatie. Die testbuild is
hersteld; de bestaande tag blijft behouden.

Gezamenlijke passieve testrelease met alle voorbereide wijzigingen sinds
alpha21/dev27. Geen vrijgave voor actieve ketel- of kraanaansturing.

- E32: systeemlog in Settings, met niveaus, modulefilter, pauzeren, downloaden
  en lokaal wissen. Begrensde RAM-opslag; geen logarchief in flash.
- E32: optionele RFC5424 UDP-syslogserver met IPv4-adres, poort, eigen niveau
  en markeringen. Instellingen worden pas na NVS-readback toegepast.
  Extern loggen staat standaard uit; bestemming en ontvangst blijven lokaal
  in te stellen en te controleren. Zie LOGGING.nl.md.
- E32-dashboard: meetwaarden verversen zonder open details, toetsenbordfocus,
  scrollpositie of de ketelillustratie opnieuw op te bouwen. Statusverzoeken
  overlappen niet; verbindingsfouten laten de pagina staan met een melding.
- HA dev29: oorspronkelijke TV02-datapointontvangst via de bestaande native MQTT-
  lifecycle, met expliciete bronpins, ouderdoms- en identiteitscontrole.
  De kamerpagina toont beschikbare oorspronkelijke rapporten in English of
  Nederlands, inclusief gerapporteerd doel, eigen kraantemperatuur, programma,
  verwarmingsstop en vorstbeveiliging. Ontvangst bewijst geen opdrachtbevestiging,
  klepstand of geleverde warmte. Standaard bronpins blijven leeg: zonder apart
  beoordeelde bron en extension verschijnen geen oorspronkelijke rapporten.
- HA-editor krijgt een eigen dev28/v28-identiteit zodat een oude browserkaart
  de nieuwe weergave niet kan overschrijven. Oude handmatige kaarten blijven
  compatibel. Geen nieuwe polling of automatische kraancommando's.

De app-only HTTPS-update gebruikt dezelfde partitie-indeling en behoudt bestaande
instellingen. HA is een afzonderlijk pakket; de firmware installeert dit niet.
Eerdere ketelprofielen, modelonafhankelijke ontvangst, 69 voorbereide velddefinities,
EN/NL-bediening en configuratie-/programmastructuren blijven behouden.

Fysieke bron-/kraan-/zendinterface-/start-stopkwalificatie blijft open. E32 EMS-TX,
forwarder en fysieke uitgangen blijven compile-time geblokkeerd. Deze release
verandert geen meetselectie, weekprogramma, SOURCE-eigendom of syslogbestemming.

# E32 V2 alpha21 — profiel Nefit Ecomline Classic HRC 22H

Settings → My boiler bevat nu het afzonderlijke profiel Nefit Ecomline Classic
HRC 22H, het door de gebruiker bevestigde exacte model. Home toont de volledige
naam en bestaande familie-illustratie. De oudere generieke Classic-keuze blijft
bewaard en geldig. Opslaan en oorspronkelijke NVS-readback zijn voor beide
identiteiten getest; de opslagmelding volgt English/Nederlands.

Het bronprofiel bewaart de waargenomen gerapporteerde kandidaatvelden, met apart
vermelde afgeleide activiteit en nog niet fysiek bewezen bruikbaarheid. Een
modelkeuze begrenst nooit de EMS-ontvangst en kiest geen busadressen, limieten of
zendmodus. Alle eerdere uitlees-, taal- en interfacecorrecties blijven behouden.
E32-TX en fysieke uitgangen blijven geblokkeerd; geen actieve ketelbèta-vrijgave.

# E32 V2 alpha20 — volledige passieve meetrelease met HA dev26

Bundelt alle alpha19-voorbereiding: native Classic-ketelvelden, EN/NL-bediening,
ketelprofiel en diagnose. HA dev26 herstelt bovendien de bestaande v2-sensoren
in de productinstallatie via de gevalideerde native MQTT-cache. Een ontbrekende
standaardheader in de native BLE-test is expliciet toegevoegd voor een schone
CI-build. Alpha19 is niet live geïnstalleerd; historische tags worden behouden.

De normale app-only update behoudt instellingen en dezelfde partitie-indeling.
EMS-TX en fysieke uitgangen blijven geblokkeerd. Geen actieve ketelbèta-vrijgave.

# E32 V2 alpha19 — ketelvelden naar HA en tweetalige bediening

Gezamenlijke passieve update met HA dev25. De bestaande native MQTT-verbinding
publiceert nu alle 69 voorbereide Classic-velddefinities met oorspronkelijke
rapportleeftijd, kwaliteit en eenheden. Dat maakt geldige ontvangen ketelvelden
zichtbaar in HA; niet ontvangen, verlopen of onbetrouwbare waarden worden niet
als werkende meting voorgesteld. Een modelkeuze begrenst de ontvangst nooit.
Deze decoderdekking is geen maximum voor andere EMS-ketels.

Meegeleverd: English/Nederlands met onthouden E32-browserkeuze, aangevulde HA-
vertalingen, Mijn ketel met lokale illustratie, uitgebreide berichtdiagnose en
alle eerdere voorbereide correcties. De gewone app-only HTTPS-update behoudt
netwerk, SOURCE, kamers en programma’s en gebruikt dezelfde partitie-indeling.

E32-zenden en fysieke ketel-/kraanuitgangen blijven geblokkeerd. Dit is een
gebundelde uitleesupdate, geen vrijgave van de actieve ketelbèta. De echte
meetproducent-, kraan-, zendinterface- en stopacceptatie blijven apart.

# E32 V2 alpha18 — gezamenlijke ontvangst- en diagnose-release

Deze release bundelt de voorbereide bronwijzigingen met HA dev24. Settings → Keteltest toont ontvangstdiagnose, ouderdom en beschikbare ketelwaarden en biedt een downloadrapport. Originele UART-ontvangsttijden blijven behouden. De begrensde proefpolicy, gedeelde pollroute, Classic-encoder en SDK-zendcontroles zijn meegeleverd als geblokkeerde voorbereiding.

E32 EMS-zenden en aanvullende GPIO-uitgangen blijven compile-time geblokkeerd. De proefbediening verleent geen verwarmingsvrijgave. Echte meetrapportproducent, fysieke kraanacceptatie, zendinterface en onafhankelijk stopgedrag blijven open. Deze release is bedoeld voor de volgende passieve praktijkcontrole, niet als afgeronde actieve ketelbèta.

Normale app-only HTTPS-update, met behoud van instellingen en dezelfde partitie-indeling. Alle eerdere update-, web-, About-, dashboard- en sessieverbeteringen blijven behouden.

# E32 V2 alpha17 — gebundelde update- en webverbeteringen

Deze release hoort bij de gezamenlijke testbatch met Home Assistant dev23.

- De automatische updater vindt de recente alpha-releases via een begrensde tagindex, controleert vervolgens de echte openbare release, assets, het compatibele manifest en de broncommit. Annotated tags worden alleen indien nodig opgelost. De bestaande catalogusroute blijft als terugval beschikbaar.
- Ingebouwde webbestanden krijgen een expliciete GET-route met de bestaande authenticatie. Hiermee verdwijnt de misleidende seriële melding `request handler not found` voor correct geleverde webpagina's en bestanden; echte onbekende routes blijven een 404.
- Het dashboard kan de werkelijke kamernamen uit de toegelaten HA-sessie tonen, inclusief UTF-8. De labels zijn begrensd en veranderen geen opgeslagen regelplan, meetbewijs of uitgangsbevoegdheid.
- De in alpha16 geleverde interne/PSRAM-geheugendiagnostiek en eerdere HTTPS-geheugencorrecties blijven behouden.

App-only update via de normale HTTPS-updater; bestaande instellingen en partitie-indeling blijven behouden. Testrelease voor BBQKees E32 V2 met dual-app/SPIFFS-layout. Geen fabriekswisactie of filesystem-upload nodig. E32-uitgangsblokkades en de bestaande afzonderlijke fysieke acceptatievoorwaarden blijven gelden.

# E32 V2 alpha16 — geheugen uitlezen tijdens normaal apparaatbeheer

De bestaande statusroute meldt nu vrij geheugen, de SDK-minimumtellers en het grootste vrije geheugenblok afzonderlijk voor intern RAM en PSRAM. Deze informatie blijft daarmee ook beschikbaar in HA-beheerd bedrijf, waar de oude MQTT-apparaatreporter bewust niet wordt gestart. Dit voegt geen tweede MQTT-client of regelaar toe.

De tellers zijn uitlezingen van de gepinde SDK. De minimumtellers gelden sinds boot volgens de SDK en zijn geen afzonderlijke 72-uurs- of harde real-timekwalificatie. HTTP-reactietijden zijn apart op het bestaande apparaat gemeten als netwerkbaseline; er wordt geen snelheidswinst geclaimd.

De native CI logt voortaan testnamen en een stacktrace bij langdurig wachten, met dezelfde tijdslimiet en ongewijzigde releasegates. De meegeleverde HA-bron is dev22; de firmware installeert geen HA-component.

# E32 V2 alpha15 — navigatie, About en releasebeheer

Sign out staat rechts in de bovenbalk, ook op mobiel. Restart device staat onderaan Settings en behoudt de bevestiging. About beschrijft OpenThermostat en Mark Dielessen als ontwikkelaar, met oorspronkelijke auteur- en bibliotheekcredits in een uitklapbaar onderdeel.

De werkende HTTPS-updater uit alpha14 blijft behouden. Na publicatie worden actuele downloads en archieflabels automatisch bijgewerkt. De meegeleverde HA-bron is gelijk aan dev20; deze firmware-update installeert geen HA-component.

Dit is een experimentele firmware-update met behoud van bestaande instellingen. Hardware- en langdurige acceptatie blijven afzonderlijk open.

# E32 V2 alpha.14 — explicit inactive-task allocator guard

The scoped TLS allocator now explicitly requires a registered, non-null updater
task before querying or matching the current task. Outside an active updater,
the original SDK allocator is always used, including early initialization.
This small follow-up also supplies a subsequent normal app release for actual
alpha.13 in-device HTTPS download/install verification. No live verification
is assumed by these notes. The TLS-memory fix and all restrictions below remain.

# E32 V2 alpha.13 — external memory for verified HTTPS updates

The real updater trace reports FFFFBD70 (-0x4290). The pinned mbedTLS source
combines RSA_PUBLIC_FAILED (-0x4280) and MPI_ALLOC_FAILED (-0x0010): memory
allocation failed during certificate signature verification. This is not
proof of an untrusted root. The pinned SDK reserves internal RAM for TLS.

Only the temporary HTTPS updater task now requests its TLS allocations from
PSRAM, following the SDK external-memory allocation policy. A scoped linker
wrapper selects that task; all other tasks retain the original SDK allocator.
The SDK free function supports both heaps. No global allocator or SDK binary
is replaced. A changed SDK memory configuration fails the build for review.
External allocation failure stops the connection; it never consumes internal
heap as fallback. Response buffers are also explicitly bounded in PSRAM,
and converted to JSON text only after TLS teardown. The older default malloc
could already place large buffers externally; that change alone was not
accepted as a fix. Alpha.12 was an unpublished intermediate candidate.

Certificate/hostname verification, approved redirects, release/manifest checks,
image SHA, native image validation, flash readback, previous valid slot and
normal boot confirmation remain required. Settings, filesystem and partitions
are unchanged; physical heating outputs remain blocked. Keep EMS disconnected.

Native tests and complete release CI are required. Actual board HTTPS discovery
and a subsequent verified in-device update must still establish physical
acceptance; this release does not assume success from compilation alone.
Use only firmware.bin for app-only updates; do not erase or upload SPIFFS or
the factory image. Retain existing settings and programs.

# E32 V2 v0.1.0-e32v2-alpha.11 — testkandidaat

De updatecatalogus controleert alle maximaal twaalf releaseberichten voordat
hij de twee laatst gepubliceerde passende firmwareversies aanbiedt. De echte
GitHub-lijst plaatste alpha.10 na9,8en7; eerder stopte de controle al bij9en8.
Publicatietijd wordt alleen gebruikt als geldige UTC-datum. Per release blijven
de vaste hosts, passende manifesten en alle bestaande download-/image-/readback-
controles vereist. Een fout later in de scan levert geen gedeeltelijke toelating.
De meegeleverde HA-bron bevat de afzonderlijk uitgebrachte dev17-correctie.

De toelatingsdiagnostiek van alpha.10 blijft aanwezig; er is geen automatische
commandoherhaling of verruiming van grants, replaycontrole of fysieke uitgangen.
De eerdere22°C-afwijzing is nog niet verklaard. De alpha.10-HTTP-upload werd
verbroken; een echte readback bevestigde alpha.9 met ongewijzigde configuratie.
Die uitval is niet door deze cataloguscorrectie opgelost. Instellingenformaat,
partities, fysieke voorwaarden en open herstelacceptatie blijven behouden.

# E32 V2 alpha.10 — bounded command-admission diagnostics

Experimental bench-test candidate. The normal HA connection/configuration path
is live-verified, while a subsequent 22°C command was rejected. Its precise
admission reason has not yet been established; this release adds observations,
without changing admission rules or enabling heating.

- Rejected envelope acknowledgements include a static `rejection_reason` from
  the existing admission decision. No grant token, private setting or secret hash
  is added to diagnostics.
- The existing authenticated state snapshot optionally includes the most recent
  user-command admission: binding, sequence, received revision/time and outcome.
  This bounded RAM record clears when the session/owner is invalidated. It is
  neither an execution receipt nor a measurement timestamp or durable state.
- Expired grants, changed duplicates and other rejected commands still cannot
  execute. Diagnostics never retry a command, refresh a grant or change a
  watermark. Qualified measurements, hydraulic commissioning and physical output
  rights remain separate and unchanged.
- Settings/update schemas and partitions are unchanged. Current HA16 sources
  accompany this firmware source commit; no HA installation is performed by OTA.

Use the immutable CI app-only release with current configuration/source/plan
before-and-after checks. Cold/power-loss/USB recovery and physical acceptance
remain open. The earlier live command failure is not declared fixed by adding
its diagnostic field.

# E32 V2 alpha.9 — conditional device settings for Home Assistant linking

Experimental bench-test candidate. Physical boiler/TRV/GPIO authority is unchanged.

- Authenticated device-settings reads return an opaque random ETag associated
  with this boot, browser session and the complete saved settings. The private
  settings digest stays on the controller; broker/weather secret hashes are not
  exposed as ETags.
- A settings POST with `If-Match` is rejected with HTTP412 before merging or
  saving if another edit changed the settings or the session/readback expired.
  Unquoted, weak, wildcard, combined and other-session tags are rejected. Existing
  local forms remain compatible; cookie, origin, CSRF and update guards remain.
- This is the firmware prerequisite for the normal Home Assistant connection
  step under development. It does not itself install that integration flow,
  select a room profile, validate measurements or enable heating.

Use the immutable CI release assets, app-only with private before/after snapshots.
Cold/power-loss/USB recovery and physical room/boiler acceptance remain separate.

# E32 V2 alpha.8 — bounded OTA upload headers and updater stack

Experimental bench-test candidate. Keep EMS disconnected; physical outputs remain
blocked until the existing commissioning checks pass.

- Authenticated multipart app/filesystem uploads no longer append three security
  headers for every chunk. The final response emits them once; cookie, origin,
  CSRF and updater-busy checks still run for each chunk and the final route.
- Flash SHA readback uses a separate non-inlined 1 KiB scratch frame, keeping its
  buffer out of the updater's TLS/download frame. Exact image length, board marker,
  streamed SHA, native validation, whole-image flash SHA and boot selection remain
  required. This bounds stack use; it does not establish the cause of the earlier
  alpha.6 manifest-stage reset.
- Alpha.7 was installed app-only on the development E32 and its published
  source/UI/ELF identities, confirmed boot and saved settings/program were verified.
  Its GitHub install attempt had reset to idle; local upload installed it but
  exposed the duplicate headers. These observations are not acceptance of alpha.8
  or proof of cold recovery, physical TRV operation or boiler heating.

Publish only through the existing full CI/release pipeline. Upload only the exact
published `firmware.bin`; preserve filesystem/settings and the previous valid slot.

# E32 V2 alpha.7 — controller status and separate firmware release discovery

Experimental bench-test candidate. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This candidate is not approved for heating.**

- Authenticated controller status distinguishes compiled graph/controller
  contracts and limits from the active configuration and physical permissions.
  A compiled capability does not enable runtime control or certify a device.
- The managed web interface presents controller status without requiring a
  restart for ordinary display refreshes. The complete heating dashboard and
  end-to-end HA→E32→acknowledgement/TRV acceptance remain follow-up work.
- Firmware discovery searches up to twelve bounded GitHub release pages for
  at most two compatible E32 app releases. Home Assistant releases, drafts,
  missing firmware assets and incompatible manifests are skipped. A transport
  failure preserves the previous list. The image, board/layout, hash/readback
  and boot-selection checks are unchanged.
- Home Assistant integration packages have separate `ha-v…` releases. Installing
  an HA ZIP does not update this firmware or enable physical heating control.
- The complete release kit supplies pinned vendor source/notice archives,
  exact application source and objects, an offline relink recipe, and evidence
  that both original and deliberately modified Arduino libraries link. Required
  CI independently reproduces all 629 reviewed open SDK/runtime compilation
  units. The vendor binary-only archives retain their original provenance and
  notices; this is a target-specific distribution check.

## Candidate and update status

Release downloads are produced from the same clean source commit as their
firmware and embedded UI identity. Publication requires the current source,
relink and SDK reproduction evidence and all build/package checks. Source-only
`sources-e32v2-…` releases are not firmware updates. These notes do not claim
physical installation or acceptance.

After a verified firmware release is published, use the existing device updater
or upload only its `firmware.bin`. The web interface is embedded in the app.
**Do not erase flash, install the factory image or upload SPIFFS for this update.**
Preserve a private settings backup and the previous immutable alpha.6 release.
Verify firmware/source/UI identity, settings, network health and recovery after
installation. Software and simulated-browser checks do not prove physical
update/recovery behavior or qualify the bathroom sensor/TRV control chain.
