# OpenThermostat — actueel uitvoeringsplan

**Bijgewerkt:** 20 oktober 2026, naar aanleiding van Mark11694.
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
  helpervrije weekeditor, setup/OTA-bronwerk.
- **Geïnstalleerd:** HA-kamer-/weekeditorpakket; alpha.3-basis op het bord door Mark
  bevestigd, inclusief beide tabs en instellingenbehoud. Alpha.4 gepubliceerd;
  installatie en automatische herstart daarvan niet afzonderlijk bevestigd.
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
eigen begrensde bronwijziging; in deze planreconciliatie is niets verwijderd.

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

- [ ] Exacte menu-/route-/configreferentielijst maken voor HA-managed mode.
- [ ] Dubbele instellingen verbergen/read-only maken; onduidelijk label corrigeren.
- [ ] Routeautorisatie en enige configschrijver ook server-side afdwingen;
  alleen een knop verbergen lost dubbel eigenaarschap niet op.
- [ ] Bestaande instellingen behouden/importeren; modewissel, reboot, rollback,
  setup/OTA en generieke/legacytargets controleren vóór broncode verwijderen.
- [ ] Nieuwe release en fysieke gebruikerscheck apart uitvoeren. Geen extra
  firmwareflash of productieonderhoud uitsluitend vanwege dit document.

### Afzonderlijke open vervolgtaak — login Mark11732/11734

- [ ] **Mark11732 login-/sessie-UX:** normaal loginvenster met blijvende sessie
  als gewenste richting vastgelegd (parentterugmelding Telegram11734).
  Eerst afzonderlijke bron-/runtimegebonden diagnose; oorzaak nog NIET bewezen.
- [ ] Authbronfix met eigen doel/baseline/diff/tests/rollback en handoff opleveren,
  gescheiden van graphvalidator-GV-R1/GV-R2. Sessieduur, herstel/logout en
  beveiligingssemantiek niet uit de wens afleiden of stil verzwakken.
- [ ] Afzonderlijke scherm-/productacceptatie na bronreview; deze tracking is
  geen productie-installatie/herstart of authconfig-/apparaatwijziging.

Bewijs/taak: [logintracking11732](/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-auth-11732-tracking-20261020/TRACKING.md).
Eigenaar: parent houdt canoniek werkbord/taakbrief; bronfix apart specialistpakket.
Oorspronkelijke11732opdracht uit sanitized history hersteld; afzonderlijke
specialistfollowup330ce07f geaccepteerd, resultaat nog open. Geen tweede uitvoering.
Validatorreview kan onafhankelijk afgerond worden; geen tweede loginuitvoering.

## 5. De 11 productfasen — bijgewerkt en afgevinkt waar bewezen

### F0 — basis, upstream en installatieprofiel · in_progress

- [x] WP01-bronkeuzes, builds en behoud van E32partities/locks softwarematig
  gecontroleerd; Arduino3 nu niet overgenomen, begrensde platform7.1.3/Arduino2basis [B1].
- [x] Alpha.3 op bord, beide tabs laden en instellingen behouden: door Mark
  bevestigd [B5]. Dit is operatoracceptatie van die basis, geen volledige F0.
- [ ] Volledig woning-/device-/hydrauliekprofiel en dependency-/capaciteitsacceptatie.
- [ ] Resterende fysieke netwerk/load/PSRAM/restorechecks; alpha.4-installatie en
  automatische reboot apart aantonen. De oorspronkelijke flashbackupwaiver van
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
  HA-managed E32bediening opschonen volgens §4.

**Eigenaar:** HA-specialist, firmware voor contract/UI. **Fase klaar als:** native
bediening en werkelijke profielen met juiste single-writer/status/migratie bewezen.
**Volgende:** gedeelde exacte fixtures en pure Python/C++validators voor graph-shadow,
met totale parser-/schedule-/streambudgetten en expliciete onvolledige bron-/device-
kwalificatie; nog los van actieve MQTT/Store/applyGUI. Daarna pas gereviewde
capabilityadvertentie, persistence/reconnect/readback en bron-/GUIacceptatie;
HA-managed E32-afbouw blijft een aparte bronstap;
browsercheck hervat bij beschikbare bestaande sessie, blokkeert bronwerk niet [B4,B7].

### F4 — regelkern en hydraulische supervisor · pending

- [ ] Moderne radiator-/vloer-/klepprofielen, waterdoelen/stooklijn per circuit,
  minimumflow, opening/readiness/start/stop/naloop/DHW en vorst/zomer bewijzen.
- [ ] Gezamenlijke vraag voor A/B/samen/allesuit en fout-/stalescenario's testen.

**Eigenaar:** firmware, onafhankelijke review HA-specialist. **Fase klaar als:**
volledige deterministische supervisoracceptatie uit PLAN§14 F4 groen; legacycurve
en shadowdoel alleen voldoen niet. **Volgende:** scenario-/contractgestuurde
software-implementatie zonder TXvrijgave [PLAN§7/14, B3].

### F5 — betrouwbare grafieken en diagnose · pending

- [ ] Counters/interval-/stale-semantiek, vraag versus werkelijke keteldata,
  juiste HA-statistieken, tijdlijnen, gaten/reboot/CSV en mobiele UX aantonen.

**Eigenaar:** firmware + HA-specialist. **Fase klaar als:** meet-/schatlabels en
data-integriteit met onafhankelijke verwachtingen kloppen. **Volgende:** bestaande
metrics en pariteit hergebruiken, onbetrouwbare vlam/gas/flow niet als feit tonen [B2, PLAN§11].

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

Dit is werkvolgorde, geen extra onderhouds-/actuatieautorisatie. Bestaande
softwareautorisatie blijft geldig; geen onnodig nieuw algemeen akkoord vragen.

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
