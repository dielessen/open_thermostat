# HA dev47 / E32 alpha34 — gezamenlijke release en HA-uitrol

25 oktober 2026. Beide onveranderlijke releases zijn gepubliceerd op bron
`6f21f34ff773645645c98dc2602337c648e18ffe`.

HA dev47 is geïnstalleerd op bron `6f21f34`, met een verse HA46-back-up van
96 bestanden en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober **06:47:49 UTC** slaagt: 44 controles, alle 86 livebestanden exact
publiek pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; alpha34 is gepubliceerd, zonder firmwareactie.
De nieuwe code is normaal opgestart; er zijn geen foutinjecties op productie uitgevoerd.

## Samenhangende wijzigingen

- De native HA-opstart behoudt één eigenaar over programma-, Store- en MQTT-
  leesgrenzen. Afsluiten of annuleren kan geen oude worker, listener of timer
  daarna alsnog starten. Dubbele start vervangt de eerste eigenaar niet.
- Late unsubscribe-handles worden direct opgeruimd; een andere ontvanger blijft
  behouden. De oorspronkelijke temperatuurdiagnose deelt één begrensd totaalbudget;
  optionele diagnosefouten geven geen fysieke bevoegdheid en sluiten de bestaande
  besturing niet wegens die diagnosefout.
- De E32-bron bewaart vier gerichte checkpoints vóór checksum, imagevalidatie,
  onafhankelijk flash-readback en bootselectie. De bestaande statuspagina verklaart
  ze in Nederlands/Engels. Een bevestigde opslag is geen voltooide bewerking,
  resetoorzaak, succesvolle installatie of herstelbewijs.
- Alle eerdere bron-/deadline-/verzendcontroles en ontvangstdiagnostiek blijven
  behouden. Alle 23 onderdelen, 286 bronverwijzingen en 31 producteisen blijven
  opgenomen. HA-frontend dev41/v41 met v38/v35-aliases blijft bytegelijk.

[HA-opstart, reproductie en grenzen](HA-OPSTART-LIFECYCLE-20261025.nl.md) en
[updatercheckpoints](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).

## Exacte bron en publicatie

[HA dev47](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev47)
en [E32 alpha34](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.34)
zijn dezelfde bevroren Git-bron. Eerdere tags en downloads zijn niet vervangen.

