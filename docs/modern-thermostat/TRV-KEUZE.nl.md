# Radiatorkranen (TRV's) in 1.0: welke route en welke kraan?

Keuzedocument voor de eigenaar, 31 oktober 2026. Besluit eigenaar: "aansturing
trvs moet wel echt in 1.0 komen". Bouwen in beta.24, na de overstap (beta.22)
en de UX-release (beta.23). Dit document bouwt niets; het legt de keuze voor.

## 1. Samenvatting

- **Advies: route A, Zigbee-kranen via Zigbee2MQTT.** Jouw Zigbee2MQTT draait
  al, en de TV02 werkt al zo. Er is ook al software die kranen een
  doeltemperatuur stuurt.
- **Advies voor de kraan: Bosch BTH-RA** (radiatorthermostaat II, Zigbee).
  - De klepstand is direct in te stellen (0–100 %) en wordt teruggemeld. Dat
    is nodig voor de terugkoppeling van kraanstanden naar de aanvoer.
  - De kraan neemt een externe ruimtetemperatuur aan en meldt de batterij in
    procenten.
  - **Budgetalternatief: Sonoff TRVZB**, ongeveer € 25–40. Die heeft een
    externe temperatuur en een open/dicht-begrenzing, maar meldt geen echte
    klepstand. De terugkoppeling wordt daarmee grover.
- **3 kranen** voor de 3 radiatoren boven (badkamer en 2 slaapkamers).
  - De TV02 blijft bruikbaar als reserve of in de eenvoudige doeltemperatuur-modus.
    Hij meldt alleen "batterij bijna leeg" en neemt geen externe temperatuur aan.
- **Kosten:** Bosch ongeveer € 60–80 per stuk, dus ongeveer € 180–240.
  Sonoff ongeveer € 75–120 voor drie. Adapters zitten er meestal bij.
- **Route B (Shelly BLU TRV direct via Bluetooth vanaf de E32)** is voor 1.0
  niet verstandig. Schrijven naar de kraan vereist een "bonded" verbinding.
  Het koppel- en versleutelproces is voor derden niet openbaar beschreven, en
  in de praktijk loopt alles via de Shelly BLU Gateway Gen3. Uitlezen kan de
  E32 al wel.
- **Zonder Home Assistant:** de E32 kan Zigbee2MQTT ook rechtstreeks via de
  MQTT-broker aansturen, zonder HA Core. Een herstart van HA raakt de kranen
  dan niet. Valt de hele HA-machine uit (de broker en Zigbee2MQTT draaien
  daarop), dan regelen de kranen op hun eigen sensor met de laatst bekende
  doeltemperatuur. De E32 blijft de ketel aansturen op zijn eigen
  Bluetooth-sensoren.

## 2. Route A: Zigbee-kranen via Zigbee2MQTT

| Kraan | Klepstand instellen | Klepstand gemeld | Externe temperatuur | Batterij | Bij uitval externe sensor | Prijs (indicatie) |
|---|---|---|---|---|---|---|
| **Bosch BTH-RA** | **Ja**: `pi_heating_demand` lezen/schrijven, 0–100 % | Ja | `remote_temperature`, minstens elke 30 min | % plus `battery_low` | Valt terug op de eigen sensor | € 60–80 |
| **Sonoff TRVZB** | Begrenzing: `valve_opening_degree` / `valve_closing_degree` (fw ≥ 1.1.4) | Nee, alleen aan/uit-status | `external_temperature_input` plus `temperature_sensor_select` | %, tot 24 uur vertraagd | Schakelt zelf naar de eigen sensor (`remote_source_offline`) | € 25–40 |
| **Danfoss Ally** | Nee | `pi_heating_demand` (alleen gemeld) | `external_measured_room_sensor`, elke 30 min tot 3 uur | % | Zet de externe waarde na 35 min of 3 uur uit | € 60–70 |
| **Aqara E1** | Nee | Nee | `external_temperature_input` (sensor = external) | % | Niet beschreven | € 45–60 |
| **TuYa TV02 (heb je al)** | Nee, alleen `heating_stop` (helemaal dicht) | Nee | Nee, alleen een kalibratie-offset | Alleen `battery_low` | n.v.t. | – |

**Wat dit betekent:**
- Voor wat we samen bedachten, kraanstanden die de aanvoer zo laag mogelijk
  houden, moet de E32 de klepstand kennen en liefst ook kunnen zetten. Dat
  kan alleen de **Bosch BTH-RA** volledig.
- Danfoss meldt de stand wel, maar laat zich niet sturen.
- Sonoff en Aqara regelen zelf op een doeltemperatuur. Daarmee kan de E32 alleen
  "deze ruimte warm, die niet" doen, niet de aanvoer verfijnen.
