# M2 — oorspronkelijke kraanaanvraag en firmwarekanaal

25 oktober 2026. Werk voor de volgende grotere release. Geïnstalleerd blijft
HA44/E32alpha28. De productfabriek is niet geselecteerd; geen fysieke opdracht,
nieuwe publicatie of E32-update door deze bronstap.

## Wat de software verbindt

`ActuatorChannel` beheert per binding de volledige aanvraag → grant → opdracht.
Het eigen aanvraagvolgnummer, de oorspronkelijke lokale monotone begintijd en
het kleinste waargenomen deadlineplafond blijven bij dezelfde eigenaar.
`ActuatorDispatch` en de encoder blijven de bestaande opdrachtgrenzen bewaken.

De HA-worker antwoordt met `request_sequence`. Het kanaal accepteert alleen een
antwoord op zijn eigen nog openstaande aanvraag, met exact dezelfde sessie,
configuratie en binding. Een vertraagd antwoord kan geen nieuw aanvraagvenster
lenen. Een bekende retained aflevering wordt geweigerd. De losse encoder blijft
oude dertienveldgrants ondersteunen; het volledige nieuwe kanaal vereist de
correlatie. Deze nieuwe kanaalroute vereist dus de bijbehorende nieuwe HA-wirecode.

Een nog ongebruikt HA-grant blijft aan de oorspronkelijke aanvraag gebonden.
HA mag hetzelfde grant niet onder een hoger aanvraagvolgnummer opnieuw labelen.
Na verbruik of verlopen van dat grant kan een expliciete nieuwe aanvraag een
nieuw grant krijgen. Een duplicaat vernieuwt geen deadline of opdracht.

## Bestaande transportverbinding

`ModernTransport` krijgt een optionele interne lokale bronfabriek. De normale
productconstructors leveren die niet. Zonder fabriek wordt geen extra granttopic
geabonneerd en ontstaat geen kanaal of kraanverkeer. Er is geen nieuwe MQTT-client,
worker, timer, commandowachtrij, opslag of remote instelling toegevoegd.

Een geselecteerde fabriek moet zelf gekwalificeerde lokale feiten leveren.
De transportlaag beperkt die met de actuele controllercontext vóór én na het
lezen van de feiten, verbinding, vertrouwde klok en oorspronkelijke leasedeadlines.
Een geldige shadow-sessie levert geen fysieke bevoegdheid. Er zijn maximaal acht
kanaaleigenaren; dit kwalificeert geen installatie met acht kamers.

De aanvraag en opdracht gebruiken dezelfde synchrone publishfunctie, zonder
retained publish of automatische herhaling. De bestaande loop leest grants en
controleert de kanaalcontext. `ActuatorChannels` bewaakt de inventaris tijdens
fabrieks- en broncallbacks: herintrede trekt de eigenaar in voordat een binding
kan worden toegevoegd of een lopende iteratie gewijzigd. De actuele lokale
netwerkstatus geldt ook als TCP nog verbonden lijkt. De interne kanaalaanroeper moet dezelfde bestaande
geserialiseerde taak gebruiken; de API is geen mutex of REST-bediening.

PubSubClient geeft via zijn publieke callback geen retainmetadata door. Daarom
rust replaybeperking op de oorspronkelijke lokaal openstaande aanvraag,
aanvraagvolgnummer, exacte nieuwe sessiescope en lokale deadline, naast de
HA-deadline. De expliciete retained-parameter van het losse kanaal bewijst niet
dat de transportcallback retainmetadata kan zien. Dit blijft een afzonderlijk
review- en kwalificatiepunt vóór selectie van een productfabriek.

### Absolute deadline op de echte socketgrens

De gepinde WiFiClient kan bij een gewone write op socketruimte wachten en opnieuw
proberen. Alleen een controle vóór `publish()` voldoet daarom niet aan de
voorbereide actuator-deadline. `DeadlineWiFiClient` gebruikt tijdens precies die
ene expliciete actuatorpublish één nonblocking `send(MSG_DONTWAIT)` per write.
PubSubClient blijft zelf het MQTT-pakket maken op dezelfde verbinding.

De writecontrole gebruikt het gedeelde klokwatermerk en de oorspronkelijke
absolute deadline vóór en na iedere handoff. Ook contextlezingen krijgen hun tijd
uit datzelfde watermerk; een klokterugloop tussen verschillende kanalen kan niet
via een nieuwe laag verdwijnen. Een contextcallback die intrekt, kan daarna geen
nieuwe eigenaar meer laten invoegen.

