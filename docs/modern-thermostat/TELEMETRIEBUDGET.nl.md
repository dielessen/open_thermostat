# Telemetriebudget E32 ↔ Home Assistant — ontwerp (beta.19)

Status: **goedgekeurd door de eigenaar** (29 oktober 2026): "Bij verandering, rustig", "Ja, samen installeren", "Na ~3 minuten stilte".
Aanleiding (eigenaar): "we zullen echt moeten nadenken hoe we dat realistisch
gaan inrichten zodat het werkbaar blijft en dat de performance goed blijft. We
werken uiteindelijk met dat E32 ESP-board." en "we hoeven niet iedere seconde
een update te hebben".

## 1. Wat we zagen

Op de E32 van de eigenaar (beta.18, 17 minuten na de update):
`mqtt_budget_disconnects = 4`, laagste vrije interne geheugen 13 280 B. Elke
verbreking maakt de HA-entiteiten kort "niet beschikbaar".

Wat de E32 nu verstuurt (uit de broncode):

| Bericht | Hoe vaak | Grootte | Per uur |
| --- | --- | --- | --- |
| `fw/telemetry/boiler_fields` (één groep per keer, rondgaand) | elke 1,8 s | tot 2 KB | ~4 MB |
| `fw/telemetry/heating` (alle ruimtes + `ha_entities`) | elke 15 s | 3,8 KB normaal, tot 7,9 KB | ~1–1,9 MB |
| `fw/telemetry/heating_learned/<ruimte>` (2 per keer) | elke 15 s | tot 0,9 KB elk | ~0,4 MB |
| `fw/telemetry/heating_summary` | elke 15 s | ~0,4 KB | ~0,1 MB |
| `fw/telemetry/device_status`, `controller_request` | elke 15 s | klein | <0,1 MB |
| `fw/telemetry/ems_metrics` | elke 30 s | tot 2 KB | ~0,2 MB |

Samen gemiddeld ~1,7 KB/s, zonder pauze. Erger nog: elke 15 s gaan 5–6
berichten (6–10 KB) **direct achter elkaar** de deur uit, terwijl de
TCP-zendbuffer van de ESP32 ~5,7 KB is. Het tweede of derde bericht moet dan
wachten op bevestigingen van de broker; wifi deelt de radio met Bluetooth, dus
dat duurt soms langer dan de 300 ms die een bericht mag kosten → verbreken.

## 2. Uitgangspunten

1. **Regelen gaat voor.** Meten, beslissen en (later) de ketel aansturen
   wachten nooit op netwerkverkeer. Telemetrie naar HA is *best effort*.
2. **Kleine berichten.** Geen bericht groter dan **1 KB** (harde grens 1,5 KB);
   dan past elk bericht in één keer in de zendbuffer.
3. **Versturen naar betekenis, niet naar de klok.** Alleen wat veranderd is,
   met een drempel; daarnaast een rustige "ik leef nog".
4. **Spreiden.** Nooit meer dan één groot bericht per lusronde; berichten
   worden over de tijd verdeeld, niet in een salvo.
5. **Begrensd geheugen.** Vaste buffers bij het opstarten, niets per bericht
   aanvragen; doel **≥ 20 KB** intern geheugen altijd vrij.
6. **Meetbaar.** De E32 rapporteert zelf zijn verkeer en haperingen.

## 3. Budget

| | Nu | Doel |
| --- | --- | --- |
| Gemiddeld verkeer E32 → HA | ~1,7 KB/s | **≤ 0,25 KB/s** (~0,9 MB/uur) |
| Grootste bericht | 7,9 KB | **≤ 1 KB** (hard 1,5 KB) |
| Berichten in één salvo | 5–6 | **1**, daarna ≥ 50 ms rust |
| Onterechte verbrekingen | ~14 per uur | **0 in 24 uur** |
| Laagste vrije interne geheugen | 13 KB | **≥ 20 KB** |
| Tijd van een waarde tot HA bij een echte verandering | ≤ 15 s | **≤ 5 s** (belangrijk) / ≤ 30 s (overig) |

## 4. Berichten in de nieuwe opzet

| Bericht | Inhoud | Wanneer | Retained |
| --- | --- | --- | --- |
| `fw/state/room/<id>` | temperatuur, doel, warmtevraag, toestand, bron, leeftijd meting | bij verandering (≥ 0,1 °C, ander doel/toestand/bron), hoogstens elke 10 s; anders elke 5 min | ja |
| `fw/state/heating` | ketelvraag (aanvoer), modus, bewaking, redenen | bij verandering (≥ 1 °C of andere toestand), hoogstens elke 10 s; anders elke 5 min | ja |
| `fw/state/boiler` | aanvoer, retour, modulatie, druk, brander, tapwater, storing | bij verandering (aanvoer/retour ≥ 0,5 °C, modulatie ≥ 5 %, brander/tapwater/storing direct), hoogstens elke 10 s; anders elke 5 min | ja |
| `fw/state/boiler_fields/<groep>` | overige ketelvelden (de huidige catalogus) | per groep bij verandering, hoogstens elke 60 s per groep; anders elke 15 min | ja |
| `fw/telemetry/learned/<id>` | wat per ruimte geleerd is, advies | elke 15 min of bij nieuw resultaat | ja |
| `fw/telemetry/summary` | dagtotalen, tapwater vandaag, schaduwvergelijking | elke 5 min | ja |
| `fw/config/plan` + `fw/config/entities` | ruimteplan, lijst entiteiten (nu `ha_entities` in elk statusbericht) | alleen bij wijziging en bij verbinden | ja |
| `fw/telemetry/ems_metrics` | ontvangststatistiek | elke 5 min | nee |
| `fw/availability` | online / offline (LWT) | bij verbinden / verbreken | ja |
| `fw/heartbeat` | uptime, vrij geheugen, verkeerstellers | elke 60 s | nee |

