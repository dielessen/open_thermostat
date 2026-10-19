# WP02 — passieve Classic-status en veldclassificatie

Softwarecontrole, 20 oktober 2026. Geen flash, nieuwe buscapture, ketel- of
HA-bediening. Fysieke board-/bus-/netwerkacceptatie blijft open.

## Geïmplementeerd

- Pure `BoilerCapabilities` onderscheidt waargenomen Classic, Plus, onbekend
  en tegenstrijdige families. Dat is geen fysieke protocolvrijgave.
- `ClassicBoilerMonitor` decodeert data uit bron08 van0x18/19/16/33/34,
  inclusief data voor een andere master. READs, requestecho's, vreemde bronnen
  en lege berichten tellen niet als meting.
- CRC en minimale/uitgebreide headerlengtes worden vóór veldtoegang getoetst.
  Deeltabelvelden moeten geheel in één fragment zitten; geen ongemerkt
  samenvoegen van delen uit verschillende meetmomenten. De24bitcounter aan
  een frame-einde gebruikt exact3bytes, geen onnodige vierde byte.
- Onbekend, expliciet ongeldig en verouderd zijn afzonderlijk herkenbaar.
  Onafhankelijke64bit monotone ontvangsttijd voorkomt herleving na een
  32bit-millisomloop. GET/readback vernieuwt metingen niet.
- Temperaturen worden intern in honderdsten°C bewaard; draad-/legacyunits
  worden expliciet geconverteerd. Negatieve buitenwaarden en sentinels zijn
  apart getest. Een gevraagde36°C uit0x1A vervangt nooit gerapporteerde0°C.
- Brander-/pomp-/ventilatorbits, debiet en stationaire tellers op deze Classic
  blijven `unreliable`; CV/tapwaterstatus uit boiler-statebits is `inferred`.
  Geen gasmeter, onafhankelijke vlam- of fysieke flowmeting suggereren.
- Bestaande Plusdecoderregistraties/veldoffsets blijven aanwezig. Legacy
  Plus-WRITEs worden nu bij onbekende, Classic of conflicterende familie
  geweigerd. E32 heeft daarbovenop nog altijd zijn harde compile-time-TXlock.

## Uitleesroute en grenzen

`GET /status/ems/telemetry` geeft bron-ID, adres, leeftijd, toestand, unit en
kwaliteit per veld. Dit is een nieuwe **read-only bronroute**, niet een
uitgevoerde HTTP-/hardwareproef. Geen schrijfproxy. Oude compacte status
blijft voor bestaande consumenten beschikbaar met protocolprofiel en
`physicalValidation=false`; betrouwbare Classicwaarden worden daarin in
legacyunits gespiegeld en verlopen. Onbetrouwbare gas/pomp/fan/debietwaarden
worden niet als vertrouwde legacywaarden aangeboden.

De uitgebreide metadata is bewust niet stilzwijgend aan het bestaande
MQTT-statusbericht toegevoegd. Transportbudget, v1schema en een nieuwe
consument horen bij WP03/04. Bestaande energie-/intervalproblemen zijn niet
met een nieuw label opgelost: die blijven WP07.

## Volledige inventaris is niet volledige pariteit

[boiler-field-parity.json](boiler-field-parity.json) classificeert **alle68**
door de HA-specialist geïnventariseerde boilerentiteiten, zonder vaste
huishoudelijke entity-ID's in de productcode:

- 13 `required+mapped` (bij CV/DHW expliciet afgeleid, geen onafhankelijke meting);
- 4 `optional+mapped`;
- 18 `unreliable_on_this_chain`, deels als ruwe diagnostiek aanwezig;
- 33 `not_yet_implemented`, waaronder optionele parameters/adminfuncties en
  energie-modelvelden voor WP07. Deze zijn niet stilzwijgend ondersteund.

42 van deze68velden hadden een gerichte actuele HA-state-read; de totale
specialistread omvatte daarnaast5gatewaydiagnoses. Registry-only is geen
actuele meetvalidatie. R15 als volledige product-/hardwarepariteit is dus
**niet afgerond**. Ontvangsttijd toont een recent ontvangen ketelbericht,
niet een onafhankelijk bewezen interne fysieke sensormeettijd.

## Bronbewijs

Protocolfeiten gecontroleerd tegen EMS-ESP tag3.8.6 boiler.cpp:
SHA256 `42505c773bcbf6631718abd517d61ee5dec9bcf429b2123d402a69ed5445503e`.
Alleen berichtfeiten zijn gebruikt; geen LGPL-implementatie gekopieerd.
De onafhankelijke HA-spike/bronbundle staat in het lokale uitvoeringsbewijs.

Native tests gebruiken zowel synthetische, onafhankelijk gespecificeerde
goldenframes als werkelijk vastgelegde CRC-geldige frames voor alle vijf
families en de bekende0P-status. Broncorpus-SHA256:
`8a45aa6f5184e60c67d1034ca02f42014c5af6eb9afcd4c4cb1a95dd81d26e64`.
Het =H-voorbeeld bewijst DHW, niet een complete CV-regelketen. Geen volledige
corpusreplay of nieuwe livecapture geclaimd.

## Uitgevoerde softwarechecks

- Native: **81/81 PASS** (bestaande66 +15 nieuwe cases), echte parserbron
  meegebouwd, niet vervangen door een mock.
- E32/ESP32/S3 firmwarebuilds: **3/3 PASS**. E32 ELF flash1.749.437 bytes,
  RAM64.416; generieke4MB flash1.700.957/1.703.936 bytes (nog2.979 bytes).
- E32 buildfs, ongewijzigde gecompileerde veiligheidsverifier en bestaande
  vijf foutinjectieproeven: **PASS**. Nog steeds geen project-UART-TX-pad.
- Eerste testlink miste productieparser door PlatformIO's standaard
  `test_build_src=false`; bronfilter en de officiële `test_build_src=yes`
  corrigeren dit. Geen productcode om tests te misleiden vervangen.

Logs en hand-off:
`/home/dielessen/artifacts/open-thermostat-build-20261020/taskflow.md`.
De generieke4MB-resourcegrens mag niet door een onbesproken partitieverandering
worden verborgen; vervolgfeatures richten zich primair op de E32.
