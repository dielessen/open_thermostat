# rc.4 — werkpakket (besluit eigenaar 3 november 2026)

Dit is het volledige plan voor E32 `v1.0.0-e32v2-rc.4` met de bijbehorende HA-release
`1.0.0rc5`. Het is geschreven zodat een ander (ook kleiner) model het stap voor stap kan
uitvoeren. Onderbouwing van het leerdeel: [LEREN-PLAN-RC4.nl.md](LEREN-PLAN-RC4.nl.md).
Codereview: [RC4-CODE-REVIEW.md](RC4-CODE-REVIEW.md). Overzicht: [NEXT-RELEASE.nl.md](NEXT-RELEASE.nl.md).

## 0. Doel en grenzen

- **Doel:** een thermostaat die binnen een week na installatie zichtbaar zelf leert en op
  tijd warm is; de fouten en optimalisaties uit de codereview opgelost; de resterende
  E32-punten van de lijst na rc.3.
- **Vertrekpunt:** `release-1.0` op de commit die dit plan bevat (na 43d231b1); E32 rc.3
  en HA 1.0.0rc4 draaien bij de eigenaar.
- **Niet in rc.4:** EMS+ (1.1), schrijven van ketelinstellingen, Bluetooth koppelen vanuit
  HA, alleen-lezen API-sleutel, het RC-huismodel (L7, 1.1), pendelregeling vóór de meting.
- **Gevolg:** rc.4 is firmware; de 14 dagen naar 1.0.0 beginnen opnieuw bij de installatie.

## 1. Werkwijze voor het uitvoerende model

Vaste regels van de eigenaar (gelden altijd):

1. **Nooit zelf installeren of publiceren.** Installeren gebeurt alleen bijgewoond, met de
   eigenaar thuis; publiceren alleen na zijn uitdrukkelijke akkoord. De E32 en Home
   Assistant worden alleen gelezen (HA-token alleen tegen `https://192.168.1.130:8123`).
2. **Een releasebranch pas pushen na de volledige lokale controle**
   (`scripts/final_check.sh`, bij voorkeur via `tools/dev/final_check_runner.sh --copy`;
   met `FUZZ=1` ook de fuzztest). Een race nooit verbergen met retries of langere
   wachttijden.
3. **Git:** elk werkpakket in een eigen worktree en branch vanaf `release-1.0`
   (`git worktree add -b rc4-<pakket> ../open_thermostat-rc4-<pakket> release-1.0`), kleine
   commits met expliciete paden, LF-regeleinden, Engelse commitberichten die eindigen met
   de Co-Authored-By-regel van de sessie. Nooit `git stash` zonder naam; tags nooit
   verplaatsen; `out/` nooit in zijn geheel verwijderen (AGENTS.md).
4. **Tekst:** interface in het Engels met volledige Nederlandse en Poolse vertaling
   (`strings.json` identiek aan `translations/en.json`; de taaltest
   `node --test test/ui-language.test.cjs` moet slagen); gewone taal, geen jargon; geen
   tekst die een oude thermostaat veronderstelt.
5. **Vendor-code:** geen nieuwe newlib/libm-functies in de firmware (`link_review` faalt
   anders); gebruik `learnmath` (`src/control/FlowLearner.h`) of een eigen lus.
6. **Bewijs vóór firmware:** elke leerwijziging eerst op de afspeelbank
   (`tools/replay`) met de opnames; pas bij het gehaalde doel naar de firmware.
7. **Integratie:** branches samenvoegen op `rc4-integrate`; vertaalconflicten oplossen met
   `tools/dev/json_merge3.py` (unie per sleutel) en daarna de menuvolgorde controleren
   (`test_menu_structure.py`); na elke samenvoeging de gerichte tests.
8. **Omgeving:** bouwen en testen in WSL (`~/venvs/pio`, `~/venvs/ha`, node in
   `~/node/bin`); de PlatformIO-lock `/tmp/openthermostat-pio.lock` delen; de volledige
   controle op een kopie op de WSL-schijf (`--copy`).

