# Bluetooth-apparaten onder Settings

Uitbreiding X01, bijgewerkt 25 oktober 2026. **Software voor lokale
SBHT-103C-diagnoseontvangst aangesloten in de ongepubliceerde grote bèta.**
Nog geen fysieke apparaatacceptatie of vrijgave als regelbron. De geïnstalleerde
basis blijft E32 alpha36 / HA dev48; er is niets geflasht of geïnstalleerd.
Het [werkbord](WORKBOARD.nl.md) blijft de acceptatiechecklist.

## Aangesloten: lokale Shelly-ontvangst en apparaatinstellingen

De E32-pagina **Settings → Bluetooth devices / Instellingen → Bluetoothapparaten**
beheert maximaal acht expliciet gekozen **Shelly BLU H&T Display, SBHT-103C**-
adressen. Een zoekactie toont maximaal 32 sinds opstarten waargenomen adressen;
modelselectie blijft handmatig. Een adres, naam of RSSI bewijst geen model.
De pagina is Engels/Nederlands en wordt alleen op E32 met de sessie-API getoond.

Dezelfde bestaande NimBLE-scanner ontvangt de advertenties. Zonder ingestelde
profielen verandert het automatische scangedrag van modern HA-bedrijf niet.
Met profielen werkt de lokale ontvangst zonder HA. De SDK-callback kopieert
alleen ingestelde adressen naar een vaste wachtrij van vier frames. De bestaande
hoofdloop verwerkt maximaal één frame per keer; geen extra taak, BLE-client,
koppelverzoek, kraanwrite of automatische bronwissel. De legacy ATC/MJ_HT_V1-route
blijft afzonderlijk werken en selecteert dit nieuwe profiel niet.

### Sleutel, integriteit en levensduur

