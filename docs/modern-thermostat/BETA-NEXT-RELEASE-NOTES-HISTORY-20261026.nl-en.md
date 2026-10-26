# Eerdere conceptnotities - archief van 26 oktober 2026

# Volgende gezamenlijke bèta — concept voor gebruikers

Deze verbeteringen zijn in broncode voorbereid bovenop de geïnstalleerde
E32 beta.1 / HA 0.4.0b1. Er is nog geen nieuwe versie gepubliceerd of geïnstalleerd.

## Nieuw en verbeterd

- **Meer uitleg bij ontbrekende ketelwaarden in HA.** De kenmerken van een
  ketelsensor laten zien of een meting nog niet is ontvangen, ongeldig of verlopen
  is, of dat de verbinding ontbreekt. Een ontbrekende waarde wordt geen nul.

- **CV-instellingen eenmalig uitlezen.** De keteltestpagina kan na vrijgave van
  de zendroute de ontbrekende CV-instellingen opvragen. Je ziet of het verzoek
  nog wacht of de ketel heeft geantwoord. De actie verandert geen instelling,
  start geen warmte en wordt niet automatisch herhaald.

- **Duidelijker meetrapport voor ketelproeven.** Het downloadrapport bevat nu
  de gebruikte nulvraagreferentie en de oorspronkelijke ontvangsttijd van
  meetvelden. Daardoor kunnen we achteraf de volgorde controleren. Dit is
  softwarediagnose en geen bevestiging dat de ketel fysiek is gestopt.

- **Ketelkeuze op merk en model.** Een alfabetische merkenlijst vervangt de
  gemengde technische groepen. Bestaande opgeslagen keuzes blijven geldig.
- **Uitgebreidere EMS-apparatenpagina.** Herkenbare apparaatrollen en ontvangen
  productidentificatie, plus een doorzoekbare EMS-ESP-referentie met lees- en
  schrijfkenmerken en uitleg van waargenomen telegrammen.
- **Meer telegrammen zichtbaar.** Per apparaat blijven maximaal 64 verschillende
  telegramtypen beschikbaar, binnen een vaste geheugenlimiet.
- **Duidelijkere logging.** EMS-logregels benoemen apparaten, richting en
  telegramnaam. ESP is de standaardweergave; bestaande opgeslagen bronkeuzes
  voor syslog blijven behouden.
- **Kleinere firmware en minder downloaden.** De EMS-referentie wordt gecomprimeerd
  geleverd. Ontvangen meetwaarden blijven zichtbaar als de referentie niet laadt.

## Opgelost

- **Buswisseling netjes afsluiten.** Na een passend ketelantwoord sluit de
  handmatige proefroute de communicatie één keer af. Een afgewezen schrijfopdracht
  wordt als fout gemeld. Dit schakelt de proef niet automatisch in en geldt niet
  als bevestiging dat de verwarming is gestopt.

- **Handmatige proef wacht op de UART.** Als er al ontvangstdata wacht, de
  bufferstatus onbekend is of TX nog bezig is, wordt de poging nu geweigerd
  voordat de zendpin wordt gekoppeld. De laatste controle blijft ook gelden.

- **Proefcommando exact gecontroleerd.** Het uiteindelijke bericht moet nu
  precies dezelfde bestemming en aanvoerwaarde hebben als de toegelaten
  proefopdracht. Ook een afwijkend bericht met geldige checksum wordt geweigerd.

- **Extra controle vóór handmatige ketelcommando’s.** De laatste UART-grens
  weigert een beschadigde checksum vóór de zendpin wordt gekoppeld. Deze
  softwarecontrole geeft de fysieke ketelproef niet automatisch vrij.

- **Bevestigen na een onderbreking.** Een bevestigingsvenster kan geen verlopen
  proeftoezicht omzeilen. Na bevestiging worden de proef en toestemming opnieuw
  gecontroleerd voordat een verzoek wordt verstuurd. Dit geldt ook voor de
  nulvraagvoorbereiding en het afsluiten van een proeffout.

- **Proeftoezicht bij tabbladwisselen.** Ook kort weggaan beëindigt het lokale
  toezicht. Een laat voorbereidingsantwoord kan dit niet herstellen. Terugkeren
  start niets opnieuw; Stop blijft beschikbaar en de server bewaakt zijn lease.

- Ongeldige interne EMS-opdrachten worden geweigerd vóór er verzendbytes worden
  gemaakt. EMS+-leesverzoeken met overtollige bytes worden niet meer gedeeltelijk
  geaccepteerd. Geldige berichten blijven ongewijzigd.

