# Wifi instellen met automatisch aanmeldvenster — 20 oktober 2026

## Gebruik

1. Verbind met **OpenThermostat-xxxxxx**. De telefoon of laptop hoort nu zijn
   wifi-aanmeldvenster met de instelpagina te openen. Gebeurt dat niet, kies
   **Aanmelden bij netwerk** of open **http://10.10.10.1/** in een browser.
2. Kies je **2,4 GHz-thuisnetwerk**, voer het wifi-wachtwoord in en kies
   **Verbinden**. De setup-wifi blijft beschikbaar tijdens deze controle.
3. Na een geslaagde verbinding verschijnt **Verbonden met wifi**, met het
   echte thuisnetwerkadres. Je hoeft niet apart op Afronden te klikken.
   De pagina bevestigt automatisch dat het adres ontvangen is. Het
   setupnetwerk sluit daarna na **acht seconden**; twee seconden later
   probeert de pagina het nieuwe adres te openen.
4. Je telefoon moet zelf terugkeren naar je thuiswifi. Lukt dat niet vanzelf,
   kies je thuiswifi. Sluit je telefoon het aanmeldvenster, open dan het
   getoonde adres in je gewone browser. Het apparaat blijft daar beveiligd
   met de bestaande beheerlogin. Bewaar het adres eventueel als bladwijzer.

Een apparaatwebpagina kan geen wifi-netwerk op je telefoon selecteren of
afdwingen dat het systeemaanmeldvenster openblijft. Automatisch openen en
deze overgang moeten daarom ook op de echte telefoon worden beproefd.
HTTPS-sites worden niet onderschept: het aanmeldvenster gebruikt de normale
HTTP-captive-portalcontroles van het besturingssysteem.

## Fouten en terugval

- Verkeerd wachtwoord, geen DHCP of onbevestigde opslag: geen succesmelding
  of automatische afsluiting; dezelfde pagina laat je opnieuw proberen.
- De thuiswifi valt weg tijdens het aftellen: afsluiten wordt geannuleerd
  en de pagina trekt het oude succesadres in zodra zij de status ontvangt.
- Het DHCP-adres verandert tijdens het aftellen: de oude afsluittermijn
  vervalt; de pagina moet het nieuwe adres eerst ontvangen en bevestigen.
- Een verloren antwoord op automatisch afronden wordt via de status
  hersteld. Een herhaalde aanvraag verlengt de afsluittermijn niet.
- Ontvangt de pagina nooit het adres, dan sluit het setupnetwerk niet
  voortijdig. Het bestaande maximale setupvenster van vijftien minuten
  blijft gelden. USB `setup` + Enter heropent setup na gecontroleerde reboot.

## Technische begrenzing

De bestaande Arduino DNSServer en WebServer verzorgen wildcard-DNS en de
Android/iOS/Windows-proberoutes. DNS-TTL is nul en DNS stopt samen met het AP.
Als DNS niet kan starten, blijft het directe IP bereikbaar en meldt USB dit.
Alleen de setupflow op de **lokale AP-socketinterface** heeft geen extra
HTTP-login nodig. Het juiste Host-adres alleen volstaat niet: via de
thuisnetwerkinterface blijft de beheerlogin vereist. Overige configuratie,
bestandsupdates, reboot en bediening blijven beveiligd. Methode- en
same-origincontroles blijven ook op de setupflow van kracht.

De Bluetooth-modemslaapreparatie, kamer-/HA-herstel en alle EMS-/TRV-/GPIO-
uitvoerblokkades blijven behouden. Dit is geen vrijgave voor verwarming.

## Testpakket en installatie

Gebruik het aparte **wifi-portal**-pakket; eerdere ZIPs blijven bewaard.
Firmware **en** de bijbehorende webbestanden zijn gewijzigd: alleen de
firmware vernieuwen laat de oude webpagina staan.

De eerder afgesproken schone USB-testinstallatie gebruikt de nieuwe
`e32v2-factory.bin` op **0x0**, met volledig wissen en schrijfverificatie.
**Dat wist wifi, kamers, programma's en overige instellingen.** Daarna
Disconnect en USB los/vast, zonder BOOT. Houd EMS los. Controleer de
nieuwe checksum uit `FACTORY-CHECK.txt` en de USB-regel
`Setup captive portal: active`. Toegangsdefaults staan in `WIFI-FIX.nl.md`.

Dit factorybeeld is **geen OTA-updatebestand**. De huidige handmatige
SPIFFS-upload neemt kamers/programmaconfiguratie nog niet automatisch over.
Gebruik die niet alsof het een bewezen instellingenbehoudende upgrade is.
GitHub Releases met geïntegreerde, instellingenbehoudende apparaatupdates
blijven de afzonderlijk geautoriseerde vervolgstap.

Fysieke acceptatie: setup-SSID -> automatisch aanmeldvenster -> scan ->
verkeerde sleutel/herstel -> DHCP/succesadres -> automatisch AP uit ->
thuisnetwerkadres bereikbaar/login -> stroomcyclus/herverbinding. Controleer
ook tijdelijk wifi-verlies tijdens het aftellen. Software/browserproeven
vervangen deze echte radioproef niet.
