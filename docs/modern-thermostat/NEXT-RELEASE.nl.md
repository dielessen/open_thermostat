# Beta.16 + HA0.4.0b8 — plan (eigenaar, 28 oktober)

**Stand 28 oktober, middag:** beta.15 is gepubliceerd en via de lokale upload
geïnstalleerd ([installatie](BETA15-INSTALLATION-20261028.json)). Beta.16 is in
uitvoering: onderdeel 0 (UART-zelfherstel, begrensde proef-foutstatus,
supervisor en zwarte doos, rustiger Bluetooth-scan) en de kamerregeling in
schaduwmodus (ruimteplan op de E32, bronnen op volgorde, één HA-route,
pagina "Ruimtes en verwarming") zijn gebouwd en lokaal getest; "Mijn ketel" en
"Keteltest" zijn samengevoegd. De Xiaomi-sensor van de eigenaar draait pvvx-
firmware 5.9 (BTHome, onversleuteld); beta.16 krijgt daarvoor een eigen profiel.

Grote release met alle fixes en nieuwe functies (eigenaar: "maak van beta 16 een grote release met alle fixes en nieuwe features"); E32 en HA worden samen geïnstalleerd (HA b7 weigert extra
veldgroepen). Volgorde: 0, dan 7, dan 1 → 6.

| # | Onderdeel | Inhoud | Klaar als |
| --- | --- | --- | --- |
| 0 | UART-ontvangst en proef-foutstatus (hoogste prioriteit) | Waargenomen 28 okt 04:45 UTC op beta.12: na een echo-fout zette `performReset()` eerst `uart_flush_input` en daarna `xQueueReset`; een byte daartussen bleef in de buffer zonder DATA-event. Sindsdien kreeg elk bericht de `00` van de vorige BREAK vooraan (`00 08 00 34 …`) en werd het ongeldig, tot herstart. Herstel: nooit buffer wissen bij een framefout (EMS-ESP-model: lezen tot elke BREAK), zelfherstel als een bericht met die losse `00` begint, en de echo-boekhouding vereenvoudigen naar EMS-ESP-niveau. Een proef in foutstatus mag niet uren nulvragen blijven sturen (1270 in de nacht) en moet na herstart of bij vastgelopen ontvangst netjes sluiten. Daarnaast wifi-uitval die herstart vereist (28 okt 10:57 UTC) | Hosttest die de race naspeelt; 24 uur zonder ongeldige reeks; ketel blijft door thermostaat bediend |
| 1 | Eén route, één set entiteiten | Eén entiteitentabel genereert C++ en HA (`--check` in CI); thermostaat-, 0x1A- en EMS+-waarden via de bestaande `boiler_fields`-route met bronadres; HA maakt alleen geziene entiteiten | Geen tweede lijst of route; bestaande entity-ID's en historie behouden |
| 2 | Tapwater | Episodestatistiek (tappen vs warmhouden), 0x33-instellingen lezen, temperatuur/comfort-eco/circulatie schrijven met bevestiging en readback | Legionellabeveiliging onaangetast; elke write teruggelezen |
| 3 | Keteldata en energie | Branderstarts, branduren, CV-/tapwateruren als HA-tellers; korte branderpendels per uur; onderhoudsmelding/laatste storing als tekst | Waarden alleen uit gemelde telegrammen |
| 4 | Stabiliteit en updates | Wifi-uitval analyseren en zelf herstellen, herstartoorzaak in HA; native HTTPS-update met TLS-buffers in PSRAM opnieuw proberen; updatepagina meldt zelf nieuwe versie | Monitorbewijs vóór/na; browserknop blijft als terugval |
| 5 | EMS universeel op hardware | Thermostaatrijen tegen de tado (0x17, RC10-type) controleren en als geverifieerd markeren; onbekende apparaten één keer identificeren | Alleen echt waargenomen rijen geverifieerd |
| 6 | Proefbediening | Uitleg waarom een knop geblokkeerd is; werkelijke temperatuur naast proefgrens | EN/NL, smal/breed |
| 8 | tado als meet- en instelpunt, Bosch herkennen | Opstelling (eigenaar 28 okt): de Bosch EasyControl Adapter zit op de ketel en staat op de EMS-bus als ketel 0x08 (EMS-ESP: product 211 "EasyControl Adapter", type BOILER); tado en E32 zitten op de adapter; de tado is de RC10-thermostaat op 0x17 (stuurt 0xB1 en 0x1A). Identiteit van 0x08 en 0x17 eenmalig uitlezen ter bevestiging. Woonkamer vloerverwarming, boven 3 radiatoren (badkamer, 2 slaapkamers). Doel van de eigenaar: tado later ontkoppelen van de regeling en alleen gebruiken om temperatuur te meten en in te stellen. Beta.16: tado-klimaatentiteit uit HA (actuele temperatuur en doeltemperatuur) kiesbaar als ruimtebron en setpointbron in de kamereditor; de E32 stuurt nog geen warmtevraag | Kamer toont tado-meting en -setpoint met ouderdom; geen ketelopdracht; overname van de regeling is een aparte, bijgewoonde stap |
| 9 | Pagina's samenvoegen | Eigenaar 28 okt: "Mijn ketel" en "Keteltest" worden één pagina "Mijn ketel" (uitlezing, instellingen en de bijgewoonde proef als sectie) | Eén navigatie-item; bestaande proefbeveiliging en browsertests behouden |
| 7 | Codereview, performance, opruimen, structuur | Hele E32- en HA-bron nalopen op fouten (concurrency/ISR, buffergrenzen, foutpaden, heap/stack); hot paths meten (EMS-ontvangst, REST/JSON, MQTT-publicatie) en onnodige kopieën/allocaties weghalen; ongebruikte code en verouderde documenten verwijderen; grote bestanden (`REST.h` 1904 regels, `ShadowController.h`, `config.cpp`) opdelen per verantwoordelijkheid | Gedrag ongewijzigd (alle tests groen), gemeten winst in heap/CPU/latentie, kleinere firmware |

## Plan naar volledige aansturing (eigenaar vroeg 28 oktober)

