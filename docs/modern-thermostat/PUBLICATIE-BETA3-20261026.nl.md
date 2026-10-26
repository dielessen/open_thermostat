# Gezamenlijke bèta gepubliceerd — 26 oktober 2026

E32 **v0.1.0-e32v2-beta.3** en HA **0.4.0b3** zijn gepubliceerd uit dezelfde
commit `996587da4a05c8a9de4a25a5b8ab3d9ed4c6f99a`. Beide zijn testreleases.
**Installatie en live nacontrole zijn in deze sessie niet uitgevoerd.**

## Software- en publicatiebewijs

- [E32-release](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-beta.3)
- [HA-release](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0b3)
- [E32-tag-CI](https://github.com/dielessen/open_thermostat/actions/runs/40294573407):
  PASS na herhaling van uitsluitend de afgebroken browserjob. De eerste poging
  bereikte de 15-minutenlimiet na ruim 11 minuten afhankelijkheidsinstallatie;
  die poging wordt niet als geslaagd voorgesteld.
- [HA-tag-CI](https://github.com/dielessen/open_thermostat/actions/runs/40294574045): PASS.
- Drie firmwareboards, native controles, bronreproductie, afzonderlijke
  handmatige compileerproef en browsers zijn gecontroleerd. De oorspronkelijke
  1.059 native gevallen en de echte logging-UDP-/NVS-/SDK-hooktest slagen.
- Op elk van Core2026.10.2/.3/.4: 2.450 HA-checks, geen fouten of overslagen.
- Alle zes openbare E32-assets komen overeen met het tagpakket. De aanvullende
  lokale payloadverifier doorstaat 1.249 controles; de CI met broncheckout 2.197.
- Alle vijf openbare HA-assets gecontroleerd; de component-ZIP bevat exact de
  verwachte 87 integratiebestanden. De optionele Zigbee-companion is niet geïnstalleerd.
- Firmware: 2.828.000 bytes; SHA256
  `1bffbffa5bb1e296d1257a370442de86ab04e932c0538e395b62232e3073c49b`.
- [Geanonimiseerd publicatierapport](release-publication/beta3-20261026.json).
  Uitgebreid lokaal bewijs: `out/release-beta3-20261026/`.

## Afgekeurde kandidaat en behouden beperkingen

De b2-kandidaat `07a9937` is niet gepubliceerd of geïnstalleerd. De uitgebreide
native CI ontdekte een fixture die EMS-syslog verwachtte zonder de standaard
uitgeschakelde EMS-bron te selecteren. De fixture kiest EMS nu expliciet;
de productstandaard blijft ESP-aan/EMS-uit. Beide b2-publicatieruns zijn
geannuleerd; de tags zijn behouden en niet verplaatst.

De gebruiker bevestigt dat zijn ketel geen digitale druksensor heeft. De huidige
warmteproefguard vereist die nog wel: modelgebonden aanpassing en passende
controle van de installatiedruk blijven open. Geen fictieve waarde of
warmtevrijgave toegevoegd. Fysieke ketel-/kraansturing en beide TX-routes blijven geblokkeerd.

## Installatie nog open

De bestaande native HA-specialist/beheertool is niet beschikbaar in deze
Codex-sessie; de documentsessietool biedt geen verbonden sessies. Er is geen
nieuwe live voorcontrole, back-up, installatie, herstart of nacontrole uitgevoerd.
Dit stelt geen verbindingsstoring van HA of E32 vast. De laatst eerder
geverifieerde basis blijft administratief beta.1 / HA0.4.0b1; actuele versies
moeten via de bestaande bevoegde beheerroute worden gelezen.

De opdracht voor gezamenlijke installatie blijft open. Volg het bestaande
[E32-updateproces](E32-UPDATE-PROCES.nl.md), met verse back-up, één native
GitHub-OTA en afzonderlijke nacontrole. De updatepoort blijft **pending beta.3**;
accepted beta.1 wordt pas na echte installatieacceptatie vervangen.
