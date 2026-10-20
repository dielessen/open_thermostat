# Wifi/Bluetooth-opstartherstel — 20 oktober 2026

## Vastgestelde fout

De USB-proef van Mark toont `Should enable WiFi modem sleep when both WiFi and
Bluetooth are enabled` gevolgd door `abort()`. Bluetooth is dan al gestart;
de setupcode schakelde wifi-modemslaap uit. De firmware brak af voordat het
setupnetwerk beschikbaar was en voordat de USB-opdracht `setup` kon worden
verwerkt. De vijftienminutentimer verklaart deze crash niet.

De crashhash `3424af401e408bbf` hoort bij de eerdere wifi-build. Dezelfde fout
stond ook nog in de daaropvolgende kamerherstelbuild. De kamermelding in dat
log is geen bewijs dat het nieuwe lege kamerbestandssysteem geïnstalleerd was.

## Gerichte wijziging

De E32-setup selecteert nu de officiële `WIFI_PS_MIN_MODEM`-stand vóór het
starten van wifi en schakelt modemslaap niet meer uit. Dit behoudt de
Bluetoothfunctie en volgt de standaard van de vastgepinde Arduino/IDF-SDK.
Het nieuwe succesbericht bevat `BLE coexistence MIN_MODEM`.

De oorspronkelijke radiotestdubbel negeerde `setSleep` en miste deze fout.
Die grens controleert nu Bluetooth/modemslaap: oude productiecode faalt op
deze proef, de gerepareerde code doorloopt ook scan, verbinden en afronden.
Dit simuleert de SDK-beperking; het vervangt geen echte radioproef.

Kamerherstel, HA-herstel, lokale toegangsdefaults en alle EMS-/TRV-/GPIO-
blokkades blijven behouden. Er is geen HA-productie-installatie gedaan.

## Installatie en fysieke acceptatie

Gebruik uitsluitend `e32v2-factory.bin` uit deze nieuwe ZIP voor de eerder
afgesproken schone USB-testinstallatie: offset `0x0`, met volledig wissen.
**Dit verwijdert aanwezige instellingen.** Niet automatisch flashen of wissen;
bewaar de oude ZIP. Bestandsgrootte alleen is geen versiecontrole: vergelijk
de nieuwe checksum uit `FACTORY-CHECK.txt`.

Na geslaagde schrijfverificatie: Disconnect, USB los/vast, geen BOOT indrukken.
Houd EMS los. Zoek binnen vijftien minuten `OpenThermostat-xxxxxx` en open
http://10.10.10.1/. Toegangsgegevens staan in `WIFI-FIX.nl.md`.

Acceptatie op het bord blijft open tot:

1. Normale boot zonder abort en met het nieuwe `MIN_MODEM`-succesbericht.
2. Setup-SSID zichtbaar en de pagina bereikbaar.
3. Netwerkscan, verkeerde sleutel en opnieuw proberen werken.
4. Juiste sleutel geeft opgeslagen verbinding plus thuisnetwerk-IP.
5. Afronden, bereiken via thuisnetwerk en opnieuw verbinden na stroomcyclus.
6. Kamer toevoegen, opslaan, herladen, hernoemen en verwijderen zonder
   niet-bestaande-kamermelding.

Bij een nieuwe crash: stop de proef en lever de fout/backtrace plus `ELF file
SHA256`, zonder wachtwoordregels. Blijf niet `setup` herhalen bij een bootcrash.
Het bijbehorende ELF en de symbolen worden bij het lokale buildbewijs bewaard.
Geen vrijgave voor verwarming, ketelbediening of OTA wordt hiermee beweerd.
