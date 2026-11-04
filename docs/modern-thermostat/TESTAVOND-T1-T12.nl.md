# Testavond T1–T12: de bijgewoonde tests

**Status:** draaiboek voor na de installatie van rc.5, nog niet uitgevoerd (opgesteld 4 november 2026 voor Mark).
De tests zelf staan in [OVERSCHAKELING.nl.md §6](OVERSCHAKELING.nl.md#6-bijgewoonde-tests). Dit bestand zegt in
welke volgorde je ze doet, wie wat doet en met welk commando je elke uitkomst vastlegt. De woorden volgen de
schermen van rc.5: waar OVERSCHAKELING een oudere naam noemt (zoals "Schaduwmodus", nu "Proefperiode"), geldt dit
bestand.

**Waarom:** het 1.0-criterium `failure_tests` is pas `PASS` als T1 t/m T12 elk zijn vastgelegd met
`tools/switchover/record_test.py` (T12 mag het alternatief). Een test die je doet maar niet vastlegt, telt niet.

## 1. In het kort

| Deel | Tests, in deze volgorde | Duur | Wat het is |
| --- | --- | --- | --- |
| **Deel 1** | T12 → T1 → T2 (met T4 erin) → T3 → T5 → T6 → T7 | ± 2 u 20 | Verwarmen, stoppen, teruggeven, herstarten, de E32 stroomloos. Jij staat bij de ketel. |
| **Deel 2** | T9 → T8 → T10 → T11 | ± 2 u | Uitval van buiten (Home Assistant, wifi, sensor) en de tado terug. Veel wachten. |

**Samen ± 4 u 20; alle twaalf in één avond van 2,5 uur past niet.** De wachttijden die checklist en firmware
voorschrijven zijn alleen al bijna twee uur (T2 3 × 6 min, T7 tot 30, T8 20, T9 15, T10 30 min); met T1, T3, T5,
T6, T11 en T12 is het minimum ruim 2,5 uur, zonder overhead. Elke herstart of ketelstart kost er 4 à 5 minuten
bij. Daarom twee delen van elk minder dan 2,5 uur, op één dag met een pauze of op twee avonden vlak na elkaar. Er
valt niets af.

**Waarom deze volgorde:** T12 eerst (geen warmtevraag nodig; de ketel koelt af voor T1). T4 in T2, en de pauze van
T3 is de wachttijd voor T5. Alle E32-herstarts (T6, T7) in deel 1; deel 2 herstart de E32 niet (alleen T11, bij
busvoeding). T9 vóór T8: Home Assistant gaat 15 minuten eerder uit dan de wifi, dus de overgang naar de
reservesensor zie je live en T8 draait er bovenop (zwaarder dan de checklist). T11 als laatste: het enige moment
met twee regelaars, direct gevolgd door het herstel.

**De 14 dagen naar 1.0.0 beginnen ná deel 2.** Deze tests breken de klokken van `release_ready.py`. `stability`
telt 14 dagen vanaf de laatste herstart van de E32: T6 en T7 zijn voor het script onverwachte herstarts (alleen een
herstart rond een firmware-installatie is gepland) en een E32 die 5 minuten of langer onbeschikbaar is (T7) geeft
14 dagen `FAIL`. `active_control` telt 14 dagen waarin de E32 de ketel zelf vraagt zonder terugzetten: T5, T6, T7,
T10 en T11 breken die reeks. Doe de tests dus **vlak na de installatie van rc.5** en vóór je het venster start; het
venster begint op het moment dat de E32 na T11 weer regelt (§8). Doe je ze later, dan begint de klok daarna opnieuw.

## 2. Wat in dit huis niet van toepassing is

Alle twaalf tests gelden voor dit huis (een tado die op de adapter vervangen is door de E32, vloerverwarming met
drie radiatoren erbij, een Xiaomi als reservesensor, ketel achter een EasyControl Adapter). In T1–T12 zit geen
kranentest. **n.v.t.** zijn:

| Onderdeel | Status | Waarom | `release_ready.py` |
| --- | --- | --- | --- |
| Radiatorkranen: schakelaar "Radiatorkranen aansturen", kraanproef, criterium `trv_control` | **n.v.t. voor dit huis** | Geen slimme kranen op de drie radiatoren, geen zoneklep op de vloer. Doet de veldtester ([TESTER-PAKKET.nl.md](TESTER-PAKKET.nl.md)). | `trv_control` is `PASS` als "niet van toepassing" zodra er in de Home Assistant van `--ha-url` geen `…_valve_control`-schakelaar bestaat (rc.5: die schakelaars zijn er alleen voor ruimtes met kranen); met kranen moet de schakelaar 14 dagen aan hebben gestaan. |
| T3 "eerst Minimale brandertijd" (alleen bij een vraag korter dan 5 min) | **n.v.t. voor dit huis** | Na T2 brandde de brander al 25 minuten of langer. De minimale pauze is wel een eis en wordt gedaan. | Geen aparte uitslag. |
| T9 "Variant: broker weg 20 min" | Niet ingepland (optioneel) | De Mosquitto-add-on stop je in de Home Assistant-pagina, en die staat dan uit. | Zeg in de uitslag van T9 of je hem deed. |
| T12 "buiten koud leggen" | Alternatief mogelijk | Het hoeft niet te vriezen: weg A (hulpsensor in Home Assistant) of weg B (koeltas). | `alternative` mag alleen bij T12, met `--evidence`. |

`release_ready.py` kent geen "n.v.t.": een test zonder uitslag of met `skipped` geeft `failure_tests` = `WAIT` en
blokkeert 1.0.0. Een `fail` geeft `FAIL` tot een latere `pass` voor dezelfde test; de laatste uitslag telt.

## 3. Voor je begint

**De dag ervoor (± 15 min):**
- [ ] E32 `v1.0.0-e32v2-rc.5` met HA `1.0.0rc6` staan erop (met vastlegging geïnstalleerd), de E32 draait ≥ 24 uur
  stabiel, de overname is bevestigd, de tado is los. Ruimtes → **Actieve regeling** zegt "De E32 regelt de ketel."
  Draait er nog rc.4, gebruik dan bij `init` die versies (open vraag 1).
- [ ] Back-ups: Home Assistant (Instellingen → Systeem → Back-ups → Nu back-up maken) en de E32 (Systeem →
  Back-up en terugzetten → Back-up downloaden).
- [ ] **T12:** kies weg A (hulpsensor, 5 minuten in Home Assistant, bij T12) of weg B (Bluetooth-sensor, zakje,
  koeltas met koelelementen).
- [ ] Je weet hoe de E32 gevoed wordt: **eigen voeding** of **via de EMS-bus** (bepaalt T7 en T11; op de bus
  herstart de E32 elke keer dat de ketel uit gaat).
- [ ] Foto's van de bedrading op de adapter: het tado-paar (label "TADO") los en geïsoleerd, het E32-paar (label
  "E32 — niet losmaken") vast. De kaart van bijlage B is geprint en hangt bij de ketel.