## 2. Werkpakketten firmware (E32)

Volgorde: eerst F1 (fundament voor L2/L6), dan L1–L5, dan F2–F8, dan de review-pakketten.

### L1–L5. Zelf leren (zie LEREN-PLAN-RC4.nl.md voor doel, bewijs en anker per punt)

| WP | Inhoud | Bestanden | Tests |
| --- | --- | --- | --- |
| L1 | Afkoelen leren ondanks warm water: `Kind::pause` ook voor koelstukken (≤ 30 min), `offSince_` niet terugzetten op warm water zonder verwarming | `src/control/FlowLearner.h` | `test/test_native/test_flow_learner.cpp`: `KeepWarmStoreBlocksCoolingUnlessPaused`; replay: ≥ 3 koelstukken op de opname |
| L2 | `ArrivalLearner` (puur): factor per ruimte 0,5–2,0, bewaard in `LearnedState` (nieuw deel, ontbreken = 1,0); gebeurtenis per programmastap omhoog; telemetrie `arrival` per ruimte | nieuw `src/control/ArrivalLearner.h`, `LearnedState.h`, `WarmupPlanner.h` (factor op de voorlooptijd), `HeatingController.h` (voeden en bewaren), `HeatingTelemetry.h` | nieuw `test_arrival_learner.cpp` (simulatie 2× te lang/kort → ±15 min binnen 8 ochtenden; restore oud record = 1,0); replay: 31 okt en 1 nov geven "te laat" |
| L3 | `FlowPolicy::optimumStart` past ook een `default`-start toe (standaardvoorlooptijd × factor, plafond vloer 3 u / radiator 90 min zolang de factor 1,0 is); tekst "schatting; leert van elke ochtend" | `src/control/FlowPolicy.h`, `WarmupPlanner.h`, teksten in `data/html/ui-messages.js`, HA `learned_overview.py` | `test_flow_policy.cpp`; duurtest-invarianten; replay actief met `--apply-learned`: ochtendstappen op tijd vanaf dag 2 |
| L4 | `readyForTiming(room)` met één gevulde bak voor de tijdschatting; `advise()` houdt 2 bakken; HA/E32-tekst "opwarmtijd geleerd; koelste water leert hij nog" | `FlowLearner.h`, `WarmupPlanner.h`, HA `learned_overview.py` + vertalingen | `test_flow_learner.cpp`; replay: `confidence: learned` binnen dagen |
| L5 | AutoTuner: dagtellers in het NVS-record (elk uur en bij de dagwissel), wachttijd 2 u na een herstart met hersteld record, 24 u na een regelende planwijziging, geen herstart bij cosmetische wijzigingen (namen, afwezigheidstemperatuur, personen, kranen, contacten, "uit tot") | `src/control/AutoTuner.h`, `HeatingController.h` (`AutoTunerNvs`, regel ~349 en ~456), `ControlPartitionBudget.h` (budget +~120 B) | `test_auto_tuner.cpp` (restore van tellers, cosmetisch vs regelend); replay zonder `--no-grace`: beoordeling op dag 2 |

### F1. Scorebord in de telemetrie (fundament voor L2 en L6)

Per lokale dag en per ruimte: aankomstfout (min), doorschieten (mediaan, uit `AutoTuner`),
starts per verwarmingsuur, pendeluren; per huis: gas verwarming (schatting
`GasCalibration`), graaddagen (gemiddelde buitentemperatuur). Compact in
`fw/telemetry/heating_summary` (`HeatingTelemetry.h`), bewaard over een herstart (zelfde
mechanisme als L5). Test: `test_heating_telemetry.cpp` (grootte binnen `TelemetryPolicy`).

### F2. Tellers die een herstart overleven

Warm water vandaag en de afgelopen 7 dagen (`DhwEpisodes.h`): dag- en 7-dagentotalen elk
uur en bij de dagwissel in NVS (gated via `HeatingNoteNvs::writeGated`, ~150 B); lukt dat
niet, dan toont de Ketel-pagina "sinds herstart om hh:mm". "Branderstarts" en
"Branderuren" van de ketel zelf verbergen zolang de ketel ze nooit meldt (altijd 0 op de
EasyControl-adapter). Bestanden: `DhwEpisodes.h`, `HeatingController.h`,
`data/html/boiler.html`. Tests: native (restore) en `boiler-browser.cjs`.

### F3. E32-overzicht: reden per ruimte

Per ruimtekaart de regel waarom hij wel of niet verwarmt, dezelfde teksten als
`room_overview.py` in HA 1.0.0rc4 (uit, raam open, geen meting, warm water, ketelpauze,
vakantie, weg, kamer-weg, tijdelijk doel, Slim opwarmen, verwarmen, warm genoeg) met iconen
voor wie thuis is en open ramen. Vertrekpunt: `git show v11-room-overview:data/html/index.html`
(het E32-deel van het prototype) en `data/html/ui-messages.js` op die branch; geen nieuw
firmwareveld nodig (`comfort.away_by`, raamstatus en `smart_warm_up` staan in de status).
Test: `test/root_status_render.test.cjs` + een browsertest op 390 px.

### F4. Overzichtslabels en telefoonweergave

"CH active" en "Heat demand" worden samen "Heating on" / "Verwarming aan"; op een telefoon
hooguit 2 labels (wat er gebeurt, wie de ketel regelt), de rest onder Details.
`data/html/index.html` (chips in de kop), `ui-messages.js`. Test: `root_status_render.test.cjs`.

### F5. "Te vaak aan en uit" als leerinformatie

Op het E32-overzicht en de Ketel-pagina niet als probleem maar als regel bij het leren:
"De brander gaat vaak kort aan; de E32 verlengt de rusttijd stap voor stap (stap x)" uit
het tuning-log; pas een waarschuwing als het aanhoudt nadat de tuner zijn kans had
(`restCeiling_` bereikt of 3 dagen zonder verbetering). `index.html`, `boiler.html`,
`house.html`, `ui-messages.js`. HA doet dit al sinds 1.0.0rc4.

### F6. Namen op de E32-pagina's

Overal "Weather compensation" / "Weerafhankelijke regeling" in plaats van heating curve /
stooklijn / Follow outdoor temperature (menu "Boiler and heating curve", `curve.html`, de
geleerd-kaart in `house.html`, `ui-messages.js`, `ui-messages-pages.js`), en
"Water temperature in hard frost (−10 °C)" / "Watertemperatuur bij strenge vorst (−10 °C)"
met de uitleg uit HA 1.0.0rc4. De exacte regels staan in RC4-CODE-REVIEW.md (R3). Test:
`ui-language.test.cjs`, de browsertests van de betrokken pagina's.

### F7. Kleinere UX-punten

Geleerd-kaart 2 regels per ruimte met "Meer"; Uitloggen als menu-item in plaats van een
grote knop; 10 % marge boven en onder de lijnen in de grafiek; de standaardstooklijn telt
alleen ruimtes die aan staan (`FlowPolicy::apply`, `radiator` alleen over actieve ruimtes).

### F8. Eigen vakantietemperatuur (alleen als de eigenaar ja zegt)

`RoomOverrides.h` huismodus: `holiday_temperature` naast de afwezigheidstemperatuur;
HA: nummer-entiteit en veld in Configureren → Huis; E32 Huis-pagina. Standaard gelijk
aan de afwezigheidstemperatuur, zodat niets verandert zonder keuze.

### F9. Moderne weergave zonder Home Assistant (R3-01)

