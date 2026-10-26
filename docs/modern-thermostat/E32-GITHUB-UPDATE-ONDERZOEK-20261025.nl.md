> Vervolg afgerond: alpha36 is via de native GitHub-route geïnstalleerd en
> afzonderlijk geaccepteerd. Zie [installatie en bewijs](INSTALLATIE-E32-ALPHA36-20261025.nl.md).
> Hieronder staat de voorafgaande routebeoordeling; de oude multipart-oorzaak blijft onbekend.

# E32: GitHub-update onderscheiden van bestandsupload

## Nieuwe waarneming

De begrensde HA-agentcontrole van 25 oktober 10:10:44 UTC bevestigt alpha31,
bron `659879e`, bevestigde boot (`boot_pending=false`), gelijke actieve en
opstartpartitie en geen lopende update/herstart. Er zijn geen firmwareacties
uitgevoerd. Het native controlepunt vermeldt:

- alpha28 / bron `3efb0a1` naar alpha31;
- `native_https_install_only`, `boot_slot_selected`, HTTP200;
- 2.595.888 ontvangen van 2.595.888 verwachte bytes.

Dezelfde omvang, doelversie, bron en webhash staan in het onafhankelijk opnieuw
gedownloade publieke alpha31-manifest. Alle vier native updater-/verificatie-/
catalogusbronbestanden zijn bytegelijk tussen alpha28 en alpha31. Dertien
onafhankelijke bron-/statusvergelijkingen slagen.

Dit bewijst dat de vastgelegde native poging de download, verificatie en
partitieselectie bereikte. Het is méér dan alleen een idle-status. Exacte actor,
HTTP-opdracht, tijdstip en volledige causale historische bootketen zijn niet
achteraf bewezen. Een huidig geldig alpha31-image en het checkpoint vormen geen
bewijs dat de oude multipart-uploadwatchdog gerepareerd is.

## Twee verschillende routes

`POST /ota` verstuurt een firmwarebestand via het beheerpad naar de E32.
De werkelijk vastgelegde alpha29-poging via die route mislukte op 24 oktober
na 16,36 seconden: curl56/HTTP000, daarna alpha28/reset6 (task-watchdog).
De betreffende taak en stack zijn onbekend. Deze route wordt niet blind herhaald.

`POST /updates/install` laat de E32 een eerder gecontroleerde gepubliceerde
GitHub-release downloaden. Committen alleen is niet voldoende: firmware en het
passende update-manifest moeten als release gepubliceerd zijn. De bron controleert
bord, layout, schema, checksum, image, readback en bootselectie. De nieuwe
automatische controle installeert niet en verandert die verificatiepoorten niet.

## Beoordeling voor vervolg

De SDK schakelt native bootrollback in; de applicatie bevestigt een nieuwe boot
pas na haar bestaande netwerk-/toegangs-/bestandssysteem-/UI-controles. Dit zijn
softwarevoorzieningen, geen reeds uitgevoerde fysieke herstelproef.
Een afzonderlijke HA-agentreview beoordeelt de native route op het nieuwe
bewijs en de huidige werkelijke basis. Alpha36 is al als onveranderlijke release
geverifieerd; bronwerk na die release hoort bij een volgende bundel.
Zolang de afzonderlijke review niet gereed is, wordt geen nieuwe
controle-/installatie-/herstartopdracht gegeven en geen herstel geclaimd.

Bewijs: `out/e32-remote-flash-recovery-20261025/`, met verse read-only agentcontrole,
publiek alpha31-manifest en `ROOT-NATIVE-RECOVERY-REVIEW.json`.
