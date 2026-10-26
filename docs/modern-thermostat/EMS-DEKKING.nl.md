# EMS-dekking en apparatenreferentie

Deze wijziging is voorbereid in broncode; niet op de E32 geïnstalleerd.

## Beschikbaar in de aangepaste interface

- Productherkenning uit ontvangen versie-/producttelegrammen, los van de handmatig
  gekozen ketelfoto. Adressen 0x08, 0x10 en 0x17 krijgen de bekende apparaatrol;
  een adres alleen bewijst geen exact model. Hergebruikte product-ID’s worden
  per apparaatcategorie onderscheiden. Bij een onbekende of dubbelzinnige
  productidentificatie wordt geen model gegokt.
- Alle 6.042 entiteitsvermeldingen uit de vastgelegde EMS-ESP-export, in 105
  productgroepen, met naam, datatype, eenheid, grenzen en lees-/schrijfkenmerk.
  Onder elk herkend apparaat staat een inklapbare referentie met zoekfunctie
  en filter voor alle, schrijfbare of alleen-lezen entiteiten.
- Telegrambibliotheek per waargenomen type: 234 telegramnamen uit de telegramlijst,
  aangevuld tot 274 type-ID’s met de bibliotheekmetadata. Alle 1.853 velddefinities
  zijn behouden, inclusief offset, bereik, resolutie, eenheid en toelichting.
  ID-reeksen worden voor ieder betrokken telegramtype beschikbaar gemaakt.
- Ontvangen lokale meetwaarden houden hun eigen kwaliteit en leeftijd. De
  referentie zet ontbrekende waarden niet op nul of op ‘ontvangen’ en verleent
  geen zendbevoegdheid. Open details en zoekfilters blijven bij verversen behouden.
- Op E32 worden ook telegrammen tussen andere busleden via de bestaande begrensde
  wachtrij bekeken voor de passieve inventaris, onafhankelijk van verbose logging.
  De bestemmingscontrole van bestaande stuurcallbacks blijft intact.
- Logregels bevatten bron/bestemming, B/R/W-richting, telegramnaam, type-ID,
  offset en originele framebytes. Het leesbit wordt vóór adresnormalisatie
  bewaard. Rollen worden in de Nederlandse webweergave vertaald; technische namen
  blijven herkenbaar. Syslog ontvangt dezelfde benoemde telegrammen.
- De standaardwebweergave is ESP. Nieuwe sysloginstellingen hebben ESP aan en EMS
  uit. Bestaande expliciete bronkeuzes worden bij laden/opslaan behouden.

De bibliotheek is ingebouwd als afzonderlijke gecomprimeerde webasset: de browser verwerkt de referentie,
geen extra per-telegram JSON-decodering of HTTP-download door de ESP. Alle
verwijzingen zijn begrensd door lokale, met SHA-256 vastgelegde bronbestanden
in `public/ems/SOURCES.json`. De bronbestanden en generator blijven controleerbaar.

## Nog geen volledige EMS-ESP-driverdekking

**Een entiteit beschrijven is iets anders dan haar waarde daadwerkelijk ontvangen,
decoderen, naar HA publiceren of kunnen schrijven.** De huidige eigen meetketen
bevat 69 Classic-ketelvelden en de bestaande Plus-processors. De entiteitenexport
bevat geen volledige uitvoerbare velddecoders of schrijfencoders. Offsettabellen
alleen zijn onvoldoende voor onder meer modelafhankelijke bitvelden, onbekende
waarden, schaalfactoren, fragmentatie, circuitkeuze en antwoordbevestiging.

Voor volledige functionele gelijkwaardigheid blijven deze onderdelen open:

1. Per productfamilie een expliciete koppeling tussen entiteit, telegram,
   offset/bitveld, schaal, ongeldige sentinel en houdbaarheid, met echte of
   upstream vastgelegde pakketproeven. Classic en Plus afzonderlijk beoordelen.
2. Decoders voor thermostaten/circuits, mengmodules, warmtepompen, zonneboilers,
   ventilatie, controller-, gateway-, connect-, extension-, switch-, alert-,
   water- en poolapparaten aansluiten. Productherkenning alleen sluit die niet aan.
3. Nieuwe ontvangen meetwaarden met bron, eenheid en verval naar de HA-entiteiten
   doorgeven. Referentievelden worden geen fictieve HA-sensoren.
4. Voor schrijfbare velden per familie een geteste encoder, grenzen,
   configuratie-/regelbevoegdheid, antwoord/readback en stop-/herstelgedrag maken.
   Een EMS-ESP-schrijfkenmerk wordt geen onbeveiligde schrijfknop.
5. Ondersteunde varianten van het fysieke protocol en busbelasting testen. Passief
   luisteren levert niet noodzakelijk alle instellingen: sommige apparaten sturen
   die pas na een leesverzoek. Ook lezen op aanvraag is een zendactie en blijft
   onder de afzonderlijke zendkwalificatie vallen.

Deze open punten blijven open in het releaseplan. Geen volledige protocol-,
actieve ketel- of schrijfvrijgave op grond van deze referentie-import.

## Bronnen

- [Alle apparaten en entiteiten](https://emsesp.org/nl/All-Entities)
- [EMS Library](https://emsesp.org/nl/ems-library)
- [EMS Telegrams](https://emsesp.org/nl/EMS-Telegrams)
- [EMS-bus](https://emsesp.org/nl/EMS-bus)
- Device library: EMS-ESP32 `8f7049b47a1641cc22c91c63cfb27c1278b282ed`.
- Bibliotheekmetadata: EMS-ESP docs `227c21a942211724f0c481d295fd7f22f976422b`.

Dit zijn vastgelegde protocolfeiten en referentiedata; er is geen upstream
uitvoerbare drivercode gekopieerd of een EMS-ESP-runtime naast de bestaande
controller gestart. Engelse protocolbeschrijvingen blijven Engels wanneer geen
gecontroleerde Nederlandse vertaling bestaat.

## Optimalisatie voor de volgende bèta

De volledige referentie staat in een vaste gzip-asset van 69.922 bytes. De gewone
EMS-paginacode blijft apart leesbaar en gebruikt dezelfde gegevens. Samen circa
85 kB in plaats van ruim400 kB, zonder ESP-decompressie, netwerkafhankelijkheid of
extra runtimegeheugen. De browser ontvangt normale Content-Encoding:gzip via de
bestaande statische route. De generator controleert de exacte uitgepakte inhoud,
alle 6.042 velden en een vaste gzip-tijdstempel. Een ontbrekend referentiebestand
verbergt geen ontvangen meetwaarden en leidt niet tot verzonnen productnamen.

De passieve apparateninventaris bewaart nu maximaal 64 telegramtypen per apparaat,
voor maximaal 16 apparaten. De opslag blijft vast en onder 3 KiB; een volledig
gevulde JSON-inventaris blijft onder 12 kB. Overschrijdingen worden geteld zonder
oude gegevens te verdringen. Dit verruimt zichtbaarheid, niet de decoderdekking.
