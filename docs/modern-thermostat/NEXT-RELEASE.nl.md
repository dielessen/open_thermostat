# Onderhoudsrelease HA dev43 — E32 alpha30 blijft beschikbaar

Bijgewerkt: 24 oktober 2026. Dit is het korte releaseoverzicht.
Het [werkbord](WORKBOARD.nl.md) bevat de enige actuele checklist en prioriteiten;
het [masterplan](PLAN.nl.md) bewaart alle 31 producteisen en acceptatievoorwaarden.

## Eerdere gezamenlijke bundel dev39 / alpha30

De gezamenlijke bundel bevat alle bronwijzigingen sinds dev38/alpha29:
transactionele handmatige app-upload, intrekking van verworpen veiligheidsfeiten,
veldgebonden ontvangstvolgorde van ketelrapporten en blijvende HA-cache-intrekking.
689 firmwaretests en 2195 HA-testgevallen per ondersteunde Core-versie zijn lokaal
geslaagd. Alle drie definitieve CI-runs zijn geslaagd, beide tags gepubliceerd
en alle negen openbare downloads vergeleken. HA39 is geïnstalleerd en de afzonderlijke
nacontrole van 18:54 UTC is geslaagd. De oude alpha28-uploader blijft een
herstelpunt: nieuwe broncode bewijst geen reparatie van de eerdere watchdogreset.

## Geleverd in HA43 — bronkeuze en voorbereide ontvanger