Ondersteund zijn de expliciete keuzes onversleuteld en BTHome v2 AES-CCM.
De gebruiker voert een bestaande bindkey in als 32 hexadecimale tekens.
Mbed TLS uit de firmware-SDK controleert de MIC met de gekozen MAC en sleutel;
nonce en ontbrekende v2-AAD volgen het [officiële protocol](https://bthome.io/encryption/).
Verkeerde sleutel, gewijzigde inhoud, te lange/afgebroken containers en
plaintext bij een versleuteld profiel leveren geen metingen op.

Iedere veldleeftijd begint bij de oorspronkelijke SDK-ontvangst, vóór de wachtrij.
Temperatuur, vochtigheid, batterij en licht verlopen na drie minuten; knoppen
na twee seconden; model-/firmwaredeclaraties na 65 minuten. Een batterij-,
knop- of identificatiebericht vernieuwt geen eerdere temperatuur. Een defecte
of teruglopende ontvangstklok sluit de eigenaar tot herstart. Tijdens een
firmware-update wacht ontsleuteling; wachtrijvertraging maakt berichten niet jonger.
Nieuwe uitgebreide Bluetooth-HTTP-reads worden tijdens de update afgewezen om
niet tegelijk extra JSON-buffers naast TLS toe te laten.

Alleen een geldig geauthenticeerd en strikt gedecodeerd bericht verhoogt de
ontvangen 32-bits teller. Oude/herhaalde tellers vernieuwen geen waarden of
leeftijden. Dit geldt **binnen dezelfde boot**; na herstart is nog geen blijvende
anti-replaykwalificatie aanwezig. Berichtintegriteit bewijst bovendien geen
fysieke acquisitietijd. Daarom blijven `measurement_qualified` en
`control_qualified` expliciet onwaar. De gegevens zijn diagnoseontvangst en
worden niet aan de verwarmingsregelaar, kraanroute of HA-meetkwalificatie gevoerd.

### Opslaan en publieke API

De versiegebonden compacte lijst staat in `bt.devices` in het bestaande
`ot_network/settings`-blob. Geen nieuwe partitie/namespace en geen schrijfcyclus
per advertentie. De bestaande totale grens van 2048 bytes geldt ook met broker-,
netwerk- en installatieprofielinstellingen; bij ruimtegebrek wordt de volledige
wijziging geweigerd, zonder afkappen of andere instellingen te wissen.

- `GET /config/bluetooth`: publieke instellingen plus ontvangststatus en een
  sessiegebonden ETag voor precies de actuele complete instellingen.
- `POST /config/bluetooth`: sessie/CSRF/origin, update-/ketelproefbewaking en
  verplichte `If-Match`. Alleen exact hetzelfde adres/profiel/versleuteling kan
  de bestaande sleutel behouden; vervangen en wissen zijn expliciete acties.
- `GET /bluetooth/status`: alleen status, zonder formuliervelden of ETag te
  vernieuwen. Polling laat invoer, focus en open panelen staan. Fouten maken de
  getoonde ontvangstwaarden onbekend en laten het conceptformulier behouden.
- `POST /config/bluetooth/scan`: één expliciete begrensde zoekscan; geen GET-
  neveneffect of automatische herhaling na weigering. Scaninstellingen,
  cooldown en de bestaande scannerlevensduur blijven gelden.

Bindkeys worden nooit teruggestuurd, ook niet door `GET /config/device`, en niet
in browseropslag bewaard. De oudere netwerkpagina behoudt verborgen bindings
bij opslaan. Een expliciete volledige configuratierestore wordt gevalideerd.
Opslaan sluit de oude ontvanger **vóór** de duurzame schrijf-/terugleescontrole;
een onzekere schrijfactie blijft gesloten en wordt niet blind herhaald.
De nieuwe lijst wordt na een handmatige apparaatherstart actief. Een ongeldige
lijst kan na expliciete bevestiging worden leeggemaakt, met behoud van andere
instellingen; een onleesbare volledige netwerkconfig wordt niet stil vervangen.

### Softwarecontrole en resterende acceptatie

De bestaande en nieuwe native suites en losse echte-Mbed-TLS/sanitizergevallen
staan bij `test/test_native/test_ble_device_settings.cpp`,
`test/test_native/test_managed_ble_observer.cpp`, `test/ble_crypto/mbedtls.cpp`
en `test/bluetooth-browser.cjs`. De volledige bibliotheek gebruikt het officiële
publieke BTHome-voorbeeld en onafhankelijk gemaakte protocolfixtures; geen
echte apparaatsleutel of productieverbinding. Boardbuilds controleren de echte
SDK-koppeling; browserproeven gebruiken uitsluitend nagebootste HTTP-antwoorden.
Actuele resultaten en bronhashes staan bij de bundelcontrole.

Open blijven: echte SBHT-103C-ontvangst, sleutelverkrijging, hardware-/firmware-
variant, reboot-/batterij-/radio-/resourceproeven, blijvende anti-replay en
acquisitiekwalificatie. Xiaomi Monitor 3, Shelly TRV en zelfstandig regelen
zijn nog afzonderlijke implementatie-/acceptatiepunten. Geen werkende
zelfstandige thermostaat of fysieke regelautorisatie afvinken op deze diagnosepagina.

**English:** The unpublished beta connects bounded, local SBHT-103C reception
and EN/NL device settings to the existing E32 scanner. It supports explicit
plain/encrypted bindings, real SDK AES-CCM verification, write-only bindkeys,
conditional durable storage, original reception ages and boot-local replay
rejection. Diagnostics remain separate from qualified control measurements.
Real-device acceptance, persistent replay/acquisition qualification, Xiaomi,
TRV control and standalone heating remain open. Nothing has been deployed.

## Gevraagde profielen en protocolreferenties

De gevraagde reeks omvat naast Shelly BLU TRV de **Shelly BLU H&T Display ZB, SBHT-103C**.
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

## Nog te bouwen: volledige onboarding en koppeling aan kamers

Onderstaande stappen zijn het verdere doelontwerp, niet de hierboven aangesloten
diagnosepagina. Kamerselectie, bonds, sleutelverkrijging en regelbronkwalificatie
zijn nog niet beschikbaar.

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
buiten setup keren juist de displaykleuren om. De volledige onboarding moet daarom modelspecifieke
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
