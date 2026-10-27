# OpenThermostat — actueel werkbord en releasechecklist

Beta.5 is gepubliceerd en volledig softwarematig gecontroleerd; installatie
blokkeert op de native GitHub-catalogusverbinding. [Actuele blokkade](BETA5-INSTALL-BLOCKER-20261027.json).
Beta.4 blijft native geïnstalleerd en onafhankelijk geaccepteerd:
[dertien installatiechecks](update-acceptance/e32-beta4-20261026.json).
De actuele uitvoeringsvolgorde staat in [NEXT-RELEASE](NEXT-RELEASE.nl.md).
De oudere voortgangsnotities blijven ongewijzigd in de
[beta.4-werkbordhistorie](WORKBOARD-HISTORY-BETA4-20261026.nl.md).

## Actieve handmatige proefbèta heeft nu voorrang

De bijgewoonde beta.4-nulvraagproef is op opdracht uitgevoerd: één
configuratieleesopdracht, zeven nulframes en een latere gemelde stop. Aanvoer54°C;
geen positieve vraag gestart. [Bewijs](BETA4-ATTENDED-ZERO-20261026.json).
De gebruiker vraagt vervolgens50°C gedurende tien minuten. Beta.5 ondersteunt
hiervoor40–50°C/maximaal600s, standaard50°C/600s, met een gemeten-watergrens
van5–<60°C, verse voorwaarden vóór start, vijfseconden-toezicht en een vaste
warmtedeadline. De nagebootste tienminutenproef bewijst softwaregedrag; nieuwe
firmware moet eerst worden geïnstalleerd voor een echte langere warmteproef.

Beta.5 bundelt ook duidelijkere knopvoorwaarden, GitHub-verbindingsdiagnostiek
en alle entiteiten, instelbaarheid en protocolreferenties op Keteltest. De
volledige catalogus blijft bereikbaar, ook zonder herkend product-ID. Algemene
ketel-/kraanuitvoer en blijvende instellingenwrites blijven uit.

De 31 producteisen en 14 gezamenlijke productaftekeningen hieronder blijven behouden.
De beta.4-software/installatie is afzonderlijk geaccepteerd; dit vinkt niet de
volledige productroadmap of fysieke B07–B09/B14 vooruit af.

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
545 bronverwijzingen met hashes, status en resterende acceptatie.
De CI controleert deze bronhashes en de dekking van alle eisen en releasechecks
met `scripts/verify_beta_release_inventory.py`. Bij een bewuste bronwijziging
hoort een gereviewde inventarisupdate; een ontbrekend onderdeel faalt de controle.

