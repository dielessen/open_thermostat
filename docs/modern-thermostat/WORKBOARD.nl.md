# OpenThermostat — actueel werkbord en releasechecklist

**Bijgewerkt: 24 oktober 2026.** Dit is de enige actuele afvinklijst. Het
[masterplan](PLAN.nl.md) bewaart alle 31 eisen en oorspronkelijke acceptatievoorwaarden.
Oude uitvoeringsnotities zijn gearchiveerd; hun oude woorden “open” en “niet
geïnstalleerd” bepalen de huidige stand niet meer.

## 1. Waar staan we?

| Onderdeel | Vastgestelde stand |
| --- | --- |
| Geïnstalleerde firmware | E32 `v0.1.0-e32v2-alpha.26`, na één bestaande app-only webupload met verse back-up; bron, ELF/web, bevestigde boot en live ESP-diagnose gecontroleerd |
| Geïnstalleerde HA-integratie | `0.4.0.dev34`, via bestaande HA-agent met verse back-up/nacontrole; 105 registryrecords en alle koppelingen behouden |
| Geleverde bron | E32 `e9ae314f2519ac4208f89d183b4a73a96131d8a4`; HA `0aeff4dbaed9f187228e5621545b428648edfce5`, alle 83 live componentbestanden gelijk aan het HA-pakket |
| Softwarebasis | `out/beta-boiler-20261023`, `work/beta-boiler-20261023`; alpha26/dev34 geleverd met herstel ESP-diagnose en EN/NL-uitleg; alle eerdere bron behouden. Dev34 is gepubliceerd en geïnstalleerd met exacte live bestandscontrole |
| Doel volgende release | Eerste samenhangende bèta: aansluiten, ketelgegevens zien en begrensde start/stop kunnen beproeven |
| Nog geen bèta-vrijgave | Actieve proef-/zendketen en concrete fysieke voorwaarden ontbreken nog |
| Huidige fysieke grens | Geen bewezen echte kraan-/ketelregeling; E32-TX en actuatoruitgangen geblokkeerd |

**Broncontrole:** de release-inventaris bewaart alle 23 voorbereide onderdelen
met 228 gecontroleerde bronverwijzingen. Het gepubliceerde bron-/licentie-/
herlinkpakket is onafhankelijk vergeleken met de exacte Git-tag en bijbehorende
ELF/webidentiteit. Bij de gezamenlijke alpha24/dev30-bundel zijn alle 82 HA-componentbestanden ook
met het E32-pakket vergeleken. De latere HA-updates dev31/dev32/dev33/dev34 zijn afzonderlijk met
hun eigen publieke pakket, Git-bron en alle live hashes gecontroleerd. Historische checkpoints en afgewezen kandidaten blijven bewaard;
geen bestaande tag of download is vervangen.

**Afvinken:** `[x]` geldt alleen voor de genoemde software-/leveringsuitkomst.
Een meegeleverd model of geslaagde simulatie bewijst geen aangesloten functie,
ketelreactie of productacceptatie. Alle oorspronkelijke fasen blijven open waar
verplichte fysieke of langere-termijnproeven ontbreken.

## 2. Af, geleverd en dus ook in de volgende release behouden

- [x] Eigen bron-/SDK-/licentie-/herlinkbasis en onveranderlijke pakketten.
- [x] Weblogin, sessie/CSRF, netwerk/setup en bestaande update/herstelroutes.
- [x] HTTPS-updater met TLS-geheugenreparatie, begrensde catalogus en automatische release-indeling.
- [x] About, uitloggen rechtsboven en herstart onder Settings.
- [x] HA-kamer-/apparaatinrichting, metadata/identiteiten en helpervrije weekplanner.
- [x] Korte plannerblokken op touch; programmawijziging met echte E32-readback/ACK.
- [x] Actieve sensor/TRV/grenswijziging via normale gecontroleerde save/apply/retry.
- [x] HA-koude-startreparatie; drie echte verse sessies zonder refresh/errorcard.
- [x] Echte kamernamen op het E32-dashboard en expliciete statische webroutes.
- [x] Meetstatus, toelatings-/geheugendiagnose en passieve Classic-decoderbasis.
- [x] Alpha17/dev23 gepubliceerd, geïnstalleerd en onafhankelijk gecontroleerd met behouden instellingen/programmas.
- [x] Gezamenlijke passieve alpha24/dev30-bundel gepubliceerd en normaal geïnstalleerd; 82 HA-bestanden, nieuwe E32-boot, ELF/web/bron en behoud onafhankelijk gecontroleerd.

Bewijs: `out/combined-release-evidence-20261023/FINAL-REVIEW.json` en deelreviews.
De 1694 HA-tests horen bij die historische bron. De gezamenlijke alpha24/dev30-
levering heeft 2003 HA-checks zonder fout/skip en een afzonderlijk geïnstalleerde
bron-/runtimecontrole in `out/combined-alpha24-dev30-20261024/`. HA dev31 voegt
het geteste graph-bronherstel toe met 2011 geslaagde HA-checks en afzonderlijk
installatiebewijs in `out/ha-dev31-native-binding-20261024/`. Seriële stilte na de routereparatie is niet opnieuw fysiek
opgenomen; correcte live HTTP-/assetroutering wel.

## 3. Alles wat voorbereid is, meenemen in de bèta

Elke rij hieronder blijft in de nieuwe bronbasis. “Meenemen” is geen opdracht
om onafgemaakte of ongekwalificeerde mogelijkheden automatisch te activeren.
De machineleesbare [release-inventaris](BETA1-RELEASE-INVENTARIS.json) bevat
228 bronverwijzingen met hashes, status en resterende acceptatie.
De CI controleert deze bronhashes en de dekking van alle eisen en releasechecks
met `scripts/verify_beta_release_inventory.py`. Bij een bewuste bronwijziging
hoort een gereviewde inventarisupdate; een ontbrekend onderdeel faalt de controle.

| ID | Onderdeel | Stand | Nog nodig |
| --- | --- | --- | --- |
| I01 | Eigen project, bron/licenties en reproduceerbaar pakket | Geleverde softwarebasis | Volgende exacte release opnieuw bouwen/verifiëren; geen nieuwe upstream-sync. |
| I02 | Weblogin, sessies, CSRF, setup en herstelroutes | Geleverde softwarebasis | Fysieke AP-/uitval-/herstelmatrix blijft apart. |
| I03 | Automatische HTTPS-update, TLS-geheugen en catalogus | Geleverde basis; blijvende diagnose voorbereid | Alpha26-afwijking blijft open. Eén begrensd checkpoint en EN/NL-webdiagnose gebouwd/getest; nog niet geïnstalleerd, geen blinde updaterherhaling. |
| I04 | Actuele/archief-releases automatisch ordenen | Geleverde softwarebasis | Nieuwe publicatie moet bestaande tags/assets behouden. |
| I05 | About, uitloggen rechts en herstart onder Settings | Geleverde softwarebasis | Behouden; bevestiging/herstartguards opnieuw in eindregressie. |
| I06 | Kamerinrichting, identiteiten en apparaatmetadata | Geleverd inclusief versieprojectie | Gemelde Z2M-/converterversie zichtbaar; ontbrekend blijft onbekend. Metadata kwalificeert geen fysieke sensor of kraan. |
| I07 | Weekplanner, korte aanraakblokken en effectief doel | Geleverde softwarebasis | Echte programma-save/ACK bevestigd; bron-/uitval-/reconnectproef nog open. |
| I08 | Actieve sensor/TRV/grenzen wijzigen, bewaren en opnieuw toepassen | Geleverde softwarebasis | Alleen normale expliciete save; geen live apparaatwissel tijdens installatie bewezen. |
| I09 | HA-kaart registreren na opstart, zonder herhaald refreshen | Geleverde softwarebasis | Drie echte koude HA-sessies bewezen; versiegebonden module behouden. |
| I10 | Kamernamen op E32 en juiste statische webroutes | Geleverde softwarebasis | Badkamer live bevestigd; geen nieuwe seriële opname van de logstilte. |
| I11 | Meetstatus, systeemlog en geheugen-/toelatingsdiagnose | Observer/native identiteit en web-/syslogsoftware geleverd | Oude kwalificatie wordt ingetrokken bij bron-/apparaatwissel; productie-meetprofiel, externe collector en lange resourceproef blijven open. |
| I12 | Passieve Classic-decoder en Classic-proefencoder | Decoder en geblokkeerde encoder geleverd | Vast 0x1A-flow/nulformaat gebouwd; beoordeelde bronadressering, fysieke UART-/stopkwalificatie en ontvangstpariteit blijven open. |
| I13 | Ketencontract, SOURCE, journal, configuratie en readback | Geleverde softwarebasis | Logische provisioning/programma-ACK werkt; verse fysieke meet- en actuatorbewijzen ontbreken. |
| I14 | Kraanadapter profiel C, TV02-moduscontrole en bronbench | Modus/identiteit en oorspronkelijke HA-ontvangst/diagnose geleverd; fysieke route onvolledig | Native identiteit en doelcapaciteit vlak vóór dispatch opnieuw gecontroleerd; TV02 auto/vakantie/uit/onbekend zichtbaar en vóór doelactie geweigerd. Verse kraanecho, exclusief eigenaarschap en fysieke werking blijven open; oude bench op SOURCE geblokkeerd. |
| I15 | Kamerregelaar, seizoensbeleid en hydraulische supervisor | Voorbereide code, functie nog onvolledig | Controller-/supervisorkoppeling en HA-diagnose gebouwd; werkelijke producenten, installatieprofiel en fysieke uitvoerketen niet gekwalificeerd. |
| I16 | Groepswaterdoelen, vloer, menger en centrale graph-config | Voorbereide code, functie nog onvolledig | Pure policies/declaraties en begrensde DATA-paden aanwezig; niet gelijk aan actieve groepen/pomp/menger. |
| I17 | Metrics, grafieken, historiegrens en CSV-export | Voorbereide code, functie nog onvolledig | Niet opnieuw vanaf nul bouwen; echte Classic-tijdlijn, Recorder-retentie/migratie en grafiekacceptatie open. |
| I18 | Comfortprioriteiten, raam/aanwezigheidscontext en HEAT/OFF | Voorbereide code, functie nog onvolledig | Logische/oudere opt-in paden bestaan; native eenvoudige kamereditor/bronkwalificatie niet compleet. |
| I19 | Thermisch model, optimum-start, uitlopen en curveaanpassing | Voorbereide code, functie nog onvolledig | Code/replay/opslag aanwezig en behouden; geen bewezen leerwinst of actieve vrijgave. Geen nieuwe F9-stage vóór M2. |
| I20 | Meldingen, batterij en modelspecifieke tapwaterpresentatie | Voorbereide code, functie nog onvolledig | Niet generiek als werkende onderhouds-/tapwaterregeling presenteren; modelgerichte acceptatie open. |
| I21 | Keteltest-pagina, ontvangstdiagnose en meetrapport | Geleverd en op E32 gecontroleerd | Volledige release-CI PASS; echte E32-pagina en rapportdownload op 1280/390/320 px gecontroleerd. Tijdens de latere README-opname is verse Classic-ontvangst waargenomen; veldvalidatie blijft open. |
| I22 | Begrensde ketelproefpolicy en originele UART-ontvangsttijd | Policy en RX-integratie geleverd; actieve proef nog onvolledig | 80 unieke native gevallen onder ASan/UBSan PASS; beoordeeld profiel/adressering en fysieke TX-/stopkwalificatie open. |
| I23 | Beveiligde controller-/HTTP-/webbediening van de ketelproef | Geleverd met actieve proef geblokkeerd | Poll-executor aangesloten; default start geblokkeerd. Classic-formaat gekoppeld; beoordeeld profiel/adressering en fysieke UART-kwalificatie open. 80 native en eerder 3 control-browserprofielen PASS. |

Er wordt geen voorbereide supervisor, vloer-/mengerpolicy, CSV-/grafiekroute,
comfortcode of leer-/modelcode weggegooid of opnieuw vanaf nul gebouwd. Deze
onderdelen waren deels ten onrechte als geheel “nog te programmeren” aangeduid.
De ontbrekende verbinding met actuele profielen, productiebronnen, uitvoer en
praktijkbewijs blijft wél zichtbaar open. Bestaande F9/F10-code behouden is geen
nieuwe F9/F10-ontwikkelstage; die start pas na M2.

## 4. Alle 31 producteisen — actuele softwarestand en resterend werk

Geen van deze volledige producteisen wordt op basis van alleen aanwezigheid in
de code afgetekend. De oorspronkelijke acceptatie in PLAN §4/§14 blijft gelden.

| Eis | Functie | Al geprogrammeerd/geleverd | Inventaris | Nog af te maken of te bewijzen |
| --- | --- | --- | --- | --- |
| R01 | Kamerdoel en identiteit | Gebouwd en geleverd; programma-save/ACK op echte E32 bewezen | I06–I08,I13 | Verse fysieke meetketen en volledige ruimteproef. |
| R02 | Externe kamerdoelbediening | Bindings/modelbasis aanwezig; moderne kamerketen onvolledig | I18 | Editor + profiel/identiteit + één override per fysieke bediening + echopreventie. |
| R03 | Gemengde temperatuursensoren | Binding, normalisatie en stale-guards aanwezig; productie-meetprofiel ontbreekt | I06,I11,I13,I14 | Modelspecifieke meetrapportproducent, echte acquisitie en uitval; geen diagnostische device_temp als ambientbewijs. |
| R04 | Meerdere TRVs per kamer/merken | Declaraties en selecties bestaan; huidig native radiatorcontract één TRV per kamer | I06,I08,I14,I16 | Ondersteunde modellen en groepsfeedback; native uitbreiding niet als geleverd claimen. |
| R05 | Open/dicht/proportioneel regelen | Bewaakte profiel-C-adapter en pure regelprofielen aanwezig | I14,I15 | Echte kraan zonder ketel; juiste regelmethode, eigen agenda, echo, afronding en uitval. |
| R06 | Vloerkleppen | Graphdeclaraties, klep-/groepsbasis aanwezig | I16 | Actieve profiel-/wire-/uitvoerketen en eigen fysieke vloeracceptatie. |
| R07 | Onafhankelijke zones/ketelvraag | A/B/samen/uit shadow-regellogica aanwezig | I13,I15 | Gekwalificeerde actuatoren, afgiftepad en echte begrensde ketelvraag. |
| R08 | Classic EMS en behoud Plus | Passieve Classic- en Plusbasis geleverd; alle E32-TX geblokkeerd | I12,I21,I23 | Classic-proefcommandopad + elektrische zendmodus/stopbewijs; Plus later eigen fysieke vrijgave. Modelonafhankelijke velddekking uitbreiden; profiel is nooit een leesfilter.  |
| R09 | Weersafhankelijke aanvoer | Curve-/groep-/begrenzingspolicies en centrale draft aanwezig | I15,I16 | Centrale instellingen verbinden met geselecteerde regelaar, actuele buitenbron en keteluitvoer. |
| R10 | Eigen buitenbron | Bronabstractie/binding/draft en validatie aanwezig | I16 | Normale configuratie/apply + bronkwalificatie, leeftijd, bronwisseling/uitval. |
| R11 | Internetweer via HA | HA-bronroute ontworpen; geen volledig gekwalificeerde praktijkketen | I16 | Gratis HA-weerbron, ouderdom/terugval en internetuitval bewijzen. |
| R12 | Zelflerende kamerregeling | Model-, begrenzings-, resource- en replaycode aanwezig | I19 | Verplicht in definitieve versie: per ruimte leren en gevalideerde modellen/regelparameters blijvend bewaren en gecontroleerd herstellen na herstart. Tijdelijke I-correctie blijft veilig resetbaar. Niet actief vrijgegeven; getoetste meetdata, baseline/comfortvoordeel en modelrollback blijven vereist. |
| R13 | Optimum-start | Opwarmmodel en begrensd advies/replay aanwezig | I19 | Aansluiten na M2/stabiele basis; meerdere vergelijkbare echte starts en comfortbewijs. |
| R14 | Uitlopen/curve leren | Coast- en curve-adaptatiecode/opslag/replay aanwezig | I19 | Afzonderlijke toelating en meetbaar comfort-/curvebewijs; geen leerwinstclaim. |
| R15 | Alle relevante keteldata | 69 native velddefinities geleverd op alpha21/dev27; laatste controle 26 beschikbaar, eerdere boot 27 | I12,I17,I21 | Vereiste betrouwbare velden op eigen E32 ontvangen en vergelijken; unsupported/unreliable expliciet. |
| R16 | Brander/modulatiegrafieken | Native ketelkaarten en drie historiekaarten geleverd; gerapporteerd/afgeleid gescheiden | I17,I21 | Echte CV/DHW-tijdlijn, gaten en herkomst; vlam/pompbit niet onafhankelijk betrouwbaar. |
| R17 | Historie/statistics/CSV | Recordergrens, metrics-schema en read-only CSV-code aanwezig | I17 | Werkelijke retentie/omvang, oude deltahistorie/migratie, reset/gaten en mobiele grafiekacceptatie. |
| R18 | Weekprogramma/override | Native weekeditor/UTC-plan/apply geleverd; echte save/ACK bewezen | I07,I13 | Volledige fysieke stale/reconnect/tijd-/overrideketen; huidige 1–2 kamer-/bytebudgetten behouden. |
| R19 | Comfort/eco/away/vakantie/boost | Prioriteits-/expiry-/opt-in comfortcode aanwezig | I18 | Normale huidige producteditor/bronketen en conflicten compleet; geen nieuwe F10-stage vóór M2. |
| R20 | Aanwezigheid/geofencing | Opt-in logische HA-contextbasis aanwezig | I18 | Modelspecifieke contextactualiteit en complete gebruikersroute; P2 blijft later. |
| R21 | Raam-open | Zone-inhibit/prioriteits-/contextcode aanwezig | I18 | Native kamereditor/contract voor huidige SOURCE en stabiele contactactualiteit; later F10. |
| R22 | Vorst/zomer | Seizoens-/prioriteitspolicy en bounded frost-target aanwezig | I15,I18 | Installatiegebonden fysieke bescherming bij uitval; softwaretarget is geen bewezen vorstbeveiliging. |
| R23 | Anti-pendelen/hydrauliek | Supervisor-, timing-, waterbudget- en minimumlastcode aanwezig | I15,I16,I23 | Actieve profiel/readiness/flow/pomp/naloopketen en fysieke kleinste-last/DHW-proeven. |
| R24 | Uitval HA/MQTT/sensor/E32 | Lease/session/boot/stale/owner-guards aanwezig | I11,I13,I15,I23 | Werkelijke uitvalmatrix, E32-powerloss/ketelstop, actuatorfallback en exclusieve overdracht. |
| R25 | Waarom stoken | Redencodes, kamervraag en dashboard geleverd; diagnose uitgebreid | I10,I11,I15,I17,I21,I23 | Echte opdrachtentijdlijn en gecontroleerde vraag/verzending/ketelreactie apart zichtbaar. |
| R26 | Verbruik/kosten/comfort | Metrics/export/schatlabels gedeeltelijk aanwezig | I17 | Echte gas-/warmtemeter en kostenbron/kalibratie; geen verzonnen besparing of fysiek gasvolume. |
| R27 | Meldingen/onderhoud/batterij | Diagnostics/Repairs en batterijbasis aanwezig; systeemlog/syslog voorbereid | I11,I20 | Passende meldingen en echte fout-/batterij-/geen-responsscenario’s; geen automatische ketelreset. |
| R28 | Open/lokaal/veilig/herstelbaar | Eigen bron, auth, HTTPS-updates en behoud/rollback deels live bewezen | I01–I04,I08,I23 | Concrete ACL/HTTP/AP-/koude herstel-/uitvalmatrix; oorspronkelijke backupwaiver blijft geldig. |
| R29 | Modern eenvoudig scherm | HA-kamer/week, koude-startfix, E32-dashboard/About/navigatie geleverd | I05–I11,I21,I23 | Ontbrekende centrale/uitvoerfuncties en complete gebruikersacceptatie; echte latentie/geen ongefundeerde speedup. |
| R30 | Schaalbaar/onderhoudbaar | CI/build/source-/budgetguards en 1–2 native kamers aanwezig | I01,I03,I11,I13 | Acht zones zijn productdoel: maximumconfig/heap/NVS/powerloss/72u nog open. |
| R31 | Optionele tapwaterbediening | Modelspecifieke read-only presentatie/bewaking aanwezig | I20 | Alleen echt ondersteunde writefuncties later apart testen; DHW/legionellabeveiliging behouden. |

