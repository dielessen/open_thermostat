# Bluetooth-apparaten onder Settings

**Beta.16 (28 oktober):** sensoren met pvvx-firmware (github.com/pvvx/ATC_MiThermometer)
krijgen het profiel "Thermometer met pvvx-firmware (BTHome)": BTHome v2, onversleuteld
of met bindkey, en het oudere PVVX Custom-formaat (0x181A). De MJWSD05MMC van de
eigenaar (pvvx 5.9, naam `BTE_A3E8DB`) stuurt BTHome zonder versleuteling elke 5 s;
als "Xiaomi Monitor 3" (MiBeacon) gekoppeld bleef hij daarom op "wachten". Per sensor
tonen tellers hoeveel berichten zijn ontvangen en niet herkend.

Uitbreiding X01, bijgewerkt 25 oktober 2026. **Software voor lokale
SBHT-103C-/MJWSD05MMC-diagnoseontvangst aangesloten in de ongepubliceerde grote bèta.**
Nog geen fysieke apparaatacceptatie of vrijgave als regelbron. De geïnstalleerde
basis blijft E32 alpha36 / HA dev48; er is niets geflasht of geïnstalleerd.
Het [werkbord](WORKBOARD.nl.md) blijft de acceptatiechecklist.

## Aangesloten: lokale Shelly-/Xiaomi-ontvangst en apparaatinstellingen

De E32-pagina **Settings → Bluetooth devices / Instellingen → Bluetoothapparaten**
beheert maximaal acht expliciet gekozen adressen, met de afzonderlijke profielen
**Shelly BLU H&T Display, SBHT-103C** en **Xiaomi Monitor 3, MJWSD05MMC**. De voorbereide beta.4 toont maximaal 128 waargenomen adressen in een afzonderlijk scrollvak, inclusief apparaten zonder naam en zonder ondersteund profiel. Het aantal gevonden apparaten staat erboven; bij overschrijding verschijnt een melding. Een nieuwe expliciete zoekactie wist de vorige ontdeklijst. De acht opgeslagen koppelingen staan hier los van;
modelselectie blijft handmatig. Een adres, naam of RSSI bewijst geen model.
De pagina is Engels/Nederlands en wordt alleen op E32 met de sessie-API getoond.

Dezelfde bestaande NimBLE-scanner ontvangt de advertenties. Zonder ingestelde
profielen verandert het automatische scangedrag van modern HA-bedrijf niet.
Met profielen werkt de lokale ontvangst zonder HA. De SDK-callback kopieert
alleen ingestelde adressen naar een vaste wachtrij van vier frames. De bestaande
hoofdloop verwerkt maximaal één frame per keer; geen extra taak, BLE-client,
koppelverzoek, kraanwrite of automatische bronwissel. De legacy ATC/MJ_HT_V1-route
blijft afzonderlijk werken en selecteert dit nieuwe profiel niet.

### Xiaomi Monitor 3: apart MiBeacon-profiel

