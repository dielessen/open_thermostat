# HA dev43 — publicatie en installatie

24 oktober 2026. **Gepubliceerd, geïnstalleerd en onafhankelijk gecontroleerd.**
Nacontrole 21:17:50 UTC: HA43/Core 2026.10.3, E32alpha28 behouden; alle 38 checks geslaagd.

## Release

[HA 0.4.0.dev43](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev43)
verwijst naar `97eb9a03f7968dd043e6542979a4815887e9704b`.
De kamereditor legt interne/diagnostische temperatuurbronnen direct in Nederlands
of Engels uit. Onbruikbare optionele metadata breekt de editor niet; geen
onzichtbare bronwissel of automatische regelkwalificatie.
De voorbereide M2-ontvangertoelating staat standaard dicht en is niet door de
normale bronfabriek geselecteerd. Eigen HA-grants verlopen vanaf hun oorspronkelijke
klokanker; gewijzigde context, replay of onzekere uitkomst verleent geen vrijgave.

## Bewezen publicatie

- Bron-CI [40132011504](https://github.com/dielessen/open_thermostat/actions/runs/40132011504): zeven softwarepoorten geslaagd.
- Exacte tag-CI [40132021545](https://github.com/dielessen/open_thermostat/actions/runs/40132021545): browser, beide native Core-versies en publicatie geslaagd.
- 2.281 gevallen per Core 2026.10.2/2026.10.3: 2.213 tests en 68 subtests, nul fouten/errors/skips.
- Onafhankelijke bronreview en 1.028 pakketcontroles geslaagd.
- Alle 84 componentbestanden exact Git; vier openbare bestanden bytegelijk aan de beoordeelde kandidaat en beide CI-pakketten.
- Releasecatalogus zonder resterende wijzigingen; E32 alpha30-tag en vijf assets behouden.

Publieke ZIP: `OpenThermostat-HA-0.4.0.dev43.zip`, 519368 bytes,
SHA256 `8c021c3757b072ed89fe7f1c88db76542071213ce861d779febf233bd193d136`.
Frontend dev41/v41 behoudt v38/v35-kaartaliases; alleen eigen gegenereerde
kaart-/resourceverwijzingen mogen migreren.

## Installatie en afzonderlijke nacontrole

| Controle | Werkelijke uitkomst |
| --- | --- |
| HA | dev43/Core 2026.10.3, integratie geladen en room/get shadow_ready |
| Identiteit | Alle 84 livehashes exact openbare ZIP/Git; nieuwe bronkeuze-uitleg uit werkelijk geladen backend, frontend HTTP200/hash gelijk |
| UI | Twee eigen kamerkaarten v38→v41; handmatige kaarten, resources, panels en overige dashboardvelden behouden |
| Uitrol | 84 componentbestanden, één normale Core-herstart; eerste WS-lezing na herstart mislukte, één begrensde leesherhaling slaagde; geen herhaalde schrijfactie/herstart |
| Back-up | Verse HA40-back-up met 83 componentbestanden en 10 projectpayloads; alle 93 hashes vóór/na schrijven en apart na herstart geverifieerd |
| Behoud | 105 registryrecords/2 apparaten/1 entry/2 subentries, instellingen, programma’s, bindingen, SOURCE/journal rev4/digests, bronpins/producent en E32/netwerk/model/syslog behouden |
| Uitgangen | Fysieke uitvoer, ketel, actuator en forwarding uit; EMS-TX/polls/testframes nul |
| ESP | Vijf numerieke verse metriekwaarden; RTC verwacht unknown |
| Bronkeuze | Werkelijke melding internal_device_temperature, authorizes_control=false; meetprofiel blijft profile_missing en TV02 blijft ongekwalificeerd |
| E32 | Exact alpha28/3efb0a1/ELF/web behouden; updater idle, boot_pending=false, uptime loopt door; nul uploads/herstarts/updaterproeven |

Back-up: `/homeassistant/.openthermostat-backups/20261024-ha43-only-install-owned/backup-20261024T210923098139Z`. Manifest-SHA256
`df82b2e11960b3535290cd2739c2adc9fb234e0c31cb8d1c71c976be875e44e7`. Eigen installatie-tempbestanden zijn afwezig;
eigen HTTP-/WS-/cookiesessies gesloten. De aparte nacontrole heeft geen productie-
acties uitgevoerd. De bestaande geplande leescontrole krijgt alleen de bevestigde
HA43/alpha28-uitgangssituatie; tijdstip, eigenaar, aflevering en scope zijn behouden.
Er is geen extra geplande taak of fysieke proef gestart.

Dit is een eindige actuele controle; geen bewijs van langdurige stabiliteit of
actieve ketel-/kraanregeling.

## Grenzen

De aparte verloren-opstartberichtregressie en precieze testklokgrens zijn
gecontroleerd. De oorspronkelijke incidentele CI-kamerassertie is niet causaal
verklaard of als productreparatie afgevinkt. Acht herhalingen per Core blijven
naspeelbaar; definitieve tag en twee voorafgaande diagnostische native jobs slagen.
De diagnostische jobs hadden een afzonderlijke broninventarisafwijking die vóór
de HA43-freeze is bijgewerkt en door de definitieve CI is gecontroleerd.

Geen actieve bèta-vrijgave. Normale FW→HA-kraanroute, actuele leasebinding,
oorspronkelijke causale echo, geschikte kamerbron en fysieke proeven blijven open.
E32 alpha28-watchdogtaak/stack/oorzaak en herstelroute onbekend; geen blinde retry,
HTTPS-proef, reboot, rollback, factoryflash of wipe. Pendeloorzaak en Bluetooth-
ondersteuning niet als gerepareerd of geleverd voorgesteld.

Bewijs: `out/ha-dev43-release-20261024/`; gericht voor/na- en diagnostisch bewijs
blijft in `out/m2-release-candidate-20261024/` bewaard.
