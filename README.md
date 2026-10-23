# OpenThermostat — E32 V2 + Home Assistant

Lokale verwarmingssoftware van **Mark Dielessen**: kamers en weekprogramma’s
in Home Assistant, met een eigen E32-interface voor installatiestatus,
ketelgegevens en beheer.

**Beschikbaar: E32 alpha18 + Home Assistant dev24.** De interfaces, planning,
koppeling, updates en ontvangstdiagnose zijn geleverd. De actieve kamer-/ketelregeling
is nog in ontwikkeling: de E32-zendfunctie en fysieke uitgangen blijven geblokkeerd.

[Downloads](https://github.com/dielessen/open_thermostat/releases) ·
[Functies](#wat-er-nu-in-zit) · [Screenshots](#screenshots) ·
[Roadmap](#wat-er-nog-komt) · [Documentatie](#documentatie)

## Wat er nu in zit

### Home Assistant

- **Eigen OpenThermostat-integratie en dashboard**, met kamerpagina’s en herkenbare
  kameridentiteiten. De opstartregistratie van de kamerkaart is gecorrigeerd.
- **Weekplanner per kamer:** temperatuurblokken tekenen, verplaatsen en aanpassen,
  inclusief bediening van korte blokken op een aanraakscherm.
- **Kamerinrichting:** naam, radiatortype, temperatuursensor, radiatorknop en
  temperatuurgrenzen kiezen uit bestaande HA-entiteiten.
- **Gecontroleerd opslaan en toepassen:** configuratie en programma worden via de
  gekoppelde E32 toegepast en teruggelezen. Een onbevestigde toepassing blijft
  zichtbaar als wachtend en kan expliciet opnieuw worden aangeboden.
- **Klimaatbediening:** tijdelijke kamerdoelen en HEAT/OFF-logica via de native
  klimaatentiteit. Dit verandert de logische regelintentie; fysieke aansturing
  blijft afzonderlijk geblokkeerd.
- **Apparaatcontrole:** beschikbare modellen, eenheden, temperatuurgrenzen en
  stapgrootte; expliciet gemelde Zigbee2MQTT- en converterpakketversies.
- **Meetstatus:** beschikbaarheid in HA en een voor de regeling gekwalificeerde
  meting worden afzonderlijk getoond. Verouderde of onbevestigde metingen krijgen
  geen nieuwe leeftijd door cache, herladen of een andere apparaatbinding.
- **TV02-conflicten zichtbaar:** auto, vakantie, uit en onbekende modus worden
  beoordeeld voordat de voorbereide kraanadapter een doelopdracht kan toestaan.
  De software schakelt de eigen kraanmodus daarbij niet automatisch om.
- **Bestaande klimaat-, diagnose- en batterijfuncties behouden**, voor zover de
  betreffende bronroute de gegevens levert. Onbekende waarden blijven onbekend.

De huidige native configuratieroute ondersteunt **één of twee kamers**, met één
radiatorknop per kamer. Een gekozen sensor of een geaccepteerd temperatuurdoel
bewijst nog geen fysieke kraanwerking. De productiebron voor gekwalificeerde
kamermetingen en de fysieke actuatorproeven zijn nog niet afgerond.

### E32-webinterface

- **Installatieoverzicht** met echte kamernamen, kamertargets, berekende warmtevraag,
  actuele regelstatus en beschikbare ketelwaarden.
- **Settings → Keteltest:** passieve EMS-ontvangst, protocolfamilie, ouderdom en
  kwaliteit van gegevens, fouttellers en een downloadbaar meetrapport.
- **Classic- en Plus-decoderbasis.** Verse Classic-ketelberichten zijn tijdens de
  actuele screenshotopname op de E32 ontvangen. Ondersteuning en betrouwbaarheid
  van ieder afzonderlijk veld en ketelmodel blijven apart te beoordelen.
- **Duidelijke ontbrekende gegevens:** niet beschikbaar, verlopen, afgeleid en
  onbetrouwbaar worden onderscheiden van een geldige gemeten nul.
- **Beveiligd beheer:** webaanmelding, sessie-/verzoekcontrole, netwerk- en
  setup/herstelroutes en interne/PSRAM-geheugendiagnose.
- **About en navigatie:** projectinformatie en oorspronkelijke credits,
  uitloggen rechtsboven en herstarten onder Settings met bevestiging.
- **Normale HTTPS-updater:** versies zoeken, compatibiliteit en checksums
  controleren, en de toepassing bijwerken met behoud van instellingen.
- **Duidelijke releases:** actuele firmware en HA-pakketten bovenaan, oudere
  versies als archief. Eerdere downloadadressen blijven behouden.

De proefbediening voor voorbereiden, starten, toezicht en stoppen is meegeleverd,
maar blijft zonder gekwalificeerde zend-/installatieroute geblokkeerd.
Passieve ontvangst is beschikbaar; actieve ketelaansturing is nog niet vrijgegeven.

## Screenshots

### Home Assistant — kamer en weekprogramma

![Demonstratie van de HA-kamereditor en weekplanner met voorbeeldgegevens](docs/img/screenshots/ha-room-dev24.png)

Lokaal weergegeven demonstratie van de **uitgeleverde dev24-frontend**, met
voorbeeldgegevens en dezelfde kamereditor/weekplanner. Dit is geen live
Home Assistant-opname; het demonstratiekarakter staat ook in de afbeelding.

### E32 — installatieoverzicht

![E32-installatieoverzicht met kamervraag, doelen en ketelstatus](docs/img/screenshots/e32-dashboard-alpha18.png)

Echte opname van alpha18. De interface toont apart wat de regeling berekent,
wat de ketel meldt en of aansturing is vrijgegeven. Ontbrekende kamermetingen
worden niet als een temperatuur van nul weergegeven.

<details>
<summary>Bekijk de E32-Keteltest en ontvangstdiagnose</summary>

![E32-Keteltest met ontvangen Classic-berichten en veldkwaliteit](docs/img/screenshots/e32-keteltest-alpha18.png)

Echte opname van alpha18 met passief ontvangen Classic-berichten.
De getoonde waarden zijn momentopnamen. De zendfunctie en actieve proefknoppen
zijn geblokkeerd; een ontvangstbericht is geen bewijs van fysieke ketelaansturing.

</details>

## Wat er nog komt

Er is al code voorbereid voor onderstaande functies. Wat nog ontbreekt is per
onderdeel de aansluiting op de complete productroute en de vereiste praktijkproef.
Deze tabel belooft geen functies die in de huidige release al actief zijn.

| Onderdeel | Al voorbereid | Nog te leveren of te bewijzen |
| --- | --- | --- |
| Betrouwbare kamermetingen | Bronbinding, identiteit, ouderdom, replay- en uitvalcontroles | Modelspecifieke originele meetrapporten via de volledige HA → E32-keten |
| Radiatorkranen | Profieladapter, modus-, identiteit- en capaciteitscontroles | Verse terugmelding, schema-eigenaarschap, uitvalgedrag en fysieke proef zonder ketel |
| Begrensde ketelproef | Vaste deadline, stopprioriteit, controller/webbediening, gedeelde pollroute en Classic-encoder | Beoordeelde businterface/adressering, echte zender, stopbevestiging en onafhankelijk stopgedrag |
| Meer apparaten en wandbediening | Bindings, normalisatie, selectie- en modelbasis | Meer gekwalificeerde sensoren/TRV-merken, meerdere kranen per kamer en externe doelbediening met echopreventie |
| Meerdere radiatorzones | Kamerregelaars, gezamenlijke vraag en supervisor in shadowmodus | Actieve afgifte-/ketelketen; later opschalen naar het productdoel van acht gevalideerde zones |
| Weersafhankelijk regelen | Stooklijn-, buitenbron-, groepswaterdoel- en begrenzingscode | Normale inrichting, actuele buitenbron, terugval en werkelijke keteluitvoer |
| Vloerverwarming en gemengde afgifte | Groepen, klep-, pomp- en mengerpolicies | Actieve uitvoerroute, verdelerprofiel en afzonderlijke fysieke acceptatie |
| Grafieken, historie en CSV | Metrics-, opslag-/Recordergrens- en exportcode | Echte CV-/tapwatertijdlijn, retentie/migratie, gaten en complete grafiekbediening |
| Zelflerende regeling | Thermische modellen, opslag en replaycontroles | Gekwalificeerde metingen, gecontroleerde aansluiting en aantoonbaar comfortvoordeel |
| Optimum-start en uitlopen | Opwarm-/afkoelmodellen en begrensde adviezen | Praktijkvergelijking van voorverwarmen, uitlopen en curveaanpassing |
| Comfort, eco, weg, vakantie en boost | Prioriteiten, tijdelijke toestanden en contextbasis | Complete gebruikersroute en conflictafhandeling voor de huidige native koppeling |
| Raam en aanwezigheid | Contextbinding en logische zoneblokkering | Actuele sensoren, bronuitval en normale configuratie; geofencing later |
| Anti-pendelen, zomer en vorst | Timing-, minimumlast-, seizoens- en hydraulische policies | Doorstroming, pomp/naloop, tapwatervoorrang en werkelijke bescherming bij uitval |
| Verbruik en kosten | Metrics, export en als schatting gelabelde berekeningen | Echte meter-/kostenbronnen en kalibratie; geen bewezen besparingsclaim |
| Meldingen en tapwater | Diagnose, batterijblueprint en modelspecifieke uitlezing | Geteste foutmeldingen en alleen aantoonbaar ondersteunde tapwaterbediening |
| Herstel bij uitval | Sessies, leases, boot-/stale-controles en update-/herstelroutes | Complete fysieke HA/MQTT/sensor/E32-uitvalmatrix en langdurige stabiliteitsproeven |

De eerstvolgende mijlpaal blijft een **eerste actieve ketelbèta**: de echte
meet-/kraanketen afronden, de installatievoorwaarden vaststellen en vervolgens
ontvangst plus een afzonderlijke begrensde start-/stopproef aantonen.
Daarna volgen verdere zones, vloerfuncties en actieve leerfuncties. Er is nog
geen datum vastgelegd voor deze vervolgstappen.

De volledige status staat in het [actuele werkbord](docs/modern-thermostat/WORKBOARD.nl.md),
met alle 31 producteisen, de resterende acceptatie en de releasechecklist.
De [release-inventaris](docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json)
bewaakt dat alle 23 voorbereide onderdelen in de bronbasis behouden blijven.

## Releases en installeren

Voor de native koppeling zijn Home Assistant met de MQTT-integratie en een
lokale MQTT-broker nodig. Apparaten die via HA zijn gekoppeld blijven van die
diensten afhankelijk.

| Onderdeel | Huidige uitgave | Gebruik |
| --- | --- | --- |
| E32 V2 | [v0.1.0-e32v2-alpha.18](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.18) | Toepassingsupdate via de normale E32-updater |
| Home Assistant | [0.4.0.dev24](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev24) | Afzonderlijk HA-integratiepakket; de firmware installeert dit niet |

Dit softwarepaar komt uit [dezelfde broncommit](https://github.com/dielessen/open_thermostat/commit/6ef01d0e8468f2bb88310d165fb5d49d033b21d4).
De volledige CI slaagt, inclusief drie firmwareboards, native tests,
SDK-bronreproductie, browsers en **1.758 HA-checks**. Bij de gecontroleerde uitrol
zijn instellingen, weekprogramma, bindings en identiteiten behouden.

- [Normale updates, bron en pakketten](docs/modern-thermostat/GITHUB-UPDATES.nl.md)
- [Installeren, back-up en herstel](docs/FLASHING.md)
- [HA-inrichting en beheerde interface](docs/modern-thermostat/HA-MANAGED-GUI.md)

Een normale app-only OTA is iets anders dan een nieuwe partitie-indeling of
fabrieksinstallatie. Gebruik daarvoor de bijbehorende hardware-/installatiegids.

## Hardware en ontwikkelen

Hoofddoel is de **BBQKees E32 V2**, met classic ESP32, 16 MB flash en fysieke
PSRAM. Het is een andere target dan de oorspronkelijke E32 of ESP32-S3.
De oorspronkelijke `esp32dev`- en `esp32s3`-builds blijven behouden; hun
uitgangsmogelijkheden gelden niet automatisch voor E32 V2.
Ethernet-/WiFi- en setupcode zijn aanwezig; fysieke netwerk- en herstelacceptatie
blijft per installatie te beoordelen.

```sh
git clone https://github.com/dielessen/open_thermostat.git
cd open_thermostat
python3 -m venv .venv
. .venv/bin/activate
pip install platformio==6.2.0
pio run -e e32v2
pio run -e e32v2 -t buildfs
python scripts/verify_e32v2.py
pio test -e native
```

Deze opdrachten bouwen en controleren bestanden; ze flashen geen apparaat.
Bouwen voor de andere boards kan met `pio run -e esp32dev` of `pio run -e esp32s3`.
Voer PlatformIO-opdrachten binnen één checkout achter elkaar uit.

## Documentatie

- [Actueel werkbord en roadmap](docs/modern-thermostat/WORKBOARD.nl.md)
- [Ontwerp en alle producteisen](docs/modern-thermostat/PLAN.nl.md)
- [Firmware-releasenotes](docs/modern-thermostat/RELEASE-NOTES.md)
- [HA-releasenotes](docs/modern-thermostat/HA-RELEASE-NOTES.md)
- [E32 V2-hardware en pinnen](docs/BBQKEES_E32V2.md)
- [Hardwareverschillen](docs/HARDWARE.md)
- [REST-interface](docs/RESTAPI.md)
- [Testinfrastructuur](docs/modern-thermostat/TEST-INFRA.nl.md)
- [Historische functies en legacy-instructies](docs/README-LEGACY.md)

## Herkomst en licentie

Dit project is gestart vanuit [OpenThermostat van Pawel Filipczak / intuibase](https://github.com/intuibase/open_thermostat).
De oorspronkelijke auteursrechten en [MIT-licentie](LICENSE) blijven behouden.
De verdere ontwikkeling, productkeuzes en releases worden onafhankelijk beheerd
door Mark Dielessen; dit is geen officiële intuibase-uitgave.

Hergebruikte bibliotheken en SDK-onderdelen behouden hun eigen licenties.
Zie [de bron- en licentiedocumentatie](docs/third-party/README.md) voor de
bijbehorende distributie- en herlinkinformatie.