- De product-ID en versie van sommige EMS-apparaten verschenen niet correct in
  het log. Apparatenlijst en logging gebruiken nu dezelfde controle op complete
  versieberichten, inclusief de alternatieve indeling.
- Het direct lezen van een te kort EMS-fragment kon buiten het bericht lezen.
  Alle veldbreedtes worden nu ook bij directe payloadtoegang gecontroleerd.
- Negatieve protocolwaarden worden expliciet en consequent omgezet; de
  hexweergave gebruikt vaste opslag in plaats van een variabele stackbuffer.
- Ongeldige kamertemperaturen en foutcodes worden geen HA-meetwaarden of
  statistiekpunten. Geldige waarden, inclusief een echte nul, blijven behouden.

## Wat nog openstaat

Een referentievermelding is nog geen nieuwe decoder of werkende schrijfopdracht.
Volledige EMS-ESP-functionele dekking, echte bron-/kraan-/ketelkwalificatie en
normaal aangesloten leren blijven open. Deze bronverbeteringen schakelen geen
fysieke uitgangen in. De definitieve bundel krijgt opnieuw een bronfreeze,
volledige releasecontroles en een eigen update/nacontrole.

## English

- **Clearer diagnostics for unavailable boiler values in HA.** Sensor attributes
  distinguish measurements that have not arrived, are invalid or have expired
  from connection loss. Missing readings never become zero.

Prepared for the next joint beta; not published or installed yet.

- The manual trial path now closes a matching bus exchange once and reports
  rejected write replies as a fault. This enables no physical output and does
  not prove that heating has stopped.
- A one-shot heating-settings read is prepared on the boiler-test page. After
  transmit-path qualification, it requests the missing configuration and shows
  whether it is waiting or has received a boiler response. It changes no
  settings, starts no heat demand and never retries automatically.

- Boiler choices are grouped by brand and model, preserving saved selections.
- EMS devices show identified product families and searchable entity/telegram
  references, including read/write metadata. Up to 64 observed types per device.
- Named EMS logs and an ESP default view; existing syslog selections are preserved.
- Compressed reference data reduces firmware/download size; reference failures
  do not hide actual readings.
- Shared device-version decoding fixes alternate-version diagnostics. Bounded
  field access, explicit signed conversions and fixed-size hex formatting harden
  EMS processing. Invalid room temperatures no longer enter HA measurements.

Complete driver/write parity and physical heating/learning qualification remain
open. No physical output is enabled by these changes.

## Bluetoothapparaten eenvoudiger toevoegen / Easier Bluetooth setup

- **NL:** Zoek apparaten in de buurt en kies **Dit apparaat toevoegen**. De uitgezonden naam, het Bluetoothadres en de signaalsterkte zijn zichtbaar; naam en adres worden automatisch ingevuld. Al toegevoegde apparaten worden gemarkeerd. Controleer het profiel, voer voor versleutelde sensoren de bindkey in en sla op. Een apparaat zonder uitgezonden naam blijft herkenbaar aan zijn adres. Verversen bewaart invoer en focus. Deze instelling is lokale ontvangst; kraanbediening wordt hiermee niet ingeschakeld.
- **EN:** Discover nearby devices and choose **Add this device**. Broadcast names, Bluetooth addresses and signal strength are shown; name and address are filled in automatically. Existing entries are marked. Check the profile, enter the bindkey for encrypted sensors and save. Devices without a broadcast name remain identifiable by address. Refreshing preserves drafts and focus. This configures local reception and does not enable valve control.

Names supplied by advertisers are untrusted hints, not proof of model or identity. Discovery remains bounded to 32 entries; the old address-only API field is preserved. These changes are prepared in source and are not installed on the E32 yet.

## EMS message validation / EMS-telegramcontrole

**EN:** Invalid internal EMS commands are rejected before generating transmit
bytes. EMS+ read requests with trailing bytes are rejected instead of silently
ignoring those bytes. Valid supported messages retain their exact wire format.
This is software validation, not approval or execution of boiler control.

## Bluetoothzoeken en profielwissel / Bluetooth search and profile changes

