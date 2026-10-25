# OpenThermostat — slimme verwarming met Home Assistant

Een lokale, open thermostaat voor **regeling per kamer, slimme radiatorkranen en
centrale ketelregeling**, met Home Assistant als bedieningsomgeving en een
BBQKees E32 V2 bij de ketel. Ontwikkeld door **Mark Dielessen**.

Je stelt per kamer in wanneer het warm moet zijn. De regelsoftware bepaalt de
warmtevraag en het gewenste aanvoerwater; de E32 verzorgt de ketelkoppeling.
Hieronder staat welke onderdelen nu bruikbaar zijn, welke al zijn geprogrammeerd
en welke nog op de roadmap staan.

[Downloads](https://github.com/dielessen/open_thermostat/releases) ·
[Mogelijkheden](#alle-mogelijkheden) · [Roadmap](#wat-we-nog-gaan-bouwen) ·
[Screenshots](#screenshots) · [Documentatie](#documentatie)

**Gepubliceerd:** [E32 alpha36](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.36), bron `7ddf341`, en [HA dev48](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev48), bron `70135db3`.
**Geïnstalleerd en gecontroleerd:** E32 alpha36 via één native GitHub-update,
HA48 ongewijzigd. Alle 36 installatiecontroles en 45 afzonderlijke nacontroles slagen:
bron/ELF/web, 31 geserveerde UI-bestanden,86 HA-bestanden en instellingen/programma's/
koppelingen gecontroleerd. Verse back-up nagelezen. Iedere volgende E32-release
vereist opnieuw een bewezen update en aparte nacontrole.
[Installatie en bewijs](docs/modern-thermostat/INSTALLATIE-E32-ALPHA36-20261025.nl.md) ·
[Verplicht updateproces](docs/modern-thermostat/E32-UPDATE-PROCES.nl.md).

**Actuele HA-status:** na de update naar Core **2026.10.4** ziet de laatste
alleen-lezen controle `setup_error` bij dev48. De opstartreparatie is lokaal
uitgewerkt en getest op Core .2/.3/.4, maar nog niet geïnstalleerd: alle
uitvoerbare verbeteringen gaan in één grote bèta, zonder tusseninstallaties.
[Oorzaak en herstelstatus](docs/modern-thermostat/HA-CORE4-OPSTART.nl.md).

**In dezelfde bèta voorbereid:** lokale Bluetoothontvangst voor Shelly BLU H&T
Display en Xiaomi Monitor 3, met EN/NL-apparaatinstellingen, echte
berichtontsleuteling en verborgen sleutels. Dit zijn nog diagnostische
ontvangstwaarden; echte apparaatproeven en vrijgave als verwarmingsbron staan
apart. [Voortgang](docs/modern-thermostat/BLUETOOTH-APPARATEN.nl.md).

Kamerinrichting, weekprogramma's, webinterfaces, passief EMS uitlezen en
Settings → EMS-apparaten zijn beschikbaar. De huidige native inrichting ondersteunt
**1–2 kamers, één radiatorknop per kamer**; acht zones blijft het uitbreidingsdoel.
Tado-configuratie blijft behouden; fysieke OpenThermostat-uitgangen blijven geblokkeerd.

Deze firmwarebundel combineert About na Settings, 60 modelkeuzes, vier originele
extern geladen modelafbeeldingen en gescheiden ESP-/EMS-logging met onafhankelijke
syslogdoorsturing. Een oude open logpagina bewaart de nieuwe bronvinkjes.
Modelkeuze verleent geen extra driver- of zendbevoegdheid; afbeeldingen voor
onzekere groepen blijven leeg. Functionele profielimport blijft op de roadmap.

Voor de gepubliceerde bundel slagen 803 native kerngevallen en 2.356 gerapporteerde HA-tests per ondersteunde Core
slagen. Alle toepasselijke main-/tag-CI en onafhankelijke bron-/pakketcontroles
zijn geslaagd; alle vijf nieuwe publieke downloads zijn exact met hun eigen
tagbuild vergeleken. De normale GitHub-updatepoort accepteert alpha36; de actieve bèta blijft **NOT_READY** voor haar fysieke voorwaarden.

**English:** The latest read-only check reports dev48 in setup_error after Core
updated to 2026.10.4. A tested startup repair and local Shelly/Xiaomi Bluetooth
diagnostics are being prepared in one beta; neither has been deployed.
E32 alpha36 is installed through one native GitHub update; HA48
remains unchanged. All 36 installation checks and 45 separate postchecks pass, including
exact firmware/source/ELF/web identities,31 served UI assets,86 HA component files,
settings, programs, bindings and the fresh backup. Every successor E32 release
requires recorded update acceptance and an independent postcheck. Physical boiler
and valve qualification remains open. Scheduled checks/dashboard notifications
are prepared for the next bundle and are not running in alpha36.

## Alle mogelijkheden

**Beschikbaar** = geleverd in de huidige software voor de genoemde functie.
**Voorbereid** = code aanwezig; aansluiting, gebruikersbediening of praktijkproef
moet nog worden afgerond. **Gepland** = uitbreiding die nog moet worden gebouwd
of gekwalificeerd. Een voorbereide regeling is dus nog geen werkende fysieke
verwarmingsinstallatie.

### Kamers, zones en temperatuurregeling

| Mogelijkheid | Wat je ermee kunt | Status |
| --- | --- | --- |
| Kamerinrichting | Kamers benoemen en sensoren, radiatorkranen, afgiftetype en temperatuurgrenzen kiezen uit HA | **Beschikbaar** voor 1–2 kamers |
| Eigen temperatuur per zone | Per kamer een doeltemperatuur en warmtevraag berekenen; gezamenlijke vraag naar de ketel | **Voorbereid**; fysieke meet-/kraan-/ketelketen nog afronden |
| Hystereseregeling | Verwarmen met een instelbare temperatuurmarge rond het doel | **Voorbereid** in de regelkern |
| PI-regeling | Warmtevraag geleidelijk aanpassen aan temperatuurafwijking en de duur daarvan, met begrensde integraal | **Voorbereid**; dit is PI, zonder D-term van PID |
| Langzame tijdproportionele regeling | PI-vraag omzetten naar lange aan/uit-cycli met minimum aan- en uittijd voor geschikte kleppen | **Voorbereid** |
| Lokaal regelende radiatorkraan | De eigen regeling van de kraan respecteren en daarboven kamerdoel en ketelvraag coördineren | **Voorbereid**; geen tweede concurrerende PI op de kraan |
| Slimme radiatorkranen via HA | Bestaande HA-apparaten selecteren, mogelijkheden controleren en modusconflicten zichtbaar maken | Selectie/controle **beschikbaar**; fysieke doelopdracht en terugmelding **voorbereid** |
| Originele sensor- en kraanberichten | [WSDCGQ11LM-meetberichten](docs/modern-thermostat/ORIGINAL-ZIGBEE-REPORTS.nl.md) en [TV02-datapoints](docs/modern-thermostat/ORIGINAL-TV02-REPORTS.nl.md) onderscheiden van cachewaarden | **HA-ontvangst en diagnose geleverd**; Zigbee-extensions, bronpins en fysieke bronkwalificatie nog afronden |
| Meer zones en kranen | Acht gevalideerde zones, meerdere kranen per kamer en meer merken | **Gepland**; huidige inrichting heeft één kraan per kamer |

Een geselecteerde sensor is nog geen gekwalificeerde regelmeting. De actuele
productieroute voor originele kamermetingen en de fysieke kraanproeven staan nog
open. TV02-modusconflicten zijn al zichtbaar; dit is nog geen volledige
compatibiliteitsverklaring voor iedere TV02-variant.

### Ketel, modulatie en EMS

| Mogelijkheid | Wat je ermee kunt | Status |
| --- | --- | --- |
| Je eigen ketel op Home | Model kiezen onder Settings → Mijn ketel; keuze blijft lokaal bewaard | **Beschikbaar** voor Ecomline Classic/HRC22H. **Geleverd en geïnstalleerd in alpha36:** 60 keuzes met EMS-ESP-productgroepen en officiële ketelvermeldingen; publieke afbeeldingen buiten de ESP. Vermelding kwalificeert geen nieuwe driver. [Catalogus en profielopslag](docs/modern-thermostat/KETELCATALOGUS.nl.md) |
| EMS-ketelgegevens uitlezen | Beschikbare temperaturen, doelen, modulatie en overige gedecodeerde ketelwaarden bekijken | **Beschikbaar**; verse Classic-berichten ontvangen op de E32 |
| EMS-apparaten onder Settings | Ontvangen apparaten, beschikbare entiteiten, bronkwaliteit en ouderdom per afzender bekijken; zoekfilter en open details blijven behouden | **Beschikbaar**, passief en EN/NL; geen actieve scan |
| Classic en EMS Plus | Decoderbasis voor beide protocolfamilies behouden | **Beschikbaar als basis**; velddekking en ondersteuning blijven ketelafhankelijk |
| Datakwaliteit | Zien of een waarde gemeten, afgeleid, verouderd, onbetrouwbaar of niet beschikbaar is | **Beschikbaar** |
| Centrale ketelvraag | Warmtevraag uit kamers samenbrengen en voorwaarden voor verwarmen beoordelen | **Voorbereid**; rekent mee zonder actieve uitvoer |
| Modulerende ketelregeling | Een gewenst aanvoerwaterdoel berekenen op basis van vraag, groepen en grenzen | **Voorbereid**; echte EMS-aansturing nog testen en vrijgeven |
| Weersafhankelijke regeling | Stooklijn en buitenbron gebruiken voor het gewenste aanvoerwater | **Voorbereid**; complete inrichting en uitvoerroute nog afronden |
| Eigen buitensensor / HA-weerbron | Buiteninformatie met expliciete bronkeuze, actualiteit en terugval gebruiken | Bronbasis **voorbereid**; volledige productroute nog afronden |
| Anti-pendelen en hydrauliek | Minimumtijden, minimumlast, groepsgrenzen en voorwaarden voor doorstroming meenemen | Policies **voorbereid**; installatieproeven nog nodig |
| Keteltest en diagnose | Ontvangst, protocol, veldkwaliteit en fouttellers bekijken en meetrapport downloaden | Passieve diagnose **beschikbaar**; actieve proefbediening **voorbereid en geblokkeerd** |
| Tapwater | Ondersteunde tapwatergegevens bekijken; later eventueel modelspecifiek bedienen | Uitlezing **beschikbaar waar ondersteund**; bediening **gepland** |

Een uitgelezen modulatiepercentage is wat de ketel meldt. Een berekend
waterdoel is wat de regelaar wil. **Actief versturen en de werkelijke ketelreactie
zijn nog niet vrijgegeven of bewezen.** De E32-zendfunctie en fysieke uitgangen
blijven in de huidige uitgave geblokkeerd. Het overzicht belooft geen volledige
EMS-ESP-velddekking of ondersteuning voor iedere ketel/converter.

### Programma’s, comfort en slimmer verwarmen

| Mogelijkheid | Wat je ermee kunt | Status |
| --- | --- | --- |
| Weekprogramma per kamer | Temperatuurblokken tekenen, verplaatsen en aanpassen, ook op een aanraakscherm | **Beschikbaar**, inclusief opslaan/toepassen en terugbevestiging |
| Tijdelijk temperatuurdoel en HEAT/OFF | Een kamerdoel of logische verwarmingsstand wijzigen via de native klimaatentiteit | **Beschikbaar als regelintentie**; fysieke uitvoering volgt de actieve regelketen |
| Comfort, eco, weg, vakantie en boost | Programma’s en tijdelijke keuzes met prioriteiten en eindtijden combineren | Logica **voorbereid**; complete huidige gebruikersroute nog afronden |
| Raam-open en aanwezigheid | Warmtevraag aanpassen of blokkeren op basis van HA-context | Logica **voorbereid**; bronkoppeling/inrichting nog afronden; geofencing later |
| Zelflerende kamerregeling | Opwarm- en afkoelgedrag modelleren en begrensde adviezen berekenen | Modellen/opslag **voorbereid**; actieve toepassing en comfortvoordeel nog aantonen |
| Optimum-start | Eerder beginnen zodat een kamer op het gewenste tijdstip warm is | **Voorbereid**; praktijkvergelijking nog nodig |
| Slim uitlopen en stooklijn leren | Restwarmte benutten en de curve gecontroleerd bijstellen | **Voorbereid**; nog niet actief vrijgegeven |
| Zomer- en vorstlogica | Seizoensstand en een begrensd vorstdoel meewegen | **Voorbereid**; fysieke vorstbescherming bij uitval nog niet bewezen |
| Vloerverwarming / gemengde afgifte | Radiatoren en vloergroepen met eigen watergrenzen, kleppen, pomp en menger combineren | Groeps-/regelbasis **voorbereid**; actieve vloerroute en hardwareproeven volgen |

### Home Assistant, inzicht en dagelijks beheer

| Mogelijkheid | Wat je ermee kunt | Status |
| --- | --- | --- |
| Eigen HA-integratie en dashboard | Kamerpagina’s, klimaatbediening, inrichting en weekplanner in één omgeving | **Beschikbaar** |
| Directe Bluetooth-sensoren | Shelly BLU H&T Display ZB en Xiaomi Monitor 3 (MJWSD05MMC, bindkey vereist); lokale ontvangst en EN/NL-instellingen op E32 | **Aangesloten in de ongepubliceerde bètabron**: begrensde diagnoseontvangst, afzonderlijke crypto-/profielkeuze en private sleutelopslag. Echte apparaatacceptatie, acquisitiekwalificatie en kamerregelbron nog open. [Voortgang](docs/modern-thermostat/BLUETOOTH-APPARATEN.nl.md) |
| Directe Bluetooth-kranen | Shelly BLU TRV rechtstreeks koppelen aan E32; extra mogelijkheid naast HA-apparaten | **Onderzocht/gepland**, nog geen driver of praktijkkwalificatie. [Ontwerp](docs/modern-thermostat/SHELLY-BLU-TRV-STANDALONE.nl.md) |
| Zelfstandige E32-modus | Lokale verwarmingskern met eigen bronnen, programma, opslag en bewaking; HA optioneel voor bediening | **Gepland**; expliciet eigendom en fysieke stop-/uitvalacceptatie vereist |
| Bestaande HA-apparaten gebruiken | Sensoren en klimaatapparaten uit HA selecteren, met controle op eenheden, grenzen en stapgrootte | **Beschikbaar**; regelkwalificatie per apparaat blijft nodig |
| Ketelvelden in HA | 69 huidige Classic-velddefinities met bronleeftijd, eenheden en kwaliteit via de bestaande verbinding; modelkeuze begrenst de ontvangst niet | **Beschikbaar** met eigen overzicht en drie historiekaarten. Waarde, eenheid en kwaliteit zijn met de E32 vergeleken; gerapporteerde en afgeleide velden staan apart. [Details](docs/modern-thermostat/BOILER-FIELDS-V1.md) |
| Externe wandbediening | Kamerdoelen vanuit andere bedieningen overnemen zonder terugkoppellussen | Basis **voorbereid**; complete route **gepland** |
| E32-webinterface | Installatie, kamernamen, doelen, berekende vraag en beschikbare ketelwaarden bekijken; open details blijven staan tijdens verversen | **Beschikbaar** |
| Nederlands en Engels / Dutch and English | E32: taalkeuze in menu en bij aanmelden/wifi-installatie. HA: profieltaal voor kamereditor en native vertalingen; vaste opgeslagen dashboardteksten vallen terug op Engels | **Beschikbaar**; Engels is standaard en terugval |
| Uitleg waarom er vraag is | Regelstatus en redenen voor warmtevraag of blokkering zien | **Beschikbaar als diagnosebasis**; echte opdracht-/reactietijdlijn volgt |
| Grafieken, historie en CSV | Temperatuur, vraag, brander/modulatie en tapwater over tijd analyseren | Recorder-overzichten en alleen-lezen CSV-actie **beschikbaar**. In de grote bèta: dag/week/maand tot 31 dagen met NL/EN-bediening; nog niet geïnstalleerd. [Gebruik en grenzen](docs/modern-thermostat/HISTORIE-EXPORT.nl.md) |
| Verbruik, kosten en comfort | Metergegevens en duidelijk gelabelde schattingen combineren | **Deels voorbereid**; echte bronnen/kalibratie en presentatie volgen |
| Systeemlog en syslog | Recente E32-logregels bekijken/filteren/downloaden; langer bewaren op een eigen RFC5424 UDP-collector | **Beschikbaar**; externe syslog staat standaard uit. **Geleverd en geïnstalleerd in alpha36:** ESP/EMS-weergave en onafhankelijke doorstuurkeuze voor beide bronnen. [Gebruik en grenzen](docs/modern-thermostat/LOGGING.nl.md) |
| Meldingen en onderhoud | Diagnose-, batterij- en foutinformatie benutten | Basis **aanwezig**; complete scenario’s en meldingen nog afronden |
| Lokaal en open | Eigen broncode, lokale E32 en koppeling via lokale MQTT-broker; geen verplichte thermostaatcloud | **Beschikbaar**; via HA gekoppelde apparaten blijven afhankelijk van HA/MQTT |
| Beheer en updates | Weblogin, About, uitloggen, herstarten onder Settings, HTTPS-updater en herstelroutes | **Beschikbaar**; normale update behoudt instellingen |
| Gedrag bij uitval | Oude/onbevestigde gegevens afwijzen en sessies, eigenaarschap en deadlines bewaken | Softwarecontroles **aanwezig**; volledige fysieke HA/MQTT/sensor/E32-uitvalproeven nog open |

## Wat we nog gaan bouwen

De volgorde blijft gericht op een werkende eerste ketelbèta. Bestaande
voorbereide functies blijven in de codebasis behouden.

1. **De actieve basis afronden:** originele kamermetingen aansluiten, radiatorkraan
   met verse terugmelding testen en de echte vraag-/afgifteketen verbinden.
2. **De eerste actieve ketelbèta:** de concrete EMS-interface en converterketen
   kwalificeren, daarna een begrensde start-/stopproef met ketelterugmelding.
3. **Het product compleet aansluiten:** centrale instellingen, comfortstanden,
   weersregeling, grafieken en historie via de normale gebruikersinterface afmaken.
4. **Uitbreiden:** meer gekwalificeerde sensoren/kranen, externe wandbediening,
   meerdere kranen per kamer en acht geteste zones; vloerfuncties apart beproeven.
5. **Slimmer optimaliseren:** zelfleren, optimum-start, uitlopen en curveaanpassing
   gecontroleerd activeren en met echte metingen beoordelen.

Meer ketelvelden uitlezen blijft onderdeel van de ontwikkeling; passieve
ontvangst levert alleen de berichten die de installatie daadwerkelijk verzendt.
Er zijn nog geen vaste datums voor deze vervolgstappen.

Het [actuele werkbord](docs/modern-thermostat/WORKBOARD.nl.md) bevat de volledige
31 producteisen en acceptatiechecks. Het [ontwerpplan](docs/modern-thermostat/PLAN.nl.md)
werkt de regeling uit. De [release-inventaris](docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json)
bewaakt de 23 voorbereide onderdelen. Deze detaildocumenten zijn de plek voor de
technische uitvoeringsstatus.

## Screenshots

<details>
<summary>Home Assistant — kamerbediening en weekprogramma</summary>

![Demonstratie van de HA-kamereditor en weekplanner met voorbeeldgegevens](docs/img/screenshots/ha-room-dev24.png)

Demonstratie van de **uitgeleverde dev24-frontend** met voorbeeldgegevens.
Dit is geen live HA-opname; de afbeelding is ook als demonstratie gemarkeerd.

</details>

<details>
<summary>E32 — installatieoverzicht</summary>

![E32-installatieoverzicht met kamervraag, doelen en ketelstatus](docs/img/screenshots/e32-dashboard-alpha18.png)

Echte opname van alpha18. Berekende vraag, ketelmeldingen en vrijgave van
actieve aansturing worden afzonderlijk getoond.

</details>

<details>
<summary>E32 — passieve EMS-ontvangst en Keteltest</summary>

![E32-Keteltest met ontvangen Classic-berichten en veldkwaliteit](docs/img/screenshots/e32-keteltest-alpha18.png)

Echte opname van alpha18 met passief ontvangen Classic-berichten.
Zendfunctie en actieve proefknoppen zijn geblokkeerd.

</details>

## Releases en installeren

Voor de native koppeling zijn Home Assistant met de MQTT-integratie en een
lokale MQTT-broker nodig. Apparaten die via HA zijn gekoppeld blijven van die
diensten afhankelijk.

| Onderdeel | Huidige uitgave | Gebruik |
| --- | --- | --- |
| E32 V2 | [v0.1.0-e32v2-alpha.36](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.36) | Toepassingsupdate via de normale E32-updater |
| Home Assistant | [0.4.0.dev48](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev48) | Afzonderlijk HA-integratiepakket; de firmware installeert dit niet |

Beide pakketten zijn afzonderlijk geïnstalleerd en gecontroleerd, met behoud van
instellingen, weekprogramma, koppelingen en identiteiten. De firmware gebruikt
[bron 7ddf341](https://github.com/dielessen/open_thermostat/commit/7ddf3410666d814850275433d9dddd266e5d83ba),
de HA-integratie [bron 70135db](https://github.com/dielessen/open_thermostat/commit/70135db3c86df1f970265bc426fe5e35729c8261).
De eerste grote bèta is in bewerking; er wordt geen losse alpha37 tussendoor
uitgebracht. [Voortgang en resterende voorwaarden](docs/modern-thermostat/BETA1-UITVOERING.nl.md).

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
