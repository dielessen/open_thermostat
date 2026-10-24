# Oorspronkelijke TV02-kraanberichten

Status: producent, HA-ontvangstkern en native lifecycle voorbereid en getest; niet geïnstalleerd. B05 blijft open
voor concrete bronpins/installatie, koppeling aan een doelopdracht, eigenaarschap, readiness en
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

De native HA-consument bewaart deze oorspronkelijke herkomst en het
verloop-/reconnectbeleid. Een beoordeelde koppeling aan de werkelijk verzonden
doelopdracht ontbreekt nog. De bestaande profiel-C-adapter blijft standaard geblokkeerd.

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

## HA-ontvangstkern voor dezelfde bètabatch

`original_tv02.py` controleert schema 1 en decodeert iedere oorspronkelijke DP
onafhankelijk opnieuw uit `raw_hex`. Model, ondersteunde fabrikant, IEEE, endpoint,
berichtsoort, types en bereiken moeten exact passen. Een extra of dubbele sleutel,
dubbele DP, afwijkende afgeleide waarde of beweerde regelkwalificatie wordt geweigerd.

`Tv02Reception` bindt één expliciete IEEE/fabrikant/endpointcombinatie. Retained,
oude ontvangstgeneraties, toekomstige of verlopen ontvangst en herhaalde/teruggekeerde
producer-runs worden geweigerd. Maximaal acht run-watermerken blijven behouden,
ook bij disconnect. De lokale wachttijd telt mee voor ontvangstouderdom; een
klokteruggang blokkeert tot heropbouw. Elk rapport vervangt het vorige volledig:
een losse preset vult geen eerder gemeld doel aan. Publieke status bevat geen
IEEE, producer-UUID of ruwe packet. Ontvangsttijd blijft ontvangsttijd;
`command_correlated`, `valve_ready` en `control_qualified` blijven false.

De kern is inmiddels aangesloten op de bestaande native MQTT-worker en
registry-/bindingintrekking; room/get biedt de veilige ontvangstsamenvatting
optioneel aan onder actuator_target_review. De huidige frontend toont deze nieuwe
ontvangstsamenvatting nog niet. Een causale doel-echo en exclusief eigenaarschap
vragen afzonderlijk bewijs vóór enige fysieke vrijgave.

Controle: 98 gerichte HA-tests voor deze kern en de bestaande temperatuurontvangst,
inclusief werkelijk door de Node-producent opgebouwd wirebericht, oorspronkelijke
DP-grenswaarden, herhaling, reconnect, wachtrijouderdom en klokfouten. Dit is
bron-/testbewijs; de geïnstalleerde HA dev27 en E32 alpha21 wijzigen hierdoor niet.

## Native lifecycle en expliciete bronpins

`NativeShadowConnection(..., tv02_sources=())` heeft standaard geen TV02-bronpins
of rapportabonnement. Alleen een expliciete bron-eigen `Tv02DiagnosticSource`
bindt de integratie-identiteit, kamer, reeds geselecteerde native MQTT-climate,
beoordeelde fabrikant en endpoint. Een optie, discovery-vendor, brokerbericht,
HA-state of eerste ontvangen datapoint stelt deze pins niet in. De werkelijke
pins/extensioninstallatie blijven een afzonderlijke gecontroleerde uitvoeringsstap.
Een pin autoriseert geen kraanbediening.

`OriginalTv02Reports` controleert het native registry-record, apparaatmodel
TV02-Zigbee, IEEE en werkelijk ontdekte Z2M-prefix. Zowel bij ontvangst/status
als via de bestaande entity-/device-registrylisteners wordt herkomst opnieuw
getoetst. Verwijderen, uitschakelen, apparaat-/model-/kamerbindingwissel of
gewijzigde discovery trekt de diagnose in tot heropbouw. Een waargenomen wijziging
die later wordt teruggedraaid maakt oude bewijsdata niet opnieuw geldig.

Dezelfde bestaande MQTT-client, worker en 64-plaatsenqueue verwerken de berichten.
Temperatuur en TV02 delen maximaal één wachtend diagnostisch bericht; de helft
van de queue blijft gereserveerd voor de bestaande keten. Hoogstens één exact
topic per geselecteerde Z2M-prefix wordt toegevoegd. Identiteit wordt vóór dispatch
gezocht in maximaal 64 expliciete bindings; onbekende apparaten worden niet
bewaard. Geen extra client, worker, timer, Store, discovery of fysieke opdracht.

Een verbroken verbinding trekt beide diagnoses onmiddellijk in, vóór eerder
wachtende berichten kunnen worden toegelaten. Replay-watermerken blijven binnen
deze eigenaar behouden; heropbouw is geen authenticatie van onbekende historische
producer-runs. Optionele abonnements-/diagnosefouten raken alleen de diagnose.
Unload verwijdert de eigen subscriptions en runtimeverwijzing; een oude opruiming
verwijdert geen nieuwe eigenaar. Geen verandering aan SOURCE, controllerlease,
meetkwalificatie, kraanreadiness of TX-lock.

Gerichte controle: 222 HA-checks PASS, met de echte HA-registries en bestaande
C++-interop waar de bestaande suites dat gebruiken. Inclusief 23 nieuwe lifecyclegevallen
en één nieuw room/get-geval. Volledige regressie en actuele bronpins zijn apart vastgelegd
in `out/tv02-lifecycle-20261024/`; dit blijft offline softwarebewijs.

Volledige HA-regressie: 1.840 tests + 68 subtests = 1.908 checks PASS, zonder
fouten of overslagen, acht opnieuw gebouwde C++-peers en een tijdelijke lokale
MQTT-testfixture. De fixture is na afloop verwijderd. Dit bewijst de bronketen;
een geïnstalleerde extension, oorspronkelijke fysieke ontvangst en kraanreactie
blijven afzonderlijke open acceptatiepunten.