| ID | Onderdeel | Stand | Nog nodig |
| --- | --- | --- | --- |
| I01 | Eigen project, bron/licenties en reproduceerbaar pakket | Geleverde softwarebasis | Volgende exacte release opnieuw bouwen/verifiëren; geen nieuwe upstream-sync. |
| I02 | Weblogin, sessies, CSRF, setup en herstelroutes | Geleverde softwarebasis | Fysieke AP-/uitval-/herstelmatrix blijft apart. |
| I03 | Automatische HTTPS-update, TLS-geheugen en catalogus | Geleverde basis inclusief blijvende diagnose | Checkpoint/EN/NL-diagnose geleverd in alpha27; oorspronkelijke HTTPS-afwijking blijft onverklaard. Geen blinde updaterherhaling. |
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
| I17 | Metrics, grafieken, historiegrens en CSV-export | Native velden/grafieken en begrensde Recorder-CSV; maandexport in bètabron | echte Classic-tijdlijn, Recorder-retentie/migratie en grafiekacceptatie open. |
| I18 | Comfortprioriteiten, raam/aanwezigheidscontext en HEAT/OFF | Beta.6: contacten, extra doelhelper, comfort/aanwezigheid en eindige vakantiebediening in normale HA-route voorbereid | Actieve save/readback, oorspronkelijke HA-/trackerouderdom, zomertijd en kamerscope softwarematig getoetst; fysieke bronkwalificatie en hardwareproef blijven open. |
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
| R02 | Externe kamerdoelbediening | Beta.6/HA0.4.0b4: ingebouwde temperatuurhelper via normale editor/wizard, nieuwe gebruikersactie en eindige override; fysieke bron onvolledig | I18 | Modelspecifiek oorspronkelijk actieprofiel, één override per fysieke wandbediening en echopreventie; hardwareproef. |
| R03 | Gemengde temperatuursensoren | Binding, normalisatie en stale-guards aanwezig; productie-meetprofiel ontbreekt | I06,I11,I13,I14 | Modelspecifieke meetrapportproducent, echte acquisitie en uitval; geen diagnostische device_temp als ambientbewijs. |
| R04 | Meerdere TRVs per kamer/merken | Declaraties en selecties bestaan; huidig native radiatorcontract één TRV per kamer | I06,I08,I14,I16 | Ondersteunde modellen en groepsfeedback; native uitbreiding niet als geleverd claimen. |
| R05 | Open/dicht/proportioneel regelen | Bewaakte profiel-C-adapter en pure regelprofielen aanwezig | I14,I15 | Echte kraan zonder ketel; juiste regelmethode, eigen agenda, echo, afronding en uitval. |
| R06 | Vloerkleppen | Graphdeclaraties, klep-/groepsbasis aanwezig | I16 | Actieve profiel-/wire-/uitvoerketen en eigen fysieke vloeracceptatie. |
| R07 | Onafhankelijke zones/ketelvraag | A/B/samen/uit shadow-regellogica aanwezig | I13,I15 | Gekwalificeerde actuatoren, afgiftepad en echte begrensde ketelvraag. |
| R08 | Classic EMS en behoud Plus | Classic-/Plus-ontvangst en afzonderlijke bediende Classic-proef in beta.4 geleverd; automatische/blijvende TX uit | I12,I21,I23 | Classic-proefcommandopad + elektrische zendmodus/stopbewijs; Plus later eigen fysieke vrijgave. Modelonafhankelijke velddekking uitbreiden; profiel is nooit een leesfilter.  |
| R09 | Weersafhankelijke aanvoer | Curve-/groep-/begrenzingspolicies en centrale draft aanwezig | I15,I16 | Centrale instellingen verbinden met geselecteerde regelaar, actuele buitenbron en keteluitvoer. |
| R10 | Eigen buitenbron | Bronabstractie/binding/draft en validatie aanwezig | I16 | Normale configuratie/apply + bronkwalificatie, leeftijd, bronwisseling/uitval. |
| R11 | Internetweer via HA | HA-bronroute ontworpen; geen volledig gekwalificeerde praktijkketen | I16 | Gratis HA-weerbron, ouderdom/terugval en internetuitval bewijzen. |
| R12 | Zelflerende kamerregeling | Model-, begrenzings-, resource- en replaycode aanwezig | I19 | Verplicht in definitieve versie: per ruimte leren en gevalideerde modellen/regelparameters blijvend bewaren en gecontroleerd herstellen na herstart. Tijdelijke I-correctie blijft veilig resetbaar. Niet actief vrijgegeven; getoetste meetdata, baseline/comfortvoordeel en modelrollback blijven vereist. |
| R13 | Optimum-start | Opwarmmodel en begrensd advies/replay aanwezig | I19 | Aansluiten na M2/stabiele basis; meerdere vergelijkbare echte starts en comfortbewijs. |
| R14 | Uitlopen/curve leren | Coast- en curve-adaptatiecode/opslag/replay aanwezig | I19 | Afzonderlijke toelating en meetbaar comfort-/curvebewijs; geen leerwinstclaim. |
| R15 | Alle relevante keteldata | 69 native velddefinities geleverd op alpha21/dev27; laatste controle 26 beschikbaar, eerdere boot 27 | I12,I17,I21 | Vereiste betrouwbare velden op eigen E32 ontvangen en vergelijken; unsupported/unreliable expliciet. |
| R16 | Brander/modulatiegrafieken | Native ketelkaarten en drie historiekaarten geleverd; gerapporteerd/afgeleid gescheiden | I17,I21 | Echte CV/DHW-tijdlijn, gaten en herkomst; vlam/pompbit niet onafhankelijk betrouwbaar. |
| R17 | Historie/statistics/CSV | Read-only Recorder-CSV tot 31 dagen met native installatiekeuze/NL/EN in bètabron; eigenaarscontrole na wachttijd | I17 | Werkelijke retentie/omvang, oude deltahistorie/migratie, reset/gaten en mobiele grafiekacceptatie. |
| R18 | Weekprogramma/override | Native weekeditor/UTC-plan/apply geleverd; echte save/ACK bewezen | I07,I13 | Volledige fysieke stale/reconnect/tijd-/overrideketen; huidige 1–2 kamer-/bytebudgetten behouden. |
| R19 | Comfort/eco/away/vakantie/boost | Beta.6: normale comforteditor/wizard, kamerpresets, eindige vakantie-einddatumflow en native save/readback voorbereid; bronvorstpolicy blijft5°C | I18 | Oorspronkelijke fysieke bronkwalificatie, tijd-/uitval-/herverbindingsproef en praktijkacceptatie. |
| R20 | Aanwezigheid/geofencing | Beta.6: optionele persoon via normale inrichting; native HA-meldingen behouden oorspronkelijke trackerouderdom en verlopen na twee minuten | I18 | Werkelijke modelrapportage/uitval en fysieke bronkwalificatie; uitgebreid geofencing/P2 blijft later. |
| R21 | Raam- en deurcontacten | Beta.6: maximaal acht expliciet gekozen contacten, normale editor/wizard, instelbare reactie/ouderdom, status en gecontroleerde native save/readback voorbereid | I18 | Oorspronkelijke modelspecifieke rapportkwalificatie, fysieke openen/sluiten-/uitvalproef en eindacceptatie blijven apart; deuren worden niet automatisch gekoppeld. |
| R22 | Vorst/zomer | Seizoens-/prioriteitspolicy en bounded frost-target aanwezig | I15,I18 | Installatiegebonden fysieke bescherming bij uitval; softwaretarget is geen bewezen vorstbeveiliging. |
| R23 | Anti-pendelen/hydrauliek | Supervisor-, timing-, waterbudget- en minimumlastcode aanwezig | I15,I16,I23 | Actieve profiel/readiness/flow/pomp/naloopketen en fysieke kleinste-last/DHW-proeven. |
| R24 | Uitval HA/MQTT/sensor/E32 | Lease/session/boot/stale/owner-guards aanwezig | I11,I13,I15,I23 | Werkelijke uitvalmatrix, E32-powerloss/ketelstop, actuatorfallback en exclusieve overdracht. |
| R25 | Waarom stoken | Redencodes, kamervraag en dashboard geleverd; diagnose uitgebreid | I10,I11,I15,I17,I21,I23 | Echte opdrachtentijdlijn en gecontroleerde vraag/verzending/ketelreactie apart zichtbaar. |
| R26 | Verbruik/kosten/comfort | Metrics/export/schatlabels gedeeltelijk aanwezig | I17 | Echte gas-/warmtemeter en kostenbron/kalibratie; geen verzonnen besparing of fysiek gasvolume. |
| R27 | Meldingen/onderhoud/batterij | Diagnostics/Repairs en batterijbasis aanwezig; bèta voegt installatiegebonden klokmelding met NL/EN-herstel toe | I11,I20 | Passende meldingen en echte fout-/batterij-/geen-responsscenario’s; geen automatische ketelreset. |
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

