# Eerste geïsoleerde bordtest — invulblad

Status bij levering: **niet uitgevoerd**. Dit blad is geen verwarmingsvrijgave.
Gebruik de [testgids](INTEGRATED-TEST.nl.md); houd de EMS-kabel los en Tado intact.

## Voor schrijven

- [ ] Exact E32 V2 / ESP32 / 16MB en security-status vastgesteld.
- [ ] Originele instellingen geëxporteerd; twee onafhankelijke volledige flashlezingen
  byte-identiek en privé opgeslagen; originele herstelsoftware beschikbaar.
- [ ] Pakketchecksum en broncommit genoteerd.

## USB en netwerk

- [ ] Fabrieksimage geschreven en geverifieerd vóór normaal booten.
- [ ] Unieke admin/setup-credentials alleen privé uit fysieke USB-console overgenomen.
- [ ] Wifi-only setup, fout wachtwoord, geslaagde opslag, AP-afloop en USB-herstel getest.
- [ ] Ethernet-only na herstart getest, zonder wifi-scan/reconnect; PSRAM/heap/resetreden vastgelegd.
- [ ] HTTP zonder credentials en ongeldige upload geweigerd vóór schrijven.

## HA-shadow, zonder echte uitgangen

- [ ] Afzonderlijke test-HA/broker/prefix met juiste ACL en unieke adapter-ID.
- [ ] Kamer via GUI gemaakt; revision/digest, firmware-ACK en blijvende kamer-ID gecontroleerd.
- [ ] Doel en native schema bevestigd; geen optimistisch alleen lokaal doel.
- [ ] Meetbron expliciet gekwalificeerd, of bewust onbruikbaar/unknown; geen cache als nieuwe meting.
- [ ] Bronstilte, HA/MQTT/E32-herstart, LWT en oude override gecontroleerd.
- [ ] Gesimuleerde vraag apart zichtbaar; climate IDLE, beide outputflags false.
- [ ] Eventuele eindige sensorbench beëindigd; bron ingetrokken en optie exact teruggelezen/hersteld.

## Apart vóór normale ingebruikname

OTA/herstel, stroomuitval/NVS-vol, langdurige broncadans, echte kraanbediening,
ketelregeling, minimumdoorstroming, stop/naloop en overige masterplaneisen zijn
afzonderlijke bouw-/acceptatiepunten. Een afgevinkt blad hierboven geeft daarvoor
geen GO.

Datum / firmwarecommit / HA-commit / testopstelling:

Bewijsbestanden (geredigeerd; geen credentials of volledige flashbackups):

Afwijkingen / stopreden / eigenaar / volgende proef:
