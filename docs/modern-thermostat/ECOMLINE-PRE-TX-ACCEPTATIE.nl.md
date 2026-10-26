# Ecomline Classic HRC 22H — acceptatie vóór fysieke TX

Bijgewerkt 26 oktober 2026. Onderdeel van WORKBOARD B09, geen tweede afvinklijst
of uitvoeringsopdracht. Status: **niet vrijgegeven**. Tado blijft de actieve
regelaar; E32 blijft RX-only. Ook een nulvraag valt buiten deze stap.

## Nieuwe opdracht en gebruikersgegevens — 25 oktober

De gebruiker vraagt nu eerst de actieve, handmatig bediende proefbèta af te maken
en daarna gezamenlijk op HA/E32 te installeren. Dit vervangt de eerdere keuze
om eerst alle overige roadmapfuncties in de bundel af te werken. Het is geen
opdracht om nu al ketel-/kraancommando's te sturen.

Gebruiker bevestigt: E32 en Tado zitten parallel op de Bosch-adapter; Tado kan
voor de proef worden losgenomen; de ketel kan ter plaatse onafhankelijk worden
uitgezet. Dit is een **handmatige, bediende stopmogelijkheid**, geen gemeten
automatische uitvalgarantie. De genoemde reset via het display is niet als
normale proefstop of automatische herstelactie opgenomen. Tado is nog niet
losgenomen en er is nog geen overdracht uitgevoerd. Meerdere radiatoren staan
volgens de gebruiker open; de bekende E32 V2/V2.2 met ethernet is bevestigd.
Dit bewijst nog geen gemeten minimumflow of naloop.

De bestaande native HA-specialist heeft een alleen-lezen preflight uitgevoerd
(25 oktober 22:21–22:22 UTC, 12 gestructureerde HA-MCP-lezingen): HA0.4.0b1 op
Core2026.10.4 geladen, E32-diagnose bereikbaar, Tado nog in `heat` met `idle`
terugmelding, fysieke/ketel/actuatoruitgangen uit. De supervisor meldt
`hydraulic_profile_unqualified`. Actuele E32-versie/bron waren niet uit die
lezingen af te leiden. Een aansluitende directe E32-lezing bevestigt beta.1,
bron5e3ed30, verse Classic-rapporten (aanvoer57°C, gemelde modulatie0%,
CV/tapwater niet actief), geen RX-fouten en nul verzonden frames.
Een gerichte HA-nacontrole om22:43UTC bevestigt dat de nieuwe
`boiler_fields_v1`-entiteiten wél meetwaarden tonen (54°C/0% gemelde modulatie,
`reported`, `classic_observed`). De onbeschikbaarheid betreft oudere EMS+-
contractentiteiten en herstelde oude entiteiten. Deze worden niet met andere
meetdefinities gevuld; de Classic-meetketen is hiermee niet als defect aangemerkt.
De HA-tijdstempels zijn geen onafhankelijke busmeting.
Geen service-, MQTT-, update-, herstart- of installatieactie uitgevoerd.

Open technisch werk blijft concreet: fysieke warmtepad-/adapter- en
zenderkwalificatie ontbreken nog. Het concrete softwareprofiel is aangesloten
in `EmsController.h` via `ClassicHeatTrialEnvelope`. Nulvraag-softwaretermijnen, het Classic-serviceadres
en installatieverklaringen per proef zijn inmiddels aangesloten. De proefcontroller is
nu verbonden met een eigen private UART-route. Zowel de algemene als de
handmatige bordtoelating in `Board.h` staat uit. Handmatige toelating activeert
geen legacy-zendroutes. De route koppelt GPIO5 slechts voor één proeftelegram;
alle herstelstappen naar ingang/geen pull worden ook na fouten geprobeerd. Een
mislukt herstel blokkeert verdere handmatige writes tot een nieuwe boot en
beoordeling; dit is geen gemeten garantie over de echte elektrische toestand. Een aparte begrensde Classic-echo-writer is nu gebouwd
(13µs-polls, maximaal160 per byte, gecontroleerde BREAK/rustherstel). De
writer vergelijkt nu ook elke werkelijk gelezen echobyte en weigert de resterende
bytes bij een afwijking. De UART-eigenaar trekt de verbruikte echo’s exact één
keer af van latere DATA-events; onverwachte extra bytes of onvolledige telling
bij BREAK veroorzaken resynchronisatie. Dit is geen bus-ACK, bevestigde
ketelreactie of fysieke kwalificatie van de installatie.