B04/B05/B10: gesloten HA-ontvangertoelating met oorspronkelijke vijfseconden-grants,
exacte scope en zonder replay, plus directe EN/NL-bronkeuze-uitleg in de kamereditor.
De ontvangstkern is niet door de normale fabriek geselecteerd; afzender/leasebinding,
causale echo en fysieke kwalificatie blijven open. Frontend v41 behoudt v38/v35.
[Details en bewijs](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

## Geleverde HA40-release

B05/M2: de Profile-C-kraanadapter trekt zijn eigenaar blijvend in bij
klokterugloop of ongeldige tijd, vóór en na serviceafhandeling. 14 nieuwe
regressies; alle 141 gerichte tests en 2209 volledige gevallen op beide
Core-versies geslaagd. Gepubliceerd en geïnstalleerd op bron `a01bc68`;
afzonderlijke nacontrole van 19:28 UTC geslaagd. Geen fysieke vrijgave. De normale FW→HA-route en echte
doelterugmelding blijven open. [Uitwerking](M2-KRAAN-KLOK-20261024.nl.md).

## 1. Wat draait er nu?

| Onderdeel | Geïnstalleerd | Stand |
| --- | --- | --- |
| E32 | `v0.1.0-e32v2-alpha.28`, bron `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f` | Passief EMS uitlezen; TX, forwarding en fysieke uitvoer geblokkeerd |
| Home Assistant | `0.4.0.dev43`, bron `97eb9a03f7968dd043e6542979a4815887e9704b` | Geladen op Core 2026.10.3; frontend dev41/v41 met v38/v35-aliases |
| Actieve regelaar | Tado | Geen automatische ketel- of kraansturing door OpenThermostat |

Bron/pakket/ELF/web, alle 84 HA-bestanden en behoud van instellingen, programma's
en identiteiten zijn gecontroleerd. Zie [installatieverslag](INSTALLATIE-HA43-20261024.nl.md).
De uitgebreide geleverde bundel staat in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

### Actuele installatie — 24 oktober, nacontrole 21:17:50 UTC

HA dev43 geladen; 84 bestanden exact publieke ZIP/Git, verse HA40-back-up van
93 bestanden en één normale Core-herstart. Alle 38 afzonderlijke nacontroles
slagen. Instellingen, programma’s, SOURCE, registry en bronpins behouden; alleen
twee eigen kamerkaarten gaan van v38 naar v41. E32alpha28 niet gewijzigd;
nul uploads/herstarts, TX/polls/testframes nul. 2281 testgevallen per Core,
zeven softwarepoorten en definitieve tag-CI geslaagd; vier downloads bytegelijk.
[Installatieverslag HA43](INSTALLATIE-HA43-20261024.nl.md).

### Historische HA39-installatie — nacontrole 18:54 UTC

HA dev39 geladen; 83 bestanden exact, verse gecontroleerde back-up van 93 bestanden,
één normale Core-herstart. E32alpha28 en alle instellingen/koppelingen behouden;
geen E32-upload of herstart. Uitgangen geblokkeerd, TX/polls/testframes nul.
Afzonderlijke nacontrole geslaagd; zie [installatieverslag](INSTALLATIE-HA39-ALPHA30-20261024.nl.md).

### Historische installatiecontrole — 24 oktober, na 17:07 UTC

HA dev38 exact geladen; E32 blijft alpha28 na één mislukte alpha29-upload.
Resetcode 6 bevestigt een task-watchdogreset, maar taak en oorzaak zijn onbekend.
Geen herhaling uitgevoerd. Instellingen en verse 93-bestandenback-up zijn
onafhankelijk gecontroleerd; alle uitgangen blijven geblokkeerd.
[Actuele installatie-uitkomst](INSTALLATIE-HA38-ALPHA29-20261024.nl.md).
Eerdere alpha28/dev37-installatie hieronder blijft historische basis.

## 2. Geleverde inhoud van alpha28 / HA dev37

| Onderdeel | Wat verandert er? |
| --- | --- |
| Settings → EMS-apparaten | Per ontvangen afzender identiteit indien bekend, telegramtypen en entiteiten met waarde/kwaliteit/ouderdom; EN/NL, zoekfilter en behouden openklapstatus |
| E32-klokbewaking | Verlopen grant/lease kan bij teruggaande klok niet herleven; ook diagnostische lezingen gecontroleerd |
| HA-klokbewaking | Ongeldige/teruggaande monotone klok trekt sessie, wachtende opdrachten en bewijzen in; oude rechten herstellen niet door reconnect |
| Herhalen na vertraagde verzending | Deadline/lease en SOURCE opnieuw controleren na wachten; geen herhaling van ingetrokken of vervangen opdrachten, geen heartbeat op verlopen sessie |
| HA-opstart en annulering | Vroege fouten ruimen eigen resources op; een oude setup verwijdert geen nieuwe eigenaar |
| Kamereditor | Te grote numerieke kraanmetadata wordt afgewezen zonder editorcrash |
| Webnavigatie | Vertraagde pagina-antwoorden kunnen een nieuwere pagina niet overschrijven of oude scripts uitvoeren |
| EMS-tabel | Bestaande rijen hergebruikt, adressen correct geordend, waarden gecontroleerd en getallen volgens EN/NL weergegeven |
| Keteltestplan | Concrete volgorde en criteria voor toekomstige stop-, zend-, naloop- en uitvalproeven |

**Gepubliceerd, geïnstalleerd en gecontroleerd.** Bron `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f`,
2167 HA-tests op beide echte Core-versies zonder fout/skip, alle zeven softwarejobs
geslaagd. Openbare pakketten, live HA-bestanden en echte E32-boot apart gecontroleerd.
Bewijs: `out/combined-dev37-alpha28-20261024/FINAL-REVIEW.json`.

Alle 23 voorbereide onderdelen met 252 actuele bronverwijzingen blijven in de
[release-inventaris](BETA1-RELEASE-INVENTARIS.json). Bestaande regeling,
supervisor, groepen/vloer/menger, historie/CSV, comfort en leren blijven behouden.
Hun ontbrekende verbindingen en fysieke acceptatie staan op het werkbord.

## 3. Wat doen we hierna?

| Volgorde | Werk | Gereed wanneer |
| --- | --- | --- |
| P0 vóór actieve M2 | Eerdere incidentele CI-kamerassertie causaal verklaren | Definitieve regressies en herhaalproeven slagen; oorspronkelijke afwijking nog niet causaal verklaard |
| P0 vóór fysieke proef | Gemeld pendelen verklaren en passieve nulmeting beoordelen | Oorzaak of concrete vervolgmeting vastgelegd; geschikte stabiele proefbeginsituatie |
| P0, B05 ontvangst | Softwareherstel voor late MQTT-discovery is geleverd in HA38 en behouden in HA43; oorspronkelijke ontvangst kwalificeren | Echte nieuwe ontvangst via dezelfde bron/pins/producent; geen geforceerde rapportage of cachekwalificatie |
| P0 software, B04 | Echte geschikte kamerbron met oorspronkelijk rapport en meetprofiel | Werkelijke acquisitie/actualiteit en uitval bewezen; geen diagnostische device_temperature als ruimtemeting |
| P0 software, B05/M2 | Normale FW→HA-kraanroute met HA-ontvangergrant en bestaande adapter afronden | Native zendtransactie aan oorspronkelijke kraanecho gekoppeld; profiel, modus, eigenaarschap en fallback getoetst |
| P0 software, B06 | Werkelijke veiligheids-/DHW-/water-/kraan-/flowfeiten aansluiten | Iedere bron met eigen geldigheid en beoordeeld installatieprofiel; geen generieke flowaanname |
| P1, B07–B09 | Classic-TX-/stopketen afronden en installatievoorwaarden beoordelen | Adres/masker, interface/polariteit/arbitrage, afgifte/naloop, onafhankelijke stop en één actieve schrijver vastgesteld |
| Release, B10–B13 | Eén gezamenlijke kandidaat bevriezen, verifiëren, publiceren en installeren | Exacte bron/pakketten, volledige CI, checksums, herstelroute, backup en nacontrole |
| Fysiek, B14 | Afzonderlijk toegelaten stop-/zend-/uitvalproeven uitvoeren | Gemeten reactie en stop binnen beoordeelde grenzen; gecontroleerd herstel vastgelegd |

Onafhankelijk softwarewerk kan doorgaan terwijl fysieke gegevens ontbreken.
Een begrensde handmatige ketelproef en automatische kamerregeling hebben
verschillende voorwaarden: die laatste vereist ook de volledige M2-kamer-/kraanketen.

## 4. Pendelen: wat weten we?

De passieve controle van 24 oktober 16:26 CEST bevestigt **0 EMS-verzendingen,
0 polls en alle uitgangen geblokkeerd**. Geen UART-fouten of ongeldige telegrammen;
geen bewijs van OpenThermostat-aansturing. De beschikbare geschiedenis toont
warmwatergerelateerde vermogensperiodes van ongeveer 3–4 minuten met 10–12 minuten
tussen starts, ook nadat Tado voor de kamer idle meldde.

**Oorzaak nog onbekend.** Warmwatergebruik/bijwarmen is de onderzoeksrichting.
Telemetrie bewijst geen exact aantal fysieke ontstekingen en sluit indirecte
elektrische invloed niet volledig uit. Geen instellingen gewijzigd of zendproef
gedaan. Bewijs: `out/boiler-cycling-20261024/SAFE-RESULT.json`.

De latere controle van 17:00–17:01 CEST toont in de voorafgaande 30 minuten alleen
code 0H/0% gemeld vermogen en afkoeling, zonder nieuwe positieve vermogensperiode.
De eerdere oorzaak blijft onbekend; dit is geen bewijs van een reparatie.

## 5. Wanneer is de actieve bèta gereed?

Er is nog geen onderbouwde kalenderdatum. De softwarekandidaat kan met
geblokkeerde uitgangen worden geleverd; actieve proeven volgen pas na de
bijbehorende installatie- en stopvoorwaarden. Het [testplan](BETA1-KETELPROEF.nl.md)
beschrijft nulmeting → fysieke proefkaart → stop in rust → één begrensde vraag →
stop/naloop → afzonderlijke uitval → terugkeer naar Tado.

De oudere native HTTPS-updaterfout blijft onverklaard; checkpointdiagnose is
geleverd, maar bewijst geen reparatie. Geen blinde herhaling van de mislukte route.

## 6. Blijvend in het productplan

Alle 31 eisen blijven gelden, inclusief per ruimte leren en blijvend bewaarde,
gevalideerde parameters. Nieuwe F9/F10-ontwikkeling volgt na M2. Acht zones,
vloer/menger, grafiek-/historieacceptatie, comfort en onbeheerd verwarmingsbedrijf
houden hun eigen acceptatievoorwaarden. Niets wordt op basis van alleen aanwezige
code of een geslaagde build als werkende fysieke functie afgevinkt.

## 7. Nieuwe extra functie: direct BLE / zelfstandige E32

[Uitbreiding X01](SHELLY-BLU-TRV-STANDALONE.nl.md) voegt Shelly BLU TRV via
Bluetooth en een expliciete lokale E32-modus toe aan het ontwikkelplan. De
bestaande HA-functies blijven behouden. Haalbaarheid onderzocht met officiële
GATT-documentatie; nog geen driver, koppeling of lokale regelvrijgave geleverd.
Eerst één kraan uitlezen en zonder ketel kwalificeren, daarna lokale
programmering/eigendom/opslag/tijd en de bestaande stop-/uitvalvoorwaarden verbinden.
Dit wijzigt de laatst gecontroleerde installatie HA38/E32alpha28 niet en is geen nieuwe release.

X01 omvat ook de Shelly BLU H&T Display ZB (SBHT-103C) en een tweetalige
[Bluetooth-apparaatpagina onder Settings](BLUETOOTH-APPARATEN.nl.md): vinden,
beveiligd toevoegen waar nodig, kamertoewijzing en meetkwaliteit/uitval zichtbaar.
Dit onderdeel is ontworpen, nog niet gebouwd of op echte apparaten getest.

Ook opgenomen in X01: Xiaomi Smart Temperature and Humidity Monitor 3
(MJWSD05MMC), via dezelfde Bluetooth-pagina. Versleutelde ontvangst vereist
een geldige apparaatsleutel; de verkrijgingsroute en praktijkkwalificatie zijn
nog open. Originele sensorfirmware heeft de voorkeur; geen automatische flash.

HA38 levert het TV02-opstart-/lifecycleherstel voor dezelfde vooraf vastgelegde
bron, met begrensde subscripties en veilige redencodes. De huidige diagnose is
wachtend/stale en ongekwalificeerd; echte nieuwe ontvangst en causale echo blijven
open. De oude incidentoorzaak is niet bewezen. Eerdere bronproeven blijven bewaard
in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

## Onderhoudsrelease dev38 / alpha29

Gepubliceerd uit `d131c503f42e6b834a0815db8384983a7fc1b46f`; HA dev38
geïnstalleerd, E32 alpha29 nog niet. Alle 23 voorbereide onderdelen behouden.
2189 tests per Core-versie en vier browserregressies geslaagd; publieke pakketten
exact gecontroleerd. Hoogste prioriteit is offline onderzoek van de mislukte
E32-upload en een onderbouwde herstelroute. Zie het actuele installatieverslag.
Geen actieve bèta of werkende Shelly-/Xiaomi-driver claimen.

## Voorbereid voor de volgende gezamenlijke bundel

| Onderdeel | Software afgewerkt | Nog nodig voor praktijk/levering |
| --- | --- | --- |
| I03 uploadherstelbaarheid | Strikte/exacte lengte, opruimen bij annulering/toegangsverlies, één appbestand en selectie na volledig geautoriseerd verzoek; 16 nieuwe native en 11 REST-grensscenario's | Onderbouwde herstelroute voor alpha28; watchdogtaak/oorzaak onbekend. [Bewijs](OTA-UPLOAD-ONDERZOEK-20261024.nl.md) |
| B06 veiligheidsfeiten | Afgewezen toekomstige/oudere/tegenstrijdige acquisities blijven ingetrokken; gedeelde zonepolicy-/storingscontrole en correcte nul-uptimemarkeerders | Werkelijke producenten, bron-/installatiekwalificatie, minimumflow en naloop. [Bewijs](VEILIGHEIDSFEITEN-20261024.nl.md) |
| B07/B08 en R15 ketelrapporten | Per veld nieuwste originele meting behouden; oudere deeltelegrammen vullen ontbrekende velden; HA herstelt ingetrokken cache niet via een andere groep; 12 native en 6 HA-regressies in deze batch | Beoordeeld profiel, adres/masker, echte UART en fysieke start/stop-/DHW-proeven. [Bewijs](KETELRAPPORT-VOLGORDE-20261024.nl.md) |

De gecombineerde native suite telt **689 geslaagde tests**; beide firmwarebuilds
zijn gecontroleerd. Op elk van HA Core 2026.10.2 en 2026.10.3 slagen **2195 gevallen**,
zonder fouten of skips. Pakket-/release-CI op een bevroren eindkandidaat blijft vereist. Alle 23 voorbereide onderdelen en 31 producteisen blijven behouden.
Niets uit deze bronbundel is opnieuw geïnstalleerd of gepubliceerd als release.
De huidige installatie en de fysieke releasepoorten blijven hierboven afzonderlijk vermeld.
