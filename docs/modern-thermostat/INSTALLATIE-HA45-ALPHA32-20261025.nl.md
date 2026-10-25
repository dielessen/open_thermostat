# HA dev45 / E32 alpha32 — grotere voorbereidingsrelease

25 oktober 2026. Beide pakketten zijn gepubliceerd op bron
`3f12d8b63895b1b13202d34cc02c714f953aa2de`. **HA dev45 is geïnstalleerd; E32
alpha31 is behouden. Deze opdracht heeft geen E32-upload uitgevoerd.** De actieve
ketelbèta blijft NOT_READY.

**Afzonderlijke alleen-lezen nacontrole geslaagd op 25 oktober 03:09:24 UTC:**
alle 38 controles geslaagd. Opnieuw 85 livebestanden exact publiek pakket/Git
en alle 95 back-uppayloads gecontroleerd. De nacontrole schreef niets en
bevestigt dezelfde E32-boot met oplopende uptime. Root vergeleek de verse hashes
afzonderlijk met het publieke doel en de oorspronkelijke HA44-bron.

## Wat de bundel toevoegt

- Oorspronkelijke firmware-aanvraag → HA-grant → eenmalige opdracht, met eigen aanvraagvolgnummer, exacte scope en het kleinste oorspronkelijke deadlineplafond. Een vertraagd antwoord of herlabeling vernieuwt geen venster.
- Optioneel kanaalbeheer op de bestaande MQTT-verbinding/loop; callbackherintrede kan de inventaris niet wijzigen. Maximaal acht eigenaren kwalificeert geen installatie met acht kamers. De normale productfabriek blijft gesloten.
- Eén gedeeld klokwatermerk, actuele context/bron/verbinding en nonblocking socketwrite zonder retry. Partiële, late of onzekere IO trekt in vóór socketcleanup; er volgt geen nieuwe opdracht.
- De ACK-zonder-snapshotproef bereikt eerst de echte ACK-fase; vertraagde voorbereiding is getoetst. De productie-time-out van 90 seconden verandert niet. De eerdere incidentele CI-kameroorzaak blijft afzonderlijk onbekend.

[Contract, regressies en grenzen](M2-AANVRAAG-EN-KANAAL-20261025.nl.md).
Alle 23 voorbereide onderdelen, 279 bronverwijzingen en 31 producteisen behouden.
De nieuwe voorbereide kanaalroute vereist HA45; gewone v1-bediening blijft
compatibel met alpha28 en de daadwerkelijk waargenomen alpha31.

## Bron, pakketten en controle

[HA dev45](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev45)
en [E32 alpha32](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.32)
blijven onveranderlijke tags op dezelfde bron.

