# Verplicht update- en acceptatieproces per E32-release

De volgende reguliere release mag pas worden gepubliceerd als de vorige E32-
release via de normale GitHub-updater is geïnstalleerd en onafhankelijk
gecontroleerd. Een build, HTTP202, volledige uploadbalk of opgeslagen
`boot_slot_selected` afzonderlijk is geen geslaagde oplevering. Een storing blijft
open totdat herstel en nacontrole zijn bewezen; niet als “bekende beperking”
doorschuiven naar de volgende reguliere release.

De actuele machineleesbare stand staat in `E32-UPDATE-GATE.json`.
`accepted: null` betekent dat nog geen volledige acceptatie volgens dit proces
is vastgelegd, niet dat eerdere updates nooit gelukt zijn. De actuele geaccepteerde
versie is beta.1, met vastgelegd oorspronkelijk installatie- en nacontrolebewijs.
Een volgende pending-versie mag pas na haar eigen echte nacontrole worden geaccepteerd.

## Apart conceptvoorstel voor ontbrekend beta.3-bewijs

Op de afzonderlijke voorstelbranch staat een [eenmalig uitzonderingsvoorstel](E32-PUBLICATION-EXCEPTION-PROPOSAL.en.md).
Het concept is niet goedgekeurd en wijzigt geen installatieacceptatie. De
normale regel hierboven blijft van kracht. Alleen een expliciete besluittekst
van de eigenaar zou één beta.4-voorrelease kunnen toestaan, met beta.3 nog
steeds INCOMPLETE en beta.1 als laatste echte acceptatie. Het voorstel geeft
geen toestemming voor een apparaatinstallatie of ketelproef. Alle bestaande
software-/pakketcontroles blijven vereist. Een algemeen verzoek om verder te
werken geldt niet als die goedkeuring.

## Actuele opdracht: alleen beta.3-nacontrole

Gebruiker bevestigt op 26 oktober zowel de beta.3-installatie als de route:
**Controleren op updates → installeren op de E32**. Dit is een gebruikersmelding
over de native GitHub-updater. De oorspronkelijke receipts en onafhankelijke
apparaatlezing zijn hiermee nog niet gecontroleerd. De bestaande HA-agent heeft de toegelaten alleen-lezen nacontrole uitgevoerd.
Uitkomst: **INCOMPLETE**. Hij las HA Core2026.10.4 / integratie0.4.0b1 als
`shadow_ready`, maar had geen gestructureerde E32-leesroute: 0 van 2 E32-
waarnemingen en alle 13 installatiechecks onvolledig. Er zijn geen productie-
wijzigingen uitgevoerd. Het [geanonimiseerde resultaat](BETA3-POSTCHECK-20261026.json)
bewaart de hash van het onafhankelijke bewijs. De bestaande acceptatiepoort is
ongewijzigd. Hieronder staat welke nog ontbrekende gegevens nodig zijn.

1. Hergebruik de bestaande geauthenticeerde beheercontext en bewaar de originele
   antwoorden op de beveiligde bewijsplek. Lees op twee afzonderlijke momenten:

   | E32-route | Vergelijking |
   | --- | --- |
   | `GET /status/version` | `version`, `source`, `web_sha256` en `sha256`; die laatste is de **ELF-hash**, niet de firmwarebestandhash |
   | `GET /updates/status` | Dezelfde versie/bron/web, `boot_pending=false`, geen busy/workerfout of geplande/verplichte herstart; draaiende en gekozen bootpartitie |
   | `GET /status` | Stijgende uptime en de werkelijk aangeboden control-/projectstatus |
   | `GET /status/ems/telemetry` | Dezelfde `test.boot_id`, project-/proefstatus en E32-TX-/poll-/testtellers |

   Vergelijk ook de werkelijk geladen HA-versie en projectresources via de
   bestaande native HA-tools. Een terminale `checked`-status kan quiescent zijn.
   Normale ketelactiviteit onder Tado is op zichzelf geen E32-aansturing; toets de
   projectuitgangen en de eigen E32-tellers tegen de oorspronkelijke baseline.
2. Gebruik uitsluitend de **openbare** beta.3-identiteit als doel: bron
   `996587da4a05c8a9de4a25a5b8ab3d9ed4c6f99a`, firmware 2.828.000 bytes.
   De volledige firmware-/ELF-/web-/manifesthashes staan in
   [BETA4-KANDIDAAT.json](BETA4-KANDIDAAT.json) onder `predecessor_installation.expected_published_identity`.
   Controleer het openbare manifest opnieuw. Ontwikkelimages met hetzelfde
   beta.3-versielabel hebben een andere bron en vervangen dit doel niet.
