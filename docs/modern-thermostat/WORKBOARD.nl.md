# OpenThermostat — actueel werkbord en releasechecklist

**Bijgewerkt: 23 oktober 2026.** Dit is de enige actuele afvinklijst. Het
[masterplan](PLAN.nl.md) bewaart alle 31 eisen en oorspronkelijke acceptatievoorwaarden.
Oude uitvoeringsnotities zijn gearchiveerd; hun oude woorden “open” en “niet
geïnstalleerd” bepalen de huidige stand niet meer.

## 1. Waar staan we?

| Onderdeel | Vastgestelde stand |
| --- | --- |
| Geïnstalleerde firmware | E32 `v0.1.0-e32v2-alpha.18`, normale OTA/nacontrole geslaagd |
| Geïnstalleerde HA-integratie | `0.4.0.dev24`, via bestaande HA-agent met back-up/nacontrole |
| Geleverde gezamenlijke bron | `6ef01d0e8468f2bb88310d165fb5d49d033b21d4` (passieve voorbereidingsrelease) |
| Nieuwe softwarebasis | `out/beta-boiler-20261023`, `work/beta-boiler-20261023`; ontvangstcheckpoint `cebb0a2` |
| Doel volgende release | Eerste samenhangende bèta: aansluiten, ketelgegevens zien en begrensde start/stop kunnen beproeven |
| Nog geen bèta-vrijgave | Actieve proef-/zendketen en concrete fysieke voorwaarden ontbreken nog |
| Huidige fysieke grens | Geen bewezen echte kraan-/ketelregeling; E32-TX en actuatoruitgangen geblokkeerd |

**Broncontrole:** alle bron-/testbestanden uit de hoofdwerkmap zijn in de
bètabasis aanwezig. De enige testafwijking is een spatie aan het regeleinde,
geen ontbrekende test. Negen bestaande gekoppelde werkbomen zijn schoon. De oude
niet-samengevoegde alpha7-catalogustak is functioneel ingehaald door de latere
geleverde catalogus; deze wordt niet blind opnieuw toegepast.

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

Bewijs: `out/combined-release-evidence-20261023/FINAL-REVIEW.json` en deelreviews.
De 1694 HA-tests horen bij die geleverde bron, niet bij een nog niet gebouwde
nieuwe eindrelease. Seriële stilte na de routereparatie is niet opnieuw fysiek
opgenomen; correcte live HTTP-/assetroutering wel.

## 3. Alles wat voorbereid is, meenemen in de bèta

Elke rij hieronder blijft in de nieuwe bronbasis. “Meenemen” is geen opdracht
om onafgemaakte of ongekwalificeerde mogelijkheden automatisch te activeren.
De machineleesbare [release-inventaris](BETA1-RELEASE-INVENTARIS.json) bevat
95 bronverwijzingen met hashes, status en resterende acceptatie.
De CI controleert deze bronhashes en de dekking van alle eisen en releasechecks
met `scripts/verify_beta_release_inventory.py`. Bij een bewuste bronwijziging
hoort een gereviewde inventarisupdate; een ontbrekend onderdeel faalt de controle.

