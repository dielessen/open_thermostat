# Volgende actieve bèta — geïnstalleerde basis HA47 / E32 alpha31

Bijgewerkt: 25 oktober 2026. Dit is het korte releaseoverzicht.
Het [werkbord](WORKBOARD.nl.md) bevat de enige actuele checklist en prioriteiten;
het [masterplan](PLAN.nl.md) bewaart alle 31 producteisen en acceptatievoorwaarden.

## Grotere release HA47 / E32 alpha34 — gepubliceerd en HA geïnstalleerd

Beide onveranderlijke tags staan op bron `6f21f34`. Alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketcontroles slagen. De bundel verenigt
robuuste HA-opstart/afsluiten met vier gerichte updatercheckpoints en EN/NL-uitleg.
782 native gevallen en 2.349 HA-gevallen per ondersteunde Core slagen. Alle 23
onderdelen, 286 bronverwijzingen en 31 eisen blijven behouden. Actieve bèta blijft
**NOT_READY**; bron-/kraan-/installatiekwalificatie staan afzonderlijk open.

HA dev47 is geïnstalleerd op bron `6f21f34`, met een verse HA46-back-up van
96 bestanden en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober **06:47:49 UTC** slaagt: 44 controles, alle 86 livebestanden exact
publiek pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; alpha34 is gepubliceerd, zonder firmwareactie.
[Installatie en bewijs](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).

## Voorbereid voor de volgende grotere bundel

De native afsluitroute ruimt de overige eigen handles, worker en wachtrij ook
op als één cleanupcallback een gewone exception geeft. Drie gevallen falen
vóór correctie; 162 gerichte gevallen per ondersteunde Core slagen erna.
Dit is bronvoorbereiding, nog niet geïnstalleerd en geen verklaring voor een
eerder productieincident. [Bewijs en beperking](HA-OPSTART-LIFECYCLE-20261025.nl.md).

