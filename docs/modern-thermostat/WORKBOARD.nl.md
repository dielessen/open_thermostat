# OpenThermostat — actueel werkbord en releasechecklist

**Bijgewerkt: 25 oktober 2026.** Dit is de enige actuele afvinklijst. Het
[masterplan](PLAN.nl.md) bewaart alle 31 eisen en oorspronkelijke acceptatievoorwaarden.
Oude uitvoeringsnotities zijn gearchiveerd; hun oude woorden “open” en “niet
geïnstalleerd” bepalen de huidige stand niet meer.

## 1. Waar staan we?

## Voor volgende bundel — betrouwbare oorspronkelijke Zigbee-ontvangst

P0 R03/B04 en R05/B05, alleen bronmatig voorbereid voor temperatuur en TV02:

- Mislukte luisteraarregistratie trekt de eigenaar in en ruimt gedeeltelijke
  registratie op. Falen registratie én cleanup, dan blijven beide fouten zichtbaar.
- Afsluiten wacht ook bij cleanupfouten op de lopende publicatie. Parallel starten
  kan pas een nieuwe eigenaar maken nadat de oude afsluiting en cleanup slagen.
- Het publicatieslot bestaat vóór de MQTT-SDK-aanroep. Direct geneste ontvangst
  start geen tweede publicatie; direct stoppen wacht op datzelfde SDK-resultaat.

Alle 36 producenttests slagen. Voor/na-bewijs staat onder
`out/receiver-lifecycle-20261025/`, `out/receiver-shutdown-20261025/` en
`out/receiver-publication-20261025/`. Geen wachtrij/retry, productie-installatie,
bronkwalificatie, kraan-ACK of ketelopdracht. Fysieke B04/B05-acceptatie blijft open.

## Voor volgende bundel — automatische updatecontrole en dashboardmelding

De E32 controleert vanaf vijf minuten na opstarten iedere twaalf uur de bestaande
compatibele releasecatalogus. Iedere poging, ook een fout, verschuift de volgende
automatische poging; geen snelle retrylus. Geen controle tijdens pending boot,
installatie/herstart of zonder thuisnetwerk/geldige tijd. Een geslaagde controle
blijft vijf minuten in RAM beschikbaar voor herhaalde handmatige controles.
Het dashboard leest de lokale samenvatting via de bestaande statuspoll en toont
alleen numeriek nieuwere compatibele alpha-versies, met een knop naar Updates.
Geen automatische installatie of firmwareactie in deze opdracht. 44 gerichte
native gevallen, 26 Node-gevallen, dashboardbrowser en E32-compile geslaagd;
updaterbrowser apart gecontroleerd. Volledige releasegate/uitrol blijft open.

## Alpha36 — gepubliceerd; E32-installatie blijft open

Alle voorbereide catalogus-/afbeeldings-/navigatie-/loggingwijzigingen samengevoegd
op bron `7ddf341`. Compatibiliteitsfix bewaart bronvinkjes bij oude log-POST.
Main/tag alle softwarejobs PASS,803 native/2356 gerapporteerde HA-tests per Core,
onafhankelijke bron-/pakketreviews PASS;1927 pakketchecks per build en vijf
publieke downloads exact. Alle 23 onderdelen/294 refs/31 eisen behouden.

Verse controle09:41:46UTC: HA48 / 86 bestanden exact en geladen; geen herinstallatie
nodig. E32 alpha31 op dezelfde boot; geen firmwareactie. Alpha36 is gepubliceerd,
maar uploadgateNOT_READY wegens onbekende oude watchdog-/herstelroute.
[Oplevering en resterende uitrol](OPLEVERING-ALPHA36-20261025.nl.md).

## Grotere release HA48 / E32 alpha35 — gepubliceerd, HA geïnstalleerd

Beide tags staan op bron `70135db3`. Main- en tag-CI en alle negen publieke
pakketten zijn gecontroleerd. HA48 is met verse HA47-back-up van 96 en één normale
Core-herstart geïnstalleerd: alle 86 bestanden exact, SOURCE5, instellingen,
programma's, koppelingen en kaarten behouden. De bundel levert cleanup na een
gewone callbackexception, vier klokregressies en een pure Shelly-decoderbasis.
798 native en 2.356 HA-gevallen per Core slagen; de parser is nog niet geselecteerd
door de BLE-runtime. E32 alpha35 is gepubliceerd, niet geïnstalleerd; actuele
module alpha31 blijft behouden. Uploadgate en actieve bèta blijven **NOT_READY**.
Alle 23 onderdelen, 289 bronverwijzingen en 31 eisen blijven behouden.
[Installatie, aparte nacontrole en grenzen](INSTALLATIE-HA48-ALPHA35-20261025.nl.md).

## Voor volgende release — publieke ketelcatalogus

About staat direct na Settings. Alle31 BOILER-productgroepen uit de vastgelegde
EMS-ESP-bron plus officiële documentatievermeldingen staan in een catalogus van
60 selecties. Alleen compacte weergavegegevens staan in de firmware; afbeeldingen
staan onder public en worden door de browser geladen. Geen cloudafhankelijkheid
voor bediening en geen automatische driver-/regelprofielwissel. Foto's voor de
nieuwe modellen en functionele profielimport blijven open.
Vier modelafbeeldingen op vijf selecties met bronlink voorbereid; fabrikant-
afbeeldingen voor TrendLine II/GB162 en specialistproductrenders voor ProLine/
SmartLine. Ecomline Classic HRC22H nog zonder geverifieerde originele foto;
generieke tekening niet meer geselecteerd. Afbeeldingen blijven op originele host.
[Ontwerp en grenzen](KETELCATALOGUS.nl.md). Geen firmware- of HA-installatie.

## Voor volgende release — gescheiden ESP-/EMS-logbronnen