## 5. De 11 productfasen

| Fase | Software die er al is | Waarom de gehele fase nog open is |
| --- | --- | --- |
| F0 Eigen basis/installatie | Bron-, build-, licentie-, update- en behoudsbewijs geleverd | Volledig woning-/device-/hydrauliekprofiel, fysieke resource/herstelacceptatie |
| F1 Classic uitlezen | Decoder/capabilities/paritybasis geleverd; nieuwe ontvangstdiagnose getest | Vereiste betrouwbare velden op deze E32/keten passief ontvangen en vergelijken |
| F2 Contract/verticale keten | SOURCE/provisioning/journal/plan/readback; programma-ACK live bewezen | Originele meetactualiteit/producer, fysieke bron→statusketen en uitval/capaciteit |
| F3 HA-product/apparaten | Kamer/week/profielsave, identiteit/metadata en koude-startfix geleverd | Getoetste sensor/TRV, externe doelbron, centrale/groepsuitvoering en complete gebruikersroute |
| F4 Regeling/hydrauliek | Zone-/seizoens-/hydraulische policies, water-/mengerbasis aanwezig | Geselecteerde gekwalificeerde profielen, feedback/flow/pomp/DHW/stopuitvoer |
| F5 Metrics/grafieken | Counters/kwaliteitscode, Recordergrens/CSV/presentatie aanwezig | Echte Classic-CV/DHW-tijdlijn, retentie/migratie en grafiekacceptatie |
| F6 Board/bus/stop/uitval | TX-locks, auth-/updateguards en historische stopanalyse | Elektrische interface/timing, zelfstandige stop/powerloss, minimumflow en concrete overdracht |
| F7 Radiatorzones | Shadow- en bewaakte adapterbasis; huidig native bereik 1–2 kamers | Echte kraan zonder ketel, begrensde ketelproef, daarna meer zones/72u |
| F8 Vloer/gemengde afgifte | Declaraties en pure klep-/water-/mengerpolicies aanwezig | Actieve graph/profiel-/uitvoerketen en fysiek beoordeelde verdeler/begrenzing |
| F9 Leren/optimum | Modellen/replay/persistentie/resourcegrenzen aanwezig | Actieve aansluiting en meetbaar voordeel; geen nieuwe stage vóór M2 |
| F10 Comfort/releasekwaliteit | Comfort/context/prioriteit en veel release-/GUIwerk aanwezig | Complete actuele gebruikersroute, gekozen functies, praktijk- en eindreleaseacceptatie |

## 6. Werkpakketten en eerstvolgende uitvoering

| Werkpakket | Stand | Open vervolg |
| --- | --- | --- |
| WP01 Eigen basis | Software en meerdere echte releases geleverd | Resterend fysiek F0-profiel/resource/herstelbewijs |
| WP02 Classic | 69-velddecoder en native HA-projectie geleverd op alpha21/dev27 | Langere CV/DHW-veldvergelijking en ontvangstdekking; actieve opvragen blijven geblokkeerd |
| WP03 Contract/bron | Native SOURCE/config/plan/readback gebouwd en toegepast | Modelspecificieke meetrapportproducent, fysieke actualiteit en uitval |
| WP04 Kamerbediening | Kamer/week/actieve profielsave geleverd | Externe doelbron en centrale/groeps-/deviceketen compleet |
| WP05 Actuator | Profiel-C-adapter voorbereid, geen fysieke native vrijgave | Eerste echte kraan zonder ketel, echo/readiness/fallback |
| WP06 Supervisor | Policies en controllerkoppeling met eigen profiel, afzonderlijke bronleeftijden en lokale foutbevestiging gebouwd | Werkelijke bronproducenten/installatieprofiel, praktijkkwalificatie en keteluitvoer |
| WP07 Metrics | Metrics/Recorder/CSV/grafiekcode aanwezig | Echte dataketen, historie-/grafiekacceptatie |
| WP08 Beveiliging/herstel | Auth/setup/update/ETag/methodguards en live behoudsbewijs | Concrete ACL/AP/koude herstel-/powerlossmatrix vóór passende live inzet |

**Vaste volgorde voor deze release:** eerst ontbrekende M2-bron-/actuatorsoftware
en begrensde proefsupervisor; vervolgens Classic-commandopad en laatste
queue/poll-/deadline-/stopcontrole; daarna één bevroren gezamenlijke kandidaat,
volledige releasechecks en één gecoördineerde uitrol. Passieve ontvangst en
onafhankelijk bron-/testwerk hoeven niet te wachten op een fysieke waarneming.

### Nieuw bronwerk binnen dezelfde grotere bètabatch

- Begrensde `BoilerTestSession`: eerst verzonden nul en strikt latere gemelde
  CV-uit/nulvermogen; dan afzonderlijke expliciete start met vaste eindtijd.
  Dubbele start verlengt niets. Stop, lease-/feedbackverlies, DHW, verloren
  proefvoorwaarden, klokfout en zendfout trekken positieve intentie in.
- Laatste verzendcontrole verwerpt oude positieve intenties na stop/deadline.
  Een onzekere stop blijft fout; geen automatische nieuwe sessie of hervatting.
- RX bewaart nu de UART-callbacktijd door de echte begrensde wachtrij heen.
  Later decoderen verjongt een pre-commandotelegram niet tot stopbewijs.
  De extra vaste tijdstempelopslag voor 60 RX-slots is 480 bytes; TX-framegrootte
  blijft ongewijzigd. Dit is geen nieuwe live heap-/latentieacceptatie.
- 72 unieke native gevallen onder ASan/UBSan met leakcontrole PASS: 20 policy,
  5 queue (inclusief 100.000 gelijktijdige pakketten), 18 Classic-regressies, 14 service-/HTTP-gevallen, 9 poll-executorgevallen en 6 encodertests.
  Geen fysieke proef en geen nieuwe release/installatie voor dit bronwerk.
- Controller/status en vier exacte POST-acties zijn aangesloten op dezelfde policy:
  prepare/start/keepalive/stop, bestaande cookie+CSRF, boot-/revisie- en operatorbinding.
  Lezen of opnieuw openen verlengt geen proef. Andere HTTP-writers/OTA/reboot zijn
  tijdens een actieve proef geblokkeerd; Stop blijft door updateguards toegelaten.
- De echte webpagina heeft stopbasis/start/stop, expliciet toezicht, geen automatische
  start/hervatting/retry en bescherming tegen late startantwoorden/oude readbacks.
  Drie Chromium-controlviewports met fixture-HTTP PASS; geen fysieke zenderproef.
- Begin/finish-IO scheidt toelating van echte voltooiing: een eerder begonnen positieve
  opdracht blijft zichtbaar na stop/deadline, zonder de daaropvolgende nul te vertragen.
- De echte E32-pollroute gebruikt nu een gedeelde executor: geen opgeslagen positieve
  intentie, opnieuw controleren na encoderen, geen legacy queue/pong zolang de proef
  eigenaar is. Een bezette telemetry-owner slaat de poll over zonder te wachten.
  Reset, RX-overloop en decodefout trekken de positieve proefintentie in. De
  poll-servicetijd blijft ook voor deze route geteld.
- B07/B08 blijven open voor het beoordeelde profiel, hydraulische voorwaarden,
  beoordeelde adres-/maskerkeuze en gekwalificeerde fysieke UART-zender. De geïnstalleerde bron heeft geen testprofiel of
  gekoppelde proefzender; HTTP kan deze niet aanzetten. De E32-TX-lock blijft staan.

### Nieuw Classic-bronwerk: begrensde flow-/nulencoder

- De pollcallback gebruikt nu `ClassicBoilerTestEncoder`: een vast zes-byte
  UBASetPoints `0x1A`-bericht met offset 0, één aanvoerdoelbyte en de bestaande
  checksum. Een nulvraag verandert geen permanent enable-/maximumdoel, vermogen
  of tapwaterbyte. Geen hergebruik van de generieke EMS+-schrijfroute.
- Bronadres, keteladres en bronmasker moeten expliciet beoordeeld zijn. De default
  adresstructuur is oningevuld/onbeoordeeld en weigert ieder frame. De code kiest
  geen adres/masker op basis van alleen ontvangen Classic-telemetrie. Het bestaande
  board-TX-slot en de ontbrekende installatie-/hydraulische vrijgave blijven gelden.
- Zes nieuwe encodergevallen binnen 72 ASan/UBSan-tests: vaste gouden bytes voor
  expliciete maskers, decoder-roundtrip, alle 256 doelbytes, ongeldige tickets/
  adressen, 48 afzonderlijke bitcorrupties en echte pollpolicy met deadline die
  tussen selectie en dispatch verstrijkt. Geen heapallocatie in het frameformaat.
- De protocolreferentie is de gepinde primaire EMS-ESP32 v3.8.4-bron, blob
  `1c40b9ff3556213cbde213ac9e7e8563ec75de7a`, `set_flow_temp`; geen nieuwe externe
  zendimplementatie gekopieerd. Dit is softwarebewijs, geen ketel-/elektrische proef.
  Bewijs: `out/beta-boiler-evidence-20261023/classic-encoder/REVIEW.json`.

### Nieuw HA-bronwerk: levensduur van de meetrapportobserver

- Een native rapportprofiel vervangen of intrekken maakt de oude kwalificatie
  direct lokaal ongeldig, annuleert de oude expiry en biedt de intrekking aan de
  bestaande transportketen aan. Een al verzonden bericht is daarmee niet met
  terugwerkende kracht fysiek ingetrokken; de normale wire-/leasebewaking blijft gelden.
- Registratie levert een eigenaargebonden opruimcallback. Een oude callback of
  oude verlooptimer kan een nieuwe registratie/nieuw rapport niet verwijderen.
  Zelfs een oude observer die zichzelf vervangt en daarna terugkeert of faalt,
  kan geen meetbewijs onder de nieuwe eigenaar afgeven.
- Sample-ID/tijd-watermerken blijven behouden: geen herkwalificatie van dezelfde
  cache, geen verjonging en geen terugkeer naar oude acquisitietijd bij herregistratie.
- De oude bron reproduceert de fout; de gewijzigde bron slaagt in 31 gerichte
  HA-tests. Volledige HA-regressie: 1.637 tests + 68 subtests = 1.705 checks,
  nul fouten/overslagen, met 8 opnieuw gebouwde echte C++-peers en tijdelijke
  lokale MQTT-broker. Broker is opgeruimd. Geen echte apparaat-/HA-wijziging.
- B04 blijft open: deze lifecycle is geen modelspecifieke rapportproducer en
  kwalificeert de huidige diagnostische bron of fysieke TRV niet. Bewijs:
  `out/beta-boiler-evidence-20261023/source-lifecycle/REVIEW.json`.

### Nieuw TRV-bronwerk: TV02-moduscontrole

- De opgeslagen kraancontrole toont bij model TV02-Zigbee de gemelde eigen
  automatische planning, vakantie, verwarming uit of onbekende modus. Die meldingen
  staan in de kamereditor en native configuratiestatus, Nederlands/Engels. Er wordt
  niets automatisch hersteld, omgeschakeld, opgeslagen of naar de kraan gestuurd.
- De voorbereide profiel-C-adapter weigert bij deze conflicten een extern doel,
  ook als een synthetische test profiel/autorisatie expliciet inschakelt. Hij leest
  de modus opnieuw na wachten op de eigenaar en na de laatste autorisatiecheck;
  een tussentijdse wissel van modelclassificatie wordt geweigerd.
- Een gemelde handmatige/heat-modus kwalificeert geen verse doel-echo, klepstand,
  flow of fysieke aansturing. De standaardadapter blijft uit. Andere modellen
  krijgen niet stilzwijgend TV02-semantiek op grond van alleen een presetnaam.
- 64 gerichte HA-tests (21 nieuwe modusgevallen), volledige HA-suite 1.658 tests
  + 68 subtests = 1.726 checks PASS, nul fouten/overslagen. Zes nieuwe mode-browser-
  profielen en acht bestaande kamereditorprofielen PASS. Acht echte C++-peers
  opnieuw gebouwd, tijdelijke lokale MQTT-broker gebruikt en weer verwijderd.
  Nieuwe browsercheck is in CI opgenomen. Firmwarebron is sinds `d4eadea` gelijk;
  het vorige 72-native-/drie-boardbewijs is niet als nieuwe volledige freeze herlabeld.
- B05 blijft open voor verse modelspecifieke rapporten/echo, werkelijk exclusief
  schema-eigenaarschap, readiness/fallback en de fysieke proef zonder ketel.
  Bewijs: `out/beta-boiler-evidence-20261023/tv02-mode/REVIEW.json`.

### Nieuw actuatorbronwerk: identiteit en grenzen bij dispatch

- De voorbereide profiel-C-adapter bindt aan de exacte native registry-identiteit,
  integratie en apparaatidentiteit/model. Verwijderen/heraanmaken onder dezelfde
  entity-ID, hernoemen, uitschakelen of een apparaatwissel kan de oude autorisatie
  niet overnemen. Een gewone wijziging van de weergavenaam blijft toegestaan.
- Na de laatste autorisatiecallback worden identiteit, beschikbaarheid, eenheid,
  doeltemperatuurfunctie en numerieke grenzen opnieuw gecontroleerd. Er zit geen
  externe callback of await tussen deze controles en de service-aanroep. Gewijzigde
  gegevens leiden tot weigering, zonder herstelactie of retry.
- Tien native regressiegevallen gebruiken echte geïsoleerde HA-registries/services.
  De vorige bron faalt reproduceerbaar in negen gevallen; de gewijzigde bron slaagt
  in alle tien en in alle 74 gerichte HA-tests. Volledige suite: 1.668 tests + 68 subtests = 1.736 checks
  PASS, nul fouten/overslagen; zeven HA-pakkettests PASS. Acht bestaande echte
  C++-peers en tijdelijke MQTT-broker gebruikt; broker onafhankelijk afwezig
  bevestigd. Geen firmware- of browserassetwijziging. Een geslaagde synthetische service
  blijft uitsluitend acceptatie van een opdracht, geen fysieke kraanterugmelding.
- B05 blijft open voor het oorspronkelijke rapport/echo, exclusief eigenaarschap
  en de fysieke proef. Geen standaardadapter ingeschakeld en geen live actie.
  Bewijs: `out/beta-boiler-evidence-20261023/actuator-dispatch/REVIEW.json`.

### Nieuw UART-bronwerk: gecontroleerde voltooiing

- Hoofd-UART en forwarder gebruiken dezelfde gecontroleerde zendschakel. Iedere
  byte moet door de SDK zijn geaccepteerd, de transmitter moet bij de nul-tick-
  voltooiingscontrole idle melden en zowel BREAK-invoer als terugzetten naar
  normale polariteit moeten slagen. Anders retourneert de route geen succes.
  Een mislukte BREAK-invoer probeert alleen normale polariteit te herstellen;
  er is geen herhaling van het frame. Fysiek herstel is daarmee niet bewezen.
- Null/lege/te grote invoer wordt vóór iedere SDK-call geweigerd. Vectorlengte
  blijft size_t: bijvoorbeeld 257 bytes kan niet meer naar een geldig één-byte-
  frame worden afgekapt. De forwarder maakt geen onnodige vectorkopie meer.
- De bestaande 1768-us-byte-/1144-us-BREAK-pacing is behouden, zonder die als
  juiste Classic-installatiemodus te kwalificeren. De nul-tick SDK-controle voegt
  geen wachtbudget toe. De bestaande SDK-write kan intern nog blokkeren;
  totale latentie, waveform/arbitrage en fysieke stop/flow blijven te kwalificeren.
- Acht nieuwe native gevallen, samen 80 ASan/UBSan-gevallen met leakcontrole PASS:
  fout op iedere bytepositie, korte/negatieve SDK-resultaten, niet-idle TX,
  mislukte BREAK/normal-herstel, lengtegrenzen, exacte pacing en volledig wegge-
  compileerde board-uitvoer. Geen firmware geïnstalleerd of fysieke actie.
  Bewijs: `out/beta-boiler-evidence-20261023/uart-completion/REVIEW.json`.

### Bron-/produceronderzoek voor de resterende M2-keten

De HA-specialist heeft de bestaande geselecteerde bindings opnieuw read-only
bevestigd. De RTCGQ11LM-bron is `device_temperature` en blijft diagnostisch;
het product meldt `profile_missing`. De TV02 meldt een eigen automatisch programma.
De geïnspecteerde normale MQTT-projectie biedt geen aangetoond oorspronkelijk
property-acquisitietijdstip/sample-ID of verse gecorreleerde doel-echo. Niet-retained
verkeer of HA-last_reported maakt dit ontbrekende bewijs niet alsnog beschikbaar.

Primaire Z2M 2.14.2-bron bevestigt de relevante grens: de receive-route kiest
converters op cluster/type, maar de normale publicatieroute voegt bij cache_state
oude velden samen. De interne state-update alleen onderscheidt nog geen spontane
rapportage, read-response of optimistische opdracht. Een productieproducer moet
model/property en oorspronkelijke berichtsoort vóór die samenvoeging bewaren,
met aantoonbare ouderdom en replay-/reconnectafhandeling. De converterreferentie
v26.115.1 was aanvankelijk alleen een gepinde referentie. Een gerichte latere
read-only controle van bridge/info meldt nu converters 26.115.1, Z2M 2.14.2 en
herdsman 10.10.0. Dit is broker-metadata, geen directe packagebron-/hashcontrole.
Geen extra externe extensie geïnstalleerd, bron gewisseld of cacheoptie aangepast.

Bewijs: `out/beta-boiler-evidence-20261023/actuator-dispatch/HA-SOURCE-READONLY.json`
en `PRODUCER-SOURCE-TRACE.json` in hetzelfde dossier. Dit onderzoek sluit B04/B05
niet. Het maakt de ontbrekende producentfunctie concreet; alleen extra timestamps
op een HA-cache zijn geen implementatie daarvan.

### Nieuwe bronstap: originele Zigbee-temperatuurproducer

De eerste producentstap voor B04 is gebouwd: een losse, nog niet geïnstalleerde
Z2M-extension bewaart oorspronkelijke WSDCGQ11LM/lumi.weather-temperaturevents,
model/IEEE/endpoint, raw measuredValue en attributeReport versus readResponse.
De state-cache wordt niet gelezen; de bestaande MQTT-client publiceert maximaal
één bericht tegelijk, zonder applicatiebacklog of retained publicatie. De
standaard apparatenlijst is leeg. RTCGQ11LM blijft uitgesloten als ruimtemeting.

Elf Node-contract-/lifecyclegevallen PASS, inclusief cachemerge, ontbrekende
property, vreemde identiteit, offline/busy, transactie-omloop, SDK-fouten en
herstart tijdens stop. Dezelfde controle staat nu in CI. Deze bronbrug levert
ontvangsttijd, geen bewezen acquisitietijd: sampled_at blijft null en beide
kwalificatievlaggen false. De HA-consument/modelkwalificatie, werkelijke
bron-/ouderdomsvalidatie en TV02-echo blijven nog te implementeren. B04/B05
blijven open; geen installatie, sensorwissel of fysieke actie.
Zie [broncontract](ORIGINAL-ZIGBEE-REPORTS.nl.md).

