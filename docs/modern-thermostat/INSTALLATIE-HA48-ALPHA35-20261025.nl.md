# Gezamenlijke release HA48 / E32 alpha35 — 25 oktober 2026

HA `0.4.0.dev48` is geïnstalleerd; E32 `alpha35` is gepubliceerd, maar niet
geïnstalleerd. De module is opnieuw direct waargenomen op `alpha31`, dezelfde
boot en oplopende uptime. Actieve bèta en E32-uploadgate blijven **NOT_READY**.

## Bron en publicatie

Beide onveranderlijke tags verwijzen naar bron
`70135db3c86df1f970265bc426fe5e35729c8261`:
[HA48](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev48) en
[E32 alpha35](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.35).
Main-CI [40175184341](https://github.com/dielessen/open_thermostat/actions/runs/40175184341),
HA-tag-CI [40175840929](https://github.com/dielessen/open_thermostat/actions/runs/40175840929)
en E32-tag-CI [40175840947](https://github.com/dielessen/open_thermostat/actions/runs/40175840947)
slagen met alle toepasselijke controles. Alle negen publieke bestanden zijn
volledig vergeleken met hun eigen tagbouw.

De bundel bevat cleanup die doorgaat na een gewone callbackexception, vier
klokregressies voor de bestaande kamerfixture en de pure Shelly SBHT-103C-
decoderbasis. De BLE-runtime selecteert die parser nog niet: koppelen, sleutels,
replay-/bronkwalificatie en fysieke apparaatondersteuning blijven open.
798 native kerngevallen, 16 aanvullende decoder-sanitizergevallen en
2.356 HA-gevallen per ondersteunde Core slagen. De ongewijzigde pakketverifier
slaagt met 1.921 controles voor main en tag; de onafhankelijke specialist
controleert de daadwerkelijke tag eveneens, met 1.151 standaardcontroles en
aparte bron-/ELF-/web-/HA-controle. Deze aantallen hebben verschillende scopes.

Alle 766 bronbestanden en 726 pakketbestanden zijn beoordeeld. Main en tag
hebben dezelfde app en logisch dezelfde 41 SPIFFS-bestanden. De ruwe SPIFFS-
bytes verschillen met onbekende oorzaak; er is geen volledige ZIP- of ruwe
SPIFFS-reproduceerbaarheidsclaim.

## HA-installatie en herstelpunt

De bestaande native HA-specialist heeft eerst alle 86 HA47-componentbestanden
gecontroleerd en een nieuwe back-up van 96 payloads gemaakt en teruggelezen.
Back-up: `/homeassistant/.openthermostat-backups/20261025-ha48-current5-install-owned/backup-20261025T083222480529Z`.
Manifest-SHA256: `b8fad5a50f8d8e631698299d0a17e9a4cf12dd1dd71d93ba668860e174ab2a93`.
Metadata-SHA256: `ea262f07582e47ce2317055520c4c15e771423e41a4fd30913c1f0ba1679e4d1`.

Het publieke HA48-pakket is 529.009 bytes, SHA256
`8b63b63fd1b595325a445745932e6d84df6ae40196a76e2299076b73d315927e`.
Alle 86 componentbestanden zijn geschreven en exact teruggelezen: 84 inhoudelijk
ongewijzigd, twee gewijzigd tegenover HA47. Er was één normale Core-herstart,
één back-up, nul configuratiewijzigingen en nul fysieke/MQTT-apparaatopdrachten.
De eerste schrijfinvocation stopte vóór componentwijzigingen op een lokale
metadatasleutel; die is gecorrigeerd. Geen dubbele installatie of herstart.

Installatieacceptatie: 2026-10-25T08:37:28.182042+00:00, 40 controles geslaagd, geen gaps.
Core 2026.10.3, HA48 geladen, room_get en shadow_ready bevestigd. Alle 86 live-
en 96 back-uphashes komen overeen met pakket en vastgelegde voorcontrole.
Instellingen, SOURCE5, programma's, koppelingen, 105 entiteitsrecords,
2 apparaten, 1 entry, 2 subentries, kaarten/resources en 41 frontendbestanden
zijn behouden. Tado-configuratie is behouden; dit bewijst geen fysieke regelstatus.

## Afzonderlijke nacontrole

Nieuwe afzonderlijke read-only opname op 2026-10-25T08:43:56.078320+00:00: **46 controles
geslaagd, nul gaps**. Alle 86 livebestanden en 96 back-upbestanden opnieuw gelezen
en exact; manifest en metadata gelijk aan het herstelpunt. Projecthashes en
frontend behouden; HA48 geladen, Core 2026.10.3 en shadow_ready opnieuw bevestigd.
E32 alpha31 op dezelfde boot met oplopende uptime; fysieke uitgangen uit en
EMS-TX/poll/testtellers nul. Vijf ESP-diagnosewaarden numeriek en niet restored;
RTC blijft onbekend. Deze nacontrole voerde nul productieacties, writes,
back-ups, herstarts, servicecalls, MQTT-publicaties of apparaatopdrachten uit.
Deze nultellers staan los van de 86 writes/één back-up/één herstart bij installatie.

## E32 en resterende grenzen

De installatieacceptatie leest alpha31, bron `659879e`, opnieuw direct uit.
EMS-TX, poll- en testtellers zijn nul; uitgangen staan uit en geen update is
pending of bezig. Er is geen firmware-upload, HTTPS-updateproef of E32-herstart
uitgevoerd. De oudere uploader-reset6/TASK_WDT en herstelroute blijven onbekend;
de actor/methode van de eerdere alpha31-installatie blijven onbekend.
Alpha35 is dus een gepubliceerde bron-/softwarebundel, geen module-installatie.

Geen bron-/kraan-/ketelkwalificatie, pendeloorzaak, watchdogherstel of langdurige
stabiliteit aangetoond. Nieuwe ontvangsttellers horen bij een nieuwe RAM-eigenaar;
nul of waiting na herstart bewijst geen upstreamfout of causale kraanecho.
Alle 23 voorbereide onderdelen, 289 bronverwijzingen en 31 producteisen blijven
behouden; de fysieke releasepoorten blijven open op het [werkbord](WORKBOARD.nl.md).

Lokaal bewijs: `out/combined-dev48-alpha35-20261025/`, met afzonderlijke bron-,
CI-, pakket-, publieke download-, installatie- en nacontrolereceipts.
