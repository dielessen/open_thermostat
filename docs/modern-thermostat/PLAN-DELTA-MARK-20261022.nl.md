# PLAN-delta van Mark — 22 oktober 2026

**Voor:** OpenClaw (parent), enige canonieke schrijver van PLAN en WORKBOARD.
**Bron:** Marks branch `review/mark-vscode-20261021`, op basis van `defd2ae`.
**Aard oorspronkelijke planwijziging:** alleen documentatie. De latere lokale
software-uitvoering staat apart hieronder; geen installatie, publicatie of
verwarmingswijziging. Eisen R01–R31 en de acceptatiecriteria van
F0–F10 zijn inhoudelijk ongewijzigd; er zijn alleen verwijzingen bijgekomen.
Deze kwalificatie betreft de oorspronkelijke planwijziging. De aanvullende
product-/GUI-eisen van Mark staan gedateerd onderaan; die scherpen de acceptatie
van bestaande eisen aan en moeten eveneens canoniek worden geïntegreerd.

## Nieuwe besluiten van Mark

1. **Tado V3/V3+ vervalt als regelaar** zodra OpenThermostat de ketel regelt. De
   ketelkoppeling wordt fysiek losgekoppeld (één schrijver). De Tado mag een
   kiesbare kamertemperatuurbron worden, bij voorkeur lokaal via HomeKit Controller.
   Tot en met de F6/F7-commissioning blijft hij de werkende verwarming en daarna de
   gedocumenteerde rollbackregelaar. PLAN §6.3, §12, §16 en §17.
2. **Kritisch pad:** een haalbaarheidsvoorproef van de ketelstop/timeout van de
   HRC22H en de fysieke terugval, zonder TX of ketelwrites, vóór verdere
   verbreding. Een negatieve of onbekende uitkomst legt het besluit uit §12 nu terug.
3. **WIP-limiet:** geen nieuwe F9-, F10- of P2-bronstages tot M2 bewezen is;
   lopend werk mag worden afgerond. PLAN §14, begin.

## Opschoning van PLAN.nl.md

- De kop bevat geen status meer; die staat alleen in WORKBOARD.
- Het besluitenlog van §1 (Mark11883/11944/11950/11956) is letterlijk verplaatst naar
  het nieuwe [BESLUITEN.nl.md](BESLUITEN.nl.md); §1 heeft een korte samenvatting.
- Eenduidige mijlpalen: **M1** = de softwareketen met twee kamers
  (ARCHITECTURE-DECISION §5), **M2** = de eerste fysieke kamerketen (één kamer, echte
  bron → E32 → configACK, plus een echte kraan zonder ketel).
- §9: het genomen schemabesluit vastgelegd (lokale weekeditor standaard, HA
  Schedule-helper als alternatief, precies één per kamer).
- §13 verwijst naar route B en het herbouwmandaat.
- De statusalinea in §15 is vervangen door een verwijzing naar WORKBOARD §6.

## Gevraagd aan OpenClaw voor WORKBOARD

- F0, woningprofiel: open punt voor de Tado V3/V3+ (koppeltype, ontkoppelen,
  werking als sensor, lokale HomeKit-route, gemeten meetfrequentie).
- §6, uitvoeringsvolgorde: mijlpalen M1/M2 en de WIP-limiet opnemen.
- F6: de haalbaarheidsvoorproef van de ketelstop als eerste concrete bewijsactie.
- Deze delta canoniek integreren of gemotiveerd afwijzen; Marks branch niet
  overschrijven.

Rollback: de commit met deze delta op Marks branch terugdraaien.

## Uitvoering in VS Code — 22 oktober, na deze planwijziging

- Mark bevestigt de Bosch iRT↔EMS-converter en dat Tado EMS spreekt. Deze
  protocolketen is gebruikersinformatie; exacte fysieke uitvoering en veilige
  timeout blijven apart te bewijzen.
- De vroege [F6-documentatie-/bewijsvoorproef](KETELSTOP-VOORPROEF.nl.md) is
  uitgevoerd zonder device-IO. Primaire historische commands/Recorder opnieuw
  gecontroleerd: expliciete nul → CV uit na11,825845s. Geen bewijs voor veilige
  stop bij communicatie-/controlleruitval. Het §12-beslispunt staat daarmee nu
  expliciet open; een handmatige Tado-rollback is geen automatische uitvalstop.
- Begrensde M1-afwerking: native HA-enable/prepare geeft specifieke uitleg bij
  acht totale UTC-overgangen of4096Boverschrijding, met behoud van opgeslagen
  kamer-/journal-/apparaatdata. Geen capaciteitsverruiming of volledige R18claim.
- Lokale bewijsmap: `out/critical-path-20261022`, inclusief TaskFlow,
  herberekening/hashes, C++-peer en native HA-testlogs.151verschillende gerichte
  HA/C++-gevallen PASS; twee verouderde brugtestlabels bijgewerkt na bevestiging
  van dezelfde mismatch op de ongewijzigde basis. De code is niet geïnstalleerd.
- Aanvulling voor de canonical WORKBOARD-review: leg de protocolbevestiging,
  uitkomst van de F6-voorproef en de concrete volgende converter-/stopbewijsactie
  vast; M2 en F6 blijven open. Geen wijziging aan de andere canonical checkout.

## Lokale testkandidaat — vervolg op Marks hele-planopdracht

- Mark bevestigt de badkamer met zelf later te selecteren sensor en TRV als
  eerste proefkamer. Geen vaste woningentiteiten of verplichte tweede kamer.
- Nieuw expliciet `control.plan.week.v1`-SOURCE/plancontract: één of twee kamers,
  maximaal128UTC-punten per kamer binnen bestaande4096Bconfig/8192Bwire/JSONgrenzen.
  Oude contracten blijven gesloten voor dit formaat. Volledige28blokkenweekschema's
  zijn zonder afkappen opgeslagen en teruggelezen. Geen extra owner/Store/timer.
- Ongewijzigde lokale weken kunnen via de bestaande dagelijkse callback en
  verse exacte readback hun horizon vernieuwen. Oude-vensterhercompilatie bewijst
  dat geen gewijzigd gebruikersplan wordt meegestuurd. Helpers/concepten/onzekerheid/
  verlopen horizon blijven expliciete review vereisen.
-249verschillende gerichte HA2026.10.2/C++-gevallen hebben een groene einduitkomst,
  inclusief ASan/UBSan op controller/cJSON; het nieuwe compacte evaluatorpad is
  eveneens geïnstrumenteerd. DST per seconde, grenzen, oude contracten, uitval,
  ownerwissels tijdens laatste await, storagefouten en éénkamerherladen getest.
  Eerste runs met een verkeerde testfixture blijven als zodanig bewaard; telling
  komt uit unieke eindgevallen, niet uit opgetelde overlappende runs.
- Werkelijke gepinde HA2026.10.2-frontend/Chromium desktop1440×1000 en mobiel390×844:
  native kamer-/week-/groepsinrichting, onafhankelijk profiel, runtime-enable,
 121puntenreview, annuleren en apply via een echte geïsoleerde Mosquitto2.0.22
  naar dezelfde C++-controller/store. Eén write;1888Bconfig exact gelijk aan
  het duurzame native HA-journal. Geen echte deviceHTTP/NVS of bronkwalificatie.
-34release-auditregressies en volledige actuele HA-bron-/import-/notice-inventaris
  PASS. Historische firmware-/SDKreceipts worden niet herlabeld. Kandidaatversie
  `v0.1.0-e32v2-alpha.7`; normale app/FS en guarded packaging worden apart vastgelegd.
