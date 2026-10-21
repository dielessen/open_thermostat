# OpenThermostat — actueel uitvoeringsplan

**Bijgewerkt:** 21 oktober 2026, voortgaande uitvoering Mark11785.
**Eigenaar:** OpenClaw; HA-integratie/apparaatvalidatie: HA-specialist.
**Dit is de enige actuele afvinklijst.** [PLAN](PLAN.nl.md) bevat het ontwerp,
31 eisen en acceptatievoorwaarden; oude PDFs en losse taakdossiers zijn naslag/bewijs.
Deze lijst vervangt geen bestaande technische acceptatiecriteria.

## 1. Waar staan we?

**We zitten in F2/F3: de eerste HA↔E32-kamerketen in shadow, nog geen werkende
zoneregelaar.** WP01/WP02-software is gedaan; contract-/shadowsoftware en HA-GUI
zijn gebouwd. Op 20 oktober is de kamer-/weekeditor in productie-HA geïnstalleerd
en technisch gecontroleerd. De badkamerconfiguratie bestaat, maar runtime,
transport en actuatie staan uit; een volledig verse bron→E32→ACK-proef ontbreekt.

- **Gebouwd/getest:** gecontroleerde firmwarebasis, passieve Classicdecoders,
  sessie-/config-/schema-shadowsoftware, HA-kamerbindingsflow, temperatuurgrenzen,
  helpervrije weekeditor, setup/OTA-bronwerk; onafhankelijke F5-metricsreparatie
  en HA-managed E32-GUIafbouw in bron geaccepteerd, niet geïnstalleerd.
- **Geïnstalleerd:** HA-kamer-/weekeditorpakket; E32 alpha.6 via app-only OTA op
  20okt22:38–22:40CEST (Mark11746), automatische boot/source/UI/ELF en elf
  instellingen-/statussnapshotparen bewezen. Authpad in twee Chromiumviewports
  bewezen; echte telefoon/AP/zevendagen-/volledige UIacceptatie blijft open.
  Renderfix11751 en herstartknop11774 zijn bronwijzigingen, niet geïnstalleerd.
- **Nog niet bewezen/geleverd:** fysieke HA/E32-shadowketen, echte actuatorbediening,
  volledige supervisor en centrale weers-GUI, vloer-/klepprofielen, echte EMS-regeling,
  volledige ketelgrafieken, zelfleren en overige comfortfuncties.
- **Geen normale verwarmingsvrijgave.** Output-/TXblokkades blijven staan; een
  groen softwaretestresultaat of een opgeslagen kamer is geen fysieke proef.

Legenda: `[x]` = de genoemde begrensde uitkomst met bewijs; `[ ]` = open.
Een complete productfase blijft open als één verplichte proef nog ontbreekt.
Geen totaalpercentage: software, installatie en fysieke productacceptatie zijn
verschillende meeteenheden. De 11 productfasen hieronder zijn niet afgetekend.

## 2. Waar configureren en bedienen we straks?

**Normale gebruikersinstellingen en bediening in HA; uitvoering van de regelkern
op E32.** HA is geen tweede PID-/schema-/ketelregelaar. Bestaande apparaatdrivers
blijven in HA; geen extra helpers/YAML/automations nodig voor normale inrichting.

| Functie | Instellen/bedienen | Uitvoeren / autoriteit | Actuele grens |
| --- | --- | --- | --- |
| Kamers, sensor, TRV/klep, optionele wandbediening | HA-integratie → kamer | HA beheert entitybindings; E32 kent stabiele kanaal-/kamer-IDs | Kamerflow geïnstalleerd; echte profielen nog kwalificeren |
| Doeltemperatuur, kamergrenzen, weekprogramma, tijdelijke override | HA-kamerclimate en native kameropties | HA bewaart gewenst; E32 accepteert revisie, voert schema uit en meldt effectief doel | Editor bewezen; fysieke applied-ACK-keten open |
| Buitenbron en ontbrekend/oud-beleid | HA-integratie → algemene instellingen | HA levert gekwalificeerde bron; E32 valideert leeftijd en toepasbaarheid | Centrale draftflow in bronkandidaat; volledige toepassing nog te bouwen |
| Weersafhankelijk aan/uit, stooklijn, aanvoergrenzen | HA-integratie → centraal verwarmingscircuit | E32 berekent waterdoel, inclusief begrensde zonecorrectie | Niet in huidige kamereditor; volledige moderne supervisor open |
| Radiator/vloer, circuit, pomp, menger en klepprofiel | HA → afgiftegroep + kameractuatoren | E32 coördineert vraag/vertraging/limieten; HA voert ondersteunde deviceacties uit | Gewenste graph-GUI in bronkandidaat; toegepast profiel-/E32gedrag ontbreekt |
| Leren aan/uit, begrenzing, modelreset en optimum-start | HA → kamer/algemene regeling | E32 bewaart modellen en voert adaptatie uit | Nog niet geleverd/gevalideerd |
| Ketelprofiel, toegestane limieten, vrijgavestatus | HA → geavanceerde centrale instellingen; commissioning afzonderlijk | E32 native EMS; ketel behoudt eigen beveiligingen/DHWprioriteit | Passieve softwarebasis, geen actieve EMSvrijgave |
| Grafieken, waarom warmtevraag, historie/storingen | HA-dashboard/Recorder/diagnostiek | E32 rapporteert feiten/redenen, HA toont en bewaart | Volledige vraag/werkelijk-/pariteitsweergave open |
| WiFi/Ethernet, lokaal account, MQTT-koppeling, firmwareupdate/herstel | E32 lokale apparaatpagina | E32 apparaatbeheer | Blijft op E32, fysieke update-/herstelchecks apart |

### Centraal, per afgiftegroep of per kamer

- **Algemeen / gedeeld circuit:** buitenbron, weersbeleid en ketelinstellingen.
  In Marks gedeelde circuit één centrale waterstooklijn/aanvoerbegrenzing, niet
  dezelfde instellingen nog eens per kamer. Werkelijk afzonderlijke hydraulische
  groepen kunnen later eigen curve en limieten krijgen.
- **Afgiftegroep:** radiator of vloer, waterlimieten, eventuele pomp/menger,
  gezamenlijke readiness/naloop. Meerdere kamers mogen dezelfde groep gebruiken.
- **Kamer:** representatieve sensor, doel, programma, override, kamerdoelgrenzen,
  gekozen actuator(en) en optionele wandbediening. Kamergrens in °C is geen maximale
  ketel-/vloeraanvoertemperatuur.
- Huidig label **“External temperature setting”** bedoelt een externe
  **kamerdoelbron**, niet buitenweer. Voorstel Engels label: **“Optional room
  setpoint source (e.g. wall thermostat)”**; wijziging zelf staat nog open.
- Na opslaan: HA toont gewenst/toegepast/conflict apart. Een HA-save of servicecall
  is niet vanzelf een firmware-ACK of fysiek bereikt resultaat.

## 3. Vloerverwarming en regelkleppen — expliciet bouwbereik

Deze functies stonden conceptueel al in R05/R06 en F4/F8, maar zijn nog geen
bruikbare keuzes in de geïnstalleerde kamereditor. Geen universele TRVselector
als vervanging voor deze verschillende profielen gebruiken.

| Profiel | Gewenste HA-opties | Regeling en acceptatie |
| --- | --- | --- |
| Radiator met lokaal regelende TRV | Model/capabilities, doel, eventuele externe kamermeting, feedback/fallback | TRV heeft binnenlus; E32 superviseert, geen tweede klep-PID |
| Binaire zone-/vloerklep | Bestaande switch/actuator, NC/NO, omgekeerde logica, open-/sluittijd, minimumstandtijd, feedback of expliciete aanname | Langzaam schakelen/dutycycle passend bij actuator, geen snelle PWM; pas warmte na geldige readiness |
| Proportionele regelklep | Bestaande ondersteunde position/number-uitgang, schaal 0–100%, richting, min/max, looptijd, feedback en veilige uitvalstand | E32 bepaalt begrensde stand; percentage is geen bewezen flow/ketelvermogen |
| Vloerverwarmingsgroep | Gekoppelde kamers/actuatoren, traag emitterprofiel, veilige water-/eventuele vloertemperatuurgrens, pomp, startvertraging en naloop | Eigen trage thermiek, vaste hardwarebegrenzer; één pomp op groepsniveau |
| Mengklep / gemengde kring | Afzonderlijk type en bestaande geschikte HA-controller; eigen aanvoersensor en grenzen | 3-punts open/dicht of 0–10V niet gelijkstellen aan generieke 0–100%-klep; driver/kalibratie/feedback en limiet apart aantonen |

NC/NO beschrijft de fysieke spanningsloze stand, niet alleen software-inversie.
0–10V is een elektrische interface en kan zowel een flowklep als mengklep
bedienen; functie, kalibratie en feedback blijven profielgebonden. Een 3-punts
menger vraagt een onderling vergrendelde OPEN/CLOSE-uitgang, looptijd/referentie-
of homingbeleid en eigen aanvoertemperatuurlus. Tijd-gebaseerde standschatting is
geen gemeten positie. Het huidige shadow-wireprofiel bevat nog geen actieve
terugroute voor actuatoropdrachten/resultaten; daarvoor is expliciete versie-/
contractuitbreiding nodig, geen willekeurige HA-serviceproxy.

Te bouwen en te toetsen vóór ondersteuning claimen:

- [ ] Native GUI voor emitter-/actuatorprofiel en afgiftegroepen, inclusief
  één kamer met meerdere actuatoren zonder dubbele schrijvers.
- [ ] Profielvelden ook in configuratiecontract, atomaire opslag, capability-
  onderhandeling en E32-uitvoering opnemen; GUI alleen is niet voldoende.
- [ ] Pomp/klepvolgorde, trage regeling, klepfeedback, stale input, NC/NO en
  onbekende stand in software- en foutscenario's bewijzen.
- [ ] Per werkelijk device/verdeler spanning, fysieke type/looptijd, veilige
  stop/uitval en onafhankelijk temperatuur-/minimumflowbeleid vaststellen.
- [ ] Fysieke actuatorproef eerst zonder ketel; menger/pomp en mix radiator/vloer
  vervolgens afzonderlijk meten. Geen willekeurige E32-GPIO of 230V-aansturing.

Exacte aanwezige vloer-/regelklephardware is nog onbekend. Dat verhindert deze
uitwerking en softwarevoorbereiding niet; devicevrijgave vraagt later het echte
model/type en installatiegegevens. Hoge radiatoraanvoer naast vloer is alleen
toegestaan met aantoonbaar passende menging/begrenzing, of één bewezen veilig
laagtemperatuurregime voor het hele circuit. Alleen een vloerklep sluiten is geen
gelijkwaardige onafhankelijke overtemperatuurbeveiliging.

## 4. E32 eenvoudiger maken: behouden versus afbouwen

Mark11694 staat afbouw van niet meer benodigde functies toe. Uitvoering is een
eigen begrensde bronwijziging. HA-managed menu-/routeafbouw nu in bron geaccepteerd
(Mark11785), niet geïnstalleerd; legacyassets/data en herstelroutes behouden.

| Onderdeel in HA-managed bedrijf | Besluit | Voorwaarde / open werk |
| --- | --- | --- |
| Regelkern, schema-evaluatie, modellen, weersberekening, ketelvraag | **Behouden op E32** | Niet alles naar HA verplaatsen; dit is het afgesproken product |
| EMS-protocol, TX-/veiligheidsgates, stop/leases, diagnostiek | **Behouden** | Geen opschoning die locks, readback of herstel wegneemt |
| Netwerk/setup, lokale toegang, MQTT, OTA/reboot/herstel | **Behouden op E32** | Nodig zonder werkende HA; geen secrets terugtonen |
| Dubbele kamer-/sensor-/TRV-/GPIO-/BLEbinding-editors | **Uit normale HA-managed bediening halen** | Eén configschrijver; eerst opgeslagen legacydata/referenties en modegrens inventariseren |
| Dubbele weekprogramma-/doel-/stooklijneditors | **Geen parallelle schrijver in HA-managed** | Status/readback mag blijven; noodbediening alleen via hetzelfde geautoriseerde pad en heldere override |
| Oude directe BLE-/lokale GPIO/expanderroute | **Geen vereiste voor HA-managed E32** | Niet globaal uit alle generic/legacytargets slopen; E32-outputlocks behouden en profielafhankelijk afbouwen |
| Eigen internetweerselectie naast HA-buitenbron | **Geen verborgen tweede bron** | HA-managed bronkeuze leidend; bestaande legacyroute pas na expliciete migratie/fallbackafspraak afbouwen |
| Oude legacy-MQTTcommands/discovery | **Niet parallel met moderne writer** | Actuele productie-legacyentry/identiteiten zijn bewust behouden; niet zonder migratie verwijderen |

- [x] Exacte menu-/route-/configreferentielijst in HA-MANAGED-GUI.md gereviewd.
- [x] Dubbele E32editors in werkelijk runtime shadowmode verborgen/geblokkeerd,
  legacy/generic behouden; native backendwriter-/CSRF-/updateguards gecontroleerd.
  Verborgen legacyweer server-side na secretmerge read-only. Alleen bronacceptatie.
- [ ] Onduidelijk label van optionele kamerdoelbron in HA corrigeren; normale
  mode-/config-/migratie- en fysieke gebruikersacceptatie blijven apart open.
- [ ] Bestaande instellingen behouden/importeren; modewissel, reboot, rollback,
  setup/OTA en generieke/legacytargets controleren vóór broncode verwijderen.
- [ ] Nieuwe release en fysieke gebruikerscheck apart uitvoeren. Geen extra
  firmwareflash of productieonderhoud uitsluitend vanwege dit document.

### Afzonderlijke bronreparatie — webaanmelding Mark11732/11734

- [x] Afzonderlijke auth-/settingsbaseline read-only vastgelegd: 20okt19:24UTC,
  bordversielabel alpha.4, Digest-login via correcte native client werkt.
  Exact draaiend sourcecommit ontbreekt; mobiele rootcause NIET bewezen.
- [x] Native Engels loginformulier, onafhankelijke begrensde browsersessies,
  CSRF/logout en app-/jQueryfragment-/upload-/recoverybronpad gebouwd. Instellingen,
  fysieke AP-interfacecheck, HA-writer-/update-/EMS-/TXlocks behouden.
- [x] Onafhankelijke parentreview: 61dossierhashes,13before/afterhashes,233andere
  bronpaden behouden;170nativePASS (inclusief18gerichte),15JS en19updaterbrowser
  scenario's PASS. Echte Chromium desktop-/mobielviewportbronpreview PASS,
  NIET fysieke telefoon- of ESP-cookieproef.
- [x] Normale host-E32build en buildfs zonder compilergeheugenafwijking PASS;
  bestaande image-/TXverifier +7verifierfoutproeven PASS. Alpha.6 app-only
  herstelrelease voorbereid; publicatie/werkelijke downloads apart controleren.
- [x] Alpha.5 CI blokkeerde publicatie wegens ontbrekende native RNG-APIshims.
  Testgrens hersteld zonder productiecodeafwijking:36onboardingscenario's onder
  ASan/UBSan PASS; drie nieuwe lifecycle/foutproeven zijn GEEN cryptografiebewijs.
  Mislukte alpha.5tag blijft onveranderd; herstelversie alpha.6.