3. Koppel deze verse lezingen aan de **oorspronkelijke beta.3-installatie**:
   voorcontrole en bootidentiteit, back-up met hashmanifest, werkelijk aantal
   check-/installcommando's, oorspronkelijke install-HTTP202 met ruwe body en
   het download-/image-/flash-readback-/selectieverloop. Controleer behoud van
   instellingen, programma's, bindings en SOURCE tegen die voorcontrole.
   Een opgeslagen `boot_slot_selected` alleen bewijst deze hele keten niet.
4. Lever een geanonimiseerd verslag met `PASS`, `FAIL` of `INCOMPLETE` per
   gecontroleerd onderdeel, tijdstippen, originele bronpaden en SHA256-verwijzingen.
   Ontbrekend of niet meer herstelbaar bewijs blijft expliciet onbekend. Houd
   een geslaagde actuele nacontrole apart van de volledige installatieacceptatie.
   Pas wanneer alle checks uit `scripts/verify_e32_update_gate.py::REQUIRED`
   rechtstreeks zijn onderbouwd volgt het acceptatierapport uit stap 5 hieronder.

Deze nacontrole bevat geen nieuwe installatie, updatecheck, herstart, rollback,
instellingenwijziging, MQTT-publicatie of ketel-/kraancommando. Geen nieuwe login
per lezing of sessieherstel. Bewaar geen cookies, wachtwoorden of ruwe
instellingen in Git. Bij ontbrekende toegang wordt de nacontrole als onvolledig
vastgelegd; een tweede installatie wordt niet gebruikt om oud bewijs te vervangen.

## 1. Kandidaat en vorige acceptatie

Bewaar de laatste geaccepteerde tag met het SHA256-gebonden, geanonimiseerde
acceptatierapport. Houd de complete installer-/nacontrole-/back-upreceipts op de
bestaande beveiligde bewijsplek. Geen wachtwoorden, cookies of ruwe instellingen
in Git. Geen oude waarneming voor een nieuwe release hergebruiken.

Voor een nieuwe freeze moet de vorige pending-release zijn geaccepteerd. Zet
daarna uitsluitend de nieuwe kandidaat als `pending_tag`; behoud de vorige
acceptatie en receipt. Bouw en controleer alle software, bron-/licentiepakketten,
manifesten en werkelijke publieke bestanden zoals bij de bestaande releasegates.
Publicatie blijft kandidaatstatus; fysieke installatieacceptatie volgt afzonderlijk.

Vóór publicatie, ook bij handmatige publicatie na een CI-storing:

```
python3 scripts/verify_e32_update_gate.py --candidate v0.1.0-e32v2-alpha.N
```

De E32-publicatiejob hangt af van de browsergate die deze controle verplicht
uitvoert. Een ontbrekende of onvolledige vorige acceptatie, andere pending-tag,
beschadigde receipt of teruggaande versie blokkeert de opvolger. Gewoon bronwerk
en CI-tests mogen doorgaan terwijl een fysieke acceptatie openstaat.
Deze controle valideert vastgelegd bewijs; ze voert zelf geen hardwareproef uit.

### Eerste bèta vanaf de geïnstalleerde alpha36

De bètabundel voert `scripts/verify_alpha36_beta_path.py` verplicht uit op het
werkelijke manifest en `firmware.bin`, vóór de pakketchecksums. De proef haalt
vier ongewijzigde headers uit de exact geaccepteerde alpha36-bron
`7ddf3410666d814850275433d9dddd266e5d83ba`, controleert hun vaste hashes en
compileert de oude manifest-/cataloguscode. Ontbrekende bron blokkeert verpakken;
CI haalt vooraf precies die commit op. Er wordt geen oude parser aangepast.

Alpha36 kent de bètanaam niet in de snelle index en kiest daarom de bestaande
algemene releasezoekroute. De hostproef controleert alle twaalf toegestane
posities, exact manifest-/imagehash en ingebedde versie-/bron-/webmarker,
en behoud van de oude keuzelijst bij een mislukte manifestdownload. De bèta
moet dus tussen de eerste twaalf releaseberichten staan. Het bewijs heet
`alpha36-beta-compatibility.json` en gaat mee in pakket en checksumlijst.

De fixtures hebben vier geslaagde tests, inclusief verkeerde layout en
tegenstrijdige image-identiteit. Dit is uitsluitend een lokale parser-/pakket-
controle: echte GitHub/TLS/heap/flash/boot en afzonderlijke nacontrole blijven
hieronder verplicht. Geen tussenrelease of extra installatie nodig op grond
van deze broncontrole; fysieke geschiktheid wordt niet vooruit afgetekend.

