# WP03 — begrensde BLE-advertentiedecoder

20 oktober 2026. Private softwaretak; geen flash of fysieke sensoracceptatie.

## Werkelijke firmwarekoppeling

`BeaconTemperatureReader::parseAdvertisment` roept nu rechtstreeks
`control/BleTemperatureAdvertisement.h` aan. Diezelfde decoder draait in de
native tests; er staat geen gekopieerde decoder in de tests. Het resultaat
wordt pas na volledige validatie als één callback aan de bestaande kamerroute
gegeven. Battery-/humidity-only MiBeacon-objecten bevatten geen temperatuur
en vernieuwen daardoor de temperatuurbuffer niet.

Concrete eerdere fouten: AD-lengtes werden niet tegen de resterende buffer
gecontroleerd; de Xiaomi-minimumlengte 15 stond uitlezen van bytes 15 en
bij gecombineerde objecten 16/17 toe; service-UUID, volledig objecttype en
objectlengte werden genegeerd. Sign-/rangeconversie vertrouwde bovendien op
narrowing naar int16. Het nieuwe pad valideert vóór uitlezen en vernauwen.

- Container maximaal 255 bytes, eerst geheel controleren; geen heapallocatie
  of groeiende servicevector in deze decoder. Zero-terminator mag uitsluitend
  door zeropadding worden gevolgd; een kapotte suffix levert geen deelsample.
- Alleen de bestaande ATC-custom-naamfamilie (`ATC_…`, UUID 0x181A,
  exact 13 databytes) en `MJ_HT_V1` (UUID 0xFE95, product 0x01AA,
  MAC/dataflags, niet versleuteld, zonder capabilityextension, één object).
- Advertiseradres en ingebed adres moeten overeenkomen, met de juiste
  bytevolgorde per formaat. Dit is consistentiecontrole, **geen BLE-authenticatie**.
- Mi-objecten 0x1004/0x1006/0x100A/0x100D krijgen exact 2/2/1/4 bytes;
  onbekende objecten, dubbele passende services en conflicterende namen
  worden niet willekeurig als één bruikbare meting gekozen.
- ATC-temperatuur is signed big-endian, Mi-temperatuur signed little-endian.
  Eerst verbreden en valideren, dan omrekenen naar honderdsten. Sanitygrenzen
  −40..85°C, 0..100% vocht/batterij; dit zijn decodergrenzen, geen bewijs dat
  een specifieke sensor of zone dit volledige bereik ondersteunt.

## Referenties en afbakening

Lichtgewicht existing-solutionscontrole: behoud bestaande NimBLE-stack en
ondersteunde advertentieformaten. Geen nieuwe bibliotheek, HA-regelbrein,
plug-in, sidecar of scheduler nodig. Formaatfeiten gecontroleerd tegen:

- [ATC firmware-advertentieformaat](https://github.com/atc1441/ATC_MiThermometer#advertising-format-of-the-custom-firmware)
- [ESPHome ATC-parser](https://github.com/esphome/esphome/blob/dev/esphome/components/atc_mithermometer/atc_mithermometer.cpp)
- [ESPHome Xiaomi-parser](https://github.com/esphome/esphome/blob/dev/esphome/components/xiaomi_ble/xiaomi_ble.cpp)

Opgehaalde referenties blijven als gehashte snapshots in het uitvoeringsbewijs.
De ATC-READMEvoorbeeldregel heeft een inconsistente AD-lengtebyte; de
13 servicedatabytes zijn afzonderlijk in de daadwerkelijke ESPHome-parser
bevestigd, niet uit die voorbeeldlengte afgeleid.
Geen broncode uit die projecten gekopieerd. Fixtures zijn synthetisch op basis
van de gedocumenteerde wirewaarden, geen captures van Marks BLE-apparaten.

Dit voegt geen ondersteuning voor encrypted MiBeacon, ATC/pvvx-alternatieve
formaten, anonieme broadcasts, meerdere Mi-objecten of andere productmodellen
toe. Striktere weigering van zulke invoer is bewust; geen universele
achterwaartse devicecompatibiliteit claimen zonder captures/benchproef.

**Advertentieontvangst is niet automatisch een verse fysieke meting.** Herhaalde
advertenties/counters krijgen met deze wijziging geen nieuwe provenancegarantie;
per-bron samplecadans, replaybeleid, leeftijd en echte bronprofielen blijven
open werk. Oude Roomstatusflags/tijdvalidatie en HA-transport eveneens.

## Acceptatie

Reproduceerbaar: `pio test -e native` met de bestaande projectvenv.
De extra tests controleren beide signed/endianformaten, alle vier bestaande
Mi-objectcategorieën, iedere prefixafkapping, kapotte suffix, UUID/MAC/type/
lengte/rangefouten en 30.000 deterministisch seeded mutations/random inputs.
Sanitizerproef compileert dezelfde header/tests met ASan+UBSan en exacte
inputallocaties, zodat één byte buiten de aangeboden buffer detecteerbaar is.
Firmwarematrix en ongewijzigde E32-verifier moeten daarnaast slagen; resultaten
staan in de canonieke TaskFlow. Geen fysieke RF-, sensor- of ketelproef.
