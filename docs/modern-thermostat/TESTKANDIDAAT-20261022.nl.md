> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

## E32 alpha15 uitgevoerd — 2026-10-23

De E32 draait nu `v0.1.0-e32v2-alpha.15`, bron `043862c154eb314ad70f96c88062a716962c2a5e`. Het apparaat heeft de release zelf via HTTPS ontdekt, gedownload en app-only geïnstalleerd; de nieuwe boot is bevestigd. Alle zeven instellingen-/programmasnapshots zijn gelijk gebleven; SOURCE-policy/configrevision/digest en uitgeschakelde uitgangen zijn behouden. HA blijft de reeds geïnstalleerde dev20.

About, Sign out rechtsboven en Restart onder Settings staan nu live. Rechtstreekse Chromium-controle op het apparaat op 1280/390/320px PASS: exacte HTML-bron, About/credits, geen horizontale overflow, herstartbevestiging annuleren zonder opdracht. De bestaande 42 Node-tests en samengestelde browserproeven PASS. Volledige CI `39959955216` PASS, openbare downloads onafhankelijk geverifieerd: 1030 pakketcontroles/552 Gitbronbestanden plus echte ELF/embeddedweb/TLS-allocatoridentiteit PASS.

De publicatieworkflows op deze kandidaat bevatten nu `scripts/organize_releases.py`. De echte alpha15-publicatie heeft automatisch alpha15 als Actueel en alpha14 als Archief gelabeld, en de actuele downloadtabellen bijgewerkt. Catalogus idempotent; alle 22 publieke records passen in de firmwareparser. Voor toekomstige publicaties verdergaan vanaf deze schone kandidaat; de oudere GitHub-main bevat deze workflowwijzigingen nog niet. Tags en bestaande downloads niet vervangen.

Bewijs: `out/e32-alpha15-evidence-20261023/FINAL-REVIEW.json`, inclusief onafhankelijke deelcontroles en live screenshots. Dit sluit de voorbereide About/navigatie/releasebeheerwerkzaamheden af. Afzonderlijke langdurige/hardware-/verwarmingskwalificatie wordt hiermee niet geclaimd.

# Testkandidaat 22 oktober 2026

**GitHub-releases opgeruimd, 23 oktober:** alle 21 publieke releases en het ene
bestaande concept hebben consistente titels en een downloadoverzicht gekregen.
Actueel: `E32-firmware · alpha.14 · Actueel` en
`Home Assistant · 0.4.0.dev20 · Actueel`. Oudere softwareversies heten Archief;
SDK-bron-/licentiepakketten zijn afzonderlijk gelabeld. Oorspronkelijke notities
zijn byte-exact behouden in een uitklapbaar onderdeel. Alle publieke downloads,
asset-IDs/checksums/groottes, tags, publicatiedata en prerelease-/conceptstatussen
zijn behouden. Geen release verwijderd/toegevoegd en niets geïnstalleerd.
De GitHub-lijst blijft één gecombineerde lijst; de actuele downloadtabel staat
bovenaan iedere release, ook wanneer GitHub een oudere tag eerst toont.
Alle 21 werkelijke publieke API-records passen door de firmware-JSON-parser;
maximaal 22.571 bytes bij de bestaande grens van 32.768 bytes. Live metadata nacontrole en
idempotentie PASS. Bewijs/back-up: `out/release-organization-20261023/`.
In de werkmap staan `scripts/organize_releases.py` en aanpassingen aan beide
publicatieworkflows klaar om dezelfde indeling na volgende publicaties bij te
werken. Neem die mee in de volgende schone bronkandidaat; de gepubliceerde
broncommits zijn niet achteraf gewijzigd. Het bestaande concept kreeg bij
bewerken een door GitHub vernieuwde tijdelijke privé-download-URL en een
herberekende creatiedatum; bestand/asset-ID/checksum en originele tagkoppeling
zijn behouden. Publieke URLs en datums zijn ongewijzigd.

**Kamerkaart-laadfout, 23 oktober — dev20-kandidaat:** Mark ziet soms een
Lovelace Configuration error bij rechtstreeks openen van Badkamer. De werkelijk
geïnstalleerde dev19-JS wacht vóór registratie op `ha-card`. Een koude browser
zonder die ingebouwde component reproduceert daardoor een geblokkeerde editor;
het exacte consolebericht uit Marks browser is niet uitgelezen.
De editor erft van HTMLElement en registreert nu meteen. URL/kaarttype zijn
versienummer20, zodat de nieuwe module apart van gecachte dev19 kan laden.
Acht desktop/mobiel NL/EN-proeven met koud/vooraf geladen ha-card slagen, inclusief
behoud van een concept wanneer ha-card later registreert; vier bestaande
apparaatmetadataproeven slagen ook. Geen backend-, kamer-, programma- of
regelcontractwijziging. Schone bron `6edbf3722c0185229fcb457b16bd5fd0f3644ff1`,
HA-publicatie-CI39954924057 PASS; dev20 is gepubliceerd. Alle vier downloads,
79 ZIP-bestanden en 74 Git-bronbestanden onafhankelijk gecontroleerd.
Nog niet live geïnstalleerd. De hier beschikbare
HA-API kan de live bron lezen maar biedt geen integratiebestandsbeheer; de
supervisorroute geeft401. Er is hier geen passende verbonden beheertool gevonden.
Bewijs: `out/ha-room-cold-load-20261023/DIAGNOSIS.json` en `browser-dev20/BROWSER.json`.

**Actuele updaterlevering 23 oktober — alpha.14 werkelijk via GitHub geïnstalleerd:**
De E32 draait `v0.1.0-e32v2-alpha.14`, bron
`b4e2704c56bfe4e6d1649f9751992c30ca8d7d21`. Alpha.13 is eerst via de normale
app-upload geplaatst; daarna heeft het bord zelf alpha.14 via de ingebouwde
GitHub-updater gevonden, gedownload en geïnstalleerd. Ontvangst van
1.503.726/2.380.560 bytes is tussentijds uitgelezen; de nieuwe opstart is daarna
bevestigd. Versie/bron/webhash komen overeen met de publieke release.
Alle zeven vooraf/achteraf gelezen configuratie-/programmabestanden zijn gelijk;
native SOURCE-beleid, configuratierevisie en digest ook. Alle fysieke uitgangen
blijven false. Geen factorybeeld, wisactie, filesystem-upload of HA-herstart.

De seriële fout `FFFFBD70` is RSA_PUBLIC_FAILED + MPI_ALLOC_FAILED: onvoldoende
geheugen tijdens certificaatverificatie. Alleen de tijdelijke updatetaak gebruikt
nu expliciet PSRAM voor TLS; andere taken behouden de SDK-allocator. De werkelijke
ELF-allocatorpointer is gecontroleerd. Certificaat-/hostname-/download-/image-/
readbackcontroles blijven ingeschakeld. Een buffer-only tussencorrectie is niet
als voldoende oplossing geaccepteerd; alpha.12 is ongepubliceerd gebleven.
470 native tests, app/FS-build, bordverificatie en volledige CI slagen. Beide
publieke pakketten zijn onafhankelijk op 1029 pakketcontroles, 548 Git-bronfiles,
checksums en bijbehorende CI-ELF gecontroleerd. Alpha.13 CI39950927499 PASS;
alpha.14 CI39951336252 PASS in poging2. Poging1 had één HA-native klimaat-/
vraagtestfout; dezelfde ongewijzigde testbron slaagde bij de gerichte jobherhaling.
Geen gate of assertion omzeild; de eerste fout is bewaard als afzonderlijk bewijs.

Ook een verse HTTPS-controle op de geïnstalleerde alpha.14 is zonder fout
afgerond: alpha.14 en alpha.13 worden aangeboden.
Normale in-device HTTPS-ontdekking én update zijn nu fysiek aangetoond. Dit is
geen acceptatie van spanningsuitval/USB-herstel, 72h-bedrijf of verwarming.
Bewijs: `out/ota-tls-diagnostics-20261023/FINAL-REAL-UPDATE-REVIEW.json`,
`ALPHA*-PACKAGE-REVIEW.json`, `ALPHA*-SOURCE-REVIEW.json`,
`ALPHA*-CI-LINK-REVIEW.json`; privé-uitlezingen blijven in dezelfde 0700-map.

**Actuele uitvoering 23 oktober — HA-dev19 live gecontroleerd:**
HA **0.4.0.dev19** is gepubliceerd en exact geïnstalleerd. Na één Core-herstart
om **08:59:36 UTC** is de integratie gezond, met dezelfde installatie, twee
apparaten en één Badkamer. Alle 74 integratiebestanden en de werkelijk geserveerde
frontend komen overeen met de publieke bron. De beheerde kamerkaarten gebruiken
`openthermostat-room-editor-v19`. Sensor
`sensor.motion_badkamer_device_temperature` en TRV `climate.thermostaat_badkamer`
zijn behouden; SOURCE, credentials, weekprogramma en registries ook.

**Rechtstreeks opslaan van het kamerprogramma is nu werkelijk bevestigd.**
Via de normale kamerbediening is basis **21→20,5→21°C** opgeslagen en op de E32
teruggelezen. Revisies liepen normaal **1→2→3**; de zeven weekblokken bleven21°C.
De einddigest is `e8fad6fe0fca90eb6345f02c94e81ca951c0b2d1a9459e1feff9e7ff50a303ab`.
De onafhankelijke E32-uitlezing09:04UTC bevestigt revisie3, dezelfde digest en
het ongewijzigde profiel, doel21°C/weekprogramma en uitgangen uit. De volledige
kamerinstellingen zijn hersteld; geen fysieke TRV-/ketelopdrachten uitgevoerd.
De oude revisie1/journalbytes zijn terecht niet teruggezet.