Daarnaast herkende de bestaande pollroute alleen de Junkers-polariteit. De E32
herkent nu de omgekeerde poll-MSB van een CRC-geldig ketel-broadcastbericht;
zonder zo’n bericht of na UART-reset blijft pollherkenning gesloten. Een poll-ACK
wordt niet als poll behandeld. Bron: [EMS-bus](https://emsesp.org/EMS-bus).
Dit verklaart mogelijk de nul pollteller van de huidige firmware, maar is nog
niet op de installatie nagemeten. De actuele bron gebruikt nu het expliciete Classic-serviceadres 0x0B;
de fysieke adres-/arbitragekwalificatie blijft afzonderlijk te beoordelen. Deze
bronfeiten worden niet door gebruikersbevestigingen over Tado/uitschakelen
opgelost. Een actieve release mag niet worden aangekondigd zolang dit ontbreekt.

## Vastgesteld en begrensd

De gebruiker heeft de Ecomline Classic HRC 22H en Bosch EasyControl Adapter
8737908035 V2.3 opgegeven. De fysieke printrevisie van de E32, UBA-revisie en
actuele bedrading zijn hiermee niet geïnspecteerd.

De [fabrikantpagina](https://www.nefit-bosch.nl/producten/thermostaten/slimme-thermostaten/easycontrol/easycontrol-adapter/)
noemt de EcomLine Classic HR(C)-familie als adaptertoepassing. De
[compatibiliteitsmatrix 6720882620, oktober 2024, pagina 1](https://www.nefit-bosch.nl/media/country_pool/products/thermostaten/6720882620.pdf)
plaatst EcomLine HR(C) onder iRT met adapter. Dat is familiedocumentatie voor
EasyControl; geen certificering van onze E32-software of individuele installatie.
De matrix gebruikt verkoopnummer 7736701654. De relatie met het opgegeven
onderdeelnummer 8737908035 is in deze review niet onafhankelijk vastgesteld.

De [adapterhandleiding 6720888197, juli 2019, pagina 33](https://www.bosch-homecomfort.com/pl/media/country_pool/dokumenty/wsparcie/apps/6720888197.pdf)
beschrijft onder meer iRT voor UBA 1.5 en waarschuwt dat protocolomzetting
functies kan beperken. Pagina 35, tabel 7 onderscheidt communicatieverlies met
ketel, communicatieverlies met temperatuurregelaar en voedingsverlies. De
beoordeelde tabel geeft geen maximale tijd tot CV-stop voor deze situaties.
Een storingsindicatie geldt daarom niet als bewezen warmte-intrekking.

De actuele [fabrikantmatrix](https://bbqkees-electronics.nl/wiki/gateway/hardware-details.html)
benoemt voor zowel E32 V2 (PCB2.0/2.1) als V2.2 EMS-circuitgeneratie Gen3a.
Dit vernauwt de bekende circuitfamilie, maar levert geen schema/BOM of gemeten
inactief TX-niveau van het aangesloten exemplaar op. De elektrische voorwaarden
hieronder zijn daarmee niet afgetekend.

## Adapterprotocol bij overdracht en herstel

De [Bosch-installatie-FAQ](https://www.bosch-homecomfort.com/be/nl/residentieel/service-ondersteuning/onze-apps/bosch-easycontrol/)
beschrijft automatische terugval naar aan/uit wanneer bij opstarten binnen een
minuut geen iRT/OpenTherm wordt gedetecteerd. Het
[Nefit Technisch Bulletin van juni 2019, pagina 8](https://nefit-nl-nl-b.boschhc-documents.com/download/pdf/file/6721805066)
bevestigt dat groen na ongeveer een minuut juist de verkeerde aan/uit-keuze kan
betekenen bij een iRT/OT-installatie. Dit zijn fabrikantbronnen voor het
adaptergedrag, geen meting van dit exemplaar of bewijs voor eerder pendelen.

Neem daarom bij B09 en de latere overdracht/herstelproef expliciet op welk
ketelzijdig protocol daadwerkelijk is vastgesteld en met welk bewijs. Alleen
EMS-ontvangst, de modelkeuze of een groene led volstaat niet voor deze acceptatie.
De bron vermeldt een inschakelvolgorde en herdetectieprocedure; voer die niet
automatisch vanuit firmware, HA, OTA of een statuspagina uit. Een noodzakelijke
herdetectie hoort bij de afzonderlijk begeleide inbedrijfstelling, gevolgd door
opnieuw een stabiele nulmeting en beoordeling van het gekozen protocol. Onbekend
protocol blijft een open installatievoorwaarde; geen extra HTTP-vinkje kan dit
bewijs vervangen. Er is nu geen adapterherstart of aansluitwijziging uitgevoerd.

## Resterende installatiegegevens

De volgende tabel legt het benodigde bewijs vast. Lege gegevens worden geen
instellingen, veilige standaardwaarden of goedgekeurd proefprofiel.

| Onderdeel | Huidige stand | Benodigd vóór passende fysieke proef |
| --- | --- | --- |
| Fysieke identiteit | Ketel/adapter door gebruiker opgegeven; E32-print-/UBA-revisie niet geïnspecteerd | Vastgelegde type-/revisiecontrole zonder openbare unieke serienummers |
| Elektrische TX-route | GPIO4/5 komen uit gepinde E32V2-boardprofielen; TX blijft input/geblokkeerd | Beoordeling van echte interface, rustniveau, polariteit, timing, echo/arbitrage en voeding door geschikte fysieke uitvoerder |
| Busadres en masker | Bron: serviceadres0x0B/ketel0x08/masker0; geen vrij-adresbewijs | Expliciet beoordeelde Classic-adressering en exclusief eigenaarschap; niets automatisch kiezen uit telemetrie |
| Afgifte en naloop | Geen gekwalificeerd installatieprofiel | Beoordeeld open afgiftepad, minimumflow, begrenzing en pomp-/naloopgedrag, ook bij kraan- of regelaarverlies |
| Onafhankelijke stop | Historische expliciete nul ondersteunt latere gemelde CV-stop; geen uitvalgarantie | Concrete stop-/herstelmogelijkheid die ook zonder werkende E32/MQTT beschikbaar blijft |
| Proefgrenzen | Nulvraagtermijnen en warmte-softwaregrenzen40–45°C/max60s aangesloten; fysieke kwalificatie ontbreekt | Vastgelegde passende temperatuur-/duur-/feedback-/stopgrenzen en verantwoordelijke toezichthouder |
| Overdracht | Tado actief; E32 passief | Vastgelegde overdracht naar één actieve eigenaar en herstel naar Tado zonder oude positieve vraag |

## Bewijskaart voor een later afzonderlijk toegelaten proef

Geen uitvoerend draaiboek: pas invullen nadat bovenstaande voorwaarden zijn
beoordeeld en de passende fysieke proef is toegelaten. Uitvalroutes afzonderlijk
beoordelen; niet aannemen dat één route de andere afdekt.

| Vast te leggen gegeven | Vereiste registratie |
| --- | --- |
| Identiteit en tijd | Ketel/adapter/E32-revisie, firmwarebron, operator, monotone meettijd en wandklok |
| Uitvalroute | Verlies van EMS-regelaar, adaptervoeding of iRT afzonderlijk; feitelijk beproefde route expliciet noemen |
| Laatste vraag | Werkelijk verzonden opdracht en voltooiingstijd; intentie en SDK-acceptatie apart houden |
| CV-stop | Onafhankelijke waarneming en strikt latere ketelrapporten; ontbrekende waarden niet als nul behandelen |
| Tapwater/naloop | CV versus DHW onderscheiden; toestand van afgiftepad/pomp tijdens en na intrekking |
| Termijn | Gemeten duur en toegestane grens met bron; geen termijn invullen uit een herhaalinterval of softwarelease |
| Herstel | Geen automatische hervatting/oude vraag; gecontroleerde terugkeer naar bestaande regeling |
| Uitkomst | Geslaagd, mislukt of onbekend; ruwe bewijslocatie en beoordelaar |

Tot dit bewijs bestaat blijven B09 en de actieve bèta open. Het normale
uitleespad blijft alle ontvangen ondersteunde velden verwerken; het ketelprofiel
beperkt geen decoder, stelt geen ontbrekende sensoren aanwezig en ontgrendelt
geen uitvoer. Softwarepakketcheckpoint `fbed431` is geen fysieke vrijgave.

### Busidentiteit vóór handmatige verzending

De broncontrole vergelijkt het beoordeelde zendadres met het lokale polladres en
het door ketelbroadcasts waargenomen masker. Bij onbekende of afwijkende identiteit
volgt geen toelating. Een CRC-geldig telegram van hetzelfde bronadres wordt vóór
queueing als conflict vastgezet. Dit kan ook een onvolledig verwerkte eigen echo
zijn: ook dan wordt niet verder gezonden op een onzekere ontvangstketen.
Een UART-reset wist het conflict niet. Afwezigheid van conflict is geen vrije-adres-
of eigenaarschapsbewijs. Het concrete Classic-serviceadres is nu in bron gekozen; er is geen fysieke proef
uitgevoerd. De diagnostiek staat onder `manual_bus_identity` in de EMS-status.

### Serviceadres en latere gateway-identiteit

De op 26 oktober gecontroleerde [officiële EMS-ESP-configuratiehandleiding](https://github.com/emsesp/docs/blob/main/docs/Configuring.md)
adviseert voor normaal gatewaygebruik `Gateway 2 (0x49)`. Zij benoemt `0x0B`
als serviceadres dat ook onderhoudsapparatuur kan gebruiken en dat tot versie
3.8.1 de standaard was. Dit maakt `0x0B` niet ongeldig, maar het mag niet als
gegarandeerd vrij gateway-adres worden beschouwd.

Onze voorbereide handmatige route gebruikt expliciet `0x0B` in encoder,
configuratieverzoek, antwoordmatching, pollcontrole en busafsluiting. Beoordeel
voor die tijdelijke proef ook mogelijke service-/onderhoudsapparatuur op dat
adres; de bestaande conflictbewaking blijft vereist en afwezigheid van frames
bewijst geen exclusiviteit. Een latere normale gateway-identiteit is een aparte
samenhangende bronwijziging met protocolregressie en passende installatiecontrole,
geen losse wijziging van één adres of automatische uitwijk naar `0x49`.
Dit brononderzoek wijzigt geen adres, zendtoelating of B09-aftekening. De
fabrikantdocumentatie over Gen3a levert nog geen gemeten TX-rustniveau van dit
exemplaar of gegarandeerde stoptermijn van de Bosch-adapter op.

### Voorbereiding per proef en nulvraagtermijnen

De productie-API vereist exacte booleans voor losgenomen andere regelaars en
onafhankelijke lokale stop, plus het beoordeelde afgiftepad voor een warmteproef.
Een geaccepteerde voorbereiding bindt die verklaringen alleen aan deze boot,
proefrevisie en bediener. Een nieuwe voorbereiding vereist opnieuw de velden.
Statuslezen bevestigt niets; een andere bediener kan de lopende proef wel stoppen.
Verklaringen vervangen geen bron-/adres-/zender-/warmteprofielkwalificatie.

Het aangesloten nulvraagprofiel heeft 15s feedbackactualiteit, een 5s operatorlease,
minimaal 1s tussen writes en 30s waarnemingsvenster per stopfase. Leaseverlies kan
eerst naar de afzonderlijke stopfase leiden; 30s is dus geen totale proefduur of
garantie dat de ketel fysiek stopt. Zonder verse latere CV-uit/modulatie0-rapporten
wordt geen geslaagde stop gemeld. Het profiel laat geen positieve vraag toe.
Alle zendtoelating blijft uit. Geen fysieke proef uitgevoerd.

De [primaire EMS-ESP-busbeschrijving](https://emsesp.org/EMS-bus) benoemt service-
adres0x0B en ketel0x08, het bronmasker0 voor niet-Junkers en een normale Classic-
0x18-broadcastcadans van 10s. De code gebruikt deze vaste protocolidentiteit;
15s actualiteit en 30s stopwaarneming zijn afzonderlijke softwarekeuzes. De pagina
bewijst geen vrije identiteit, eigen busmeting of werkende hardware. Afwijkend of
onbekend waargenomen masker en bronadresconflict blijven blokkeren.

### Proef met fout bewust afsluiten na gemelde stop

Een proeffout blijft actief en blokkeert wijzigingen zolang er geen voldoende
stopterugmelding is. `close_fault` kan alleen na daadwerkelijk verzonden nul,
strikt latere verse CV-uit/modulatie0/DHW-uit-rapporten plus een nul gevraagde
aanvoertemperatuur uit Classic0x18, gezonde toegelaten
zendidentiteit, exclusief eigenaarschap, onafhankelijke stop en zonder lopende
verzending. De ingelogde bediener bevestigt daarnaast ter plaatse de stop met
`local_stop_confirmed:true`, gebonden aan de actuele boot/revisie. Ook een andere
ingelogde bediener mag deze afsluiting doen; dit verleent geen zendbevoegdheid.

Afsluiten bewaart de foutreden en eerdere stopregistratie, retireert alle tickets,
maakt de proef inactief en vereist een herstart vóór iedere volgende proef.
De status `closed` is geen geslaagde fysieke kwalificatie. Alleen de blokkade door
deze proef vervalt, zodat het gewone geautoriseerde update-/herstartproces weer
mogelijk is; er wordt niets automatisch gestart. Een herhaalde identieke
bevestiging is idempotent en verleent geen nieuwe bevoegdheid. Zonder voldoende
stop blijft de blokkade en onafhankelijke lokale stop/controle noodzakelijk.

De gedeelde stopbasis controleert nu ook die nul gevraagde aanvoertemperatuur:
ontbrekend, onbetrouwbaar, vóór de nul ontvangen, verouderd of nog positief telt
niet. Daardoor kan een branderpauze met bijvoorbeeld nog 40°C vraag de stopbasis,
stopafronding of foutafsluiting niet vrijgeven. Testhelpers voor echte stop hebben
nu expliciet een nulselectie; negatieve regressies houden de positieve selectie.
De bewaarde HA-`selflowtemp` uit 16 oktober bleef ook bij positieve vraag nul;
die oude publicatie kwalificeert het huidige Classic0x18-veld niet als onafhankelijke
causale meting. De echte adapterreactie en betekenis blijven onderdeel van de
fysieke acceptatie; hieruit volgt geen vrijgave voor zelfstandig verwarmen.

### Warmte-envelope: bron en gekozen softwaregrenzen

De oorspronkelijke Nefit-installatie-instructie is als
[fabrikantdocument via een spiegel beschikbaar](https://www.smarthomesupply.nl/handleiding/nefit/instalecomlineclassic.pdf).
PDF-pagina22 noemt bijvullen beneden1,0bar, pagina24 de lokale cv-instelrange
40–90°C en pagina40 de maximale cv-werkdruk3bar. Pagina14 verlangt blijvende
watercirculatie. Dit document is geen gemeten kwalificatie van deze adapter of
installatie. Het oorspronkelijke oude Bosch-resourceadres was niet bereikbaar;
er wordt geen succesvolle lokale download van die oorspronkelijke host geclaimd.

**Correctie opstellingsgegevens, 26 oktober 2026:** de gebruiker bevestigt dat
zijn ketel geen digitale druksensor heeft. Onderstaande digitale drukeis beschrijft
de huidige softwareguard en is voor deze opstelling nog te herzien, geen vereiste
om een ontbrekende sensor alsnog uit te lezen. Passende afzonderlijke controle
van de installatiedruk moet in het modelgebonden proefprofiel worden vastgelegd.
Geen fictieve meetwaarde of automatische proefvrijgave; overige voorwaarden en
beide TX-blokkades blijven gelden.

Onze proefkeuzes zijn smaller: gevraagde40–45°C, maximaal60s, gerapporteerde
druk1,0–2,5bar en gemeten watertemperatuur5 tot onder50°C. Die keuzes zijn geen
fabrikantgarantie over fysieke temperaturen, stoptijd of minimumflow. De guard
vereist gerapporteerde Classic0x18-metingen jonger dan15s, plus gerapporteerde
Classic0x16-cv-instelling en lokale temperatuurgrens jonger dan10min. De hele
proefrange moet binnen de lokale grens passen: een grens onder45 of boven90°C
voldoet niet. Er worden geen ketelinstellingen verhoogd of cv-/tapwatermodi geschreven.

De echte afgifte-/sensorbetekenis moet nog beoordeeld worden; de bronpoort
manualHeatInstallationReviewed_ blijft false. Boilerfoto/keuze en operatorvinkjes
kunnen deze poort niet vullen. De guard wordt na selectie/encoding opnieuw
gelezen vóór verzending. Onbruikbare druk of te hoge temperatuur trekt positieve
intentie in zonder een benodigde nulvraag te blokkeren. De gemelde softwaregrens
is geen gegarandeerde fysieke maximumtemperatuur tussen rapporten.

## Het stopmeetrapport controleren

Download het bestaande meetrapport vanaf de keteltestpagina. Gebruik binnen
`telemetry.test` dezelfde boot/revisie en klok `boot_monotonic_ms`.
`stop_reference_emitted_at_ms` is de eerste afgeronde passende nulvraag in de
huidige bewijsfase, niet de laatste herhaling en geen bus-ACK. `null` betekent
dat er geen huidige referentie is; numeriek 0 is een geldige referentie.
Vergelijk met de oorspronkelijke `observed_at_ms` van de relevante
`telemetry.fields`, plus kwaliteit, herkomst, waarde en actualiteit.
Stopbevestiging vereist de bestaande combinatie CV-uit/modulatie0/DHW-uit/
nul gevraagde aanvoer en strikt latere passende rapporten. Een tijdstempel
alleen bewijst geen stop; een oude of ongeldige meting blijft onbruikbaar.
Bij warmtestart, nieuwe fout of teruglopende klok tijdens een actieve proef
wordt oude nulbewijsreferentie ingetrokken. Na terminale afronding blijft
de referentie historische informatie, geen nieuwe regeltoestemming. Vernieuw het rapport voor de nieuwe fase. Browser-captured UTC is
alleen de downloadtijd en mag niet worden vergeleken met de bootklok. De
elektrische/adapter- en werkelijke stopkwalificatie blijven afzonderlijk nodig.

## Laatste softwarecontrole vóór TX-koppeling

De private handmatige UART-route controleert nu naast lengte, bron/destination,
Classic-type0x1A, offset0 en toegelaten flowbyte ook de checksum vóór pinmapping.
De controle heeft geen logger-/parser-/heapafhankelijkheid. Kruiscontrole tegen
de bestaande tabeldecoder dekt 21.924 geldige bron/masker/flow-combinaties;
beschadigde checksums/payloads en de SDK-adapter worden afzonderlijk getoetst.
Dit voorkomt dat een fout encoderresultaat alsnog de pin bereikt, maar bewijst
geen juiste fysieke polariteit, collision-detectie, adapterreactie of ketelstop.
Bron-/adres-/profiel-/eigenaarschapscontrole en de vaste TX-lock blijven nodig.

## Frame-inhoud en proefintentie

De productie-encoder vereist na het vullen van het frame ook `matches`:
exacte lengte6, expliciete bron/masker en ketel, type0x1A/offset0, exact de
flowbyte uit de toegelaten intentie, geldige CRC en een geldig nul-/warmteticket.
Een andere temperatuur met correct herberekende CRC is geen toegelaten vraag.
Afwijzing gaat vóór de laatste zendtoelating; een echte polldriver-hostproef
bevestigt geen write, foutstatus en behoud van uitsluitend nulvraaguitvoer.
Dit is inhoudscontrole in bron; transport-/adres-/opstellings-/tijd- en
meetvoorwaarden blijven afzonderlijk gelden. De fysieke TX-lock is ongewijzigd.

## UART controleren vóór pinverwerving

Na frame-/CRC-controle volgt een alleen-lezen UART-voorcontrole: geen
openstaande echotellingen, succesvol gelezen lege ontvangstbuffer en een
niet-blokkerende TX-idle-controle. Bekend wachtende RX-data, onbekende bufferstatus
of nog lopende TX weigert de poging vóór inversie, pinmapping of pinherstel.
Een geweigerde/exceptionele voorcontrole verwerft geen pin en start geen cleanup.
Na verwerving blijven de oorspronkelijke controles en alle herstelpogingen gelden.
Data die later binnenkomt kan nog steeds de write tegenhouden; de verworven pin
wordt dan vrijgegeven. SDK-hosttests bewijzen deze volgorde, geen atomair vrije
bus, collision-detectie of gemeten elektrische toestand. Beide TX-locks blijven uit.

## Eenmalige configuratie-uitlezing vóór de warmteproef

De softwarekandidaat bevat `POST /boiler/test/read_configuration`. Dit is geen
algemene EMS-console: het enige frame is `0B 88 16 00 02 CRC`, een Classic
leesverzoek voor CV-aan/uit en ingestelde maximumtemperatuur. Het is afzonderlijk
gecontroleerd aan de UART-grens; de setpointwriter blijft uitsluitend `0x1A`.
Wire-formaat: [EMS-busreferentie](https://emsesp.org/EMS-bus).

De actie vereist auth/CSRF, huidige boot, oplopende eigen revisie en nieuwe
verklaringen over exclusieve bediening en onafhankelijke stopmogelijkheid.
TX-compiletoelating, adres/masker/conflict en transportgezondheid blijven vereist.
Een uitlezing schakelt algemene TX of de warmte-installatievrijgave niet in.
Een actieve ketelproef sluit deze uitlezing uit en omgekeerd; OTA, herstart en
configuratieschrijven blijven tijdens de actieve uitlezing geblokkeerd.

Maximaal 5 seconden pollwachttijd en 15 seconden antwoordtijd; geen herhaling.
Een nieuwe bewuste poging gebruikt een nieuwe revisie en heeft 30 seconden
voorbereidingsafstand. Een dubbele HTTP-aanvraag vernieuwt geen tijdslimiet.
Een antwoord moet werkelijk van `0x08` aan `0x0B`, type `0x16`, offset 0 met
beide bytes zijn, oorspronkelijk ontvangen ná de afgeronde verzending en vóór
de antwoorddeadline. Ongeldige/conflicterende veldwaarden worden geen succes.
De meetrapportage bewaart de bootklok en verzend-/ontvangstreferenties.

De waarneming op 26 oktober bevatte alleen temperatuur55°C via offset1/één byte;
CV-aan/uit ontbrak. Host-/browser-/SDK-tests bewijzen de afhandeling in software,
geen ketelantwoord of elektrische kwalificatie. Beide TX-flags blijven false.

## Afzonderlijke afsluiting van de handmatige buswisseling

De protocolreview vond nog een softwaregat: de handmatige route verwerkte geen
schrijfstatus en sloot een afgerond leesantwoord niet expliciet af. De gepinde
[EMS-ESP-core, `incoming_telegram`](https://github.com/emsesp/EMS-ESP32/blob/6e9ed5e516a5751b56534d2f0e71e22590442a0c/src/core/emsesp.cpp)
sluit na een schrijfstatus of passend leesantwoord de buswisseling af.
De implementatie hieronder is eigen code; er is geen algemene EMS-ESP-zender
of onbegrensde antwoordwachtrij overgenomen.

Een UART-lokale `ManualClassicTransaction` wordt uitsluitend voor een werkelijk
toegelaten vast proef-/leesframe gereserveerd en wacht pas na afgeronde emissie.
Een tweede opdracht kan een open wisseling niet overschrijven: de nieuwe
verzending wordt geweigerd en de proef krijgt via de bestaande route een fout.
Alleen een latere schrijfstatus `0x01`/`0x04` binnen de eigen context, of een
CRC-geldig volledig Classic0x16-antwoord van `0x08` aan `0x0B`, kan één
`0x0B`-afsluitbyte met echo/BREAK/pinvrijgave uitlokken. De toestand wordt vóór
IO ingetrokken, zodat herhaalde antwoorden en exceptions nooit nogmaals sluiten.
Een eenbyte-schrijfstatus heeft geen zelfstandig bronadres; de context is geen
onafhankelijke identiteit of fysieke ketelbevestiging.

De SDK-grens laat voor deze afzonderlijke bewerking uitsluitend die ene byte toe;
setpoint- en leesgrenzen blijven afzonderlijk. Geen idle-pong, algemene legacy-TX,
automatische herhaling of nieuwe warmtebevoegdheid. Een afgewezen schrijfstatus
wordt na de afsluitpoging als proeffout doorgegeven. Mislukte afsluiting of
verlopen antwoord wordt geen geslaagde wisseling. De laatste transport-/tijd-
controle blijft vóór de afsluitbyte staan.

Het venster van 200000 microseconden is een gekozen software-antwoordgrens,
geen bewezen responstijd van deze adapter of fysieke stoptermijn. Een passend
antwoord buiten dat venster veroorzaakt geen late afsluiting. De fysieke timing,
polariteit, interface en arbitrage moeten nog passend worden beoordeeld.
De oorspronkelijke ontvangsttijd wordt vóór afsluit-IO vastgelegd en gaat
ongewijzigd de decodewachtrij in. `manual_transaction` in het meetrapport telt
afgesloten wisselingen, afgewezen writes en antwoordfouten; geen van deze
counters vervangt de strikt latere CV-stoprapporten of fysieke waarneming.
Beide TX-flags blijven false. Geen werkelijke buswisseling uitgevoerd.

### Compileerbewijs voor de afzonderlijke handmatige variant

Op een tijdelijke, geïsoleerde checkout is dezelfde voorbereide bron gebouwd
met uitsluitend `emsManualTestTransmitAllowed=true`; algemene TX en
`manualHeatInstallationReviewed_` bleven false. De echte E32-toolchain levert
een image van 2.834.096 bytes. Onder de projectobjecten komt `uart_write_bytes`
uitsluitend voor in `src/EmsController.cpp.o`; `uart_send_break`, `uart_tx_chars`
en `uart_write_bytes_with_break` komen niet voor. De standaardcheckout blijft
ongewijzigd geblokkeerd en doorstaat de oorspronkelijke verifier zonder enige
project-UART-zendverwijzing. Deze afzonderlijke controle vervangt die verifier
niet. Bronhashes, symbolen en bouwlog zijn lokaal bewaard; de tijdelijke
checkout en niet voor installatie bestemde proefimage zijn verwijderd.

Dit bewijst dat de actieve C++-/SDK-vertakkingen compileren en waar de genoemde
zendverwijzing staat. Het bewijst geen aangesloten hardware, juiste elektrische
rust/polariteit of busarbitrage. De oorspronkelijke installatievoorwaarden en
fysieke acceptatie blijven open; er is niets geflasht of verstuurd.