Gedeeltelijke, mislukte, late of onzekere IO wordt niet herhaald. De bestaande
socket wordt na zo'n mislukte publish gesloten zonder nog een MQTT-pakket te
schrijven, zodat achtergebleven gedeeltelijke bytes niet worden aangevuld met
een volgende opdracht. Gewoon shadowverkeer houdt het bestaande SDK-writepad.
Dit is softwarematige overdracht, geen bewijs van netwerklatency of fysieke ACK.
De productfabriek blijft gesloten en de fysieke acceptatie blijft vereist.

Vier eindige adapterproeven gebruiken een echt lokaal nonblocking socketpaar,
met een expliciete fixture van alleen de openbare WiFiClient-API. Ze toetsen
normale delegatie, overdracht op dezelfde socket, verlopen budget, volle socket
zonder retry en onzekerheid na al geschreven bytes. De echte ESP-SDK-build wordt
apart gecontroleerd; de hostfixture wordt niet als volledige SDK voorgesteld.

Bij disconnect, SOURCE-vervanging of inhibit worden eigenaren blijvend ingetrokken.
Reconnect maakt geen automatische nieuwe eigenaar. Ongeldige tijd, scopeverlies,
re-entrantie en een onzekere IO-uitkomst blijven gesloten. Alleen historische
transportacceptatie of HA-serviceacceptatie wordt gerapporteerd; geen kraanecho,
klepstand, afgiftepad of fysieke stopgarantie wordt daaruit afgeleid.

## Verificatie en gevonden grensgevallen

De onafhankelijke eerste bronreview vond LBCH25-001/002: het buitenste kanaal en
de ingesloten dispatcher moesten hetzelfde onomkeerbare deadlineplafond en
klokwatermerk gebruiken. Extra tests reproduceren de verschillen tussen beide
lagen, waaronder een te late terugkeer na een op tijd begonnen handoff.

Het kleinste kanaalplafond begrenst nu ook de feiten van de dispatcher, iedere
kloklezing loopt door het kanaalwatermerk en na delegated dispatch volgt opnieuw
een controle. Verlopen vóór IO weigert verzending; na mogelijke IO is de uitkomst
onzeker en de eigenaar ingetrokken. Ook een verkorte lease tijdens aanvraagcodering
is afzonderlijk gereproduceerd en hersteld.

De echte C++-pipefixture produceert eerst zijn aanvraag, ontvangt een door de
bestaande native HA-wire uitgegeven grant en produceert dan de opdracht voor de
bewaakte HA-serviceadapter. Foutpaden dekken verlopen, offline, retained en een
verkeerd aanvraagvolgnummer. De fixture gebruikt synthetisch gekwalificeerde
lokale feiten; geen broker of apparaat. Einduitslagen en tweede onafhankelijke
review worden vóór de releasefreeze aan het werkbord toegevoegd.

Bewijs: `out/large-beta-channel-20261025/`. De eerste falende regressies en reviews
blijven behouden. De oorspronkelijke actieve M2-/fysieke acceptatie en het
E32-uploaderherstel blijven open.

**English:** The prepared firmware channel owns the original request sequence,
time and narrowing budget. HA replies echo that sequence and cannot relabel an
unconsumed grant. Optional wiring uses the existing MQTT connection and loop;
normal product constructors supply no qualified source factory. Replay metadata
limits, physical feedback/stop qualification and E32 recovery remain open.

## Afzonderlijke HA-testfasecorrectie

Een volledige kandidaat-run stopte op de bestaande proef “ACK zonder snapshot”.
Die proef kon haar 150ms-timeout al vóór de bedoelde ACK-fase bereiken. Een
gerichte vertraging van 200ms in de voorbereiding reproduceert precies die
verkeerde fase. De aangepaste proef wacht op de werkelijk door C++ geproduceerde
en door de HA-worker behandelde ACK, laat snapshots weg en laat daarna de echte
asyncio-timeout verlopen. De productie-timeout van 90 seconden verandert niet.

Deze correctie verklaart die kandidaat-testuitkomst; ze verklaart niet met
terugwerkende kracht de oudere incidentele CI-kamerassertie. Die oude oorzaak
blijft als afzonderlijke P0-grens open.
