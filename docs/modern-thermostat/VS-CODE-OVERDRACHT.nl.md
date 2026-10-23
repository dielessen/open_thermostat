# OpenThermostat — actuele overdracht

Bijgewerkt 23 oktober 2026 na volledige plan-/releaseherijking.

1. Lees [WORKBOARD](WORKBOARD.nl.md): de enige actuele afvinklijst met alle 31
   eisen, 11 fasen, 8 werkpakketten en B01–B14-releasechecklist.
2. [PLAN](PLAN.nl.md) bewaart het ontwerp en alle oorspronkelijke acceptatie.
3. [Release-inventaris](BETA1-RELEASE-INVENTARIS.json): 23 voorbereide onderdelen,
   75 bronverwijzingen met hashes. Alles blijft in de eerste bètabasis, ook
   begrensde code die nog niet als complete productfunctie is aangesloten.

## Actuele bron en installatie

- Geïnstalleerd/gecontroleerd: E32 alpha17 + HA dev23, bron `86f99a9`.
- Laat de bevroren `out/plan-batch-20261023` intact.
- Werk verder in `out/beta-boiler-20261023`, branch `work/beta-boiler-20261023`.
- `cebb0a2`: ontvangstdiagnose en Settings → Keteltest met downloadrapport;
  18 native, 43 GUI, 3 Chromiumviewports en normale E32-build geslaagd.
  Geen nieuwe release/installatie/fysieke ketelopdracht voor dit checkpoint.
- Planherijking voegt actuele PLAN/WORKBOARD en inventaris aan de kandidaat toe;
  de kandidaat-HEAD kan daardoor nieuwer zijn dan het ontvangstcheckpoint.

## Nieuwe bronstap binnen dezelfde bètabatch

Controller/status en beveiligde HTTP/webbediening zijn aangesloten op de geteste
proefpolicy. 57 native ASan/UBSan-gevallen en 3 echte Chromium-controlviewports
slagen; late responses/oud readback hervatten geen vraag, Stop blijft bereikbaar
bij een lopend startverzoek. Begin/finish-IO bewaart werkelijke voltooiing na
stop/deadline en verlangt terugmelding ná voltooiing van de nulopdracht.
De default E32 heeft geen beoordeeld proefprofiel of pollzender: acties blijven
geblokkeerd, geen nieuwe outputrechten. Vervolg nu op echte profiel-/poll-/Classic-
zenderintegratie en de overige B04–B09-punten, niet opnieuw HTTP/UI vanaf nul.
Geen nieuwe release/installatie/fysieke opdracht. Bewijs in
`out/beta-boiler-evidence-20261023/SERVICE-REVIEW.json`.

## Eerstvolgende uitvoering

Volg B04–B09 uit het werkbord: modelspecifieke productie-meetrapportproducent,
passende native kraanroute, bestaande supervisor aansluiten en eindige expliciete
ketelproef met vaste deadline/stopprioriteit/verse terugmelding. Classic-commandopad
en elektrische TX-/stopvoorwaarden apart beoordelen. De bestaande bronbench mag
niet op SOURCE worden gestart. Een kamer-save/metadata/HA-last_reported kwalificeert
geen fysieke meting. Huidige RTCGQ11LM-bron is diagnostische device_temperature;
alternatieve WSDCGQ11LM was laatst unavailable. Geen defect of sensorwissel verzinnen.

Geen nieuwe F9/F10/P2-stage vóór M2. Bestaande models/comfort-/vloer-/CSVcode
blijft behouden; niet opnieuw als ongeprogrammeerd opvoeren. Geen algemene TX-vlag
of Plus-commandoknop inzetten als Classic-proef. Pas na één bevroren complete
kandidaat volledige checks, publicatie en één gecoördineerde installatie.

## Werkafspraken en bewijs

HA-updates altijd via bestaande bevoegde HA-agent, met back-up en nacontrole.
Vragen voor later; onafhankelijk werk gaat door. Instellingen/programma/identiteit
behouden. Geen claim van onbeheerde verwarming, acht zones of leerwinst zonder
passende acceptatie. Geen eigen watcher/scheduler.

- Geleverde release: `out/combined-release-evidence-20261023/FINAL-REVIEW.json`.
- Nieuwe ontvangstbasis: `out/beta-boiler-evidence-20261023/CHECKPOINT.json`.
- Herijking: `out/plan-audit-20261023/AUDIT.json`.
- Oude overdracht en alle historische receipts blijven ongewijzigd bewaard als
  `out/plan-audit-20261023/VS-CODE-OVERDRACHT.nl.md.before`; niet als huidige
  installatie-/opdrachtstatus lezen. Oude vragen niet opnieuw als vereiste stellen.
