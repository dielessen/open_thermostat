# HA dev46 / E32 alpha33 — gezamenlijke release en HA-uitrol

25 oktober 2026. Beide onveranderlijke releases zijn gepubliceerd op bron
`2d32ad3c84f8439540a04e2d87fdd5a8265f3670`.

HA dev46 is geïnstalleerd op bron `2d32ad3`, met een verse HA45-back-up van
95 payloads en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober 05:12:15 UTC slaagt: 38 controles, alle 86 livebestanden exact publiek
pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; er is geen firmwareactie uitgevoerd.
De nieuwe ontvangstdiagnostiek is via de bestaande HA-download live teruggelezen.

## Wat deze bundel toevoegt

- Oorspronkelijke temperatuur-/TV02-ontvangst wordt zichtbaar via vaste tellers in
  de bestaande HA-diagnostiekdownload. Vroege drops zijn onderscheiden van
  workeracceptatie, afwijzing en observerfouten. Er is geen extra abonnement,
  worker, route of blijvende opslag.
- De tellers zijn begrensd, niet per apparaat en bevatten geen topics, unieke
  ID's, berichtinhoud, exceptiontekst, clocks of grants. Een kopie lezen verandert
  geen ontvangsttijd, meetprofiel of regelbevoegdheid. Een nieuwe eigenaar na
  herstart begint opnieuw; nul betekent niet automatisch geen brokerverkeer.
- De laatste socketcontrole en beschikbaarheids-/klokcallbacks bewaken herintrede
  ook vanuit gewone kanaaltoelating. Alle betrokken kanaaleigenaren trekken
  blijvend in; de echte lokale socketproef bevestigt dat de ongeldige herintrede
  geen byte overdraagt. Normale overdracht in de bestaande callback blijft mogelijk.
- Alle 23 voorbereide onderdelen, 282 bronverwijzingen en 31 eisen blijven behouden.
  Gewone v1-bediening blijft compatibel met de waargenomen E32 alpha31. De
  voorbereide kanaalroute vereist minimaal HA45; de nieuwe diagnosetellers HA46.

[Ontvangstdiagnostiek, betekenis en EN/NL-velduitleg](ORIGINAL-INGRESS-DIAGNOSTIEK.nl.md)
en [verzendcontroles/reproducties](M2-LAATSTE-VERZENDCONTROLE-20261025.nl.md).

## Bron, publicatie en controle

[HA dev46](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev46)
en [E32 alpha33](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.33)
zijn afzonderlijke kanalen op dezelfde exacte bron. Bestaande tags/downloads zijn
niet vervangen; het release-overzicht behoeft na publicatie nul metadatawijzigingen.