- [ ] Het HA-token staat in `tools/acceptance/ha-token.txt` (alleen op de laptop) en `python3 --version` werkt in
  PowerShell (anders `py`). Alle commando's draai je in de hoofdmap van de repository (waar `tools/` staat).

**Op de dag zelf:**
- [ ] Buiten minder dan ± 12 °C (warmtevraag) en geen schakelpunt van het weekprogramma van de woonkamer tijdens de
  test (een schakelpunt verandert het doel).
- [ ] Huisgenoten weten het: warm water 3 minuten (deel 1), wifi 20 minuten uit en Home Assistant uit (deel 2).
- [ ] Waterdruk 1,1–2,5 bar (foto), geen storing op het display. De hoofdschakelaar of de CV-functie van de ketel
  is binnen handbereik.
- [ ] HA-automatiseringen die de tado of het plan wijzigen staan uit. Vandaag geen firmware-installatie.
- [ ] Stopwatch, camera, liefst een tweede persoon aan de laptop.

## 4. Steeds hetzelfde

- **[Claude]** kijkt mee en legt vast. Ik lees alleen (bewakingsbestanden, Home Assistant) en schrijf de
  uitslagenbestanden in de repository; ik druk niets in op de E32 of in Home Assistant. Jij drukt, ik kijk.
- Het E32-wachtwoord typ je in het PowerShell-venster van de bewaking, niet in dit gesprek. Ik zie en bewaar het
  nooit.
- De E32 kan **4 websessies** tegelijk (bewaking: één per meting, Home Assistant: één per wijziging). Gebruik hooguit
  **twee** browsers of tabbladen. Staat er "te veel sessies": Systeem → Diagnose en systeemlog → **Ongebruikte
  websessies beëindigen**.
- Druk nooit twee keer op dezelfde knop zonder te kijken wat de eerste deed. Foto van het keteldisplay bij elke test;
  de tijden legt de bewaking vast (`out/switchover-<datum>/`, blijft bij het opruimen bewaard).
- De getallen in de voorbeeldcommando's zijn verzonnen: schrijf wat je zelf zag, in gewone tekens (geen pijltjes of
  ≥, `C` voor graden) en niet beginnend met een streepje.
- **Twijfel? Afbreken en teruggeven** (bijlage B). Is een test niet gelukt: leg hem vast als `fail` met wat je zag en
  probeer niet blind opnieuw; een latere `pass` na een oplossing overschrijft de `fail`.

**Vastleggen:** één bestand voor beide delen, met de datum van deel 1. Zet de datum eenmalig (PowerShell onthoudt hem
niet tussen aanroepen):

```powershell
$D = '2026-11-14'     # de datum van deel 1; dezelfde in ALLE commando's, ook in deel 2
python3 -I tools/switchover/record_test.py --date $D status
```

`--date` en `--root` moeten vóór de naam van de test staan. Elke aanroep schrijft de tijd er zelf bij en toont de
stand van alle twaalf. Zonder `init` voor die datum zegt het commando "run init first".

## 5. Veiligheid

- **Jij staat bij de ketel**, met de hoofdschakelaar binnen handbereik. Geen test waarbij je de woning verlaat.
- **Vorstbeveiliging** blijft aan (de E32 vraagt de minimumaanvoer onder 8 °C, uit bij 9 °C, ook voor een inactieve
  ruimte), behalve in vensters waarin de E32 niets stuurt: T5 (± 3 min), T6 (tot ± 130 s na het opstarten), T7 (tot
  30 min) en T11 (de tado regelt dan, met zijn eigen vorstbeveiliging). Houd ze zo kort als de test vraagt.
- **Nooit de ketel zonder regelaar achterlaten:** elke test eindigt met "De E32 regelt de ketel." of met de tado
  terug. **Nooit twee regelaars:** alleen in T11 sluit je de tado aan, met de ketel eerst uit.
- **Afbreken en teruggeven** (bijlage B) bij: gemeten aanvoer meer dan 3 °C boven het plafond terwijl de CV verwarmt
  (niet bij tapwater) of een vraag boven het plafond (bewaking: `flow_above_limit`, `request_above_limit`; plafond
  = het laagste van planmaximum 60 °C, ketelmaximum en 80 °C); waterdruk onder 1,0 of boven 2,7 bar of een nieuwe
  vergrendelende storing; "Brander slaat te vaak aan en uit" of 6 of meer branderstarts per uur; `transmit_failed` of
  `boiler_no_response` zonder verklaring, of `foreign_controller` terwijl de tado los is; de ketel stookt zonder
  vraag of de keteltelemetrie valt weg (behalve T7, T8); de E32 meer dan 3 min onbereikbaar terwijl hij regelt
  (behalve T6, T7, T8) of een ruimte meer dan 1,5 °C boven het doel terwijl de E32 nog warmte vraagt; tapwater werkt
  niet, lawaai, geur, of jij twijfelt.
- **Geen firmware-installatie** vanavond: een update wist de bevestiging, en dan blijft er alleen vorstbeveiliging.

## 6. Deel 1: verwarmen, teruggeven, herstart, stroom eraf (± 2 u 20)

| Minuut | Wat | Duur |
| --- | --- | --- |
| 0 | 6.0 Start en nulmeting | 15 |
| 15 | T12 Vorstbeveiliging | 12 |
| 27 | T1 Start | 10 |
| 37 | T2 Modulatie, met T4 Tapwater erin | 28 |
| 65 | T3 Stop en minimale pauze | 8 |
| 73 | T5 Teruggeven en opnieuw overnemen | 12 |
| 85 | T6 E32-herstart | 12 |
| 97 | T7 E32 stroomloos | 38 |
| 135 | Deel 1 afsluiten | 5 |

### 6.0 Start (± 15 min)

**Jij:** open `http://192.168.1.206`, meld je aan, ga naar **Ruimtes → Actieve regeling** ("De E32 regelt de ketel.",
met een ketelmaximum) en maak een schermafbeelding. Foto van het keteldisplay en de manometer. Hang de kaart bij de
ketel.

**[Claude]:**
1. Maak de uitslagenlijst aan (één keer, voor beide delen):

   ```powershell
   $D = '2026-11-14'
   python3 -I tools/switchover/record_test.py --date $D init --firmware v1.0.0-e32v2-rc.5 --ha 1.0.0rc6
   ```

2. Start de bewaking in een **eigen venster**; het vraagt "E32 password for admin:" en jij typt daar het E32-wachtwoord.
   Hij meet elke 30 s, schrijft naar `out/switchover-<datum>/` en stopt na 3 uur zelf:

   ```powershell
   Start-Process powershell -WorkingDirectory $PWD.Path -ArgumentList '-NoExit','-Command',"python3 -I tools/switchover/monitor.py --host http://192.168.1.206 --interval 30 --duration-h 3 --out out/switchover-$D"
   ```

