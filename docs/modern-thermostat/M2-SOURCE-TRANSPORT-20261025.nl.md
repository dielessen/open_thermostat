# M2 — actuele bron-, lease- en transportcontrole

25 oktober 2026. Voorbereiding voor de grotere bèta, geen bèta-publicatie of
productie-installatie. HA43/E32alpha28 blijft de laatst geverifieerde basis.

## Samenhangende verzendcontrole

`ActuatorDispatch` verbindt de bestaande `ActuatorIntent`-encoder met een lokale
SOURCE-snapshot, een eigen monotone klok en een bestaande synchrone
transportfunctie. Standaard ontbreken die producenten en blijft de eigenaar dicht.
Dit is een voorbereide component; de normale firmwarefabriek selecteert hem niet.
Geen nieuwe MQTT-client, topic, subscriber, worker, timer, opslag of commandowachtrij.

De lokale snapshot bevat de exacte controller/boot/epoch/adapter/sessie/config/
binding-identiteit, leasedeadline en actuele bevoegdheid. Een brokerbericht kan
deze niet vervangen. De toekomstige bronfabriek moet de echte native lease,
profielkwalificatie en exclusieve eigenaar zelf bewijzen. Een `true` in een proef
is geen productiepin, GUI-optie of fysieke toestemming.

- De onafhankelijke klok wordt vóór en na de lokale broncallback gelezen. Tijd
  in die callback telt dus mee; de oude momentopname kan geen verlopen lease dekken.
- Na het coderen volgt opnieuw bron-/klokcontrole, vóór de bestaande transportfunctie.
  De functie krijgt de absolute lokale deadline en moet die bij de daadwerkelijke
  synchrone overdracht bewaken. Ze mag bytes niet als opdracht opslaan, wachtrijen
  maken of later opnieuw verzenden.
- Ook na terugkeer van de transportfunctie worden bron, klok en deadline opnieuw
  gecontroleerd. `transport_accepted` betekent alleen historische transportacceptatie,
  geen HA-serviceacceptatie, oorspronkelijke kraanecho of open afgiftepad.
- Bron-/scopeverlies, klokterugloop, waargenomen leaseverlies, re-entrante uitvoering
  of encodeergeheugenfout trekt deze eigenaar blijvend in. Herstel van een callback of een
  latere lease kan hem niet opnieuw activeren.
- Een false/exception van transport kan volgen op gedeeltelijke IO en blijft daarom
  `outcome_unknown`. Ook te late terugkeer of bronverlies na overdracht blijft unknown,
  met intrekking en zonder automatische retry. Er wordt niet aangenomen dat een mislukte overdracht niets heeft verzonden.

De callbacks zijn begrensde lokale lezingen binnen dezelfde bestaande geserialiseerde
firmwaretaak. De re-entrantiecontrole is geen mutex voor willekeurige andere taken.
Het oorspronkelijke lokale aanvraagmoment blijft van de aanroeper; een binnenkomend
bericht mag geen nieuw aanvraag-/leasebudget aanleveren.

## Sessies uit de bestaande controller halen

De bestaande `ShadowController` kan nu een lokale `ActuatorSessionContext`
leveren voor een werkelijk geconfigureerd, genormaliseerd kraankanaal. Scope en
configuratiedigest komen uit de eigen actuele controller; lease- en grantdeadline
komen rechtstreeks uit `SessionAdmission`. De encoder en controller gebruiken
één gedeelde `ActuatorScope`, met ongewijzigde veld-/identiteitsvalidatie.

Vóór handshake/mapping/heartbeat, bij een onbekende binding, disconnect, ongeldige
klok of verlopen grant is er geen context. Uitlezen publiceert niets, schrijft
geen configuratie en verlengt geen deadline. Een context blijft expliciet
niet-authoriserend: `authorizesActuation()` geeft altijd false. Een geldige
verbinding is geen geschikt meetprofiel of fysieke installatiekwalificatie.

Zeven nieuwe native gevallen controleren de oorspronkelijke deadlines en de echte
controllerhandshake. De voorbereide dispatcher leest daarin de werkelijke
controllercontext; disconnect en een nieuwe sessie stoppen de oude eigenaar vóór
iedere transportoverdracht. De enkele positieve profielvlag in die proef is
uitsluitend een synthetische testinvoer; de productfabriek krijgt die niet.

## Vijf reproduceerbare grensfouten gesloten