- **NL:** Een nieuwe toegelaten zoekopdracht vernieuwt de lijst in de buurt,
  zodat een volle lijst van 32 oude adressen nieuwe apparaten niet blijft
  verbergen. Opgeslagen apparaten blijven behouden. Een volledige naam wordt
  niet vervangen door een verkorte naam of uitsluitend spaties. Bij een nieuw
  versleuteld apparaat blijft de bindkeyinvoer zichtbaar na een profielwissel;
  een ingevoerde sleutel wordt bij die wissel gewist om verkeerd hergebruik
  te voorkomen. Verversen bewaart de overige conceptinvoer.
- **EN:** An admitted new search refreshes the nearby list so a full list of
  32 older addresses cannot keep hiding new devices. Saved devices are kept.
  Complete names are preserved over shortened or blank advertisements. New
  encrypted devices retain visible key entry after a profile change; a typed
  key is cleared on that change to prevent reuse for a different profile.
  Refreshing preserves other draft fields.

These changes remain source preparation; no pairing or installation was performed.

## Betrouwbaarder opslaan / More reliable saving

- **NL:** Bluetoothinstellingen krijgen pas de melding ‘opgeslagen’ na opnieuw
  uitlezen en vergelijken van apparaatadres, naam, profiel, versleuteling en
  sleutel-aanwezigheid. Bij een mislukte of afwijkende uitlezing blijft het
  concept staan, wordt de ingevoerde sleutel gewist en is opnieuw opslaan
  geblokkeerd tot de gebruiker de opgeslagen instellingen herlaadt. Een
  weggevallen verbinding leidt niet tot automatisch opnieuw schrijven.
- **EN:** Bluetooth settings are confirmed saved only after an independent
  readback matches the address, name, profile, encryption and key-presence
  fields. Failed or mismatching readback preserves the draft, clears typed
  keys and blocks further writes until an explicit reload. Connection loss
  does not trigger an automatic write retry. Deferred requests cannot start
  after leaving the Bluetooth page.

No key bytes are returned by the settings API. Public readback confirms key
presence, not a physical key match; reception diagnostics remain separate.

## Updatecontrole herstelt na fouten / Update checking recovers after errors

- **NL:** Een mislukte automatische controle van de releaselijst wordt na een
  halfuur opnieuw geprobeerd. Na succes blijft de normale termijn twaalf uur.
  Eerdere resultaten blijven als laatste bekende informatie beschikbaar, maar
  gelden na een nieuwe of mislukte controle niet meer als verse cache. Na een
  mislukte installatie haalt ‘Controleren op updates’ de lijst opnieuw op.
- **EN:** Failed automatic release-list checks retry after 30 minutes; successful
  checks retain the normal 12-hour interval. Earlier results remain as last-known
  information but are not reused as fresh cache after another attempt or failure.
  Checking after a failed installation fetches the release list again.

This retries discovery only. Firmware installation, reboot and rollback are
not retried automatically. Existing startup, readiness and active-test guards
remain in force. The schedule stays in RAM and does not periodically write flash.

## Updatestatus bij verbindingsverlies / Update status during connection loss

- **NL:** Updateknoppen wachten op een verse, geldige status na netwerkverlies,
  onvolledige antwoorden of een opdracht. Vertraagde oudere antwoorden kunnen
  geen knoppen opnieuw vrijgeven. Na paginaverlating veroorzaakt een laat
  herstartantwoord geen onverwachte herlaadactie.
- **EN:** Update actions wait for fresh validated status after connection loss,
  incomplete responses or a command. Older delayed responses cannot unlock
  controls, and a late post-reboot response cannot reload a page after leaving it.

BLE proxy range extension has been added to the roadmap (HA route plus a
separate standalone relay). It is planned, not implemented in this candidate.

## Proefzendpad bij fouten / Commissioning transport failures

- **NL:** Een fout in de encoder, zender, klok of veiligheidscontrole ontsnapt niet
  meer uit de proefpoll. Een onbekende verzenduitkomst wordt niet als levering of
  stop bevestigd; positieve vraag wordt ingetrokken en hervat niet vanzelf.
- **EN:** Exceptions in the commissioning encoder, writer, clock or condition
  callbacks are contained. Unknown delivery is not reported as successful delivery
  or confirmed stop; positive demand is retired and does not resume automatically.

This is source hardening, not an enabled or physically qualified transmitter.

## EMS Classic-polls en zendvoorbereiding / EMS Classic polling and transport preparation

