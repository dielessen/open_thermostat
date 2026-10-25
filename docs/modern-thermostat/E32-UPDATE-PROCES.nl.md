# Verplicht update- en acceptatieproces per E32-release

De volgende reguliere release mag pas worden gepubliceerd als de vorige E32-
release via de normale GitHub-updater is geïnstalleerd en onafhankelijk
gecontroleerd. Een build, HTTP202, volledige uploadbalk of opgeslagen
`boot_slot_selected` afzonderlijk is geen geslaagde oplevering. Een storing blijft
open totdat herstel en nacontrole zijn bewezen; niet als “bekende beperking”
doorschuiven naar de volgende reguliere release.

De actuele machineleesbare stand staat in `E32-UPDATE-GATE.json`.
`accepted: null` betekent dat nog geen volledige acceptatie volgens dit proces
is vastgelegd, niet dat eerdere updates nooit gelukt zijn. Alpha36 staat bij
invoering als pending; die toestand mag pas na de echte nacontrole veranderen.

## 1. Kandidaat en vorige acceptatie

Bewaar de laatste geaccepteerde tag met het SHA256-gebonden, geanonimiseerde
acceptatierapport. Houd de complete installer-/nacontrole-/back-upreceipts op de
bestaande beveiligde bewijsplek. Geen wachtwoorden, cookies of ruwe instellingen
in Git. Geen oude waarneming voor een nieuwe release hergebruiken.

Voor een nieuwe freeze moet de vorige pending-release zijn geaccepteerd. Zet
daarna uitsluitend de nieuwe kandidaat als `pending_tag`; behoud de vorige
acceptatie en receipt. Bouw en controleer alle software, bron-/licentiepakketten,
manifesten en werkelijke publieke bestanden zoals bij de bestaande releasegates.
Publicatie blijft kandidaatstatus; fysieke installatieacceptatie volgt afzonderlijk.

Vóór publicatie, ook bij handmatige publicatie na een CI-storing:

```
python3 scripts/verify_e32_update_gate.py --candidate v0.1.0-e32v2-alpha.N
```

De E32-publicatiejob hangt af van de browsergate die deze controle verplicht
uitvoert. Een ontbrekende of onvolledige vorige acceptatie, andere pending-tag,
beschadigde receipt of teruggaande versie blokkeert de opvolger. Gewoon bronwerk
en CI-tests mogen doorgaan terwijl een fysieke acceptatie openstaat.
Deze controle valideert vastgelegd bewijs; ze voert zelf geen hardwareproef uit.

## 2. Verse voorcontrole en behoud

Alle HA-/E32-beheer via de bestaande HA-agent. Controleer onmiddellijk vooraf:
werkelijke huidige versie/bron/ELF/web, bevestigd boot-slot, geen pending boot,
lopende update of geplande herstart; thuisnetwerk, geldige tijd en toegang;
werkelijke firmwarecatalogus en exact doelmanifest. Controleer SOURCE, instellingen,
programma's, bindings en geblokkeerde fysieke uitgangen tegen de werkelijke basis.
Geen historische basis forceren. Leg heapwaarden vast zonder een verzonnen grens.

Maak een verse beperkte back-up met nagelezen hashmanifest via de bestaande
methode. Bewaar de huidige image-/herstelidentiteit. Leg vast dat de inactieve
app wordt overschreven en welk herstel daadwerkelijk beschikbaar en getest is.
Native rollbackbeleid is geen garantie voor iedere stroom-/flash-/CPU-fout.
Bij tegenstrijdig of ontbrekend bewijs: geen installatie.

## 3. Eén expliciete native installatie

Indien nodig maximaal één `POST /updates/check`, daarna begrensd uitlezen van
het lokale resultaat. Geen herhaalde checks om een fout te verbergen. Leg vóór
mutatie tag, bron, firmware-/ELF-/webhash, back-up, basis en verwacht verloop vast.
Geef maximaal één `POST /updates/install` met de exacte gepubliceerde tag.
De E32 downloadt zelf `firmware.bin` en het manifest. Geen multipart `/ota`,
factory-/SPIFFS-image, gewijzigde partities, extra reboot of stille fallback.

Bewaar de oorspronkelijke HTTP-respons en het worker-/controlepuntverloop.
HTTP202 bevestigt toelating tot de worker. Download, checksum, native imagecheck,
onafhankelijke flash-readback en partitieselectie moeten aantoonbaar slagen.
Gebruik eindige polls en een vooraf vastgelegde eindtijd. Geen tweede commando
bij een onzekere respons. Houd instellingenwrites tijdens bootacceptatie bevroren.

## 4. Nieuwe boot en afzonderlijke nacontrole

De firmware herstart volgens haar bestaande beleid. Controleer de werkelijke
nieuwe boot, exacte tag/bron/ELF/web en bevestiging (`boot_pending=false`),
updater vrij, geen fout of nog geplande herstart. Observeer op twee afzonderlijke
momenten dezelfde nieuwe boot met stijgende uptime. Controleer alle bewaarde
instellingen-/programma-/binding-/SOURCE-identiteiten en alle geblokkeerde
uitgangen/TX-/poll-/testtellers. Alleen een geopende webpagina is onvoldoende.

Start vervolgens een afzonderlijke read-only nacontrole via de bestaande
HA-agent, zonder installaties of herstarts. Vergelijk onafhankelijk met het
publieke doelpakket én de voorcontrole. Bij iedere fout blijft de poort dicht;
geen blinde retry en geen gewone volgende release voordat herstel is bewezen.
Een onderzoek/herstelkandidaat is geen geaccepteerde productrelease en mag deze
regel niet stilzwijgend omzeilen.

## 5. Duurzame acceptatie

Bewaar een klein geanonimiseerd JSON-rapport in de repository, met exacte
identiteiten, oorspronkelijke admissionstatus, commandoaantallen, alle vereiste
checks en SHA256-verwijzingen naar installerreceipt, afzonderlijke nacontrole en
back-upmanifest. De volledige bronreceipts blijven beveiligd beschikbaar. Alle
checks moeten rechtstreeks uit die echte receipts worden afgeleid; onbekend
wordt niet true. Maak het rapport pas na de onafhankelijke controle.

Werk pas daarna `accepted` bij naar deze tag, receiptpad en receipt-SHA256;
zet `pending_tag` op null. Voer beide gate- en inventariscontroles uit, commit het
bewijs en werk het werkbord bij. De oude oorzaak mag alleen als gerepareerd
worden beschreven als dat oorzakelijk bewezen is. Een geslaagde native update
bewijst de native route; niet automatisch de afzonderlijke multipart-route.