- Alle kranen behalve de TV02 accepteren een externe ruimtetemperatuur. De
  kraan regelt dan op de echte ruimtetemperatuur in plaats van op de warme
  lucht vlak bij de radiator. Dat is belangrijk voor een goede regeling.

## 3. Route B: Bluetooth-kranen direct vanaf de E32 (Shelly BLU TRV)

- De E32 leest de Shelly BLU TRV al (`src/control/ShellyTrvAdvertisement.h`).
  Elke 8 s komen doeltemperatuur, gemeten temperatuur, batterij en externe
  temperatuur binnen. De klepstand zit **niet** in die uitzending.
- **Schrijven** gaat via GATT-kenmerken die "Read, Write bonded" zijn: alleen
  over een gekoppelde (bonded) verbinding. De versleuteling en het koppelen
  zijn voor derden niet openbaar beschreven. Alle bekende integraties gaan via
  de **Shelly BLU Gateway Gen3**: HA via MQTT naar de gateway, en openHAB via
  de HTTP-RPC van de gateway. Een opdracht kan tot 60 s duren, omdat de kraan
  batterij spaart.
- **Conclusie:** route B betekent ofwel een niet-gedocumenteerd koppelproces
  nabouwen in de E32 (risico), ofwel toch een gateway die van een andere
  partij afhangt. Dat is niet geschikt voor 1.0. Mogelijk later, als Shelly
  het koppelen documenteert.

## 4. Uitval en terugval (afgesproken ontwerp, toegepast op route A)

- **Batterij:** waarschuwen bij ongeveer 20 % en bij geen contact (Reparaties
  en dashboard). Bosch, Sonoff, Danfoss en Aqara melden procenten; de TV02
  alleen "laag".
- **Een kraan valt weg:** de ruimte blijft meetellen ("beperkt") zolang er
  een andere temperatuurbron is. Alleen dichtknijpen kan dan niet meer. Bij
  een lege batterij gaan de meeste kranen open, dus de ruimte wordt eerder te
  warm dan te koud.
- **Geen meting meer:** de eigen warmtevraag van de ruimte stopt na 30 min,
  er volgt een melding, en de E32 stookt nooit blind.
- **Advies per kraanruimte:** een losse Bluetooth-sensor op de E32, en een tip
  in de ruimte-instellingen als een ruimte op één apparaat leunt.
- **HA Core valt weg:**
  - Stuurt de E32 Zigbee2MQTT direct via MQTT aan, dan merken de kranen niets.
  - Gaat het via HA, dan regelen de kranen op de laatst gestuurde
    doeltemperatuur en hun eigen sensor; de externe temperatuur valt na 30 min
    terug op de eigen sensor.
  - De E32 blijft de ketel aansturen.
- **De hele HA-machine valt weg:** dan zijn de broker en Zigbee2MQTT ook weg.
  De kranen regelen dan zelf, op hun eigen sensor en de laatste doeltemperatuur,
  en de E32 stuurt de ketel op zijn Bluetooth-sensoren.
- **Nog een kanttekening voor jouw huis:** de vloerverwarming in de woonkamer
  heeft geen eigen zoneklep. Vragen alleen de slaapkamers warmte, dan krijgt
  ook de vloer warmte (de mengkraan begrenst dat). Echte scheiding van de vloer
  vraagt een zoneklep of pompsturing op de verdeler. Dat valt buiten deze
  keuze, maar is goed om te weten.

## 5. Wat er al is en wat beta.24 moet bouwen

**Er is al:**
- Doeltemperatuur naar een kraan per ruimte: `ha/.../e32_setting_device.py`.
  HA zet het doel van de E32 op het "instelapparaat" van de ruimte (ook een
  TRV), en ziet handmatig draaien als een tijdelijke aanpassing.
- Warmtevraag per ruimte en aanvoer op basis van het grootste tekort:
  `src/control/FlowDemand.h` en `src/control/FlowPolicy.h`.
- Een voorbereid actuatortransport, bewust uitgeschakeld
  (`actuator_output_enabled: false`):
  - `src/control/ActuatorChannel.h`, `ActuatorChannels.h`, `ActuatorDispatch.h`,
    `ActuatorIntent.h` en `ActuatorScope.h`;
  - `ha/.../actuator_receiver.py` en `actuator_wire.py`;
  - `ha/.../v1_profile_c.py` (doeltemperatuur-actuator met controle op de
    TV02-modus).
- Het uitlezen van de TV02 via Zigbee2MQTT (`ha/.../original_tv02.py`, alleen
  diagnose) en van de Shelly BLU TRV via Bluetooth
  (`src/control/ShellyTrvAdvertisement.h`).

**Beta.24 moet bouwen:**
1. **Per ruimte kranen koppelen** in het ruimteplan: welke kranen, het type
   (Bosch/Sonoff/…) en de modus (klepstand of doeltemperatuur). Een blok
   "Radiatorkranen" op de ruimtepagina (E32 en HA, past in de beta.23-indeling).