- **NL:** De E32 herkent nu de juiste pollrichting voor Classic-ketels, nadat
  een geldig ketelbericht is ontvangen. Een antwoordbyte wordt niet als nieuwe
  poll gezien. Ook is een aparte Classic-zendroute met begrensd wachten op echo
  voorbereid. Fysiek verzenden blijft geblokkeerd; dit is nog geen uitgevoerde
  ketelproef of vrijgave voor automatische regeling.
- **EN:** The E32 now recognizes Classic boiler polls after receiving a valid
  boiler report, without treating acknowledgement bytes as new polls. A separate
  Classic transport with bounded echo waiting is prepared. Physical transmission
  remains blocked; this does not qualify boiler operation or automatic control.

## Updatepagina herstelt bij vastgelopen antwoord / Recovery from stalled status responses

- **NL:** Als de statusinhoud tijdens een updatecontrole blijft hangen, stopt
  het wachten na10seconden. De bedieningsknoppen blokkeren tot opnieuw een
  geldige status binnenkomt. Installatieopdrachten worden niet automatisch herhaald.
- **EN:** A stalled update-status response now times out after10seconds. Controls
  remain blocked until a fresh valid status arrives. Installation commands are
  never retried automatically.

## Afzonderlijke nulvraagproef / Separate zero-demand test

- **NL:** Nieuwe, afzonderlijke nulvraagproef onder Keteltest. Deze kan nooit
  verwarmen en wacht op een latere gemelde stop. Voor een warmteproef is nieuwe
  voorbereiding nodig. De fysieke zender blijft geblokkeerd zolang de
  installatie en koppeling niet zijn beoordeeld.
- **EN:** A separate zero-demand test cannot start heating and waits for a later
  reported stop. A heat test needs new preparation. Physical transmission stays
  blocked until the installation and transmitter binding have been reviewed.

## Strengere controle van de zendroute / Stricter transmit-path checks

- **NL:** De voorbereide Classic-zendroute vergelijkt ontvangen echobytes met de
  verzonden bytes. Bij een afwijking stopt het versturen van de resterende bytes.
  De ontvangstwachtrij telt die echo’s niet opnieuw als nieuwe berichten.
  Een juiste echo geldt niet als bevestigde ketelreactie; de fysieke zender
  blijft geblokkeerd tot de installatie en koppeling zijn beoordeeld.
- **EN:** The prepared Classic transmitter checks each echo against the sent
  byte and stops the remaining bytes on a mismatch. Consumed echoes are not
  counted again as incoming telegrams. A matching echo is not a confirmed
  boiler response; physical transmission remains blocked pending review.

## Afzonderlijke handmatige zendroute / Separate manual transmit path

- **NL:** De voorbereide ketelproef gebruikt nu een eigen zendroute. Die geeft de
  oude automatische opdrachten en forwarding niet vrij. Na iedere poging wordt
  de zendpin weer losgekoppeld; een gemelde herstelfout blokkeert verdere pogingen.
  De route blijft uit tot het proefprofiel en de installatie zijn beoordeeld.
- **EN:** The prepared boiler trial uses a separate transmitter without enabling
  legacy automatic commands or forwarding. The TX pin is disconnected after
  each attempt; a reported release failure blocks further attempts. The route
  remains disabled pending review of the trial profile and installation.

## Busadrescontrole voor de proef / Trial bus-address checks

De handmatige ketelproef controleert of het beoordeelde zendadres bij de
waargenomen busidentiteit past. Een ontvangen adresconflict blokkeert verdere
pogingen en is zichtbaar in de statusdiagnose. Dit geeft nog geen zendvrijgave.

Manual boiler trials check the reviewed sender address against the observed bus
identity. An observed address conflict blocks further attempts and appears in
status diagnostics. This does not enable transmission.

## Opstelling voor iedere proef / Setup for each trial

Voor een ketelproef bevestig je opnieuw dat de andere regelaar is losgenomen en
je de ketel zelf kunt uitschakelen. Een warmteproef vraagt daarnaast het
beoordeelde open afgiftepad. De vinkjes worden niet opgeslagen of automatisch
hergebruikt. Het voorbereide eerste nulvraagprofiel kan geen verwarming starten.
Een nulvraagproef kan niet meer overlappen met een firmware-update.

Before each boiler trial, confirm again that the other controller is disconnected
and you can switch off the boiler yourself. A heat trial also requires confirmation
of the reviewed open heat dissipation path. These checkboxes are not saved or
reused automatically. The prepared initial zero-demand profile cannot start
heating. Zero-demand trials can no longer overlap a firmware update.

