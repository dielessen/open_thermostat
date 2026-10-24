# HA dev38 geïnstalleerd; E32 alpha29 gepubliceerd, upload mislukt

Gecontroleerd op 24 oktober 2026. Bevroren releasebron: `d131c503f42e6b834a0815db8384983a7fc1b46f`.

| Onderdeel | Gepubliceerd | Werkelijk geïnstalleerd |
| --- | --- | --- |
| Home Assistant | 0.4.0.dev38 | dev38, Core 2026.10.3; alle 83 bestanden exact gecontroleerd |
| E32 | v0.1.0-e32v2-alpha.29 | alpha28, bron `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f` |

De oorspronkelijke-rapportdiagnose is robuuster bij vertraagde metadata en tijdelijke
registrywijzigingen. EN/NL-meldingen en frontend dev38/v38 zijn geleverd, met een
v35-compatibiliteitsalias. TV02 staat diagnostisch op wachten; daadwerkelijke nieuwe
ontvangst, causale kraanbevestiging en fysieke regelkwalificatie zijn niet bewezen.

## Controle en publicatie

2189 regressiegevallen per Core 2026.10.2 en 2026.10.3, vier browserregressies en
alle toepasselijke softwaregates geslaagd. Onafhankelijke bron- en pakketreview
uitgevoerd. De automatische publicatiestap faalde vóór publicatie wegens oude
versieheaders in release notes. De publicatietekst is gecorrigeerd en gevalideerd;
de ongewijzigde CI-pakketten zijn daarna voor het eerst handmatig gepubliceerd.
Negen werkelijke publieke downloads zijn exact vergeleken. De mislukte
publicatiejobs worden niet als geslaagde volledige pipelines voorgesteld.

Een aanvullende repositorycontrole valideert beide release-noteversies vóór de
release-inventariscontrole. Deze toolingwijziging volgt na de bevroren release;
ze verandert de gepubliceerde pakketten niet.

## Werkelijke installatie-uitkomst

Een verse back-up van 93 bestanden is vóór wijzigingen en na afloop gecontroleerd.
SHA256 van het hashmanifest:
`21f3378a182a5d0ec55077b8413fbf572fd81f8626a3d16977b308d223e7e65c`.
Instellingen, programma's, koppelingen, 105 registryrecords, SOURCE-revisie 4 en
pins/producer zijn behouden. De HA-specialist voerde installatie en onafhankelijke
nacontrole uit via de bestaande methode.

Precies één app-only POST naar `/ota`, 16:58:04–16:58:21 UTC, mislukte na
16,36 seconden met curl 56/HTTP 000. Er was geen geldige HTTP-respons en geen
waargenomen alpha29-boot. De module herstartte en draait alpha28. De onafhankelijke
nacontrole geeft resetcode **6: task-watchdogreset**. Taak, stack en grondoorzaak
zijn onbekend; startupregels waren al uit de RAM-ring verdwenen. Een oude inhoud
van een hergebruikt responsbestand is uitgesloten als uploadbewijs.

Er is geen tweede upload, expliciete herstart of rollback uitgevoerd. Een alpha29-
boot of rollback is niet bewezen. De huidige lege updaterfout en idle-status
beschrijven alleen de toestand na herstart. De native HTTPS-checkpointregistratie
is geen registratie van deze legacy `/ota`-upload.

## Vervolg met hoogste prioriteit

1. Offline de geïnstalleerde `/ota`-afhandeling, synchrone flashbewerkingen en
   watchdog/yieldgedrag onderzoeken. Bekende grootte wordt gecontroleerd, maar
   `esp_ota_begin` ontvangt nog `OTA_SIZE_UNKNOWN`. Dat is een onderzoekspunt,
   geen bewezen oorzaak. De multipart-parser heeft zelf al wachtmomenten; alleen
   een ontbrekende yield in onze callback bewijst dus geen starvation.
2. Een onderbouwde herstelroute en onafhankelijke review afronden vóór een nieuwe
   installatiepoging. Geen blinde retry of native HTTPS-proef.
3. Oorspronkelijke bronontvangst en de bestaande B04–B14-praktijkvoorwaarden
   afronden vóór actieve ketel-/kraanproeven. Tado blijft regelaar; alle fysieke
   uitgangen, EMS TX, polls en testframes blijven geblokkeerd/0.

Het eerder in grafieken waargenomen pendelen is niet verklaard. Warmwatercorrelatie
is een aanwijzing, geen oorzaakbewijs of reparatieclaim. De gebruiker kent de
warmwatertijden niet en meldt dat het nu weer goed lijkt.

Bluetooth voor Shelly/Xiaomi en zelfstandige E32-regeling blijven gepland;
deze onderhoudsrelease levert daarvoor geen werkende drivers.

Bewijs: `out/combined-dev38-alpha29-20261024/SAFE-POSTCHECK.json`,
`PUBLIC-PACKAGE-REVIEW.json`, `SOFTWARE-GATES.json` en `INSTALL-CHECKPOINT.json`.
