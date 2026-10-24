# Privé installatiepins voor oorspronkelijke TV02-ontvangst

Status: bronvoorbereiding na HA dev29, nog niet geïnstalleerd. Onderdeel van
WORKBOARD B05. Dit koppelt uitsluitend ontvangstdiagnose; het kwalificeert geen
meting, doelopdracht, klepstand, flow of actuatoruitvoer.

## Bestand en eigenaarschap

Een beoordeelde installatie kan de pins bewaren in
`<HA-config>/.openthermostat-original-tv02.json`, buiten de integratiemap en het
openbare bronpakket. Werkelijke native IDs blijven in deze privé installatie.
De bestaande HA-agent verzorgt een latere installatie met privé back-up en
nacontrole; deze notitie voert die stap niet uit.

De loader leest één snapshot bij normale opstart van een ingeschakelde native
shadow-entry. Hij schrijft geen bestand en maakt geen watcher, Store, timer,
MQTT-client of apparaatopdracht aan. Een ontbrekend bestand betekent geen pins.
Een wijziging wordt pas bij een gewone integratieherlaad/opstart beoordeeld.
Bestaande native registry-/model-/bindingguards blijven daarna actief.

Het bestand moet een gewoon privébestand zijn, bijvoorbeeld modus 0600 of 0400.
Groeps-/wereldtoegang, symlinks, speciale bestanden en bestanden groter dan
32 KiB worden geweigerd. Maximaal 64 bronrijen. Een verandering tijdens lezen
weigert de snapshot. Een fout schakelt alleen deze optionele diagnose uit met
een generieke logmelding; bestaande kamer-/controlleropstart blijft werken.

## Schema 1

Een geldig leeg bestand heeft deze vorm:

```json
{"schema":1,"kind":"original_tv02_receive_only","sources":[]}
```

Iedere bronrij bevat exact de volgende velden, na afzonderlijke beoordeling van
de bestaande native installatie:

| Veld | Betekenis |
| --- | --- |
| `entry_unique_id` | Exacte unieke identiteit van de bedoelde HA-integratie-entry |
| `room_id` | Bestaande achtcijferige hex-kamer-ID |
| `entity_id` | Geselecteerde native `climate`-entiteit |
| `platform` | `mqtt` |
| `unique_id` | Exacte native registry-identiteit van dezelfde entiteit |
| `manufacturer` | Expliciet beoordeelde ondersteunde TV02-fingerprint |
| `endpoint` | Expliciet beoordeeld Zigbee-endpoint |

Geen eerste bericht, friendly name of HA-optie kiest deze waarden. De bestaande
`OriginalTv02Reports` controleert dat de referentie echt bij een geselecteerde
actuator van deze kamer hoort, het native apparaat TV02-Zigbee is en de registry-
/discoverybinding nog klopt. Onjuiste of verdwenen binding geeft geen vervanger.
Een manifest bevat geen code, paden, instellingen voor regelgrenzen of
kwalificatie-/readinessvelden; onbekende velden worden geweigerd.

Expliciete gecompileerde `_ORIGINAL_TV02_DIAGNOSTIC_SOURCES` hebben voorrang.
Als die selectie aanwezig maar ongeldig is, wordt niet teruggevallen op een
ander bestand. De standaardtuple blijft leeg; opties en MQTT-berichten wijzigen
noch die tuple noch het privébestand.

## Ontvangst en resterende acceptatie

De bestaande MQTT-client en begrensde worker verwerken de oorspronkelijke
rapporten. `command_correlated`, `valve_ready` en `control_qualified` blijven
false. Het bestand installeert of start de Zigbee2MQTT-producent niet. De daarvoor
benodigde afzonderlijke bronbinding, native loader-/SDK-beoordeling en echte
ontvangst blijven B05. Dit is evenmin een causale doel-echo of fysieke kraanproef.

Controle: 40 nieuwe gevallen; samen met bestaande lifecycle-/native-opstarttests
91 gerichte HA-checks PASS. De echte HA-registries en normale integratieopstart
zijn gebruikt, met synthetische MQTT-berichten. Speciale bestanden, privémodus,
exact schema, foutisolatie, entryselectie, gecompileerde voorrang en behoud van
`profile_missing` zijn gecontroleerd. Geen productie-installatie of live opdracht.
Bewijs: `out/diagnostic-source-manifest-20261024/`.