De moderne overzichtspagina (kamerkaarten, grafieken, comfort) gaat alleen aan als HA ooit
`modern_shadow` heeft gezet (`src/MQTT.h:247`, `src/HeatingController.h:645`); een E32 zonder
HA-koppeling toont de oude tegelweergave, terwijl de README "ook zonder Home Assistant"
belooft. Fix: `modernMode_` is waar zodra een kamerplan bestaat (of altijd op de E32 V2;
legacy alleen voor de oude ib-therm-builds), onafhankelijk van `modern_shadow`; de pagina
haalt `/status/heating` dan altijd. Eerst nakijken op een E32 zonder HA-koppeling
(browsertest met `controlMode: 'legacy'` plus een plan met ruimtes reproduceert het).

### R. Reviewpakketten (uit RC4-CODE-REVIEW.md)

Per bevinding: de fix uit het recept in RC4-CODE-REVIEW.md, de daar genoemde test, en de
bevinding-ID in het commitbericht. Volgorde: eerst de rijen met "veiligheid/regeling",
dan de rest. `cleanup`-rijen gaan naar 1.1 tenzij triviaal.

**Firmware (zet de klok, dus in rc.4):**

| ID | Ernst | Kort | Raakt |
| --- | --- | --- | --- |
| R1-05 | risk | Onleesbaar plan + bewaarde bevestiging: de guard slaat de nulvraag bij het opstarten over en trekt de laatste 0x1A niet in (`ActiveHeatGuard.h:130-135`) | veiligheid |
| R1-04 | risk | Status per ruimte hangt aan de index, niet aan de id: `FlowPolicy` startvergrendeling, `CurveLearner`-venster, `AutoTuner rooms_/over_`, `TakeoverReadiness`, `RoomOverrides leadS_` opnieuw koppelen bij `setPlan` | regeling |
| R1-07 | risk | Vroege start: eigen minimale rusttijd, alleen verse metingen, meer dan één ruimte — vóór L3 | regeling |
| R1-06 | risk | Comfort-, kranen- en overname-opslag buiten de ruimteboekhouding (`RoomOverridesStore.h:22`, `TrvStore.h:28`, `HeatingController.h:885`) → `storage_full` bij planopslag | opslag |
| R2-02 | bug | Antwoorden naar een trage browser hebben geen tijdslimiet en zetten de verwarmingslus stil (`ResponsiveHttpServer.h:76-198`): `_currentClientWrite` met deadline | regeling |
| R2-03 | risk | Firmware-upload en grote bodies blokkeren de lus zonder de ketelvraag eerst in te trekken: omkeerbare pauze in `ActiveHeatGuard` | veiligheid |
| R2-06 | bug-critical (beperkt bereik) | `config.cpp:662` schrijft de lijst `heatingCurve` zonder lengtecontrole in een array van 9 (legacy `POST /config/boiler`) | geheugen |
| R2-04 | bug | `requestRollback()` wist de geleerde NVS-records vóór de vorige image gevalideerd is (`GitHubUpdate.cpp:95-98,285-297,332`) | data |
| R2-01 | bug (prestaties) | `update::mutationBlocked()` twee keer per lus → `esp_ota_get_state_partition` ~2000×/s (`REST.h:343,347`): status één keer lezen en in een atomic bewaren | CPU |
| R2-07 | bug | `POST /setup/reenter` en USB `setup` herstarten direct zonder de ketelvraag in te trekken (`SetupNetwork.h:141`, `main.cpp:569`): dezelfde route als `/config/reboot` | veiligheid |
| R2-08 | bug | Upload-callbacks autoriseren per blok van 1436 B (`REST.h:1981-2009`): één keer per upload | CPU |
| R2-13 | bug | `MqttOutbox::push()` verwijdert het wachtende frame van hetzelfde topic vóór de ruimtecontrole (`MqttOutbox.h:72-82`) | MQTT |
| R2-09 | risk | MQTT-herverbinding zonder backoff; CONNACK busy-wait | netwerk |
| R2-12 | risk | Lusstilstand pas na 300 s hersteld | regeling |
| R2-14/16/26 | optimization | Twee INFO-regels per 10 s vullen het weblog; de legacy-status wordt elke 15 s geserialiseerd en opnieuw geparsed; elke 2 s de hele compacte status opbouwen ook zonder wijziging | CPU/log |
| R2-05 | risk (1.1) | NVS van 20 KiB; Arduino wist de partitie bij `NO_FREE_PAGES`: partitie-indeling v2 (USB-flash nodig) | opslag |

