# Testerpakket: OpenThermostat 1.0

Je bent de eerste die OpenThermostat installeert zonder dat de schrijver erbij is, en de eerste met een **Nefit TopLine** en
echte radiatorkranen. Dat levert twee dingen voor 1.0 op: (1) de installatiegids **tot het eind volgen zonder hulp** en (2)
de **kranen op echte hardware**. Elke vraag die je aan Mark zou stellen is een gat in de gids: schrijf hem op. De overname van
de ketel is altijd jouw eigen beslissing.

## 1. Wat je nodig hebt

- Een **BBQKees E32 V2**, een USB-C-datakabel en een computer met Chrome of Edge; een **EMS Classic**-ketel (een TopLine is dat
  normaal). Blijft de pagina **Ketel** leeg terwijl **Boiler bus (EMS) on** aanstaat: meld dat meteen (waarschijnlijk alleen EMS+,
  dat komt in 1.1).
- **Home Assistant 2026.10.0 of nieuwer**, een MQTT-broker (Mosquitto-add-on) met de MQTT-integratie en **HACS**;
  Zigbee2MQTT alleen als je kranen daaraan hangen (ZHA en andere integraties lopen via Home Assistant).
- Kamersensoren (in Home Assistant of Bluetooth), je radiatorkranen en een telefoon voor foto's.
- **Versies:** E32-firmware **1.0.0** (tag `v1.0.0-e32v2`) met HA-integratie **1.0.0** (tag `ha-v1.0.0`);
  Mark meldt wanneer ze gepubliceerd zijn. Het is een gewone release (geen pre-release): voeg `https://github.com/dielessen/openthermostat-ha`
  toe als custom repository in HACS (type Integration) en kies **Download**; de **Pre-release**-schakelaar is niet nodig.
  Zie je de nieuwste versie nog niet, kies dan **Update information** bij de OpenThermostat-regel in HACS.
- **Tijd:** ± 1 uur E32 en ± ½ uur Home Assistant als niets hapert, daarna 1–2 weken meekijken. De E32-pagina's volgen de
  taal van je browser (wisselen kan onderaan elke pagina); de gids noemt de Engelse namen.

## 2. De volgorde, en de documenten die je opent

1. [FIELD-TESTER.md](../FIELD-TESTER.md): lees het (10 min) en print de kaart "Give control back to your thermostat"
   (sectie 4). Maak een Home Assistant-back-up en fotografeer en label de bedrading van je thermostaat bij de ketel.