- [Main-CI40159829355](https://github.com/dielessen/open_thermostat/actions/runs/40159829355): alle 7 softwarepoorten geslaagd.
- [HA-tag-CI40161827411](https://github.com/dielessen/open_thermostat/actions/runs/40161827411) en [E32-tag-CI40161827418](https://github.com/dielessen/open_thermostat/actions/runs/40161827418): alle toepasselijke software-/publicatiepoorten geslaagd. HA-tag slaat firmwarebouw over volgens bestaande workflow.
- 773 native kerngevallen en 5 aanvullende echte lokale socketgevallen. De 77
  sanitizer-/debugiterator-kerngevallen zijn een subset, geen extra unieke gevallen.
- 2.339 HA-gevallen per Core 2026.10.2/2026.10.3: 2.271 tests + 68 subtests,
  nul fouten/errors/skips. Beide echte tagrapporten zijn apart teruggelezen.
- Alle 760 bronbestanden exact Git, ruwe commit en alle 88 tree-objecten onafhankelijk
  geverifieerd. Alle 86 HA-componentbestanden exact zelfstandige ZIP/Git/E32-companion.
- Alle 9 publieke downloads exact eigen tag-CI; de 4 HA-assets ook exact main/lokaal.
  Onafhankelijke bron-, hoofdpakket- en daadwerkelijke tagpakketreview geslaagd.
  Beide werkelijke E32-pakketten doorstaan de vaste 1.147 payloadcontroles.

HA-ZIP: 527050 bytes, SHA256
`b0174aa03c355b9b293330391ef2cd3b8c441deb891cbb9411351e74550a3708`.
E32-app: 2606208 bytes, SHA256
`270193dcb9403e0598e7bbaaac35766097bbd3ffb5f994531ebf029e12296956`.
E32-distributie-ZIP: SHA256 `fb3dfbbe129e7cade55206d8558e5b9d85ab63d6ecc8b6becf852775559716c8`.

De eerste onafhankelijke verifierprocessen eindigden met -9 zonder volledig
resultaat. Die oorspronkelijke oorzaak blijft onbekend. Daarna zijn de exacte
ongewijzigde functies met expliciet begrensde calls en fase-/resourcediagnose
volledig onafhankelijk afgerond: vendorinputs en 1.147 vaste controles PASS.
Geen geleverd bestand of vast controlepredicate is gewijzigd; de geslaagde proef
gebruikte de bevroren scripts ongewijzigd.

## Volledig E32-archief: werkelijke verschillen

De main- en tag-ZIP zijn niet bytegelijk: 10 van 722 payloads en 721 ZIP-datums
verschillen. App/manifest/softwareverificatie en volledige bron zijn bytegelijk.
Het hulpobject verschilt alleen in de compileerdatum/tijdliteral; het bijbehorende
archief is exact die objectvervanging. De SDK-prooflijst heeft 629 semantisch
identieke records met alle velden/duplicaten behouden, alleen een andere volgorde.
Relink-/distributie-/notice-/checksumverschillen zijn exact de bijbehorende hashes.

Ook de ruwe SPIFFS verschilt in 2119 bytes; de oorzaak daarvan is niet vastgesteld.
Beide echte images zijn afzonderlijk uitgepakt: alle 41 namen/inhouden zijn exact
gelijk en komen overeen met de bevroren inerte staging-defaults. Het factoryimage
verschilt uitsluitend op die SPIFFS-slice; de tekst draagt uitsluitend de juiste
gewijzigde MD5. Er wordt geen ruwe SPIFFS- of volledige ZIP-reproduceerbaarheid
geclaimd. De onafhankelijke eindcontrole keurt de daadwerkelijke tagbytes goed.

## Werkelijke installatie en afzonderlijke nacontrole

De bestaande native HA-agent heeft vóór schrijven een verse HA45-back-up gemaakt:
85 componentbestanden en 10 projectbestanden. Alle 95 payloads zijn teruggelezen;
de 85 componenten zijn daarnaast door Root exact met Git `3f12d8b` vergeleken.
Back-up: `/homeassistant/.openthermostat-backups/20261025-ha46-current5-install-owned/backup-20261025T045918789567Z`.
Manifest SHA256: `918cbf3d14d615a2ea349a5839d3d8e234b0b48d3bcd005d6843622c7c8eb047`.

Daarna zijn uitsluitend 86 componentbestanden geschreven en teruggelezen; één
normale Core-herstart is aangevraagd. De installatieturn eindigde met een
provider-uitvoertijdlimiet vóór runtimeacceptatie. Er volgde geen herinstallatie
of tweede herstart: een nieuwe afzonderlijke alleen-lezen nacontrole bevestigde
om **05:12:15 UTC** HA46 geladen, normale room-get en bestaande MQTT-worker
`shadow_ready`. Alle 38 controles slagen. Root vergeleek opnieuw alle 86 verse
livehashes met het publieke doel en alle 95 back-uppayloads met de eerdere set;
85 HA45-bestanden daarnaast weer exact Git `3f12d8b`.

SOURCE-revisie5/config-/profieldigests, programma's, 105 registry-entiteiten,
2 apparaten/1 entry/2 subentries, bron-/producentselectie en privébindings blijven
behouden. Geen staged/pending. Alle kaarten, panels en resources zijn volledig
vergeleken inclusief ID/type/query. Frontend dev41/v41 en v38/v35-aliases blijven
bytegelijk; normale HTTP200, SHA256
`5a8ac05a1636a6598d20c63d50c52e8cab92bdff44df8a4e98d9ad85b006b30a`.

De bestaande geauthenticeerde diagnostiekdownload levert om 05:12:14 UTC een
verse `read_only_original_ingress`: beschikbare, geïnitialiseerde, open native
eigenaar, exact temperatuur/TV02, geen blijvende/per-apparaat-/regelfunctie.
Temperatuur heeft 0 geconfigureerde oorspronkelijke topics, TV02 heeft 1;
alle tellers zijn op deze momentopname nul. Dat verklaart geen producentoorzaak,
bewijst geen fysieke ontvangst en kwalificeert geen bron of kraan.

Vijf ESP-metrieken zijn numeriek en niet restored; RTC-temperatuur blijft verwacht
onbekend. De gekozen interne kamerbron en TV02 blijven ongekwalificeerd.
E32 alpha31 behoudt bootidentiteit, bron/ELF/web; uptime stijgt 14482→15259s,
updater idle/geen bootpending. Alle uitgangen/forwarder uit, EMS-TX/polls/testframes
nul, Tado actief. Geen E32-upload, herstart of fysieke opdracht.

Werkelijke installatie: **86 componentwrites / 1 Core-herstart / 1 back-up**.
De afzonderlijke nacontrole: **0 productieacties, herstarts of nieuwe subscriptions**.
Dit is een eindige controle, geen bewijs van 72 uur stabiliteit of fysieke werking.
Receipts: `SAFE-INSTALL-RESULT.json`, `SAFE-POSTCHECK.json`,
`ROOT-BACKUP-COMPARISON.json`, `ROOT-POSTCHECK-COMPARISON.json` in de bewijsmap.

## Open actieve bèta

Geschikte oorspronkelijke kamerbron, geselecteerde en gekwalificeerde
product-SOURCE-fabriek, oorspronkelijke causale kraanecho en fysieke
start-/stop-/uitvalproeven blijven open. Software-integraal/leerbasis en eerdere
modellen krijgen geen fysieke vrijgave door opname in deze bundel. De bron-/
ontvangsttellers leveren geen meet-/kraankwalificatie of fysieke sluitgarantie.

Eerdere uploaderwatchdog, native HTTPS-afwijking en pendeloorzaak blijven open.
De uitvoerder/methode van de eerder waargenomen alpha31-installatie zijn niet
vastgesteld. Alpha33-publicatie is geen firmware-installatie of herstelproef;
geen nieuwe flash of blinde herhaling door deze opdracht. Externe geïnstalleerde
converter-/helperbytes en producentstart blijven buiten het bewezen beheervenster.
Actieve bèta blijft **NOT_READY**.

**English:** HA46 and E32 alpha33 are published from the same immutable source.
The bundle adds bounded original-ingress diagnostics and callback recursion
fences. Existing configuration/cards and alpha31 compatibility are retained.
Physical source/feedback/stop qualification and earlier E32 updater recovery
remain open. Publication and HA deployment do not authorize physical heating.

Bewijs: `out/combined-dev46-alpha33-20261025/`; nieuwe diagnosetests:
`out/original-ingress-diagnostics-20261025/`; eerdere verzendregressies:
`out/large-beta-handoff-20261025/`.
