# Releaseplan tot en na 1.0 (eigenaar, 30 oktober – 2 november 2026)

Dit is het actuele plan (stand 3 november: rc.3 gepubliceerd en geïnstalleerd, HA 1.0.0rc4 gepubliceerd; de volgende firmware-release is rc.4, zie [RC4-PLAN.nl.md](RC4-PLAN.nl.md)). De oudere secties hieronder zijn geschiedenis.

## Klaar

| Release | Inhoud | Status |
| --- | --- | --- |
| Beta.20 + HA 0.4.0b12 | Alleen fixes: geen storage fault meer na "Connect E32", geen dode integratie na een mislukte stap, ketelwaarden uit retained topics, weekplanner zonder "Configuration error", sessieruimte, opgeruimde entiteiten en dashboard | Geïnstalleerd 30 okt, **eerste volledige acceptatie (PASS)** op de HA-route |
| Beta.21 + HA 0.4.0b13 | Raam- en deurcontacten per ruimte (HA-contacten, geen Bluetooth), aanvoergrenzen op de Ketel-pagina, diagnoseconsole op de E32 (geen SSH; alleen-lezen commando's, 512 logregels, syslog-uitleg), compacte sessie (~een derde minder MQTT-verkeer), vernieuwd HA-dashboard (gegroepeerd, Aan/Uit en codes leesbaar), overstapveiligheden gebouwd achter de dichte blokkade, snellere CI met hergebruik van de branch-run | Geïnstalleerd 31 okt, **PASS** |
| Beta.22 + HA 0.4.0b14 | Alleen `board::emsActiveHeatAllowed = true`; HA toont wanneer de E32 de ketel zelf aanstuurt | Gepubliceerd en via de HA-route geïnstalleerd 31 okt, **PASS** ([bewijs](update-acceptance/e32-beta22-20261031.json)); geaccepteerde basis van de updategate |
| HA 0.4.0b15 | Alleen HA: weekplanner zonder "Configuration error" (de weekkaarten zetten zich terug); de E32 blijft op beta.22 | Gepubliceerd 31 okt |
| **Overstap naar actieve regeling** | Tado los van de adapter, plan actief, overname bevestigd | **Gedaan zondag 1 november rond 21:05** (lokale tijd), eerder dan het geplande dinsdag 3 november; de eigenaar deed het zelf |
| **E32 1.0.0-rc.1 + HA 1.0.0rc1** | De eerste 1.0-kandidaat: beta.23, beta.24 en 1.0 in één release (zie hieronder) | **Gepubliceerd 2 november** (tags `v1.0.0-e32v2-rc.1` en `ha-v1.0.0rc1` op 1dc0b06, GitHub-pre-releases; akkoord eigenaar "publoceren mag ook"). HA 1.0.0rc1 staat ook als pre-release in de HACS-repository `dielessen/openthermostat-ha`. **Niet geïnstalleerd:** de E32 draait beta.22 in actieve regeling; installeren gebeurt met rc.2 |
| **E32 1.0.0-rc.2 + HA 1.0.0rc2** | Zelf bijstellen, leren bewaard, ketelproef, eigen wachtwoord, gewone taal, HACS | Gepubliceerd 3 november (88edbb8); door de eigenaar zelf geïnstalleerd 3 november 07:34 (geen acceptatiebewijs; eenmalige uitzondering voor rc.3) |
| **E32 1.0.0-rc.3 + HA 1.0.0rc3** | Afwezigheid per ruimte, alles instelbaar vanuit HA, Slim opwarmen en weerafhankelijke regeling standaard aan, één onthouden ketelproef, geen oude thermostaat verondersteld, welke ruimtes warmte vragen | **Gepubliceerd en geïnstalleerd 3 november** (tags op 666daf68, HACS 1.0.0rc3), opnieuw zonder acceptatiebewijs |
| HA 1.0.0rc4 | Alleen HA: Configureren met 6 onderdelen, ← Terug en Klaar, alle instellingen erin, dashboard in tabbladen zonder gaten, ruimtestatus met reden, probleemtegel met reden, reparaties alleen voor echte problemen, gewone taal, HACS zonder schijnupdate | **Gepubliceerd 3 november** (43d231b1, HACS 1.0.0rc4); de E32 blijft op rc.3 |

## Beta.22 — de overstap ✅ klaar

- ✅ **Alleen** `board::emsActiveHeatAllowed = true`, verder niets. Ook dan stuurt de E32 pas na de bevestiging van de eigenaar; de bestaande veiligheden blijven.
- ✅ Gepubliceerd en geïnstalleerd op 31 oktober (eigenaar: "ja akkoord voor beta 22", "je mag hem ook installeren"), eerst in schaduw.
- **Schaduwanalyse** (`tools/switchover/shadow_exit.py`), de afgesproken criteria:
  1. 72 uur stabiel. Alle data tellen samen; een geplande update-herstart reset de klok niet, een onverwachte wel (eigenaar 31 okt).
  2. Minstens 10 verwarmingsperiodes van de tado, met nachtverlaging, ochtendopwarming en een periode zonder vraag.
  3. Aan/uit ongeveer op dezelfde momenten (enkele minuten).
  4. Niet vaker aan/uit dan de tado.
  5. Aanvoer **nooit boven de harde grens**: de laagste van planmaximum 60 °C (vloerverwarming), ketelgrens (nu 55 °C) en 80 °C. De vaste band 31–43 °C vervalt (eigenaar 30 okt: "ik zou daar de harde grens aanhouden en gewoon leren").
  6. De vergelijking met de tado is alleen informatie.
- Minimale aanvoer 30 °C. Daaronder vraagt de E32 niets; daarboven leert hij zelf, zo laag mogelijk.
- ✅ **Overstap gedaan op 1 november rond 21:05** (lokale tijd, 20:05 UTC): eerder dan de geplande dinsdag en vóór de volle 72 uur van de schaduwanalyse. De checklist blijft [OVERSCHAKELING.nl.md](OVERSCHAKELING.nl.md). De bijgewoonde tests T1–T12 (starten, stoppen en moduleren, tappen tijdens verwarmen, de E32 uit, wifi/HA/meting weg, het gedrag van de adapter, terug naar de tado) tellen voor 1.0 pas als ze zijn vastgelegd met `tools/switchover/record_test.py`.
- De tado blijft in HA als meting en instelpunt van de woonkamer. Alleen de woonkamer regelt; de Badkamer blijft uit tot de eigenaar hem aanzet.
- **Tot de 1.0-kandidaat geen andere installatie op de E32**, en nooit een firmware-installatie als er niemand thuis is: beta.22 wist bij een firmwarewissel de bevestiging, zonder vorstbeveiliging tot opnieuw bevestigd (S3). De fixes S1–S3 komen alleen met de kandidaat.

## Beta.23 — UX en aanwezigheid ✅ gebouwd, gaat op in de 1.0-kandidaat

**Eigenaar 1 november 18:30: beta.23 komt niet los uit.** Alles hieronder zit op `release-1.0` en verschijnt in de 1.0-kandidaat. Volgens het UX-voorstel (`VOORSTEL-UX-BETA22.md`) met de keuzes van de eigenaar van 31 okt.

- ✅ **Eén indeling op E32 en in HA:** Overzicht · Ruimtes · Huis · Ketel · Systeem; dezelfde namen in EN/NL/PL.
- ✅ **Huis:**
  - huismodus Automatisch / Thuis / Weg / Vakantie tot datum (op tijd weer warm);
  - aanwezigheid met meerdere personen: thuis zodra iemand thuis is, weg pas na 15 minuten iedereen weg, bij twijfel warm;
  - verwarming: aanvoergrenzen (verhuisd van Ketel naar Huis), stooklijn, leren, vorst;
  - energie: ketelvermogen in kW, gasmeter en prijs, buitentemperatuur.
- ✅ **"Weg" bestaat alleen als huismodus**; de Weg-preset op de thermostaat van één ruimte is verdwenen.
- ✅ **Ruimte:** alles op één pagina:
  - Algemeen;
  - Temperatuur (bronnen, instelapparaat);
  - Weekprogramma;
  - Ramen en deuren (raamvertraging per ruimte, standaard 2 min);
  - Personen.
- ✅ **Bluetooth-sensoren** onder Systeem, met een snelkoppeling vanuit de ruimte.
- ✅ **Weekplanner:**
  - niveaus Comfort / Eco / Nacht, per ruimte opgeslagen en elk los instelbaar (gelijk mag, hooguit een zachte hint);
  - een niveau aanpassen past alle blokken met dat niveau aan;
  - "Kopiëren…", stap voor stap ongedaan maken en een lijstweergave op de telefoon;
  - het oude "Away" in de planner is Eco.
- ✅ **Apparaat-ID's in HA:** de apparaten op de EMS-bus als HA-apparaten (model, productnummer en versie); de E32 leest hun identiteit na het opstarten zelf.
- ✅ **Opruimen:**
  - geheugen in kB en uptime in uren, ook voor bestaande entiteiten;
  - entiteiten die een ketel nooit vult (EMS+-tellers, "Boiler test: requested flow") uit en verborgen tot de eerste waarde;
  - de oude MQTT-discovery-entiteiten van vóór de v1-koppeling eenmalig opgeruimd;
  - de terugkerende TV02-melding stil;
  - lange entiteit-ID's optioneel opruimen (zie de 1.0-kandidaat).
- ✅ Compatibel: entiteit-ID's en historie blijven; HA werkt met oudere firmware via onderhandelde capabilities; terugrollen naar beta.21/22 leest de nieuwe velden niet of negeert ze.

**Erbij gekomen voor beta.23 (eigenaar 1 november), ook ✅ gebouwd:**
- ✅ personen per ruimte (eerst gepland voor na 1.0);
- ✅ de menu's afmaken: een Systeem-groep op de E32 (netwerk, updates, back-up, Bluetooth-sensoren, diagnose), Ketel alleen kijken en testen, het losse Comfort-menu in HA opgegaan in Ruimtes en Huis;
- ✅ inklapbare blokken op de ruimtepagina, met een samenvatting;
- ✅ apparaatidentiteit automatisch uitlezen en een voorgesteld ketelvermogen;
- ✅ warm water universeel gesplitst in tappen en warmhouden (directe ketelsignalen eerst, anders afgeleid met een geleerde nachtbasis; optioneel een watermeter in HA), met een tijdlijn in HA en een warmwaterband in de E32-grafiek;
- ✅ de veiligheidsfixes uit de review vóór de overstap: "terug naar de thermostaat" stopt eerst de E32 (S1), een nulvraag na een onverwachte herstart (S2), en na een firmwarewissel opnieuw bevestigen met intussen alleen vorstbeveiliging, plus de HA-Reparatie "Confirm the takeover again" (S3).

## rc.2 — zelf bijstellen, onthouden wat geleerd is en de ketelproef (versies gezet, wacht op controle en akkoord publiceren)

De tweede 1.0-kandidaat: `v1.0.0-e32v2-rc.2` + `ha-v1.0.0rc2`. Rc.1 wordt niet geïnstalleerd; rc.2 is de kandidaat die de eigenaar installeert en die de 14 dagen moet lopen. Concept-releasenotities (Engels): [RELEASE-1.0-RC2-NOTES-DRAFT.en.md](RELEASE-1.0-RC2-NOTES-DRAFT.en.md).

**Status (2 november):** al het rc.2-werk staat op `release-1.0`, ook `rc2-learned-room` en `rc2-doc-labels` (handleidingen en labels gelijk aan de schermen, HACS-route). Versies `v1.0.0-e32v2-rc.2` + `1.0.0rc2` gezet; de releasenotities staan bovenaan [RELEASE-NOTES.md](RELEASE-NOTES.md) en [HA-RELEASE-NOTES.md](HA-RELEASE-NOTES.md). Daarna: volledige lokale controle, CI, en publiceren na akkoord van de eigenaar.

Samengevoegd op `release-1.0`:
- ✅ **zelf bijstellen** (rc2-autotune): de E32 stelt zijn brander- en ruimteknoppen zelf bij uit de gemeten dagen, hooguit één kleine stap per knop per dag, met genoeg bewijs, niet in de eerste 24 uur, alleen op dagen dat de E32 de ketel stuurde; in schaduw alleen "zou wijzigen". Op Huis heet het "Comfort and boiler care", met "Set it myself", "Back to automatic" en "Back to start values";
- ✅ **wat de thermostaat geleerd heeft** op E32 Huis en als HA-sensor met een eigen Learned-pagina op het dashboard;
- ✅ **leren blijft bewaard** (rc2-persist) over herstarts, stroomuitval en updates, en zit in de instellingenback-up;
- ✅ **ketelproef en overname** (rc2-active-default, rc2-rooms-active): een nieuwe installatie kiest haar route van de ketelbus (proefdraaien naast een thermostaat die nog stuurt, anders meteen de begeleide ketelproef); niets naar de ketel vóór de bevestiging; op Ruimtes eerst de actieve regeling;
- ✅ **beveiliging** (rc2-security): geen enkele wijziging zolang het fabriekswachtwoord admin actief is (E32-pagina na het aanmelden of HA-Reparatie "Choose a new E32 password"); teruggeven aan de oude thermostaat blijft altijd werken (69e581f); Host-controle tegen DNS-rebinding; handmatige upload alleen met een OpenThermostat-E32-V2-image; begrensde HTTP-verzoeken; aanmeldblokkade per apparaat; back-upgeheimen gebonden aan de netwerkinstellingen en een wachtzin van minstens 12 tekens; begrensde JSON-diepte van kraanberichten;
- ✅ **Bluetooth** (rc2-ble-fix): een herhaald oud bericht kan een echte sensor niet meer buitensluiten;
- ✅ **HA-review** (rc2-ha-review2, acht fixes): back-ups met accenten, ongedaan maken van een terugzetting, geen terugzetting op de E32 van een andere installatie, een vervangende E32 in gebruik nemen, huismodus en wegtemperatuur, foutmeldingen na een herstart, lege rijen van hernoemde ketelwaarden, een samenvatting in gewone woorden;
- ✅ **GUI** (rc2-gui-e32b met rc2-gui-e32, rc2-gui-ha, rc2-ha-polish): gewone taal (EN/NL/PL, het dashboard nu ook volledig Pools), problemen bovenaan het overzicht, rustiger ruimtekaarten, fouten met "Try again" op de pagina, ketelwaarden onder Diagnostic, het dashboard standaard aan voor een nieuwe installatie, de weekkaart op de telefoon;
- ✅ **HACS**: HA ook als custom repository `dielessen/openthermostat-ha`, elke HA-release ook daar (`scripts/publish_hacs_repo.py`);
- ✅ **replay-gereedschap** (rc2-replay-tool): leren en zelf bijstellen nagerekend op echte data van het huis, als stap in `scripts/final_check.sh`.

Samengevoegd met `rc2-learned-room` (2 november):
- ✅ fixes in het zelf bijstellen: alleen de eigen verwarmingsstarts van de E32 tellen (een ketel die zelf aan en uit gaat of warmhoudt krijgt geen langere pauzes), schaduwvoorstellen alleen uit de eigen vraag, nachtverlaging telt niet mee;
- ✅ NVS-budget: het geleerde en de knoppen nemen nooit de ruimte die het plan, het teruggeven en Bluetooth nodig hebben; bij krapte gaat het minst nuttige eerst;
- ✅ leren van de eigen vraag van de E32 in actieve regeling (de tado is van de bus);
- ✅ warmwater overbruggen: korte warmhoudrondes breken een verwarmingsperiode niet meer af; vloerruimtes leren vanaf 30 minuten;
- ✅ opwarmplanning vanaf de huidige kamertemperatuur zolang het afkoelen niet geleerd is (eerder tot 4,4 uur te vroeg);
- ✅ de effectieve minimale aanvoer van de ketel leren (de HRC 22 stookt pas vanaf ~40 °C);
- ✅ geleerde toestand gehard (onmogelijke waarden uit een bewerkte back-up geweigerd, geen NaN-advies), de back-up past altijd binnen wat terugzetten accepteert;
- ✅ ruimte voor het geleerde van alle ruimtes.

**Installeren** (rond 8 november, bijgewoond, iemand thuis): eerst HA 1.0.0rc2 (de eigenaar stapt dan over van de handmatige installatie naar HACS, zonder de integratie te verwijderen), dan de E32 via de Firmware-entiteit; staat het fabriekswachtwoord er nog, dan eerst een eigen wachtwoord; daarna direct de overname opnieuw bevestigen. Het leren begint één keer opnieuw, want rc.1 en ouder bewaarden het niet; het zelf bijstellen wacht minstens 24 uur.

## Veldtester

Een vriend van de eigenaar gaat een Nefit TopLine draaien met een E32, deze firmware en HA, met radiatorkranen en sensoren in elke ruimte.
- Hij dekt het criterium `install_guide` (iemand anders volgt de installatiehandleiding) en de kranen op echte hardware.
- Hij krijgt rc.2 met een kort testerspakket: de installatiehandleiding, de checklist [INSTALL-CHECK.md](../INSTALL-CHECK.md), de kaart "terug naar de thermostaat" en hoe hij diagnose deelt.
- Nog te vragen: welke kranen en via welke integratie (Zigbee2MQTT of ZHA), zijn huidige thermostaat, zijn sensoren en zijn startdatum.

## 1.0-kandidaat rc.1 — één release voor beta.23, beta.24 en 1.0 (eigenaar 1 november)

Beta.23, beta.24 en 1.0 zijn **één release, de "1.0-kandidaat"**: één releasebranch (`release-1.0`), één volledige controle, één installatie. Hij komt uit als `v1.0.0-e32v2-rc.N` met `ha-v1.0.0rcN`; na 14 dagen met alle criteria op PASS wordt dezelfde code `v1.0.0-e32v2` / `ha-v1.0.0`. Verandert er nog iets, dan volgt een nieuwe kandidaat en begint de klok opnieuw.

**Gepubliceerd op 2 november** als `v1.0.0-e32v2-rc.1` + `ha-v1.0.0rc1` (tags op 1dc0b06; akkoord van de eigenaar op 2 november ~00:10, "publoceren mag ook"). **Niet geïnstalleerd:** het bijstellen van het leren op echte data van de actieve regeling werd zelf bijstellen in rc.2, en rc.2 is de kandidaat die geïnstalleerd wordt (zie hierboven). Releasenotities: bovenaan [RELEASE-NOTES.md](RELEASE-NOTES.md) en [HA-RELEASE-NOTES.md](HA-RELEASE-NOTES.md) (concept: [RELEASE-1.0-CANDIDATE-NOTES-DRAFT.en.md](RELEASE-1.0-CANDIDATE-NOTES-DRAFT.en.md)).

Inhoud (stand `release-1.0` 7916d31: al het 1.0-werk samengevoegd):
- ✅ alles van beta.23 hierboven, met de veiligheidsfixes S1–S3;
- ✅ radiatorkranen per ruimte (hieronder), per ruimte standaard uit: de Zigbee2MQTT-route, de Sonoff TRV Gen2 (TRV-ZBT) met de fix voor de sensorkeuze van Sonoff, en kranen die HA aanstuurt (elke `climate`-entiteit: ZHA, Z-Wave, Shelly, cloud);
- ✅ een dagoverzicht in HA (brandertijd, starts en "Burner starts today", korte runs, op tijd warm, gemist comfort, buitentemperatuur, gas per dag inclusief warmhouden) en waarschuwingen (ruimte blijft koud, sessie weg; elk verwarmingsprobleem ook als Reparatie);
- ✅ lange entiteit-ID's vrijwillig opruimen (Geavanceerd), met voorbeeld (vertaald, ook scènes als gebruiksplaats), historie mee en 30 dagen terugzetten;
- ✅ de code op het ketelscherm in gewone taal, uit de handleidingen van de fabrikant: de EcomLine Classic plus tien families (Nefit EcomLine Excellent, ProLine HRC, TrendLine II, TopLine/AquaPower, SmartLine Basic; Buderus GB172 en GB162; Bosch Condens 7000i W en Cerapur 5C; Worcester Bosch Greenstar 4000), generieke EMS-tabel als terugval; op het E32-overzicht en het HA-dashboard;
- ✅ een eerlijk ketelprofiel: een waarde die een adapter op 0 laat terwijl de ketel werkt (aanvoer-setpoint, brander- en driewegklepbits achter de EasyControl Adapter) heet "Not reported" in plaats van een misleidende 0; HA maakt er geen entiteit voor;
- ✅ "Ready to take over?": de schaduwanalyse van `shadow_exit.py` ingebouwd in de E32 (checklist op de Ruimtes-pagina) en in HA (sensor "Takeover readiness");
- ✅ het leren bijstellen zonder nieuwe firmware: tien begrensde regelknoppen als instelling (E32 Huis → "Advanced: tuning"; o.a. minimale brander-aan/uit-tijd, start-/stopdrempels, aanvoer per graad, opwarmvoorsprong), standaard precies het gedrag van a81d991; veiligheidsgrenzen zijn geen knop. Daarbij het gereedschap (replay, dagelijkse review, opt-in warmwaterbrug, zie [LEREN-ANALYSE.nl.md](LEREN-ANALYSE.nl.md)). Na ongeveer een week actieve data worden de waarden bijgesteld als instelling, zonder de 14-dagenklok te resetten;
- ✅ automatische dagelijkse E32-back-ups in HA (7 dagen, in de eigen HA-back-ups, knop "Back up E32 settings now", Reparatie na 3 dagen zonder), en terugzetten op een nieuwe of gewiste E32 met eerst een overzicht van de wijzigingen; de E32 komt terug in schaduw;
- ✅ HA-schrijfacties wachten op een vrije E32-websessie (tot ~155 s), alleen de nieuwste wijziging per ruimte gaat uit;
- ✅ dertien HA-fixes: allowlist voor het kraan-endpoint, geen verloren kraanwijziging, de weg-vertraging telt vanaf het moment dat de laatste persoon vertrok, warmwatertellingen na een herstart, één Reparatie voor opnieuw bevestigen, warmhoudgas in het dagoverzicht, verdwenen EMS-apparaten na 24 uur weg, opruimen van entiteit-ID's met scènes en vertaald voorbeeld, "Burner starts today", de pauzevertraging per ruimte alleen opgeslagen als die afwijkt, het productbestand niet meer in de event loop gelezen, het voorgestelde ketelvermogen niet meer als eigen waarde opgeslagen;
- ✅ zes firmwarefixes: de nulvraag na een update wordt ook later nog verstuurd, de kraanstop houdt de (afstelbare) minimale brandertijden aan, kraanruimtes houden hun eigen id na een planwijziging, een verwijderde ruimte blokkeert het opslaan van kranen niet meer, bevestigen tijdens vorstbeveiliging neemt direct over, en kranen pas na een bevestigde overname;
- ✅ de fix voor de interne heap: REST-antwoorden gaan zonder extra kopie in intern RAM de deur uit;
- ✅ readiness: `tools/switchover/release_ready.py` meet de 1.0-criteria; de gate laat `v1.0.0-e32v2` alleen door met een definitief PASS-rapport;
- ✅ gebruikershandleiding en installatiegids nagelopen zoals een nieuwe gebruiker 1.0 aantreft, met de checklist voor een tweede persoon [INSTALL-CHECK.md](../INSTALL-CHECK.md) (en [INSTALLATIE-TEST.nl.md](INSTALLATIE-TEST.nl.md)); HA-teksten noemen de echte E32-menupaden (bijv. System → Network and Home Assistant); tot 8 raam- en deurcontacten per ruimte uitgelegd;
- ☐ de installatiegids gevolgd door iemand anders dan de schrijver (criterium `install_guide`).

### Radiatorkranen per ruimte

- ✅ **Route:** Zigbee-kranen via Zigbee2MQTT; de E32 stuurt Zigbee2MQTT direct via de MQTT-broker aan, zodat een herstart van HA Core de kranen niet raakt. Daarnaast de HA-route (`ha_climate`) voor elke kraan die HA bedient. Keuzedocument: [TRV-KEUZE.nl.md](TRV-KEUZE.nl.md).
- **Kraanadvies:** Bosch BTH-RA (klepstand zetten en teruglezen, externe temperatuur, batterij in %); goedkoper alternatief Sonoff TRVZB of TRV Gen2. De TV02 kan reserve zijn (geen klepstand of externe temperatuur). De Shelly BLU TRV rechtstreeks via Bluetooth valt af voor 1.0 (schrijven vraagt in de praktijk de Shelly-gateway).
- ✅ **Regeling:**
  - de aanvoer wordt berekend uit de vraag van alle ruimtes;
  - de kranen verdelen per ruimte;
  - de kraanstanden sturen de aanvoer zo laag mogelijk (allemaal half dicht = omlaag, één helemaal open en nog koud = omhoog); alle kranen dicht = geen ketelvraag.
- ✅ **Uitval:**
  - vroeg waarschuwen bij een bijna lege batterij (~20 %) of geen contact (Reparaties en dashboard);
  - een kraan die wegvalt laat de ruimte "beperkt" meetellen zolang er een andere meting is ("liever iets te warm dan koud"; de meeste kranen vallen open);
  - zonder meting nooit blind stoken: na 30 minuten stopt de eigen vraag van die ruimte, met een melding;
  - per kraanruimte een losse Bluetooth-sensor adviseren, en een hint als een ruimte op één apparaat leunt.
- ☐ **Nog niet op echte kranen geverifieerd:** getest met gesimuleerde Zigbee2MQTT-kranen (met de faalgevallen en een duurtest van twee weken). De verificatie op echte hardware volgt na de installatie van de kandidaat.
- **De eigenaar kijkt na:**
  - merk en type van de afsluiters en de schroefdraad (M30×1,5);
  - ruimte rond de kraan;
  - een Zigbee-router boven;
  - de radiator in de badkamer.
- **Bekende grens:** de vloerverwarming heeft geen zoneklep, dus vraagt alleen boven warmte, dan krijgt de vloer die ook (de mengkraan begrenst).
- **Bekende grens (driewegklep):** achter de EasyControl Adapter blijft byte 7 van telegram 0x18 leeg (ook tijdens een tap van 4 minuten op 1 november), dus de stand van de driewegklep is niet te zien; "warm water actief" is het enige klepsignaal. Dat geldt voor elke ketel achter een EMS-adapter die die byte leeg laat.

## 1.0

Volgorde: beta.22 (✅ overstap 1 november) → rc.1 (✅ gepubliceerd, niet geïnstalleerd) → rc.2 (✅ geïnstalleerd 3 november) → rc.3 (✅ geïnstalleerd 3 november) → **rc.4** (besluit eigenaar 3 november, zie hieronder) → `v1.0.0`.

**De weg naar `v1.0.0` (eigenaar 2 november):**
- de laatste kandidaat draait **14 dagen ongewijzigd** (dat wordt rc.4); elke firmwarewijziging geeft een nieuwe kandidaat en zet de klok terug;
- de resterende **bijgewoonde tests** T1–T12 gedaan en vastgelegd met `tools/switchover/record_test.py`;
- het **leren gezien werken** in actieve regeling: geleerde opwarming per ruimte, de minimale aanvoer van de ketel en stappen van het zelf bijstellen op dagen dat de E32 stuurde;
- de **radiatorkranen via de veldtester** (hierboven); lukt dat niet op tijd, dan komt `v1.0.0` zonder claim over kranen op echte hardware.

Daarna wordt dezelfde code `v1.0.0-e32v2` / `ha-v1.0.0`.

De criteria, gemeten met `tools/switchover/release_ready.py` (alleen lezen):

| Criterium | Wat telt | Vastgelegd in |
| --- | --- | --- |
| `stability` | 14 dagen zonder onverwachte herstart of langdurig offline; een geplande update telt niet | HA-geschiedenis (uptime, Firmware-entiteit) |
| `active_control` | de E32 stuurt de ketel zelf, 14 dagen zonder teruggeven | HA 0.4.0b14+: `boiler_output_enabled` |
| `trv_control` | elke ruimte met kranen heeft de kraansturing 14 dagen aan | de kraanschakelaars van de 1.0-kandidaat |
| `failure_tests` | alle bijgewoonde tests T1–T12 geslaagd (T12 mag het alternatief uit de checklist) | `OVERSCHAKELING-RESULTATEN-<datum>.json`, via `tools/switchover/record_test.py` |
| `updates` | minstens één update geaccepteerd via de HA-route | `update-acceptance/e32-beta20/21/22-*.json` (PASS) |
| `install_guide` | iemand anders volgde de installatiehandleiding tot het eind; elk gevonden probleem opgelost | `INSTALLATIETEST-<datum>.json`, via `record_test.py install` |

De kandidaat mag uit vóór de 14 dagen. De gate (`scripts/verify_e32_update_gate.py`) laat `v1.0.0-e32v2` pas toe met een definitief readinessrapport (`release_ready.py --stage final --json …`) van de kandidaat ervoor: elk criterium PASS, minstens 14 dagen, vastgelegd met zijn hash onder `readiness_report` in `E32-UPDATE-GATE.json`.
Verwachting: rc.4 geïnstalleerd rond 8–10 november, dus 1.0.0 op zijn vroegst eind november; de kranen hangen af van de veldtester (de 14 dagen van `trv_control` lopen pas als de kraansturing aan staat). Let op: rc.2 en rc.3 hebben geen acceptatiebewijs; rc.4 wordt mét vastlegging vooraf en achteraf geïnstalleerd, want `v1.0.0` krijgt geen uitzondering.

## rc.4 — zelf leren dat echt werkt, en de rest van de lijst (besluit eigenaar 3 november)

Het volledige werkpakket, uitvoerbaar door een ander model, staat in [RC4-PLAN.nl.md](RC4-PLAN.nl.md); de onderbouwing van het leerdeel in [LEREN-PLAN-RC4.nl.md](LEREN-PLAN-RC4.nl.md); de codereview in [RC4-CODE-REVIEW.md](RC4-CODE-REVIEW.md).

Aanleiding (eigenaar 3 november): "het zelflerende stuk, is dat goed genoeg? kunnen we dat verbeteren?" De code van rc.3 heeft in dit huis vier blokkades: warm water zet de afkoelmeting terug (afkoeling nooit geleerd, dus Slim opwarmen past zich nooit toe), vóór het leren wordt niets toegepast, "klaar" eist twee aanvoerbakken, en het zelf bijstellen heeft door de 24 uur wachttijd na elke herstart nog nooit een dag beoordeeld.

**A. Zelf leren (de kern)**

| # | Punt | Werk |
| --- | --- | --- |
| L1 | Afkoelen leren ondanks warm water: een warmwaterronde pauzeert de afkoelmeting in plaats van hem te wissen | klein |
| L2 | Terugkoppeling op aankomsttijd: per ruimte een correctiefactor (te laat → 10 % eerder, te vroeg → later), op de standaard- én de geleerde voorlooptijd, bewaard | klein–middel |
| L3 | Slim opwarmen vanaf dag één toepassen met de standaardschatting vanaf de huidige kamertemperatuur, gestuurd door L2, met een plafond | klein |
| L4 | "Klaar" voor de opwarmtijd bij één gevulde aanvoerbak; de laagste watertemperatuur houdt twee bakken | klein |
| L5 | Zelf bijstellen: dagtellers bewaard bij een herstart, 2 uur wachten na een herstart, geen herstart bij cosmetische planwijzigingen | klein–middel |
| L6 | Scorebord per dag: op tijd warm, doorschieten, starts per uur, pendeluren, gas per graaddag; in HA op het tabblad Leren | middel (vooral HA) |
| L7 | Later (1.1): één natuurkundig huismodel dat van elke meting leert | groot |

Pendelen: eerst meten met de nieuwe driewegklep (vanaf 4 november); geen regelwijziging vóór die data.

**B. Overige E32-punten uit de lijst van na rc.3**

- E32-overzicht: per ruimte de regel waarom hij wel of niet verwarmt (zoals de ruimtekaart in HA 1.0.0rc4; E32-deel van `v11-room-overview`).
- Overzichtslabels: "CH active" en "Heat demand" → "Verwarming aan"; hooguit 2 labels op een telefoon.
- "Te vaak aan en uit" als leerinformatie, niet als probleem (in HA al zo sinds 1.0.0rc4).
- Namen op de E32-pagina's: Weerafhankelijke regeling en "Watertemperatuur bij strenge vorst (−10 °C)".
- Tellers die een herstart overleven (warm water vandaag en 7 dagen); branderstarts en -uren verbergen als de ketel ze nooit meldt.
- Geleerd-kaart korter; Uitloggen als menu-item; marge in de grafiek.
- Standaardstooklijn alleen op ruimtes die aan staan.
- Vakantieplanner: periodes vooruit plannen (tot 8), met een eigen vakantietemperatuur (besluit eigenaar 4 november; RC4-PLAN F8).

**C. Codereview** (eigenaar 3 november: "bekijk ook de rest van de code, check op fouten en kijk waar we kunnen optimaliseren"): de gevonden fouten en optimalisaties staan in [RC4-CODE-REVIEW.md](RC4-CODE-REVIEW.md) en zijn als werkpakketten in RC4-PLAN.nl.md opgenomen.

**D. Al gedaan in HA 1.0.0rc4 (3 november, alleen HA)**: Configureren met 6 onderdelen, ← Terug en Klaar, alle instellingen in Configureren, dashboard in tabbladen, ruimtestatus met reden, probleemtegel met reden, reparaties alleen voor echte problemen, gewone taal, HACS zonder schijnupdate.

**Gevolg:** de 14 dagen naar 1.0.0 beginnen opnieuw bij de installatie van rc.4; 1.0.0 eind november op zijn vroegst. Slim opwarmen werkt dan echt in 1.0.0.

## Na 1.0

- **Alleen-lezen API-sleutel voor assistenten** (eigenaar 2 november): een sleutel op de E32 voor gereedschap en assistenten, standaard uit en in te trekken; alleen GET-routes, zonder websessie, met een verzoeklimiet. Zo kan bijvoorbeeld de Claude van een vriend zijn E32 lezen zonder het admin-wachtwoord.
- **1.1:** EMS+-ketels lezen en aansturen.
- **Overzicht per ruimte:** het HA-deel (sensor "Reason", ruimtestatuskaart) zit in HA 1.0.0rc4; de regel op het E32-overzicht staat in rc.4 (B hierboven).
- **Schrijfbare EMS-instellingen (access/write):** pas na 1.0 (eigenaar 30 en 31 okt). Plan: [EMS-INSTELBARE-WAARDEN.nl.md](EMS-INSTELBARE-WAARDEN.nl.md).
  - W1: tabel met schrijfgegevens;
  - W2: bewijsniveaus (L0 verzonden, L1 teruggelezen, L2 blijvend, L3 effect gemeten) met automatisch terugzetten;
  - W3: gebruikersinstellingen in HA, alleen als ze bewezen werken;
  - W4: Geavanceerd voor monteursinstellingen, met waarschuwing;
  - W5: EMS+.

  De ketel van de eigenaar (iRT via de EasyControl Adapter) krijgt alleen een vergelijking van servicecodes; het doel zijn andere ketels.
- **Meer thermostaatfamilies:** naast de RC10-achtige thermostaat (0x17) ook andere EMS-thermostaten herkennen en lezen, tabelgestuurd en alleen geverifieerd op echte busdata.
- **Testerprogramma:** opt-in in HA; "Deel resultaat" opent een vooraf ingevuld GitHub-issue met alleen het ketelprofiel; een GitHub Action controleert het; een profiel komt pas na beoordeling mee.
- **HACS-vermelding** van de integratie in de standaardlijst van HACS; sinds 2 november staat ze al als custom repository `dielessen/openthermostat-ha`.
- De overige ruimtes (Badkamer, slaapkamers) zodra de eigenaar dat wil.
- **Bewust niet in rc.4 (uit de eindreviews van 4 november), voor 1.0.x of 1.1:**
  - R2-16 een eigen EMS-projectie voor `controller_request` (HA leest nu nog `fw/telemetry/controller_request`);
  - R2-26 generatietellers in `FlowLearner`/`RoomEngine`;
  - F5 de waarschuwing als het pendelen aanhoudt nadat de zelfafstemming haar kans had (`tuning.short_cycling_persists`; de pagina's tonen nu alleen de leerinformatie);
  - F9 het firmwaredeel (de moderne status zonder koppeling melden zou de HA-koppeling haar herstart laten overslaan);
  - de terugkeervoorlooptijd met de aankomstfactor (`RoomOverrides::returnLeadS` neemt de standaardvoorlooptijd zonder plafond);
  - review-fw L2 (een herstart midden in een opwarmstart telt als één les "te laat"), L5 (~0,9 KB stapel in `AutoTuner::setPlan` op het HTTP-pad), L6 (het terugzetten van het vakantierecord na een mislukte comfort-opslag is zelf gepoort);
  - R5-28 (tooling) en het echt draaien van de publicatiescripts tegen GitHub (gebeurt bij deze release);
  - **idee eigenaar 4 november:** de ketel meldt displaycode 0Y (water warmer dan gevraagd, brander uit) zelf op de bus; dat als direct signaal gebruiken dat de gevraagde aanvoer te hoog is voor wat het huis afneemt, zodat het leren de aanvoer sneller verlaagt dan via het doorschieten van de kamer.

## Werkafspraken

- Pushen naar een releasebranch alleen na de volledige lokale controle (`scripts/final_check.sh`), met de stresstest van de browsertests vóór een tag. Een race nooit verbergen met retries of langere wachttijden.
- Teststubs in dezelfde commit als de productwijziging; bestanden met LF-regeleinden.
- Elke installatie met een volledig installatiebewijs (vastlegging vooraf, back-up, twee metingen, onafhankelijke controle); daarna de opruiming volgens AGENTS.md.
- Een firmware-installatie alleen als er iemand thuis is om de overname direct opnieuw te bevestigen.
- Teksten in de interface in het Engels met volledige Nederlandse (en Poolse) vertaling; GitHub en commits in het Engels.

# Beta.19 + HA0.4.0b11 — plan: klaar voor de overstap (eigenaar, 29 oktober)

Eigenaar: "je kan vast aan de volgende release werken van mij hoor beta 19.
maak vast een plan". Doel: de release waarmee de bijgewoonde overstap kan
(tado fysiek los, E32 het enige brein). De actieve modus staat erin, maar
start pas na de bevestiging van de eigenaar op de pagina. Bouwen tijdens de
schaduwperiode van beta.18 (3–5 dagen); publiceren als die periode slaagt.

| # | Onderdeel | Inhoud | Klaar als |
| --- | --- | --- | --- |
| 1 | Ketelgrens uit de ketel | De E32 leest 0x16 (`heatingTemp`) zelf: bij opstarten en elke 6 uur, alleen lezen, eigen review van het nieuwe busverkeer. Plafond = min(plan, 80, 0x16). Zonder bekende grens geen actieve warmte. | Grens bekend na herstart zonder tado; hosttest + busopname |
| 2 | Bevestiging "tado los" bewaard | NVS; gewist bij vreemde 0x1A, "terug naar thermostaat" of firmwarewissel. HA-melding bij `awaiting_confirmation`. | Herstart tijdens actief: binnen 1 min weer warmte/vorstbeveiliging |
| 3 | Supervisor tijdens actief | Geen herstart voor wifi/broker/Bluetooth zolang de E32 de ketel bezit; alleen bij echte vastloper (loop/RTC-watchdog). | Policytests; duurtest met netwerkuitval tijdens actief |
| 4 | Vergrendeling open, achter bevestiging | `emsActiveHeatAllowed` aan in de build; actieve modus alleen via de pagina na bevestiging; "terug naar thermostaat" altijd bereikbaar (ook zonder HA). | Schaduw blijft de standaard; review van de zendroute |
| 5 | Faalscenario's actief | Duurtest uitbreiden: HA weg, meting weg, E32-herstart, wifi weg, vreemde 0x1A, tapwater tijdens verwarmen, stop van de E32 (gedrag adapter), vorst. Nulvraag tot bevestigd. | Alle scenario's groen in `test/soak` + CI |
| 6 | Leren toepassen (optie) | Laagste aanvoer die op tijd warmt en optimale start, standaard **advies**; optie "geleerde aanvoer gebruiken", eerst 2 weken alleen advies. | Advies ↔ werkelijk zichtbaar in HA |
| 7 | Gas ijken | Nachtverlaging doorrekenen met de echte gasmeter (m³ of kWh, elke meter), kWh/m³ en prijs; zonder meter ruwe schatting. | Vergelijking per nacht in HA |
| 8 | Ruimte in flash en plan | Webbestanden alleen gzip (flash nu 92–93 %); compacter ruimteplan (8 ruimtes × 4 punten past nu niet in 4095 B). | Flash < 85 %; plantest 8×4 |
| 9 | HA-opruiming | `track_entities` vergeet verwijderde sleutels (geen herlaad meer); dubbele EMS+-entiteiten (F28); pl.json aanvullen of weglaten. | Geen verouderde entiteiten |
| 10 | Overstapdraaiboek + live bewaking | OVERSCHAKELING.nl.md bijwerken; bewakingsscript voor de eerste 48 uur (aanvoer, brander, ruimtes, herstarts). | Draaiboek stap voor stap getest in schaduw |
| 11 | Updaten via HA is de officiële route | Zoals ESPHome (eigenaar 29 oktober): HA haalt firmware.bin van GitHub, controleert SHA-256, grootte en versie en uploadt lokaal naar de E32 (`firmware_update.py`, bestaat al). De updategate accepteert die route (`method: home_assistant`) met een acceptatiebewijs; de HTTPS-update op de E32 zelf wordt optioneel. | Eén E32-update via de HA-updateknop geslaagd en vastgelegd |
| 12 | Versie 1.0 mogelijk maken | Releasecontroles, updatecatalogus en de HA-update (`TAG` kent nu alleen alpha/beta/rc) kennen `v1.0.0` naast `beta.N`; volgorde van oud naar nieuw klopt. | Gate- en HA-tests met een 1.0-tag |
| 13 | Documentatie voor nieuwe gebruikers | Installatiegids van nul (flashen, setup-wifi, HA-integratie, ruimtes, Bluetooth-sensor), ondersteunde hardware (EMS Classic), probleemoplossing. Engels op GitHub. | Iemand anders kan hem volgen |
| 14 | Tado-rijen controleren | In de schaduwperiode de thermostaatrijen (0x17) tegen echte busdata verifiëren, vóór het loskoppelen. | Alleen waargenomen rijen geverifieerd |

**Uitbreiding (eigenaar 29 oktober: "we kunnen wel wat meer dingen meenemen";
gekozen: comfort en bediening, weersafhankelijk stoken, inzicht en energie,
onderhoud en 1.0-zekerheid, raam- en deursensor).** Alles via hetzelfde
ruimteplan op de E32 en dezelfde bewaking (`ActiveHeatGuard`); werkt ook zonder
HA waar de bron op de E32 zit. Bestaande voorbereide code (o.a.
`room_contacts.py`, `room_vacation.py`, `CurveAdaptation.h`, `MetricsTelemetry.h`)
wordt hergebruikt waar die past.

| # | Onderdeel | Inhoud | Klaar als |
| --- | --- | --- | --- |
| 15 | HA-thermostaat per E32-ruimte | Gewone klimaatentiteit (thermostaatkaart, spraakassistenten): huidige temperatuur, doel, modus auto/verwarmen/uit, presets. Schrijft via het ruimteplan. | Doel wijzigen in HA → E32 binnen 15 s |
| 16 | Tijdelijk overrulen | Boost of "tot het volgende schakelpunt" / "2 uur 21 °C", op de E32-pagina en in HA; daarna terug naar het weekprogramma. | Vervalt vanzelf, ook na herstart |
| 17 | Raam- en deursensor | Per ruimte HA-contacten (raam/deur), met vertraging; open → ruimte pauzeert (vorstgrens blijft); dicht → hervat. Bluetooth-contacten (bijv. Shelly BLU Door/Window) als E32-bron indien haalbaar. | Pauze/hervat zichtbaar met reden |
| 18 | Afwezig en vakantie | Verlaagde temperatuur tot een datum; optioneel "iedereen weg" uit HA-personen. | Komt op tijd terug (optimale start) |
| 19 | Weersafhankelijk stoken (optie) | Stooklijn uit de buitentemperatuur (HA-sensor of weerentiteit) als basisaanvoer, de leerfunctie stelt bij; nooit boven plan- of ketelgrens. Zonder buitentemperatuur: huidige regeling. | Lagere aanvoer bij zacht weer in de schaduwvergelijking |
| 20 | Grafieken op de E32 | 24 uur ruimtetemperatuur, doel, aanvoer en brander, ook zonder HA, begrensd in geheugen. **Gebouwd:** `control/HeatingHistory.h`: 288 × 5-minutengemiddelden per reeks (int16, 0,1 °C; brander als % van de tijd aan), 12 528 B PSRAM, eenmalig bij het opstarten (lukt dat niet: geen grafiek), alleen RAM (weg na herstart, de pagina zegt dat). Bemonsterd in `stepHeating()` (10 s). Ruimtekolommen volgen de ruimte-id. `GET /status/history` (compacte JSON via de PSRAM-responsbuffer, ≤ ~30 KB bij 8 ruimtes), `/status` → `resources.history`. Overzicht: grafiek per ruimte (gemeten/doel) i.p.v. de korte live-trend, plus "Ketelverloop" (aanvoer, retour, vraag van de E32 en van de thermostaat; brander als aparte strook), met tekstsamenvatting, tabel per uur en kruisdraad; `history-chart.js`, geen bibliotheek. | Pagina blijft snel en klein |
| 21 | Energie in HA | Gas (m³) en kWh per dag/week, verwarmen vs tapwater, als langetermijnstatistiek voor het HA-energiedashboard. | Waarden kloppen met de gasmeter |
| 22 | Weekadvies | Wekelijks bericht in HA met advies en besparing (blueprint), uitschakelbaar. | EN/NL, gewone taal |
| 23 | Instellingen back-up en terugzetten | Exporteren/importeren van netwerk, ruimtes en Bluetooth-sensoren (wachtwoord en sleutels alleen versleuteld of niet). | Terugzetten op een nieuwe E32 werkt |
| 24 | HA-diagnose | Downloadbare diagnose (zonder wachtwoorden/adressen) voor hulp bij problemen. | Geen geheimen in het bestand |
| 27 | Eigen naam overal | Eigenaar 29 oktober: "waarom maken we nog gebruik van de naam intuibase?". Fabrikant "OpenThermostat" in HA en MQTT-discovery (i.p.v. "intuibase"); contactadres info@intuibase.pl weg van de Over-pagina (bronvermelding blijft); oude AP-standaard `IntuiBaseHeating` → OpenThermostat-naam met uniek wachtwoord (alleen esp32dev/esp32s3); standaard MQTT-voorvoegsel `openthermostat` voor nieuwe installaties, bestaande (`ib-therm`) ongewijzigd. Blijft: MIT-copyright, bronvermelding, bibliotheek `esp32_utilities`. | Geen "intuibase" meer in HA of de E32-interface, behalve de bronvermelding |
| 28 | Weekprogramma gebruiksvriendelijk | Eigenaar 29 oktober: "een weekprogramma maken niet heel gebruiksvriendelijk … daar kan echt nog veel verbetering in de ux". Nu tekstregels als `mon-fri: 06:30 20.5, 22:30 19`. Wordt: visuele weekplanner (dagen × tijdblokken, slepen/aanraken), temperatuurniveaus (comfort/nacht/afwezig) i.p.v. losse getallen, sjablonen (werkdag/weekend, thuiswerken), dag kopiëren, voorbeeldgrafiek; op de E32-pagina én in HA (bestaande planner-code `week_planner.py`/planner-panel hergebruiken). EN/NL. | Eigenaar maakt zonder uitleg een weekprogramma |
| 29 | MQTT zonder verbindingsverlies (telemetriebudget, `TELEMETRIEBUDGET.nl.md`) | Waargenomen 29 oktober op beta.18: 4× `mqtt_budget_disconnects` in 17 min (schrijfgrens 300 ms per bericht), HA-entiteiten kort onbeschikbaar. **Gebouwd (beta.19 + HA 0.4.0b11, samen installeren):** uitgaande wachtrij van 24 KB in PSRAM (`MqttOutbox.h`) met samenvoegen per onderwerp en voorrang (sessie/keepalive, toestand, configuratie, langzaam), hoogstens één telemetriebericht per lusronde met 50 ms rust; verbreken alleen na 15 s zonder voortgang of bij een socketfout (`mqtt_stalled_disconnects`, `mqtt_socket_error_disconnects`; `mqtt_budget_disconnects` = de som). Kleine retained onderwerpen (`fw/state/room/<id>`, `heating`, `boiler`, `ble/<id>`, `boiler_fields/<g>`, `fw/config/plan`, `entities`, `fw/telemetry/learned/<id>`, `summary`, `shadow`) met drempels en vaste ritmes, `fw/heartbeat` elke 60 s, `fw/availability` retained; het oude `fw/telemetry/heating*` en het boiler_fields-ritme van 1,8 s zijn weg. HA: onbeschikbaar pas na 3 gemiste heartbeats of offline. Nog te doen: `fw/hello` en `fw/state/zones` (sessieprotocol, elk 3 s) zijn nu het grootste verkeer. | 0 onterechte verbrekingen in 24 uur; ≤ 0,25 KB/s; elk bericht ≤ 1 KB (hard 1,5 KB) |
| 25 | Code opsplitsen | Grote bestanden (`REST.h`, `ShadowController.h`, `config.cpp`) per verantwoordelijkheid, gedrag ongewijzigd. | Alle tests groen, firmware niet groter |
| 26 | HA-integratie via HACS | Eigenaar 29 oktober (heeft HACS; "kan ook in de volgende release", "wel netter om het via hacs te doen"): eigen repository voor de integratie (bijv. `open_thermostat-ha`) met `hacs.json` (`zip_release`), waar de CI elke HA-release publiceert; firmware-releases blijven in de hoofdrepository. Installatiegids: "Custom repository" toevoegen. Vanaf dan geen Samba-installatie meer. | Integratie-update verschijnt in HA onder Updates |

Volgorde: eerst 1–5 en 10–14 (de overstap), dan 15–18, 19, 23–24, 20–22, 25.
Flash is krap (93 %): punt 8 (gzip) gaat vóór 20.

**Beta.19 is de kandidaat voor 1.0 (eigenaar 29 oktober).** Dezelfde code
wordt v1.0.0 zodra: 14 dagen actief regelen zonder vastloper of onverwachte
herstart, alle storingstests van de overstap geslaagd, minstens één update op
de officiële route geslaagd, en de installatiegids door iemand anders te
volgen is. Kleine problemen eerst in een beta.20, die dan 1.0 wordt. EMS+ komt
na 1.0 (1.1).

Niet in beta.19: EMS+-ketels, lezen én aansturen (eigenaar 29 oktober: "laten
we die maar in beta 20 doen"; na 1.0 dus 1.1), het schrijven van de maximale
aanvoer via EMS (pas na een beoordeelde schrijfroute), meer ruimtes dan de
woonkamer actief (na 1–2 weken live).

# Beta.18 + HA0.4.0b10 — in uitvoering (eigenaar, 28–29 oktober)

Eigenaar: "zorg dat je voor heel de nacht werk blijft houden maak desnoods de
release groter", "het moet heel gebruiksvriendelijk worden en een mooie gui",
"alles moet in het nederlands en engels . behalve github", "we willen geen
crashes meer en vastlopers". Gebouwd (lokaal getest, niet gepubliceerd):

- **Actieve modus, vergrendeld** (`board::emsActiveHeatAllowed = false`):
  `ActiveHeatGuard` (overname alleen na bevestiging "tado losgekoppeld",
  stop + waarschuwing bij 0x1A van een andere regelaar, hervatten na meetverlies,
  vorst aan < 8 °C / uit 9 °C, aanvoer ≤ min(plan, 60, ketelgrens)), zendroute
  via de beoordeelde proefroute (`ActiveHeatPollDriver`), `POST
  /config/heating/handover`, pagina-sectie "Actieve regeling", proef/instellingen
  geweigerd zolang de E32 de ketel bezit.
- **Bluetooth:** metingen 15 min geldig, doorlopend passief scannen (pvvx stuurt
  meetpakketten ~1×/min).
- **HA:** ruimte-editor (opties → E32-ruimtes; bronnen kiezen, °C-controle,
  weekprogramma), schaduwvergelijking als sensoren, opruimen van dubbele/lege
  entiteiten (155 → ~74 bij de eigenaar), dashboard "Verwarming" en vernieuwde
  namen/iconen (in uitvoering).
- **Ketel:** pendeldetector uit het vlambit (de EasyControl Adapter meldt de
  eigen start-/urentellers als 0), laatste vergrendelende/blokkerende storing en
  ketel-uptime in de ene tabel; HA kent het aantal catalogusvelden
  (`catalog_fields`), dus HA0.4.0b9 blijft werken.
- **Betrouwbaarheid:** netwerkbewaking (ICMP naar de router, herstart na 3 min
  "wifi verbonden maar netwerk dood"), reviews van kern en geheugen/opslag,
  fuzz-tests van alle externe invoer (in uitvoering).
- **Proefbediening:** reden bij elke geblokkeerde knop, werkelijke aanvoer naast
  de proefgrens.
- In uitvoering: leren van opwarmsnelheid per ruimte en laagste aanvoer, op
  tijd voorverwarmen, nachtverlaging doorrekenen (kWh/m³/€, ijken met de
  P1-gasmeter `sensor.gas_consumed`); tapwaterstatistiek; tado-rijen
  verifiëren; vernieuwde interface (ontwerpsysteem, menu, licht/donker).

**Besluiten eigenaar 29 oktober (voor beta.19, vóór de overstap):**
1. Ketelgrens: "dat moet een waarde uit de ketel zelf zijn" — de E32 leest 0x16
   zelf bij de ketel (bij opstarten en periodiek, alleen lezen; eigen review van
   dit nieuwe busverkeer).
2. Plan eigenaar: de tado regelt tot hij definitief fysiek van de Bosch-adapter
   gaat; daarna is de E32 het enige brein. De bevestiging blijft dus bewaard over
   herstarts (gewist bij een vreemde 0x1A, "terug naar thermostaat" of
   firmware-wissel); HA waarschuwt bij `awaiting_confirmation`.
3. Geen supervisor-herstart voor wifi/broker/Bluetooth zolang de E32 de ketel
   bezit (alleen bij echte vastloper).
4. De tado fysiek loskoppelen.
Draaiboek: [OVERSCHAKELING.nl.md](OVERSCHAKELING.nl.md).

**Beslissen vóór de bijgewoonde overstap (vergrendeling open):**
1. Ketelgrens na herstart: alleen bekend als de ketel 0x16 meldt (nu alleen op
   vragen van de tado). Periodiek 0x16 lezen, of een opgeslagen waarde accepteren?
2. Bevestiging "tado los" staat nu alleen in RAM: na een herstart geen warmte
   (en geen vorstbeveiliging) tot opnieuw bevestigd. Bewaren over herstart
   (gewist bij vreemde 0x1A), en HA laten waarschuwen bij `awaiting_confirmation`?
3. Brandermelding telt ook tapwater mee (alleen een waarschuwing).

# Beta.17 + HA0.4.0b9 — vervangt de ongepubliceerde beta.16 (eigenaar, 28 oktober)

**Stand 28 oktober, avond:** de tags van beta.16/HA0.4.0b8 (3d928d2) faalden in
CI en blijven ongepubliceerd: (1) de HA-interoptest verwachtte 69 ketelveld-
entiteiten, de echte firmware onderhandelt boiler.fields.v2 (99); (2) de
bronafsluiting van het pakket vond `stdatomic.c.obj` (software-64-bit-atomics
van de supervisortijden). Beta.17 bevat alles van beta.16 plus:

- Bluetooth-pagina liep de E32 vol (eigenaar reproduceerde: pagina open → E32
  onbereikbaar): antwoord nu begrensd in PSRAM, max. 32 apparaten, lijst alleen
  tijdens Zoeken; cJSON-allocaties in PSRAM; RTC-watchdog via de beoordeelde HAL
  (120 s, zwarte doos blijft); fijnere loopfases.
- pvvx-profiel overleefde geen herstart (opgeslagen lezer accepteerde 1..3).
- Ruimteplan met revisienummer (HA en E32-pagina, 409 bij verouderd plan),
  weekprogramma per ruimte (terugval zonder HA, editor op de E32-pagina),
  dagelijkse schaduwvergelijking E32 ↔ tado, E32-Bluetoothsensoren en ruimtes
  in HA met bediening (actief/inactief/tot, terugvalsetpoint).
- Voorbereid, niet aangesloten: `ActiveHeatGuard` (actieve modus, fase 3).
  Open vragen voor de eigenaar: is 10 min zonder 0x1A van de tado genoeg, of
  ook een expliciete bevestiging "tado losgekoppeld"? Na meetverlies automatisch
  hervatten of handmatig opnieuw starten? Ketelterugmelding: waarschuwing na
  15 min zonder brander of 3 °C stijging? Vorst: aan onder 5 °C, uit bij 6 °C?
  Mag de beoordeelde zendroute tot 60 °C (de proef was 50 °C)?

Volgende stap: schaduwperiode (zie hieronder), daarna actieve modus bouwen.

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
   momenten (enkele minuten verschil) en niet vaker aan/uit dan de tado; de
   gevraagde aanvoer komt nooit boven de harde grens (het laagste van het
   planmaximum 60 °C, de eigen ketelgrens en 80 °C). Het aanvoerniveau leert de
   E32 zelf, zo laag mogelijk; de eerdere band ±31–43 °C is geen criterium meer
   (eigenaar, 30 oktober: "ja ik zou daar de harde grens aanhouden en gewoon
   leren"). Het verschil met de tado blijft ter informatie in het rapport
   (`tools/switchover/shadow_exit.py`);
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
- **Regeling:** de E32 moduleert de aanvoertemperatuur (zoals de tado nu doet;
  op 28 oktober waargenomen 31–43 °C, op 30 oktober bij kou tot 49 °C) op basis
  van ruimtetemperatuur en setpoint, met minimale brander-aan/uit-tijden. Het
  niveau leert de E32 zelf binnen de harde grens; geen vaste band (eigenaar,
  30 oktober).
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

Instelbare EMS-ketelwaarden (na 1.0, met bewijsniveaus en een geavanceerde sectie): [plan](EMS-INSTELBARE-WAARDEN.nl.md).

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