**E32-pagina's (zetten de klok, dus in rc.4):**

| ID | Ernst | Kort |
| --- | --- | --- |
| R3-03 | bug | "Ruimtes opslaan" zonder bezig-status tijdens de buscontrole van ≤ 150 s; dubbelklik en tussentijdse wijzigingen gaan verloren (`heating.html:1063-1098`) |
| R3-06 | bug | De 10 s-verversing overschrijft het afwezigheidsveld en de vakantiedatum zodra het veld de focus verliest (`house.html:184-199`) |
| R3-17 | bug | Een mislukte verversing na het eerste antwoord is stil (`house.html:201-205`) |
| R3-24 | bug | "Uit tot" rekent met de tijdzone-offset van nu in plaats van die van de datum (`heating.html:303`) |
| R3-25 | bug | `String.replace('{name}', …)` interpreteert `$&`/`$'` in ruimtenamen (`heating.html:670,1039,824`) |
| R3-34 | bug | `BoilerDisplay.load()` draait één keer bij laden, tegelijk met de eerste poll; mislukt hij, dan blijft de ketelweergave leeg (`boiler-display.js:79-95`) |
| R3-05 | bug | Tellers "vandaag / 7 dagen" zijn boot-lokaal (= F2) |
| R3-02 | risk | Ruimtes en Huis pollen elke 10 s in een verborgen tabblad (`heating.html:1018`, `house.html:201`): pauzeren op `visibilitychange` |
| R3-04 / R3-10 | optimization | Huis-pagina 147.661 B tegen een budget van 150.000 B; `ems-reference.js.gz` (70 KB) wordt meegeleverd maar niet gebruikt; Engelse browsers laden de Nederlandse catalogus (14,9 KB) |
| R3 WP-0..WP-7 | ux | De hernoem- en UX-pakketten met regelnummers (F4–F7) staan in RC4-CODE-REVIEW.md onder R3 |

**Home Assistant (HA 1.0.0rc5, zet de klok niet):**

| ID | Ernst | Kort |
| --- | --- | --- |
| R4-01 | bug | Eén leesbeurt van een leeg plan (`revision 0, rooms []`, wat de firmware stuurt bij een onleesbaar plan) wist alle kamerapparaten, entiteiten en groepen (`native_entity_cleanup.py:464-485`). Fix: een leeg plan verwijdert nooit iets; een ruimte pas verwijderen als hij bij twee opeenvolgende leesbeurten ontbreekt |
| R4-06 | bug | `set_comfort` is voor elk klimaat geregistreerd, maar E32-kamerthermostaten hebben geen `async_set_comfort` (`climate.py:38-47`) |
| R4-02 | risk | Een schrijfactie die tot 155 s op een vrije E32-sessie wacht houdt `RoomPlanLink._lock` vast (`room_plan.py:371`): wachten buiten de lock |
| R4-03 | risk | `NativeShadowConnection` abonneert op heel `fw/#` naast de hub: elke boodschap twee keer gedecodeerd (`v1_mqtt.py:296`) |
| R4-05 | risk | De inlogreeks is op 7 plekken gekopieerd met 3 losse foutief-wachtwoord-grendels: één `async_e32_call` |
| R4-07 / R4-10 / R4-11 | risk | Publish-taken zonder foutafhandeling; één falende listener geeft een traceback per boodschap; 150 dashboard-herbouwen bij 150 losse registry-events (debounce) |
| R4 "Legacy inventory" | cleanup (1.1) | 62 modules, 14.732 regels (35 %) en 588 tests dienen alleen de v1-route; 37 testbestanden (289 tests) kunnen weg; de v1-transportlaag niet |