Ook de kamer-/HVAC-testopstelling gebruikt nu één klokdomein voor ontvangst
en meetleeftijd. Vier epochproeven toetsen het volledige bestaande servicepad;
50 gerichte gevallen per ondersteunde Core slagen. Regeltijden en veiligheids-
asserties blijven behouden; de oudere CI-oorzaak blijft afzonderlijk onbekend.
[Uitwerking en bewijs](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

De gecombineerde voorbereiding met de cleanupfix is volledig lokaal getoetst:
2.356 gevallen per Core2026.10.2 en2026.10.3, nul fouten of skips; zeven
pakketunittests en twee onafhankelijke offline bronreviews slagen. Geen nieuwe
releaseversie of installatie voor deze bronstap. Alle fysieke poorten blijven open.

X01 heeft nu een eerste pure Shelly SBHT-103C-decoderbasis:798native tests,
16aparte sanitizergevallen en ESP32-syntaxcontrole slagen. Deze parser wordt
nog niet door de BLE-reader geselecteerd. Settings/onboarding, sleutels,
bron-/replaykwalificatie en echte apparaatproeven blijven open. De actuele
bronvoorbereiding bewaart23onderdelen en31eisen, nu met289bronverwijzingen.
[Uitwerking en grenzen](BLUETOOTH-APPARATEN.nl.md).

## Historische release HA46 / E32 alpha33

Beide tags zijn gepubliceerd op bron `2d32ad3`; alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketreviews slagen. De bundel bevat
begrensde oorspronkelijke ontvangstdiagnostiek en extra herintredebewaking bij
socketoverdracht en kanaaltoelating. 773 native kerngevallen, 5 lokale socketgevallen
en 2.339 HA-gevallen per ondersteunde Core slagen. Alle 23 onderdelen en 282
bronverwijzingen blijven opgenomen. E32 alpha33 is gepubliceerd; de module blijft
op alpha31. Actieve bèta blijft **NOT_READY**.

HA dev46 is geïnstalleerd op bron `2d32ad3`, met een verse HA45-back-up van
95 payloads en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober 05:12:15 UTC slaagt: 38 controles, alle 86 livebestanden exact publiek
pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; er is geen firmwareactie uitgevoerd.
[Installatie en bewijs](INSTALLATIE-HA46-ALPHA33-20261025.nl.md).

## Geleverd in alpha34-bron — gerichte updaterinstrumentatie

De alpha34-bron onderscheidt vier opgeslagen stappen vóór checksum,
native imagevalidatie, onafhankelijk flash-readback en bootselectie. Oude
checkpoints blijven leesbaar; de UI toont de betekenis in Nederlands/Engels.
782 native gevallen, 40 sanitizergevallen en 24 updaterbrowsergevallen slagen;
E32-compile geslaagd. De updaterstap behield 23 onderdelen en 31 eisen; met de
HA-opstartcorrectie hieronder bevat de gepubliceerde HA47-inventaris 286 bronverwijzingen.
Dit is gepubliceerd in alpha34,
zonder firmware-installatie door deze opdracht; de oudere watchdog blijft onverklaard.
[Uitwerking en bewijs](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).

## Geleverd in HA47 — opstart en afsluiten

De native opstart behoudt nu één eigenaar over programma-, Store- en MQTT-
leesgrenzen. Afsluiten of annuleren kan de oude verbinding niet later alsnog
laten starten; een dubbele start vervangt de eerste eigenaar niet. De optionele
temperatuurdiagnose heeft één begrensd aanmeldbudget en ruimt late handles op.
Alle tien nieuwe gevallen falen op de oude code; 139 gerichte en 2.349 volledige
HA-gevallen per ondersteunde Core slagen. Dit bronwerk is geleverd in HA47,
samen met de gepubliceerde alpha34-updatercheckpoints.
[Uitwerking en bewijs](HA-OPSTART-LIFECYCLE-20261025.nl.md).

De afzonderlijke alleen-lezen controle vóór de uitrol van **05:46:49 UTC** zag bij de toenmalige
TV02-owner één callback/enqueue/workeracceptatie, zonder getelde drops of fouten.
Het oorspronkelijke lokale-temperatuurbericht is inmiddels stale; dit bewijst
ontvangst, geen kraan-ACK, positie of regelkwalificatie. De gekozen interne
kamerbron blijft onbruikbaar en heeft nul oorspronkelijke topics. SOURCE5 en
instellingen behouden; nul productie-/deviceacties. Geen nieuwe E32-/bestandsaudit.
Na de HA47-herstart is de RAM-eigenaar nieuw: bij de nacontrole van 06:47:49 UTC
zijn de tellers nul en TV02 `waiting`. Oude ontvangst wordt niet als verse meting
hergebruikt. De bewaarinventaris behoudt alle 23 onderdelen met 286 bronverwijzingen.

## Historische grotere release HA45 / E32 alpha32

HA45 is geïnstalleerd op bron `3f12d8b`, met een verse HA44-back-up van 95 payloads
en één normale Core-herstart. De afzonderlijke nacontrole van 03:09 UTC slaagt:
38 controles, alle 85 livebestanden exact publiek pakket/Git, instellingen en
kaarten behouden. E32 blijft alpha31 op bron `659879e`; alpha32 is gepubliceerd,
zonder firmwareactie door deze opdracht. Alle 23 onderdelen en 279 bronverwijzingen
blijven opgenomen. [Installatieverslag](INSTALLATIE-HA45-ALPHA32-20261025.nl.md).

767 native kerngevallen, 4 lokale socketadaptergevallen en 2.333 HA-gevallen per
ondersteunde Core slagen; alle definitieve CI- en pakketreviews zijn geslaagd.
Actieve product- en fysieke kwalificatie blijven open.

## Gezamenlijke release HA44 / E32 alpha31

Beide onveranderlijke tags en alle negen openbare downloads zijn gepubliceerd op
bron `659879e`. Bron-/pakket-/tagreview en alle drie CI-runs geslaagd: 728 native
firmwaretests en 2.323 HA-gevallen per Core 2026.10.2/2026.10.3. Alle 23 voorbereide
onderdelen met 267 bronverwijzingen blijven opgenomen.

**HA44 is geïnstalleerd en onafhankelijk gecontroleerd:** 85 livebestanden exact
publieke ZIP/Git, verse HA43-back-up van 94 bestanden, één normale Core-herstart.
Instellingen, programma's, bindingen, registry en frontend behouden. Nacontrole
25 oktober 00:32:01 UTC: alle 20 checks geslaagd. De actuele SOURCE-revisie5 is
behouden; de voorafgaande horizonverschuiving wijzigde geen programma of binding.
[Installatieverslag](INSTALLATIE-HA44-ALPHA31-20261025.nl.md).

De native HA-worker verwerkt nu grantaanvragen en kraanopdrachten, met lokale
sessie-/config-/bindingcontrole, oorspronkelijke deadlines, eenmalige grants en
onmiddellijke intrekking bij scopeverlies. Optioneel verkeer kan de shadow-sessie
niet via een volle queue resetten. De echte C++-bytes worden via deze worker en
de bewaakte serviceadapter beproefd; serviceacceptatie blijft geen fysieke ACK.
[Uitwerking](M2-NATIVE-KRAANROUTE-20261025.nl.md).

**Vers waargenomen: E32 alpha31.** Alleen-lezen controle 25 oktober 01:50 UTC
bevestigt bron659879e/ELF045dfe53 en normale beschikbaarheid. De uitvoerder en
methode van die gewijzigde installatie zijn onbekend; deze opdracht heeft geen
E32-upload gestart. De oudere alpha28-momentopname is historisch. De eerdere
watchdogoorzaak/herstelroute blijven open; geen nieuwe flashpoging.
[Waarneming en bewijs](WAARNEMING-E32-ALPHA31-20261025.nl.md).

## Geleverd in HA45 / E32 alpha32

De oorspronkelijke firmware-aanvraag en het grantantwoord worden nu per kanaal
gekoppeld, inclusief aanvraagvolgnummer, oorspronkelijke deadline en gedeeld
klokwatermerk. De optionele aansluiting gebruikt dezelfde MQTT-client/loop;
de productfabriek blijft gesloten. [Uitwerking en grenzen](M2-AANVRAAG-EN-KANAAL-20261025.nl.md).
De bundel omvat ook beschermd kanaalbeheer en deadlinegebonden nonblocking writes
op dezelfde socket, plus een correct gefaseerde ACK-test. Regressie, definitieve
bronreview en exacte CI/publicatie zijn geslaagd; HA45 is geïnstalleerd.

## Volgende stap naar actieve bèta

De product-kraanfabriek blijft gesloten. Normale firmware-MQTT-grant-/zendbedrading,
actuele gekwalificeerde SOURCE, geschikte kamerbron, causale oorspronkelijke
kraanecho en fysieke stop-/uitvalproeven blijven open. E32-herstelbaarheid moet
ook worden vastgesteld. De volledige actieve bèta is daarom nog niet vrijgegeven.
[Voorbereide firmwareketen](M2-SOURCE-TRANSPORT-20261025.nl.md).

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
| E32 | `v0.1.0-e32v2-alpha.31`, bron `659879e52b3e0e517e8dea1e28edb2d189c38c77`; dezelfde boot bevestigd 06:47 UTC | Passief EMS uitlezen; TX, forwarding en fysieke uitvoer geblokkeerd |
| Home Assistant | `0.4.0.dev47`, bron `6f21f34ff773645645c98dc2602337c648e18ffe` | Geladen op Core 2026.10.3; frontend dev41/v41 met v38/v35-aliases |
| Actieve regelaar | Tado | Geen automatische ketel- of kraansturing door OpenThermostat |

Bron/pakket/ELF/web, alle 86 HA-bestanden en behoud van instellingen, programma's
en identiteiten zijn gecontroleerd. Zie [installatieverslag](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).
De uitgebreide geleverde bundel staat in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

### Historische HA43-installatie — 24 oktober, nacontrole 21:17:50 UTC

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

Alle 23 voorbereide onderdelen met 267 actuele bronverwijzingen blijven in de
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