Webfilter ESP / EMS / beide, begrensde RX-framelogging buiten UART-callback en
onafhankelijk opgeslagen bronvinkjes voor dezelfde RFC5424-collector voorbereid.
REST/syslog dragen een bronlabel; afscherming en gedeelde begrensde buffers blijven
behouden. Native25, UDP-loopback/NVS en vier EN/NL-browserprofielen slagen.
Geen hardware-, collector- of firmware-installatieclaim. [Grenzen](LOGGING.nl.md).

## Historische release HA47 / E32 alpha34 — gepubliceerd en HA geïnstalleerd

Beide onveranderlijke tags staan op bron `6f21f34`. Alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketcontroles slagen. De bundel verenigt
robuuste HA-opstart/afsluiten met vier gerichte updatercheckpoints en EN/NL-uitleg.
782 native gevallen en 2.349 HA-gevallen per ondersteunde Core slagen. Alle 23
onderdelen, 286 bronverwijzingen en 31 eisen blijven behouden. Actieve bèta blijft
**NOT_READY**; bron-/kraan-/installatiekwalificatie staan afzonderlijk open.

HA dev47 is geïnstalleerd op bron `6f21f34`, met een verse HA46-back-up van
96 bestanden en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober **06:47:49 UTC** slaagt: 44 controles, alle 86 livebestanden exact
publiek pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; alpha34 is gepubliceerd, zonder firmwareactie.
[Installatie en bewijs](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).

## Historische release HA46 / E32 alpha33

Beide tags zijn gepubliceerd op bron `2d32ad3`; alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketreviews slagen. De bundel bevat
begrensde oorspronkelijke ontvangstdiagnostiek en extra herintredebewaking bij
socketoverdracht en kanaaltoelating. 773 native kerngevallen, 5 lokale socketgevallen
en 2.339 HA-gevallen per ondersteunde Core slagen. Alle 23 onderdelen en 282
bronverwijzingen blijven opgenomen. E32 alpha33 is gepubliceerd; de module blijft
op alpha31. Actieve bèta blijft **NOT_READY**.

HA dev46 is geïnstalleerd op bron `2d32ad3`, met een verse HA45-back-up van
95 payloads en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober 05:12:15 UTC slaagt: 38 controles, alle 86 livebestanden exact publiek
pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; er is geen firmwareactie uitgevoerd.
[Installatie en bewijs](INSTALLATIE-HA46-ALPHA33-20261025.nl.md).

**Historische grotere release HA45 / E32 alpha32:** bron `3f12d8b`, beide tags en
negen downloads gepubliceerd. Alle definitieve CI- en onafhankelijke bron-/pakketreviews
slagen: 767 native kerngevallen, 4 lokale socketadaptergevallen en 2.333 HA-gevallen
per ondersteunde Core. 75 native gevallen ook onder sanitizers (geen extra unieke gevallen).

**HA45 geïnstalleerd:** 85 livebestanden exact publiek pakket/Git, verse HA44-back-up
van 95 payloads en één normale Core-herstart. Afzonderlijke alleen-lezen nacontrole
25 oktober 03:09:24 UTC: alle 38 controles geslaagd, instellingen/programma's/kaarten
behouden. E32 alpha31 en dezelfde boot behouden; alpha32 is gepubliceerd maar niet
geflasht door deze opdracht. [Installatieverslag](INSTALLATIE-HA45-ALPHA32-20261025.nl.md).

**Vorige gezamenlijke release HA44 / E32 alpha31:** bron `659879e`, beide
onveranderlijke tags en negen downloads gepubliceerd. Alle drie definitieve
CI-runs slagen; 728 native firmwaretests en 2.323 HA-gevallen per ondersteunde
Core, nul fouten/skips. Onafhankelijke bron-, hoofd- en definitieve tagpakketreview
geslaagd. Alle negen publieke bestanden exact eigen tag-CI; de aanvullende
E32-distributieverschillen door buildmetadata zijn afzonderlijk gecontroleerd.

**HA44 geïnstalleerd:** 85 bestanden exact publieke ZIP/Git, verse HA43-back-up
van 94 bestanden en één normale Core-herstart. Afzonderlijke nacontrole
25 oktober 00:32:01 UTC: alle 20 checks geslaagd. Alle instellingen, programma's,
koppelingen en frontend behouden. SOURCE5 bleef behouden; de voorafgaande
horizonrollover veranderde geen gebruikersprogramma. Die nacontrole zag E32
alpha28; de nieuwere alleen-lezen waarneming van 01:50 UTC ziet alpha31. Deze
opdracht heeft geen E32-upload gestart; oude watchdogoorzaak en fysieke poorten blijven open.
[Installatieverslag](INSTALLATIE-HA44-ALPHA31-20261025.nl.md).

**Vorige HA-release dev43:** bron `97eb9a0`, gepubliceerd en geïnstalleerd op
Core 2026.10.3. Alle 84 bestanden exact publieke ZIP/Git; verse HA40-back-up van
93 bestanden en één normale Core-herstart. Zeven softwarepoorten en exacte tag-CI
geslaagd; 2281 gevallen per ondersteunde Core-versie, 1028 onafhankelijke
pakketcontroles. Vier openbare downloads bytegelijk aan beide CI-pakketten en de
beoordeelde kandidaat. Afzonderlijke nacontrole 21:17:50 UTC: alle 38 checks geslaagd.
Alle instellingen/koppelingen behouden; alleen twee eigen kamerkaarten v38→v41.
E32 alpha30-downloads/tag ongewijzigd; module blijft alpha28 met herstelblokkade.
[Installatieverslag](INSTALLATIE-HA43-20261024.nl.md).