**Tooling en release (zet de klok niet; eerst doen, want de controle en de release hangen eraan):**

| ID | Kort |
| --- | --- |
| R5-01..04 | De drie races in de stresstest (`dashboard-browser.cjs:194-200` echte tijd vóór `pause()`, `display-code-browser.cjs:45` vaste 50 ms, `bluetooth-browser.cjs:40` klik zonder wachten) bij de oorzaak oplossen; lanes `jobs` begrenzen op de 9 browser-CPU's (`final_check.sh:259`) |
| R5-07..09 | Gate: `previous_published_tag` controleren tegen GitHub; observaties aan de boot van de installatie binden; de 14-dagenklok aan de kandidaat binden |
| R5-12 | De cache-busting-controle dekt 2 van de 5 kaart-URL's (`final_check.sh:157`): alle vijf |
| R5-14 | De GitHub-publicatiestap idempotent maken (rc.3 poging 1 faalde) |
| R5-16 / R5-17 | `publish_hacs_repo.py`: origin-controle vóór `git add -A`/push; de trailer en de voorbeeldversie niet hard-coded |
| R5-18 / R5-19 | CI: `concurrency`-groep; `harnesses` en `build (native)` compileren dubbel |
| R5-21 / R5-23 | `cleanup-latest.json` wordt overschreven (herstel-URL's weg): per release een bestand; LOGDIR/MQTT-poort per worktree |
| R5-29 | `tools/dev` en `tools/acceptance` committen (anders faalt `static`) — gedaan met dit plan |
| R5 §3 | **Checklist A** (release-procedure met commando's, delen 0–7) en **Checklist B** (installatiedag met vastlegging) zijn de gezaghebbende stappenlijsten voor §5 en §6 |

## 3. Werkpakketten Home Assistant (HA 1.0.0rc5)

| WP | Inhoud | Bestanden |
| --- | --- | --- |
| H1 | Scorebord: sensor per ruimte en per huis uit F1, kaart op het tabblad Leren en instellingen ("Gisteren warm om 09:12, 12 min te laat; morgen 10 % eerder"), geschiedenis via Recorder | `heating_link.py`, `learned_overview.py`, `dashboard.py`, vertalingen |
| H2 | Teksten voor L3/L4 (schatting; opwarmtijd geleerd) en de aankomstregel in het klimaat-attribuut `smart_warm_up` | `e32_comfort.py`, `learned_overview.py`, vertalingen |
| H3 | Review-bevindingen R4 met ernst bug of risk | zie RC4-CODE-REVIEW.md |
| H4 | Documentatie voor de nieuwe menu's van 1.0.0rc4 (zie §7) | docs |

De HA-wijzigingen komen op dezelfde `release-1.0` en worden als `ha-v1.0.0rc5` samen met
rc.4 gepubliceerd (één HA-versie per E32-kandidaat).

## 4. Bewijs

1. **Afspeelbank:** `tools/replay` met de opname 30 oktober – 2 november (in de repo) en de
   opname vanaf 4 november (ophalen met `tools/replay/from_ha.py`, alleen lezen; de nieuwe
   driewegklep zit erop sinds 3 november 19:00). Per leerwijziging vóór/ná: metingen
   geleerd, dag van "klaar", aankomstfout per ochtend, starts per uur. De cijfers komen in
   `tools/replay/README.md` onder "Baseline".
2. **Unit tests** per werkpakket (native via `pio test -e native -f <test>`, HA via pytest,
   pagina's via de browsertests); de duurtest `test/soak` met zijn invarianten.
3. **Volledige controle** `scripts/final_check.sh --stress 2` met `FUZZ=1`, op de kopie
   (`--copy`), vóór de push: alles PASS.
4. **Dagelijkse meting** in het huis van de eigenaar vanaf 4 november:
   `tools/switchover/active_review.py` (op tijd per ochtend, aanvoer, pendelen, gas,
   afkoelen, leersensoren) — ook als nulmeting voor rc.4.

## 5. Release

Versies: E32 `v1.0.0-e32v2-rc.4`, HA `1.0.0rc5` (tag `ha-v1.0.0rc5`); de kaart-URL's
`-1.0.0rc5.js`. Stappen (details en commando's in
[HA-ONLY-RELEASE-CHECKLIST.md](HA-ONLY-RELEASE-CHECKLIST.md) en in RC4-CODE-REVIEW.md, R5):

1. Alles samengevoegd op `release-1.0`; volledige controle PASS.
2. Versiecommit met `tools/dev/prepare_rc4.py` (kopie van `prepare_rc3.py`): `release.json`,
   `manifest.json`, kaart-URL's (`e32_week.py`, `frontend/e32-week-card.js`,
   `room_overview.py`, `week_planner.py`, `test/week-editor-browser.cjs`), release-notes
   bovenaan `RELEASE-NOTES.md` en `HA-RELEASE-NOTES.md` (Engels, gewone taal, secties New /
   Fixed / Updating / Limitations, < 6000 bytes), `RC4-KANDIDAAT.json`,
   `RC4-OWNER-INSTRUCTION-<datum>.json`, `E32-UPDATE-GATE.json` (`pending_tag` rc.4,
   `candidate_plan`), inventaris en shipped-policy (`tools/dev/refresh_beta19_inventory.py . --apply`,
   daarna `python scripts/verify_beta_release_inventory.py` PASS).
3. **Gate:** `python scripts/verify_e32_update_gate.py --candidate v1.0.0-e32v2-rc.4` moet
   PASS geven. rc.2 en rc.3 hebben geen acceptatiebewijs. R5 §4: een eerlijk bewijs van rc.3
   achteraf is **niet** mogelijk (de checks `backup_verified`,
   `settings_programs_bindings_preserved` en `control_state_safe_after_restart` vragen
   meting vooraf; alleen een HA-dagback-up van vóór de installatie plus de
   recorder-geschiedenis, tot ongeveer 13 november, kan die deels vervangen, en dan nog
   blijft het INCOMPLETE). Dus: een **derde eenmalige uitzondering**
   (`RC4-PUBLICATION-EXCEPTION-<datum>.json`, gap-rapport `RC3-UPDATE-GAP-<datum>.json`,
   het uitdrukkelijke akkoord van de eigenaar letterlijk in het record; voorbeeld:
   `RC3-PUBLICATION-EXCEPTION-20261103.json`). Voor `v1.0.0` bestaat geen uitzondering: de
   installatie van rc.4 wordt mét vastlegging gedaan (§6), anders komt 1.0.0 er niet.
4. Push `release-1.0`; wacht op groen (`tools/dev/ci_wait.py <sha>`); tags
   `v1.0.0-e32v2-rc.4` en `ha-v1.0.0rc5` op dezelfde commit; `tools/dev/tag_wait.py`;
   faalt de publicatiestap van de E32-release op GitHub (zoals bij rc.3), dan laat de
   eigenaar de mislukte job opnieuw draaien.
5. `main` bijwerken in een tijdelijke worktree (merge van `origin/release-1.0`), README-status
   en installatiestappen bijwerken (§7), pushen.
6. HACS: `python -I scripts/publish_hacs_repo.py 1.0.0rc5 ../openthermostat-ha --push`.
7. Opruimen volgens AGENTS.md (`scripts/cleanup_release_artifacts.py --fetch-published --apply --report out/cleanup-latest.json`).

## 6. Installatie van rc.4 met vastlegging

Bijgewoond, eigenaar thuis, zoals `tools/acceptance/rc2-kit/RC2-INSTALL-STAPPEN.nl.md`:

- **A1 (vooraf):** de kit generaliseren naar `tools/acceptance/`: versies, tags en
  entiteitsnamen als argumenten (geen `rc2` in de naam), de HA-token uit `ha-token.txt`
  (git-ignored) naast de scripts, de MQTT-login via stdin van de eigenaar (het oude
  `mqtt_creds.py` is bewust niet meegenomen), de offline tests meeverhuizen en laten
  slagen (`python -I -m unittest` in die map). Wat de kit precies moet bevatten en de
  commandovolgorde op de dag zelf: RC4-CODE-REVIEW.md, R5 §5.3 en Checklist B. Controleer
  het bewijs met `scripts/verify_accepted_update_path.py` op een testbewijs.
- Volgorde op de dag: meting vooraf (`capture --stage ha-baseline`, daarna `--stage e32`;
  de eigenaar typt het E32-wachtwoord en de MQTT-login) → HACS naar 1.0.0rc5 + HA herstart
  → E32 via de Firmware-entiteit (één keer Installeren) → meting 1 direct na de herstart
  → overname opnieuw bevestigen → meting 2 na ≥ 10 min → onafhankelijke controle → bewijs
  schrijven (`write_receipt`) → `E32-UPDATE-GATE.json` `accepted` op rc.4 met de hash.
- Daarna 14 dagen zonder firmwarewijziging; `tools/switchover/release_ready.py` dagelijks;
  de bijgewoonde tests T1–T12 die nog open staan vastleggen met
  `tools/switchover/record_test.py`.

## 7. Documentatie

- `docs/INSTALL.md`, `docs/USER-GUIDE.md`, `docs/INSTALL-CHECK.md`, `docs/FIELD-TESTER.md`:
  de menupaden van HA 1.0.0rc4 (Configureren met 6 onderdelen, ← Terug/Klaar, huismodus en
  vakantie, Slim opwarmen en Weerafhankelijke regeling), het dashboard in tabbladen, de
  nieuwe namen; de regellijst met regelnummers staat in HA-ONLY-RELEASE-CHECKLIST.md.
- `README.md` (hoofdpagina): status rc.4, "Wat het doet" met de aankomst-terugkoppeling,
  installatiestappen ongewijzigd behalve de versienummers.
- HACS-voorpagina via `scripts/publish_hacs_repo.py` (sjabloon in het script).
- De Nederlandse PDF-handleiding opnieuw maken: de generator staat buiten de repo
  (scratchpad `handleiding/make_pdf.py`, reportlab in WSL `~/venvs/pdf`); verhuis hem naar
  `tools/dev/manual/` en werk de menupaden en versies bij; resultaat
  `OpenThermostat-Handleiding.pdf` bij de release als bijlage.
- `docs/modern-thermostat/NEXT-RELEASE.nl.md` bijwerken bij elke mijlpaal.

## 8. Volgorde en inschatting

| Stap | Werk | Inschatting |
| --- | --- | --- |
| 1 | A1 kit generaliseren; F1 scorebord; afspeelbank nulmeting met de opname vanaf 4 nov | 1 dag |
| 2 | L1–L5 met bewijs op de afspeelbank | 2–3 dagen |
| 3 | F2–F8 en de reviewpakketten (parallel, eigen worktrees) | 2–3 dagen |
| 4 | H1–H4 (parallel met 3) | 1–2 dagen |
| 5 | Samenvoegen, volledige controle, review-ronde op het geheel, versiecommit | 1 dag |
| 6 | Publiceren (akkoord eigenaar), installeren met vastlegging (eigenaar thuis) | ½ dag |
| 7 | 14 dagen draaien, dagelijkse meting, dan 1.0.0 | 2 weken |