- Eerste normale app/FS op `63be9bc` PASS;22ingebouwde webassets en31werkelijk
  teruggelezen SPIFFS-bestanden exact. Op deze werkelijke build bleek de auditor
  een geldige4170secties tellende ELF af te wijzen. Alleen die hostaudit is
  gecorrigeerd: de volledige sectietabel moet binnen het bestand liggen; ELF32
  begrenst het aantal al tot16bits. Firmware/configbudgetten blijven ongewijzigd.
  Finale bron-/image-identiteit staat in het lokale IMAGE-CHECK- en POSTCHECK-bewijs.
- Instructies: [testkandidaat](TESTKANDIDAAT-20261022.nl.md), technische definitie:
  [ControlPlan](NATIVE-CONTROL-PLAN.nl.md). Bewijs: `out/release-candidate-20261022`.
  Die lokale map bevat aparte testcredentials en mag nooit integraal gedeeld worden.
- M2/F6 en normale verwarmingsvrijgave blijven OPEN. Gekwalificeerde continue
  meet-/safetyproducers, fysieke kraan/ketelstop, hardware/update/recovery/resources,
  overige F0–F10 en SDKbron/licentieclosure zijn hiermee niet afgevinkt.

## Live HA-inrichting — vervolg op Marks beheeropdracht

- Mark geeft toestemming om zelfstandig HA-instellingen te controleren en aan
  te passen, inclusief een HA-herstart indien nodig. De defecte badkamersensor
  mag voor de configuratieproef worden vervangen door de motion-apparaattemperatuur.
- Via de bestaande HA-specialist is de testentry `opth_bath_shadow_20261020` in
  HA2026.10.2 van `legacy` naar `v1_shadow` gezet. Verse readback en een aparte
  vergelijking van vóór-/na-opties bevestigen dat alleen die modus veranderde.
  Runtime en kameractuatie blijven uit; de oorspronkelijke `ib-therm` is niet
  gewijzigd. Een HA-herstart was niet nodig.
- Het badkamerformulier opent nu zonder de eerdere 404. Motion-temperatuur en
  badkamer-TRV waren al bewaard; basis21°C, grenzen5–35°C, kameridentiteit en
  programmagegevens zijn niet veranderd. De volledige weekinhoud is niet gelezen.
- De beschikbare HA-beheertool biedt geen gedocumenteerde manier om dezelfde
  meerstaps-subentryflow met de gegenereerde groeps-ID te hervatten. Er is daarom
  geen verwarmingsgroep opgeslagen en geen halve graphkamermigratie uitgevoerd.
  De kamer blijft voorlopig `climate_trv`; de nieuwe volledige planroute is nog open.
- De huidige bron geeft voor de ongeldige combinatie van kamermodus en directe
  TRVs een leesbare uitleg in de werkelijke gepinde HA-frontend. Een ongeldige
  submit wijzigde daar geen bindings of doelen. Dit was een geïsoleerde proef;
  de exacte live bronhash en de oorzaak van Marks eerdere kale foutcode blijven
  onbekend. Er is voor deze controle geen productcode gewijzigd.
- Voortgang en vervolgstappen staan in de [testinstructies](TESTKANDIDAAT-20261022.nl.md).
  Lokaal bewijs: `out/ha-bathroom-setup-20261022`; de officiële specialist bewaart
  afzonderlijke vóórsnapshots en rollbackgegevens. M2, E32-/SOURCE-acceptatie,
  fysieke kraan-/ketelproeven en releaseblokkades blijven open.

## Eenvoudige kamerinrichting — volgende afgestemde bronfase

- Mark vraagt expliciet om de omslachtige handmatige kamer-/groepsinrichting
  eerst te vereenvoudigen. Na deze fase stemmen we samen de installatie af;
  er wordt niet stilzwijgend doorgegaan naar productie- of fysieke proeven.
- Nieuwe native HA-route **Radiatorkamer instellen** voor nieuwe en bestaande
  kamers: naam, temperatuursensor, TRVs, doel en optioneel weekprogramma.
  Eén bevestiging bewaart kamer en automatisch aangemaakte/hergebruikte groep.
  Geavanceerde instellingen blijven afzonderlijk bereikbaar. Geen extra
  transport, opslagowner, timer of firmwarecontract; SOURCE/runtime blijven behouden.
- De twee losse publieke HA-subentrycallbacks bleken eager listeners tussen
  de wijzigingen te activeren. De nieuwe route gebruikt daarom één complete
  subentry-maptransactie van dezelfde HA-coreopslag. Dit is een private core-API:
  de wizard is expliciet beperkt tot geteste HA2026.10.2 en weigert andere versies.
  Bestaande geavanceerde comfort-/vloer-/externe regelingen worden niet omgebouwd.
-254tests PASS:20wizardgevallen plus200bestaande native HA/C++-gevallen en34release-
  audits. Werkelijke HA-frontend desktop/mobiel: bestaande kamer, voorgeselecteerde
  apparaten, dichtgeklapt Geavanceerd, review, annuleren en één keer opslaan.
  Afzonderlijk Nederlands mobiel formulier gecontroleerd. Geen woningapparaat-IO.
- HA-kandidaat **0.4.0.dev2**, broninventaris62bestanden, exacte werkkopiehashes en
  apart HA-bronpakket `OpenThermostat-HA-0.4.0.dev2.zip`; oude download behouden.
  Bewijs: `out/simple-room-20261022`. Nog niet op Marks HA geïnstalleerd.
  De volgende afgesproken stap is installatie met back-up/herstart en daarna
  de badkamer via deze route inrichten. M2/F6 en firmware-releasegates blijven open.

## Automatische HA-installatie — expliciet gevraagd vervolg

- Mark vraagt de update zelfstandig te installeren. De bestaande File editor6.2.0
  via de geautoriseerde HA-/Ingress-route blijkt daarvoor bruikbaar; geen nieuwe
  login, proxy, service of updater. Marks eerdere handmatige route was Samba.
- Native volledige HA-back-up faalt op ontbrekend standaard back-upwachtwoord.
  Geen credentialwijziging. In plaats daarvan volledige bronmapkopie buiten
  `custom_components`:99bestanden, byte-exact onafhankelijk gecontroleerd.
- De bevroren HA-ZIP is via native File editor-tekstoverdracht en base64 veilig
  gestaged. Alle62kandidaatbestanden exact tegen SOURCE vergeleken. Gereviewde
  bronmapvervanging met directe herstelbranch lokaal getest, inclusief gesimuleerde
  laatste-renamefout. Actieve dev2bron en beide oude kopieën daarna weer gelezen.
- Native configuratiecheck geldig, precies één HA-herstart. Verse onafhankelijke
  leescontrole22oktober13:03CEST: HA2026.10.2 healthy/supported, beide entriesgeladen,
  manifest0.4.0.dev2, identieke persistente opties/identiteiten/subentrylijsten;
  nieuw `room_setup`-formulier beschikbaar. Runtime en badkameractuatie uit.
- Geen nieuwe kamer/groep of SOURCE geselecteerd; één bestaande kamer, geen
  heating-subentry. Repairrecords behouden; hun dismissalversie wijzigt tijdens
  de laatste waarnemingen naar2026.10.2, zonder repair-mutatie door de installer.
  Oorzaak onbekend; geen historie/meterreset. Bewijs: `out/ha-install-dev2-20261022`.
- Deze installatiefase is afgerond. Eerst met Mark afstemmen over het invullen
  en bewaren van de bestaande Badkamer via de nieuwe wizard. Fysieke proeven,
  M2/F6, firmwarelicentieclosure en overige eerdere gates blijven open.

## Product-/GUI-aanvulling — nieuwe planopdracht van Mark, 22 oktober

- Mark vraagt om een zeer gebruiksvriendelijk eindproduct met de reeds besproken
  slimme thermostaatfuncties, een duidelijke grafische weekplanner en een snellere,
  opgefriste E32-GUI. Dit stuurt de volgende fase; de eerdere voorgestelde
  badkamerinrichting is niet stilzwijgend uitgevoerd.