**Vorige gezamenlijke release dev39 / alpha30:** bron `3bad1747`, beide onveranderlijke
Git-tags gepubliceerd, alle drie CI-runs geslaagd; negen openbare downloads
bytegelijk aan CI. Onafhankelijke bron-/pakketreview geslaagd (2424 pakketchecks).
HA39 geïnstalleerd met verse 93-bestandenback-up en behouden 105 registryrecords;
afzonderlijke nacontrole van 18:54 UTC geslaagd. E32 alpha30 is niet geïnstalleerd: de eerdere
alpha28-uploader-watchdogoorzaak en herstelroute blijven onbekend.
[Installatieverslag](INSTALLATIE-HA39-ALPHA30-20261024.nl.md).


| Onderdeel | Vastgestelde stand |
| --- | --- |
| Geïnstalleerde firmware | Vers waargenomen E32 `v0.1.0-e32v2-alpha.31`, bron 659879e/ELF045dfe53; uitvoerder/methode onbekend. Oudere alpha28-watchdogoorzaak blijft open; geen flash door deze opdracht |
| Geïnstalleerde HA-integratie | `0.4.0.dev48`, bron 70135db3, geladen op Core 2026.10.3; 86 bestanden exact, 105 registryrecords en koppelingen behouden |
| Geïnstalleerde bron | HA `6f21f34ff773645645c98dc2602337c648e18ffe`; E32 `659879e52b3e0e517e8dea1e28edb2d189c38c77`; 86 HA-bestanden exact |
| Softwarebasis | `out/beta-boiler-20261023`, `work/beta-boiler-20261023`; HA48 levert bewaakte async-opstart/afsluiten, cleanup na callbackexception en ontvangstdiagnostiek; alpha35-bron bevat pure Shelly-decoderbasis en updatercheckpoints naast de eerdere beveiligde aanvraag-, kanaal- en socketoverdracht. Productfabriek blijft gesloten; alle 23 voorbereide onderdelen behouden |
| Doel volgende release | Eerste actieve bèta: huidige passieve ketelkoppeling behouden en begrensde start/stop beproeven na bron-/kraan-/installatiekwalificatie |
| Nog geen bèta-vrijgave | Actieve proef-/zendketen en concrete fysieke voorwaarden ontbreken nog |
| Huidige fysieke grens | Geen bewezen echte kraan-/ketelregeling; E32-TX en actuatoruitgangen geblokkeerd |
| Laatste volledige installatiecontrole | 25 oktober 08:43:56 UTC: HA48 / 86 bestanden en verse HA47-back-up van 96 exact; E32 alpha31 op dezelfde boot, SOURCE5/instellingen behouden, uitgangen geblokkeerd. Alle 46 afzonderlijke nacontroles geslaagd |
| Beperkte ontvangstcontrole vóór uitrol | 25 oktober 05:46:49 UTC: HA46/shadow_ready, SOURCE5/digests behouden, TV02-owner met één callback/enqueue/acceptatie en stale lokale temperatuur; kamermeting ongekwalificeerd. Acht checks / nul productieacties, geen nieuwe directe E32- of volledige bronhashaudit |

[Verse alpha31-waarneming en grenzen](WAARNEMING-E32-ALPHA31-20261025.nl.md).

**Broncontrole:** de release-inventaris bewaart alle 23 voorbereide onderdelen
met 286 gecontroleerde bronverwijzingen. Het gepubliceerde bron-/licentie-/
herlinkpakket is onafhankelijk vergeleken met de exacte Git-tag en bijbehorende
ELF/webidentiteit. Bij de gezamenlijke alpha24/dev30-bundel zijn alle 82 HA-componentbestanden ook
met het E32-pakket vergeleken. De latere HA-updates dev31/dev32/dev33/dev34 zijn afzonderlijk met
hun eigen publieke pakket, Git-bron en alle live hashes gecontroleerd. Historische checkpoints en afgewezen kandidaten blijven bewaard;
geen bestaande tag of download is vervangen.

**Afvinken:** `[x]` geldt alleen voor de genoemde software-/leveringsuitkomst.
Een meegeleverd model of geslaagde simulatie bewijst geen aangesloten functie,
ketelreactie of productacceptatie. Alle oorspronkelijke fasen blijven open waar
verplichte fysieke of langere-termijnproeven ontbreken.

## GitHub-updater — nieuwe afzonderlijke herstelbeoordeling

Verse read-only controle10:10:44UTC vindt een native alpha28→31-controlepunt:
HTTP200, alle2.595.888bytes ontvangen, `boot_slot_selected`. Publiek manifest en
actuele31-bron/web passen; vier native bronbestanden zijn gelijk tussen28/31.
Dit bewijst meer dan idle/bereikbaarheid. De mislukte multipart-upload blijft
apart: reset6, taak/stack/oorzaakUNKNOWN. De native vervolgroute wordt afzonderlijk
beoordeeld; nog geen nieuwe controle/installatie/herstart uitgevoerd.
[Feiten, routes en grenzen](E32-GITHUB-UPDATE-ONDERZOEK-20261025.nl.md).

## Prioriteiten na HA48 en de gepubliceerde E32 alpha36

Alle 31 eisen, 23 brononderdelen, 11 fasen, 8 werkpakketten en 14 releasepoorten
zijn opnieuw naast de geïnstalleerde basis gelegd. B01–B03 zijn softwarematig af;
B04–B14 blijven open voor de genoemde volledige bèta-uitkomst. De geleverde
passieve bundel sluit die actieve poorten niet. Oudere losse bewijsregels zijn
historisch; de tabellen en deze volgorde bepalen nieuw werk.

