# Bluetooth-apparaten onder Settings

Uitbreiding X01, bijgewerkt25oktober2026. **Ontwerp met eerste geteste
decoderbasis; nog geen aangesloten of fysiek geteste apparaatondersteuning.** De uitvoering staat
op het [werkbord](WORKBOARD.nl.md). Dit vult het
[BLE-/standalone-ontwerp](SHELLY-BLU-TRV-STANDALONE.nl.md) aan.

## Voorbereid: passieve SBHT-103C-decoder

`src/control/ShellyHtDisplayAdvertisement.h` levert een pure parser voor het
gedocumenteerde SBHT-103C-deel van [BTHomev2](https://bthome.io/format/).
Temperatuur, vochtigheid, batterij, batterijwaarschuwing, licht/lichtniveau,
knop en ruwe firmware-/modeldeclaraties worden afzonderlijk gedecodeerd.
Temperatuur gebruikt getekende little-endian0,1°C; de projectgrens
−40..85°C wordt vóór omzetting naar honderdsten gecontroleerd.
De [Shelly-identificatietabel](https://shelly-api-docs.shelly.cloud/docs-ble/common/)
vermeldt0x000C voor dit model. Zo'n broadcastdeclaratie is geen authenticatie.

De volledige AD-container wordt eerst gecontroleerd; afgebroken of dubbele
services, verkeerd geordende/dubbele objecten, onbekende objecten en ongeldige
waarden leveren geen gedeeltelijke meetwaarden op. Dit is een strikte subset,
geen algemene BTHome-parser: toekomstige extra objecten worden geweigerd.
Een versleuteld formaat geeft alleen `key_required`, zonder meetwaarden of
identiteit. Authenticatie, AES-CCM en sleutelbeheer zijn hier nog niet geïmplementeerd;
het formaatlabel bewijst geen geldig cryptografisch bericht.

Er is geen veldcache: batterij-, identificatie- en knoppakketten krijgen geen
eerdere temperatuur mee. Een teller wordt alleen als ontvangen getal getoond;
herhaling/omloop, echte acquisitietijd en adres-/sleutelbinding worden niet
gekwalificeerd. Een gewone beacon bevat geen modelidentificatie. De toekomstige
apparaateigenaar moet de expliciet gekozen bron en haar kwaliteit beoordelen.

798 native tests slagen, inclusief16nieuwe decodergevallen en bestaande legacy
BLE-tests. De16gevallen slagen ook onder ASan/UBSan/leakcontrole, met12.000
begrensde willekeurige buffers en6.656mutaties van een synthetisch profielpakket.
De echte ESP32-toolchain controleert de headersyntax met warnings als fouten;
dit is geen complete firmware-/radio- of praktijkproef. Een eerste testsamenstelling
faalde op een GoogleTest-macrocombinatie; die testsyntax is gecorrigeerd en de
foutuitvoer blijft bewaard.

De normale NimBLE-reader selecteert deze parser nog niet; een regressie bewaakt
dat dezelfde Shelly-advertentie door de legacy-reader wordt geweigerd. Geen
extra scanner, verbinding, taak, write, fysieke opdracht of bronwissel.
Settings/onboarding, sleutels, replay-/bronlevensduur, runtimebedrading, Xiaomi
Monitor3 en BLUTRV blijven open. Bewijs: `out/shelly-ht-decoder-20261025/`.

**English:** Prepared strict SBHT-103C advertisement decoder, not a connected
device driver. Sixteen new cases pass within798native tests and separately
under sanitizers; the ESP32 toolchain accepts the header. Whole-container and
field validation is atomic. Encrypted input exposes no measurements. Address
binding, authenticated decryption, replay/acquisition qualification, runtime
onboarding and real-device acceptance remain open. Existing BLE routing is unchanged.

## Eerste ondersteunde profielen

Naast de Shelly BLU TRV nemen we de **Shelly BLU H&T Display ZB, SBHT-103C** op.
Volgens de [officiële documentatie](https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/ht_display/)
zendt deze BTHome-bakens met temperatuur, vochtigheid, licht en batterijstatus
iedere 60 seconden; apparaatidentificatie wordt ieder uur uitgezonden.
Temperatuurveld 0x45 is een getekend 16-bits getal in stappen van 0,1 °C.
Een drukknopbericht bevat geen nieuwe temperatuurmeting.
Andere H&T-uitvoeringen krijgen pas ondersteuning na afzonderlijke profielcontrole.

### Xiaomi Smart Temperature and Humidity Monitor 3

Ook gevraagd: **MJWSD05MMC**, door Xiaomi bevestigd als BLE 5.0-model in de
[Nederlandse specificaties](https://www.mi.com/nl/product/xiaomi-smart-temperature-and-humidity-monitor-3/specs/).
De [BLE Monitor-projectdocumentatie](https://custom-components.github.io/ble_monitor/encrypted_advertisements)
vermeldt voor dit exacte model temperatuur, luchtvochtigheid en batterij via
versleutelde advertenties. Dit is een haalbaarheidsreferentie; onze E32 heeft
nog geen gekwalificeerde decoder voor dit model.

Neem een afzonderlijk Xiaomi/MiBeacon-profiel op in dezelfde apparaatpagina.
De bestaande onversleutelde MJ_HT_V1-decoder bewijst geen ondersteuning voor
deze Monitor 3. Identificeer de echte hardware/firmware en het advertentieformaat;
de naam ‘Monitor 3’ geeft geen vrijgave voor Mini, Pro of andere revisies.

Bij versleutelde data toont de UI **‘Apparaatsleutel nodig / Device key required’**.
Bied een beveiligd invoerveld voor een passende bindkey, controleer formaat en
bevestig de sleutel pas na een authentiek ontsleuteld apparaatbericht. Bewaar
geen Xiaomi-accountwachtwoord op de E32. De bruikbare verkrijgingsroute voor de
sleutel bij dit exacte model blijft een expliciet onderzoekspunt; geen automatische
sleutelextractie of volledige onboarding zonder app/cloud beloven. Bestaande
projecten zoals [xiaomi-ble](https://github.com/Bluetooth-Devices/xiaomi-ble) zijn
protocol-/testreferenties, geen direct te installeren firmwaredriver.

Voorkeursroute is de originele sensorfirmware. Een eventueel afzonderlijk
custom-firmwareprofiel vereist eigen variant-/herstelcontrole en expliciete keuze;
toevoegen mag nooit automatisch flashen. Na verkrijgen en lokaal opslaan van een
geldige sleutel is het ontwerpdoel rechtstreeks uitlezen door de E32 zonder HA
in de ontvangstroute. Dat moet nog met een echt apparaat worden bewezen.

Acceptatie omvat naast de algemene proeven hieronder: correcte en verkeerde
sleutel, gewijzigde sleutel na reset/herkoppelen, authenticatiefout, tellerverloop
en herhaling, gedeeltelijke meetberichten, herstart en batterijverlies. Geen
bronkwalificatie herstellen uit een eerder opgeslagen meetwaarde. Meet de echte
rapportage- en acquisitiegrenzen; neem de Shelly-beaconperiode niet over.
Sleutelverkrijging, offline ontvangst en regelgeschiktheid krijgen elk eigen
bewijs. De UI scheidt een ontbrekende sleutel van een niet bereikbaar apparaat.

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

Daarna per sensorprofiel een echt apparaat (SBHT-103C en MJWSD05MMC), samen
met één TRV en eerst zonder ketel: model/firmware
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
BLU TRV, and Xiaomi Smart Temperature and Humidity Monitor 3 (MJWSD05MMC).
The Xiaomi profile requires authenticated decoding of its encrypted reports;
the exact device-key acquisition workflow remains to be validated. Prefer stock
firmware, never flash automatically, and do not store Xiaomi account passwords.
Settings → Bluetooth devices will offer bounded discovery, verified
identity, required security setup, measurement preview, explicit room assignment
and persistent configuration. All UI text and help must support English and Dutch.

Device presence, bonding, received data and qualified room measurements remain
distinct. Reject malformed, unauthenticated and replayed data; expire old
measurements without refreshing them from unrelated packets. Keep secrets out of
logs and ordinary exports. Reuse the existing BLE owner and verify coexistence,
restart, radio loss and recovery on real hardware before declaring support.
