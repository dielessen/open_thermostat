# Bluetooth-apparaten onder Settings

Uitbreiding X01, 24 oktober 2026. **Ontwerp en acceptatievoorwaarden;
nog geen geïmplementeerde of fysiek geteste ondersteuning.** De uitvoering staat
op het [werkbord](WORKBOARD.nl.md). Dit vult het
[BLE-/standalone-ontwerp](SHELLY-BLU-TRV-STANDALONE.nl.md) aan.

## Eerste ondersteunde profielen

Naast de Shelly BLU TRV nemen we de **Shelly BLU H&T Display ZB, SBHT-103C** op.
Volgens de [officiële documentatie](https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/ht_display/)
zendt deze BTHome-bakens met temperatuur, vochtigheid, licht en batterijstatus
iedere 60 seconden; apparaatidentificatie wordt ieder uur uitgezonden.
Temperatuurveld 0x45 is een getekend 16-bits getal in stappen van 0,1 °C.
Een drukknopbericht bevat geen nieuwe temperatuurmeting.
Andere H&T-uitvoeringen krijgen pas ondersteuning na afzonderlijke profielcontrole.

## Settings → Bluetooth devices / Instellingen → Bluetooth-apparaten

Alle teksten beschikbaar in Engels en Nederlands, inclusief fouten en hulp.
De gebruiker doorloopt deze stappen:

1. **Apparaat toevoegen / Add device:** een begrensde zoekactie, met stoppen en
   een zichtbare voortgang. Bestaande apparaten blijven bereikbaar in de lijst.
2. Selecteer het apparaat. Toon geverifieerd model, identiteit en ondersteunde
   functies. Bij onvoldoende identiteit: ‘Wacht op apparaatidentificatie’;
   geen model raden uit naam, signaalsterkte of alleen temperatuurvelden.
3. Toon alleen benodigde koppelstappen voor dit profiel. Passief ontvangen,
   beveiligde koppeling en advertentie-ontsleuteling zijn afzonderlijke zaken.
   Toon fouten begrijpelijk: verkeerd geheim, verlopen koppelvenster,
   niet ondersteund profiel of onvoldoende signaal.
4. Toon een voorbeeldmeting, ontvangstleeftijd, batterij en bronstatus.
   Laat de gebruiker een naam en kamer kiezen en bevestigen of deze bron de
   kamertemperatuur mag leveren. Geen automatische vervanging van een HA-bron.
5. Sla op en lees de opgeslagen configuratie terug. Na herstart blijven naam,
   profiel, kamer en benodigde beveiligingsgegevens behouden; meetwaarden
   moeten opnieuw ontvangen en gekwalificeerd worden.

De apparaatlijst toont model, kamer, temperatuur, vochtigheid, batterij,
signaalsterkte, laatste ontvangst en een concrete fout/status. Houd opengeklapte
details en invoer vast tijdens het bijwerken; vernieuw alleen gewijzigde gegevens.
‘Gevonden’, ‘toegevoegd’, ‘wacht op meting’, ‘bruikbare kamermeting’, ‘verouderd’
en ‘niet bereikbaar’ hebben verschillende betekenissen. Een Bluetooth-bond
of groen signaalicoon geeft geen regelbevoegdheid.

Verwijderen wist uitsluitend de eigen apparaatconfiguratie en bijbehorende
geheimen, met expliciete bevestiging als een kamer deze bron gebruikt. De oude
bronkwalificatie vervalt direct; het bestaande bronuitvalbeleid beslist over
regeling. Geen fabrieksreset, andere bron of warmteopdracht als bijwerking.

## Koppeling en beveiliging

Voor deze sensor beschrijft Shelly: eerst één druk voor setup (‘SEt’), daarna
vier drukken voor het Bluetooth-koppelvenster (‘BLe’, één minuut). Vier drukken
buiten setup keren juist de displaykleuren om. De UI geeft daarom modelspecifieke
instructies en een link naar de fabrikant.

De [Shelly-beveiligingsdocumentatie](https://shelly-api-docs.shelly.cloud/docs-ble/encryption/)
beschrijft AES-CCM voor versleutelde advertenties en het uitlezen van de sleutel
na pairing. Een GATT-bond en deze advertentiesleutel worden apart beheerd.
Een bestaande sleutel kan nodig zijn; onboarding verandert geen passkey,
versleutelingsmodus, kalibratie of Zigbee-configuratie zonder aparte expliciete
gebruikersactie. Geheimen komen niet in logs, normale configuratie-export,
URL's of API-status. Beheer vereist de bestaande geauthenticeerde sessie en CSRF.

## Betrouwbaarheid en acceptatie

Gebruik de bestaande NimBLE-beheerder. Scan, verbinding en verzoeken hebben
vaste grenzen en kunnen worden geannuleerd. Geen tweede BLE-stack; geen drukke
herverbindlus. Meet WiFi-/EMS-responstijd, heap en radiobudget met sensor en TRV
samen. Instellingen worden alleen bij wijzigingen opgeslagen, niet per pakket.

De decoder controleert service, formaat, versleuteling, veldlengtes, bereik en
identiteit. Ongeldige, afgebroken, herhaalde of niet-authentieke pakketten worden
afgewezen. Een knop-, batterij- of identificatiepakket verjongt de temperatuur
niet. Ontvangsttijd is geen bewezen meettijd: kwalificatie moet de meet- en
transportleeftijd begrenzen via het bestaande meetprofiel. De beaconperiode
alleen bepaalt geen geldige bewaartermijn. Bij onbekende leeftijd blijven
waarden diagnostisch; verlopen metingen trekken regelkwalificatie in.

Vóór een release zijn reproduceerbare decoderproeven nodig voor negatieve
temperaturen, corrupte/ontbrekende velden, verkeerde sleutels, herhaling en
identiteitsverwisseling. UI-proeven controleren EN/NL, afbreken, dubbel klikken,
timeouts, opgeslagen readback en behoud van open details.

Daarna één echte SBHT-103C plus één TRV, eerst zonder ketel: model/firmware
vastleggen, onboarding en herstart doorlopen, batterij-/bereikuitval en herstel
meten, actuele metingen vergelijken met een referentie, en bewijzen dat
verouderde gegevens geen regelbevoegdheid houden. Passieve advertentiereceptie
en benodigde beveiligde koppeling worden afzonderlijk aangetoond. Pas daarna
volgt een langere stabiliteitsproef en uitbreiding naar meer apparaten.

Deze uitbreiding behoudt bestaande HA-, EMS- en zonefuncties. Zelfstandig
regelen vereist daarnaast de lokale eigenaar/programmering/tijd uit X01;
alleen een sensor toevoegen realiseert dat nog niet.

## English

Planned additional support: Shelly BLU H&T Display ZB (SBHT-103C), alongside the
BLU TRV. Settings → Bluetooth devices will offer bounded discovery, verified
identity, required security setup, measurement preview, explicit room assignment
and persistent configuration. All UI text and help must support English and Dutch.

Device presence, bonding, received data and qualified room measurements remain
distinct. Reject malformed, unauthenticated and replayed data; expire old
measurements without refreshing them from unrelated packets. Keep secrets out of
logs and ordinary exports. Reuse the existing BLE owner and verify coexistence,
restart, radio loss and recovery on real hardware before declaring support.