| Prioriteit | Punt / koppeling | Eerstvolgende concrete uitkomst | Wat buiten software blijft |
| --- | --- | --- | --- |
| P0 | E32-upload / R28/I03 | Uploadhardening geleverd; alpha34-bron levert vier vaste verificatiecheckpoints, 782 native/40 sanitizer/24 updaterbrowsergevallen en E32-compile geslaagd. Gerichter herstelonderzoek voorbereiden | Oude reset6-oorzaak onbekend; huidige31 waargenomen zonder actor-/methodebewijs, geen blinde retry of native HTTPS-proef |
| P0 vóór actieve M2 | Incidentele CI-kamerassertie | Klokdomeinfout in de eindige kamerfixture hersteld en gepubliceerd in HA48: twee van vier epochregressies falen vóór correctie; 50 gerichte gevallen per Core slagen erna. Acht bestaande replays behouden; oude afwijking verder causaal onderzoeken | Definitieve HA43-CI en twee diagnostische native jobs slagen; oorspronkelijke oorzaak onbekend, geen fysieke vrijgave |
| P0 vóór fysieke proef | Gemeld pendelen | Onderzoek richting warmwaterbedrijf vervolgen: gebruik/bijwarmen onderscheiden; stabiele nulmeting vastleggen | Geen bewezen oorzaak; geen zendproef bij onverklaarde instabiliteit |
| P0 | TV02-opstartdiagnose, B05 | HA38-opstartherstel geleverd; verse beperkte HA46-controle 05:46 UTC toont één oorspronkelijke workeracceptatie. HA47 sluit late/cancel/dubbele opstart; 2.349 HA-gevallen per Core geslaagd. HA48 levert cleanup na callbackexception: 3 negatieve/162 gerichte en 2.356 volledige gevallen per Core gecontroleerd; geïnstalleerd | Ontvangst is nu geobserveerd maar stale; terugkerende verse ontvangst, oorspronkelijke causale echo en fysieke bron-/kraankwalificatie blijven open |
| P0 | Echte kamerbron, R03/B04/WP03 | Brongebonden acquisitie-/profielketen afmaken met echte oorspronkelijke rapporten | RTCGQ11LM device_temperature niet als kamerbron kwalificeren; geen automatische sensorwissel |
| P0 | Kraantransactie, R05/B05/WP05 | HA-workerbedrading geleverd in HA44; normale firmware-MQTT-route en product-SOURCE-fabriek verbinden, native zendtransactie aan oorspronkelijke echo koppelen | Exact geïnstalleerde converterbron ontbreekt nog in bestaande toegang; geen cache/serviceacceptatie als ACK |
| P0 | Veiligheidsproducenten, R07/R23/B06/WP06 | Softwarefences voor alle zes gedateerde feiten afgerond/getest; echte producenten en installatieprofiel aansluiten | Geen generieke flow-/pompaanname of ongekwalificeerde vrijgave |
| Geleverd | EMS-apparatenweergave, R15/R25/R29/I11/I12/I21 | Eerder geleverd op alpha28, echte GET en twee apparaten gecontroleerd; huidige versie31 apart waargenomen | Passief; ontbrekende identiteit/decoder blijft zichtbaar |
| P1 | Classic-zender en stopketen, R08/B07–B08/WP02 | Rapportvolgorde en HA-intrekking softwarematig afgerond; beoordeeld profiel en echte zend-/stopketen kwalificeren | TX/adres/masker en fysieke zender pas na B09 beoordelen |
| P1 | Installatieacceptatie, R22–R24/B09 | Bestaande acceptatiekaart concreet maken voor UART/arbitrage/Tado óf E32/minimumflow/naloop/onafhankelijke stop | Fysieke feiten blijven open; vragen bundelen voor de proef, niet iedere bronstap blokkeren |
| P1 | HTTPS-herstelbaarheid, R28/I03/WP08 | Geïnstalleerde checkpointdiagnose gebruiken bij gericht onderzocht vervolg | Vorige workerfout onbekend; app-only succes is geen workerreparatie of reden voor replay |
| P2 na M2 | Productafwerking en schaal, R01/R02/R04/R06/R09–R21/R26/R27/R30/R31 | Bestaande editor/groep/vloer/weer/metrics/historie/comfort/leerbasis gecontroleerd verbinden en toetsen | Acht zones/72u, echte grafiektijdlijn, externe meter en modelspecifieke writefuncties niet fictief aftekenen |
| Releasepoort na relevante implementatie | R28/R29/B10–B14 | Eén gezamenlijke freeze, volledige regressie, exact pakket en uitrol met back-up/readback | Geen aparte kleine release voor ieder bronpunt; fysieke proef blijft afzonderlijk |

Leren/PI/PID en blijvend bewaarde, gevalideerde parameters per ruimte blijven
verplicht voor de definitieve versie (R12); nieuwe F9/F10-stages volgen na M2.
Een ontbrekende fysieke waarneming blokkeert onafhankelijk softwarewerk niet.

### Geleverd in alpha34-bron — updateverificatie gericht onderscheiden

Vier vaste pre-operatiecheckpoints gebruiken de bestaande NVS-journal:
checksum, native imagevalidatie, flash-readback en bootselectie. Dezelfde
verificatiepoorten blijven in dezelfde volgorde verplicht. Oude schema1/164-byte
checkpoints blijven leesbaar; opslagfalen behoudt de laatste bevestigde snapshot.
De bestaande status-UI vertaalt alle vier fasen in EN/NL; lezen start geen update.

Negen nieuwe native gevallen, totaal 782 geslaagd; 40 updatergevallen ook onder
ASan/UBSan, 24 updaterbrowsergevallen en vier taal-/schermprofielen geslaagd.
E32-compile en alpha34-publicatie geslaagd. Geen firmware-installatie, blinde retry,
herstelbewijs of verklaring van de historische watchdog. HA47 is geïnstalleerd;
E32 alpha31 blijft behouden. De actuele inventaris heeft 286 bronverwijzingen
na toevoeging van de HA-opstartcorrectie hieronder.
[Betekenis en verificatie](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).

### Geleverd in HA47 — native opstart blijft bij één eigenaar