Het voorgaande broncheckpoint `60c548f` is volledig groen op GitHub CI
[40027429946](https://github.com/dielessen/open_thermostat/actions/runs/40027429946):
3 firmwareboards, native, HA, browser, bronreproductie en E32-pakketcontrole.
Dit sluit de broncontrole van dat checkpoint, niet de actieve bèta-acceptatie.

### Nieuwe bronstap: originele Zigbee-rapporten naar native HA

Het voorgaande producentcheckpoint `7f52ed3` is inmiddels volledig groen op
[GitHub CI 40028936470](https://github.com/dielessen/open_thermostat/actions/runs/40028936470).

De producent is nu aangesloten op een echte native HA-ontvanger voor reeds
opgeslagen WSDCGQ11LM-temperaturebindings. Het bestaande MQTT-topic/workerpad
bewaart de originele waarde en berichtsoort; geen HA-cachewaarde wordt overgenomen.
Schema, native identiteit, retained/oud/replay, wachttijd, herstart en reconnect
worden begrensd behandeld. Maximaal één wachtend diagnostisch bericht; minimaal
32 plaatsen blijven vrij in de bestaande queue. Optionele abonnements-/diagnose-
fouten wijzigen de regelverbinding niet. De kamereditor toont ontvangst apart
van het nog ontbrekende meetprofiel en trekt oude broninformatie in bij conceptwissel.

Een echt Node-producentbericht is door de native HA-registries/ontvanger getest.
De 32 nieuwe HA-gevallen behandelen ook model/registry/discoverywijziging,
queue-reservering, onverwachte observerfout, abonnementsweigering en disconnect
vóór verwerking van een wachtend bericht. B04 blijft open voor acquisitie-/bron-
kwalificatie en fysieke validatie; geen QualifiedReport, fysieke sensorwissel,
nieuwe ketelvrijgave of installatie. B05 blijft open voor de afzonderlijke TV02-echo.

Verificatie: volledige HA-regressie 1.747 tests + 68 subtests PASS, geen skips;
na de afsluitende optionele-abonnementafhandeling 148 gerichte native HA-tests
PASS op de definitieve bron. Elf bestaande producenttests en 20 echte Chromium-
profielen PASS (6 ontvangst/metadata, 8 kamerprogramma, 6 TV02-modus), inclusief
NL/EN en smalle schermen. Firmwarebron is in deze stap niet gewijzigd. Bewijs:
`out/original-reports-ha-20261023/`. Dit is geen gezamenlijke bèta-freeze.

### Nieuwe gebruikersfunctie: Mijn ketel en afbeelding op Home

Op verzoek toegevoegd aan dezelfde bètabasis: Settings → Mijn ketel kiest een
ketelpresentatie en toont naam plus lokale, originele SVG-illustratie op Home.
De eerste concrete keuze is Nefit Ecomline Classic, waarvoor passieve uitlezing
is vastgesteld. Geen andere modellen als ondersteund verzonnen; de lijst kan
uitgebreid worden na controle. De keuze is geen actieve ketelvrijgave en wijzigt
geen protocol, adres, regelgrens, hydraulisch profiel of EMS-configuratie.

De keuze staat apart in NVS (`ot_display/boiler`), buiten vervangbare filesystem-
slots. Opslaan vereist de bestaande sessie/CSRF-route en bevestigde NVS-readback.
Lege keuze, onleesbare/opslagfout of onbekend model tonen geen verzonnen apparaat;
geen browser-localStorage of externe foto-/trackingsbron. Schermen blijven bruikbaar
bij 1440/390/320 px. Drie nieuwe browserprofielen, 37 bestaande JS-regressies en de
originele NVS-helper met SDK-foutinvoer onder ASan/UBSan PASS. Firmwarebouw voor E32/ESP32/S3, echte binaire OTA-groottes, nieuwe embedded
webbestanden en E32-filesystem/layout/no-TX-controles PASS op bron `b3920ef`.
Ook drie gewone-homepageprofielen en twee dashboardregressieprofielen PASS:
8 browserprofielen samen. Bewijs: `out/boiler-display-20261024/`. Nog niet
geïnstalleerd en geen wijziging van B04–B09-vrijgavevoorwaarden.

### Nieuwe B05-bronstap: oorspronkelijke TV02-datapoints

Het voorgaande HA-ontvangstcheckpoint `0e2793b` is volledig groen op
[GitHub CI 40030592815](https://github.com/dielessen/open_thermostat/actions/runs/40030592815).

De nieuwe zelfstandige Z2M-producent bewaart uitsluitend originele TV02-doel-,
lokale temperatuur-, preset-, verwarmingsstop- en vorstbeveiligingsdatapoints uit
één werkelijk inbound deviceMessage. DP/type/raw bytes, fabrikant/endpoint,
berichtsoort en oorspronkelijke protocolsequences blijven behouden. Geen
HA-modeprojectie, ontbrekende cachevelden, klepstand of fysieke readiness afgeleid.
De eerste ondersteuning is expliciet beperkt tot twee gerefereerde fingerprints;
het werkelijk aangesloten exemplaar krijgt geen stilzwijgende kwalificatie.

Dertien TV02-gevallen plus elf bestaande temperatuurproducentgevallen PASS,
inclusief gouden bytes, onder-/bovengrenzen, type/lengte/duplicate-afwijzing,
onbekende modellen, offline/busy, SDK-fouten, concurrent stop/herstart en
sequence-omloop. Standaard apparatenlijst leeg, maximaal één lopende publicatie,
2048-byte wiregrens, geen extra MQTT-client of applicatiebacklog. CI controleert
nu beide producenten. De native HA-echo-consument, causale doelkoppeling,
eigenaarschap/readiness/fallback en fysieke kraanproef blijven open. Geen
installatie, actuatoropdracht of ketelvrijgave. Zie
[TV02-broncontract](ORIGINAL-TV02-REPORTS.nl.md); bewijs in
`out/tv02-original-reports-20261024/`.

### Nieuw HA-bronwerk: volledige begrensde versieprojectie

- De bestaande metadatafunctie filterde de converter-/herdsmanversies weg uit
  bridge/info. Zij behoudt nu uitsluitend hun expliciet gemelde stringversies,
  naast Z2M-versie/commit. Ontbrekende, lege of onbruikbare velden blijven onbekend;
  er wordt niets uit een benchpin of ander configuratieveld afgeleid.
- De apparaatcontrole toont de gemelde Z2M-/converterversie in Nederlands/Engels.
  Het zijn declaraties, geen packagebron-/hashcontrole of meet-/actuatorvrijgave.
  Geen extra abonnementspaar, brokerclient, publicatie, opslag of instelling.
- Twaalf nieuwe native gevallen controleren ontbrekende/onjuiste versies en
  de whitelist, naast de bestaande echte native registry-/cleanup-/privacytests.
  Volledige HA-suite: 1.680 tests + 68 subtests = 1.748 checks PASS, nul fouten/
  overslagen. Echte C++-peers en tijdelijke MQTT-broker gebruikt; broker verwijderd.
  Zes metadata-browserprofielen (1440/390/320 px × NL/EN), zes TV02-profielen en
  acht bestaande kamereditorprofielen PASS. De versievelden blijven plaintext,
  ook bij markup; een fout/late respons verandert geen draft of kamer.
- De HA-specialist las één exacte geselecteerde bridge/info-publicatie via native
  MQTT/WS met deadline en expliciete unsubscribe; eigen WS gesloten, nul wijzigingen.
  Gerapporteerd: Z2M 2.14.2, converters 26.115.1, herdsman 10.10.0. Retained metadata
  bewijst geen meetactualiteit. B04/B05 blijven open voor de oorspronkelijke rapporten.
  Bewijs: `out/beta-boiler-evidence-20261023/bridge-versions/REVIEW.json`.

### Nieuw meetbronwerk: native identiteit behouden tot transport

- Vertrouwde rapportprofielen worden aan de native sensor-/apparaatidentiteit
  gebonden. Native model-/apparaatwissel of uitschakelen trekt de oude registratie
  en kwalificatie in, ook zonder een nieuwe temperatuurgebeurtenis. De statusview
  weigert bruikbaarheid al vóór de ingeplande registry-callback is verwerkt.
- Identiteit wordt vóór en na de observercallback en vóór overdracht van een
  wachtende gekwalificeerde meting opnieuw gecontroleerd. Een nieuwe registratie
  blijft nodig; oude revokers kunnen geen nieuwe eigenaar verwijderen. Watermerken
  blijven staan. Reeds aan transport overgedragen verkeer is niet terug te halen;
  de bestaande geordende intrekking/lease blijft daarvoor gelden.
- Dezelfde native rij hernoemen of een apparaatweergavenaam aanpassen behoudt de
  identiteit. Een cachebericht krijgt daardoor geen nieuwe acquisitietijd.
  De actuator en runtime delen dezelfde private identityfunctie; geen IDs in de UI.
- Tien nieuwe native regressies: acht fouten op de vorige bron, alle tien en
  alle 116 gerichte HA-tests inclusief comfort/context PASS. De bestaande
  synthetische comfort-fixture registreert nu ook de native rapportprofieleigenaar;
  de productiecontrole is daarvoor niet versoepeld. Volledige HA-suite: 1.690 tests
  + 68 subtests = 1.758 checks PASS, nul fouten/overslagen, met acht echte C++-peers
  en tijdelijke lokale MQTT-broker. Beide gebruikte brokers zijn verwijderd.
  Geen nieuw productie-meetprofiel, fysieke meting,
  kraan-/ketelactie of installatie. B04 blijft daarvoor open. Firmware/webassets
  zijn ongewijzigd. Bewijs: `out/beta-boiler-evidence-20261023/report-binding/REVIEW.json`.

De cumulatieve releasenotes staan als concept in
[BETA1-RELEASE-NOTES-DRAFT.nl.md](BETA1-RELEASE-NOTES-DRAFT.nl.md). Versies,
checksum-/installatiebewijzen en fysieke acceptatie worden pas bij de echte freeze
gekoppeld; het concept is geen nieuwe release of extra afvinklijst.

### Releasechecklist — eerste bèta

- [x] B01 Alle 31 eisen, 11 fasen en 8 werkpakketten opnieuw beoordeeld; oude statusregels uit actuele lijst gehaald.
- [x] B02 Alle bekende voorbereide brononderdelen geïnventariseerd en in bètabasis behouden; geen bron-/testbestand uit hoofdwerkmap ontbreekt.
- [x] B03 Nieuwe ontvangstdiagnose/Keteltest/rapport gebouwd en getest: 18 native, 43 GUI-regressies, 3 echte Chromiumviewports met fixture-HTTP, normale E32-build.
- [ ] B04 Observer-lifecycle/native binding en originele WSDCGQ11LM-producer/HA-ontvangstdiagnose gebouwd/getest; productie-meetprofiel met echte acquisitie-/bronkwalificatie en fysieke validatie afronden. Geen trustvinkje of sensorwissel als omweg.
- [ ] B05 TV02-modus/native identiteit/doelcapaciteit, eindige doellevensduur, originele datapuntproducer en native HA-ontvangst/lifecycle geleverd; privé pins en producent geplaatst, één bron geregistreerd. Nog natuurlijke rapportontvangst, causale zendtransactiekoppeling, schema-eigenaarschap en profiel/readiness/fallback afronden. Fysieke proef eerst zonder ketel.
- [ ] B06 Supervisor aan bron-eigen profiel en actuele afzonderlijk gedateerde veiligheids-/DHW-/water-/kraan-/flowfeiten gekoppeld en in controller getest; werkelijke producenten, installatieprofiel en fysieke kwalificatie blijven open. Geen generieke flowaanname.
- [ ] B07 Eindige proefpolicy en controller/HTTP/webbediening gebouwd/getest; afronden met beoordeeld profiel en echte zender. Vaste grenzen/stopprioriteit/operatorbinding, geen automatisch hervatten.
- [ ] B08 Poll-executor, Classic-flow/nulformaat en gecontroleerde SDK-zendresultaten aangesloten/getest; installatieadressering/masker en fysieke UART-zender kwalificeren. Geen oude positieve intentie na deadline/stop/conflict/reset; geen generieke Plusroute.
- [ ] B09 Modelgebonden pre-TX-acceptatiekaart en fabrikantbronnen beoordeeld; concrete TX-interface, timing/polariteit/arbitrage, adres/masker, minimumflow/naloop, onafhankelijke stop/herstel en Tado óf E32 nog fysiek vaststellen.
- [ ] B10 Bestaande voorbereide gebruikersfuncties en juiste onbekend-/draft-/geblokkeerdstatussen in eindkandidaat controleren; niets stilzwijgend laten verdwijnen.
- [ ] B11 Versies/bron bevriezen, volledige CI/3 boards/native/HA/C++/browser/release-/source-/licentie-/compatibiliteitschecks op die exacte kandidaat.
- [ ] B12 Openbare pakketten/bron/ELF/web/checksums en updatecatalogus onafhankelijk controleren; volledige releasenotes met open punten en herstelroute.
- [ ] B13 Eén E32-update via normale updater en HA indien gewijzigd via bestaande HA-agent, met back-up/nacontrole en behoud van programma/bindings/identiteiten.
- [ ] B14 Echte passieve ontvangst en afzonderlijke gecontroleerde start/stop/terugmelding aftekenen zodra B09 fysieke aansluiting toelaat; software- en praktijkbewijs apart bewaren.

B04–B09 bevatten concrete onafgemaakte implementatie/kwalificatie; de release
is dus nog niet gereed. B14 is het fysieke proefrapport bij de bèta, geen reden
om een succesvolle softwarebuild als ketelproef aan te merken. Onbeheerd normaal
verwarmen, acht zones, fysieke vloerverwarming en leerwinst zijn latere
productacceptaties; zij blijven in het plan en worden niet stilzwijgend geschrapt.

M1-software (native kamerprogramma/config/apply) is geleverd in het genoemde
bereik. **M2 blijft open:** originele echte meting → HA → E32 → effectieve
status, plus echte TRV zonder ketel en gesimuleerde ketelvraag met TX uit.
Alleen programma-ACK of beschikbaarheid van een entiteit sluit M2 niet.

## 7. Werkafspraken en bijwerken na iedere taak

1. Eén actieve integratietak; bestaande gepubliceerde bron/tags en de per component vastgelegde geïnstalleerde basis intact laten.
2. Per taak: broncommit, relevante testuitkomst, inventaris-ID en resterende acceptatie bijwerken. Geen vinkje zonder bijbehorend bewijs.
3. Alles wat al voorbereid is behouden; onafgemaakte code zichtbaar beperkt houden. Geen nieuwe comfort-/leer-/P2-stage vóór M2.
4. Grotere samenhangende release, geen tags/uploads/flashes per losse reparatie.
5. HA-installaties via bestaande bevoegde agent met back-up/nacontrole; routinewerk niet opnieuw ter goedkeuring voorleggen.
6. Vragen voor later; ontbrekende fysieke feiten blokkeren alleen afhankelijk werk. Geen langlopende watchers of nieuwe externe diensten.
7. Een documentatieherijking start geen ketel-, actuator-, configuratie- of firmwareactie. Backupwaiver voor de oorspronkelijke flash blijft geldig; niet als herstel-PASS markeren of opnieuw vragen.

## 8. Bewijsindex en historische notities

| Bewijs | Betekenis |
| --- | --- |
| `out/combined-release-evidence-20261023/FINAL-REVIEW.json` | Werkelijk gepubliceerde/geïnstalleerde alpha17/dev23 en instellingenbehoud |
| `out/beta-boiler-evidence-20261023/CHECKPOINT.json` | Ontvangstsoftwarecheckpoint, geen bèta- of fysieke vrijgave |
| `out/plan-audit-20261023/AUDIT.json` | Bron-/inventaris-/takken-/plancontrole van deze herijking |
| `BETA1-RELEASE-INVENTARIS.json` | Alle 23 voorbereide brononderdelen en 95 bestandsverwijzingen met hashes |
| `BETA1-KETELPROEF.nl.md` / `BETA1-PROEFSTAND-ONTWERP.nl.md` | Scope en nog te implementeren begrensd proefcontract |
| `out/critical-path-20261022/SAVED-STOP-RECHECK.json` | Historisch expliciet nulcommando; geen zelfstandige stop bij communicatiewegval |
| `out/plan-audit-20261023/*.before` | Ongewijzigde oude PLAN/WORKBOARD/overdracht/nachtvolgorde; historische bewijsregels behouden |

De lokale `out/`-dossiers worden niet integraal gepubliceerd: ze kunnen privé-
configuratie bevatten. Het releasepakket bevat uitsluitend de gereviewde
bron-/notices-/herlink-/bewijsselectie volgens de bestaande verpakkingsregels.

## Bevestigde ketencomponent: EasyControl Adapter (23 oktober 2026)

De gebruiker heeft het etiket doorgegeven: **Bosch EasyControl Adapter
36749998-18052310-000879-8737908035 V2.3**. Het convertermodel is daarmee
geïdentificeerd op basis van de gebruikersmelding; V2.3 is de etiketversie,
geen onafhankelijk uitgelezen firmwareversie.

De [officiële Bosch-handleiding 6720821559 (2017/06)](https://www.nefit-bosch.nl/media/country_pool/professioneel/documenten/thermostaten/6720821559.pdf),
Nederlandse pagina’s 46–48, beschrijft EMS ↔ iRT voor UBA versie 3,7, naast
OpenTherm 4,0 en aan-uit. De thermostaatzijde gebruikt EMS; dit ondersteunt
de beoogde keten E32 → EMS → EasyControl Adapter → iRT → ketel. Het bewijst
nog niet de UBA-versie van de aanwezige HRC22H, de telegramvertaling van dit
exemplaar of compatibiliteit van onze eigen zender.

De handleiding noemt aparte thermostaat-/cv-klemmen, maximaal 3 meter tussen
adapter en ketel, en polariteitsongevoelige busklemmen. Dat laatste bepaalt
niet de UART-inversie of elektrische uitvoering van de E32-interface.
Protocolherkenning en een groene led bewijzen communicatie, geen geslaagde
begrensde verwarmingsproef of onafhankelijke stop bij verlies van de regelaar.

**B09 blijft open:** actuele aansluiting, E32-zendinterface/timing/adressering,
bevestigde telegrammen en terugmelding, minimumflow/naloop en stopgedrag bij
verbindingsverlies moeten nog worden vastgesteld. De modelvraag is beantwoord;
geen automatische TX-vrijgave of nieuwe fysieke opdracht volgt uit deze registratie.

## Geautoriseerde uitrol voorbereide bron — alpha18/dev24

De gebruiker heeft expliciet gevraagd de voorbereide bron nu te committen en op
HA en E32 te installeren. Deze gezamenlijke passieve release wordt alpha18/dev24;
zij vervangt de ambitie van de actieve eerste bèta niet. B04–B09 blijven open.
De bestaande compile-time uitgangsblokkades blijven behouden. Na freeze volgen
volledige CI, onafhankelijke pakketcontrole, normale OTA en HA-agentinstallatie
met back-up/nacontrole. Uitrolbewijs: `out/prepared-rollout-20261023/`.

## Geleverde passieve release alpha18/dev24

Op expliciet verzoek is de volledige voorbereide bron nu gezamenlijk gecommit,
gepubliceerd en geïnstalleerd. Beide onveranderlijke tags verwijzen naar
`6ef01d0e8468f2bb88310d165fb5d49d033b21d4`. Volledige CI op beide releasetags
en main is geslaagd: drie firmwareboards, native tests, SDK-reproductie,
HA/C++/MQTT-interoperabiliteit en browsers. HA: 1.758 checks, nul fouten/skips.
E32-pakket: 1.065 controles; bronarchief met 614 bestanden exact met de commit
vergeleken. Openbare firmware/manifest/checksums zijn gedownload en vergeleken;
de openbare ZIP heeft volgens de GitHub-server exact de SHA256 van het volledig
gecontroleerde CI-archief. De grote publieke ZIP is niet opnieuw gedownload.

E32 alpha18 is één keer via de normale updater geïnstalleerd. Alle zeven
configuratievergelijkingen slagen, SOURCE rev3/digest behouden en HA-verbinding
na reboot vers/actief. HA dev24 is via de bestaande agent met private back-up,
één Core-herstart en 24 nacontroles geïnstalleerd; alle 76 bronbestanden exact.
De HA-frontendroute en beheerde v24-kaartidentiteit zijn door de agent bevestigd;
geen nieuwe live HA-koude-browserproef geclaimd. Op de echte E32 zijn dashboard,
About, herstartannulering, Keteltest en rapportdownload op drie schermbreedtes
zonder writes of browserfouten gecontroleerd.

**Bij de uitrol stond ontvangst nog uit** (`enabled=false`, nul ketelrapporten).
Tijdens die uitrol was geen fysieke ontvangst- of verwarmingsproef uitgevoerd.
E32-zenden en aanvullende GPIO blijven compile-time geblokkeerd; actieve
proefknoppen zijn uitgeschakeld. B04–B14 blijven voor de actieve bèta gelden.
Een latere read-only opname voor de README bevestigt inmiddels passieve
Classic-ontvangst; zie de actuele observatie hieronder. Veldpariteit en actieve
meet-/kraan-/ketelkwalificatie blijven open.

Actueel bewijs: `out/prepared-rollout-20261023/FINAL-REVIEW.json`. De vorige
alpha17/dev23-assets blijven beschikbaar als archief/herstelbasis; niets overschreven.

## Actuele README-opname: passieve Classic-ontvangst

Bij de echte alpha18-screenshotopname op 23 oktober 2026 staat EMS-ontvangst aan.
Een daaropvolgende GET op `/status/ems/telemetry` meldt
`classic_reports_received`, 49 ketelrapporten, een laatste rapportleeftijd van
168 ms en vijftien verse Classic-velden. Zenden is compile-time geblokkeerd en
het aantal verzonden gegevensframes is nul. Tijdens deze opname waren ook
wachtrijverlies, afgekeurde telegrammen, UART-fouten en UART-resets nul; dit is
een momentopname, geen langdurige uitval-/stabiliteitsproef.

Hiermee is echte passieve ontvangst waargenomen. De afzonderlijke waarden en
afgeleide toestanden zijn nog niet onafhankelijk met de ketel vergeleken.
`control_approved=false`; B04–B09 en de volledige B14-proef blijven open. De
screenshotopdracht heeft geen EMS-instelling, programma of uitgang gewijzigd.
Bewijs: `out/github-readme-20261023/E32-RECEPTION-OBSERVATION.json`.


## Vervolg na aansluiting ketel: uitgebreid passief uitlezen

De aansluiting is bevestigd met een nieuwe read-only meting op de geïnstalleerde
alpha18: 676 Classic-rapporten, laatste leeftijd 3.339 ms, vijftien verse velden.
TX, wachtrijverlies, afgekeurde telegrammen, UART-fouten en resets zijn nul in die
momentopname. Dit bevestigt ontvangst; fysieke aansturing blijft ongekwalificeerd.

**Nieuwe bron voor dezelfde grotere batch, nog niet geïnstalleerd:**

- Classic-decoder uitgebreid van 30 naar 69 velden binnen de bestaande types
  `0x18`, `0x19`, `0x16`, `0x33`, `0x34`: extra temperaturen, ionisatiestroom,
  pompmodulatie, hysterese/minimumperiode en tapwater-/circulatieparameters.
- Vaste inventaris van maximaal 24 ontvangen ketelberichttypen, met telling,
  fragmentoffset/-lengte, leeftijd en decoderstatus. Onbekende types verversen
  geen meting of protocolvrijgave. Bij volle lijst blijft verlies zichtbaar.
- Het ketelscherm verliest geen velden meer door de oude afkap na 40 regels.
  Alle velden en berichtmetadata staan ook in het meetrapport. Verdachte ruwe
  bits en historisch stilstaande tellers blijven onbetrouwbaar voor regeling.
- Zes nieuwe decoder-/catalogusregressies: in totaal 86 native gevallen onder
  ASan/UBSan geslaagd. Het uitgebreide scherm en de bestaande actieve-proefguards slagen elk
  in echte Chromium op 1280/390/320 px met fixturetransport. Alle drie boardbuilds op broncommit `274f39d` slagen. Dit is nog geen
  levering of fysieke veldacceptatie.

**HA-pariteit is nog open.** De bestaande HA-agent heeft alleen de exact
historische ketel en huidige projectentiteiten geïnventariseerd. De 68 oude
EMS-ESP-entiteiten zijn onbekend/onbeschikbaar; aanwezigheid in het register
bewijst geen actuele ketelwaarde. De huidige native HA-route heeft nog geen
volledige projectie van de nieuwe ketelvelden: deze mag niet via een extra
MQTT-client/worker of ongekwalificeerde cache worden nagebouwd. Vervolg is één
begrensde read-only publicatie via de bestaande transport-/eigenaarroute, met
identiteit, originele bronleeftijd en expliciete kwaliteit. M2-meetproducent,
kraanproeven en B04–B14 blijven open.

Wire-offsets zijn onafhankelijk geïmplementeerd na vergelijking met
[EMS-ESP32 v3.8.4 boiler.cpp](https://github.com/emsesp/EMS-ESP32/blob/v3.8.4/src/devices/boiler.cpp)
en de [wirewaardedefinities](https://github.com/emsesp/EMS-ESP32/blob/v3.8.4/src/core/telegram.h).
Geen GPL-implementatie overgenomen. Niet elk veld bestaat op deze ketel;
parameters die alleen op verzoek komen blijven bij passief luisteren onbekend.
Bewijs: `out/ems-readout-improvements-20261023/` en de read-only HA-pariteitsreview.


### Afgetekende broncontroles en volgende uitvoeringsstap

- [x] 86 native tests met ASan/UBSan; bestaande Plus-/poll-/stop-/queuegevallen behouden.
- [x] Uitgebreid scherm en bestaande proefbediening elk op 1280/390/320 px in Chromium.
- [x] `esp32dev`, `esp32s3` en `e32v2` gebouwd op broncheckpoint `274f39d`.
- [x] E32-filesystem gebouwd; partities, dubbele OTA/SPIFFS, inerte defaults en
  gecompileerde afwezigheid van project-UART-zendaanroepen gecontroleerd.
- [x] Bestaande 23 voorbereide onderdelen behouden; 108 bronverwijzingen gecontroleerd.
- [ ] Nieuwe uitlezing via de gezamenlijke volgende release installeren en
  de werkelijk ontvangen nieuwe velden op de eigen keten vergelijken.
- [ ] Native HA-ketelveldprojectie aansluiten en testen op bronleeftijd,
  sessie-/apparaatbinding, herhaling, uitval en unsupported/onbetrouwbaar.

De E32-image is 2.430.496 / 3.670.016 bytes. De oudere `esp32dev`-appslot is
met 1.699.365 / 1.703.936 bytes vrijwel vol; verdere firmware-uitbreiding moet
ook die bestaande buildgrens bewaken. Dit verandert de E32-partitie-indeling niet.

Voor de HA-projectie is het bestaande `fw/telemetry/ems_metrics`-pad onderzocht:
het is sessiegebonden, read-only en begrensd op 2.048 envelopebytes. Het volledige
69-veld-HTTP-rapport past daar niet zomaar in. De volgende implementatiestap is
een afzonderlijk versiegebonden ketelveldcontract over dezelfde transporteigenaar,
met begrensde veldgroepen en originele observatieleeftijden; geen verruiming van
de bestaande metrics-validatie, besturingslease of controletoelating. Daarna de
HA-readprojectie aansluiten op deze gevalideerde berichten. Geen tweede client,
achtergrondpoller of behouden MQTT-bericht als verse ketelmeting gebruiken.


## Native ketelveldprojectie naar HA — aangesloten in bron

Het vervolg op de passieve decoder is aangesloten via de bestaande
ModernTransport/ShadowController en HA-worker. `boiler.fields.v1` verstuurt maximaal
tien velden per groep, één groep per twee seconden, maximaal 2.048 envelopebytes.
De 69 HA-sensoridentiteiten hebben vaste eenheden, originele bronleeftijd en
kwaliteitsattributen. Onbetrouwbare bits/tellers zijn standaard uitgeschakeld;
geen nieuwe statistiek-/energie-identiteiten of ketelwrites. Oude entiteiten en
historie worden behouden. Dit is voorbereid voor de gezamenlijke release en nog
niet op de echte installatie geleverd.

De bron bewaart alle bestaande besturingsgrenzen. Telemetrie kan geen grant,
lease, kamermeting, kraanreadiness of model vernieuwen. Herhaalde acquisitie
verlengt de oorspronkelijke geldigheid niet; HA-wachtrijtijd telt mee. Het
netwerktransport vóór MQTT-ontvangst is niet onafhankelijk getimed en is expliciet
als beperking gemarkeerd. Er wordt geen fysieke controlkwalificatie geclaimd.
Zie [het contract en de foutafhandeling](BOILER-FIELDS-V1.md).

De vorige publieke CI (`40022902449`) faalde op de oude `esp32dev`: de uiteindelijke
binary was 1.705.856 bytes voor een OTA-slot van 1.703.936 bytes. De eerdere
PlatformIO-succesmelding betrof de link-/ELF-grens, geen zelfstandig bewijs voor
de gepadde binary. Herstel: alleen dit 4 MB-board met `-Os` en link-timeoptimalisatie compileren en een
post-buildcontrole op het echte `.bin` tegen beide OTA-slots toevoegen. E32/S3
houden hun bestaande `-O3`-profiel en partitie-indeling. De guard heeft een echte
grensregressie en draait ook in CI. Nieuwe boardresultaten volgen op deze bron.

Bronchecks tot nu: 555 volledige native gevallen en 90 daarvan tevens onder
ASan/UBSan; gerichte HA/C++-interop en veldcontroles geslaagd. Volledige HA-suite: 1.713 tests en 68 subtests geslaagd; twee opt-in packettests
zijn afzonderlijk met de tijdelijke lokale broker uitgevoerd, samen met de extra
workerregressie (67 tests in die run, nul fouten/skips). Nieuwe boardbuilds en
publieke CI nog aftekenen. Installatie, fysieke veldvalidatie,
M2-kamerbron/kraanroute en B04–B14 blijven open.


De `-Os`-controle alleen bleef boven het oude OTA-slot; de nieuwe lokale guard
heeft dat correct afgewezen. De bestaande gepinde GCC8-toolchain is daarom eerst
met een zelfstandige LTO-compile/link gecontroleerd. Alleen `esp32dev` krijgt
`-flto`/fat LTO-objecten en de bijpassende linkoptie. E32/S3 houden hun bestaande
compiler-/linkprofiel. De echte imagegrootte blijft een harde voorwaarde; er is
geen partitie vergroot en geen functie verwijderd. De bronproef `03bb861` bouwde
E32 en S3 wel, maar is nadrukkelijk geen geslaagde drie-boardkandidaat.


De effectieve linkregel verklaart de uitgeschakelde LTO: Arduino voegt ná het
pre-script `-fno-lto` toe. De oude-board-hook draait nu na het framework en haalt
alleen voor `esp32dev` die tegenstrijdige vlag weg. De guardregressie controleert
ook de uiteindelijke vlagkeuze. E32/S3 zijn niet naar dit profiel overgezet.


De uiteindelijke oude-boardbinary met effectieve LTO is **1.641.120 bytes** en
past daarmee in beide bestaande OTA-slots van 1.703.936 bytes (62.816 bytes vrij).
De post-buildguard slaagt. Er zijn geen functies of partities verwijderd.
De HA-cache heeft ook een expliciete monotone-lokale-klokregressie: een teruggaande
ontvangstklok mag geen bestaande of nieuwe velddeadline laten herleven.


### Afgetekend: ketelvelden naar native HA in de bronbasis

- [x] Bestaande transportverbinding/worker gebruikt; zeven begrensde veldgroepen,
  capability-/scope-/sequencecontrole, originele leeftijd en lokale wachtrijtijd.
- [x] Native HA-sensorprojectie voor alle 69 vaste velddefinities; kwaliteit,
  ontbrekende gegevens, eenheden en geen onterechte counterstatistiek.
- [x] 555 native tests; 90 betrokken gevallen tevens onder ASan/UBSan.
- [x] Definitieve HA-run met tijdelijke loopbackbroker: **1.716 tests + 68
  subtests geslaagd**, nul fouten/skips. Broker en eigen clients opgeruimd.
- [x] Werkelijke C++-controller/HA-client-interop, plus vaste eenheden, schalen,
  TTLs, bronsoorten, kwaliteiten en limieten voor alle 69 IDs vergeleken.
- [x] Alle drie boardbuilds geslaagd: oude `esp32dev` op `0a616be`, E32/S3 op
  `fa52faa`; productie-C++ is daarbij gelijk. E32-firmware 2.434.720 bytes;
  oude-boardbinary 1.641.120 bytes. Werkelijke beelden passen in beide OTA-slots.
- [x] E32-filesystem, dubbele OTA/SPIFFS, PSRAM/defaults en afwezigheid van
  project-UART-zendaanroepen in de gecompileerde objecten gecontroleerd.
- [x] Inventaris: 23 voorbereide onderdelen, 108 bronverwijzingen behouden.
- [ ] Openbare CI op de nieuwe eindcommit beoordelen; oude CI-fout niet als
  geslaagde run voorstellen. Nog geen nieuwe tag of installatie.
- [ ] Gezamenlijke uitrol en echte veldvergelijking; daarna M2-originele
  kamermetingen/kraanterugmelding en de afzonderlijke actieve ketelproef afronden.

Bronbewijs: `out/native-boiler-telemetry-20261023/`. Deze aftekening betreft
softwarevoorbereiding; alpha18/dev24 blijft geïnstalleerd en de actieve bèta
blijft `NOT_READY`. De fysieke B04–B14-checks zijn niet stilzwijgend afgevinkt.

### 24 oktober — Nederlands en Engels

De gebruiker vraagt EN/NL voor HA en E32, met Engels als standaard en terugval.
De E32 heeft één vaste-tekstcatalogus voor schermen, knoppen, meldingen en
herstelflows. De taalkeuze staat in het menu en op aanmelden/wifi-installatie;
een browsercookie bewaart de keuze. Wisselen herlaadt de pagina met een
bevestiging voor niet-opgeslagen werk. Kamernamen, SSID’s, formulierwaarden,
model-ID’s en API/protocolgegevens worden niet vertaald.

HA gebruikt de bestaande profieltaal voor de kamerkaart/weekplanner en de
native vertaalvoorziening voor formulieren en entiteiten. EN/NL-catalogi worden
op dezelfde sleutels en placeholders gecontroleerd. Opgeslagen native
Lovelace-dashboardteksten hebben geen taalcontext per kijker: daarvoor geldt de
gevraagde Engelse terugval. Gebruikersnamen van ruimtes/apparaten blijven staan.
Deze uitbreiding hoort bij R29/I05/I09 en de gezamenlijke bèta; geen losse
firmware-installatie of wijziging van ketelvrijgave.

### 24 oktober — alle EMS-velden, modelonafhankelijk

Expliciete gebruikerscorrectie: altijd alle beschikbare ketelentiteiten blijven
uitlezen, ook na het aansluiten van een andere ketel. Het modelprofiel is geen
ontvangst-/decoderfilter. De huidige 69 Classic-definities zijn geen productlimiet;
extra families/velden vereisen nog passende decoders en transportondersteuning.
Onbekende berichttypen en inventaris-overloop blijven zichtbaar. Regelopdrachten
hebben een gemeenschappelijke productinterface met een onderliggende vertaling
per EMS-variant; ontvangst is geen universele zendkwalificatie.
Zie [EMS-uitleesbeleid](EMS-DISCOVERY-POLICY.md).

Passieve waarneming voor de door gebruiker benoemde Ecomline HR 22H wordt via de
bestaande HA-specialist voorbereid, inclusief beschikbare Recorder-historie.
Bewijs en persoonlijk veldprofiel: `out/ecomline-observation-20261024/`. De
geïnstalleerde decodeer-/transportdekking wordt eerst vastgesteld; broncode voor
extra HA-velden is geen bewijs dat die al live beschikbaar zijn. Nieuwe velden
blijven welkom en worden niet beperkt tot het lijstje van deze ketel. De fysieke
vrijgavechecks en de status `NOT_READY` blijven ongewijzigd.

## Actueel herstel HA-ketelvelden — alpha20/dev26

Normale automatische HTTPS-catalogusupdate naar alpha20 geslaagd; HA dev26 via bestaande specialist met privéback-up, configuratiecontrole en één Core-herstart. De E32-webhash en alle 79 HA-bronbestanden zijn exact gecontroleerd. Alle 69 ketelvelddefinities staan op hetzelfde installatieapparaat; bestaande entiteits- en apparaatidentiteiten, SOURCE rev3/digests, kamers, programma en instellingen zijn behouden.

Live nabij-gelijktijdige vergelijking: 27 HA-waarden, waarvan 25 gerapporteerd en 2 afgeleid, komen qua waarde, eenheid en kwaliteit overeen met E32 REST. 22 onbetrouwbare velden zijn standaard uitgeschakeld; 20 overige velden zijn op deze momentopname onbeschikbaar. Dit is bronovereenkomst, geen onafhankelijke fysieke sensorkalibratie. Geen nulwaarden voor ontbrekende metingen of Plus-tellers; ruwe bits zijn geen vlam-/pompbewijs.

De beheerde HA-ketelkaarten verwezen nog uitsluitend naar legacy-IDs. HA dev27 is hiervoor voorbereid: native veldkaarten en temperatuur-/modulatiehistorie, afzonderlijke kwaliteitsgroepen, behoud van hernoemde IDs en uitgeschakelde/andere-installatievelden. 100 gerichte native HA-tests PASS; publicatie/installatie/kaartreferenties nog open. Bewijs: `out/telemetry-rollout-20261024/HA-FIELDS-INDEPENDENT-REVIEW.json`. E32-TX/actuatoruitgangen blijven geblokkeerd; B04–B14 en actieve bèta blijven open.

## Bevestigd gebruikersmodel en profiel — HRC 22H

De gebruiker heeft het exacte model bevestigd als **Nefit Ecomline Classic HRC 22H**. De nieuwe presentatiekeuze en het bronprofiel zijn toegevoegd voor alpha21, met 25 gerapporteerde kandidaatvelden en apart 2 afgeleide activiteiten. Dit vervangt de eerdere modelonzekerheid, geen technische acceptatie. Originele NVS-helper en 4 smalle/desktop-browserprofielen PASS; publieke alpha21-uitrol en echte keuze-readback staan nog open. Alle veldontvangst blijft modelonafhankelijk; geen busopdrachten of uitgangsvrijgave.

## Geleverde profiel- en HA-overzichtsrelease — alpha21/dev27

Nefit Ecomline Classic HRC22H is de expliciet door de gebruiker bevestigde
identiteit en staat nu opgeslagen als E32-weergavekeuze. De oudere HR22H/H22-
alternatieven blijven alleen historische notities. Het bronprofiel bewaart
25 eerder gerapporteerde kandidaten, met onbewezen fysieke bruikbaarheid en
aparte afgeleide activiteit. Alle veldontvangst blijft onafhankelijk van model.

Alpha21 is via de normale HTTPS-catalogusroute geplaatst; running-ELF-SHA en
embedded-webhash komen exact overeen met het onveranderlijke CI-pakket. HA27
is via de specialist met scoped back-up, broncontrole en één Core-herstart
geplaatst. 1094 onafhankelijke pakketchecks,651 firmwarebronbestanden,79 HA-
componentbestanden en1818 native HA-tests PASS. De vaste kamereditor blijft
terecht op de ongewijzigde dev25/v25-frontendidentiteit.

Het bestaande beheerde keteloverzicht bevat nu47 ingeschakelde native velden en
3 historiekaarten: aanvoer/retour/gerapporteerde selectie, modulatie en tapwater.
Gerapporteerde en afgeleide velden staan apart;22 standaard uitgeschakelde ruwe
onbetrouwbare velden blijven buiten gerapporteerde kaarten/grafieken. Laatste
controle:26 waarden,24 reported+2 inferred; beschikbaarheid is momentafhankelijk.
Alle105 entiteitsrecords, apparaatgroep, kamers, week en instellingen behouden;
alleen de expliciet gevraagde weergavemodelkeuze is gewijzigd. De controle van
unitlabels normaliseert wire `degC/uA/bool/bits/code/text` naar HA `°C/µA/geen
unit`; ongenormaliseerde operationele checkerlabels waren geen productfout.

SOURCE3→4 is gereconcilieerd: uitsluitend15-daagse UTC-horizon +86400 seconden,
beide pure compilaties en digests exact, volledig gelijke opgeslagen week en
gebruikersintentie. Updates moeten de verse geaccepteerde revisie/digest als
fence nemen; geen herstel naar3 of oude helper-DIG uit revision1.

Bewijs: `out/boiler-profile-rollout-20261024/FINAL-INDEPENDENT-LIVE.json` en
`SOURCE4-INDEPENDENT-REVIEW.json`. Native+1h-observatie faalde vóór dataverzameling
op de Fileeditor-aanroepbody; dit blijft FAILED/UNKNOWN. De bewezen URLencoded-
body en HA-eerst volgorde staan in de toekomstige+6h/+24h-jobpayloads; de bestaande
uitgeschakelde foutjob is eenmalig native geïsoleerd herbeproefd: PASS. Alle
actuele velden zijn gelezen, plus629 Recorder-rijen voor67 entiteiten binnen
een expliciet begrensd historiebudget;26 entiteiten hebben nog meer rijen. Dit
is gedeeltelijke retrospectieve historie, geen volledige periode-extrema of
herstel van de oorspronkelijke fysieke1h-momentopname. De retryjob is na succes
native verwijderd; de twee toekomstige controles en alle overige jobdefinities
zijn behouden. Geen nieuwe planner/permanente watcher. Langere bruikbaarheids-
beoordeling blijft open totdat de geplande waarnemingen zijn uitgevoerd. TX/actuatoruitgangen blijven false;
B04–B14 en actieve bèta blijven NOT_READY.


### Vervolg B05 — oorspronkelijke TV02-ontvangstkern voorbereid

- [x] Pure HA-decoder en begrensde ontvangstkern toegevoegd aan dezelfde bètabatch:
  onafhankelijke raw-DP-controle, exacte bronbinding, replay-/disconnectgeneratie,
  ontvangstouderdom inclusief wachttijd en maximaal acht producer-runs.
- [x] 98 gerichte HA-tests voor TV02/temperatuurontvangst PASS; het nieuwe
  interoperabiliteitsgeval voert de echte Node-producent uit. Iedere status houdt
  opdrachtcorrelatie, kraanreadiness en regelkwalificatie false.
- [ ] Eerstvolgende uitvoering: aansluiten op de bestaande native MQTT-worker,
  geselecteerde registry-identiteit en intrekking bij bronwijziging; daarna
  afzonderlijk causale doelkoppeling en fysieke kraanproef zonder ketel.

Geen nieuwe installatie of fysieke opdracht. E32 alpha21 / HA dev27 blijven
geïnstalleerd, B05 blijft open en de actieve bèta blijft NOT_READY. Bewijs:
`out/tv02-consumer-20261024/`.


### Vervolg B05 — native ontvangst/lifecycle aangesloten in de bètabron

- [x] TV02-ontvangstkern aangesloten op de bestaande MQTT-client/worker, met
  expliciete bronpins en een gedeeld maximum van één wachtend diagnostisch
  bericht voor temperatuur en TV02.
- [x] Native registry-/model-/discovery-/kamerwijziging trekt oude diagnose in;
  disconnect verwerpt ook al wachtende berichten. Unload ruimt alleen eigen
  abonnementen en runtimeverwijzingen op.
- [x] Room/get kan de veilige ontvangstsamenvatting naast de bestaande
  kraandoelcontrole leveren, zonder SOURCE/configuratie of readiness te wijzigen.
- [x] 222 gerichte HA-checks PASS. Bestaande client-/controller-/kamerregressies
  meegenomen; geen nieuwe browser-/fysieke acceptatie geclaimd.
- [ ] Bronpins voor de werkelijk geselecteerde kraan beoordelen, extension via de
  bestaande specialist gecontroleerd installeren en echte oorspronkelijke ontvangst
  bewijzen. De standaard pinlijst blijft leeg; de huidige frontendweergave en
  causale opdrachtkoppeling volgen apart.

De actuele uitvoeringsgrens is hiermee verder dan de pure ontvangstkern van
`528914e`. E32 alpha21 / HA dev27 blijven geïnstalleerd; B04/B05 en de actieve
bèta blijven open. Bewijs: `out/tv02-lifecycle-20261024/`.


### B04/B05 — werkelijke geselecteerde bronmetadata gecontroleerd

De bestaande HA-specialist heeft op 24 oktober 2026 om 00:45 UTC de actuele
selecties tweemaal ongewijzigd teruggelezen en bestaande metadata/cache bekeken:
TV02-Zigbee / TS0601, fabrikantfingerprint `_TZE200_hue3yfsn`, endpoint 1 en een
voltooid cached interview. Dit past bij het voorbereide decoderprofiel. Het is
geen nieuw apparaatinterview, verse datapoint of fysieke kraankwalificatie.
Z2M meldt 2.14.2 en converters 26.115.1; packagebestanden zijn niet geattesteerd.
De cached moduleversie verschilt van de registryversie; de werkelijke huidige
kraanfirmware blijft daarom onbekend.

Voor B04 blijft RTCGQ11LM `device_temperature` geselecteerd. De aanwezige aparte
WSDCGQ11LM `temperature`-entiteit was niet beschikbaar en is niet geselecteerd.
Er is niets omgeschakeld en geen acquisitiebewijs aangenomen. Het volgende
praktijkbewijs vraagt een beschikbare passende ruimtemeting, beoordeelde
bronacquisitie en oorspronkelijke rapporten; een trustvinkje lost dit niet op.

Geen SOURCE-/configuratie-/kraandoel-/moduswijziging, MQTT-publicatie, devicequery,
installatie, herstart of schedulerwijziging. Privé-identiteiten blijven uitsluitend
in het private HA-rapport; de openbare bron bevat geen woning-IEEE-adressen.
Bewijs: `out/tv02-lifecycle-20261024/HA-PREFLIGHT-INDEPENDENT-REVIEW.json` en het
0600-rapport `TV02-READONLY-PREFLIGHT.json` in de bestaande HA-artefactmap.


Volledige HA-regressie van de TV02-lifecyclebatch: **1.840 tests + 68 subtests =
1.908 checks PASS**, nul fouten/overslagen, met alle acht C++-peers opnieuw uit
actuele bron gebouwd en een tijdelijke localhost-MQTT-broker. Brokerafwezigheid
na afloop onafhankelijk gecontroleerd. De 222 gerichte checks zijn hierin
inbegrepen. Geen fysieke kraan-/ketelproef of nieuwe productie-installatie.
Bewijs: `out/tv02-lifecycle-20261024/HA-ACCEPTANCE.xml` en `BROKER-FINAL.json`.


### Gebruikersaanvulling — systeemlog in webinterface en instelbare syslog

- [x] Bron voorbereid: 32-regels RAM-log, niveaus/modulefilter, pauzeren,
  tekstdownload en lokaal wissen; Nederlandse/Engelse webinterface.
- [x] Eigen persistente instellingen met NVS-commit/readback; standaard geen
  externe bestemming. RFC5424/UDP, IPv4, poort, apart web-/syslogniveau en
  optionele INFO-markeringen. Geen logschrijfacties naar flash.
- [x] Gewone applicatie-, Arduino- en ESP-IDF-logs aangesloten; native USB-uitvoer
  behouden. Begrensde niet-blokkerende capture, afscherming en verliescounters.
- [x] Bronopname toegevoegd aan I11; bestaande meet-/regelbronkwalificatie niet
  omzeild. Instellingen houden bestaande auth/CSRF/methode-/update-/proefguards.
- [ ] Exacte gezamenlijke release verifiëren/installeren en ontvangst op een door
  de gebruiker gekozen collector plus lange runtime-/heap-/stackbelasting bewijzen.

Gebruik en beperkingen: [LOGGING.nl.md](LOGGING.nl.md). Deze functie gaat mee in
de grotere bètabatch; er is hiervoor geen losse kleine release of live server-
/configuratiewijziging uitgevoerd. B04–B14 blijven voor de actieve bèta gelden.


Loggingbatch — bronverificatie: 573 native gevallen (18 nieuw), echte firmware-
logger/NVS/native hooks en loopback-UDP onder ASan/UBSan/leakcontrole PASS;
4 NL/EN logging-browserprofielen, 4 bestaande modelkeuzeprofielen, 4 bestaande
UI-taalprofielen en 46 bestaande webunitchecks PASS. Generieke ESP32/S3-builds
PASS; E32-build/layout/no-TX/ingebedde assets PASS vóór bronfreeze. Deze bewijzen
zijn geen live collector-/RAM/stack-/duurlastacceptatie of bèta-vrijgave.


### Dashboardverversing — voorbereid voor de gezamenlijke bèta

- [x] Oorzaak hersteld in de bron: iedere tien seconden werd het volledige
  dashboard vervangen. Nu blijven bestaande DOM-elementen behouden en veranderen
  alleen tekst, attributen en daadwerkelijk toegevoegde/verwijderde onderdelen.
- [x] Open details, toetsenbordfocus en scrollpositie blijven behouden;
  ruimtekaarten volgen hun zone-ID bij herschikking. Nieuwe ruimtes beginnen dicht.
  De ketelillustratie en bijbehorende link worden niet opnieuw opgebouwd.
- [x] Hoogstens één statusrequest tegelijk; 15-seconden timeout, afbreken bij
  navigatie en bestaande generatiecontrole. Een tijdelijke fout toont een melding
  met behoud van het dashboard; de volgende succesvolle poll herstelt automatisch.
- [x] Echte Chromium-test op desktop/mobiel gebruikt de bestaande 10-secondenpoll:
  gewijzigde meetwaarden, dezelfde nodes/openstatus/focus/scroll, herschikking,
  vervanging van ruimtes, fout/herstel, begrensde requests en bestaande escaping/
  stale-onderdrukking. Daarnaast 46 webunitchecks en bestaande model-/taalprofielen.
- [ ] Installeren en nakijken op de E32 als onderdeel van de gezamenlijke release.
  Dit is bronvoorbereiding, geen afzonderlijke release of live aansturingsproef.

Bewijs: `out/dashboard-refresh-20261024/`. B04–B14 blijven ongewijzigd open.


### Gezamenlijke releasekandidaat alpha22/dev28

- [x] Oorspronkelijke TV02-room/get-diagnose zichtbaar gemaakt in de HA-editor,
  NL/EN, met typed/bounded waarden en expliciet ontvangst/werking-onderscheid.
  Stale/ongeldige/onderbroken rapporten tonen geen oude datapointwaarden.
- [x] Nieuwe editoridentiteit dev28/v28; bestaande v25/v24/handmatige aliases
  blijven beschikbaar. Browserproef omvat een reeds geregistreerde oude v25.
- [x] Kandidaten alpha22/dev28 bundelen TV02-ontvangst, E32-systeemlog/syslog en
  incrementele dashboardfix, plus alle eerdere geïnventariseerde bron.
- [ ] Volledige controles op de bevroren kandidaat, openbare pakketten en uitrol
  aftekenen met afzonderlijk bewijs. Installed blijft alpha21/dev27 tot die tijd.

Dit is een passieve testreleasekandidaat; B04–B14 worden niet door deze UI- of
versiewijziging afgevinkt. Bronpins blijven leeg; er is geen apparaatselectie of
fysieke aansturing veranderd. Bewijs: `out/next-release-20261024/`.


Kandidaatcorrectie: openbare CI van `8f99809` vond in de losse Logger.cpp-
native testcompilatie een ontbrekende expliciete `<cstdint>`-include op de
runnercompiler. De 573 native gevallen en firmwarebuilds waren hiervoor groen;
de aanvullende helpercompile hield publicatie terecht tegen. Vendorbron blijft
ongewijzigd: de testcompile geeft de standaardheader expliciet mee. De bestaande
alpha22-tag wordt niet herschreven; de gezamenlijke E32-kandidaat wordt alpha23.
HA dev28 houdt zijn ongewijzigde componentbron en eigen onafhankelijke gates.
Installatie blijft pending totdat de nieuwe E32-pakketcontroles groen zijn.


Pakketcontrole vóór publicatie: HA dev28 bevatte nog de historische dev27-
pakketnotities. De tag-run is vóór publicatie gestopt; tag/bron blijven bewaard.
Dev29 krijgt de complete oorspronkelijke TV02-/lifecycle-/UI-notities en behoudt
expliciet de identieke dev28/v28-frontendbytes en -identiteit. De gezamenlijke
kandidaat is daarom alpha23/dev29. Geen extra functionele versie tussentijds
geïnstalleerd. Alle openbare gates moeten op de definitieve bron groen zijn.


### Normale E32-updater — publicatiemetadata begrensd

De gezamenlijke installatie bereikte HA dev29 met behoudsbewijs; de E32 bleef
veilig op alpha21 omdat het actuele GitHub-releaseantwoord 33.010 bytes was bij
32.768 bytes maximum. De uitgebreide oorspronkelijke notities plus een dubbele
samenvatting veroorzaakten dit. Het gaat om de metadata, niet de firmwaregrootte.

- [x] Oorzaak onafhankelijk gemeten met dezelfde API/Accept/User-Agent als de E32.
- [x] Alleen de optionele dubbele samenvatting verwijderd: antwoord 30.621 bytes.
  Alle oorspronkelijke notities, tags, bron, releasestatus en assets behouden;
  catalogus opnieuw idempotent. Geen nieuwe firmware of controleversoepeling.
- [x] Toekomstige publicaties gebruiken de huidige versiesectie plus een vaste
  link naar de volledige notities/historie in de onveranderlijke Git-tag. UTF-8-
  bytegrens en controle dat de releasekop bij de tag past vóór publicatie.
- [x] Zes gerichte regressies: behoud/idempotentie, begrensd API-envelope,
  versiekop, veilige identiteit en bytegrens; standaard browser-CI neemt ze mee.
- [ ] E32 normale catalogus/app-only update en exacte postchecks opnieuw uitvoeren.

Bewijs: `out/next-release-20261024/UPDATER-METADATA-REPAIR.json`. Geen wijziging van
SOURCE, instellingen, programma of fysieke vrijgave door deze publicatiereparatie.


## Geleverde gezamenlijke passieve release — alpha23/dev29

- [x] Openbaar gepubliceerd en geïnstalleerd uit bron `5f31dd7`; volledige
  bronreproductie, 3 boardbuilds, 573 native firmwaregevallen, 1.840 HA-tests
  plus 68 subtests en 14 browser-suites geslaagd. 46 webunitchecks inbegrepen.
- [x] Negen openbare downloads zonder credentials opgehaald en gecontroleerd;
  1.780 onafhankelijke E32-pakketchecks. Alle 80 HA-bestanden gelijk aan Git en
  het firmwarepakket; echte running-ELF/web/source-identiteit gelijk aan de tag.
- [x] Systeemlog/syslog en incrementeel dashboard geleverd; log-/instellingen-GETs
  HTTP 200, buffer 32, standaard syslog uit zonder bestemming. Twee korte samples
  rond 74KB vrij intern geheugen; dit is geen lange belastingkwalificatie.
- [x] Oorspronkelijke TV02-ontvangst/lifecycle en NL/EN-diagnose geleverd in HA29.
  De v28-frontendidentiteit is bewust behouden omdat de frontendbytes gelijk zijn.
  Extension-/bronpins blijven leeg; geen oorspronkelijke fysieke ontvangst bewezen.
- [x] Verse scoped dev27-back-up, één HA Core-herstart en één normale E32 app-only
  HTTPS-update met automatische OTA-boot. Geen extra E32-reboot of rollback.
- [x] SOURCE-revisie4/digest `78012d7e…` op het meetmoment gelijk tussen HA/E32,
  vers/ready en niets staged. Week, bindings, credentials, 105 registryrecords en
  HRC22H-model behouden. Toekomstige controles lezen steeds de verse revisie.
- [x] 27 native ketelvelden beschikbaar: 25 reported + 2 inferred, nul E32/HA-
  vergelijkingsverschillen. 20 unavailable blijven onbekend; 22 onbetrouwbare velden
  blijven uitgeschakeld. Dit zijn momentwaarden, geen volledige fysieke dekking.
- [x] Eerdere catalogusfout server-side hersteld: actuele metadata 30.621 bytes
  tegenover de limiet van 32.768 bytes. Oorspronkelijke notities/assets/tags behouden. Zes
  aanvullende publicatieregressies en volledige CI `40053834962` groen.
- [ ] Originele bron-/kraankwalificatie, collector-/lange resourceproef en actieve
  ketel-/start-stopacceptatie blijven open. B04–B14 en bèta-GO onveranderd open.

Bewijs: `out/next-release-20261024/LIVE-INDEPENDENT-REVIEW.json`,
`PUBLIC-PREINSTALL-INDEPENDENT-REVIEW.json`, `UPDATER-METADATA-REPAIR.json` en de
private scoped installatie-/rollbackreceipts bij de bestaande HA-specialist.
Geen live browserpixels of flashdump geclaimd: geserveerde exacte bytes/hashes,
echte descriptor en native OTA-verificatie zijn de bewezen installatiegrens.


### Afgerond: updater op nieuwe firmware en geplande waarnemingen

- [x] Ook op draaiende alpha23 één gewone releasecontrole uitgevoerd: terminal
  `checked`, fout leeg, passende alpha23/alpha21 gevonden. Geen firmwaredownload,
  tweede installatie, herstart of configuratie-/SOURCE-write bij deze proef.
- [x] De bestaande twee meetjobs behouden: dezelfde IDs, enabled, tijdstippen
  24 oktober 04:58:01.424 UTC en 22:58:01.424 UTC, eigenaar/model/timeouts,
  delivery en deleteAfterRun. Alleen een actuele software-/bootbasis toegevoegd
  aan de oorspronkelijke berichten; geen job erbij en niets opnieuw ingepland.
- [x] Specialist kon deze jobs niet lezen door zijn sessiescope; de bevoegde
  bestaande root-/admin-Gatewayroute heeft uitsluitend de twee native Automations-
  berichten bijgewerkt. Onafhankelijke herlezing bewijst behoud van alle overige
  configuratie en alle andere opgevraagde jobs. Geen HA-configuratiehandeling.
- [x] Oudere versiereferenties blijven historische context; controles lezen de
  verse SOURCE en behandelen de bewuste OTA/Core-bootgrens correct. De mislukte
  oorspronkelijke +1h-proef blijft FAILED/UNKNOWN, geen achteraf gerepareerd bewijs.

Bewijs: `MONITOR-BASELINE-OWNER-REVIEW.json` en `POSTINSTALL-DISCOVERY-REVIEW.json`
in `out/next-release-20261024/`. Lange/actieve acceptaties blijven ongewijzigd open.


### Voorbereiding zendproef — harde deadlines bij vertraagde verwerking

In de volgende gezamenlijke bètabatch is `BoilerTestSession` aangescherpt:

- De vaste stopbasis-/stopdeadline wordt vóór een late uitmelding beoordeeld.
  Een verse uitmelding op of na de deadline kan een verlopen stopbasis niet
  alsnog startklaar maken of een verlopen stopproef als geslaagd markeren.
- Verlopen operatorlease of warmtevraag begint de stoptijd op de oorspronkelijke
  deadline, ook wanneer de eigenaar pas later weer draait. De vroegste van beide
  deadlines geldt. Een al verlopen stopbasis krijgt door leaseverlies geen
  nieuwe observatietijd.
- Een fout blijft vergrendeld. Een nieuwe nulvraag met strikt latere ontvangst
  kan nog gemelde stop aantonen, maar herstelt geen startbevoegdheid.

Zes nieuwe regressiegevallen, inclusief exacte grens, net ervoor/erna, lange
verwerkingspauze en twee tegelijk verlopen deadlines. Volledige native suite:
579 tests PASS. De twee oorspronkelijke late-uitmeldinggevallen faalden vóór de
broncorrectie. Bewijs: `out/pre-tx-preparation-20261024/`.
Dit is nog geen nieuwe installatie of fysieke timing-/stopkwalificatie.
B04–B14 blijven open; geïnstalleerd blijft alpha23/dev29 en TX blijft geblokkeerd.


### Passieve preflight vóór zendproeven — 24 oktober

De HA-specialist heeft alpha23/dev29, gelijke geaccepteerde SOURCE, ongewijzigde
bindings en uitgeschakelde uitgangen opnieuw bevestigd, zonder configuratie- of
apparaatopdrachten. De kamerbron blijft `profile_missing`; de TV02 meldt `auto`
met `local_schedule_active`. Deze conflicten zijn niet automatisch gerepareerd.

De oorspronkelijke producentbestanden zijn niet geïnstalleerd. De bestaande
beheerroute toont de gedeelde Z2M-data, maar niet de werkelijk draaiende
packagebestanden/loader. Er is geen alternatieve toegang of restart geprobeerd.
Een afzonderlijke offline specialistreview controleert nu de exacte bronbundle:
6/6 hashes onveranderd, 24 producenttests PASS, geen apparaatcommando in
constructor/start/stop/berichtpad. Alleen bestaande inbound events kunnen een
QoS0/niet-retained diagnosebericht op het eigen bridge-topic produceren; de
apparatenlijsten zijn leeg. Dit bewijst niet de werkelijke loader/SDK of een
installatie. De producentcode en tests zijn gelijk aan het geïnstalleerde
release-Gitobject; de meegeleverde TV02-documentatie is de bijgewerkte tekst.

Bewijs: `out/pre-tx-preparation-20261024/LIVE-PASSIVE-PREFLIGHT-REVIEW.json`,
`PRODUCER-OFFLINE-INDEPENDENT-REVIEW.json` en `PRODUCER-BUNDLE-GIT-ATTESTATION.json`.
De vervolggrens blijft een gecontroleerde ontvangst-/kraanproef en vervolgens
installatiegebonden elektrische TX-/stopkwalificatie. Er is nog geen actieve
bèta-GO; B04–B14 blijven open. Een geblokkeerde fysieke voorwaarde wordt niet
opgelost door een trustvlag, sensorwissel of het vrijzetten van de TX-compileergrens.


### B05-vervolgbron — normale HA-opstart en diagnose-isolatie

De normale integratieopstart geeft nu de expliciete bron-eigen
`_ORIGINAL_TV02_DIAGNOSTIC_SOURCES` door aan de bestaande MQTT-eigenaar,
uitsluitend voor de juiste integratie-identiteit. Voorheen bestond dat
constructorargument alleen als aansluitpunt voor apart opgebouwde ontvangers.
De standaardtuple blijft leeg; opties, discovery en eerste berichten kiezen
geen fabrikant/endpoint of bron. Er is geen nieuwe client, worker of opslag.

Een ongeldige of door een native wijziging onbruikbaar geworden optionele pin
maakt nu alleen deze diagnose leeg met een generieke logmelding. De bestaande
regelverbinding blijft starten; er wordt geen ander apparaat aangenomen.
Negen nieuwe regressiegevallen dekken de normale echte integratieopstart,
lege/expliciete selectie, andere installatie, genegeerde opties, bounds en zes
ongeldige bindingssituaties. Gerichte lifecycle: 32 tests PASS. Volledige HA-suite:
1.849 tests + 68 subtests = 1.917 checks PASS, zonder overslagen. De tijdelijke
lokale MQTT-fixture is verwijderd en onafhankelijk als afwezig gecontroleerd.
Dit bronwerk is nog niet geïnstalleerd; HA blijft dev29 en alle uitgangen uit.

Een aanvullende native alleen-lezen snapshot ziet de draaiende Z2M 2.14.2-1,
bridgeversie 2.14.2 en een retained extensielijst met 0 bestanden. Dat toont geen
bestands-/klassenaamconflict, maar bewijst geen actuele producentstart of
hot-loadtoelating. De officiële gepinde loader heeft save/remove zonder
controllerherstart; zijn startcallback vangt fouten af, zodat alleen een
succesvolle save-respons geen werkende producent bewijst. De werkelijke
`enable_external_js`-waarde is niet vastgesteld; er is niets ingeschakeld,
geladen, herstart of naar een apparaat gestuurd.

Bewijs: `out/pre-tx-preparation-20261024/ha-full-routing.xml`,
`MQTT-FIXTURE-CLEANUP.json`, `LOADER-CAPABILITY-READ-REVIEW.json` en
`official-z2m-loader/REVIEW.json`. De oorspronkelijke ontvangst, causale echo,
exclusief kraaneigenaarschap/readiness en fysieke zend-/stopkwalificatie blijven
open. B04–B14 en actieve bèta-GO blijven onveranderd open.


### Code-audit — logredactie en EMS-serialisatie

De codecontrole heeft vier reproduceerbare fouten hersteld voor de volgende
gezamenlijke release:

- ANSI-opmaak kon een gevoelig label splitsen, waarna de logweergave het weer
  samenvoegde. Redactie controleert nu ook de volledige genormaliseerde tekst,
  vóór inkorting; dezelfde normalisatie bepaalt beide sinks zonder heapallocatie.
- Een vectorlengte van 256 bytes werd in de EMS-constructor vernauwd tot nul.
  De vector blijft nu volledig eigendom van het telegram; de encoder weigert
  een ongeldige lengte in plaats van een ingekort telegram te produceren.
- Te lange Classic-/Plus-frames worden vóór opbouw/checksum geweigerd. Bestaande
  geldige frames tot 32 bytes inclusief CRC blijven behouden.
- Een leesverzoek met extra payload wordt geweigerd; extra bytes verdwijnen
  niet meer stilzwijgend uit de geserialiseerde opdracht.

Zes nieuwe native regressiegevallen. De fouten zijn met falende tests vóór de
correcties aangetoond; na correctie 585 native tests PASS. Daarnaast 48 gerichte
gevallen onder ASan/UBSan/leakcontrole, de werkelijke logger-/NVS-/SDK-hook-/
lokale UDP-test, 46 webunitgevallen en 101 tooling-/pakketgevallen PASS.
Bewijs en exacte dekking: `out/code-audit-20261024/`. Dit is code-/testbewijs,
geen fysieke ketel-/zendkwalificatie; de geïnstalleerde versie wijzigt niet.


## B06: supervisor in de echte shadow-controller (24 oktober 2026)

De bestaande hydraulische supervisor ontvangt nu een onveranderlijk bronprofiel
en afzonderlijk gedateerde veiligheids-, storings-, DHW-, waterdoel-, kraan- en
flowfeiten. Boot, eigenaar, sessie en configuratierevisie moeten overeenkomen.
Dubbele berichten verlengen geen geldigheid; teruglopende, toekomstige of
tegenstrijdige feiten leveren geen toestemming. Kamerwarmtevraag verzint geen
kraanstand of onafhankelijke flow. Actuele seizoensvoorwaarden blijven beperken.

Na uitval hervat de supervisor niet automatisch. Een lokale broncode-interface
voor foutbevestiging vereist verse veilige feiten van de huidige eigenaar; een
volgende cyclus vereist opnieuw een openingsopdracht en latere terugmelding.
Er is geen HTTP/MQTT-trustvinkje toegevoegd. De standaardselectie blijft leeg en
alle fysieke uitgangen blijven geblokkeerd.

Lokaal: 602 native tests PASS; 54 gerichte controller-/policytests ook onder
AddressSanitizer/UndefinedBehaviorSanitizer met lekcontrole PASS. Bewijs:
`out/supervisor-integration-20261024/`. B06 blijft open voor werkelijke producenten,
een beoordeeld installatieprofiel en fysieke kwalificatie. Nog niet geïnstalleerd.


## B06/B10: supervisor-diagnose in HA (24 oktober 2026)

De native HA-client verwerkt nu de bestaande supervisorstatus uit dezelfde
gecontroleerde kamerstatus. Het HA-diagnosebestand toont fase, reden en
optionele warmte-/pomp-/afgiftepadintenties afzonderlijk van fysieke uitvoer.
De vier bestaande supervisorvelden blijven compatibel; aanvullende intenties
moeten als volledige, begrensde groep binnenkomen. Alleen bekende velden en
redencodes worden geëxporteerd, geen extra wiretekst, identiteiten of opdrachten.

De diagnose is maximaal 15 seconden na lokale ontvangst beschikbaar, vereist
een geldige huidige sessie en verdwijnt bij ontbrekende/ongeldige data, verlies,
verloop of waargenomen klokteruggang. Dat is ontvangstouderdom, geen acquisitie-
of feedbackkwalificatie. Ongeldige optionele diagnose verandert geldige
kamerbeslissingen niet. Geen nieuwe timer, opslag, MQTT-client of actuatorroute.

64 gerichte HA-checks PASS, met opnieuw gebouwde echte C++-controller. Volledige
CI en de afzonderlijke read-only broninstallatiebeoordeling staan bij het bewijs
in `out/beta-source-chain-20261024/`. B04–B14 blijven open; niet geïnstalleerd.


## B11/B12: HA-pakket vóór de release-tag controleren (24 oktober 2026)

Op `main` werden de HA-tests wel uitgevoerd, maar waren het HA-pakket en de
pakketcontroles beperkt tot `ha-v`-tags. De kandidaatworkflow bouwt en bewaart nu
ook vóór een tag het HA-pakket na de volledige HA/C++-interopsuite. Het originele
JUnit-rapport wordt als afzonderlijk artefact bewaard, ook bij een mislukte suite.
De publicatietaken blijven ongewijzigd aan passende release-tags gebonden.

Dit maakt een onafhankelijke gezamenlijke pakketcontrole mogelijk vóór enige
publicatie of installatie. Een CI-artefact met de bestaande alpha23/dev29-versie
is uitsluitend een broncheckpoint: niet over een gepubliceerde versie heen
installeren/publiceren. Definitieve nieuwe versies en alle resterende bron-,
installatie- en fysieke voorwaarden moeten bij de echte freeze ingevuld zijn.
B11/B12 worden hiermee niet als volledig afgerond afgevinkt.

De zeven pakket-unittests slagen lokaal. Exacte kandidaat-/CI-/pakketresultaten:
`out/combined-candidate-20261024/`. Geen tags, productie-update of zendproef.


## B09: fabrikantbewijs en concrete installatiekaart (24 oktober 2026)

De officiële adapterhandleiding 6720888197 (2019/07) en compatibiliteitsmatrix
6720882620 (2024/10) zijn rechtstreeks gedownload, gehasht en beoordeeld; de
matrix is ook visueel gecontroleerd. Familiedocumentatie ondersteunt de
EcomLine HR(C)-iRT-route via EasyControl Adapter. De relatie tussen verkoopnummer
7736701654 en het opgegeven onderdeelnummer 8737908035 is niet onafhankelijk
vastgesteld; ook de geïnstalleerde UBA-revisie blijft onbevestigd.

De beoordeelde storingssectie beschrijft communicatieverlies en voedingsverlies,
maar specificeert geen maximale CV-stoptermijn. Er is daarom geen timeout of
zelfstandige stopgarantie aan het profiel toegevoegd. De profielnotities blijven
read-only; alle ontvangen ondersteunde velden blijven uitleesbaar.

[ECOMLINE-PRE-TX-ACCEPTATIE](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) legt per onderdeel
het resterende installatiebewijs en een afzonderlijke toekomstige proefregistratie
vast. De E32-portnotitie onderscheidt nu de oude losgekoppelde ontwikkelscope van
de werkelijk geïnstalleerde passieve basis. B09 blijft open. Geen fysieke proef,
profielkwalificatie, configuratiewijziging of nieuwe software-installatie. Bewijs:
`out/installation-review-20261024/`. Het gezamenlijke pakketcheckpoint `fbed431`
blijft intact; deze aanvulling wijzigt alleen documentatie en profielnotities.


## B05: geen oude kraandoelen na wachten of onzekere afloop (24 oktober 2026)

Een nieuwe falende regressietest op de oude bron toont dat wachten op de
adapter-lock niet door de bestaande servicetimeout werd begrensd. Een oude
opdracht kon daardoor later alsnog worden verstuurd. De oorspronkelijke
doeldeadline omvat nu zowel lock-wachttijd als dispatch. Het nieuwste wachtende
doel vervangt oudere wachtende doelen. Een laatste deadlinecontrole vangt ook
synchrone callbacks op die de tijd hebben opgebruikt.

Na timeout, annulering, fout of late voltooiing tijdens een gedispatchte actie
blijft de fysieke uitkomst onbekend en blokkeert dezelfde adapter vervolgdoelen
tot een bron-eigenaar na afzonderlijke beoordeling/herkwalificatie een nieuwe
adapter opbouwt. Er volgt geen retry, modusreparatie, gesimuleerde kraanstand of
generieke fysieke stopopdracht. Serviceacceptatie blijft onderscheiden van
causale echo/readiness/flow. De normale native shadow-route roept de adapter
nog steeds niet aan; geen apparaat-/ketelopdracht of productieaanpassing.

Tien nieuwe gevallen; 84 gerichte HA-tests PASS. De volledige CI en het
vooraf falende geval staan bij `out/actuator-lifetime-20261024/`. B05 blijft open
voor de oorspronkelijke live producenten/pins, causale doelkoppeling, schema-
eigenaarschap en fysieke kraan-/fallbackkwalificatie.


## WP02: actuele passieve controle van alle ketelvelden (24 oktober 2026)

De bestaande HA-specialist heeft een afzonderlijke actuele snapshot gemaakt,
geen zesuurscontrole en geen historie-/continue-dekkingsproef. Twee E32-REST-
opnamen rond de HA-uitlezing bevatten elk 69 velddefinities. De huidige grens
van de decoder is hiermee waargenomen, niet tot maximum of modelfilter gemaakt.

| Uitkomst in dit leesvenster | Aantal | Betekenis |
| --- | --- | --- |
| Geldig, gemeld | 25 | Beschikbare gerapporteerde waarden; fysieke sensor/kalibratie niet bewezen |
| Geldig, afgeleid | 2 | CV/DHW-afleiding; geen onafhankelijke vlam-/pompwaarneming |
| Onbetrouwbare diagnostiek | 22 | E32 verwerkt de velden; native HA-entiteiten bleven uitgeschakeld |
| Ongeldig gemeld | 7 | Geen nul invullen; geen bewijs dat hardware ontbreekt |
| Nog niet waargenomen, gemeld | 13 | In deze boot/snapshot onbekend; geen permanente unsupported-claim |

Alle 27 beschikbare HA-waarden passen in waarde, eenheid en kwaliteit bij beide
REST-opnamen; nul verschillen. Het backend-leesvenster was circa 1,08 seconde.
Elf HA-waarden waren nul: nul blijft een gemelde waarde, geen bewijs van
fysieke bruikbaarheid. De bronwaarnemingsmarkeringen verschillen tussen HA en
REST; er wordt geen exacte ouderdomsgelijkheid geclaimd en HA-last_updated is
niet als acquisitietijd gebruikt. De bronregistraties bewaren die verschillen.

De geïnstalleerde basis blijft alpha23/dev29, bron `5f31dd7`; alle gemelde fysieke
uitgangen bleven uit. Eigen HA-/E32-sessies zijn gesloten. Geen bediening,
configuratie, busopvraag, software-update of schedulerwijziging uitgevoerd. Het
ketelprofiel bevat alleen de gedateerde veldgroepen/tellingen en grenzen van dit
bewijs, geen ruwe huishoudwaarden of native apparaatidentiteiten. Read-all blijft
aan; profielkeuze beperkt geen decoder. Bewijs:
`out/passive-field-review-20261024/INDEPENDENT-PARITY.json` en `PUBLIC-SUMMARY.json`.
B04–B14 blijven open voor de afzonderlijke bron-, installatie- en fysieke eisen.


## WP02: gepland +6h-moment en onafhankelijke Recorder-review (24 oktober 2026)

De bestaande native taak heeft de passieve controle uitgevoerd, zonder nieuwe
taak, bediening, configuratie of busopvraag. Het aangevraagde Recorder-venster
loopt van 00:26:18 tot 04:58:44 UTC: circa **4 uur en 32 minuten**, niet zes uur
aaneengesloten gekwalificeerde metingen. De onafhankelijke review telt 34
geslaagde opvragen in batches van hoogstens vijf entiteiten, 165 unieke
entiteitsantwoorden en 532 statusregels. Iedere antwoordtelling en periode past;
er zijn geen gemelde vervolgpagina's overgeslagen. De 165 antwoorden omvatten
ook legacy/projectdiagnose en zijn geen 165 ketelsensoren. Alle 69 huidige native
velddefinities hebben een expliciet historieantwoord, ook als er geen bruikbare
meting is opgeslagen.

In de native Recorder-waarden variëren `measured_flow_temperature`,
`measured_return_temperature` en `measured_dhw_temperature`. Het ketelprofiel
noemt deze als volgende kandidaten voor onafhankelijke praktijkvalidatie.
Constante instellingen/nulwaarden worden daarmee niet nutteloos verklaard en
er wordt geen veld verwijderd of door het model uitgesloten.

De huidige gestructureerde ontvangst bevat opnieuw 25 geldige gemelde en twee
afgeleide velden; 22 onbetrouwbare diagnostiekvelden blijven apart. De minimale
Recorder-antwoorden bevatten geen oorspronkelijke kwaliteit/acquisitie per
regel. Het venster omvat ook toegestane herstarts en een bootgrens. Daarom geen
cross-boot-countervergelijking, bewezen fysieke CV/DHW-cyclus, gas-/warmtemeting
of continue bronkwalificatie. De oorspronkelijke mislukte +1h-controle blijft
FAILED/UNKNOWN; deze retrospectieve opvraag herstelt dat niet.

De specialist heeft eigen logout/cookie-opruiming bevestigd. Zijn eindrapport en
de onafhankelijke controle stemmen overeen over scope/tellingen/paginering.
Privé bronbewijs: `ecomline-observation-20261024/CHECK-6H.json` in de bestaande
HA-artifactruimte. Smal projectbewijs:
`out/long-observation-review-20261024/INDEPENDENT-HISTORY.json`. B04–B14 blijven
open voor hun afzonderlijke acceptatie. De bestaande +24h-taak is ongewijzigd.


## B05: privé ontvangstpins zonder installatie-IDs in releasecode (24 oktober 2026)

De normale HA-opstart kan nu een expliciet installatiebestand uit de HA-configroot
lezen voor ontvangstdiagnose. De gecompileerde bronpins behouden voorrang;
ontbrekend bestand/defaulttuple geeft nog steeds geen TV02-pins. Exact schema,
privémodus, gewone bestanden zonder symlink, maximaal 32 KiB/64 rijen en stabiele
lezing begrenzen deze optionele bron. Native referentie/model/registry/kamer en
expliciete fabrikant/endpoint blijven vereist. Opties, eerste pakketten en
brokerdata vullen de pins niet in.

Een fout of ongeldige binding schakelt alleen de diagnose uit, niet de gewone
controller. Geen nieuw bestandsschrijver, Store, timer, client, watcher, modus-
reparatie of apparaatopdracht. De loader installeert geen Z2M-extension en
kwalificeert geen sensor, causale echo, klepstand of flow. Een geldige pin laat
een synthetisch origineel rapport via de bestaande worker binnenkomen met alle
kwalificatievlaggen false en `profile_missing` ongewijzigd.

40 nieuwe gevallen; 91 gerichte HA-checks PASS. De integratie-opstart is met
echte HA-registries getest, inclusief ontbrekende/verkeerde kamer/model,
options-only, defecte/te grote/veranderende bestanden, symlink/FIFO/directory,
gecompileerde voorrang en descriptoropruiming. Details:
[ORIGINAL-TV02-DEPLOYMENT](ORIGINAL-TV02-DEPLOYMENT.nl.md). Bewijs en volledige
CI: `out/diagnostic-source-manifest-20261024/`. Nog geen privébestand of nieuwe
integratie op productie geïnstalleerd. De concrete producentinstallatie/pins,
causale doelkoppeling en fysieke B05-proef blijven open.


## B05/B13: installatiepad en actuele update-instructies (24 oktober 2026)

De bestaande HA-specialist heeft de huidige geselecteerde kamer, native MQTT-
actuatoridentiteit en opgeslagen binding opnieuw vergeleken met het privé
TV02-concept: alle bindingchecks gelijk. De bestaande bridgecache bevestigt
fabrikant en expliciet endpoint; dit is geen nieuwe fysieke fingerprintmeting.
HA dev29 en E32 alpha23 blijven geïnstalleerd, met `profile_missing` en alle
fysieke uitgangen uit. Geen producent of privémanifest is geïnstalleerd.

Het [installatiedraaiboek](ORIGINAL-TV02-DEPLOYMENT.nl.md) legt de gezamenlijke
versie-/pakketcontrole, tussenversiecompatibiliteit, verse privé back-up,
hercontrole van pins, normale HA-/E32-update, afzonderlijke producentinstallatie,
spontane ontvangstacceptatie en beperkte terugval vast. De
[update-instructies](GITHUB-UPDATES.nl.md) onderscheiden nu de actuele alpha23/
dev29-installatie van historische alpha14/15/17-status en oude aansluitinstructies.
Bestaande main-CI-pakketten met dezelfde versies worden niet geïnstalleerd.

Bewijs: `out/receive-installation-review-20261024/`. De eerste specialist-CLI
bereikte zijn tijdlimiet ná het schrijven van een duurzaam receipt; dat receipt
is afzonderlijk gecontroleerd op binding, ongewijzigde installatie en gesloten
beheersessies. Ontbrekende native extensionbeheercontrole blijft apart van
ontbrekende package-/loaderhashattestatie. B05 en B13 blijven open; een draaiboek
of succesvolle bindingcontrole is geen producentontvangst of bèta-vrijgave.


## B11–B13: gezamenlijke kandidaat alpha24/dev30 voorbereiden (24 oktober 2026)

Alle bronwijzigingen sinds de geïnstalleerde alpha23/dev29 worden samen gebouwd
als kandidaat alpha24/dev30. De twee tagnamen waren bij controle nog ongebruikt;
versies en pakketnotities zijn bijgewerkt. Geen bestaande tag/download vervangen.
Dit is de passieve bundel met deadline-/logger-/encoderreparaties, hydraulische
controllerkoppeling, read-only HA-supervisordiagnose, kraandoellevensduur en privé
TV02-ontvangstpins. Alle 23 voorbereide onderdelen blijven behouden.

De nieuwe bronversies zijn geen publicatie- of installatiebewijs. De actuele
installatie blijft alpha23/dev29; B11–B14 en de actieve bèta blijven open totdat
hun eigen checks zijn uitgevoerd. Bron-/pakket-CI en onafhankelijk gedownloade
assets worden bij de kandidaat vastgelegd in
`out/combined-alpha24-dev30-20261024/`. De bestaande HA frontendidentiteit dev28/v28
blijft gelijk omdat de frontendbytes gelijk blijven. Geen SOURCE-/sensor-/
kraanmodus-/programmawijziging of fysieke uitgangsvrijgave.


## Gezamenlijke passieve release alpha24/dev30 gepubliceerd (24 oktober 2026)

Beide nieuwe, onvervangende tags wijzen naar
`a1fe06be5e709ff4c6477b7b9be6c8dbd7573987`. Main-CI `40067038967` en de
publicatieruns E32 `40067564931` en HA `40067565237` zijn PASS. De gedownloade
publieke app, updatermanifest en HA-ZIP zijn bytegelijk aan de onafhankelijk
beoordeelde kandidaat. 1740 gezamenlijke pakketchecks, 1108 aanvullende
E32-verifierchecks, 682 exacte Git-bronbestanden, 213 voorbereide bronverwijzingen
en 2003 HA-checks zonder fout/skip. Dit is geen actieve ketelbèta-vrijgave.

De werkelijke Z2M-frontend heeft `config.advanced.enable_external_js: true`
gemeld. Een tijdelijke exacte retained-metadataread via de bestaande HA-MQTT-
verbinding toont nul extensions en geen naam-/klasseconflict; de subscription is
weer verwijderd. Daarmee is de eerdere 50KB-frontendcollectorgrens voor de
extensielijst omzeild via een bestaande readroute, zonder nieuwe brokerclient of
apparaatopdracht. De privé gepinde producent verschilt uitsluitend in één
`DEVICE_BINDINGS`-array; codehash en syntax zijn afzonderlijk gecontroleerd.
Geen producentontvangst, readiness, acquisitie- of actuatorvrijgave geclaimd.

De normale gezamenlijke installatie is via de bestaande HA-specialist uitgevoerd:
één Core-herstart en één normale app-only OTA, nieuwe OTA-boot bevestigd, alle
82 HA-bestanden en running-ELF/web/source exact. Programma/koppelingen/journal,
105 registryrecords, model, syslog en alle E32-instellingen behouden; geen staged
SOURCE. Alle uitgangen false. Na de boot: 69 definities, 24 beschikbare velden
met gelijke waarde/eenheid/kwaliteit, 22 diagnostische velden uit en 23 onbekend/
onbeschikbaar. Dit moment is geen acquisitie-/fysieke kwalificatie. Bewijs:
`out/combined-alpha24-dev30-20261024/` en `out/z2m-receive-guard-20261024/`.


De bestaande +24h-observatietaak is door de native root-eigenaarsroute opnieuw
gelezen en uitsluitend in de verwachte installatieversies/bron bijgewerkt naar
alpha24/dev30/a1fe06b. Tijd 24 oktober 22:58:01.424 UTC, eigenaar, model, tools,
timeout, delivery, enabled en deleteAfterRun exact behouden; geen nieuwe job of
run. De HA-specialist had hiervoor geen callerscope. Native readback en volledige
veldvergelijking: `out/combined-alpha24-dev30-20261024/MONITOR-REVIEW.json`.


## B05: privé pins en producent geplaatst, HA-bronbinding nog afgewezen

- [x] Privémanifest op de HA-configroot: één expliciete pin, regulier 0600-bestand,
  hash gelijk aan het eerder beoordeelde privéconcept; geen SOURCE-/sensorwijziging.
- [x] Eén zelfstandige ontvangende TV02-extension via normale native beheerroute
  opgeslagen en geladen. Exacte teruggelezen codehash gelijk aan de onafhankelijke
  privé voorbereiding; native startlog bevestigd. Geen apparaatopdracht.
- [ ] Oorspronkelijke HA-ontvangst: de ontvanger weigert de bron met de statische
  melding `source binding unavailable`. Natuurlijke rapportontvangst onbevestigd.

De mutatieturn bereikte zijn providertijdlimiet. De afzonderlijke read-only audit
stelde de actuele uitkomst vast zonder writes te herhalen: één manifestwrite,
één integratie-entryreload en één extension-save; geen extra Core-herstart,
remove of rollback. Project/accepted SOURCE/kamer-/TRV-instellingen behouden,
uitgangen false. Actuele metadata-readsubscription expliciet opgezegd; alle
bekende eigen sessies gesloten. Bij een oudere timeoutcollector ontbrak een
expliciete unsubscribe-ACK; diens socketafsluiting is wel bewezen. Geen claim
dat alle servercallbacks afzonderlijk zijn geïnventariseerd.

Native entity/device zijn ingeschakeld, entry/kamer/ref komen overeen, discovery
is aanwezig en native `model_id` is `TV02-Zigbee`. Deze guards zijn dus geen
bewezen oorzaak. De exacte eerste weigering is vervolgens lokaal gereproduceerd met een privé
native snapshot: een graph-kamer heeft geen oude kameractuators. Haar gekozen
output staat onder de centrale installatie-eigenaar. Geen live Python-evaluator
of versoepelde identiteit-/model-/prefixguard toegevoegd. B05 en alle fysieke kwalificaties
blijven open. Bewijs: `out/z2m-receive-guard-20261024/`.


## B05: bronfix voor de werkelijke native graph-eigenaar, nog niet geleverd

De oude constructor op de echte privésnapshot geeft `TV02 source is not a selected
actuator`: `RoomBinding.actuators` is in deze native graph-inrichting bewust leeg.
Entry/kamer/model/discovery/native identiteit slagen. De aangepaste ontvanger
leest uitsluitend voor graph-kamers de unieke centrale configuratie-eigenaar,
valideert het bestaande begrensde heating-draftschema en matcht de expliciete
privéreferentie met de gekozen TRV-output van dezelfde kamer. Er wordt geen
oude actuatorlijst gevuld, SOURCE gewijzigd, bron vervangen of profiel toegekend.
Bij elk status-/ontvangstmoment wordt dezelfde eigenaar opnieuw gecontroleerd;
verwijdering/ongeldigheid trekt de bron blijvend in. Geen fallback naar legacy.

De oorspronkelijke code faalt op de nieuwe regressie; de nieuwe code bindt in de
privé replay precies één bron. Acht nieuwe gevallen plus bestaande lifecycle,
manifest, metadata en kamereditor: 143 PASS, één bestaande localhost-MQTT-check
lokaal overgeslagen wegens afwezigheid van zijn opt-in fixture. De volledige CI
verzorgt die fixture en bewaart zijn eigen resultaat. Privacyfixture blijft buiten
Git; alleen hashes/guarduitkomsten staan in `out/tv02-binding-replay-20261024/`.

Deze correctie gaat mee in de volgende grotere bundel. Er is geen tweede kleine
release, stille livepatch of vervanging van alpha24/dev30 gedaan. De geïnstalleerde
bron blijft `a1fe06be5e709ff4c6477b7b9be6c8dbd7573987`; daadwerkelijke HA-
ontvangstacceptatie blijft open tot de nieuwe bron normaal is geleverd.


## B05: normale levering van de bronfix via HA dev31 voorbereid

De volledige bron-CI 40071267003 is PASS: 2011 HA-checks zonder fout/skip en
82 componentbestanden exact gecontroleerd. Om oorspronkelijke ontvangst werkelijk
te kunnen toetsen, krijgt de geteste fix een unieke HA-versie dev31. Dit is een
gerichte ontvangstherstelupdate na de grotere alpha24/dev30-bundel; E32 alpha24
blijft staan. Geen tagvervanging, stille livepatch of nieuwe firmware alleen om
broncommits gelijk te trekken. Pakketcontrole, normale installatie via de
HA-specialist met verse back-up en natuurlijke ontvangstacceptatie volgen in
`out/ha-dev31-native-binding-20261024/`. Nog geen installatieclaim.


## B05: HA dev31 geleverd; bron geregistreerd, natuurlijke ontvangst wacht

- [x] Nieuwe onvervangende HA-tag `ha-v0.4.0.dev31`, bron `92f5e2b189f4e3eb5bfa544fb41d206a1b9f3ec2`.
  Main-CI 40072179731 en tag-CI 40072196113 PASS; 2011 HA-checks zonder fout/skip.
  Publieke ZIP onafhankelijk byte-voor-byte met alle 82 bronbestanden vergeleken.
- [x] Normale specialistinstallatie met verse scoped back-up en één Core-herstart.
  HA geladen, precies één TV02-bron geregistreerd, oude bindingsfout verdwenen.
  Kamers/weekprogramma's/koppelingen, volledige entry/registry/journal, geaccepteerde
  SOURCE, dashboard, privé manifest/extension en E32-model/syslog behouden.
- [ ] Natuurlijke oorspronkelijke ontvangst: nul rapporten in één begrensde
  observatie van 20 seconden. Status `WAITING`; dit bewijst geen apparaatstoring.

E32 alpha24 blijft bron `a1fe06be5e709ff4c6477b7b9be6c8dbd7573987`; nul OTA's en
geen nieuwe pinwrite/extension-save of apparaatopdracht. Alle uitgangen false,
Tado actief en meetprofiel nog `profile_missing`. De release-inventaris legt
firmware- en HA-bron afzonderlijk vast; de oude HA-commitverwijzing is gecorrigeerd.
B04–B14 en hun fysieke/bronkwalificaties blijven open. Ontvangstregistratie alleen
sluit B05 niet. Bewijs: `out/ha-dev31-native-binding-20261024/`.

De bestaande +24h-taak houdt tijdstip 24 oktober 22:58:01.424 UTC en alle overige
instellingen. Alleen de actuele updatebasis vermeldt nu afzonderlijk alpha24/a1fe
en dev31/92f5, inclusief `WAITING` voor oorspronkelijke ontvangst. Geen nieuwe
job of run. Native readback vergelijkt alle overige velden exact;
`MONITOR-REVIEW.json` bewaart het openbare controlebewijs.


## B04/B05: rapportlevensduur gebonden aan de actuele kamerpolicy

Broncontrole na dev31 vond twee reproduceerbare gaten in de optionele diagnose:
beide oorspronkelijke ontvangers behielden hun oude maximale rapportleeftijd
wanneer de runtime-kamerpolicy veranderde; de temperatuurontvanger kon bij een
verkeerd getypeerde klok of overlopende tijdsdelta een uitzondering geven. Dit
is regressiebewijs, geen vastgestelde oorzaak van een storing op de installatie.

De ontvangers trekken hun bron nu blijvend in bij gewijzigde `maximum_age_ms`.
Een latere terugzetting hergebruikt geen oude rapporten; een normale nieuwe
ontvangsteigenaar begint leeg en handhaaft de nieuwe grens. Alleen een andere
weergavenaam laat de bron en haar oorspronkelijke ontvangsttijd intact. Dit is
getest voor native graph-kamers én legacy-koppelingen, via status, ontvangst en
de bestaande registry-recheck. Temperatuurdiagnose behandelt ongeldige initiële
of latere klokwaarden als blijvend `clock_invalid` en weigert een overlopende
ontvangsttijd zonder uitzondering. Geen nieuwe timer, client of bevoegdheid.

Vóór de fixes falen vier policygevallen en vier klok-/overflowgevallen aantoonbaar;
de corresponderende controlegevallen slagen. Na correctie: 224 gerichte native
HA-checks PASS en één bestaande opt-in localhost-MQTT-check lokaal overgeslagen
wegens ontbrekende fixture; volledige CI levert daarvoor de geïsoleerde fixture.
Bewijs: `out/original-report-policy-20261024/`. Deze bronwijzigingen worden
gebundeld; geen nieuwe release/installatie. Actueel blijft alpha24/dev31 met één
geregistreerde TV02-bron en oorspronkelijke ontvangst `WAITING`. B04/B05 blijven
open voor echte bron-/acquisitie-/causale en fysieke kwalificatie.

Volledige bron-CI `40073641234` op `a948bd806807e5c65e2ef56fcdc0809679d18831`
is PASS: browser, native en alle drie ESP32-builds, bronreproductie en 2040
HA-checks zonder fout/skip. De lokale opt-in MQTT-check slaagt in die CI met zijn
fixture. Het gedownloade CI-pakket is onafhankelijk met alle 82 Git-bronbestanden
en het echte JUnit-rapport vergeleken. Het hergebruikte dev31-nummer in dat
CI-pakket is uitsluitend bouwbewijs en wordt niet over de bestaande release
gepubliceerd of geïnstalleerd.

Een afzonderlijke read-only controle om 07:20:18 UTC ziet nog één TV02-bron met
`WAITING`, zonder actuele veldnamen/rapportleeftijd. Deze status bewaart geen
levenslang ontvangsttotaal en bewijst geen afwezig Zigbeeverkeer. HA meldde ook
`transport_status=rejected`, terwijl native E32-telemetrie actueel was. Dat is
een apart te onderzoeken waarneming; geen bewezen configuratie-, lease- of
apparaatfout. Het aansluitende read-only onderzoek bereikte zijn providertijdlimiet
zonder eindrapport; eerst de al verzamelde resultaten en owned sessieafronding
auditen, geen brede scan of configuratie-apply blind herhalen.

De completion-audit heeft de reeds verzamelde native resultaten teruggevonden:
laatste uitlezing 07:23:54.343 UTC `shadow_ready`, SOURCE/journal gelijk en niet
gestaged, planhorizon geldig. Geen nieuwe live query of mutatie voor die audit;
alle bekende eigen leessessies gesloten. De historische afwijzingsreden blijft
`UNKNOWN`: de huidige HA-projectie bewaart alleen generiek `rejected`, niet de
reply-specifieke reden. Een Recorder-read kwam terug maar de orkestratie meldde
`history_parse_failed`; er is geen bewezen native Recorderfout of historie-export.
Die route niet blind herhalen. Dit ondersteunt geen reparatie/apply of claim
van een blijvende storing. Volgende gerichte bewijsstap is eerst het bestaande
resultaatformaat controleren, of bij een volgende echte afwijzing de begrensde
reply-specifieke diagnose vastleggen via de bestaande ontvanger. Geen extra
client, watcher of fysieke opdracht. Auditbewijs: `TRANSPORT-SUMMARY.json` en
`INDEPENDENT-TRANSPORT-REVIEW.json` in hetzelfde dossier.


## B10: begrensde afwijzingsdiagnose en gezamenlijke HA dev32-bundel

De al aanwezige E32 `rejection_reason` verdween uit HA-diagnostiek. De bestaande
ontvanger bewaart nu maximaal één passende, tijdige, aangevraagde afwijzing in de
actuele configuratie/sessie. Alleen vaste stroom/status/redencodes en lokale
ontvangstouderdom worden geëxporteerd; geen replybytes, pins, binding-ID of
peer-tekst. Dit is expliciet historische diagnose, geen bevoegdheid of actuele
uitgangsstatus. Gezonde state/ACK blijft onafhankelijk; sessiereset en een
geconstateerde klokfout verwijderen de diagnose. Geen extra client/timer/Store.

Een tweede schemafout is lokaal gereproduceerd: `native_config_result` negeerde
een echte afwijzing met het optionele redenveld. Die reply wordt nu doorgegeven
aan de bestaande foutafhandeling. Extra velden en een redenveld bij een
successtatus blijven geweigerd; readback- en toelatingsregels blijven geldig.
De replay bewijst deze schemafout, niet de historische live afwijzingsreden.

Deze wijzigingen en de rapportpolicy-/klokcorrecties worden samen bevroren als
HA dev32, zonder extra E32-flash. De tagnaam was ongebruikt. Volledige CI,
onafhankelijke pakketcontrole en normale specialistinstallatie met verse scoped
back-up volgen op deze exacte kandidaat. Tot bewijs blijft alpha24/dev31 de
geïnstalleerde basis. Bron-/testbewijs: `out/transport-rejection-diagnostic-20261024/`.


## HA dev32 gepubliceerd en normaal geïnstalleerd — 24 oktober 2026

HA `0.4.0.dev32`, bron `e63c06bca41d7e22895fd0100c3d6ca2a916ce4a`, is
gepubliceerd en via de bestaande specialist met verse scoped back-up en één Core-
herstart geïnstalleerd. Main-CI `40074904920` en tag-CI `40075233635` PASS: 2062
HA-checks zonder fout/skip, browser, native/3 boards en bronreproductie. De publieke
ZIP is bytegelijk aan de geteste main-kandidaat. Onafhankelijke bronreview: 30
aanvullende checks zonder issue; root vergelijkt alle 82 uiteindelijke live hashes
met het openbare pakket en de Git-bron.

Nieuwe diagnoseroute werkelijk bereikbaar, `read_only_last_rejection=null` bij
`shadow_ready` en transport_ready. Geen afwijzing geforceerd; de oude onbekende
reden wordt niet achteraf ingevuld. Eén oorspronkelijke TV02-bron geregistreerd
maar `WAITING`; profiel nog `profile_missing`. Alle uitgangen false en Tado blijft
actief. SOURCE/journal, 105 registryrecords, volledige entry/options/subentries,
kamers/week/bindings/dashboard, privé pin/producer en model/syslog behouden.
E32 blijft alpha24/a1fe; geen OTA, SOURCE-apply, extra subscription of apparaatopdracht.
Alle bekende eigen sessies gesloten. Bewijs: `out/transport-rejection-diagnostic-20261024/`.

De bestaande +24h-taak behoudt exact tijdstip 24 oktober 22:58:01.424 UTC en alle
overige instellingen; uitsluitend de geverifieerde HA-verwachting is dev32/e63c,
E32 blijft alpha24/a1fe. Geen nieuwe job/run. De B05-checktekst is bijgewerkt zodat
reeds geplaatste pins/producent niet opnieuw als onafgeronde installatie worden
gepresenteerd. B04–B14 blijven open; een passieve HA-bundel is geen actieve bèta.

Voor de volgende B05-stap is het concrete bronpad onderzocht: de referentie-TV02-
converter gebruikt vaste sequence 1 en kan doelstate optimistisch teruggeven.
Daarom moet een echte, brongebonden native zendtransactie beschikbaar zijn voordat
causale koppeling aangesloten kan worden; een gelijke doelwaarde is geen omweg.
Primaire bronlinks staan in `ORIGINAL-TV02-REPORTS.nl.md`; geen bewijs over de
geïnstalleerde converterbytes of fysieke werking. Geen actieve converterpatch.

Voor de eerste kraanproef zonder ketel is de fysieke opstelling nog niet bekend:
zit de geselecteerde TV02 op de radiator of is een losse proefkraan beschikbaar?
Deze informatie is opgevraagd. Een antwoord is geen zendtoestemming of
profielkwalificatie; de actieve routes blijven geblokkeerd. Eerst bron-/
zendtransactiekoppeling en alle toepasselijke benchvoorwaarden afronden.

### Herstel ESP-eigen diagnose — kandidaat, nog niet geïnstalleerd

De native MQTT-tak keerde terug vóór registratie van de legacy DeviceStatusReporter. HA luisterde voor CPU-temperatuur, vrij/minimaal geheugen, grootste vrije blok en uptime nog naar de legacy topic/availability. Kandidaatbron publiceert deze zes velden elke 15 seconden over dezelfde native MQTT-verbinding; HA behoudt bestaande unique IDs, gebruikt native availability en trekt beschikbaarheid na 45 seconden zonder geldige meting in. Uitgeschakelde RTC-temperatuur blijft onbekend. Dit is afzonderlijk van de 69 ketelvelden en geeft geen regelbevoegdheid. Installatie en actuele waarden zijn nog niet bewezen; geïnstalleerd blijven HA dev32 en E32 alpha24.

### Duidelijke bediening en controles — kandidaat, nog niet geïnstalleerd

HA-installatiestatus toont voor actieve berekeningen expliciet ‘Alleen uitlezen en berekenen (schaduwmodus)’. HA en E32 leggen uit dat configuratieteruglezing, bruikbare metingen, passende kraandoelen en fysieke opdracht-/stopproeven verschillende controles zijn. E32-instellingen en dashboard tonen de betekenis van deze modus in EN/NL. Deze presentatiewijziging verandert geen instelling, toelatingscontrole of uitgang.

### Publicatiecontrole firmwarekandidaat

De bevroren alpha25-tag kreeg geen openbare release of OTA: de publicatiecontrole weigerde de niet-bijgewerkte firmware-releasenotities. Tag en pakketten zijn niet overschreven. De gecorrigeerde firmwarekandidaat is alpha26; de componentbron van het reeds gepubliceerde HA dev33 blijft exact behouden.

### Voorbereiding volgende HA-bundel — niet geïnstalleerd

Parallelle main-CI vond een fractionele-klokgrens bij de alleen-lezen supervisordiagnose: een exact verlopen rapport kon door aftrekken van klokwaarden nog korter dan 15 seconden lijken. Een deterministische repro faalt vóór de correctie en slaagt met directe deadlinevergelijking. De kandidaat voor dev34 behoudt alle overige code; actieve regel-/opdracht-/leasecontroles zijn niet gewijzigd. Gepubliceerde pakketten en de installatie dev33 blijven bevroren.

### Actuele uitvoering diagnoseherstel

HA dev33 is geïnstalleerd: alle 83 live bestanden, frontend v28, 105 registryrecords, SOURCE rev4, programma’s en privé pins/producent zijn gecontroleerd behouden. De zes diagnose-entiteiten bestaan zonder restored-status, maar hebben nog geen live E32-waarden.

E32 alpha26 is gepubliceerd met geteste bron, ELF/web en 1109 onafhankelijke pakketchecks. Eén normale updateaanvraag gaf HTTP202 en een herstart, maar daarna draaide aantoonbaar alpha24. Oorzaak en automatische rollback zijn niet bewezen; de relevante oude RAM-logs waren al overschreven. Hetzelfde HTTPS-pad wordt niet blind herhaald. De bestaande app-only webupload wordt als afzonderlijke herstelroute beoordeeld; er is nog geen geslaagd herstelbewijs. Fysieke uitgangen blijven geblokkeerd.

Vóór een volgende tag: render en controleer de versiegebonden publicatienotities voor beide kanalen met de bestaande organizer; geen nieuwe tag op basis van alleen geslaagde builds.

### Nacontrole: diagnoseherstel geslaagd

De afzonderlijk beoordeelde bestaande app-only upload gaf HTTP200/success; daarna draait alpha26 (`e9ae314…`) met de exacte publieke ELF- en webidentiteit en `boot_pending=false`. Twee gewone niet-retained berichten met 15 seconden verschil kwamen exact overeen met de bestaande HA-entiteiten: vijf numerieke ESP-waarden (vrije/minimale heap, grootste blok, CPU-temperatuur, uptime), RTC terecht onbekend. Vier live webbestanden komen exact overeen met de bevroren bron en bevatten de EN/NL-uitleg. Alle 105 registryrecords, kamers/programma’s, SOURCE rev4, privé pins/producent en instellingen zijn behouden; uitgangen blijven uit.

De mislukte native HTTPS-poging en haar bewijs blijven bewaard. Het automatische downloadpad is **niet** als hersteld afgevinkt. De bestaande eenmalige 24-uurscontrole behoudt eigenaar, tijdstip, aflevering en grenzen; alleen de verwachte software-identiteiten zijn aangepast naar alpha26/dev33. De voorbereidende dev34-correctie heeft volledige geslaagde CI, maar is niet geïnstalleerd.

### Release afgerond — HA dev34 en E32 alpha26

HA `0.4.0.dev34` is gepubliceerd en via de bestaande HA-agent geïnstalleerd met verse, beperkte back-up en één normale Core-herstart. Alle 83 live componentbestanden komen overeen met het openbare pakket van `0aeff4dbaed9f187228e5621545b428648edfce5`; frontend v28, 105 registryrecords, kamers/programma’s, SOURCE rev4, privé pins/producent en instellingen zijn behouden. De alleen-lezen supervisordiagnose gebruikt nu een directe deadlinevergelijking; actieve toelatings-, lease- en regelpaden zijn ongewijzigd. De openbare ZIP is 506204 bytes, SHA256 `a048b9d70ddc811272b93deeabef042a2b77270be7a060b3e340c98fb2388786`. Beide CI-runs (`40082916715`, `40082916725`) slagen; 2066 HA-tests zonder fouten of skips en browsertests geslaagd.

E32 alpha26 blijft exact dezelfde geïnstalleerde firmware: bron `e9ae314f2519ac4208f89d183b4a73a96131d8a4`, ELF/web en bevestigde boot opnieuw gecontroleerd. Vijf ESP-waarden zijn numeriek, de uitgeschakelde RTC blijft onbekend. Geen extra flash of E32-herstart. EMS-TX, forwarder en actuatoruitvoer blijven geblokkeerd; Tado blijft actief. Dit sluit de softwarelevering af, niet de actieve bèta of de resterende fysieke roadmapproeven. Het automatische HTTPS-updatepad blijft open. De bestaande eenmalige controle verwacht nu dev34/alpha26; eigenaar, tijdstip, aflevering en grenzen zijn behouden.

Bewijs: `out/release-finalize-20261024/PACKAGE-REVIEW.json`, `FINAL-REVIEW.json` en de afzonderlijke specialist-installatie-/livehash-/preservatiebewijzen. Oudere voorbereidende/onbevestigde notities hierboven zijn historische checkpoints.


### Volgende gezamenlijke bundel: blijvende updatediagnose

De bekende HTTPS-afwijking verloor het relevante RAM-bewijs na herstart. De bron bewaart nu maximaal één native NVS-controlepunt met fase, oorspronkelijke/doelversie, broncommit, bytes en HTTP-resultaat. De bestaande statusroute toont ook de actuele SDK-resetreden en boot-/app-partitieadressen. EN/NL-updatediagnose blijft open tijdens verversen. Geen extra taak, verbinding, herhaalpoging of wijziging aan de OTA-verificatie-/selectie-/bootregels. Opslagfalen is expliciet en geeft geen automatische herstelactie.

611 native tests, waaronder zeven nieuwe opslag-/reconstructiegevallen, geslaagd. Browser- en E32-buildbewijs staan in `out/update-diagnostics-20261024/`. De browserproef houdt nu ook rekening met de korte afwezigheid van de DOM tijdens de bestaande echte herlaadactie; dit verandert geen productgedrag. Zie [grenzen en vervolg](UPDATE-DIAGNOSTICS.nl.md). Dit is voorbereid bronwerk voor de volgende grotere bundel: alpha26/dev34 blijven geïnstalleerd, de oude oorzaak en fysieke update-/powerlossacceptatie blijven open. M2-bron-/kraanwerk en B04–B14 zijn hiermee niet afgetekend.


### Volgende gezamenlijke release: HA-uitval, lokale naloop en bronbewijs

De bundel omvat nu de eerder voorbereide blijvende updatediagnose, lokaal doorlopende offline naloopbewaking, de klokregressiecorrectie, EN/NL-uitleg op Home en begrensde TV02-ontvangstmetadata. Zie [releaseoverdracht](NEXT-RELEASE.nl.md) en [uitvalaanpak](FAILSAFE.nl.md). De E32 gebruikt bestaande lokale leases; er is geen nieuwe watcher, verbinding of automatische overname door Tado. Alle fysieke uitgangen blijven geblokkeerd.

Zeven nieuwe native gevallen bewijzen stille HA met werkende broker, exacte15s-lease, uitblijven van oude-heartbeatherstel, offline naloop zonder publish/observer, blijvende naloopbewaking na SOURCE-lockout en geen herleving bij klokterugloop. De klokrepro faalt op de bestaande bron en slaagt na correctie. De cumulatieve native suite slaagt met618 gevallen;121 gerichte HA-checks slagen inclusief twee nieuwe metadata-/privacy-/replaygevallen. Browsertests controleren beide viewports en behoud van uitgeklapte uitvaluitleg; de volledige bronfreeze-CI hoort bij het bewijsdossier.

De afzonderlijke passieve HA-agentcontrole zag69 EMS-velden:25 vers gerapporteerd,2 afgeleid,22 onbetrouwbaar,7 ongeldig en13 onbekend. Het HRC22H-profiel bewaart deze momentopname zonder de uitlezing te filteren of fysieke sensorkalibratie te claimen. De oorspronkelijke TV02-ontvanger is nu stale in plaats van waiting: er was eerdere geaccepteerde ontvangst, maar geen verse/causale/kraan-/flowkwalificatie. De gekozen kamertemperatuurbron blijft diagnostische RTCGQ11LM device_temperature zonder meetprofiel; geen bronwissel uitgevoerd.

Alpha26/dev34, SOURCE rev4, kamers/programma’s en pins/producent zijn ongewijzigd. Geen firmware-/HA-installatie, herstart, geforceerd rapport of fysieke opdracht. De forwarderstand is in deze momentopname niet opnieuw als instelling uitgelezen; eerdere disabled-acceptatie blijft afzonderlijk. B04–B14 blijven open waar implementatie, onafhankelijke fysieke stop-/uitvalproef, eindfreeze of uitrol nog ontbreken; geen actieve bèta-PASS. Bewijs: `out/next-release-completion-20261024/`.


### Bronactualiteit: verlopen blijft verlopen

De gedeelde meetkern bewaart verval per waarneming, ook als dit via een diagnoseread wordt vastgesteld. Een oudere leestijd kan oude meetdata niet opnieuw bruikbaar maken. Nieuwe al toegelaten fysieke waarnemingen blijven mogelijk; cache/device-seen/restored blijft ongeschikt als meetbewijs.

De bestaande OpenWeather-eigenaar houdt daarnaast één begrensd ontvangstrecord bij: hetzelfde berekeningstijdstip kan een ingetrokken/verlopen bron niet herstellen of de oorspronkelijke geldigheidsduur verlengen bij een teruglopende UTC-klok. Afwijkende/oudere berichten worden geweigerd; klok-/bronintrekking blijft gelden tot passend nieuw bewijs. Providerberekeningstijd wordt niet als fysieke acquisitietijd voorgesteld. Geen nieuwe taak, client, Store, instelling, bronkwalificatie of fysieke actie.

Zeven nieuwe native gevallen; de volledige native suite slaagt met 625 tests. Beide afzonderlijke regressies falen op de oude bron en slagen met de correctie. De echte E32-build slaagt. Alle 23 voorbereide onderdelen blijven behouden; de nieuwe bronverwijzingen zijn in de inventaris opgenomen. [Broncontract en grenzen](SOURCE-FRESHNESS.nl.md); bewijs `out/source-freshness-20261024/`. De geïnstalleerde alpha26/dev34 en alle open M2-/bèta-/fysieke poorten blijven ongewijzigd.


## B05: verlies van kraan-eigenaarschap tijdens een lopende service (24 oktober 2026)

Vijf regressies op de vorige bron tonen dat intrekking van autorisatie/profiel,
gewijzigde native binding/capability of onbeschikbaarheid tijdens de HA-service
nog tot een geaccepteerd resultaat leidden. De adapter controleert deze feiten
nu ook na de service, binnen dezelfde oorspronkelijke deadline. Ook een gewijzigd
TV02-model, terugkeer naar een lokaal programma en een mutatie vanuit de laatste
autorisatiecallback worden gecontroleerd. De reeds verstuurde opdracht kan niet
worden teruggenomen: de fysieke uitkomst blijft onzeker, dezelfde adapter blokkeert
wachtende en toekomstige doelen. Alleen herstel van de lease wist dit niet.
Een nieuw wachtend doel ontkent de historische acceptatie van een eerdere,
ongewijzigde service niet. Geen retry, presetwijziging of generieke stopopdracht.

Dit sluit een fout in de bestaande begrensde adapter; de normale M2-actuatorroute
is nog niet aangesloten. De bestaande oorspronkelijke TV02-producent observeert
uitsluitend ontvangst en kan geen unieke native zendtransactie leveren. Vaste
Tuya-sequence1, optimistische HA-state en een gelijke doelwaarde blijven onvoldoende
voor causale ACK/readiness. B05 en de gezamenlijke release blijven open.
Bewijs: `out/actuator-owner-loss-20261024/`; uitsluitend synthetische services en
echte HA-registers, geen productieactie of fysieke kraan-/ketelopdracht.


## Grotere vervolgbundel: ontvangst, loghistorie en betrouwbare bediening (24 oktober 2026)

Deze samenhangende softwarepunten zijn toegevoegd aan de gezamenlijke release:

| Planonderdeel | Voorbereide uitwerking | Nog open |
| --- | --- | --- |
| WP05 / I14 kraanontvangst | EN/NL-berichttype, ontvangstouderdom en aanwezige gegevensnamen zichtbaar na verval; oude waarden blijven verborgen | Echte unieke zendtransactie, causale echo, readiness en fysieke proef |
| I09 / R29 HA-kaart laden | Unieke volgende frontend-URL/tag v35; registratie naast bestaande v28 en compatibele handmatige tags | Normale gezamenlijke levering en echte koude sessies met deze nieuwe versie |
| WP07 / I11 systeemlog | Volledige batchvalidatie vóór historie/cursor, oplopende begrensde volgnummers en correcte bootwissel | Collector-/langdurige belasting- en fysieke uitvalproeven |
| WP08 / R28 loginstellingen | Onzekere opslag blokkeert nieuwe submit; invoer behouden, heropenen leest opgeslagen waarden | Gezamenlijke installatie en fysieke opslag-/powerlossacceptatie |
| I05 / R29 ketelprofielkeuze | Afzonderlijke GET na POST, echo is geen opgeslagen toestand; begrensde verzoeken en geen herhaalde submit na onzeker resultaat | Nieuwe gezamenlijke levering; profielkeuze verleent geen ketelvrijgave |

Drie scenario's falen aantoonbaar op de vorige bron: ontbrekende ontvangstmetadata,
logcursor3 in plaats van2 na een ongeldige suffix, en opnieuw beschikbare opslag
na een onzekere ketelwrite. De nieuwe browserproeven controleren ook een correct
POST-antwoord zonder opgeslagen ketelkeuze en een verloren GET-readback na een
wel opgeslagen write. Geen succesmelding of replay bij die onzekere afloop.

Dit is bronvoorbereiding voor dezelfde grotere release. Geïnstalleerd blijven
HA dev34/frontend v28 en E32 alpha26; geen nieuwe tag, livepatch, HA-herstart,
firmwareflash, syslogbestemming of kraan-/ketelopdracht. De volgende beheerde
frontend gebruikt alvast de ongebruikte dev35-URL/v35-tag; de manifestversie
wordt bij de gezamenlijke freeze gecontroleerd. Alle 23 inventarisonderdelen
blijven behouden, B04–B14 en de oorspronkelijke M2-volgorde blijven open.
Bewijs: `out/release-diagnostics-bundle-20261024/`.


Afgeronde softwaredeelpunten van deze bundel (nog niet geïnstalleerd):

- [x] Oorspronkelijke TV02-ontvangstmetadata in de EN/NL-editor aangesloten.
- [x] Ongeldige/verlopen datapointwaarden blijven verborgen; ingetrokken bron
  toont geen oude ontvangstsamenvatting.
- [x] Volledige logbatch valideren vóór incrementele cursor en historie wijzigen.
- [x] Onzekere loginstellingen kunnen vanuit dezelfde pagina niet opnieuw worden verstuurd.
- [x] Ketelprofielkeuze onafhankelijk teruglezen; POST-echo alleen geeft geen succes.
- [x] Ketelverzoeken begrensd; verloren readback blokkeert herhaling en behoudt het concept.
- [x] Nieuwe beheerde HA-module/tag naast v28, met behoud van handmatige kaarttags.

Deze deelpunten veranderen de oorspronkelijke vrijgavechecks B04–B14 niet.


## B06–B08: supervisorbron en Classic-stop verder afgemaakt (24 oktober 2026)

De vrijgave blijft fysiek geblokkeerd. In de bestaande bronroute zijn deze
softwaredeelpunten afgerond voor dezelfde gezamenlijke release:

- [x] Bij een ongeldige snapshottijd blijven stop, limiettrip, ketelfout,
  DHW-prioriteit en actuatorfout van de juiste huidige eigenaar restrictief.
- [x] Een afgewezen/ontbrekend/verlopen bronbewijs wordt niet door herhaling
  opnieuw geldig; alleen een strikt nieuwere getroffen waarneming herstelt het.
- [x] Andere bronvelden behouden hun eigen deadlines; geen verjonging of
  verplicht opnieuw acquisitie uitvoeren voor ongewijzigde, nog geldige velden.
- [x] Teruggaande feedbackklok blijft geblokkeerd tot reconstructie van de bron-eigenaar.
- [x] Echte controller samengesteld met verschillende terugvalpolicies: een
  foutieve waterdoeltijd kan een actuele stop-/DHW-/limiet-/ketelfout niet maskeren.
- [x] Classic-fouttoestand behoudt poll-eigenaarschap en biedt bij verse gemelde
  stop geen overbodige nul aan; geen automatische herstart of legacy-terugval.
- [x] Verlies van stopfeedback trekt bevestiging en oude nultickets in; nieuwe
  nul heeft geen oude schrijf-wachttijd en vereist een strikt later ontvangen stopmelding.
- [x] Engelse stopbevestiging in de bestaande ketelproefpagina gecorrigeerd; Yes/Ja getest.

Acht eerste regressies op de vorige bron: zeven falen, één bestaande weigering
van een verkeerde eigenaar blijft geldig. Rechtstreeks uitgevoerde GoogleTest
bevestigt dit onafhankelijk van de extra SIGHUP-status die PlatformIO bij een
falend testproces rapporteert. Na correctie: 638 native tests PASS, waaronder
13 nieuwe gevallen; 88 gerichte ASan/UBSan-gevallen met lekcontrole PASS, 60
HA-supervisortests en drie NL/EN-browserformaten PASS. Echte E32-build PASS.
De native feedbackgate groeit vast van104 naar120 bytes; proefpolicy blijft176
bytes. Geen extra heapstructuur, taak, client, watcher, bronproducent of fysieke opdracht.

De normale M2-actuatorroute is hiermee niet aangesloten of vrijgegeven. De
ontbrekende oorspronkelijke kamermeting, unieke native zendtransactie/causale
echo en werkelijke hydraulische producenten/installatiekwalificatie blijven
open. B04–B14 blijven open; geen nieuwe kleine release of installatie van deze
bronwijziging. Bewijs: `out/release-control-gates-20261024/`.


Aanvullende combinatiereview binnen dezelfde bronbundel: alle gelijktijdig
foutieve velden worden in één vaste bitmaskercontrole ingetrokken. Alleen het
eerste veld herstellen kan geen oud foutloosheids- of waterdoelbewijs terugbrengen.
De rechtstreekse regressie faalt op bron `c24a316`; de eerdere CI40091742362 is
bewust geannuleerd voor een nieuwe volledige run op de gecorrigeerde bron.
Onafhankelijke brondeadlines blijven behouden; geen extra dynamische opslag.


## B05 / M2: genummerde opdrachten en oorspronkelijke HA-deadline (24 oktober 2026)

De bestaande kraanadapter krijgt een lokale, bron-eigen opdrachtingang. Deze
softwaredeelpunten zijn voorbereid voor dezelfde gezamenlijke release:

- [x] Integer Celsiusdoel en positief uint32-volgnummer met oorspronkelijke
  HA-monotone deadline; wachten en service delen het bestaande maximale tijdsbudget.
- [x] Duplicaat deelt één lopende uitkomst of ontvangt historische serviceacceptatie;
  een gewijzigd duplicaat krijgt geen nieuwe dispatch of deadline.
- [x] Eén laatste resultaat plus het hoogste toegelaten volgnummer; oudere
  nummers en wrap blijven geweigerd nadat hun resultaat is vervangen.
- [x] Duplicaat annuleren kan de uitvoerende eigenaar niet annuleren. Uitvoerende
  annulering/fout wordt bewaard; onzekere fysieke afloop blokkeert vervolgacties.
- [x] Wachtende doelen worden vervangen door het nieuwste; resultaten van een
  eerdere lopende en nieuwere opdracht blijven aan het juiste volgnummer gekoppeld.
- [x] Immutable serviceacceptatie met werkelijk afgeronde native waarde/eenheid;
  apparaatrapport, readiness en regelkwalificatie blijven false.
- [x] Ongenummerde proefingang blijft compatibel; beide ingangen kunnen niet
  binnen dezelfde eigenaar worden gemengd om de volgnummers te omzeilen.

32 nieuwe HA-gevallen; 200 gerichte adapter-/model-/native-bronregressies PASS.
Deze ingang is geen broker-API en krijgt geen settingsvinkje of eigen uitvoertaak.
De normale shadow-verbinding roept haar niet aan. De toekomstige native ontvanger
moet actuele boot/sessie/config/binding en een eigen HA-ontvangstvenster toelaten;
een firmwaredeadline of een bij ontvangst vernieuwde TTL voldoet niet. Daarna
blijven de echte native zendtransactie, causale echo en fysieke kwalificatie nodig.
Geen automatische retry, kraanmodusreparatie, Store, nieuwe wachtrij of client.
B05/M2 en B04–B14 blijven open. Geen publicatie, installatie of fysieke opdracht.
Bewijs: `out/m2-actuator-commands-20261024/`.