- [Main-CI40167516226](https://github.com/dielessen/open_thermostat/actions/runs/40167516226): alle 7 softwarepoorten geslaagd.
- [HA-tag-CI40168564923](https://github.com/dielessen/open_thermostat/actions/runs/40168564923) en [E32-tag-CI40168564740](https://github.com/dielessen/open_thermostat/actions/runs/40168564740): alle toepasselijke jobs en publicaties geslaagd.
- 782 native kerngevallen; 40 updatergevallen ook onder strikte ASan/UBSan en
  lekcontrole. Die 40 zijn een subset, geen extra unieke gevallen. Eerdere
  actuator-/socket-/browserpoorten blijven onderdeel van de volledige CI.
- Tien nieuwe HA-opstartgevallen falen vóór herstel; 139 gerichte gevallen slagen.
  Per ondersteunde Core 2026.10.2/2026.10.3 slagen 2.349 volledige HA-gevallen
  (2.281 tests + 68 subtests), nul failures/errors/skips. Beide echte tagruns zijn
  daarnaast via hun vier daadwerkelijke XML-rapporten geverifieerd.
- Onafhankelijke bronreview: alle 763 bestanden en 88 ruwe Git-treeobjecten exact,
  eigen 139 Core2-proeven geslaagd, geen bevindingen.
- Onafhankelijke hoofdpakketreview: alle negen assets en eigen ongewijzigde vaste
  verifier met 1.150 controles geslaagd. Alle 86 HA-bestanden exact Git/standalone/
  E32-companion; 84 bytegelijk aan HA46, alleen manifest en opstartroute gewijzigd.
- Alle negen echte publieke downloads exact eigen tag-CI; alle vier HA-assets ook
  exact main/lokaal. De daadwerkelijke E32-tagbytes doorstaan de vaste 1.150 controles.

De afzonderlijke definitieve tag-/publieke pakketreview slaagt: eigen vaste
1.150 controles, alle negen publieke/tagbytes en eigen 41-bestands-/stagingcontrole.
Geen bevindingen; bron-, hoofd- en daadwerkelijke tagreview zijn apart bewaard.
Het release-overzicht vroeg na beide publicaties nul metadatawijzigingen.

HA-ZIP: 528079 bytes, SHA256 `52ca0cfaab9a628826b48e838d8b93034ed2f9ea97e7def0b36feb3b43b88bbd`.
E32-app: 2607312 bytes, SHA256 `347a564adafee6066ca3e079496c3748ba2866674aad206b1ad2aa525f8bbc37`.
Werkelijke tag-ELF/descriptor: `9751c90d33afa61918a9e925465fbe891adb34a307cacd959801dbd7d199d453`; webrevision `c9c73435026da0396564f5ad34f450c0705075acc3eed0efd19e2c4a392f5b9d`.
Publieke E32-distributie-ZIP: SHA256 `7b877866ec01c603621e3902dd06177e1dd26d5f21209cc17a2405afe9cf157f`.

## Volledige E32-distributies: feitelijke verschillen

Main en tag zijn niet bytegelijk: 10 van 725 payloads en 724 ZIP-datums verschillen.
App, manifest, softwareverificatie en volledige bron zijn bytegelijk. Het
hulpobject verschilt uitsluitend in de compileertijdliteral; het volledige
Arduino-archief is exact die enkele objectvervanging, met twee correcte relink-SHA's.
De SDK-prooflijst heeft dezelfde 629 records met alle velden en duplicaten,
alleen in een andere volgorde. De overige distributie-/notice-/checksumwijzigingen
zijn exact de afgeleide hashes, inclusief de juiste inventoryhash.

De ruwe SPIFFS verschilt in 2122 bytes; de oorzaak daarvan is onbekend. Beide
werkelijke images zijn uitgepakt: alle 41 namen/inhouden zijn exact gelijk en
komen overeen met de bevroren inerte staging-defaults. Het factoryimage verschilt
uitsluitend op zijn werkelijke SPIFFS-slice; FACTORY-CHECK wijzigt uitsluitend de
juiste MD5. Geen ruwe SPIFFS- of volledige ZIP-reproduceerbaarheid geclaimd.

## Werkelijke HA-installatie en afzonderlijke nacontrole

De bestaande native HA-agent heeft vóór schrijven een verse **HA46-back-up van
96 payloads** gemaakt en teruggelezen: 86 componentbestanden + 10 projectbestanden.
Pad: `/homeassistant/.openthermostat-backups/20261025-ha47-current5-install-owned/backup-20261025T064203792048Z`.
Manifest SHA256: `34e47729184fe6a61069987279f17e46cdba45fef86cac21b98427e5b36945c0`.
Root vergeleek de 86 componenten onafhankelijk met Git `2d32ad3`.

Uitsluitend 86 doelcomponenten zijn geschreven, teruggelezen en met de publieke
HA47/Git-bron vergeleken. Alle 96 back-uppayloads zijn daarna opnieuw gelezen.
Eén normale Core-herstart volgde; HA47 is geladen op Core 2026.10.3 en de bestaande
native MQTT-worker/room-get is `shadow_ready`. De installeracceptatie van
06:44:47 UTC slaagde met 36 checks.

Daarna is een **nieuwe afzonderlijke alleen-lezen nacontrole** uitgevoerd op
**06:47:49 UTC**: alle 44 controles geslaagd. Root vergeleek opnieuw alle 86
verse livehashes met het publieke doel en alle 96 back-uppayloadhashes met de
voor-/na-installatiesets, inclusief alle 86 HA46-bestanden exact Git `2d32ad3`.
Manifest en payloads zijn behouden. Deze nacontrole heeft nul productieacties.

SOURCE-revisie5, config-/profieldigests, programma's, 105 registry-entiteiten,
2 apparaten/1 entry/2 subentries, bindings en private bron-/producentselectie
zijn behouden; niets staged/pending. Kaarten, panels en resources zijn volledig
vergeleken inclusief ID/type/query. Frontend dev41/v41/v38/v35 blijft bytegelijk,
HTTP200 en SHA256 `5a8ac05a1636a6598d20c63d50c52e8cab92bdff44df8a4e98d9ad85b006b30a`.

De normale diagnostiekdownload toont de werkelijke, geïnitialiseerde/open native
eigenaar. Na de HA-herstart is dit een nieuwe RAM-eigenaar: temperatuur heeft nul
originele topics, TV02 één; alle tellers zijn op deze momentopname nul en TV02
`waiting`. Het eerdere stale bericht/owner-counter1 is niet als nieuwe ontvangst
hergebruikt. De geselecteerde interne kamermeting blijft ongekwalificeerd.
Vijf bestaande ESP-metrieken zijn numeriek en niet restored; RTC blijft verwacht
onbekend. Geen live cancel-/dubbelstart-/foutinjectieproef uitgevoerd.

E32 alpha31 behoudt bron659879e/ELF045dfe53/web6ec3 en dezelfde gerapporteerde
bootidentiteit. Uptime stijgt van 20647s vóór uitrol via 20811s bij installacceptatie naar
20993s bij de nacontrole. Updater idle/geen bootpending; uitgangen/forwarder uit,
EMS-TX/polls/testframes nul. Tado-configuratie behouden; een actuele fysieke
Tado-controllerstatus wordt niet uit deze capture afgeleid. Er is geen E32-flash,
herstart, native HTTPS-proef of fysieke opdracht uitgevoerd.

Feitelijke uitrol: **86 componentwrites / 1 Core-herstart / 1 verse back-up**.
Afzonderlijke nacontrole: **0 productie-/herstart-/deviceacties**. Dit is een eindige
controle en geen bewijs van 72 uur stabiliteit of fysieke failsafe.
Receipts: `SAFE-INSTALL-RESULT.json`, `SAFE-POSTCHECK.json`,
`ROOT-INSTALL-COMPARISON.json` en `ROOT-POSTCHECK-COMPARISON.json`.


## Nog open voor actieve bèta

Een geschikte oorspronkelijke kamermeting, gekwalificeerde product-SOURCE-fabriek,
oorspronkelijke causale kraanecho en fysieke installatie-/start-/stop-/uitvalproeven
blijven open. De beperkte voor-uitrolcontrole van 05:46 UTC zag één oorspronkelijke
TV02-workeracceptatie, inmiddels stale en ongekwalificeerd; dit is geen klepstand,
causale ACK of regelrecht. De gekozen interne temperatuur bleef onbruikbaar.

De eerdere uploaderwatchdog-/HTTPS-/pendeloorzaak en concrete E32-herstelroute
blijven open. Alpha34 is gepubliceerd, geen bewijs van een geslaagde device-update.
De uitvoerder/methode van de eerder waargenomen alpha31-installatie zijn onbekend.
Geen nieuwe E32-flash, reboot, HTTPS-proef of fysieke opdracht door deze uitrol.
Actieve bèta blijft **NOT_READY**.

**English:** HA47 and E32 alpha34 are published from the same immutable source.
The bundle combines single-owner async HA startup with four bounded pre-verification
update checkpoints. Existing cards/settings and all prepared roadmap code remain
preserved. Physical source/feedback/stop qualification and installed E32 updater
recovery are still separate open gates; publication/HA deployment is not heating GO.

Bewijs: `out/combined-dev47-alpha34-20261025/`; oorspronkelijke softwareproeven:
`out/native-startup-ownership-20261025/` en `out/update-verification-checkpoints-20261025/`.
