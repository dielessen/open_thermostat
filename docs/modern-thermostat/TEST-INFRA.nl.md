> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Afzonderlijke Home Assistant/MQTT-testomgeving

Gebruik de officiële Home Assistant Container en Eclipse Mosquitto, met eigen
configuratie/opslag, accounts, poorten, ACL en topicprefix. Geen productiebackup,
tokens, device-mounts, hostnetwork, MQTT-bridge of tweede regelaar kopiëren.

## Werkende native voorbereiding

1. Inventariseer bestaande containers/projecten en luisterpoorten. Kies een nieuw
   Compose-project en vrije, alleen lokaal/LAN gebonden poorten. Bewaar de baseline.
2. Pin de officiële images op versie én gecontroleerde digest. De proef van
   20 oktober 2026 gebruikte HA Core 2026.10.2 en Mosquitto 2.0.22.
3. Gebruik een eigen normale Docker-bridge. `internal: true` is niet zomaar een
   vervanging voor netwerkbeleid: op de geteste host verschenen opgegeven
   poortbindings wel in HostConfig, maar niet als werkelijke gepubliceerde poort.
   Controleer bereikbaarheid echt. Een gewone bridge met eigen configuratie en
   accounts is applicatie-isolatie, **geen netwerkairgap**.
4. Configureer HA met expliciete benodigde componenten; geen `default_config`,
   automatische device-discovery of hardwaretoegang. Kopieer alleen de integratie
   uit `ha/config/custom_components/open_thermostat`, met de broncommit genoteerd.
5. Genereer nieuwe private testcredentials. Hash de brokerpasswordfile met het
   officiële `mosquitto_passwd`; mount brokerconfig read-only. Gebruik passende
   eigenaar/permissies voor de broker-UID. Zet geen password of token in argv,
   terminaluitvoer, een rapport of bronbeheer.
6. Voer `docker compose config --quiet` en HA's native `check_config` uit.
   Start uitsluitend het eigen project, met `restart: "no"`. Maak via normale
   HA-onboarding een nieuwe testowner; schakel analytics uit. Verwijder eventuele
   automatisch toegevoegde, onnodige onboarding-integraties.
7. Voeg native MQTT toe met de interne testbrokernaam en discovery uit. Voeg een
   expliciete `v1_shadow`-entry toe; laat `shadow_enabled` false en kamers leeg.
   Lees entrymodus, geladen status, ondersteunde subentries en opties terug.
8. Verifieer UI-bereikbaarheid, onbevoegde API-weigering en MQTT-auth/ACL. Stop en
   start alleen het testproject als rollbackproef; behoud binddata. Vergelijk
   daarna de namen/images/poortbindings van alle niet-testcontainers.

## Auth en ACL daadwerkelijk controleren

E32 schrijft alleen `<base>/v1/fw/#` en leest `<base>/v1/ha/#`; HA precies andersom.
Native HA birth/will op `homeassistant/status` vraagt een expliciete uitzondering
voor alleen de HA-testgebruiker op deze broker. Anonymous moet geweigerd worden.

Gebruik officiële Mosquitto-clients met private clientconfig, geen secrets in argv.
Een lege, toegestane subscription mag met timeout 27 eindigen nadat CONNACK/SUBACK
succes bevestigen. Test verkeerde schrijfrichtingen uitsluitend met een afzonderlijk
probetopic en zonder firmware/actuator aangesloten. Controleer MQTT-v5 PUBACK:
de geteste `mosquitto_pub` gaf **exit 0 ondanks PUBACK 135 / Not authorized**.
Commandexit alleen bewijst dus geen geslaagde publicatie.

## Bewijsgrens en volgende stap

Een lege test-HA heeft niet vanzelf de productie-sensoren en TRV's. HA-statecache,
een pollingproxy of een softwarefixture is geen nieuwe fysieke temperatuurmeting.
Breng vóór kamerbinding eerst een geschikte werkelijke bronroute in kaart; verplaats
Zigbee2MQTT of productieapparaten niet stilzwijgend naar de testomgeving.

Infrastructuur en een geladen, uitgeschakelde shadow-entry bewijzen geen gezamenlijke
E32-keten. Configuratie-readback, verse bron, firmware-ACK en beide outputs false
blijven aparte acceptatiecriteria. Productie-HA/broker aanpassen is een afzonderlijk
beoordeelde stap, geen automatische oplossing voor ontbrekende testsensoren.

Stoppen/herstellen: `docker compose -p <eigen-testproject> down`, eigen binddata en
bewijs behouden; geen globale prune, productieherstart of volume-verwijdering.
Dit herstelt geen later gewijzigde E32-instellingen: daarvoor is eigen baseline nodig.