### Aanvullend: updater van de laatst geaccepteerde bèta

Nieuwe bètapakketten doorlopen ook `scripts/verify_accepted_update_path.py`.
Deze kiest de oorspronkelijke bron uit de SHA256-gebonden acceptatiereceipt in
`E32-UPDATE-GATE.json`, niet uit een gekozen ketelprofiel of de huidige headers.
De CI haalt precies die Git-commit op; ontbrekende bron of receipt blokkeert
verpakken. De eerdere vaste alpha36-proef blijft afzonderlijk behouden.

De proef compileert vijf ongewijzigde productieheaders en de oorspronkelijke
imageharness uit die geaccepteerde bron. Zij controleert de snelle tag-/release-/
manifestcatalogus, weigering van bronverschil en mislukte overdracht met behoud
van de oude keuzelijst, alle twaalf posities in de algemene zoekroute en vijf
scenario's met het echte kandidaatimage via de oorspronkelijke commitpoort.
OpenSSL controleert de hashes; HTTP en flash zijn lokale fixtures. Er worden
geen netwerk-, flash- of bootproeven op het apparaat uitgevoerd.

`accepted-predecessor-compatibility.json` gaat mee in pakket, release-assets en
beide checksumlijsten. De onafhankelijke pakketverifier controleert receipt,
doelmanifest, firmwarehash, aantallen en expliciete beperkingen. Met de Git-bron
beschikbaar controleert zij ook elke bewaarde bronhash tegen de oorspronkelijke
commit. Historische pakketten waarvan de bron deze proef nog niet bevatte blijven
met hun eigen controles verifieerbaar.

Dit is aanvullende softwarecompatibiliteit, geen fysieke updateacceptatie of
publicatievrijgave. De huidige bètavoorbereiding blijft versieveld beta.3 voeren
zolang beta.4 nog niet is bevroren; een CI-image met dat versieveld vervangt de
bestaande openbare beta.3-download niet. Na echte beta.3-acceptatie en een
beta.4-freeze moet de proef opnieuw op het definitieve beta.4-bestand slagen.

## 2. Verse voorcontrole en behoud

Alle HA-/E32-beheer via de bestaande HA-agent. Controleer onmiddellijk vooraf:
werkelijke huidige versie/bron/ELF/web, bevestigd boot-slot, geen pending boot,
lopende update of geplande herstart; thuisnetwerk, geldige tijd en toegang;
werkelijke firmwarecatalogus en exact doelmanifest. Controleer SOURCE, instellingen,
programma's, bindings en geblokkeerde fysieke uitgangen tegen de werkelijke basis.
Geen historische basis forceren. Leg heapwaarden vast zonder een verzonnen grens.

### Websessie behouden tijdens diagnose en installatie

Gebruik voor alle E32-lezingen en de installatie dezelfde reeds geauthenticeerde
browser-/beheercontext. De normale login vervangt een aanwezige eigen sessie;
een nieuwe context zonder cookie gebruikt een van de vier bootlokale slots.
Alleen het wachtwoord opnieuw aanbieden hergebruikt een slot niet. Bewaar de
cookie uitsluitend in de bestaande beveiligde beheercontext, nooit in Git,
loguitvoer, releasebewijs of een tijdelijke losse opdracht die hem direct verliest.
Dit is geen toestemming voor directe HA-API-calls; HA-beheer blijft via de
bestaande native specialist lopen.

Controleer vóór nieuwe aanmelding of de bestaande context nog toegang heeft.
Lees voor originele ketelvelden `/status/ems/telemetry`; `/status/ems` is het
oudere samengevatte statuscontract en vervangt die veldinformatie niet.
Maak onderscheid tussen HTTP429 met `session_capacity` en loginpogingen met
`try_again_later`. Bij volle slots geen herhaalde login, geen grotere limiet,
geen automatische afmelding van andere gebruikers en geen herstart om slots
vrij te maken. Laat één bestaande ingelogde browser expliciet afmelden als er
geen bruikbare beheercontext beschikbaar is. Noteer ontbrekend livebewijs als
open; gebruik historische data niet als actuele nacontrole.

Hergebruik een eigen beheersessie ook bij vervolgopdrachten. Sluit haar pas via
de bestaande CSRF-beveiligde afmeldroute af wanneer het geautoriseerde werk en
de nacontrole klaar zijn en geen proef/benodigde stopbediening daarvan afhangt.
Bewaar bij een onderbroken installatie de beveiligde context voor onderzoek;
geen nieuwe login per statuscheck en geen ongecontroleerde herhaling van writes.

