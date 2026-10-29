# Bijgewoonde overstap: de E32 neemt de ketel over van de tado (fase 4)

**Status:** concept van 29 oktober 2026, nog niet uitgevoerd. Dit is fase 4 van
het [plan naar volledige aansturing](NEXT-RELEASE.nl.md#plan-naar-volledige-aansturing-eigenaar-vroeg-28-oktober):
tado los, E32 actief, met de eigenaar aanwezig. Duur: één middag (~4–5 uur).
Engelse samenvatting voor GitHub: [SWITCHOVER.md](../SWITCHOVER.md).

Verwachtingen hieronder gelden voor de code van beta.18 (`ActiveHeatGuard`,
`ActiveHeatPollDriver`, `RoomEngine`, `FlowDemand`, `RoomDemand`,
`SupervisorPolicy`). Valt een besluit in §1 anders uit, dan eerst de verwachte
uitkomst in §6 bijwerken.

**Installatie:** Nefit EcomLine HRC 22H achter een Bosch EasyControl Adapter
(EMS 0x08). tado (RC10-type, 0x17) stuurt nu 0x1A elke ~40 s en 0xB1/0x35/0x33
elke ~20 s (0x33: tapwater 55 °C). Woonkamer: vloerverwarming met eigen verdeler,
pomp en thermostatische kraan (~50 °C); boven 3 radiatoren op hetzelfde circuit
zonder TRV's (worden mee warm). Woonkamerbronnen: tado via HA, daarna Xiaomi pvvx
(Bluetooth). Badkamer inactief. Vorst aan < 8 °C, uit ≥ 9 °C. Na meetverlies
automatisch hervatten. Overname alleen na bevestiging door de eigenaar.

---

## 1. Beslissen vóór de overstap

De eerste drie staan al open in [NEXT-RELEASE](NEXT-RELEASE.nl.md); 4–7 volgen
uit het nalopen van de code voor deze procedure.

| # | Onderwerp | Nu (beta.18) | Gevolg tijdens/na de overstap | Opties (voorstel vet) |
| --- | --- | --- | --- | --- |
| B1 | **Ketelgrens 0x16 na herstart** — *beslissen vóór de overstap* | `ActiveHeatEnvelope::limitC` kent de grens alleen als 0x16 **deze boot** is gemeld; tot nu vroeg alleen de tado erom. | Na loskoppelen van de tado vraagt niemand nog 0x16. Elke E32-herstart (ook door de ketel uit/aan bij busvoeding) → `boiler_limit_unknown`, cap 0, **geen warmte en geen vorstbeveiliging**. Workaround: Mijn ketel → "1. Ketelinstellingen ophalen". | **E32 leest 0x16 zelf (read-only) bij opstart en elke ~6 h**; of laatst gemelde waarde in NVS accepteren (risico: instelling aan de ketel gewijzigd); of handmatig na elke herstart (niet onbewaakt bruikbaar). |
| B2 | **Bevestiging "tado los" over herstart** — *beslissen vóór de overstap* | Alleen in RAM. | Na elke herstart `awaiting_confirmation`: de E32 stuurt **niets** (ook geen nul) tot de eigenaar opnieuw bevestigt; geen vorstbeveiliging. Wat de ketel dan doet hangt af van de adapter (T5). | **Bewaren in NVS; wissen bij vreemde 0x1A, bij teruggeven en bij firmwarewissel; na herstart pas na 120 s luisteren zonder vreemde 0x1A hervatten. HA meldt `awaiting_confirmation` altijd.** Of RAM houden en HA laten melden. |
| B3 | **Brandermelding telt tapwater mee** — *beslissen vóór de overstap* | `burnerOn` = modulatie > 0; tapwater (0x18 DHW-bit) telt dus als "ketel reageert". | Tapt iemand net bij de start, dan kan een niet-reagerende CV-vraag onopgemerkt blijven (alleen waarschuwing, geen stop). | **Alleen het CV-actief-bit tellen of perioden met DHW-bit overslaan**; of zo laten (alleen waarschuwing). |
| B4 | Supervisorherstarts tijdens actieve regeling — *beslissen vóór de overstap* | `SupervisorPolicy` herstart bij wifi weg 15 min (`wifi_lost`, verdubbelt), broker weg 15 min (`broker_lost`), wifi verbonden maar geen IP-verkeer 3 min (`network_dead`), geen advert van gekoppelde BT-sensoren 30 min (`bluetooth_silent`). `restartDeferred` geldt alleen voor proef/instellingen. | Met B2 = RAM eindigt elke zo'n herstart de actieve regeling. T7, T8b en T9 lopen daar nu tegenaan. | **B2 bewaren (herstart kost dan ~2–3 min) én `wifi_lost`/`broker_lost`/`bluetooth_silent` overslaan zolang de E32 de ketel bezit**; `loop_stall` blijft. |
| B5 | Tado fysiek los of "niet laten regelen" — *eigenaar beslist vóór de overstap* | Elke 0x1A-write naar 0x08 van een ander adres dan 0x08/0x0B blokkeert de E32, ook met aanvoer 0. | Optie B werkt alleen als de tado dan **helemaal geen** 0x1A meer stuurt. Zie §4. | **Optie A (fysiek los)**; optie B alleen na passieve controle in schaduwmodus. |
| B6 | Gedrag EasyControl Adapter als de E32 stopt met zenden — *beslissen na meting T5, vóór fase 5* | Onbekend: vasthouden of na een timeout naar nul. | Houdt de adapter de laatste vraag vast, dan stookt de ketel na een E32-crash of -stroomuitval door op die aanvoer (≤ 60 °C) tot iemand ingrijpt. | Acceptabel als de adapter binnen ~15 min terugvalt. Houdt hij langer vast: maatregel kiezen vóór fase 5 (B2+B4 zodat herstarts snel hervatten, HA-melding bij E32 onbereikbaar, eventueel onafhankelijke onderbreking). |
| B7 | HA-meldingen voor actieve regeling — *bouwen vóór de overstap* | HA0.4.0b10 leest het `active`-blok van `/status/heating` niet; "Boiler request (E32)" is de **berekende** vraag, niet de verzonden. | Zonder HA-entiteit merkt niemand een herstart naar `awaiting_confirmation` of een waarschuwing. | Sensor "Actieve regeling" (status, verzonden aanvoer, leeftijd laatste zending) + probleemsensor per waarschuwing + melding naar de telefoon. |

---

## 2. Wat de firmware doet (naslag)

**Toestanden** (`ActiveHeatGuard::State`, pagina Ruimtes → "Actieve regeling"):

| Toestand | Pagina | Stuurt |
| --- | --- | --- |
| `shadow` | Schaduwmodus: je thermostaat regelt de ketel. | niets |
| `awaiting_confirmation` | Wacht op je bevestiging dat je thermostaat van de ketel is losgekoppeld. | niets |
| `arming` | Overnemen: wacht op verse ruimtemetingen en de ketelbus. | niets; wordt `active` zodra ≥ 120 s na boot, zendroute klaar en alle actieve ruimtes vers (of na 30 min zonder verse meting: eigenaar met nulvraag) |
| `active` | De E32 regelt de ketel. | vraag elke 60 s, direct bij aan/uit; na elke stop 60 s lang elke 10 s nul |
| `stopped_measurement_lost` | Geen ruimtemetingen: de E32 vraagt de ketel geen warmte tot er weer een meting is. | nul (vorstminimum blijft mogelijk); hervat vanzelf |
| `stopping` | Stoppen: de E32 vraagt de ketel één minuut lang nul. | nul elke 10 s, 60 s lang, daarna `shadow`/`blocked` |
| `blocked_foreign_controller` | Gestopt: een andere regelaar stuurde na de overname een ketelvraag. | niets; opnieuw bevestigen nodig |

**Waarschuwingen:** `foreign_controller` (0x1A van een ander adres na de
bevestiging), `measurement_lost` (een actieve ruimte zonder meting),
`boiler_no_response` (15 min warmte gevraagd zonder brander of 3 °C
aanvoerstijging), `transmit_failed` (3 min geen geslaagde zending),
`boiler_limit_unknown` (geen 0x16 deze boot → geen warmte).

**Getallen:** stap 10 s · aanvoer 30–60 °C en ≤ min(plan, 60, ketelgrens) ·
P 10 °C per °C tekort, I +10 °C per °C·30 min · hysterese 0,2 °C · minimaal
brander aan 5 min en uit 5 min (alleen bij een normale stop; meetverlies stopt
direct) · Bluetooth/HA-meting 15 min geldig, daarna "Laatste waarde (bron weg)",
na 30 min "Geen meting: geen warmtevraag" · HA-setpoint 15 min geldig, daarna
weekprogramma (met klok), anders "temperatuur zonder HA" · vorst op de koudste
verse meting van **alle** ruimtes, ook inactieve · de E32 zendt als 0x0B, alleen
wanneer de ketel 0x0B pollt.

---

## 3. Voorwaarden (alles afvinken)

**Bewijs en software**
- [ ] Schaduwfase klaar volgens de [vier criteria](NEXT-RELEASE.nl.md#plan-naar-volledige-aansturing-eigenaar-vroeg-28-oktober)
      (≥ 72 h zonder hang/herstart, ≥ 10 vergeleken periodes incl. nacht/ochtend/zonder vraag,
      beslissingen ongeveer gelijk, Xiaomi heeft minstens één keer overgenomen).
- [ ] B1–B5 en B7 besloten en gebouwd; hosttests groen (`test_active_heat_guard`, `test_active_heat_poll`).
- [ ] Firmware met `board::emsActiveHeatAllowed = true` volgens de releaseafspraken
      gepubliceerd en geïnstalleerd, met bijpassende HA-versie; ≥ 24 h stabiel in schaduwmodus op die build.
- [ ] Pagina Ruimtes → Actieve regeling toont **niet** "Actieve regeling is in deze firmware niet ingeschakeld."
- [ ] HA-meldingen (B7) getest: een geforceerde `awaiting_confirmation` (E32 herstarten in schaduw/actief) komt op de telefoon.

**Ruimteplan**
- [ ] Woonkamer actief; bronnen 1. tado-klimaatentiteit (HA), 2. Xiaomi pvvx; gewenste temperatuur van de tado-entiteit.
- [ ] Weekprogramma op de E32 gelijk aan het tado-schema; "temperatuur zonder HA" ingesteld (bijv. 19 °C).
- [ ] Badkamer inactief. Aanvoergrenzen 30/60 °C (voorstel: het eerste uur max. 50 °C, het niveau van de eerdere proeven).
- [ ] Klok vertrouwd (NTP) — nodig voor het weekprogramma.

**Back-ups en terugval klaar**
- [ ] Volledige HA-back-up; `GET /config/heating` (plan + revisie) opgeslagen; Bluetoothkoppeling (adres, profiel) genoteerd.
- [ ] ZIP van de huidige schaduwfirmware klaar voor de lokale upload.
- [ ] Foto's van de bedrading op de EasyControl Adapter (welke draden zijn van de tado, welke van de E32).
- [ ] Bekend hoe de E32 gevoed wordt (EMS-bus of eigen voeding): bepaalt of "ketel uit" de E32 herstart.

**Ketel en mensen**
- [ ] Waterdruk 1,1–2,5 bar (foto van de manometer); geen actuele storing (laatste vergrendelende/blokkerende storing genoteerd).
- [ ] Eigenaar aanwezig bij de ketel, met telefoon/laptop op de pagina Ruimtes en HA; bij voorkeur een tweede persoon aan de laptop.
- [ ] Onafhankelijke stop bekend: CV-functie op het ketelpaneel of hoofdschakelaar.
- [ ] Middag met warmtevraag (buiten < ~12 °C); huisgenoten weten dat tapwater getest wordt.
- [ ] HA-automatiseringen die de tado of het plan wijzigen uit; geen firmware-update tijdens de overstap.
- [ ] Opname klaar (§8): map `out/switchover-<datum>/`, poll-script, stopwatch.

---

## 4. De tado loskoppelen (eigenaar beslist, B5)

De tado blijft in beide opties in HA als meet- en instelpunt (via de tado-bridge
en batterijen; controleer dat). Hij moet alleen ophouden de ketel te sturen.

**Optie A — fysiek los (voorstel).**
1. Wacht tot de tado geen warmte vraagt: HA "Requested flow temperature (thermostat)" = 0
   (zet de tado zo nodig even lager). Zo begint de adapter in een bekende toestand.
2. Ketel uit met de hoofdschakelaar (laagspanningsbus, maar geen kortsluiting riskeren).
   Bij busvoeding gaat de E32 mee uit.
3. Maak alleen het draadpaar van de tado los van de adapter, isoleer de uiteinden
   (lasklem), label ze en fotografeer. Draden van de E32 blijven zitten.
4. Ketel aan. Noteer de tijd.

**Optie B — tado laten staan maar niet laten regelen** (bijv. zone "Uit" in de
tado-app). Werkt met de huidige firmware **alleen** als de tado dan geen enkele
0x1A meer naar 0x08 stuurt; de E32 blokkeert ook op een 0x1A met aanvoer 0.
Vooraf in schaduwmodus controleren: tado op "Uit", 15 min wachten, de regel
"laatste vraag van een andere regelaar (0x17)" moet blijven oplopen en HA
"Requested flow temperature (thermostat)" onbeschikbaar worden. Nadelen: de tado
houdt zijn eigen vorstbeveiliging en blijft 0x33 (tapwater) sturen; het
setpoint in HA is in "Uit" leeg, dus de E32 volgt het weekprogramma.

**Na het loskoppelen (beide opties) — T0, 10–15 min, E32 nog in schaduwmodus:**
- [ ] Keteltelemetrie blijft binnenkomen (Mijn ketel / HA: aanvoer, "Heating active", modulatie).
      Kwam die alleen op vragen van de tado, dan **afbreken**: de E32 ziet dan geen terugmelding.
- [ ] De ketel blijft zonder regelaar in rust (geen CV, geen brander). Gaat de adapter zelf stoken: noteren, afbreken.
- [ ] Tapwater zonder 0x33 van de tado: kraan 1 min open → "Hot water active", temperatuur ~55 °C. Anders noteren (tapwater-instelling ligt dan bij de ketel/adapter).
- [ ] "Requested flow temperature (thermostat)" en "Room temperature (thermostat)" worden binnen ~3 min onbeschikbaar (verwacht, geen fout).
- [ ] Tado in HA: temperatuur en setpoint blijven actueel; tado-app eventueel met melding over de ketelverbinding (noteren).

---

## 5. Overname stap voor stap

| # | Doen | Verwacht op de E32 (Ruimtes → Actieve regeling) | Verwacht in HA | Uiterlijk |
| --- | --- | --- | --- | --- |
| 1 | E32 is ≥ 2 min opgestart (bootwachttijd 120 s). | Schaduwmodus. Woonkamer "Gemeten", leidende bron de tado-entiteit. | Room status "ok"; heat request met `mode: shadow`. | — |
| 2 | Is de E32 herstart sinds de tado los is (ketel uit/aan bij busvoeding)? Dan Mijn ketel → "1. Ketelinstellingen ophalen" (B1-workaround). | Leesresultaat toont de CV-instelling en grens. | — | 1 min |
| 3 | Knop "Mijn thermostaat is losgekoppeld van de ketel — laat de E32 overnemen" → dialoog bevestigen. | Melding "Bevestigd. De E32 neemt de ketel binnen een minuut over." Plan gaat naar `active`; kort `awaiting_confirmation`/`arming`. | heat request `mode: active`. | 10 s |
| 4 | Wachten. | "De E32 regelt de ketel. · Ketelvraag: NN °C (of uit) · laatst verzonden < 60 s geleden". Waarschuwingenlijst leeg. | B7-sensor: `active`, verzonden aanvoer. | 1 min |
| 5 | Controleren. | "laatste vraag van een andere regelaar (0x17)" blijft ouder worden; knop "Teruggeven aan de thermostaat" zichtbaar. | Geen melding. | 2 min |

Fout in stap 4: `boiler_limit_unknown` → stap 2; `transmit_failed` na 3 min →
afbreken (§7); blijft `arming` → ruimtebron niet vers (pagina: status van de
woonkamer); `blocked_foreign_controller` → de tado stuurt nog (§4), niet opnieuw
bevestigen voor dat is opgelost.

---

## 6. Testmatrix

Volgorde (voorstel): T1 → T3 → T4 → T2 → T12a → T8 → T9 → T7 → T11 → T5 → T6 →
T10 → T12b. Per test: tijden noteren, screenshot van Actieve regeling, snapshot
van `/status/heating`.

### T1 Start
- **Doen:** gewenste temperatuur woonkamer (in de tado/HA) ~1 °C boven de gemeten temperatuur.
- **Verwacht:** binnen één stap (10 s) "Verwarmen" en ketelvraag ~40 °C (30 + 10 × 1 °C), direct verzonden.
- **Geslaagd:** "Heating active" binnen 2 min (tot ~10 min als de eigen pendelblokkering van de ketel loopt — noteren);
  aanvoer stijgt ≥ 3 °C binnen 15 min en nadert de vraag; geen `boiler_no_response`.
- **Waarnemen:** pagina (ketelvraag, laatst verzonden), HA "Flow temperature", "Heating active", "Burner modulation", ketelsdisplay.

### T2 Stop en minimale pauze
- **Doen:** gewenste temperatuur ≥ 0,5 °C onder de gemeten temperatuur.
- **Verwacht:** was de brander < 5 min aan: eerst "Minimale brandertijd", daarna "Warm genoeg"; ketelvraag uit; 60 s lang elke 10 s nul.
  Direct daarna weer omhoog: "Minimale pauze" tot 5 min na de stop.
- **Geslaagd:** "Heating active" uit binnen ~30 s na de eerste nul (16 okt: 12 s); geen nieuwe start binnen 5 min; geen waarschuwing.
- **Waarnemen:** tijdstip eerste nul (pagina/log), HA "Heating active", "Burner starts last hour".

### T3 Modulatie
- **Doen:** setpoint achtereenvolgens +1 °C, +2 °C, +3 °C boven de meting (elk ~10 min); eventueel maximum in het plan tijdelijk op 45 °C.
- **Verwacht:** vraag ~40 → ~50 → 60 °C (I-deel loopt langzaam op), nooit boven het planmaximum, 60 °C of de ketelgrens.
- **Geslaagd:** gemeten aanvoer volgt binnen ±3 °C binnen ~10 min; CV blijft onafgebroken actief over de 60-s-verversingen
  (dus de adapter accepteert 60 s); bij planmaximum 45 vraag ≤ 45.
- **Waarnemen:** HA-grafiek "Boiler request (E32)" (B7-sensor: verzonden) naast "Flow temperature" en "Selected flow temperature".

### T4 Tapwater tijdens verwarmen
- **Doen:** tijdens T3 een warme kraan 3 min open, dan dicht.
- **Verwacht:** "Hot water active" aan, CV pauzeert (voorrang), aanvoer kan ~75 °C melden (warmtewisselaar, niet het CV-circuit);
  de E32 blijft dezelfde vraag elke 60 s sturen; geen stop, geen waarschuwing (B3).
- **Geslaagd:** CV weer actief binnen 5 min na het dichtdraaien, aanvoer terug naar de vraag; tapwatertemperatuur ok.
- **Waarnemen:** HA "Hot water active", "Heating active", "Flow temperature"; ketelsdisplay.

### T12a Terugzetknop (zonder de tado aan te sluiten)
- **Doen:** tijdens verwarmen "Teruggeven aan de thermostaat".
- **Verwacht:** "Teruggegeven. De E32 vraagt de ketel één minuut lang nul…"; `stopping` 60 s, daarna Schaduwmodus.
- **Geslaagd:** CV uit binnen ~30 s; daarna stuurt de E32 niets meer. Daarna opnieuw overnemen (§5 stap 3–5).

### T8 Home Assistant weg (HA Core stoppen, broker blijft draaien)
- **Doen:** HA Core stoppen (bij HA OS blijft de Mosquitto-add-on draaien). Laat T1-achtige vraag lopen.
- **Verwacht:** na ≤ 15 min woonkamer "Terugvalbron" (Xiaomi leidt) en "Gewenste temperatuur uit het weekprogramma"; regeling loopt door.
- **Geslaagd:** geen stop, geen herstart, ketelvraag blijft logisch; na HA-start binnen 5 min weer tado-bron en HA-setpoint.
- **T8b broker weg:** met de huidige code herstart de E32 na 15 min (`broker_lost`) en wacht dan op bevestiging (B2/B4).
  Alleen testen na B4, of bewust om die herstart vast te leggen.

### T9 Bluetooth-sensor weg (aansluitend op T8, HA nog uit, of tado-integratie in HA uitgeschakeld)
- **Doen:** batterij uit de Xiaomi op t0 (noteren).
- **Verwacht:** t0+15 min "Laatste waarde (bron weg)" (stookt door op de laatste waarde); t0+30 min "Geen meting: geen warmtevraag",
  ketelvraag direct nul (geen minimale brandertijd), `stopped_measurement_lost`, waarschuwing "Ruimtemetingen ontbreken."
  **Let op:** rond t0+30 min herstart de huidige code ook (`bluetooth_silent`, als dit de enige gekoppelde BT-sensor is) → daarna `awaiting_confirmation` (B4).
- **Geslaagd:** CV uit binnen ~1 min na t0+30; waarschuwing op de pagina en in HA (zodra HA draait).
  Batterij terug → binnen ~2 min weer "Gemeten"/"Terugvalbron" en automatisch `active` (na de minimale pauze), zonder nieuwe bevestiging (tenzij herstart).
- **Waarnemen:** pagina-status van de woonkamer met tijden; daarna `/status/logs` (`previous_boot`) als er herstart is.

### T7 Wifi weg (10 min)
- **Doen:** het accesspoint (of alleen het SSID van de E32) uit; **niet** alleen verkeer blokkeren (dan `network_dead` na 3 min). 10 min, dus onder de 15 min van `wifi_lost`.
- **Verwacht:** de E32 regelt door op de Xiaomi en het weekprogramma; pagina en HA zijn onbereikbaar.
- **Geslaagd:** na terugkeer geen herstart (uptime loopt door, zwarte doos leeg), toestand `active`, geen gat in de regeling op de ketelsdisplay.
- **Waarnemen:** ketelsdisplay en aanvoerleiding tijdens de test; daarna `/status/logs` en HA-geschiedenis.
  Langer dan 15 min geeft met de huidige code een herstart (B4).

### T11 Vorstbeveiliging (simulatie)
- **Doen:** woonkamer warm genoeg (geen vraag). Tijdelijk een Bluetooth-sensor als enige bron van de **inactieve** badkamer
  (Xiaomi of tweede sensor) en die koud leggen: buiten als het < 8 °C is, of in een koeltas met koelelementen
  (niet in de koelkast: Bluetooth komt daar slecht door). In een zakje tegen condens.
- **Verwacht:** zodra de verse meting < 8 °C is: ketelvraag = minimumaanvoer (30 °C), reden `frost_minimum`; ≥ 9 °C weer uit.
- **Geslaagd:** beide omslagen binnen één stap na de meting; badkamer zelf blijft inactief. Plan daarna terugzetten.
- **Alternatief** als het niet koud genoeg wordt: hosttest `test_active_heat_guard` als bewijs, ter plaatse alleen vastleggen dat het niet gelukt is.

### T5 E32-herstart en gedrag van de EasyControl Adapter (meting)
- **Doen:** bij een matige positieve vraag (~40 °C, CV actief) Systeem → "Apparaat herstarten". t0 = laatste positieve zending.
- **Verwacht (B2 = RAM):** na ~30 s terug in `awaiting_confirmation`; de E32 **stuurt niets** maar leest de bus. Na opnieuw
  bevestigen (B1: eerst "Ketelinstellingen ophalen") `arming` → `active` ≥ 120 s na boot.
- **Meten:** hoe lang blijft "Heating active"/modulatie/"Selected flow temperature" zonder zender staan? Maximaal 30 min wachten.
  Uitkomst: *vasthouden* (> 30 min), *timeout naar nul na X min*, of iets anders. Dit is de invoer voor B6.
- **Geslaagd:** uitkomst gemeten en getimed; E32 neemt daarna weer over; zwarte doos toont de handmatige herstart.

### T6 E32 stroomloos
- **Doen:** voeding van de E32 eraf (bij busvoeding: de busdraden van de E32 los). Stopwatch.
- **Verwacht:** de ketel gedraagt zich als in T5 (zelfde adaptergedrag), nu zonder E32-telemetrie.
- **Geslaagd:** gedrag en tijd komen overeen met T5. Waarnemen op de ketelsdisplay (bij Nefit doorgaans `-H` = CV, `=H` = tapwater,
  `0H` = rust; in de ketelhandleiding controleren), aanvoerleiding (hand/IR-thermometer), branderlawaai.
  Daarna E32 weer aan, als T5 opnieuw overnemen.

### T10 Vreemde regelaar (de tado weer aansluiten terwijl de E32 actief is)
- **Doen:** tado-draadpaar terug op de adapter. Kan dat alleen met de ketel uit **en** wordt de E32 uit de bus gevoed, dan herstart
  de E32 en test dit de bewaking niet: kies dan de variant hieronder.
- **Verwacht:** binnen ~40 s na de eerste 0x1A van 0x17: `stopping` (60 s nul, kort samen met de tado), dan
  `blocked_foreign_controller`, waarschuwing "Een andere regelaar (je thermostaat?) stuurt nog ketelvragen…",
  "laatste vraag van een andere regelaar (0x17) … geleden" < 1 min.
- **Variant na herstart:** tado aangesloten, E32 in `awaiting_confirmation`, toch bevestigen → zelfde uitkomst binnen ~1 min.
- **Geslaagd:** de E32 stopt en waarschuwt zelf, zonder dat iemand de knop gebruikt; de tado regelt daarna.

### T12b Teruggeven aan de tado (einde)
- **Doen:** "Teruggeven aan de thermostaat" (plan naar schaduw). Na T10 is de tado al aangesloten; anders eerst
  wachten tot "Schaduwmodus" en dan de tado aansluiten (§4 in omgekeerde volgorde).
- **Geslaagd:** pagina "Schaduwmodus: je thermostaat regelt de ketel."; HA "Requested flow temperature (thermostat)" weer actueel binnen ~1 min;
  tapwater 55 °C (0x33 van de tado terug); schaduwvergelijking telt weer; geen waarschuwing.
  Wil de eigenaar door naar fase 5, dan in plaats hiervan de tado los laten en opnieuw overnemen.

---

## 7. Afbreken en direct terugdraaien

**Afbreken bij:**
- aanvoer > 62 °C terwijl CV (niet tapwater) actief is, of een verzonden vraag boven het planmaximum/60 °C;
- waterdruk < 1,0 of > 2,7 bar, of een nieuwe vergrendelende/blokkerende ketelstoring;
- "Burner short cycling" aan, of meer starts per uur dan de tado in de schaduwweek;
- `transmit_failed` of `boiler_no_response` zonder verklaring; `foreign_controller` terwijl de tado los is;
- de adapter stookt zonder vraag (T0) of keteltelemetrie valt weg;
- E32 > 2 min onbereikbaar tijdens actief (niet in T7), of ruimte > 1,5 °C boven setpoint terwijl de E32 nog warmte vraagt;
- tapwater werkt niet, lawaai, geur, of de eigenaar twijfelt.

**Direct terugdraaien, in deze volgorde:**
1. **Knop "Teruggeven aan de thermostaat"** → wachten op "Schaduwmodus" (≤ 70 s) → tado aansluiten.
2. Pagina onbereikbaar of de E32 gedraagt zich vreemd: **E32 stroomloos** (voeding of busdraden los) → tado aansluiten.
   De tado regelt weer binnen ~40 s (eerste 0x1A).
3. Ketel blijft ongecontroleerd stoken: **CV uit op het ketelpaneel of hoofdschakelaar**, dan stap 2.
4. Vermoeden van een firmwarefout: schaduwfirmware via de lokale upload terugzetten; plan op `shadow`.

Na terugdraaien controleren: tado-0x1A komt binnen (HA "Requested flow temperature (thermostat)"),
tapwater 55 °C, druk, geen storing. Oorzaak vastleggen vóór een nieuwe poging.

---

## 8. Vastleggen

- **Per stap/test:** lokale tijd en UTC, toestand en waarschuwingen (screenshot Actieve regeling), ketelsdisplay (foto), uitkomst geslaagd/niet.
- **Doorlopend:** poll-script dat `/status/heating` en `/status/boiler` elke 10 s met tijdstempel wegschrijft (met de inlogsessie)
  naar `out/switchover-<datum>/` (valt onder bewaarde logs, niet onder opruimen); stopwatch-tijden voor T2, T5, T6, T9.
- **Na elke herstart:** `/status/logs` → `previous_boot` (zwarte doos, herstartreden) bewaren.
- **HA:** geschiedenis-export van de entiteiten uit §9 over de hele middag; HA-back-up van vóór en na.
- **Bedrading:** foto's vóór, tijdens en na.
- **Verslag:** `docs/modern-thermostat/SWITCHOVER-<datum>.json` in de vorm van `BETA12-ATTENDED-HEAT-20261027.json`
  (firmware, aanwezigen, druk, per test tijden/uitkomst, adaptergedrag T5/T6 met gemeten tijd, oordeel eigenaar, vervolgpunten),
  plus een regel in NEXT-RELEASE.

---

## 9. Daarna: 1–2 weken monitoren (fase 5)

Alleen als de eigenaar na T12 de E32 actief laat, B6 besloten is en de
HA-meldingen (B7) werken.

**Dagelijks (~5 min):**
- [ ] Actieve regeling `active`, geen waarschuwingen; HA-meldingen van het afgelopen etmaal nagelopen.
- [ ] Geen herstart (uptime, zwarte doos); zo wel: reden, en of de E32 zelf hervatte (B2/B4).
- [ ] Woonkamer: afwijking van het setpoint (< 0,5 °C normaal, overschot < 1 °C), ochtendopwarming op tijd.
- [ ] Ketel: starts per uur (≤ tado-niveau uit de schaduwweek), "Burner short cycling" uit, aanvoer 30–60 °C, druk 1,1–2,5 bar, geen storing.
- [ ] Tapwater werkt; gas per dag (`sensor.gas_consumed`) vergeleken met vergelijkbare dagen (buitentemperatuur).
- [ ] Badkamer en slaapkamers niet te koud/warm (radiatoren lopen mee).

**HA-grafieken (dashboard "Verwarming"):** woonkamer Temperature + Target temperature;
Boiler request (E32) / verzonden aanvoer (B7) + Flow temperature + Return temperature;
Heating active + Hot water active + Burner modulation; Burner starts last hour + Burner short cycling;
Water pressure; Outdoor temperature; gasverbruik per dag.

**Wekelijks:** verwarmingstijd en starts per dag naast de schaduwweek; parameters
(startpunt, aanvoer per graad, trage correctie) alleen bijstellen met een
genoteerde reden.

**Terug naar de tado** (§7) bij een afbreekcriterium of als de eigenaar het
comfort onvoldoende vindt. **Door naar de eerste echte release (fase 6)** na
≥ 7 aaneengesloten dagen zonder ingreep, geen onverklaarde waarschuwing en
geen comfortklacht.
