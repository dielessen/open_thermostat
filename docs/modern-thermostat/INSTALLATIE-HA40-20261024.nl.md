# HA dev40 — publicatie en installatie

24 oktober 2026. **Gepubliceerd, geïnstalleerd en onafhankelijk gecontroleerd.**
Nacontrole 19:28 UTC: HA40/Core 2026.10.3, E32alpha28 behouden; alle 34 controles geslaagd.

## Release

[HA 0.4.0.dev40](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev40)
verwijst naar `a01bc68d211b310090568e8b2b83d3e652782866`. De M2-kraanadapter
blijft ingetrokken na teruggaande/ongeldige tijd, ook rond wachten, autorisatie
of serviceafhandeling. Een onzekere fysieke uitkomst veroorzaakt geen retry;
een duplicate blijft uitsluitend een historisch service-acceptatiereceipt.

De gewone FW→HA-kraanroute, causale doel-echo, eigenaar-/bron-/kraankwalificatie
en fysieke proef blijven open. Geen instelling of fysieke vrijgave toegevoegd.
Alle bestaande functies, opslagcontracten, entiteits-ID’s en statistieken behouden.
Frontend v38/v35-alias blijft bytegelijk.

## Verificatie

- Bron-CI `40123920367`: alle zeven softwarepoorten geslaagd.
- Exacte HA-tag-CI `40124105634`: browser/native en automatische publicatie geslaagd.
- 2209 HA-testgevallen per echte Core 2026.10.2/2026.10.3: nul fouten/errors/skips.
- 141 gerichte adaptergevallen per Core; 14 nieuwe regressies, waarvan 13 faalden op de oude bron.
- Onafhankelijke bronreview geslaagd; pakketreview 208 controles zonder bevindingen.
- Alle 83 componentbestanden exact Git-bron, manifest en pakket; vier echte openbare downloads bytegelijk aan kandidaat- en tag-CI.
- Catalogus zonder resterende wijzigingen; bestaande tags en assets behouden.

Publieke ZIP: `OpenThermostat-HA-0.4.0.dev40.zip`, 514146 bytes,
SHA256 `db21a8ddd67203a9c4e76f371233af37d65d1d9e49c053ae902c5cdaf519deba`.

## Installatiecontrole

| Controle | Werkelijke uitkomst |
| --- | --- |
| HA | dev40/Core 2026.10.3, integratie geladen en room/get shadow_ready |
| Identiteit | Alle 83 livebestandshashes exact openbare ZIP en bron a01bc68; frontend HTTP200/hash gelijk, v35-alias behouden |
| Uitrol | 83 componentbestanden, één normale Core-herstart; nul E32-uploads/herstarts |
| Back-up | Verse HA39-back-up van 93 bestanden, alle hashes vóór/na schrijven en afzonderlijk na herstart gecontroleerd |
| Behoud | 105 registryrecords/2 apparaten/1 entry/2 subentries; instellingen, programma’s, bindingen, SOURCE/journal rev4/digests, private pins/producent, dashboards/resources en E32/netwerk/model/syslog behouden |
| Uitgangen | Ketel, actuator, fysieke uitvoer en forwarding uit; TX/polls/testframes nul; passief EMS-ontvangstpad actief |
| ESP | Vijf numerieke verse waarden (geheugen, CPU-temperatuur, uptime); RTC verwacht unknown |
| Bronkwalificatie | TV02 waiting zonder ACK/readiness/regelkwalificatie; geselecteerde temperatuurbron profile_missing en diagnostisch |

Back-up: `/homeassistant/.openthermostat-backups/20261024-ha40-only-install-owned/backup-20261024T192216187825Z`. Manifest-SHA256
`348b29a54132b24a49c7d1cffc33922f557a3347fb3c11af276f2be653df87e2`. De bestaande geplande leescontrole krijgt alleen de
bevestigde HA40/alpha28-identiteit; tijdstip, eigenaar, scope en aflevering blijven
behouden. Eigen HTTP-/WS-/cookiesessies gesloten en eigen installatie-tempbestanden
opgeruimd. Geen geforceerde rapporten, bronwissel of fysieke commands uitgevoerd.

Dit is een eindige actuele controle; geen bewijs van langdurige stabiliteit,
actieve bèta of herstel van de eerdere tijdelijke transportafwijking.

## E32 behouden

Geen nieuwe firmware-runtimecode: alpha30 blijft de actuele firmwaredownload.
Tag `v0.1.0-e32v2-alpha.30` blijft op bron `3bad1747`; alle vijf asset-SHA256’s
en groottes zijn vergeleken met het eerdere echte downloadbewijs en ongewijzigd.
Geen nieuwe firmwaretag of nieuwe publicatie van anders gebouwde alpha30-assets.

De module blijft alpha28 zolang de initiërende taak/stack/oorzaak van de eerdere
uploader-task-watchdogreset en een compatibele herstelroute onbekend zijn.
Geen upload, native HTTPS-proef, reboot, rollback, factoryflash of wipe in deze
HA-uitrol. Alle fysieke uitgangen blijven geblokkeerd; Tado-configuratie behouden.
Geen actieve bèta-, pendel-, Bluetooth- of updaterreparatieclaim.

Bewijs: `out/ha-dev40-release-20261024/` met bron-/pakketreview,
`PUBLIC-DOWNLOAD-REVIEW.json`, CI-/XML-uitkomsten en
`E32-RELEASE-PRESERVATION.json`, `SAFE-INSTALL-RESULT.json`,
`SAFE-POSTCHECK.json` en `SCHEDULE-REVIEW.json`.
