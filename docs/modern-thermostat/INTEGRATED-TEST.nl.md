# Geïntegreerde testkandidaat: E32 + Home Assistant

Deze ontwikkelversie is bedoeld voor de **eerste gezamenlijke software- en
geïsoleerde bordtest**, niet als vervanging van de werkende verwarming.
Firmware en HA praten rechtstreeks via één MQTT-broker. Geen bridge, sidecar of
tweede regelprogramma. `shadow` berekent kamerdoelen en gesimuleerde vraag;
**keteluitvoer en echte kraanbediening zijn uitgeschakeld**. EMS-TX/forwarder,
reset-breaks en lokale GPIO/I2C blijven bovendien compile-time geblokkeerd.

## Wat deze test moet bewijzen

- Via de HA-GUI een kamer maken en sensor/TRV/optionele bediening/schema kiezen,
  later wijzigen en de blijvende kamer-ID bewaren; geen kamer-YAML nodig.
- Eén configuratie met revision/digest aan beide kanten; duurzame HA-mapping vóór
  firmwarecommit, teruglezen bij verloren ACK, geen automatisch oude backup terugduwen.
- Verse bron → firmwaredoel/schema/override → zichtbare bevestigde kamerstatus.
- Cache/restored/stale/onbeschikbaar is niet ineens een verse thermometer.
- HA-, broker- en firmwareherstart maken oude berichten/boosts niet opnieuw actief.
- Beveiligde eerste wifi-installatie en herstel, zelfstandige wifi- óf Ethernetmodus,
  settingsbehoud en een aantoonbare seriële terugweg.

Maximaal acht logische kamers; totale berichten begrensd op8192bytes/512nodes,
duurzame regelconfiguratie4096bytes. Eén schema heeft maximaal128overgangen,
maar acht volle schema's passen niet automatisch in het totaalbudget. Afwijzen
is verplicht, nooit stil afkappen. Netwerkinstellingen maximaal2048bytes.
De20KiB-NVS-partitie en alle app-/filesystempartities zijn ongewijzigd; test op
het bord ook maximale configuratie-updates en NVS-vol/powerlossgedrag.

## Eerste installatie: pas na afgesproken fysieke voorbereiding

