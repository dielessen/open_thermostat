# Gezamenlijke release HA39 / E32 alpha30 — werkelijke levering

24 oktober 2026. **Publicatie geslaagd; HA39 geïnstalleerd. E32-installatie geblokkeerd.**
Afzonderlijke nacontrole van 18:54 UTC geslaagd; alle 30 controles waar.
Een verse leesactie en bestands-/back-uphashcontrole bevestigen de installatie.

## Bron en openbare pakketten

Beide tags verwijzen naar `3bad1747f53cd82dcf1bf5953787b42459ef8187`:

- [HA 0.4.0.dev39](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev39).
- [E32 v0.1.0-e32v2-alpha.30](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.30).

CI `40120954148` (main), `40120955899` (HA-tag) en `40120955914` (E32-tag)
zijn volledig geslaagd. Alle zeven softwarepoorten op de firmwaretag zijn groen;
publicatiejobs geslaagd. Geen bestaande tags of assets vervangen. De negen echte
openbare downloads zijn bytegelijk aan de gecontroleerde CI-bestanden; de
releasecatalogus heeft geen resterende wijzigingen.

De bronreview vond geen concrete fout. De onafhankelijke pakketreview voerde
2424 controles uit; daarnaast controleerde de rootverifier 1130 pakketvoorwaarden,
alle 716 Git-bronbestanden, firmwaredescriptor en webbestanden. De 83 HA-bestanden
zijn tegen publieke ZIP en Git vergeleken. Dit bewijst software-/pakketidentiteit,
geen fysieke regelkwalificatie.

## Inhoud en tests

Alle eerdere functies en 23 voorbereide onderdelen blijven behouden. Nieuwe
wijzigingen: transactionele handmatige upload; intrekking van verworpen
veiligheidsfeiten; oorspronkelijke ontvangstvolgorde per ketelveld; blijvende
HA-cache-intrekking na transportfouten en expliciet ongeldige waarden.

689 firmwaretests, 11 REST-uploadscenario’s en 2195 HA-testgevallen per echte
Core 2026.10.2/2026.10.3 zonder fouten of skips. De HA-XML bevat 2127 testfuncties
plus 68 subtestgevallen per versie. Frontend dev38/v38 en v35-alias blijven bytegelijk.

## Werkelijk geïnstalleerd

| Onderdeel | Werkelijke uitkomst |
| --- | --- |
| HA | `0.4.0.dev39`, Core 2026.10.3, integratie geladen; 83 bestanden exact bron/publicatie |
| HA-bediening | room/get beschikbaar, transport shadow_ready; fysieke uitvoer uitgeschakeld |
| E32 | Ongewijzigd alpha28, bron `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f` |
| E32-actie in deze uitrol | Nul uploads, nul herstartverzoeken; updater idle en boot_pending false |
| Behoud | 105 entiteitsrecords, 2 apparaten, 1 entry/2 subentries; SOURCE/journal rev4/digests, instellingen, programma’s, bindingen, private pins/producent en dashboards gelijk |
| Back-up | Verse HA38-back-up, 93 bestanden; manifesthash `83e804ccb0e041e161400a06852ee9ed6d20c3419c02b5a565d67c2f71579897`; readback vóór/na schrijven en na herstart |
| Herstart | Eén normale Core-herstart; geen device-, bron- of profielwijzigingen |
| ESP-diagnose | CPU-temperatuur, vrij/minimum geheugen, maximale allocatie en uptime numeriek/vers; RTC-temperatuur verwacht unknown bij uitgeschakelde RTC |
| Veiligheid | EMS-TX, forwarding en alle fysieke uitgangen geblokkeerd; TX/polls/testframes nul; Tado-configuratie behouden |

De back-up staat onder
`/homeassistant/.openthermostat-backups/20261024-ha39-only-install-owned/backup-20261024T184747890032Z`.
Eigen HTTP-/WS-/cookiesessies en tijdelijke installatiebestanden zijn gesloten/opgeruimd.
De bestaande eenmalige leescontrole krijgt alleen deze bevestigde HA39/alpha28-basis;
tijdstip, eigenaar, aflevering en oorspronkelijke leesscope blijven behouden.

## E32-herstelblokkade

De eerdere alpha29-upload gaf curl56/HTTP000 en een task-watchdogreset (code6).
De taak, stack en oorzaak zijn onbekend. De module draait nog alpha28; er is geen
bewezen alpha29-boot of rollback. Alpha30 uploadhardening repareert de al draaiende
alpha28-uploader niet voordat die nieuwe firmware werkelijk is geïnstalleerd.

De onafhankelijke herstelbeoordeling vond geen onderbouwde veilige bestaande
remote route. Geen blinde /ota-, native HTTPS-, reboot- of rollbackproef uitgevoerd.
Vervolg vereist gerichte diagnose met aantoonbare mitigatie voor alpha28, of apart
beoordeelde fysieke servicetoegang met behoud van NVS, SPIFFS en partitie-indeling.
Er is geen factoryflash/wipe voorbereid of uitgevoerd.

## Grenzen en bewijs

Finite installatiecontrole is geen duurproef. De eerdere tijdelijke transportafwijking,
het gemelde pendelen en native HTTPS-updatergedrag hebben geen bewezen reparatie.
TV02 en geselecteerde RTCGQ11LM blijven ongekwalificeerde diagnostiek; geen geforceerde
rapportage, bronvervanging, kraan-ACK of actieve regelvrijgave. Nieuwe Shelly-/Xiaomi-
Bluetoothdrivers, M2 en fysieke start-/stop-/uitvalproeven blijven open.

Bewijs in `out/combined-dev39-alpha30-20261024/`:
`SOURCE-REVIEW.json`, `PACKAGE-REVIEW.json`, `PUBLIC-DOWNLOAD-REVIEW.json`,
`FROZEN-HA-TESTS.json`, `SAFE-INSTALL-RESULT.json`, `SAFE-POSTCHECK.json`,
`SCHEDULE-REVIEW.json` en `RECOVERY-ASSESSMENT.json`.
Dit verslag sluit de fysieke bèta-releasepoorten niet.
