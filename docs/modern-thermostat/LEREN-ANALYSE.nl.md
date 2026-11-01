# Leren afstellen voor 1.0: wat de schaduwperiode laat zien

Stand: 1 november 2026. Basis: beta.23 (commit c8cafb6). Alleen gelezen uit de
Home Assistant-geschiedenis; de E32 en HA zijn niet aangeraakt.

Dit stuk gaat over de drie leerdelen voor 1.0: **aanvoer leren** (FlowLearner en
de stooklijn), **optimale start** (WarmupPlanner) en **minimale brander aan/uit**
(FlowDemand). De echte afstelling vraagt data van actieve regeling na de
overstap op dinsdag 3 november. Alles staat nu klaar om die data meteen te
gebruiken.

## Kort

- De E32 rekent precies wat hij in de schaduw meldde. Het harnas speelt de
  geschiedenis opnieuw af door de firmware en geeft dezelfde vraag: 100 %
  overeenstemming over 14 853 momenten.
- De E32 vraagt **ongeveer 3 °C minder aanvoer** dan de tado (op 1 november
  1 °C minder). Hij zou ook **half zo vaak starten**: 7 keer tegen 14.
- **Groot risico: met de huidige instellingen leert de E32 bij deze ketel
  niets.** De HRC 22 houdt zijn voorraadvat elke ~11 minuten warm. Elke ronde
  breekt de meting af, zodat er nooit 45 minuten schone verwarming overblijft.
  In 41 uur kwam er nul bruikbare meting uit.
- Een nieuwe optie, **"warmhoudrondes overbruggen"**, lost dit op. Ze staat
  standaard uit. Met die optie plus meetstukken van 30 minuten komen er 4
  bruikbare metingen in 41 uur. Naar schatting is het leren dan na **3–5 dagen
  actieve regeling** klaar.
- De optimale start met de standaard voorlooptijd (2 uur per °C) klopt goed
  met wat de vloer echt doet. Hij is eerder iets te vroeg dan te laat.
- De minimale aanvoer van 30 °C remt nergens. Die laten we staan.

## De data

| | |
|---|---|
| Periode | 30 okt 17:10 – 1 nov 10:26 UTC, 41,3 uur |
| Ruimte | woonkamer (vloerverwarming beneden), tado als thermostaat |
| Buiten | 1,9 – 11 °C (Buienradar) |
| Ketel | Nefit EcomLine HRC 22, 25 l voorraad op 60 °C, achter de EasyControl Adapter |
| Gaten | enkele korte; HA legt alleen veranderingen vast |

### Aanvoer: E32 tegen tado

Gemeten op de momenten dat allebei warmte vragen:

| Dag | Samen warmte | E32 − tado (mediaan) | 10–90 % | Alleen E32 | Alleen tado |
|---|---|---|---|---|---|
| 30 okt | 127 min | −3 °C | −4 … −2 | 5 min | 3 min |
| 31 okt | 234 min | −3 °C | −9 … −2 | 6 min | 45 min |
| 1 nov (deel) | 145 min | −1 °C | −4 … −1 | 2 min | 0 min |

De gevraagde aanvoer lag tussen 40 en 52 °C (mediaan per dag). De gemeten
aanvoer zat er 2 tot 5 °C boven: de ketel schiet wat door bij het opstarten.

### Opwarmen na de nachtverlaging

| Dag | Stap | Kamer bij start | Tijd tot binnen 0,2 °C | Echte stijging | Standaard voorlooptijd |
|---|---|---|---|---|---|
| 30 okt | 19 → 21 | 20,3 | 76 min | 0,4 °C/u | 84 min |
| 1 nov | 18,5 → 21 | 20,0 | 97 min | 0,5 °C/u | 120 min |
| 31 okt | 20,5 → 21 | 20,7 | 46 min | 0,13 °C/u | 36 min |

- De kamer koelt 's nachts nauwelijks af. Van 21 °C is hij 's ochtends
  nog 20–20,3 °C. De nachtverlaging scheelt dus weinig.
- De vloer warmt op met 0,4–0,5 °C per uur. De standaard voorlooptijd van
  2 uur per °C komt daar goed mee overeen; op twee van de drie ochtenden
  was de kamer eerder warm dan voorspeld.
- Op 31 oktober is de stap maar 0,3 °C. Dan telt de opwarmtijd van de vloer
  zelf zwaarder dan de stap, en is de kamer 10 minuten later dan voorspeld.
  Bij zo'n kleine stap is dat niet erg.
- Twee stappen op 31 oktober zijn niet gehaald, omdat het doel tussendoor weer
  veranderde (onder andere handmatig 22,5 °C).

### Afkoelen

Met de verwarming minstens 2 uur uit (daarna 1 uur gemeten) zakt de kamer
0,004–0,0075 °C per uur per graad verschil met buiten. Dat is heel traag: een
zware vloer en een goed geïsoleerd huis.