3. Kijk één keer met de kijkregel (bijlage A). Verwacht: `active`, bevestiging bewaard (`true`), geen
   waarschuwingen, ketelmaximum bekend (`boiler_limit.flow_c`). Anders niet beginnen.

### T12 Vorstbeveiliging (eerst, ± 12 min)

**Controleert:** dat de E32 minimumaanvoer vraagt zodra een (ook inactieve) ruimte onder 8 °C komt en weer stopt
vanaf 9 °C, terwijl de woonkamer zelf geen warmte vraagt.

**Weg A, eenmalig vooraf (5 min):** in Home Assistant: Instellingen → Apparaten en diensten → Hulpmiddelen
(Helpers) → Hulpmiddel maken: (1) **Getal** (Number) `Test vorst badkamer`, 0–30, stap 0,5, invoerveld, beginwaarde
20; (2) **Sjabloon → Sjabloon voor een sensor** (Template a sensor) `Test vorst badkamer meting`, staatsjabloon
`{{ states('input_number.test_vorst_badkamer') | float(20) }}`, eenheid `°C`, apparaatklasse temperatuur,
statusklasse meting. Dat geeft `sensor.test_vorst_badkamer_meting`.

**Jij (weg A):**
1. E32 **Overzicht** → kaart Woonkamer → **Tijdelijk wijzigen**: ± 1 °C **onder** de meting, Duur **1 uur**,
   **Instellen**. De woonkamer vraagt dan geen warmte meer ("Warm genoeg"); loopt de brander nog, dan maakt hij eerst
   zijn kortste brandtijd af.
2. Home Assistant: Configureren (OpenThermostat) → **Ruimtes** → **Ruimte bewerken of verwijderen** → Badkamer →
   **Ruimte bewerken**: voeg bij **Temperatuurbronnen uit Home Assistant** de testsensor toe, sleep hem **naar
   boven**, **Verzenden**. De ruimte blijft inactief.
3. Getal `Test vorst badkamer` op **20** (wacht 1 min), dan op **7,5** (E32 reageert binnen ± 15 s: **Ruimtes →
   Actieve regeling** toont een Ketelvraag: de minimumaanvoer), dan **8,5** (30 s: de vraag blijft), dan **9,5** (vraag uit binnen
   ± 15 s).
4. Herstel: haal de testsensor weer uit de badkamer (zelfde formulier) en zet de woonkamer terug met **Terug naar het
   weekprogramma**.

**Weg B (zoals de checklist):** Xiaomi in een zakje in een koeltas met koelelementen naast de E32 (Bluetooth-bereik).
Geef de badkamer in het formulier tijdelijk de Xiaomi als bron (Bluetooth-sensoren op de E32, **Bluetooth-sensoren
eerst gebruiken**), wacht tot hij onder 8 °C meldt, houd hem dan in je hand tot boven 9 °C, en zet daarna alles terug.

**[Claude]:** na 20 °C: badkamer `temperature` 20 met de testsensor als `source`. Na 7,5 °C: `guard.command.why` =
`frost_minimum` met `flow_c` = de minimumaanvoer (30 °C, of de geleerde laagste aanvoer waarop jouw ketel aangaat),
badkamer `state` `inactive`. Na 8,5 °C blijft de vraag (hysterese). Na 9,5 °C is hij 0. Geen `frost_not_protected`.

**Geslaagd als:** beide omslagen binnen één stap (10 s plus het doorgeven door Home Assistant) na de meting, de badkamer
blijft inactief, geen `frost_not_protected`, het plan is teruggezet.

```powershell
python3 -I tools/switchover/record_test.py --date $D T12 pass 'bad 7,5 C: vraag 30 C met reden frost_minimum na 12 s; 8,5 C bleef aan; 9,5 C uit na 10 s; badkamer bleef inactief; gesimuleerd met HA-hulpsensor' --evidence 'monitor out/switchover-<datum>, schermafbeelding Actieve regeling 18:42'
```

(Weg B: schrijf "echte koude sensor".) Lukte geen van beide, dan mag het alternatief uit de checklist, met bewijs:

```powershell
python3 -I tools/switchover/record_test.py --date $D T12 alternative 'niet koud kunnen maken op de avond zelf' --evidence 'soakscenario frost en test_active_heat_guard groen, CI-run <nummer>'
```

**Mislukt?** Vraag blijft uit onder 8 °C of blijft aan boven 9 °C: `fail` met de gemeten waarden; kijk of de testsensor de
**eerste** bron van de badkamer is. Geen reden om af te breken, tenzij de woonkamer ongevraagd warmte vraagt.

### T1 Start (± 10 min)

**Controleert:** dat een vraag van de E32 bij de ketel aankomt en de brander laat starten.

**Jij:** (1) ketel ten minste 5 min uit, noteer de woonkamertemperatuur. (2) Overzicht → Woonkamer → **Tijdelijk
wijzigen**: ± 1 °C **boven** de meting, Duur **2 uur**, **Instellen** ("Opgeslagen. De ruimte volgt binnen 10
seconden."); stopwatch. (3) Kijk op het ketelscherm en op **Ruimtes → Actieve regeling**: Ketelvraag ± 40 °C (30 °C
plus 10 °C per graad tekort; met de weerafhankelijke regeling kunnen het enkele graden meer of minder zijn) en
"laatst verzonden … geleden". Foto van het display zodra de CV aanslaat.

**[Claude]:** `guard.command.flow_c` > 0 binnen 10–20 s (`why` = `heat_request`), woonkamer `demand` `true`,
`boiler.heating_active` `true`, `selected_flow_c` volgt de vraag, aanvoer ≥ 3 °C hoger binnen 15 min,
`transmitted_frames` + 1 per minuut, geen waarschuwing.

**Geslaagd als:** Verwarming actief binnen 2 min (tot ± 10 min als de eigen pendelblokkering van de ketel loopt:
noteren), aanvoer ≥ 3 °C hoger binnen 15 min, geen `boiler_no_response`.

```powershell
python3 -I tools/switchover/record_test.py --date $D T1 pass 'doel +1 C: vraag 41 C na 10 s verzonden; verwarmen actief na 4 min; aanvoer +8 C in 9 min; gekozen aanvoer volgde de vraag' --evidence 'foto display 18:58, monitor out/switchover-<datum>'
```

**Mislukt?** Geen brander na 10 min of geen aanvoerstijging na 15 min: `fail` en de rest van de avond heeft geen zin.
Foto, **teruggeven** (bijlage B), vastleggen, bewakingsmap bewaren.

### T2 Modulatie, met T4 Tapwater erin (± 28 min)

**Controleert:** (T2) dat de aanvoer de vraag volgt bij een groter tekort, onder het plafond blijft en de CV aan blijft
over de verversing van elke 60 s; (T4) dat tapwater voorrang krijgt zonder dat de E32 stopt of waarschuwt.

