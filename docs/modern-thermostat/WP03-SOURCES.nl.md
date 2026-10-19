# WP03 — beperkte koppeling met bestaande firmwarebronnen

20 oktober2026. Private ontwikkeltak, geen deployment-/hardwarevrijgave.
Deze veranderingen zijn echte legacycallpathwijzigingen; de overige pure
v1-kern is daarmee nog niet als nieuwe HA/MQTT-regelketen aangesloten.

## Gewijzigd gedrag

- `HeatingController` herstart de hele E32 niet meer wanneer gedurende5minuten
  geen BLEtemperatuur binnenkomt. Bestaande kamers blijven ieder hun eigen
  actualiteit beoordelen; een gezonde andere kamer blijft onafhankelijk.
  Dit is geen implementatie van volledige nieuwe BLE-/HA-bronprofielen.
- De buitenbron is alleen de expliciete `outdoorSensor`-configuratie:
  `openweather`, `ems` of geen. Geen stille substitutie en geen fictieve−20°C.
- `BoilerController` ontvangt `optional<int16_t>`. Zonder gekozen geldige
  buitenwaarde remmen EMS/stooklijnafhankelijke relaisregeling normale
  verwarming, inclusief een aanvoeroverride. Stop kan nog worden aangevraagd.
  Status toont `inhibitionReason: outdoor_unavailable` en geen fictieve meting.
  Gewone relaisregeling zonder stooklijn krijgt geen nieuwe buitensensorplicht.
- Buitenverlies tijdens verwarmen trekt de normale vraag in; bronherstel
  zonder actuele startvraag verzint geen nieuwe start. Bestaande handmatige
  testmode en alle E32-TX/GPIO/reset-/forwarderblokkades zijn niet vrijgegeven.

## Concrete bronactualiteit

`EMS/OutdoorTemperatureSample.h` verwerkt alleen nieuwe boilerreports van
adres08: Classic0x19 en de reeds gebruikte0xD1-buitenwaarde, signed tienden°C.
Fragmenten moeten beide bytes bevatten. Requests/andere bron/ander veld
verversen niets. Sentinels/outliers worden niet bruikbaar. Behoud64bit leeftijd,
begrensd op180seconden; `EmsController.getOutdoorTemperature` leest dat sample,
niet een onbeperkt oude optionele statuswaarde. Dit is geen Classicwrite-GO.

`WeatherObservation.h` gebruikt OpenWeathers werkelijke `dt`-observatietijd,
niet alleen HTTPontvangst. Geldige Celsiusnumber en integerUTCdatum vereist;
bool/string/ontbrekend/uitbijter/toekomstige of≥1uur oude observatie afgewezen.
Leeftijd bij ontvangst plus monotone looptijd blijft behouden: een nieuwe GET
van oude data geeft geen nieuw uur geldigheid. Zonder vastgestelde kalender
in2000..2099 geen acceptatie. Dit is alleen een klokplausibiliteitsgrens,
geen volledige NTP-/RTCvertrouwensvalidatie. De toekomstige supervisor moet
zijn expliciete tijdvalidatie en gekozen degradedpolicy nog aansluiten.

OpenWeathergetters verlopen het sample ook zonder nieuwe HTTPantwoorden;
APIsecret/locatie worden niet meer door de constructor gelogd. De bestaande
HTTPclient/APItransportroute, diagnostische payload en legacy UI zijn hiermee
niet volledig herontworpen of security-/meetintegraal vrijgegeven.

## Bewijs en grenzen

`wp03-runtime-sources.log`:114/114 nativePASS; acht nieuwe gevallen toetsen
de echte BoilerController met optionele bron en de echte EMS-/weatherdecoder.
`wp03-bounded-json.log`:118/118 na vier aanvullende parsergevallen. Baseline-
BoilerControllergevallen voor relais/preheat/EMS/override blijven groen.
De historische Room-gemiddeldetests bevatten nog een nagebouwde berekening;
noem die niet een nieuwe volledige Room-runtime-/HAbronproef.

Niet opgelost/geclaimd: volledige sourceprofiel-GUI, echte HAobservatietransport,
volledige BLEbronprovenance (aanvullende framevalidatie: [WP03-BLE](WP03-BLE.nl.md)),
alle per-veld Plusstatusactualiteit, oude Roomstatusflags/
tijdvalidatie, actuatorreconciliatie, onafhankelijke stop/naloop, minimumflow,
volledige EMS-ESPpariteit, security/onboarding/OTA, volledige WP03acceptatie.
Stoprequestsoftware ≠ fysieke stop van een vastgelopen controller/ketel.

Rollback: aparte broncommit(s) op de private WP03tak terugdraaien; main/alpha
blijven onveranderd. Geen bestaande installatie of configuratie gemigreerd.