| ID | Onderdeel | Stand | Nog nodig |
| --- | --- | --- | --- |
| I01 | Eigen project, bron/licenties en reproduceerbaar pakket | Geleverde softwarebasis | Volgende exacte release opnieuw bouwen/verifiëren; geen nieuwe upstream-sync. |
| I02 | Weblogin, sessies, CSRF, setup en herstelroutes | Geleverde softwarebasis | Fysieke AP-/uitval-/herstelmatrix blijft apart. |
| I03 | Automatische HTTPS-update, TLS-geheugen en catalogus | Geleverde softwarebasis | Nieuwe bèta via dezelfde normale updater controleren. |
| I04 | Actuele/archief-releases automatisch ordenen | Geleverde softwarebasis | Nieuwe publicatie moet bestaande tags/assets behouden. |
| I05 | About, uitloggen rechts en herstart onder Settings | Geleverde softwarebasis | Behouden; bevestiging/herstartguards opnieuw in eindregressie. |
| I06 | Kamerinrichting, identiteiten en apparaatmetadata | Geleverd inclusief versieprojectie | Gemelde Z2M-/converterversie zichtbaar; ontbrekend blijft onbekend. Metadata kwalificeert geen fysieke sensor of kraan. |
| I07 | Weekplanner, korte aanraakblokken en effectief doel | Geleverde softwarebasis | Echte programma-save/ACK bevestigd; bron-/uitval-/reconnectproef nog open. |
| I08 | Actieve sensor/TRV/grenzen wijzigen, bewaren en opnieuw toepassen | Geleverde softwarebasis | Alleen normale expliciete save; geen live apparaatwissel tijdens installatie bewezen. |
| I09 | HA-kaart registreren na opstart, zonder herhaald refreshen | Geleverde softwarebasis | Drie echte koude HA-sessies bewezen; versiegebonden module behouden. |
| I10 | Kamernamen op E32 en juiste statische webroutes | Geleverde softwarebasis | Badkamer live bevestigd; geen nieuwe seriële opname van de logstilte. |
| I11 | Meetstatus en geheugen-/toelatingsdiagnose | Geleverd inclusief observer-lifecycle/bronidentiteit | Vervangen/intrekken en native bron-/apparaatwissel trekken oude kwalificatie in; pending transport wordt opnieuw gecontroleerd. Productieprofiel blijft open. |
| I12 | Passieve Classic-decoder en Classic-proefencoder | Decoder en geblokkeerde encoder geleverd | Vast 0x1A-flow/nulformaat gebouwd; beoordeelde bronadressering, fysieke UART-/stopkwalificatie en ontvangstpariteit blijven open. |
| I13 | Ketencontract, SOURCE, journal, configuratie en readback | Geleverde softwarebasis | Logische provisioning/programma-ACK werkt; verse fysieke meet- en actuatorbewijzen ontbreken. |
| I14 | Kraanadapter profiel C, TV02-moduscontrole en bronbench | Modus-/identiteitscontrole geleverd; fysieke route nog onvolledig | Native identiteit en doelcapaciteit vlak vóór dispatch opnieuw gecontroleerd; TV02 auto/vakantie/uit/onbekend zichtbaar en vóór doelactie geweigerd. Verse kraanecho, exclusief eigenaarschap en fysieke werking blijven open; oude bench op SOURCE geblokkeerd. |
| I15 | Kamerregelaar, seizoensbeleid en hydraulische supervisor | Voorbereide code, functie nog onvolledig | Regellogica/shadow voorbereid; hydraulische profiel- en uitvoerketen niet gekwalificeerd. |
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
| R08 | Classic EMS en behoud Plus | Passieve Classic- en Plusbasis geleverd; alle E32-TX geblokkeerd | I12,I21,I23 | Classic-proefcommandopad + elektrische zendmodus/stopbewijs; Plus later eigen fysieke vrijgave. |
| R09 | Weersafhankelijke aanvoer | Curve-/groep-/begrenzingspolicies en centrale draft aanwezig | I15,I16 | Centrale instellingen verbinden met geselecteerde regelaar, actuele buitenbron en keteluitvoer. |
| R10 | Eigen buitenbron | Bronabstractie/binding/draft en validatie aanwezig | I16 | Normale configuratie/apply + bronkwalificatie, leeftijd, bronwisseling/uitval. |
| R11 | Internetweer via HA | HA-bronroute ontworpen; geen volledig gekwalificeerde praktijkketen | I16 | Gratis HA-weerbron, ouderdom/terugval en internetuitval bewijzen. |
| R12 | Zelflerende kamerregeling | Model-, begrenzings-, resource- en replaycode aanwezig | I19 | Niet actief vrijgegeven; getoetste meetdata, baseline/comfortvoordeel en modelrollback. |
| R13 | Optimum-start | Opwarmmodel en begrensd advies/replay aanwezig | I19 | Aansluiten na M2/stabiele basis; meerdere vergelijkbare echte starts en comfortbewijs. |
| R14 | Uitlopen/curve leren | Coast- en curve-adaptatiecode/opslag/replay aanwezig | I19 | Afzonderlijke toelating en meetbaar comfort-/curvebewijs; geen leerwinstclaim. |
| R15 | Alle relevante keteldata | Veldinventaris/Classic-decoder en kwaliteitslabels aanwezig | I12,I17,I21 | Vereiste betrouwbare velden op eigen E32 ontvangen en vergelijken; unsupported/unreliable expliciet. |
| R16 | Brander/modulatiegrafieken | Metrics-/presentatiecode aanwezig; ontvangstscherm nieuw getest | I17,I21 | Echte CV/DHW-tijdlijn, gaten en herkomst; vlam/pompbit niet onafhankelijk betrouwbaar. |
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
| R27 | Meldingen/onderhoud/batterij | Diagnostics/Repairs en batterijblueprintbasis aanwezig | I20 | Passende meldingen en echte fout-/batterij-/geen-responsscenario’s; geen automatische ketelreset. |
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
| WP02 Classic | Passieve software geleverd; ontvangstscherm nieuw getest | Echte ketenpariteit en ontvangst |
| WP03 Contract/bron | Native SOURCE/config/plan/readback gebouwd en toegepast | Modelspecificieke meetrapportproducent, fysieke actualiteit en uitval |
| WP04 Kamerbediening | Kamer/week/actieve profielsave geleverd | Externe doelbron en centrale/groeps-/deviceketen compleet |
| WP05 Actuator | Profiel-C-adapter voorbereid, geen fysieke native vrijgave | Eerste echte kraan zonder ketel, echo/readiness/fallback |
| WP06 Supervisor | Pure policies en geselecteerde shadowlogica bestaan | Kwalificatie en complete hydraulische-/keteluitvoerketen |
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
- [ ] B04 Observer-lifecycle en native bron-/apparaatbinding vóór pending transport getest; productie-meetrapportprofiel/-producer aansluiten. Originele acquisitie, cache/reconnect/stale correct; geen trustvinkje of sensorwissel als omweg.
- [ ] B05 TV02-modusconflicten, native identiteit en actuele doelcapaciteit vóór dispatch gecontroleerd/getest; verse modelspecifieke rapporten/echo, schema-eigenaarschap en profiel/readiness/fallback afronden. Fysieke proef eerst zonder ketel.
- [ ] B06 Bestaande supervisor koppelen aan vereiste actuele profiel-/feedback-/DHW-/hydraulische voorwaarden; geen generieke flowaanname.
- [ ] B07 Eindige proefpolicy en controller/HTTP/webbediening gebouwd/getest; afronden met beoordeeld profiel en echte zender. Vaste grenzen/stopprioriteit/operatorbinding, geen automatisch hervatten.
- [ ] B08 Poll-executor, Classic-flow/nulformaat en gecontroleerde SDK-zendresultaten aangesloten/getest; installatieadressering/masker en fysieke UART-zender kwalificeren. Geen oude positieve intentie na deadline/stop/conflict/reset; geen generieke Plusroute.
- [ ] B09 Concrete TX-interface en aansluit-/stopvoorwaarden vaststellen: timing/polariteit/arbitrage, converterketen, minimumflow/naloop, onafhankelijke stop/herstel en Tado óf E32.
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

1. Eén actieve integratietak; bevroren alpha17/dev23-bron intact laten.
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