Dev19 herstelt de in dev18 gevonden savefout: een actuele kamerstatus kan blijven
binnenkomen terwijl de eerdere configuratie-uitlezing ouder dan15seconden is.
Opslaan haalt dan via dezelfde bestaande worker eerst een nieuwe bevestiging op.
Zonder antwoord of bij gewijzigde credentials wordt niets opgeslagen. De grens
blijft staan; er is geen nieuwe bevoegdheid, bronkwalificatie of blinde herhaling.
Naam, basis en lokale weekblokken zijn bij actieve verbinding bewerkbaar;
apparaten/profielgrenzen wijzigen blijft apart vervolgwerk.

Schone bron `96918b2766e83eef3076fe0236d7e69b56474c59`: **1600 tests +
68 subtests**, acht browserproeven en volledige branch-CI39925932671 en
publicatie-CI39927562526 slagen. Vier openbare downloads, 79 ZIP-bestanden en
74 integratiebronnen zijn onafhankelijk gecontroleerd.
[Geteste HA-dev19-release](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev19).
De gezamenlijke HA19/alpha11-bron `ac77d40cedf85ddc685a6e9487fefd9cb6eded27`
slaagt op alle zeven verplichte jobs van CI39927688486. Dat is bronintegratie,
geen nieuwe firmwarepublicatie of upload.

**Eerstvolgend softwarewerk:** de mobiele weekplanner verder verbeteren.
Een echte Chromium-aanraakproef op390px laat zien dat een kort blok bij slepen
onbedoeld wordt ingekort: de vaste randzone is groter dan het blok. Dit is
vastgelegd als concreet vervolg; de publieke dev19-bron is niet aangepast.
De proef gebruikt scherm-/aanraakemulatie en is geen fysieke telefoonacceptatie.
Gebruikersvragen blijven gebundeld bij **Vragen voor later** in de overdracht.

**E32-alpha.11 is gepubliceerd en onafhankelijk gecontroleerd; het bord draait
nog alpha.9.** De catalogusfix scant ook later vermelde releases, in plaats van
te stoppen na de eerste twee passende vermeldingen. Bron
`7e3889bd8316ded1e91c6fefda125700241d42f4`, volledige publicatie-CI
**39916118166**, 466 native C++-proeven, 1029 publieke pakketcontroles en 544
Git-bronbestanden zijn bevestigd. Alpha.11 bevat ook de toelatingsdiagnostiek van
alpha.10; dit verandert geen fysieke rechten of commandotoelating.
De eerdere alpha.10-app-upload werd verbroken en reset de E32. Onafhankelijke
uitlezing bevestigde alpha.9 met dezelfde configuratie en uitgangen uit. De
resetoorzaak is onbekend. Mark kan **later** USB/serieel aansluiten; tot die
controle geen herhaling van de mislukte upload. Alpha.11 lost die reset niet
aantoonbaar op en is niet geïnstalleerd.

De gekozen Aqara is aanwezig en beschikbaar. Werkelijke metadata-uitlezing via
de productfunctie bevestigt **Aqara RTCGQ11LM**, diagnostische
`device_temperature`, en **Tuya TV02-Zigbee** met doeltemperatuur 5–30°C/stap
0,5, kalibratie, preset en eigen weekprogramma. Externe temperatuurinvoer of
directe klepstand staat niet in de gemelde definitie; dit is geen bewijs van
algemene onmogelijkheid. De verklaringen zijn geen fysieke kwalificatie of
bewijs van originele meetactualiteit. Geen ontbrekende of defecte sensor aannemen.

Een normale handmatige kameropdracht naar 22°C werd eerder werkelijk afgewezen;
21°C/weekprogramma bleef behouden. De precieze toelatingsreden is nog onbekend.
Geen blinde herhaling en geen conclusie dat sensor, seizoensgrens of hydrauliek
deze afwijzing veroorzaakte. Open blijven apparaten wijzigen bij actieve SOURCE,
externe kamerdoelbron (R02), raamcontact (R21), getoetste TRV-regelmethode,
uitbreiding naar acht kamers, fysieke M2/EMS- en koude/herstelproeven.
**Het volledige plan is niet afgerond en verwarming is niet vrijgegeven.**

Bewijs onder `out/plan-execution-20261023/`: `HA-DEV19-LIVE-ROOT-REVIEW.json`,
`HA-DEV17-METADATA-ROOT-REVIEW.json`, `E32-HA19-AFTER-READONLY.json`, `HA-DEV18-PUBLISHED-ROOT-REVIEW.json`,
`HA-ACTIVE-ROOM-PROGRAM-TASKFLOW.json`, `ALPHA11-PUBLISHED-ROOT-REVIEW.json`,
`E32-ALPHA10-FAILED-UPLOAD-READBACK.json` en `HA-ROOM-CONTROL-PROBE.json`.


