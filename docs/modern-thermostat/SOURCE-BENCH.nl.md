> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Eindige echte-sensorproef via native HA-acties

Dit is een **afzonderlijk te starten shadow-proef**, geen automatisch meetprofiel
voor normale verwarming. De integratie heeft alle softwareaansluitingen; er is
geen extra script, sidecar of forwarder nodig. Er is nog niets geïnstalleerd of
aan Zigbee2MQTT gewijzigd.

## Toegang en voorwaarden

De native admin-acties verschijnen bij expliciete shadow-entries in HA:

- `open_thermostat.source_bench_start`
- `open_thermostat.source_bench_status`
- `open_thermostat.source_bench_stop`

Start vereist een ingeschakelde, toegelaten shadowverbinding met **precies één
kamer**. Hoogstens één proef per HA-instantie; maximaal300seconden. Legacy- of
meerkamerconfiguraties worden niet stilzwijgend omgebouwd. Gebruik een bewuste
testentry, geen parallelle oude commandowriter. Beide fysieke uitgangen blijven
false; climate blijft IDLE, eventuele warmtevraag is alleen gesimuleerd.

De begrensde route is onderzocht voor Aqara WSDCGQ11LM, Zigbee2MQTT2.14.2 en
converters26.115.1. Een ander model/versie is geen impliciete match. Gebruik
actuele, **alleen tot deze bron beperkte** native bridge/info-config en MQTT
Discovery; geen volledig netwerkconfiguratiebestand of secrets in actievelden.
De historische metadata is geen bewijs van de actuele instellingen.

## Uitvoeren tijdens een afgesproken proef

1. Behoud Tado en houd de E32 los van EMS. Spreek één operator af. Tijdens het
   venster geen andere Z2M-optiewijzigingen, custom-converterwijzigingen,
   apparaat-set/get, reloads, interviews, OTA of herstarts. Dit is een begeleide
   operationele voorwaarde, geen door MQTT afgedwongen lock.
2. Lees actuele expliciete apparaatopties, geërfde `device_options`, relevante
   `advanced.cache_state`/`last_seen` en Discovery terug. Debounce/throttle moeten
   effectief0 zijn, bron-QoS0/retainfalse, geen pending restart. Anders stopt deze
   route; geen blinde herstart of cache-uitschakeling als reparatie.
3. Open Ontwikkelaarstools → Acties → `source_bench_start`. Vul `entry_id`,
   `baseline`, `discovery`, `ieee`, `discovery_topic`, `ha_status_topic`, een nieuwe
   unieke `transaction` en `duration_s` in. Selectors staan in de actie-UI; het
   bronarchief bevat ook `services.yaml`. Start schrijft eerst de afzonderlijke
   mapping via de bestaande HA-Store/config/readback-route en sluit de generieke
   cachewriter voor deze kamer uit.
4. De respons bevat een **voorstel** voor precies één native
   `bridge/request/device/options`-wijziging plus exacte rollback. De actie
   verstuurt deze niet. Beoordeel die concrete delta vóór afzonderlijke uitvoering
   via de bestaande native Z2M-interface. Alleen `filtered_cache` wordt uitgebreid
   met `^temperature$`; bestaande filters blijven behouden. Verander geen globale
   cache, kalibratie of andere apparaatopties. Verstuur één keer; bij verloren ACK
   eerst teruglezen, niet automatisch herhalen.
5. De listener moet zelf actuele config én Discovery, het exacte verzoek, nieuwe
   niet-retained info en de bijbehorende native ACK waarnemen. Raadpleeg
   `source_bench_status` met hetzelfde `entry_id`. Een afwijking sluit de proef.
6. Het eerste geldige temperatuurdragende bericht na omschakeling wordt weggegooid:
   dat kan nog oude cache bevatten. Pas een later bericht met voortschrijdende
   native tijd en aanwezige geldige temperatuur mag worden doorgegeven. Gelijke
   temperatuur kan wel een nieuw rapport zijn; `last_seen` alleen niet. Eventueel
   kort met de hand verwarmen om twee rapporten uit te lokken. Een check-in-knop
   bewijst geen verse temperatuur. Geen tweede rapport betekent: proef onbewezen.
7. Controleer firmware-bronstatus, bevestigd doel en gesimuleerde vraag, daarna
   bronstilte/stale. Er is géén ketel- of kraanactie. De kwalificatie heet bewust
   `validated_integration_report`, niet een verzonnen fysieke acquisitietijd.
8. Roep `source_bench_stop` aan. Controleer `normal_mapping_restored:true`.
   Onbevestigd herstel blijft `blocked` en de generieke bron blijft afgeschermd.
   Stop verwijdert listeners/timers en trekt de bron in. Firmwareverlies,
   leaseverlies zonder nieuw pakket, bindingswijziging en expiry doen dat ook.
9. Herstel daarna afzonderlijk de voorgestelde oorspronkelijke Z2M-optie en
   controleer native ACK plus expliciete readback. Was de per-device eigenschap
   afwezig, dan herstelt native `null` de oorspronkelijke overerving; `[]` is iets
   anders. Overschrijf geen wijziging van een andere eigenaar. De actie beweert
   niet dat deze externe rollback automatisch is uitgevoerd.

## Bewijsgrens

De softwareproef omvat native HA-acties/lifecycle/Store en de echte C++-kern.
De gedeelde JSONL-gevallen staan in `ha/tests_native/fixtures/`; de gewone
pakketlustest gebruikt de echte HA MQTT-client en geïsoleerde Mosquitto.
De fysieke sensoromschakeling en rapportcadans zijn nog niet uitgevoerd.
Langdurige beschikbaarheid, thermische nauwkeurigheid en onbeheerde regeling
worden hiermee niet vrijgegeven. Zie [testkaart](TEST-RECORD.nl.md).

Native bronbasis: [Z2M cache](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/state.ts),
[opties/ACK](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/extension/bridge.ts),
[publicatie](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.2/lib/controller.ts),
[modelconverters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.115.1/src/lib/lumi.ts).