Er is één bestaande E32, geen tweede bord verondersteld. Houd Tado en de
werkende verwarming intact. Begin **los van ketel/EMS**, met de door BBQKees
beschreven USB-C-programmeer-/voedingsroute. Productgegevens staan bij
[BBQKees](https://bbqkees-electronics.nl/product/gateway-e32-v2-ethernet-wifi-edition-v2/).
Een extra foto is geen voorwaarde voor softwarebouw; werkelijk bord/16MB-flash,
backup en herstel worden vóór de eerste erase/flash wél gecontroleerd.

1. Controleer pakketchecksums en `SOURCE_COMMIT.txt`. Gebruik uitsluitend het
   E32-V2-pakket: klassieke ESP32/16MB, geen S3 of oude E32.
2. Exporteer oorspronkelijke EMS-ESP-configuratie en maak **twee volledige16MB
   flashbackups**, vergelijk en bewaar ze privé/off-device. Controleer passende
   originele herstelsoftware, security-status en exacte seriële poort. Stop bij
   afwijkende lezingen of ontbrekende herstelroute. Geen backup in dit testpakket.
3. Gebruik de backup/USB-installatieprocedure in
   [de bordhandleiding](../BBQKEES_E32V2.md) en
   [de flashgids](../FLASHING.md). De gecombineerde fabrieksimage hoort op0x0,
   niet in de EMS-ESP-webupdater. Eerst verifiëren met `--after no_reset`, pas
   daarna normaal booten. Een gehele flashvergelijking na eerste boot is ongeldig
   omdat NVS dan al kan veranderen. Deze stappen zijn hier niet uitgevoerd.
4. Open de fysieke USB-console op115200baud. Daar verschijnen twee unieke
   apparaatwachtwoorden: setup-wifi en HTTP-gebruiker `admin`. Bewaar ze privé;
   stuur geen ongeredigeerd seriëel log door. Ze gaan niet naar de netwerklogger.
5. Eerste boot zonder wifi begint als **alleen wifi**, zonder Ethernetklok.
   Verbind met `OpenThermostat-xxxxxx`, met het setup-wachtwoord. Open handmatig
   `http://10.10.10.1/`, log in als `admin` en kies het thuisnetwerk. Er wordt geen
   automatische captive-portalopening beloofd.
6. Verkeerd wachtwoord: na circa30s verschijnt een fout, opnieuw proberen blijft
   mogelijk binnen het15minutenvenster. Pas na geslaagde verbinding én NVS-readback
   worden credentials bevestigd. De setup-AP stopt daarna na10s. Noteer het
   getoonde station-IP en verbind telefoon/laptop weer met het thuisnetwerk.
7. Herstel/wifiwijziging: fysieke USB-opdracht `setup` + Enter herstart het bord
   gecontroleerd in wifi-only herstel; er worden geen globale credentials gewist.
   Via ingelogde HTTP kan ook `POST /setup/reenter`. Ethernetklok wordt daarbij
   niet naast wifi aangezet. Een korte netwerkstoring opent geen permanente AP.

De oude alpha.1-handleiding noemt gedeelde voorbeeldwachtwoorden en gelijktijdig
Ethernet/wifi. Dat beschrijft **die historische release**, niet deze kandidaat.

## Rechtstreekse HA-koppeling

Gebruik eerst een afzonderlijke test-HA en testbroker/prefix, niet de productie-
configuratie of bestaande EMS-ESP-entiteiten. HA-doelversie2026.10.2/Python3.14.
Installatie van de meegeleverde integratie en apparaatbesturing worden pas tijdens
de afgesproken test uitgevoerd; niets is hier in productie geïnstalleerd.

1. Voeg de integratie toe in expliciete v1/shadowmodus. Noteer de HA-adapter-ID.
2. In de E32-netwerkpagina: kies wifi of Ethernet (pas actief na herstart), eigen
   brokercredentials, unieke prefix/client-ID en moderne HA-teststand. Kopieer
   de adapter-ID. Moderne modus start géén tweede legacy-MQTT-writer. Opgeslagen
   passwords/APIkeys worden niet teruggekaatst; leeg bewaart bij ongewijzigde
   broker/gebruiker het bestaande geheim. Bij andere broker/gebruiker nieuw invoeren.
3. Broker-ACL: E32 schrijft alleen `<base>/v1/fw/#` en leest alleen
   `<base>/v1/ha/#`; HA precies andersom. Geen anonieme toegang. Nonces en hashes
   zijn geen authenticatie. Deze versie gebruikt vertrouwd lokaal MQTT/HTTP,
   geen bewezen TLS-/internetvrijgave; stel haar niet publiek bloot.
4. Sla instellingen op en herstart gecontroleerd. Netwerk/broker, wifi, lokale
   toegang en regelconfiguratie staan in NVS buiten vervangbare filesystemslots.
   Test hun behoud later ook met echte app-/filesystem-OTA; dat is nog geen bewezen
   rollback of migratiegarantie.
5. Maak één kamer met een geschikte gekozen sensor en bestaande TRV-binding.
   De binding voert in shadow geen deviceactie uit. Een rapportprofiel moet echt
   gekwalificeerd zijn; HA-statecache/`last_reported` alleen is geen fysiek bewijs.
   Een ongekwalificeerde bron blijft zichtbaar maar onbruikbaar voor normale vraag.
   De generieke GUI-keuze is nog geen apparaatkwalificatie: deze eerste basis
   heeft niet automatisch een vrijgegeven meetprofiel voor iedere HA-sensor.
   De automatische ketentests gebruiken een expliciete test-driver; de echte
   badkamerbron krijgt afzonderlijk bron-/cadansbewijs vóór gebruik. De aansluitbare
   eindige proef staat in [SOURCE-BENCH.nl.md](SOURCE-BENCH.nl.md); native
   start/status/stopacties zijn aanwezig, standaard niet actief.
6. Verander het HA-kamerdoel. Controleer firmware-ACK, teruggelezen doel, revision,
   bronkwaliteit en reden. **Gesimuleerde vraag is geen `heating` of vlamdetectie.**
7. Koppel desgewenst een native HA-Schedule met blokdata `temperature`. Firmware
   voert de begrensde UTC-kalender uit (normaal15dagen); HA is editor/exporteur,
   geen tweede scheduler. Tijdloosboot of verlopen kalender geeft geen normaal
   schemadoel. Test aangrenzende blokken, basisdoel, override-afloop en tijdsprongen.

Gebruik de E32-webinterface in deze stap voor setup/netwerk/updates. De setup-
links openen de volledige applicatie met netwerk-/apparaatpagina, ook tijdens
het AP-venster. Het hoofdscherm toont in shadow een expliciete testmelding,
geen oude kamer-/keteltegels. HA-climate toont de bevestigde moderne kamerstatus;
legacy-controlwrites zijn in shadow geblokkeerd. Statusvragen wachten niet op NTP;
zonder geldige klok zijn tijd/datum null, geen verzonnen tijd.

## Reproduceerbare gezamenlijke softwareproef

De bron bevat `ha/tests_native/test_v1_packet_loop.py` en de geïsoleerde broker-
fixture `test/interop/mqtt-fixture/`. CI bouwt de echte C++-kernrunner, start de
vastgezette officiële Mosquitto-image uitsluitend op localhost en voert native
HA-lifecycle-, protocol- en pakketlustests uit. Fixturecredentials zijn openbaar
en uitsluitend voor deze tijdelijke test. De pakketlus gebruikt HA's echte MQTT-
client; de firmwarepeer is de echte C++-regel-/protocolkern op de host, niet een
geflashte ESP32 of bewijs van diens fysieke netwerkgedrag. De test omvat ook
een harde socketonderbreking met broker-LWT, zonder onterechte gereedstatus.

## Testkaart: uitkomst en bewijs opschrijven

- Bron constant maar aantoonbaar nieuw gerapporteerd; daarna bron stil met gezonde
  HA-heartbeat: waarde moet verlopen. Cache/restored mag geen nieuwe meting worden.
- Verkeerde binding/revision/owner; retained/reorder/duplicaat; verloren config-ACK;
  reboot tijdens opslag. Oud óf volledig nieuw, nooit half; conflict blijft zichtbaar.
- HA unload/reload, MQTT-uitval, E32-reboot: geen oude override of beschikbare bron
  zonder nieuwe sessie/kwalificatie; luisteraars en taken worden opgeruimd.
- Zonder inlog HTTP-status/config/OTA weigeren; GET-reboot weigeren; cross-origin
  mutatie weigeren. Controleer uploadweigering vóór flashschrijven. Unit-/buildtests
  zijn hiervoor bronbewijs, geen uitgevoerde echte HTTP- of flashproef.
- Wifi-only en Ethernet-only apart na herstart; geen automatische scan/reconnect
  die in Ethernetmodus toch de radio aanzet. Log PSRAM, vrije/minimale heap, resets,
  verbinding en tijd. Ook exclusieve modus is nog niet fysiek bewezen.
- Seriële restore van het origineel, geldige/ongeldige/afgebroken app-/filesystem-
  OTA en settingsbehoud zijn afzonderlijke fysieke acceptatiechecks.

## Expliciet nog niet af / niet vrijgegeven

Deze kandidaat voltooit niet het gehele masterplan. Echte TRV-bediening/readiness,
wandbedienings-echo met echte apparaten, waterdoel/hydraulische supervisor,
aanvullende ketelpariteit/grafieken/counters, zelfleren/optimum-start en comfort-
uitbreidingen blijven afzonderlijke bouw-/bewijsstappen. Classic-EMS-aansturing
blijft uit tot elektrische/timing-/start/stop/minimumflow/naloop/powerlossproeven
en een afzonderlijk beoordeelde bronwijziging. Geen normale verwarmingsvrijgave
op basis van groene softwaretests. Zie [masterplan](PLAN.nl.md) en
[concreet wireprofiel](TEST-WIRE.md).