2. [INSTALL.md](../INSTALL.md), sectie 2 t/m 14, in volgorde, met [USER-GUIDE.md](../USER-GUIDE.md) erbij (voor
   [Radiator valves](../USER-GUIDE.md#radiator-valves)). Vraag niets aan Mark: loop je vast, noteer waar en ga zo ver als kan.
3. [INSTALL-CHECK.md](../INSTALL-CHECK.md): vink een kopie af tijdens het werk: per rij *gedaan*, *gedaan met moeite* of
   *vastgelopen*, met de tijd en wat niet klopte (een woord, een knop, een ontbrekende uitleg). Sla de rij over een update
   van een eerdere versie over. Dit is je rapport.
4. De dagen erna: de rijen **Daily summary**, **Yesterday** en **Morning check**, en het kranendeel (§4).
5. Stuur Mark de ingevulde kopie en je opmerkingen (§3).

**Veiligheid:** de E32 stuurt niets naar de ketel tot jij de overname bevestigt, en dat doe je alleen met iemand bij de
ketel. Sluit nooit twee thermostaten tegelijk aan. Terug naar je thermostaat: knop **Give control back to my thermostat** op
de pagina Rooms; werkt die niet: ketel uit, E32 stroomloos, draden terug (de kaart).

## 3. Vastleggen dat je de gids hebt gevolgd

Het criterium `install_guide` is `PASS` als iemand anders dan de schrijver de gids tot het eind volgde en elk gevonden
probleem is opgelost. Mark vult met jou dit formulier in (10 min) en legt het vast; jij hebt de repository niet nodig:

| Vraag | Wordt |
| --- | --- |
| Dag waarop je klaar was; E32- en integratieversie; HACS of ZIP | `--date`, verslag |
| Gids tot het eind gevolgd zonder hulp? ja / nee | `--followed yes` / `--followed no` |
| Elk punt waar je vastliep of twijfelde: sectie, wat er stond, wat je verwachtte | één `--problem "…"` per punt |
| Route (proefperiode of keteltest), ketelmodel, oude thermostaat (bus of aan/uit-contacten) | verslag |

```text
python3 -I tools/switchover/record_test.py --date 2026-11-20 install --followed yes --guide-commit <commit van de gids> --problem "sectie 8.3: de poort van de broker stond nergens"
python3 -I tools/switchover/record_test.py --date 2026-11-20 install --resolve 1 --fixed-in "commit <hash van de verbetering>"
```

`--date` staat vóór `install` en is de dag dat je klaar was, ook bij `--resolve`; `--guide-commit` is de commit van de
release-tag die je volgde (`git rev-parse --short <tag>`). Vastgelopen: `--followed no`; het criterium
staat dan op `FAIL` tot een nieuwe poging slaagt (`--followed yes`). `PASS` komt pas als elk punt een `--resolve` met
`--fixed-in` heeft. Je ingevulde checklist komt bij de releasebewijzen; stuur hem privé of als GitHub-issue met een titel
die met "Field test:" begint, zonder wachtwoorden.

## 4. De kranen: wat Mark wil leren

De kraansturing is alleen met nagebootste kranen getest. Kies per ruimte de kranen in het kamerformulier (Configureren →
Ruimtes → Ruimte bewerken of verwijderen → de ruimte → sectie **Radiatorkranen**). Ze sturen pas als **Radiatorkranen
aansturen** (*Valve control*) aan staat **en** de E32 de ketel zelf regelt: zet het dus pas na de overname aan, één ruimte
tegelijk, als je thuis bent, en geef een kraan één taak (instelapparaat of aangestuurde kraan, niet beide). Zigbee2MQTT-
kranen: de E32-login op de broker moet `zigbee2mqtt/#` lezen en `zigbee2mqtt/+/set` schrijven (INSTALL.md sectie 15).

Kijk een week, per kraan:
1. Zet hij binnen ± 1 minuut het doel van de ruimte, wordt de radiator warm bij vraag en koud als de ruimte warm is?
2. Meldt hij stand en batterij (**Stand radiatorkranen**, **Batterij radiatorkranen**)? Hoeveel procent gaat er per week af?
3. Valt hij weg (**Probleem radiatorkraan**, na 2 uur zonder bericht) en komt hij vanzelf terug na een herstart van Home
   Assistant, de broker of de E32?
4. Staan alle kranen van een vragende ruimte 10 minuten dicht en melden ze dat: stopt dan de ketelvraag?
5. Wordt een ruimte te warm, te koud of trager dan zonder kranen?

**Laat de schakelaar per kraanruimte 14 dagen onafgebroken aan staan**: dat meet het 1.0-criterium `trv_control`. Moet hij
uit, meld dat en waarom. **Stuur Mark:** merk en type, Zigbee2MQTT of ZHA/anders en de route die de pagina noemt, een
schermafbeelding van de kraanentiteiten van één ruimte over twee dagen (geschiedenis), de batterij na 1 en 2 weken, en
alles wat raar was.

## 5. Diagnose delen zonder geheimen

- **Home Assistant:** Instellingen → Apparaten en diensten → OpenThermostat → ⋮ → **Download diagnostics**. Het bestand laat
  wachtwoorden, sleutels, adressen en wifi-namen weg.
- **E32-back-up:** Systeem → Back-up en terugzetten, het vinkje **Wachtwoorden en Bluetooth-sleutels meenemen…** **uit**,
  dan **Back-up downloaden** (wel je ruimtenamen en instellingen). **E32-log:** Systeem → Diagnose en systeemlog → **Log
  downloaden**; lees hem eerst door.
- Deel **nooit** je E32-wachtwoord, een Home Assistant-token, het MQTT-wachtwoord of een back-up met wachtzin, en niets
  daarvan openbaar. Uitgelekt: wijzig het wachtwoord of trek het token in.
- Live meekijken (optioneel): alleen-lezen broker-login of token van een aparte gebruiker, FIELD-TESTER sectie 6.

**Dit moet Mark nog weten:** welke kranen (Zigbee2MQTT of ZHA), je huidige thermostaat (bus of aan/uit-contacten), je sensoren
per ruimte en je startdatum.
