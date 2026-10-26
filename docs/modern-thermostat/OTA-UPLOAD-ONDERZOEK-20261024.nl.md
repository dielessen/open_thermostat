# E32 app-upload: offline onderzoek en voorbereide correctie

## Vastgesteld

Op 24 oktober mislukte één alpha29-upload na 16,36 seconden, curl 56/HTTP 000.
De onafhankelijke nacontrole bevestigt alpha28, bron `3efb0a1`, en resetcode 6:
task-watchdogreset. Taak/stack en grondoorzaak zijn onbekend. Startupregels zijn
uit de RAM-ring verdwenen. Geen alpha29-boot of rollback bewezen. HA dev38 draait
wel en instellingen/back-up zijn behouden; zie het
[installatieverslag](INSTALLATIE-HA38-ALPHA29-20261024.nl.md).

De alpha28- en alpha29-uploadcode is gelijk. Onderzocht is de bestaande
`/ota`-route, zonder een upload, herstart, rollback of native HTTPS-proef.

## Bibliotheek en watchdog

De lokale frameworkidentiteit komt overeen met de vastgepinde
`3.20017.241212+sha.dcc1105b` in `platformio.ini` (Arduino 2.0.17).
De bijbehorende ESP32 dio_qspi-configuratie gebruikt Arduino-loopcore 1,
watchdogtimeout 5 seconden en bewaking van idle CPU0. Flash-erase-yield staat aan.
De native multipart-parser wacht met `delay(2)` wanneer geen netwerkbyte
beschikbaar is; hij garandeert daarmee geen periodieke vertraging als er wel
continu gegevens beschikbaar zijn. Deze feiten wijzen geen schuldige taak aan.
Een ontbrekende expliciete yield in onze callback bewijst dus geen oorzaak.
Er is geen watchdog uitgezet, timeout verhoogd of willekeurige delay toegevoegd.

De pinned `WebServer::handleClient()` voert `_parseRequest()` en daarna
`_handleRequest()` synchroon uit. App-uploadstaat wordt aan deze bestaande
requestgrens gebonden. Deze afhankelijkheid moet bij een frameworkupgrade opnieuw
worden gecontroleerd; er is geen asynchrone uploadondersteuning geclaimd.

## Concrete correcties in de volgende bronbundel

De oude route gebruikte `atol`, controleerde geen exacte ontvangen lengte en
koos de opstartpartitie in de bestand-END-callback. Een toegangsweigering ruimde
een open native handle niet direct op. Een aanvraag voor een upload bevestigde
bovendien de huidige appboot, onafhankelijk van de gewone bootacceptatie.

De gedeelde, hosttestbare `ManualAppUpload` voert nu uit:

- Alleen een positieve decimale grootte binnen de inactieve partitie accepteren,
  zonder overflow of geaccepteerde tekstachtervoegsels. Voor native begin de
  gevalideerde omvang gebruiken; geen volledige partitie wissen met onbekende grootte.
- Ontvangen bytes exact tellen. Een te groot blok vóór schrijven afwijzen;
  een te korte upload vóór valideren afwijzen. Een leeg laatste WRITE-blok blijft geldig.
- Iedere open handle bij annulering, verbroken verzoek of toegangsverlies opruimen.
  Native `esp_ota_end` verbruikt de handle ook bij fouten, dus geen tweede abort.
- Een tweede firmwarebestand in hetzelfde verzoek afwijzen. Het image eerst
  native valideren; de opstartpartitie pas in de laatste geautoriseerde handler
  kiezen na verwerking van het hele verzoek. Alleen daarna succes en herstart plannen.
- Geen pending boot bevestigen als bijwerking van een uploadaanvraag.

De native contracten over omvang en handle-eigenaarschap volgen de
[ESP-IDF 4.4.7 OTA-documentatie](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/system/ota.html).
Deze correcties bewijzen geen verband met de watchdogreset. Ook een kortere
initiële erase is geen gemeten timing- of herstelresultaat.

## Verificatie en resterend herstelwerk

Zestien nieuwe native testgevallen toetsen de productieklasse, inclusief
begin/write/end/select-fouten, overloop, te weinig/te veel bytes, dubbele bestanden,
toegangsverlies en onherleefbare fouten. De volledige native suite telt 665 tests.
Elf extra scenario's voeren de exacte productie-REST-methoden uit met uitsluitend
HTTP/native-OTA-randen gemockt, onder AddressSanitizer en UndefinedBehaviorSanitizer.
Dit is geen echt netwerk-, flash-, watchdog- of hardwarebewijs. De scenario's
staan in de bestaande CI-nativegate; de echte firmware wordt ook gebouwd.

Bewijs: `out/manual-ota-hardening-20261024/` met native log, REST-grenslog,
firmwarebuildlogs en resultaatmanifest. Gepubliceerde tags/downloads blijven
ongewijzigd. De correctie is nog niet op de E32 geïnstalleerd.

Vóór een nieuwe fysieke poging is een onderbouwde herstelroute nodig, met
vastgelegde capture van taak/panic-/bootinformatie en behoud van de werkende
alpha28-route. Een mogelijke seriële capture moet via bestaande toegang worden
beoordeeld; een trace ontbreekt momenteel. De nieuwe bron kan de reeds
geïnstalleerde alpha28-uploadhandler niet achteraf wijzigen. Daarom geen blinde
herhaling met alleen een ander doelbestand. De oorzaak van de eerdere native
HTTPS-afwijking en de flash-/powerloss-/herstelacceptatie blijven eveneens open.
