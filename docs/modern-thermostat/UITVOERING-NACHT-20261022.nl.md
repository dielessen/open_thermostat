# Doorlopende uitvoering — actuele werkvolgorde

Geactualiseerd 23 oktober 2026. De oorspronkelijke nachtvolgorde en alle
historische checkpoints zijn ongewijzigd bewaard in
`out/plan-audit-20261023/UITVOERING-NACHT-20261022.nl.md.before`.

De enige actuele uitvoerlijst is [WORKBOARD §6](WORKBOARD.nl.md#6-werkpakketten-en-eerstvolgende-uitvoering).
Het [masterplan](PLAN.nl.md) bewaart alle 31 eisen; de
[release-inventaris](BETA1-RELEASE-INVENTARIS.json) voorkomt vergeten voorbereid werk.

- Basis alpha17/dev23 is geleverd en gecontroleerd.
- Ontvangstdiagnose/Keteltest/rapport is nieuw gebouwd/getest, nog niet geleverd.
- Werk door naar één eerste bèta met gegevensontvangst én begrensde start/stop.
- Eerst productie-meetprofiel/actuator/supervisor/proef-/Classic-zendpad en concrete
  fysieke voorwaarden afmaken; daarna één gezamenlijke freeze/verificatie/uitrol.
- Bestaande supervisor-/vloer-/comfort-/CSV-/modelcode meenemen en grenzen zichtbaar
  houden. Geen nieuwe F9/F10/P2-stage vóór M2; geen functie verliezen door editorafbouw.
- Software gebouwd, geleverd en fysiek bewezen afzonderlijk aftekenen.
- Vragen bewaren voor later. Eén afhankelijk fysiek onbekend punt blokkeert geen
  onafhankelijk bronwerk. Geen losse tags/updates per correctie.
- HA-installaties via bestaande bevoegde agent met back-up en nacontrole.

Er wordt door dit document geen eigen nachtjob, watcher of scheduler gestart.