**Jij:** stap +1 is T1 en loopt al. (1) Stap +2: **Tijdelijk wijzigen** op ± 2 °C boven de **actuele** meting,
**Instellen**, wacht 6–8 min. (2) Stap +3: ± 3 °C boven de actuele meting; wacht tot de CV stabiel verwarmt (± 6 min).
(3) **T4:** warme kraan helemaal **3 minuten** open, dicht; stopwatch; foto van het display tijdens het tappen (Nefit
doorgaans `=H`; zie de ketelhandleiding). (4) Wacht tot de CV terug is (≤ 5 min).

**[Claude]:** per stap blijft de vraag onder het plafond (de bewaking is stil bij `request_above_limit` en
`flow_above_limit`) en zit de gemeten aanvoer binnen ± 3 °C van de vraag binnen ± 10 min; `heating_active` blijft `true`
over de verversingen. De vraag stijgt meestal per stap of blijft op het geleerde plafond: beoordeel het patroon, niet
het getal. Tijdens het tappen: `dhw_active` `true`, `heating_active` `false`, toestand `active`, vraag ongewijzigd, geen
waarschuwing, aanvoer mag naar ± 75 °C (warmtewisselaar); daarna `heating_active` weer `true` binnen 5 min.

**Geslaagd als:** T2: aanvoer binnen ± 3 °C per stap, CV blijft aan, geen alarm. T4: CV binnen 5 min terug, geen stop,
geen waarschuwing, tapwater normaal.

```powershell
python3 -I tools/switchover/record_test.py --date $D T2 pass 'stappen +1/+2/+3 C: vraag 41/44/47 C; aanvoer binnen 3 C na 6 min per stap; CV bleef aan over de verversingen; geen alarm' --evidence 'monitor out/switchover-<datum>, 19:05-19:25'
python3 -I tools/switchover/record_test.py --date $D T4 pass 'kraan 3 min open: warm water actief, CV pauze, toestand active, vraag ongewijzigd, geen waarschuwing; CV terug na 2 min; tapwater warm' --evidence 'foto display 19:21'
```

**Mislukt?** Meer dan 3 °C boven het plafond bij CV: afbreken en teruggeven. Aanvoer volgt niet binnen ± 3 °C na 10 min of
de CV valt even weg: T2 `fail`. CV niet terug binnen 5 min na het tappen of toestand niet meer `active`: T4 `fail`.

### T3 Stop en minimale pauze (± 8 min)

**Controleert:** dat de E32 bij een bereikt doel stopt (een minuut elke 10 s een nul), de ketel binnen ± 30 s uit gaat
en er daarna niet vóór 5 minuten een nieuwe start komt.