Bij het opnieuw verbinden stuurt de E32 alles één keer (gespreid), zodat HA
meteen compleet is; door `retained` ziet een herstarte HA de laatste waarden
direct.

Geschatte belasting met 3 ruimtes: ~0,1–0,2 KB/s bij normaal verwarmen,
minder als alles stil staat.

## 5. Verzenden

- **Eén uitgaande wachtrij in PSRAM** (vast, bijvoorbeeld 16 KB) met
  **samenvoegen per onderwerp**: staat er voor hetzelfde onderwerp nog een
  oudere waarde in de rij, dan vervangt de nieuwe die. De rij kan dus niet
  onbeperkt groeien; hoogstens één bericht per onderwerp wacht.
- **Rustig leegmaken**: elke lusronde hoogstens één bericht (of enkele ms),
  niet-blokkerend. Belangrijke berichten (ruimte, ketelvraag, ketel) gaan voor
  op langzame (geleerd, metingen).
- **Verbreken alleen bij echte stilstand**: komt er 15 s geen enkele byte weg,
  of geeft de verbinding een fout. Dan opnieuw verbinden met oplopende
  wachttijd (bestaat al).
- De bijzondere schrijfroute met deadline (voor de ketelbediening) blijft
  gescheiden en ongewijzigd; de wachtrij wordt eerst leeggemaakt.

## 6. Home Assistant

- HA abonneert op de nieuwe onderwerpen; een waarde is pas "niet beschikbaar"
  als `fw/availability` offline meldt of na **3 gemiste heartbeats (~3 min)**,
  niet na 60 s zoals nu.
- Bij verbinden of herstart van HA komen de laatste waarden direct uit de
  retained berichten.
- HA 0.4.0b10 begrijpt de nieuwe onderwerpen niet. Beta.19 en HA 0.4.0b11
  horen dus samen (zoals bij elke release); in de release notes staat dat
  duidelijk. Om flash te sparen stuurt beta.19 de oude grote berichten niet
  meer mee.

## 7. Geheugen en processor

- Alle buffers één keer bij het opstarten (wachtrij in PSRAM, JSON-opbouw in
  PSRAM via de bestaande cJSON-haken); kleine berichten houden de interne
  heap rustig.
- Bluetooth-scannen en wifi delen de radio: het scanvenster blijft zoals nu,
  maar het verzenden wordt gespreid zodat er geen salvo's meer botsen.
- Doel processortijd voor telemetrie: < 2 % (nu niet gemeten; wordt gemeten).

## 8. Meten en bewijzen

De E32 rapporteert in `/status/logs` en de heartbeat: berichten en bytes per
minuut, grootste wachtrij, verzendtijd (gemiddeld en slechtste), verbrekingen
met reden, laagste vrije geheugen.

- **Duurtest** (test/soak): scenario's met trage wifi (300–2000 ms per
  bevestiging), korte uitval, brokerherstart; eis: geen verbreking door
  traagheid, geen groei van de wachtrij boven de grens, waarden komen binnen de
  doeltijd.
- **Op de E32 van de eigenaar**: 24 uur met het bewakingsscript; eis 0
  onterechte verbrekingen, ≥ 20 KB vrij geheugen, verkeer binnen het budget.

## 9. Besluiten eigenaar (29 oktober 2026)

1. **Snelheid:** bij verandering, rustig — ruimtetemperatuur, ketelvraag en
   brander binnen ~5–10 s na een echte verandering (≥ 0,1 °C / ≥ 1 °C aanvoer),
   anders elke 5 min; geleerde waarden en statistiek elke 5–15 min.
2. **Samen installeren:** beta.19 en HA 0.4.0b11 horen samen; de oude grote
   berichten verdwijnen.
3. **Niet beschikbaar** in HA pas na ~3 minuten stilte (3 gemiste heartbeats)
   of als de E32 zelf offline meldt.

## 10. Sessieprotocol (beta.19 + HA 0.4.0b11)

Naast de telemetrie praat de E32 met HA via de schaduwsessie (`ShadowController`
↔ `v1_wire.py`). Gemeten met de echte C++-regelaar en de echte HA-client
(1 ruimte, 600 s): **vóór 664 B/s, na 122 B/s** van de E32 naar HA
(HA → E32: ~100 → 28 B/s).

