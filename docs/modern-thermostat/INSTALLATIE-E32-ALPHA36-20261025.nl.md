# Alpha36 via GitHub geïnstalleerd en onafhankelijk geaccepteerd

25 oktober 2026. De E32 draait `v0.1.0-e32v2-alpha.36`, bron `7ddf341`.
De normale native GitHub-update is met één installatiecommando uitgevoerd en
vervolgens in een afzonderlijke read-only opdracht gecontroleerd. HA48 bleef
ongewijzigd; geen HA-herinstallatie/herstart, bestandsupload, expliciet E32-
herstartcommando of fysieke ketel-/kraanopdracht.

## Exact verloop

1. Verse alpha31-/HA48-voorcontrole en werkelijk publiek alpha36-manifest en
   firmware opnieuw gecontroleerd. Alle 35 voorcontrolechecks slagen.
2. Verse beperkte back-up van tien payloads, hashmanifest nagelezen.
   Manifest-SHA256: `27971f9c646d9d0db90cf383492e4dddb4f3fa4c83ea694a356e2f59fe90dbc6`.
3. Eén native cataloguscontrole op 10:28:48 UTC; alpha36 werkelijk in de catalogus.
4. Exact één `POST /updates/install` met tag alpha36 op 10:29:47 UTC;
   oorspronkelijke HTTP202 en vooraf opgeslagen intent bewaard.
5. De E32 downloadt zelf 2.619.952 bytes. Controlepunt poging2, van alpha31 naar36,
   HTTP200/volledige omvang/`boot_slot_selected`. In de geverifieerde draaiende
   bron volgt dit uitsluitend na checksum, imagecheck en volledige flash-readback.
6. Normale automatische herstart; alpha36 op de andere app-partitie `0x390000`,
   `boot_pending=false`, updater idle en geen nog geplande herstart.
   Installatieacceptatie 10:31:55 UTC: alle 36 checks geslaagd.
7. Afzonderlijke read-only nacontrole 10:36:53 en 10:37:02 UTC: dezelfde nieuwe
   boot, uptime 365→375 seconden, alle 45 checks geslaagd; nul mutaties.

## Onafhankelijke vergelijking

- Exacte bron: `7ddf3410666d814850275433d9dddd266e5d83ba`.
- Firmware-SHA256: `e8a242d00288e70172fae90ee006d90d59287d024480505d38a887e99f6eb5d4`.
- ELF-SHA256: `ef313784cdc5e6a83c290225abbdac5a27138c7228890bd804ec9f39d82dc738`.
- Web-SHA256: `2b858b3ed32c9748c4b00c0c4f25e0160d17fbcadbb4b040252c3f9ec47dc505`.
- Alle 31 werkelijk geserveerde UI-bestanden exact publieke kandidaat.
- Alle 86 HA-bestanden exact en ongewijzigd; dertien gedeelde projecthashes gelijk.
- Instellingen, netwerk, programma's, bindings, SOURCE5 en bron-/profielidentiteit
  behouden. De zes bestaande loggingvelden zijn gelijk. Alleen de twee nieuwe
  API-velden `syslog_esp`/`syslog_ems` verschijnen met defaulttrue; geen settingssave.
- Verse back-up en alle tien payloadhashes opnieuw nagelezen.
- Alle fysieke uitgangen geblokkeerd; EMS TX/poll/test 0, UART-/ontvangstfouttellers0.

De root heeft de 86 HA-hashes, dertien projecthashes, zes loggingvelden, twee
bootwaarnemingen en oorspronkelijke admission-/commandoaantallen nogmaals naast
voorcontrole, publieke bestanden en onafhankelijke receipts gelegd.

## Verplichte volgende releasepoort

Het [acceptatierapport](update-acceptance/e32-alpha36-20261025.json) bevat dertien
vereiste checks en SHA256-verwijzingen naar originele beveiligde bewijsbestanden.
`E32-UPDATE-GATE.json` accepteert nu alpha36. De volgende kandidaat moet deze
acceptatie behouden en zelf pending worden; zonder eigen installatie/nacontrole
kan daarna geen opvolgende reguliere E32-release worden gepubliceerd.
Zie [verplicht proces](E32-UPDATE-PROCES.nl.md). De gate heeft zes regressietests,
waaronder blokkeren bij ontbrekend bewijs, herhaalde installatie of verkeerde tag.

De historische multipart-watchdogoorzaak blijft onbekend; dit accepteert de
normale native GitHub-route. Geen universele powerloss-/rollbackgarantie of
actieve ketel-/kraanvrijgave. De actieve bèta blijft NOT_READY voor haar eigen
fysieke voorwaarden. Automatische twaalfuurscontrole en dashboardmelding zijn
na alpha36 geprogrammeerd voor de volgende bundel en draaien nog niet op de E32.

Volledige beveiligde receipts: `artifacts/e32-remote-flash-recovery-20261025/`.
Kopieën/vergelijkingen: `out/e32-remote-flash-recovery-20261025/`.