Het profiel `xiaomi_monitor_3` accepteert uitsluitend de productdeclaraties
`0x2832` en `0x4c47` uit de [upstream apparatentabel](https://github.com/Bluetooth-Devices/xiaomi-ble/blob/main/src/xiaomi_ble/devices.py)
(blob `af2186eae54f0e8ff0bb35b3640ec4bae0a15f92`). `0x0b48` hoort bij
CGG1-ENCRYPTED en is nadrukkelijk geen Monitor3-profiel.

De [upstream parser](https://github.com/Bluetooth-Devices/xiaomi-ble/blob/main/src/xiaomi_ble/parser.py)
(blob `1b85f93c42a5ef6cb709f7c03b007d43d04de61a`) levert de protocolreferentie:
service FE95, MiBeacon v4/v5, AES-CCM met MIC4 en AAD `11`. De nonce gebruikt
het **omgekeerde** display-MAC, product-ID, frameteller en drie extra
counterbytes. Dit is bewust een andere route dan BTHomev2. Een meegezonden MAC
moet bij het geselecteerde adres horen; mesh, verkeerde versie/product-ID,
onversleutelde input, kapotte of dubbele containers worden geweigerd.

De strikte TLV-subset leest `1004/1006/100a/100d` en
`4c01/4c02/4c03/4c08`: temperatuur, vochtigheid en batterij. Getekende gehele
waarden en IEEE-floats worden vóór omzetting begrensd; NaN/oneindig,
afgebroken of dubbele semantische velden en onbekende objecten leveren geen
partiële meetwaarden op. Eenzelfde versleuteld pakket met de naam ‘MJ_HT_V1’
wordt ook door de oude reader geweigerd. Er wordt geen oude firmware aangepast.

De normale profielkeuze biedt voor Xiaomi alleen MiBeacon-versleuteling.
Een protocol-/profielwissel neemt geen opgeslagen sleutel van het andere
profiel over. Ontvangst onder een nog niet opgeslagen adres, profiel of sleutel
wordt niet als de nieuwe koppeling getoond: de meetweergave wacht op opslaan
en herstart, terwijl de invoer behouden blijft.

De fixtures zijn onafhankelijk met Python AESCCM gemaakt; ze zijn **geen echte
Monitor3-opname**. Upstream's huidige tests bevatten geen expliciet benoemde
Monitor3-opname. Werkelijke variant/firmware, sleutelverkrijging,
rapportage-/acquisitiegrenzen, radio en batterij-/herstartgedrag blijven dus te
toetsen. Een werkende fysieke sensor of regelbron wordt hier niet afgevinkt.

### Sleutel, integriteit en levensduur

Voor Shelly zijn de expliciete keuzes onversleuteld en BTHome v2 AES-CCM
beschikbaar; Xiaomi gebruikt uitsluitend het afzonderlijke MiBeacon v4/v5-profiel.
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

### Statusuitlezing en navigatie in de volgende bèta

De pagina heeft één automatische statusaanvraag per vijf seconden. Een
verborgen tab stopt de timer en trekt de lopende statusaanvraag in. Terugkeren
haalt één nieuwe momentopname op, zodra geen configuratielaad-/schrijfactie
bezig is. Een laat antwoord kan geen nieuwere uitlezing vervangen. Conceptnaam,
sleutelactie/getypte sleutel, focus en open details blijven bij tabwisselen
behouden; verlaten van de pagina wist de getypte sleutel.

Een expliciete configuratielaadactie of vereiste save-readback behoudt zijn
bestaande begrensde uitlezing, ook bij tabwisselen. Navigatie trekt deze reads
in. Reeds ingediende saves en scans houden hun eigen tienseconden-deadline,
worden nooit automatisch herhaald en doen na verlaten geen verificatie-readback.
Bij terugkeren leest de nieuwe pagina de opgeslagen configuratie opnieuw. Een
onbevestigde save blijft onbevestigd, ook als latere statusreads slagen. Alleen
een eerdere statusleesfout wordt bij herstel opgeruimd.

Dit verandert de radio, rapportkwalificatie, opslag of scanbediening niet.
Softwaretests gebruiken uitsluitend geïsoleerde HTTP-antwoorden.

### Opslaan en publieke API

De versiegebonden compacte lijst en de sleutels staan **samen in één privéblob**
`ot_bluetooth/settings`, buiten het netwerkdocument. Dit is bewust gewijzigd
vóór uitrol: oudere firmware kan onbekende netwerkvelden terugsturen. Door
sleutels nooit in dat document te plaatsen, kunnen die ook bij terugrollen niet
via de oudere netwerkreader verschijnen. De ongewijzigde netwerkreader en de
nieuwe opslagfuncties worden samen in de hostproef uitgevoerd.

De private blob is begrensd op 2048 bytes inclusief NUL, in de bestaande
NVS-partitie. Er is geen partitievergroting, tweede sleuteltransactie of
schrijfcyclus per advertentie. Acht bindings met elk een sleutel en een naam
van 40 bytes passen binnen de geteste JSON-grens. Opslag-/commit-/terugleesfouten
blijven fouten: geen automatische wisactie of poging om netwerkruimte vrij te
maken. Een ontbrekende selectie wordt alleen-lezen als leeg geïnterpreteerd;
corruptie krijgt geen opgeslagen/default- of netwerkfallback.

Vóór schrijven worden de actuele NVS-statistieken en de bestaande 20 KiB-
partitie gecontroleerd. De nieuwe blob moet passen zonder oude bytes alvast
vrij te rekenen, met ruimte voor vervanging van de regelconfiguratie,
garbage collection en de reservering van een eventuele modelopslageigenaar.
Onbekende of inconsistente statistieken weigeren de wijziging. De API meldt
onvoldoende ruimte vóór het sluiten van de huidige ontvanger; de opslaglaag
controleert opnieuw vóór het openen van een schrijfnamespace. Geen automatische
wisactie. Dit bewijst geen aaneengesloten vrije pagina's of fysieke capaciteit.
Een gefaalde modelopslageigenaar houdt zijn reservering tot zijn vernietiging;
deze backend blijft voorbereid en is niet als normale leerroute geactiveerd.
De grensberekening heeft 10 sanitizergevallen; de voorbereide NVS-modelbackend
heeft daarnaast 21 hostgevallen met echte Mbed-TLS-SHA en een nagebootste SDK.

- `GET /config/bluetooth`: publieke instellingen plus ontvangststatus en een
  sessiegebonden ETag voor precies de actuele private instellingen. De netwerk-
  en Bluetoothformulieren hebben elk een eigen begrensde readbackcontrole en
  maken elkaars ongewijzigde formulier niet ongeldig.
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
in browseropslag bewaard. Nieuwe bindings kunnen niet via een netwerkrestore
worden ingevoerd. Gewone netwerkopslag verandert de private lijst niet;
onbekende oudere netwerkvelden worden behouden en niet als nieuwe bron gelezen.
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
Actuele resultaten en bronhashes staan bij de bundelcontrole. De private opslag
heeft daarnaast 32 gerichte SDK-grensgevallen, samen met de echte regelconfiguratieopslag, onder ASan/UBSan: eigen namespace,
read-only ontbrekende selectie, netwerkbehoud, commit-/terugleesfouten,
terminator-/groottegrenzen en geen sleutel in de oudere netwerkreader. Ook de normale graph-configuratieschrijver bewaart nu de modelreservering; een geforceerde stringallocatiefout sluit de NVS-handle en behoudt de eerdere callerbytes.
De native suite heeft nu 906 geslaagde gevallen. Apart slagen 52 eigenaar-/
instellingen-/MiBeacon-/TRV-parsergevallen en 25 echte Mbed-TLS-/ontvangstgevallen
onder ASan/UBSan/leakcontrole; de eerdere 18 sessiegevallen blijven behouden.
Twaalf browserprofielen dekken de drie profielen, EN/NL en 1280/320 pixels, inclusief
behoud van invoer/focus en geen oude metingen onder een gewijzigde conceptbron.

Open blijven: echte SBHT-103C-/MJWSD05MMC-ontvangst, sleutelverkrijging, hardware-/firmware-
variant, reboot-/batterij-/radio-/resourceproeven, blijvende anti-replay en
acquisitiekwalificatie. Shelly TRV-bediening en zelfstandig regelen zijn nog afzonderlijke implementatiepunten;
ook beide sensorprofielen houden hun fysieke acceptatie apart. Geen werkende
zelfstandige thermostaat of fysieke regelautorisatie afvinken op deze diagnosepagina.

**English:** The unpublished beta connects bounded, local SBHT-103C reception
and EN/NL device settings to the existing E32 scanner. It supports explicit
plain/encrypted bindings, real SDK AES-CCM verification, write-only bindkeys,
conditional durable storage, original reception ages and boot-local replay
rejection. Diagnostics remain separate from qualified control measurements.
A separate Monitor3 profile now uses the two upstream product declarations and
MiBeacon AES-CCM with its own nonce/AAD. Real-device acceptance, key acquisition,
persistent replay/acquisition qualification, TRV control and standalone heating
remain open. Nothing has been deployed.

## Shelly BLU TRV: lokale diagnoseontvangst

Dezelfde ongepubliceerde bundel bevat ook een expliciet `shelly_blu_trv`-profiel
voor SBTR-001AEU. Volgens de [fabrikantbeschrijving](https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/trv/)
hebben de herhaalde temperatuurvelden verschillende betekenissen: gemeld doel,
berekende TRV-temperatuur en optioneel externe temperatuur. De ontvanger houdt
ze apart, met hun oorspronkelijke ontvangstleeftijd. Een volledig rapport
zonder externe temperatuur verwijdert de oude externe waarde. Batterij- of
statusberichten vernieuwen geen temperatuur.

BTHome-versleuteling gebruikt dezelfde echte AES-CCM-controle met een expliciete
bindkey. De statusrevisie blijft een ruwe diagnosewaarde; zij bevestigt geen
opdracht, kleppositie of afgifte. De modelkeuze is een opgeslagen selectie en
geen bewezen apparaatidentiteit. De pagina verklaart dit in Nederlands en Engels.

Er worden geen GATT-verbinding, pairing, kalibratie, schemawijziging, boost of
kraanopdracht uitgevoerd. Eenmalige temperatuurvelden, onbekende objecten,
verkeerde lengtes of corrupte berichten leveren geen gedeeltelijke waarden op.
Ook dit profiel blijft **geen gekwalificeerde kamerbron of actuator**.
Echte apparaat-/firmwareacceptatie, sleutelverkrijging, beveiligde verbinding,
causale opdrachtterugmelding, stopgedrag en zelfstandige regeling blijven open.
De protocolproeven gebruiken fixtures, geen ontvangen TRV-pakket.

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
nu een apart softwareprofiel voor dit formaat, maar nog geen fysiek
gekwalificeerde decoder voor deze hardware.

Het afzonderlijke Xiaomi/MiBeacon-profiel staat nu op dezelfde apparaatpagina.
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

The unpublished beta connects local diagnostic reception/settings for Shelly
BLU H&T Display ZB (SBHT-103C) and Xiaomi Monitor 3 (MJWSD05MMC). BLU TRV
control and the full standalone/qualified room route remain planned.
The Xiaomi profile requires authenticated decoding of its encrypted reports;
the exact device-key acquisition workflow remains to be validated. Prefer stock
firmware, never flash automatically, and do not store Xiaomi account passwords.
The diagnostic page offers bounded discovery, explicit profiles, write-only keys
and persistent private configuration. Full key acquisition/bonding, physical
identity/acquisition qualification and room assignment remain future work.
All UI text and help support English and Dutch.

Device presence, bonding, received data and qualified room measurements remain
distinct. Reject malformed, unauthenticated and replayed data; expire old
measurements without refreshing them from unrelated packets. Keep secrets out of
logs and ordinary exports. Reuse the existing BLE owner and verify coexistence,
restart, radio loss and recovery on real hardware before declaring support.
