# Updatediagnose — controlepunten vóór de verificatiestappen

25 oktober 2026. Bronwerk voor de volgende grotere bundel na HA46 / alpha33.
Geen nieuwe release, firmware-installatie of herstelproef door deze wijziging.
De geverifieerde productie blijft HA46 / E32 alpha31.

## Wat verandert

De bestaande automatische updater bewaarde één algemene fase `verifying` voor
vier verschillende bewerkingen. Dezelfde begrensde NVS-journal bewaart nu ook
vóór iedere bewerking één controlepunt:

| Controlepunt | Betekenis |
| --- | --- |
| `before_hash_verification` | Vóór controle van de streaming firmwarechecksum |
| `before_image_validation` | Vóór native `esp_ota_end`-imagevalidatie |
| `before_flash_readback` | Vóór onafhankelijk teruglezen en hashen van de app-partitie |
| `before_boot_slot_selection` | Vóór kiezen van de opstartpartitie; nog niet gekozen |

Alle bestaande verificatiepoorten blijven verplicht en in dezelfde volgorde.
Een fout bereikt de volgende bewerking niet. Een exception of herintrede in de
nieuwe lokale callback trekt de overdracht blijvend in; geen automatische retry.
De gewone aanroep zonder observer behoudt dezelfde backendcontroles.

De bestaande statusroute toont de laatst bevestigde opslag, in Nederlands en
Engels. Lezen schrijft niets en start geen update. Bij een opslagfout blijft de
laatste bevestigde momentopname zichtbaar met `checkpoint_save_failed`; latere
fasen krijgen geen fictieve opslagclaim. De journal wordt niet per chunk beschreven:
hoogstens vier extra vaste checkpoints per volledige automatische verificatie.
Geen extra payloads, timers, watchers, workers, routes of abonnementen.

Schema 1 en de blobgrootte van 164 bytes blijven gelijk. De oorspronkelijke
stagenummers 1–5 veranderen niet. De nieuwe firmware leest oudere checkpoints;
een oudere reader kent de nieuwe stagenummers niet en kan die als onbekend
verwerpen. Dat is geen firmware- of instellingenmigratie. Handmatige uploads
blijven buiten deze journal.

## Wat dit bewijs betekent

Een opgeslagen controlepunt bewijst alleen tot waar die opslag is bevestigd.
Het bewijst niet dat de daaropvolgende bewerking begon, voltooid is of de reset
veroorzaakte. Een normale afgehandelde fout schrijft nog steeds `error`; een
reset kan het laatste voorafgaande checkpoint achterlaten. Ook
`boot_slot_selected` is geen bevestigde installatie, boot of rollback.

De historische alpha28-watchdogoorzaak, HTTPS-afwijking en herstelroute blijven
onbekend. Deze wijziging is gerichte instrumentatie voor later onderzoek;
zij rechtvaardigt geen blinde nieuwe upload of nieuwe fysieke bevoegdheid.

## Verificatie

- 782 native gevallen geslaagd; negen nieuwe OTA-/journalgevallen.
- 40 updater-/checkpointgevallen onder ASan/UBSan, lekcontrole en verplichte
  stop bij een sanitizerfout. Deze 40 zijn een subset van de 782.
- E32-compile geslaagd; geen uitrol of herstelclaim.
- 24 updaterbrowsergevallen in Chromium met gesimuleerde HTTP, inclusief vier
  nieuwe fasen in beide talen op 320px en behoud van open details zonder POST.
- Vier algemene taal-/schermprofielen geslaagd.

De eerste nieuwe Nederlandse browserassertie vond verkeerd gedecodeerde
accenten in de bestaande synthetische testpagina. Die miste de UTF-8-meta die
het echte `index.html` al heeft. De fixture is gelijkgetrokken; de oorspronkelijke
foutuitvoer blijft bewaard. Dit was geen aangetoonde firmware-tekencoderingsfout.

Bewijs: `out/update-verification-checkpoints-20261025/`. De bestaande release-
inventaris behoudt alle 23 onderdelen en alle 31 eisen; fysieke B04–B14-poorten
blijven open waar hun oorspronkelijke acceptatie nog ontbreekt.

**English:** The existing bounded update journal gains four pre-operation
checkpoints: checksum, native image validation, independent flash readback and
boot-slot selection. They describe the last confirmed save, not successful
execution or a reset cause. Verification order, rejection gates and read-only
status semantics remain intact. This is source preparation for the next bundle;
no firmware update, retry, recovery or physical qualification was performed.