Open gebruikersvragen worden op Marks verzoek verzameld bij [Vragen voor later](VS-CODE-OVERDRACHT.nl.md#vragen-voor-later); zelfstandig werk loopt door.

### Historisch checkpoint — alpha.9 / HA-dev14

**Actuele uitvoering 23 oktober — E32-alpha.9 gepubliceerd en geïnstalleerd:**
[E32-alpha.9](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.9)
komt uit schone bron `63da3550185881365c8153df041ca4fce5a7606e`.
Alle verplichte publicatiejobs in run39897415753 slagen. Alle vijf openbare
assets,535 bronbestanden en1025 pakketcontroles zijn onafhankelijk gecontroleerd.
Werkelijke versie, bron-/interface-/ELF-identiteit, stabiele boot, alle bestaande
instellingen en het bestaande lege programma zijn op de E32 bevestigd.

De volledige app-upload door alpha.8 geeft nu HTTP200 met precies één set
beveiligingsheaders. De nieuwe alpha.9-configuratiecontrole is ook werkelijk
beproefd: andere sessie/onjuiste controle geeft HTTP412 zonder wijziging; een
identieke save geeft HTTP201 en behoudt zelfs de volledige privé-instellingen
achter de tijdelijke controlecode. De echte nieuwe HA-client slaagt op het bord.

Native warme terugval9→8 is met identiteit/configuratiebehoud gecontroleerd.
De releasecataloguscontrole vanuit8 gaf daarna een HTTPS−1-fout; installatie
vanuit die catalogus is niet gestart en telt niet als geslaagde online proef.
De bestaande vorige-slotfunctie heeft9 teruggezet. Een aparte eindcontrole
bevestigt weer9, stabiele uptime, alle instellingen/programma en uitloggen401.
Koude, voedingsuitval- en USB-herstelacceptatie blijven open.

**HA-dev14 is gepubliceerd én live gecontroleerd.**
[De testrelease](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev14)
komt uit schone bron `6f7faf5d34252ce582e1174406b7791c6db14028`.
Volledige branchCI39902849307 en HA-publicatieCI39903157559 slagen;
1554nativeHA-tests+68subtests, geen skips. Vier openbare assets,77ZIPentries en
72bronbestanden zijn onafhankelijk tegen Git vergeleken. De specialist heeft
het exacte pakket geïnstalleerd, één Core-herstart uitgevoerd en een geladen,
gezonde dev14 bevestigd. Dezelfde entry/twee apparaten/één Badkamer, sensor,
kraan en zeven weekblokken zijn behouden; de terugvalkopie is privé bewaard.

De normale optie **E32 verbinden** is geleverd met adres/wachtwoord, HA-voortgang,
annuleren, gecontroleerde E32-instellingen en synchronisatie via de bestaande
MQTT-worker. De echte koppelproef is **nog niet bevestigd**: de MCP-beheertool kan
de asynchrone `controller_connecting`-stap niet volgen. Dit is geen E32-foutbewijs.
De bestaande flow wordt via de normale native HA-flow-API onderzocht; geen blinde
retry. Bij de laatste specialistuitlezing05:13UTC waren runtime/transport/actuatie
uit en geen bron of controlleraanmelding opgeslagen. Eventuele E32-wijzigingen
van die poging zijn nog onbekend; oude E32-readbacks zijn geen actuele proef.

De Aqara is gekoppeld en beschikbaar20°C. Discovery noemt diagnostische
`device_temperature`; nieuwe HA-tijdstempels na Core-herstart bewijzen geen
nieuwe fysieke meting. Geschiktheid als kamerthermometer/acquisitie en werkelijke
TRV-regelmethode blijven ongekwalificeerd. De kraan is beschikbaar heat/auto,
doel21°C/eigen17,9°C. Geen ontbrekende of defecte sensor aannemen.

**Vervolgbron voor dev15, nog niet gepubliceerd/geïnstalleerd:** een begrensde
uitlezing onder Geavanceerd toont alleen de door Zigbee2MQTT gemelde mogelijkheden
van de opgeslagen sensor/kranen. Eén bestaande HA-MQTT-client, twee exacte
metadatatopics,12s wachttijd, geen opdrachten/credentials of andere apparaten.
24gerichte native tests, waaronder een echte HA-client met lokale retainedbroker,
en4Chromiumproeven (desktop/mobiel,Nederlands/Engels) slagen. De volledige
HA-testset loopt. Declarations zijn geen fysieke kwalificatie. Normaal wijzigen
tijdens actieve uitvoering, externe doelbron en raamcontact blijven vervolgwerk.

**M2 en het volledige plan blijven open; geen verwarmingsvrijgave.**
Bewijs onder `out/plan-execution-20261023/`: `ALPHA9-PUBLISHED-ROOT-REVIEW.json`,
`E32-ALPHA9-HTTP-INSTALL.json`, `E32-ALPHA9-CLIENT-CONDITIONAL-POSTCHECK.json`,
`E32-ALPHA9-NATIVE-WARM-ROUNDTRIP.json`, `E32-ALPHA9-FINAL-RESTORE-POSTCHECK.json`,
`HA-ALPHA9-CHECKPOINT.json` en `HA-CONTROLLER-LINK-TASKFLOW.json`.
De parent beheert het WORKBOARD; oudere notities hieronder zijn historisch bewijs.

**Uitvoeringsupdate 23 oktober — firmwarebouw en bronlevering:**
De generieke ESP32 past weer in de bestaande OTA-partities: werkelijk beeld
1.700.880 bytes bij 1.703.936 bytes per slot. Acht uitvoerstreams gebruiken nu
`ostringstream`; de bestaande Xtensa-linkermaatregel `--size-opt` geldt uitsluitend
voor `esp32dev`. De partities, E32/S3-linkinstellingen en uitvoerblokkades zijn
behouden. Native C++456 PASS; GitHub bevestigt generiek, S3, native en browser PASS
op commit `7dddd6f` (run39878720662). De afzonderlijke E32-releasegate is nog open.

De schone E32-alpha.7-app uit dezelfde commit bouwt en doorstaat de bordcontrole:
2.373.712 bytes, SHA256
`10aff9b8d14403123cf6c0c9f1545e19ec5d423d0cf2ac27c6411c157053c911`.
Alle behouden SDK-/runtime-identiteiten zijn gelijk aan de beoordeelde set.
De huidige applicatieobjecten zijn exact herlinkt; een bewust aangepaste Arduino-
bibliotheek linkt ook en wijzigt aantoonbaar de behouden `millis()`-code.
De aangepaste proefbeelden worden niet geïnstalleerd of als firmware aangeboden.

Het officiële PlatformIO-frameworkarchief is op de gepubliceerde checksum
gecontroleerd: alle1.020 Arduino-bronbestanden en2.237 ESP32-SDK-bestanden komen
overeen. De zeven verschillen met de Arduino-Gitbron zitten dus ook exact in het
officiële pakket; hun pakketuitgever is vastgesteld, auteurs worden niet verzonnen.
Een apart bronpakket bevat12 bronarchieven en52 originele bron-/noticepayloads;
2.311 verplichte bronpaden en alle payloadchecksums zijn getoetst. Negen controles,
ook op corruptie, ontbrekende notices en onveilige archiefpaden, slagen.
De afzonderlijke bronrelease `sources-e32v2-20261023.2` is via GitHub Actions
run39879346054 gepubliceerd. De gedownloade204.384.360 bytes komen exact overeen
met SHA256 `4ffa03e6704c440763ef09a27234cd6c2a4f809fb62bece3a2a3190c8b71166c`.
Dit pakket keurt op zichzelf geen firmware goed. Volledige huidige firmwareverpakking,
notice-/bron-/herlinkvrijgave en app-only installatie blijven open. Geen E32-update,
HA-wijziging of fysieke M2-aftekening in deze stap.

Bewijs: `out/plan-execution-20261023/` met `FIRMWARE-CI-FIX-PRECHECK.json`,
`E32-CLEAN-ROOT-REVIEW.json`, `CURRENT-APPLICATION-RELINK-ROOT-REVIEW.json`,
`FRAMEWORK-OFFICIAL-SOURCE-COMPARISON.json` en `SOURCE-INPUT-VERIFY.json`.


> **23 oktober — GitHub-release en E32-updatewerk actief.** Mark heeft publicatie
> van geteste GitHub-releases en passende E32-upgrades expliciet toegestaan.
> HA-dev11 blijft de laatst gecontroleerde live versie. Afzonderlijke HA-release
> dev13 staat op tag `ha-v0.4.0.dev13`, commit
> `eeaeb1f900ef41d40074c33a6f4039774e6884ef`; publicatie-CI39874255341 PASS.
> [Dev13 is gepubliceerd](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev13).
> Werkelijke download430.092bytes, SHA256
> `8a0f80c54a0e72be7f93c4f6583a6ed587506db43dd119356bbdaa9bcaaae828`.
> Alle4 GitHubassetdigests,74 ZIPentries en69 bronbestanden onafhankelijk PASS.
> Dev11/dev12-tags zijn na CI-fouten behouden, zonder gepubliceerde assets.
> Twee ontbrekende testprobes en een gemengde monotone testklok zijn hersteld.
> Dev13: oude klokproef faalt/nieuwe slaagt;87 gerichte en1442 volledige HA-tests
> PASS,2 lokale optionele MQTT-proeven SKIP,68 subtests PASS. GitHub heeft alle
> proeven uitgevoerd:1512 JUnitgevallen inclusief subtests,0 fouten/skip.
> Geen nieuwe HA-installatie/herstart.
> Nieuwe schone E32-bron `69f92eda89d2cd149ddcea7b6608d85108e4e02c` bouwt PASS:
> app2.375.360 bytes, layout/inert defaults PASS. Updatezoeker passeert HA-tags;
> 21 native tests PASS. Dezelfde490 SDK- en272 runtimeleden als eerder bewijs.
> Deze kandidaat vervangt de eerdere build niet stilzwijgend; nieuw bron- en
> herlinkpakket blijft nodig vóór uitrol. Geen firmware geplaatst; notice- en
> leveringsreview en fysieke M2 staan open. C++-testregistratie apart hersteld:
> alle70 bestaande tests behouden en gezamenlijk eenmaal gelinkt/geslaagd;
> volledige schone PlatformIO-native suite456 PASS.
> Bewijs: `out/github-release-prep-20261023/TASKFLOW.json`. Volgende actie is de
> E32-review en update-/M2-keten. De generieke ESP32-build overschrijdt zijn
> bestaande1.703.936byte-slot; Os-proef zonder resultaat, oorspronkelijke flags
> bytegelijk hersteld. Dit blijft een firmware-CI-punt, geen reden om partities
> te vergroten of bestaande blokkerende pakketcontroles te passeren.
> Softwarevervolgbranch `review/e32-catalog-native-tests-20261023`, commit
> `93b267d4c8b5900097ff5c1e3c53aa7b6f735a20`; geen nieuwe firmwaretag.


> **Vervolg 23 oktober:** HA dev11 blijft de laatst gecontroleerde liveversie.
> E32-bronbewijs uitgebreid: alle onderzochte SDK-objecten (357), runtimeobjecten
> (269) en startup-objecten (3) exact gereproduceerd en onafhankelijk getoetst.
> Ook de bestaande CA-bundel is aan oorspronkelijke bron/notices gekoppeld en
> exact opnieuw gegenereerd. Zie [actueel bronbewijs](SDK-BRONBEWIJS-20261023.nl.md).
> Schone E32-kandidaat met app/FS-build en bordcontrole PASS; volledige ELF exact
> herlinkt en gewijzigde-libraryproef PASS. Bron-/herlinkreviewpakket met 512
> gecontroleerde checksums beschikbaar; notice-/leveringsreview en M2 blijven open.
> Geen firmware geplaatst. Gekozen sensor bestaat: model RTCGQ11LM, apparaattemperatuur; TRV
> TV02-Zigbee. Converter-/meetactualiteitskwalificatie blijft afzonderlijk open.

Deze kandidaat richt zich op de volledige lokale softwareketen en de voorbereiding
van de badkamerproef. Temperatuursensoren en TRVs worden via de native
HA-formulieren gekozen. Er staan geen woningentiteiten in de productbron.

## Actuele koers: direct de normale inrichting

Mark bevestigt dat de E32 **los van de ketel staat** en dat we geen productie
draaien. We bouwen en configureren meteen de normale productroute: één installatie,
centrale instellingen en ruimtes via de wizard. Er hoeft geen aparte schaduw-
configuratie te worden gemaakt en later opnieuw als productie te worden ingericht.

De bestaande OpenThermostat-testentries mogen na een gerichte back-up worden
opgeschoond, samengevoegd of vervangen door één schone inrichting. Bruikbare
HA-apparaten blijven gekoppeld; overige HA-integraties en historie blijven buiten
de opruimscope. Niet verbonden of nog niet toegepast wordt een status in dezelfde
installatie. De juiste verbinding/profielcontrole wordt in het product begeleid.

De actuele liveversie en de technische nacontrole staan hieronder per stap. Interne
protocolnamen blijven voor compatibiliteit bestaan; het gewone toevoegmenu biedt
alleen ruimtes en de centrale instellingen staan op één plaats.
De oude shadow-instructies verderop zijn historische technische naslag. Ketel
aansluiten en fysieke ketelregeling testen volgen later; dat verhindert de gewone
inrichting van de ontkoppelde E32 nu niet.

## Historisch: HA 0.4.0.dev11 live en gecontroleerd

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
lege actuatorissues en `authorizes_actuation=false`.26 native nacontroles en11
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

## Kraancontrole in het complete kamerscherm — HA 0.4.0.dev9

**Tussenkandidaat dev9; live laatst bevestigd dev7.** Dev9 bevat de
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

## Tussenkandidaat — HA 0.4.0.dev8, niet geïnstalleerd

**Live laatst bevestigd: dev7. Bron en pakket: dev8.** Mark bevestigt dat het
OpenClaw-onderhoud nog bewust loopt. Dat onderhoud blijft ongemoeid; de
specialistroute voor HA-beheer en de E32-login wacht daarop.

Dev8 vergelijkt de opgeslagen kamergrenzen, basistemperatuur en lokale weekdoelen
met de door HA gemelde kraangrenzen en temperatuurstap. De configuratiestatus
benoemt bereik/stap en eventuele aandachtspunten; `room/get` bevat de afzonderlijke
verschillen, waaronder afronding en doelen buiten het kraanbereik. De controle
gebruikt dezelfde conversie als de bestaande begrensde actuatoradapter. Ongeldige
of ontbrekende metadata blijven onbekend. Een bestaande externe programmabinding
wordt expliciet als niet gecontroleerd benoemd en krijgt geen algemene groenstatus.
Er worden geen kamerinstellingen, apparaatmodi of doelen gewijzigd.

Dit ondervangt in de software de eerder uitgelezen discrepantie tussen kamergrenzen
5–35 °C en kraangrenzen 5–30 °C. **Dit is geen nieuwe live-uitlezing en geen bewijs
van de huidige opgeslagen waarden.** De gekozen sensor is gekoppeld; in deze stap
is geen nieuwe sensorstatus of rapportversheid gemeten. Geen conclusie dat de sensor
ontbreekt of defect is. Metadata-compatibiliteit is geen fysieke kraankwalificatie.
Het grafische kamerscherm en de weekplanner zijn in deze stap ongewijzigd.

Bewijs: **1.380 native tests PASS, 2 optionele brokerproeven SKIP**; 34 release-
auditgevallen PASS en 6 subtests PASS. Native tests dekken °C/°F, afronding,
onbruikbare metadata, meerdere kranen, externe programma's en de werkelijke
configuratiestatus/room-readback zonder servicecommando's of opslagwijzigingen.
Onafhankelijke pakketcontrole: alle 69 bronhashes gelijk aan werkboom/policy,
73 pakketchecksums correct; precies 8 bronbestanden gewijzigd en 61 gelijk aan dev7.
De dev7 ZIP blijft bytegelijk. `git diff --check` PASS.

Onveranderlijk pakket: `OpenThermostat-HA-0.4.0.dev8.zip`, 424.473 bytes;
SHA256 `9a70436fc72d5be704078964e9af0e35ad22e64ace7dea5abfba8d7ec7e973d9`.
Bronidentiteit `sha256:5eb91787a3ae149acb23a821ac27f27009e2b3ecb63b89fd3f1ed049236f8f28`.
Bewijs: `out/plan-resume-m2-20261022/{NATIVE-ALL.xml,RELEASE-AUDIT.log,DOWNLOAD.json,ROOT-REVIEW.json,TASKFLOW.json}`.
**Geen live installatie/herstart, firmwareflash of fysieke vrijgave in deze stap.**

Mark heeft expliciet **“E32-invoer staat klaar”** bevestigd. Die toestemming blijft
voor hetzelfde eenmalige bestand en één normale login gelden; niet opnieuw vragen.
Beide beheerproeven stopten vóór de specialist/provider begon. Het bestand is
niet gelezen, loginpogingen: **0**. Publieke GET-controle op 22 oktober 22:27:24 CEST:
E32 `/login` HTTP200 en `/status` HTTP401. Het bord is bereikbaar, de status is
terecht afgeschermd. Er is geen gateway-/auth-/serviceconfiguratie aangepast.

**Vervolg na onderhoud:** hervat de bestaande specialistopdracht met controle op
reeds aanwezige sessie/receipts vóór een eventuele eerste login. Lees de actuele
E32-identiteit en contracten en de HA-kamer/kraan/sensor uit. Installeer dev8 pas
via de bestaande back-up/configcheck/herstart/nacontrole. Bewijs daarna de
HA→E32→ACK-keten en de afzonderlijke sensor-/kraanproef zonder ketel. Het hele
plan en M2 blijven open; het canonieke WORKBOARD wordt door zijn eigenaar bijgewerkt.

## Eén kamerprogramma — HA 0.4.0.dev7

Mark laat de alternatieve Schedule-helper weg. De toevoegwizard, het gewone
kamerformulier en het grafische kamerscherm bieden uitsluitend de ingebouwde
weekplanner. Geavanceerd bevat temperatuurgrenzen en maximale meetleeftijd;
geen Schedule-entity of programmabronselectie. Sensor, radiatorkranen, basisdoel
en bloktemperaturen blijven samen met één gezamenlijke opslag bewerkbaar.

Een bestaande externe binding wordt bij gewone bewerking behouden en expliciet
benoemd. Er worden geen HA-helpers, programma's of historie verwijderd. Het
beheerde dashboard gebruikt een afzonderlijke room-editorcomponent: een al
geregistreerde dev5/dev6-weekplanner kan deze niet meer overnemen.

Bewijs: **1.359 native PASS, 2 optionele brokerproeven SKIP**, waaronder behoud
van een bestaande externe binding bij normale kamerbewerking. 34 release-audit-
gevallen PASS, met 6 subtests. Zes Chromium-proeven: desktop/mobiel, vers en na
laden van de echte dev5/dev6-assets, geen helperkeuze, apparaatveld en week samen
in één save, bestaande binding behouden. Deze browserproeven gebruiken een
expliciet synthetisch admin-WS-model; de transacties zijn apart met echte native
HA getest. Bronwissel en geïnjecteerde eind-renamefout herstellen correct.

Onveranderlijk pakket `OpenThermostat-HA-0.4.0.dev7.zip`, 69 bronbestanden;
SHA256 `53afe9da5e6bca10cce40d3e0705b5d81622aef0ff148ca39ba3ce800eee630a`.
Bronidentiteit `sha256:c81d1b272799a92f276fc0aa332855d066c3f399e28afe4cd2d7a75ab58a953e`.
**Live geïnstalleerd; technische nacontrole PASS op 22 oktober.** Verse native
private back-up PASS, dezelfde 1 entry/2 apparaten/36 entiteiten. Configuratiecheck
PASS, één native Core-herstart; verse Core-start 21:54:14 CEST en dev7 gezond/loaded.
Twaalf native nacontroles PASS: alle 69 bronhashes, volledige configuratie, opties,
subentries, registryrecords en reparaties behouden; tien overige dashboardbestanden
en 79 andere integratie-ID's ongewijzigd. Publieke JS-module HTTP200, 31.124 bytes,
exacte pakketchecksum. Onafhankelijke rootvergelijking: 15 controles PASS, uitsluitend
negen verwachte bronbestanden gewijzigd en zestig gelijk aan dev6. De dev6 ZIP
is ongewijzigd. Aanvullende native room/dashboard-WS-uitlezing is niet verzameld;
de beheerverbinding ging na de geslaagde bestands-/modulenacontrole tijdelijk in
offline onderhoud. Geen Gateway-/auth-/configreparatie uitgevoerd.

Ververs de HA-browser na deze update; gebruik de ingebouwde weekplanner.
Er is geen kamerprogramma, apparaatkoppeling, HA-helper of historie verwijderd.
Bewijs: `out/ha-single-program-20261022`, waaronder `ROOT-LIVE-REVIEW.json` en
`FILESYSTEM-POSTCHECK.json`. Dev6 en de gerichte private back-up blijven beschikbaar
voor herstel. Het volledige plan en de fysieke proeven blijven open.

## Eén grafisch kamerscherm — HA 0.4.0.dev6

Mark verduidelijkt: alleen **Ruimte toevoegen** krijgt een wizard. Bestaande
ruimtes aanpassen gaat direct naar instellingen. De dev6-bron heeft één volledig
grafisch kamerscherm: naam, verwarmingstype, temperatuursensor, radiatorkranen,
basistemperatuur, gesloten Geavanceerd en weekplanner bij elkaar. Eén concept,
één knop **Alles opslaan**. Geen verplichte blokdialogen of controlescherm.

Open het eigen dashboard → **Ruimtes instellen** (kalendericoon), of de instelknop
van je kamer op het ruimteoverzicht. Bij meerdere kamers kun je binnen hetzelfde
scherm wisselen; niet-opgeslagen wijzigingen vragen eerst bevestiging. De native
HA-aanpasknop biedt één formulier met een directe link naar het volledige scherm,
zonder de toevoegwizard opnieuw te doorlopen.

Klik of sleep op een leeg tijdvak om een blok te tekenen. Selecteer het blok
en pas **Van**, **Tot** en **Temperatuur** direct in hetzelfde scherm aan.
Verslepen en verlengen werken met de aanwijzer; de toevoegknop, blokkeuzelijst
en precieze invoervelden bieden toetsenbord-/mobielbediening. Dagen kopiëren en
blokken verwijderen blijven conceptwijzigingen. Buiten blokken geldt het basisdoel.
Een helper als programmabron wordt benoemd; bewust wisselen vereist bevestiging.

Opslag gebruikt dezelfde native parent-/kamersubentrytransactie en validators.
De hele kamer en haar radiatorbindingen worden atomair opgeslagen; centrale
instellingen, andere kamers en bestaande identiteiten blijven behouden. Actieve
regeling, overlap, bronconflicten, ongeldige grenzen en gewijzigde registries/
eigenaren worden vóór opslag geweigerd. Laatste-awaitcontrole en token voorkomen
overschrijven vanuit een verouderd scherm. Bij een verloren antwoord blijft
het concept behouden en is blind opnieuw opslaan geblokkeerd.

Bewijs: **1358 native gevallen PASS, 2 optionele brokergevallen SKIP**, 34 release-
auditgevallen PASS. De echte gepinde HA-frontend desktop en mobiel bewijst tekenen,
verlengen, inline temperatuur, kopiëren én daarna kamerinstellingen wijzigen,
één gezamenlijke opslag, exact heropenen, annuleren, invoerbehoud en conflicten.
Extra browserproeven: toetsenbord, 24:00-roundtrip, blokkeuzelijst, verloren
antwoord en correcte helperweergave. Geen fysieke apparaatcommando's.

Onveranderlijk pakket `OpenThermostat-HA-0.4.0.dev6.zip`, **69 bronbestanden**;
SHA256 `521485588c8227619010ba38a1a36e9f56b5c353197c53d8bd59c7cf0e74b7e6`.
Bronidentiteit `sha256:91d6ecb499e0ef40fa07fa65e4f6bec8c0205968f329b4619175dfd50285da3d`.
**Bron en browser bewezen; gerichte live back-up PASS om 17:47 CEST.** De oude
68 bronbestanden zijn exact bewaard, samen met configuratie, registry, reparaties
en het eigen dashboard; twee apparaten en 36 entiteiten, bindings en IDs zijn
vastgelegd. Tien andere dashboardhashes en 79 andere integratie-entry-ID's staan
in de nulmeting. Het bronwissel-/herstelpad slaagt ook bij een geïnjecteerde
laatste-renamefout.

**Live geïnstalleerd; onafhankelijke nacontrole PASS op 22 oktober om 19:07 CEST.**
De hervatte native uitlezing van 18:45 bevestigde dev5 en geen eerdere
installatiestappen. Overdracht via de bestaande projectpreview is geslaagd:
volledige ZIP-checksum en alle 69 uitgepakte bronbestanden exact. De tijdelijke
download is opgeruimd. Native configuratiecontrole PASS, gevolgd door **één
Core-herstart**. Verse Core-start 18:57:38 CEST; native health bevestigt gezond,
ondersteund en dezelfde integratie-entry **geladen als 0.4.0.dev6**.

De afzonderlijke bestandsnacontrole en onafhankelijke rootvergelijking bevestigen:
alle 69 bronhashes, volledige kamer-/centrale data, options, subentries, beide
apparaat- en alle 36 entiteitsrecords en reparaties exact gelijk aan de back-up.
Alle tien overige dashboardbestanden zijn ongewijzigd en de 79 andere integratie-
entry-ID's zijn behouden. De oorspronkelijke telfilterfout is als bewijs bewaard;
de gecorrigeerde controle sluit alleen het actieve projectdashboard uit en slaagt.

Native `room/get` bewijst **supported=true, editable=true** voor Badkamer, met
`sensor.motion_badkamer_device_temperature` en `climate.thermostaat_badkamer`.
Basis 21 °C, grenzen 5–35 °C, maximale sensorleeftijd 120 s en het lege lokale
weekprogramma zijn behouden. Native dashboarduitlezing bewijst één volledig
instelscherm op `week`, de directe `room-aec404da`-subview en de instelknop.
Bestaande viewpaden blijven bestaan. De nieuwe publieke JS-module levert HTTP 200,
31.770 bytes en de exacte pakketchecksum. Tijdens nacontroles is niets opgeslagen
of naar apparaten/MQTT gestuurd; bestaande actuatietoestanden zijn behouden.

Open **OpenThermostat → Ruimtes instellen** of de instelknop bij Badkamer.
Ververs de browser met **Ctrl+F5** als de vorige module nog in het geopende scherm
staat. De integratie, kamer of apparaten hoeven niet opnieuw toegevoegd te worden.

Eerdere provider-/opstart- en overdrachtsfouten blijven historisch bewijs.
Actuele status en rollback: `out/ha-room-editor-20261022/DEPLOYMENT-RESULT.json`,
`ROOT-LIVE-REVIEW.json` en de afzonderlijke native receipts. De gerichte private
back-up en oude dev5-bron blijven op HA bewaard voor herstel.
De E32-toegang en fysieke kamer-/ketelproeven staan hier los van.

## Grafisch weekprogramma — HA 0.4.0.dev5 (vorige uitvoering)

De geïnstalleerde versie biedt in het eigen **OpenThermostat-dashboard → Weekprogramma**
(kalendericoon) een grafisch overzicht per kamer. Elke dag heeft een tijdlijn en
blokken met **temperatuur én begin/einde**. Open een blok, pas de temperatuur aan,
bewaar het blok in je concept en kies **Weekprogramma opslaan**. Dagen kopiëren,
blokken toevoegen/verwijderen en annuleren zijn gewone knoppen. Buiten blokken
staat het basisdoel; middernacht is expliciet. Geleerd voorverwarmen wordt als
nog niet beschikbaar benoemd.

Dit is dezelfde `week_program` in de bestaande kamersubentry. De native
kamereditor blijft dezelfde gegevens lezen/bewerken; er is geen tweede Store of
scheduler. Een gekoppelde Schedule-helper wordt benoemd en niet als lege lokale
week weergegeven of overschreven. De editor heeft dezelfde beheerdersrechten en
runtimevoorwaarden als de bestaande configuratieroute. Opslaan is geen ACK.

De native configuratieherlaad behoudt nu het bestaande managed dashboardobject,
zodat een open concept of opslagmelding niet verdwijnt. Runtime en transport
worden normaal opnieuw geladen; alleen de presentatie blijft bestaan. Bij een
mislukte overdracht wordt het achtergebleven dashboard opgeruimd. Een tweede
editor kan een nieuwere configuratie niet overschrijven: het concept blijft
zichtbaar en opnieuw opslaan vereist eerst expliciet herladen.

Bronchecks: **1340 native HA-gevallen PASS, 2 optionele brokergevallen SKIP**;
34 release-auditgevallen PASS. De echte gepinde HA-frontend desktop/mobiel toetst
bewerken, kopiëren, verwijderen, annuleren, overlap met invoerbehoud, één opslag-
request, exact heropenen en twee gelijktijdige editors. Aanvullende browserproeven:
toetsenbord/Escape/focus, 24:00 en gesimuleerd verloren antwoord; geen blinde retry.
Andere gebruikersdashboards worden niet aangepast.

Onveranderlijk pakket `OpenThermostat-HA-0.4.0.dev5.zip`, **68 bronbestanden**;
SHA256 `5f03eb6f526ae9d1bcb191f85bcb360cd933db89225a619722d2e823b0bd279b`.
Bronidentiteit `sha256:6838982316be6bb21410b322a9a190f55895ac34aea140a45b60f491899bc8e4`.
**Geïnstalleerd; functionele live nacontrole PASS om 16:58 CEST.** De gerichte
bron-/config-/registryback-up staat onder
`.openthermostat-backups/20261022-week-planner-dev5-preflight`. Alle 68 bestanden
staan exact op HA, de native configuratiecheck is geldig en na één native
herstart is Core gezond met dev5 geladen. Parentdata, opties, centrale instellingen,
beide subentries en alle gegevens van dezelfde twee apparaten en 36 entiteiten
zijn exact vergeleken met de back-up. De gekoppelde sensor/TRV zijn behouden.
De eigen dashboardroute heeft de weekkaart; tien andere dashboardbestanden zijn
ongewijzigd. De echte week-API leest Badkamer met basis 21 °C, grenzen 5–35 °C en
een lege bewerkbare lokale week terug. De aangeboden frontendmodule is bytegelijk
aan het pakket. Er is live geen week opgeslagen of apparaat bediend.

**Afzonderlijke onzekerheid in de strikte omgevingscontrole:** de bestaande
metricshistoriereparatie staat nu op genegeerd. Om 16:19 was deze nog niet
genegeerd; de dev5-back-up om 16:45 bevatte geen reparatiestatus. Moment, oorzaak
en actor zijn daarom niet vastgesteld. Het wijzigingsjournal registreert geen
reparatieactie en de metricshandlers zijn bytegelijk aan dev4. De oorspronkelijke
strikte FAIL blijft bewaard naast de afzonderlijke functionele PASS; volledig
behoud van deze reparatiestatus wordt niet geclaimd. De melding is niet opnieuw
gewijzigd. Neem bij een volgende installatie ook reparaties in de nulmeting op.
Bewijs/rollback: `out/ha-week-planner-20261022`.

Verse M2-voorcontrole van **16:25 CEST**: de gekoppelde Aqara-sensor rapporteert
**20 °C**, HA-rapportleeftijd ongeveer 66 seconden. De kraan is geïdentificeerd
als **Tuya TV02-Zigbee**, met doel 21 °C en lokale preset auto. Dit is uitleesbewijs,
geen open/dicht-/manualmode-/echo- of uitvalkwalificatie. Er is geen kraanbediening
uitgevoerd. De E32-connectiviteitsentiteit is aan, maar SOURCE ontbreekt en
runtime/actuatie staan uit. Een passieve vijfsecondenlezing van `device_status`
ontving geen bericht; dat bewijst geen afwezigheid of exacte huidige firmware.
De gekoppelde sensor ontbreekt dus niet. Open blijven de werkelijke producer-
kwalificatie, firmware-identiteit/toegang, HA→E32→ACK en de kraanproef.

**E32-adres door Mark bevestigd:** `http://192.168.1.206/`. Alleen-lezen
bordcontrole om **17:06 CEST**: `/` verwijst naar `/login`, de inlogpagina werkt,
`/status` geeft HTTP 401. Er was geen ingelogde bordsessie beschikbaar. Daardoor
zijn actuele firmwareversie/commit, identiteit tegenover `ib-therm`, SOURCE,
sessie/ACK en outputlocks niet vastgesteld; een firmware-updatebehoefte is niet
bewezen. Geen loginpoging, instellingenwijziging of uitvoeractie in die controle.
Mark heeft daarna toegang voor de beheerverbinding laten regelen. In de
gecontroleerde credentialproviders is geen E32-authreferentie beschikbaar;
er is geen login geprobeerd. Een privémap voor eenmalige invoer via de bestaande
Samba-configmap is voorbereid: `.openthermostat-access`. De verbinding wacht op
de gewone E32-webinloggegevens in `e32-192-168-1-206.once.json` en Marks expliciete
gereedmelding. Geen inloggegevens in chat, broncode of bewijs. Na een geslaagde
sessieoverdracht wordt het invoerbestand gericht verwijderd. De status is nog
steeds niet geauthenticeerd uitgelezen.
De apparaatgerichte vervolgstappen staan in
[Badkamer: koppeling en proef](BADKAMER-KOPPELING-EN-PROEF-20261022.nl.md).

## Nieuwe groepsindeling — HA 0.4.0.dev4

De nieuwe bron groepeert de centrale E32 automatisch onder **Installatie en ketel**,
met Badkamer als aparte ruimte. Hierdoor verdwijnt de standaardgroep voor apparaten
zonder subentry. De lege presentatie-subentry bevat geen instellingen: de bestaande
parententry blijft de enige eigenaar van de centrale configuratie. Ruimte toevoegen
blijft de gewone toevoegkeuze. Geen HAcore-, CSS- of frontendpatch.

Bronverificatie: **1321 native HA-tests PASS, 2 optionele brokergevallen SKIP** en
34 release-auditgevallen PASS. De echte HA 2026.10.2-frontend is op desktop en
mobiel gecontroleerd: nieuwe groepskop, aparte ruimte, geen standaardrestgroep of
horizontale overflow. Registry-migratie is met echte Core-events beproefd, inclusief
behoud van IDs en herstel bij een geweigerde apparaatverplaatsing.

Onveranderlijk pakket: `OpenThermostat-HA-0.4.0.dev4.zip`, 66 bronbestanden;
SHA256 `55e0c02a6d7cfc6953d40d002ccd8dbce04bffc306705938e9bd760e86837641`.
Bronidentiteit: `sha256:59d2905c5fca23cb2a0ac0860883b1dc4b0b9894c70e6b6289c806c1081e11b3`.
Het dev3-pakket is ongewijzigd bewaard. De gerichte bron-/config-/registryback-up
staat op HA onder `.openthermostat-backups/20261022-installation-heading-dev4-preflight`.

**Geïnstalleerd en live gecontroleerd om 16:19 CEST.** Alle 66 bronbestanden
staan exact op HA; de native configuratiecheck is geldig. Na één native herstart
is Core gezond en dev4 geladen. De ene bestaande installatie, twee apparaten en
36 entiteiten zijn behouden. Alle 35 centrale entiteiten en hetzelfde E32-apparaat
horen nu bij de nieuwe presentatiegroep; er zijn geen ongegroepeerde projectapparaten.
Badkamer behoudt dezelfde subentry, sensor/TRV en instellingen. Parentdata, opties,
centrale configuratie en badkamerdata zijn JSON-exact vergeleken met de back-up.
Device-/entiteits-ID's, gebruikersnamen en uitgeschakelde entiteiten zijn behouden;
de verwachte registrywijziging is uitsluitend de groepskoppeling en de normale
wijzigingsdatum. De onafhankelijke rootvergelijking van de verse native registry-
readback bevestigt dit. Runtime en actuatie blijven uit, SOURCE blijft geen bron.

De eerste beheersessie eindigde na broninstallatie/configcheck op haar tijdslimiet;
een verse uitlezing bevestigde daarna dat de herstart nog niet was uitgevoerd.
De herstart is één keer uitgevoerd. Een tweede sessie eindigde na terugkeer van HA;
de laatste sessie deed uitsluitend de resterende vergelijking, zonder nieuwe
installatie of herstart. De bestaande metricshistoriereparatie is niet genegeerd.
Deze presentatiewijziging sluit geen controller-, actuator-, ketel- of firmwareacceptatie af.
Bewijs en rollback: `out/ha-installation-heading-20261022`.

## Actuele uitvoering — 22 oktober, update dev3

**0.4.0.dev3 is geïnstalleerd**, met geldige native configuratiecheck en één
herstart. Verse specialistcontrole **14:51–14:53 CEST**: HA 2026.10.2 gezond,
beide bestaande entries geladen op opslagversie 3; alle 65 bronbestanden exact
tegen het onveranderlijke pakket gecontroleerd. Badkamer behoudt bij deze
migratie zijn subentry-ID en volledige gegevens. De centrale verwarmingsgegevens
zijn JSON-exact naar dezelfde parententry verplaatst, zonder los heatingchild.
Runtime en kameractuatie blijven uit.

De strikte legacy-gelijkheidscontrole meldde één verschil: het ontbrekende veld
`integration_mode` kreeg de bestaande default `legacy`. De bronmigratie doet dit
expliciet. Alle overige legacy-data, opties en subentries zijn gelijk; het
originele FAIL-bewijs is behouden en de semantische beoordeling apart vastgelegd.

| Onderdeel | Aantoonbare stand |
| --- | --- |
| Normale HA-inrichting | Eén installatieroute, centrale instellingen en uitsluitend ruimtes in het toevoegmenu. Geen gewone legacy/shadow- of adapter-ID-keuze. |
| Radiatorruimtes | Begeleide naam/type → sensor/kranen → temperatuur/week → samenvatting. Aanpassen/verwijderen vanuit dezelfde configuratie; Geavanceerd gesloten en hulp per instelling. |
| Weekprogramma | Bestaande native blokeditor met bloktemperatuur en nieuw kopiëren van dagen. Het fraaie interactieve weekraster uit het ontwerp is nog geen geleverde producteditor. |
| Vloer/combinatie | Als nog niet beschikbaar aangeduid; wordt geweigerd in deze radiatorroute. Geen fictieve apparaatondersteuning. |
| Bestaande projectentries | Na back-up via native flows samengebracht naar één geladen normale `ib-therm`-installatie met Badkamer. Centrale waarden en badkamerbindingen exact vergeleken; oude testentries verwijderd. |
| E32-dashboard | Nieuwe bron toont beschikbare ketelmetingen apart van berekende kamervraag/uitvoerstatus, met begrensde lokale trends. Bronbrowser desktop/mobiel gecontroleerd; nog niet geflasht. [Bronoplevering](E32-DASHBOARD-20261022.nl.md). |
| Fysieke kamer-/ketelproeven | Temperatuursensor is gekoppeld en rapporteert; zie de sensorcheck hieronder. Open: controller-/toepassingsketen HA→E32→ACK, actuatorvalidatie en echte kraan zonder ketel. Representatieve kamermeting en ketelstop/uitval afzonderlijk beproeven. |
| Firmware-release | Normale app/FS-builds op deze gewijzigde bron geslaagd; distributie blijft geblokkeerd op SDK-bron-/licentieclosure. |

De gerichte ontwikkelherinrichting is daarna uitgevoerd via de native HA-flows.
Verse lezing **15:16 CEST** bevestigt één geladen installatie met Badkamer; de volledige
vergelijking van **15:12 CEST** bevestigt dezelfde sensor/TRV, basistemperatuur
21 °C, kamergrenzen 5–35 °C en maximale meetleeftijd 120 seconden. Centrale curve, grenzen
20–45 °C en weerbeleid zijn exact behouden. Deze expliciet toegestane reset heeft
nieuwe interne installatie-/ruimte-/groep-/actuator-ID's; de oude→nieuwe mapping
staat in het bewijs. Geen enkele device-/ketelservice of extra herstart uitgevoerd. HA is gezond en
de native configuratiecheck is opnieuw geldig. Alleen Ruimte toevoegen wordt als
gewone toevoegroute aangeboden.

Alle andere 79 integratie-ID's zijn behouden. Bij twee andere entries verschillen
in de verse vergelijking uitsluitend authenticatie-/verloopvelden; de oorzaak
is niet vastgesteld.
Daarom claimen we geen totale data-identiteit van alle HA-integraties. Die waarden
zijn niet uitgelezen of teruggezet. Het wijzigingsjournal bevat uitsluitend native
OpenThermostat-configuratieflows; sensor/TRV-registry en hun actuele staat/attributen
zijn exact behouden. 28 verwijderde registryrecords waren uitsluitend van de oude
projectentries. Recorderhistorie is niet verwijderd. Bewijs en onafhankelijke
bron-/journalcontrole: `out/product-ha-20261022/live-consolidation`.

Het pakket staat als `OpenThermostat-HA-0.4.0.dev3.zip` in de projectroot;
SHA256 `033a5b9d476c59b73728f9996533669a85b04931239e75ad11aae96e5daea2ad`.
Het eerdere dev2-pakket blijft bewaard. De 65 bronbestanden hebben identiteit
`sha256:3ecb804814650e0106730dfbe0eabcc580c7e19151949128a05b8481018794d6`.

Verificatie: **1316 native HA-tests geslaagd, 2 optionele brokerscenario's
overslagen**; daarnaast 34 release-auditgevallen met 6 subtests. De echte gepinde
HA 2026.10.2-frontend is op desktop en mobiel gebruikt voor centrale instellingen,
ruimte toevoegen, bestaande koppelingen aanpassen, annuleren en één opslagactie.
Een echte geïsoleerde MQTT-proef bevestigt passieve telemetrie zonder
legacy-kamerimport of apparaatcommando. Bewijs: `out/product-ha-20261022`.

Op HA staat een beschermde volledige bron-/projectconfiguratie-/registryback-up
onder `.openthermostat-backups/20261022-product-dev3-preflight`. Terug naar dev2
vereist ook de bijpassende projectconfiguratie; alleen bron terugzetten na de
opslagversie 3-migratie is onvoldoende. Livebeheer gebeurt via de bestaande
HA-specialist en bestaande File editor/native beheerroute.

Mark heeft inmiddels gevraagd **door te werken zonder na iedere fase op een
antwoord te wachten**. Bekende vervolgstappen worden uitgevoerd; wezenlijke
ontbrekende fysieke informatie wordt aan het eind apart gemeld. Dit is geen
voltooiing van alle 31 eisen. M2/F6, de volledige E32-opschoning, gebruikerstests,
vloerprofielen en overige productfasen blijven hun eigen acceptatie houden.

### Apparaatindeling gecontroleerd — 15:26 CEST

Na Marks screenshot opnieuw actueel gecontroleerd: **één installatie, twee
apparaten en 36 entiteiten**. De oude tweede koppeling en oude Woonkamer-kamer
zijn afwezig; geen losse entity-/devicerestanten gevonden. De huidige apparaten
hebben nu duidelijke gebruikersnamen:

- **E32-regelaar — ketel en diagnose:** 35 centrale ketel-/apparaatentiteiten.
- **Badkamer — thermostaat:** 1 kamerclimate-entiteit.

Op dit controlemoment stond de centrale E32 nog onder de standaard HA-groepskop
“Devices that don't belong to a sub-entry”. Deze presentatie wordt in dev4
vervangen door een native groep **Installatie en ketel**; zie de dev4-update bovenaan. Het is geen foutmelding en geen extra koppeling. Centrale gegevens worden
niet onder uitsluitend Badkamer geplaatst. Sommige bestaande technische
`woonkamer_…`-entity-ID's zijn deze centrale metingen; ze zijn geen overgebleven
Woonkamer-regeling. Hun identiteit en historie zijn behouden.

In deze nacontrole zijn alleen de twee apparaatnamen aangepast, na een gerichte
privéback-up. Alle 36 entiteitsregistraties, device-ID's en sensor/TRV-identiteiten
zijn gelijk gebleven. Alle 65 bronhashes exact, HA gezond en configuratiecheck
opnieuw geldig; runtime en actuatie uit. Geen herinstallatie, herstart,
apparaatcommando of extra verwijderactie nodig. Bewijs:
`out/ha-cleanup-20261022/ROOT-POSTCHECK.json` en `CLEANUP-CHECK.json`.

### Correctie sensorstatus — verse controle 15:29 CEST

Badkamer heeft al een werkende gekoppelde temperatuurbron:
`sensor.motion_badkamer_device_temperature`, van **Aqara Motion badkamer** via
Zigbee2MQTT/MQTT. De opgeslagen kamerbinding en de actuele HA-entiteit zijn beide
gelezen. Om **15:29:19 CEST** was de sensor beschikbaar en ingeschakeld, met
**19 °C**. De laatste HA-rapportage was **15:29:05**, ongeveer 14 seconden eerder;
de begrensde historie toont een verandering van 20 naar 19 °C.

De eerdere uitspraak dat nog een werkende sensor moest worden gekoppeld was
onjuist. Mark had deze alternatieve bron al voor de tijdelijke test aangewezen.
Er is geen nieuwe sensor nodig om die afgesproken testinrichting te maken.
De entitynaam `device_temperature` is op zichzelf geen bewijs van ongeschiktheid.
Representativiteit/plaatsing en het echte fysieke meetmoment worden afzonderlijk
beproefd; een HA-rapporttijd alleen bewijst dat laatste niet.

De open stap is de controller-/toepassingsketen: `transport_ready=false`, runtime
en actuatie uit. Dat is geen ontbrekende sensor. Deze controle heeft niets aan
HA, apparaten of configuratie gewijzigd. Bewijs:
`out/bathroom-sensor-check-20261022/SENSOR-CHECK.json` en `ROOT-CHECK.json`.
Bij volgende voortgangsclaims eerst de actuele opgeslagen binding en entiteit
controleren; oude defectinformatie of een entitynaam mag geen hardwaregebrek
suggereren.

### Repair over oude verbruikstellers — controle 15:35–15:46 CEST

De zichtbare repair **Legacy metric history needs review** hoort bij de huidige
installatie, niet uitsluitend bij een verwijderde oude koppeling. De huidige
issue is om 15:10:55 aangemaakt na ontvangst van numerieke oude EMS-tellervelden.
Twee oudere issues bij de verwijderde entry zijn al genegeerd; de huidige issue
is niet genegeerd. Er zijn geen oude onversioneerde metriekidentiteiten meer aan
de huidige entry gekoppeld, maar dat bewijst geen gecorrigeerde Recorderhistorie.

Alle zeven nieuwe verbruiks-/brander-/watertellers staan bij de lezing van 15:35
op `unknown`, met `metrics_schema=null` en `protocol_scope=unverified`. De bron
laat oude numerieke tellervelden niet onder de nieuwe v2-identiteiten als
gecorrigeerde statistieken door. De melding zelf schakelt de regeling niet uit;
de badkamersensor en de nog open controller-/actuatorketen zijn aparte punten.
Een vijfsecondencontrole van exact `ib-therm/ems_metrics` via de bestaande native
`mqtt.dump`-service leverde om 15:45:55–15:46:02 geen berichten op. Dit bewijst niet
dat de producer ontbreekt of nog steeds een bepaald formaat verstuurt.
De actuele volledige payload, retainstatus en fysieke firmwareversie zijn daarom
niet vastgesteld; de oude alpha6-notitie wordt niet als verse firmwarelezing gebruikt.

Dit blijft een open punt bij de ketel-/verbruiksgegevens. Eerst een actuele,
inhoudelijk geldige tellerdefinitie en producer vaststellen; daarna oude
statistiekdefinities en eventuele afnemers beoordelen. De oude waarden alleen
hernoemen of er een schemamarker aan toevoegen is geen correctie. Een geldige
v2-ontvangst verwijdert deze historische reviewmelding niet automatisch.
Er is bij deze melding nu geen instelling die Mark moet aanpassen.

Geen repair genegeerd/verwijderd, geen Recorder-/statistiekreset, geen
apparaatcommando, publicatie of firmwarewijziging uitgevoerd. De native capture
gebruikte dezelfde bestaande HA-MQTT-client, één topic en één serviceaanroep.
Het al bestaande diagnostiekbestand is vooraf privé bewaard en naderhand met
dezelfde bytes/SHA256 en herstelbare metadata teruggezet; alleen ctime wijzigde
zoals bij een bestandsverplaatsing gebruikelijk. Bewijs:
`out/metrics-repair-review-20261022/ROOT-REVIEW.json`, `REPAIR-READBACK.json`
en `PAYLOAD-CHECK.json`. Dit is afronding van de begrensde diagnose, geen opgelost
verbruiks-/firmware- of F5-acceptatiepunt.

## Historische dev2-oplevering

De onderstaande secties beschrijven oudere ontwikkelstappen. Gebruik voor de
huidige inrichting de normale dev3-route hierboven; technische shadowstappen
zijn uitsluitend historische naslag.

## Eenvoudige kamerinstelling — nieuwe HA-kandidaat

Op verzoek van Mark is de handmatige kamer-/groepsinrichting vervangen door een
nieuwe gewone route: **Radiatorkamer instellen** / **Set up a radiator room**.
Deze HA-kandidaat heeft versie **0.4.0.dev2** en is op verzoek van Mark
**automatisch geïnstalleerd op zijn HA**. Afzonderlijke verse nacontrole op
**22 oktober 2026, 13:03 CEST**: HA2026.10.2 healthy/supported, beide integraties
geladen en manifest0.4.0.dev2. De volgende badkamerinrichting stemmen we samen af.

Het pakket staat in de projectroot als `OpenThermostat-HA-0.4.0.dev2.zip`.
Het bevat alleen de HA-integratie, met installatie-/rollbackinstructies en exacte
bestandshashes; geen firmware. Het eerdere `OpenThermostat-HA.zip` blijft de oude
download en is niet stilzwijgend vervangen.

De nieuwe route laat je een nieuwe of bestaande kamer kiezen en vraagt daarna
alleen naam, temperatuursensor, radiatorkranen, gewenste temperatuur en optioneel
een weekprogramma. Bij een bestaande kamer zijn de huidige waarden voorgeselecteerd.
De radiatorgroep wordt automatisch aangemaakt of hergebruikt. De samenvatting
heeft één knop **Kamer opslaan**; annuleren bewaart niets. Grenzen en een alternatieve
Schedule-helper staan in een dichtgeklapte sectie **Geavanceerd**. De bestaande
technische kamer- en verwarmingseditors blijven bereikbaar als geavanceerde opties.

De gezamenlijke opslagactie is uitsluitend geverifieerd voor HA **2026.10.2**;
deze wizard weigert andere versies. Bestaande geavanceerde comfort-, externe
setpoint-, vloer- of meerdere-groepenconfiguraties worden niet automatisch
omgebouwd. Bestaande kameridentiteiten, programma's, grenzen en centrale
instellingen blijven behouden. Opslaan wijzigt SOURCE, runtime en apparaten niet.

Bewijs: **254 tests geslaagd**, inclusief 20 gerichte wizardgevallen, bestaande
native HA/C++-regressies en 34 release-auditgevallen. De werkelijke gepinde
HA-frontend is op desktop en mobiel gebruikt voor annuleren en opslaan; de eigen
testinstallatie gebruikt uitsluitend synthetische apparaten. Bron-/pakketbewijs
staat in `out/simple-room-20261022`. Dit is geen fysieke M2/F6-acceptatie.

De installatie gebruikte de bestaande File editor-beheerroute. De oude
integratiemap is volledig en byte-exact geback-upt:99bestanden. Alle62nieuwe
bronbestanden zijn na de vervanging onafhankelijk tegen het pakket gecontroleerd.
De native HA-configuratiecheck was geldig; HA is precies eenmaal herstart.
Beide entries hebben dezelfde opgeslagen opties, kameridentiteiten en subentrylijsten.
Bij de installatiecontrole van 13:03 CEST stonden runtime en badkameractuatie uit;
er was één kamer en geen verwarmingssubentry. De wizard was toen beschikbaar en
had nog niets opgeslagen. De latere lezing van 13:23 CEST hierboven toont wél één
centrale verwarmingssubentry; haar volledige groepsinhoud is niet uitgelezen.

Herstelkopieën op HA: `.openthermostat-backups/20261022-dev2/open_thermostat`
en `.openthermostat-backups/20261022-dev2/live-before-swap`, naast
`custom_components` onder de HA-configuratiemap. Een volledige HA-back-upaanvraag
faalde op het ontbrekende standaard back-upwachtwoord; daarvoor is niets aan
credentials aangepast. De bewezen bronmapkopieën waren het herstelpunt voor deze
afgebakende update. Installatiebewijs: `out/ha-install-dev2-20261022`.

De bestaande metrics-repairrecords zijn behouden. In de laatste leescontrole is
hun `dismissed_version` veranderd van `null` naar `2026.10.2`; de oorzaak is niet
vastgesteld. De installatie heeft geen repair- of historiereset uitgevoerd.

## Historische badkamercontrole vóór de bronupdate

Live gewijzigd en daarna opnieuw gecontroleerd op **22 oktober 2026,
11:31 CEST**, in HA **2026.10.2**:

- Alleen de bestaande testintegratie is van `legacy` naar `v1_shadow` gezet.
  Runtime blijft uit; aan de oorspronkelijke `ib-therm` zijn geen writes gedaan.
- Het bewaarde badkamerformulier is nu bereikbaar. Daarin staan de tijdelijke
  motion-temperatuursensor en de badkamer-TRV al geselecteerd. De oorspronkelijke
  losse badkamersensor was defect. Mark koos de motion-temperatuur als tijdelijke
  testbron. De latere sensorcheck van 15:29 hierboven bevestigt een werkende
  koppeling; uit de entitynaam alleen volgt geen afkeur als kamermeting.
- Basisdoel **21 °C**, kamergrenzen **5–35 °C**, kameridentiteit en bestaande
  programmagegevens zijn niet gewijzigd. Het formulier biedt `Save bindings
  (keep local program if present)`; de volledige weekinhoud is niet uitgelezen.
- De radiatorgroep is **nog niet aangemaakt**. De beschikbare HA-beheertool kan
  hetzelfde meerstapsformulier niet aantoonbaar hervatten met de teruggegeven
  groeps-ID. Daarom blijft de badkamer voorlopig `climate_trv` met de bestaande
  directe TRV-koppeling; er is geen halve omschakeling naar een graphkamer gedaan.
- Voor de nieuwe planroute blijven stap 2 en 3 hieronder open: de badkamer moet
  `graph_only_draft` worden met lege directe TRV-selectie, en de TRV hoort daarna
  in één radiatorgroep. Laat runtime uit totdat die inrichting en de afzonderlijke
  SOURCE-/E32-controles voltooid zijn. Een opgeslagen concept is geen
  teruggelezen E32-configuratie en bedient geen kraan of ketel.

Bij deze vroegere controle meldde het integratiemanifest `0.4.0.dev1`; de toen
geïnstalleerde bronhash was niet vastgesteld. Een volledige HA-herstart was voor
alleen de moduswijziging niet nodig; de latere bronupdate hierboven is wel herstart.
Lokaal bewijs van deze controles staat in `out/ha-bathroom-setup-20261022`.
De laatste lezing bevestigt beide integraties geladen en Supervisor
healthy/supported; de begrensde integratielog bevat geen vermeldingen.
De OpenThermostat-kamer blijft `unavailable` met runtime uit. De bestaande TRV
is beschikbaar en is alleen uitgelezen, niet bediend. Een volledige vergelijking
met de oorspronkelijke `ib-therm` is niet mogelijk: daarvan ontbreekt een
vóórsnapshot. De oude historie-/metric-reparatiemeldingen zijn niet gewist.

Open in HA **Instellingen → Apparaten en diensten → OpenThermostat** de bestaande
testintegratie **OpenThermostat shadow (opth_bath_shadow_20261020)**. Opnieuw
toevoegen is niet nodig. Gebruik voor deze proef niet de oorspronkelijke
`ib-therm`-integratie.

De ongeldige combinatie achter `room_mode_actuator_conflict` is apart gecontroleerd
in de echte geïsoleerde HA-frontend: een climate-TRV-kamer vereist een directe
TRV-selectie; een graphkamer vereist juist een lege directe selectie. De actuele
bron toont daar een leesbare uitleg en slaat de ongeldige wijziging niet op.
Waarom Marks eerdere scherm uitsluitend de foutcode toonde, is niet vastgesteld.

Softwarebewijs:249verschillende gerichte native HA/C++-gevallen met sanitizers,
34release-auditgevallen, echte gepinde HA2026.10.2-frontend desktop/mobiel en een
geïsoleerde echte MQTT-keten met één exacte1888Bopslagtransactie. De normale
E32-app/FS op de eerste bron `63be9bc` zijn succesvol gebouwd en teruggelezen;
de finale exacte bron-/imagehashes staan in `out/release-candidate-20261022`.
De firmwarepakketcontrole blijft geblokkeerd op SDKbron-/licentieclosure.

## Technische proefroute van dev2 — naslag, niet de eerstvolgende gebruikersactie

Deze oudere stappen beschrijven de technische voorbereiding van de shadowproef.
Door de nieuwe gebruikersafspraken is eerst de bouwfase bovenaan aan de beurt;
Mark hoeft deze technische reeks nu niet zelf af te werken. De wizard ondersteunt
eenvoudige radiatorkamers; bestaande geavanceerde configuraties vragen behoud of
een gecontroleerde migratie.

1. De HA-update is geïnstalleerd. Ververs de HA-pagina en open de bestaande
   testintegratie. Voeg haar niet opnieuw toe. Laat runtime uit.
2. Open **Radiatorkamer instellen** en kies de bestaande **Badkamer**.
   Controleer naam, tijdelijke sensor, radiatorkraan en gewenste temperatuur.
   Behoud het bestaande programma of bewerk de lokale tijdblokken. Gebruik
   per kamer precies één programmabron.
3. Controleer de samenvatting en kies **Kamer opslaan**. De gekoppelde
   radiatorgroep wordt automatisch opgeslagen. Er is geen handmatige graphmodus,
   directe-TRV-clear of reeks aanvoer-/groepsformulieren nodig voor deze route.
4. Open **Independent local shadow profile (runtime off)**. Vul de echte E32-ID
   in en kies **Use the complete-week shadow contract**. Controleer kamer,
   resourcekoppeling, grenzen en fingerprint. Het oude achtpuntsprofiel blijft
   een afzonderlijke keuze en vereist twee kamers.
5. De bijbehorende lokale E32-descriptor en brokerinstellingen moeten apart
   overeenkomen. Deze HA-review installeert of herstart de E32 niet.
6. Pas na die voorbereiding: schakel shadow-runtime in; kies prepare, lees het
   volledige plan en bevestig apply eenmaal. Alleen **exact current plan readback
   verified** bewijst dat het plan is teruggelezen. Een ACK alleen is onvoldoende.
7. Controleer annuleren, gewijzigd doel, dubbele bevestiging, herladen en offline.
   Een concept mag niet zelfstandig worden toegepast; onbekende configuratie
   of onzekere verzending moet zichtbaar blokkeren.

Voor deze softwarekandidaat blijven fysieke uitgangen uitgeschakeld. Een echte
kraan bewegen hoort bij de afzonderlijke M2-acceptatie en vereist een bewezen
meet-/actuatorprofiel; het kiezen van een climate-entiteit is dat bewijs niet.
De Tado blijft de werkende verwarmingsregelaar zolang de commissioning openstaat.

## Grenzen voor oplevering

De pakketbouwer controleert SDK-notices/bronclosure vóór hij een firmwarepakket
maakt. De bekende closureblokkade wordt niet omzeild door een handmatige zip of
andere naam voor hetzelfde firmwarepakket. Lokale buildresultaten zijn wel
inspecteerbaar bewijs, geen vrijgegeven download of flashopdracht.

E32-stack/peakheap/NVS-GC, echte HTTP/NVS/update/recovery, continue gekwalificeerde
metingen en veiligheidsproducers, fysieke kraan, ketelstop bij uitval en72uurproef
blijven afzonderlijk te bewijzen. Zie ook
[de ketelstopvoorproef](KETELSTOP-VOORPROEF.nl.md) en het canonieke werkbord.

Lokale bewijsmap: `out/release-candidate-20261022`. Deze bevat ook strikt lokale
testaccounts en browserstate; deel of archiveer die map nooit integraal.
Alleen expliciet geselecteerde bron-/bewijsbestanden mogen naar een overdracht.

Rollback vóór installatie: alleen deze bronwijzigingen terugnemen. Geen HA-journal,
NVS, kamerdata, modellen, Recorder of historie wissen. Na een werkelijk toegepast
nieuw contract vraagt teruggaan compatibele bron en expliciete migratie.