**Actuele volgorde voor de handmatige bèta:** eerst de oorspronkelijke
ketelmeetketen en de beoordeelde handmatige Classic-proefroute/installatie;
dan één bevroren gezamenlijke kandidaat, de volledige passende releasechecks,
één gecoördineerde uitrol en onafhankelijke nacontrole. De afzonderlijke fysieke
ketelproef volgt pas bij haar eigen toelating en opdracht. Dit volgt de latere
gebruikersopdracht om eerst handmatige ketelproeven mogelijk te maken.

M2-bron-/kraanwerk blijft onderdeel van het productplan en de voorbereide bundel,
maar de fysieke M2-acceptatie is geen voorwaarde voor een uitsluitend handmatige
ketelproef waarbij automatische kamer-/kraanuitvoer geblokkeerd blijft. Een echte
M2-kraanproef gebeurt later eerst zonder ketel. De handmatige bèta krijgt hiermee
geen vrijgave voor automatische zones, onbeheerd verwarmen of zelfleren.

### Releasechecklist — eerste bèta

De onderstaande B01–B14 blijven de gezamenlijke productacceptatie bewaken.
Hun deelresultaten hebben verschillende beslismomenten:

| Beslismoment | Relevante controles | Betekenis voor deze handmatige bèta |
| --- | --- | --- |
| Proefvariant voorbereiden | B07–B09 | De echte zendroute, adres-/timing-/interfacekeuze, oorspronkelijke ketelmetingen en passende installatievoorwaarden moeten voor de betrokken handmatige proef beoordeeld zijn. Dit wordt niet vervangen door M2- of hosttests. |
| Publiceren en installeren | B01–B03, B10–B13 en passende B07–B09-voorwaarden | Alle voorbereide bron behouden, functies correct als actief of beperkt presenteren, exacte kandidaat en distributie controleren, één installatie met back-up en onafhankelijke readback. |
| Fysieke proef aftekenen | B14 en toepasselijke B07–B09-voorwaarden | Echte ontvangst/start/stop/uitval/herstel vastleggen na de afzonderlijk toegelaten proef. Publicatie of installatie tekent dit resultaat niet vooruit af. |
| Automatische kamer-/kraanregeling | B04–B06 en verdere productacceptatie | Oorspronkelijke ruimtebronnen, echte kraan/echo, hydraulische supervisor en uitvalkwalificatie afronden voordat deze functies fysieke uitvoer krijgen. Ze blijven nu open. |

