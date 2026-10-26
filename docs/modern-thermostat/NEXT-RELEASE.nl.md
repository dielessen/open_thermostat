# Volgende gezamenlijke bèta — actueel uitvoeringsplan

Bijgewerkt op 26 oktober 2026. Status: **NOT_READY voor actieve ketelproeven**.
Dit document beschrijft het volgende werk; het [werkbord](WORKBOARD.nl.md)
bewaakt alle 31 producteisen en 14 eindcontroles. De
[release-inventaris](BETA1-RELEASE-INVENTARIS.json) bewaakt alle 23 voorbereide
onderdelen en hun 460 bronverwijzingen. De
[volledige voortgangshistorie](NEXT-RELEASE-HISTORY-20261026.nl.md) blijft bewaard;
oude versies en aantallen daarin zijn historische checkpoints.

## Doel en afbakening

Eén gezamenlijke HA/E32-bèta waarmee we na passende vrijgave de ketel
**handmatig en onder toezicht** kunnen testen: eerst nulvraag, daarna één
begrensde warmtevraag en expliciete stop. Alle voorbereide wijzigingen gaan mee.
Geen losse tussenreleases of tussentijdse installaties per fix.

Automatische kamerregeling en onbeheerd verwarmen hebben aanvullende bron-,
kraan- en installatievoorwaarden. Volledige zelflerende regeling, overige
EMS-families en alle andere roadmapfuncties blijven op het productplan staan;
ze zijn geen afgevinkte functie doordat er voorbereidende code aanwezig is.

## Wat draait er en wat staat klaar?

| Onderdeel | Laatst vastgelegde stand |
| --- | --- |
| Geïnstalleerde E32 | Gebruiker bevestigt op 26 oktober: `v0.1.0-e32v2-beta.3` geïnstalleerd. Bron/ELF/web, native installreceipts en onafhankelijke nacontrole nog niet teruggelezen; laatste formele acceptatie blijft beta.1 |
| Geïnstalleerde HA-integratie | `0.4.0b1`, gezamenlijke basis `5e3ed30` |
| Voorbereide bron | Huidige branch, inclusief eenmalige configuratie-uitlezing, afzonderlijke busafsluiting en alle eerdere voorbereide wijzigingen |
| Nieuwe gezamenlijke kandidaat | E32 beta.3 / HA 0.4.0b3 gepubliceerd uit `996587d`; exacte tag-CI en openbare pakketten gecontroleerd. E32-installatie door gebruiker bevestigd; native bewijs en onafhankelijke nacontrole nog open. De bestaande HA-MCP-beheertools zijn hier niet beschikbaar. Passieve release, geen warmteproefvrijgave |
| Volgende E32-release | Beta.4 in voorbereiding: sessieherstel, 30-minuten-inactiviteitsverval, algemene ketelillustratie en voorbereid CV-instellingenoverzicht/-bedieningspad. Geen nieuwe HA-versie voor deze wijzigingen. Nog niet bevroren of gepubliceerd; beta.3-installatieacceptatie staat open |
| Algemene en handmatige fysieke TX | Beide uit; geen runtime- of buildflag-ontgrendeling |
| Warmte-installatievrijgave | `manualHeatInstallationReviewed_ = false` |

De native HA-specialist bevestigde op 26 oktober 02:59–03:02 UTC Core2026.10.4
en integratie0.4.0b1 als geladen. De actuele E32-versie/bron en UART-tellers
werden daar niet aangeboden. De latere beta.3-installatiemelding hierboven komt
van de gebruiker; een nieuwe onafhankelijke identiteitsteruglezing blijft nodig.
Een lokale commit of ontwikkelbuild is geen beschikbare GitHub-update.

## Eerstvolgende werk, in volgorde

| Prioriteit | Werk | Vereist resultaat |
| --- | --- | --- |
| P0 — modelprofiel zonder digitale drukmeting | Apart brongebonden Ecomline-profiel geïmplementeerd: afzonderlijke drukcontrolemethode vereist, met een nieuwe verklaring per warmteproef. De methodepoort blijft uit | Passende fysieke drukcontrolemethode voor deze installatie beoordelen en vastleggen; geen digitale drukwaarde eisen of verzinnen. Overige meet-, installatie- en stopvoorwaarden blijven behouden |
| P0 — configuratieontvangst | Eenmalige uitleesroute is aangesloten in HTTP, UART-poll en NL/EN-bediening; afronden met kandidaat- en fysieke controle | Echte latere boilerrespons levert CV-aan/uit en temperatuur met originele ontvangsttijd; standaard TX blijft uit tot afzonderlijke vrijgave |
| P0 — handmatige proefvariant | Bronbeoordeling en installatiekaart B07–B09 afronden voor de echte E32/EasyControl/Classic-keten | Expliciete adres-/interface-/timing-/arbitragebeoordeling en passende afgifte-, stop- en overdrachtsvoorwaarden; geen willekeurig openzetten van algemene TX |
| P0 — gezamenlijke freeze | Volledige CI geslaagd op `171d3be`, inclusief receipt-gebonden updaterproef, sessiegebonden uitlezing en opslagonderhoud. Onafhankelijke pakketcontrole op `4c9a33d`; nieuwste UI-aanvulling lokaal gecontroleerd. Beta.4-versie en bron nog niet bevroren | Exacte kandidaat met volledige native-/HA-/browser-/board-/bron-/licentie-/pakketcontroles; ontwikkelbewijs apart houden |
| P0 — release en installatie | Eén gezamenlijke publicatie en installatie na kandidaatacceptatie | Begrijpelijke Engelse GitHub-notities, actuele README en juiste assets/manifest/checksums; HA via de bestaande native HA-specialist met back-up; E32 via native GitHub-OTA |
| P0 — onafhankelijke nacontrole | Nieuwe boot, versie/bron/ELF/web en instellingenbehoud vastleggen | Verse readback en acceptatierapport; HTTP202 of alleen een build telt niet als geslaagde installatie |
| P0 — afzonderlijke ketelproef | B14 uitvoeren zodra de fysieke voorwaarden en proefopdracht gelden | Nulmeting → nulvraag/latere stopmelding → eindige warmtevraag → stop/naloop → afzonderlijke uitval/herstel → terug naar Tado |
| Daarna — automatische zones | B04–B06/M2 afronden, kraanproef eerst zonder ketel | Oorspronkelijk verse kamermeting, echte TV02-route en causale echo, geldige profielen, bronuitval en hydrauliek bewezen |

De [installatiekaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) en het
[keteltestplan](BETA1-KETELPROEF.nl.md) bevatten de details. De huidige opdracht
om de bèta af te maken is geen opdracht om nu proefcommando’s te versturen.
B01–B03 zijn volledig afgetekend. B04–B14 bevatten gebouwd werk én open
acceptatie; drie aftekeningen op veertien zijn geen percentage programmeerwerk.
Het werkbord onderscheidt nu voorbereiding, publicatie/installatie, fysieke
proefacceptatie en latere automatische regeling. De fysieke M2-acceptatie gaat
niet vóór deze handmatige bèta; automatische kamer-/kraanuitvoer blijft daarbij
geblokkeerd. De eigen B07–B09-voorwaarden voor ketelmetingen, zender en installatie
blijven vereist. B14 wordt pas na de afzonderlijk toegelaten echte proef afgetekend.

## Sensorloze Ecomline: drukvoorwaarden in de bron herzien

Het vaste E32-proefprofiel gebruikt nu `ecomline-classic-separate-pressure-v1`.
De keuze staat in de bron; een ketelfoto, ontbrekende meting of HTTP-parameter
kan haar niet veranderen. De afzonderlijke bronpoort
`manualPressureMethodReviewed_ = false` vereist eerst beoordeling van een
passende lokale drukcontrolemethode. Naast de bestaande opstellingsverklaringen
vereist iedere warmtevoorbereiding daarna een nieuwe expliciete
`pressure_check_confirmed: true`. Een nulproef en stop vereisen deze
warmteverklaring niet.

De drukverklaring blijft bij de boot, revisie en operator van die ene proef;
zij wordt geen ketelmeting en levert geen fysieke validatie. De keteltestpagina
legt dit uit in EN/NL en vraagt bij elke nieuwe warmtevoorbereiding opnieuw
bevestiging. De modelroute zonder druksensor behoudt dezelfde verse
watertemperatuur, CV-instelling, temperatuurgrenzen, operatorlease en stopregels.
Het bestaande profiel mét digitale sensor blijft digitale druk controleren.
Algemene TX, handmatige TX, instellingen-TX en installatievrijgave blijven uit.

Lokale softwarecontrole: 61 native tests met ASAN/UBSAN, desktop-/mobiele
bedienings- en passieve regressies, 72 bevestigingsgevallen en 4
configuratie-uitleesgevallen geslaagd. E32-firmware en filesystem gebouwd;
partities, standaardblokkades en afwezigheid van project-UART-TX-verwijzingen
gecontroleerd. Bewijs staat lokaal onder `out/beta4-sensorless-pressure/`.
Dit is ontwikkelbewijs vóór freeze.

De feitelijke controlemethode en fysieke proef zijn nog niet beoordeeld of
uitgevoerd; deze codewijziging tekent B07–B09/B14 niet af.

## Handmatige busafsluiting: oorspronkelijke ontvangsttijd en nacontrole

De voorbereide `ManualClassicTransaction` controleert nu de oorspronkelijke
microseconden-ontvangsttijd tegenover de afgeronde verzending. Een vóór of
tegelijk met de verzending ontvangen antwoord wordt door latere verwerking
niet alsnog geldig. Toekomstige ontvangsttijden blijven ongeldig.

Na de enige toegelaten afsluitbyte worden de transportpoort en dezelfde
200ms-busdeadline opnieuw gecontroleerd. Een verlopen, teruglopende klok of
weggevallen transportpoort wordt fout, ook als de SDK-write zelf slaagde.
Tijdens afsluit-IO kan geen nieuwe transactie worden geopend of dezelfde
ontvangst opnieuw een afsluitbyte sturen. De fout blijft via de bestaande
controllerroute een transportfout; dit is geen bewijs van fysieke CV-stop.

De oorspronkelijke ontvangsttijd wordt door de echte UART-eigenaar doorgegeven;
geen nieuw HTTP-pad, vrijgave of automatische herhaling. Standaard TX blijft uit.
Deze wijziging maakt de voorbereide bron consistenter met de bestaande strengere
instellingenroute. Zij stelt geen werkelijke adaptertiming of proefacceptatie vast.