- [Hoofd-CI40153442030](https://github.com/dielessen/open_thermostat/actions/runs/40153442030): alle 7 softwarepoorten geslaagd.
- [HA-tag-CI40154877209](https://github.com/dielessen/open_thermostat/actions/runs/40154877209) en [E32-tag-CI40154877201](https://github.com/dielessen/open_thermostat/actions/runs/40154877201): alle toepasselijke software- en publicatiepoorten geslaagd.
- 767 native kerngevallen, 4 aanvullende echte lokale socketadaptergevallen. 75 hiervan ook onder strikte ASan/UBSan, lek- en debugiteratorcontrole; die 75 zijn geen extra unieke gevallen.
- 2.333 HA-gevallen per Core 2026.10.2/2026.10.3: 2.265 tests + 68 subtests, nul fouten/errors/skips.
- Alle 755 bestanden in het geleverde bronarchief exact Git. Alle 85 HA-bestanden exact Git en de E32-companion. Alle 9 publieke downloads exact hun EIGEN tag-CI; de 4 HA-assets ook exact de lokale/hoofd-CI-pakketten.
- Onafhankelijke definitieve bron-, hoofd- en daadwerkelijke tagpakketreview geslaagd; nul open pakketbevindingen.

HA-ZIP: 524901 bytes, SHA256
`6b600a44c14f8bdc03be3da78635a794cc70425098e94ec6f86ecdf721c12180`.
E32-app: 2605920 bytes, SHA256
`b777ba1031766ec6b24f183508b49a5e4f643dfb948d415a404d91c27231ad08`.
E32-distributie-ZIP: SHA256 `661728a4dcdacd26bc1a61aff85352579956251502a3e2b0e0317bac9247e548`.

Het volledige E32-hoofd/tag-ZIP is niet bytegelijk: 7 van 718 payloads verschillen
via 4 hulpopbouwtijdbytes, daarvan afhankelijke checksums en een SDK-prooflijst
waarvan alle 629 records met alle velden als multiset gelijk zijn. 717 ZIP-datums
verschillen. Werkelijke app, manifest, softwareverificatie, bron en ruwe SPIFFS
zijn exact gelijk. Het echte tagpakket is apart aan 1143 payloadcontroles en de
onafhankelijke eindreview onderworpen. Geen tag of download is vervangen om
schijnbare reproduceerbaarheid te creëren.

## Werkelijke installatie

| Controle | Uitkomst |
| --- | --- |
| HA | dev45/Core 2026.10.3, bron 3f12d8b, entry geladen en room/get shadow_ready |
| Bestanden | 85 livehashes exact publiek pakket/Git; root heeft ze afzonderlijk vergeleken |
| Back-up | Verse CURRENT HA44-back-up van 85 componenten + 10 projectpayloads = 95; alle hashes vóór/na schrijven opnieuw gelezen |
| Uitrol | 85 componentbestanden, precies 1 normale Core-herstart; geen project- of kaartmigratie |
| SOURCE | Revisie 5 en configuratie-/profiel-digests behouden, geen staged/pending |
| Behoud | Instellingen, programma's, bindingen, 105 projectregistryrecords/2 apparaten/1 entry/2 subentries en private pin-/producerSELECTION behouden |
| Frontend | dev41/v41 en v38/v35-aliases bytegelijk; handmatige kaarten/dashboards/panels/resources behouden |
| Diagnose | 5 verse numerieke ESP-metrieken; RTC-temp verwacht onbekend; interne sensor en wachtende TV02 blijven ongekwalificeerd |
| E32 | Alpha31/source659879e/ELF045dfe53/web6ec3 behouden, idle/no boot_pending; nul firmwareacties door deze uitrol |
| Fysieke grens | Ketel/kraan/forwarding uit; EMS-TX/polls/testframes nul; Tado blijft actief |

Verse HA44-back-up:
`/homeassistant/.openthermostat-backups/20261025-ha45-current5-install-owned/backup-20261025T025752817339Z`.
Manifest-SHA256:
`ba206068e257968a68c35d7cb86126bfd417e570bfd8926c55b751cef092e801`.
De 95 payloads vervangen geen historisch bewijs; de oude HA43-back-up van 94 bestanden
is niet voor deze update hergebruikt. Externe converter/helperbytes blijven
onbekend en buiten de HA-schrijfscope; alleen hun bestaande private selectie
wordt als behouden bewezen.

## Wat openblijft

De verse alpha31-waarneming verschilde van de eerdere alpha28-momentopname en
stopte terecht de eerste voorcontrole. Huidige identiteit en configuratie zijn
apart beoordeeld voor de HA-only-update; alpha28 is niet teruggeforceerd.
[Waarneming en bewijsgrenzen](WAARNEMING-E32-ALPHA31-20261025.nl.md).
De uitvoerder/methode van de eerdere 31-installatie zijn niet vastgesteld.
De oorspronkelijke uploader-watchdogoorzaak en herstelroute blijven open;
alpha32 is gepubliceerd, niet door deze opdracht geflasht.

Geschikte oorspronkelijke kamermeting, gekwalificeerde product-SOURCE-fabriek,
causale oorspronkelijke kraanecho en fysieke flow-/stop-/uitvalproeven blijven
open. De software trekt nieuwe opdrachten in, maar bewijst geen fysieke sluiting
van een eerder ingestelde kraan. Pendelen, oude HTTPS-fout, Shelly/Xiaomi-drivers,
volledige PID-/leerkwalificatie en alle overige open roadmapvoorwaarden worden
niet als opgelost of geleverd geclaimd.

**English:** Both immutable preparation releases are published. HA45 is installed
with a fresh 95-payload HA44 backup; E32 alpha31 is preserved and no firmware action
was performed by this delivery. Original request correlation, guarded ownership,
shared clocks and nonblocking writes remain behind default-denied product
qualification. Physical feedback/stop tests and earlier updater recovery remain
open; active beta is NOT_READY.

Bewijs: `out/combined-dev45-alpha32-20261025/`; implementatie/regressies:
`out/large-beta-channel-20261025/`.