- Lokaal [PLAN](PLAN.nl.md) §1, R18/R29, §9, §11, §13 en §14 aangevuld en
  [BESLUITEN](BESLUITEN.nl.md) uitgebreid. De 31 eisidentiteiten en prioriteiten
  blijven behouden; gebruikservaring en dashboard-/opschoonacceptatie zijn concreter.
- Weekblokken tonen begin/einde en temperatuur; openen/bewerken, dagen kopiëren,
  duidelijke concept-/opslaan-/annuleerroute, basisdoel en override/hervatten.
  Het bestaande native blokveld is bevestigd in de bron; een volwaardige intuïtieve
  grafische planner is daarmee niet bewezen of afgevinkt.
- E32-startdashboard: samenhangend keteloverzicht, opdrachtentijdlijn en kamervraag
  met redenen. Berekening/verzending/bevestiging/werkelijke terugmelding blijven
  gescheiden; geen verzonnen nul, vlamstatus, klepstand of gemeten kamerverbruik.
- E32-opschoning omvat werkelijk verwijderen van overbodige functies, routes,
  assets en afhankelijkheden in de betreffende build na gecontroleerde migratie.
  Functie-inventaris, behoud van afgesproken functies/recovery en fysieke
  voor-/nameting van snelheid/resources/regel-/UART-timing horen bij acceptatie.
- HA blijft normale configuratie-/bedieningsplek. Geen nieuwe scheduler, database
  of configuratie-eigenaar; geen nieuwe F9/F10/P2-stage vóór M2. Deze ronde wijzigt
  alleen de drie lokale plandocumenten; geen WORKBOARD, productcode, HA-inrichting,
  installatie, E32-flash of fysieke aansturing.
- Gevraagd aan de canonieke eigenaar: deze aanvulling in PLAN/BESLUITEN en de
  bestaande F3/F5/F10-/migratieverwijzingen reconciliëren zonder bestaande
  veiligheids-/releasepoorten of werkvolgorde af te vinken.
- Na afronding van deze planfase: met Mark afstemmen over een concreet schermontwerp
  van weekplanner en E32-startdashboard als volgende afgebakende stap. Bewijs en
  rollback van deze documentwijziging: `out/plan-product-ux-20261022`.

## Samenhangende HA-inrichting — verdere concretisering door Mark

- Mark vindt de integratie rommelig: oude E32-configuratie is lastig te verwijderen
  en de meerdere toevoeg-/configuratieroutes zijn onduidelijk. Gewenst: één centrale
  ketel-/installatieconfiguratie, ruimtes via een wizard met radiator/vloer/combinatie,
  passende sensoren en kranen/kleppen, Geavanceerd apart en uitleg/impact bij elk veld.
