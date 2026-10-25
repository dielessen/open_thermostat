# HA dev44 / E32 alpha31 — publicatie en werkelijke installatie

25 oktober 2026. **Beide pakketten gepubliceerd; HA44 geïnstalleerd en onafhankelijk
gecontroleerd. De E32 blijft op alpha28 en is niet geflasht.**

Afzonderlijke nacontrole 00:32:01 UTC: alle 20 checks geslaagd. Dit is een eindige
controle, geen actieve bèta-vrijgave of bewijs van langdurige stabiliteit.

## Gepubliceerde bron en pakketten

[HA 0.4.0.dev44](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev44)
en [E32 alpha31](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.31)
verwijzen naar dezelfde onveranderlijke bron
`659879e52b3e0e517e8dea1e28edb2d189c38c77`.

De bundel behoudt alle 23 voorbereide onderdelen en 31 producteisen. De native
HA-worker verwerkt nu de voorbereide kraangrant-/opdrachtberichten met actuele
scope, oorspronkelijke deadlines, eenmalige grants en intrekking vóór de queue
bij firmware-scopeverlies. Optioneel verkeer kan de shadow-sessie niet via een
volle queue resetten. De product-kraanfabriek blijft gesloten.
[Contract en verificatie](M2-NATIVE-KRAANROUTE-20261025.nl.md).