Deze indeling wijzigt geen bestaande aftekening. De volledige productchecklist
mag nog open zijn terwijl een beperktere handmatige proefvariant wordt voorbereid;
haar eigen zend-, meet-, installatie- en releasevoorwaarden blijven verplicht.

- [x] B01 Alle 31 eisen, 11 fasen en 8 werkpakketten opnieuw beoordeeld; oude statusregels uit actuele lijst gehaald.
- [x] B02 Alle bekende voorbereide brononderdelen geïnventariseerd en in bètabasis behouden; geen bron-/testbestand uit hoofdwerkmap ontbreekt.
- [x] B03 Nieuwe ontvangstdiagnose/Keteltest/rapport gebouwd en getest: 18 native, 43 GUI-regressies, 3 echte Chromiumviewports met fixture-HTTP, normale E32-build.
- [ ] B04 Observer-lifecycle/native binding en originele WSDCGQ11LM-producer/HA-ontvangstdiagnose gebouwd/getest; productie-meetprofiel met echte acquisitie-/bronkwalificatie en fysieke validatie afronden. HA43 toont de interne/diagnostische bron direct met uitleg; dit kwalificeert geen meting. Geen trustvinkje of sensorwissel als omweg.
- [ ] B05 TV02-modus/native identiteit/doelcapaciteit, eindige doellevensduur en oorspronkelijke ontvangst/lifecycle geleverd; HA38-opstartherstel en HA43-ontvangerkern geleverd; de kern is niet geselecteerd door de normale fabriek. Pins/producent behouden, huidige diagnose wachtend/stale en ongekwalificeerd. Nieuwe natuurlijke ontvangst, causale zendtransactiekoppeling/doelecho, schema-eigenaarschap en profiel/readiness/fallback nog bewijzen. Fysieke proef eerst zonder ketel.
- [ ] B06 Supervisor aan bron-eigen profiel en afzonderlijk gedateerde veiligheids-/DHW-/water-/kraan-/flowfeiten gekoppeld/getest; toekomstige afgewezen feiten en klokterugloop blijven softwarematig ingetrokken. Gedeelde veiligheidscontrole blokkeert ook ontbrekende/oudere/tegenstrijdige acquisities bij zonepolicy en storingsbevestiging. Werkelijke producenten, installatieprofiel en fysieke kwalificatie blijven open. Geen generieke flowaanname.
- [ ] B07 Eindige proefpolicy en controller/HTTP/webbediening gebouwd/getest; oude/tegenstrijdige ketelrapporten bevestigen geen stop of positieve toestemming. Afronden met beoordeeld profiel en echte zender. Vaste grenzen/stopprioriteit/operatorbinding, geen automatisch hervatten.
- [ ] B08 Poll-executor, Classic-flow/nulformaat en gecontroleerde SDK-zendresultaten aangesloten/getest; monitor en HA-overdracht behouden per veld volgorde/intrekking. Installatieadressering/masker en fysieke UART-zender kwalificeren. Geen oude positieve intentie na deadline/stop/conflict/reset; geen generieke Plusroute.
- [ ] B09 Modelgebonden pre-TX-acceptatiekaart en fabrikantbronnen beoordeeld; concrete TX-interface, timing/polariteit/arbitrage, adres/masker, minimumflow/naloop, onafhankelijke stop/herstel en Tado óf E32 nog fysiek vaststellen.
- [ ] B10 HA43-bronkeuze/kaartcompatibiliteit geleverd en gecontroleerd. Overige bestaande voorbereide gebruikersfuncties en juiste onbekend-/draft-/geblokkeerdstatussen in eindkandidaat controleren; niets stilzwijgend laten verdwijnen.
- [ ] B11 Versies/bron bevriezen, volledige CI/3 boards/native/HA/C++/browser/release-/source-/licentie-/compatibiliteitschecks op die exacte kandidaat.
- [ ] B12 Openbare pakketten/bron/ELF/web/checksums en updatecatalogus onafhankelijk controleren; volledige releasenotes met open punten en herstelroute.
- [ ] B13 Verplichte updatepoort per release: één native GitHub-update via de HA-agent, verse back-up, exacte versie/bron/ELF/web na bevestigde nieuwe boot, instellingenbehoud en afzonderlijke nacontrole; zonder vastgelegd PASS geen volgende reguliere release.
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