Lokale controle: 41 native gevallen met ASAN/UBSAN geslaagd; standaard E32-build
en standaardblokkadecontrole geslaagd. De geïsoleerde handmatige compilevariant
slaagt eveneens; alleen `EmsController.cpp.o` bevat de verwachte UART-write.
De proefvariant is uitsluitend gebouwd, niet geïnstalleerd. Bewijs staat onder
`out/beta4-manual-reply/`.

## Actuele software- en pakketpreflight — 26 oktober

De volledige [CI op `171d3be`](https://github.com/dielessen/open_thermostat/actions/runs/40356501714)
is geslaagd: negen validatiejobs, waaronder alle bordbuilds, native-/browser-/
HA-controles, beide zendroute-compileproeven en de receipt-gebonden updaterproef.
Dit omvat de sessiegebonden uitlezing en het opslagonderhoud. De nieuwste
UI-aanvulling hieronder krijgt nog een eigen CI. De eerdere bron `4c9a33d`
heeft eveneens een volledig geslaagde eigen CI. Publicatiejobs zijn uitsluitend
voor tags bedoeld en zijn in deze ontwikkelruns overgeslagen.

Het werkelijk gedownloade E32-pakket van `4c9a33d` is onafhankelijk tegen de exacte Git-bron,
firmware, webbestanden, ELF, factory-slices, checksums, bron-/licentiemateriaal
en relinkbewijs gecontroleerd: 2.229 controles geslaagd. Imagegrootte is
2.862.416 bytes. De bestaande alpha36-hostcompatibiliteit slaagt opnieuw; HA-
integratiebron is bytegelijk aan de gepubliceerde beta.3-bron. Lokaal bewijs:
`out/beta4-release-preflight/`. Dit CI-pakket heeft nog versieveld beta.3 en
andere bron dan de openbare beta.3; het is geen vervangende publieke download.

De pakketbouw krijgt bovendien een verplichte proef met de **ongewijzigde
updater uit de laatst geaccepteerde receipt**, nu beta.1. Lokaal zijn drie
indexcatalogusgevallen, twaalf zoekposities en vijf image-/readbackgevallen met
het echte CI-image geslaagd. Een verkeerd manifest, beschadigd image,
ontbrekende acceptatie of veranderde bewaarde bron wordt geweigerd. Het bewijs
wordt aan pakket en checksumlijsten gebonden. Zeven nieuwe fixtures, de vier
bestaande alpha36-fixtures, zes updatepoortcontroles en twintig publicatiecontroles
slagen lokaal. De nieuwe pakketroute is inmiddels ook in de volledige CI op
`b6fe339` en `171d3be` geslaagd; fysieke updateacceptatie blijft afzonderlijk.

`accepted` blijft beta.1, `pending_tag` blijft beta.3. De gebruiker bevestigt nu
de beta.3-installatie; native bewijs en onafhankelijke nacontrole staan nog open; geen opvolgerfreeze,
publicatie, installatie of fysieke ketelactie uitgevoerd. De model-/installatie-
en stopacceptatie blijven daarnaast afzonderlijk open.

## Configuratie-uitlezing en geldige bedienersessie

De voorbereide eenmalige uitlezing gebruikt nu bij toelating de echte geldige
websessie. Op de HTTP-eigenaartaak wordt uitsluitend de bestaande eindtijd onder
de controllerlock geprojecteerd; de UART-taak leest geen sessietabel en vernieuwt
geen sessie. Uitloggen, sessievervanging, herstel of verlopen toegang trekt een
klaargezet verzoek in vóór uitzending. De laatste gate gebruikt een nieuwe
kloklezing ná de gatecontrole.

Een al uitgezonden leesframe kan niet worden teruggedraaid. Het blijft daarom
exclusief gereserveerd tot het passende antwoord of de bestaande eindige
antwoorddeadline. De status noemt dit `withdrawn: true`; zo ontstaat geen
concurrerende instellingen-/proefopdracht. Het latere antwoord bevestigt geen
geannuleerde uitlezing. Geen automatische herhaling, sessieherleving of nieuwe
opdracht tijdens IO. Standaard TX blijft geblokkeerd.

Lokale controle: 56 native gevallen met ASAN/UBSAN, 11 echte login-/logout-
scenario's en 11 REST-OTA-boundarygevallen geslaagd. Standaard E32-build en
afzonderlijke handmatige compilevariant slagen; alleen de controller bezit de
verwachte UART-write. Bewijs: `out/beta4-read-session/`. Dit is bronwerk vóór
freeze, geen opdracht aan het geïnstalleerde apparaat.

## Geannuleerde uitlezing zichtbaar in de webbediening

De keteltestpagina toont nu in EN/NL wanneer een configuratie-uitlezing is
geannuleerd omdat de bedienersessie eindigde. Een al verstuurd verzoek blijft
herkenbaar in afwachting van afronding; opstellingsvinkjes en nieuwe uitlezing
blijven daarbij geblokkeerd. Een terminale annulering vraagt nieuwe
opstellingsbevestiging. Annulering of een andere boot/revisie wist oude vinkjes.

Een later statusantwoord kan een bekende annulering voor dezelfde revisie niet
intrekken, ook niet na een tussentijds ongeldig statusantwoord. Een onjuist
getypeerde `withdrawn`-waarde of een combinatie van annulering en succesvolle
afronding toont onbeschikbare status. Het bestaande
statuscontract zonder dit extra veld blijft bruikbaar. Het drukvinkje is alleen
zichtbaar als het door de gerapporteerde proefvoorwaarden wordt vereist; de
Bootstrap-weergaveklasse overschrijft het verbergen niet meer. Het bewerkingspad vraagt
nog steeds uitsluitend expliciete bevestiging; geen automatische herhaling,
proefstart of hervatting bij heropenen. Standaard TX blijft uit.

Lokale controle van deze aanvulling: vier EN/NL-browserverlopen op desktop en
mobiel, inclusief ingetrokken status, late afronding, verkeerde veldtypen,
heropenen en nieuwe bevestiging; drie volledige bedieningsweergaven geslaagd.
Firmware en filesystem gebouwd en de standaard E32-blokkades gecontroleerd.
Bewijs staat lokaal onder `out/beta4-read-cancellation-ui/`; dit is geen fysieke
nacontrole van de geïnstalleerde beta.3.

## Opslagonderhoud na iedere release

Gebruiker vraagt dit op 26 oktober expliciet voortaan bij iedere release.
`AGENTS.md` en het releaseproces leggen de vaste lokale opruimstap vast met
`scripts/cleanup_release_artifacts.py`: drie nieuwste openbare E32-releases plus
geaccepteerde en pending versies behouden; oude downloads alleen na exacte
vergelijking met de publieke GitHub-SHA256 verwijderen; identieke ZIPs delen
alleen-lezen opslag. Bron, werkbomen, back-ups, logs en geleverde relinkinputs
blijven behouden. Zonder `--apply` wordt alleen de planning getoond.

De eerste opruiming verminderde dit project van 39,6 naar 22,8GiB: 16,8GiB
teruggewonnen. 69 oude cachemappen en 32 opnieuw downloadbare oude release-ZIPs
verwijderd; 37 identieke ZIP-paden delen opslag. Hashes, herstel-URLs en resultaat
staan lokaal onder `out/cleanup-20261026/`. Het bewaarde E32-pakket is daarna
opnieuw onafhankelijk gecontroleerd; negen opruimfixtures slagen. Dit verandert
geen release- of hardwareacceptatie.

## GitHub en releaseonderhoud — 26 oktober

De openbare hoofdpagina krijgt een Engelse README met de actuele gepubliceerde
E32 beta.3 / HA 0.4.0b3, functiegrenzen en roadmap inclusief raam- en deurcontacten.
De laatste vastgelegde installatieacceptatie blijft beta.1/b1; beta.4 is nog een
niet-bevroren voorbereiding. Iedere volgende release krijgt Engelse notities
(`user-release-notes:v2:en`) en een inhoudelijke README-controle. De automatische
versieverversing werkt alleen het downloadblok op de GitHub-standaardbranch bij;
firmwarebron en fysieke vrijgaven veranderen hierdoor niet. Zie het
[releaseproces](RELEASE-NOTES-PROCES.nl.md).

De volledige bron-CI op `ff54e0f` is geslaagd:
[negen validatiejobs](https://github.com/dielessen/open_thermostat/actions/runs/40333594425).
Dit omvat de boardbuilds, native-/browser-/HA-controles en beide afzonderlijke
compileproeven. Publicatiejobs waren overgeslagen. De daarna gewijzigde
README-/releasehulpmiddelen krijgen eigen controles; dit eerdere CI-bewijs
wordt niet als bewijs voor latere wijzigingen voorgesteld. Ook het latere
Engelse documentatie-/releasecheckpoint `d5e354a` is volledig geslaagd in
[CI-run 40338704546](https://github.com/dielessen/open_thermostat/actions/runs/40338704546).
De sensorloze drukroute en de hierna verbeterde busafsluiting hebben hun eigen
bron-/CI-identiteit; eerdere groene runs vervangen die controle niet.

## Bekende opstelling — niet opnieuw uitvragen

- Ketel: Nefit Ecomline Classic HRC 22H.
- Adapter: Bosch EasyControl Adapter 8737908035 V2.3.
- Gateway: BBQKees E32 V2/V2.2 met ethernet; E32 parallel met Tado op de adapter.
- De gebruiker kan Tado losnemen en de ketel onafhankelijk uitschakelen.
  Displayreset is geen normale proefstop of automatische uitvalgarantie.
- Meerdere radiatoren staan volgens de gebruiker open; TV02 zit op een radiator.
- Werkelijke Tado-overdracht en gemeten minimumflow/naloop zijn nog niet bewezen.
  Kunnen losnemen is geen bevestiging dat Tado voor de proef al los is.

Het eerdere pendelen is niet causaal verklaard. De historische samenloop met
warmwaterbedrijf bewijst geen oorzaak of reparatie. Een stabiele passieve
beginsituatie en CV/DHW-onderscheid blijven onderdeel van de fysieke proef.

Bij overdracht en herstel moet ook het ketelzijdige adapterprotocol worden
vastgesteld: Bosch documenteert terugval naar aan/uit bij mislukte iRT/OT-detectie.
Alleen een groene led of EMS-ontvangst is hiervoor geen bewijs. De
[pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) bevat de fabrikantbronnen;
Keteltest geeft hierover NL/EN-uitleg zonder herstart- of configuratieactie.

## Vastgestelde blokkade in de live meetketen

Alleen-lezencontrole op 26 oktober: de E32 is bereikbaar. De CV-temperatuur
is 55 °C, ontvangen via `0x16`; het laatste bericht heeft offset 1 en één
payloadbyte. `heating_enabled` is onbekend. Ook de eerdere bewaarde snapshot
mist dit veld. Deze waarnemingen bewijzen geen ontbrekende ondersteuning in de
ketel: ze tonen dat byte 0 in deze snapshots niet beschikbaar is.

De voorbereide bron heeft nu een afzonderlijke uitleesroute naast de
`0x1A`-setpointzender. De knop **CV-instellingen eenmalig uitlezen** vraagt
nieuwe opstellingsverklaringen en verstuurt uitsluitend `0x16`, offset 0,
lengte 2. Zij gebruikt dezelfde vaste service-identiteit, adres-/pollcontrole,
UART-voorcontrole, echoafhandeling en pinvrijgave. De setpointzender zelf
accepteert dit leesframe niet.

De uitleesactie wacht maximaal 5 seconden op een toegelaten poll en daarna
15 seconden op antwoord. Alleen een werkelijk later ontvangen, volledig
boilerantwoord aan serviceadres `0x0B` telt; een verzoek, echo, broadcast,
gedeeltelijk of oud antwoord telt niet. Een nieuwe expliciete poging heeft een
nieuwe revisie en minimaal 30 seconden tussen voorbereidingen nodig. Geen
achtergrondpoller, automatische herhaling, warmtevraag of instellingenwijziging.
Tijdens de actie zijn proefvoorbereiding en OTA/configuratiemutaties uitgesloten.
De standaard TX-blokkade blijft intact; deze bronwijziging heeft nog geen
live-uitleesverzoek of vrijgave van de warmteproef opgeleverd.

## Actuele meetketencontrole via HA — 26 oktober

De bestaande native HA-specialist heeft uitsluitend gestructureerde lezingen
uitgevoerd, 02:59–03:02 UTC. Classic-aanvoer, geselecteerde aanvoer, modulatie
en CV/DHW-velden worden aangeboden; CV/DHW blijven afgeleide velden. De
native `boiler_fields_v1`-entiteiten voor `pressure` en `heating_enabled` bestaan,
zijn ingeschakeld, maar zijn `unavailable`. Dit is geen verwisseling met oude
EMS+-entiteiten. Hun oorspronkelijke meettijd, kwaliteit en ruwe bytes ontbreken
in deze HA-lezing; geen ontvangst, ongeldige/verlopen data en een runtime-
overdrachtsprobleem zijn hiermee nog niet onderscheiden.

De supervisor meldt `hydraulic_profile_unqualified` en fysieke uitgangen uit.
SOURCE-revisie is 6, zonder staged-revisie; de oorzaak van een revisiewijziging
is niet onderzocht en er is niets teruggezet. Er is geen actuele E32-versie-,
UART-teller-, protocolmodus- of fysieke stopverificatie uit deze HA-tools.

Het bewaarde oorspronkelijke E32-telemetriebewijs uit
`out/active-beta-readiness/E32-telemetry.private.json` onderscheidt de velden wel:
`pressure` was **invalid**, bron `0x18`, leeftijd 3098ms; `heating_enabled` was
**unknown**, zonder bron/tijd. Dit is historisch bewijs, geen nieuwe actuele
veldlezing of bewijs dat de ketel geen druksensor heeft. De nieuwe directe
uitlezing bereikt het oudere EMS-statusendpoint; een tweede nieuwe sessie wordt
met HTTP429 geweigerd. Geen herstart of verdere aanmeldpogingen uitgevoerd.

De toegangsbottleneck ontstond nadat de uitleessessie niet in de beheercontext
werd behouden. De bestaande login kan een eigen aanwezige sessie vervangen;
zonder cookie verbruikt een nieuwe login een extra slot. Het
[updateproces](E32-UPDATE-PROCES.nl.md) schrijft nu expliciet één behouden
beheercontext voor diagnose/installatie en afmelding na afgerond werk voor.
De eerstvolgende actuele veldlezing wacht op een vrij slot of een al geldige
beheercontext; geen automatische herstart of afmelding van andere gebruikers.

De bètabron voegt daarom aan native HA-veldkenmerken meetstatus en reden voor
onbeschikbaarheid toe, plus veldnaam, schaal en oorspronkelijke TTL. Niet ontvangen,
ongeldig en verlopen blijven onderscheiden van sessie-/streamverlies; bestaande
beschikbaarheidsvoorwaarden, oorspronkelijke deadlines en stuurtoestemming
blijven gelijk. Gerichte regressie: 32 tests geslaagd op elk van Core2026.10.2/.3/.4.
Deze aanvulling is nog niet geïnstalleerd en herstelt geen ontbrekende drukmeting.

De echte HA-entiteitenplatformtest bevestigt waarom de eerdere HA-lezingen geen
extra bronkenmerken bij `unavailable` toonden: Core2026.10.2/.3/.4 neemt
`extra_state_attributes` alleen bij beschikbare entiteiten op. Daarom staat de
uitleg voor ontbrekende waarden in de diagnosedownload, niet in verborgen
sensorkenmerken. Een echte 45°C-meting verschijnt correct; ongeldige druk,
onbekende CV-aan/uit en later verlopen aanvoer blijven `unavailable`. De
standaard diagnose-export bewaart hun verschillende oorzaken en oorspronkelijke
meettijden. Dit is geverifieerd met de echte HA EntityPlatform/StateMachine,
zonder nagebootste entiteitgetters: 41 veld-/diagnosetests op elk van de drie
ondersteunde cores. Bewijs: `out/beta-ha-native-state/`.

Ook de standaard HA-diagnose-export krijgt nu een begrensd overzicht van alle
69 bekende ketelvelden: ruwe waarde, schaal/eenheid, meetstatus, reden van
onbeschikbaarheid, brontelegram en oorspronkelijke bootrelatieve ontvangsttijd.
De leeftijdsschatting gebruikt de bestaande oorspronkelijke deadline en lokale
verstreken tijd; netwerktransittijd blijft onbekend. Lezen verandert geen
meetdeadline, controlestatus of inhoud van de cache. De export bevat geen sessie-,
grant- of brokergegevens. Bij een ongeldige lokale klok worden waarden niet als
bruikbaar weergegeven. Deze bronaanvulling slaagt in 162 gerichte native HA-tests
op ieder van Core2026.10.2/.3/.4; zij is nog niet geïnstalleerd en vervangt geen
actuele drukmeting. Bewijs: `out/beta-ha-field-export/`.

Gebruiker bevestigt op 26 oktober 2026 dat zijn Nefit Ecomline Classic HRC 22H
geen digitale druksensor heeft. Dit is opstellingsinformatie van de gebruiker;
de historische ongeldige `pressure`-waarde is hiervoor geen zelfstandig bewijs.
De zoektocht naar een ontbrekende digitale drukmeting vervalt voor deze opstelling.

Tijdens deze alleen-lezencontrole vereiste de toenmalige
`ClassicHeatTrialEnvelope` nog gerapporteerde digitale druk uit `0x18`. Die
mismatch is inmiddels in de bron herzien met het afzonderlijke sensorloze
profiel hierboven; de fysieke drukcontrolemethode blijft te beoordelen.
Dit herstelt geen digitale ontvangst en verzint geen meetwaarde. Temperatuur-,
configuratie-, stop-, flow- en overige installatievoorwaarden blijven gelden.
Bewijs: `out/beta-live-readiness/`, lokaal en zonder publicatie van ruwe diagnostiek.
Geen configuratie-, installatie-, herstart-, kraan- of ketelopdracht uitgevoerd.

## Handmatige proefsoftware die al is voorbereid

- Afzonderlijke nulvraagproef; deze kan geen warmte starten. Een warmteproef
  vraagt nieuwe voorbereiding en een bewezen stopbasis.
- Concreet softwareprofiel: 40–45 °C, maximaal 60 seconden warmte; operatorlease
  5 seconden, write-cadans minimaal 1 seconde, stopwaarneming 30 seconden per fase.
  Dit zijn softwaregrenzen, geen gemeten fysieke stopgarantie.
- De implementatie vereist verse Classic-watertemperatuur en CV-configuratie.
  Het vaste sensorloze profiel vereist afzonderlijke beoordeling van de
  drukcontrolemethode plus een nieuwe verklaring per warmtevoorbereiding; het
  profiel met digitale druksensor blijft gerapporteerde druk bewaken. Ontbrekende,
  ongeldige, toekomstige of verlopen vereiste metingen geven geen warmtevrijgave.
- Auth/CSRF, boot/revisie/bediener en nieuwe opstellingsverklaringen per proef;
  geen automatische hervatting na heropenen, onderbreking of onzekere aanvraag.
- Private UART-route met vaste adreskeuze, pollmasker-/adresconflictcontrole,
  eindige echoverwerking en gecontroleerde pinvrijgave. Checksum en een alleen-lezen
  UART-voorcontrole vóór pinmapping;
  exact frame/intentie vergelijken vóór de laatste tijd-/meet-/zendtoelating.
- Afzonderlijke eindige buswisseling: alleen een passend later leesantwoord of
  schrijfstatus kan één vaste afsluitbyte uitlokken. Een afgewezen write of
  mislukte/verlopen afsluiting wordt proeffout; geen algemene pong of herhaling.
  Ontvangsttijden blijven vóór deze IO vastgelegd. Het gekozen antwoordvenster
  bewijst geen fysieke adaptertiming of CV-stop.
- Stopbewijs vereist werkelijk afgeronde nulvraag en passende latere, verse
  rapporten. Branderpauze bij positieve vraag geldt niet als stopbewijs.
- Expliciete foutafsluiting bewaart de fout; volgende proef vereist een nieuwe
  boot. Stop blijft apart beschikbaar bij onzekere netwerkantwoorden.
- Downloadrapport met bootklok, huidige nulvraagreferentie en oorspronkelijke
  ontvangsttijd per veld. Historische/ongeldige tijdstempels geven geen vrijgave.

## Alles wat in de bundel behouden blijft

Onderstaande statussen komen uit de inventaris. “Geleverd” kan een eerder
geleverde basis aanduiden; het betekent niet dat alle nieuwe wijzigingen al op
de apparaten staan. Per onderdeel blijven `remaining_acceptance` en het werkbord
leidend. Gedeeltelijk aangesloten functies worden niet als volledig actief getoond.

| ID | Onderdeel | Inventarisstatus |
| --- | --- | --- |
| I01 | Eigen project, bron/licenties en reproduceerbaar pakket | geleverd |
| I02 | Weblogin, sessies, CSRF, setup en herstelroutes | geleverd |
| I03 | Automatische HTTPS-update, TLS-geheugen en catalogus | geleverd |
| I04 | Actuele/archief-releases automatisch ordenen | geleverd |
| I05 | About, navigatie, ketelillustratie en EN/NL-interface | geleverd |
| I06 | Kamerinrichting, identiteiten en apparaatmetadata | Geleverd inclusief versieprojectie |
| I07 | Weekplanner, korte aanraakblokken en effectief doel | geleverd |
| I08 | Actieve sensor/TRV/grenzen wijzigen, bewaren en opnieuw toepassen | geleverd |
| I09 | HA-kaart registreren na opstart, zonder herhaald refreshen | geleverd |
| I10 | Kamernamen op E32 en juiste statische webroutes | Geïnstalleerde naam-/routebasis; aanvullende JSON-/tijdafhandeling in bètabron |
| I11 | Meetstatus, systeemlogging en geheugen-/toelatingsdiagnose | Geleverd inclusief observer-lifecycle/bronidentiteit |
| I12 | Passieve Classic-decoder en begrensde Classic-proefencoder | 69 Classic-velddefinities geleverd en geregistreerd in HA |
| I13 | Ketencontract, SOURCE, journal, configuratie en readback | geleverd |
| I14 | Kraanadapter profiel C, TV02-moduscontrole en tijdelijke bronbench | HA38-opstartherstel en HA43-ontvangertoelating geleverd; firmware-intentie en actuele bron-/lease-/transportcontrole voorbereid/getest |
| I15 | Kamerregelaar, seizoensbeleid en hydraulische supervisor | deels |
| I16 | Groepswaterdoelen, vloer, menger en centrale graph-config | deels |
| I17 | Metrics, grafieken, historiegrens en CSV-export | Native ketelvelden/grafieken en begrensde Recorder-CSV; 31-daagse native export in bètabron |
| I18 | Comfortprioriteiten, raam/aanwezigheidscontext en HEAT/OFF | deels |
| I19 | Thermisch model, optimum-start, uitlopen en curveaanpassing | deels |
| I20 | Meldingen, batterij en modelspecifieke tapwaterpresentatie | deels |
| I21 | Keteltest-pagina, ontvangstdiagnose en meetrapport | Alpha18 geleverd; uitgebreid veld-/berichtoverzicht voorbereid |
| I22 | Begrensde ketelproefpolicy en originele UART-ontvangsttijd | Policy en RX-integratie geleverd; actieve proef nog onvolledig |
| I23 | Beveiligde controller-/HTTP-/webbediening van de ketelproef | Geleverd met actieve proef geblokkeerd |

## Softwarebewijs en grenzen

- **Actuele aanvullende integratiecontrole op schone bron `b0abca7`:** HA Core
  2026.10.2/.3/.4 ieder **2373 tests en 68 deeltests**, zonder fouten/skips.
  De 11 echte C++-peers zijn opnieuw gebouwd. Elke run gebruikte een eigen
  lokale MQTT-testserver; de drie servers zijn gestopt en hun verwijdering
  onafhankelijk bevestigd. Bestaande containers bleven behouden. Vijf bestaande
  afhankelijkheidswaarschuwingen per run zijn niet onderdrukt.
- **Actuele E32-build op `b0abca7`:** firmware en bestandssysteem slagen,
  evenals de ongewijzigde standaard-TX-/layoutverifier. Alle **34 webbestanden**
  zijn byte-exact aanwezig; bron-/webmarker klopt. Image: **2.828.096 bytes**.
- **Actueel afzonderlijk HA-pakket:** 87 integratiebronbestanden zijn byte-exact
  met de bron vergeleken, pakket en checksums slagen met het verse Core.4-rapport.
  De nieuwe diagnostische kenmerken zijn hiermee meegenomen. Dit is geen
  bijgewerkte volledige E32-distributiebundel of een nieuwe installatie.
- Stuurcode, bordconfiguratie en partities zijn ongewijzigd sinds `0acae7c`.
  Het eerdere bewijs van **1059 native tests**, **190 strikte ASAN/UBSAN-
  proef-/encodergevallen**, drie firmwarevarianten en 146 scriptcontroles blijft
  aan die code gekoppeld. De uitgebreidere SDK-adapterset heeft **19 tests**
  met onder andere 15 geïnjecteerde foutcombinaties (`ecfee08`).
- De afzonderlijke handmatige E32-compileproef slaagt; objectcontrole vindt
  `uart_write_bytes` uitsluitend in `EmsController.cpp.o`. Algemene TX en
  warmte-installatievrijgave bleven uit; tijdelijke proefimages zijn verwijderd.
  Deze compileerproef is nu ook een verplichte afzonderlijke CI-job. Dit is geen
  fysieke zendvrijgave of bewijs dat die nieuwe CI-job al op GitHub heeft gedraaid.
- **Eerdere volledige distributiepreflight op `0acae7c`:** 2065 E32-
  pakketcontroles, 629 onafhankelijk gecontroleerde SDK-/runtime-eenheden,
  exacte en werkelijk gewijzigde herlinkproef, volledige bron-/licentiebundel
  en toenmalige HA-/E32-archiefvergelijking. De vendorobjecten zijn uit de
  bestaande cache gecontroleerd, niet opnieuw als vandaag gecompileerd aangemerkt.
- Webbron is ongewijzigd sinds de geslaagde `c719ca3`-browsercontrole: NL/EN,
  drie schermformaten en de echte root/auth/fragmentroute. De eerdere vier
  configuratiegevallen en overige bevestigings-/downloadcontroles blijven
  behouden. Browserbewijs is geen fysieke proef.

Bewijs van de aanvullende controle: `out/beta-current-integration/`.
De lokale pakketproeven gebruiken nog de bestaande versievelden beta.1 /
0.4.0b1. Deze artifacts zijn **uitsluitend auditmateriaal**, geen nieuwe
publicatie- of installatiekandidaten. Bestaande tags/assets mogen hiermee niet
worden vervangen. De oorspronkelijke fysieke TX-blokkade blijft van kracht.

B11 verlangt passend bewijs op de definitieve bron-/versiefreeze. De lokale
integratiecontrole sluit geen installatie-, zend-, stop-, comfort- of
Bluetoothbereikproef af. De ingekorte NL/EN-conceptnotities bewaren hun volledige
eerdere tekst in een afzonderlijk gekoppeld archief.

## Bestaande productroadmap blijft staan

Alle 31 eisen en werkpakketten blijven op het [werkbord](WORKBOARD.nl.md).
Open blijven onder andere actieve bron-/kraankoppeling, schaal-/duurproeven,
zelfleren en blijvende gevalideerde parameters per ruimte, groepen/vloer/menger,
comfortfuncties, aanvullende Bluetoothmodellen en BLE-proxy. De EMS-referentie
met entiteiten en telegramnamen is metadata; dit is geen volledige functionele
EMS-ESP-dekking. Het ketelprofiel mag ontvangen ondersteunde velden niet beperken.

## Vaste releaseafspraken

- Eén gezamenlijke bèta; alle voorbereide bron meenemen en beperkingen zichtbaar houden.
- Geen automatische ketel-/kraanproef, herstart of installatie door een statuscontrole.
- Geen volgende reguliere E32-release zonder vastgelegd bewijs dat de native
  GitHub-update en onafhankelijke nacontrole van de vorige release slaagden.
  Zie [updateproces](E32-UPDATE-PROCES.nl.md).
- HA-installatie via de bestaande native HA-specialist, met back-up en nacontrole.
- Engelse GitHub-gebruikersnotities met nieuwe functies, fixes, bijwerken en beperkingen:
  [actuele beta.4-conceptnotities](BETA4-RELEASE-NOTES-DRAFT.en.md),
  [notitieproces](RELEASE-NOTES-PROCES.nl.md).
- Alle details en oudere checkpoints blijven vindbaar in de
  [historie](NEXT-RELEASE-HISTORY-20261026.nl.md); die is geen actuele afvinklijst.

## Kandidaatcontrole 26 oktober — b2 afgekeurd

Commit `07a9937` doorstaat boards/pakket, browser, bronreproductie en alle
2.450 HA-checks op elk van Core2026.10.2/.3/.4. De uitgebreide native CI
faalt in de logging-runtimefixture: die verwacht EMS-syslog terwijl de fixture
de standaard uitgeschakelde EMS-bron niet inschakelt. De productstandaard
ESP-aan/EMS-uit blijft behouden; de fixture kiest EMS nu expliciet en slaagt
lokaal met de echte loopback-UDP-/NVS-/SDK-hooktest. Beide b2-publicatieruns
zijn geannuleerd; tags blijven ongewijzigd. De herstelde gezamenlijke kandidaat
is beta.3 / HA0.4.0b3 en vereist eigen volledige tag-CI en pakketcontrole.

## Publicatie beta.3 / HA0.4.0b3 afgerond

Beide releases uit `996587d` zijn gepubliceerd en onafhankelijk gecontroleerd.
Zie [publicatieverslag](PUBLICATIE-BETA3-20261026.nl.md) en het bijbehorende
geanonimiseerde JSON-rapport. Installatie, verse back-up en live nacontrole zijn
niet uitgevoerd: de bestaande HA-beheertool is in deze sessie niet beschikbaar.
Dit is geen vastgestelde verbindingsstoring van de apparaten. De installatieopdracht
blijft open; updatepoort pending beta.3, accepted beta.1 ongewijzigd.

## Websessies herstellen — bron voorbereid na beta.3

De gebruiker zit buiten de webinterface met vier bezette sessieplaatsen en kan
zonder geldige cookie niet afmelden. Een gesloten browser of verwijderde cookie
beëindigt de bootlokale sessie niet; de absolute geldigheid is zeven dagen.
De melding over vier aangemelde browsers was daarom misleidend.

De bron voegt expliciet herstel toe aan de bestaande login. Na `session_capacity`
verschijnt een keuze om eerdere websessies te beëindigen. De gebruiker moet die
keuze aanvinken en het wachtwoord opnieuw invoeren. Hetzelfde POST-loginendpoint
controleert gebruikersnaam, wachtwoord, formulier, origin en pogingslimiet;
geen nieuwe openbare beheerroute of automatische verdringing bij gewoon aanmelden.
Pas na geldige nieuwe tokens worden alle oude sessies en readbackbewijzen
verwijderd en één nieuwe sessie uitgegeven. Ongeldige invoer, mislukte entropie
of een alias laat oude sessies intact. Een actieve ketelproef of een werkende,
gestagede of nog onbevestigde firmware-update blokkeert herstel.

Gerichte controles: 20 native WebAuth-tests, 17 JavaScript-auth/login-tests,
3 taaltests en 9 scenario's met de werkelijke C++-loginhandler en gesimuleerde
HTTP-/apparaatgrenzen. De aangepaste E32-build slaagt.
Dit is nog niet gepubliceerd of geïnstalleerd; beta.3 is hiermee niet gewijzigd.
Voor de bestaande firmware wist een handmatige herstart van uitsluitend de E32
bootlokale sessies en behoudt opgeslagen instellingen. Alleen uitvoeren als er
geen update of ketelproef loopt; geen ketelreset, factory-reset of automatische
herstart vanuit diagnose. De bestaande installatieopdracht blijft open.

## Automatisch vervallen ongebruikte websessies — vervolg op herstart

De gebruiker heeft de E32 handmatig herstart en vraagt om automatisch verval.
De bron voegt **30 minuten zonder toegelaten geauthenticeerde HTTP-aanvraag**
toe aan de bestaande absolute grens van zeven dagen. Geldige aanvragen na
method/origin/auth/CSRF- en mutatiecontroles vernieuwen uitsluitend `lastSeen`
van hun eigen sessie. Een nog communicerend dashboard blijft dus aangemeld;
een achtergelaten beheersessie zonder aanvragen houdt geen plaats zeven dagen vast.
Opzoekingen of afgewezen aanvragen vernieuwen niets. Verlopen tokens worden
niet hersteld door late aanvragen; een nieuwe login kan de vrijgekomen plaats
hergebruiken. Bij klokterugloop wordt geen sessie vernieuwd. `expires_in` geeft
de kortste resterende termijn weer. De cookie heeft nog steeds maximaal zeven
dagen geldigheid; de server handhaaft de kortere inactiviteitsgrens.

De eerder voorbereide expliciete hersteloptie met nieuwe wachtwoordcontrole
blijft behouden. Login-uitleg is aangepast in EN/NL. Gerichte regressies: 24 native
WebAuth-gevallen, 20 JavaScript-auth/taalgevallen en 9 scenario's met de werkelijke
C++-loginhandler tegen gesimuleerde HTTP-/apparaatgrenzen slagen. De E32-build
slaagt eveneens. Nieuwe firmware
is nog niet gepubliceerd of geïnstalleerd; de gebruikersherstart levert deze
bronwijzigingen niet vanzelf op. Geen extra herstart of apparaatmutatie uitgevoerd.

## Algemene ketelillustratie als terugval — bron voorbereid

Op gebruikersverzoek toont een geselecteerd ketelprofiel zonder eigen foto nu
een neutrale, merkloze ketelillustratie op Home en bij Mijn ketel. De originele
SVG zit in de lokale interface en vraagt geen externe afbeelding op. Ook een
niet-ladende productfoto valt terug op deze illustratie; de bronvermelding van
die ontbrekende foto wordt dan verborgen. Een beschikbare modelgebonden foto
behoudt haar eigen beeld, modelomschrijving en bronvermelding. Geen geselecteerd
of een onbekend profiel krijgt nog steeds geen ketelbeeld.

Cataloguscontrole, drie taaltests en de bestaande echte Chromiumregressie op
vier schermprofielen slagen, inclusief opgeslagen model na herladen, offline
foto, mobiele weergave en behoud van de ketelkeuze. Alleen lokale gesimuleerde
HTTP/opslag; geen apparaat gewijzigd. Dit bronwerk is nog niet gepubliceerd of
geïnstalleerd en verandert de bestaande beta.3-release niet.

## Volgende release voorbereiden — E32 beta.4

De gebruiker vraagt de volgende release te maken. Het concrete concept staat in
[BETA4-KANDIDAAT.json](BETA4-KANDIDAAT.json), met
[Engelse conceptnotities](BETA4-RELEASE-NOTES-DRAFT.en.md). De drie nieuwe
E32-functies worden samen gebundeld; HA blijft op zijn bestaande openbare b3-versie.
De drukprofielaanpassing en actieve ketelvrijgave horen niet bij deze reparatiebundel.

De volledige bron-CI op `210f71f` is geslaagd: browserregressies, afzonderlijke
handmatige compileerroute, bronreproductie, native HA en builds voor native,
E32 V2, ESP32-S3 en ESP32dev.
[CI-run 40311201734](https://github.com/dielessen/open_thermostat/actions/runs/40311201734)
publiceerde niets; de publicatiejobs zijn overgeslagen. Dit is bewijs voor deze
broncommit, niet voor een toekomstige versiefreeze of installatie. Twee eerdere
browserjobs bereikten hun 15-minutenlimiet nadat afhankelijkheidsinstallatie
het grootste deel daarvan verbruikte. De CI krijgt daarom 30 minuten totale
jobtijd, met een afzonderlijke limiet van 15 minuten voor de echte browserscenario's;
geen test of publicatiepoort wordt overgeslagen. De actuele branch wordt opnieuw
volledig gecontroleerd. Bronartefacten met nog beta.3 als ontwikkelversie zijn
geen nieuwe release of installatiedoel en vervangen de bestaande beta.3-assets niet.

Beta.3 staat nog pending in de updatepoort. Tot echte installatie en onafhankelijke
nacontrole zijn vastgelegd blijven release.json, pending_tag en de openbare tags
ongewijzigd. Gewoon bronwerk, conceptnotities en CI gaan door; een beta.4-freeze
of publicatie wordt niet als gereed afgetekend. De gebruiker heeft aangegeven
zelf te installeren; in deze stap worden geen apparaatmutaties uitgevoerd.

## Schrijfbare ketelentiteiten — ontbrekende functionele dekking

De gebruiker meldt dat de schrijfbare EMS-ESP-ketelentiteiten in de E32 ontbreken.
Dit blijft expliciet open productwerk en wordt niet afgetekend met de beta.4-
sessiereparaties. De reproduceerbare [schrijfinventaris](BOILER-WRITE-INVENTORY.json)
bevat alle 1.907 schrijfbare ketelvermeldingen uit de vastgelegde, hashgecontroleerde
referentie: 117 unieke namen in 31 productgroepen. Deze brede lijst bewijst geen
ondersteuning door de Ecomline Classic/EasyControl-keten. Type, opties, grenzen,
eenheid en productgroep blijven per variant bewaard.

De huidige uitzondering is de begrensde handmatige `selflowtemp`-proefencoder
voor `0x1A`; algemene instellingenbediening ontbreekt. Per veld moeten de
model-/adapterondersteuning, telegrammapping, schaal, encoder, toegelaten grenzen,
bevoegdheid en latere readback worden vastgesteld en getest. Daarna volgen
NL/EN-bediening en expliciete fout-/onbeschikbaarstatus. Ook reset-, onderhouds-,
tapwater-, pomp- en vermogenscommando's blijven zichtbaar in de inventaris;
referentiemetadata verleent geen schrijfbevoegdheid. Algemene TX blijft uit.

Reproduceren: `python3 scripts/inventory_boiler_writes.py --check`.
De bron-CI hierboven ging vooraf aan deze inventaris-/documentatieaanvulling.

## Eerste Classic-instellingenencoders — bronwerk na releasevoorbereiding

`ClassicBoilerSettingsEncoder.h` bevat nu afzonderlijke éénbyte-encoders voor
`heatingactivated` (0/1 → 0x00/0xFF, offset 0), `heatingtemp` (0–90 °C,
offset 1), `burnminperiod` (0–120 minuten, offset 6) en `pumpdelay` (0–60 minuten,
offset 8), alle via `0x16`. Dit zijn protocolgrenzen, geen installatiespecifieke
advieswaarden. Zij wijzigen blijvende instellingen en zijn gescheiden van de
tijdelijke `0x1A`-warmtevraag. De protocolfeiten zijn gecontroleerd tegen
[EMS-ESP32 v3.8.6 boiler.cpp](https://github.com/emsesp/EMS-ESP32/blob/v3.8.6/src/devices/boiler.cpp),
SHA256 `42505c773bcbf6631718abd517d61ee5dec9bcf429b2123d402a69ed5445503e`.
Er is geen upstream stuurimplementatie overgenomen.

De encoder vereist expliciete Classic-kwalificatie en beoordeelde adressering;
onbekende instellingen en waarden buiten bereik leveren geen frame op.
Terugleesvergelijking vereist de exacte waarde in een boilerantwoord aan het
serviceadres; echo's, broadcasts, andere adressen, verkeerd telegramtype en
ontbrekende fragmentbytes voldoen niet. Boot/revisie, oorspronkelijke ontvangsttijd,
uiterste antwoordtijd en bedienbevoegdheid moeten nog in de transactielaag worden
aangesloten. De encoder alleen bewijst geen latere ontvangst of schrijfacceptatie.

De nieuwe native tests bestrijken alle invoerwaarden van -256 tot en met 512 per
instelling en afwijzing van onjuiste antwoordroutes. De suite wordt tevens in de
bestaande ASAN/UBSAN-CI-opdracht meegenomen. Geen HTTP-, HA-, web- of UART-route
is hierop aangesloten. Geen firmware gepubliceerd, geïnstalleerd of ketelinstelling
gewijzigd. Dit is aanvullende encoderbouw; algemene schrijfbediening blijft open.

## Begrensde instellingstransactie — voorbereid, nog niet aangesloten

De vier Classic-instellingen hebben nu een afzonderlijke bootlokale
`ClassicBoilerSettingTransaction`: één write, vervolgens op een nieuwe poll één
leesverzoek voor precies dezelfde byte. Alleen een passend boilerantwoord aan
serviceadres `0x0B`, oorspronkelijk ontvangen ná afronding van dat leesverzoek,
kan de instelling als teruggelezen bevestigen. Oude/toekomstige ontvangsttijden,
echo's, broadcasts, gedeeltelijke of afwijkende antwoorden geven geen bevestiging.

Toelating vereist een passende boot, interne bedieneridentiteit, opeenvolgende
revisie en nieuwe verklaringen over exclusief busbezit en onafhankelijke stop.
De aanroepende laag moet authenticatie, Classic-capability, installatievrijgave,
sessie en uitsluiting van OTA/ketelproef daadwerkelijk aanleveren. De klasse is
standaard uitgeschakeld en registreert geen HTTP- of UART-route.

Elke pollfase vervalt na 5 seconden; antwoordwachten na 15 seconden. Een nieuwe
expliciete poging vraagt minimaal 30 seconden sinds voorbereiding. Identieke
verzoeken vernieuwen niets; een andere bediener of gewijzigde intentie kan een
revisie niet hergebruiken. Voor verzending worden tijd en toestemming opnieuw
gecontroleerd, ook wanneer de toestemmingscontrole zelf tijd verbruikt. Onzekere
of mislukte IO, uitzonderingen, klokterugloop en rechtenverlies stoppen definitief
zonder automatische herhaling. Een begonnen write blijft als mogelijk uitgevoerde
wijziging gemarkeerd, ook zonder terugleesbewijs. Er is geen automatische rollback.

De zendcallback bevestigt uitsluitend emissie/echo. Een afzonderlijke, aan de
revisie gebonden UART-callback moet daarna een positieve schrijfstatus en geslaagde
busafsluiting bevestigen voordat het leesverzoek wordt klaargezet. De bestaande `ManualClassicTransaction` accepteert deze nieuwe frames
nog niet. Die aansluiting, transactiestatus via beveiligde HTTP, NL/EN-bediening,
actuele model-/installatiekwalificatie en fysieke readback blijven open. Algemene
TX, warmteproefvrijgave en bestaande releasepoort blijven ongewijzigd.

Gerichte lokale controle: 12 transactietests plus 3 encodertests slagen met strikte
compilerwaarschuwingen en ASAN/UBSAN. Tests bestrijken ook deadlines tijdens
trage toelatingscontroles en herintredende IO. De nieuwe transactiesuite staat
in dezelfde CI-opdracht als de bestaande handmatige ketelproeven. Dit is geen
GitHub-CI-resultaat of fysieke schrijfacceptatie van deze bronwijziging.

De volledige lokale ASAN/UBSAN-opdracht voor de handmatige ketelroute uit
`.github/workflows/build.yml` is daarna opnieuw gecompileerd en uitgevoerd:
**205 tests in 21 suites geslaagd**, inclusief de 15 encoder-/transactiegevallen.
Release-inventaris (450 bronverwijzingen), EMS-referentie en diffcontrole slagen.
Er is geen firmwarebuild of openbare releaseacceptatie aan deze uitslag ontleend.

## UART-aansluitcontrole — asynchrone schrijfbevestiging

De werkelijke UART levert schrijfstatus later aan. Daarom heeft de nieuwe
instellingstransactie nu een afzonderlijke fase `waitingWriteStatus` en een
revisiegebonden `writeClosed`-callback. Emissie/echo levert geen toestemming
voor de volgende leesactie. Negatieve status, ontbrekende of te late afsluiting,
rechtenverlies en klokterugloop beëindigen de poging. De wachtgrens is 200 ms,
overeenkomstig het bestaande softwareantwoordvenster; dit is geen gemeten
adaptergarantie. De UART-eigenaar moet de oorspronkelijke microsecondevolgorde
en daadwerkelijke afsluit-IO bewijzen voordat hij de callback aanroept.

De gewijzigde encoder-/transactiesuite slaagt lokaal: 17 tests met strikte
waarschuwingen en ASAN/UBSAN. De hierboven genoemde 205 tests zijn de eerdere
volledige run vóór deze asynchrone correctie. Er is nog geen nieuwe volledige
CI- of firmwarebuild voor deze correctie vastgelegd. De bestaande UART-whitelist
is niet verruimd, geen HTTP-route toegevoegd en geen fysieke write uitgevoerd.

## Raam- en deursensoren — expliciete productscope R21

De gebruiker bevestigt dat raam- én deursensoren ontbreken in het overzicht.
Beide horen bij de kamerinrichting, met één of meer geselecteerde contacten per
kamer, herkenbare naam, sensortype en zichtbare open/dicht/onbekend-status.
De bestaande raam-/zone-inhibitpolicy is geen complete sensorfunctie.

Nog te bouwen: normale sensorselectie en opslag/apply via het actuele
SOURCE-contract, oorspronkelijke bronactualiteit en beschikbaarheid, instelbare
reactie per contact, vertraging tegen kort openen/contactdender en gecontroleerd
hervatten met behoud van programma/override. Bij meerdere contacten mag één
sluitbericht geen pauze opheffen zolang een ander geldig contact nog open is.
Een ontbrekende of verlopen sensor wordt onbekend, niet automatisch gesloten.

Raamcontacten kunnen de betrokken kamer tijdelijk pauzeren. Deurcontacten krijgen
een afzonderlijke keuze voor alleen status of ook kamerpauze; het label deur
geeft niet automatisch dezelfde verwarmingsreactie als een raam. De interface
moet de actieve reden en betrokken sensor tonen. De gekozen reactie werkt samen
met het bestaande vorst-/storingsbeleid en mag dat niet opheffen.

De eerste koppelroute gebruikt geschikte bestaande HA-contactentiteiten; directe
Bluetooth-ondersteuning vereist een eigen ondersteund modelprofiel. Dit is een
expliciete roadmapaanvulling, geen al gebouwde editor, sensorroute of vrijgave.

## Afzonderlijke instellingen-buswisseling — lokaal gecontroleerd

`ClassicSettingBusExchange` bewaakt uitsluitend de vier exacte instellingen-
intenties, met revisie, originele microsecondeontvangsttijd en eindige afsluiting.
Een positieve schrijfstatus geeft pas na geslaagde busafsluiting een
`writeClosed`-event; het terugleesantwoord krijgt apart `readClosed`. Een passend
antwoord met afwijkende waarde kan de bus sluiten, maar bevestigt de instelling
niet. Geen tweede afsluiting na replay, fout of uitzondering. Een stille bus
verliest zijn wisseling op de 200ms-softwaredeadline.

28 gerichte encoder-/transactie-/busgevallen slagen met ASAN/UBSAN, inclusief
een geïntegreerde write → status/afsluiting → read → antwoord/afsluiting →
terugleesbevestiging. De oude `ManualClassicTransaction` weigert aantoonbaar
alle nieuwe instellingenframes. Er is geen fysieke UART-/HTTP-aansluiting of
nieuwe zendvrijgave; dit onderdeel is voorbereide broncode.

## Instellingen-API aangesloten — schrijven blijft uit

De E32-controller heeft nu twee routes onder de bestaande sessie-, origin-,
method- en CSRF-bescherming: GET `/status/boiler/settings` toont de vier vaste
Classic-definities met grenzen, eenheid, telegram en offset; POST
`/boiler/settings/write` controleert een begrensd JSON-verzoek. Het statusantwoord
verzint geen huidige instellingwaarde en bevat geen sessietoken. Deze definities
zijn nog geen bewezen mogelijkheden van de fysieke ketel.

De requestservice controleert boot, revisie, exacte veldnaam, gehele waarde,
protocolgrenzen en beide opstellingsverklaringen. Een andere bediener kan een
revisie niet hergebruiken; een identiek verzoek herhaalt geen opdracht. Updates
(in uitvoering, staged of pending boot) en actieve ketelproeven blokkeren de
schrijfroute via de bestaande requestwrapper.

De productiecontroller construeert de service expliciet met een afzonderlijke
bronpoort op `false` en geeft geen zendtoestemming door. Ook met juiste invoer
volgt daarom HTTP409 `settings_transport_unqualified`, nooit een geaccepteerde
schrijfopdracht. De bestaande handmatige TX-buildflag opent deze instellingenroute
niet. Web-/HA-bediening, echte UART-koppeling, sessie-uitval tijdens uitvoering en
fysieke kwalificatie blijven open. De GET-route leest uitsluitend lokale metadata.

De E32-firmware en het bestandssysteem bouwen; de ongewijzigde standaard-TX-/
partitieverifier slaagt met een firmwareimage van 2.836.992 bytes. Dit lokale
ontwikkelimage is auditmateriaal, geen publicatie- of installatiedoel.

De aanvullende volledige native run slaagt: **1.100 tests**. De exacte bijgewerkte
ASAN/UBSAN-CI-opdracht voor de ketelroute slaagt eveneens: **225 tests in 23
suites**, inclusief de zeven instellingenservicegevallen. Verkeerde methoden,
update-/proefblokkade, onjuiste/extra/dubbele JSON-velden, boot, verklaringen,
bereik, bediener en idempotentie zijn gecontroleerd. De firmware-/bestandssysteem-
build en ongewijzigde standaard-TX-/partitiecontrole slagen. Lokaal bewijs met
bronhashes en native log: `out/beta4-settings-api/`. Dit is geen GitHub-tag-CI,
API-proef op het apparaat, publicatie of fysieke installatieacceptatie.

## Instellingenoverzicht in de E32-webbron

Instellingen → EMS-apparaten toont nu boven de ontvangen apparaten de vier
voorbereide CV-instellingen. Het overzicht koppelt alleen werkelijk ontvangen
`0x16`-waarden uit de bestaande veldsnapshot aan de vaste definities. Geldige
waarden vereisen een passende bron/eenheid, gerapporteerde kwaliteit en bekende
leeftijd binnen de oorspronkelijke 10min-TTL. Ontbrekend, ongeldig, verlopen of
onbevestigd bewijs wordt geen nulwaarde of bevestigde instelling. De oorspronkelijke
ontvangen waarde wordt niet op het encoderbereik begrensd.

De pagina toont geen bewerkingsvelden of schrijfknop. NL/EN-uitleg houdt
protocolbereik, ontvangen waarde en daadwerkelijke ketelondersteuning apart.
Desktop gebruikt een tabel; op mobiele schermen staan waarde, status, leeftijd
en bereik per instelling onder elkaar. Een metadatafout verbergt geen ontvangen
EMS-metingen; bij een mislukte meetmomentopname worden eerdere instellingen niet
als actuele waarden getoond. Beide GET-aanvragen zijn begrensd en worden bij
navigatie ingetrokken. Geen polling, busquery of POST vanuit dit overzicht.

De echte Chromiumregressie slaagt op EN/NL × 1280/390/320 px, met ontvangen,
ontbrekende en verlopen waarden, verkeerde bron, ongeldige/prototype-veldnaam,
metadata-uitval, snapshot-uitval en navigatie. Alle aanvragen blijven GET;
geen apparaatverkeer. Drie taal-/cataloguscontroles slagen. Browserbewijs en
screenshots staan in `out/ems-devices-browser/`; ontwikkelbuildbewijs in
`out/beta4-settings-web/`. Publicatie, installatie en echte schrijfbediening
blijven afzonderlijk open.

De definitieve lokale webbron bouwt in firmware én bestandssysteem; de
ongewijzigde standaard-TX-/partitieverifier slaagt. Ontwikkelimage: 2.843.376 bytes.
Geen versievelden, openbare assets, updatepoort of apparaten gewijzigd.

## Instellingen-UART: afzonderlijke laatste SDK-controle voorbereid

De vier protocoldefinities staan nu in een kleine zelfstandige specificatie,
gedeeld door encoder en SDK-grens zonder JSON-, logger- of decoderafhankelijkheid.
De afzonderlijke `ClassicSettingUartWrite` vergelijkt vóór elke pinactie lengte,
vaste bron `0x0B`, bestemming, type `0x16`, instellingoffset, exacte toegelaten
waarde en zelfstandig berekende checksum. Voor teruglezen geldt apart bestemming
`0x88` en precies één gevraagde byte. Onbekende instellingen, verkeerde intenties
en frames buiten deze voorwaarden krijgen geen UART-/GPIO-voorcontrole of pinactie.

De SDK-adapter gebruikt dezelfde read-only UART-voorcontrole, echoafhandeling en
pinvrijgave als de bestaande handmatige route. De oude toegestane telegrammen
zijn niet verruimd. Beide paden delen nu alleen de SDK-operaties. Een mislukte of
uitzonderlijke voorcontrole raakt geen pin; na een begonnen koppeling wordt
vrijgave altijd geprobeerd. Mislukte vrijgave kan geen succes opleveren.

De nieuwe grens is nog niet aangesloten op een productie-UART-eigenaar. Een
resultaat met mislukte vrijgave moet bij die latere koppeling ook blijvend verdere
writes blokkeren. Alle TX-/instellingenpoorten blijven ongewijzigd dicht; de
instellingen-API blijft HTTP409 retourneren. Geen fysieke write of vrijgave.

Gerichte lokale controles slagen met strikte compilerwaarschuwingen en
ASAN/UBSAN: 7 nieuwe grensgevallen plus 3 bestaande encodertests; de echte
SDK-adapterfixture heeft 23 geslaagde gevallen. De grenssuite controleert ook
alle 2.550 gewijzigde inhoudsbytes met opnieuw geldige CRC, 255 onjuiste
checksumbytes, alle invoerwaarden -256 t/m 512, onjuiste lengte en geïnjecteerde
voorcontrole-/koppel-/schrijf-/vrijgavefouten. De SDK-fixture controleert nieuwe
write/readframes, verkeerde intentie, bezette UART, echoafwijking, late RX en
ieder van de drie pinvrijgavestappen. Dit is hostbewijs, geen hardwareproef.

De uitgebreide lokale nacontrole van deze SDK-wijziging slaagt: **1.107 native
gevallen**, **232 ASAN/UBSAN-ketelroutegevallen in 24 suites** en **23 SDK-adapter-
gevallen**. E32-firmware, bestandssysteem en de ongewijzigde standaard-TX-/
partitieverifier slagen; ontwikkelimage 2.843.360 bytes. Bewijs met bronhashes en
build-/nativelogs: `out/beta4-settings-uart/`. De webbron en HA-code zijn in deze
stap ongewijzigd; hun eerder vastgelegde controles blijven afzonderlijk staan.
Dit is geen definitieve kandidaatfreeze, publieke tag-CI, apparaatinstallatie of
fysieke schrijfacceptatie. Beta.3-installatieacceptatie blijft de releasepoort.

## Instellingenservice: interne transportketen gekoppeld en bewaakt

De instellingenservice verbindt nu de eenmalige transactie, exacte buswisseling
en intentiegebonden SDK-zendcallback. De zendcallback krijgt de oorspronkelijke
instelling, waarde en read/write-variant. Een write-echo geeft nog geen readpoll;
pas positieve schrijfstatus én geslaagde afsluiting maken de gerichte read vrij.
Een passend, later ontvangen en afgesloten antwoord met de juiste waarde levert
terugleesbevestiging op. Een afwijkende of niet tijdig bevestigde waarde sluit
de poging af zonder automatische herhaling.

Iedere zend-, afsluit- en tickcontrole vraagt de aanroepende laag opnieuw om
actuele toestemming voor de oorspronkelijke interne sessie-identiteit. Verlies
van die toestemming stopt de poging. De service kan de oorspronkelijke bediener
ook expliciet intrekken; een andere token trekt die niet in. Een identiek verzoek
bij wachten op schrijfstatus herhaalt niets. Herintredende IO kan de intentie niet
vervangen. Een terugleesantwoord wordt vóór afsluit-IO lokaal gekopieerd, zodat
wijziging van de oorspronkelijke buffer geen ander meetbewijs oplevert.

Mislukte pinvrijgave en onzekere zend-/afsluituitzonderingen zetten een blijvende
transportfout: latere revisies krijgen geen opdrachttoelating. Een fout wist de
busbevoegdheid; late antwoorden krijgen geen afsluitbyte of succes. De status
vermeldt `transport_fault`, zonder sessietoken of grantgegevens. De service moet
onder één controller-eigenaar worden aangeroepen; zij bevat geen eigen taak of
achtergrondpoller.

De gate is een expliciet contract met de toekomstige controller, geen reeds
gekoppelde controle op de echte HA-/websessie. De productiecontroller gebruikt
nog steeds de afzonderlijke bronpoort `false` en toestemming `false`. UART-loop,
werkelijke sessie-intrekking/uitval, OTA-/proefuitsluiting tijdens uitvoering,
model-/installatiekwalificatie en fysieke write/readback blijven aan te sluiten.
Er is geen instellingencommando of apparaatmutatie uitgevoerd.

Elf nieuwe geïntegreerde hostgevallen slagen met ASAN/UBSAN: volledige keten,
late/afwijkende readback, verlies van sessietoestemming in alle fasen, expliciete
intrekking (ook tijdens IO), blijvende zend-/pin-/afsluitfout, clockexception,
herintreding, idempotentie en wijziging van de ontvangstbuffer tijdens afsluiting.
Dit zijn gesimuleerde transport-/SDK-callbacks, geen ketelproef.

De gezamenlijke gerichte instellingenregressie slaagt op deze bron: **53 gevallen
in zes suites met ASAN/UBSAN**, inclusief de 11 nieuwe ketengevallen. E32-firmware,
bestandssysteem en de ongewijzigde standaard-TX-/partitieverifier slagen;
ontwikkelimage 2.843.680 bytes. Bewijs met bronhashes en buildlogs:
`out/beta4-settings-pipeline/`. De vorige volledige native/ketelroute-/SDK-runs
blijven eerdere checkpoints; zij worden niet als nieuw uitgevoerd aangemerkt.
Geen publicatie, installatie of wijziging van de beta.3-updatepoort.

## Werkelijke websessie aan instellingenopdracht gebonden

De HTTP-/controllerkoppeling projecteert nu de oorspronkelijke sessiegeldigheid
naar de instellingenservice. De sessietabel wordt uitsluitend op de bestaande
HTTP-thread gelezen; de projectie staat onder de telemetrie-/controllerlock.
Een toekomstige UART-aanroep leest alleen de bewaarde monotone deadline, nooit
rechtstreeks de niet-threadveilige websessietabel. De projectie verandert geen
`lastSeen`, sessie-expiratie of transactie-/antwoorddeadline.

Een geaccepteerde opdracht krijgt haar sessiebewijs binnen dezelfde controllerlock.
Vóór en na HTTP-afhandeling wordt het bewijs met de echte sessie vergeleken.
Afmelden en geslaagde vervanging/herstel van sessies synchroniseren bovendien
onmiddellijk na de werkelijke intrekking. De oude opdracht wordt niet overgenomen
door de nieuwe login. Ongeldige credentials, entropy-/capaciteitsfout en geweigerd
herstel trekken via de loginhandler geen geldige eigenaar in.

Elke IO-toelating toetst de bewaarde deadline opnieuw. Ook als HTTP-afhandeling
stilvalt mag de opdracht niet voorbij de oorspronkelijke inactiviteits- of
absolute sessiegrens doorgaan. Ontbrekend sessiebewijs, klokterugloop en een
werkelijk ingetrokken sessie leveren geen vervolgzending of afsluitbyte op.
Een later opnieuw geldige sessie hervat de terminale poging niet automatisch.

Lokale gerichte regressie: **59 instellingengevallen in zes suites met
ASAN/UBSAN**, waaronder 17 geïntegreerde keten-/sessiegevallen. De echte C++-
login-/logout-handler slaagt in **11 scenario's**, inclusief expliciete intrekking,
herstel, normale vervanging en behoud bij weigering. E32-firmware/bestandssysteem
en de ongewijzigde standaard-TX-/partitiecontrole slagen; ontwikkelimage
2.844.208 bytes. Bewijs: `out/beta4-settings-session/`.

De productieservice blijft met bronpoort `false` en zendtoestemming `false`
geconstrueerd. De productie-UART-loop, installatie-/modelkwalificatie en actieve
uitsluiting van concurrerende uitvoer blijven afzonderlijk open. Geen apparaten,
versies, openbare pakketten of beta.3-updateacceptatie gewijzigd.

## Productie-UART-route aangesloten — afzonderlijke poorten blijven dicht

De service is nu aangesloten op de eigen UART-polls en oorspronkelijke RX-tijd
in microseconden. Eén controller-eigenaar bewaakt request, sessieprojectie,
write/status/afsluiting en read/antwoord/afsluiting. Alleen een actuele eigen
poll kan een toegelaten frame aanbieden. Gedurende eigenaarschap wordt de oude
zendwachtrij geleegd en worden nieuwe legacyproducenten uitgesloten. De RX-route
gebruikt een niet-blokkerende lock; gemiste eigendomsoverdracht of UART-fout tijdens
een opdracht beëindigt die met een fout, zonder blinde herhaling.

De private SDK-methoden hebben een afzonderlijke bronconstante
`emsSettingsTransmitAllowed = false`, naast de ongewijzigd uitgeschakelde algemene
en handmatige TX-poorten. Bovendien blijft `settingsInstallationReviewed_ = false`.
Geen van deze toestemmingen kan via JSON, een modelillustratie, runtimeoptie of
buildflag worden aangezet. De normale firmware bevat nog steeds geen verwijzing
naar een fysieke UART-zendprimitive.

Runtime-toelating vereist beide settingspoorten, ingeschakelde EMS-ontvangst,
Classic-protocol, actuele adres-/masker-/transportvoorwaarden, geldige websessie,
geen proef of configuratie-uitlezing en geen werkende/staged/pending-bootupdate.
De HTTP/update-eigenaar publiceert de updatevoorwaarde onder dezelfde lock; de
UART-thread leest daarvoor geen updater-mutex of websessietabel. HTTP-afhandeling
en automatische updatechecks draaien op dezelfde hoofdloop. Een actieve
instellingenopdracht blokkeert concurrerende configuratie-/update-/proefwrites.
Idempotente herlezing van dezelfde schrijfopdracht, afmelden en Stop/foutafsluiting
blijven apart beschikbaar. Automatische updatechecks wachten op vrij eigenaarschap.

Een gewone UART-opstart of fout buiten een instellingenopdracht wordt niet ten
onrechte een blijvende instellingenfout. Een fout tijdens een actieve opdracht
blijft wel blokkerend. De bestaande warmteproef- en configuratie-uitleesroutes
lenen geen toestemming van de instellingenpoort en sluiten elkaar wederzijds uit.

Lokale controles: **64 gerichte ASAN/UBSAN-gevallen in zeven suites**, de **11 echte
login-/logout-handlerscenario's**, standaard E32-firmware/bestandssysteem en de
ongewijzigde standaard-TX-/partitieverifier slagen. Standaard ontwikkelimage:
2.845.856 bytes. Een afzonderlijke tijdelijke checkout compileert ook met alleen
de settings-bronconstante aan; installatievrijgave en beide andere TX-poorten
blijven uit. Uitsluitend `EmsController.cpp.o` verwijst daar naar `uart_write_bytes`;
andere schrijfprimitieven ontbreken. De tijdelijke images en checkout zijn na de
proef verwijderd, de gewone bron is nooit ontgrendeld.

De nieuwe verplichte CI-job `settings-route-compile` bewaakt deze aparte bronroute
vóór E32-publicatie. YAML en publicatiedependency zijn lokaal gecontroleerd; de
nieuwe job is nog niet op GitHub uitgevoerd. Lokaal bewijs met buildlogs en
compile-only-rapport: `out/beta4-settings-runtime/`.

Dit is software-integratie, geen model-/adapter-/installatievrijgave, echte
schrijf-/stopproef of installatieacceptatie. De vier instellingen blijven in de
webinterface alleen-lezen. Definitieve kandidaatcontrole en vastgelegde beta.3-
installatieacceptatie blijven vereist voordat beta.4 kan worden gepubliceerd.

## Bewerkingspad voor vier instellingen gebouwd — standaard alleen-lezen

De webbron heeft nu invoer, beide nieuwe opstellingsverklaringen en expliciete
bevestiging voor één blijvende instellingenwijziging. Het formulier verschijnt
alleen bij een volledig passende, door de server als beschikbaar aangeboden
status. De normale bron geeft die beschikbaarheid niet: beide settingspoorten
blijven dicht, dus de gewone firmware toont uitsluitend het bestaande overzicht.
Geen lokaal vinkje of frontendaanpassing opent de server-/UART-poorten.

Voor invoer gelden de vaste type-/bereikdefinities; aan/uit gebruikt een expliciete
keuze en numerieke waarden moeten gehele getallen zijn. Een voorstel krijgt
maximaal 30 seconden vanaf de lokale statusontvangst, zonder achtergrondpoller.
Vernieuwen, een andere instelling kiezen, onderbreking of een verzonden poging
vraagt nieuwe verklaringen. Authvoorbereiding en de bevestigingsdialoog worden
gevolgd door opnieuw toetsen van zichtbaarheid, paginaverbinding, generatie,
boot/revisie, invoer en verklaringen. Een tweede klik levert geen tweede POST.

De bestaande CSRF-wrapper verzorgt het ene POST-verzoek. De UI onderscheidt
HTTP-toelating van daadwerkelijke teruglezing. Daarvoor exporteert de API nu ook
fase, oorspronkelijke intentie, eigendom ten opzichte van de huidige sessie en
oorspronkelijke terugleestijd; geen token of grant. Alleen een nieuwe passende
status met dezelfde boot/revisie/intentie, huidig eigendom en terminale
terugleesbevestiging maakt de melding “teruggelezen” zichtbaar. Een eerdere
bevestiging verdwijnt bij het beginnen van een nieuw concept.

Netwerkverlies, een afwijkend/malformed antwoord of onduidelijk eigendom blijft
onzeker: geen automatische herhaling en geen heropening van het formulier door
een oude status. De gebruiker kan expliciet de status vernieuwen. Een afgesloten
passende poging of nieuwe boot wordt apart behandeld; nieuwe voorbereiding
vereist opnieuw invoer/verklaringen. Navigatie en verborgen worden breken lokale
voorbereiding af en trekken een lopende HTTP-aanvraag in. Dat draait een mogelijk
al toegelaten serveropdracht niet terug; daarom blijft de uitkomst dan onzeker.

Gerichte controles op de definitieve lokale bron: **65 ASAN/UBSAN-gevallen** in de
zeven instellingen-/runtime-suites; zes echte Chromiumprofielen voor bewerking
en zes voor alleen-lezen (EN/NL, 1280/390/320 px), plus drie taalcontroles.
De bewerkingstest gebruikt uitsluitend gesimuleerde HTTP-vrijgave, geen ketel:
integer/bool-invoer, CSRF, expliciete verklaring/bevestiging, annuleren, twee klikken,
verloren/malformed/andermans antwoord, handmatig teruglezen, weigering,
bevestigingsonderbreking, gewijzigde invoer, navigatie, verlopen voorstel en
onderbroken POST. Native statuscontrole bewaakt fase/intentie/eigendom en het
ontbreken van tokens in de export.

E32-firmware, bestandssysteem en de ongewijzigde standaard-TX-/partitieverifier
slagen; ontwikkelimage 2.859.152 bytes. Browserbewijs: `out/boiler-settings-browser/`
en `out/ems-devices-browser/`; build-/bronbewijs: `out/beta4-settings-editor/`.
De nieuwe browsertest staat in de verplichte CI-browserjob; deze aanvulling is
nog niet op GitHub uitgevoerd. Geen apparaatmutatie, publicatie of beta.3-
installatieacceptatie. Model-/installatiekwalificatie en de overige schrijfbare
entiteiten blijven open; vier voorbereide instellingen zijn geen volledige pariteit.

## Gezamenlijk ontwikkelcheckpoint vóór beta.4-freeze

De volledige voorbereide bron wordt nu als één gewoon ontwikkelcheckpoint op de
bestaande reviewbranch vastgelegd voor de complete CI: alle bordvarianten,
volledige native regressie, echte HA-cores, browserroutes, bronreproductie,
SDK-/licentie-/pakketcontrole en beide geïsoleerde zendroute-compileproeven.
De reproduceerbare schrijfinventaris is voortaan ook verplicht in CI.

Dit checkpoint is geen beta.4-versie-/kandidaatfreeze. `release.json`, openbare
tags/assets en de beta.3-updatepoort blijven ongewijzigd. Definitieve freeze,
publicatie en installatie vereisen nog de vastgelegde beta.3-installatieacceptatie.
De uitkomst van deze gezamenlijke preflight wordt lokaal bewaard onder
`out/beta4-current-preflight/`, met exacte commit en CI-identiteit. Oudere lokale
bronbewijzen blijven hun eigen bronhashes en beperkingen houden.

## Volledige ontwikkel-CI — OTA-fixture hersteld na eerste run

De eerste volledige run op `5edab0c` slaagt voor bronreproductie, beide aparte
compileproeven, ESP32/ESP32-S3 en het E32-distributiepakket. De native job heeft
**1.130 volledige native gevallen**, de afzonderlijke sanitizersuites en 24
authgevallen doorlopen, maar stopt bij de geëxtraheerde echte REST-OTA-handler:
de fixture miste de nieuwe controller-/sessie-/updateprojectie uit `handle()`.
Dit is geen geslaagde volledige CI-run; de fout blijft bij die bron vastgelegd.

De fixture gebruikt nu de echte begrensde sessieklasse en nagebootste controller-
en updaterranden. De oorspronkelijke productiehandler blijft ongewijzigd in de
proef. Bestaande assertions voor upload-/flash-/bootafhandeling blijven behouden;
nieuwe assertions controleren dat de settingsprojectie vóór HTTP toestaat en na
geslaagde app-installatie blokkeert. Geen test of releasepoort overgeslagen.

Lokale vervolgcontrole: 11 echte OTA-boundaryscenario's onder ASAN/UBSAN,
11 login-/logoutscenario's, 36 onboardinggevallen, catalogus-/referentiecontrole,
werkelijke logger-/NVS-/UDP-fixture en 38 HA-unittests slagen. De bestaande
vendorlogger-waarschuwing is niet onderdrukt. De gewijzigde fixture krijgt een
nieuwe broncommit en eigen volledige CI-run. De eerste run blijft historisch
vindbaar; beide runs worden lokaal gevolgd onder `out/beta4-current-preflight/`.
Geen firmware-/HA-productcode, releaseversie, tag of apparaat gewijzigd door
het herstel van deze fixture.
