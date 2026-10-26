# Volgende gezamenlijke bèta — concept voor gebruikers

Deze wijzigingen staan klaar in de broncode bovenop E32 beta.1 / HA 0.4.0b1.
De nieuwe gezamenlijke versie is nog niet gepubliceerd of geïnstalleerd.
Fysiek verzenden en automatische ketel-/kraansturing blijven geblokkeerd.

## Nederlands

### Nieuw

- **Ketels kiezen op merk en model.** De keuzelijst is alfabetisch ingedeeld.
  Bestaande opgeslagen keuzes blijven geldig.
- **Uitgebreidere EMS-apparatenpagina.** Bekijk herkenbare apparaatrollen,
  ontvangen productgegevens en versies, en zoek in de entiteit- en telegramreferentie.
  Per apparaat zijn maximaal 64 ontvangen berichttypen zichtbaar. Lees- en
  schrijfkenmerken in de referentie betekenen niet dat iedere functie al werkt.
- **Bluetoothapparaten eenvoudiger toevoegen.** Zoek apparaten in de buurt,
  bekijk naam, adres en signaalsterkte en kies **Dit apparaat toevoegen**.
  Naam en adres worden ingevuld; al opgeslagen apparaten zijn herkenbaar.
  Kies het passende profiel en vul waar nodig een bindkey in. Dit stelt lokale
  ontvangst in; Bluetooth-kraanbediening wordt hiermee niet ingeschakeld.
- **Duidelijkere systeemlogging.** EMS-regels benoemen apparaten, richting en
  berichtnaam. ESP is de standaardweergave; opgeslagen syslogkeuzes blijven behouden.
- **Duidelijker keteldiagnose in HA.** De diagnosedownload onderscheidt niet
  ontvangen, ongeldige en verlopen metingen van verbindingsverlies en bewaart
  oorspronkelijke meettijden. Bij een onbeschikbare sensor vind je de toelichting
  in deze download. Ontbrekende waarden blijven ontbreken; aanmeldgegevens
  worden niet opgenomen.

### Opgelost

- **Bluetoothinstellingen betrouwbaarder bewaren.** ‘Opgeslagen’ verschijnt pas
  na een overeenkomende uitlezing. Bij een mislukte controle blijft het concept
  staan en kun je de opgeslagen instellingen opnieuw laden. Sleutels worden niet
  teruggelezen of automatisch voor een ander profiel hergebruikt.
- **Zoeken en verversen bewaren invoer.** Oude zoekresultaten blokkeren nieuwe
  apparaten niet meer. Volledige namen, conceptinvoer en focus blijven behouden;
  profielwissels wissen een ingevoerde sleutel om verkeerd hergebruik te voorkomen.
- **Updatecontrole herstelt na fouten.** Na een geslaagde controle geldt het
  normale interval van twaalf uur; een mislukte lijstcontrole wordt na een
  halfuur opnieuw geprobeerd. Eerdere resultaten blijven herkenbaar als laatst
  bekende informatie. Installeren en herstarten worden niet automatisch herhaald.
- **Updatebediening bij verbindingsverlies.** Knoppen wachten op een verse,
  geldige status. Vertraagde antwoorden geven geen oude opdrachten opnieuw vrij
  en veroorzaken na paginaverlating geen onverwachte herlaadactie.
- **Betere verwerking van meetgegevens.** Ongeldige kamertemperaturen en
  foutcodes komen niet als geldige HA-meetwaarden of statistiekpunten binnen.
  Ondersteunde geldige waarden, inclusief een echte nul, blijven behouden.
- **EMS-weergave en verwerking verbeterd.** Productversies verschijnen correct
  bij ondersteunde alternatieve berichtindelingen. Berichten worden strenger
  gecontroleerd. De gecomprimeerde referentie verkleint de download; ontvangen
  meetwaarden blijven zichtbaar als die referentie niet laadt.

### Ketelproeven: voorbereid, nog geblokkeerd

Onder **Instellingen → Keteltest** is bediening voorbereid voor een eenmalige
uitlezing van CV-instellingen, een afzonderlijke nulvraagproef en een begrensde
warmteproef. De uitlezing wijzigt geen instellingen en de nulvraagproef kan niet
verwarmen. Het voorbereide warmteprofiel is 40–45 °C, maximaal 60 seconden.
Dit zijn softwaregrenzen; de echte zender, installatie en stopreactie zijn nog
niet vrijgegeven of met deze bron getest.