- [x] [Alpha.6 gepubliceerd](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.6),
  source b6b57df. [CI39490486532](https://github.com/dielessen/open_thermostat/actions/runs/39490486532):
  alle7jobs groen. Alle5downloads tegen providerdigests gecontroleerd;305sourcefiles
  exacttag,138pakketchecks,exactCI-ELF/UIregistry en5echte image-gate/OpenSSLproeven
  onder ASan/UBsan PASS. Publieke API26401B past de bestaande32KiBparser.
  Gepubliceerde app2235296B, SHA579019267fc4f8b6dfb31210d6e37ef471cf275373594277b2e0fce42f97d266.
- [x] Mark11746: alpha.4 → alpha.6 app-only via bestaande native GitHub-updater
  op 20okt22:38–22:40CEST uitgevoerd. Volledige2235296B ontvangen, verificatie/
  bootselectie en automatische herstart bewezen; live source b6b57df, UI en
  ELF-identiteit gelijk aan gepubliceerde image. Native boot bevestigd,
  boot_pending=false, vorige geldige appslot/rollback beschikbaar.
- [x] Technische HTTP-acceptatie op echt bord:82checks PASS, twee onafhankelijke
  cookiesessies/login/herladen/assets/CSRF/afzonderlijklogout. Parent controleert
  echte firmwarehash/ELF, OTA-events en11bytegelijke voor/na-snapshotparen:
  negen instellingen-/programmareadbacks en twee EMS-readbacks. Geen erase,
  factory/SPIFFS/NVSreset of HA/broker/EMS/Tadoactie; credentials ongewijzigd.
- [x] Regressie11751: echte host-Chromium op live alpha.6, zonder netwerkfixtures:
  root→/login→formulier POST /auth/login→cookie→root en eigen logout PASS in
  twee onafhankelijke desktop-/mobielviewportcontexten.32requests vastgelegd;
  onafhankelijke bewijscontrole PASS. GET /auth/login reproduceert exact405;
  /login werkt. Marks werkelijke URL/browser en oorzaak nog onbekend.
  [Browserbewijs](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-login-405-11751-20261020/LIVE-BROWSER.json).
  Geen nieuwe flash of configuratiewijziging; bestaande credentials gebruikt.
- [x] Bronreparatie post-loginrenderfout11751: ontbrekende selectedFlowTemperature
  in showBoiler veroorzaakte undefined.toFixed. Alleen eindige temperatuurwaarden
  formatteren, ontbrekende waarden leeg laten; vier-bestandenpatch op exactalpha.6
  gereviewd en overgenomen. Parent21/21gerichte root-/authtests en diffcheck PASS.
- [ ] Kandidaatbrowser-/installatieacceptatie bronfix11751: overlayproef faalde
  door Chromium PNA na vervangen HTTP-document, niet door bewezen bronfixfout.
  Eigen testsessies konden daardoor niet afmelden; live429session_capacity.
  Geen verdere loginpogingen; native read-onlyproef bevestigt401 op status/config,
  ook met oude Digestclient. Eigen cookies verloren na contextsluiting; herstel
  vereist geldige bestaande sessie of normale fysieke herstart (alleen geïsoleerd
  bord). Geen reboot/flash uitgevoerd. Browser-PASS hierboven betreft oorspronkelijke
  auth/session/logout. Geen bewezen verband tussen renderingfout en Marks405.
- [ ] Marks echte mobiele én desktopbrowser toetsen: visuele login/navigatie,
  sluiten/heropenen, zeven dagen expiry en interfacegebonden fysieke AP-proef.
  HTTP-clients zijn geen telefoon-/desktoprenderingproef. Alle fysieke ketel-/
  shadow-/bron-/TX-/rollback-/powerlossgates blijven open; geen verwarmingsGO.

Installatiebewijs: [TaskFlow/resultaat](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-e32-alpha6-install-11746-20261020/RESULT.md),
[onafhankelijke parentcontrole](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-e32-alpha6-install-11746-20261020/PARENT-VERIFICATION.json).

Bestaande credentials blijven; vier boot-lokale sessies, maximaal7dagen absoluut,
na E32herstart één nieuwe login; geen NVS-tokenopslag. Geen extra dienst.
Parentbewijs: [authreview](/home/dielessen/artifacts/open-thermostat-web-auth-parent-11732-20261020/RESULT.md).
API-/sessiebeleid: [AUTH-LOGIN](AUTH-LOGIN.md). Afzonderlijk van GV-R1/GV-R2;
geen nieuwe productfase, verwarmingsvrijgave of runtime-configuratieschrijver.

### Mark11774/11778 — herstartknop, renderfix en performance · in_progress

- [x] BRON: zichtbare Engelse Restart device-knop met bevestiging, bestaande
  POST /updates/reboot en sessie+CSRF. Busy/onbevestigde boot/ongeldige status
  blokkeren; geen reset/configschrijfactie/automatische mutatieretry.
  Parent diffreview en onafhankelijk 27JS + 20opnieuw gecompileerde C++tests PASS.
- [x] Echte Chromium BRONpreview desktop en mobielviewport: zichtbare knop,
  annuleren, busyblokkade, één geïntercepteerde CSRF-POST en metadata-only
  rootrender zonder pageErrors. Geen apparaatverkeer; negen resources per context.
  Testharnas decodeert gzipassets vóór Playwright-fulfillment; eerste onjuiste
  gzipdoorvoer faalde, niet als productfout/PASS geboekt.
- [x] Publieke performancebaseline: negen GETs, drie per asset; mediane totale
  laadtijd /login 50.624ms, /login.js 50.572ms, /auth-client.js 65.319ms.
  Geen bewijs van oorzaak van trage ingelogde pagina's; geen optimalisatieclaim.
- [ ] Ingelogde apparaatnavigatie/rendering en voor/nameting van eventuele
  optimalisatie: volle sessies blijven livecontrole blokkeren, geen loginspam.
- [ ] Build/release/installatie en echte apparaatherstart/instellingenbehoud;
  bronpreview bewijst deze niet. Vier niet-verdringende bootsessies blijven behouden.
- [x] F2/F3 begrensde HA graph-storage/apply/reconnect/capability-bronincrement
  onafhankelijk geaccepteerd (31HA-tests); actieve firmware/api2-/GUIverbinding
  nog open, geen volledige productfase of fysieke vrijgave afgetekend.

Bewijs: [specialistRESULT](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/RESULT.md),
[parentreview](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/PARENT-REVIEW.md),
[bronbrowser](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/RESTART-SOURCE-BROWSER.json).
Geen live herstart/flash/HA-/broker-/EMS-/Tadoactie of verwarmingsGO.

## 5. De 11 productfasen — bijgewerkt en afgevinkt waar bewezen

### F0 — basis, upstream en installatieprofiel · in_progress

- [x] WP01-bronkeuzes, builds en behoud van E32partities/locks softwarematig
  gecontroleerd; Arduino3 nu niet overgenomen, begrensde platform7.1.3/Arduino2basis [B1].
- [x] Alpha.3 op bord, beide tabs laden en instellingen behouden: door Mark
  bevestigd [B5]. Dit is operatoracceptatie van die basis, geen volledige F0.
- [ ] Volledig woning-/device-/hydrauliekprofiel en dependency-/capaciteitsacceptatie.
- [ ] Resterende fysieke netwerk/load/PSRAM/restorechecks; alpha.6-installatie en
  automatische reboot zijn inmiddels bewezen (Mark11746), niet opnieuw uitvoeren.
  De oorspronkelijke flashbackupwaiver van
  Mark blijft geldig; niet opnieuw als verplicht gebruikersbesluit opvoeren.

**Eigenaar:** firmware/OpenClaw + benodigde fysieke feiten Mark.
**Fase klaar als:** stabiele basis én werkelijk installatieprofiel bewezen.
**Volgende bewijsactie:** bestaande bordacceptatie behouden; alleen open boardchecks uitvoeren [B1,B5].

### F1 — passieve Classic-uitlezing en pariteit · in_progress

- [x] WP02 passieve Classicdecoders/capabilities, goldenframes, kwaliteit en
  veldclassificatie van 68 inventarisvelden softwarematig gecontroleerd [B2].
- [ ] Alle vereiste betrouwbare velden daadwerkelijk passief in eigen E32keten
  ontvangen/vergelijken; volledige R15-pariteit en uitleeskwaliteit accepteren.

**Eigenaar:** firmware + HA-specialist. **Fase klaar als:** vereiste pariteit en
bronkwaliteit aangetoond, niet alleen een veldlijst. **Volgende:** bestaande captures/
paritymanifest tegen een passende veilige passieve E32ontvangst toetsen [B2].

### F2 — contract en verticale shadowketen · in_progress

- [x] Versie/session/source-age/config/schema-shadowsoftware gebouwd; gezamenlijke
  host-C++/HA/MQTTproeven beschikbaar, zonder fysieke ESP32 te suggereren [B3].
- [x] Geïsoleerde native HA/Mosquitto-testinfrastructuur en HA-onboarding geverifieerd [B6].
- [ ] Echte meetbron kwalificeren, compatibele E32sessie en configACK bewijzen;
  doel/schema/expiry/reconnect in de fysieke shadowketen aantonen.
- [ ] Volledige capaciteit/powerloss/recovery op het bord aantonen.

**Eigenaar:** firmware + HA-specialist. **Fase klaar als:** echte bron→E32→ACK/status
met uitgangen uit en alle contractacceptatiechecks bewezen. **Volgende:** bronkwalificatie
en session/configACK; huidige bronroute-/ACLbeperking niet omzeilen [B6].

### F3 — HA-productintegratie en apparaatprofiel · in_progress

- [x] Native kamercreate/edit/delete, sensor-/TRV-/optionele bindingen, grenzen,
  persistente IDs en helpervrije weekeditor in test-HA GUI/API getest [B4].
- [x] Exact negen Engelse bestanden in productie-HA geïnstalleerd, configcheck
  en één Coreherstart, hashes/bindings/offstatus onafhankelijk gecontroleerd [B7].
- [x] Eerste centrale HA-configuratiebronpakket **samengevoegd in bron, niet geïnstalleerd**:
  native centrale draft-subentry, 9-puntscurve/buitenbron/stalebeleid en pure
  groep-/actuator-/mengerdeclaraties gevalideerd; 107 gerichte native tests PASS [B10].
  Status expliciet draft_not_applied; geen nieuwe actieve wirekeys/E32-uitvoering.
  Parent: 18/18 dossierhashes en exacte negen bronbestanden gecontroleerd;
  106 relevante native tests onafhankelijk opnieuw PASS (overlap, niet optellen).
  Broncommit c23bae2; review en rollback [B11].
- [x] Native gewenste graph-CRUD **samengevoegd in bron, niet geïnstalleerd**:
  groepen/actuatorverklaringen/mengerinterfaces, Save/Cancel, referenties/uitgangseigendom,
  begrensde native roomdeletecascade en echte HA-manager/Store gecontroleerd [B12].
  Volledige native suite218PASS/1broker-opt-inSKIP met bron-gematchte echte C++kern.
  Status blijft draft_not_applied; geen uitrol of wire-/hardwareprofielvrijgave.
  Parent: 21/21 dossierhashes, twaalf afterhashes en reversecheck PASS;
  volledige native suite onafhankelijk 218PASS/1broker-opt-inSKIP herhaald.
  Broncommit d9d3b00; review en rollback [B13].
- [x] Native gewenste kamers zonder verplichte TRV en expliciete mode-migratie
  samengevoegd in bron afcf2ed [B14,B15], **niet geïnstalleerd**. Oude TRV-roomvorm/IDs/
  week/bounds en shadowpayload blijven behouden; graph-only rooms blokkeren
  huidige runtime/legacy/transport vóór IO. Native manager/Store en foutatomiciteit
  bewezen; volledige suite239PASS/1bewuste brokerSKIP. Dit is geen toegepast vloerprofiel.
- [x] Concreet graph capability/revision/apply-**voorstel** en actuele firmwarebudget-
  inventaris opgeleverd [B14]; actuele TEST-WIRE/firmware ongewijzigd. De echte
  huidige C++parser weigert het nieuwe schema zonder oude config te vervangen.
- [x] Eerste onafhankelijke firmwarecontract-/budgetreview [B15]: versiegrens en
  fail-closed migratie geaccepteerd als bronbasis, niet als geïmplementeerde api2.
  31/31 dossierhashes, vijftien afterhashes, reversecheck, acht runnerbronnen/binary
  en onafhankelijke volledige239PASS/1brokerSKIP; budgetmatrix exact herhaald.
  Acht kamers×128transities overschrijdt de huidige bytes/nodebudgetten;
  geen build-/heap-/NVS-/fysieke capaciteit afgetekend.
- [x] Eerste LOSSE gedeelde graph-shadowvalidators in bronkandidaat [B16]:
  pure Python/C++,98identieke rawfixtures (6synthetisch compleet/92negatief),
  kwalificatie-/hash-/revision-/resourcebudgetchecks en echte native allocatie-
  metingen. Volledige actuele native suite346PASS/1broker-opt-inSKIP.
  Testlayout1kamer/1ongemengde vloer/1binaire klep/8transities/7streamrollen;
  geen firmwarecapaciteitsclaim. NIET geïnstalleerd/geadverteerd/aangesloten.
  r2sluit GV-R1typed-channelcontrole en GV-R2RAII-ownership af:6exacte parent-
  regressies +556echte cJSONfaultsites zonder leaks; geen partiële kandidaat.
- [x] HA-managed E32-GUIafbouw onafhankelijk geaccepteerd in bron (11785):
  35JS+21C+++2echte Chromiumbronviewports PASS; herstel/generic behouden,
  geen installatie of modemigratie op apparaat. Zie §4 en §6.
- [ ] Gezamenlijke schemas/validators/capabilityadvertentie,
  graph-storage/apply/reconnect en echte device-/veiligheidsvelden implementeren;
  graphdraftlimieten zijn geen bewezen E32capaciteit.
- [ ] Zichtbare productie-Engelse schermcontrole in bestaande ingelogde browser.
- [ ] Eén echt sensor-/actuatorprofiel en HA-doel inclusief fouten/toegepaste
  firmwarestatus aantonen; geen fysieke TRVactie geclaimd. Een wandapparaat is
  niet nodig voor deze eerste kamer. Indien gekozen, dezelfde doelwijziging en
  echopreventie van dat profiel bewijzen; R02 blijft een aparte productmogelijkheid.
- [ ] Centrale/groepsconfig met firmware-capability/revisie/applycontract verbinden;
  gewenste graph-only kamermigratie is bronwerk hierboven, ontbrekende
  veiligheids-/deviceprofielvelden en fysieke ondersteuning volgens §2/3;
  fysieke HA-managed mode-/migratieacceptatie volgens §4; bronafbouw nu geaccepteerd.

**Eigenaar:** HA-specialist, firmware voor contract/UI. **Fase klaar als:** native
bediening en werkelijke profielen met juiste single-writer/status/migratie bewezen.
**Volgende:** bestaande gedeelde validators hergebruiken voor echte samenhangende
graph-storage/apply/reconnect/readback en capabilityadvertentie; losse validators
zijn al bewezen in B16. Alleen geadverteerde capaciteit gebruiken, migratie en
foutatomiciteit controleren; bronkwalificatie en bron-/GUIacceptatie blijven open.
HA-managed E32-afbouw is in bron geaccepteerd; fysieke mode-/migratiecheck open;
browsercheck hervat bij beschikbare bestaande sessie, blokkeert bronwerk niet [B4,B7].

### F4 — regelkern en hydraulische supervisor · pending

- [ ] Moderne radiator-/vloer-/klepprofielen, waterdoelen/stooklijn per circuit,
  minimumflow, opening/readiness/start/stop/naloop/DHW en vorst/zomer bewijzen.
- [ ] Gezamenlijke vraag voor A/B/samen/allesuit en fout-/stalescenario's testen.

**Eigenaar:** firmware, onafhankelijke review HA-specialist. **Fase klaar als:**
volledige deterministische supervisoracceptatie uit PLAN§14 F4 groen; legacycurve
en shadowdoel alleen voldoen niet. **Volgende:** scenario-/contractgestuurde
software-implementatie zonder TXvrijgave [PLAN§7/14, B3].

### F5 — betrouwbare grafieken en diagnose · in_progress

- [x] F5/WP07 Plus-metricsbron hersteld en onafhankelijk geverifieerd: bootcounters,
  GET zonder reset,30sdeadline, eerdere CV/DHWintervalmode, expliciete schatting,
  floweenheden en HA-schema2/statistieklabels.9echte-parser-C+++14HAchecks PASS.
- [ ] Build/installatie, Classic-meetkwalificatie, fysieke vraag/werkelijk-tijdlijn,
  Recorderhistorie-/migratieacceptatie, CSV, omvang en mobiele grafiek-UX.

**Eigenaar:** firmware + HA-specialist. **Fase klaar als:** meet-/schatlabels en
data-integriteit met onafhankelijke verwachtingen kloppen. **Volgende:** bestaande
Recorder-/dashboardroutes en expliciete migratie van oude deltahistorie beoordelen;
onbetrouwbare vlam/gas/flow niet als feit tonen [B2, PLAN§11].

### F6 — board, bus, stop en uitval · pending

- [ ] Elektrische/interface-/bustiming en herstel, security/ACL en bekende stop
  bij HA/broker/E32-/voedingsuitval aantonen; flow/naloop/exclusieve overdracht.
- [ ] TXvrijgave alleen na eigen gereviewde bronwijziging en concrete commissioning.

**Eigenaar:** firmware + geschikte fysieke uitvoerder/Mark + onafhankelijke review.
**Fase klaar als:** alle toepasselijke P0-gates voldaan. Backupwaiver is geen
bewijs van restore; setup/OTAbronwerk is geen fysieke veiligheidstest.
**Volgende:** gerichte commissioningkaart opstellen zodra hardware/stopvoorwaarden
concreet zijn; huidige outputlocks blijven behouden [B5,B6, PLAN§12/14].

### F7 — één radiatorzone, daarna meerdere · pending

- [ ] Actuator zonder ketel bewijzen; daarna begrensde ketelstart/stop/DHW/naloop,
  echte kamerreactie en uitvalherstel onder toezicht.
- [ ] Twee→maximaal acht gekwalificeerde zones, kleinste last en 72u resourceproef.

**Eigenaar:** HA-specialist + firmware + fysieke uitvoerder. **Fase klaar als:**
alle toepasselijke P0-eisen cumulatief groen. **Volgende:** pas na F2/F3-apparaatbewijs
en F4/F6-gates een concrete éénzoneproef, geen voortijdig enable [PLAN§14 F7].

### F8 — vloerverwarming en gemengde afgifte · pending

- [ ] §3 vloer-/klep-/pomp-/mengerconfig en softwareprofielen bouwen en testen.
- [ ] Werkelijke NC/NO/looptijd/begrenzing/pompflow en gemengde radiatortemperatuur
  fysiek bewijzen, inclusief uitval en minimumflow.

**Eigenaar:** HA-specialist + firmware + installatiedeskundige waar nodig.
**Fase klaar als:** eigen vloerverwarmingsacceptatie groen, geen hernoemd radiatorprofiel.
**Volgende:** profiel-/GUIsoftware mag vóór fysieke F7 worden voorbereid; eerste
hardwarecommissie op echt verdelermodel/type, geen fictieve ondersteuning [PLAN§7.3/14 F8].

### F9 — zelfleren en optimum-start · pending

- [ ] Leren regeling, optimum-start en later optimum-stop/stooklijnaanpassing
  afzonderlijk implementeren, begrenzen, shadowreplay en modelrollback.
- [ ] Baselinevergelijking met voldoende echte data/starts, niet alleen tijd verstreken.

**Eigenaar:** firmware, HA voor opties/inzicht. **Fase klaar als:** elk geclaimd
leerniveau eigen comfort-/databewijs heeft. **Volgende:** na stabiele conventionele
regelbasis thermische replay/voorstelproeven; nog geen zelflerenclaim [PLAN§8/14 F9].

### F10 — comfortfuncties en releasekwaliteit · pending

- [ ] Away/vakantie/boost, optionele aanwezigheid, raam-open, meldingen en
  alleen ondersteunde tapwateropties stapsgewijs valideren.
- [ ] Firmware-/integratiecompatibiliteit, mobiele UX, diagnostics, migratie,
  dependency/securityreview, rollback en gebruikersproef afronden.

**Eigenaar:** firmware + HA-specialist. **Fase klaar als:** gekozen functies en
releasechecks met bewijs afgetekend; opties zonder hardware uit/unsupported.
**Volgende:** functies één voor één toevoegen na stabiele kern, niet combineren
met een brede live ketel-/vloerwijziging [PLAN§14 F10].

## 6. Werkpakketten en eerstvolgende uitvoering

Er zijn **8 oorspronkelijke werkpakketten**, niet 11; F0–F10 zijn de 11 fasen.

| WP | Softwarepositie | Wat voor volledige uitkomst nog openstaat |
| --- | --- | --- |
| WP01 | Software geaccepteerd [B1] | F0 fysieke installatie-/resourceacceptatie |
| WP02 | Passieve decoder-/inventarissoftware geaccepteerd [B2] | R15-productpariteit/live E32ontvangst |
| WP03 | Contract/source/session/schema-shadowsoftware aanwezig [B3] | Volledige fysieke bron-/config-/herstelacceptatie F2 |
| WP04 | Kamer-/week-GUI gebouwd, getest en geïnstalleerd [B4,B7] | Echte sensor/HA-doel/ACK en ontbrekende centrale/groepsprofielen F3; fysieke bediening indien gekozen, R02-profieltest apart |
| WP05 | Nog geen vrijgegeven echt remote actuatorprofiel | Readiness/echo/foutproef met echte kraan zonder ketel |
| WP06 | Volledige moderne supervisor nog open | F4-scenario's en water-/hydrauliekbeleid |
| WP07 | Volledige meetintegriteit/grafieken nog open | F5-counters/Recorder/kwaliteit |
| WP08 | Auth/setup/OTA-bronwerk en releases aanwezig [B5] | Security/ACL/HTTP/OTA/restore fysiek én credentialbeleid vóór livebedrijf |

WP05 heeft al een bewaakte, standaard niet-geautoriseerde profile-C-
`set_temperature`adapter in broncode. Die is geen bewezen werkende actuatorroute;
de shadowketen activeert hem niet. WP06 heeft eenvoudige gesimuleerde hysterese,
niet de volledige moderne hydraulische supervisor. WP08-bronwerk omvat de
eerdere testtoegangsbeleidkeuze; toegangsbeleid moet voor livebedrijf expliciet
worden beoordeeld, niet door “auth aanwezig” stilzwijgend worden afgetekend.

Afzonderlijk open updaterprobleem Mark11584: eerste updatepoging verliest volgens
Mark verbinding; controleren versus installeren/fout/reset is nog onbekend,
melding niet gereproduceerd. Niet mengen met de alpha.4-autorebootherstelling of
als nieuw bewezen TLS/heap/radioprobleem presenteren.

Uitvoeringsvolgorde na deze reconciliatie:

1. Eén duidelijke HA-configstructuur en HA-managed E32afbouw als begrensde
   bronpakketten; labelverbetering, centrale weersinstellingen, afgiftegroepen en
   expliciete actuatorprofielen, ieder met contract/acceptatiecheck.
2. Bestaande éénkamer-bronkwalificatie en E32-session/configACK-shadowketen
   hervatten; bron-/ACLbeperking of benodigde apparaatinteractie concreet houden.
3. Werkelijk actuatorprofiel zonder ketel; supervisor en uitval-/veiligheidsgates.
4. Begrensd radiatorbedrijf; vloer-/regelklep/menger daarna eigen fysieke proef.
   Onafhankelijke vloer-/GUIsoftware hoeft niet op die fysieke proef te wachten.
5. Volledige grafieken, zelfleren en comfortfasen volgens hun eigen gates.

### Voortdurende uitvoering — opdracht Mark11785 (20okt23:28CEST)

Mark: "Werk desnoods heel de nacht door maar voer alle punten uit van ons hele plan."
Deze opdracht geldt voor het gehele bestaande PLAN (31eisen/F0–F10), niet alleen
de herstartknop. Werk alle uitvoerbare software-/integratie-/test-/releasevoorbereiding
af; één geblokkeerde fysieke proef blokkeert geen onafhankelijk softwarepakket.
Geen garantie dat fysieke of meerdaagse acceptatie in één nacht haalbaar is.

- Eigenaar uitvoering HA/apparaat: bestaande specialist agent:home-assistant:main;
  parent OpenClaw: onafhankelijke review, samenvoeging en bewaking van ditzelfde bord.
  Niet gelijktijdig dezelfde bestanden door andere workers laten aanpassen.
- Doorloop de bovenstaande werkvolgorde en vervolgens ALLE nog open F0–F10-eisen:
  HA-managed opschoning, werkende contractketen, profieladapters/supervisor,
  grafieken/dataintegriteit, uitvalbeveiliging, vloer/klep/menger, begrensde
  learning/optimumstart en comfort/releasekwaliteit. Concrete implementaties en
  passende fout-/migratie-/integratieproeven; geen reeks losse voorstellen als eindresultaat.
- Herstartbron039e567 is al samengevoegd en onafhankelijk geverifieerd:27JS,
  20C++,desktop+mobielbronpreview. Niet opnieuw bouwen/testen zonder relevante wijziging.
  E32build/installatie en ingelogde voor/naprofilering zijn nog open; bestaande
  volle sessies niet opnieuw vullen, geen aanmeld-/CSRFomweg introduceren.
- Lees bij hervatting memory_search en dit bord/PLAN plus het actuele RESULT van
  specialist; hervat actieve uitvoering, start geen tweede concurrerende eigenaar.
  Bij een gereed codepakket: review diff en gerichte passende tests, samenvoegen,
  dit bord bijwerken en meteen volgend uitvoerbaar pakket oppakken/delegeren.
- Native OpenClaw Automation borgt nachtelijke hervatting; geen scripts/watchers/
  extra schedulerlaag. Automations vóór wijzigen inspecteren en bestaande jobs
  behouden. Hervattingsjob stopt zichzelf zodra alleen externe/fysieke bewijschecks
  overblijven of het geheel echt voltooid is; geen herhaalde groene checks als werk.
  Job-ID: `72ec7e68-5c8f-4203-9f0c-fb11fa92e8bf`, standaard30min, adaptief15–60min;
  lokale officiële CLIroute met expliciete beperkte toolset, adminreview en
  aflevering in dezelfde gesprekroute. Headless hosttoegang is echt bewezen;
  eerdere account-bound proef490a63dc miste shelltoegang en is verwijderd.
  [Configuratie-/uitvoeringsbewijs](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/NIGHT-EXECUTION.md).
- Fysieke proeven, powerloss/restore/72u/echte woningrespons en verwarming/TXvrijgave
  blijven gebonden aan de oorspronkelijke PLANgates. Geen onbewezen actieve
  ketel-/klep-/Tado-/EMSoverdracht tijdens de nacht. Markeer gebouwd, geïnstalleerd
  en fysiek bewezen afzonderlijk; test-/appauthproblemen niet omzeilen.
- Bewaar codecommits/diffs, reproduceerbare checks en rollback per pakket. Stop
  een foutpad met concreet bewijs en ga naar onafhankelijk werk. Geen nieuwe
  betaalde diensten, corepatches of algemene nieuwe akkoordvragen voor routinebronwerk.
- Werk 's nachts stil door; meld een substantieel opgeleverd pakket of werkelijk
  onvermijdelijke blokkade compact. Geen bericht voor alleen "nog bezig".

Bestaande softwareautorisatie blijft geldig en is door11785 bevestigd; fysieke
vrijgavevoorwaarden blijven onderdeel van het plan, geen nieuw algemeen akkoord.

### Mark11774/11785 — graph native Store/apply/readback-bronincrement

- [x] Native HA Store-journal: immutable mapping+config atomair staged vóór expliciete
  single-send, volledige gedeelde validator en caller-owned kwalificatieanchor.
  Eén Store/lock per entry, geen listener/worker/extra service.
- [x] Strikt api2 shadow_graph-contract: exacte testcapabilities/limieten,
  boot/session/grant/revision/mapping/configtuple, niet-retained ontvangst <10s,
  boiler/actuatoroutputflags false. Huidig api1 wordt geweigerd vóór opslag/verzending.
- [x] ACK is geen applybewijs; verse exacte bekende readback promoveert staged.
  Verloren ACK/restart/reconnect herstellen geen admission uit opslag. Onbekende
  remoteconfig wordt conflict, nooit automatisch overschreven/geadopteerd.
  Sessiewissel tijdens Store-await en verlopen capability vóór send blokkeren.
- [x] 31 gerichte native HA-checks PASS:30 Store/lifecycle/negatieve scenario's
  en1 actieve-runtimegrens. Echte HA2026.10.2 Store, afzonderlijke disk-readback,
  geen broker/device/netwerk. Schrijffout incl ambigu gecommitteerde save,
  corrupte/legacy/futurejournal, parallel conflict en uitval failclosed.
- [ ] Nog NIET: api2-wire/runtime-adapterverbinding, GUIapply, firmware-NVS/
  heap/stack/powerloss/budgetproef, capabilityadvertentie en profieladmission.
  Dit is een afgebakende HA-transactie-implementatie, niet de gehele F2/F3.
  Actieve api1runtime, HAconfig/broker en alle fysieke/TX/EMS/actuatorgates blijven.
- Bewijs/patch: gedeeld dossier open-thermostat-restart-graph-11774-20261020,
  GRAPH-RESULT.json en graph-only-core.patch. Parent behoudt actuele canonieke
  WORKBOARD/PLAN en voegt dit resultaat toe; geen oude headers terugzetten.

#### Onafhankelijke parentacceptatie en echte nachtuitvoering

- [x] Canonical hostcheckout op36b10ea schoon vóór wijziging; date -Is en volledige
  HEAD werkelijk geschreven in NIGHT-RUNTIME-CHECK.txt. WORKBOARD§6, PLAN-gates en
  actuele specialistRESULT daadwerkelijk gelezen; geen cronstatus als bewijs.
- [x] Exact graph-only-core.patch SHA256
  7789848b487603f5ed6228d5f35f8df764c1a8e5030301d3ac0ca2b92d3bee37 gereviewd.
  Definitieve specialistcommit e4b4b09 (RESULT noemt nog voorganger94cfbf6);
  alle drie bronhashes matchen GRAPH-RESULT.json. Parent voert vanuit canonical
  checkout31 gerichte HA2026.10.2/Python3.14.8-tests zelf uit:31PASS,
  vijf bestaande dependencydeprecatiewaarschuwingen. Geen broker/device/netwerk.
- [x] Bronpakket samengevoegd via afzonderlijke branch; geen actieve runtime-import,
  api1writer-, firmware-, productieHA- of fysieke wijziging. Rollback: alleen deze
  graphbroncommit terugdraaien; geen bestaande configuratie/journal aangeraakt.
- Bewijs: [hostreceipt](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/NIGHT-RUNTIME-CHECK.txt),
  [parentreview](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/GRAPH-PARENT-REVIEW.md),
  [native testresultaat](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/GRAPH-PARENT-NATIVE.xml).
- Eerstvolgende uitvoering: bestaande specialist is actief aan F5 EMS metrics:
  GET mag counters niet resetten; stale-powerdeadline, flow/volume en expliciete
  schattings-/Recordersemantiek. Parentreview zodra pakket gereed; daarna F4/WP06
  supervisorbron met readiness/postrun/limieten en reproduceerbare foutreplay.
  Hele11785 blijft gelden; geen tweede eigenaar en geen herhaling restarttests.
- Huidige hosthervattingsjob:72ec7e68-5c8f-4203-9f0c-fb11fa92e8bf;
  bronreview afgerond → volgende check15min. Eerdere490a63dc-config hierboven is
  historisch configuratiebewijs, geen bewijs van uitvoeringssucces.

### Mark11785 — F5 meetintegriteit: bronincrement

- [x] Exacte alpha.6-bronreproductie: tweede GET wist0.033333kWh naar0,
  gemiddelde waterflow retourneerde0 bij1.2L/min, één uur zonder nieuw
  vermogensbericht telde12kWh door. Native parser/monotone testklok, geen liveproef.
- [x] Bestaande EMS-metricspad hersteld: observation-driven bootcounters,
  read zonder reset/actualiteitsverlenging,30sdeadline, eerdere intervalmode,
  geen energie zonder nominale factor én verse betrouwbare Plusvlam/power;
  exclusieve CV/DHWsplitsing met unattributedrest, echte floweenheden/gemiddelde.
- [x] Echte nul versus unknown/null, sentinels/fragments/adres/dataoperation/
  stale/boundedgap/clockbackwards;9native C++checks met echte parser PASS.
  14actuele HAchecks: stabiele IDs, expliciete schattingslabels, bootreset/
  total_increasing en schema2grens; geen oude delta als nieuwe cumulative.
- [ ] Nog open: Classic onbetrouwbare vlam/flow NIET opgewaardeerd,
  meter-/fysieke tijdlijn-/CSV-/recorderomvang-/mobiele grafiekacceptatie,
  firmwarebuild/installatie; onafhankelijke bronreview is nu PASS.
- Bronpatch/evidence: metrics-only-core.patch / METRICS-RESULT.json in11774dossier.
  Geen live HArecorder-, configuratie-, TX-, boiler- of apparaatwijziging.

#### Onafhankelijke parentacceptatie F5/WP07

- [x] Exacte patch f18057419e7c18431bac93c420444ac784f19f198ef26a65118a6185e7c3a4a4
  en alle7niet-WORKBOARDbron-/dochashes tegen METRICS-RESULT.json gecontroleerd.
- [x] Vanuit canonical checkout werkelijk opnieuw gecompileerd met hostg++ en echte
  EMSparser:9PASS; nieuwe metricscode -Wall/-Wextra/-Werror schoon. Bestaande
  parserwaarschuwingen apart behouden. Native HA2026.10.2/Python3.14.8:14PASS,
  vijf bestaande dependencydeprecaties. Geen netwerk/device/HAproductieactie.
- Bewijs:11774dossier METRICS-PARENT-COMMANDS.json, METRICS-PARENT-NATIVE.json,
  METRICS-PARENT-HA.xml en NIGHT-PACKAGE-REVIEW.md. Rollback: alleen deze
  metricsbroncommit terugdraaien; geen bestaande Recorderdata/config gewijzigd.
- CONTROL2285b8e nog niet geaccepteerd: eigen probe toont onbegrensde pump_wait
  zonder flow en verdwijnen van gevalideerd nalooppad bij boilerFault. Exact bewijs
  CONTROL-PARENT-REVIEW-PROBES.json; correctie als nieuwe informatie aan actieve
  bestaande specialist gestuurd, admission steered is geen correctie/completion.
- Eerstvolgende parentactie: HA-managed GUIce461a2 onafhankelijk bronreviewen;
  specialist werkt eigen volgende F4/F8/F9software af en herstelt controlpakket.
  Hele11785 en alle fysieke gates blijven open.

### Mark11785/11778 — HA-managed nativeGUI-afbouw + gerichte requestreductie

- [x] Exacte editor/routekaart HA-MANAGED-GUI.md; kamers/programmas/curve/
  hardware verborgen in werkelijk runtime shadowmode; legacy/generic behouden.
  Netwerk/setup/MQTT/OTA/reboot/herstel blijven ook zonder statusprobe bereikbaar.
- [x] Bestaande backend singlewriter/CSRF/update/boardlocks behouden; legacyweer
  hidden/disabled en opgeslagen object/afwezigheid behouden bij netwerksave.
  /config/device blokkeert gewijzigde verborgen weather na secretmerge.
- [x]35echte JSchecks en21nativechecks PASS, incl onbekendemode/recovery,
  verouderde poll/navigatierace, lazydependencyfailure en configbehoud.
- [x] Aangetoonde onnodige startupdependency: Chart69199gzipbytes alleen voor
  curve; nu op expliciet verzoek, deduplicatie en navigatiegrens.
  Exacte byte/nettovergelijking MANAGED-GUI-PERFORMANCE.json.
- [x] Onafhankelijke nieuwe echte Chromiumbronpreview vanuit canonical checkout,
  desktop/mobileviewport PASS;8startupresources, geen Chart tot expliciet verzoek,
  exact1lazyChartrequest, restart/CSRF/cancel/busy behouden en geen pageErrors.
  MANAGED-GUI-PARENT-SOURCE-BROWSER.json; geen apparaatverkeer/aanmeldingen.
- [ ] Live ingelogde TTFB/render/navigation/polls, fysieke modemigratie/
  instellingen/Marktelefoon, normale build/release/installatie blijven open.
  Geen subjectieve snelheidsclaim; oude source9resources79/65ms is GEEN E32tijd.

#### Onafhankelijke parentacceptatie GUI11785/11778

- [x] Exacte corepatch cb89e4decfb3dde2c662cb0e0dd2f4b2d159fa697921ae37de9da61c1bcd39e4,
  alle9niet-WORKBOARDbron-/dochashes vóór parentdocaanvulling matchen manifestce461a2.
  Targeted hercompile met hostg++/echte cJSON21PASS; daadwerkelijke geleverdeJS35PASS.
- [x] Voor/na startupbronbytes:37226→40900HTMLbytes,69199gzipbytes Chart uit
  startup; netto65525bronbytes minder,9→8geïntercepteerde browserresources.
  DCL75.1/56.6ms in deze bronpreview is GEEN representatieve E32latency of
  bewezen liveverbetering. MANAGED-GUI-PARENT-PERFORMANCE.json bewaart exacte scope.
- [ ] Huidige ingelogde E32voor/nameting, build/installatie, modewissel/reboot/
  fysieke telefoon en gehele F3acceptatie blijven open; sessielimiet niet omzeild.
- Bewijs: NIGHT-PACKAGE-REVIEW.md, MANAGED-GUI-PARENT-COMMANDS.json,
  MANAGED-GUI-PARENT-NATIVE.json, MANAGED-GUI-PARENT-JS.tap en bronbrowserJSON
  in hetzelfde11774dossier. Rollback alleen deze GUIbroncommit; geen liveconfig gewijzigd.
- Volgende uitvoering: actieve bestaande specialist voltooit eigen emitter/learningwerk
  en concrete CONTROLreviewcorrectie; daarna F5native dashboard/Recorder-/CSV-/
  migratiekwaliteit. Parentreview zodra concreet pakket gereed; volgend check15min.
  Hele11785 blijft gelden; geen tweede eigenaar of algemene herbevestiging.


### Mark11785 — F4/F6 gecorrigeerde supervisor: onafhankelijke bronacceptatie

- [x] Verworpen CONTROL2285b8e niet samengevoegd; exacte gecorrigeerde rollup
  91fe2f33966b5d7745e8a9dc5f0de5e74e03a506c64b434f1c929b0576c16df4
  gereviewd. Expliciete withdrawalpolicy per oorzaak, begrensde flow-/pompwait,
  geen verlenging van eerste naloopdeadline of herleving van ingeperkte intentie.
- [x] Originele twee parentfoutsequenties onafhankelijk opnieuw gecompileerd:
  na1uur zonder flow fault/pump0/heat0; bij boilerfault heat0/open1/pump1
  uitsluitend met nieuwe expliciete synthetische gekwalificeerde nalooppolicy.
- [x] Canonical hostg++ -Wall/-Wextra/-Werror, echte cJSON/ShadowController:
  50gerichte nativechecks PASS inclusief aansluitend emitterpakket; tellingen
  overlappen eerdere pakketten.14native HA2026.10.2-wireinteropchecks PASS
  tegen nieuw gecompileerde actuele firmwarecore, netwerk verboden;
  vijf bestaande dependencydeprecaties. Alle9bron-/testhashes matchen manifests.
- [x] Werkelijke api1 gebruikt baselinehysterese, wist regelgeheugen bij reconnect
  en toont requested_heat afzonderlijk van hydraulic_profile_unqualified.
  Alle fysieke outputflags false; geen profieladmission/driver/TXcapability toegevoegd.
- [ ] Volledige F4/F6 blijven open: graph/wireprofielselectie, lage-last-/vorst-/
  zomerbeleid, E32build/resources/installatie, minimumflow/stop/powerloss en
  fysieke veilige mapping/naloopacceptatie. Dit is alleen bronacceptatie.
- Bewijs11774dossier: CONTROL-EMITTER-PARENT-HASHES.json,
  CONTROL-EMITTER-PARENT-COMMANDS.json / NATIVE.json,
  CONTROL-PARENT-CORRECTED-PROBES.json, CONTROL-PARENT-INTEROP.xml;
  ontwerpgrenzen in MODERN-CONTROL.md en SUPERVISOR-CORRECTION.md.
  Rollback alleen deze nieuwe controlbroncommit, geen runtime/configdata gewijzigd.
- Eerstvolgende onafhankelijke bronacceptatie: F4/F8 water-/vloer-/mengerpakket
  in dezelfde reviewbranch; specialist blijft eigenaar van actieve F9uitvoering.


### Mark11785 — F4/F8 water-/vloer-/mengergroepen: onafhankelijke bronacceptatie

- [x] Exacte emitter-after-control-correctionpatch
  9f07682e247a824c97f1fc4def24a0812c19eaafa788c34e2883f60e12e36156
  gereviewd, bron-/testhashes tegen finale manifests gecontroleerd.
- [x] Centigraadstooklijn met begrensde kamercorrectie, hoogste werkelijk vragende
  groep, geen permanente minimumvraag; expliciete fallback, positieve writebudget/
  deadband/slew en onbelemmerde stopintentie. Iedere geconfigureerde vloer telt
  mee voor meng-/shared-low-limitbarrière, ook met gesloten/inactieve klep.
- [x] Synthetisch gekwalificeerde driepunts-/0–10Vmengerpolicy: veilige referentie,
  verse postcommand-eindschakelaar of expliciet getoetste tijdreferentie, exclusieve
  richtingen/deadtime/travelgrens; analoge gekalibreerde eindpunten, één pending
  intentie, passende verse feedback en timeout. Geen NCNO-/spanningsaanname.
- [x]15gerichte groeps-/menger-/postcommandchecks als deel van dezelfde50native
  parentchecks PASS; geen tweede onafhankelijke50claim. Native hostcompile schoon.
- [ ] Nog geen actieve graph/api1profielselectie, driver/actuatorownerreconciliatie,
  E32build/resource/installatie of fysieke vloer-/water-/menger-/high-limitproef.
  F4/F8 blijven open; fysieke outputs niet vrijgegeven en geen verwarmingsGO.
- Bewijs: dezelfde CONTROL-EMITTER-PARENT-*.json/logs en
  EMITTER-WATER-MIXER.md. Rollback alleen deze emitterbroncommit;
  daarna zo nodig voorafgaande controlcommit. Geen productie-/apparaatwijziging.
- Volgende uitvoering: bestaande specialist voltooit F9model/persistentie/replay;
  reeds aangeboden F5dashboard/Recorder/CSV/migratie volgt daarop. Daarna volgende
  nog open uitvoerbare F2/F3/F10software, niet stoppen bij deze bronpakketten.
  Parentreview zodra concreet pakket gereed; volgende hervattingscheck15min.

### Mark11785 — F2/F3 firmware graphtransactie: onafhankelijke bronacceptatie

- [x] Exacte firmware-graph-only-core.patch SHA256
  9ed3ce2e6171b4390814a6d7168d27484dc482f06c574ced3777b0210e9d9893
  onafhankelijk gereviewd; alle9 niet-WORKBOARDbron-/test-/dochashes matchen
  GRAPH-CONFIG-RESULT.json c1a1ada. Canonical prechange ad20d66 schoon.
- [x] Bestaande ControlStore/SessionAdmission/gedeelde validator hergebruikt:
  config+mapping+digest+owner+controller+schema in één tuple maximaal4096bytes;
  exacte readback vóór geheugenpromotie. Drift/ambiguous-save/hash-/schema-/
  klokfout blokkeert admission; restore herstelt alleen data, geen grant/lease.
- [x] Werkelijke canonical hostg++17 -Wall/-Wextra/-Werror, echte cJSON/OpenSSL:
  33nativechecks PASS (9graph +11admission +13actieve api1regressies).
  HA2026.10.2/Python3.14.8:34PASS (3echte C++/native Storeinterop +30journal
  +1runtimegrens),5bestaande dependencydeprecaties. Geen broker/device/netwerk.
  Eerste HAaanroep gebruikte ongeldige sandboxvenvsymlink; daarna bestaande
  bewezen hostinterpreter/sitepackages gebruikt, zonder installatie/wijziging.
- [ ] F2/F3 blijven open: alleen synthetisch1kamer/1vloer/1actuator-testprofiel,
  niet actieve ModernTransport/api2selectie/capadvertentie, uitvoerende profielen,
  NVSkey/ESPheap/stack/powerloss/build/installatie of nativeGUIapply.
  Default SessionAdmission blijft major1; alle fysieke outputflags false.
- Bewijs in11774dossier: GRAPH-CONFIG-PARENT-PRECHANGE.json, COMMANDS.json,
  HASHES.json, BUILD.log, NATIVE.json/log, HA.xml/log en REVIEW.md.
  Rollback uitsluitend nieuwe graphbroncommit; parentdocs en runtimedata bewaren.
- F5presentatie2fb7780 NIET samengevoegd: chartgating/Repairs alleen is geen
  isolatie van historische statistiekdefinities. Actieve specialist werkt aan
  expliciete V2entity-/Discovery-/wirevelden en behoud oude registry/history.
  Eerdere geaccepteerde broncounters/stabieleIDs betekenen dus GEEN veilige
  historiekmigratie; geen productie-uitrol of datavervuiling geclaimd/geconstateerd.
- Eerstvolgende review: die concrete F5V2correctie inclusief echte SQLite-
  isolatieproef. Reeds aangeboden F2/F3api2transport-/nativeGUI-integratie blijft
  daarna van dezelfde specialist; geen dubbele eigenaar of redundant werkdoorbericht.
  F9cooling/coast/curve/shadowreplay volgt als afzonderlijk softwarepakket.
  Hele11785 blijft actief; volgende hervattingscheck15min, fysieke gates intact.

#### Postcheck en concrete voortzetting graphparentmerge

- Canonical graphbroncommit0e74c68 via afzonderlijke branch fast-forward
  samengevoegd; gitstatus leeg en commitdiffcheck PASS. Bewijs:
  GRAPH-CONFIG-PARENT-POSTCHECK.json, bronchecks33native/34HA geslaagd.
- Volgende zelfstandige F9cooling/coast/optimum-stop/stooklijnadvies-/replay-
  opdracht met acceptatie, standaarddisabled en rollback aan dezelfde specialist
  aangeboden, ná huidige F5V2correctie en al aangeboden graphtransport/GUIwerk.
  Run85c54586-79bf-4dc6-a884-1d4b65b70e42 QUEUED, geen completionclaim.
- Hervatting15min bevestigd; uitvoerbare softwarechecks blijven open, dus eigen
  job72ec7e68-5c8f-4203-9f0c-fb11fa92e8bf behouden. Niet geïnstalleerd;
  geen productieHA-/apparaat-/TX-/EMS-/actuator-/verwarmingsvrijgave.

### Mark11785 — F9 thermisch model/optimum-start: onafhankelijke bronacceptatie

- [x] Exacte thermal-only-core.patch SHA256
  1960714a2af927d9cdfe1b191238fb572cfa44c30500ac96eea3bdc57c6a4831
  gereviewd; alle6 niet-WORKBOARDbron-/dochashes matchen9281d15.
- [x] Vanuit canonical checkout werkelijk hostg++17 -Wall/-Wextra/-Werror,
  echte cJSON/ShadowController en bestaande OpenSSL libcrypto.so.3:32PASS
  (19model/opslag +13runtime). Geen nieuwe dependency geïnstalleerd.
  Eerste linkpoging miste alleen ongeversioneerde -lcrypto developmentlink;
  bestaande versiegebonden library expliciet gelinkt, geen bronwijziging.
- [x] Standaarddisabled, frozen/shadowadvies;16begrensde runs, minimaal6starts/
  6dagen/14dagenspan en vergelijkbaar weer/water/kamertemperatuur; robuuste
  mediaan, geen extrapolatie buiten gemeten stijging of emittervoorlooptijd.
  Replay-/klok-/gap-/targetfences, afzonderlijke modelcodec max426bytes,
  expliciete30mincheckpoints, ambiguous-save/storagefault failclosed.
- [ ] F9 blijft open: actieve graph/wire/model-owner, HAcontrols/status, echte
  key-/E32resourceacceptatie, cooling/coast/curve en representatieve
  baseline/comfortreplay plus werkelijke14dagenobservatie. Tests zijn synthetisch.
  Geen runtime-instantie/capadvertentie, installatie of verwarmingsvrijgave.
- Bewijs11774dossier: THERMAL-COMFORT-PARENT-PRECHANGE.json,
  THERMAL-PARENT-COMMANDS.json, THERMAL-PARENT-BUILD.log/NATIVE.json/log.
  Rollback uitsluitend deze thermalbroncommit terugdraaien; geen runtimedata
  gewijzigd. Eerstvolgende parentactie: comfort-targetpakket onafhankelijk
  toetsen; bestaande specialist voert overige11785software/releasewerk uit.


### Mark11785 — F10 comfortdoelbeleid: onafhankelijke bronacceptatie

- [x] Exacte comfort-target-only-core.patch SHA256
  3c0fe1c2622e769c1fb83eff712869868f3fbe334c1c16e13b4624b4f42fe49e
  gereviewd; alle4 niet-WORKBOARDbron-/dochashes matchedenef91f12.
  Werkelijke api1 automatische/tijdelijke/offdoelselectie gecentraliseerd
  met behoud van bestaande wire-/owner-/outputgrenzen.
- [x] Nieuwe pure profielgekwalificeerde boost/away/vakantie/presence/window-
  policy is NIET geadverteerd/toegelaten via huidige api1/HA-GUI. Raam-open/
  unknown blokkeert boost; ownerloss wist override; monotone/UTCafloop en
  klokterugloop kunnen verlopen override niet herleven.
- [x] Canonical hostg++17 strict:41PASS gecombineerd (19thermal +9comfort
  +13echte ShadowControllerregressies; overlap, niet optellen bij32).
  Nieuwe actuele firmwarecore hercompileerd voor native HA2026.10.2:
  14wireinteropPASS, vijf bestaande dependencydeprecaties; geen netwerk/device.
- [ ] F10 blijft open: actieve graph/wire/HA-GUIfeatureketen, profielen/
  aanwezigheid/raam/telefoonacceptatie, overige comfort-/DHW-/releasekwaliteit.
  Dit is bronacceptatie, geen nieuwe fysieke output/installatie/vrijgave.
- Bewijs11774dossier: THERMAL-COMFORT-PARENT-COMMANDS.json,
  THERMAL-COMFORT-PARENT-NATIVE.json/log, COMFORT-PARENT-INTEROP-COMMANDS.json
  en COMFORT-PARENT-INTEROP.xml/log. Rollback alleen deze comfortbroncommit.
  Eerstvolgende actie: test-only thermal-nativecompatibiliteitsaddon toetsen
  zonder nieuwe cryptoheaders/linkerinstallatie; gereed F5presentatiepakket
  daarna onafhankelijk reviewen. Specialist blijft actieve uitvoeringseigenaar.


#### Thermal native-testcompatibiliteit — afzonderlijk geaccepteerd

- [x] Test-only thermal-native-test-compat.patch SHA256
  51822692bc9d03fea6291d6e07a6231e0e65e0cb0d544dfcaa9d8db40f4185c8
  gereviewd; definitieve testhash matchtbcb0263a. Bestaande ControlTestHash
  gebruikt echte SHA256 via al aanwezige libcrypto.so.3 en behoudt known-answer.
- [x] Canonical strict hercompile ZONDER OpenSSLheaderpad of -lcryptolink:
  41thermal/comfort/runtimechecks PASS. Reproduceerbaar bewijs
  THERMAL-COMPAT-PARENT-COMMANDS.json, BUILD.log en NATIVE.json/log.
  Geen cryptokopie, nieuwe dependency, firmwarecode of actieve runtimewijziging.
- [ ] Normale volledige PlatformIO-/generic-/E32releasebuild blijft afzonderlijk
  te bewijzen; deze gerichte nativecheck is daarvoor geen vervanging.
  Rollback uitsluitend deze test/doccommit.
- Volgende parentreview: gereed METRICS-PRESENTATION-RESULT.json2fb7780,
  echte native HA-/SQLite-export/migratiechecks; geen productieRecorderwijziging.
  Specialist blijft overige11785software afwerken, inclusief actieve contract-/
  productintegratie en resterende F9/F10/releasechecks. Hele plan blijft actief.


#### Vervolg na thermal/comfortparentmerge

- Canonical broncommits4732e33(thermal),0754e4e(comfort),5608478(testcompat);
  schone technische postcheck vastgelegd in THERMAL-COMFORT-PARENT-POSTCHECK.json.
- Aan dezelfde specialist concrete volgende F2/F3opdracht aangeboden: graph
  Store/apply/readback naar begrensde api2-shadowtransport-/nativeGUIketen,
  gedeelde HA+firmwarefixtures voor persist/readback/boot/session/conflict/
  reconnect/foutinjectie. Geen nieuwe outputvrijgave of live-uitrol.
  Followupbc9fe561-ea98-46e8-950b-9d781e386e4e is QUEUED, geen completionbewijs;
  bestaand actief pakket niet onderbroken. Acceptatie/rollback meegegeven.
- Parent reviewt eerst gereed F5metrics-presentatie2fb7780. Eigen hervattingsjob
  behoudt opdracht11785; volgende check15min bevestigd. Softwareplan NIET klaar;
  fysieke gates blijven ongewijzigd, dus job niet verwijderd.

### Mark11785 — F5 grafieken/CSV en expliciete statistiekdefinitie-V2: onafhankelijke bronacceptatie

- [x] Exacte presentatiecorepatch1ab056c4e58bc2aa380148f10ca3c33ace1d0b1805ad7fabfbe50d3dda5cce5c
  en verplichte V2correctie7c6fb051a955a7d7c4fc619ecd86644e7e1c522b2b2d694e2d75f46b49f2dcdc
  samen gereviewd. Alle17 finale niet-WORKBOARDbron-/dochashes matchen manifests;
  corepatches laten docs weg, daarom docs uit exacte immutable specialistcommits
  gehaald en gehasht, niet uit de actieve mutable kandidaat.
- [x] Nieuwe JSONvelden én nativeHA-/Discoveryidentiteiten explicietV2; oude
  rootvelden null, oude eigen registryidentiteiten unavailable/zonder state_class,
  geen alias naar nieuwe getallen, geen wissen/backfill/automatische migratie.
  Oude behouden Discoverytemplate krijgt native unknown, niet fallback0.
  Alleen V2aggregaten; energie, water en gerapporteerde vlamtijd apart.
- [x] Bestaand opt-in dashboard vijf nativeviews met gemeld/doel/schatting apart;
  admin-only responseCSV via native Recorder:24u/64eigen entities/5000rijen/1MiB,
  UTC, formules escaped, zonder attributen/bestanden/DBwrites en expliciete truncatie.
  Native Repairs en unload/lifecycle; eigen gebruikersdashboards niet aangepast.
- [x] Vanuit canonical checkout werkelijk hostg++17/echte EMSparser:10nativePASS;
  nieuwe metrics/tests strict schoon, bestaande parserwaarschuwingen apart bewaard.
  Native HA2026.10.2/Python3.14.8:45PASS, vijf bestaande dependencydeprecaties,
  geen skips. Echte tijdelijke SQLiteRecorder, oude/nieuwe histories, registry,
  adminauth, retainedTemplate/null en CSVchecks; netwerk in HAfixture verboden.
  Tellingen overlappen eerdere pakketten, niet optellen.
- [ ] F5 nog open: actieve shadowtelemetry/Sensorplatform (bestaande specialist
  actief), echte Lovelace-/telefoonvisuals, firmwarebuild/resources/installatie,
  live retentie/DBgroei/timing en fysieke CV/DHW-/Classic-/meterkwalificatie.
  Geen productiehistoriek onderzocht of datavervuiling geclaimd; geen deployment.
- Bewijs11774dossier: METRICS-V2-PARENT-REVIEW.md, HASHES.json, COMMANDS.json,
  PARSER.log/COMPILE.log/NATIVE.json/log en HA.xml. Eerste testaanroep gebruikte
  sandboxvenvsymlink en kon niet starten; bestaande bewezen hostinterpreter met
  sitepackages hergebruikt, geen runtime/dependency gewijzigd.
- Rollback uitsluitend gecombineerde nieuwe broncommit vóór installatie; geen
  runtimedata gewijzigd. Na toekomstige uitrol beide namespaces bewaren en
  eventuele rollback-/historiekdefinitie afzonderlijk beoordelen.
- Eerstvolgende actie: actuele read-only ModernTransport/Sensorplatformsoftware
  onafhankelijk reviewen zodra gereed; reeds aangeboden F2/F3graphtransport/GUI
  en F9coast/curve/replay blijven dezelfde eigenaar. Daarna F4/F6lage-last-/vorst-/
  zomerbeleid als defaultdisabled/shadowbron met foutreplay; fysieke gates intact.
  Hele11785 blijft actief, hervatting15min; softwareplan niet voltooid.

#### Postcheck en voortzetting F5V2parentmerge

- Canonical70fae7b via afzonderlijke reviewbranch fast-forward samengevoegd;
  gitstatus leeg, commitdiffcheckPASS. METRICS-V2-PARENT-POSTCHECK.json bewaart
  exacteHEAD en bron-/testscope;10native/45HA, niet geïnstalleerd.
- Concrete volgende F4/F6/R22-R23lage-last-/vorst-/zomerpolicyopdracht met
  negatieve replayacceptatie/defaultdisabled/shadow/rollback aan dezelfde
  specialist aangeboden na huidig telemetry-, graph- en modelwerk.
  Followup4c42c030-46fd-4dbd-801d-b54fd8c3339e QUEUED; geen completionbewijs.
- Automations next_check15m bevestigd. Hele11785software nog open; eigen job
  behouden, geen nieuwe eigenaar/watcher, alle fysieke gates ongewijzigd.

### Mark11785 — F5 actieve read-only metrics en F2/F6 grantjitter: onafhankelijke bronacceptatie

- [x] Exacte metricscorepatch647877d87b9d8f7df03c3c4981c485d60c5852e2603eb07d6be6c8a3f7f5d168
  en grantcorepatcha1a379da91b852294ccd8b3eefe0be6191c24ae7c0beb93b51da5576e3000dd9
  gereviewd; alle20finale niet-WORKBOARDbron-/dochashes matchen manifests.
  Canonical0b9217e vooraf schoon; bronpakketten via afzonderlijke reviewbranch
  fast-forward samengevoegd: metrics5d087c0, grantc2470a5, testbarrièree809264.
- [x] Bestaande ModernTransport/client/queue hergebruikt: vaste V2snapshot maximaal
  2048bytes/30s; actuele sessie/config/grant/sequence vereist, geen retained/replay.
  Native Sensorplatform/opt-in dashboard via bestaande lifecycle;45sreceiptverval,
  geen statewrites op ongewijzigde2spolls. Geen bron-/model-/regelkwalificatie of
  leaseverlenging door meetdata; raw/Classicpariteit blijft afzonderlijk open.
- [x] Aparte capabilitygerichte grantcorrectie: alleen NIEUWE geaccepteerde heartbeat
  levert eenmalige nonce voor volgende geplande grantrotatie. HA bewaart maximaal8
  oorspronkelijke verzendtijden, geen receipt+10verlenging. Oude peers behouden
  conservatieve fallback; duplicate/expired/foreign/reorderedproofs verlengen niet.
  De OPENjitterbevinding in MODERN-METRICS.md is historisch op oude bron;
  opvolging en nieuwe grenzen staan in GRANT-NONCE.md, geen liveprobleem geclaimd.
- [x] Canonical hostg++17/echte cJSON:34controller-/admissionchecks en10echte
  EMSparserchecks PASS; nieuwe code strict schoon, bestaande parserwarnings apart.
  Native HA2026.10.2/Python3.14.8:107PASS/5bestaande dependencywarnings/0skips.
  Nieuw gecompileerde finite C++/HAinterop25PASS incl twee synthetische360s
  jitterreplays: dezelfde sessie blijft ready, HAdeadline nooit voorbij echte
  firmwaregrantdeadline. Tellingen overlappen eerdere pakketten, niet optellen.
- [x] Eerste HAverificatie105/107: laatste SQLitewaarde ontbrak in twee readbacks;
  oorspronkelijke log/xml behouden. Test-only commitbarrière vóór history-read
  toegevoegd(e809264); assertions/tijdvenster onveranderd,107/107PASS. Geen
  product-/database-/dependency-/HAcorepatch, geen wegpoetsen van eerste failure.
- [x] Actuele canonical main.cpp met gepinde Xtensa/Arduino2.0.17flags typecheckPASS;
  oude gegenereerde webassets alleen voor TYPECHECK hergebruikt. Geen volledige
  actuele firmwarebuild/link/image/resource-/performance-/duurproefclaim.
- [ ] Nog open: volledige firmwarebuild/installatie, MQTT-/E32-/telefoonvisuals,
  fysieke ontvangst/Classic-/meterkwalificatie, Recorderomvang/liveperformance;
  actieve graph/profile/model/comfortintegratie en F0–F10gates blijven gelden.
  Geen HAproductie-/broker-/login-/EMS-/Tado-/TX-/actuatoractie of verwarmingsGO.
- Bewijs11774dossier: MODERN-GRANT-PARENT-REVIEW.md, HASHES.json, COMMITS.json,
  NATIVE-COMMANDS.json/native_run.log, PARSER-*.log/NATIVE.json,
  HA-BARRIER.xml/log, INTEROP.xml/log, JITTER/, E32-SYNTAX.json/log en POSTCHECK.json.
  Eerste HA.log/xml en RECORDER-BARRIER.patch blijven afzonderlijk bewaard.
- Rollback vóór deployment: grantc2470a5 terugdraaien, daarna metrics5d087c0;
  testfixe809264 afzonderlijk. Geen runtimegegevens/config gewijzigd.
- Voortzetting: bestaande specialist actief aan F9coast/koelrespons/curve; reeds
  aangeboden graph-/seizoens-/comfortsoftware blijft dezelfde eigenaar. Concrete
  volgende F10/R31capability-/profielgerichte tapwaterpresentatie en supported/
  unsupported/stale/migratie-/redactietests aangeboden ná huidig werk, zonder
  nieuwe DHWwritevrijgave. Followupb5448b4d-b78e-4a0a-b46d-82d0cab463d7 QUEUED,
  geen completion. Heel11785 blijft actief; next_check15m bevestigd, job behouden.


### Mark11785 — F9/R14 koelrespons en uitloopadvies: onafhankelijke bronacceptatie

- [x] Canonical hosttoegang werkelijk bewezen op schone48d0b9e; bestaande eenmalige
  NIGHT-RUNTIME-CHECK.txt behouden, proef niet herhaald. WORKBOARD§6/PLAN en actuele
  RESULT Stage15 gelezen; bounded history toont specialist actief aan curve/replay.
- [x] Exacte coastcorepatch e1aca991b2bbb33dd06f39d8566365d9da8c0990933c45801fc3375684125c2b
  volledig gereviewd; alle4niet-WORKBOARDbron-/dochashes matchen COAST-RESULT.json.
  Afzonderlijke canonical reviewbranch, geen specialistcheckout gewijzigd.
- [x] Alleen complete onafhankelijke gekwalificeerde warmte-/uitvensters tellen;
  maximaal16, minstens6cycli/6dagen/14dagenspan en vergelijkbare buiten-/water-/
  kamer-/warmteduurcondities. Conservatieve volledige-vensterextremen plus
  samplingonzekerheid; geen vroege comfortverlaging vóór dalende UTCovergang.
  Gekwalificeerd startmodel standaardfalse; eigenaar/binding blijft toelatingsgate.
- [x] Defaultdisabled/frozen/shadowbron; geen actieve caller/capability/GUI of
  warmteterugname. Versie/binding/SHAcodec maximaal554B, expliciet30mincheckpoint,
  exacte readback en foutlatch bij ambigu commit. Geen actieve NVSkeytoewijzing.
- [x] Werkelijk hercompile vanuit canonical bron met hostg++17 strictwarnings:
  40nativePASS(21nieuwe+19bestaande warmmodel/store), dezelfde40PASS onder
  ASan/UBSan inclusief framework/testtranslationunits; echte OpenSSLSHAprovider.
  Geen skips; overlappende tellingen niet optellen, synthetische tijd is geen
  werkelijk tweeweken-/comfort-/besparingsbewijs.
- [x] Nieuwe observe/propose/checkpointmethoden onafhankelijk naar echt gepind
  Xtensa/Arduino2.0.17object gecompileerd: model696B/snapshot484B. Perfunctie
  proposal240B/checkpoint592B; GEEN volledige callgraph/8zoneheap/NVSGC/runtimeclaim.
- [ ] F9 blijft open: actieve graph/modelowner/bindingadmission, gepaarde baseline-
  en counterfactualreplay, volledig8zoneresourcebudget, volledige firmwarebuild/
  link/installatie en echte comfort-/woningobservatie. Geen fysieke/TX/EMS/
  actuatorvrijgave, geen runtime-/productieHA-/broker-/loginactie.
- Bewijs11774dossier: COAST-PARENT-REVIEW.md, PRECHECK.json, HASHES.json,
  COMMANDS.json/BUILD.log/NATIVE.json/log, SANITIZER-COMMANDS.json/BUILD.log/
  NATIVE.json/log en E32-RESOURCE.json/BUILD.log/SYMBOLS.log/STACK.log.
- Rollback vóór deployment: uitsluitend nieuwe coastbroncommit terugdraaien;
  bestaande warmmodel-/runtime/configdata zijn niet gewijzigd.
- Volgende uitvoering bij dezelfde actieve specialist: huidig curve-/gepaarde
  replaypakket afronden; daarna concrete F0/F2/F9bronacceptatiegate voor gezamenlijk
  warm/coast/curve8zonemodelbudget en begrensde checkpointallocatie, zonder
  actieve modeladmission. Graph-/seizoens-/comfortsoftware blijft eveneens open.
  Hele11785 blijft actief; na inhoudelijk pakket hervatting15min, eigen job behouden.


#### Postcheck en voortzetting F9coastparentmerge

- Canonical7e89364 via reviewbranch fast-forward; gitstatus leeg/commitdiffcheckPASS.
  COAST-PARENT-POSTCHECK.json bewaart exacteHEAD en bron-/verifierscope.
- Concrete volgende F0/F2/F9max8zone-modelbudget/checkpointgate met negatieve
  grens-/storagechecks en bronrollback aan dezelfde specialist aangeboden na
  huidig curve/replaywerk. Followupd3ecde0c-7b95-4e2f-8cd1-8822ab39bb96 QUEUED;
  admission is geen completion. Geen nieuwe eigenaar/actieve runtimevrijgave.
- Automations next_check15m bevestigd; hele11785softwareplan niet voltooid,
  eigen hervattingsjob behouden. Geen herhaalde groene checks als vervangend werk.

### Mark11785 — F9/R09/R14 langzaam stooklijnadvies: onafhankelijke bronacceptatie

- [x] Canonical prechange a4b2b81 schoon; WORKBOARD§6/PLAN, actuele RESULT Stage16
  en eenmalige bounded sessions_history werkelijk gelezen. Bestaande hostreceipt
  behouden; eenmalige proef niet herhaald. Specialist actief, geen tweede eigenaar.
- [x] Exacte curvecorepatch ad8857575271f3ded9a09d734d6acd10347190fa0a5bcd99e42e33e5727368d1
  volledig gereviewd; alle4niet-WORKBOARDhashes matchen CURVE-RESULT.json e91c94ad.
- [x] Afzonderlijke verse kamer-/buitenrapporten, vaste2–8zone/sourcequorum,
  complete4uurvensters, >=6dagen/14dagenspan/10Cweerspreiding en consensus van
  ALLE betrokken zones; eigen groupWaterTarget/flowwatertracking en vloer-/limiet-
  begrenzing hergebruikt. Cache/polling geeft geen nieuwe leerkwalificatie.
- [x] Alleen één geobserveerd interieurknooppunt <=0.25C per onveranderlijke oude
  curve, geen automatische parameteradoptie. Defaultdisabled/frozen/shadow;
  modelownerkwalificatie standaardfalse, geen actieve caller/GUI/capability/NVSkey.
  Codec maximaal412B;30mincheckpoint, binding/basecurve/SHA/readback/ambigu-foutlatch.
- [x] Canonical hostg++17 -Wall/-Wextra/-Werror:32PASS(17nieuw+15gedeeld), dezelfde
  32PASS onder ASan/UBSan inclusief echte framework-/testtranslationunits. Gepind
  Xtensa/Arduino2.0.17 actual-methodsobject PASS: model1016B/snapshot372B; GEEN
  volledige callgraph/8zoneheap/NVSGC/runtime/firmwareimage- of fysieke acceptatie.
- [ ] F9 blijft open: actieve graph/modelowner/admission, enabledmodel-/historische
  baselinevergelijking, volledig8zonebudget en echte14dagen-/comfort-/seizoensproef.
  Niet gebouwd als volledige firmware, niet geïnstalleerd, geen fysieke/TXvrijgave.
- Bewijs11774dossier: CURVE-PARENT-REVIEW.md, PRECHECK.json, HASHES.json,
  COMMANDS.json/BUILD.log/NATIVE.json/log, SANITIZER-COMMANDS.json/BUILD.log/
  SANITIZER.json/log en E32-RESOURCE.json/BUILD.log/SYMBOLS.log.
- Rollback uitsluitend deze nieuwe curvebroncommit vóór deployment; geen runtime-
  of productieHA-/broker-/apparaatdata gewijzigd. Geen login-/warmteactie.
- Volgende echte uitvoering: inmiddels gereed Stage17 gepaarde replayevaluator
  onafhankelijk reviewen; specialist houdt graph/profile/modelowner-/resource-
  vervolg en resterende F0–F10software. Hele11785 blijft actief, hervatting15min.

### Mark11785 — F9 gepaarde replayevaluator: onafhankelijke bronacceptatie

- [x] Canonical prechange eaa7eb1 schoon; exacte replaycorepatch
  6055aabc56f88516021a964d6ab48e4cb76ae20cc3368bf69d5c564aa221b615
  volledig gereviewd; alle3niet-WORKBOARDhashes matchen REPLAY-RESULT.json ada2e5fc.
- [x] Constante-memory OFFLINE scorer voor identieke exogene tijd-/targetcontext;
  unpaired/klok/volgorde/budgetfouten latched, gaten/missing niet als0 of goede
  dekking, geen verzonnen branderstarts/voltooide runs. Onbekende vlamkwaliteit
  levert geen cyclingbewijs. Aankomstevents niet door later warme cache herstellen.
- [x] Comfort/MAE/band/overshoot, werkelijk geobserveerde CVpendelfrequentie en
  complete brandduur, >=10gekwalificeerde aankomsten en veiligheid afzonderlijk;
  ALL-required acceptatie, veiligheidsovertredingen ook op uitgesloten faultframes.
- [x] Canonical strict hostg++17:12nativePASS, dezelfde12ASan/UBSanPASS inclusief
  echte GTest én cJSON-writer;12semantische scenariorijen exact gelijk tussen
  normale/sanitizerparent en specialistuitvoer. Gepind Xtensa actual add/assessment
  object PASS: comparator392B/assessment184B, geen volledige firmwareimageclaim.
- [x] Twee echte ZoneRegulator-replays met identieke synthetische cold/mildplant:
  defaultdisabled kandidaat == baseline; GEEN enabledmodel-/verbeteringsbewijs.
  Onafhankelijk opnieuw: foutomzeilende kandidaat lagere MAE0.1587vs0.1638C,
  maar5veiligheidsovertredingen en dus VERWORPEN. Negen aankomsten blijven tekort;
  geen verlaagde10grens of verborgen fault om een groen resultaat te krijgen.
- [ ] F9 OPEN: daadwerkelijk enabled warm/coast/curve pairedcandidate, representatieve
  historische/huisdata, actieve graph/modelowner-/resourceacceptatie, echte14dagen/
  comfort-/seizoensproef. Niet geïnstalleerd, geen fysieke/TX/EMS/actuatorvrijgave.
- Bewijs11774dossier: REPLAY-PARENT-REVIEW.md, PRECHECK.json, HASHES.json,
  COMMANDS.json/NATIVE.json/log, SANITIZER-COMMANDS.json/SANITIZER.json/log,
  SCENARIOS.jsonl/SANITIZER-SCENARIOS.jsonl/SEMANTIC-CHECK.json en E32-RESOURCE.json.
- Rollback uitsluitend nieuwe replaybroncommit vóór deployment; geen runtime-
  productieHA-/broker-/apparaatdata gewijzigd. Bestaande bronpakketten behouden.
- Volgende concrete F9/R12–14opdracht aangeboden aan dezelfde specialist NA actief
  graph/profile/resourcewerk: echte enabledmodelvoorstellen in bestaande gepaarde
  offline harness, identieke baseline/exogene input, cold/mild/raam/DHW/fault/
  gap/reconnect en weigering slechtere kandidaat; synthetische14dagen expliciet
  labelen. Followup eb935cd0-ef6b-478e-8eca-05bf6ab6435c QUEUED, geen completion.
  Reeds aangeboden8zonebudgetgate en overige F0–F10software blijven gelden;
  geen tweede eigenaar of herhaling van ongewijzigde groene suites. Hervatting15min.


### Mark11785 — F2/F3 atomair graph-wiretuple: onafhankelijke bronacceptatie

- [x] Canonical hostcheckout3dc8b06 schoon; WORKBOARD§6/PLAN-gates, RESULT Stage18
  en eenmaal bounded sessions_history gelezen. Bestaande eenmalige hostreceipt
  behouden; specialist actief aan owner/profile/partition, geen tweede eigenaar.
- [x] Volledige621regelcorepatch SHA256
  4b29787bd1096499825e1d7950c08d1584f247595d15f4cd260cdc0700ecd46a gereviewd;
  alle10niet-WORKBOARDbron-/test-/dochashes matchen GRAPH-WIRE-RESULT.json af6689dc.
- [x] Eén expliciet onderhandelde atomic_mapping_tuple.v1 met mapping+config,
  dezelfde validator/Storelock/postawaitdurable+generation+freshness en firmware
  SessionAdmission/atomair4096Bstore/readback. Decoder geeft geen autoriteit;
  ACK is geen applybewijs. Geen automatische API2selectie of nieuwe outputflags.
- [x] Onafhankelijk canonical strict hostg++17:47nativePASS; dezelfde47ASan/UBSan
  inclusief echte GTest/cJSON/testtranslationunits PASS. Native HA2026.10.2/
  Python3.14.8:57PASS(23wire+30Store+3firmwareStore+1runtimegrens), vijf bestaande
  dependencydeprecaties, geen skips/netwerk/device. Tellingen overlappen eerder werk.
- [x] Zelfde3819Bfixture:1378encoder+415decoderallocatiefoutposities, geen leak/
  geaccepteerde fout/onbereikte site en exacte recovery. Native64requestedpeaks
  29094/25251B; GEEN E32performanceverbeteringsclaim. Gepind echt Xtensa/Arduino
  methodsobject PASS: owner4472B/candidate344B/parts48B/cJSON40B, geen fullimage.
- [ ] F2/F3 OPEN: actieve API2owner/handshake/capability/profile/model/GUIapply,
  echte partitie-/migratie-/8zoneheap/stack/NVS/GC/resourceacceptatie en fysieke
  ketenproef. Alleen bronacceptatie; niet geïnstalleerd, geen TX/actuator/verwarmingsGO.
- Bewijs11774dossier: GRAPH-WIRE-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS.json,
  BUILD/NATIVE.log/json, INTEROP-COMMANDS.json/HA.xml/log, ALLOCATIONS.json/PROBE.log,
  SANITIZER*.json/log en E32-RESOURCE.json/BUILD/SYMBOLS/STACK.log.
- Rollback alleen nieuwe graphwirebroncommit vóór afhankelijke wijzigingen/uitrol;
  geen runtime-/HAproductie-/broker-/apparaatdata gewijzigd.
- Volgende uitvoering: bestaande specialist voltooit actieve graphowner/profile/
  partition/resources; reeds aangeboden seizoens-/DHW-/enabledmodelreplay behouden.
  Daarna concrete F0/F10 lokale releasecandidatevoorbereiding met bestaande volledige
  generic/E32builds, gepinde HAcompatibiliteits-/schema-/model-/asset-/rollbackmatrix
  en negatieve migratie/securitychecks. Geen publiceren/installeren of open fysieke
  gates als PASS presenteren. Hele11785 blijft actief; volgende hervatting15min.
- Canonical bronmerge4a0e67f technisch nagecontroleerd: schoon,10bronhashes en
  commitdiffcheckPASS. F0/F10vervolg a66f4831-6957-49dc-bc1b-1216bb2f1d08 QUEUED
  bij bestaande specialist; admission is geen completion. next_check15m bevestigd.

### Mark11785 — F2/F3 conservatieve NVS-preflight: onafhankelijke bronacceptatie

- [x] Echte canonical hostcheckout00822be schoon; WORKBOARD§6/PLAN, RESULT Stage19,
  memory en eenmaal bounded specialistgeschiedenis gelezen. Bestaande eenmalige
  hostreceipt behouden; specialist actief aan graphowner/HAverbinding.
- [x] Volledige corepatch SHA256
  31bc39a3f4418b9d4bb691812c991ac45972a2b44e1eee358a244fd3c11e0330 gereviewd;
  alle4niet-WORKBOARDhashes matchen CONTROL-BUDGET-RESULT.json70ee0d8e.
- [x] Expliciet graphstorageprofiel controleert echte partitie/NVSstats vóór writeopen;
  onbekend/inconsistent/overflow weigert, oude config/netwerkbytes blijven belast.
  Default API1 ongewijzigd; geen factoryselectie, nieuwe key/namespace/partitie.
- [x] Canonical hostg++17 Wall/Wextra/Werror:6gerichte nativechecks PASS;
  actuele main.cpp/ModernTransport met echt gepind Xtensa/Arduino2.0.17/NVS-SDK:
  typecheck PASS. Oud gegenereerd webassetheader uitsluitend voor typecheck;
  geen volledige image/link/build-/installatieclaim.
- [x] Conservatieve vrije264entryreserve en4096Bconfiggrens;8warm/coast/curve-
  checkpointsets vragen504entries vóór overige reserveringen en worden geweigerd.
  Dit is geen bewijs dat elke compactere layout onmogelijk is; geen succesvolle
  NVSallocatie/GC-/heap-/stack-/8zoneresource- of fysieke acceptatie afgevinkt.
- Bewijs11774dossier: CONTROL-BUDGET-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS/
  NATIVE/E32-SYNTAX.json en BUILD/NATIVE/E32-SYNTAX.log.
- Rollback alleen nieuwe preflightbroncommit vóór afhankelijke ownerwijzigingen;
  geen runtime-/HA-/broker-/apparaatdata of fysieke outputs gewijzigd.
- Volgende uitvoering: bestaande specialist voltooit actieve graphowner/handshake/
  HAverbinding; daarna concrete F2/F3 normale GUIapply met expliciete verse readback,
  conflict-/reload-/reconnectafhandeling, zonder automatische send of admission.
  Bestaande seizoens-/DHW-/enabledmodel-/F0/F10opdrachten blijven gelden;
  hele11785 actief, hervattingscheck15min na dit bronpakket.

- Canonical broncommitbf1845a technisch nagecontroleerd: schoon, commitdiffcheckPASS,
  CONTROL-BUDGET-PARENT-POSTCHECK.json. Concreet GUIapplyvervolg
  2ef680e5-ac1c-47fd-af43-575bef10f71f QUEUED bij dezelfde specialist, niet
  completion; indien al actief onderdeel alleen ontbrekende acceptatiegaten.
  Eigen automation geïnspecteerd en next_check15m bevestigd.

### Mark11785 — F2/F3 expliciete graph-handshake/readback: onafhankelijke bronacceptatie

- [x] Canonical prechange34cd917 schoon; actuele WORKBOARD/PLAN-gates en Stage20
  RESULT/handoff gelezen. Stage18/19 al geaccepteerd; geen dubbele merge/telling.
  Begrensde specialistgeschiedenis gaf een projectiefout; session_status bevestigt
  bestaande specialist met followupqueue. Geen tweede uitvoeringseigenaar gestart.
- [x] Corepatch SHA256
  a742b42224ab956cff0639b92e325faad67df30f65a15d84606c1a452988bea3 gereviewd;
  alle16niet-WORKBOARDbron-/test-/dochashes exact GRAPH-OWNER-RESULT.jsonc8fbaea.
- [x] Expliciet source-owned API2profiel in dezelfde native verbinding/queue/worker/
  Store; defaultAPI1 behouden, geselecteerd2 valt nooit terug1. Echte challenge/
  open/heartbeat/grant/atomiccommit/nieuwe sessie/exacte readback vereist. ACK alleen
  is geen applybewijs; graph_ready is uitsluitend DATA, ready/control blijftfalse.
  Huidige main/options selecteert dit profiel niet; geen runtimewijziging.
- [x] Onafhankelijk canonical hostg++17 strict:53nativePASS; native HA99PASS,
  inclusief bestaande API1lifecycle/grant. Eerste98PASS/1FAIL was ontbrekende
  testbinary; oorspronkelijke log bewaard. Werkelijke canonical shadow_runner
  gebouwd/expliciet aangewezen, daarna volledige99PASS zonder bron-/assertiewijziging.
- [x] Werkelijke graphowner/core/finiterunner/cJSON volledig ASan+UBSan gebouwd;
  dezelfde17HAgraphprotocolchecksPASS met leakdetectie/halt-on-error. Geen GTest
  in die runner; native-only nonPIEflags, geen productflags. Tellingen overlappen.
- [x] Synthetische6min/2s actual-protocolmeting onafhankelijk gereproduceerd:
  1snapshotrequest/183HAtotaal/50879HAbytes; eerder bewaard before181snapshots.
  Dit is geen daadwerkelijke brokerduur-/liveE32GUI-/telefoonsnelheidsmeting.
- [ ] F2/F3 OPEN: volledige graphGUIapply/source/controller/modeluitvoering,
  8zoneheap/stack/NVS/GC-/partitie-/migratieacceptatie, volledige firmwareimage en
  fysieke ketenproef. Niet geïnstalleerd; geen actuator/TX/EMS/verwarmingsvrijgave.
- Bewijs11774dossier: GRAPH-OWNER-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS.json,
  BUILD/NATIVE/RUNNER/API1/SANlogs, FINAL-HA.xml/log, SAN-HA.xml/log en POLL.json.
  Specialist Xtensaobject/typecheckbewijs behouden; geen nieuwe parentfullbuildclaim.
- Rollback alleen dit nieuwe bronpakket vóór afhankelijke activatie; geen live data
  gewijzigd. OudAPI1 blijft bewaard, geen automatische migratie/reset.
- Volgende uitvoering blijft bij dezelfde specialist: bestaande GUIapply2ef680e5,
  enabledmodelreplayeb935cd0 en F0/F10releasevoorbereidinga66f4831, zonder duplicaten.
  LiveGUIperformance en alle overige F0–F10open checks blijven deel van11785.
  Bestaande officiële automation72ec7e68 enabled/gepland geïnspecteerd en behouden;
  het gehele PLAN blijft in_progress, geen stilzwijgende afronding na dit bronpakket.

### Mark11785 — F5 kamermodellen/Recorder: Stage21 onafhankelijk NIET geaccepteerd

- [x] Canonical9726bce schoon, exacte21padencorepatch
  8ee3b5d649d5ff91beee936ee87dca70379f3b87fa57676a587092aad0ed534a
  en21bronhashes5d413549 gecontroleerd. Echte hostg++17/EMSparser16PASS;
  native HA2026.10.2/Python3.14.8 volledig gericht86PASS incl onveranderde
  parentRecorderregressie, geen uitsluiting. Zes echte C++serializerrows gebruikt.
- [x] Extra onafhankelijke native herstartprobe vindt onjuiste eenheidsrestore:
  display1000Wh wordt1000kWh (verwacht1),600s wordt2160000s (verwacht600).
  Nieuwev2totalen zouden bij unitkeuze/reload onjuist groeien; daarom NIET
  samengevoegd ondanks groene aangeleverde tests. Alleen candidatepatch exact
  teruggedraaid; gitdiff/status daarna schoon. Geen livehistorie gewijzigd.
- [ ] Specialistcorrectie vereist: ondersteunde native RestoreSensor-data met
  unit/finite/grenskwalificatie; gekwalificeerde conversie of weigering bij ontbrekende
  native data, nooit displaywaarden stil als kWh/h lezen. Native lifecycleproeven
  voor Wh/kWh,s/min/h, onbekende/incompatibele units en oudehistoriescheiding.
- Bewijs11774dossier: ROOM-METRICS-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS.json,
  NATIVE.json/log, HA.xml/log en RESTORE-PROBE.json/log. Eerste85PASS/1harnessFAIL
  (ontbrekende parentbewijsmap) behouden; dezelfde86tests daarna PASS zonder
  product-/assertiewijziging. Echte tijdelijke SQLitefixture900pogingen/300nieuwe
  rows/0.58kWhreset-sum, géén productiecadans/retentie/72uclaim.
- Nieuwe foutinformatie aan bestaande actieve eigenaar via steer101d68ca gestuurd;
  admission is geen correctie/completion. Geen concurrerende code-eigenaar gestart.
  Actieve GUIapply/enabledmodelreplay/releasevoorbereiding en hele11785 lopen door;
  volgende bronreview na gecorrigeerd manifest, officiële hervattingscheck15min.
  Geen installatie, nieuwe login, broker/HAconfig, TX/EMS/actuator-/verwarmingsGO.

### Mark11785 — F5 gecorrigeerde kamerrestore en begrensde modellen: bronacceptatie

- [x] Canonical0c72974 schoon; bestaand hostreceipt behouden, actuele§6/PLAN,
  gecorrigeerd specialistRESULT7064f8c8 en eenmaal begrensde specialistgeschiedenis
  gelezen. Bestaande eigenaar actief aan connectedcomfort, geen tweede eigenaar.
- [x] Volledige gecorrigeerde22padenpatch357da92072ca44dda8312a7689d16480a60e6f6d0f3948613dea09c20c694b97
  gereviewd; alle22bronhashes exact. Eerdere afwijzing5d413549 blijft geldig:
  uitsluitend gecorrigeerde rollup overgenomen, geen stapeling met oudepatch.
- [x] Canonical echte EMSparser/serializer opnieuw gecompileerd:16nativePASS,
  zes echte wireframes. Native HA2026.10.2/Python3.14.8:121PASS zonder skips/
  deselecties, inclusief35echte RestoreSensor/EntityPlatform/unitlifecyclechecks
  én oorspronkelijke parentRecorderregressie; vijf bestaande dependencywarnings.
- [x] Native opgeslagen waarde+unit via ondersteunde conversie;1000Wh→1kWh,
  600s/10min/1/6h→600seconden. Geen displayfallback, onbekend/incompatibel/
  niet-eindig geweigerd; ongeronde native heropslag en add/remove/readd bewezen.
  Oude roomhistoriek geïsoleerd/onbeschikbaar zonder nieuwe statistiek/backfill.
- [x] Begrensde room-/EMSobservationTTL, boot/sequence/retained/offlinefences,
  native vervaltimer en gemeldeCH versus werkelijke warmte apart. EN442model
  blijft schatting; native adminCSV opt-in opgenomen historische units, geen
  huidige unit raden of waardeconversie. TijdelijkeSQLiteproef géén live72ubewijs.
- [ ] F5 blijft open: Classic-/bron-/fysiekepariteit, werkelijke UI/telefoon,
  firmwarefullbuild/resources/installatie, livecadans/retentie en modelnut.
  Geen livehistorie/config/broker/apparaat gewijzigd of verwarmingsGO.
- Bewijs11774dossier: ROOM-CORRECTED-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS,
  NATIVE/HA/RESTORE-ROWS en room-corrected-parent-recorder/. Rollback uitsluitend
  nieuwe broncommit; beide historiekdefinities bewaren, geen runtimedata te herstellen.
- Eerstvolgende echte parentactie: gereed Stage22enabledreplay onafhankelijk
  toetsen; alle7aangeleverde policies afgewezen/onvoldoende, niet als modelwinst
  aftekenen. Bestaande specialist vervolgt connectedcomfort/GUIapply/modelowner/
  seizoen-/releasewerk; hele11785software actief, fysieke gates ongewijzigd.

### Mark11785 — F9 enabledadvies-replay: testbron geaccepteerd, modelbeleid AFGEWEZEN

- [x] Exact tweepaden-test/docpakketcb2f4e916afdfe3e9650975673334f403bf6f6af7cd9fa68b96a085fee671334
  en beide bronhashes715b5a59 gereviewd op canonical5a7ab16. Geen productiecode,
  modelowner, capability, profiel, runtimeconfig of output gewijzigd.
- [x] Echte observe()-training met6onafhankelijke synthetische episodes,
  frozen warm/coast/curveadvies en werkelijke regulator/water/evaluator. Zelfde
  exogene hashgebonden scenario's, afzonderlijke room-/opslagtrajecten en
  expliciete toyplant/prehistory; géén werkelijke woning/14dagenbewijs.
- [x] Canonical strict hostg++17:6PASS; volledige echte GTest plus test/model/
  regel-/evaluatorTU opnieuw ASan+UBSan gebouwd:dezelfde6PASS met leakdetectie.
  Native/sanitizer/specialist7semantische rows exactgelijk; geen firmwareflags.
- [ ] Alle7modelpolicies AFGEWEZEN/ONVOLDOENDE: warm/combined0/14tijdigwarm,
  deels extra pendelen; coast-only pendelgatefaalt, sourceblocked onvoldoende
  data/geen advies of vraag. Lagere MAE is géén vrijgave/besparing/modelnut.
  Gewone combinedcoast0keer gebruikt; expliciete aparte heatinitialpair1keer.
  Geen veiligheidschending in deze fixtures is geen fysiekeveiligheidsproef.
- Bewijs11774dossier: ENABLED-REPLAY-PARENT-REVIEW.md, PRECHECK/HASHES/COMMANDS/
  CHECKS.json, NATIVE/SANITIZER.json/log/BUILD.log en SCENARIOS.jsonl. Rollback
  uitsluitend dit nieuwe test/docbronpakket, geen runtimedata te herstellen.
- Gecorrigeerd F5pakket canonical5a7ab16 nagecontroleerd: schoon22hashes,
  16C++/121HA; ROOM-CORRECTED-PARENT-POSTCHECK.json. Niet geïnstalleerd.
- Concrete volgende F9diagnose-/softwareopdracht bij bestaande specialist
  followup02b1d608-d0af-4c68-937d-041382e56628 QUEUED: arrival/cyclingtrace,
  kwalificatie versus reële modelbeperking; alleen bewezen softwarefout repareren,
  geen thresholds/plant retunen voorPASS. Admission is geen completion.
  Bestaande connectedcomfort/GUIapply/modelowner/seizoen/releasevoorbereiding
  blijft actief. Hele11785software niet klaar; fysieke/72u/verwarmingsgates open.

### Mark11785 — F10 verbonden comfortbeleid: onafhankelijke bronacceptatie Stage23

- [x] Canonical596bd38 schoon; bestaand eenmalig hostreceipt niet herhaald.
  Actuele§6/PLAN en specialistRESULT498a5fb0 gelezen, eenmaal boundedhistory6:
  bestaande eigenaar werkt aan nativeAPI2apply; geen tweede eigenaar gestart.
- [x] Exact16padenpatch00793e58553b5d5899dd45c7bb9f00d23fb4125b215c978c4b3836880d5ed5b2
  gereviewd; alle16voor-/nahashes exact. Bestaande EffectiveTarget, controller,
  Store/configreadback, native roomform/climate/entityaction hergebruikt; opt-in
  comfort.target.v1, oudere peer weigert vóór write, oude kamershape behouden.
- [x] Canonical strict hostg++17:51C++PASS; nativeHA2026.10.2/Python3.14.8
  51PASS met opnieuw gecompileerde werkelijkeC++peer. Afzonderlijk37PASS
  gedeelde RoomBinding/API1nativeconnection/API2graphconnection/ownerinterop.
  Geen skips/deselecties; vijf bestaande dependencywarnings per HArun.
- [x] Dezelfde51C++checks onafhankelijk volledig ASan+UBSan herbouwd, inclusief
  echteGTest/cJSON/test/controller/policy; leakdetectie/halt-on-error PASS.
  ExterneOpenSSL niet geïnstrumenteerd; nonPIE alleen native test, geen productflags.
- [x] Begrensde override/boost, away/vacation/presence/window/frost/off;
  firmware-eigendom/UTC-/monotoneafloop, geen ACK-optimisme/commandrestore,
  twee-zoneisolatie en beide AmsterdamDSTovergangen in nativefixtures bewezen.
  Stop/bounds/source/admission blijven voorwaarden, fysiekeoutputflagsfalse.
- [ ] R19–21/F10 blijven open: onveranderde contact/personstatus wordt na120s
  unknown en pauzeert automatische vraag; expliciet shadowpreview, GEEN
  gekwalificeerd fysiek/stabielbronprofiel. Geen fysieke vorst-/actuatorclaim.
  Nativebrowser/telefoon/fullimage/resources/installatie/livecomfort blijven open.
- Bewijs11774dossier: COMFORT-CONNECTED-PARENT-REVIEW.md, PRECHECK/HASHES/
  COMMANDS.json, NATIVE/SAN.json, HA/COMPAT-HA.xml en build/runlogs.
  SpecialistXtensatypecheck behouden, geen nieuwe parentfullbuildclaim.
  Rollback alleen nieuwe comfortbroncommit vóór afhankelijke wijzigingen; geen
  runtime/HA/broker/config/historie/credentials/publicatie/TX/EMS/verwarmingsactie.
- Volgende echte uitvoering bij dezelfde specialist: bestaande nativeAPI2
  review/apply/readback/reconnect en releasevoorbereiding; resterend F4/F6
  seizoen-/laaglastbeleid aansluiten op werkelijke controller indien nog niet
  aantoonbaar geleverd. F9afgewezen modellen blijven afgewezen; diagnoseopdracht
  reeds queued, niet dubbel gestart. Hele11785software blijft in_progress.

### Mark11785 — F2/F3 native graphreview en geïntegreerde HA-bronkwaliteit: Stage24/25

- [x] Canonical3b4e19b vooraf schoon; huidige§6/PLAN en RESULTStage24/25
  daadwerkelijk gelezen. Bestaand hostreceipt20okt23:40 niet herhaald;
  eenmaal bounded specialistgeschiedenis6: dezelfde eigenaar werkt actief aan
  native graph-draftvertaling. Geen tweede eigenaar of redundant werkdoorbericht.
- [x] Exacte8padenStage24patchb0135acb en3padenStage25patchbeb42ea2
  gereviewd, alle11frozenbronhashes exact. Review bevestigt8private tuple-/
  sessievelden; kopie en hercontrole onder dezelfde Storelock na awaited
  diskreadback. Disconnect blokkeert oude DATA onmiddellijk vóór send.
- [x] Native optionsreview gebruikt bestaande worker, expliciet defaultfalseconsent,
  geen profiel/owner/kwalificatiecreatie, geen optionsreload. Onzekere send blijft
  pending; alleen werkelijke bekende readback promoveert DATA. Defaultapi1 en
  alle fysiekeoutputflags ongewijzigd; graph_ready is GEEN regelvrijgave.
- [x] Werkelijke canonical hostgcc/g++17/echte pinnedcJSON/EMSparser: alle
  vereiste finite peers nieuw gebouwd. Volledige HA2026.10.2/Python3.14.8:
  670PASS+68subtests,1optionelebrokerSKIP,0deselecties; beide oorspronkelijke
  parentRecorderbarrièretets uitgevoerd, ongewijzigde bestanden/asserties.
  Daarna die ene packettest met officiële bestaande pinnedMosquittofixture:
  1PASS, echte HA/Paho/nieuwe C++peer, uitsluitend tijdelijke localhostpoort.
  671testgevallen dus verdeeld over2commando's; GEEN volledige CImatrixclaim.
- [x] Tijdelijke broker gestopt en onafhankelijk afwezig bewezen. Eerste directe
  --rminspectie liep vóór asynchrone verwijdering; nacontrole No such container.
  Vijf bestaande dependencydeprecaties; geen productieHA/broker/deviceactie.
- [ ] F2/F3/hele11785 blijven open: willekeurige native graphdraftvertaling/
  expliciete sourceprofile-integratie bij actieve specialist; officiële volledige
  nativeJS/browser/firmwareimages/resources/build/installatie en alle fysieke/
  meerdaagse/TX/EMS/actuator/verwarmingsgates niet vervangen door deze tests.
  Stabiele contact/personkwalificatie en afgewezen F9modellen blijven open.
- Bewijs11774dossier: GRAPH-REVIEW-PARENT-REVIEW.md, PRECHECK/HASHES/
  COMMANDS/FULL-HA-COMMAND/PACKET-COMMAND.json, FULL-HA.xml/log,
  PACKET-HA.xml/log en verse peerbuildlogs. Specialistbewijs behouden.
  Rollback Stage25 eerst, dan Stage24; parentRecorder/bord en historische data behouden.
- Eerstvolgende uitvoering: bestaande specialist voltooit graphdraft/API2keten;
  daarna begrensde comfortbronfreshnesssoftware met passende negatieve replay.
  Parent behoudt normale officiële release/buildgates; niets geïnstalleerd of
  gepubliceerd. Heleplan in_progress; hervatting15min na inhoudelijk pakket.

### Mark11785 — F2/F3 native opgeslagen graphdraft naar DATA: Stage26 bronacceptatie

- [x] Canonical112afd8 vooraf schoon; huidige§6/PLAN en Stage26RESULT werkelijk
  gelezen, bestaand eenmalig hostreceipt behouden. Eenmaal begrensde geschiedenis6:
  dezelfde specialist actief aan F9replaydiagnose; geen tweede implementatie-eigenaar.
- [x] Exact12padenpatch1f732e457f46546493c19618e9135af59faefe85ca7f6cf9a7c62a6ebab4066f
  en frozenarchive plus alle12voor-/nahashes gecontroleerd. Source-defaultNone,
  exact native entrypin, volledige onveranderlijke bronkwalificatie en registrybindingen;
  geen GUIcheckbox die feiten/kwalificatie of fysieke vrijgave creëert.
- [x] Opgeslagen native room/heatingdraft via dezelfde UTCcompiler/validator/Storeworker
  naar bestaande begrensde DATA; prepare verzendt niets, aparte exactgebonden
  defaultfalse review/apply/readback blijft vereist. Rename bewaart identiteit;
  ontbrekende/disabled/veranderde bron, onbekend beleid, extra topology, oversized
  kalender en draft-/disconnectrace falen vóór stage. Geen truncatie/guessedfallback.
- [x] Echte canonical hostgcc/g++peers opnieuw gebouwd; volledige HA2026.10.2/
  Python3.14.8:694PASS+68subtests,1optionelebrokerSKIP,0deselecties. Beide bestaande
  parentRecorderbarrières daadwerkelijk ongewijzigd uitgevoerd;24nieuwe draftcases.
  Vijf bestaande dependencywarnings, geen nieuwe browser/image/packet/liveclaim.
- [ ] Alleen bestaande1kamer/unmixedbinaryfloorDATA ondersteund. DATA-onlyruntime
  heeft geen bronlisteners/timers/observaties/regelbesluiten/climateuitvoer; readyfalse.
  Multiroom/menger/TRVprofielen en echte source/controlkwalificatie blijven open,
  evenals contact/personfreshness, afgewezen F9modellen en officiële build/releasegates.
- Bewijs11774dossier: GRAPH-DRAFT-PARENT-REVIEW.md, PRECHECK/HASHES/
  BUILD-COMMANDS/FULL-HA-COMMAND.json, FULL-HA.xml/log, verse peerbuildlogs en
  graph-draft-parent-recorder/. Rollback alleen Stage26 na latere dependents;
  parentRecorder/docs bewaren. Geen productieconfig/historie/HA/broker/device/
  profielselectie/login/installatie/publicatie/TX/EMS/actuator-/verwarmingsactie.
- Volgende uitvoering: specialist vervolgt actieve F9diagnose en al aangeboden
  F10bronfreshness/F4F6werk; parent neemt officiële native/browser/imagebuildgates
  op bestaande tooling op. Hele11785 blijft in_progress, geen stop na dit pakket.

### Mark11785 — F0/F10 matrixbuilds en echte OTA-bestandsgrens; generiek GEBLOKKEERD

- [x] Exacte officiële PIO6.2.0/IntelHex2.3.0 en Playwright1.63.0 geïsoleerd
  voorbereid; geen runtimeconfig. HostPython3.12 wijkt af van CIsetup3.11;
  geen volledige hostedCIclaim. Native356PASS, Chromiumbron76PASS/35JS-PASS,
  afzonderlijke echte onboardingASan+UBSan36PASS; dekking overlapt eerdere tests.
- [x] Canonical b3d521f-implementatie: E32 fullimage+SPIFFS werkelijk opnieuw
  gebouwd, safetyverifier+7foutproevenPASS; statischRAM65704/ELFflash2292853,
  echte app2299424/3670016bytes. S3 fullimagePASS, RAM59308/ELFflash1601361,
  echte app1601728/3670016bytes. Geen runtimeheap/stack-/latencybewijs.
- [ ] Genericesp32dev standaardbuild1710209>1703936ELFbytes. -Os exact0winst;
  fullLTO past maar nieuwe NimBLE2.5.1int/uint8_t-mismatch NIET onderdrukt of
  coregepatcht. ProjectLTO ELF1703261 meldtPASS, echte firmware.bin1709840
  past NIET in1703936:5904bytes over. Alle kandidaatflags exact teruggedraaid;
  geen partitie/feature/budgetversoepeling. Geen generieke releaseacceptatie.
- [x] Concrete kwaliteitsfix bestaande officiële CI: echte firmware.bin moet in
  BEIDE geconfigureerde OTAslots passen, niet alleen ELFcheck. Exacte workflow-
  Python/YAML werkelijk getoetst: verse echte E32/S3bytesPASS; hashgebonden echte
  ongeldige genericimage correctFAIL. Geen nieuw script/service/coördinatielaag.
  PIOconfigchecksum had oude buildfiles gewist; positieve images echt herbouwd.
- [x] Alle12Stage26bronhashes, oorspronkelijke platformio.ini en3partitietabellen
  exact behouden. Eerdere694HA+68subtests/1optionelebrokerSKIP/0deselecties blijven
  sourcebewijs; geen nieuwe packettest/volledigeCImatrix-/fysieke claim.
- Bewijs11774dossier: OFFICIAL-GATES-PARENT-REVIEW.md, NATIVE/BROWSER/MATRIX/
  RAW-IMAGE-CHECKS-commandos/logs, RAW-GATE-PARENT-BUILD-COMMANDS.json plus
  E32/FS/VERIFY/VERIFIER/S3logs en GENERIC-SIZE-PARENT-* met alle afwijzingen.
  Echte ongeldige image REJECTED-GENERIC-SOURCE-LTO-OVERSIZED.bin bewaren als
  negatief bewijs, niet flashen/verpakken. Rollback alleen nieuwe CIbroncommit.
- Concrete F0/F10broncorrectie bestaande specialist followupc414463c QUEUED:
  bron-/linkmapgedreven generieke groottecorrectie, rawimage binnen beide huidige
  slots, gerichte regressie/voor-nameting, behoud features/locks en eigen rollback.
  Admission is geen completion. F9diagnose/F10freshness/F4F6/tweekamerbronwerk
  blijft gelden; parent enige canonicalWORKBOARD/PLAN-eigenaar.
- Hele11785 in_progress; genericbuild/next-versionpackage/sourceprofielen en alle
  installatie-/liveperformance-/fysieke/72u/TX/EMS/actuator-/verwarmingsgates open.
  Lokale images met historischealpha6label zijn GEEN nieuwe release; niets
  geïnstalleerd/gepubliceerd/ingelogd of bestaandealpha6asset overschreven.
  Eigen officiële hervattingsjob behouden; volgende inhoudelijke check15min.

### Mark11785 — F4/F6 seizoensbeleid: Stage28 onafhankelijk AFGEWEZEN

- [x] Canonical dabdfe2 vooraf schoon; actuele§6/PLAN/RESULT werkelijk gelezen,
  memory_search+verified-taskflow toegepast; bestaand eenmalig receipt niet herhaald.
  Eenmaal bounded specialistgeschiedenis6: bestaande eigenaar actief aan Stage30
  DHWpresentatie. Geen tweede implementatie-eigenaar of redundant werkdoorbericht.
- [x] Exact4padenpatch06e6b9c4, archive en29specialistbewijs-hashes gecontroleerd.
  Alleen geïsoleerde canonical-afgeleide reviewbranch; oorspronkelijke Stage28
  NIET samengevoegd. Strict hostgcc/g++17/echteGTest/versecJSON:81PASS
  (16seasonal+65bestaande inclgroep/menger), geen skips; dit is geen acceptatie.
- [ ] Nieuwe onafhankelijke combinatieproef FAALT: SeasonalInputs stop=true én
  limitsKnownSafe=false verliest unknownSafety door eerste seasonal_stopreturn.
  Bij expliciet normalStop retainExistingPathAndPump en unknownSafety
  withdrawHeatOnly blijven pomp/pad onterecht retained. Heatfalse/outputfalse;
  kandidaatbrondefect, GEEN geïnstalleerd incident of fysieke naloopvaststelling.
- Bewijs11774dossier: SEASONAL-PARENT-REVIEW.md, PRECHECK/COMMANDS/NATIVE.json/log,
  CONCURRENT-INHIBIT.json, PROBE-COMMANDS.json en zelfstandige C++probe.
  Rollback: originele ongeaccepteerde branch niet mergen; canonicalbron behouden.
- Concrete nieuwe info/repro met mode:steer8bc80458 bij actieve specialist:
  alle gelijktijdige restricties monotone door bestaande supervisor behouden,
  combinatiegevallen en onverlengde deadlines bewijzen; geen policyversoepeling.
  Admission is geen completion. F4/F6/R22-R23 en fysieke vorstacceptatie open.

### Mark11785 — F9 vaste aanvullende holdouts: Stage27 testbron geaccepteerd

- [x] Exact2paden-test/docpatch5cb1fbd0, frozenarchive,20bewijs-hashes en2bronhashes
  gecontroleerd. Zeven bestaande productie-model-/storehashes exact ongewijzigd;
  geen modelpolicy/default/API1/CI/runtime-/outputverandering.
- [x] Canonical-afgeleide strict hostg++17:67PASS (10replay+57model/store).
  Dezelfde10replay ASan+UBSan/leakdetectiePASS; echteGTest+test/model/regulator/
  evaluatorTU opnieuw gebouwd/geïnstrumenteerd, ongebruikte cJSON/externeOpenSSL
  provider niet geïnstrumenteerd. Native/sanitizer/specialist11semantische rows
  exactgelijk; tellingen overlappen oudere suites, niet als nieuwe67optellen.
- [ ] Alle11modelassessments AFGEWEZEN/ONVOLDOENDE: nieuwe slow-floor/known-gain
  comfortgatefaalt, small-load deadlinegatefaalt,3dagen sensorverlies onvoldoende
  dekking7840bp. Modelkalibratie frozen6windows; geen thresholds/plantretuning,
  woning-/energiebewijs of softwarematige modelverbetering geclaimd.
- Bewijs11774dossier: F9-COVERAGE-PARENT-REVIEW.md, PRECHECK/COMMANDS/CHECKS.json,
  NATIVE/SANITIZER.json/log/BUILD.log enSCENARIOS.jsonl. Rollback uitsluitend dit
  nieuwe test/docpakket na latere dependents; parentRecorder/runtimedata bewaren.
- Volgende echte uitvoering: specialist herstelt afgewezen seizoenscombinaties na
  huidig DHWpakket; F9arrival/cyclingoorzaaktrace op exacte frozenholdouts blijft
  nodig, naast reeds aangeboden genericimage/sourcefreshness/productprofielen.
  Softwareplan11785 niet klaar; geen installatie/publicatie/login/broker/device/
  TX/EMS/actuator/verwarmingsvrijgave. Hervattingsjob behouden, inhoudelijke check15min.

#### Postcheck en concrete voortzetting Stage27/28parentreview

- Canonical0d24993 via onafhankelijke reviewbranch fast-forward samengevoegd;
  gitstatus leeg, commitdiffcheck en alle acceptatie-/ongewijzigde model-/
  afgewezen seasonal-voorhashes PASS. F9-COVERAGE-SEASONAL-PARENT-POSTCHECK.json.
- Concrete F9arrival/cyclingoorzaaktrace met exacte frozenholdouts/geen retuning/
  acceptatie/rollback aan dezelfde specialist aangeboden ná huidig DHWwerk en
  noodzakelijke Stage28correctie. Followup59fea8bc QUEUED, geen completionclaim.
  Seasonalreprosteer8bc80458 is nieuwe informatie, geen dubbele uitvoerder.
- Automations next_check15min bevestigd; uitvoerbare software/repair/imagegates
  staan open, eigenjob72ec7e68 behouden. Geen runtime/installatie/fysieke vrijgave.

### Mark11785 — F10/R31 read-only tapwaterpresentatie: gecorrigeerde Stage30 bronacceptatie

- [x] Canonical3284a51 vooraf schoon; echte hostshell/HEAD, actuele§6/PLAN,
  Stage30RESULT en eenmaal bounded specialistgeschiedenis6 daadwerkelijk gelezen.
  Bestaand eenmalig hostreceipt behouden; memory_search/verified-taskflow toegepast.
  Bestaande eigenaar actief aan concurrente seizoenscorrectie, geen tweede eigenaar.
- [x] Exact10padenpatch01e9b506 en frozenarchive plus alle10voor-/nahashes PASS.
  NativeHA2026.10.2/Python3.14.8 oorspronkelijk93PASS, maar onafhankelijke
  JSON10**400probe geeft ongehanteerde OverflowError in3tapwatervelden. Originele
  levering NIET ongewijzigd geaccepteerd; exacte bron/bewijzen behouden.
- [x] Parent begrensde correctie: range vóór math.isfinite;6echte tracker/MQTT-
  callbackproeven voor positieve/negatieve401cijferige getallen en volgend geldig
  bericht. Zelfde6gevallen tegen origineel6FAIL, gecorrigeerd99HA-PASS.
  Alleen dhw.py/testbestand gereserveerd, specialist met nieuwe foutinfo gesteerd;
  geen drempel-/profiel-/assertieversoepeling of concurrerende seasonalwijziging.
- [x] Volledige canonical HA-discovery734PASS+68subtests,1optionelebrokerSKIP,
  0deselecties; beide oorspronkelijke Recorderbarrières ongewijzigd uitgevoerd.
  Werkelijke hostgcc/g++17/cJSON/EMS/fivefinitepeers opnieuw gebouwd; vijf bekende
  dependencywarnings.99gerichte tests overlappen de volledige suite, niet optellen.
- [x] Broncommit94d2836: read-only native options/diagnostics/sensor/dashboard;
  bestaande listeners/timer, expliciete last-reported/onbekende fysieke bronleeftijd,
  Classicflow onderdrukt, geen DHWwriter/comfort-/tijd-/resetcapability verzonnen.
  Oude registryIDs/historie, productieHA/broker/firmware/controlpriority behouden.
- [ ] F10/R31/hele11785 niet klaar: echte bronleeftijd/ketelcompatibiliteit,
  native frontend/telefoon, normale images/release/generic-size/installatie,
  contact/personkwalificatie, afgewezen F9modellen en fysieke/72u/TX/EMS/actuator/
  verwarmingsgates blijven open. Geen nieuwe packet-/browser-/firmwarebuildclaim,
  runtimewijziging, performanceverbetering, installatie of verwarmingsGO.
- Bewijs11774dossier: DHW-PARENT-REVIEW.md, PRECHECK/HASHES/RANGE-PROBE,
  RED.xml/log, CORRECTED-HA.xml/log, FULL-HA.xml/log, FULL-COMMANDS/CHECKS.json,
  CORRECTED-HASHES.json en dhw-parent-corrected-only-core.patch. Rollback alleen
 94d2836 na latere dependents; parentRecorder/WORKBOARD/historie/runtimedata bewaren.
- Concrete bestaande F10bronfreshnessopdracht nader begrensd aangeboden:
  native contact/personreport/availabilityprofiel, alleen echte nieuwe reports
  verlengen eigen context, nooit temperatuur/lease/physicalreadiness; negatieve
  replay/compatibiliteit/twee-zone/unload vereist. Followup26cd2fc8 QUEUED is
  GEEN completion. Actieve seizoensreparatie en eerdere generic-size/F9opdrachten
  blijven behouden; hele softwareplan in_progress, officiële hervattingsjob behouden.
  Automations next_check15min bevestigd; geen stille beëindiging na dit pakket.

### Mark11785 — F4/F6 gelijktijdige seizoensrestricties: gecorrigeerde Stage31 bronacceptatie

- [x] Canonicale echte hostcheckout e8982ad vooraf schoon; actuele §6/PLAN,
  specialistRESULT Stage31, memory_search/verified-taskflow en eenmaal bounded
  sessions_history6 gelezen. Bestaand eenmalig hostreceipt niet herhaald.
  Dezelfde specialist actief aan model-/resourcewerk; geen tweede eigenaar.
- [x] Alleen volledige gecorrigeerde vierpadenrollup502a7efb toegepast op eigen
  canonical-afgeleide reviewbranch; alternatief deltapatchet NIET toegepast.
  Alle4voor-/nahashes, frozenarchive en38specialistbewijshashes exact.
  Originele Stage28 blijft historisch AFGEWEZEN, niet achteraf goedgekeurd.
- [x] Alle gelijktijdige restricties vóór vroege displayreturn bewaard; bestaande
  supervisor intersecteert iedere actieve oorzaak. Gedeelde withdrawalhelper
  neemt nu ook normalStop mee na adapterfaultlatch: bewust strenger voor gewone
  én seizoensaanroeper; niet claimen dat alle legacylogica ongewijzigd is.
- [x] Onafhankelijke echte hostgcc/g++17 strict:85nativePASS; dezelfde85 volledig
  opnieuw ASan+UBSan/leakdetectiePASS, incl echte GTest/cJSON/test/controlTUs.
  Externe OpenSSLprovider niet geïnstrumenteerd; nonPIE uitsluitend native runner.
  Exact oorspronkelijke onafhankelijke parenttegenproef nieuw gebouwd:PASS,
  initieel heattrue, daarna stop+unknownlimit heat/pump/path/physicalfalse.
- [x] Alle37semantische en635combinatierijen exact native/sanitizer/specialist;
  zowel expliciet toegestane bestaande retention als verboden retention bewezen,
  geen always-offoracle. Onverlengde naloop/escalatie/heropening in nativefixtures.
  Alle10geaccepteerdeDHWbron-/testhashes en beide Recorderbarrières behouden.
- [ ] F4/F6/R22-R23/hele11785 open: deze SOURCE-optinroute is nog niet door een
  productprofiel geselecteerd. Specialist Xtensamethodsobject/targetsizeof blijft
  objectbewijs, geen nieuwe parentfirmwareimage-/8zoneresource-/fysiekeproef.
  Geen generieke vorstbescherming, installatie, TX/EMS/actuator-/verwarmingsGO.
  Generic-size, bronfreshness, F9afgewezen policies en overige F0–F10gates open.
- Bewijs11774dossier: SEASONAL-CONCURRENT-PARENT-REVIEW.md/PRECHECK.json,
  verify-seasonal-concurrent-parent.py en seasonal-concurrent-parent-evidence/
  COMMANDS.json/CHECKS.json, NATIVE/SANITIZER.json/log en oorspronkelijke PROBElog.
  Collectorveld corrigeerde alleen hergebruikte hashvariabele naar bestaande
  succesvolle proberesultaat; geen product-/test-/assertiewijziging of herhaling.
- Rollback alleen nieuwe gecorrigeerde broncommit na afhankelijke wijzigingen;
  parentDHW/Recorder/PLAN/historie/runtimedata bewaren. Geen runtimeactie gedaan.
- Volgende concrete F4/F6/F2actie bij dezelfde specialist: bestaande source-owned
  graph-/controllerprofielketen met expliciete seizoensselectie verbinden, zonder
  GUIkwalificatie/automatische selectie/fysiekeoutputs; admission/reconnect/
  bron-/DHW-/limits-/twee-zonefoutreplay en rollback aantonen. Bestaande actieve
  modelresource-, genericimage-, F9diagnose- en contact/personopdrachten behouden.
  Hele softwareplan in_progress; officiële hervattingsjob behouden, check15min.

#### Stage31 canonical postcheck en echte voortzetting

- Canonical e63b681 fast-forward samengevoegd, status schoon, commitdiffcheck en
  alle4acceptedbron-/10DHW-/Recorder-/PLANhashes PASS; bewijs
  SEASONAL-CONCURRENT-PARENT-POSTCHECK.json. Geen nieuwe runtime-/imageclaim.
- Concrete bronprofiel-/controllerintegratie hierboven met acceptatie en rollback
  aan dezelfde specialist aangeboden: followup287b5c7f QUEUED, geen completion.
  Actief modelresourcewerk en bestaande overige opdrachten blijven behouden.
- Eigen officiële job72ec7e68 geïnspecteerd/actief behouden; next_check15min
  daadwerkelijk bevestigd. Hele11785 blijft in_progress, niet stil gestopt.

### Mark11785 — F9/F0 modelresource/checkpoint: Stage32 onafhankelijk AFGEWEZEN

- [x] Canonicale echte hostcheckout e7b77da schoon; actuele §6/PLAN,
  specialistRESULT Stage32, memory_search/verified-taskflow werkelijk gelezen.
  Bestaand hostreceipt behouden. Eenmaal boundedhistory6 gaf interne projectiefout;
  eenmaal session_status gelezen, geen rawtranscripts/verzonnen specialiststatus.
- [x] Exacte11padenpatch b87b49dc/ec2c4b4, frozenarchive en26bewijshashes
  gecontroleerd. Eigen canonical-afgeleide reviewworktree;11voor-/nahashes exact,
  beschermde modellen/partitie en eerdere DHW/Recorder/PLAN behouden.
- [x] Echte hostgcc/g++17/cJSON/GTest:121nativePASS,13semantische rijen exact.
  Nieuwe onafhankelijke foutproef NIET-LEGE warm/coast/curverestore: hashcallback-
  reentry blokkeert gedeelde gate; alle3load() melden toch true en model.restore()
  wist storageFault. Dezelfde3FAIL native én volledige GTest/testTU-ASan+UBSan/
  leakdetectie; externe libcrypto niet geïnstrumenteerd. Geen outputvrijgave.
- [x] Oorspronkelijk Stage32pakket NIET samengevoegd. Herstelreview afgehandeld
  via gecorrigeerde Stage33 hieronder: alle3stores controleren gedeelde gate na
  decode/hash VÓÓR restore én vóór loaded_/true; faultlatch/no-extra-IO/retry
  behouden. Ongewijzigde parentprobe en nieuwe frozenbron geverifieerd.
  Dit is geen generieke resource-/runtimeacceptatie.
- Bewijs11774dossier: MODEL-RESOURCE-PARENT-PRECHECK.json/REVIEW.md/POSTCHECK.json,
  verify-model-resource-parent.py, model-resource-parent-decode-probe.cpp en
  model-resource-parent-evidence/COMMANDS.json/CHECKS.json/NATIVE.json,
  PROBE.json/log en SANITIZER-PROBE.json/log. Alleen eerste parent coast/curve-
  statusoracle gecorrigeerd; originele logs bewaard, gecorrigeerde3probes nogFAIL.
- Rollback exact11padencandidatepatch in reviewworktree uitgevoerd; review én
  canonical daarna schoon, allebeforehashes exact. Canonicalproductbron nooit
  gewijzigd; geen runtime/config/historie/installatie/publicatie/TX/EMS/actuatorGO.
- Nieuwe foutinformatie bij dezelfde actieve specialist via steer3ca61a49:
  accepted/steered is GEEN correctie/completion. Bestaand generic-size/contact-
  person/F9diagnose/seasonal-profielwerk behouden; hele11785software in_progress,
  fysieke/72u/verwarmingsgates ongewijzigd. Officiële hervattingsjob behouden;
  volgende check15min, niet stil stoppen na dit pakket.

### Mark11785 — F9/F0 gedeelde modelopslag: gecorrigeerde Stage33 bronacceptatie

- [x] Echte canonical hosttoegang op1927222 schoon; §6/PLAN, memory_search,
  verified-taskflow, actuele RESULT/Stage33 en eenmaal boundedhistory6 gelezen.
  Bestaand NIGHT-RUNTIME-CHECK-receipt niet herhaald. Specialist actief aan
  afzonderlijk F9guard-holdoutwerk; één bestaande uitvoeringseigenaar behouden.
- [x] Corrected FULL11pathrollup e24903fc onafhankelijk gereviewd; alle11voor-/
  nahashes, frozenarchive en38bewijshashes exact. Alleen volledige gecorrigeerde
  rollup gebruikt, NIET origineleStage32 of aanvullende5padendelta daarbovenop.
  Afzonderlijke canonical-afgeleide reviewworktree; modellen/codecsemantiek/
  partities/resourceledger byte-exact behouden; geen nieuwe productiecaller.
- [x] Actual hostgcc/g++17/cJSON/GTest:124nativePASS,13semantische rijen exact.
  EXACT ongewijzigde onafhankelijke parentCPP:3nonemptydecode-foutproevenPASS
  native én dezelfde3met volledig GTest/testTU ASan+UBSan/leakdetectie.
  Ieder: load0/gate0/store0, sticky storagefault,2hashcalls/1read/0writes.
  Externe libcrypto niet geïnstrumenteerd. Specialist24resourceASancases en
  pinnedSDKsizeof/framebewijs frozen-hashgecontroleerd; niet als extra eigen
  hostuitvoering of runtime-/volledigcallgraph-/freeheapbewijs geclaimd.
- [x] Canonical broncommit6f3be371d1ea5383886c329c11a68bbd336e44f9;
  exact11bronpaden, fast-forward, source/protectedhashes en schone status
  technisch nagecontroleerd. Stage32afwijzing en oorspronkelijke3FAILlogs blijven.
- Bewijs11774dossier: MODEL-RESOURCE-DECODE-PARENT-PRECHECK.json, REVIEW.md,
  POSTCHECK.json, verify-model-resource-decode-parent.py en
  model-resource-decode-parent-evidence/{COMMANDS,CHECKS,NATIVE,PROBE,
  SANITIZER-PROBE}.json plus compile-/runlogs. Herhaalbare hostverifier gebruikt
  echte bronheaders en onveranderde parentfoutproef; geen cronstatus als bewijs.
- Rollback vóór deployment: revert alleen broncommit6f3be37 na review van
  eventuele afhankelijken; geen modelbytes/config/history wissen, eerdere
  Recorder/DHW/PLANwijzigingen behouden. Geen installatie/buildrelease/publicatie,
  HA/brokerwijziging, login of EMS/TX/actuator/verwarmingsGO.
- [ ] Echte backend/provider/callgraph/heap/stack/NVS-GC/8zoneruntime/product-
  binding en normale firmware/release-/fysieke/72ugates blijven OPEN.
  Bronreservering en één individuele compilerframe zijn geen runtimeacceptatie.
- Concrete voortzetting bij dezelfde specialist via followup846a3936 queued:
  lopende F9guard-holdouts gescheiden afronden, daarna F2/F9/F0 opt-in bounded
  modelbackend en gepinde echte SHA-provider via bestaande ControlStore/
  Preferences/NVS, lengtecheck vóór allocatie, verse stats/commit/readback en
  reproduceerbare foutinjectie; geen configkey/partitie-/budgetverruiming of
  automatische runtimebinding. Admission is geen completion. Bestaande generic-
  OTAsize-/overige11785softwarebacklog blijft gelden; hervattingscheck15min.


### Mark11785 — F9 expliciete guard-holdouts: Stage34 onafhankelijke testbronacceptatie

- [x] Echte canonical hostcheckout b6bc35e schoon; actuele§6/PLAN,
  memory_search/verified-taskflow en RESULTStage34 werkelijk gelezen. Bestaand
  hostreceipt niet herhaald; eenmaal boundedhistory6 plus session_status:
  bestaande specialist actief aan samengestelde nativeHA/migratiereleasechecks.
- [x] Exact2paden-test/docpatch b9d61f1d5fc0089f79d9ececad9c529a4754b932501973ea8d800643806996bb
  gereviewd; beidevoor-/nahashes, frozenarchive en23bewijshashes exact.
  Canonical-afgeleide reviewworktree; alle6beschermde productieheaders exact.
- [x] Actual hostg++17 strict:13nativePASS; dezelfde13PASS met volledige echte
  GTest/replay/model/regulator/water/evaluatorTU ASan+UBSan/leakdetectie.
  Externe echteOpenSSL niet geïnstrumenteerd; native-onlynonPIE, geen productflags.
  Alle14semantische rijen exact native/sanitizer/specialist; alle velden van11oude
  oracles exact, geen versoepelde gates/retuning of gewijzigde modelbytes.
- [x] Onvergelijkbaar weer geeft0advies; window/DHW/fault remmen advies;
  180min geheel ontbrekende telemetrie levert geen verzonnen frames, wist
  test-referencepolicycache en vereist verseownerepoch.14arrivalpogingen/
  13gekwalificeerde observaties blijven apart. Geen productiecallerbewijs.
- [ ] Alle14modelassessments blijven AFGEWEZEN/ONVOLDOENDE; geen woning-/
  besparings-/modelnut-/fysiekeveiligheidsclaim.15kalibratie-/14holdoutdagen
  zijn synthetisch, geen echte meerdaagse/72uproef of modelowneracceptatie.
- Bewijs11774dossier: F9-GUARD-PARENT-REVIEW.md, verify-f9-guard-parent.py,
  f9-guard-parent-evidence/{PRECHECK,COMMANDS,CHECKS,NATIVE,SANITIZER}.json,
  echtebuild/runlogs en beideSCENARIOS.jsonl. Rollback alleen nieuwe2paden-
  test/docbroncommit vóór afhankelijken; resource6f3be37/data/Recorder/DHW/PLAN bewaren.
- Eerstvolgende uitvoering bij dezelfde specialist: bestaande samengestelde
  releasechecks afronden en bestaande boundedbackend846a3936 met echte SHAprovider/
  NVS-foutinjectie vervolgen, zonder dubbele owner of automatische productbinding.
  Generic-OTAsize/contact-person/F9diagnose/seizoensprofielen blijven softwarewerk;
  hele11785 in_progress. Niet geïnstalleerd/gepubliceerd; fysieke gates ongewijzigd.

## 7. Bijwerken na iedere taak — onderdeel van opleveren

1. Koppel vóór uitvoering taak-ID aan F/WP en concrete acceptatiecheck in dit bord.
2. Na het resultaat: werk dezelfde regels bij, zet alleen bewezen deeluitkomsten
   op `[x]`, voeg bron/versie toe en noteer eerstvolgende open bewijsactie.
3. Schrijf apart of iets gebouwd, geïnstalleerd, zichtbaar getest of fysiek bewezen
   is. Een overgeslagen/gewaivde check wordt geen PASS.
4. Verwijder achterhaalde actuele status uit register/profiel; verwijs hierheen.
   Taakdossiers blijven gedateerd bewijs, geen extra concurrerende werkborden.
5. Hand-off/eindantwoord bevat pas een afrondingsclaim nadat deze update en
   technische nacontrole zijn gedaan. Bij ontbrekend bewijs blijft de taak open.

## 8. Bewijsindex

- **B1:** [WP01-BASELINE](WP01-BASELINE.nl.md),
  [uitvoeringsbewijs](/home/dielessen/artifacts/open-thermostat-wp01-20261019/taskflow.md).
- **B2:** [WP02-CLASSIC](WP02-CLASSIC.nl.md), [68-veldenmanifest](boiler-field-parity.json),
  [bouwbewijs](/home/dielessen/artifacts/open-thermostat-build-20261020/taskflow.md).
- **B3:** [geïntegreerde testgrenzen](INTEGRATED-TEST.nl.md), [wireprofiel](TEST-WIRE.md),
  [contract](CONTRACT.nl.md); host-C++ is geen fysieke ESP32proef.
- **B4:** [dynamische kamerconfig](HA-DYNAMIC-CONFIG.nl.md), [weekeditor](HA-WEEK-EDITOR.nl.md),
  [parent GUI-/cleanupbewijs](/home/dielessen/memory/open-thermostat-week-editor-20261020.md).
- **B5:** [alpha.3-release](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.3),
  [alpha.4/bordgrenzen](/home/dielessen/artifacts/open-thermostat-auto-reboot-20261020/taskflow.md),
  [Mark11579 en continuïteit](/home/dielessen/memory/open-thermostat-project.md).
- **B6:** [gedateerde shadow-/bron-/testinfra-uitvoering](/home/dielessen/artifacts/open-thermostat-shadow-setup-20261020/taskflow.md).
  Dit is bewijs/historie; de actuele productchecklist staat uitsluitend hier.
- **B7:** [HA-productieonderhoud](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-maintenance-11686-20261020/RESULT.md),
  [parent hashes/readback](/home/dielessen/artifacts/open-thermostat-shadow-setup-20261020/maintenance-11686-parent-verification.json),
  [browserblokkade](/home/dielessen/artifacts/open-thermostat-shadow-setup-20261020/maintenance-11686-browser-route-check.json).
- **B8:** [deze planreconciliatie, review en documentatieverificatie](/home/dielessen/artifacts/open-thermostat-plan-reconcile-11694-20261020/taskflow.md).
  Een voltooid planonderhoud is geen voltooid product.
- **B9:** [onafhankelijke HA-/actuatorinventaris](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-plan-review-11694-20261020/REVIEW.md).
  Geen nieuwe runtimequery. Exacte bronhashvergelijking met actieve checkout en
  review van dit werkbord zijn in B8 vastgelegd; snapshotbevindingen niet als
  een nieuwe fysieke E32-/alpha.4-binaire audit presenteren.

- **B10:** [Mark11706/11709 centrale configuratiebronpakket](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-heating-config-11706-20261020/RESULT.md).
  Getoetst tegen exact ea54c256-archief; centrale native draftflow+validatiebasis,
  geen productie-installatie, volledige groeps-/profiel-GUI, transportcontract of fysieke support.
- **B11:** [parent bron-/contractreview en samenvoeging](/home/dielessen/artifacts/open-thermostat-heating-config-parent-20261020/taskflow.md).
  Broncommit c23bae2, 18/18 manifestchecks, negen afterhashes en reversecheck PASS;
  106 relevante native HA-tests onafhankelijk herhaald. Geen nieuwe installatie of fysieke acceptatie.

- **B12:** [native gewenste graph-CRUD en referentiële integriteit](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-graph-gui-20261020/RESULT.md).
  Baseline76cef4f,218nativePASS/1broker-opt-inSKIP; geen productie-installatie,
  E32-applycontract, live device-/elektrische-/hydraulische ondersteuning of fysieke GO.
- **B13:** [parent graph-bronreview en samenvoeging](/home/dielessen/artifacts/open-thermostat-graph-parent-20261020/taskflow.md).
  Broncommit d9d3b00; 21/21 dossierhashes, twaalf bronafterhashes, acht runnerbronnen
  en runnerbinaryhash PASS. Volledige native suite onafhankelijk218PASS/1SKIP;
  oude B12-telling216 gecorrigeerd op primaire finale log en onafhankelijke herhaling.
  Geen installatie, actieve wirewijziging of fysieke acceptatie.


- **B14:** [desired-roommigratie en graph-applyvoorstel](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-room-contract-20261020/RESULT.md).
  Basis daf5347; native bronacceptatie239PASS/1broker-opt-inSKIP, overlappend met
  eerdere suites, niet optellen. Capabilities/schema2 zijn een reviewvoorstel,
  niet geïmplementeerde firmware. Zie [HA-GRAPH-APPLY-PROPOSAL](HA-GRAPH-APPLY-PROPOSAL.nl.md).
  Geen uitrol, fysieke proef of source-/actuator-/ketelvrijgave.
- **B15:** [parent room-/contractreview en samenvoeging](/home/dielessen/artifacts/open-thermostat-room-contract-parent-20261020/taskflow.md),
  [firmware-/budgetreview](/home/dielessen/artifacts/open-thermostat-room-contract-parent-20261020/firmware-review.md).
  Bron afcf2ed;31/31manifest,15afterhashes,8runnerbronnen/binary,reverse/diff PASS;
  onafhankelijk239nativePASS/1expliciete brokerSKIP. Actieve wire/firmware behouden.
  Alleen bronacceptatie; qualifiers/validators/apply en fysieke E32acceptatie open.


- **B16:** [losse gedeelde graph-shadowvalidators en gemeten native budget](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-graph-validator-r2-20261020/RESULT.md).
  Basis e16c4e6; zie [exacte testspecificatie](GRAPH-SHADOW-VALIDATORS.nl.md).
  Pure bronacceptatie346PASS/1broker-opt-inSKIP; gedeelde fixtures zitten in die
  telling. Geen nieuwe MQTT/Store/applyGUI/capadvertentie, geen actieve profielen,
  ESP32heap/NVS/latencybewijs of fysieke GO. Onafhankelijke parentreview PASS;
  bron samengevoegd als a6cb9cc. [Parentbewijs](/home/dielessen/artifacts/open-thermostat-graph-validator-parent-r2-20261020/RESULT.md):
  43/43r2 +29/29origineel,9afterhashes,98fixtures,15originele typeprobes,
  556nativefaultsites zonder leaks; ongewijzigde parentfaultprobe ook PASS.
  Native suite346PASS/1brokerSKIP zowel schone toegepaste patch als mergedcheckout
  (overlap, niet optellen). Geen runtime-import/installatie of fysieke vrijgave.
