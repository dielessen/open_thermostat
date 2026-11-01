# Installatietest: iemand anders volgt de handleiding

Een van de eisen voor 1.0 is een installatiehandleiding die iemand anders kan
volgen. Geef deze lijst aan een tester met een BBQKees E32 V2, een EMS
Classic-ketel en Home Assistant (2026.10.0 of nieuwer), die het project niet
kent. De tester volgt alleen [INSTALL.md](../INSTALL.md) en de
[gebruikershandleiding](../USER-GUIDE.md). Help niet mee: elke vraag die de
tester stelt, is een gat in de handleiding.

Noteer per stap: **gelukt**, **gelukt met moeite** of **vastgelopen**, met
de tijd die het kostte en wat onduidelijk was (woorden, knoppen die niet
klopten, ontbrekende uitleg).

## Voor de tester begint

- [ ] De nieuwste E32-release en de bijbehorende Home Assistant-release staan
  klaar (de releasenotes noemen het paar).
- [ ] Een USB-C-datakabel en een computer met Chrome of Edge.
- [ ] Toegang tot de configuratiemap van Home Assistant (bijvoorbeeld de
  Samba share of File editor).
- [ ] De bestaande thermostaat blijft aangesloten: deze test schakelt niets
  over.

## Checklist

| # | Stap (hoofdstuk in INSTALL.md) | Klaar als |
|---|---|---|
| 1 | Firmware via USB (2) | ESPConnect of esptool meldt succes en de MD5 klopt met `FACTORY-CHECK.txt` |
| 2 | Eerste start en wifi (3) | Het setupnetwerk `OpenThermostat-xxxxxx` verschijnt, de E32 meldt **WiFi connected** en is op het thuisnetwerk bereikbaar |
| 3 | Inloggen en wachtwoord (4) | Ingelogd met `admin`/`admin`, eigen wachtwoord gezet onder **Settings → Password** |
| 4 | Tijdzone en ketelontvangst (5) | Tijdzone gekozen, **EMS bus enabled** aangevinkt, opgeslagen en herstart |
| 5 | Aansluiten op de ketel (6) | De pagina **Boiler** toont binnen enkele minuten aanvoer- en retourtemperatuur |
| 6 | Bluetooth-thermometer (7, optioneel) | De sensor staat onder **Your sensors** met een temperatuur |
| 7 | MQTT (8) | Broker en MQTT-integratie in Home Assistant draaien; **System → System log** op de E32 toont een verbinding met de broker |
| 8 | Integratie installeren (9) | `custom_components/open_thermostat/manifest.json` bestaat, Home Assistant is herstart |
| 9 | Integratie toevoegen en E32 verbinden (10) | **E32 connected** verschijnt; de E32 **Overview** toont **Home Assistant: connected** |
| 10 | Eerste ruimte (11.1) | De ruimte staat op de E32 en in Home Assistant, met een temperatuur |
| 11 | Weekprogramma (11.2) | In de weekplanner **Comfort**, **Eco** en **Nacht** gezet, een dag gekopieerd en opgeslagen |
| 12 | Huismodus en aanwezigheid (11.5) | **Configure → Home → Presence** ingesteld; de keuzelijst **House mode** werkt |
| 13 | Raamcontact (11.5, optioneel) | Raam open langer dan de vertraging: de ruimte pauzeert; dicht: hij gaat verder |
| 14 | Controle (11.6) | Het OpenThermostat-dashboard toont de ruimtes; **Heating problem** staat uit |
| 15 | Update via Home Assistant (13.3) | Bij een nieuwe release installeert de **Firmware**-entiteit hem zonder hulp |
| 16 | Back-up (14.1) | Een back-up gedownload, eventueel met wachtwoordzin |
| 17 | Diagnoseconsole (gebruikershandleiding) | `status` en `log 20` geven antwoord op de pagina **System → System log** |

## Na de test

- [ ] Alle stappen gelukt zonder hulp: de 1.0-eis "een handleiding die iemand
  anders kan volgen" is gehaald. Noteer naam/datum (of anoniem) en de versies.
- [ ] Elke opmerking wordt een verbetering in de handleiding, vóór 1.0.
- [ ] Bewaar de ingevulde lijst bij de releasebewijzen.