De proef vraagt telkens nieuwe bevestiging van de opstelling, bruikbare
ketelmetingen en lokaal toezicht. Weggaan uit de pagina beëindigt het lokale
toezicht; terugkeren hervat niets. Een bevestigingsvenster kan geen verlopen
proef herstellen. Een gerapporteerde stop vereist een werkelijk verzonden
nulvraag en passende latere ketelgegevens, inclusief nul gevraagde aanvoer.
Een tijdelijke branderpauze telt daarvoor niet. Het meetrapport bewaart de
ontvangstvolgorde. Een proef met fout kan na bewezen gerapporteerde stop bewust
worden afgesloten; de fout blijft bewaard en een volgende proef vereist herstart.

### Bijwerken en gebruik

Er is nog geen nieuwe download. De definitieve bèta wordt als één gezamenlijke
HA-/E32-release voorbereid, met de normale updatecontrole en nacontrole.
Automatische kamerregeling, blijvend aangesloten zelfleren, BLE-proxy en volledige
functionele EMS-ESP-dekking blijven open. Een ketelprofiel of vinkje schakelt die
functies en de fysieke zendroute niet in. Het eerder gemelde pendelen is niet
causaal verklaard en wordt hier niet als opgelost gemeld.

## English

### New

- **Choose boilers by brand and model.** Alphabetical choices retain existing
  saved selections.
- **Expanded EMS device view.** Recognizable roles, received product information
  and versions, a searchable entity/telegram reference, and up to 64 received
  message types per device. Reference read/write metadata does not mean every
  function is implemented.
- **Easier Bluetooth setup.** Discover broadcast names, addresses and signal
  strength, then choose **Add this device**. Existing entries are marked and
  name/address fields are filled in. Select the profile and enter a bindkey where
  required. This configures local reception, without enabling valve control.
- **Clearer logging.** EMS messages identify devices, direction and message
  names. ESP is the default view; saved syslog choices are retained.
- **Better HA boiler diagnostics.** The diagnostic download distinguishes missing,
  invalid and expired readings from connection loss and preserves original
  observation timestamps. For unavailable sensors, use this download to see the
  explanation. Missing values remain absent; sign-in credentials are not included.

### Fixed

- Bluetooth saves require matching readback. Failed checks preserve drafts and
  allow an explicit reload; keys are not returned or reused across profiles.
- Discovery and refresh retain complete names, draft input and focus. A full
  list of old discoveries no longer hides new devices. Profile changes clear
  typed keys to prevent accidental reuse.
- Automatic release checks recover after failures: twelve hours after success,
  thirty minutes after a failed list check. Earlier results remain last-known
  information. Installation and restart commands are never retried automatically.
- Update controls wait for fresh valid status after connection loss. Delayed
  responses cannot restore old actions or reload a page after leaving it.
- Invalid room temperatures and error codes no longer become valid HA readings
  or statistics. Supported valid values, including zero, remain unchanged.
- Supported alternate EMS version messages display correctly, message validation
  is stricter, and compressed reference data reduces downloads. A reference-load
  failure does not hide actual readings.

### Boiler trials: prepared, still blocked

**Settings → Boiler test** prepares a one-shot heating-settings read, a separate
zero-demand test and a bounded heat trial. Reading changes no settings; a
zero-demand test cannot start heating. The prepared software profile is 40–45 °C
for at most 60 seconds. Physical transmission, the installation and actual stop
behavior remain unqualified for this source.

Each trial requires fresh setup confirmations, usable boiler measurements and
local supervision. Leaving the page ends local supervision; returning or a late
confirmation never resumes it. Reported stop requires an emitted zero demand and
matching later boiler reports, including zero requested flow temperature. A
burner pause alone is insufficient. Downloads retain observation ordering.
A faulted trial can be explicitly closed after proven reported stop; the fault
is retained and another trial requires a restart.

### Updating and use

No new download is available yet. One joint HA/E32 beta is being prepared with
the normal update and independent readback process. Automatic zone control,
fully connected persistent learning, BLE proxy and complete functional EMS-ESP
coverage remain open. Profiles and checkboxes do not enable physical outputs.
The earlier reported cycling has no established cause and is not claimed fixed.

[Volledige eerdere conceptnotities / Previous draft notes](BETA-NEXT-RELEASE-NOTES-HISTORY-20261026.nl-en.md)