### Branderstarts

De teller ziet veel "verwarmingsrondes" van 0,2–0,6 minuut (24, 57 en 18 per
dag). Die zijn grotendeels **schijn**. De ketel start een warmhoudronde voor
het voorraadvat, en de vlag "warm water" komt pas één bericht later binnen.
Na zo'n ronde (aanvoer ~75 °C) zakt de aanvoer in ~10 minuten van 75 naar
36 °C, omdat de warmte uit het vat naar de cv wegloopt.

De echte verwarmingsstarts tellen we pas goed nadat de E32 aanstuurt. Het
nieuwe dagoverzicht (zie onder) telt ze apart.

### Gas (schatting)

Berekend uit modulatie × 22 kW ÷ 9,77 kWh/m³. Dit is nog niet geijkt op de
gasmeter.

| Dag | Verwarming | Warm water (incl. warmhouden) |
|---|---|---|
| 30 okt | 0,86 m³ | 0,91 m³ |
| 31 okt | 0,58 m³ | 4,18 m³ |
| 1 nov (deel) | 1,69 m³ | 0,74 m³ |

## Het harnas

Drie onderdelen, alleen lezen:

1. `tools/switchover/replay_export.py` haalt de HA-geschiedenis op en schrijft
   een CSV met een rij per 10 seconden: kamer, doel, aanvoer, retour,
   modulatie, brander, warm water, vraag van de tado, vraag van de E32 en
   buiten.
2. `test/learning_replay/replay.cpp` speelt die CSV af door de echte
   firmwarecode. Het draait FlowLearner, RoomEngine en FlowDemand op de pc, in
   een paar varianten, en geeft JSON terug. Het wordt meegebouwd in
   `test/native_harnesses.sh` (`learning_replay`).
3. `tools/switchover/active_review.py` geeft het dagoverzicht voor de 14 dagen
   naar 1.0 (zie onder).

Tests: `tools/switchover/test_replay_tools.py` (exporter, dagoverzicht en een
korte run van het harnas op een nagebootst huis met voorraadvat) en twee nieuwe
FlowLearner-tests in `test/test_native/test_flow_learner.cpp`.

Zo draai je het na de overstap:

```sh
export OT_HA_TOKEN='<token>'
python3 -I tools/switchover/replay_export.py --ha-url https://192.168.1.130:8123 --insecure \
    --room-climate climate.<woonkamer> --outdoor weather.buienradar \
    --since 2026-11-03T08:00Z --out replay.csv
bash test/native_harnesses.sh build      # bouwt o.a. learning_replay
<build-map>/learning_replay replay.csv --emitter floor > replay.json
python3 -I tools/switchover/active_review.py --csv replay.csv --start 2026-11-03T08:00Z
```

## Wat het harnas vond

### 1. Leren: de warmhoudrondes houden alles tegen

| Variant | Verwarmingsperiodes | Leertijd | Bruikbare metingen | Geleerde stooklijn |
|---|---|---|---|---|
| firmware (nu) | 81 | 45 min | 0 | – |
| warm-water-wachttijd 5 min | 81 | 72 min | 0 | – |
| + meetstuk 20 min | 81 | – | 1 | 54 °C: 0,78 °C/u |
| overbruggen | 33 | 192 min | 1 | 38 °C: 0,20 °C/u |
| overbruggen + meetstuk 30 min | 33 | 192 min | 4 | 38: 0,20 · 41: 0,14 · 49: 0,44 · 52: 0,58 °C/u |
| idem + 30 min inregelen | 33 | 192 min | 4 | gelijk |

Wat er misgaat:

- Elke warmwaterronde beëindigt een meting.
- Na warm water wacht de firmware 15 minuten. Bij elke herstart regelt hij
  daarbovenop nog 10 minuten in.
- Met een ronde elke 11 minuten blijft er nooit 45 minuten schone
  verwarming over.
- De firmware ziet 81 losse "periodes" in plaats van ~33 echte.

De nieuwe optie `bridgeHotWater` (in `FlowLearner::Params`):

- Een warmwaterronde midden in een verwarmingsstuk zet de meting op pauze in
  plaats van te stoppen. Dat mag hooguit 30 minuten (`maxBridgeMs`).
- De wachttijd na zo'n ronde is 5 minuten (`bridgeHoldoffMs`).
- Een herstart na warm water telt niet als nieuwe periode en krijgt geen
  nieuwe inregeltijd.

De test `KeepWarmStoreBlocksLearningUnlessBridged` bootst dit huis na. Zonder
de optie leert hij niets. Met de optie is het leren na 4 dagcycli klaar, met
hetzelfde advies (±3 °C) als in een huis zonder voorraadvat. Geen enkele
gemeten stooklijnwaarde komt van de hete warmhouderonde (geen bak ≥ 54 °C).

