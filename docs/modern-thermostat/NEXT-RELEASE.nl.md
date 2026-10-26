# Volgende gezamenlijke bèta — actueel uitvoeringsplan

Bijgewerkt op 26 oktober 2026. Status: **NOT_READY voor actieve ketelproeven**.
Dit document beschrijft het volgende werk; het [werkbord](WORKBOARD.nl.md)
bewaakt alle 31 producteisen en 14 eindcontroles. De
[release-inventaris](BETA1-RELEASE-INVENTARIS.json) bewaakt alle 23 voorbereide
onderdelen en hun 425 bronverwijzingen. De
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
| Geïnstalleerde E32 | `v0.1.0-e32v2-beta.1`, bron `5e3ed30`; passieve basis |
| Geïnstalleerde HA-integratie | `0.4.0b1`, gezamenlijke basis `5e3ed30` |
| Voorbereide bron | Huidige branch, inclusief eenmalige configuratie-uitlezing, afzonderlijke busafsluiting en alle eerdere voorbereide wijzigingen |
| Nieuwe gezamenlijke kandidaat | E32 beta.3 / HA 0.4.0b3 in voorbereiding op gebruikersopdracht; exacte nieuwe CI-/pakketcontrole, publicatie en installatie nog te bewijzen. Passieve release, geen vrijgave van warmteproeven |
| Algemene en handmatige fysieke TX | Beide uit; geen runtime- of buildflag-ontgrendeling |
| Warmte-installatievrijgave | `manualHeatInstallationReviewed_ = false` |

De native HA-specialist bevestigde op 26 oktober 02:59–03:02 UTC Core2026.10.4
en integratie0.4.0b1 als geladen. De actuele E32-versie/bron en UART-tellers
werden daar niet aangeboden; de E32-identiteit hierboven blijft eerder vastgelegd.
Een lokale commit of ontwikkelbuild is geen beschikbare GitHub-update.

## Eerstvolgende werk, in volgorde

| Prioriteit | Werk | Vereist resultaat |
| --- | --- | --- |
| P0 — modelprofiel zonder digitale drukmeting | Gebruiker bevestigt op 26 oktober: deze ketel heeft geen digitale druksensor. De bestaande proefguard vereist die nog wel | Modelgebonden proefvoorwaarden en implementatie herzien voor deze opstelling; geen digitale drukwaarde eisen of verzinnen. Passende controle van installatiedruk afzonderlijk vastleggen; overige meet- en stopvoorwaarden behouden |
| P0 — configuratieontvangst | Eenmalige uitleesroute is aangesloten in HTTP, UART-poll en NL/EN-bediening; afronden met kandidaat- en fysieke controle | Echte latere boilerrespons levert CV-aan/uit en temperatuur met originele ontvangsttijd; standaard TX blijft uit tot afzonderlijke vrijgave |
| P0 — handmatige proefvariant | Bronbeoordeling en installatiekaart B07–B09 afronden voor de echte E32/EasyControl/Classic-keten | Expliciete adres-/interface-/timing-/arbitragebeoordeling en passende afgifte-, stop- en overdrachtsvoorwaarden; geen willekeurig openzetten van algemene TX |
| P0 — gezamenlijke freeze | Complete lokale bron-/pakketpreflight is geslaagd op `0acae7c`; na proefvariant-/installatiebeoordeling definitieve versies en bron vastleggen | Exacte kandidaat met volledige native-/HA-/browser-/board-/bron-/licentie-/pakketcontroles; ontwikkelbewijs apart houden |
| P0 — release en installatie | Eén gezamenlijke publicatie en installatie na kandidaatacceptatie | Begrijpelijke NL/EN-notities, juiste assets/manifest/checksums; HA via de bestaande native HA-specialist met back-up; E32 via native GitHub-OTA |
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

De huidige `ClassicHeatTrialEnvelope` vereist nog wel verse gerapporteerde druk
uit `0x18`, naast CV-instellingen uit `0x16`. Dat is een mismatch tussen de huidige
softwareguard en deze opstelling, geen ontvangstreparatie. Het modelgebonden
proefprofiel moet worden herzien met passende afzonderlijke controle van de
installatiedruk, zonder een digitale meetwaarde te verzinnen. De software is
hiermee nog niet aangepast of vrijgegeven; temperatuur-, configuratie-, stop-,
flow- en overige installatievoorwaarden blijven gelden.
Bewijs: `out/beta-live-readiness/`, lokaal en zonder publicatie van ruwe diagnostiek.
Geen configuratie-, installatie-, herstart-, kraan- of ketelopdracht uitgevoerd.

## Handmatige proefsoftware die al is voorbereid

- Afzonderlijke nulvraagproef; deze kan geen warmte starten. Een warmteproef
  vraagt nieuwe voorbereiding en een bewezen stopbasis.
- Concreet softwareprofiel: 40–45 °C, maximaal 60 seconden warmte; operatorlease
  5 seconden, write-cadans minimaal 1 seconde, stopwaarneming 30 seconden per fase.
  Dit zijn softwaregrenzen, geen gemeten fysieke stopgarantie.
- De huidige implementatie vereist verse Classic-temperatuur/druk en CV-configuratie;
  ontbrekende, ongeldige, toekomstige of verlopen metingen geven geen warmtevrijgave.
  De digitale drukeis moet voor de bevestigde opstelling zonder digitale druksensor
  modelgebonden worden herzien; dit is nog open implementatiewerk.
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
- NL/EN-gebruikersnotities met nieuwe functies, fixes, bijwerken en beperkingen:
  [conceptnotities](BETA-NEXT-RELEASE-NOTES.nl-en.md),
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
