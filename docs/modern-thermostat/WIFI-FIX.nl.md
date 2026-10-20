# Wifi-herstelbuild — 20 oktober 2026

Deze build vervangt het eerder verstuurde20oktoberpakket voor de wifi-proef.
Alleen E32 V2 / klassieke ESP32 /16MB. Houd de EMS-kabel los; de bestaande
shadowblokkades van ketel-/kraan-/GPIO-uitgangen zijn ongewijzigd.

## Eén keer de nieuwe build installeren

1. Pak de nieuwe ZIP uit. Gebruik **`e32v2-factory.bin` uit dit pakket**.
2. In ESPConnect: **Flash Tools → Flash Firmware**, offset **`0x0`**,
   **Erase entire flash before writing** aangevinkt. Klik Flash Firmware.
   Dit is een schoon begin: aanwezige instellingen verdwijnen. Mark heeft de
   oorspronkelijke flashbackups al expliciet overgeslagen; dit pakket bevat ze niet.
3. Controleer de geslaagde schrijf-/verificatiemelding. Kies **Disconnect**,
   haal USB kort los en sluit hem weer aan, zonder BOOT ingedrukt te houden.
   Het bord start vanzelf in zijn setupnetwerk; geen seriële opdracht nodig.

De factory-image is nog steeds0xB80000bytes lang; de **inhoud/checksum is nieuw**.
De concrete checksum staat in `FACTORY-CHECK.txt` in de ZIP. Een volledige
ComputeMD5-check hoort vóór de eerste normale boot: daarna verandert NVS.

## Verbinden

- Wifi: **`OpenThermostat-xxxxxx`**, wachtwoord **`openthermostat`**.
- Browser: **http://10.10.10.1/**.
- Gebruikersnaam: **`admin`**, wachtwoord: **`admin`**.
- De pagina zoekt op de achtergrond naar **2,4GHz**-netwerken. Geen5GHz.
  Kies je netwerk of vul een verborgen SSID handmatig in en klik Verbinden.
- Bij een verkeerd wachtwoord blijft het setupnetwerk beschikbaar; probeer opnieuw.
- Na succes verschijnt het thuisnetwerk-IP. Klik desgewenst **Afronden en
  setupnetwerk sluiten**, verbind je telefoon/laptop weer met je thuisnetwerk
  en open het getoonde adres. Zonder Afronden vervalt setup na het15minutenvenster.

De ESP32 heeft één radio; bij verbinden met een ander kanaal kan de telefoon
kort opnieuw associëren. De pagina hervat automatisch, maar RF-stabiliteit en
het gedrag van jouw telefoon moeten nog fysiek worden bevestigd. Bij een vraag
van de telefoon om zonder internet verbonden te blijven, kies je dat.

## Latere hersteltoegang

De opgegeven standaardlogins gelden ook bij een update met bestaande access-NVS.
Wifi wijzigen kan via de ingelogde herstelroute; fysieke USB-opdracht `setup`
met regeleinde Enter blijft beschikbaar. In **ESPConnect v1.1.23** deelt
Serial Monitor de bestaande verbinding: verbonden laten, **Serial Monitor →
Start**, wachten op **Live**, dan **Reset**. Er is geen aparte Connect-knop
voor die monitor. Gebruik115200baud.

Softwarechecks staan in `ACCEPTANCE.json` in het pakket. Het zijn geen bewijs
dat deze nieuwe build al op jouw bord is geflasht of dat de fysieke wifi-proef
geslaagd is. Noteer scan, verkeerde sleutel/retry, succesvolle verbinding en
herverbinding na stroomonderbreking op het bijgewerkte testblad.