Annuleren/afsluiten tijdens programma-/Store-lezingen kan geen transport, worker,
listener of timer meer achteraf aanmaken. Dubbele start wordt geweigerd zonder
de eerste eigenaar te sluiten; een afgesloten object start niet opnieuw.
Late unsubscribe-handles worden direct opgeruimd. De optionele temperatuur-
aanmelding deelt één seconde totaalbudget; beschikbare besturing blijft intact
bij die diagnosefout. Geen nieuw abonnement, worker, route, retry of uitvoerfunctie.

Tien negatieve baselinegevallen falen vóór herstel; 139 gerichte en 2.349 volledige
HA-gevallen per Core 2026.10.2/2026.10.3 slagen. Zeven pakkettests slagen.
Dezelfde bundel behoudt de eerdere updatercheckpoints en alle 23 onderdelen,
nu 286 bronverwijzingen. Gepubliceerd in HA47 / alpha34; HA47 is met back-up/nacontrole geïnstalleerd.
[Uitwerking, oorspronkelijke fouten en bewijs](HA-OPSTART-LIFECYCLE-20261025.nl.md).

De beperkte livecontrole 05:46 UTC via de bestaande HA-agent toont oorspronkelijke
TV02-workerontvangst (1), zonder getelde drops/fouten; het bericht is stale en
geen causale kraan-ACK. Temperatuur heeft nul oorspronkelijke topics en blijft
`profile_missing`. SOURCE5/digests behouden, nul productie-/deviceacties. De diagnose
kwalificeert geen kamerbron/afgiftepad. Na de HA47-herstart is de eigenaar nieuw:
tellers nul/TV02 waiting bij 06:47 UTC; oude data wordt niet hergebruikt. Fysieke
B04–B14-poorten blijven open.

### Geleverd in HA46 / alpha33 — oorspronkelijke ontvangstdiagnostiek

De bestaande HA-diagnostiekdownload bevat vaste RAM-tellers voor temperatuur-
en TV02-verkeer: callback, plaatsing, vroege drops en workeracceptatie/-afwijzing/
-fouten. Er zijn geen topics, unieke ID's of berichtinhouden in de snapshot.
Geen nieuwe route, abonnement, worker of opslag. De bestaande wachtrijreservering
blijft behouden; counters geven geen meet-/kraankwalificatie.

223 gerichte native HA-gevallen slagen, inclusief de echte bestaande worker en
beide ontvangers. Volledige lokale suite: 2.339 gevallen per Core 2026.10.2/2026.10.3,
nul fouten of skips. HA46 / E32 alpha33 bundelt dit met de eerdere
verzendcontroles; definitieve CI en onafhankelijke pakket-/publicatiereviews slagen.
[Betekenis, begrenzing en verificatie](ORIGINAL-INGRESS-DIAGNOSTIEK.nl.md).

### Geleverd in alpha33-bron — laatste verzendcontrole

Een begrensde regressieproef op de gepubliceerde alpha32-bron bevestigt drie
callbackproblemen in de voorbereide `beforeHandoff`-grens: recursie via
beschikbaarheid, recursie via de klok en toelating van een nieuw kanaal vanuit
de beschikbaarheidscontrole. De broncorrectie bewaakt die grens afzonderlijk en
bewaakt ook beschikbaarheid en klok op hun eigen callbackgrens. Betrokken kanalen worden bij herintrede
blijvend ingetrokken. Normale controle binnen een zendcallback blijft mogelijk.

Zes kanaalgevallen en één echte lokale socketproef zijn toegevoegd; vijf
kanaalgevallen en de socketproef falen aantoonbaar vóór de correctie. Alle 773
native kerngevallen en 5 socketgevallen slagen; 77 kerngevallen ook onder
sanitizers en debugiteratoren. E32-build en publicatie alpha33 geslaagd.
E32 blijft alpha31; deze broncorrectie is niet op de module geïnstalleerd.
[Reproductie en releasegrens](M2-LAATSTE-VERZENDCONTROLE-20261025.nl.md).
Geen aanwijzing dat dit de eerdere uploader-watchdog of het pendelen verklaart.

### Geleverd in HA45 / alpha32 — oorspronkelijke FW-aanvraag en transportkanaal

De volgende bundel verbindt aanvraagvolgnummer, oorspronkelijke lokale deadline,
HA-antwoord en eenmalige opdracht. Optionele firmwarebedrading gebruikt de bestaande
MQTT-client en loop, met intrekking bij disconnect/SOURCE-wissel. De productfabriek
blijft gesloten; normale regelaarselectie, oorspronkelijke kraanecho en fysieke
kwalificatie blijven open. [Uitwerking](M2-AANVRAAG-EN-KANAAL-20261025.nl.md).
Deze samenhangende wijzigingen zijn gepubliceerd als HA45 / E32 alpha32. HA45 is
geïnstalleerd en onafhankelijk gecontroleerd; E32 blijft op alpha31. De actieve
bèta blijft NOT_READY.

### Geleverd in HA43 — B04/B05/B10

- HA-ontvangertoelating als standaard gesloten, brongebonden kern: vijfsecondenvenster op de HA-klok, exacte scope/grant/sequence en één lopende actie. Geen verlenging bij ontvangst of retry; historische serviceacceptatie blijft geen kraan-ACK. Nog niet geselecteerd door de normale native fabriek; FW-wireafzender, huidige leasebinding en causale oorspronkelijke echo blijven open.
- Kamereditor: directe EN/NL-waarschuwing voor de gekozen interne apparaattemperatuur en diagnostische entiteiten. Gewone getalwaarden kwalificeren geen bron; ontbrekende native metadata blokkeert de editor niet. Geen automatische sensorwissel.
- Frontend dev41/v41 met behoud van v38/v35-kaarten; koude upgrade, conceptkeuze en beide talen getest. Geïnstalleerd en onafhankelijk gecontroleerd; geen fysieke vrijgave.