- [Bron-CI 40143427322](https://github.com/dielessen/open_thermostat/actions/runs/40143427322): alle zeven softwarepoorten geslaagd.
- [HA-tag-CI 40144686119](https://github.com/dielessen/open_thermostat/actions/runs/40144686119) en [E32-tag-CI 40144686418](https://github.com/dielessen/open_thermostat/actions/runs/40144686418): alle toepasselijke controles en publicatie geslaagd.
- 728 native firmwaretests; 32 actuatorgrensgevallen ook onder strikte ASan/UBSan met lekcontrole. Die 32 zijn onderdeel van de native suite, geen extra unieke gevallen.
- 2.323 HA-gevallen per Core 2026.10.2/2026.10.3: 2.255 tests plus 68 subtests; nul fouten/errors/skips.
- Onafhankelijke bronreview, initiële pakketreview met 2.334 checks en definitieve review van de werkelijke tagpakketten geslaagd.
- Alle negen openbare downloads bytegelijk aan hun eigen tag-CI; alle 85 HA-bestanden ook gelijk aan de E32-companion en de bevroren Git-bron. Alle 740 bestanden in het E32-bronarchief exact Git.

Publieke HA-ZIP: `OpenThermostat-HA-0.4.0.dev44.zip`, 524122 bytes, SHA256
`5fc73341003dc32b4b363128e2de22fadebf805febb7cd4182876f113a0c3163`.

De E32-app is 2595888 bytes, SHA256
`11e0893edc5af87d37987b6fc9c92b6ba29df67009db98ea689ad04ce3257487`.
Het openbare E32-distributiearchief heeft SHA256
`3dde68451225c975a69030491ec9d143d7578feecda92752342b2f432ed93c17`.

### Aanvullende controle van de distributie

Het volledige E32-main/tag-ZIP is niet byte-reproduceerbaar. De werkelijke
app, ELF-identiteit en bron zijn gelijk; de distributie bevat daarnaast
buildtijdafhankelijke bytes in een niet meegekoppeld Arduino-object,
SPIFFS-metadata, bijbehorende checksums/receipts en ZIP-datums. Alle 41 uitgepakte
SPIFFS-bestanden zijn inhoudelijk gelijk. Het werkelijke tagpakket is afzonderlijk
aan 1.140 controles en een onafhankelijke definitieve tagreview onderworpen.
Openbare downloads zijn vervolgens exact met díe tagartefacten vergeleken.
Er is geen tag of download vervangen om een schijnbare gelijkheid te maken.

## Installatie en afzonderlijke nacontrole

| Controle | Vastgestelde uitkomst |
| --- | --- |
| HA | dev44/Core 2026.10.3, entry geladen en room/get shadow_ready |
| Bestanden | Alle 85 livehashes exact publieke ZIP en bevroren Git; apart opnieuw uitgelezen |
| Uitrol | 85 componentbestanden, één normale Core-herstart; geen tweede schrijfactie/herstart |
| Back-up | Verse CURRENT HA43-back-up: 84 componenten plus 10 projectpayloads; alle 94 hashes vóór/na schrijven en apart na herstart gecontroleerd |
| Configuratie | Actuele SOURCE/journal revisie5, digests en geen staged/pending behouden |
| Behoud | Instellingen, programma's, bindingen, 105 registryrecords/2 apparaten/1 entry/2 subentries, private pin-/producerselectie, netwerk/model/syslog behouden |
| Frontend | dev41/v41; v38/v35-aliases en HTTP200/hash gelijk; nul kaart-/resourcemigraties; handmatige kaarten, overige dashboards/panels behouden |
| ESP | Vijf verse numerieke metrics; uitgeschakelde RTC-temperatuur verwacht onbekend |
| Meetbron | Interne apparaattemperatuur blijft diagnostisch/profile_missing; geen bronwissel of automatische kwalificatie |
| TV02 | Waiting/stale en ongekwalificeerd; geen causale ACK, klepstand of regelbevoegdheid |
| E32 | Exact alpha28/3efb0a1/ELF/web behouden; reageert, idle en niet boot_pending; geen upload/herstart door deze uitrol |
| Uitgangen | Ketel, actuator en forwarding uit; EMS-TX/polls/testframes nul |

De back-up staat op
`/homeassistant/.openthermostat-backups/20261025-ha44-current5-install-owned/backup-20261025T002644271305Z`.
Manifest-SHA256:
`aa4cf2954f8a9a4d83aa8169c0186ee4b26a04d703f748014430361a66979ead`.
Dit is de verse HA43-back-up met actuele revisie5; de oudere HA40-back-up met
93 payloads is niet hergebruikt. Externe converter/helperbytes vallen buiten de
HA-componentuitrol en zijn niet als bekende bestandsback-up voorgesteld;
de private pin-/producerselectie is wel exact behouden.

De eerste voorcontrole stopte zonder enige wijziging omdat de eerder vastgelegde
SOURCE4 inmiddels5 was. De inhoudelijke vergelijking toonde uitsluitend een
15-daagse horizonverschuiving van één dag, plus revisie/digest; alle programma's,
overgangen, bases, policies en mappings waren gelijk. De dagwissel wordt sterk
ondersteund, maar de oorspronkelijke trigger is niet rechtstreeks geaudit.
De installatie bewaart daarom de actuele5 en forceert geen oude4 terug.

De afzonderlijke nacontrole maakte geen productie- of apparaatwijziging. Eigen
HTTP-/WS-sessies, cookies en handles zijn gesloten; geen scheduler of nieuwe
watcher/toegangsroute is toegevoegd.

## Wat blijft open?

E32alpha31 is gepubliceerd, **niet geïnstalleerd**. De eerdere alpha28-uploader
gaf reset6/TASK_WDT; taak/stack/oorzaak en een onderbouwde herstelroute zijn nog
onbekend. Er is geen seriële aansluiting. De module werkt; er is geen nieuwe
uitval als reden voor een flash aangenomen. Geen blinde OTA-/HTTPS-herhaling,
reboot, rollback, factoryflash of wipe uitgevoerd.

Normale firmware-MQTT-zendbedrading, gekwalificeerde product-SOURCE-fabriek,
geschikte kamerbron, oorspronkelijke causale kraanecho en fysieke stop-/flow-/
uitvalproeven blijven open. De externe converter/helperbytes zijn niet bekend
gemaakt door de HA-update. Pendelen, de oude updaterfout en de nieuwe
Shelly-/Xiaomi-drivers zijn niet als opgelost of geleverd geclaimd.

**English:** Both immutable releases are published. HA dev44 is installed with a
fresh 94-payload HA43 backup and an independent 85-file/settings/health postcheck.
Current configuration revision5 is preserved. E32 remains responsive on alpha28;
no firmware update or physical control was performed. Active heating qualification
and the earlier uploader-watchdog recovery remain open.

Bewijs: `out/combined-dev44-alpha31-20261025/`; afzonderlijke bron-/regressieproeven
blijven in `out/large-beta-wire-20261025/` bewaard.