Maak een verse beperkte back-up met nagelezen hashmanifest via de bestaande
methode. Bewaar de huidige image-/herstelidentiteit. Leg vast dat de inactieve
app wordt overschreven en welk herstel daadwerkelijk beschikbaar en getest is.
Native rollbackbeleid is geen garantie voor iedere stroom-/flash-/CPU-fout.
Bij tegenstrijdig of ontbrekend bewijs: geen installatie.

## 3. Eén expliciete native installatie

Indien nodig maximaal één `POST /updates/check`, daarna begrensd uitlezen van
het lokale resultaat. Geen herhaalde checks om een fout te verbergen. Leg vóór
mutatie tag, bron, firmware-/ELF-/webhash, back-up, basis en verwacht verloop vast.
Geef maximaal één `POST /updates/install` met de exacte gepubliceerde tag.
De E32 downloadt zelf `firmware.bin` en het manifest. Geen multipart `/ota`,
factory-/SPIFFS-image, gewijzigde partities, extra reboot of stille fallback.

Bewaar de oorspronkelijke HTTP-respons en het worker-/controlepuntverloop.
HTTP202 bevestigt toelating tot de worker. Download, checksum, native imagecheck,
onafhankelijke flash-readback en partitieselectie moeten aantoonbaar slagen.
Gebruik eindige polls en een vooraf vastgelegde eindtijd. Geen tweede commando
bij een onzekere respons. Houd instellingenwrites tijdens bootacceptatie bevroren.

## 4. Nieuwe boot en afzonderlijke nacontrole

De firmware herstart volgens haar bestaande beleid. Controleer de werkelijke
nieuwe boot, exacte tag/bron/ELF/web en bevestiging (`boot_pending=false`),
updater vrij, geen fout of nog geplande herstart. Observeer op twee afzonderlijke
momenten dezelfde nieuwe boot met stijgende uptime. Controleer alle bewaarde
instellingen-/programma-/binding-/SOURCE-identiteiten en alle geblokkeerde
uitgangen/TX-/poll-/testtellers. Alleen een geopende webpagina is onvoldoende.

Start vervolgens een afzonderlijke read-only nacontrole via de bestaande
HA-agent, zonder installaties of herstarts. Vergelijk onafhankelijk met het
publieke doelpakket én de voorcontrole. Bij iedere fout blijft de poort dicht;
geen blinde retry en geen gewone volgende release voordat herstel is bewezen.
Een onderzoek/herstelkandidaat is geen geaccepteerde productrelease en mag deze
regel niet stilzwijgend omzeilen.

## 5. Duurzame acceptatie

Bewaar een klein geanonimiseerd JSON-rapport in de repository, met exacte
identiteiten, oorspronkelijke admissionstatus, commandoaantallen, alle vereiste
checks en SHA256-verwijzingen naar installerreceipt, afzonderlijke nacontrole en
back-upmanifest. De volledige bronreceipts blijven beveiligd beschikbaar. Alle
checks moeten rechtstreeks uit die echte receipts worden afgeleid; onbekend
wordt niet true. Maak het rapport pas na de onafhankelijke controle.

Werk pas daarna `accepted` bij naar deze tag, receiptpad en receipt-SHA256;
zet `pending_tag` op null. Voer beide gate- en inventariscontroles uit, commit het
bewijs en werk het werkbord bij. De oude oorzaak mag alleen als gerepareerd
worden beschreven als dat oorzakelijk bewezen is. Een geslaagde native update
bewijst de native route; niet automatisch de afzonderlijke multipart-route.

## Geaccepteerde beta.1 en aanvullende bewijsregels

[Beta.1 is via de normale GitHub-route geaccepteerd](INSTALLATIE-BETA1-20261025.nl.md).
Gebruik vóór iedere mutatie de verse, geldige volledige resource-inventaris als
behoudsbaseline. Een historische afwijking in een niet-projectresource is geen
reden om oude IDs of versietokens terug te schrijven. Leg het verschil vast.
Bewaar HTTP-status en ruwe body onafhankelijk van JSON-parsing; ontbrekende
metadata wordt UNKNOWN, niet gereconstrueerd met een tweede mutatie.
Een terminale `checked`-status kan quiescent zijn: toets busy, bootpending,
reboot en workerfout in samenhang, niet uitsluitend de tekst `idle`.
Bij onveranderde numerieke HA-sensorwaarden betekent een oudere state-tijdstempel
niet vanzelf stale brondata. Vergelijk met een vers direct bronpakket en benoem
welke tijdstempel daadwerkelijk is bevestigd. Dit vervangt geen bronkwalificatie.