[Uitwerking en verificatie](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

### In voorbereiding voor de grotere bèta — FW→HA-kraanberichten

**HA-workerbedrading 25 oktober:** grantaanvragen en opdrachten lopen nu door de
bestaande native worker en MQTT-verbinding. Actuele lokale sessie/config/binding,
oorspronkelijke ontvangsttijd en lease begrenzen de ontvanger. Dezelfde context
beperkt ook de adapter na wachten op zijn servicelock. De productfabriek levert
nog geen fysieke kraaneigenaar; firmware-MQTT-bedrading, echte SOURCE-kwalificatie
en causale kraanecho blijven open. Geen fysieke opdracht of bèta-vrijgave.
[Contract, tests en grenzen](M2-NATIVE-KRAANROUTE-20261025.nl.md).

**Aanvullende ontvangercontrole 25 oktober:** een reproduceerbare fout liet na
serviceacceptatie een tweede nieuw volgnummer met hetzelfde vijfseconden-grant
toe. De ontvanger verbruikt het grant nu vóór callbacks/awaits. Exacte duplicaten
blijven het oorspronkelijke resultaat delen; een volgende nieuwe opdracht vereist
een nieuw grant. Dit verandert geen serviceacceptatie in een kraan-ACK en sluit
B05 niet. Deze ontvangerfix is meegeleverd in de geïnstalleerde HA44; gerichte regressie
vóór herstel faalt, daarna slagen 146 gerelateerde gevallen en de volledige
regressie van 2.298 gevallen (2.230 tests + 68 subtests) op beide Core-versies.
De eigen tijdelijke localhost-testbroker is gestopt en verwijderd.
Bewijs: `out/large-beta-grant-20261025/` in de bronwerkboom.

De firmwaretegenhanger `ActuatorIntent` kan het bestaande HA-grant lezen en een
exacte `room_target`-envelop produceren. Dit blijft broncode in voorbereiding,
zonder productie-selectie, publisher, nieuwe brokerroute of fysieke opdracht.
De C++-bytes worden daadwerkelijk door de native HA43-ontvanger en de bestaande
Profile-C-adapter gecontroleerd; de ontvangst bewijst alleen serviceacceptatie.

Oorspronkelijke lokale aanvraag- en leasedeadlines begrenzen het venster; een
herhaald grant verlengt dat niet. Eén grant produceert maximaal één opdracht,
zonder automatische retry. Scopeverlies, waargenomen leaseverlies, klokterugloop
en intrekken tijdens autorisatie blokkeren deze eigenaar blijvend.
702 native tests en 2.287 HA-gevallen per ondersteunde Core slagen; onafhankelijke
bronreview v2 geslaagd. Zie [uitwerking en grenzen](M2-FW-HA-INTEROPERABILITEIT-20261024.nl.md).

**B05 blijft open:** de normale SOURCE-/lease-eigenaar en transportbedrading,
causale oorspronkelijke Tuya-zendtransactie/echo en fysieke kwalificatie ontbreken.
Geen nieuwe release/tag of productie-installatie alleen voor deze tussenstap.

### Verder voorbereid — bron-/leasecontrole op de transportgrens

`ActuatorDispatch` verbindt de afzender met actuele lokale bron-/kloklezingen en
de bestaande synchrone transportfunctie, inclusief controle na codering en
na overdracht. Geen normale fabrieksselectie of nieuwe MQTT-route. Vijf
reproduceerbare lease-/intrekkingsgrensfouten zijn gesloten; 728 native tests
en 32 gerichte strikte ASan/UBSan-proeven slagen; 2.297 HA-gevallen per Core
slagen. De sanitizerpoort is met een echte foutproef gecontroleerd. De nieuwe C++/HA-proeven toetsen de
gehele voorbereide keten met synthetische feiten; geen fysieke opdracht.
[Uitwerking en open grenzen](M2-SOURCE-TRANSPORT-20261025.nl.md).

De bestaande controller levert nu daarnaast een read-only actuele sessiecontext
uit eigen configuratie/SessionAdmission. Zeven nieuwe native proeven toetsen echte
handshake, deadlines, disconnect/reconnect en nul fysieke bevoegdheid.

Normale SOURCE-/profiel-/grant-/transportselectie, causale oorspronkelijke echo en fysieke
kwalificatie blijven B05-openpunten. Transportacceptatie is geen kraan-ACK;
intrekken verhindert nieuwe opdrachten maar bewijst geen fysieke sluiting.

### Geleverd in HA40 — B05/M2-kraanadapter

De kraanadapter bewaakt nu één monotone kloklevensduur per toegelaten eigenaar.
Klokterugloop/ongeldige tijd trekt de adapter blijvend in, ook bij weigering of
exception in een autorisatiecallback en na wachten of dispatch. Bij een al
verzonden opdracht blijft de fysieke uitkomst unknown; geen automatische retry.
14 nieuwe regressiegevallen, waarvan 13 vóór reparatie falen; alle 141 gerichte
tests slagen op Core 2026.10.2 en 2026.10.3; volledige tag-CI 2209 per versie.
HA40 geïnstalleerd en onafhankelijk gecontroleerd; E32 alpha28 en fysieke
blokkades blijven behouden. De normale ontvangstroute,
causale doel-echo en fysieke kwalificatie blijven open.
[Uitwerking en bewijs](M2-KRAAN-KLOK-20261024.nl.md).

### Pendelen — praktijkonderzoek blijft open

De gebruiker zag het in grafieken, kent begintijd en warmwatergebruik niet en
meldt dat het nu weer goed lijkt. De eerdere waarnemingen correleerden met
warmwaterbedrijf; dat bewijst geen oorzaak. Eerdere controles: TX/polls/proefframes
0 en uitgangen geblokkeerd. Geen reparatie of normale ketelwerking claimen.
De volledige nulmetingen en eerdere TV02-/releasecheckpoints staan in de
[historie](WORKBOARD-HISTORIE-20261024.nl.md).

### Historisch checkpoint — HA dev38 / E32 alpha29

Destijds was HA dev38 geïnstalleerd; E32 bleef alpha28 na één mislukte upload en
task-watchdogreset (code 6; taak/oorzaak onbekend). Hoogste prioriteit: offline
uploadonderzoek en onderbouwde herstelroute, zonder blinde retry.
[Actuele installatie-uitkomst](INSTALLATIE-HA38-ALPHA29-20261024.nl.md).
De bundel behoudt alle 23 voorbereide onderdelen en voegt het volgende toe:

- Oorspronkelijke temperatuurrapporten verliezen hun diagnosegeldigheid direct
  bij native model-/identiteitswijziging of uitschakeling. Terugzetten van de
  registry herstelt de oude ontvangst niet; alleen een nieuw beoordeelde eigenaar
  kan opnieuw beginnen. Gewone gebruikersnamen blijven behouden.
- Beide oorspronkelijke-rapportwaarnemers worden vanuit de bestaande native
  registrygebeurtenissen gecontroleerd. Een fout in één waarnemer verhindert de
  controle van de andere niet. Geen nieuwe listeners, taken of fysieke opdrachten.
- Metadata-wachten en niet-beschikbare kraanontvangst krijgen duidelijke EN/NL-
  meldingen. Frontendmodule en kaartidentiteit gaan naar dev38/v38 zodat de
  aangepaste pagina bij een update geladen wordt; oude waarden blijven verborgen.

Zes nieuwe native regressiegevallen; vóór reparatie faalden de drie tijdelijke
model-/uitschakelgevallen. 142 gerichte tests en vier browserregressies slagen.
Volledige controle: 2189 gevallen op elk van Core 2026.10.2 en 2026.10.3
geslaagd, zonder fouten/errors/skips.
Onafhankelijke live voorcontrole geslaagd; bronreview vond één v35-compatibiliteitsprobleem,
hersteld met alias en expliciete koude upgradeproef. Vier browserregressies
opnieuw geslaagd; onafhankelijke bron/pakketreview en software-CI geslaagd.
Publicatiejobs faalden op oude noteheaders; eerste publicatie is met gecorrigeerde
tekst en ongewijzigde CI-pakketten hersteld. Publieke downloads exact gecontroleerd.
Verse back-up en onafhankelijke nacontrole bevestigen HA38/E32 alpha28. Een nieuwe
voorcontrole voorkomt deze noteversiefout vóór publicatie.
Dit levert geen actieve bèta of Bluetooth-driver op. Bewijs:
`out/release-source-lifecycle-20261024/` en `out/combined-dev38-alpha29-20261024/`.

### Voorbereid na de release — handmatige app-upload

- [x] Strikt decimale positieve bestandsgrootte, binnen de inactieve apppartitie;
  alleen de opgegeven omvang aanbieden aan native `esp_ota_begin`.
- [x] Afgebroken, te korte, te lange of ongeautoriseerde uploads kunnen niet selecteren;
  native handles worden precies één keer vrijgegeven. Native `end` verbruikt de handle
  ook bij fouten; een nieuwe upload bevestigt geen oude pending boot.
- [x] Hoogstens één firmwarebestand per verzoek. Opstartpartitie pas kiezen in de
  laatste geautoriseerde handler na het volledig verwerkte multipart-verzoek.
- [x] Zestien nieuwe native foutgevallen en elf uitvoerbare REST-grensscenario's;
  uploadbatch 665 geslaagd; huidige totaalsuite 689. REST-proef opgenomen in bestaande CI-nativegate.
- [ ] Herstel van de watchdogfout op echte hardware bewijzen. Deze bronhardening
  is geen oorzaakverklaring en is nog niet geïnstalleerd of als nieuwe versie gepubliceerd.

Zie [offline uploadonderzoek](OTA-UPLOAD-ONDERZOEK-20261024.nl.md).

### Afgewerkt in de volgende bronbundel — B06 veiligheidsfeiten

- [x] Afgewezen toekomstige tijdstempels blijven per feit ingetrokken als de klok
  die tijd later bereikt; alleen strikt nieuwer bewijs kan dat feit vervangen.
- [x] Alle tegelijk afgewezen feiten worden apart onthouden. Reparatie van één
  veld herstelt geen ander veld en verlengt geen oorspronkelijke levensduur.
- [x] Lokale klokterugloop blijft ongeldig, ook bij gelijktijdig verkeerde eigenaar
  of een sessiestart die door de terugloop nog in de toekomst ligt.
- [x] Zonepolicy en storingsbevestiging gebruiken dezelfde veiligheidscontrole;
  toekomstige, ontbrekende, oudere of tegenstrijdige acquisities blijven ingetrokken.
- [x] Veranderde veiligheidswaarden met dezelfde meettijd kunnen geen toestemming
  herstellen; een nieuw feit heeft een nieuwe acquisitietijd nodig.
- [x] Twaalf nieuwe regressies; vijf hydraulische en zes gedeelde-policygevallen
  faalden vóór reparatie in afzonderlijke voorproeven. Definitieve suite: 677 native
  tests; E32 en ESP32-build gecontroleerd. Geen nieuwe taken/IO/allocaties.
- [ ] Werkelijke producenten, bronprofielen, hydraulische installatie en fysieke
  stop-/flow-/DHW-proeven kwalificeren. Alle fysieke uitvoer blijft geblokkeerd.

Bewijs en grenzen: [veiligheidsfeiten](VEILIGHEIDSFEITEN-20261024.nl.md).

### Afgewerkt in de volgende bronbundel — B07/B08 ketelrapporten

- [x] Vertraagde veldupdates overschrijven geen nieuwere ketelgegevens; oudere
  deeltelegrammen kunnen ontbrekende velden nog met hun oorspronkelijke leeftijd aanvullen.
- [x] Tegenstrijdige waarden op dezelfde acquisitietijd blijven ongeldig totdat
  strikt nieuwer bewijs beschikbaar is. Ontvangsttellingen blijven alle rapporten tellen.
- [x] Echte proefpolicy/poll-executor: oude uit-berichten bevestigen geen stop en
  kunnen nieuwere DHW-prioriteit niet verbergen om een positieve vraag toe te laten.
- [x] HA-cache: een andere veldgroep of hogere publicatiesequentie herstelt geen
  ingetrokken oude waarde. Geldige null-intrekking behoudt de oorspronkelijke deadline
  en trekt alleen de betrokken entiteit in, zonder andere geldige velden te verbergen.
- [x] Tien rapport-/overdrachtsregressies, twee nul-uptimecompatibiliteitstests en
  zes HA-regressies toegevoegd; negen native en zes HA-gevallen faalden vóór reparatie.
  Native totaalsuite 689 en beide firmwarebuilds geslaagd; 2195 HA-gevallen per
  ondersteunde Core-versie, zonder fouten of skips. Eigen testfixture opgeruimd.
- [x] Volledige HA/FW-controle vond een nul-uptimeregressie in de vorige aanscherping;
  echte acquisitie bij uptime nul hersteld met afzonderlijke interne markeringen.
  Gewijzigde proef-feiten krijgen een eigen nieuwe acquisitietijd.
- [ ] Beoordeeld profiel, bron-/installatiekwalificatie, echte UART en fysieke
  start/stop-/DHW-proeven afronden; geen automatische fysieke vrijgave.

Bewijs: [ketelrapportvolgorde en HA-overdracht](KETELRAPPORT-VOLGORDE-20261024.nl.md).

### Uitbreiding X01 — direct Bluetooth en zelfstandige E32

Nieuwe gebruikersopdracht: Shelly BLU TRV rechtstreeks koppelen en een lokale
E32-bedrijfsmodus toevoegen. **Aanvullend op alle bestaande functies; onderzocht,
nog niet gebouwd of geïnstalleerd.** De technische haalbaarheid steunt op de
Shelly-GATT-documentatie en onze bestaande NimBLE-stack. Uitwerking:
[directe BLE-/standalone-route](SHELLY-BLU-TRV-STANDALONE.nl.md).

Ook toegevoegd aan X01: **Shelly BLU H&T Display ZB (SBHT-103C)** en
Settings → Bluetooth-apparaten, met EN/NL-onboarding, expliciete kamertoewijzing,
beveiliging en zichtbare meetkwaliteit/bronuitval. Ook gevraagd: **Xiaomi Monitor 3
(MJWSD05MMC)** via een apart versleuteld BLE-profiel; verkrijging van de
apparaatsleutel en echte ontvangst/meetkwaliteit moeten nog worden bewezen.
[Ontwerp en acceptatie](BLUETOOTH-APPARATEN.nl.md). Eerste pure SBHT-103C-decoder voorbereid/getest: 798 native gevallen, 16 aparte sanitizergevallen en ESP32-syntaxcontrole slagen. Normale reader/onboarding/sleutels/replay-/acquisitiekwalificatie nog niet aangesloten; geen werkende Shelly-/Xiaomi-driver of fysieke vrijgave.

Volgorde: apparaatgebonden alleen-lezen BLE-basis inclusief sensor → begrensde proefkraan zonder
ketel → lokale eigenaar/programmering/tijd/opslag → integratie en uitvalproeven.
Bestaande P0-opstartdiagnose en M2-werk blijven lopen. Dezelfde regelkern en
veiligheidsvoorwaarden blijven gelden; geen tweede schrijver of langere HA-lease
als vervanging voor zelfstandigheid. Bestaande 31 eisen/23 onderdelen blijven behouden.
HA-only apparaten, Recorder en HA-automatiseringen houden hun eigen afhankelijkheid.

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
245 bronverwijzingen met hashes, status en resterende acceptatie.
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

### Releasechecklist — eerste bèta

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

## 8. Navigatie en bewijs

| Document / bewijs | Doel |
| --- | --- |
| [Volgende release](NEXT-RELEASE.nl.md) | Kort overzicht: geïnstalleerd, klaar voor bundel, open vervolg |
| [Masterplan](PLAN.nl.md) | Alle 31 oorspronkelijke eisen en acceptatievoorwaarden |
| [Release-inventaris](BETA1-RELEASE-INVENTARIS.json) | Alle 23 onderdelen en245gecontroleerde bronverwijzingen |
| [Keteltestplan](BETA1-KETELPROEF.nl.md) | Volgorde van toekomstige stop-/zend-/uitvalproeven |
| [Pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) | Nog benodigde installatiegegevens en fysieke voorwaarden |
| [Installatieverslag](INSTALLATIE-HA37-ALPHA28-20261024.nl.md) | Werkelijk geleverde alpha28/dev37, behoudsbewijs en TV02-diagnosebeperking |
| [Werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md) | Ongewijzigd vroeger uitvoeringslog; geen actuele planning |
| `out/ha-session-clock-20261024/FINAL-REVIEW.json` | Laatste softwarecheckpoint en volledige CI |
| `out/boiler-cycling-20261024/SAFE-RESULT.json` | Begrensd passief pendelonderzoek; oorzaak niet bewezen |

Lokale `out/`-dossiers worden niet integraal gepubliceerd wegens mogelijke
privégegevens. Nieuwe voortgang wordt in de actuele tabellen verwerkt; uitgebreide
uitvoeringslogs horen in het bewijsdossier of de historie, niet onder de checklist.
