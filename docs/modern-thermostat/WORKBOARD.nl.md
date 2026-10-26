# OpenThermostat — actueel werkbord en releasechecklist

Actuele uitvoeringsvolgorde en bundeloverzicht: [volgende gezamenlijke bèta](NEXT-RELEASE.nl.md).
Alle oudere voortgangsnotities blijven bewaard in de [planhistorie](NEXT-RELEASE-HISTORY-20261026.nl.md).

**Afzonderlijk versievoorstel:** [concept-PR #2](https://github.com/dielessen/open_thermostat/pull/2)
bevat nu een echte beta.4-kandidaat met bijbehorende Engelse releasenotities.
Het pakket is onafhankelijk gecontroleerd; de actuele bewijsstand en de nog
open publicatievoorwaarden staan in [het kandidaatrapport](BETA4-VERSIONED-PREVIEW.json).
De ontwikkelbranch blijft beta.3; er is nog geen tag, publicatie of installatie.

Actueel ontwikkelwerk: beta.4 krijgt een uitvoerbare, bijgewoonde Ecomline Classic-
commissioningproef met een nieuwe manometerwaarde per warmtevoorbereiding en een
scrollbare Bluetoothlijst met maximaal 128 ontdekte adressen. Algemene TX en
blijvende instellingenwrites blijven uit; fysieke kwalificatie is niet afgetekend.
De [actuele details en lokale bewijsstand](NEXT-RELEASE.nl.md#actuele-uitbreiding-uitvoerbare-proef-en-bluetoothscrollvak)
gaan vóór oudere voorbereidingsnotities hieronder.

Nieuwste ontwikkelbron `27bb535`: alle negen CI-validatiejobs en 2.240
onafhankelijke pakketcontroles geslaagd. Publicatiejobs zijn overgeslagen. De Engelse pakket-
README sluit aan op de bediende proefroute. Grote tijdelijke downloads zijn
verwijderd; bewijs blijft onder `out/beta4-package-27bb535/`.

Het eerdere checkpoint `c058dd2` slaagde voor alle negen CI-validatiejobs en
2.236 pakketcontroles. De toegelaten beta.3-nacontrole is nu uitgevoerd maar
**INCOMPLETE**: HA wel gelezen, geen E32-leeskanaal of originele installreceipts.
Beta.4 blijft niet-bevroren en ongepubliceerd; de acceptatiepoort blijft staan.
[Geanonimiseerd nacontroleresultaat](BETA3-POSTCHECK-20261026.json).

Eerdere aanvullende integratiecontrole op schone bron `b0abca7`: HA Core
2026.10.2/.3/.4 ieder 2373 tests en 68 deeltests geslaagd; 11 C++-peers opnieuw
gebouwd. E32-firmware/bestandssysteem en standaard geen-TX/layoutcontrole slagen;
34 webbestanden byte-exact in de image van 2.828.096 bytes. Afzonderlijk HA-pakket
met 87 exact vergeleken bronbestanden en verse Core.4-acceptatie gecontroleerd.
Eigen MQTT-fixtures verwijderd; bestaande containers behouden. Dit is een lokale
integratiecontrole, geen definitieve freeze, publicatie of installatie.

Eerdere volledige gezamenlijke pakketpreflight op schone bron `0acae7c`: 2065 E32-
pakketcontroles, onafhankelijke SDK-/runtimecontrole van 629 eenheden en echte exacte/gewijzigde
herlinkproef geslaagd. HA Core 2026.10.2/.3/.4 ieder 2372 tests en 68 deeltests geslaagd; 11 C++-peers
opnieuw gebouwd. Afzonderlijk HA-pakket en byte-exacte 87 bronbestanden tussen beide
bundels gecontroleerd. Geen nieuwe versie/publicatie/installatiekandidaat:
de lokale proef behield bestaande versievelden. B11 blijft open voor de
uiteindelijke actieve bron-/versiefreeze; B09/B14 blijven fysiek open.

Actuele busafsluiting: een UART-lokale eindige wisseling sluit uitsluitend na
passend antwoord één keer met de vaste servicebyte. Schrijfafwijzing en
antwoord-/afsluitfout worden geen succes; algemene pongs blijven uit.
Oorspronkelijke ontvangsttijd wordt vóór deze IO vastgelegd. De afzonderlijke
handmatige variant compileert voor de E32; objectcontrole vindt byte-uitvoer
uitsluitend in het controllerobject, standaardvariant blijft zonder TX. Dit is nog geen
fysiek gekwalificeerde zendroute of stopbevestiging.

Actuele configuratie-uitlezing: een expliciete eenmalige Classic0x16-uitleesroute
is aangesloten in HTTP/UART en NL/EN-bediening, naast de afzonderlijke setpointwriter.
Alleen een echt later volledig boilerantwoord telt; geen echo, automatische
herhaling of warmtevraag. De UART-voorcontrole en vaste TX-blokkade blijven gelden.
1059 native en 190 strikte proef-/encodergevallen slagen; de latere SDK-adapterset
heeft 19 gevallen (`ecfee08`).
Kandidaatfreeze, fysieke TX-vrijgave en daadwerkelijke installatie blijven open.

**Proefbericht aan de toegelaten opdracht gebonden:** de productie-encoder
vergelijkt nu zijn uiteindelijke Classic-frame expliciet met de beoordeelde
adressering én de concrete sessie-intentie. Lengte, bron/masker, keteladres,
type0x1A, offset0, flowbyte en CRC moeten allemaal overeenkomen. Een checksum
alleen kan daardoor geen afwijkende vraag laten doorgaan. Nulvraag en warmte
blijven onderscheiden, inclusief vereiste boot/sessie/epoch en eindigheid.
De bestaande laatste tijd-/eigenaarschaps-/meetcontrole blijft ná encoding staan.

De nieuwe tests toetsen 1275 verschillende inhoudsmutaties met opnieuw geldige
CRC, verkeerde lengte/checksum en nul-/warmteverwisseling. De echte pollpolicy
weigert een 41°C-frame bij een toegelaten 40°C-intentie zonder verzending,
zet de proef op fout en kan daarna uitsluitend een toegelaten nulvraag leveren.
De encodergevallen zijn toegevoegd aan de strikte CI-sanitizersuite.
Beide fysieke TX-vrijgaven blijven false; dit kwalificeert geen elektrische
interface of echte adapter-/ketelreactie. Geen publicatie of installatie.

**Controles:** 1024 native tests, 155 strikte ASAN/UBSAN-gevallen, drie
firmwarebuilds en 146 scriptcontroles slagen. De beschermde standaard-TX-/
layoutverifier is ongewijzigd en slaagt; alle 34 webassets zijn byte-exact
aanwezig in het ontwikkelimage van 2.816.736 bytes. Geen web-/HA-codewijziging;
eerdere browser-/HA-preflight blijft apart vastgelegd. Eindfreeze en echte
OTA-/HA-/installatieacceptatie staan nog open.

**Handmatige UART-grens verder gekwalificeerd in bron:** vóór enige TX-koppeling
wordt nu ook de checksum van het volledige proeftelegram gecontroleerd. Een
bericht met foute checksum veroorzaakt geen pinmapping, zendactie of cleanup van een niet
verworven pin. De bestaande encoder blijft de checksum genereren; de laatste
SDK-grens controleert die zelfstandig met dezelfde EMS-rekenregel. De oude
geïsoleerde probe accepteerde een fout CRC en koppelde zijn fake-pin; de nieuwe
weigert dit zonder IO. Alle 255 verkeerde checksumbytes, payload-bitcorrupties
en 21.924 toegestane bron/masker/flow-combinaties zijn in hosttests getoetst aan
de bestaande telegramencoder. De SDK-adapter heeft een afzonderlijke regressie.
Geldige nul-/warmteframes, foutafhandeling en pinvrijgave blijven gecontroleerd.
Beide fysieke zendtoelatingen blijven false; dit is geen elektrische of fysieke
ketelkwalificatie en geen reeds geïnstalleerde wijziging.

**Controles:** 1020 native tests, 145 strikte ASAN/UBSAN-proefcontrollergevallen
en 11 afzonderlijke SDK-adaptergevallen slagen. Drie firmwarebuilds, 146 scripts,
de ongewijzigde standaard-TX-/layoutverifier en 34 byte-exacte webassets in
2.816.736 bytes slagen. Browser/HA-code is ongewijzigd; bestaand bewijs blijft
behouden en vervangt geen uiteindelijke freeze-/installatie-/praktijkcontrole.

**Brede HA-bronregressie afgerond op `66140f9`:** de volledige suites
`ha/tests` en `ha/tests_native` slagen op Core 2026.10.2, 2026.10.3 én
2026.10.4. Per versie: 2372 tests plus 68 deeltests (2440 JUnit-gevallen),
0 fouten, 0 errors en 0 skips. De bron bleef tijdens iedere run schoon en
ongewijzigd; alle drie rapporten vermelden dezelfde HA-bronhash. De echte
C++-interopprogramma’s zijn vooraf uit deze bron herbouwd. Iedere runtime had
een afzonderlijke, tijdelijke localhost-MQTT-fixture. Er zijn vijf bestaande
deprecatiemeldingen uit HA/backoff-afhankelijkheden per run, geen projectfouten.
Dit is een lokale bron-preflight, geen bevroren eindkandidaat, productie-installatie
of fysieke ketel-/kraanproef. Er was geen aanvullende codefix nodig.

**Volgende releasepoort:** concrete beoordeling/vrijgave van de handmatige
proefvariant en installatievoorwaarden, daarna één gezamenlijke versie-/bronfreeze
met volledige pakket-/OTA-/HA-back-up- en onafhankelijke installatiecontrole.
B11 blijft open voor die exacte eindkandidaat; B09/B14 worden niet afgevinkt op
basis van deze offline regressie. Beide fysieke TX-vrijgaven blijven uit.

**Meetrapport voor de stopproef uitgebreid:** het proefstatusobject vermeldt
`clock: boot_monotonic_ms` en `stop_reference_emitted_at_ms`. Dat laatste is
de eerste succesvol afgeronde, bij de huidige fase passende nulvraag; zonder
zo’n referentie staat er `null`. Tijdstip 0 is geldig. Herhaalde nulvragen
verschuiven deze referentie niet. Warmtestart, nieuwe fout of klokterugloop
retireert de oude referentie tijdens een actieve proef volgens dezelfde policy.
Na terminale afronding blijft de referentie historische informatie. Elk lokaal
JSON-meetveld bevat nu ook zijn oorspronkelijke `observed_at_ms`, zelfs als het
oud of ongeldig is; dat maakt het niet vers of bruikbaar. Het gedownloade
rapport bevat deze gegevens automatisch. De gehele status gebruikt één
snapshottijd. Geen nieuwe zend- of stoptoestemming; geen bus-ACK of fysiek bewijs.
De compacte firmware→HA-veldcontracten blijven ongewijzigd.

**Broncontroles:** 1017 native tests, 142 strikte ASAN/UBSAN-gevallen,
146 scriptcontroles en drie firmwarebuilds slagen. De beschermde
standaard-TX-/layoutcontrole blijft ongewijzigd en slaagt. Alle 34 webassets
staan byte-exact in het ontwikkelimage van 2.816.736 bytes. Geen publicatie,
installatie of fysieke proef uitgevoerd; de actieve bèta blijft NOT_READY.

**Bevestigingsvensters opnieuw gecontroleerd:** starten, nulvraagvoorbereiding
en foutafsluiting beoordelen na het bevestigingsvenster opnieuw zichtbaarheid,
paginaverbinding, dezelfde boot/proefrevisie, lokale toezichtgeneratie en de
actuele knoptoestemming. Een onderbreking tijdens bevestiging levert geen
nieuw HTTP-proefverzoek op. De nulvraagverklaringen worden pas daarna verstuurd;
Stop blijft een afzonderlijke actie. Dit wijzigt geen fysieke TX-vrijgave.

**Gericht bewijs:** de oude pagina verstuurt een startverzoek na verborgen
worden tijdens bevestiging; de nieuwe controle slaagt voor 72 browsergevallen
(NL/EN, desktop/mobiel, drie acties, normaal bevestigen/annuleren/verborgen/
korte onderbreking/pagehide/verwijderde pagina). Vier taalprofielen, drie
firmwarebuilds en 146 scriptcontroles slagen. Alle 34 webbestanden staan
byte-exact in het huidige ontwikkelimage van 2.816.640 bytes. Dit is geen
nieuwe geïnstalleerde of fysiek gekwalificeerde release.

**Browsertoezicht — bronfix gecontroleerd:** verlies van zichtbaarheid en paginaonderbreking
trekken de lokale proefbevoegdheid direct in, ook als de pagina vóór de
volgende timer terugkeert. Een antwoord op een eerder gestarte voorbereiding
herstelt na zo’n onderbreking geen leaseverlenging of startknop.
De serverlease blijft de begrenzing voor reeds verzonden verzoeken; een browser
kan eerder verzonden netwerkverkeer niet terughalen. Stop blijft afzonderlijk
beschikbaar; terugkeren naar de pagina voert geen proefcommando uit.

**Controles van deze UI-fix:** echte oude browsercode reproduceert onbedoelde
verlenging na een laat voorbereidingsantwoord. De nieuwe browsertest controleert
late warmte-/nulvraagvoorbereiding, korte zichtbaarheidsonderbreking en
`pagehide`, zonder automatisch proefcommando bij terugkeer. Drie firmwarebuilds,
146 scriptcontroles en vier taalprofielen slagen; 34 webassets zijn byte-exact
in het ontwikkelimage van 2.815.792 bytes. De eerdere 1012 native en 138
ASAN/UBSAN-tests blijven van toepassing op de ongewijzigde C++-bron.

**Warmteproefsoftware concreet aangesloten:** het Ecomline Classic-proefprofiel
bevat nu 40–45°C en maximaal 60s warmtevraag. De bedieningslease blijft 5s en
de bestaande nulvraag-/stoptermijnen blijven gelden. De software controleert
opnieuw vóór iedere zendtoelating: Classic-gemeten watertemperatuur 5 tot onder 50°C,
keteldruk 1,0–2,5 bar, ingeschakeld cv-bedrijf en een uitgelezen lokale cv-grens
van minimaal 45 en maximaal 90°C. Live metingen moeten jonger zijn dan 15s;
configuratieterugmelding jonger dan 10min. Ontbrekend, ongeldig, toekomstig of
verouderd bewijs geeft geen warmtevrijgave. De normale uitleesdekking verandert
niet en deze controle start geen actieve leesopdrachten.

**Softwarecontrole:** 1012 native tests, 138 strikte ASAN/UBSAN-tests en
146 scriptcontroles slagen. Drie firmwarevarianten bouwen; de standaard
RX-/TX-blokkade- en layoutcontrole slaagt ongewijzigd. NL/EN-bediening is
getest op drie schermbreedtes, plus vier taalprofielen. Alle 34 webbestanden
zitten byte-exact in het ontwikkelimage van 2.814.224 bytes. Dit is nog geen
bevroren releasepakket of bewijs van installatie/OTA op het apparaat.

**Installatiebeoordeling blijft apart:** `manualHeatInstallationReviewed_` staat
nog false en beide fysieke bordtoelatingen blijven false. Een gekozen ketelfoto,
gezonde cijfers of aangevinkte verklaring kan die bronpoort niet vervangen.
De NL/EN-interface toont nu de softwaregrenzen, meetreden en de afzonderlijke
installatiebeoordeling. Druk-/temperatuurverlies trekt alleen de positieve vraag
in; een toegelaten nulvraag blijft beschikbaar om te stoppen. De grenzen zijn
gekozen proefsoftware, geen zelfstandige hydraulische of fysieke goedkeuring.

**Herstel van een proeffout en updates:** een fout blijft geblokkeerd totdat
werkelijk een nulvraag is verzonden en strikt latere, verse Classic-rapporten
CV-uit, modulatie0, geen tapwaterbedrijf én een gevraagde aanvoertemperatuur
van nul melden. Daarna kan een ingelogde
bediener de proef expliciet afsluiten, met bevestiging dat de verwarming ter
plaatse is gestopt. De oorspronkelijke fout blijft zichtbaar en de proef gaat
naar terminale status `closed`; geen herhaling, nieuwe voorbereiding of warmtevraag
is mogelijk tot een herstart. De proef bezet daarna de update-/configuratieblokkade
niet meer. Afsluiten start zelf geen update of herstart.

De nieuwe POST-route `/boiler/test/close_fault` vereist de actuele boot/revisie,
CSRF-bescherming en exact `local_stop_confirmed:true`. Ontbrekende/stale stop,
actieve brander/tapwater, lopende verzending of ontbrekende zender-/eigendoms-/
stopvoorwaarden blokkeren deze actie. Een handmatig vinkje vervangt geen verse
ketelterugmelding. Een verloren antwoord wordt niet automatisch herhaald.

**Stopbasis aangescherpt:** ook voorbereiding van een warmteproef, normale
stopafronding en herstel na een fout vereisen nu een verse, strikt latere
Classic-terugmelding van nul gevraagde aanvoertemperatuur. Branderpauze bij een
blijvende positieve vraag geeft geen stopbewijs. De regressie accepteerde die
pauze in de oude policy; de nieuwe blijft wachten. Dit blijft gerapporteerd
protocolbewijs, geen onafhankelijke fysieke kwalificatie van de adapter.
Bronacceptatie: 1.000 native tests, 126 strikte ASAN/UBSAN-gevallen, drie
bordbuilds en 146 scriptcontroles slagen. NL/EN-bediening slaagt op drie
schermformaten, inclusief verloren afsluitantwoord en geen hervatting na
heropenen; vier taalprofielen slagen. Alle 34 webassets staan bytegelijk in de
2.807.536-byte ontwikkelimage. De bestaande standaard-TX-lock-/layoutcontrole
is ongewijzigd en slaagt. Dit is geen nieuwe installatie of fysieke proef.

**Opstelling per proef bevestigen:** de productie-API en NL/EN-bediening vereisen
bij iedere voorbereiding expliciet dat de andere regelaar uit het regelpad is en
dat de bediener aanwezig is met een onafhankelijke stopmogelijkheid. Voor een
warmteproef is ook bevestiging van het beoordeelde afgiftepad vereist. De
bevestigingen worden alleen aan de geaccepteerde proef, boot en ingelogde bediener
gekoppeld; ze worden niet opgeslagen. In de interface worden ze na een poging,
nieuwe proefidentiteit of ontbrekende status gewist. Start/stop/keepalive kunnen
geen installatiebevestigingen toevoegen. Het zijn verklaringen van de bediener,
geen automatische sensormeting of fysieke kwalificatie.

**Concrete nulvraagpolicy aangesloten:** feedback mag maximaal 15 seconden oud
zijn, de bedieningslease duurt 5 seconden, writes liggen minimaal 1 seconde uit
elkaar en de software wacht per stopfase maximaal 30 seconden op een latere
stopterugmelding. Dit zijn softwaretermijnen voor afbreken/foutmelding, geen
bewezen fysieke stoptijd. De afzonderlijke nulvraagpolicy bevat geen positieve temperatuur of
tijdsduur. Ook met de volledige software-envelope blijft prepare_zero uitsluitend nul maken. De fysieke zenderkwalificatie en
beide bordtoelatingen blijven geblokkeerd; fysieke warmtepad-/zenderkwalificatie en proef blijven
open. Ook nulvraagvoorbereiding is nu geblokkeerd tijdens lopende, klaargezette of
nog te bevestigen updates; een stopverzoek blijft beschikbaar.

**Classic-serviceadres vastgelegd:** de E32-bron gebruikt nu bron0x0B,
ketel0x08 en bronmasker0; de bestaande andere bordtypes behouden hun adres0x19.
[EMS-ESP beschrijft](https://emsesp.org/EMS-bus) dit serviceadres en de normale
10s-cadans van Classic0x18. Het 15s-actualiteitsvenster houdt daar rekening mee.
Deze protocolkeuze bewijst geen vrij adres of werkende elektrische zender:
waargenomen masker, adresconflict, transportherstel en alle fysieke toelatingen
blijven vóór iedere verzending gecontroleerd. Er is niets op de module gewijzigd.
Bronacceptatie: 988 native tests, 114 strikte ASAN/UBSAN-gevallen, drie
bordbuilds en 146 scriptcontroles slagen. De bedieningsproef slaagt op drie
schermformaten in NL/EN; vier algemene taalprofielen slagen. Alle 34 webassets
staan bytegelijk in de ontwikkelimage van 2.802.400 bytes. De bestaande
layout-/standaard-TX-lockcontrole is ongewijzigd en slaagt. Geen fysieke proef.

**Aanvullende adresblokkade voor de handmatige proef:** het beoordeelde zendadres
moet overeenkomen met het adres waarop de controller polls ontvangt en het
waargenomen bronmasker. Onbekend of afwijkend masker geeft geen zendtoestemming.
Een CRC-geldig ontvangen telegram met hetzelfde bronadres blokkeert de handmatige
route al in de UART-ontvanger, vóór uitgestelde verwerking. De conflictmelding
blijft tot herstart staan; een UART-reset wist deze niet. Statusdiagnose toont
`manual_bus_identity` met adres, conflict en overeenkomst. Geen waargenomen
conflict bewijst niet dat een adres vrij is en vervangt geen Tado-overdracht.
Het warmtepadprofiel is nog niet fysiek beoordeeld en alle fysieke zendtoelating blijft geblokkeerd.
Vier nieuwe adresgevallen slagen onder ASAN/UBSAN; de volledige native suite
heeft 979 geslaagde tests. Drie bordbuilds en de ongewijzigde layout-/TX-lockcheck
slagen. Alle 34 bestaande webassets staan bytegelijk in de ontwikkelimage
van 2.798.048 bytes. Dit is geen vastgezette release of fysieke proef.


## Actieve handmatige proefbèta heeft nu voorrang

Nieuwe expliciete opdracht: eerst een actieve proefbèta voor handmatige ketelproeven,
dan één gezamenlijke release/installatie op HA en E32. Overige comfort-, leer-
en BLE-proxyfuncties blijven in het totale plan, maar blokkeren deze scope niet.

**Bevestigd door gebruiker:** E32 parallel met Tado op Bosch-adapter; Tado kan
voor de proef los; ketel kan onafhankelijk ter plaatse worden uitgezet; meerdere
radiatoren staan open. E32 V2/V2.2 met ethernet opnieuw bevestigd.
Dit is een bediende proefopstelling in voorbereiding, geen uitgevoerde overdracht
of automatische fail-safe. Nog geen ketel-, kraan-, update- of installatieactie.

**Live preflight via bestaande HA-specialist:** integratie0.4.0b1/Core2026.10.4
geladen, E32-diagnose bereikbaar, Tado nog `heat`/`idle`; fysieke uitgangen uit.
Directe, alleen-lezen E32-controle bevestigt beta.1/bron5e3ed30, verse Classic-
ketelrapporten en nul verzonden frames. De gerichte HA-nacontrole bevestigt ook
werkende `boiler_fields_v1`-entiteiten (54°C/0% gemelde modulatie); alleen oudere
EMS+-contractentiteiten blijven onbeschikbaar. Dit is geen kapotte Classic-
meetketen. Het hydraulische profiel is nog niet fysiek gekwalificeerd. [Actuele pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md).

**Resterend programmeer-/integratiewerk:** echte zender-/adapter- en
installatiekwalificatie, beoordeelde bronvrijgave en frozen gezamenlijke kandidaat
met daadwerkelijke OTA-/HA-installatieacceptatie.
Handmatige UART-route, softwarematige warmte-/nulvraaggrenzen, telemetriecontrole,
installatieverklaringen en Classic-serviceadres zijn gekoppeld. Fysieke zender- en
installatievoorwaarden ontbreken nog; zowel algemene als handmatige TX-toelating blijft uit. Een nieuwe passieve bundel installeren voldoet niet aan de
opdracht voor een actieve proefbèta. Er is nog geen nieuwe release gepubliceerd.

De proefcontroller gebruikt nu een private UART-route met een eigen
`emsManualTestTransmitAllowed`-toelating; deze staat uit. De algemene
`emsTransmitAllowed`-toelating blijft eveneens uit. Handmatige toelating kan geen
legacy-pongs, reset-BREAKs, startup-/queue- of forwardingpaden vrijgeven.
GPIO5 wordt alleen voor één toegelaten proeftelegram gekoppeld en daarna weer
als ingang zonder pull ingesteld. Mislukt dat herstel, dan blokkeert een blijvende
fout verdere handmatige writes; een gewone UART-reset wist die fout niet.
Een herstart is daarbij geen fysieke vrijgave of bewezen herstel.
975 native tests, 101 kerngevallen en 10 SDK-adaptergevallen onder ASAN/UBSAN,
drie bordbuilds en 146 scriptcontroles slagen. De standaardbuild heeft nog geen
bereikbare UART-zendaanroep; alle 34 bestaande webassets zijn bytegelijk aanwezig
in de ontwikkelimage van2.797.568bytes. Dit is geen uitgevoerde fysieke proef.

**Deze bronstap afgerond:** exceptions in proefencoder, writer, klok of gates
worden ingesloten. Een lopende verzending wordt zonder bevestigde levering
afgesloten; positieve vraag hervat niet. Foutafhandeling roept een falende callback
niet opnieuw aan; opvolgende toegelaten polls leveren uitsluitend nul. Vier
regressies faalden eerst. Met de aparte Classic-echo-writer en de gecorrigeerde
pollpolariteit slagen nu 950 native tests en 30 gevallen onder ASAN/UBSAN.
E32 leert de pollpolariteit pas uit een CRC-geldig ketel-broadcastbericht; na
UART-reset is deze weer onbekend. Dit ontgrendelt geen zender. Drie boardbuilds,
146 scriptcontroles en de onafhankelijke layout-/TX-lockcontrole slagen. Alle
34 webassets zijn bytegelijk aanwezig in de ontwikkelimage van2.793.488bytes.

**Updatevoorwaarde aangescherpt:** de10seconden-timeout van de updatepagina
omvat nu ook het uitlezen van de JSON-status. Een antwoord dat na de headers
blijft hangen blokkeert de knoppen na timeout; een volgende geldige status
herstelt de bediening. Geen automatische herhaling van installatiecommando’s.
De nieuwe regressie faalt vóór de wijziging; 30 NL/EN-browserproeven slagen.
Dit is gesimuleerde HTTP, geen nieuwe fysieke OTA- of ketelproef.

**Afzonderlijke nulvraagproef aangesloten:** sessiepolicy, beveiligde POST-route
en NL/EN-webknop ondersteunen nu een proef die uitsluitend nulvragen kan maken.
Deze vraagt beoordeelde zender/timing, exclusief eigenaarschap, onafhankelijke
stopmogelijkheid en verse Classic-terugmelding, maar geen warmteprofiel of
warmte-afgiftegoedkeuring. De bestaande fysieke TX-lock blijft doorslaggevend.
Een strikt latere gemelde stop sluit de proef af; geen overgang naar verwarmen.
Een latere warmteproef vereist nieuwe voorbereiding en een nieuwe stopbasis.
959 native tests, 85 controles onder ASAN/UBSAN, drie boardbuilds en
146 scriptcontroles slagen. Bedienings- en ontvangstweergave slagen op drie
schermformaten, inclusief NL/EN-nulvraagproef en echte meetrapportdownload; vier
taalprofielen slagen. Dit is fixture-/ontwikkelbewijs, geen fysieke proef of vrijgave. Het concrete productieprofiel en de zenderkoppeling blijven open.

**Classic-echocontrole verder aangesloten:** de writer leest en vergelijkt nu
elke echo voordat de volgende byte wordt aangeboden. Een afwijkende, ontbrekende
of onleesbare echo stopt de resterende bytes vóór het aanbieden van de BREAK.
De UART-eigenaar verrekent reeds gelezen echo’s één keer met de DATA-events;
een ontbrekende telling of onverwachte extra bytes bij BREAK resynchroniseert
de ontvangst. Een nieuwe write wordt geweigerd zolang de BREAK van de vorige echo
niet is verwerkt. Dit bewijst geen bus-ACK of ketelreactie en ontgrendelt geen TX.
De oude helper accepteerde de afzonderlijk gereproduceerde verkeerde echobyte;
de nieuwe weigert deze. 968 native tests, 94 kerngevallen onder ASAN/UBSAN
en 5 afzonderlijke SDK-adaptergevallen slagen. De SDK-grenzen zijn expliciete
hostfakes; dit is geen uitgevoerde fysieke proef. Drie eindbuilds, 146 script-
controles en de onafhankelijke layout-/TX-lockcontrole slagen. Alle 34 bestaande
webassets zijn bytegelijk aanwezig in de ontwikkelimage van2.797.552bytes.

## Status richting eerste actieve ketelproef

**Geïnstalleerd:** de gezamenlijke passieve basis E32 beta.1 / HA 0.4.0b1,
bron5e3ed30. **Voorbereid:** de grotere bundel met profiel-/EMS-/Bluetooth-/
updateverbeteringen; nog niet uitgerold. **Niet vrijgegeven:** actieve ketelsturing.

De 14 brede bèta-eindcontroles hebben drie volledige aftekeningen (B01–B03).
De overige elf bevatten veel gebouwde onderdelen, maar blijven deels open;
dit aantal is geen percentage van programmeerwerk. Er zijn 31 eisen en
23 geïnventariseerde componenten. Niet alles op de totale roadmap is noodzakelijk
voor de eerste begrensde handmatige ketelproef.

1. **Handmatige proef:** beoordeeld Ecomline/EasyControl-installatieprofiel,
   echte TX-route/adres/arbitrage, grenzen voor duur/temperatuur en feedback,
   open afgifte/minimumflow/naloop, onafhankelijke stop en één actieve eigenaar
   (Tado óf E32). De huidige firmware blijft RX-only. Het softwareproefpad moet
   met deze concrete gegevens en de zender worden afgerond, niet met fictieve
   standaardwaarden.
2. **Gezamenlijke kandidaat:** versie/bron vastzetten; volledige firmware-/HA-/
   browser-/pakketcontroles op precies die kandidaat; één uitrol met back-up,
   bewezen GitHub-update en onafhankelijke nacontrole. Ontwikkelbuilds vervangen
   dit niet.
3. **Proefvolgorde:** eerst gecontroleerde nulvraag met verse stopterugmelding;
   daarna een kleine, eindige warmtevraag en expliciete stop, met toezicht en
   beoordeeld herstel. Dit is nog geen uitvoeringsvrijgave.
4. **Automatische kamerregeling daarna:** de oorspronkelijke verse kamermeting
   en normale firmware→HA→TV02-route verbinden/kwalificeren, causale doelecho,
   readiness en uitval aantonen. De kraanproef komt eerst zonder ketelvraag.

Zelfleren/persistentie, volledige overige EMS-families, schaal-/comfortfuncties en
BLE-proxy zijn afzonderlijk werk in de totale roadmap. Zij worden niet als
voltooid of als voorwaarde voor iedere handmatige ketelproef voorgesteld.

## BLE-proxy — nieuwe bereikuitbreiding, nog te bouwen

Behoud directe E32-ontvangst; voeg aanvullend twee routes toe:

- **Via HA:** standaard ESPHome BLE-proxy → Home Assistant Bluetooth → onze
  bron-/apparaatkoppeling. De laatste stap is nog niet aangesloten. Gebruik de
  gedeelde HA-Bluetoothstream, geen tweede eigen scanner.
- **Zonder HA:** een eigen lokale relay/brug → E32. Een standaard ESPHome-proxy
  spreekt niet automatisch met onze E32; dit vereist een afzonderlijk protocol,
  implementatie en praktijktest.

UI: één apparaat met herkenbare naam en zichtbare ontvangstbron/proxynaam en
signaalsterkte bij die ontvanger. Directe en proxymeldingen dedupliceren; geen
oud pakket als nieuwe kamermeting behandelen. Sleutels, oorspronkelijke
rapportidentiteit, bronuitval en omschakeling afzonderlijk toetsen. Proxyverlies
maakt een bron onbeschikbaar; het levert geen verzonnen verse waarde op.
Sensoradvertenties en actieve TRV-verbinding/bediening zijn aparte ondersteuning.
Dit is gepland, geen reeds geleverde zelfstandige proxy- of regelfunctie.

Bronnen: [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy/),
[HA Bluetooth](https://www.home-assistant.io/integrations/bluetooth/),
[HA integratie-API](https://contributors.home-assistant.io/core/integrations/bluetooth/).

## Updatecontrole: begrensd herstel na tijdelijke fouten

De eerste automatische controle blijft na vijf minuten, daarna iedere twaalf
uur na succes. Na een mislukte controle volgt een nieuwe poging na dertig
minuten, zonder een lus die continu netwerk-/TLS-verzoeken uitvoert. De laatste
geslaagde lijst en haar oorspronkelijke leeftijd blijven zichtbaar; een nieuwe
of mislukte poging maakt die lijst niet opnieuw vers. Cachegebruik vereist ook
een geslaagde `checked`-fase, zodat een eerdere installatiefout een nieuwe
handmatige controle niet binnen de cachetermijn blokkeert.

Dit herhaalt uitsluitend het ophalen van de lijst; geen automatische installatie,
herstart of rollback. Bestaande gereedheids-/actieve-proefblokkades blijven gelden.
Drie regressies faalden vóór herstel; 933 native tests slagen na herstel, inclusief
32 herhaalde fouten over millis-overloop. De gebruikersuitleg is in NL/EN bijgewerkt.
Bronvoorbereiding, nog niet geïnstalleerd; actieve bèta blijft NOT_READY.

## Bevestigd opslaan van Bluetoothinstellingen

De pagina vergelijkt opgeslagen adressen, namen, profielen, versleuteling en
sleutel-aanwezigheid met het concept voordat zij ‘opgeslagen’ meldt. De volgorde
van de lijst mag verschillen; inhoud en aantal moeten overeenkomen. Een
mislukte uitlezing, afwijkende inhoud of onzekere POST-uitkomst bewaart het
concept, wist ingetypte sleutels en blokkeert herhalen tot expliciet herladen.
Statuspolling bevestigt geen onbewezen schrijfresultaat. Een uitgestelde
request start niet na het verlaten van de pagina. Dit blijft bronvoorbereiding;
geen installatie, echte Bluetoothkoppeling of ketel-/kraanopdracht uitgevoerd.

## Bluetoothzoekroute afgerond in broncode

Een nieuwe toegelaten zoekopdracht ruimt uitsluitend de ontdekkingslijst op,
zodat 32 oude adressen geen blijvende blokkade vormen. Afgewezen zoekopdrachten
(pending/cooldown/uitgeschakeld) wissen de lijst niet. De lijst wordt gewist vóór
SDK-start, zodat het eerste nieuwe pakket niet verloren gaat door achteraf wissen.
Opgeslagen sensoren en hun ontvangst worden niet gereset. Oude kaarten verdwijnen
bij verversen zonder opgeslagen formulieren of concepten te vervangen.

Volledige namen blijven bewaard bij verkorte/lege advertenties; een nieuwe
volledige naam kan wel worden overgenomen. Profielwissels bij nieuwe versleutelde
apparaten houden bindkeyinvoer zichtbaar en wissen de eerder ingevoerde sleutel.
Geen fysieke koppeling, kraan-/ketelopdracht of installatie uitgevoerd.

## EMS-telegramcontrole — volgende gezamenlijke bèta

- Interne `READ_WITH_DATA`-opdrachten zonder ondersteunde encoder en het
  gereserveerde marker-type leveren geen bytes meer op.
- Opdracht en bestemmingsadres moeten overeenkomen. Een leesbit op een al
  ontvangen leesverzoek blijft behouden bij opnieuw encoderen; het wordt niet
  stilzwijgend als schrijfopdracht gebruikt.
- EMS+-leesverzoeken moeten exact de ondersteunde lengte hebben. Extra bytes
  worden ook met een geldige CRC geweigerd, in plaats van genegeerd.
- Vier nieuwe tests: drie negatieve regressies faalden vóór herstel; alle 926
  native tests en 18 ASAN/UBSAN-gevallen slagen na herstel. De geldige Classic-
  en Plus-berichten zijn inclusief maximale type-ID en offset bytegelijk
  gecontroleerd bij encoderen/decoderen.

Dit sluit een softwarecontrolepunt van B08/B10. Echte zend-/stopkwalificatie,
bron-/kraan-/installatieacceptatie en B11–B14 blijven open. Geen ketelopdrachten,
nieuwe publicatie of installatie uitgevoerd.

## Actuele geïnstalleerde basis — 25 oktober 2026, 20:39 UTC

E32 **v0.1.0-e32v2-beta.1** en HA **0.4.0b1** op Core **2026.10.4** zijn
gezamenlijk geïnstalleerd vanaf bron `5e3ed30653d93b09dd65b5305accd65d079c0c06`.
De HA-opstartfout is live hersteld. Installatie24/24 en onafhankelijke
nacontrole45/45 geslaagd; normale GitHub-updatepoort geaccepteerd.
Fysieke uitgangen blijven uit. De actieve ketelbèta blijft **NOT_READY**.
[Installatie, bewijs en grenzen](INSTALLATIE-BETA1-20261025.nl.md).

De hierna gedateerde oudere alpha36/dev48-waarnemingen zijn historische
bron-/installatiebewijzen. Ze beschrijven niet de huidige geïnstalleerde basis.
Nieuwe profiel-/EMS-wijzigingen na bron5e3ed30 zijn nog niet geïnstalleerd.

## Verder werken aan dezelfde actieve bèta

De gezamenlijke passieve testrelease was expliciet goedgekeurd. Verdere
softwareverbeteringen worden gebundeld; geen losse tusseninstallaties.
B04–B14 blijven de actuele grenzen voor de volgende kandidaat, ook waar
beta.1 haar eigen software-/publicatie-/updatecontroles al heeft gehaald.
[Volgorde](BETA1-UITVOERING.nl.md).

## In de grote bètabundel — meetketen, meldingen en maandexport

Geleverd in beta.1: CSV-export via de normale HA-actie ondersteunt maximaal
31 dagen, met een installatiekeuze en NL/EN-velduitleg. Ontbrekende Recorder-data
blijft ontbreken; de bestaande rij-/groottegrenzen en eigenaarscontrole blijven.
[Gebruik en grenzen](HISTORIE-EXPORT.nl.md).

Schermcallbacks kunnen een meetintrekking niet meer onderbreken en een tijdens
zo'n callback vervangen bronprofiel kan geen oude meting opnieuw verzenden.
Een ongeldige lokale meetklok meldt HA via Repairs, met NL/EN-hersteluitleg.
Ongeldige bestaande kamerwaarden blijven onbekend; foutieve doelen worden vóór
verzending geweigerd. Gerichte echte HA-regressies worden bij deze bronstand
vastgelegd. De volledige bèta- en praktijkacceptatie blijven afzonderlijk open.

## In de grote bètabundel — kamerstatus en bediening

De bestaande kamerroute verwerkt namen, programma's en kleplabels als geldige
JSON-strings. De browser geeft kamernamen als gegevens aan een klikhandler door;
een apostrof of quote breekt de temperatuurbediening niet. Onbekende vochtigheid,
batterij en gemiddelde temperatuur verschijnen niet als een verzonnen nul.

De legacy-regelaar gebruikt bij klokfalen geen oningevulde tijdvelden of
weekdagindex en trekt zijn vorige warmtevraag in. Een EN/NL-tekst verklaart de
pauze; de SDK-klokaanvraag gebruikt een time-out van 100 ms. Native tests compileren nu de
echte Room.cpp, RoomConfig.cpp en tijdelijke override. De SDK-klok is een
expliciete native testgrens. Dit bewijst geen nieuwe praktijkwerking en verklaart
geen eerder pendelen in de moderne E32-route. [Conceptreleasenotities](BETA1-RELEASE-NOTES.nl-en.md).

## GitHub-releasenotities — alle bestaande versies bijgewerkt

Alle 65 releases (64 gepubliceerd en één concept) hebben begrijpelijke Nederlandse
versie-uitleg en een Engelse samenvatting. Nieuwe functies, opgeloste fouten en
bekende beperkingen staan vóór de technische historie. Oorspronkelijke notities,
tags, publicatiestatus en downloadidentiteiten zijn behouden. GitHub vernieuwde
alleen de tijdelijke concept-URL. Alle API-antwoorden passen binnen 32 KiB;
onafhankelijke readback en een tweede planning zonder wijzigingen slagen.
Historische teksten zijn versiegebonden vastgelegd in USER-RELEASE-NOTES.json.

## Alpha37-voorbereiding — meenemen in de grote bèta, geen losse uitgave

Alpha36 is via de normale GitHub-route geïnstalleerd en onafhankelijk geaccepteerd.
De opvolgende kandidaat bundelt automatische12ucontrole, dashboardmelding,
vijfminutencache, wachten tijdens ketelproeven en de voorbereide Zigbee-
eigenaars-/publicatiefixes. HA48 blijft bytegelijk. De updatepoort staat op
de grote bèta als opvolger; publicatie/installatie/nacontrole moeten nog slagen. Alle fysieke
ketel-/kraan-/bronkwalificaties blijven afzonderlijk open.


**Bijgewerkt: 25 oktober 2026.** Dit is de enige actuele afvinklijst. Het
[masterplan](PLAN.nl.md) bewaart alle 31 eisen en oorspronkelijke acceptatievoorwaarden.
Oude uitvoeringsnotities zijn gearchiveerd; hun oude woorden “open” en “niet
geïnstalleerd” bepalen de huidige stand niet meer.

## 1. Waar staan we?

## Voor volgende bundel — betrouwbare oorspronkelijke Zigbee-ontvangst

P0 R03/B04 en R05/B05, alleen bronmatig voorbereid voor temperatuur en TV02:

- Mislukte luisteraarregistratie trekt de eigenaar in en ruimt gedeeltelijke
  registratie op. Falen registratie én cleanup, dan blijven beide fouten zichtbaar.
- Afsluiten wacht ook bij cleanupfouten op de lopende publicatie. Parallel starten
  kan pas een nieuwe eigenaar maken nadat de oude afsluiting en cleanup slagen.
- Het publicatieslot bestaat vóór de MQTT-SDK-aanroep. Direct geneste ontvangst
  start geen tweede publicatie; direct stoppen wacht op datzelfde SDK-resultaat.

Alle 40 producenttests slagen, inclusief de begrensde publicatie-afsluiting. Voor/na-bewijs staat onder
`out/receiver-lifecycle-20261025/`, `out/receiver-shutdown-20261025/` en
`out/receiver-publication-20261025/`. Geen wachtrij/retry, productie-installatie,
bronkwalificatie, kraan-ACK of ketelopdracht. Fysieke B04/B05-acceptatie blijft open.

## Voor volgende bundel — automatische updatecontrole en dashboardmelding

De E32 controleert vanaf vijf minuten na opstarten iedere twaalf uur de bestaande
compatibele releasecatalogus. Iedere poging, ook een fout, verschuift de volgende
automatische poging; geen snelle retrylus. Geen controle tijdens pending boot,
installatie/herstart of zonder thuisnetwerk/geldige tijd. Een geslaagde controle
blijft vijf minuten in RAM beschikbaar voor herhaalde handmatige controles.
Het dashboard leest de lokale samenvatting via de bestaande statuspoll en toont
alleen numeriek nieuwere compatibele firmwareversies (alpha/beta/rc/stabiel), met een knop naar Updates.
Geen automatische installatie of firmwareactie in deze opdracht. 44 gerichte
native gevallen, 26 Node-gevallen, dashboardbrowser en E32-compile geslaagd;
updaterbrowser apart gecontroleerd. Volledige releasegate/uitrol blijft open.

## Alpha36 — geïnstalleerd via de normale GitHub-updater

Op 25 oktober om 10:29 UTC één native installatiecommando; firmware en manifest komen
rechtstreeks van GitHub. Nieuwe alpha36-boot bevestigd, bron `7ddf341`, ELF `ef313784`,
web `2b858b3e` exact; alle 36 installatiecontroles en 45 afzonderlijke nacontroles PASS.
31 geserveerde UI-bestanden exact, alle 86 HA48-bestanden en 13 projecthashes behouden;
zes loggingvelden gelijk, nieuwe bronflags alleen API-defaults, geen settingssave.
Verse back-up van 10 payloads nagelezen. Alle uitgangen uit, TX/poll/test 0.

De normale updatepoort accepteert nu alpha36. Iedere opvolgende reguliere release
vereist opnieuw een geslaagde installatie en onafhankelijke nacontrole. De
multipart-watchdogoorzaak blijft open; actieve bèta blijft NOT_READY.
[Installatie, acceptatie en proces](INSTALLATIE-E32-ALPHA36-20261025.nl.md).

## Grotere release HA48 / E32 alpha35 — gepubliceerd, HA geïnstalleerd

Beide tags staan op bron `70135db3`. Main- en tag-CI en alle negen publieke
pakketten zijn gecontroleerd. HA48 is met verse HA47-back-up van 96 en één normale
Core-herstart geïnstalleerd: alle 86 bestanden exact, SOURCE5, instellingen,
programma's, koppelingen en kaarten behouden. De bundel levert cleanup na een
gewone callbackexception, vier klokregressies en een pure Shelly-decoderbasis.
798 native en 2.356 HA-gevallen per Core slagen; de parser is nog niet geselecteerd
door de BLE-runtime. E32 alpha35 is gepubliceerd, niet geïnstalleerd; actuele
module alpha31 blijft behouden. Uploadgate en actieve bèta blijven **NOT_READY**.
Alle 23 onderdelen, 289 bronverwijzingen en 31 eisen blijven behouden.
[Installatie, aparte nacontrole en grenzen](INSTALLATIE-HA48-ALPHA35-20261025.nl.md).

## Geleverd in alpha36 — publieke ketelcatalogus

About staat direct na Settings. Alle31 BOILER-productgroepen uit de vastgelegde
EMS-ESP-bron plus officiële documentatievermeldingen staan in een catalogus van
60 selecties. Alleen compacte weergavegegevens staan in de firmware; afbeeldingen
staan onder public en worden door de browser geladen. Geen cloudafhankelijkheid
voor bediening en geen automatische driver-/regelprofielwissel. Foto's voor de
nieuwe modellen en functionele profielimport blijven open.
Vier modelafbeeldingen op vijf selecties met bronlink voorbereid; fabrikant-
afbeeldingen voor TrendLine II/GB162 en specialistproductrenders voor ProLine/
SmartLine. Ecomline Classic HRC22H nog zonder geverifieerde originele foto;
generieke tekening niet meer geselecteerd. Afbeeldingen blijven op originele host.
[Ontwerp en grenzen](KETELCATALOGUS.nl.md). Geen firmware- of HA-installatie.

## Geleverd in alpha36 — gescheiden ESP-/EMS-logbronnen

Webfilter ESP / EMS / beide, begrensde RX-framelogging buiten UART-callback en
onafhankelijk opgeslagen bronvinkjes voor dezelfde RFC5424-collector voorbereid.
REST/syslog dragen een bronlabel; afscherming en gedeelde begrensde buffers blijven
behouden. Native25, UDP-loopback/NVS en vier EN/NL-browserprofielen slagen.
Geen hardware-, collector- of firmware-installatieclaim. [Grenzen](LOGGING.nl.md).

## Historische release HA47 / E32 alpha34 — gepubliceerd en HA geïnstalleerd

Beide onveranderlijke tags staan op bron `6f21f34`. Alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketcontroles slagen. De bundel verenigt
robuuste HA-opstart/afsluiten met vier gerichte updatercheckpoints en EN/NL-uitleg.
782 native gevallen en 2.349 HA-gevallen per ondersteunde Core slagen. Alle 23
onderdelen, 286 bronverwijzingen en 31 eisen blijven behouden. Actieve bèta blijft
**NOT_READY**; bron-/kraan-/installatiekwalificatie staan afzonderlijk open.

HA dev47 is geïnstalleerd op bron `6f21f34`, met een verse HA46-back-up van
96 bestanden en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober **06:47:49 UTC** slaagt: 44 controles, alle 86 livebestanden exact
publiek pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; alpha34 is gepubliceerd, zonder firmwareactie.
[Installatie en bewijs](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).

## Historische release HA46 / E32 alpha33

Beide tags zijn gepubliceerd op bron `2d32ad3`; alle toepasselijke main-/tag-CI,
bronreviews en daadwerkelijke publieke pakketreviews slagen. De bundel bevat
begrensde oorspronkelijke ontvangstdiagnostiek en extra herintredebewaking bij
socketoverdracht en kanaaltoelating. 773 native kerngevallen, 5 lokale socketgevallen
en 2.339 HA-gevallen per ondersteunde Core slagen. Alle 23 onderdelen en 282
bronverwijzingen blijven opgenomen. E32 alpha33 is gepubliceerd; de module blijft
op alpha31. Actieve bèta blijft **NOT_READY**.

HA dev46 is geïnstalleerd op bron `2d32ad3`, met een verse HA45-back-up van
95 payloads en één normale Core-herstart. De afzonderlijke nacontrole van
25 oktober 05:12:15 UTC slaagt: 38 controles, alle 86 livebestanden exact publiek
pakket/Git en alle instellingen, programma's, koppelingen en kaarten behouden.
E32 alpha31 blijft op dezelfde boot; er is geen firmwareactie uitgevoerd.
[Installatie en bewijs](INSTALLATIE-HA46-ALPHA33-20261025.nl.md).

**Historische grotere release HA45 / E32 alpha32:** bron `3f12d8b`, beide tags en
negen downloads gepubliceerd. Alle definitieve CI- en onafhankelijke bron-/pakketreviews
slagen: 767 native kerngevallen, 4 lokale socketadaptergevallen en 2.333 HA-gevallen
per ondersteunde Core. 75 native gevallen ook onder sanitizers (geen extra unieke gevallen).

**HA45 geïnstalleerd:** 85 livebestanden exact publiek pakket/Git, verse HA44-back-up
van 95 payloads en één normale Core-herstart. Afzonderlijke alleen-lezen nacontrole
25 oktober 03:09:24 UTC: alle 38 controles geslaagd, instellingen/programma's/kaarten
behouden. E32 alpha31 en dezelfde boot behouden; alpha32 is gepubliceerd maar niet
geflasht door deze opdracht. [Installatieverslag](INSTALLATIE-HA45-ALPHA32-20261025.nl.md).

**Vorige gezamenlijke release HA44 / E32 alpha31:** bron `659879e`, beide
onveranderlijke tags en negen downloads gepubliceerd. Alle drie definitieve
CI-runs slagen; 728 native firmwaretests en 2.323 HA-gevallen per ondersteunde
Core, nul fouten/skips. Onafhankelijke bron-, hoofd- en definitieve tagpakketreview
geslaagd. Alle negen publieke bestanden exact eigen tag-CI; de aanvullende
E32-distributieverschillen door buildmetadata zijn afzonderlijk gecontroleerd.

**HA44 geïnstalleerd:** 85 bestanden exact publieke ZIP/Git, verse HA43-back-up
van 94 bestanden en één normale Core-herstart. Afzonderlijke nacontrole
25 oktober 00:32:01 UTC: alle 20 checks geslaagd. Alle instellingen, programma's,
koppelingen en frontend behouden. SOURCE5 bleef behouden; de voorafgaande
horizonrollover veranderde geen gebruikersprogramma. Die nacontrole zag E32
alpha28; de nieuwere alleen-lezen waarneming van 01:50 UTC ziet alpha31. Deze
opdracht heeft geen E32-upload gestart; oude watchdogoorzaak en fysieke poorten blijven open.
[Installatieverslag](INSTALLATIE-HA44-ALPHA31-20261025.nl.md).

**Vorige HA-release dev43:** bron `97eb9a0`, gepubliceerd en geïnstalleerd op
Core 2026.10.3. Alle 84 bestanden exact publieke ZIP/Git; verse HA40-back-up van
93 bestanden en één normale Core-herstart. Zeven softwarepoorten en exacte tag-CI
geslaagd; 2281 gevallen per ondersteunde Core-versie, 1028 onafhankelijke
pakketcontroles. Vier openbare downloads bytegelijk aan beide CI-pakketten en de
beoordeelde kandidaat. Afzonderlijke nacontrole 21:17:50 UTC: alle 38 checks geslaagd.
Alle instellingen/koppelingen behouden; alleen twee eigen kamerkaarten v38→v41.
E32 alpha30-downloads/tag ongewijzigd; module blijft alpha28 met herstelblokkade.
[Installatieverslag](INSTALLATIE-HA43-20261024.nl.md).

**Vorige gezamenlijke release dev39 / alpha30:** bron `3bad1747`, beide onveranderlijke
Git-tags gepubliceerd, alle drie CI-runs geslaagd; negen openbare downloads
bytegelijk aan CI. Onafhankelijke bron-/pakketreview geslaagd (2424 pakketchecks).
HA39 geïnstalleerd met verse 93-bestandenback-up en behouden 105 registryrecords;
afzonderlijke nacontrole van 18:54 UTC geslaagd. E32 alpha30 is niet geïnstalleerd: de eerdere
alpha28-uploader-watchdogoorzaak en herstelroute blijven onbekend.
[Installatieverslag](INSTALLATIE-HA39-ALPHA30-20261024.nl.md).


| Onderdeel | Vastgestelde stand |
| --- | --- |
| Geïnstalleerde firmware | E32 `v0.1.0-e32v2-alpha.36`, bron `7ddf341`, ELF `ef313784`, web `2b858b3e`; één native GitHub-update en 45 afzonderlijke nacontroles geslaagd |
| Geïnstalleerde HA-integratie | `0.4.0.dev48`; vorige volledige installatiecontrole op Core 2026.10.3 met 86 exacte bestanden/105 behouden registryrecords. Nieuwe alleen-lezen controle: Core 2026.10.4, `setup_error`; actuele Python-bronhashes niet gelezen |
| Geïnstalleerde bron | HA `70135db3c86df1f970265bc426fe5e35729c8261`; E32 `7ddf3410666d814850275433d9dddd266e5d83ba`;86 HA-bestanden exact |
| Softwarebasis | `out/beta-boiler-20261023`, `work/beta-boiler-20261023`; HA48 levert bewaakte async-opstart/afsluiten, cleanup na callbackexception en ontvangstdiagnostiek; alpha35-bron bevat pure Shelly-decoderbasis en updatercheckpoints naast de eerdere beveiligde aanvraag-, kanaal- en socketoverdracht. Productfabriek blijft gesloten; alle 23 voorbereide onderdelen behouden |
| Doel volgende release | Eerste actieve bèta: huidige passieve ketelkoppeling behouden en begrensde start/stop beproeven na bron-/kraan-/installatiekwalificatie |
| Nog geen bèta-vrijgave | Actieve proef-/zendketen en concrete fysieke voorwaarden ontbreken nog |
| Huidige fysieke grens | Geen bewezen echte kraan-/ketelregeling; E32-TX en actuatoruitgangen geblokkeerd |
| Laatste volledige installatiecontrole | 25 oktober 10:37 UTC: alpha36/HA48, verse back-up van 10 payloads, 36 installatiecontroles en 45 afzonderlijke checks PASS; instellingen/SOURCE5 behouden en uitgangen uit |
| Beperkte ontvangstcontrole vóór uitrol | 25 oktober 05:46:49 UTC: HA46/shadow_ready, SOURCE5/digests behouden, TV02-owner met één callback/enqueue/acceptatie en stale lokale temperatuur; kamermeting ongekwalificeerd. Acht checks / nul productieacties, geen nieuwe directe E32- of volledige bronhashaudit |

[Verse alpha31-waarneming en grenzen](WAARNEMING-E32-ALPHA31-20261025.nl.md).

**Broncontrole:** de release-inventaris bewaart alle 23 voorbereide onderdelen
met 286 gecontroleerde bronverwijzingen. Het gepubliceerde bron-/licentie-/
herlinkpakket is onafhankelijk vergeleken met de exacte Git-tag en bijbehorende
ELF/webidentiteit. Bij de gezamenlijke alpha24/dev30-bundel zijn alle 82 HA-componentbestanden ook
met het E32-pakket vergeleken. De latere HA-updates dev31/dev32/dev33/dev34 zijn afzonderlijk met
hun eigen publieke pakket, Git-bron en alle live hashes gecontroleerd. Historische checkpoints en afgewezen kandidaten blijven bewaard;
geen bestaande tag of download is vervangen.

**Afvinken:** `[x]` geldt alleen voor de genoemde software-/leveringsuitkomst.
Een meegeleverd model of geslaagde simulatie bewijst geen aangesloten functie,
ketelreactie of productacceptatie. Alle oorspronkelijke fasen blijven open waar
verplichte fysieke of langere-termijnproeven ontbreken.

## GitHub-updater — nieuwe afzonderlijke herstelbeoordeling

Verse read-only controle10:10:44UTC vindt een native alpha28→31-controlepunt:
HTTP200, alle2.595.888bytes ontvangen, `boot_slot_selected`. Publiek manifest en
actuele31-bron/web passen; vier native bronbestanden zijn gelijk tussen28/31.
Dit bewijst meer dan idle/bereikbaarheid. De mislukte multipart-upload blijft
apart: reset6, taak/stack/oorzaakUNKNOWN. De native vervolgroute wordt afzonderlijk
beoordeeld; nog geen nieuwe controle/installatie/herstart uitgevoerd.
[Feiten, routes en grenzen](E32-GITHUB-UPDATE-ONDERZOEK-20261025.nl.md).

## Prioriteiten na HA48 en de gepubliceerde E32 alpha36

Alle 31 eisen, 23 brononderdelen, 11 fasen, 8 werkpakketten en 14 releasepoorten
zijn opnieuw naast de geïnstalleerde basis gelegd. B01–B03 zijn softwarematig af;
B04–B14 blijven open voor de genoemde volledige bèta-uitkomst. De geleverde
passieve bundel sluit die actieve poorten niet. Oudere losse bewijsregels zijn
historisch; de tabellen en deze volgorde bepalen nieuw werk.

| Prioriteit | Punt / koppeling | Eerstvolgende concrete uitkomst | Wat buiten software blijft |
| --- | --- | --- | --- |
| P0 | E32-update / R28/I03 | Native alpha31→36 geïnstalleerd/geaccepteerd; volgende release verplicht nieuwe update/nacontrole met SHA256-gebonden bewijs | Oude multipart-watchdog niet verklaard; geen blinde fallback, actieve fysieke poorten blijven apart |
| P0 vóór actieve M2 | Incidentele CI-kamerassertie | Klokdomeinfout in de eindige kamerfixture hersteld en gepubliceerd in HA48: twee van vier epochregressies falen vóór correctie; 50 gerichte gevallen per Core slagen erna. Acht bestaande replays behouden; oude afwijking verder causaal onderzoeken | Definitieve HA43-CI en twee diagnostische native jobs slagen; oorspronkelijke oorzaak onbekend, geen fysieke vrijgave |
| P0 vóór fysieke proef | Gemeld pendelen | Onderzoek richting warmwaterbedrijf vervolgen: gebruik/bijwarmen onderscheiden; stabiele nulmeting vastleggen | Geen bewezen oorzaak; geen zendproef bij onverklaarde instabiliteit |
| P0 | TV02-opstartdiagnose, B05 | HA38-opstartherstel geleverd; verse beperkte HA46-controle 05:46 UTC toont één oorspronkelijke workeracceptatie. HA47 sluit late/cancel/dubbele opstart; 2.349 HA-gevallen per Core geslaagd. HA48 levert cleanup na callbackexception: 3 negatieve/162 gerichte en 2.356 volledige gevallen per Core gecontroleerd; geïnstalleerd | Ontvangst is nu geobserveerd maar stale; terugkerende verse ontvangst, oorspronkelijke causale echo en fysieke bron-/kraankwalificatie blijven open |
| P0 | Echte kamerbron, R03/B04/WP03 | Brongebonden acquisitie-/profielketen afmaken met echte oorspronkelijke rapporten | RTCGQ11LM device_temperature niet als kamerbron kwalificeren; geen automatische sensorwissel |
| P0 | Kraantransactie, R05/B05/WP05 | HA-workerbedrading geleverd in HA44; normale firmware-MQTT-route en product-SOURCE-fabriek verbinden, native zendtransactie aan oorspronkelijke echo koppelen | Exact geïnstalleerde converterbron ontbreekt nog in bestaande toegang; geen cache/serviceacceptatie als ACK |
| P0 | Veiligheidsproducenten, R07/R23/B06/WP06 | Softwarefences voor alle zes gedateerde feiten afgerond/getest; echte producenten en installatieprofiel aansluiten | Geen generieke flow-/pompaanname of ongekwalificeerde vrijgave |
| Geleverd | EMS-apparatenweergave, R15/R25/R29/I11/I12/I21 | Eerder geleverd op alpha28, echte GET en twee apparaten gecontroleerd; huidige versie31 apart waargenomen | Passief; ontbrekende identiteit/decoder blijft zichtbaar |
| P1 | Classic-zender en stopketen, R08/B07–B08/WP02 | Rapportvolgorde en HA-intrekking softwarematig afgerond; beoordeeld profiel en echte zend-/stopketen kwalificeren | TX/adres/masker en fysieke zender pas na B09 beoordelen |
| P1 | Installatieacceptatie, R22–R24/B09 | Bestaande acceptatiekaart concreet maken voor UART/arbitrage/Tado óf E32/minimumflow/naloop/onafhankelijke stop | Fysieke feiten blijven open; vragen bundelen voor de proef, niet iedere bronstap blokkeren |
| P1 | HTTPS-herstelbaarheid, R28/I03/WP08 | Geïnstalleerde checkpointdiagnose gebruiken bij gericht onderzocht vervolg | Vorige workerfout onbekend; app-only succes is geen workerreparatie of reden voor replay |
| P2 na M2 | Productafwerking en schaal, R01/R02/R04/R06/R09–R21/R26/R27/R30/R31 | Bestaande editor/groep/vloer/weer/metrics/historie/comfort/leerbasis gecontroleerd verbinden en toetsen | Acht zones/72u, echte grafiektijdlijn, externe meter en modelspecifieke writefuncties niet fictief aftekenen |
| Releasepoort na relevante implementatie | R28/R29/B10–B14 | Eén gezamenlijke freeze, volledige regressie, exact pakket en uitrol met back-up/readback | Geen aparte kleine release voor ieder bronpunt; fysieke proef blijft afzonderlijk |

Leren/PI/PID en blijvend bewaarde, gevalideerde parameters per ruimte blijven
verplicht voor de definitieve versie (R12); nieuwe F9/F10-stages volgen na M2.
Een ontbrekende fysieke waarneming blokkeert onafhankelijk softwarewerk niet.

### Geleverd in alpha34-bron — updateverificatie gericht onderscheiden

Vier vaste pre-operatiecheckpoints gebruiken de bestaande NVS-journal:
checksum, native imagevalidatie, flash-readback en bootselectie. Dezelfde
verificatiepoorten blijven in dezelfde volgorde verplicht. Oude schema1/164-byte
checkpoints blijven leesbaar; opslagfalen behoudt de laatste bevestigde snapshot.
De bestaande status-UI vertaalt alle vier fasen in EN/NL; lezen start geen update.

Negen nieuwe native gevallen, totaal 782 geslaagd; 40 updatergevallen ook onder
ASan/UBSan, 24 updaterbrowsergevallen en vier taal-/schermprofielen geslaagd.
E32-compile en alpha34-publicatie geslaagd. Geen firmware-installatie, blinde retry,
herstelbewijs of verklaring van de historische watchdog. HA47 is geïnstalleerd;
E32 alpha31 blijft behouden. De actuele inventaris heeft 286 bronverwijzingen
na toevoeging van de HA-opstartcorrectie hieronder.
[Betekenis en verificatie](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).

### Geleverd in HA47 — native opstart blijft bij één eigenaar

Annuleren/afsluiten tijdens programma-/Store-lezingen kan geen transport, worker,
listener of timer meer achteraf aanmaken. Dubbele start wordt geweigerd zonder
de eerste eigenaar te sluiten; een afgesloten object start niet opnieuw.
Late unsubscribe-handles worden direct opgeruimd. De optionele temperatuur-
aanmelding deelt één seconde totaalbudget; beschikbare besturing blijft intact
bij die diagnosefout. Geen nieuw abonnement, worker, route, retry of uitvoerfunctie.

Tien negatieve baselinegevallen falen vóór herstel; 139 gerichte en 2.349 volledige
HA-gevallen per Core 2026.10.2/2026.10.3 slagen. Zeven pakkettests slagen.
Dezelfde bundel behoudt de eerdere updatercheckpoints en alle 23 onderdelen,
nu 286 bronverwijzingen. Gepubliceerd in HA47 / alpha34; HA47 is met back-up/nacontrole geïnstalleerd.
[Uitwerking, oorspronkelijke fouten en bewijs](HA-OPSTART-LIFECYCLE-20261025.nl.md).

De beperkte livecontrole 05:46 UTC via de bestaande HA-agent toont oorspronkelijke
TV02-workerontvangst (1), zonder getelde drops/fouten; het bericht is stale en
geen causale kraan-ACK. Temperatuur heeft nul oorspronkelijke topics en blijft
`profile_missing`. SOURCE5/digests behouden, nul productie-/deviceacties. De diagnose
kwalificeert geen kamerbron/afgiftepad. Na de HA47-herstart is de eigenaar nieuw:
tellers nul/TV02 waiting bij 06:47 UTC; oude data wordt niet hergebruikt. Fysieke
B04–B14-poorten blijven open.

### Geleverd in HA46 / alpha33 — oorspronkelijke ontvangstdiagnostiek

De bestaande HA-diagnostiekdownload bevat vaste RAM-tellers voor temperatuur-
en TV02-verkeer: callback, plaatsing, vroege drops en workeracceptatie/-afwijzing/
-fouten. Er zijn geen topics, unieke ID's of berichtinhouden in de snapshot.
Geen nieuwe route, abonnement, worker of opslag. De bestaande wachtrijreservering
blijft behouden; counters geven geen meet-/kraankwalificatie.

223 gerichte native HA-gevallen slagen, inclusief de echte bestaande worker en
beide ontvangers. Volledige lokale suite: 2.339 gevallen per Core 2026.10.2/2026.10.3,
nul fouten of skips. HA46 / E32 alpha33 bundelt dit met de eerdere
verzendcontroles; definitieve CI en onafhankelijke pakket-/publicatiereviews slagen.
[Betekenis, begrenzing en verificatie](ORIGINAL-INGRESS-DIAGNOSTIEK.nl.md).

### Geleverd in alpha33-bron — laatste verzendcontrole

Een begrensde regressieproef op de gepubliceerde alpha32-bron bevestigt drie
callbackproblemen in de voorbereide `beforeHandoff`-grens: recursie via
beschikbaarheid, recursie via de klok en toelating van een nieuw kanaal vanuit
de beschikbaarheidscontrole. De broncorrectie bewaakt die grens afzonderlijk en
bewaakt ook beschikbaarheid en klok op hun eigen callbackgrens. Betrokken kanalen worden bij herintrede
blijvend ingetrokken. Normale controle binnen een zendcallback blijft mogelijk.

Zes kanaalgevallen en één echte lokale socketproef zijn toegevoegd; vijf
kanaalgevallen en de socketproef falen aantoonbaar vóór de correctie. Alle 773
native kerngevallen en 5 socketgevallen slagen; 77 kerngevallen ook onder
sanitizers en debugiteratoren. E32-build en publicatie alpha33 geslaagd.
E32 blijft alpha31; deze broncorrectie is niet op de module geïnstalleerd.
[Reproductie en releasegrens](M2-LAATSTE-VERZENDCONTROLE-20261025.nl.md).
Geen aanwijzing dat dit de eerdere uploader-watchdog of het pendelen verklaart.

### Geleverd in HA45 / alpha32 — oorspronkelijke FW-aanvraag en transportkanaal

De volgende bundel verbindt aanvraagvolgnummer, oorspronkelijke lokale deadline,
HA-antwoord en eenmalige opdracht. Optionele firmwarebedrading gebruikt de bestaande
MQTT-client en loop, met intrekking bij disconnect/SOURCE-wissel. De productfabriek
blijft gesloten; normale regelaarselectie, oorspronkelijke kraanecho en fysieke
kwalificatie blijven open. [Uitwerking](M2-AANVRAAG-EN-KANAAL-20261025.nl.md).
Deze samenhangende wijzigingen zijn gepubliceerd als HA45 / E32 alpha32. HA45 is
geïnstalleerd en onafhankelijk gecontroleerd; E32 blijft op alpha31. De actieve
bèta blijft NOT_READY.

### Geleverd in HA43 — B04/B05/B10

- HA-ontvangertoelating als standaard gesloten, brongebonden kern: vijfsecondenvenster op de HA-klok, exacte scope/grant/sequence en één lopende actie. Geen verlenging bij ontvangst of retry; historische serviceacceptatie blijft geen kraan-ACK. Nog niet geselecteerd door de normale native fabriek; FW-wireafzender, huidige leasebinding en causale oorspronkelijke echo blijven open.
- Kamereditor: directe EN/NL-waarschuwing voor de gekozen interne apparaattemperatuur en diagnostische entiteiten. Gewone getalwaarden kwalificeren geen bron; ontbrekende native metadata blokkeert de editor niet. Geen automatische sensorwissel.
- Frontend dev41/v41 met behoud van v38/v35-kaarten; koude upgrade, conceptkeuze en beide talen getest. Geïnstalleerd en onafhankelijk gecontroleerd; geen fysieke vrijgave.

[Uitwerking en verificatie](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

### In voorbereiding voor de grotere bèta — FW→HA-kraanberichten

**HA-workerbedrading 25 oktober:** grantaanvragen en opdrachten lopen nu door de
bestaande native worker en MQTT-verbinding. Actuele lokale sessie/config/binding,
oorspronkelijke ontvangsttijd en lease begrenzen de ontvanger. Dezelfde context
beperkt ook de adapter na wachten op zijn servicelock. De productfabriek levert
nog geen fysieke kraaneigenaar; firmware-MQTT-bedrading, echte SOURCE-kwalificatie
en causale kraanecho blijven open. Geen fysieke opdracht of bèta-vrijgave.
[Contract, tests en grenzen](M2-NATIVE-KRAANROUTE-20261025.nl.md).

**Aanvullende ontvangercontrole 25 oktober:** een reproduceerbare fout liet na
serviceacceptatie een tweede nieuw volgnummer met hetzelfde vijfseconden-grant
toe. De ontvanger verbruikt het grant nu vóór callbacks/awaits. Exacte duplicaten
blijven het oorspronkelijke resultaat delen; een volgende nieuwe opdracht vereist
een nieuw grant. Dit verandert geen serviceacceptatie in een kraan-ACK en sluit
B05 niet. Deze ontvangerfix is meegeleverd in de geïnstalleerde HA44; gerichte regressie
vóór herstel faalt, daarna slagen 146 gerelateerde gevallen en de volledige
regressie van 2.298 gevallen (2.230 tests + 68 subtests) op beide Core-versies.
De eigen tijdelijke localhost-testbroker is gestopt en verwijderd.
Bewijs: `out/large-beta-grant-20261025/` in de bronwerkboom.

De firmwaretegenhanger `ActuatorIntent` kan het bestaande HA-grant lezen en een
exacte `room_target`-envelop produceren. Dit blijft broncode in voorbereiding,
zonder productie-selectie, publisher, nieuwe brokerroute of fysieke opdracht.
De C++-bytes worden daadwerkelijk door de native HA43-ontvanger en de bestaande
Profile-C-adapter gecontroleerd; de ontvangst bewijst alleen serviceacceptatie.

Oorspronkelijke lokale aanvraag- en leasedeadlines begrenzen het venster; een
herhaald grant verlengt dat niet. Eén grant produceert maximaal één opdracht,
zonder automatische retry. Scopeverlies, waargenomen leaseverlies, klokterugloop
en intrekken tijdens autorisatie blokkeren deze eigenaar blijvend.
702 native tests en 2.287 HA-gevallen per ondersteunde Core slagen; onafhankelijke
bronreview v2 geslaagd. Zie [uitwerking en grenzen](M2-FW-HA-INTEROPERABILITEIT-20261024.nl.md).

**B05 blijft open:** de normale SOURCE-/lease-eigenaar en transportbedrading,
causale oorspronkelijke Tuya-zendtransactie/echo en fysieke kwalificatie ontbreken.
Geen nieuwe release/tag of productie-installatie alleen voor deze tussenstap.

### Verder voorbereid — bron-/leasecontrole op de transportgrens

`ActuatorDispatch` verbindt de afzender met actuele lokale bron-/kloklezingen en
de bestaande synchrone transportfunctie, inclusief controle na codering en
na overdracht. Geen normale fabrieksselectie of nieuwe MQTT-route. Vijf
reproduceerbare lease-/intrekkingsgrensfouten zijn gesloten; 728 native tests
en 32 gerichte strikte ASan/UBSan-proeven slagen; 2.297 HA-gevallen per Core
slagen. De sanitizerpoort is met een echte foutproef gecontroleerd. De nieuwe C++/HA-proeven toetsen de
gehele voorbereide keten met synthetische feiten; geen fysieke opdracht.
[Uitwerking en open grenzen](M2-SOURCE-TRANSPORT-20261025.nl.md).

De bestaande controller levert nu daarnaast een read-only actuele sessiecontext
uit eigen configuratie/SessionAdmission. Zeven nieuwe native proeven toetsen echte
handshake, deadlines, disconnect/reconnect en nul fysieke bevoegdheid.

Normale SOURCE-/profiel-/grant-/transportselectie, causale oorspronkelijke echo en fysieke
kwalificatie blijven B05-openpunten. Transportacceptatie is geen kraan-ACK;
intrekken verhindert nieuwe opdrachten maar bewijst geen fysieke sluiting.

### Geleverd in HA40 — B05/M2-kraanadapter

De kraanadapter bewaakt nu één monotone kloklevensduur per toegelaten eigenaar.
Klokterugloop/ongeldige tijd trekt de adapter blijvend in, ook bij weigering of
exception in een autorisatiecallback en na wachten of dispatch. Bij een al
verzonden opdracht blijft de fysieke uitkomst unknown; geen automatische retry.
14 nieuwe regressiegevallen, waarvan 13 vóór reparatie falen; alle 141 gerichte
tests slagen op Core 2026.10.2 en 2026.10.3; volledige tag-CI 2209 per versie.
HA40 geïnstalleerd en onafhankelijk gecontroleerd; E32 alpha28 en fysieke
blokkades blijven behouden. De normale ontvangstroute,
causale doel-echo en fysieke kwalificatie blijven open.
[Uitwerking en bewijs](M2-KRAAN-KLOK-20261024.nl.md).

### Pendelen — praktijkonderzoek blijft open

De gebruiker zag het in grafieken, kent begintijd en warmwatergebruik niet en
meldt dat het nu weer goed lijkt. De eerdere waarnemingen correleerden met
warmwaterbedrijf; dat bewijst geen oorzaak. Eerdere controles: TX/polls/proefframes
0 en uitgangen geblokkeerd. Geen reparatie of normale ketelwerking claimen.
De volledige nulmetingen en eerdere TV02-/releasecheckpoints staan in de
[historie](WORKBOARD-HISTORIE-20261024.nl.md).

### Historisch checkpoint — HA dev38 / E32 alpha29

Destijds was HA dev38 geïnstalleerd; E32 bleef alpha28 na één mislukte upload en
task-watchdogreset (code 6; taak/oorzaak onbekend). Hoogste prioriteit: offline
uploadonderzoek en onderbouwde herstelroute, zonder blinde retry.
[Actuele installatie-uitkomst](INSTALLATIE-HA38-ALPHA29-20261024.nl.md).
De bundel behoudt alle 23 voorbereide onderdelen en voegt het volgende toe:

- Oorspronkelijke temperatuurrapporten verliezen hun diagnosegeldigheid direct
  bij native model-/identiteitswijziging of uitschakeling. Terugzetten van de
  registry herstelt de oude ontvangst niet; alleen een nieuw beoordeelde eigenaar
  kan opnieuw beginnen. Gewone gebruikersnamen blijven behouden.
- Beide oorspronkelijke-rapportwaarnemers worden vanuit de bestaande native
  registrygebeurtenissen gecontroleerd. Een fout in één waarnemer verhindert de
  controle van de andere niet. Geen nieuwe listeners, taken of fysieke opdrachten.
- Metadata-wachten en niet-beschikbare kraanontvangst krijgen duidelijke EN/NL-
  meldingen. Frontendmodule en kaartidentiteit gaan naar dev38/v38 zodat de
  aangepaste pagina bij een update geladen wordt; oude waarden blijven verborgen.

Zes nieuwe native regressiegevallen; vóór reparatie faalden de drie tijdelijke
model-/uitschakelgevallen. 142 gerichte tests en vier browserregressies slagen.
Volledige controle: 2189 gevallen op elk van Core 2026.10.2 en 2026.10.3
geslaagd, zonder fouten/errors/skips.
Onafhankelijke live voorcontrole geslaagd; bronreview vond één v35-compatibiliteitsprobleem,
hersteld met alias en expliciete koude upgradeproef. Vier browserregressies
opnieuw geslaagd; onafhankelijke bron/pakketreview en software-CI geslaagd.
Publicatiejobs faalden op oude noteheaders; eerste publicatie is met gecorrigeerde
tekst en ongewijzigde CI-pakketten hersteld. Publieke downloads exact gecontroleerd.
Verse back-up en onafhankelijke nacontrole bevestigen HA38/E32 alpha28. Een nieuwe
voorcontrole voorkomt deze noteversiefout vóór publicatie.
Dit levert geen actieve bèta of Bluetooth-driver op. Bewijs:
`out/release-source-lifecycle-20261024/` en `out/combined-dev38-alpha29-20261024/`.

### Voorbereid na de release — handmatige app-upload

- [x] Strikt decimale positieve bestandsgrootte, binnen de inactieve apppartitie;
  alleen de opgegeven omvang aanbieden aan native `esp_ota_begin`.
- [x] Afgebroken, te korte, te lange of ongeautoriseerde uploads kunnen niet selecteren;
  native handles worden precies één keer vrijgegeven. Native `end` verbruikt de handle
  ook bij fouten; een nieuwe upload bevestigt geen oude pending boot.
- [x] Hoogstens één firmwarebestand per verzoek. Opstartpartitie pas kiezen in de
  laatste geautoriseerde handler na het volledig verwerkte multipart-verzoek.
- [x] Zestien nieuwe native foutgevallen en elf uitvoerbare REST-grensscenario's;
  uploadbatch 665 geslaagd; huidige totaalsuite 689. REST-proef opgenomen in bestaande CI-nativegate.
- [ ] Herstel van de watchdogfout op echte hardware bewijzen. Deze bronhardening
  is geen oorzaakverklaring en is nog niet geïnstalleerd of als nieuwe versie gepubliceerd.

Zie [offline uploadonderzoek](OTA-UPLOAD-ONDERZOEK-20261024.nl.md).

### Afgewerkt in de volgende bronbundel — B06 veiligheidsfeiten

- [x] Afgewezen toekomstige tijdstempels blijven per feit ingetrokken als de klok
  die tijd later bereikt; alleen strikt nieuwer bewijs kan dat feit vervangen.
- [x] Alle tegelijk afgewezen feiten worden apart onthouden. Reparatie van één
  veld herstelt geen ander veld en verlengt geen oorspronkelijke levensduur.
- [x] Lokale klokterugloop blijft ongeldig, ook bij gelijktijdig verkeerde eigenaar
  of een sessiestart die door de terugloop nog in de toekomst ligt.
- [x] Zonepolicy en storingsbevestiging gebruiken dezelfde veiligheidscontrole;
  toekomstige, ontbrekende, oudere of tegenstrijdige acquisities blijven ingetrokken.
- [x] Veranderde veiligheidswaarden met dezelfde meettijd kunnen geen toestemming
  herstellen; een nieuw feit heeft een nieuwe acquisitietijd nodig.
- [x] Twaalf nieuwe regressies; vijf hydraulische en zes gedeelde-policygevallen
  faalden vóór reparatie in afzonderlijke voorproeven. Definitieve suite: 677 native
  tests; E32 en ESP32-build gecontroleerd. Geen nieuwe taken/IO/allocaties.
- [ ] Werkelijke producenten, bronprofielen, hydraulische installatie en fysieke
  stop-/flow-/DHW-proeven kwalificeren. Alle fysieke uitvoer blijft geblokkeerd.

Bewijs en grenzen: [veiligheidsfeiten](VEILIGHEIDSFEITEN-20261024.nl.md).

### Afgewerkt in de volgende bronbundel — B07/B08 ketelrapporten

- [x] Vertraagde veldupdates overschrijven geen nieuwere ketelgegevens; oudere
  deeltelegrammen kunnen ontbrekende velden nog met hun oorspronkelijke leeftijd aanvullen.
- [x] Tegenstrijdige waarden op dezelfde acquisitietijd blijven ongeldig totdat
  strikt nieuwer bewijs beschikbaar is. Ontvangsttellingen blijven alle rapporten tellen.
- [x] Echte proefpolicy/poll-executor: oude uit-berichten bevestigen geen stop en
  kunnen nieuwere DHW-prioriteit niet verbergen om een positieve vraag toe te laten.
- [x] HA-cache: een andere veldgroep of hogere publicatiesequentie herstelt geen
  ingetrokken oude waarde. Geldige null-intrekking behoudt de oorspronkelijke deadline
  en trekt alleen de betrokken entiteit in, zonder andere geldige velden te verbergen.
- [x] Tien rapport-/overdrachtsregressies, twee nul-uptimecompatibiliteitstests en
  zes HA-regressies toegevoegd; negen native en zes HA-gevallen faalden vóór reparatie.
  Native totaalsuite 689 en beide firmwarebuilds geslaagd; 2195 HA-gevallen per
  ondersteunde Core-versie, zonder fouten of skips. Eigen testfixture opgeruimd.
- [x] Volledige HA/FW-controle vond een nul-uptimeregressie in de vorige aanscherping;
  echte acquisitie bij uptime nul hersteld met afzonderlijke interne markeringen.
  Gewijzigde proef-feiten krijgen een eigen nieuwe acquisitietijd.
- [ ] Beoordeeld profiel, bron-/installatiekwalificatie, echte UART en fysieke
  start/stop-/DHW-proeven afronden; geen automatische fysieke vrijgave.

Bewijs: [ketelrapportvolgorde en HA-overdracht](KETELRAPPORT-VOLGORDE-20261024.nl.md).

### Uitbreiding X01 — direct Bluetooth en zelfstandige E32

Nieuwe gebruikersopdracht: Shelly BLU TRV rechtstreeks koppelen en een lokale
E32-bedrijfsmodus toevoegen. **Aanvullend op alle bestaande functies; onderzocht,
nog niet gebouwd of geïnstalleerd.** De technische haalbaarheid steunt op de
Shelly-GATT-documentatie en onze bestaande NimBLE-stack. Uitwerking:
[directe BLE-/standalone-route](SHELLY-BLU-TRV-STANDALONE.nl.md).

Ook toegevoegd aan X01: **Shelly BLU H&T Display ZB (SBHT-103C)** en
Settings → Bluetooth-apparaten, met EN/NL-onboarding, expliciete kamertoewijzing,
beveiliging en zichtbare meetkwaliteit/bronuitval. Ook gevraagd: **Xiaomi Monitor 3
(MJWSD05MMC)** via een apart versleuteld BLE-profiel; verkrijging van de
apparaatsleutel en echte ontvangst/meetkwaliteit moeten nog worden bewezen.
[Uitvoering en acceptatie](BLUETOOTH-APPARATEN.nl.md). In dezelfde ongepubliceerde bèta is nu de normale E32-instellingen-/ontvangstroute voor SBHT-103C-diagnose aangesloten: acht expliciete bindings, echte AES-CCM/MIC, sleutelredactie, sessiegebonden conditional save, oorspronkelijke ontvangstleeftijd en boot-lokale tellerafwijzing. Dezelfde scanner, geen nieuwe taak of actuatorwrite. 906 native gevallen slagen; apart Xiaomi Monitor3-profiel (MiBeacon4/5, product0x2832/0x4c47) met52 parser-/eigenaar- en25 echte cryptogevallen en12 browserprofielen getest. Shelly BLU TRV-diagnose is aangesloten: doel/berekende/externe temperatuur apart, geen GATT- of kraanwrite. Private sleutelopslag is buiten het netwerkdocument geplaatst voor rollback, met 32 gedeelde SDK-grensgevallen en onafhankelijke netwerk-/Bluetooth-readbackcontrole. Opslaan controleert verse NVS-statistieken en behoudt de regelconfiguratie-/GC-/modelreservering; onbekende of te kleine opslag weigert vóór een schrijfnamespace. 10 grens-/reserveringsgevallen en 21 voorbereide modelbackendgevallen slagen onder sanitizers. Uitgebreide bundel-/browsercontroles worden vastgelegd. Echte apparaatacceptatie, sleutelverkrijging, blijvende replay-/acquisitiekwalificatie, TRV en zelfstandige regeling blijven open. Geen fysieke vrijgave of installatie.

Volgorde: apparaatgebonden alleen-lezen BLE-basis inclusief sensor → begrensde proefkraan zonder
ketel → lokale eigenaar/programmering/tijd/opslag → integratie en uitvalproeven.
Bestaande P0-opstartdiagnose en M2-werk blijven lopen. Dezelfde regelkern en
veiligheidsvoorwaarden blijven gelden; geen tweede schrijver of langere HA-lease
als vervanging voor zelfstandigheid. Bestaande 31 eisen/23 onderdelen blijven behouden.
HA-only apparaten, Recorder en HA-automatiseringen houden hun eigen afhankelijkheid.

## 2. Af, geleverd en dus ook in de volgende release behouden

- [x] Eigen bron-/SDK-/licentie-/herlinkbasis en onveranderlijke pakketten.
- [x] Weblogin, sessie/CSRF, netwerk/setup en bestaande update/herstelroutes.
- [x] HTTPS-updater met TLS-geheugenreparatie, begrensde catalogus en automatische release-indeling.
- [x] About, uitloggen rechtsboven en herstart onder Settings.
- [x] HA-kamer-/apparaatinrichting, metadata/identiteiten en helpervrije weekplanner.
- [x] Korte plannerblokken op touch; programmawijziging met echte E32-readback/ACK.
- [x] Actieve sensor/TRV/grenswijziging via normale gecontroleerde save/apply/retry.
- [x] HA-koude-startreparatie; drie echte verse sessies zonder refresh/errorcard.
- [x] Echte kamernamen op het E32-dashboard en expliciete statische webroutes.
- [x] Meetstatus, toelatings-/geheugendiagnose en passieve Classic-decoderbasis.
- [x] Alpha17/dev23 gepubliceerd, geïnstalleerd en onafhankelijk gecontroleerd met behouden instellingen/programmas.
- [x] Gezamenlijke passieve alpha24/dev30-bundel gepubliceerd en normaal geïnstalleerd; 82 HA-bestanden, nieuwe E32-boot, ELF/web/bron en behoud onafhankelijk gecontroleerd.

Bewijs: `out/combined-release-evidence-20261023/FINAL-REVIEW.json` en deelreviews.
De 1694 HA-tests horen bij die historische bron. De gezamenlijke alpha24/dev30-
levering heeft 2003 HA-checks zonder fout/skip en een afzonderlijk geïnstalleerde
bron-/runtimecontrole in `out/combined-alpha24-dev30-20261024/`. HA dev31 voegt
het geteste graph-bronherstel toe met 2011 geslaagde HA-checks en afzonderlijk
installatiebewijs in `out/ha-dev31-native-binding-20261024/`. Seriële stilte na de routereparatie is niet opnieuw fysiek
opgenomen; correcte live HTTP-/assetroutering wel.

## 3. Alles wat voorbereid is, meenemen in de bèta

Elke rij hieronder blijft in de nieuwe bronbasis. “Meenemen” is geen opdracht
om onafgemaakte of ongekwalificeerde mogelijkheden automatisch te activeren.
De machineleesbare [release-inventaris](BETA1-RELEASE-INVENTARIS.json) bevat
465 bronverwijzingen met hashes, status en resterende acceptatie.
De CI controleert deze bronhashes en de dekking van alle eisen en releasechecks
met `scripts/verify_beta_release_inventory.py`. Bij een bewuste bronwijziging
hoort een gereviewde inventarisupdate; een ontbrekend onderdeel faalt de controle.

| ID | Onderdeel | Stand | Nog nodig |
| --- | --- | --- | --- |
| I01 | Eigen project, bron/licenties en reproduceerbaar pakket | Geleverde softwarebasis | Volgende exacte release opnieuw bouwen/verifiëren; geen nieuwe upstream-sync. |
| I02 | Weblogin, sessies, CSRF, setup en herstelroutes | Geleverde softwarebasis | Fysieke AP-/uitval-/herstelmatrix blijft apart. |
| I03 | Automatische HTTPS-update, TLS-geheugen en catalogus | Geleverde basis inclusief blijvende diagnose | Checkpoint/EN/NL-diagnose geleverd in alpha27; oorspronkelijke HTTPS-afwijking blijft onverklaard. Geen blinde updaterherhaling. |
| I04 | Actuele/archief-releases automatisch ordenen | Geleverde softwarebasis | Nieuwe publicatie moet bestaande tags/assets behouden. |
| I05 | About, uitloggen rechts en herstart onder Settings | Geleverde softwarebasis | Behouden; bevestiging/herstartguards opnieuw in eindregressie. |
| I06 | Kamerinrichting, identiteiten en apparaatmetadata | Geleverd inclusief versieprojectie | Gemelde Z2M-/converterversie zichtbaar; ontbrekend blijft onbekend. Metadata kwalificeert geen fysieke sensor of kraan. |
| I07 | Weekplanner, korte aanraakblokken en effectief doel | Geleverde softwarebasis | Echte programma-save/ACK bevestigd; bron-/uitval-/reconnectproef nog open. |
| I08 | Actieve sensor/TRV/grenzen wijzigen, bewaren en opnieuw toepassen | Geleverde softwarebasis | Alleen normale expliciete save; geen live apparaatwissel tijdens installatie bewezen. |
| I09 | HA-kaart registreren na opstart, zonder herhaald refreshen | Geleverde softwarebasis | Drie echte koude HA-sessies bewezen; versiegebonden module behouden. |
| I10 | Kamernamen op E32 en juiste statische webroutes | Geleverde softwarebasis | Badkamer live bevestigd; geen nieuwe seriële opname van de logstilte. |
| I11 | Meetstatus, systeemlog en geheugen-/toelatingsdiagnose | Observer/native identiteit en web-/syslogsoftware geleverd | Oude kwalificatie wordt ingetrokken bij bron-/apparaatwissel; productie-meetprofiel, externe collector en lange resourceproef blijven open. |
| I12 | Passieve Classic-decoder en Classic-proefencoder | Decoder en geblokkeerde encoder geleverd | Vast 0x1A-flow/nulformaat gebouwd; beoordeelde bronadressering, fysieke UART-/stopkwalificatie en ontvangstpariteit blijven open. |
| I13 | Ketencontract, SOURCE, journal, configuratie en readback | Geleverde softwarebasis | Logische provisioning/programma-ACK werkt; verse fysieke meet- en actuatorbewijzen ontbreken. |
| I14 | Kraanadapter profiel C, TV02-moduscontrole en bronbench | Modus/identiteit en oorspronkelijke HA-ontvangst/diagnose geleverd; fysieke route onvolledig | Native identiteit en doelcapaciteit vlak vóór dispatch opnieuw gecontroleerd; TV02 auto/vakantie/uit/onbekend zichtbaar en vóór doelactie geweigerd. Verse kraanecho, exclusief eigenaarschap en fysieke werking blijven open; oude bench op SOURCE geblokkeerd. |
| I15 | Kamerregelaar, seizoensbeleid en hydraulische supervisor | Voorbereide code, functie nog onvolledig | Controller-/supervisorkoppeling en HA-diagnose gebouwd; werkelijke producenten, installatieprofiel en fysieke uitvoerketen niet gekwalificeerd. |
| I16 | Groepswaterdoelen, vloer, menger en centrale graph-config | Voorbereide code, functie nog onvolledig | Pure policies/declaraties en begrensde DATA-paden aanwezig; niet gelijk aan actieve groepen/pomp/menger. |
| I17 | Metrics, grafieken, historiegrens en CSV-export | Native velden/grafieken en begrensde Recorder-CSV; maandexport in bètabron | echte Classic-tijdlijn, Recorder-retentie/migratie en grafiekacceptatie open. |
| I18 | Comfortprioriteiten, raam/aanwezigheidscontext en HEAT/OFF | Voorbereide code, functie nog onvolledig | Logische/oudere opt-in paden bestaan; native eenvoudige kamereditor/bronkwalificatie niet compleet. |
| I19 | Thermisch model, optimum-start, uitlopen en curveaanpassing | Voorbereide code, functie nog onvolledig | Code/replay/opslag aanwezig en behouden; geen bewezen leerwinst of actieve vrijgave. Geen nieuwe F9-stage vóór M2. |
| I20 | Meldingen, batterij en modelspecifieke tapwaterpresentatie | Voorbereide code, functie nog onvolledig | Niet generiek als werkende onderhouds-/tapwaterregeling presenteren; modelgerichte acceptatie open. |
| I21 | Keteltest-pagina, ontvangstdiagnose en meetrapport | Geleverd en op E32 gecontroleerd | Volledige release-CI PASS; echte E32-pagina en rapportdownload op 1280/390/320 px gecontroleerd. Tijdens de latere README-opname is verse Classic-ontvangst waargenomen; veldvalidatie blijft open. |
| I22 | Begrensde ketelproefpolicy en originele UART-ontvangsttijd | Policy en RX-integratie geleverd; actieve proef nog onvolledig | 80 unieke native gevallen onder ASan/UBSan PASS; beoordeeld profiel/adressering en fysieke TX-/stopkwalificatie open. |
| I23 | Beveiligde controller-/HTTP-/webbediening van de ketelproef | Geleverd met actieve proef geblokkeerd | Poll-executor aangesloten; default start geblokkeerd. Classic-formaat gekoppeld; beoordeeld profiel/adressering en fysieke UART-kwalificatie open. 80 native en eerder 3 control-browserprofielen PASS. |

Er wordt geen voorbereide supervisor, vloer-/mengerpolicy, CSV-/grafiekroute,
comfortcode of leer-/modelcode weggegooid of opnieuw vanaf nul gebouwd. Deze
onderdelen waren deels ten onrechte als geheel “nog te programmeren” aangeduid.
De ontbrekende verbinding met actuele profielen, productiebronnen, uitvoer en
praktijkbewijs blijft wél zichtbaar open. Bestaande F9/F10-code behouden is geen
nieuwe F9/F10-ontwikkelstage; die start pas na M2.

## 4. Alle 31 producteisen — actuele softwarestand en resterend werk

Geen van deze volledige producteisen wordt op basis van alleen aanwezigheid in
de code afgetekend. De oorspronkelijke acceptatie in PLAN §4/§14 blijft gelden.

| Eis | Functie | Al geprogrammeerd/geleverd | Inventaris | Nog af te maken of te bewijzen |
| --- | --- | --- | --- | --- |
| R01 | Kamerdoel en identiteit | Gebouwd en geleverd; programma-save/ACK op echte E32 bewezen | I06–I08,I13 | Verse fysieke meetketen en volledige ruimteproef. |
| R02 | Externe kamerdoelbediening | Bindings/modelbasis aanwezig; moderne kamerketen onvolledig | I18 | Editor + profiel/identiteit + één override per fysieke bediening + echopreventie. |
| R03 | Gemengde temperatuursensoren | Binding, normalisatie en stale-guards aanwezig; productie-meetprofiel ontbreekt | I06,I11,I13,I14 | Modelspecifieke meetrapportproducent, echte acquisitie en uitval; geen diagnostische device_temp als ambientbewijs. |
| R04 | Meerdere TRVs per kamer/merken | Declaraties en selecties bestaan; huidig native radiatorcontract één TRV per kamer | I06,I08,I14,I16 | Ondersteunde modellen en groepsfeedback; native uitbreiding niet als geleverd claimen. |
| R05 | Open/dicht/proportioneel regelen | Bewaakte profiel-C-adapter en pure regelprofielen aanwezig | I14,I15 | Echte kraan zonder ketel; juiste regelmethode, eigen agenda, echo, afronding en uitval. |
| R06 | Vloerkleppen | Graphdeclaraties, klep-/groepsbasis aanwezig | I16 | Actieve profiel-/wire-/uitvoerketen en eigen fysieke vloeracceptatie. |
| R07 | Onafhankelijke zones/ketelvraag | A/B/samen/uit shadow-regellogica aanwezig | I13,I15 | Gekwalificeerde actuatoren, afgiftepad en echte begrensde ketelvraag. |
| R08 | Classic EMS en behoud Plus | Passieve Classic- en Plusbasis geleverd; alle E32-TX geblokkeerd | I12,I21,I23 | Classic-proefcommandopad + elektrische zendmodus/stopbewijs; Plus later eigen fysieke vrijgave. Modelonafhankelijke velddekking uitbreiden; profiel is nooit een leesfilter.  |
| R09 | Weersafhankelijke aanvoer | Curve-/groep-/begrenzingspolicies en centrale draft aanwezig | I15,I16 | Centrale instellingen verbinden met geselecteerde regelaar, actuele buitenbron en keteluitvoer. |
| R10 | Eigen buitenbron | Bronabstractie/binding/draft en validatie aanwezig | I16 | Normale configuratie/apply + bronkwalificatie, leeftijd, bronwisseling/uitval. |
| R11 | Internetweer via HA | HA-bronroute ontworpen; geen volledig gekwalificeerde praktijkketen | I16 | Gratis HA-weerbron, ouderdom/terugval en internetuitval bewijzen. |
| R12 | Zelflerende kamerregeling | Model-, begrenzings-, resource- en replaycode aanwezig | I19 | Verplicht in definitieve versie: per ruimte leren en gevalideerde modellen/regelparameters blijvend bewaren en gecontroleerd herstellen na herstart. Tijdelijke I-correctie blijft veilig resetbaar. Niet actief vrijgegeven; getoetste meetdata, baseline/comfortvoordeel en modelrollback blijven vereist. |
| R13 | Optimum-start | Opwarmmodel en begrensd advies/replay aanwezig | I19 | Aansluiten na M2/stabiele basis; meerdere vergelijkbare echte starts en comfortbewijs. |
| R14 | Uitlopen/curve leren | Coast- en curve-adaptatiecode/opslag/replay aanwezig | I19 | Afzonderlijke toelating en meetbaar comfort-/curvebewijs; geen leerwinstclaim. |
| R15 | Alle relevante keteldata | 69 native velddefinities geleverd op alpha21/dev27; laatste controle 26 beschikbaar, eerdere boot 27 | I12,I17,I21 | Vereiste betrouwbare velden op eigen E32 ontvangen en vergelijken; unsupported/unreliable expliciet. |
| R16 | Brander/modulatiegrafieken | Native ketelkaarten en drie historiekaarten geleverd; gerapporteerd/afgeleid gescheiden | I17,I21 | Echte CV/DHW-tijdlijn, gaten en herkomst; vlam/pompbit niet onafhankelijk betrouwbaar. |
| R17 | Historie/statistics/CSV | Read-only Recorder-CSV tot 31 dagen met native installatiekeuze/NL/EN in bètabron; eigenaarscontrole na wachttijd | I17 | Werkelijke retentie/omvang, oude deltahistorie/migratie, reset/gaten en mobiele grafiekacceptatie. |
| R18 | Weekprogramma/override | Native weekeditor/UTC-plan/apply geleverd; echte save/ACK bewezen | I07,I13 | Volledige fysieke stale/reconnect/tijd-/overrideketen; huidige 1–2 kamer-/bytebudgetten behouden. |
| R19 | Comfort/eco/away/vakantie/boost | Prioriteits-/expiry-/opt-in comfortcode aanwezig | I18 | Normale huidige producteditor/bronketen en conflicten compleet; geen nieuwe F10-stage vóór M2. |
| R20 | Aanwezigheid/geofencing | Opt-in logische HA-contextbasis aanwezig | I18 | Modelspecifieke contextactualiteit en complete gebruikersroute; P2 blijft later. |
| R21 | Raam- en deurcontacten | Zone-inhibit/prioriteits-/contextcode aanwezig; volledige contactbediening ontbreekt | I18 | Eén of meer contacten per kamer, raam/deur-type, instelbare reactie, native editor/SOURCE, oorspronkelijke actualiteit, uitval en gecontroleerd hervatten; later F10. |
| R22 | Vorst/zomer | Seizoens-/prioriteitspolicy en bounded frost-target aanwezig | I15,I18 | Installatiegebonden fysieke bescherming bij uitval; softwaretarget is geen bewezen vorstbeveiliging. |
| R23 | Anti-pendelen/hydrauliek | Supervisor-, timing-, waterbudget- en minimumlastcode aanwezig | I15,I16,I23 | Actieve profiel/readiness/flow/pomp/naloopketen en fysieke kleinste-last/DHW-proeven. |
| R24 | Uitval HA/MQTT/sensor/E32 | Lease/session/boot/stale/owner-guards aanwezig | I11,I13,I15,I23 | Werkelijke uitvalmatrix, E32-powerloss/ketelstop, actuatorfallback en exclusieve overdracht. |
| R25 | Waarom stoken | Redencodes, kamervraag en dashboard geleverd; diagnose uitgebreid | I10,I11,I15,I17,I21,I23 | Echte opdrachtentijdlijn en gecontroleerde vraag/verzending/ketelreactie apart zichtbaar. |
| R26 | Verbruik/kosten/comfort | Metrics/export/schatlabels gedeeltelijk aanwezig | I17 | Echte gas-/warmtemeter en kostenbron/kalibratie; geen verzonnen besparing of fysiek gasvolume. |
| R27 | Meldingen/onderhoud/batterij | Diagnostics/Repairs en batterijbasis aanwezig; bèta voegt installatiegebonden klokmelding met NL/EN-herstel toe | I11,I20 | Passende meldingen en echte fout-/batterij-/geen-responsscenario’s; geen automatische ketelreset. |
| R28 | Open/lokaal/veilig/herstelbaar | Eigen bron, auth, HTTPS-updates en behoud/rollback deels live bewezen | I01–I04,I08,I23 | Concrete ACL/HTTP/AP-/koude herstel-/uitvalmatrix; oorspronkelijke backupwaiver blijft geldig. |
| R29 | Modern eenvoudig scherm | HA-kamer/week, koude-startfix, E32-dashboard/About/navigatie geleverd | I05–I11,I21,I23 | Ontbrekende centrale/uitvoerfuncties en complete gebruikersacceptatie; echte latentie/geen ongefundeerde speedup. |
| R30 | Schaalbaar/onderhoudbaar | CI/build/source-/budgetguards en 1–2 native kamers aanwezig | I01,I03,I11,I13 | Acht zones zijn productdoel: maximumconfig/heap/NVS/powerloss/72u nog open. |
| R31 | Optionele tapwaterbediening | Modelspecifieke read-only presentatie/bewaking aanwezig | I20 | Alleen echt ondersteunde writefuncties later apart testen; DHW/legionellabeveiliging behouden. |

## 5. De 11 productfasen

| Fase | Software die er al is | Waarom de gehele fase nog open is |
| --- | --- | --- |
| F0 Eigen basis/installatie | Bron-, build-, licentie-, update- en behoudsbewijs geleverd | Volledig woning-/device-/hydrauliekprofiel, fysieke resource/herstelacceptatie |
| F1 Classic uitlezen | Decoder/capabilities/paritybasis geleverd; nieuwe ontvangstdiagnose getest | Vereiste betrouwbare velden op deze E32/keten passief ontvangen en vergelijken |
| F2 Contract/verticale keten | SOURCE/provisioning/journal/plan/readback; programma-ACK live bewezen | Originele meetactualiteit/producer, fysieke bron→statusketen en uitval/capaciteit |
| F3 HA-product/apparaten | Kamer/week/profielsave, identiteit/metadata en koude-startfix geleverd | Getoetste sensor/TRV, externe doelbron, centrale/groepsuitvoering en complete gebruikersroute |
| F4 Regeling/hydrauliek | Zone-/seizoens-/hydraulische policies, water-/mengerbasis aanwezig | Geselecteerde gekwalificeerde profielen, feedback/flow/pomp/DHW/stopuitvoer |
| F5 Metrics/grafieken | Counters/kwaliteitscode, Recordergrens/CSV/presentatie aanwezig | Echte Classic-CV/DHW-tijdlijn, retentie/migratie en grafiekacceptatie |
| F6 Board/bus/stop/uitval | TX-locks, auth-/updateguards en historische stopanalyse | Elektrische interface/timing, zelfstandige stop/powerloss, minimumflow en concrete overdracht |
| F7 Radiatorzones | Shadow- en bewaakte adapterbasis; huidig native bereik 1–2 kamers | Echte kraan zonder ketel, begrensde ketelproef, daarna meer zones/72u |
| F8 Vloer/gemengde afgifte | Declaraties en pure klep-/water-/mengerpolicies aanwezig | Actieve graph/profiel-/uitvoerketen en fysiek beoordeelde verdeler/begrenzing |
| F9 Leren/optimum | Modellen/replay/persistentie/resourcegrenzen aanwezig | Actieve aansluiting en meetbaar voordeel; geen nieuwe stage vóór M2 |
| F10 Comfort/releasekwaliteit | Comfort/context/prioriteit en veel release-/GUIwerk aanwezig | Complete actuele gebruikersroute, gekozen functies, praktijk- en eindreleaseacceptatie |

## 6. Werkpakketten en eerstvolgende uitvoering

| Werkpakket | Stand | Open vervolg |
| --- | --- | --- |
| WP01 Eigen basis | Software en meerdere echte releases geleverd | Resterend fysiek F0-profiel/resource/herstelbewijs |
| WP02 Classic | 69-velddecoder en native HA-projectie geleverd op alpha21/dev27 | Langere CV/DHW-veldvergelijking en ontvangstdekking; actieve opvragen blijven geblokkeerd |
| WP03 Contract/bron | Native SOURCE/config/plan/readback gebouwd en toegepast | Modelspecificieke meetrapportproducent, fysieke actualiteit en uitval |
| WP04 Kamerbediening | Kamer/week/actieve profielsave geleverd | Externe doelbron en centrale/groeps-/deviceketen compleet |
| WP05 Actuator | Profiel-C-adapter voorbereid, geen fysieke native vrijgave | Eerste echte kraan zonder ketel, echo/readiness/fallback |
| WP06 Supervisor | Policies en controllerkoppeling met eigen profiel, afzonderlijke bronleeftijden en lokale foutbevestiging gebouwd | Werkelijke bronproducenten/installatieprofiel, praktijkkwalificatie en keteluitvoer |
| WP07 Metrics | Metrics/Recorder/CSV/grafiekcode aanwezig | Echte dataketen, historie-/grafiekacceptatie |
| WP08 Beveiliging/herstel | Auth/setup/update/ETag/methodguards en live behoudsbewijs | Concrete ACL/AP/koude herstel-/powerlossmatrix vóór passende live inzet |

**Actuele volgorde voor de handmatige bèta:** eerst de oorspronkelijke
ketelmeetketen en de beoordeelde handmatige Classic-proefroute/installatie;
dan één bevroren gezamenlijke kandidaat, de volledige passende releasechecks,
één gecoördineerde uitrol en onafhankelijke nacontrole. De afzonderlijke fysieke
ketelproef volgt pas bij haar eigen toelating en opdracht. Dit volgt de latere
gebruikersopdracht om eerst handmatige ketelproeven mogelijk te maken.

M2-bron-/kraanwerk blijft onderdeel van het productplan en de voorbereide bundel,
maar de fysieke M2-acceptatie is geen voorwaarde voor een uitsluitend handmatige
ketelproef waarbij automatische kamer-/kraanuitvoer geblokkeerd blijft. Een echte
M2-kraanproef gebeurt later eerst zonder ketel. De handmatige bèta krijgt hiermee
geen vrijgave voor automatische zones, onbeheerd verwarmen of zelfleren.

### Releasechecklist — eerste bèta

De onderstaande B01–B14 blijven de gezamenlijke productacceptatie bewaken.
Hun deelresultaten hebben verschillende beslismomenten:

| Beslismoment | Relevante controles | Betekenis voor deze handmatige bèta |
| --- | --- | --- |
| Proefvariant voorbereiden | B07–B09 | De echte zendroute, adres-/timing-/interfacekeuze, oorspronkelijke ketelmetingen en passende installatievoorwaarden moeten voor de betrokken handmatige proef beoordeeld zijn. Dit wordt niet vervangen door M2- of hosttests. |
| Publiceren en installeren | B01–B03, B10–B13 en passende B07–B09-voorwaarden | Alle voorbereide bron behouden, functies correct als actief of beperkt presenteren, exacte kandidaat en distributie controleren, één installatie met back-up en onafhankelijke readback. |
| Fysieke proef aftekenen | B14 en toepasselijke B07–B09-voorwaarden | Echte ontvangst/start/stop/uitval/herstel vastleggen na de afzonderlijk toegelaten proef. Publicatie of installatie tekent dit resultaat niet vooruit af. |
| Automatische kamer-/kraanregeling | B04–B06 en verdere productacceptatie | Oorspronkelijke ruimtebronnen, echte kraan/echo, hydraulische supervisor en uitvalkwalificatie afronden voordat deze functies fysieke uitvoer krijgen. Ze blijven nu open. |

Deze indeling wijzigt geen bestaande aftekening. De volledige productchecklist
mag nog open zijn terwijl een beperktere handmatige proefvariant wordt voorbereid;
haar eigen zend-, meet-, installatie- en releasevoorwaarden blijven verplicht.

- [x] B01 Alle 31 eisen, 11 fasen en 8 werkpakketten opnieuw beoordeeld; oude statusregels uit actuele lijst gehaald.
- [x] B02 Alle bekende voorbereide brononderdelen geïnventariseerd en in bètabasis behouden; geen bron-/testbestand uit hoofdwerkmap ontbreekt.
- [x] B03 Nieuwe ontvangstdiagnose/Keteltest/rapport gebouwd en getest: 18 native, 43 GUI-regressies, 3 echte Chromiumviewports met fixture-HTTP, normale E32-build.
- [ ] B04 Observer-lifecycle/native binding en originele WSDCGQ11LM-producer/HA-ontvangstdiagnose gebouwd/getest; productie-meetprofiel met echte acquisitie-/bronkwalificatie en fysieke validatie afronden. HA43 toont de interne/diagnostische bron direct met uitleg; dit kwalificeert geen meting. Geen trustvinkje of sensorwissel als omweg.
- [ ] B05 TV02-modus/native identiteit/doelcapaciteit, eindige doellevensduur en oorspronkelijke ontvangst/lifecycle geleverd; HA38-opstartherstel en HA43-ontvangerkern geleverd; de kern is niet geselecteerd door de normale fabriek. Pins/producent behouden, huidige diagnose wachtend/stale en ongekwalificeerd. Nieuwe natuurlijke ontvangst, causale zendtransactiekoppeling/doelecho, schema-eigenaarschap en profiel/readiness/fallback nog bewijzen. Fysieke proef eerst zonder ketel.
- [ ] B06 Supervisor aan bron-eigen profiel en afzonderlijk gedateerde veiligheids-/DHW-/water-/kraan-/flowfeiten gekoppeld/getest; toekomstige afgewezen feiten en klokterugloop blijven softwarematig ingetrokken. Gedeelde veiligheidscontrole blokkeert ook ontbrekende/oudere/tegenstrijdige acquisities bij zonepolicy en storingsbevestiging. Werkelijke producenten, installatieprofiel en fysieke kwalificatie blijven open. Geen generieke flowaanname.
- [ ] B07 Eindige proefpolicy en controller/HTTP/webbediening gebouwd/getest; oude/tegenstrijdige ketelrapporten bevestigen geen stop of positieve toestemming. Afronden met beoordeeld profiel en echte zender. Vaste grenzen/stopprioriteit/operatorbinding, geen automatisch hervatten.
- [ ] B08 Poll-executor, Classic-flow/nulformaat en gecontroleerde SDK-zendresultaten aangesloten/getest; monitor en HA-overdracht behouden per veld volgorde/intrekking. Installatieadressering/masker en fysieke UART-zender kwalificeren. Geen oude positieve intentie na deadline/stop/conflict/reset; geen generieke Plusroute.
- [ ] B09 Modelgebonden pre-TX-acceptatiekaart en fabrikantbronnen beoordeeld; concrete TX-interface, timing/polariteit/arbitrage, adres/masker, minimumflow/naloop, onafhankelijke stop/herstel en Tado óf E32 nog fysiek vaststellen.
- [ ] B10 HA43-bronkeuze/kaartcompatibiliteit geleverd en gecontroleerd. Overige bestaande voorbereide gebruikersfuncties en juiste onbekend-/draft-/geblokkeerdstatussen in eindkandidaat controleren; niets stilzwijgend laten verdwijnen.
- [ ] B11 Versies/bron bevriezen, volledige CI/3 boards/native/HA/C++/browser/release-/source-/licentie-/compatibiliteitschecks op die exacte kandidaat.
- [ ] B12 Openbare pakketten/bron/ELF/web/checksums en updatecatalogus onafhankelijk controleren; volledige releasenotes met open punten en herstelroute.
- [ ] B13 Verplichte updatepoort per release: één native GitHub-update via de HA-agent, verse back-up, exacte versie/bron/ELF/web na bevestigde nieuwe boot, instellingenbehoud en afzonderlijke nacontrole; zonder vastgelegd PASS geen volgende reguliere release.
- [ ] B14 Echte passieve ontvangst en afzonderlijke gecontroleerde start/stop/terugmelding aftekenen zodra B09 fysieke aansluiting toelaat; software- en praktijkbewijs apart bewaren.

B04–B09 bevatten concrete onafgemaakte implementatie/kwalificatie; de release
is dus nog niet gereed. B14 is het fysieke proefrapport bij de bèta, geen reden
om een succesvolle softwarebuild als ketelproef aan te merken. Onbeheerd normaal
verwarmen, acht zones, fysieke vloerverwarming en leerwinst zijn latere
productacceptaties; zij blijven in het plan en worden niet stilzwijgend geschrapt.

M1-software (native kamerprogramma/config/apply) is geleverd in het genoemde
bereik. **M2 blijft open:** originele echte meting → HA → E32 → effectieve
status, plus echte TRV zonder ketel en gesimuleerde ketelvraag met TX uit.
Alleen programma-ACK of beschikbaarheid van een entiteit sluit M2 niet.

## 7. Werkafspraken en bijwerken na iedere taak

1. Eén actieve integratietak; bestaande gepubliceerde bron/tags en de per component vastgelegde geïnstalleerde basis intact laten.
2. Per taak: broncommit, relevante testuitkomst, inventaris-ID en resterende acceptatie bijwerken. Geen vinkje zonder bijbehorend bewijs.
3. Alles wat al voorbereid is behouden; onafgemaakte code zichtbaar beperkt houden. Geen nieuwe comfort-/leer-/P2-stage vóór M2.
4. Grotere samenhangende release, geen tags/uploads/flashes per losse reparatie.
5. HA-installaties via bestaande bevoegde agent met back-up/nacontrole; routinewerk niet opnieuw ter goedkeuring voorleggen.
6. Vragen voor later; ontbrekende fysieke feiten blokkeren alleen afhankelijk werk. Geen langlopende watchers of nieuwe externe diensten.
7. Een documentatieherijking start geen ketel-, actuator-, configuratie- of firmwareactie. Backupwaiver voor de oorspronkelijke flash blijft geldig; niet als herstel-PASS markeren of opnieuw vragen.

## 8. Navigatie en bewijs

| Document / bewijs | Doel |
| --- | --- |
| [Volgende release](NEXT-RELEASE.nl.md) | Kort overzicht: geïnstalleerd, klaar voor bundel, open vervolg |
| [Masterplan](PLAN.nl.md) | Alle 31 oorspronkelijke eisen en acceptatievoorwaarden |
| [Release-inventaris](BETA1-RELEASE-INVENTARIS.json) | Alle 23 onderdelen en 465 gecontroleerde bronverwijzingen |
| [Keteltestplan](BETA1-KETELPROEF.nl.md) | Volgorde van toekomstige stop-/zend-/uitvalproeven |
| [Pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) | Nog benodigde installatiegegevens en fysieke voorwaarden |
| [Installatieverslag](INSTALLATIE-HA37-ALPHA28-20261024.nl.md) | Werkelijk geleverde alpha28/dev37, behoudsbewijs en TV02-diagnosebeperking |
| [Werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md) | Ongewijzigd vroeger uitvoeringslog; geen actuele planning |
| `out/ha-session-clock-20261024/FINAL-REVIEW.json` | Laatste softwarecheckpoint en volledige CI |
| `out/boiler-cycling-20261024/SAFE-RESULT.json` | Begrensd passief pendelonderzoek; oorzaak niet bewezen |

Lokale `out/`-dossiers worden niet integraal gepubliceerd wegens mogelijke
privégegevens. Nieuwe voortgang wordt in de actuele tabellen verwerkt; uitgebreide
uitvoeringslogs horen in het bewijsdossier of de historie, niet onder de checklist.

### Achtergrondcontrole wacht op een actieve ketelproef

De hoofdloop geeft de bestaande proefstatus door aan de updateplanner. Een
achtergrondcontrole start niet zolang de controller ontbreekt of de ketelproef
actief is; die controle kan daardoor geen keepalive van de proef blokkeren.
Uitstel verbruikt geen poging en start geen wachtrij. 45 gerichte native gevallen
en de E32-build slagen. Geen ketelproef of firmwareactie voor deze broncontrole.

### Verplicht: flashen en controleren vóór de opvolgende release

[Het updateproces](E32-UPDATE-PROCES.nl.md) en `E32-UPDATE-GATE.json` bewaren de
stand per versie. De tag-publicatiepoort controleert de SHA256-gebonden vorige
acceptatie en de exacte pending-kandidaat. Bronwerk mag doorgaan; een opvolgende
reguliere release wordt geblokkeerd bij ontbrekende/mislukte installatie of
onafhankelijke nacontrole. Alpha36 is pas na de echte installatie en afzonderlijke nacontrole geaccepteerd.

### Releasenotities voor gebruikers

Actuele E32-/HA-notities zijn op GitHub herschreven naar concrete nieuwe functies,
fixes en bijwerkinformatie, in Nederlands en Engels. Publicatietooling vereist
het formaat en bewaart het bij later opruimen. Twaalf tests en publieke
teruglezing slagen; geen softwaredownloads, tags of versies vervangen.
[Werkwijze](RELEASE-NOTES-PROCES.nl.md).

### Configuratieontvangst — live bevinding 26 oktober 2026

De alleen-lezen E32-snapshot heeft `heating_enabled=unknown`, maar een geldige
CV-temperatuur van 55 °C. Laatste Classic0x16: offset1, één payloadbyte.
De warmteproef vereist beide velden en blijft terecht geblokkeerd. Een expliciet
begrensde configuratie-uitleesroute is nu aangesloten naast de private proefzender;
zie de P0-taak in het actuele releaseplan. De kandidaat- en fysieke controles
blijven apart open. Geen EMS-TX of instellingenwijziging
uitgevoerd. Regressies bewaken gedeeltelijke antwoorden, veldspecifieke
veroudering en het onderscheid tussen leesverzoek en echte boilerrespons.
