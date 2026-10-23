# Oorspronkelijke TV02-kraanberichten

Status: producentbron voorbereid en getest; niet geïnstalleerd. B05 blijft open
voor de HA-consument, koppeling aan een doelopdracht, eigenaarschap, readiness en
fysieke proef zonder ketel. Deze producent verleent geen regelbevoegdheid.

De zelfstandige Z2M-extension `integrations/zigbee2mqtt/original-tv02.cjs` luistert
naar oorspronkelijke `deviceMessage`-events op `manuSpecificTuya`. Zij gebruikt
de bestaande MQTT-client en leest geen state-cache of HA-state. Een bericht
bevat uitsluitend de ondersteunde datapoints die werkelijk in dat ene event
aanwezig zijn. Een volgend bericht vult het vorige niet aan.

## Exacte apparaatbinding

De standaard apparatenlijst is leeg. Een latere gecontroleerde installatie moet
IEEE-adres, model `TV02-Zigbee`, fabrikant en endpoint expliciet vastleggen. De
producent controleert die binding opnieuw bij ieder bericht, naast een afgerond
interview en Zigbee-model `TS0601`. De eerste bron ondersteunt uitsluitend de
referentiefingerprints `_TZE200_hue3yfsn` en `_TZE200_lllliz3p`; andere TS0601-
apparaten, white-labelvarianten en andere TV02-fingerprints worden niet aangenomen
op grond van hun naam. De fabrikant/endpoint van de werkelijk aangesloten kraan
zijn in deze stap niet fysiek of live gekwalificeerd.

De native Z2M-loader maakt een tijdelijke kopie van iedere external extension.
Daarom is dit bestand zelfstandig, met uitsluitend Node-standaardmodules als
afhankelijkheid; de temperatuurproducent hoeft niet mee geladen te worden.

## Ondersteunde oorspronkelijke datapoints

| DP | Type en lengte | Gepubliceerde property | Interpretatie |
| --- | --- | --- | --- |
| 16 | number 2, vier bytes big-endian | `target_centi_c` | Ruwe tienden °C × 10; alleen 5–30 °C in stappen van 0,5 °C. |
| 24 | number 2, vier bytes big-endian | `local_temperature_centi_c` | Ruwe tienden °C × 10; eerste decoder beperkt tot 0–60 °C. Negatieve/onbekende codering wordt geweigerd. |
| 2 | enum 4, één byte | `preset` | 0 auto, 1 manual, 2/3 holiday. Andere codes worden geweigerd. |
| 107 | bool 1, één byte | `heating_stop` | 0 false, 1 true; geen ingevulde klepstand of beweging. |
| 10 | bool 1, één byte | `frost_protection` | 0 false, 1 true. |

Elke property behoudt DP-nummer, datatype en oorspronkelijke bytes in `raw_hex`.
Er wordt geen `system_mode` uit een handmatige preset afgeleid. De lokale
kraantemperatuur is geen gekwalificeerde ruimtemeting. Onbekende DP's worden
weggelaten; dubbele DP's, ongeldige bekende waarden/types/lengtes of een te groot
bericht weigeren het hele rapport. Maximum: 16 DP's, 64 bytes per DP, 128 bytes
DP-data samen en 2048 bytes uitgaand JSON. Alleen echte inbound
commandDataResponse/DataReport/ActiveStatusReport/ActiveStatusReportAlt-events
worden verwerkt; een uitgaande dataRequest of stateChange niet.

## Wire en levensduur

Topic onder de bestaande Z2M-base: `bridge/openthermostat/original_tv02`.
Het schema 1 bevat producent/run-UUID/publicatiesequence, apparaat/model/fabrikant/
endpoint, cluster/berichtsoort, oorspronkelijke Tuya-sequence/ZCL-transactie indien
geldig, ontvangsttijd en een `fields`-lijst met bovenstaande originele properties.
Publicatie is QoS 0, niet-retained, zonder payloadlogging door deze brug.

Maximaal één publicatie loopt; offline/busy maakt geen applicatiebacklog of retry.
Stop verwijdert de eigen listener en wacht op de bestaande SDK-publicatie. Een
gelijktijdige herstart wacht op die eigenaar en krijgt daarna een nieuwe run-UUID.
De SDK bepaalt de voltooiingstijd. Een netwerkdisconnect na de connectiecontrole
kan niet worden uitgesloten; de bestaande MQTT-stack kan ook fouten intern
opvangen. De lokale dropcounter bewijst daarom geen bevestigde netwerkaflevering.

`sampled_at_unix_ms` blijft null. `command_correlated`, `valve_ready` en
`control_qualified` blijven altijd false. De producent-UUID/publicatiesequence en
de omlopende/herhalende Tuya-sequence zijn geen opdrachtbevestiging. Een passend
doel of handmatige preset bewijst geen exclusief eigenaarschap, verse causale
doel-echo, motorbeweging, geopende kraan of hydraulische doorstroming.

De volgende stap is een native HA-consument met deze oorspronkelijke herkomst,
verloop-/reconnectbeleid en een beoordeelde koppeling aan de werkelijk verzonden
doelopdracht. De bestaande profiel-C-adapter blijft standaard geblokkeerd.

## Bron en controle

Protocolfeiten zijn onafhankelijk geïmplementeerd tegen de gepinde
[TV02-modeldefinitie](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.115.1/src/devices/tuya.ts)
en [Tuya-datatypes/waardedefinities](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.115.1/src/lib/tuya.ts),
met de bestaande
[Z2M 2.14.2-eventroute](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/extension/receive.ts).
Er is geen converter- of zendimplementatie overgenomen.

`node --test test/zigbee2mqtt/*.test.cjs` controleert 13 TV02-gevallen en de 11
bestaande temperatuurproducentgevallen. Gouden DP-bytes, strict model/type/ranges,
ontbrekende properties, cachevrije verwerking, sequence-omloop, SDK-fouten en
concurrent stop/herstart slagen. Dit zijn geïsoleerde API-/Node-tests, geen
geïnstalleerde Z2M-, fysieke kraan- of ketelproef.