| Fase | Inhoud | Duur |
| --- | --- | --- |
| 1 | Beta.16 installeren (schaduwmodus), woonkamer inrichten | vandaag/morgen |
| 2 | Schaduwweek: E32-berekening naast de werkelijke tado-vraag (0x1A van 0x17); parameters afstemmen | ~7 dagen |
| 3 | Beta.17 bouwen (parallel): actieve warmtevraag (0x1A elke 60 s via de beoordeelde zendroute, nulvraag bij stop), blokkade zolang een andere regelaar 0x1A stuurt, bewaking tijdens actief (uitval meting, herstart, ketelterugmelding, vorstminimum 5 °C), schakelscherm Actief/Schaduw met terug-naar-tado-procedure, dagoverzicht en schaduwvergelijking | parallel |
| 4 | Bijgewoonde overstap: tado los, E32 actief; start/stop/modulatie, tapwater tijdens verwarmen, E32-herstart, wifi/HA/meting weg, gedrag van de EasyControl Adapter als de E32 stopt met zenden, terugzetten naar tado | één middag |
| 5 | Live met dagelijkse controle en bijsturen | 1–2 weken |
| 6 | Eerste echte release | na ~3–4 weken |

**Ruimtes: één plan, twee kanten bewerkbaar (eigenaar, 28 oktober):** het
ruimteplan staat op de E32 en de E32 voert het uit, dus het werkt ook zonder HA.
Home Assistant wordt de hoofdroute om het te bewerken (nieuwe ruimte-editor die
het E32-plan leest en terugschrijft); de E32-pagina blijft een tweede ingang op
hetzelfde plan. Het plan krijgt een revisienummer, zodat een wijziging aan de
ene kant nooit stil een wijziging aan de andere kant overschrijft. Bluetooth-
sensoren blijven aan de E32 gekoppeld (adres, profiel, sleutel); de E32 deelt
zijn sensorlijst met HA, zodat ze in de HA-editor als bron kiesbaar zijn en als
gewone HA-sensoren verschijnen. In het plan staat per bron of de E32 hem zelf
leest (Bluetooth) of dat HA hem doorgeeft. Beta.17 bouwt dit, samen met de
HA-bediening per ruimte, en haalt de oude HA-ruimte-editor uit de
verwarmingsroute.

**Wat schaduwmodus doet:** de E32 voert de hele regelketen uit behalve het zenden:
elke 10 s meten (tado via HA, Xiaomi via Bluetooth als terugval), beslissen
(verwarmen ja/nee, aanvoer 30–60 °C, hysterese, brandertijden) en melden
(pagina "Ruimtes en verwarming" en HA-sensor "Heat request"). De tado blijft de
ketel regelen; de E32 leest diens werkelijke vraag (0x1A van 0x17), die via de
ene tabel ook in HA staat als "Thermostat requested flow temperature". Zo liggen
beide lijnen naast elkaar in de HA-geschiedenis. Schaduwmodus bewijst niet hoe
ketel en EasyControl Adapter op onze vraag reageren; dat test fase 4.

**Schaduwfase klaar (minimaal 3 dagen, liefst ~5) zodra:**
1. minstens 72 uur geen hang of herstart (zwarte doos leeg, geen wifi- of
   Bluetooth-uitval);
2. minstens 10 verwarmingsperiodes van de tado vergeleken, inclusief
   nachtverlaging en ochtendopwarming en een periode zonder warmtevraag;
3. de beslissingen ongeveer gelijk zijn: warmtevraag op ongeveer dezelfde
   momenten (enkele minuten verschil), aanvoer in hetzelfde gebied (±31–43 °C)
   en niet vaker aan/uit dan de tado;
4. de bronnen werken: de tado-waarde komt via HA binnen en de Xiaomi heeft
   minstens één keer overgenomen (HA of de tado-integratie even uitgezet).

Gaat er iets mis, dan eerst bijstellen (startpunt, aanvoer per graad, trage
correctie) en opnieuw tellen. Daarna de bijgewoonde overstap (fase 4), waarbij
de eigenaar aanwezig is.

## Eerste echte release — afgesproken scope (eigenaar, 28 oktober)

Doel: de E32 neemt de ketelvraag over van de tado. Eerst alleen de woonkamer.

- **Installatie:** de vloerverwarming (woonkamer) heeft een eigen verdeler met
  pomp en een thermostatische kraan met maximaal 60 °C ingang. De 3 radiatoren
  boven (badkamer, 2 slaapkamers) zitten op hetzelfde circuit, zonder TRV's:
  zij worden warm zodra de woonkamer warmte vraagt, ook de inactieve badkamer.
- **Ketelzijde:** de EasyControl Adapter (0x08) krijgt na ontkoppeling van de
  tado alleen nog vraag van de E32. Harde grens aanvoer 60 °C.
- **Regeling:** de E32 moduleert de aanvoertemperatuur (zoals de tado nu doet:
  waargenomen 31–43 °C) op basis van ruimtetemperatuur en setpoint, met
  minimale brander-aan/uit-tijden.
- **Ruimtes:** woonkamer actief, alleen een thermostaat/temperatuurbron, geen
  kranen. Badkamer inactief. Een ruimte kan tijdelijk worden gedeactiveerd.
- **Bron:** eerst de tado via Home Assistant (klimaatentiteit: gemeten en
  ingestelde temperatuur); de tado zit dan niet meer op de adapter. Doel: ook
  zonder HA draaien met Bluetooth-sensoren (al ondersteund: Shelly BLU H&T,
  Xiaomi Monitor 3, Shelly BLU TRV) en het lokale E32-programma als setpoint.
- **Route:** beta.16 met deze functies eerst in schaduwmodus naast de tado
  (beslissingen vergelijken), daarna een bijgewoonde overdracht met uitvaltests
  (start, stop, E32-herstart, wifi/HA weg, meting te oud), dan 1–2 weken
  monitoren. Pas daarna de eerste echte release.
- **Bij uitval (keuze eigenaar):** eerst terugval op een Bluetooth-sensor; zonder
  bruikbare meting na 30 min de warmtevraag stoppen en waarschuwen (E32 en HA).
  Zonder HA valt het setpoint terug op het lokale E32-programma.
- **Bluetooth-sensor als terugval** in de woonkamer (keuze eigenaar); welk model
  de eigenaar koopt is nog open (Shelly BLU H&T of Xiaomi Monitor 3).
- **Meerdere temperatuurbronnen per ruimte** (eigenaar): een geordende lijst van
  bronnen (HA-klimaat/-sensor of Bluetooth-sensor). De eerste bruikbare bron is
  leidend, de rest is terugval. Is alleen een Bluetooth-sensor gekoppeld, dan is
  die primair en leidend. Woonkamer: tado via HA, dan Bluetooth. Andere kamers
  kunnen alleen een Bluetooth-sensor krijgen. Welke bron leidt is altijd zichtbaar.