## 8. Navigatie en bewijs

| Document / bewijs | Doel |
| --- | --- |
| [Volgende release](NEXT-RELEASE.nl.md) | Kort overzicht: geïnstalleerd, klaar voor bundel, open vervolg |
| [Masterplan](PLAN.nl.md) | Alle 31 oorspronkelijke eisen en acceptatievoorwaarden |
| [Release-inventaris](BETA1-RELEASE-INVENTARIS.json) | Alle 23 onderdelen en 468 gecontroleerde bronverwijzingen |
| [Keteltestplan](BETA1-KETELPROEF.nl.md) | Volgorde van toekomstige stop-/zend-/uitvalproeven |
| [Pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) | Nog benodigde installatiegegevens en fysieke voorwaarden |
| [Installatieverslag](INSTALLATIE-HA37-ALPHA28-20261024.nl.md) | Werkelijk geleverde alpha28/dev37, behoudsbewijs en TV02-diagnosebeperking |
| [Werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md) | Ongewijzigd vroeger uitvoeringslog; geen actuele planning |
| `out/ha-session-clock-20261024/FINAL-REVIEW.json` | Laatste softwarecheckpoint en volledige CI |
| `out/boiler-cycling-20261024/SAFE-RESULT.json` | Begrensd passief pendelonderzoek; oorzaak niet bewezen |

Lokale `out/`-dossiers worden niet integraal gepubliceerd wegens mogelijke
privégegevens. Nieuwe voortgang wordt in de actuele tabellen verwerkt; uitgebreide
uitvoeringslogs horen in het bewijsdossier of de historie, niet onder de checklist.

### Achtergrondcontrole wacht op een actieve ketelproef

De hoofdloop geeft de bestaande proefstatus door aan de updateplanner. Een
achtergrondcontrole start niet zolang de controller ontbreekt of de ketelproef
actief is; die controle kan daardoor geen keepalive van de proef blokkeren.
Uitstel verbruikt geen poging en start geen wachtrij. 45 gerichte native gevallen
en de E32-build slagen. Geen ketelproef of firmwareactie voor deze broncontrole.

### Verplicht: flashen en controleren vóór de opvolgende release

[Het updateproces](E32-UPDATE-PROCES.nl.md) en `E32-UPDATE-GATE.json` bewaren de
stand per versie. De tag-publicatiepoort controleert de SHA256-gebonden vorige
acceptatie en de exacte pending-kandidaat. Bronwerk mag doorgaan; een opvolgende
reguliere release wordt geblokkeerd bij ontbrekende/mislukte installatie of
onafhankelijke nacontrole. Alpha36 is pas na de echte installatie en afzonderlijke nacontrole geaccepteerd.

### Releasenotities voor gebruikers

Actuele E32-/HA-notities zijn op GitHub herschreven naar concrete nieuwe functies,
fixes en bijwerkinformatie, in Nederlands en Engels. Publicatietooling vereist
het formaat en bewaart het bij later opruimen. Twaalf tests en publieke
teruglezing slagen; geen softwaredownloads, tags of versies vervangen.
[Werkwijze](RELEASE-NOTES-PROCES.nl.md).

### Configuratieontvangst — live bevinding 26 oktober 2026

De alleen-lezen E32-snapshot heeft `heating_enabled=unknown`, maar een geldige
CV-temperatuur van 55 °C. Laatste Classic0x16: offset1, één payloadbyte.
De warmteproef vereist beide velden en blijft terecht geblokkeerd. Een expliciet
begrensde configuratie-uitleesroute is nu aangesloten naast de private proefzender;
zie de P0-taak in het actuele releaseplan. De kandidaat- en fysieke controles
blijven apart open. Geen EMS-TX of instellingenwijziging
uitgevoerd. Regressies bewaken gedeeltelijke antwoorden, veldspecifieke
veroudering en het onderscheid tussen leesverzoek en echte boilerrespons.
