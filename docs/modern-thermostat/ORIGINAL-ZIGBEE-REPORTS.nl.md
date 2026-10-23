# Originele Zigbee-temperatuurberichten

Status: voorbereide bron, niet geïnstalleerd en niet gekoppeld aan de
regelautorisatie. B04 blijft open. Deze ontvangstbrug is de eerste producentstap
voor het ontbrekende modelspecifieke meetprofiel.

`integrations/zigbee2mqtt/original-temperature.cjs` gebruikt het bestaande
Zigbee2MQTT `deviceMessage`-event en dezelfde MQTT-client. De gewone
`publishEntityState`-/state-cache wordt niet gelezen. Daardoor blijft de originele
`attributeReport` of `readResponse` met de concrete property behouden, ook wanneer
de normale publicatieroute eerder opgeslagen velden samenvoegt. Er is geen extra
MQTT-client, abonnement, polling, leesopdracht, actuatoropdracht of periodieke taak.

## Ondersteunde bron en installatiegrens

De bron is beoordeeld tegen Zigbee2MQTT 2.14.2 en converters 26.115.1. Dit is een
compatibiliteitsdoel, geen bewijs van de werkelijk geïnstalleerde packagehashes.
Het eerste ondersteunde profiel is uitsluitend WSDCGQ11LM / `lumi.weather`,
cluster `msTemperatureMeasurement`, eigen property `measuredValue`. Het bericht
bevat de ruwe gehele centigradenwaarde; er wordt geen HA-/Z2M-kalibratie of
afronding op toegepast. Ongeldige waarden en waarden buiten het modelbereik
worden geweigerd.

De standaard `DEVICE_BINDINGS` is leeg. Voor een latere gecontroleerde installatie
wordt daarin alleen het beoordeelde IEEE-adres met model WSDCGQ11LM opgenomen.
Het volledige bestand kan daarna via de bestaande external-extensionfunctie
worden geladen; die stap hoort bij de HA-specialist en is nu niet uitgevoerd.
Een wijziging van deze lijst autoriseert geen regeling.

RTCGQ11LM / `device_temperature` wordt niet als ruimtemeting gepubliceerd. Dat is
de huidige geselecteerde Badkamer-bron; er is geen automatische sensorwissel.
TV02-terugmelding vraagt een afzonderlijk model-/datapuntprofiel en valt buiten
deze temperatuurbrug.

## Wirecontract

Topic onder de bestaande Z2M-base:
`bridge/openthermostat/original_temperature`. Publicatie is QoS 0, niet-retained,
met uitgeschakelde payloadlogging door de brug. Het vaste schema 1 bevat:

| Veld | Betekenis |
| --- | --- |
| `producer`, `producer_run_id`, `sequence` | Producent, nieuwe UUID per start en oplopend publicatienummer. Dit zijn geen sensor-sample-ID's of geauthenticeerde MQTT-sessies. |
| `device_ieee`, `model`, `zigbee_model`, `endpoint` | Oorspronkelijke apparaat-/endpointidentiteit, getoetst aan de expliciete binding. |
| `cluster`, `message_kind`, `property` | Origineel cluster, attributeReport/readResponse en concrete temperatuurproperty. |
| `raw_value`, `value_centi_c` | Originele gehele measuredValue in honderdsten °C. |
| `zcl_transaction` | Originele 8-bit transactie indien aanwezig; anders null. Kan herhalen of omlopen. |
| `received_at_unix_ms` | Tijd van deze eventcallback; niet de fysieke acquisitietijd. |
| `sampled_at_unix_ms` | Altijd null: het apparaat levert hier geen aangetoonde acquisitietijd. |
| `acquisition_age_verified`, `control_qualified` | Altijd false. |
| `dropped_reports` | Door de producent geweigerde publicaties wegens busy/offline/SDK-fout; geen bevestigde broker- of netwerkverliesmeting. |

De producent houdt maximaal één lopende publicatie en geen applicatiebacklog bij.
Nieuwe berichten tijdens offline/busy worden weggegooid; herstel speelt die niet
opnieuw af. Een netwerkdisconnect tussen de connectiecontrole en SDK-publicatie
kan niet worden uitgesloten. De bestaande MQTT-stack kan fouten intern opvangen;
een opgeloste publish-promise is dus geen ontvangstbevestiging. Stop verwijdert
de listener en wacht op de al lopende SDK-publicatie; de SDK bepaalt diens
voltooiingstijd. Een gelijktijdige herstart wacht op die oude eigenaar.

## Nog nodig voor B04

Een volgende HA-consument moet een echte native binding en een beoordeeld
meetprofiel hebben, apparaat-/bridgeherstart, duplicaten, reconnect en ouderdom
afhandelen, en de waarde rechtstreeks aan dit originele bericht koppelen. Een
HA-state met dezelfde waarde bewijst die koppeling niet. Een callbacktijd,
ZCL-transactienummer, producer-UUID of niet-retained bericht levert op zichzelf
geen oorspronkelijke fysieke acquisitietijd. De brug produceert daarom nergens
een `QualifiedReport` en kan `profile_missing` niet omzeilen.

Bronreferenties:
[Z2M receive](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/extension/receive.ts),
[extensionloader](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/extension/externalExtensions.ts),
[MQTT-client](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/mqtt.ts),
[modeldefinities](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.115.1/src/devices/lumi.ts),
[temperatuurconverter](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.115.1/src/lib/lumi.ts).

Reproduceerbare broncontrole: `node --test test/zigbee2mqtt/original-temperature.test.cjs`.
De 11 tests gebruiken een echte Node-eventemitter met geïsoleerde SDK-interfaces;
ze bewijzen geen geïnstalleerde extension, fysieke sensoracquisitie of ketelactie.