De 30 minuten inregelen maakt op deze data geen verschil. Met overbruggen
begint een meting toch al pas ruim na de echte start. De traagheid van de
vloer is hier dus niet wat het leren afremt.

### 2. Snelheid van leren

Met overbruggen plus meetstukken van 30 minuten: 4 metingen in 41 uur, in 4
verschillende aanvoerbakken. "Klaar" vraagt 6 metingen in 3 periodes en 2 bakken
met elk 3 metingen in 2 periodes. Bij een gelijk stookpatroon is dat **3–5
dagen**. Met alleen overbruggen (meetstuk 45 min) is het ~1 meting per 2 dagen:
te traag voor het venster van 14 dagen. Te snel leren is hier geen risico: de
drempels blijven staan en gelden per bak.

### 3. Pendelen

Op de afgespeelde data zou de E32 7 keer starten tegen 14 keer voor de tado.
De minimale aan- en uittijd van 5 minuten is genoeg. Met 10 minuten blijft het
aantal starts gelijk (7) en het verschil ook (−3 °C); er schuift alleen 5 minuten
verwarmen op. Geen reden om het te veranderen.

### 4. Varianten van de aanvoerregeling

Verschil met de tado (mediaan), op dezelfde data:

| Variant | E32 − tado |
|---|---|
| firmware (min 30, 10 °C per °C, integraal 30 min) | −3 °C |
| minimum 34 °C | +1 °C |
| 15 °C per °C tekort | +3 °C |
| integraal 60 min | −7 °C |
| min aan/uit 10 min | −3 °C |

### 5. Optimale start

De geleerde stijging bij 52 °C (0,58 °C/u) ligt iets boven wat de kamer op 1
november echt deed bij ~52 °C (0,5 °C/u). Een voorlooptijd uit geleerde
waarden kan dus ~15 % te kort zijn, ongeveer 15 minuten bij 1,5 uur. De
standaard voorlooptijd van 2 uur per °C zit nu juist iets aan de veilige kant.

## Voorstellen

De standaardwaarden blijven in deze branch ongewijzigd. Het besluit volgt na de
eerste week met actieve regeling.

1. **Overbruggen aanzetten voor ketels met een warmhoudvat.** Dat wordt
   `bridgeHotWater = true` met meetstukken van 30 minuten
   (`minSegmentMs = 1800000`). Zet het aan via het ketelprofiel (ketel met
   voorraad of warmhoudfunctie), dus niet vast voor dit huis. Andere ketels
   houden het gedrag van nu. Bewijs: 0 → 4 metingen in 41 uur; de test leert
   in 4 dagen hetzelfde als een huis zonder vat.
2. **Minimum 30 °C aanhouden.** Het remt nergens; de vraag zat tussen 38 en
   54 °C. Met 34 °C komt de E32 boven de tado uit en verliest hij het
   voordeel van lagere aanvoer. Is het te weinig, dan leert de stooklijn dat
   zelf.
3. **Versterking en integraal laten staan.** De versterking (10 °C per °C) en
   de integraal (30 min) geven een vraag net onder de tado, met de helft van
   de starts. De onderzochte varianten slaan door naar boven (+3) of naar
   beneden (−7).
4. **Optimale start: een vaste aanloop voor vloerverwarming.** Overweeg 15–20
   minuten bovenop de geleerde voorlooptijd, of een veiligheidsfactor van
   1,15. Pas dit pas toe als de geleerde voorlooptijden echt te laat blijken;
   het dagoverzicht meet dit vanaf 3 november ("op tijd" per ochtend).
5. **Branderstarts niet tellen op de vlag alleen.** Een start die binnen één
   bericht warm water wordt, hoort bij warm water. Dit is voor de telling en
   de waarschuwingen in 1.0, niet voor de regeling.

## Dagelijks na de overstap (14 dagen)

```sh
python3 -I tools/switchover/active_review.py --ha-url https://192.168.1.130:8123 --insecure \
    --room-climate climate.<woonkamer> --outdoor weather.buienradar --since 2026-11-03T08:00Z
```

Per dag zie je:

- **comfort**: of elke ochtendstap op tijd binnen 0,2 °C kwam, en of dat
  langer duurde dan de standaard voorlooptijd;
- **aanvoer**: gevraagd tegen gemeten, per tekortband;
- **E32 tegen tado**: zolang de tado nog meeluistert;
- **pendelen**: starts, korte rondes en mediane duur;
- **gas**: verwarming en warm water apart;
- **afkoelen**;
- **leren**: de leer- en stooklijnsensoren in HA.

Met `--json <bestand>` bewaar je het voor vergelijking. Na de eerste week
draaien we het harnas op die data. Daarna beslissen we voorstel 1 en 4 met
echte cijfers.
