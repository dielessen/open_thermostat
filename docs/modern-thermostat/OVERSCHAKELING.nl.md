# Bijgewoonde overstap: de E32 neemt de ketel over van de tado

**Status:** draaiboek voor beta.19 (kandidaat voor 1.0), bijgewerkt 29 oktober
2026, nog niet uitgevoerd. Fase 4 en 5 van het
[plan naar volledige aansturing](NEXT-RELEASE.nl.md#plan-naar-volledige-aansturing-eigenaar-vroeg-28-oktober);
onderdeel 10 van het [beta.19-plan](NEXT-RELEASE.nl.md). Engelse, algemene
versie voor GitHub: [SWITCHOVER.md](../SWITCHOVER.md). Live bewaking:
[tools/switchover](../../tools/switchover/README.md).

**Markering.** *(beta.19, op het apparaat controleren)* = gedrag dat in
beta.19 gebouwd en met host- en duurtests (`test/test_native`, `test/soak`
scenario `active`) bewezen is, maar dat alleen een echte busopname of de
overstapdag zelf kan bevestigen. Vóór de overstapdag opnieuw controleren tegen
de gepubliceerde bron; zie §11.

**Installatie (eigenaar).** Nefit EcomLine HRC 22H achter een Bosch
EasyControl Adapter (EMS 0x08). tado (RC10-type, 0x17) stuurt nu 0x1A elke
~40 s en 0xB1/0x35/0x33 elke ~20 s (0x33: tapwater 55 °C). Woonkamer:
vloerverwarming met eigen verdeler, pomp en thermostatische kraan (~50 °C,
maximaal 60 °C ingang); boven 3 radiatoren (badkamer, 2 slaapkamers) op
hetzelfde circuit zonder TRV's (worden mee warm). Woonkamerbronnen: 1. tado via
HA (`climate.*`), 2. Xiaomi pvvx (Bluetooth). Badkamer inactief. Alleen de
woonkamer is actief in beta.19. E32 op `http://192.168.1.206`.

---

## 1. Besluiten van de eigenaar (bindend)

| # | Besluit | In de firmware | Status |
| --- | --- | --- | --- |
| E1 | De tado regelt tot hij **fysiek** van de EasyControl Adapter is losgekoppeld; daarna is de E32 de enige regelaar. Geen "tado op Uit". | Elke 0x1A van een ander adres dan 0x08/0x0B na de bevestiging stopt de E32 (`foreign_controller`). | gebouwd |
| E2 | Overnemen alleen na de expliciete bevestiging van de eigenaar op de E32-pagina. | Knop "Mijn thermostaat is losgekoppeld van de ketel — laat de E32 overnemen" → `POST /config/heating` (`mode: active`) en `POST /config/heating/handover` `{"thermostat_disconnected":true}`. | gebouwd |
| E3 | De bevestiging blijft bewaard over herstarts; gewist door een vreemde 0x1A, door teruggeven of door een firmwarewissel. | NVS (`HandoverConfirmation`), gebonden aan versie + ELF-hash; `active.confirmation_stored` en `active.confirmation.restored` in `/status/heating`. Na een herstart pas warmte na 2 min busontvangst zonder vreemde 0x1A (§2). | gebouwd; native `test_handover_confirmation`, soak `reboot`, `reboot_tado_back` |
| E4 | Na meetverlies hervat de regeling vanzelf. | `stopped_measurement_lost` → `active` zodra er weer een verse meting is, zonder nieuwe bevestiging. | gebouwd; soak `measurement_gone` |
| E5 | Aanvoer dynamisch tot het planmaximum, nooit boven het eigen maximum van de ketel (0x16), zo laag mogelijk. | Plafond `min(planmaximum, 80, 0x16)`; de E32 leest 0x16 zelf bij opstart en elke 6 h (`BoilerLimitRead`); zonder grens geen positieve vraag (`boiler_limit_unknown`). | gebouwd; native `test_boiler_limit_read`, soak `boiler_limit`; busopname *(op het apparaat controleren)* |
| E6 | Vorstbeveiliging aan onder 8 °C, uit bij 9 °C. | Koudste verse meting van **alle** ruimtes (ook inactieve) → minimumaanvoer, reden `frost_minimum`. | gebouwd |
| E7 | Geen supervisorherstart zolang de E32 de ketel bezit. | `SupervisorPolicy`: `boilerOwned` → alleen `loop_stall` en `update_stuck`; geen `wifi_lost`, `broker_lost`, `network_dead`, `bluetooth_silent`. | gebouwd; native `test_supervisor`, soak `wifi_gone`, `measurement_gone` |
| E8 | De actieve vergrendeling (`board::emsActiveHeatAllowed`) gaat pas open op de overstapdag, in een aparte, expliciet goedgekeurde build. | `src/Board.h`, E32V2-tak: nu `false`. | **niet doen vóór de overstapdag** (§4.1) |

Nog open (geen blokkade, wel vóór fase 5 beslissen):
- **O1 Brandermelding telt tapwater mee.** `boiler_no_response` kijkt naar
  modulatie > 0 en ziet tapwater dus als "ketel reageert". Alleen een
  waarschuwing; blijft zo tenzij de eigenaar anders beslist.
- **O2 Gedrag van de adapter als de E32 stopt met zenden** (crash,
  stroomuitval, firmware-update, `awaiting_confirmation`): vasthouden of na een
  timeout naar nul? Wordt gemeten in T6 en T7. Houdt de adapter de laatste vraag
  langer dan ~15 min vast, dan vóór fase 5 een maatregel kiezen.
- **O3 HA-melding bij `awaiting_confirmation`** (beta.19-plan, onderdeel 2):
  nog niet in de HA-integratie. De bestaande binaire sensor
  "Verwarmingsprobleem" meldt alleen `foreign_controller`, `measurement_lost`,
  `boiler_no_response` en `transmit_failed` na 5 min. Tot de melding er is,
  dekt het bewakingsscript (§9) dit af (alarm `awaiting_confirmation`).

---

## 2. Wat de firmware doet (naslag)

**Toestanden** (`ActiveHeatGuard`, `/status/heating` → `active.state`,
pagina **Ruimtes → Actieve regeling**):

| `state` | Pagina (NL) | Zendt naar de ketel |
| --- | --- | --- |
| `shadow` | Schaduwmodus: je thermostaat regelt de ketel. | niets |
| `awaiting_confirmation` | Wacht op je bevestiging dat je thermostaat van de ketel is losgekoppeld. | niets — **ook geen vorstbeveiliging** |
| `arming` | Overnemen: wacht op verse ruimtemetingen en de ketelbus. | niets; `active` zodra ≥ 60 s na boot, zendroute klaar en alle actieve ruimtes vers (of na 30 min zonder verse meting: eigenaar met nulvraag). **Na een herstart met bewaarde bevestiging** bovendien pas na 2 min onafgebroken ontvangst van de ketel (0x08, berichten ≤ 30 s uit elkaar) zonder vreemde 0x1A: ≈ 130 s na boot; tot dan `active.confirmation.restored: true` met `listened_s`. Een vreemde 0x1A in die tijd wist de bevestiging (`blocked_foreign_controller`); ook de vorstbeveiliging wacht hierop. |
| `active` | De E32 regelt de ketel. | vraag elke 60 s, direct bij aan/uit; na elke stop 60 s lang elke 10 s nul |
| `stopped_measurement_lost` | Geen ruimtemetingen: de E32 vraagt de ketel geen warmte tot er weer een meting is. | nul (vorstminimum blijft mogelijk); hervat vanzelf |
| `stopping` | Stoppen: de E32 vraagt de ketel één minuut lang nul. | nul elke 10 s, ≥ 60 s en tot een nul is afgeleverd |
| `blocked_foreign_controller` | Gestopt: een andere regelaar stuurde na de overname een ketelvraag. | niets; bevestiging gewist |

**Waarschuwingen** (`active.warnings`, pagina onder de toestand):
`foreign_controller` ("Een andere regelaar (je thermostaat?) stuurt nog
ketelvragen…"), `measurement_lost` ("Ruimtemetingen ontbreken."),
`boiler_no_response` (15 min warmte gevraagd zonder brander of 3 °C stijging),
`transmit_failed` (3 min geen geslaagde zending), `boiler_limit_unknown`
("De ketel heeft zijn CV-temperatuurgrens niet gemeld; de E32 vraagt geen warmte.").

**Getallen:** stap 10 s · aanvoer ≥ planminimum (30 °C) en ≤ min(planmaximum,
80, 0x16) · P 10 °C per °C tekort, I +10 °C per °C·30 min · hysterese 0,2 °C ·
minimaal brander aan 5 min en uit 5 min (meetverlies stopt direct) ·
Bluetooth/HA-meting 15 min geldig ("Laatste waarde (bron weg)"), na 30 min
"Geen meting: geen warmtevraag" · HA-setpoint 15 min geldig, daarna het
weekprogramma (met klok), anders "temperatuur zonder HA" · de E32 zendt als
0x0B, alleen wanneer de ketel 0x0B pollt · 0x16-lezing: `0B 88 16 00 02`, bij
de eerste poll na boot, opnieuw als 6 h geen 0x16-melding is gezien (ook een
antwoord aan de tado telt), herhaling na 5 min zonder antwoord; zonder bekende
grens geen positieve vraag (`boiler_limit_unknown`) · bewaarde bevestiging:
NVS-record `<versie>/<ELF-hash>`; elke andere firmware (ook dezelfde versie
opnieuw gebouwd) wist hem · zolang de E32 de ketel bezit herstart de
supervisor alleen bij een vastloper (`loop_stall`, RTC-watchdog) of een
vastgelopen update.
Aanvoeropties van beta.19 (`/config/heating/flow`: stooklijn, geleerde
aanvoer) staan standaard op **advies**; `flow.source` = `rule`.

**Waar je het ziet**

| Wat | E32-pagina | REST | MQTT (`<prefix>/v1/fw/telemetry/…`, elke 15 s) | Home Assistant |
| --- | --- | --- | --- | --- |
| Toestand, vraag, laatst verzonden, waarschuwingen | Ruimtes → Actieve regeling | `GET /status/heating` → `active` | `heating` → `active` | Verwarmingsprobleem (na 5 min); geen eigen toestandsentiteit *(O3)* |
| Bevestiging bewaard | — | `active.awaiting_confirmation`, `active.confirmation` `{age_s, restored, listened_s}`, `active.confirmation_stored` | idem | — |
| Ketelgrens (0x16) | Ruimtes → aanvoergrenzen ("Je ketel staat maximaal {max} °C toe") | `active.boiler_limit` `{flow_c, age_s, reads}` (`reads`: eigen 0x16-leesverzoeken deze boot); `GET /status/ems/telemetry` → `fields.configured_heating_temperature` | `heating` → `active.boiler_limit` | — |
| Berekende vraag | Ruimtes → "Berekende ketelvraag" | `request` `{heat, flow_c, reason}` | `heating` → `request` | Ketelvraag (E32) |
| Ruimtes | Ruimtes (status, bron, gewenst) | `rooms[]` | `heating` → `rooms` | per ruimte: Temperatuur, Doeltemperatuur, Regelstatus, Warmtevraag |
| Ketel live | Ketel | `GET /status/ems/telemetry` → `fields.*` | `boiler_fields` | Aanvoertemperatuur, Retourtemperatuur, Gekozen aanvoertemperatuur, Verwarmen actief, Warm water actief, Brandermodulatie, Waterdruk |
| Starts en pendelen | — | `burner` `{starts_last_hour, heating_starts_last_hour, short_cycling}` | `heating` → `burner` | Branderstarts afgelopen uur, Brander pendelt |
| Vraag van de tado (0x1A van 0x17) | "laatste vraag van je thermostaat / een andere regelaar … geleden" | `active.foreign_controller` `{age_s, address: 23}` | `heating` → `active` | Gevraagde aanvoertemperatuur (thermostaat) |
| Herstarts, geheugen, MQTT-verbreking | Systeem → Systeemlog | `GET /status/logs` → `boot`, `previous_boot`, `runtime` (`minimum_free_internal_bytes`, `stack_minimum_bytes`, `mqtt_budget_disconnects`, `heating_telemetry_dropped`) | `device_status` | uptime |
| Zendteller | — | `/status/ems/telemetry` → `transport.transmitted_frames` | — | — |

"Op de bus" betekent in dit draaiboek: wat de ketel zelf terugmeldt
(**Gekozen aanvoertemperatuur** = `reported_selected_flow_temperature` uit 0x18
moet de verzonden vraag volgen), de zendteller, de leeftijd van de laatste
vreemde 0x1A, en het keteldisplay (Nefit doorgaans `-H` = CV, `=H` = tapwater,
`0H` = rust; controleren in de ketelhandleiding).

---

## 3. Voorwaarden (alles afvinken)

**Schaduwperiode geslaagd** (exitcriteria uit [NEXT-RELEASE](NEXT-RELEASE.nl.md#plan-naar-volledige-aansturing-eigenaar-vroeg-28-oktober), minimaal 3 dagen, liefst ~5):
- [ ] ≥ 72 uur geen hang of herstart (zwarte doos leeg, geen wifi- of Bluetooth-uitval).
- [ ] ≥ 10 verwarmingsperiodes van de tado vergeleken, inclusief nachtverlaging, ochtendopwarming en een periode zonder warmtevraag.
- [ ] Beslissingen ongeveer gelijk: warmtevraag op ongeveer dezelfde momenten (enkele minuten), aanvoer in hetzelfde gebied (±31–43 °C), niet vaker aan/uit dan de tado (pagina Ruimtes → "Vergelijking met je thermostaat").
- [ ] Bronnen werken: de tado-waarde komt via HA binnen en de Xiaomi heeft minstens één keer overgenomen.
- [ ] Tado-rijen (0x17) tegen echte busdata geverifieerd (beta.19-plan, onderdeel 14).

**Software**
- [ ] Beta.19 + HA0.4.0b11 gepubliceerd en geïnstalleerd **met de vergrendeling dicht**, ≥ 24 h stabiel in schaduwmodus op die build.
- [ ] Hosttests en soak groen: `test_active_heat_guard`, `test_handover_confirmation`, `test_boiler_limit_read`, `test_supervisor`, `test/soak` modus `full` (scenario `active`: `ha_gone`, `measurement_gone`, `reboot`, `reboot_tado_back`, `wifi_gone`, `foreign_1a`, `dhw`, `frost`, `stop_until_delivered`, `boiler_limit`).
- [ ] `/status/heating` toont `active.boiler_limit.flow_c` ≠ null **na een E32-herstart** in schaduwmodus, met `reads` ≥ 1 (bewijst dat de E32 0x16 zelf leest). *(beta.19, op het apparaat controleren)*
- [ ] MQTT stabiel: `mqtt_budget_disconnects` loopt niet op over 24 uur (waargenomen op beta.18: 4 in 17 min; beta.19-plan onderdeel 29) en `minimum_free_internal_bytes` ≥ 20000 (waargenomen: 13280). Anders eerst oplossen: een E32 die MQTT verliest, zet HA-bronnen op "bron weg".
- [ ] Bewakingsscript één uur in schaduwmodus gedraaid (§4.2): geen onverklaard alarm.

**Ruimteplan**
- [ ] Woonkamer actief; bronnen 1. tado-klimaatentiteit (HA), 2. Xiaomi pvvx; gewenste temperatuur van de tado-entiteit.
- [ ] Weekprogramma op de E32 gelijk aan het tado-schema; "temperatuur zonder HA" ingesteld (bijv. 19 °C). Klok vertrouwd (NTP).
- [ ] Badkamer inactief. Aanvoergrenzen 30 / 50 °C voor de eerste dag (niveau van de eerdere proeven; vloerverwarming), daarna eventueel 55–60 °C.

**Mensen en ketel**
- [ ] Eigenaar aanwezig bij de ketel, met telefoon/laptop op de pagina Ruimtes en HA; bij voorkeur een tweede persoon aan de laptop.
- [ ] Waterdruk 1,1–2,5 bar (foto van de manometer); geen actuele storing.
- [ ] Onafhankelijke stop bekend: CV-functie op het ketelpaneel of de hoofdschakelaar.
- [ ] Middag met warmtevraag (buiten < ~12 °C); huisgenoten weten dat tapwater getest wordt.
- [ ] HA-automatiseringen die de tado of het plan wijzigen uit; geen andere firmware-update op die dag.

---

## 4. Voorbereiding (dag vóór de overstap)

### 4.1 Software klaarzetten

1. **Back-ups:** volledige HA-back-up; `GET /config/heating` (plan + revisie)
   en `GET /config/heating/flow` opslaan in `out/switchover-<datum>/`;
   Bluetoothkoppeling (adres, profiel) noteren.
2. **Bekende goede terugvalfirmware:** het ZIP en `firmware.bin` van de
   gepubliceerde beta.19 **met vergrendeling dicht** (de schaduwbuild die nu
   draait), plus beta.18 als tweede terugval. Lokaal op de laptop, zodat de
   upload via Systeem → Firmware bijwerken ook zonder internet of HA werkt.
3. **De vergrendelingsbuild (alleen beschrijven; aparte goedkeuring).**
   Op de overstapdag, en alleen na expliciete goedkeuring door de lead en de
   eigenaar, wordt een aparte build gemaakt: beta.19 met
   `constexpr bool emsActiveHeatAllowed = true;` in de `OPENTHERMOSTAT_E32V2`-tak
   van `src/Board.h`, verder bit-voor-bit dezelfde bron. Die build volgt de
   releaseafspraken (eigen tag, CI groen, review van de zendroute, eigen
   publicatie-uitzondering) en wordt via de officiële route (HA-update) of de
   lokale upload geïnstalleerd. Na installatie toont Ruimtes → Actieve
   regeling **niet** meer "Actieve regeling is in deze firmware niet
   ingeschakeld.". Omdat de bevestiging aan de firmware gebonden is, start
   deze build altijd zonder bevestiging. *Dit draaiboek opent de vergrendeling
   niet.*
4. **Bewaking klaar:** WSL of een andere altijd-aan computer in het thuisnet,
   repository bijgewerkt, map `out/switchover-<datum>/` (valt onder bewaarde
   logs, niet onder opruimen). Optioneel een HA-webhook voor meldingen
   (README van het script).

### 4.2 Generale repetitie in schaduwmodus

```sh
export OT_E32_PASSWORD='…'          # nooit op de opdrachtregel
export OT_NOTIFY_URL='http://homeassistant.local:8123/api/webhook/<id>'   # optioneel
python3 -I tools/switchover/monitor.py --host http://192.168.1.206 --once      # één meting
python3 -I tools/switchover/monitor.py --host http://192.168.1.206 --duration-h 1
```

Verwacht: elke minuut een regel `shadow req 0 (calc NN) …`, geen alarm
behalve eventueel `mqtt_budget_disconnects`/`heap_low` (zie §3). Een
testmelding op de telefoon: tijdelijk `--max-starts-per-hour 1`.

### 4.3 De tado weer aansluiten (oefenen, nog niet doen)

Zodat het teruggeven later zonder nadenken kan:
- [ ] Foto's van de bedrading op de EasyControl Adapter: welke twee draden zijn van de tado, welke van de E32, op welke klemmen.
- [ ] Labels op het tado-draadpaar ("TADO — klem …") en op de E32-draden ("E32 — niet losmaken").
- [ ] Lasklemmen of kroonsteentjes klaar om de losse tado-draden te isoleren.
- [ ] Bekend hoe de E32 gevoed wordt (EMS-bus of eigen voeding): bij busvoeding herstart de E32 als de ketel uit gaat.
- [ ] Een kaartje bij de ketel met §8.1 en §8.2 (teruggeven normaal en nood).

---

## 5. Overstapdag: loskoppelen, bevestigen, overnemen

### 5.1 Vergrendelingsbuild installeren (na goedkeuring, §4.1 punt 3)

- [ ] Installeren; E32 ≥ 2 min opgestart; pagina Ruimtes → Actieve regeling: "Schaduwmodus: je thermostaat regelt de ketel." en de knop "Mijn thermostaat is losgekoppeld van de ketel — laat de E32 overnemen" is zichtbaar.
- [ ] `active.enabled = true`, `active.boiler_limit.flow_c` ingevuld (bijv. 75), `active.confirmation = null`.
- [ ] Bewakingsscript starten (48 uur), in een eigen terminal laten lopen.

### 5.2 De tado fysiek loskoppelen (E1)

1. Wacht tot de tado geen warmte vraagt: HA "Gevraagde aanvoertemperatuur
   (thermostaat)" = 0 (zet de tado zo nodig even lager).
2. Ketel uit met de hoofdschakelaar.
3. Maak alleen het tado-draadpaar los van de adapter; isoleer, label en
   fotografeer. De E32-draden blijven zitten.
4. Ketel aan. Noteer de tijd (t0).

**Na het loskoppelen, 10–15 min, E32 nog in schaduwmodus:**
- [ ] Keteltelemetrie blijft binnenkomen (pagina Ketel / HA Aanvoertemperatuur, Verwarmen actief, Brandermodulatie). Kwam die alleen op vragen van de tado: **afbreken** (§7).
- [ ] De ketel blijft in rust (geen CV, geen brander). Stookt de adapter zelf: noteren, afbreken.
- [ ] Tapwater zonder 0x33 van de tado: kraan 1 min open → "Warm water actief", ~55 °C. Anders noteren.
- [ ] `active.boiler_limit.flow_c` blijft bekend (de E32 leest 0x16 zelf; `reads` ≥ 1 na de herstart door "ketel uit"). *(beta.19, op het apparaat controleren)*
- [ ] "Gevraagde aanvoertemperatuur (thermostaat)" en "Ruimtetemperatuur (thermostaat)" worden binnen ~3 min onbeschikbaar (verwacht).
- [ ] Tado in HA: temperatuur en setpoint blijven actueel (via de tado-bridge).

### 5.3 Bevestigen en overnemen (E2)

| # | Doen | Verwacht op de E32-pagina | Verwacht in HA / script | Uiterlijk |
| --- | --- | --- | --- | --- |
| 1 | E32 ≥ 2 min op. | Schaduwmodus; woonkamer "Gemeten", bron de tado-entiteit. | Regelstatus `ok`. | — |
| 2 | Knop **"Mijn thermostaat is losgekoppeld van de ketel — laat de E32 overnemen"** → dialoog bevestigen. | "Bevestigd. De E32 neemt de ketel binnen een minuut over." Kort "Overnemen…". | Script: `arming`. | 10 s |
| 3 | Wachten. | "De E32 regelt de ketel. · Ketelvraag: NN °C (of uit) · laatst verzonden … geleden"; geen waarschuwingen. | Script: `active req NN`; `confirmation_stored: true`. | 1 min |
| 4 | Controleren. | "laatste vraag van een andere regelaar … geleden" blijft ouder worden; knop "Teruggeven aan de thermostaat (de E32 vraagt één minuut lang nul)" zichtbaar. | Geen Verwarmingsprobleem. Bus: `transmitted_frames` loopt op. | 2 min |

Fout in stap 3: `boiler_limit_unknown` → wachten tot de 0x16-lezing slaagt
(≤ 5 min), anders afbreken; `transmit_failed` na 3 min → afbreken (§7);
blijft `arming` → ruimtebron niet vers (status van de woonkamer);
`blocked_foreign_controller` → de tado stuurt nog: bedrading controleren, niet
opnieuw bevestigen voordat dat is opgelost.

---

## 6. Bijgewoonde tests

Volgorde: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12.
Per test: tijden (lokaal en UTC), screenshot van Actieve regeling, het script
loopt door. **Geslaagd** = alle punten onder "Geslaagd"; anders **niet
geslaagd**: noteren, en bij een afbreekcriterium (§7) direct terug (§8).

### T1 Start
- **Doen:** gewenste temperatuur woonkamer (tado/HA) ~1 °C boven de meting.
- **Verwacht:** binnen één stap (10 s) Ketelvraag ~40 °C (30 + 10 × 1 °C), direct verzonden.
- **Geslaagd:** "Verwarmen actief" binnen 2 min (tot ~10 min als de eigen pendelblokkering van de ketel loopt — noteren); aanvoer stijgt ≥ 3 °C binnen 15 min; geen `boiler_no_response`.
- **Controle:** E32 — Ketelvraag en "laatst verzonden < 60 s"; HA — Aanvoertemperatuur, Verwarmen actief, Brandermodulatie; bus — Gekozen aanvoertemperatuur = verzonden vraag, `transmitted_frames` +1/min, display `-H`.

### T2 Modulatie
- **Doen:** setpoint achtereenvolgens +1, +2, +3 °C boven de meting (elk ~10 min).
- **Verwacht:** vraag ~40 → ~50 °C (I-deel loopt langzaam op), nooit boven het planmaximum (50 °C), 80 °C of de ketelgrens.
- **Geslaagd:** gemeten aanvoer volgt binnen ±3 °C binnen ~10 min; CV blijft actief over de 60-s-verversingen (de adapter accepteert 60 s); script zonder `request_above_limit`/`flow_above_limit`.
- **Controle:** E32 — Ketelvraag; HA — grafiek Ketelvraag (E32) naast Aanvoertemperatuur en Gekozen aanvoertemperatuur; bus — Gekozen aanvoertemperatuur ≤ plafond.

### T3 Stop en minimale pauze
- **Doen:** gewenste temperatuur ≥ 0,5 °C onder de meting.
- **Verwacht:** liep de vraag < 5 min: eerst "Minimale brandertijd", daarna "Warm genoeg"; Ketelvraag uit; 60 s lang elke 10 s nul. Direct weer omhoog: "Minimale pauze" tot 5 min na de stop.
- **Geslaagd:** "Verwarmen actief" uit binnen ~30 s na de eerste nul; geen nieuwe start binnen 5 min; geen waarschuwing.
- **Controle:** E32 — reden in "Berekende ketelvraag"; HA — Verwarmen actief, Branderstarts afgelopen uur; bus — Gekozen aanvoertemperatuur → 0/laag, display `0H`.

### T4 Tapwater tijdens verwarmen
- **Doen:** tijdens T2 een warme kraan 3 min open, dan dicht.
- **Verwacht:** "Warm water actief" aan, CV pauzeert (voorrang), aanvoer kan ~75 °C melden (warmtewisselaar); de E32 blijft dezelfde vraag elke 60 s sturen; geen stop, geen waarschuwing (O1).
- **Geslaagd:** CV weer actief binnen 5 min na het dichtdraaien, aanvoer terug naar de vraag; tapwatertemperatuur ok; script geen `flow_above_limit` (tapwater telt niet).
- **Controle:** E32 — toestand blijft `active`; HA — Warm water actief, Verwarmen actief, Aanvoertemperatuur; bus — display `=H` dan `-H`.

### T5 Teruggeefknop (zonder de tado aan te sluiten)
- **Doen:** tijdens verwarmen "Teruggeven aan de thermostaat".
- **Verwacht:** "Teruggegeven. De E32 vraagt de ketel één minuut lang nul. Sluit daarna je thermostaat weer aan op de ketel."; `stopping` ≥ 60 s, daarna Schaduwmodus; `confirmation_stored: false`.
- **Geslaagd:** CV uit binnen ~30 s; daarna zendt de E32 niets meer (`transmitted_frames` stil); script `handed_back`. Daarna opnieuw overnemen (§5.3 stap 2–4).

### T6 E32-herstart (bewaarde bevestiging) en gedrag van de adapter
- **Doen:** bij een matige vraag (~40 °C, CV actief) Systeem → "Apparaat herstarten". t0 = klik.
- **Verwacht:** de E32 zendt ~30–60 s niets (herstart); daarna **zonder nieuwe bevestiging** `arming` met `confirmation.restored: true`; na 2 min onafgebroken ketelontvangst zonder vreemde 0x1A (≈ 130 s na boot, en binnen ~1 min na de eerste verse meting) weer `active` met dezelfde vraag; `boiler_limit.reads` ≥ 1 en `flow_c` bekend vóór de eerste positieve vraag. (Soak `reboot`; op het apparaat controleren.)
- **Meten (O2):** blijft "Verwarmen actief"/Brandermodulatie/Gekozen aanvoertemperatuur staan in het gat? Tijd noteren.
- **Geslaagd:** weer `active` binnen ~4 min na t0, geen `awaiting_confirmation`; script `e32_restarted` met `reset_reason` `software`; zwarte doos (Systeemlog / `previous_boot`) toont de handmatige herstart.

### T7 E32 stroomloos (adaptergedrag, O2)
- **Doen:** voeding van de E32 eraf (bij busvoeding: de E32-busdraden los). Stopwatch. Max. 30 min wachten.
- **Verwacht:** de ketel gedraagt zich zoals de adapter dat doet zonder regelaar: *vasthouden* of *timeout naar nul na X min*.
- **Geslaagd:** gedrag gemeten en getimed (keteldisplay, aanvoerleiding met de hand/IR, branderlawaai); script `e32_unreachable` na 3 min. E32 weer aan → als T6: ≈ 130 s na boot (2 min busontvangst zonder vreemde 0x1A) `active` zonder nieuwe bevestiging, uiterlijk ~4 min; `reset_reason` `power_on`.

### T8 Wifi weg (20 min)
- **Doen:** het accesspoint (of alleen het SSID van de E32) uit; **niet** alleen verkeer blokkeren. 20 min, dus langer dan de oude 15 min van `wifi_lost`.
- **Verwacht:** de E32 regelt door; na ≤ 15 min woonkamer "Terugvalbron" (Xiaomi) en "Gewenste temperatuur uit het weekprogramma"; pagina, HA en script zien de E32 niet.
- **Geslaagd:** na terugkeer **geen herstart** (uptime loopt door, script geen `e32_restarted`, `previous_boot` ongewijzigd), toestand `active`, geen gat op het keteldisplay. *(E7; soak `wifi_gone`)*
- **Controle:** keteldisplay en aanvoerleiding tijdens de test; daarna `/status/logs` en de HA-geschiedenis.

### T9 Home Assistant weg (HA Core stoppen, broker blijft draaien)
- **Doen:** HA Core stoppen (bij HA OS blijft de Mosquitto-add-on draaien). Laat een T1-achtige vraag lopen.
- **Verwacht:** na ≤ 15 min "Terugvalbron" (Xiaomi leidt) en het weekprogramma als setpoint; regeling loopt door; pagina blijft bereikbaar.
- **Geslaagd:** geen stop, geen herstart, Ketelvraag blijft logisch; na HA-start binnen 5 min weer de tado-bron en het HA-setpoint.
- **Variant broker weg** (Mosquitto stoppen, 20 min): geen herstart (geen `broker_lost` zolang de E32 de ketel bezit). *(E7; native `test_supervisor`)*

### T10 Meting weg (aansluitend op T9, HA nog uit)
- **Doen:** batterij uit de Xiaomi op t0.
- **Verwacht:** t0+15 min "Laatste waarde (bron weg)"; t0+30 min "Geen meting: geen warmtevraag", Ketelvraag direct nul, `stopped_measurement_lost`, waarschuwing "Ruimtemetingen ontbreken."; **geen** herstart door `bluetooth_silent`. *(E7)*
- **Geslaagd:** CV uit binnen ~1 min na t0+30; script `guard_stopped` en `warning_measurement_lost`. Batterij terug → binnen ~2 min "Gemeten"/"Terugvalbron" en **vanzelf** weer `active` (na de minimale pauze), zonder nieuwe bevestiging (E4). Daarna HA weer starten.

### T11 Vreemde regelaar (0x1A): tado terug terwijl de E32 actief is
- **Doen:** tado-draadpaar terug op de adapter. Kan dat alleen met de ketel uit **en** wordt de E32 uit de bus gevoed, dan herstart de E32 mee: dat test dan ook de bewaking na een herstart (verwacht hetzelfde).
- **Verwacht:** binnen ~40 s na de eerste 0x1A van 0x17: `stopping` (60 s nul, kort samen met de tado), dan `blocked_foreign_controller`, waarschuwing "Een andere regelaar (je thermostaat?) stuurt nog ketelvragen…", "laatste vraag van een andere regelaar … geleden" < 1 min; `confirmation_stored: false`.
- **Geslaagd:** de E32 stopt en waarschuwt zelf, zonder knop; de tado regelt daarna; script `guard_stopped` + `warning_foreign_controller`; na een E32-herstart `awaiting_confirmation` (niet `active`).
- **Daarna:** "Teruggeven aan de thermostaat" (plan naar schaduw). Wil de eigenaar door naar fase 5: tado weer los (§5.2) en opnieuw bevestigen (§5.3).

### T12 Vorstbeveiliging (simulatie)
- **Doen:** woonkamer warm genoeg (geen vraag). Tijdelijk een Bluetooth-sensor als enige bron van de **inactieve** badkamer en die koud leggen (buiten als het < 8 °C is, of in een koeltas met koelelementen; in een zakje tegen condens).
- **Verwacht:** zodra de verse meting < 8 °C is: Ketelvraag = minimumaanvoer (30 °C), reden `frost_minimum`; ≥ 9 °C weer uit (E6).
- **Geslaagd:** beide omslagen binnen één stap na de meting; badkamer blijft inactief; script geen `frost_not_protected`. Plan daarna terugzetten.
- **Alternatief** als het niet koud genoeg wordt: soakscenario `frost` en `test_active_heat_guard` als bewijs; ter plaatse vastleggen dat het niet gelukt is.

---

## 7. Afbreken

Direct terug naar de tado (§8) bij:
- gemeten aanvoer > plafond + 3 °C terwijl CV (niet tapwater) actief is, of een verzonden vraag boven het plafond (script `flow_above_limit`, `request_above_limit`);
- waterdruk < 1,0 of > 2,7 bar, of een nieuwe vergrendelende/blokkerende ketelstoring;
- "Brander pendelt" aan, of meer starts per uur dan de tado in de schaduwperiode;
- `transmit_failed` of `boiler_no_response` zonder verklaring; `foreign_controller` terwijl de tado los is;
- de adapter stookt zonder vraag, of keteltelemetrie valt weg;
- E32 > 3 min onbereikbaar tijdens actief (niet in T7/T8), of ruimte > 1,5 °C boven setpoint terwijl de E32 nog warmte vraagt;
- tapwater werkt niet, lawaai, geur, of de eigenaar twijfelt.

---

## 8. Teruggeven aan de tado (voor iedereen in huis)

### 8.1 Normaal: de E32-pagina werkt

1. Open op telefoon of laptop `http://192.168.1.206` en log in.
2. Menu **Ruimtes**, blok **Actieve regeling**.
3. Druk op **"Teruggeven aan de thermostaat (de E32 vraagt één minuut lang nul)"**.
4. Wacht tot er staat **"Schaduwmodus: je thermostaat regelt de ketel."**
   (maximaal ~70 s). Blijft er langer "Stoppen…" staan: ga naar 8.2.
5. Zet de ketel uit met de hoofdschakelaar.
6. Sluit de twee tado-draden (label "TADO") weer aan op de klemmen van de
   adapter zoals op de foto. Laat de E32-draden zitten.
7. Zet de ketel weer aan.
8. Controleer binnen 2 minuten: in de tado-app geen verbindingsmelding; in HA
   heeft "Gevraagde aanvoertemperatuur (thermostaat)" weer een waarde; op de
   E32-pagina staat "laatste vraag van je thermostaat … geleden" (< 1 min).
9. Draai een warme kraan open: na ~1 min warm water (55 °C).
10. Klaar. De E32 rekent weer mee in schaduwmodus. Laat het bewakingsscript
    doorlopen of stop het met Ctrl+C.

### 8.2 Nood: pagina onbereikbaar, de E32 doet vreemd, of de ketel stookt ongecontroleerd

1. **Ketel uit** met de hoofdschakelaar (of de CV-functie op het ketelpaneel).
   Daarmee stopt de verwarming meteen.
2. **E32 stroomloos:** stekker/voeding eruit, of bij busvoeding de twee
   E32-draden (label "E32") van de adapter los en isoleren.
3. Sluit de twee tado-draden ("TADO") weer aan zoals op de foto.
4. Ketel aan. De tado regelt weer binnen ~40 s (eerste 0x1A).
5. Controleer: warme kraan geeft warm water; waterdruk 1,1–2,5 bar; geen
   storingscode op het display; HA "Gevraagde aanvoertemperatuur (thermostaat)"
   heeft een waarde.
6. Laat de E32 uit tot de oorzaak bekend is. Zet hem later weer aan **terwijl
   de tado aangesloten is**: de E32 ziet de 0x1A van de tado en blijft dan
   stil (`blocked_foreign_controller`, bevestiging gewist): na een herstart
   met bewaarde bevestiging vraagt hij pas warmte na 2 min onafgebroken
   ketelontvangst zonder vreemde 0x1A, ruim drie tado-intervallen (§11, A6).
   Druk daarna toch op "Teruggeven aan de thermostaat", zodat het plan weer op
   schaduw staat.
7. Vermoeden van een firmwarefout: de bekende goede firmware (§4.1 punt 2) via
   Systeem → Firmware bijwerken terugzetten. Een andere firmware wist de
   bevestiging; de E32 stuurt daarna niets tot er opnieuw bevestigd wordt.

Na teruggeven altijd: oorzaak, tijden en screenshots vastleggen (§10) vóór een
nieuwe poging.

---

## 9. De eerste 48 uur en de eerste 2 weken

### 9.1 Eerste 48 uur (bewakingsscript draait)

```sh
python3 -I tools/switchover/monitor.py --host http://192.168.1.206 --duration-h 48
```

Het script schrijft `out/switchover-<datum>/samples-<dag>.jsonl`,
`alarms.jsonl` en `summary-<dag>.json`, en meldt op de telefoon (webhook):
geen warmtevraag terwijl de woonkamer > 0,5 °C onder het doel is (20 min),
aanvoer boven het plafond, pendelen (≥ 6 starts per uur), woonkamer > 1 °C te
koud of > 1,5 °C te warm (30 min; 5 min als de E32 nog warmte vraagt), elke
stop of waarschuwing van de bewaking, `awaiting_confirmation`, E32
onbereikbaar (3 min), herstarts met reden, MQTT-verbrekingen, minimum heap
< 20000 B en stack < 512 B. Opties en drempels: [README](../../tools/switchover/README.md).

**Controlemomenten** (eigenaar, ~5 min elk): +1 h, +4 h, de eerste avond
(nachtverlaging), de eerste ochtend (opwarming op tijd?), +24 h, +48 h.
- [ ] Toestand `active`, geen waarschuwing; `alarms.jsonl` nagelopen.
- [ ] Geen herstart; zo wel: reden, en of de E32 zelf hervatte (zonder bevestiging).
- [ ] Woonkamer: gemiddelde afwijking (`summary` → `rooms.*.mean_deviation_c`) tussen −0,5 en +0,5 °C; overschot < 1 °C.
- [ ] Ketel: `heating_starts_per_hour_max` ≤ tado-niveau uit de schaduwperiode; `flow_while_heating_c.max` ≤ plafond; druk 1,1–2,5 bar.
- [ ] `mqtt_budget_disconnects` gelijk gebleven; `minimum_free_internal_bytes` ≥ 20000.
- [ ] Badkamer en slaapkamers niet te koud of te warm (radiatoren lopen mee).

**Door naar de 2 weken** als na 48 uur: geen onverklaard alarm, geen
herstart door de firmware zelf, comfort in orde. Anders §8.1 en eerst oplossen.

### 9.2 Eerste 2 weken (fase 5)

**Dagelijks (~5 min):** zelfde punten als hierboven via HA (dashboard
"Verwarming": woonkamer Temperatuur + Doeltemperatuur; Ketelvraag (E32) +
Aanvoertemperatuur + Retourtemperatuur; Verwarmen actief + Warm water actief +
Brandermodulatie; Branderstarts afgelopen uur + Brander pendelt; Waterdruk;
Verwarmingsprobleem; gas per dag) of door het script langer te laten lopen
(`--duration-h 0`).

**Wekelijks:** verwarmingstijd en starts per dag naast de schaduwperiode;
parameters (startpunt, aanvoer per graad, trage correctie, planmaximum) alleen
bijstellen met een genoteerde reden. Geleerde aanvoer blijft de eerste 2 weken
**advies** (beta.19-plan, onderdeel 6).

**Firmware-update tijdens fase 5 (1.0-criterium "één update via de officiële
route"):** alleen bijgewoond. Een nieuwe firmware wist de bevestiging (E3): na
de update `awaiting_confirmation`, geen warmte en geen vorstbeveiliging tot de
eigenaar op Ruimtes opnieuw bevestigt. Dus: update starten, wachten tot de E32
op is, de tado is nog steeds los, direct opnieuw bevestigen (§5.3 stap 2–4).

**1.0** (beta.19-plan): 14 dagen actief zonder vastloper of onverwachte
herstart, alle tests van §6 geslaagd, minstens één update via de officiële
route geslaagd, installatiegids door iemand anders te volgen. Andere ruimtes
dan de woonkamer pas na 1–2 weken live.

---

## 10. Vastleggen

- **Per stap/test:** lokale tijd en UTC, toestand en waarschuwingen (screenshot Actieve regeling), keteldisplay (foto), geslaagd/niet geslaagd.
- **Doorlopend:** het bewakingsscript (§9.1) in `out/switchover-<datum>/`; stopwatch-tijden voor T3, T6, T7, T10.
- **Na elke herstart:** `/status/logs` → `previous_boot` (zit ook in de samples).
- **HA:** geschiedenis-export van de entiteiten uit §9.2 over de hele middag; HA-back-up van vóór en na.
- **Bedrading:** foto's vóór, tijdens en na.
- **Verslag:** `docs/modern-thermostat/SWITCHOVER-<datum>.json` in de vorm van `BETA12-ATTENDED-HEAT-20261027.json` (firmware, aanwezigen, druk, per test tijden/uitkomst, adaptergedrag T6/T7 met gemeten tijd, oordeel eigenaar, vervolgpunten), plus een regel in NEXT-RELEASE.

---

## 11. Afhankelijkheden van beta.19-werk in uitvoering (opnieuw controleren)

| # | Draaiboek gaat uit van | Waar | Controle |
| --- | --- | --- | --- |
| A1 | De E32 leest 0x16 zelf: `0B 88 16 00 02` bij de eerste poll na boot, opnieuw als 6 h geen 0x16 is gezien, herhaling na 5 min; `active.boiler_limit {flow_c, age_s, reads}`; zonder grens geen warmte. Review: [BOILER-LIMIT-READ.en.md](BOILER-LIMIT-READ.en.md). | `src/EMS/BoilerLimitRead.h`, `EmsController`, `HeatingController::activeHeatJson` | gebouwd; native `test_boiler_limit_read`, soak `boiler_limit`. *Op het apparaat controleren:* busopname van één `0B 88 16 00 02` met antwoord na een herstart zonder tado, daarna 6 h niets |
| A2 | Bevestiging in NVS, gebonden aan de firmware; gewist bij vreemde 0x1A, teruggeven (plan naar schaduw) en firmwarewissel; `active.confirmation_stored`. | `src/control/HandoverConfirmation.h`, `HeatingController` | gebouwd; native `test_handover_confirmation` (o.a. `NewFirmwareAsksAgain`), soak `reboot`, `foreign_1a`, `stop_until_delivered`; T5, T6, T7, T11 |
| A3 | Bootwachttijd 60 s (was 120 s) voor een bevestiging van deze boot; na een herstart met bewaarde bevestiging pas na 2 min onafgebroken ketelontvangst zonder vreemde 0x1A (≈ 130 s na boot) en binnen ~1 min na de eerste verse meting weer warmte of vorstbeveiliging. | `ActiveHeatGuard::Params::bootHoldoffMs`, `restoredListenMs`, `busGapMs` | gebouwd; native `test_handover_confirmation`, soak `reboot`; T6, T7 |
| A4 | Geen supervisorherstart (`wifi_lost`, `broker_lost`, `network_dead`, `bluetooth_silent`) zolang `claimsBoiler()`; wel `loop_stall`, `update_stuck`. | `src/diagnostics/SupervisorPolicy.h`, `src/main.cpp` | gebouwd; native `SupervisorPolicy.OwningTheBoilerRestartsOnlyForARealHang`, soak `wifi_gone`, `measurement_gone`; T8, T9-variant, T10 |
| A5 | Plafond `min(plan, 80, 0x16)` in guard, zendroute en aanvoeropties (`FlowPolicy`). | `ActiveHeatGuard`, `ActiveHeatPollDriver`, `FlowPolicy` | gebouwd; soak `active` en `chain-ams-options`; T2 |
| A6 | **Opgelost.** Na een noodterugval met de tado aangesloten ziet de E32 de tado-0x1A vóór hij warmte vraagt: met bewaarde bevestiging pas warmte (en vorstbeveiliging) na 2 min onafgebroken ketelontvangst zonder vreemde 0x1A, ruim drie tado-intervallen van ~40 s; een vreemde 0x1A in die tijd wist de bevestiging zonder dat de E32 iets zendt. | `ActiveHeatGuard::restore`, `restoredListenMs` | gebouwd; native `ThermostatBackBeforeTheRestartIsCaughtBeforeAnyRequest`, `ListeningNeedsContinuousBoilerReception`, soak `reboot_tado_back`; §8.2 stap 6, T11 met herstart |
| A7 | Soakscenario's `active` groen in CI. | `test/soak` | §3 |
| A8 | HA meldt `awaiting_confirmation` (O3); tot dan alleen het script. | HA-integratie (`heating_problem.py`) | §3, T6 |
| A9 | De vergrendelingsbuild verschilt alleen in `emsActiveHeatAllowed`. | `src/Board.h` | §4.1 punt 3 |