- [PLAN §5](PLAN.nl.md#5-domeinmodel-en-configuratie-eigenaarschap),
  [BESLUITEN](BESLUITEN.nl.md) en [HA-inrichting](HA-INRICHTING-UX.nl.md) leggen de
  concrete route en migratie-/verwijderacceptatie vast. Klikbaar ontwerp:
  [HA-inrichting.html](ontwerp/ha-inrichting.html). Dit is fictieve lokale interactie,
  geen geïnstalleerde HA-frontend of nieuwe configuratieopslag.
- Broncheck bevestigt de drie huidige toevoegtypen `room_setup`/`zone`/`heating`
  en een aparte legacy-MQTT-kamerroute. De live HA-specialist leest op 22 oktober
  13:23 CEST twee entries: legacy `ib-therm` en de testentry met Badkamer én één
  centrale verwarmingssubentry. Runtime/actuatie staan uit. De legacy hub heeft
  40 telemetrie-entiteiten; geen actuele oude kamer-ID/naam is vastgesteld.
  Dus niet aannemen dat de tekst `woonkamer_` in entity-ID's een huidige kamer bewijst.
- Deze specialistcontrole was uitsluitend lezen. Geen oude entry/kamer/entity
  verwijderd, geen configuratie, device-opdracht, herstart of E32-actie. Bewijs:
  specialistartifact `openthermostat-config-ux-review-20261022/READBACK.json` en
  lokale TaskFlow `out/ha-configuration-ux-20261022`.
- Canonieke eigenaar: integreer deze aangescherpte F3/R29-/migratieacceptatie met
  behoud van R01–R31, bestaande werkvolgorde/WIP en fysieke/releasepoorten. Na de
  concrete ontwerpoplevering de afgebakende native implementatiefase met Mark afstemmen.

## Status en volgorde verduidelijkt — op verzoek van Mark

- Mark vraagt waar we staan en wat nu eerst moet gebeuren. PLAN §14 benoemt de
  eerstvolgende afgebakende bouwfase: de ontworpen centrale installatie-/ruimte-
  inrichting in de echte HA-integratie realiseren, inclusief uitleg, Geavanceerd
  en behoud/beheer van bestaande configuratie. Radiatorroute eerst afronden;
  overige profielkeuzes pas uitvoerbaar tonen wanneer werkelijk ondersteund.
- De [testinstructies](TESTKANDIDAAT-20261022.nl.md) beginnen nu met een gedateerd
  onderscheid tussen geïnstalleerd, softwaregetest, alleen ontworpen en fysiek open.
  De oude technische shadow-invulroute staat als naslag, niet als nieuwe taak voor Mark.
- Historische installatiecontrole 13:03 CEST behouden; de latere HA-lezing van
  13:23 CEST toont inmiddels één centrale verwarmingssubentry. Volledige bindings/
  groepsinhoud en exacte oude kamerbron zijn nog niet bekend. Geen nieuwe live
  controle in deze statusronde, geen instelling of apparaat gewijzigd.
- Vervolg: implementatie → geïsoleerde echte HA-controles → nieuwe HA-installatie
  met back-up → Badkamer controleren → afzonderlijke M2 zonder ketel. Ketelstop/
  uitval, hardware, firmwarebron-/licentieclosure, de grotere E32-GUI-opdracht en
  overige productfasen blijven open. Geen WIP-/vrijgavepoort opgeheven.
- Canonieke WORKBOARD-eigenaar blijft verantwoordelijk voor statusreconciliatie;
  deze ronde wijzigt alleen lokale PLAN/testinstructies/delta. Documentbewijs en
  rollback: `out/status-and-next-phase-20261022`.

## Correctie opstelling en configuratie — E32 los, direct normale productroute

- Mark bevestigt dat de E32 los van de ketel staat en OpenThermostat geen productie
  draait. Hij wil direct de uiteindelijke normale inrichting en geen afzonderlijke
  schaduwconfiguratie. Dit is gebruikersinformatie over de fysieke opstelling;
  er is in deze ronde geen onafhankelijke bekabelingsproef uitgevoerd.
- PLAN begin/§14, BESLUITEN, HA-INRICHTING-UX en de testinstructies aangepast:
  één installatie, centrale instellingen, ruimtewizard en gewone verbindings-/
  toepassingsstatus. Geen verplichte legacy/shadowkeuze, adapter-ID-/profiel-/
  graph-/preparestappen of later opnieuw in te vullen productieconfiguratie.
- Bestaande OpenThermostat-testconfiguratie mag na gerichte back-up vervangen
  worden door één schone inrichting waar hergebruik niet zinvol is. Geen zware
  productiemigratie voor wegwerpbare testdata; overige HA-integraties, devices,
  credentials en Recorderhistorie vallen buiten die opruimscope.
- Broncheck: `MODE_SHADOW`, `shadow_enabled` en `graph_only_draft` sturen werkelijk
  configuratie-/runtimegedrag. De productbouw omvat de echte route en voorwaarden,
  niet alleen nieuwe labels of ongecontroleerd inschakelen. Interne bench-/
  replaytests blijven bruikbaar. De bestaande 31 functies blijven vereist.
- Eerdere shadowbewijsstukken en WORKBOARD worden niet herschreven. Canonieke
  eigenaar: neem deze nieuwere gebruikerskeuze over als vervanging van het
  afzonderlijke shadow-gebruikerspad. Commissioning van de ketel blijft later;
  ketelstop-/fysieke-/releasevoorwaarden zijn geen blokkade voor normale GUI-inrichting.
- Deze planronde wijzigt geen HA-/E32-code, instelling of fysieke uitvoer.
  Bewijs en rollback: `out/normal-product-config-20261022`.

## Uitvoering normale productroute en E32-dashboard — vervolg op doorwerkmandaat

- Mark vraagt bekende taken door te voeren zonder verplichte afstempauzes of
  wachten op optionele antwoorden. PLAN-uitvoeringsafspraak daarop aangepast;
  geen scope-/WIP- of fysieke poort opgeheven.
- Native HA-productroute dev3 gebouwd: één centrale configuratie in bestaande
  parententry, gewone radiatorruimtewizard, bestaande bindingen voorgeselecteerd,
  hulp/impact en gesloten Geavanceerd. Aanpassen/verwijderen met gezamenlijke
  conflictdetectie en opslag, weekdagen kopiëren. Geen tweede Store/regelaar.
- Opslagversie3-migratie: Badkamer-ID/data en centrale JSON exact bewaard;
  normale route importeert geen oude E32-MQTTkamers. Bestaande passieve hub-/EMS-
  telemetrie blijft via dezelfde integratie beschikbaar, zonder commandopublisher.
- 1316 nativeHA-gevallen PASS,2 optionele brokergevallen SKIP;34 releasegevallen
  plus6 subtests PASS. Echte native frontend desktop/mobiel en afzonderlijke
  geïsoleerde MQTT-telemetrieproef PASS; geen fysieke M2-vrijgave.
- Onveranderlijke HAdev3-kandidaat geïnstalleerd met65 exacte bronhashes,
  bron/config/registryback-ups, nativeconfigcheck en één herstart. Verse
  14:51–14:53 CEST controle: Coregezond en2entriesloaded. Legacydefaultaanvulling
  integration_mode=legacy verklaard uit de bron; originele strikte FAIL behouden.
- Geautoriseerde consolidatie naar één ib-therm-installatie met hergebruik van
  badkamer-/centrale waarden is uitgevoerd via native HA-flows. CentraleJSON en
  badkamerwaarden exact vergeleken, nieuwe interneIDs onder expliciete devreset
  geregistreerd;15:16 CEST één loadedentry, Coregezond en configcheckvalid. Twee
  externe authenticatie-/verloopvelddrifts afzonderlijk gemeld, niet teruggezet. Geen live .storage-write, runtimeactivering
  of apparaatcommando. Bewijs in de testinstructies.
- E32-F3/F5-bronwerk: read-only startdashboard, ketelreadback apart van berekende
  kamervraag en autoriteit,4KiB cache van dezelfde owneruitvoer met verval5s,
  lokale begrensde trends. Geen extra poller/client/commandpad of verborgen
  activering. Oude interne controlMode-wirewaarde blijft compatibel.
- Dit sluit niet alle R29/F3/F5-eisen: menselijk leesbare namen ontbreken nog in
  de bestaande firmwarepayload, bevestigde opdrachtentijdlijn en hardware-
  performancebewijs ontbreken, volledige legacy-afbouw en commissioning blijven
  open. Geen firmwaredistributie/flash om de SDKpoort heen.
- Canonieke eigenaar: integreer deze concrete bron-/installatie-uitkomsten met
  hun afzonderlijke open checks. Marks branch en canonicalWORKBOARD niet door
  een automatisering overschrijven. Bewijs: out/product-ha-20261022 en
  out/e32-dashboard-20261022.

## Native installatiegroep — gebruikersvraag over de restgroep

- De Engelse standaardgroep voor apparaten zonder subentry wordt in HAdev4
  vervangen door **Installatie en ketel** via een automatische lege native
  presentatie-subentry. Centrale instellingen blijven uitsluitend in de
  parententry; alleen ruimtes zijn gewone toevoegkeuzes. Geen tweede
  configuratie-eigenaar, apparaat of regeling.
- Bestaande centrale apparaat-/entiteitsidentiteiten worden synchroon aan die
  groep verbonden vóór de Core-device-events. Nieuwe telemetrie gebruikt
  dezelfde groep. Badkamer behoudt haar eigen identiteit en koppelingen.
- Bron: 1321 native HA-tests PASS,2 optionele brokerscenario's SKIP;
  34 release-auditgevallen PASS. Echte gepinde HA-frontend desktop/mobiel PASS,
  inclusief afwezigheid van de oude restgroep. Geen HAcore-/CSSpatch.
- Onveranderlijke kandidaat HA0.4.0.dev4 met66 exacte bronbestanden is
  geïnstalleerd: geldige nativeconfigcheck, één herstart, gezondeCore en geladen
  dev4. Verse nacontrole16:19CEST en onafhankelijke rootvergelijking: dezelfde
  eneentry,2devices36entities;35centraleentities in Installatie en ketel,
  Badkamerdata en centraleJSON/options exact behouden, geen restgroepapparaat.
  CLI-tijdslimieten zijn opgevangen met verse uitlezingen; geen herinstallatie
  of dubbele herstart. Bewijs in TESTKANDIDAAT en out/ha-installation-heading-20261022.
- Volledige productacceptatie, controller-/actuatorproeven en firmwarepoort
  blijven afzonderlijk open; deze wijziging activeert geen fysieke uitvoer.

## Vervolg doorwerkmandaat — grafische weekplanner en actuele M2-voorcontrole

- Mark vraagt het plan door te voeren zonder routinematige afstempauzes.
  F3/R18/R29 uitgevoerd: grafische HA-weekkaart met temperatuur/tijd per blok,
  bewerken/kopiëren/verwijderen en conceptopslag boven dezelfde kamersubentry.
  Native beheerdersrechten, overlap-/grenzen-/bron-/eigenaarchecks, finale
  awaitfence en volledige-entrytoken tegen stale editors. Geen nieuwe scheduler.
- Native productherlaad behoudt uitsluitend het bestaande dashboardobject;
  runtime/transport blijven normaal unloaden. Foutopruiming en bescherming van
  een open concept in echte HA-browserproeven geverifieerd.
- Bron1340 nativegevallen PASS,2 optionele brokergevallen SKIP;34releasegevallen
  PASS. Echte gepinde frontend desktop/mobiel plus toetsenbord-/foutproeven PASS.
  Dev5pakket68exacte bronbestanden geïnstalleerd na gerichte back-up, geldige
  nativeconfigcheck en één herstart. Verse nacontrole16:58CEST: gezondeCore,
  dev5geladen, volledige projectconfiguratie en2devices36entities exact behouden,
  weekkaart/API/module bewezen; tien andere dashboardbestanden ongewijzigd.
  Livegeen weekopslag of apparaatcommando. Actuele details in TESTKANDIDAAT en
  out/ha-week-planner-20261022.
- De strikte omgevingscontrole behoudt één oorspronkelijke FAIL: de bestaande
  historiereparatie is nu genegeerd, maar haar status ontbrak in de dev5nulmeting.
  Moment/oorzaak/actor zijn niet vastgesteld; geen reparatieactie in het journal,
  metricshandlers bytegelijk aan dev4. Functionele PASS afzonderlijk vastgelegd;
  geen claim van volledig reparatiestatusbehoud en geen nieuwe reparatieactie.
  Volgende installatie neemt reparaties expliciet op in de nulmeting.
- Specialist las16:25CEST de echte Aqara-temperatuur20°C en TuyaTV02-identiteit
  uit. Geen apparaatcommando. SOURCE/runtime/actuatie blijven uit; exacte
  firmware, producer-/actuatorkwalificatie en HA→E32→ACK blijven open. Geen
  ontbrekende sensor claimen en geen firmware-/fysieke vrijgave afleiden.
- Canonical WORKBOARD blijft bij zijn eigenaar; neem alleen aantoonbare
  deeluitkomsten over. Overige31eisen, M2 en SDKdistributiepoort blijven open.

### Werkelijk bordadres en apparaatgerichte vervolgstap

- Mark geeft `http://192.168.1.206/` op. Specialistcontrole17:06CEST: inlogpagina
  bereikbaar, status401. Zonder ingelogde sessie blijven firmware/build, owner,
  profiel en ACK onbekend; geen updatebehoefte afgeleid uit die HTTP-status.
  Mark autoriseert daarna het regelen van beheerstoegang via de gewone authroute.
- De bestaande eindige sensorproef is gepind op WSDCGQ11LM/temperature; de nu
  gekozen RTCGQ11LM/device_temperature is een ander bronpad. Geen automatische
  kwalificatie of afwijzing van de gekoppelde testbron. Voor de TV02 moeten
  lokale autoagenda, doelbereik/stap, echo en fysieke reactie afzonderlijk worden
  bewezen. Concrete volgorde en actuele uitleesfeiten staan in
  [Badkamer: koppeling en proef](BADKAMER-KOPPELING-EN-PROEF-20261022.nl.md).

## F0-bronherkomst — originele SDK-binaries onafhankelijk gekoppeld

- De104 archiefregels (52 pertarget) uit de bestaande linked-SDKinventaris
  zijn bytegelijk viaGitblob aan oorspronkelijke Arduino2.0.17commit5e19e086.
  Alle lokaleSHA256 noggelijk; nativegit hash-object onafhankelijk104/104gelijk,
  originelecommitAPI koppelt de gebruikteGitTree aan de immutablecommit.
- Dit bewijst origineleSDKbinaryidentiteit, geen exacte dirty componentsource/
  build-/notice-/toolchainrelinkclosure of nieuwefirmwareimageacceptatie. Beide
  releaseclosurevelden blijvenBLOCKED; geen flash of distributieomweg.
- Bewijs: docs/third-party/sdk-upstream-binary-match.json en
  out/sdk-upstream-comparison-20261022/ROOT-REVIEW.json. Canonicalbord behoudt
  zijn eigenaar; uitsluitend dit begrensde nieuwe bewijs overnemen.

## Aanscherping Mark — wizard alleen voor toevoegen, daarna één grafisch scherm

- Nieuwe ruimte behoudt de wizard; bestaande kamer krijgt één instellingenformulier
  en de normale complete grafische editor. Naam, verwarmingstype, sensor, kranen,
  basisdoel en inline weekplanner horen in één UI met één gezamenlijke opslag.
  PLAN en UX-ontwerp daarop aangepast; geen nieuw apart configuratiepad als doel.
- Dev6-bron gebruikt dezelfde native configuratie-eigenaar en gedeelde radiator-
  validator. Complete kamer/week/graphvervanging in één transactie, geen gedeeltelijk
  apparaat-/programmaresultaat. Auth, eigenaar-/registry-/laatste-awaitchecks,
  sourceconflicten, grenzen en stale-editorbescherming blijven bestaan.
- Grafisch tekenen/verplaatsen/verlengen en inline tijden/temperatuur, kopiëren,
  toevoegen/verwijderen, keuzelijst voor korte blokken en mobiel/toetsenbord.
  Geavanceerd gesloten, hulp bij instellingen, geen onterecht ondersteunde vloer-
  of uitgebreide profielen en geen activering van apparaten of SOURCE.
- 1358 native PASS,2 optionele broker SKIP,34 release-audit PASS; werkelijke
  gepinde HA-browser desktop/mobiel en extra fout-/24:00-/toetsenbordproeven PASS.
  Dev6ZIP69bronbestanden bevroren. Live nulmeting/back-up17:47CEST PASS68oudebron,
  dezelfde1entry2devices36entities en expliciete reparatiestatus. Bronwissel- en
  foutrollbackproef PASS. Na eerdere provider-/opstart- en transportproblemen
  is de live update hervat met verse statuscontrole vóór installatie. Dev6 is
  nu live bevestigd: alle69 bronhashes exact, nativeconfigcheck PASS, één Core-
  herstart en gezond/dev6loaded. Onafhankelijke nacontrole19:07CEST PASS:
  volledigeconfig/registries/reparaties behouden, tienandere dashboardfiles
  ongewijzigd,79andere entryIDs behouden, nieuweeditor supported/editable,
  dashboardviews en publiekeJS HTTP200/hash exact. Geen kamer/weekSAVE of
  apparaatcommando's. Alleen mijn oorspronkelijke dashboardtelfilter is in de
  verifier gecorrigeerd; origineel bewijs behouden. Heleplan/M2/fysiek blijft open.
  Bewijs/rollback in out/ha-room-editor-20261022 en TESTKANDIDAAT.

## Laatste keuze Mark — ingebouwde weekplanner als normale route

De Schedule-helperkeuze vervalt uit de drie normale kamerschermen. Eigen
weekblokken en apparaten blijven één concept met één opslag. Bestaande externe
bindings blijven beschermd en worden niet stilzwijgend geconverteerd. Een
afzonderlijke room-editorcomponent voorkomt de eerder gereproduceerde botsing
met een reeds geladen oude weekplanner. Dev7-bron/native/browsertests PASS;
actuele live-status en rollback staan in de testkandidaat en
`out/ha-single-program-20261022`. Het hele plan en de fysieke proeven blijven open.

## F3/M2 hervat — broncontrole kraandoelen en expliciet onderhoudswachten

- De volgende kritieke stap blijft de actuele E32-identiteit/contracten en verse
  HA-bindingen uitlezen, gevolgd door HA→E32→ACK en de afzonderlijke bron-/kraanproef.
  Mark bevestigde dat het eenmalige E32-invoerbestand klaarstaat; toestemming blijft
  geldig. Nog geen credentialbestand gelezen of login geprobeerd: beide officiële
  beheerroutes stopten vóór provideruitvoering. Mark bevestigde vervolgens dat
  OpenClaw-onderhoud bewust nog loopt. Geen onderhouds-/auth-/servicereparatie.
- Onafhankelijke bronstap uitgevoerd binnen F3/M2: dev8 deelt de bestaande
  adapterconversie met een leescontrole van opgeslagen kamergrenzen en programma-
  doelen tegenover HA-kraangrenzen/stap. Onbekende metadata en externe programma's
  blijven expliciet onbekend. Geen automatische instellingaanpassing, actuator-
  bevoegdheid of fysieke compatibiliteitsclaim. UI/weekplanner ongewijzigd.
- Bron en onveranderlijke dev8 ZIP gecontroleerd: 1380 native PASS/2 SKIP,
  release34 PASS/6 subtests, 69 bronhashes en 73 pakketchecksums PASS; dev7 ZIP gelijk.
  **Dev8 niet geïnstalleerd; live laatst bevestigd dev7.** Zie testkandidaat en
  `out/plan-resume-m2-20261022` voor exacte identiteit en receipts.
- Geen nieuwe live-sensoruitlezing in deze stap: gekozen motion-temperatuurbron
  blijft de bekende koppeling, representativiteit/versheid apart te bewijzen.
- Na onderhoud eerst bestaande sessie/receipts controleren en de voorbereide
  specialistopdracht hervatten; niet opnieuw vragen of de E32-invoer klaarstaat.
  Daarna verse status/contractvergelijking, dev8-installatie met bestaande checks
  en de M2-ketenproef. Geen nieuw F9/F10/P2-werk of firmwareflash vooruitlopen.
  Hele plan/M2 blijven open; canoniek WORKBOARD en canonical checkout ongemoeid.

## E32 rechtstreeks gecontroleerd — 22 oktober, 22:33 CEST

Mark gaf vervolgens de normale lokale inloggegevens. Daarmee is **rechtstreeks
op de E32 ingelogd**, zonder HA-beheer of onderbreking van OpenClaw-onderhoud.
Dit nieuwe bewijs vervangt de eerdere conclusie dat de E32-uitlezing op de
beheerroute moest wachten. Het beschermde eenmalige HA-invoerbestand bleef
ongemoeid; geen credential- of sessiemateriaal opgeslagen.

- Eén login HTTP200, sessie bevestigd; `/status` en `/status/version` HTTP200.
- Gemelde firmware **v0.1.0-e32v2-alpha.6**, bronreferentie
  `b6b57df18afdfd916b9d32465ac699a670400614`, ELF-identiteit
  `ddc0a9c07931dbdaa96741244c487b19f4bb6334ab41c60e89cde939c948aff8`.
- Actuele **controlMode legacy**, nul lokale kamers; geen modern `control`-
  statusdeel in de respons. Dit zegt niets over de bestaande HA-kamer Badkamer.
- Herhaalde firmware- en statusuitlezing bevestigt dezelfde identiteit/modus.
  Daarna uitgelogd; nieuwe `/status` krijgt weer HTTP401. Geen configuratie,
  SOURCE, firmware, apparaatdoel of ketelaansturing gewijzigd.

De gemelde bronreferentie bevat niet het latere `nativeSourceCurrent`-pad dat
in de huidige ontwikkelbron aanwezig is. Dat is een bronvergelijking, geen bewijs
dat de draaiende image exact die commit bevat. **Het huidige native SOURCE-/
weekplancontract op het apparaat is nog niet bewezen.** Niet zonder verdere
controle omschakelen of een nieuwere firmware aannemen. De SDK-releasepoort
voor nieuwe firmware blijft open. HA-dev8 blijft bron/pakket, live laatst dev7.

Bewijs: `out/plan-resume-m2-20261022/E32-DIRECT-READ.json` en
`E32-DIRECT-REVIEW.json`. Volgende stap: na onderhoud verse HA-bindingen/broker-
identiteit via de specialist, exacte contractvergelijking en dan de ondersteunde
configuratie-/ACK-proef. Geen nieuwe ontbrekende/defecte-sensorclaim uit deze stap.

## Kraancontrole in het complete kamerscherm — HA 0.4.0.dev9

**Nieuwste bron en pakket: dev9. Live laatst bevestigd: dev7.** Dev9 bevat de
dev8-controle en toont die nu direct naast de gekoppelde kranen, in hetzelfde
scherm als apparaten, basistemperatuur en weekplanner. Er is geen nieuwe wizard,
programmabronkeuze of extra opslagroute toegevoegd.

- Per kraan de vriendelijke naam, het gemelde temperatuurbereik en de stapgrootte.
  Bij te ruime kamergrenzen staat waar je ze onder Geavanceerd kunt aanpassen.
  Uitklapbare details noemen de basistemperatuur of de dag/tijden van ieder
  weekblok dat afrondt of buiten het kraanbereik valt. Nederlands en Engels;
  °C en °F behouden hun gemelde eenheid.
- Bij wijzigingen aan kranen, grenzen, basistemperatuur of weekblokken verdwijnt
  de oude uitslag. Het scherm vraagt om opslaan voor een nieuwe controle; het
  resultaat van de gezamenlijke opslag wordt direct opnieuw weergegeven.
  Een onafgemaakt/ongeldig blok krijgt evenmin een oude positieve beoordeling.
  Alleen hernoemen laat de bestaande temperatuurcontrole geldig.
- Ontbrekende/onbruikbare eigenschappen en bestaande externe programma's blijven
  expliciet onbekend. Geen automatische doelcorrectie, apparaatcommando of claim
  dat een klep fysiek werkt. De bestaande backendtransactie/actuatorconversie
  zijn ongewijzigd ten opzichte van dev8. Annuleren en opslagconflicten behouden
  de bestaande bescherming van gegevens en concepten.
- Het beheerde dashboard kiest een versiegebonden component en module-URL, zodat
  een al geregistreerde oude dev7-editor de nieuwe editor niet kan overnemen.
  Compatibiliteitsaliassen voor handmatig gemaakte oude kaarten blijven bestaan.
  Naam heeft nu ook uitleg over het behoud van koppelingen en programma.

Bewijs: **1.380 native HA-tests PASS, 2 optionele brokerproeven SKIP**;
34 release-auditgevallen en 6 subtests PASS. **12 echte Chromium-gevallen PASS**:
8 desktop/mobielregressies, vers en na laden van dev5/dev6/dev7; 4 Nederlands/Engels
op desktop/mobiel met doelafwijkingen, onbekend/externe programma's, °F, onveilige
labeltekst, concept-/conflictbehoud, toetsenbordblok en gezamenlijke opslag.
De browser gebruikt een expliciet synthetisch admin-WS-model; native HA-tests
controleren de echte transacties afzonderlijk. Geen nieuwe live-uitlezing.
Een uitgebreide browserproef miste aanvankelijk het accepteren van de bestaande
annuleerbevestiging bij herladen. Chromium weigerde daardoor terecht het vervangen
van het concept; alleen de testbediening is gecorrigeerd, originele log bewaard.

Onveranderlijk pakket `OpenThermostat-HA-0.4.0.dev9.zip`, 426.542 bytes,
SHA256 `71387a0eda2174f35087dc8904eb52e15a14bf0e94bcac15a368809f7ba0341a`.
Bronidentiteit `sha256:2f24e9192079bb5b121c4d404c6e70aeb6328b3722bc471ad44f7d26d0dbee54`.
Onafhankelijke vergelijking: 69 bronhashes en 73 pakketchecksums PASS;
4 bronbestanden gewijzigd en 65 gelijk aan dev8. Dev7/dev8 ZIP ongewijzigd.
Bewijs/screenshots in `out/ha-room-feedback-20261022`, inclusief `TASKFLOW.json`,
`NATIVE-ALL.xml`, `RELEASE-AUDIT.log`, `BROWSER.json`, `BROWSER-FEEDBACK.json`,
`DOWNLOAD.json` en `ROOT-REVIEW.json`. `git diff --check` PASS.

**Niet live geïnstalleerd.** In deze stap geen HA- of E32-beheer, herstart, flash,
bronselectie of kraan-/ketelcommando. Na het onderhoud dev9 via de bestaande
private back-up/configcheck/herstart/nacontrole installeren; dev8 hoeft niet eerst.
Daarna verse HA-bindingen/broker vergelijken met de reeds rechtstreeks uitgelezen
E32 en het exacte ondersteunde contract vaststellen. Hele plan en M2 blijven open.

## Apparaatkeuze en bewuste vervanging — HA 0.4.0.dev10

**Dev10 is geplaatst en gezond geladen.** Configuratiecheck geldig, één native
Core-herstart met verse start **23:10:21 CEST**, entry loaded/geen fout. De native
nacontrole bevestigt alle69 bronhashes en behoud van configuratie/registries/
overigedashboards. Resterende module-/room-/dashboarduitlezing loopt nog;
daarvoor geen tweede bronwissel of herstart. Dev10 bevat de voorgaande verbeteringen
en maakt de apparaatkeuze herkenbaar bij uitval of verwijdering.

- Sensoren/kranen behouden een herkenbare selectie bij onbekend, onbeschikbaar,
  ontbrekende status, uitgeschakeld of ontbrekende opgeslagen koppeling.
  Een onbruikbare temperatuurwaarde wordt apart benoemd. De sensorstatus geldt
  bij laden en bewijst geen acquisitietijd of representatieve kamermeting.
- Hernoemen volgt de vaste registry-identiteit. Een ander apparaat dat later
  hetzelfde entity-ID krijgt wordt niet stilzwijgend overgenomen. Een ontbrekende
  selectie blijft staan totdat de gebruiker haar bewust vervangt/verwijdert;
  interne markeringen kunnen niet als binding worden opgeslagen.
- De editor stuurt geselecteerde registry-identiteiten mee. De native gezamenlijke
  kamer-/graph-/weektransactie controleert die vóór en na de laatste compilatie-
  await. Ook oude clients mogen een ongewijzigd ID niet ongemerkt ombinden.
  Bewuste vervanging valideert de volledige nieuwe kamer/graph; een verwijderde
  oude eigen referentie blokkeert die vervanging niet meer. Andere kamers,
  dubbele uitvoereigenaars, input/outputlussen en runtimeguards blijven gecontroleerd.
- Opslagfouten behouden het concept. Geen automatische apparaat-, doel- of
  programmawijzigingen en geen SOURCE-/actuatorvrijgave. Geen nieuwe wizard of
  alternatieve programmabron. Versiegebonden v10-editor/module voor de beheerde
  dashboardroute; oude handmatige kaartaliassen blijven behouden.

**Bewijs:** 1.401 native HA-tests PASS, 2 optionele brokerproeven SKIP, waaronder
21 nieuwe registry-/identiteitsgevallen. 34 release-auditgevallen en 6 subtests
PASS. 18 echte Chromium-gevallen PASS: desktop/mobiel, NL/EN, oude geladen modules
inclusief dev9, concrete statusmeldingen, bewuste vervanging met apparaatidentiteit
én weekblok in één save, behoud concept bij fout. Browser gebruikt een expliciet
synthetisch admin-WS-model; echte native registry/transacties apart getest.
De eerste vier nieuwe native fouten toonden onduidelijke markeringfouten en
validatie tegen verwijderde oude eigen referenties; bron hersteld en volledige
suite groen. Eén browserassertie las ten onrechte hosttekst buiten shadow DOM;
alleen die testwaarneming is gecorrigeerd. Originele logs behouden.

Onveranderlijk pakket `OpenThermostat-HA-0.4.0.dev10.zip`, 428.495 bytes;
SHA256 `34e42f39f96c2a41a56dbb9f51abf983a666e24c9b8cccc01a7e051c52e00694`.
Bronidentiteit `sha256:ece365dcb6ecc8703fa519a7783445820430d2340ca51d267e8a68d81b3f13f9`.
Onafhankelijke vergelijking: 69 bronhashes/73 pakketchecksums PASS; 7 bronbestanden
gewijzigd en 62 gelijk aan dev9. Dev7/dev9 ZIP en SDK-releasebeleid ongewijzigd.
Bewijs/screenshots: `out/ha-device-selection-20261022`, met native-/release-/
browserlogs, `DOWNLOAD.json`, `ROOT-REVIEW.json` en `TASKFLOW.json`.

### Verse HA-uitlezing en installatiepad

De Gateway draait weer en de HA-specialist heeft op **22 oktober 23:00:54 CEST**
via de native route gelezen: integratie **dev7 geladen**, geen entryfout;
Badkamer ondersteund/bewerkbaar, sensor `sensor.motion_badkamer_device_temperature`
beschikbaar met **21 °C**, kraan `climate.thermostaat_badkamer` beschikbaar in heat,
huidig18,6/doel17, min5/max30/stap0,5, preset auto. Runtime/actuatie uit,
transport-ready false. Opgeslagen kamergrenzen5–35, basis21 en zeven lokale blokken
07:00–23:30/doel21 gemeld. Geen wijzigingen. De HA-timestamps zijn geen gemeten
acquisitietijden; geen nieuwe sensorontbreekt-/defectclaim. Exact brokerendpoint,
projectprefix en subentrymapping zijn in deze beperkte uitlezing niet bevestigd.
De E32-identiteit/modus is eerder afzonderlijk rechtstreeks uitgelezen; niet als
nieuwe apparaatmeting uit de HA-registry presenteren.

**Dev10-installatie is in uitvoering; live nacontrole nog te verzamelen.**
De eerste Fileeditor-aanroep gebruikte onterecht poort3218; de addon declareert
8099 en was al gestart. De bestaande native Ingress werkt HTTP200. Geen service-,
auth- of configreparatie nodig. De verse private back-up is nu PASS:69 dev7-
bronhashes exact, bron/storage vóór/na bytegelijk,1entry/2devices/36entities,
79overige integraties behouden. Gerichte staging/swap en geïnjecteerde rename-
fout zijn lokaal getest. De specialist voert nu bronwissel/configcheck/één
native herstart en onafhankelijke bestands-/room-/dashboardnacontrole uit.
Geen voltooiing afleiden uit alleen de verstuurde opdracht. Dev8/dev9 hoeven niet eerst.
Daarna actuele HA/brokeridentiteit met het exacte E32 SOURCE-/plancontract
vergelijken en de M2-ketenproef vervolgen. Heel plan/M2/fysieke proeven blijven open.

## Rechtstreekse E32-contractcontrole — 22 oktober 23:09 CEST

De geselecteerde E32-configuratie is nu daadwerkelijk gelezen met de normale
login: firmware meldt nog alpha.6, controlMode legacy en nul lokale kamers.
`/config/device` HTTP200 met MQTTobject: enabled true, modern_shadow false,
broker192.168.1.130:1883, base ib-therm, adapter_id leeg. De huidige native-source-
readbackvelden worden niet aangeboden: `native_source_device_id`,
`native_source_live_apply` en `native_shadow_source` ontbreken. De oude gemelde
bronreferentie bevat die actuele code evenmin. Dit is geen attestatie dat de
draaiende binary exact die commit bevat; het nieuwe contract mag niet worden
aangenomen op basis van alleen de versienaam of een HA-save.

Bronnen: `out/ha-device-selection-20261022/E32-CONTRACT-READ.json` en de
onafhankelijke `E32-CONTRACT-REVIEW.json`. Herhaalde versie-/modusuitlezing gelijk;
uitgelogd en `/status`401 bevestigd. Geen settingsPOST, MQTTpublicatie, SOURCE-
selectie, firmwareflash of apparaatcommando. Geen wachtwoord/sessie opgeslagen;
het beschermde HA-invoerbestand bleef ongelezen.

Na de HA-update: de geselecteerde HA broker-/prefix-/adapteridentiteit vergelijken
met deze deviceconfig en het werkelijk ondersteunde firmwarecontract vaststellen.
Niet blind de oude modus activeren of een firmware-/SDKpoort omzeilen.

## Actueel: HA 0.4.0.dev11 live en gecontroleerd

**Dev11 is gezond geladen.** Het kamerscherm bevat nu herkenbare apparaatstatus,
behoud van ontbrekende keuzes en bewuste vervanging met controle op vaste
apparaatidentiteit. Hernoemen blijft dezelfde sensor/kraan volgen; hergebruik
van een oud entity-ID kan geen stilzwijgende vervanging worden. Apparaten,
basistemperatuur en weekplanner blijven samen in één editor en één opslag.

De live dev10-nacontrole vond een fout in onze eigenschapscontrole: de kraan
levert `supported_features=401` als officiële HA `ClimateEntityFeature` IntFlag.
De exacte-intguard wees die af, ondanks geldige grenzen5–30 en stap0,5. Een
gerichte native templateuitlezing en twee nieuwe tests met echte native `State`
bevestigen dit. Dev11 accepteert uitsluitend een gewone int of die officiële
HA-klasse. Geen bool-/float-/stringcoercie; temperatuurgrenzen, afronding en
fysieke bevoegdheid blijven ongewijzigd. Alleen parser en manifest verschillen
van dev10; de overige67 bronbestanden, inclusief de UI, zijn bytegelijk.

**Bewijs:** 1.403 native HA-tests PASS,2 optionele brokerproeven SKIP;
34 release-auditgevallen en6 subtests PASS. De18 daadwerkelijk uitgevoerde dev10-
browsergevallen blijven geldig via dezelfde UI-bytes; niet als opnieuw
uitgevoerde dev11-proeven tellen. Onveranderlijk pakket
`OpenThermostat-HA-0.4.0.dev11.zip`,428.464 bytes;
SHA256 `462c4da2b3c21966fa2fa6c17ea3226b31a30381e1adad6a523ca634b5aceb1c`.
Bronidentiteit `sha256:e1882bbb21cdba0b4adc72d413abe43aa14d5963d855c18574f5124c2af73eb8`.
69 bronhashes/73 pakketchecksums onafhankelijk gecontroleerd; dev10 ZIP behouden.

De native installatie gebruikte een nieuwe private back-up van de69 dev10-
bestanden plus actuele data/options/subentries/registries/reparaties/dashboards.
Exacte staging/swap en herstel bij een geïnjecteerde laatste renamefout zijn
lokaal getest. Alleen de twee gewijzigde bestanden zijn overgedragen; alle69
nieuwe hashes zijn tegen het onveranderlijke pakket gecontroleerd. Configuratie-
check geldig. Eén bevestigde Core-herstart voor dev11, verse start
**22 oktober23:26:08 CEST**; samen met de eerdere dev10-installatie twee herstarts.
Geen herstart herhaald wegens de eerdere uitvoertijdlimiet.

Alle11 native bron-/data-/registrychecks PASS: dezelfde entry,2 apparaten en36
entiteiten, volledige instellingen en programma's behouden,10 overige dashboard-
bestanden en79 overige integraties behouden. De werkelijke69 live bronhashes zijn
geëxporteerd en onafhankelijk gelijk aan ZIP11 bevonden. Rootvergelijking:
**18 controles PASS**, inclusief configuratiehashes tegen de private nulmeting,
verse health/versie en werkelijke room-/moduleresultaten. De publieke ongewijzigde
v10-module levert HTTP200,40.154 bytes en SHA256
`373110835372cf236fe1adfb32a024a59342bdbee208aae7b3b64cfcc26b8816`.
De beheerde kamerview gebruikt terecht dezelfde v10-component; dit is geen
oude editor die de update heeft overgenomen. Geen nieuw live browserrenderbewijs
geclaimd bovenop de bronbrowserproeven en native dashboarduitlezing.

### Laatste badkamerstand

De eerste dev11-uitlezing toonde correct de toen opgeslagen kamergrens35 tegenover
het kraanmaximum30. Bij een daaropvolgende verse controle stond de kamergrens
**al op30°C**. Daarom is in die controle **geen room/save, reload of herstart**
uitgevoerd. Twee uitlezingen bevestigen grenzen5–30, basis21 en dezelfde zeven
weekblokken07:00–23:30/doel21 met dezelfde sensor/kraan. Wie de grens tussen beide
controlemomenten wijzigde is niet vastgesteld; dit wordt niet aan onze software-
update of een niet-uitgevoerde opslag toegeschreven.

De actuele opgeslagen-doelenreview is **compatible**, met capability°C/5/30/0,5,
lege actuatorissues en `authorizes_actuation=false`.25 native nacontroles en11
onafhankelijke rootcontroles PASS voor die laatste uitlezing. Sensor en kraan zijn
beschikbaar in HA; dat bewijst geen fysieke meettijd of geschiktheid als kamerbron.
Dev11 loaded/geen entryfout, runtime/transport/actuatie uit. Koppelingen en programma
zijn behouden; geen TRV-doel/preset, MQTTpublicatie of E32-instelling aangestuurd.

Bewijs: `out/ha-native-capabilities-20261022`, waaronder `LIVE-DIAG.json`,
`NATIVE-ALL.xml`, `ROOT-REVIEW.json`, `DEPLOYMENT-RESULT.json`,
`LIVE-ROOT-REVIEW.json`, `ROOM-RANGE-RESULT.json` en `ROOM-RANGE-ROOT-REVIEW.json`.
Terugvalbron: `/homeassistant/.openthermostat-backups/20261022-native-capabilities-dev11-preflight/live-before-dev11`.
Private snapshots blijven0700/0600. `SOURCE.json installed=false` beschrijft het
pakket bij bouw; bovenstaande native receipts zijn leidend voor de live status.

**Volgende stap:** E32-firmware/regelcontract passend maken voor de M2-kamerketen.
De opgeslagen brokerroute en prefix zijn vergeleken: HA gebruikt core-mosquitto
met hostpoort1883 op192.168.1.130, E32 meldt datzelfde hostadres/poort en prefix
ib-therm. Dit bewijst configuratieconsistentie, geen TCP-/auth-/ACK-proef. Op E32
staan de nieuwe modus uit en adapter-ID leeg; actuele native SOURCE-readbackvelden
ontbreken, terwijl HA al een vaste adapter-ID heeft. Geen oude modus blind
activeren, firmwarepoort omzeilen of fysieke werking afleiden uit de GUI.
Het hele plan, het native E32-contract en de fysieke sensor-/kraanproeven blijven
open. Geen nieuw gebruikersantwoord nodig om de bekende vervolgstappen te plannen.

## Doorwerkopdracht nacht — volledige functies en E32 als eerstvolgende bronstap

Mark mist externe kamerdoelbediening en raamcontact in het nieuwe kamerscherm.
Broncontrole bevestigt de beperking: de eenvoudige editor sluit uitgebreide
bindings uit; het moderne kamer-/compilerpad ondersteunt deze combinatie nog
niet volledig. R02 en R21 blijven expliciete eisen. Niet opnieuw verwarren met
de al gekozen losse temperatuursensor of de bewust weggelaten Schedule-helper.
Ook gemengde getoetste TRV-profielen blijven vereist. PLAN is op deze punten
aangescherpt; [UITVOERING-NACHT](UITVOERING-NACHT-20261022.nl.md) ordent alle31eisen,
afhankelijkheden, bewijsacties en vervolg zonder telkens om toestemming te vragen.

Opdracht staat als actief Codex-doel. Eerste E32-bronstap uitgevoerd: via bestaande
beveiligde status is gecompileerde contractondersteuning uitleesbaar, afzonderlijk
van geselecteerde/actieve regeling. Dashboarduitleg standaard dicht.13 C++-,
110 HA/C++-,42 Node-,34 audittests en echte Chromium desktop/mobiel PASS; normale
app/FS-build plus onafhankelijke board-/bron-/imagecontrole PASS. Alle69HA-dev11-
bronbestanden/ZIP onveranderd. Geen livebeheer, SOURCE-selectie of firmwareflash.

SDK-bronspoor concreter gemaakt: origineelversiebestand exact aan immutable tree
gekoppeld,8gedeclareerde revisies opgelost,7componentregels bevestigd door de
oorspronkelijke producent-PR9339. Kandidaat-I2Spatch op gedeclareerde IDFbron geeft
2exact passende geïnstalleerde headers, onafhankelijk teruggetoetst. Dit bewijst
geen complete corresponding-source-/noticeclosure of exacte builderrevisie.
Volgende actie is die resterende component-/submodule-/buildkoppeling, daarna de
uitrolbare E32-kandidaat/M2. Bewijs `out/night-run-20261022`; heelplan open.


## Uitvoering 23 oktober: bronbewijs zonder producteisen te schrappen

De [nieuwe broncontrole](SDK-BRONBEWIJS-20261023.nl.md) levert exacte SDK-,
runtime- en startup-objectreproductie plus bron/notices/binaire binding van de
bestaande CA-bundel. Dit wijzigt geen producteis, fasering of fysieke acceptatie.
De schone E32-kandidaat is inmiddels gebouwd en onafhankelijk gecontroleerd;
exacte en gewijzigde-libraryherlinkproeven slagen. Bron-/herlinkreviewmateriaal
is opgebouwd en op alle 512 checksums getoetst. Volgend werk: targetgebonden
notice-/leveringsreview, gecontroleerd firmwarepakket en M2.
Externe kamerdoelbron, raamcontact en meerdere getoetste TRV-profielen blijven
vereist. HA dev11 blijft ongewijzigd; geen firmware geplaatst in deze bronstap.