De oorspronkelijke afzender behield zijn eerste deadline, maar onthield een later
waargenomen **kortere** lease niet consequent. Als een volgende snapshot weer een
langere lease gaf, konden toelating, codering of de nacontrole na transport daardoor
te ruim worden. Het deadlineplafond wordt nu op iedere relevante grens uitsluitend
kleiner, nooit groter. Een nieuwe grant is afzonderlijk en wist het commandowatermerk
niet. Een verkeerde nonce kan geen bestaand grant wijzigen.

Verder bleef bij een interne encoder-geheugenfout de buitenste eigenaar ten onrechte
als niet-ingetrokken zichtbaar. De operationele opruiming neemt de blijvende
encoderintrekking nu over. Er wordt geen opdracht verzonden of opnieuw geprobeerd.

Vóór herstel falen exact vijf van 32 gerichte gevallen; na herstel slagen alle 32.
De oorspronkelijke falende XML/log blijft in `out/large-beta-20261025/` bewaard.
De vijf gevallen omvatten één regressie in de eerder voorbereide encoder en vier
in de nieuwe controlelaag. Dit waren geen fouten in een actief aangestuurde ketel;
de productie heeft deze componenten niet geselecteerd.

## Verificatie

728 native firmwaretests geslaagd; de 32 actuatorgrensgevallen ook onder
AddressSanitizer/UBSan met lekcontrole. Strikte C++17-build met
`-Wall -Wextra -Werror` slaagt. De bestaande architectuurcontrole blijft ongewijzigd.

Een werkelijk door native HA afgegeven grant gaat door de echte C++-encoder én
nieuwe verzendcontrole; de bytes gaan naar dezelfde bewaakte HA-ontvanger en
Profile-C-serviceadapter. Tien extra native HA/C++-gevallen toetsen één overdracht,
bron-/leaseverlies, klokterugloop, vertraging en onzekere transportuitkomsten.
De eindige transportproef gebruikt alleen stdin/stdout en synthetische lokale feiten;
geen brokerroute naar productie en geen kraan-/ketelopdracht.

De CI bouwt beide vereiste C++-runners en voert de actuatorgrensgevallen ook onder
sanitizers uit. Volledige HA-regressies: 2.297 gevallen per Core 2026.10.2/2026.10.3
(2.229 tests en 68 subtests), nul fouten/errors/skips. De tijdelijke eigen
localhost-MQTT-fixture is gestopt en verwijderd. De onafhankelijke review en
exacte bron-CI worden afzonderlijk afgerond; geen nog lopende controle als
voltooid presenteren.

## De sanitizerpoort daadwerkelijk laten falen

De onafhankelijke review vond LB25-001: UBSan kon een fout melden en toch met
exitcode nul eindigen. De native CI-stap gebruikt nu `UBSAN_OPTIONS=halt_on_error=1`
en behoudt `ASAN_OPTIONS=detect_leaks=1`, ook voor bestaande upload- en
onboardingproeven. Een opzettelijke lokale signed-overflowproef geeft vóór de
wijziging dezelfde foutmelding met exit 0 en erna met exit 1. Dat proefprogramma
staat alleen bij het lokale bewijs en wordt niet in de firmware opgenomen.

De echte 32 actuatorproeven slagen ook met deze strikte opties, exit 0 en zonder
sanitizerdiagnostiek. Daarnaast slagen de bestaande 11 uploadgrens- en 36
onboardingscenario's met dezelfde opties. Dit is een aanscherping van de
controlepoort, geen geconstateerde undefined-behaviourfout in de productfirmware.

## Wat ontbreekt voor de grote bèta?

De normale SOURCE-/profielselectie en grant-/transportroute zijn nog niet op deze
component aangesloten. De bestaande actieve fabriek krijgt geen nieuwe fysieke
bevoegdheid. De exact geïnstalleerde TV02-converterbron blijft via bestaande toegang
onbereikbaar; eerdere bronreview heeft dit begrensd vastgesteld. Geen nieuwe toegang
of ongecontroleerde zendtransactiekoppeling toegevoegd.

Geschikte oorspronkelijke ruimtemetingen, causale Tuya-zendtransactie/echo,
schema-eigenaarschap en fysieke kraan/flow/ketel-/stopkwalificatie blijven open.
Deze controle weigert nieuwe opdrachten bij uitval; zij sluit niet op eigen kracht
een eerder fysiek ingestelde kraan. Er is geen automatische stopopdracht of bewezen
fysieke failsafe toegevoegd. De bestaande E32-watchdog-/herstelblokkade en het
onverklaarde pendelen zijn niet gerepareerd of opnieuw beproefd.