2. **Regeling per kraan:**
   - een ruimte met warmtevraag gaat open, de stand naar rato van het tekort;
   - een ruimte die warm genoeg is, knijpt dicht;
   - minimaal schakelen, voor de batterij;
   - een kalklos-beweging, bijvoorbeeld wekelijks.
3. **Externe temperatuur** naar de kraan, binnen de vereiste termijn:
   Bosch ≤ 30 min, Danfoss ≤ 30 min of 3 uur, Sonoff "op tijd".
4. **Terugkoppeling van de kraanstanden naar de aanvoer:**
   - staan alle open kranen deels dicht, dan omlaag;
   - staat één kraan volledig open en blijft die ruimte koud, dan omhoog;
   - binnen de harde grens (60/55 °C).
5. **Batterij, geen contact, "beperkt"**, Reparaties en dashboard, volgens
   §4 hierboven.
6. **Bij voorkeur:** de E32 publiceert direct naar
   `zigbee2mqtt/<kraan>/set`, zonder HA Core (zie §1). De bestaande
   veiligheidslaag van het actuatortransport, met scope, lease en grant,
   blijft daarbij de poortwachter.
7. **Tests:** een nagebootste Zigbee2MQTT-kraan (klepstand, batterij, uitval,
   trage reactie), een soak-scenario met 3 kranen, faaltests voor batterij leeg
   en voor een kraan die niet reageert, browsertests van de ruimtepagina, en
   een bijgewoonde proef met jouw kranen.

## 6. Wat jij fysiek moet controleren

- **Merk en type van de radiatorkranen** (de afsluiter, niet de knop). Het
  staat meestal op de ring onder de knop: Danfoss (RA, RAV, RTD), Heimeier,
  Oventrop, Comap, Giacomini, Honeywell.
- **De schroefdraad:** de meeste moderne afsluiters hebben **M30 × 1,5**. Bosch
  en Sonoff leveren adapters mee voor onder andere Danfoss RA, RAV en RAVL.
  Bij een afwijkend type is een losse adapter van een paar euro nodig.
- **Ruimte rond de kraan:** ongeveer 9 cm lengte, en geen kast of gordijn
  ervoor (anders heb je de externe temperatuur nog harder nodig).
- **Bereik van je Zigbee-netwerk boven:** de kranen zijn eindapparaten en
  hebben een router in de buurt nodig, zoals een Zigbee-stekker of -lamp.
- **Badkamer:** is het een handdoekradiator, kijk dan of er een
  thermostatische afsluiter op zit of alleen een handkraan. Een handkraan
  moet eerst vervangen worden.

## 7. Bronnen

- [Zigbee2MQTT: Bosch BTH-RA](https://www.zigbee2mqtt.io/devices/BTH-RA.html):
  `pi_heating_demand` lezen/schrijven, `remote_temperature` "required at least every 30 minutes".
- [Zigbee2MQTT: Sonoff TRVZB](https://www.zigbee2mqtt.io/devices/TRVZB.html):
  `valve_opening_degree` / `valve_closing_degree` (fw ≥ 1.1.4), `external_temperature_input`, `remote_source_offline`.
- [Zigbee2MQTT: Danfoss Ally 014G2461](https://www.zigbee2mqtt.io/devices/014G2461.html):
  `external_measured_room_sensor` (30 min / 3 uur), `pi_heating_demand` alleen gemeld.
- [Zigbee2MQTT: Aqara E1 SRTS-A01](https://www.zigbee2mqtt.io/devices/SRTS-A01.html).
- [Zigbee2MQTT: TuYa TV02](https://www.zigbee2mqtt.io/devices/TV02-Zigbee.html):
  geen klepstand en geen externe temperatuur, alleen `battery_low`.
- [Shelly BLU TRV, BLE-API](https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/trv/):
  "Read, Write bonded", BTHome elke 8 s zonder klepstand.
- [Shelly BLU Gateway Gen3, BluTrv-RPC](https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen3/ShellyBluGwG3).
- [openHAB: BLU TRV via de gateway](https://community.openhab.org/t/how-to-integrate-shelly-blu-trv/170245):
  opdrachten tot 60 s.
- [Home Assistant community: BLU TRV via MQTT en de gateway](https://community.home-assistant.io/t/new-shelly-trv-blu-integration/777837/61?page=5).
- [Sonoff TRVZB productpagina (NL)](https://sonoff.tech/nl-nl/products/sonoff-zigbee-thermostatic-radiator-valve):
  prijs en firmware ≥ 1.4.4 aanbevolen.
- [Expert4house: thermostatische kranen](https://www.expert4house.com/nl/thermostatische-kranen):
  prijsindicatie.

Prijzen zijn indicaties van oktober 2026 en kunnen per winkel verschillen.