- **Alles in beta.16** (eigenaar: "probeer dit allemaal in de volgende release
  mee te nemen . dan maken we een grote release"): onderdelen 0–8 hierboven plus
  deze scope; de ketelvraag eerst in schaduwmodus.

Opruimgrens: voorbereide roadmapcode (o.a. `ThermalModelStore`, `CoastModelStore`,
`CurveModelStore`, `MixerPolicy`, `ThermalReplay`, alleen door tests gebruikt)
blijft volgens de releaseafspraken behouden tenzij de eigenaar die functie laat
vallen. CI-browserstap: vijfmaal vastgelopen op ~650 s/720 s; oorzaak vinden en
de test robuust maken, niet herhalen.

# Beta.15 — betrouwbare ketelproef, browsercontrole bij updates en meer EMS-apparaten

**Beta.13 niet gepubliceerd:** de tag `v0.1.0-e32v2-beta.13` (`e166d29`) stopte
tweemaal in de CI-browserstap. Vijf mislukte runs sinds 27 oktober stopten op
dezelfde plek: tests die na een klik vast 50–200 ms wachtten en dan eisten dat
het verzoek al binnen was. Zij wachten nu begrensd op het verzoek zelf; de
CI-stap noemt een falende test voortaan in een openbare annotatie. Op keuze van
de eigenaar ("Als beta.14") is beta.14 dezelfde inhoud met die testfix; de
beta.13-tag blijft ongewijzigd.

**Beta.14 niet gepubliceerd:** ook `v0.1.0-e32v2-beta.14` (`0aa9c66`) stopte in de
browserstap. De nieuwe annotatie noemde `test/ha-device-power-browser.cjs` op de
ubuntu26-runner: de HA-kamereditor onthield een open sectie via het asynchrone
`toggle`-event; tekende hij opnieuw vóór dat event, dan klapte "Geavanceerde
instellingen" dicht. Lokaal bewezen door het event tegen te houden. De editor
neemt open secties nu direct uit de getoonde DOM over (ook comfort). Op akkoord
van de eigenaar ("Ja, publiceer beta.15") is beta.15 dezelfde inhoud met die fix;
het grotere plan hierboven schuift naar beta.16.

**Actueel (28 oktober):** de bijgewoonde proef op beta.12 is door de eigenaar
geslaagd verklaard: ~398 s 50 °C, 7 aanvragen per 60 s, CV actief en modulatie
37–41 %. Tapwater beëindigde de proef; de brander ging daarna uit (eigenaar).
De thermostaat (0x17) stuurde geen eigen 0x1A. Eén UART-fout ná de stop is nu
verklaard: na onze 6-byte echo kwam `00 01 00` zonder eigen BREAK-event.
Beta.13 herstelt dat (0x00-scheidingsbyte gecontroleerd), maakt tapwater een
pauze met CV-gebaseerde stopbevestiging, herstelt de identiteitsuitlezing naar
de thermostaat, laat mislukte updatecontroles terugschalen, geeft de hoofdlus
8 KiB stack, laat de browser releases controleren vóór upload en voegt een
tabel met EMS+-ketel- en thermostaatentiteiten toe (EMS-ESP-referentie,
nog niet op hardware geverifieerd). Installatie vanaf beta.12 via de lokale
upload. [Proefverslag](BETA12-ATTENDED-HEAT-20261027.json).


**Beta.11 niet gepubliceerd:** de tag `v0.1.0-e32v2-beta.11` (`d2ccc82`) stopte in
de CI op `test/manual_ota/run.py`: die hoststub kende `OTA_WITH_SEQUENTIAL_WRITES`
nog niet en eiste het oude wissen van de volledige lengte. Net als bij beta.7
blijft die tag ongewijzigd en ongepubliceerd; beta.12 is dezelfde inhoud plus de
aangepaste stub. De E32 viel intussen enkele keren van het wifi-netwerk (geen
ARP-antwoord, herstart nodig); een alleen-lezen monitor legt het verloop vast.


**Actueel (27 oktober, avond):** beta.10 en HA0.4.0b7 zijn gepubliceerd.
De lokale upload van beta.10 liep 5–7 s na de start in de taakwatchdog (één
grote wis-actie van het OTA-slot); de eigenaar heeft beta.10 daarna handmatig
geflasht. Bron, web en instellingen zijn gecontroleerd. HA0.4.0b7 is via Samba
geïnstalleerd en door de eigenaar herstart. De commando-entiteit verscheen niet:
de projectie verwachtte `classic`, het apparaat meldt `classic_observed`.
Beta.11 (opdracht "ok doe maar"): passieve uitlezing van de thermostaatvraag
(0x1A), onderhoudsmelding (0x1C) en laatste storing (0x10/0x11); identiteit
ophalen voor elk waargenomen apparaat; dashboard toont alleen gemelde waarden;
profielfix; OTA-wissen per sector; tijdmeting bij TLS-fouten. De decodering
van 0x18/0x19/0x16/0x33/0x34 komt overeen met de EMS-ESP-offsets.
Daarna de bijgewoonde ketelproef met verse bevestigingen.
[Freezeplan](BETA11-KANDIDAAT.json), [installatie beta.10](BETA10-INSTALLATION-20261027.json).

# Beta.10 + HA0.4.0b7 — HTTP-fix, MQTT-commandoroute en UART-foutspoor

**Actueel (27 oktober, avond):** werk hervat op de lokale Windows-laptop van de
eigenaar; bron opnieuw gekoppeld aan een verse GitHub-clone op `322999b`,
builds/tests in WSL Ubuntu. De eigenaar keurt publicatie van beta.10 en HA
0.4.0b7 en daarna installatie goed ("yes please approve").
Inhoud: de op het apparaat gemeten HTTP-fix uit privébuild beta9-httpfix.1,
de native MQTT-route voor `controller_request` met bijbehorende HA-correctie,
en een diagnostisch UART-spoor dat bij `echo_event_accounting` de laatste16
gebeurtenissen en de echo-boekhouding vastlegt vóór de reset. Dit verhelpt de
UART-fout niet. 1243 native tests en 2645 HA-tests slagen (2 skips).
Installatie en een nieuwe bijgewoonde proef blijven aparte stappen; voor de
proef zijn een verse aanwezigheids-, manometer- en uitschakelbevestiging nodig.
[Freezeplan](BETA10-KANDIDAAT.json), [publicatie-uitzondering](BETA10-PUBLICATION-EXCEPTION-20261027.json),
[overdracht](HANDOFF-CLAUDE-20261027.md).

# Beta.9 + HA0.4.0b6 — ketelproef met60secondeninterval

**Gepauzeerd op verzoek van de eigenaar — overdracht aan Claude.**
Lees eerst [de actuele overdracht](HANDOFF-CLAUDE-20261027.md). De E32 draait
de afzonderlijk gecommitteerde, niet gepubliceerde proefversie
`v0.1.0-e32v2-beta.9-httpfix.1` uit `5e1dce5`. HA draait `0.4.0b6`.
De HTTP-blokkade door lege verbindingen is op het apparaat verholpen en gemeten.
Daarna heeft de proef ongeveer 304 seconden verwarmingsvraag aangehouden:
zes 50°C-opdrachten, met intervallen van 60,166–60,635 seconden. CV-bedrijf en
modulatie zijn teruggemeld. De zesde verzending werd 6 ms later gevolgd door
`echo_event_accounting`; deze UART-fout veroorzaakte de stop. Het toezicht
bleef intact. Nulvraag en latere stop zijn teruggelezen; de eigenaar bevestigt
dat de brander uit is. De volledige tien minuten zijn niet gehaald.
Geen nieuwe proef, herstart, installatie of programmering na de stopopdracht.
[HTTP-fix en installatie](HTTP-SUPERVISION-FIX-20261027.json),
[laatste proef en fysieke stopbevestiging](HTTP-FIXED-ATTENDED-HEAT-20261027.json).

**Voorgaande diagnose — publieke beta.9, vóór de HTTP-fix:**
De eigenaar bevestigt pomp- en branderbedrijf tijdens de korte proef en dat de
brander daarna uit is. De E32 bevestigt de latere nulvraag en stop. Er is één
positieve 50°C-verzending vastgelegd; tien minuten en herhaling na 60 seconden
zijn nog niet fysiek bewezen. De ontvangen CV-status bleef tijdens deze proef 0;
de waarneming van de eigenaar en de telegrammen blijven afzonderlijk bewaard.

De eerste stopaanleiding is `operator_lease_expired`: mijn testscript wachtte
5,176 seconden op een optionele statusuitlezing voordat het opnieuw toezicht
stuurde. Dat overschreed de ongewijzigde toezichttermijn van vijf seconden.
Deze fout in de testaansturing is lokaal met HTTP-vertraging gereproduceerd.
Afzonderlijk toezicht doorstaat dezelfde vertraagde uitlezing; zes lokale
controles slagen. Dit is nog geen nieuwe proef op de ketel. De 29 ms na de
toezichtdeadline geregistreerde UART-fout `echo_event_accounting` blijft
onverklaard. Geen nieuwe warmtevraag of installatie tijdens deze diagnose.
[Proefbewijs en bevestiging eigenaar](BETA9-ATTENDED-HEAT-20261027.json).

**Methode en voorbereiding van beta.9 (historisch):**
De eigenaar vraagt expliciet dezelfde proefmethode met60secondeninterval.
De bestaande proef zond ongeveer elke1–1,5s; de nieuwe firmware herhaalt de
positieve aanvraag pas60s na de vorige voltooide UART-verzending, op de volgende
geschikte buspoll. Eerste start en nulvraag bij Stop/toezichtverlies/deadline
blijven direct. Het HTTP-toezicht blijft kort; dat is geen extra ketelopdracht.
1230 native proeven en vier browsergevallen slagen. Exacte release-CI,
installatie en de volledige bijgewoonde proef blijven apart.

HA0.4.0b6 is geïnstalleerd,96bronbestanden gecontroleerd, één HA-herstart.
Badkamer meldt weer heat/shadow_ready met accepted7 en geen staging; profiel,
targets, bindings,105entiteiten, twee apparaten en15resources zijn behouden.
De wrapper bereikte zijn12stappenlimiet; volledige handmatige reviewflow is
niet bewezen. Bronkwaliteit blijft ongekwalificeerd/current_temperature null.
Beta.8 is gepubliceerd maar de app-upload brak af met een watchdogboot naar
beta.6. De E32 draait dus nog beta.6. Een door de eigenaar gestarte tweede
proef registreerde één UART-fout/reset/replyerror; latere stop is bevestigd.
De eigenaar meldt dat hij is gestopt. Geen volledige tienminutenacceptatie.
[Huidige installatie](BETA8-INSTALLATION-20261027.json),
[tweede proef](BETA6-OWNER-TRIAL2-20261027.json),
[opdracht en vaste methode](BETA9-OWNER-INSTRUCTION-20261027.json).

**Eerdere beta.8-voorbereiding:**


Beta.7 is niet gepubliceerd: de pakketcontrole vond een extra SDK-atomicobject
door de nieuwe UART-diagnose. Beta.8 gebruikt hiervoor het bestaande korte
ESP-lockmechanisme. Volledige lokale broncorrespondentie slaagt, zonder nieuwe
SDK-objecten toe te laten. HA0.4.0b6 blijft onveranderd op zijn eigen bevroren bron.


**Actuele opdracht:** de aparte door de E32 verzonden aanvoeraanvraag leveren en
daarna één volledige bijgewoonde50°C/600s-proef uitvoeren. De bestaande opdracht
voor release, commit en installatie blijft van kracht. Beta.6 + HA0.4.0b4 staan
geïnstalleerd; beta.8/HA0.4.0b6 is softwarematig voorbereid en wacht op exacte CI.
[Opdracht](BETA7-OWNER-INSTRUCTION-20261027.json), [freezeplan](BETA8-KANDIDAAT.json).

De eerste proef liet daadwerkelijk pomp/branderbedrijf zien. De eigenaar
stopte zelf na ongeveer375s; daarnaast werd een transportfout vastgelegd.
Mijn eerdere conclusie dat de transportfout de automatische stop veroorzaakte
was te stellig. De stop is daarna teruggelezen en fysiek bevestigd.
Een volledige tienminutenproef is daarmee niet afgetekend.
[Oorspronkelijk bewijs en correctie](BETA6-ATTENDED-HEAT-20261027.json).

Beta.7 houdt de gevraagde50°C en de ketelterugmelding apart. Het E32-veld en de
nieuwe HA-uitleesentiteit volgen een werkelijk voltooide UART-verzending;
voor verzending/herstart blijft de waarde onbekend, een verzonden stop wordt0.
Ontvangen curflowtemp/selflowtemp worden niet overschreven. De oude60°C-poort
is vervangen door afzonderlijke5–<90°C-bewaking; een50°C-aanvraag mag bij66°C
water beginnen. Druk, toezicht, nulbaseline, looptijd en stop blijven vereist.
Een eerdere handmatige stop blijft als aanleiding behouden bij een latere fout.
De laatste UART-foutsoort/tijd blijft beschikbaar voor de vervolgdiagnose.
[Betekenis van de aparte waarde](E32-CONTROLLER-REQUEST.md).

**Historische beta.6-uitvoering hieronder:**

**Installatie27 oktober:** beta.6 is gepubliceerd en via de bestaande beveiligde
LAN-appupload geïnstalleerd. Nieuwe boot en bron/ELF/web kloppen; twaalf
instellingenexports zijn bytegelijk gebleven. De eerste upload brak af met een
watchdogreset naar beta.5; één na diagnose begrensde upload gaf HTTP200 success.
Dit is geen native GitHub-acceptatie: de laatste volledige native basis blijft
beta.4. HA0.4.0b4 is gepubliceerd en wordt normaal geïnstalleerd. De badkamerthermostaat
is sinds01:00 unavailable doordat het bestaande planherstel een beoordeling
vraagt, terwijl die bestaande functie uit alle productmenu’s ontbrak.
Een kleine HA0.4.0b5-vervolgfix maakt de normale planreview/status zichtbaar
bij een bestaande native verbinding. Dezelfde controles, afzonderlijke bevestiging
en echte readback blijven vereist. Geen geforceerde opslagwijziging of nieuwe
fysieke toestemming.22 gerichte echte HA/C++-proeven slagen; exacte-tag-CI volgt.
[Herstelfix](HA-RECOVERY-MENU-20261027.json).
[Installatiebewijs en grenzen](BETA6-INSTALLATION-20261027.json).

**Oorspronkelijke opdracht27 oktober:** de eigenaar vraagt de huidige bundel te
committeren, publiceren en op E32 en HA te installeren. Verdere functie-uitbreiding
is voor deze freeze gestopt. Eerst exacte CI/pakketcontrole, verse back-ups,
daarna normale installatie en afzonderlijke nacontrole. Geen echte ketelproef
of kraanopdracht als onderdeel van de installatie.
[Opdracht](BETA6-OWNER-INSTRUCTION-20261027.json) en [freezeplan](BETA6-KANDIDAAT.json).

De uitlezing vóór deze installatie toonde beta.5 uit `a4237cd` op de E32, met juiste
openbare ELF/web-identiteit, bevestigde boot, stijgende uptime en nul TX.
Het oorspronkelijke beta.5-installatiebewijs ontbreekt; de oude native checkpoint
noemt nog beta.4. De laatste volledige native acceptatie blijft daarom beta.4.
De expliciete nieuwe releaseopdracht is vastgelegd als een eenmalige publicatie-
uitzondering voor beta.6. Dit vult geen oud bewijs fictief aan.
[Actuele beta.5-waarneming en bewijsgrens](BETA5-RECOVERED-STATE-20261027.json).

**Begeleide ketelproef:** de kandidaat toont vier stappen: opstelling →
voorbereiden → verwarmen → uitslag. Per stap staat welke knop aan de beurt is,
wat er gebeurt en wat de vervolgstap is. Eén opstellingsbevestiging en een nieuwe
manometerwaarde blijven vereist; de warmtestart heeft één afzonderlijke
bevestiging. Standaard50°C/600s, resterende tijd uit de E32 en direct Stop.
De E32 bewaart per proefsessie of de gewenste temperatuur en CV-bedrijf ná een
verzonden warmteopdracht zijn teruggemeld en of de volledige duur is verstreken.
De uitslag onderscheidt geslaagde terugmelding, vroegtijdig/onvolledig,
onbevestigd, alleen nulvraag en fout. Heropenen bewaart de uitslag in dezelfde
boot/proefsessie, zonder de bediening te hervatten. Dit is geen fysieke B14-
afhandeling. De E32-code is inmiddels geïnstalleerd; de echte ketelproef blijft open.
[Softwarecontrole en bewijsgrens](GUIDED-BOILER-TRIAL-20261027.json).

**Actuele codeprioriteit:** een snellere webinterface en een opgeruimde Keteltest.
De kandidaat gebruikt build-time gzip, herbruikbare browsercache, kleine luie
paginamodules en één gedeelde telemetrieaanvraag. De ketelpagina toont ontvangen
entiteiten eenmaal per herkend apparaat. De proef staat bovenaan met één korte
opstellingsbevestiging en de stappen ophalen → voorbereiden → apart starten →
stoppen. Softwareproeven gebruiken gesimuleerde HTTP-/ketelantwoorden; er is
deze softwareproeven geen echte warmtevraag verstuurd. De latere installatie
staat apart hierboven.
[Review en meetgrens](E32-PERFORMANCE-AND-BOILER-REVIEW.md).
De native MQTT-route gebruikt daarnaast begrensde socketwrites en asynchrone
DNS via de bestaande lwIP-netwerktaak. Een DNS-storing houdt de hoofdloop niet
meer vijftien seconden vast. Ook TCP verbinden verloopt in stappen tussen de
normale looptaken, binnen dezelfde oorspronkelijke drie seconden. De MQTT-
CONNACK-/leeswacht blijft afzonderlijk reviewwerk.
Uitgeschakelde projectlogregels voeren hun dure argumenten niet meer uit;
web/syslog en seriële uitvoer houden hun eigen filters. De netwerkroute-refresh
wacht niet op een volle netwerkmailbox.
Systeemlog bevat nu lichte looptijdtellers in dezelfde statusaanvraag, met een
uitklapbare uitleg. Verborgen logpagina’s stoppen hun uitlezing; reeds verstuurde
instellingenwijzigingen worden door navigatie niet afgebroken of herhaald.
Ook het dashboard breekt een lopende uitlezing af zodra de pagina verborgen
wordt. Terugkeren start direct één nieuwe aanvraag; late/verlopen antwoorden
vervangen die niet en navigatie hervat geen oude dashboarduitlezing.
Bluetooth pauzeert eveneens zijn automatische statusuitlezing in verborgen tabs.
Laden/bewaren en automatische statusreads lopen niet door elkaar. Conceptinvoer,
getypte sleutel en open panelen blijven bij tabwisselen bewaard; verlaten wist
de sleutel. Een ingediende save/scan houdt zijn eigen deadline, zonder herhaling
of readback door een verlaten pagina. Leesherstel wist alleen de oude leesfout;
een onbevestigde save blijft zichtbaar.
Het dashboard bouwt zijn statusantwoord nu in dezelfde vaste64KiB-PSRAM-buffer
als de keteltelemetrie. Geen tweede buffer of groeiende hoofdbody op de interne
heap. De eerste dashboardaanvraag reserveert die buffer; allocatiefout of een te
grote/onvolledige body geeft één volledige503 in plaats van een afgekapt antwoord.
Ook de syslogzender heeft een lichte uitgeschakelde route: geen klok-/
instellingenwerk per hoofdlus en alleen bij verbindingswisseling de wachtrijlock.
Lokale/seriële logging houdt eigen filters; de bestaande honderd-millisecondengrens,
MARK, verliesregistratie en geen-herhaling bij herverbinden blijven behouden.
De gedeelde browsersessiecontrole houdt haar bestaande tiensecondenlimiet nu
ook tijdens het lezen/valideren van de antwoordbody. Een stilgevallen body blokkeert
paginadata niet onbeperkt; een laat antwoord geeft wachtende acties niet alsnog
vrij. Een volgende aanvraag kan normaal herstellen, zonder oude writes te herhalen.
Ook de WiFi-setup leest status-, scan- en afrondings-JSON binnen de bestaande
vijfsecondenlimiet. Een geaccepteerde afronding met verloren body wordt via de
volgende actuele status herkend, zonder opnieuw af te ronden. De bestaande
tekstbevestigingen voor scannen/verbinden blijven behouden. Geen WiFi-actie uitgevoerd.
Debuginstellingen worden pas bij uitklappen opgehaald. Dicht laten scheelt één
API-aanvraag per bezoek aan Instellingen; in-/uitklappen bewaart conceptkeuzes.
Sluiten/navigeren trekt lopende reads in. Opslaan gebruikt de bestaande direct
toegepaste filters, zonder herstartvraag; onbekende save wordt niet herhaald.
Een reeds verlaten instellingenformulier begint geen uitgestelde initialisatie.
De daadwerkelijke paginasnelheid moet na installatie worden gemeten.

**Centrale instellingen bij actieve E32-verbinding:** via Installatie instellen
kun je nu de installatienaam, dashboardkeuze en gedeelde watergrenzen wijzigen.
Gekoppelde radiatorcircuits volgen de grenzen; eigen circuitgrenzen blijven
behouden. Opgeslagen stooklijnpunten worden binnen de nieuwe grenzen gehouden.
Een botsende vloer-/maatwerkgrens wordt vóór bewaren geweigerd. De normale
SOURCE-/verbindingsroute past het volledige plan toe met echte C++-readback;
een grenswijziging kan een gecontroleerde E32-herstart vragen. Alleen hernoemen
of het dashboard wijzigen schrijft geen apparaatinstellingen. Weerregeling is
in dit verbonden profiel nog niet ondersteund en wordt niet als bedienbare
optie aangeboden. Bij onbevestigde toepassing blijft de opgeslagen wijziging
herkenbaar wachten op de gewone E32-verbindingsroute. Geen nieuwe eigenaar,
opslag, automatische retry of fysieke uitvoervrijgave.
[Softwarecontrole en bewijsgrens](ACTIVE-INSTALLATION-20261027.json).

**Nieuwe kamerfunctie in dezelfde bundel:** maximaal acht raam-/deurcontacten
kiezen, wijzigen en verwijderen via de normale kamereditor én kamerwizard.
Opent één gekozen contact, dan pauzeert de kamervraag; hervatten vereist geldige
gesloten meldingen en de ingestelde wachttijd. Ontbrekende/verlopen berichten
houden de vraag gepauzeerd. Bij actieve native plannen loopt bewaren via dezelfde
reload en gecontroleerde C++-readback. Een contact activeert geen extra comfort-
of vorststand en verandert geen temperatuurgrens. De feitelijke sensor-/uitvalproef
en modelspecifieke oorspronkelijke rapportkwalificatie blijven afzonderlijk open.

**Extra kamerbediening in ontwikkeling:** een expliciet gekozen HA-temperatuurhelper
kan door een nieuwe rechtstreekse gebruikerswijziging één tijdelijke override
aanvragen. Bewaren neemt de huidige helperwaarde niet over; automatische wijzigingen,
opstartwaarden en echo's worden geweigerd. Duur één minuut tot twaalf uur, met
afloop uit de regelaar en behoud van raamblokkering/programma/temperatuurbron.
De echte HA-helperdienst en C++-afloop worden softwarematig gecontroleerd.
Fysieke wandbediening heeft nog een eigen oorspronkelijk actieprofiel nodig.
[Werking en grenzen](MANUAL-ROOM-TARGET.md).

**Comfort en aanwezigheid in dezelfde bundel:** normale editor/wizard voor
comfortstanden, afwezigheidsdoel, standaard tijdelijke duur en een optionele
persoon. Actieve plannen bewaren via dezelfde SOURCE en C++-readback.
Oorspronkelijke HA-persoonsmeldingen houden de ouderdom van hun trackerbron;
opnieuw melden van een gecachete bron vernieuwt niets. De bestaande grens is
twee minuten en ontbrekende/verlopen aanwezigheid blijft onbekend. De native
bron behoudt zijn vorstdoel5°C; een nieuw onverenigbaar profiel wordt vóór
bewaren geweigerd. [Werking en afbakening](ROOM-COMFORT.md).

**Batterijstatus bij gekoppelde apparaten:** de normale kamereditor toont onder
Geavanceerde instellingen de HA-batterijpercentages en eigen lage-batterijflags
van de opgeslagen sensor/kranen, eenmaal per apparaat. De oorspronkelijke HA-
meldtijd en ouderdom blijven zichtbaar; onbekend, dubbelzinnig en verlopen
blijven herkenbaar. Dit is gecachete HA-informatie bij laden, geen gekwalificeerd
hardwarebericht of automatische batterijmelding. Geen extra uitleeslus of
nieuwe HA-entiteiten. [Werking](DEVICE-BATTERY-SNAPSHOT.md).

**Vakantie-einddatum aangesloten:** datum/tijd in de HA-tijdzone, expliciete keuze
bij dubbele zomertijdkloktijden en weigeren van niet-bestaande tijden. Starten of
terugkeren naar programma gebruikt de bestaande eindige comfortservice, met
gecontroleerde kamer-/configuratiescope en uitsluitend gemelde actuele status.
Geen automatisch herhalen bij een time-out. De keuze blijft sessielokaal en
vervalt bij herstart/herverbinding/kamerreload; fysieke bron-/gedragsproeven
blijven open. [Gebruikersroute en grenzen](ROOM-VACATION.md).

**Uitleg op het E32-dashboard:** Details per kamer toont de effectieve doelbron,
geselecteerde comfortstand en gemelde resterende tijd of vakantie-einde (UTC).
Raam-/deur- en aanwezigheidsmeldingen krijgen herkenbare redenen. De bestaande
regelaarmomentopname blijft de enige bron; geen extra aanvragen of eigen
aftelklok in de browser. Ontbrekende/verouderde regelstatus toont deze waarden niet.

**Laatste passieve nacontrole:** de huidige proef is `closed` met
`restart_required`, nul positieve warmteframes en gemelde stop. Daarom kan de
geïnstalleerde firmware geen nieuwe proef voorbereiden. Herstarten blijft
uitgesteld. De kandidaat benoemt dit direct bovenaan de pagina en hergebruikt
de bestaande bevestigde herstartknop. De ketel heeft nog geen volledig
product-identificatietelegram gemeld. Een afzonderlijke, expliciete knop kan in
de kandidaat één begrensde identiteitsleesopdracht aanvragen; openen/verversen
van de pagina stuurt niets. Dezelfde korte opstellingsverklaring geldt, zonder
extra vinkje of extra voorwaarde voor verwarmen. Niet-geïdentificeerde andere
busafzenders blijven in ingeklapte diagnostiek zichtbaar.

De oudere voorbereidingsnotities staan ongewijzigd in de
[beta.4-planhistorie](NEXT-RELEASE-HISTORY-BETA4-20261026.nl.md) en de
[eerdere planhistorie](NEXT-RELEASE-HISTORY-20261026.nl.md).

## Wat draait er en wat staat klaar?

| Onderdeel | Laatst vastgelegde stand |
| --- | --- |
| E32 | Openbare beta.4, bron`9ecb4da`, geïnstalleerd via één native GitHub-update |
| Installatieacceptatie | Alle 13 checks PASS; twaalf beperkte API-back-ups nagelezen; versie/bron/ELF/web, nieuwe boot en behoud onafhankelijk beoordeeld |
| HA | Core2026.10.4, geladen integratie0.4.0b1, SOURCE 6. Nieuwste openbare HA-download blijft0.4.0b3; voor deze E32-onderhoudsbron is geen HA-update nodig |
| Handmatige proef | Configuratie opnieuw uitgelezen en nulvraag met latere gemelde stop uitgevoerd; positieve warmtevraag nog niet uitgevoerd |
| Automatische uitvoer | Automatische ketel-/kraanregeling en blijvende ketelinstellingenwrites blijven uit |
| Gepubliceerde bron, installatie open | Beta.5: uitleg bij geblokkeerde proefknoppen en onderscheid tussen mislukte updatecontrole, installatie, verbinding, TLS en HTTP |

Het [beta.4-installatiebewijs](update-acceptance/e32-beta4-20261026.json),
[openbare pakketrapport](BETA4-VERSIONED-PREVIEW.json) en de
[waargenomen nulvraag](BETA4-FIRST-ZERO-OBSERVATION-20261026.json) zijn de bronnen.
De acceptatiepoort staat op geaccepteerde beta.4 en pending beta.5, zonder actieve uitzondering.
De historische beta.3-installatieacceptatie blijft INCOMPLETE; de expliciete
uitzondering voor de afgeronde beta.4-publicatie is bewaard. Zij blokkeert de
geaccepteerde beta.4 niet opnieuw.

## Actuele proef: nulvraag uitgevoerd, tien minuten warmte gevraagd

Op verzoek van de gebruiker zijn de CV-instellingen op de geïnstalleerde beta.4
opnieuw uitgelezen en is een echte nulvraagproef uitgevoerd. De gebruiker bevestigt
Tado los, 2 bar op de manometer en aanwezig bij de ketel met onafhankelijke stop.
Er zijn één configuratieleesopdracht en zeven nulframes verzonden; een strikt
latere ketelmelding bevestigt nulvraag/0%/CV uit. De ketel meldde vóór de proef
ook al nulvraag en0%; dit bewijst geen stop vanuit een brandende ketel.
[Oorspronkelijk bewijs en afbakening](BETA4-ATTENDED-ZERO-20261026.json).

Er is **geen positieve warmtevraag** gestart. Beta.4 blokkeerde bij54°C aanvoer
omdat zijn eerste proefvenster5–<50°C is. Daarna vraagt de gebruiker expliciet
**50°C gedurende tien minuten**. Beta.5 wordt hiervoor aangepast:

- Vraagbereik40–50°C, maximaal600 seconden; standaard50°C/600 seconden.
- Gemeten water blijft een afzonderlijke proefbewaking5–<60°C. Deze eigen
  proefgrens laat een doel van50°C en enige hysterese toe. Het is geen EMS-eis.
- CV-instellingen moeten bij voorbereiding/start jonger zijn dan tien minuten.
  Tijdens de eenmaal gestarte proef blijven die instellingen maximaal één
  proefduur langer geldig; nieuwe instellingen en verse liveberichten blijven
  leidend. Geen automatische configuratie-uitlezing tijdens warmte.
- Een manometerwaarde1,1–2,5bar moet per voorbereiding opnieuw worden opgegeven
  en bij de start jonger zijn dan twee minuten. De verklaring geldt daarna
  voor die eindige proef; een keepalive vernieuwt haar niet.
- Nulbasis, afzonderlijke start, exclusief busbezit, open afgifte, lokale stop,
  vijfseconden-operatorlease, verse Classic-terugmelding en expliciete stop blijven.

De langere proef vereist nieuwe firmware; de bronwijziging past de geïnstalleerde
beta.4 niet aan. Ook tien minuten50°C garandeert geen ontsteking: warmer ketelwater
kan eerst afkoelen. Setpoint, reactie en latere stop worden apart vastgelegd.
Autonome stop bij communicatieverlies is hiermee niet bewezen; B14 blijft open.

## Leesbare en instelbare entiteiten samen op Keteltest

**Regelprincipe verduidelijkt:** een normale thermostaat kan de gewenste
`selflowtemp` uit kamervraag/stooklijn afleiden. De eerdere eis5–<50°C was
een eigen grens voor deze eerste handmatige commissioningproef, geen EMS/iRT-
voorwaarde. Setpointoverdracht en zichtbare brander-/warmtereactie moeten
afzonderlijk worden beoordeeld. Een al warme ketel kan terecht niet ontsteken
bij een lagere vraag. [Onderbouwing en afbakening](THERMOSTAT-SETPOINT-REVIEW.en.md).
De later expliciet gevraagde verruiming naar50°C/600s staat hierboven afzonderlijk.

Op verzoek van de gebruiker zijn de apparaat-/entiteitentabel, vier Classic-
instellingen en alle protocolreferenties opgenomen op Keteltest. De aparte
EMS-apparatenmenuoptie vervalt; bestaande paginalinks komen op Keteltest uit.
Leeswaarden, instelbare waarden en commando’s hebben eigen labels/filters.
In de gepubliceerde beta.5 blijft de volledige vastgelegde EMS-ESP-ketelcatalogus bereikbaar, ook zonder
herkend product-ID: 258 definitievarianten, 252 entiteitsnamen en 31 modelgroepen.
Per item zijn EMS-ESP-mogelijkheid en de werkelijke E32-implementatie/toelating
apart zichtbaar. Vier Classic-instellingen zijn voorbereid, blijvend schrijven
blijft in de standaardfirmware uit; overige writers zijn zichtbaar als nog niet
geïmplementeerd. Er worden geen schrijfrechten uit de catalogus afgeleid.
[Onderzoek naar de officiële EMS-ESP-implementatie](EMS-ENTITY-ACCESS-REVIEW.en.md).
Dit zit in de gepubliceerde beta.5; installatie is nog geblokkeerd en er is geen
positieve ketelproef uitgevoerd.

De beta.6-kandidaat vervangt deze dubbele referentieweergave door één tabel met
ontvangen waarden per apparaat, inclusief toegang en E32-ondersteuning. De
volledige protocolreferentie blijft als bron bewaard; de pagina downloadt alleen
de kleine metadata die nodig is om deze waarden te benoemen.

## Eerstvolgende softwarewerk, in volgorde

| Prioriteit | Werk | Vereist resultaat |
| --- | --- | --- |
| P0 — begrijpelijke proefbediening | Bij de uitlees- en nulvraagknop tonen welke bevestiging, terugmelding of tapwaterconditie ontbreekt; bij een te hete ketel de werkelijke temperatuur en proefgrens tonen | EN/NL, smal/breed scherm; geen automatische proefopdracht of versoepelde toelating |
| P1 — GitHub-diagnose | Een negatieve HTTP-clientcode is geen HTTP-antwoord. Native TLS-code vóór sluiten bewaren; alleen toegestane hostnaam en codes in diagnose | Verbinding/TLS/HTTP/overdracht onderscheiden; geen ondertekende download-URL, tokens of automatische retries in de status |
| P1 — updatebediening | Een mislukte cataloguscontrole onderscheiden van een mislukte firmware-installatie | De geïnstalleerde versie blijft herkenbaar; geen onterechte succes-/herstartmelding |
| P1 — broncontrole | Native tests, gerichte browsergevallen, E32-build en passende CI op de exacte onderhoudsbron | Bewijs bij de nieuwe bron; beta.4-pakketten en installatiebewijs blijven intact |
| Later — ketelproef | Positieve warmte/stop/naloop en onafhankelijke fysieke waarneming | B07–B09/B14 alleen op echt bewijs aftekenen |

De GitHub/HTTPS-code-1 is na de geslaagde beta.4-installatie bij een automatische
cataloguscontrole waargenomen. De oorzaak is nog niet vastgesteld. De nieuwe
onderhoudsbron verbetert de diagnose; zij claimt geen bewezen netwerkreparatie.
[Bèta.5-kandidaatplan](BETA5-KANDIDAAT.json).

## Actuele uitbreiding: uitvoerbare proef en Bluetoothscrollvak

Beta.4 levert de afzonderlijke bijgewoonde Classic-proefroute: configuratie lezen,
nulvraag en latere stop, afzonderlijke warmtestart40–45 °C / maximaal 60 s,
operatorlease van 5 s en nieuwe manometerwaarde per warmtevoorbereiding.
Automatische regeling en blijvende instellingenwrites blijven uit.
Bluetoothontdekking heeft een scrollvak met maximaal 128 ontvangen adressen,
ook naamloze/ongesteunde apparaten, aantal en overloopmelding. Acht opgeslagen
sensorkoppelingen blijven een afzonderlijke limiet.
De exacte beta.4-tag slaagde voor alle negen CI-validatiejobs en 2250 onafhankelijke
pakketcontroles. De volgende bron is een afzonderlijk ontwikkelcheckpoint.

## Bekende opstelling — niet opnieuw uitvragen

- Ketel: Nefit Ecomline Classic HRC 22H.
- Adapter: Bosch EasyControl Adapter 8737908035 V2.3.
- Gateway: BBQKees E32 V2/V2.2 met ethernet; Tado is voor deze proef door de gebruiker bevestigd losgekoppeld.
- De gebruiker kan Tado losnemen en de ketel onafhankelijk uitschakelen.
  Displayreset is geen normale proefstop of automatische uitvalgarantie.
- Meerdere radiatoren staan volgens de gebruiker open; TV02 zit op een radiator.
- Werkelijke Tado-overdracht en gemeten minimumflow/naloop zijn nog niet bewezen.
  Voor deze bijgewoonde nulvraag is Tado wel expliciet bevestigd los.

Het eerdere pendelen is niet causaal verklaard. De historische samenloop met
warmwaterbedrijf bewijst geen oorzaak of reparatie. Een stabiele passieve
beginsituatie en CV/DHW-onderscheid blijven onderdeel van de fysieke proef.

Bij overdracht en herstel moet ook het ketelzijdige adapterprotocol worden
vastgesteld: Bosch documenteert terugval naar aan/uit bij mislukte iRT/OT-detectie.
Alleen een groene led of EMS-ontvangst is hiervoor geen bewijs. De
[pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) bevat de fabrikantbronnen;
Keteltest geeft hierover NL/EN-uitleg zonder herstart- of configuratieactie.

## Productroadmap en behoud

Het [werkbord](WORKBOARD.nl.md) bewaakt alle 31 producteisen en 14 eindcontroles;
de [broninventaris](BETA1-RELEASE-INVENTARIS.json) bewaakt alle 23 voorbereide
onderdelen. Raam- en deurcontacten, alle schrijfbare EMS-ESP-entiteiten,
BLE-proxy, automatische zones en zelfleren blijven op hun eigen roadmap staan.
Deze onderhoudsbron claimt die functies niet als geleverd of fysiek vrijgegeven.
Alle voorbereide bron en bestaande acceptatiegrenzen blijven behouden.

## Vaste releaseafspraken

- Grotere samenhangende bundels; geen tag of installatie per losse reparatie.
- Voor publicatie: exacte bron/versie, volledige passende controles en openbare
  pakketten; daarna één native update met oorspronkelijke receipts en nacontrole.
- GitHub-hoofdpagina, commits en releasenotities in het Engels bijwerken.
- Na release/grote preflight gegenereerde opslag opruimen; broncode, werkbomen,
  back-ups, receipts, logs en geleverde herlinkinputs behouden.