**Jij:** (1) **Tijdelijk wijzigen** op ± 1 °C **onder** de actuele meting, **Instellen**, stopwatch (Overzicht: "Warm
genoeg"; Ruimtes: Ketelvraag uit). (2) Foto van het display zodra de CV uit is. (3) **Na 1 minuut:** doel weer ± 1 °C
**boven** de meting, Duur 2 uur: Overzicht zegt "Wacht: minimale ketelpauze", Ruimtes "Brander rust voor de volgende
start". Wacht en kijk wat de ketel doet.

**[Claude]:** na de eerste nul `command.why` `stop_zero`, `flow_c` 0, `transmitted_frames` ± 6 per minuut;
`heating_active` `false` binnen ± 30 s; geen positieve vraag en geen nieuwe start tot ± 5 min na de stop
(`heating_starts_last_hour` loopt niet op); daarna begint de vraag weer. De E32 mag de pauze langer maken (hij leert het
rustritme van de ketel); minstens 5 minuten is de eis.

**Geslaagd als:** Verwarming actief uit binnen ± 30 s na de eerste nul, geen nieuwe start binnen 5 min, geen waarschuwing.

```powershell
python3 -I tools/switchover/record_test.py --date $D T3 pass 'doel 1 C onder meting: eerste nul, CV uit na 22 s, 6 nullen in een minuut; weer omhoog na 1 min: Brander rust voor de volgende start; geen start tot 6 min na de stop; geen waarschuwing' --evidence 'foto display 19:31, monitor out/switchover-<datum>'
```

**Mislukt?** De ketel brandt 2 min na de nullen nog door (de adapter stookt zonder vraag): afbreken, `fail`. Start vóór
5 min opnieuw: `fail`.

### T5 Teruggeven, zonder de tado aan te sluiten (± 12 min)

**Controleert:** dat de teruggeefknop de E32 netjes laat stoppen, het plan naar de proefperiode laat gaan, de bewaarde
bevestiging wist en dat je daarna gewoon weer kunt overnemen.

**Jij:** (1) Wacht tot de CV weer verwarmt (na T3 5 à 10 min); foto van het display. (2) **Ruimtes → Actieve regeling →
Regeling teruggeven aan mijn thermostaat (de E32 vraagt de ketel eerst een minuut geen warmte)**, bevestig,
stopwatch. De pagina meldt "Teruggegeven…" en vraagt je de thermostaat weer aan te sluiten: **dat doe je niet**.
(3) Wacht op "Proefperiode: je thermostaat regelt de ketel." (≤ ± 70 s). (4) Neem direct weer over: de knop onder Actieve
regeling (naam hangt van de situatie af: "Mijn thermostaat is losgekoppeld van de ketel — laat de E32 overnemen", "Toch
overnemen" of "Test overslaan en de overname nu bevestigen") en bevestig. Je ziet "Bevestigd. De E32 neemt de ketel
binnen een minuut over.", "Overstappen…" en na ± 1 min "De E32 regelt de ketel." (5) Staat het tijdelijke doel er niet
meer, zet het opnieuw (± 1 °C boven de meting, 2 uur).

**[Claude]:** `stopping` (nullen), `heating_active` `false` binnen ± 30 s, dan `shadow` met `confirmation_stored`
`false`; `transmitted_frames` staat stil (3 metingen gelijk); bewaking `handed_back`. Na de overname `arming`, dan `active`
binnen ± 2 min met `confirmation_stored` `true`.

**Geslaagd als:** CV uit binnen ± 30 s, daarna zendt de E32 niets, de bewaking toont `handed_back`, opnieuw overnemen lukt.

```powershell
python3 -I tools/switchover/record_test.py --date $D T5 pass 'teruggeven tijdens verwarmen: CV uit na 25 s; stopping 62 s; daarna Proefperiode, bevestiging niet bewaard, frames stil; opnieuw overgenomen: active na 80 s' --evidence 'schermafbeelding Actieve regeling 19:47, monitor out/switchover-<datum>'
```

**Mislukt?** "De E32 heeft het stoppen niet bevestigd": tado blijft los, één keer opnieuw, anders noodkaart. Mislukt alleen het
opslaan van het plan, dan is de E32 al gestopt: druk nogmaals.

### T6 E32-herstart met bewaarde bevestiging (± 12 min)

**Controleert:** dat een geplande herstart eerst de vraag intrekt, de E32 zonder nieuwe bevestiging terugkomt, na ± 130 s
weer regelt en wat de ketel in het gat doet (O2, deel 1).

**Jij:** (1) Wacht tot de CV weer verwarmt met een matige vraag (± 40 °C); foto. (2) **Systeem → Apparaat herstarten**,
bevestig; t0 + stopwatch. Kijk wat het display doet tijdens de herstart (stookt de CV door of valt hij stil?). (3) De pagina
valt ± 30–60 s weg; meld je daarna weer aan.

**[Claude]:** `stopping` met nullen (de E32 herstart pas als een nul is afgeleverd, uiterlijk na 90 s); daarna een nieuwe
`boot_id` met `reset_reason_name` `software` (bewaking `e32_restarted`); `arming` met `confirmation_stored` `true`;
`boiler_limit` `reads` ≥ 1 en `flow_c` bekend vóór de eerste positieve vraag; ± 130 s na het opstarten `active`
zonder nieuwe bevestiging, binnen 4 à 5 min na t0; geen `awaiting_confirmation`.

**Geslaagd als:** weer `active` binnen ± 4–5 min na t0 zonder nieuwe bevestiging, `e32_restarted` met `software`, de
zwarte doos (Diagnose en systeemlog) toont de handmatige herstart. Wat de ketel in het gat deed, schrijf je in de uitslag.

```powershell
python3 -I tools/switchover/record_test.py --date $D T6 pass 'herstart via Systeem: stopping met nullen, E32 weg 40 s, arming met bevestiging hersteld, active na 4 min 10 s zonder nieuwe bevestiging; reset_reason software; ketel stopte na de nul en bleef stil tot de E32 terug was' --evidence 'monitor out/switchover-<datum>, foto display 20:02'
```

**Mislukt?** Een nieuwe bevestiging nodig (`awaiting_confirmation`) of niet `active` binnen 6 min: `fail` (bevestig opnieuw om
door te gaan). Stookt de ketel ongecontroleerd: noodkaart.

### T7 E32 stroomloos, adaptergedrag (± 38 min)

**Controleert:** wat de ketel (via de adapter) doet als de E32 plotseling stopt met zenden: de laatste vraag vasthouden
of na een tijd stoppen (O2). Dit is de ene meting die alleen deze avond kan geven.

**Jij:** (1) Wacht tot de CV verwarmt met ± 40 °C en de kraan dicht is; foto en tijd. (2) **Eigen voeding:** stekker/USB
uit de E32. **Via de bus:** de twee E32-draden (label "E32") van de adapter, met de ketel **aan**. Stopwatch. (3) Meet
zonder E32: foto van het display bij 0, 2, 5, 10, 15, 20 en 30 min; voel aan de aanvoerleiding (of infraroodthermometer),
luister naar de brander; noteer de **tijd waarop de CV stopt**, als hij stopt (Nefit doorgaans `0H` = rust, controleer in
de handleiding; bij jou is `0Y` "doel gehaald, brander wacht"). Heb je een gasmeter in Home Assistant: loopt het verbruik
door? (4) Stop zodra de CV stopt en 2 min stil blijft, of na **30 min**. Na 15 min is O2 beantwoord: houdt hij de vraag dan
nog vast, dan is dat de uitkomst. Staat de kamer meer dan 1,5 °C boven het doel, sluit de E32 dan eerder aan. (5) E32 weer
aan (stekker of busdraden terug); noteer de tijd.

**[Claude]:** bewaking: `e32_unreachable` na 3 min (verwacht) en `e32_back`. Na het opstarten: nieuwe `boot_id`,
`reset_reason_name` `power_on`, één nul rond 10 s na het opstarten (`command.why` `boot_zero`), `arming`, en ± 130 s na
het opstarten `active` zonder nieuwe bevestiging, uiterlijk ± 4–5 min na het inschakelen.

**Geslaagd als:** het adaptergedrag is gemeten en getimed (de uitslag zegt: de ketel hield de vraag N min vast, of stopte
na N min) en de E32 regelt binnen ± 4–5 min weer zonder nieuwe bevestiging.

```powershell
python3 -I tools/switchover/record_test.py --date $D T7 pass 'E32 30 min stroomloos bij vraag 41 C: ketel hield de vraag vast en bleef stoken (aanvoerleiding warm) tot de E32 terug was; geen stop door de adapter binnen 30 min; E32 terug: boot_zero na 10 s, active na 3 min 50 s zonder bevestiging; reset_reason power_on' --evidence 'foto display 20:20-20:50, monitor out/switchover-<datum>'
```

(Stopte de adapter wel, schrijf dat met de tijd.)

**Mislukt?** Het gedrag zelf is de meting, geen mislukking. `fail` is: de E32 komt niet vanzelf terug in `active` binnen 6 min,
vraagt een nieuwe bevestiging, of de ketel stookt gevaarlijk door (kamer > 1,5 °C te warm, vreemd lawaai: afbreken). Houdt de
adapter de vraag langer dan ± 15 min vast, leg dat ook vast als vervolgpunt: er moet voor 1.0 een maatregel gekozen worden
(O2).

### Deel 1 afsluiten (± 5 min)

**Jij:** doel terug (**Terug naar het weekprogramma**), foto manometer en display, controleer "De E32 regelt de ketel."
Sluit het bewakingsvenster met Ctrl+C als je pauzeert (hij stopt anders na 3 uur zelf).

**[Claude]:**

```powershell
python3 -I tools/switchover/record_test.py --date $D status
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'monitor\.py' } | Select-Object ProcessId, CommandLine
```

Het eerste toont T1–T7 en T12 als `pass` (T8–T11 `open`). Het tweede hoort leeg te zijn zodra het venster dicht is (een
vergeten bewaking houdt een E32-websessie vast).

## 7. Deel 2: uitval van buiten en de tado terug (± 2 u)

Plan het vóór het eerstvolgende schakelpunt van het weekprogramma, niet laat op de avond: T11 doe je liefst uitgerust.
Tijdlijn, met t = 0 op het moment dat de wifi uitgaat:

| Tijd | Wat | Test |
| --- | --- | --- |
| −15 | Home Assistant Core stoppen; voorbereiding (7.0) | T9 begint |
| −5 tot −1 | woonkamer: **Reservesensor in gebruik** (10 à 15 min na het stoppen van HA) | T9: de overgang |
| 0 | wifi uit | T8 begint |
| +20 | wifi aan; E32 na 1–2 min weer bereikbaar | T8 klaar |
| +22 | batterij uit de Xiaomi | T10 begint (t0) |
| +37 | woonkamer: **Sensor stil: laatste meting gebruikt** | T10 + 15 min |
| +52 | **Geen meting**, Ketelvraag 0, CV uit | T10 + 30 min |
| +53 | batterij terug | |
| +56 | Home Assistant Core starten; binnen 5 min is de tado-bron terug | T9 klaar |
| +62 | T8, T9, T10 vastleggen | |
| +65 | T11, herstel, afsluiten | ± 35 min |

### 7.0 Start (± 15 min, gelijk met de eerste 15 min van T9)

**Jij:** (1) De Xiaomi ligt in de woonkamer en wordt gehoord (E32: Systeem → Bluetooth-sensoren → Jouw sensoren:
"Laatste update" < 1 min geleden); de badkamer heeft zijn oorspronkelijke bron weer. (2) Stop **Home Assistant Core** (zie
T9) en noteer de tijd. (3) Terwijl de 15 min van T9 lopen: E32-pagina → **Tijdelijk wijzigen**: ± 1,5 °C boven de
meting, Duur **4 uur** (werkt zonder Home Assistant), zodat er vraag is. Zeg het huisgenoten: over ± 15 min gaat de wifi 20
min uit. Foto van display en manometer.

**[Claude]:** start de bewaking opnieuw in een eigen venster (zelfde commando als in 6.0) en kijk één keer met de kijkregel;
deel 2 gebruikt dezelfde `$D`.

### T9 Home Assistant weg (t = −15 tot +56)

**Controleert:** dat de E32 zonder Home Assistant doorregelt: na 10 à 15 min leidt de reservesensor (Xiaomi) in plaats van de
tado via Home Assistant, geen stop, geen herstart, en na het starten van Home Assistant is binnen 5 min alles terug.

**Jij:** (1) `ha core stop` via SSH of op de console van de HA-machine (de browser-terminal van de add-on loopt via Home
Assistant en valt daarbij weg; de Mosquitto-add-on blijft draaien). Starten, met `ha core start`, kan dan ook alleen via SSH of
de console. Kan dat niet: schakel de integratie OpenThermostat uit (Instellingen → Apparaten en diensten → OpenThermostat →
⋮ → Uitschakelen); dat is niet precies hetzelfde (de integratie meldt zich netjes af), schrijf het in de uitslag. (2) Na 10 à 15 min (Home Assistant stuurt de tado-meting elke 5 min door en een meting is 15
min geldig) zegt de E32-pagina bij de woonkamer **Reservesensor in gebruik**: schermafbeelding. (3) Laat Home Assistant uit tot het einde van T10.

**[Claude]:** `ha.input_age_s` loopt op; na 10 à 15 min `status` `fallback` met de Xiaomi als `source`; toestand `active`; geen
stop, geen `e32_restarted`; vraag logisch.

*Optioneel, + 20 min, na T10:* Home Assistant starten, de Mosquitto-add-on 20 min stoppen (Instellingen → Add-ons) en weer
starten ("broker weg"; geen herstart verwacht). Zeg in de uitslag van T9 of je dit deed.

### T8 Wifi weg, 20 min (t = 0 tot +22)

**Controleert:** dat een netwerkverlies van 20 minuten (langer dan de oude 15 minuten van `wifi_lost`) de E32 niet herstart
en niet laat stoppen terwijl hij de ketel regelt.

**Jij:** (1) Zodra T9's reservesensor zichtbaar is (uiterlijk 15 min na het stoppen van HA): zet het wifi-toegangspunt van de E32 uit, of weiger alleen de E32 op
wifi-niveau (router: Wi-Fi-apparaat weigeren/MAC-filter; géén firewallregel, de E32 moet de wifi zien verdwijnen). Gaat alle
wifi uit, dan verliezen laptop en ik de verbinding (mag; gebruik een kabel of je telefoonhotspot om mee te kijken).
Stopwatch 20 min. (2) Blijf bij de ketel; foto van het display bij +5, +10, +15, +20 min; noteer of de CV doorstookt (geen
gat). (3) Na 20 min wifi aan.

**[Claude]:** na terugkeer (± 1–2 min): dezelfde `boot_id`, `uptime_s` loopt door (≥ 20 min meer), geen `e32_restarted`,
`previous_boot` ongewijzigd, `guard.state` `active`, vraag logisch. De bewaking toont tijdens de uitval "niet bereikbaar"
(`e32_unreachable` na 3 min is normaal).

**Geslaagd als:** na terugkeer geen herstart, toestand `active`, geen gat op het keteldisplay.

```powershell
python3 -I tools/switchover/record_test.py --date $D T8 pass 'wifi 20 min uit (naast HA uit): zelfde boot_id, uptime liep door, geen herstart, active, CV stookte door zonder gat; E32 weer bereikbaar na 90 s' --evidence 'foto display 20:44-21:04, monitor out/switchover-<datum>'
```

**Mislukt?** Een herstart (nieuwe `boot_id`, `e32_restarted`) of `awaiting_confirmation` na terugkeer: `fail`.

### T10 Meting weg, aansluitend op T9 (t = +22 tot +55; Home Assistant blijft uit)

**Controleert:** dat de E32 bij verlies van elke meting de vraag na 30 minuten veilig stopt, niet herstart
(`bluetooth_silent`) en vanzelf weer gaat regelen zodra er een meting is.

**Jij:** (1) Zodra de wifi terug is en de E32 bereikbaar: op t0 de **batterij uit de Xiaomi** (of in een blikken trommel: voor
de E32 hetzelfde); noteer t0. (2) Bij t0 + 15 min: woonkamer **Sensor stil: laatste meting gebruikt**. Bij t0 + 30 min:
**Geen meting: deze ruimte vraagt geen warmte**, Ketelvraag 0, Actieve regeling "Geen ruimtemetingen: de E32 vraagt de ketel
geen warmte tot er weer een meting is." met de waarschuwing "Ruimtemetingen ontbreken."; foto: CV binnen ± 1 min uit. (3)
Direct erna **batterij terug**; wacht tot de woonkamer binnen ± 2 min weer **Reservesensor in gebruik** zegt en Actieve
regeling "De E32 regelt de ketel."

**[Claude]:** t0 + 15: `status` `stale`. t0 + 30: `status` `lost`, `guard.state` `stopped_measurement_lost`, `warnings` met
`measurement_lost`, `command.why` `measurement_lost`, vraag 0; bewaking `guard_stopped` en `warning_measurement_lost`, **geen**
`e32_restarted`. Na de batterij: `fallback` en vanzelf weer `active` (na de minimale pauze) zonder bevestiging; de alarmen
gaan weer uit.

**Geslaagd als:** CV uit binnen ± 1 min na t0 + 30, `guard_stopped` en `warning_measurement_lost`, geen herstart, na de
batterij binnen ± 2 min een meting en vanzelf weer `active` zonder nieuwe bevestiging.

### Home Assistant weer starten (t = +56) en T8, T9, T10 vastleggen

**Jij:** `ha core start` (of de integratie weer inschakelen), wacht ± 3 min.

**[Claude]:** binnen 5 min is de woonkamerbron weer de tado-entiteit (`status` `ok`), `ha.input_age_s` klein,
HA-entiteiten beschikbaar, toestand `active`, geen herstart. Leg nu T8 (hierboven), T9 en T10 vast:

```powershell
python3 -I tools/switchover/record_test.py --date $D T9 pass 'HA Core ruim een uur uit, broker bleef aan: na 14 min Reservesensor in gebruik, geen stop en geen herstart, vraag logisch; HA terug: tado-bron na 2 min; variant broker weg niet gedaan' --evidence 'schermafbeelding 20:36, monitor out/switchover-<datum>'
python3 -I tools/switchover/record_test.py --date $D T10 pass 'batterij uit: +15 min Sensor stil: laatste meting gebruikt; +30 min Geen meting, vraag 0, stopped_measurement_lost, waarschuwing; CV uit na 40 s; batterij terug: active na 3 min zonder bevestiging; geen herstart' --evidence 'foto display 21:20, monitor out/switchover-<datum>'
```

**Mislukt?** T9: een stop of herstart, of de reservesensor leidt niet binnen ± 16 min: `fail`. T10: de E32 vraagt na t0 + 30
nog warmte, herstart door `bluetooth_silent`, of regelt na de batterij niet vanzelf weer: `fail`.

### T11 Vreemde regelaar: de tado terug terwijl de E32 regelt (t = +65, ± 25 min)

**Controleert:** dat de E32 zichzelf stopt en waarschuwt zodra een andere regelaar de ketel om warmte vraagt, zonder dat jij
een knop indrukt, en daarna niet overneemt tot jij bevestigt.

**Veiligheid:** het enige moment met twee regelaars; ketel eerst uit. Zet de E32 zonder vraag (**Tijdelijk wijzigen** ± 1 °C
**onder** de meting, 1 uur), zodat er niets positiefs op de bus staat als de tado spreekt.

**Jij:** (1) Foto's van tado-draden en klemmen klaar, kaart bij de hand. (2) Ketel **uit**. (3) Tado-paar ("TADO") weer op de
adapter, zoals op de foto; de E32-draden blijven zitten. (4) Ketel **aan**, noteer de tijd. Eigen voeding: de E32 blijft
draaien. Via de bus: de E32 herstart mee, luistert 2 min en wacht dan (verwacht). (5) De tado heeft 1–3 min nodig voor hij
spreekt (HA: **Gevraagde watertemperatuur (thermostaat)** krijgt een waarde; E32: "laatste vraag van een andere thermostaat …
geleden"). Binnen ± 1 min daarna stopt de E32: "Stoppen…", dan "Gestopt: na het overstappen vroeg een andere thermostaat de
ketel nog om warmte." met de waarschuwing "Een andere thermostaat (je oude?) vraagt de ketel nog om warmte…". (6) Kijk of de
tado regelt: warme kraan 1 min, geen storing. (7) **Stopt de E32 niet binnen 2 min na de eerste vraag van de tado: ketel uit,
E32 stroomloos, noodkaart.**

**[Claude]:** `stopping`, dan `blocked_foreign_controller`; `warnings` met `foreign_controller`; `foreign_controller.age_s` < 60 s
en jong blijvend (de tado vraagt elke ± 40 s); `confirmation_stored` `false`; bewaking `guard_stopped` en
`warning_foreign_controller`. Bij busvoeding na de herstart `awaiting_confirmation` (niet `active`).

**Geslaagd als:** de E32 stopt en waarschuwt zelf zonder knop, de tado regelt daarna, `guard_stopped` en
`warning_foreign_controller` in de bewaking, na een E32-herstart `awaiting_confirmation`.

```powershell
python3 -I tools/switchover/record_test.py --date $D T11 pass 'tado terug met ketel eerst uit: E32 stopping na 45 s, dan blocked_foreign_controller met waarschuwing, bevestiging gewist; tado regelt, warm water ok; bij herstart E32 awaiting_confirmation' --evidence 'foto display 21:52, monitor out/switchover-<datum>'
```

**Mislukt?** De E32 blijft vragen terwijl de tado ook vraagt: afbreekreden (ketel uit, E32 stroomloos, noodkaart), `fail`, stop de
avond.

**Herstel (altijd, ± 12 min):** leg eerst T11 vast, dan: (1) **Regeling teruggeven aan mijn thermostaat** (plan naar de
proefperiode; de tado regelt). (2) Wil je door met de E32 als enige regelaar: ketel **uit**, tado-paar weer los (labelen,
isoleren, foto), ketel **aan**; overnameknop onder Actieve regeling (zie T5 stap 4), bevestig, wacht op "De E32 regelt de
ketel." (± 2 min; op de bus ± 4 min). (3) Controleer binnen 3 min: HA **Gevraagde watertemperatuur (thermostaat)** wordt
onbeschikbaar, op de E32 wordt "laatste vraag van een andere thermostaat" ouder dan 3 min zonder waarschuwing, warme kraan 1
min, waterdruk 1,1–2,5 bar, geen storing. (4) Doel terug (**Terug naar het weekprogramma**).

## 8. Afsluiten

**Jij:** foto van manometer en display; controleer "De E32 regelt de ketel." en het weekprogramma; sluit het bewakingsvenster.

**[Claude]:**
1. `python3 -I tools/switchover/record_test.py --date $D status`: alle twaalf `pass` (T12 mag `alternative`); geen `fail` of `open`.
2. **Noteer het moment** (UTC: in de winter lokale tijd min 1 uur) waarop de E32 na T11 weer `active` was: dat is `--since` voor `release_ready.py`, maar niet
   vóór het einde van de rc.5-installatie (neem het latere).
3. Laat `release_ready.py` het één keer lezen (alleen lezen). `failure_tests` moet `PASS` zijn; de rest `WAIT`, en
   `install_guide` blijft `WAIT` en `trv_control` is `PASS` (niet van toepassing: geen kranen):

   ```powershell
   $env:OT_HA_TOKEN = (Get-Content tools/acceptance/ha-token.txt -Raw).Trim()
   python3 -I tools/switchover/release_ready.py --ha-url https://192.168.1.130:8123 --insecure --release v1.0.0-e32v2-rc.5 --since 2026-11-14T20:15Z --json out/switchover-$D/release-ready-$D.json
   ```

   Het tijdstip bij `--since` is verzonnen. Geef altijd `--since`: zonder leest hij 15 dagen terug en telt hij de uitval van
   deze avond (T7) als `FAIL`. Draai dit daarna dagelijks tot 1.0.0
   ([OVERSCHAKELING.nl.md §9.2](OVERSCHAKELING.nl.md#92-eerste-2-weken-fase-5)).
4. Schrijf het verslag `docs/modern-thermostat/SWITCHOVER-<datum>.json` in de vorm van
   [BETA12-ATTENDED-HEAT-20261027.json](BETA12-ATTENDED-HEAT-20261027.json) (firmware, aanwezigen, druk, per test tijden en
   uitkomst, adaptergedrag T6 en T7 met de gemeten tijd, jouw oordeel, vervolgpunten) en een regel in
   [NEXT-RELEASE.nl.md](NEXT-RELEASE.nl.md). Commit met expliciete paden (ook `OVERSCHAKELING-RESULTATEN-<datum>.json`); geen
   push zonder jouw woord.
5. Controleer dat er geen bewaking is blijven draaien (de `Get-CimInstance`-regel van "Deel 1 afsluiten").

**De klok:** vanaf stap 2 lopen de 14 dagen voor `stability` en `active_control`; 1.0.0 kan op zijn vroegst 14 dagen later.
Een nieuwe E32-herstart, teruggeven of firmware-update daarbinnen zet de klok terug.

**Open vragen aan Mark (ook in het rapport):**
1. Tellen de tests op rc.5 (dit draaiboek), of is rc.4 ook goed? `init` legt de firmware vast; `release_ready.py` controleert hem niet.
2. Na een firmwarefix op grond van een mislukte test: alleen die test opnieuw, of alles?
3. Hoe wordt de E32 gevoed (eigen voeding of bus)? Dat bepaalt T7 en T11.
4. Mag T12 met de hulpsensor in Home Assistant (gesimuleerd) in plaats van een echte koude sensor?
5. De variant "broker weg" van T9: overslaan of toevoegen (+ 20 min)? En mag T7 na 20 in plaats van 30 min stoppen (O2 is na 15 min beantwoord)?
6. ~~`trv_control` kent geen "n.v.t."~~ Opgelost in rc.5: zonder kraanschakelaars geeft `release_ready.py` `PASS` (niet van toepassing), en de poort ziet `PASS`.
   Tellen de kranen van de veldtester mee, of koop je zelf kranen voor de drie radiatoren? Het criterium meet alleen de Home
   Assistant van `--ha-url`.
7. Akkoord met T12 vóór T1 en T9 vóór T8 (T8 draait dan bovenop T9), in plaats van de volgorde T1–T12 van de checklist?

## Bijlage A: de kijkregel (alleen lezen)

Voor [Claude]: leest het laatste voorbeeld van de bewaking uit het bestand; er gaat niets naar de E32 en er is geen wachtwoord
voor nodig. Eerst `$D` zetten (zie §4).

```powershell
$f = Get-ChildItem "out/switchover-$D/samples-*.jsonl" | Sort-Object Name | Select-Object -Last 1
$s = Get-Content $f -Tail 1 | ConvertFrom-Json
'{0}  {1}  vraag {2} ({3})  gekozen {4}  aanvoer {5}  retour {6}  mod {7}  CV {8}  tap {9}  code {10}' -f $s.at_utc, $s.guard.state, $s.guard.command.flow_c, $s.guard.command.why, $s.boiler.selected_flow_c, $s.boiler.flow_c, $s.boiler.return_c, $s.boiler.modulation_pct, $s.boiler.heating_active, $s.boiler.dhw_active, $s.boiler.display_code
'waarschuwingen [{0}]  vreemde 0x1A {1}  frames {2}  boot {3}  uptime {4} s  bevestiging bewaard {5}  HA-leeftijd {6} s' -f ($s.guard.warnings -join ','), $s.guard.foreign_controller.age_s, $s.transport.transmitted_frames, $s.e32.boot_id, $s.e32.uptime_s, $s.guard.confirmation_stored, $s.ha.input_age_s
$s.rooms | Format-Table name, state, temperature, setpoint, status, source, setpoint_source, demand -AutoSize | Out-String -Width 200
$a = "out/switchover-$D/alarms.jsonl"; if (Test-Path $a) { Get-Content $a -Tail 3 } else { 'geen alarmen' }
```

Een regel per 30 s: de laatste kan tot een halve minuut oud zijn. Antwoordde de E32 niet (`reachable` is `false` in het
voorbeeld), dan zijn de meeste velden leeg: bij T6, T7 en T8 is dat verwacht.

## Bijlage B: de kaart bij de ketel (print dit)

> **Regeling teruggeven aan de tado (normaal, de E32-pagina werkt)**
>
> 1. Open `http://192.168.1.206` en meld je aan. Menu **Ruimtes**, blok **Actieve regeling**.
> 2. Druk op **Regeling teruggeven aan mijn thermostaat (de E32 vraagt de ketel eerst een minuut geen warmte)** en bevestig.
>    Dat werkt ook met het fabriekswachtwoord. Home Assistant heeft geen teruggeefknop.
> 3. Wacht tot er staat **"Proefperiode: je thermostaat regelt de ketel."** (hooguit ± 70 seconden). Blijft er "Stoppen…"
>    staan, ga dan naar de noodkaart.
> 4. Ketel **uit** met de hoofdschakelaar.
> 5. Sluit de twee tado-draden (label "TADO") weer aan zoals op de foto. De E32-draden blijven zitten.
> 6. Ketel **aan**.
> 7. Binnen 2 minuten: in Home Assistant heeft **Gevraagde watertemperatuur (thermostaat)** weer een waarde en op de
>    E32-pagina staat "laatste vraag van je thermostaat … geleden" (minder dan 1 minuut).
> 8. Warme kraan open: na ± 1 minuut warm water.
>
> **Nood (de pagina werkt niet, de E32 doet vreemd, of de ketel stookt ongecontroleerd)**
>
> 1. Ketel **uit** met de hoofdschakelaar (of de CV-functie op het ketelpaneel). De verwarming stopt direct.
> 2. De E32 **stroomloos**: stekker eruit, of bij busvoeding de twee E32-draden (label "E32") van de adapter en isoleren.
> 3. Sluit de tado-draden ("TADO") weer aan zoals op de foto.
> 4. Ketel **aan**. De tado regelt binnen ± 40 seconden weer.
> 5. Controleer: de warme kraan geeft warm water; waterdruk 1,1–2,5 bar; geen storingscode.
> 6. Laat de E32 uit tot de oorzaak bekend is. Zet hem later pas weer aan **terwijl de tado aangesloten is**: hij hoort de
>    tado dan en blijft stil. Druk daarna toch op de teruggeefknop.
> 7. Bevestig in Home Assistant **niets** ("Bevestig opnieuw dat de E32 de ketel mag regelen") zolang de tado aangesloten is.

## Bijlage C: vastleggen in het kort

| Wat | Commando |
| --- | --- |
| Lijst aanmaken (één keer) | `python3 -I tools/switchover/record_test.py --date $D init --firmware v1.0.0-e32v2-rc.5 --ha 1.0.0rc6` |
| Geslaagd | `… --date $D T<n> pass '<wat je zag>' --evidence '<foto of bestand>'` |
| Niet geslaagd | `… --date $D T<n> fail '<wat je zag>' --evidence '<foto of bestand>'` |
| Alleen T12: alternatief | `… --date $D T12 alternative '<reden>' --evidence '<bewijs>'` |
| Stand | `… --date $D status` |

Uitslagen: `pass`, `fail`, `alternative` (alleen T12, met `--evidence`) en `skipped`. `skipped` telt in `release_ready.py` als
niet gedaan (`WAIT`): gebruik het niet om een test over te slaan. Het bestand komt in
`docs/modern-thermostat/OVERSCHAKELING-RESULTATEN-<datum>.json`; commit het samen met het verslag.