Het eerste Classic-proefpad gebruikt nu expliciet het serviceadres0x0B met
controle op het waargenomen bronmasker. De ontvangsttermijnen houden rekening met
de gebruikelijke tien seconden tussen snelle Classic-ketelrapporten.

The initial Classic trial path now explicitly uses service address0x0B and checks
the observed source mask. Reception timing accommodates the normal ten-second
interval between fast Classic boiler reports.

## Proef na een fout afsluiten / Closing a faulted trial

Zodra een verzonden nulvraag en verse ketelgegevens een stop bevestigen, kun je
een proef met fout bewust afsluiten. Je bevestigt ook dat de verwarming ter
plaatse is gestopt. De fout wordt bewaard en een nieuwe proef vereist een
herstart. Een afgehandelde proeffout houdt het normale updateproces daardoor
niet onnodig geblokkeerd. Er start geen automatische update of warmtevraag.

After a transmitted zero demand and fresh boiler data confirm a stop, you can
explicitly close a faulted trial and confirm locally that heating has stopped.
The fault is retained and another trial requires a restart. A closed trial no
longer unnecessarily blocks the normal update process. No update or heat demand
starts automatically.

De stopcontrole vraagt nu ook een terugmelding van nul gevraagde aanvoertemperatuur.
Een tijdelijke branderpauze bij blijvende warmtevraag geeft de proef daardoor niet
vrij. Dit geldt vóór verwarmen, bij stoppen en na een fout.

Stop checks now also require a reported zero requested flow temperature. A burner
pause with demand still present cannot release the trial. This applies before
heating, when stopping and after a fault.

## Begrensde warmteproef voorbereid / Bounded heat trial prepared

Het softwareprofiel voor de Ecomline Classic-proef is nu ingevuld:40–45°C en
maximaal60seconden. De proefpagina toont ook de grenzen voor gemeten watertemperatuur
en druk, de uitgelezen ketelinstellingen en waarom een controle blokkeert.
Druk-/temperatuurverlies blokkeert verdere warmtevraag; een stopnul blijft mogelijk.
De aparte installatie- en zendvrijgave staat nog uit. Een ketel kiezen of vinkjes
zetten kan die vrijgave niet veranderen.

The Ecomline Classic software trial profile now specifies40–45°C and at most60seconds.
The trial page also shows measured-water-temperature and pressure limits, checked
boiler settings and why a check blocks. Loss of valid pressure or temperature
blocks further heat demand while allowing withdrawal with zero demand. Separate
installation and transmit approval remain disabled; selecting a boiler or ticking
checkboxes cannot change that approval.

### Manual test supervision / toezicht bij handmatige proeven

EN: Leaving the test page, even briefly, ends local supervision. A delayed
preparation reply cannot restore it, and returning never resumes a test. Stop
remains available. Previously sent requests cannot be recalled; the server
continues to enforce its operator lease.

NL: De firmware is hiermee niet fysiek vrijgegeven. Browserbewijs is geen
bevestiging dat de ketel werkelijk is gestopt.

EN: This does not physically qualify the firmware. Browser evidence does not
confirm that the boiler has actually stopped.

EN: Manual trial confirmations now recheck the current session, visibility and
supervision before sending a request. A confirmation cannot restore authority
lost while the dialog was open. Canceling sends no request.

EN: Boiler measurement downloads now include the current zero-demand reference
and original field observation timestamps on the same boot clock. This helps
review report ordering; it does not prove physical boiler shutdown.

### Compatibiliteit opnieuw gecontroleerd / compatibility rechecked

NL: De bestaande HA-functies en firmwarekoppeling zijn opnieuw gecontroleerd
op Home Assistant Core 2026.10.2, 2026.10.3 en 2026.10.4. Alle tests slagen.
Dit is broncontrole voor de volgende gezamenlijke bèta; er is nog niets
geïnstalleerd en de ketelsturing is niet fysiek vrijgegeven.

EN: Existing HA features and firmware interoperability have been rechecked
on Home Assistant Core 2026.10.2, 2026.10.3 and 2026.10.4. All tests pass.
This checks source for the next joint beta; it is not an installation or
physical approval of boiler control.

EN: The manual boiler UART boundary now rejects a bad checksum before attaching
the transmit pin. This software check does not grant physical trial approval.

EN: The final manual boiler frame must exactly match the admitted destination
and flow demand. A different request with a valid checksum is still rejected.

EN: Manual trials now reject known pending RX, unknown buffer state or busy TX
before attaching the transmit pin. The final receive check is retained.