### Waar elk bericht voor is

| Bericht | Waarvoor | Wat hangt van het ritme af | Was | Nu |
| --- | --- | --- | --- | --- |
| `fw/hello` | identiteit (boot, epoch), configuratierevisie, capabilities en de *challenge* om een sessie te openen | alleen het openen van een nieuwe sessie; een herstart van HA, de broker of de E32 | elke 3 s, 472 B | zonder sessie elke 3 s, in een sessie elke 15 s, direct na het verlies van een sessie en als antwoord op een open met een verlopen challenge; **retained** |
| `fw/session` (grant) | het grant-token dat elk HA-bericht moet dragen; de geldigheid begrenst hoe oud een binnenkomend bericht mag zijn (leeftijd + grant-leeftijd) | HA moet een nieuwe grant hebben voor de oude verloopt | elke 5 s, 10 s geldig (2 rotaties marge) | elke 10 s, 30 s geldig (**3 rotaties marge**) |
| `ha/heartbeat` → `fw/heartbeat_result` | HA leeft: verlengt de *lease* | lease bepaalt of metingen/opdrachten van HA worden aangenomen en `adapter_alive` in de zonestatus | HA elke 2 s, lease 15 s | HA elke 10 s, lease 30 s (**3 gemiste heartbeats**) |
| `fw/state/zones` | schaduwbesluiten per zone (vraag, doel, reden, meetstatus) en de hydraulische toezichtstatus | HA's schaduwthermostaten en het verifiëren van het plan | elke 3 s gepubliceerd | elke 3 s **berekend** (de regelaar stapt even vaak als vroeger), gepubliceerd bij een echte verandering (oplopende leeftijden en een aftellende override tellen niet), direct na een opdracht of snapshot-verzoek, anders elke 30 s; HA's venster 100 s |
| `*_result` | antwoord op één verzoek | – | ongewijzigd | ongewijzigd |

### Veiligheid

- **De ketel hangt niet van de sessie af.** De echte regeling
  (`RoomEngine`, `FlowPolicy`, `ActiveHeatGuard`) krijgt HA-waarden via
  `ha/heating_input` met eigen versheidsgrenzen en valt bij stilte terug op
  Bluetooth, het weekprogramma of de vaste temperatuur. Niets daarvan leest de
  lease of de grant; de schaduwuitgangen zijn uit (`physical_outputs_enabled:
  false`). Een langere lease maakt de ketel dus niet trager veilig.
- **Actuatorkanalen** (nog niet in het product) vragen per opdracht een eigen
  HA-bevestiging met een deadline van 5 s (`fw/actuator_grant_request` →
  `ha/actuator_grant`), altijd binnen de lease: dat blijft het snelle,
  kleine levensteken.
- De grant-leeftijd die bij metingen wordt opgeteld is nu hoogstens ~10 s
  (was 5 s); gangbare bronnen mogen minuten oud zijn (temperatuur 120 s,
  contacten tot 1 uur). Een zeer korte ingestelde maximale leeftijd (< ~20 s)
  geldt daardoor ~5 s eerder als verlopen: veilig, niet ruimer.

### Herstel zonder herladen

Eis voor b11: na (a) een HA-herstart, (b) een brokerherstart, (c) een
E32-herstart, (d) een verbreking aan de E32-kant en (e) een lange wifi-uitval
herstelt de sessie zelf binnen één traag interval (`test_session_recovery.py`,
echte C++ tegen echte HA):

- HA beëindigt een sessie altijd: bij het verlopen van de lease, en zolang
  er nog geen heartbeat bevestigd is bij het verlopen van de grant. Een
  `fw/hello` telt niet meer als levensteken van een lopende sessie.
- Een nieuwe challenge vervangt een openstaand open-verzoek direct (vroeger
  alleen bij de native bron, anders pas na 10 s).
- De E32 vervangt een sessie als een nieuw open-verzoek met de *huidige*
  challenge komt (een herstarte HA hoeft niet op de oude lease te wachten), en
  beantwoordt een open met een verlopen challenge met een nieuwe hello
  (hoogstens één per seconde). De hello is retained, dus een herstarte HA heeft
  de challenge meteen.

**Oorzaak van de storing op b10** (29 oktober, 5,5 uur zonder sessie na een
HA-herstart): HA hield een sessie vast waarvan nog geen heartbeat bevestigd
was (`lease_until` 0). De E32 beëindigde die sessie na 15 s zonder geldige
heartbeat en stuurde daarna elke 3 s een hello met dezelfde identiteit; HA
zette bij elke hello `last_rx` opnieuw, en een sessie zonder lease verliep
alleen op `last_rx`. Zo bleef HA eindeloos in een dode sessie hangen tot de
integratie herladen werd (`test_lost_first_heartbeats_never_leave_a_session_open_forever`
faalt op b10 en slaagt met één regel extra in `poll()`).
