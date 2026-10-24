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

## Draaiboek voor de gezamenlijke update

Voer dit via de bestaande HA-agent uit, samen met B11–B13. De huidige
main-CI-pakketten gebruiken nog alpha23/dev29 en zijn geen nieuwe installeerbare
release. Een privéconcept in een agent-artifactmap is evenmin een geïnstalleerd
manifest.

1. Leg één gezamenlijke broncommit vast met nieuwe, ongebruikte E32- en
   HA-versies. Beoordeel eerst de HA/E32-tussenversiecompatibiliteit en kies
   daaruit de installatievolgorde; de onderstaande nummers zijn geen bewijs
   dat iedere tussentoestand past. Controleer volledige CI, echte downloadchecksums, bron-/ELF-/
   webidentiteit, HA-componentbytes en licentie-/herlinkpakket. Behoud bestaande
   tags/assets. Leg vast of de kandidaat uitsluitend ontvangst aanbiedt of aan
   alle voorwaarden van de actieve bèta voldoet.
2. Bewaar vóór wijzigen een privé HA-back-up, de huidige integratieversie,
   geselecteerde kamer/actuator/sensor, registrybinding, programma-/profielstatus
   en het bestaande manifest of diens afwezigheid. Bewaar E32-instellingen en
   de vorige app-only release. Een eerdere back-up is geen verse back-up.
3. Vergelijk de privé TV02-pins opnieuw met de actuele geselecteerde kamer en
   native MQTT-registry. Controleer fabrikant en endpoint uit afzonderlijk
   beoordeelde discovery-/bridgegegevens. Stop bij verschil; neem geen nieuwe
   bron over op basis van naam, eerste bericht of eerdere conceptstatus.
4. Installeer de geverifieerde HA-release via de bestaande beheermethode.
   Plaats alleen het beoordeelde privémanifest onder de vaste HA-confignaam,
   met modus 0600 of 0400. Een manifest hoort nooit in de integratie-ZIP of
   openbare Git-bron. Herlaad via de gewone route en controleer normale
   controlleropstart, ongewijzigde bronselectie en uitgeschakelde uitvoer.
5. Behandel de Z2M-producent als een afzonderlijke installatie: controleer de
   ondersteunde native loader, effectieve external-JS-toelating, naamconflict en
   back-up vóór laden. Beoordeel exact de zelfstandige extensioncode met privé
   IEEE/model/fabrikant/endpoint-bindings. De openbare lege allowlist verzamelt
   niets. Een extension-save/list-antwoord bewijst geen geslaagde start; zoek ook
   naar startfouten en een werkelijk ontvangen oorspronkelijk rapport.
6. Wacht uitsluitend op spontane rapporten. Gebruik geen read/get/set, preset-
   wijziging, doelopdracht of apparaatbediening om diagnose te laten slagen.
   Bewaar onderscheid tussen bronrapport, ontvangsttijd, cache en causale echo.
   Geen rapport binnen het begrensde observatievenster betekent **niet bewezen**;
   `command_correlated`, `valve_ready` en `control_qualified` blijven false.
7. Werk de E32 via de normale HTTPS-app-only updater bij en controleer de nieuwe
   versie, stabiele boot, instellingen/programmas en HA-herverbinding. Controleer
   de uitgangen vóór en na elke stap. Gebruik geen factory- of SPIFFS-upload.
   Sluit tijdelijke beheersessies en registreer de werkelijk geïnstalleerde
   versies en broncommit op het werkbord.

**Terugval:** bij HA-opstart-/bindingsproblemen herstel de geback-upte integratie
plus de oorspronkelijke manifeststatus via dezelfde HA-agent en controleer de
gewone controller. Een ontbrekend/ongeldig manifest schakelt uitsluitend deze
optionele ontvanger uit; het is geen bewijs dat een producent is gestopt. Bij een
producentprobleem verwijder/herstel alleen de door deze installatie beheerde
extension via de ondersteunde native loader en controleer listener-/startfouten.
Gebruik geen volledige Z2M-herstart of verandering van external-JS-beleid als
verborgen terugval. Bij E32-problemen volg de bestaande gecontroleerde OTA-
herstelroute uit [Firmware bijwerken](GITHUB-UPDATES.nl.md).

Deze stappen wijzigen geen sensorprofiel, TV02-modus of exclusief eigenaarschap.
De aparte voorwaarden voor een fysieke kraan- of ketelproef blijven B04–B14.
