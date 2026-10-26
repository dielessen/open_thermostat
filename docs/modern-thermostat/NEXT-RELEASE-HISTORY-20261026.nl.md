<!-- Historisch, bevroren op 26 oktober 2026. Actuele status: NEXT-RELEASE.nl.md. -->
# Volgende actieve bèta

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
taalprofielen slagen. Dit is fixture-/ontwikkelbewijs, geen fysieke proef of vrijgave. De fysieke kwalificatie van warmtepad en zender blijft open.

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

Aanvullend gecontroleerd: 24 bestaande updaterbrowsergevallen, 146 scriptcontroles
en drie boardbuilds geslaagd. Alle 34 webbestanden zijn exact in het
ontwikkelimage van 2.792.080 bytes gecontroleerd (OTA-slot 3.670.016 bytes).
Dit is geen nieuwe fysieke flash-/herstelacceptatie.

## Bevestigd opslaan van Bluetoothinstellingen

De pagina vergelijkt opgeslagen adressen, namen, profielen, versleuteling en
sleutel-aanwezigheid met het concept voordat zij ‘opgeslagen’ meldt. De volgorde
van de lijst mag verschillen; inhoud en aantal moeten overeenkomen. Een
mislukte uitlezing, afwijkende inhoud of onzekere POST-uitkomst bewaart het
concept, wist ingetypte sleutels en blokkeert herhalen tot expliciet herladen.
Statuspolling bevestigt geen onbewezen schrijfresultaat. Een uitgestelde
request start niet na het verlaten van de pagina. Dit blijft bronvoorbereiding;
geen installatie, echte Bluetoothkoppeling of ketel-/kraanopdracht uitgevoerd.

Verificatie: foutieve succesmelding eerst gereproduceerd; 12 uitgebreide
browsergevallen (NL/EN, 320/1280 px, drie profielen), 146 scriptcontroles en
alle drie boardbuilds slagen. Alle 34 webbestanden zitten exact in het
ontwikkelimage van 2.791.744 bytes (OTA-slot 3.670.016 bytes). De browserproef
controleert ook afwijkende readback, verbindingsverlies, behouden concepten,
geen automatische herhaling en geen uitgestelde POST na paginaverlating.

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

Controle: 929 native tests, 21 ASAN/UBSAN-gevallen, 12 browsergevallen
(NL/EN, mobiel/desktop, drie profielen) en drie boardbuilds geslaagd.
Alle 34 webbestanden zijn exact in het ontwikkelimage gecontroleerd;
2.790.256 bytes passen in beide OTA-slots van 3.670.016 bytes.

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

Drie definitieve boardbuilds en 146 scriptcontroles slagen. Het ontwikkelimage
bevat alle 34 webbestanden exact en past in beide OTA-slots
(2.788.992 van 3.670.016 bytes). Dit is nog geen nieuwe pakketfreeze of live update.

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

## Bluetoothapparaten kiezen — voorbereid voor de volgende release

Apparaten in de buurt tonen hun uitgezonden naam, adres en signaalsterkte.
**Dit apparaat toevoegen** vult naam en adres in. Al toegevoegde adressen zijn
geblokkeerd tegen dubbel toevoegen. Controleer het profiel, voer indien nodig
de bindkey in, sla op en herstart via Settings. Refresh bewaart concepten en
focus. Apparaten zonder naam tonen hun adres. Geen kraanopdrachten of installatie.

Ontwikkelcontroles: 922 native tests, 14 ASAN/UBSAN-tests, 146 scriptcontroles,
12 Bluetoothbrowsergevallen (NL/EN, mobiel/desktop, drie profielen) en drie
boardbuilds geslaagd. Alle 34 webbestanden zijn exact in het ontwikkelimage
gecontroleerd (2.788.976 van 3.670.016 bytes). De HA-native suites op Core
2026.10.4/.3/.2 slagen elk met 2332 tests en twee verwachte broker-fixtureskips.
Dit is geen volledige pakket- of fysieke acceptatie; actieve bèta blijft NOT_READY.

## Aanvullende stabiliteitsfixes voor dezelfde bundel

- Onvolledige EMS-velden worden ook bij directe payloadtoegang veilig geweigerd.
  Een eerdere heap-buffer-overflow is met AddressSanitizer gereproduceerd;
  tests bewaken alle byteposities, veldbreedtes en verschoven fragmenten.
- Negatieve 8-/16-/24-bits waarden worden expliciet volgens hun protocolbreedte
  omgezet. Debug-hex gebruikt vaste opslag en correcte lengteformattering.
- Apparateninventaris en werkelijke versielogging gebruiken één decoder voor
  gewone en alternatieve product-/versietuples. Deelberichten worden niet
  samengevoegd tot een verzonnen identiteit.
- HA weigert ongeldige kamertemperaturen buiten de bestaande conservatieve
  temperatuurenvelop, inclusief foutcodes. Zes regressiegevallen faalden vóór
  herstel; de gerichte suite slaagt met 40 gevallen. Geldige nul blijft nul.

[Begrijpelijke conceptreleasenotities in NL/EN](BETA-NEXT-RELEASE-NOTES.nl-en.md).
Alle wijzigingen blijven bronvoorbereiding; niets is tussentijds geïnstalleerd.

## Laatste bronverbeteringen

- EMS-referentie gecomprimeerd: circa 323 kB minder download- en firmwaredata;
  alle entiteiten en velddefinities blijven behouden. Ontvangen meetwaarden
  blijven zichtbaar wanneer het referentiebestand niet geladen kan worden.
- Passieve inventaris van 8 naar 64 telegramtypen per apparaat verruimd, met vaste
  geheugenlimiet en expliciete overschrijdingstellers.
- Geïnstalleerde beta.1/HA0.4.0b1 en de normale GitHub-updatepoort nu met het
  oorspronkelijke onafhankelijke bewijs vastgelegd. De volgende kandidaat
  blijft een afzonderlijke bronfreeze en uitrol vereisen.

## EMS-apparaten, entiteiten en logging — voorbereid voor de volgende release

Apparaatnamen worden uit ontvangen product-ID’s afgeleid. `0x17` krijgt de rol
thermostaat; alleen een adres is geen bewijs voor een exact model. De normale
apparatenpagina heeft nu een doorzoekbare referentie met alle 6.042
EMS-ESP-entiteitsvermeldingen, waaronder 3.250 schrijfbare vermeldingen,
verdeeld over 105 productgroepen. De telegrambibliotheek bevat 274 benoemde
ID’s en alle 1.853 velddefinities. Schrijfbaarheid staat als referentiekenmerk
in de interface, zonder opdrachten uit te voeren of stuurrechten te wijzigen.
Logregels tonen apparaatrollen, B/R/W-richting en telegramnaam naast de ruwe
bytes. De standaardweergave en nieuwe syslogconfiguraties kiezen ESP.

**Volledige functionele EMS-ESP-dekking blijft open:** de geïmporteerde
referentiedata zijn geen vervanging voor nieuwe decoders, HA-meetketens,
modelafhankelijke schrijfencoders en fysieke kwalificatie.
[Concrete dekking, bronnen en resterende werkzaamheden](EMS-DEKKING.nl.md).
Deze wijziging is nog niet geïnstalleerd.

---

## Profielkeuze: merk vóór model — volgende wijziging

De ketelkeuze is opgeschoond op basis van de bestaande, vastgelegde
[EMS-ESP-apparaatbibliotheek](https://github.com/emsesp/EMS-ESP32/blob/8f7049b47a1641cc22c91c63cfb27c1278b282ed/src/core/device_library.h)
en [keteldocumentatie](https://emsesp.org/Boilers).
De keuzelijst groepeert alfabetisch per merk, met steeds `Merk Model` als naam.
Gemengde productgroepen zijn opgesplitst; dubbele zichtbare namen zijn verwijderd.
Er zijn 72 zichtbare model-/familiekeuzes plus ‘geen ketel’. De 60 bestaande
opslag-ID’s blijven geldig; oudere groepskeuzes worden alleen getoond wanneer ze
al opgeslagen zijn. Er is geen automatische wijziging van de apparaatinstelling.
Familienamen en wildcards uit EMS-ESP blijven families, geen verzonnen exacte typen.
Dit betreft de presentatiekeuze; het levert geen nieuwe gekwalificeerde keteldriver.
Bestaande geverifieerde afbeeldingen blijven extern geladen met bronvermelding.

Controle: catalogusgenerator, native opslag/readback en browsertest op vier
schermformaten, inclusief bewaren/herladen, oude ID’s en foutpaden.
Deze wijziging is nog niet op de E32 geïnstalleerd.

---

# Historische voorbereiding van de eerste softwarebèta

## Eén grote bèta — doorwerken zonder tussenreleases

De uitvoeringsopdracht is uitgebreid: alle uitvoerbare roadmaponderdelen in één
bètakandidaat verwerken. Geen losse alpha37-release, tussentijdse E32-flash of
HA-installatie. De volgorde en open implementatiepunten staan in
[BETA1-UITVOERING.nl.md](BETA1-UITVOERING.nl.md). B04–B14 blijven inhoudelijk
leidend; ontbrekende fysieke feiten worden niet met softwarevinkjes afgetekend.

## Afgerond: HA-opstart op Core 2026.10.4

Live hersteld in de gezamenlijke installatie van HA0.4.0b1/E32beta.1.
De volgende bronkandidaat vereist opnieuw passende controles.

## In bewerking voor dezelfde bèta

De volledige E32-download bewaart voortaan ook de exacte ELF-symbolen en linkerkaart,
met een onafhankelijke koppeling aan de firmwarehash en bronversie. Dit maakt latere
foutanalyse mogelijk zonder afhankelijkheid van tijdelijke CI-downloads. De opstartlog
toont de ELF-hash als leesbare hextekst. Deze bestanden zijn voor diagnose; OTA blijft
het gewone firmwarebestand gebruiken.

De bundel bevat nu ook dag-/week-/maandexport tot 31 dagen via de gewone HA-actie,
met installatiekeuze en NL/EN-uitleg. Daarnaast zijn meetintrekking bij falende
schermcallbacks, profielvervanging en ongeldige lokale klok hersteld. De klokfout
geeft een HA Repairs-melding en maakt raam-/aanwezigheidssignalen onbekend.
Ongeldige kamerwaarden en te grote getallen verstoren de statusverwerking niet.
Zie [het werkbord](WORKBOARD.nl.md) en [CSV-gebruik](HISTORIE-EXPORT.nl.md).
Deze onderdelen zijn geleverd in bron5e3ed30/beta.1; nieuwere wijzigingen staan hierboven.

Ook de normale E32-pagina voor Bluetoothapparaten en lokale SBHT-103C-/
MJWSD05MMC-/SBTR-001AEU-diagnoseontvangst is aangesloten, met echte AES-CCM, verborgen bindkeys,
begrensde privéopslag/wachtrij en ontvangstleeftijden. De sleutels staan buiten
het netwerkdocument, zodat ook de oudere netwerkreader ze na rollback niet kan
terugsturen. Dit levert nog geen
gekwalificeerde regelbron; fysieke apparaatacceptatie, TRV-bediening en zelfstandig regelen blijven open.
[Uitvoering en grenzen](BLUETOOTH-APPARATEN.nl.md).

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


Bijgewerkt: 25 oktober 2026. Dit is het korte releaseoverzicht.
Het [werkbord](WORKBOARD.nl.md) bevat de enige actuele checklist en prioriteiten;
het [masterplan](PLAN.nl.md) bewaart alle 31 producteisen en acceptatievoorwaarden.

## Alpha36 — via GitHub geïnstalleerd en onafhankelijk geaccepteerd

Navigatie,60 modelkeuzes, publieke modelbeelden en ESP-/EMS-logging draaien nu
op de E32. Eén native GitHub-installatiecommando, normale automatische herstart,
alle 36 installatiecontroles en 45 afzonderlijke nacontroles geslaagd. Exacte bron/
ELF/web, 31 geserveerde UI-bestanden, alle 86 HA48-bestanden, SOURCE5, instellingen,
programma's en koppelingen gecontroleerd. Back-up van tien payloads nagelezen.

De normale GitHub-updatepoort accepteert alpha36. Voor iedere opvolgende release
zijn opnieuw installatie en afzonderlijke nacontrole verplicht; CI-publicatie
controleert het versiegebonden bewijs. De oude multipart-watchdog is hiermee niet
oorzakelijk verklaard. Actieve bèta/fysieke ketel- en kraanproeven blijven open.
[Installatie en bewijs](INSTALLATIE-E32-ALPHA36-20261025.nl.md).

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

## Meegeleverd in alpha36 — navigatie en modelcatalogus

About staat na Settings. De modellenkeuze bevat nu 60 selecties met alle 31
EMS-ESP-productgroepen en aanvullende officiële ketelvermeldingen. Afbeeldingen
staan publiek buiten de ESP; de compacte catalogus en opgeslagen keuze werken
zonder internet. Nieuwe vermeldingen activeren geen driver of zendprofiel.
Ontbrekende modelafbeeldingen blijven leeg. [Hosting en profielontwerp](KETELCATALOGUS.nl.md).
Vier oorspronkelijke modelafbeeldingen zijn gekoppeld met bronlink, voor vijf
selecties. Ecomline Classic HRC22H heeft nog geen gecontroleerde originele foto;
de generieke tekening wordt niet meer gebruikt. Onzekere groepen blijven zonder beeld.
Deze wijzigingen zijn op alpha36 geïnstalleerd; 31 geserveerde UI-bestanden onafhankelijk exact gecontroleerd.

## Meegeleverd in alpha36 — ESP-/EMS-logging

Systeemlog krijgt ESP / EMS / beide als weergavefilter. Beide bronnen kunnen
onafhankelijk naar dezelfde syslogserver; nieuwe bronvinkjes worden opgeslagen
met teruglezing. Ontvangen EMS-frames worden begrensd in de decode-lus gelogd,
zonder UART-callback of busaansturing te veranderen. Oudere logginginstellingen
blijven leesbaar. [Gebruik, tests en grenzen](LOGGING.nl.md).
Op alpha36 geïnstalleerd; externe collector/hardwarebelasting blijven open.

## Meegeleverd in HA48 / alpha35 — bewijs en beperkingen

De native afsluitroute ruimt de overige eigen handles, worker en wachtrij ook
op als één cleanupcallback een gewone exception geeft. Drie gevallen falen
vóór correctie; 162 gerichte gevallen per ondersteunde Core slagen erna.
Dit is in HA48 geïnstalleerd en geen verklaring voor een eerder productieincident. [Bewijs en beperking](HA-OPSTART-LIFECYCLE-20261025.nl.md).

Ook de kamer-/HVAC-testopstelling gebruikt nu één klokdomein voor ontvangst
en meetleeftijd. Vier epochproeven toetsen het volledige bestaande servicepad;
50 gerichte gevallen per ondersteunde Core slagen. Regeltijden en veiligheids-
asserties blijven behouden; de oudere CI-oorzaak blijft afzonderlijk onbekend.
[Uitwerking en bewijs](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

De gecombineerde voorbereiding met de cleanupfix is volledig lokaal getoetst:
2.356 gevallen per Core 2026.10.2 en2026.10.3, nul fouten of skips; zeven
pakketunittests en twee onafhankelijke offline bronreviews slagen. Deze bronstap is nu meegeleverd in de gezamenlijke release. Alle fysieke poorten blijven open.

X01 heeft nu een eerste pure Shelly SBHT-103C-decoderbasis:798native tests,
16aparte sanitizergevallen en ESP32-syntaxcontrole slagen. Deze parser wordt
nog niet door de BLE-reader geselecteerd. Settings/onboarding, sleutels,
bron-/replaykwalificatie en echte apparaatproeven blijven open. De actuele
bronvoorbereiding bewaart23onderdelen en31eisen, nu met289bronverwijzingen.
[Uitwerking en grenzen](BLUETOOTH-APPARATEN.nl.md).

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

## Geleverd in alpha34-bron — gerichte updaterinstrumentatie

De alpha34-bron onderscheidt vier opgeslagen stappen vóór checksum,
native imagevalidatie, onafhankelijk flash-readback en bootselectie. Oude
checkpoints blijven leesbaar; de UI toont de betekenis in Nederlands/Engels.
782 native gevallen, 40 sanitizergevallen en 24 updaterbrowsergevallen slagen;
E32-compile geslaagd. De updaterstap behield 23 onderdelen en 31 eisen; met de
HA-opstartcorrectie hieronder bevat de gepubliceerde HA47-inventaris 286 bronverwijzingen.
Dit is gepubliceerd in alpha34,
zonder firmware-installatie door deze opdracht; de oudere watchdog blijft onverklaard.
[Uitwerking en bewijs](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).

## Geleverd in HA47 — opstart en afsluiten

De native opstart behoudt nu één eigenaar over programma-, Store- en MQTT-
leesgrenzen. Afsluiten of annuleren kan de oude verbinding niet later alsnog
laten starten; een dubbele start vervangt de eerste eigenaar niet. De optionele
temperatuurdiagnose heeft één begrensd aanmeldbudget en ruimt late handles op.
Alle tien nieuwe gevallen falen op de oude code; 139 gerichte en 2.349 volledige
HA-gevallen per ondersteunde Core slagen. Dit bronwerk is geleverd in HA47,
samen met de gepubliceerde alpha34-updatercheckpoints.
[Uitwerking en bewijs](HA-OPSTART-LIFECYCLE-20261025.nl.md).

De afzonderlijke alleen-lezen controle vóór de uitrol van **05:46:49 UTC** zag bij de toenmalige
TV02-owner één callback/enqueue/workeracceptatie, zonder getelde drops of fouten.
Het oorspronkelijke lokale-temperatuurbericht is inmiddels stale; dit bewijst
ontvangst, geen kraan-ACK, positie of regelkwalificatie. De gekozen interne
kamerbron blijft onbruikbaar en heeft nul oorspronkelijke topics. SOURCE5 en
instellingen behouden; nul productie-/deviceacties. Geen nieuwe E32-/bestandsaudit.
Na de HA47-herstart is de RAM-eigenaar nieuw: bij de nacontrole van 06:47:49 UTC
zijn de tellers nul en TV02 `waiting`. Oude ontvangst wordt niet als verse meting
hergebruikt. De bewaarinventaris behoudt alle 23 onderdelen met 286 bronverwijzingen.

## Historische grotere release HA45 / E32 alpha32

HA45 is geïnstalleerd op bron `3f12d8b`, met een verse HA44-back-up van 95 payloads
en één normale Core-herstart. De afzonderlijke nacontrole van 03:09 UTC slaagt:
38 controles, alle 85 livebestanden exact publiek pakket/Git, instellingen en
kaarten behouden. E32 blijft alpha31 op bron `659879e`; alpha32 is gepubliceerd,
zonder firmwareactie door deze opdracht. Alle 23 onderdelen en 279 bronverwijzingen
blijven opgenomen. [Installatieverslag](INSTALLATIE-HA45-ALPHA32-20261025.nl.md).

767 native kerngevallen, 4 lokale socketadaptergevallen en 2.333 HA-gevallen per
ondersteunde Core slagen; alle definitieve CI- en pakketreviews zijn geslaagd.
Actieve product- en fysieke kwalificatie blijven open.

## Gezamenlijke release HA44 / E32 alpha31

Beide onveranderlijke tags en alle negen openbare downloads zijn gepubliceerd op
bron `659879e`. Bron-/pakket-/tagreview en alle drie CI-runs geslaagd: 728 native
firmwaretests en 2.323 HA-gevallen per Core 2026.10.2/2026.10.3. Alle 23 voorbereide
onderdelen met 267 bronverwijzingen blijven opgenomen.

**HA44 is geïnstalleerd en onafhankelijk gecontroleerd:** 85 livebestanden exact
publieke ZIP/Git, verse HA43-back-up van 94 bestanden, één normale Core-herstart.
Instellingen, programma's, bindingen, registry en frontend behouden. Nacontrole
25 oktober 00:32:01 UTC: alle 20 checks geslaagd. De actuele SOURCE-revisie5 is
behouden; de voorafgaande horizonverschuiving wijzigde geen programma of binding.
[Installatieverslag](INSTALLATIE-HA44-ALPHA31-20261025.nl.md).

De native HA-worker verwerkt nu grantaanvragen en kraanopdrachten, met lokale
sessie-/config-/bindingcontrole, oorspronkelijke deadlines, eenmalige grants en
onmiddellijke intrekking bij scopeverlies. Optioneel verkeer kan de shadow-sessie
niet via een volle queue resetten. De echte C++-bytes worden via deze worker en
de bewaakte serviceadapter beproefd; serviceacceptatie blijft geen fysieke ACK.
[Uitwerking](M2-NATIVE-KRAANROUTE-20261025.nl.md).

**Vers waargenomen: E32 alpha31.** Alleen-lezen controle 25 oktober 01:50 UTC
bevestigt bron 659879e/ELF045dfe53 en normale beschikbaarheid. De uitvoerder en
methode van die gewijzigde installatie zijn onbekend; deze opdracht heeft geen
E32-upload gestart. De oudere alpha28-momentopname is historisch. De eerdere
watchdogoorzaak/herstelroute blijven open; geen nieuwe flashpoging.
[Waarneming en bewijs](WAARNEMING-E32-ALPHA31-20261025.nl.md).

## Geleverd in HA45 / E32 alpha32

De oorspronkelijke firmware-aanvraag en het grantantwoord worden nu per kanaal
gekoppeld, inclusief aanvraagvolgnummer, oorspronkelijke deadline en gedeeld
klokwatermerk. De optionele aansluiting gebruikt dezelfde MQTT-client/loop;
de productfabriek blijft gesloten. [Uitwerking en grenzen](M2-AANVRAAG-EN-KANAAL-20261025.nl.md).
De bundel omvat ook beschermd kanaalbeheer en deadlinegebonden nonblocking writes
op dezelfde socket, plus een correct gefaseerde ACK-test. Regressie, definitieve
bronreview en exacte CI/publicatie zijn geslaagd; HA45 is geïnstalleerd.

## Volgende stap naar actieve bèta

De product-kraanfabriek blijft gesloten. Normale firmware-MQTT-grant-/zendbedrading,
actuele gekwalificeerde SOURCE, geschikte kamerbron, causale oorspronkelijke
kraanecho en fysieke stop-/uitvalproeven blijven open. E32-herstelbaarheid moet
ook worden vastgesteld. De volledige actieve bèta is daarom nog niet vrijgegeven.
[Voorbereide firmwareketen](M2-SOURCE-TRANSPORT-20261025.nl.md).

## Eerdere gezamenlijke bundel dev39 / alpha30

De gezamenlijke bundel bevat alle bronwijzigingen sinds dev38/alpha29:
transactionele handmatige app-upload, intrekking van verworpen veiligheidsfeiten,
veldgebonden ontvangstvolgorde van ketelrapporten en blijvende HA-cache-intrekking.
689 firmwaretests en 2195 HA-testgevallen per ondersteunde Core-versie zijn lokaal
geslaagd. Alle drie definitieve CI-runs zijn geslaagd, beide tags gepubliceerd
en alle negen openbare downloads vergeleken. HA39 is geïnstalleerd en de afzonderlijke
nacontrole van 18:54 UTC is geslaagd. De oude alpha28-uploader blijft een
herstelpunt: nieuwe broncode bewijst geen reparatie van de eerdere watchdogreset.

## Geleverd in HA43 — bronkeuze en voorbereide ontvanger

B04/B05/B10: gesloten HA-ontvangertoelating met oorspronkelijke vijfseconden-grants,
exacte scope en zonder replay, plus directe EN/NL-bronkeuze-uitleg in de kamereditor.
De ontvangstkern is niet door de normale fabriek geselecteerd; afzender/leasebinding,
causale echo en fysieke kwalificatie blijven open. Frontend v41 behoudt v38/v35.
[Details en bewijs](M2-ONTVANGER-EN-BRONKEUZE-20261024.nl.md).

## Geleverde HA40-release

B05/M2: de Profile-C-kraanadapter trekt zijn eigenaar blijvend in bij
klokterugloop of ongeldige tijd, vóór en na serviceafhandeling. 14 nieuwe
regressies; alle 141 gerichte tests en 2209 volledige gevallen op beide
Core-versies geslaagd. Gepubliceerd en geïnstalleerd op bron `a01bc68`;
afzonderlijke nacontrole van 19:28 UTC geslaagd. Geen fysieke vrijgave. De normale FW→HA-route en echte
doelterugmelding blijven open. [Uitwerking](M2-KRAAN-KLOK-20261024.nl.md).

## 1. Wat draait er nu?

| Onderdeel | Geïnstalleerd | Stand |
| --- | --- | --- |
| E32 | `v0.1.0-e32v2-alpha.31`, bron `659879e52b3e0e517e8dea1e28edb2d189c38c77`; dezelfde boot bevestigd 06:47 UTC | Passief EMS uitlezen; TX, forwarding en fysieke uitvoer geblokkeerd |
| Home Assistant | `0.4.0.dev47`, bron `6f21f34ff773645645c98dc2602337c648e18ffe` | Geladen op Core 2026.10.3; frontend dev41/v41 met v38/v35-aliases |
| Actieve regelaar | Tado | Geen automatische ketel- of kraansturing door OpenThermostat |

Bron/pakket/ELF/web, alle 86 HA-bestanden en behoud van instellingen, programma's
en identiteiten zijn gecontroleerd. Zie [installatieverslag](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).
De uitgebreide geleverde bundel staat in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

### Historische HA43-installatie — 24 oktober, nacontrole 21:17:50 UTC

HA dev43 geladen; 84 bestanden exact publieke ZIP/Git, verse HA40-back-up van
93 bestanden en één normale Core-herstart. Alle 38 afzonderlijke nacontroles
slagen. Instellingen, programma’s, SOURCE, registry en bronpins behouden; alleen
twee eigen kamerkaarten gaan van v38 naar v41. E32 alpha28 niet gewijzigd;
nul uploads/herstarts, TX/polls/testframes nul. 2281 testgevallen per Core,
zeven softwarepoorten en definitieve tag-CI geslaagd; vier downloads bytegelijk.
[Installatieverslag HA43](INSTALLATIE-HA43-20261024.nl.md).

### Historische HA39-installatie — nacontrole 18:54 UTC

HA dev39 geladen; 83 bestanden exact, verse gecontroleerde back-up van 93 bestanden,
één normale Core-herstart. E32 alpha28 en alle instellingen/koppelingen behouden;
geen E32-upload of herstart. Uitgangen geblokkeerd, TX/polls/testframes nul.
Afzonderlijke nacontrole geslaagd; zie [installatieverslag](INSTALLATIE-HA39-ALPHA30-20261024.nl.md).

### Historische installatiecontrole — 24 oktober, na 17:07 UTC

HA dev38 exact geladen; E32 blijft alpha28 na één mislukte alpha29-upload.
Resetcode 6 bevestigt een task-watchdogreset, maar taak en oorzaak zijn onbekend.
Geen herhaling uitgevoerd. Instellingen en verse 93-bestandenback-up zijn
onafhankelijk gecontroleerd; alle uitgangen blijven geblokkeerd.
[Actuele installatie-uitkomst](INSTALLATIE-HA38-ALPHA29-20261024.nl.md).
Eerdere alpha28/dev37-installatie hieronder blijft historische basis.

## 2. Geleverde inhoud van alpha28 / HA dev37

| Onderdeel | Wat verandert er? |
| --- | --- |
| Settings → EMS-apparaten | Per ontvangen afzender identiteit indien bekend, telegramtypen en entiteiten met waarde/kwaliteit/ouderdom; EN/NL, zoekfilter en behouden openklapstatus |
| E32-klokbewaking | Verlopen grant/lease kan bij teruggaande klok niet herleven; ook diagnostische lezingen gecontroleerd |
| HA-klokbewaking | Ongeldige/teruggaande monotone klok trekt sessie, wachtende opdrachten en bewijzen in; oude rechten herstellen niet door reconnect |
| Herhalen na vertraagde verzending | Deadline/lease en SOURCE opnieuw controleren na wachten; geen herhaling van ingetrokken of vervangen opdrachten, geen heartbeat op verlopen sessie |
| HA-opstart en annulering | Vroege fouten ruimen eigen resources op; een oude setup verwijdert geen nieuwe eigenaar |
| Kamereditor | Te grote numerieke kraanmetadata wordt afgewezen zonder editorcrash |
| Webnavigatie | Vertraagde pagina-antwoorden kunnen een nieuwere pagina niet overschrijven of oude scripts uitvoeren |
| EMS-tabel | Bestaande rijen hergebruikt, adressen correct geordend, waarden gecontroleerd en getallen volgens EN/NL weergegeven |
| Keteltestplan | Concrete volgorde en criteria voor toekomstige stop-, zend-, naloop- en uitvalproeven |

**Gepubliceerd, geïnstalleerd en gecontroleerd.** Bron `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f`,
2167 HA-tests op beide echte Core-versies zonder fout/skip, alle zeven softwarejobs
geslaagd. Openbare pakketten, live HA-bestanden en echte E32-boot apart gecontroleerd.
Bewijs: `out/combined-dev37-alpha28-20261024/FINAL-REVIEW.json`.

Alle 23 voorbereide onderdelen met 267 actuele bronverwijzingen blijven in de
[release-inventaris](BETA1-RELEASE-INVENTARIS.json). Bestaande regeling,
supervisor, groepen/vloer/menger, historie/CSV, comfort en leren blijven behouden.
Hun ontbrekende verbindingen en fysieke acceptatie staan op het werkbord.

## 3. Wat doen we hierna?

| Volgorde | Werk | Gereed wanneer |
| --- | --- | --- |
| P0 vóór actieve M2 | Eerdere incidentele CI-kamerassertie causaal verklaren | Definitieve regressies en herhaalproeven slagen; oorspronkelijke afwijking nog niet causaal verklaard |
| P0 vóór fysieke proef | Gemeld pendelen verklaren en passieve nulmeting beoordelen | Oorzaak of concrete vervolgmeting vastgelegd; geschikte stabiele proefbeginsituatie |
| P0, B05 ontvangst | Softwareherstel voor late MQTT-discovery is geleverd in HA38 en behouden in HA43; oorspronkelijke ontvangst kwalificeren | Echte nieuwe ontvangst via dezelfde bron/pins/producent; geen geforceerde rapportage of cachekwalificatie |
| P0 software, B04 | Echte geschikte kamerbron met oorspronkelijk rapport en meetprofiel | Werkelijke acquisitie/actualiteit en uitval bewezen; geen diagnostische device_temperature als ruimtemeting |
| P0 software, B05/M2 | Normale FW→HA-kraanroute met HA-ontvangergrant en bestaande adapter afronden | Native zendtransactie aan oorspronkelijke kraanecho gekoppeld; profiel, modus, eigenaarschap en fallback getoetst |
| P0 software, B06 | Werkelijke veiligheids-/DHW-/water-/kraan-/flowfeiten aansluiten | Iedere bron met eigen geldigheid en beoordeeld installatieprofiel; geen generieke flowaanname |
| P1, B07–B09 | Classic-TX-/stopketen afronden en installatievoorwaarden beoordelen | Adres/masker, interface/polariteit/arbitrage, afgifte/naloop, onafhankelijke stop en één actieve schrijver vastgesteld |
| Release, B10–B13 | Eén gezamenlijke kandidaat bevriezen, verifiëren, publiceren en installeren | Exacte bron/pakketten, volledige CI, checksums, herstelroute, backup en nacontrole |
| Fysiek, B14 | Afzonderlijk toegelaten stop-/zend-/uitvalproeven uitvoeren | Gemeten reactie en stop binnen beoordeelde grenzen; gecontroleerd herstel vastgelegd |

Onafhankelijk softwarewerk kan doorgaan terwijl fysieke gegevens ontbreken.
Een begrensde handmatige ketelproef en automatische kamerregeling hebben
verschillende voorwaarden: die laatste vereist ook de volledige M2-kamer-/kraanketen.

## 4. Pendelen: wat weten we?

De passieve controle van 24 oktober 16:26 CEST bevestigt **0 EMS-verzendingen,
0 polls en alle uitgangen geblokkeerd**. Geen UART-fouten of ongeldige telegrammen;
geen bewijs van OpenThermostat-aansturing. De beschikbare geschiedenis toont
warmwatergerelateerde vermogensperiodes van ongeveer 3–4 minuten met 10–12 minuten
tussen starts, ook nadat Tado voor de kamer idle meldde.

**Oorzaak nog onbekend.** Warmwatergebruik/bijwarmen is de onderzoeksrichting.
Telemetrie bewijst geen exact aantal fysieke ontstekingen en sluit indirecte
elektrische invloed niet volledig uit. Geen instellingen gewijzigd of zendproef
gedaan. Bewijs: `out/boiler-cycling-20261024/SAFE-RESULT.json`.

De latere controle van 17:00–17:01 CEST toont in de voorafgaande 30 minuten alleen
code 0H/0% gemeld vermogen en afkoeling, zonder nieuwe positieve vermogensperiode.
De eerdere oorzaak blijft onbekend; dit is geen bewijs van een reparatie.

## 5. Wanneer is de actieve bèta gereed?

Er is nog geen onderbouwde kalenderdatum. De softwarekandidaat kan met
geblokkeerde uitgangen worden geleverd; actieve proeven volgen pas na de
bijbehorende installatie- en stopvoorwaarden. Het [testplan](BETA1-KETELPROEF.nl.md)
beschrijft nulmeting → fysieke proefkaart → stop in rust → één begrensde vraag →
stop/naloop → afzonderlijke uitval → terugkeer naar Tado.

De oudere native HTTPS-updaterfout blijft onverklaard; checkpointdiagnose is
geleverd, maar bewijst geen reparatie. Geen blinde herhaling van de mislukte route.

## 6. Blijvend in het productplan

Alle 31 eisen blijven gelden, inclusief per ruimte leren en blijvend bewaarde,
gevalideerde parameters. Nieuwe F9/F10-ontwikkeling volgt na M2. Acht zones,
vloer/menger, grafiek-/historieacceptatie, comfort en onbeheerd verwarmingsbedrijf
houden hun eigen acceptatievoorwaarden. Niets wordt op basis van alleen aanwezige
code of een geslaagde build als werkende fysieke functie afgevinkt.

## 7. Historisch X01-ontwerp — actuele uitvoering bovenaan

[Uitbreiding X01](SHELLY-BLU-TRV-STANDALONE.nl.md) voegt Shelly BLU TRV via
Bluetooth en een expliciete lokale E32-modus toe aan het ontwikkelplan. De
bestaande HA-functies blijven behouden. Haalbaarheid onderzocht met officiële
GATT-documentatie; nog geen driver, koppeling of lokale regelvrijgave geleverd.
Eerst één kraan uitlezen en zonder ketel kwalificeren, daarna lokale
programmering/eigendom/opslag/tijd en de bestaande stop-/uitvalvoorwaarden verbinden.
Deze oorspronkelijke ontwerpuitbreiding wijzigde destijds HA38/E32 alpha28 niet
en was geen nieuwe release. De actuele basis en nieuwe software staan bovenaan.

X01 omvat ook de Shelly BLU H&T Display ZB (SBHT-103C) en een tweetalige
[Bluetooth-apparaatpagina onder Settings](BLUETOOTH-APPARATEN.nl.md): vinden,
beveiligd toevoegen waar nodig, kamertoewijzing en meetkwaliteit/uitval zichtbaar.
Dit was de ontwerpstand bij HA38. In de ongepubliceerde grote bèta zijn
instellingen, private sleutels en lokale Shelly-/Xiaomi-diagnoseontvangst inmiddels
aangesloten. Kamertoewijzing als gekwalificeerde regelbron en echte apparaatproeven
blijven open; de actuele stand staat bovenaan en op het werkbord.

Ook opgenomen in X01: Xiaomi Smart Temperature and Humidity Monitor 3
(MJWSD05MMC), via dezelfde Bluetooth-pagina. Versleutelde ontvangst vereist
een geldige apparaatsleutel; de verkrijgingsroute en praktijkkwalificatie zijn
nog open. Originele sensorfirmware heeft de voorkeur; geen automatische flash.

HA38 levert het TV02-opstart-/lifecycleherstel voor dezelfde vooraf vastgelegde
bron, met begrensde subscripties en veilige redencodes. De huidige diagnose is
wachtend/stale en ongekwalificeerd; echte nieuwe ontvangst en causale echo blijven
open. De oude incidentoorzaak is niet bewezen. Eerdere bronproeven blijven bewaard
in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

## Onderhoudsrelease dev38 / alpha29

Gepubliceerd uit `d131c503f42e6b834a0815db8384983a7fc1b46f`; HA dev38
geïnstalleerd, E32 alpha29 nog niet. Alle 23 voorbereide onderdelen behouden.
2189 tests per Core-versie en vier browserregressies geslaagd; publieke pakketten
exact gecontroleerd. Hoogste prioriteit is offline onderzoek van de mislukte
E32-upload en een onderbouwde herstelroute. Zie het actuele installatieverslag.
Bij deze historische uitgave was nog geen aangesloten Shelly-/Xiaomi-driver
beschikbaar. Dit is geen actuele uitspraak over de ongepubliceerde bètabron.

## Voorbereid voor de volgende gezamenlijke bundel

| Onderdeel | Software afgewerkt | Nog nodig voor praktijk/levering |
| --- | --- | --- |
| I03 uploadherstelbaarheid | Strikte/exacte lengte, opruimen bij annulering/toegangsverlies, één appbestand en selectie na volledig geautoriseerd verzoek; 16 nieuwe native en 11 REST-grensscenario's | Onderbouwde herstelroute voor alpha28; watchdogtaak/oorzaak onbekend. [Bewijs](OTA-UPLOAD-ONDERZOEK-20261024.nl.md) |
| B06 veiligheidsfeiten | Afgewezen toekomstige/oudere/tegenstrijdige acquisities blijven ingetrokken; gedeelde zonepolicy-/storingscontrole en correcte nul-uptimemarkeerders | Werkelijke producenten, bron-/installatiekwalificatie, minimumflow en naloop. [Bewijs](VEILIGHEIDSFEITEN-20261024.nl.md) |
| B07/B08 en R15 ketelrapporten | Per veld nieuwste originele meting behouden; oudere deeltelegrammen vullen ontbrekende velden; HA herstelt ingetrokken cache niet via een andere groep; 12 native en 6 HA-regressies in deze batch | Beoordeeld profiel, adres/masker, echte UART en fysieke start/stop-/DHW-proeven. [Bewijs](KETELRAPPORT-VOLGORDE-20261024.nl.md) |

De gecombineerde native suite telt **689 geslaagde tests**; beide firmwarebuilds
zijn gecontroleerd. Op elk van HA Core 2026.10.2 en 2026.10.3 slagen **2195 gevallen**,
zonder fouten of skips. Pakket-/release-CI op een bevroren eindkandidaat blijft vereist. Alle 23 voorbereide onderdelen en 31 producteisen blijven behouden.
Niets uit deze bronbundel is opnieuw geïnstalleerd of gepubliceerd als release.
De huidige installatie en de fysieke releasepoorten blijven hierboven afzonderlijk vermeld.

## Voor volgende bundel: oorspronkelijke Zigbee-ontvangers

P0 R03/B04 en R05/B05: herstel na gedeeltelijk mislukte luisteraarregistratie
voorbereid voor temperatuur- en TV02-producent. Een fout laat geen actieve
schijneigenaar achter; registratie kan na geslaagde cleanup opnieuw plaatsvinden.
Ook een cleanupfout blijft expliciet zichtbaar, met publicatie uitgeschakeld.
Geen installatie of fysieke kwalificatie; bestaande M2-acceptatie blijft open.

### Veilige afsluiting bij SDK-cleanupfouten

De voorbereide temperatuur-/TV02-producenten wachten nu ook bij mislukte
luisteraarverwijdering op de oude publicatie. Parallel stoppen en starten kan
daardoor geen nieuwe run mengen met de oude run. Een achtergebleven callback
blijft inert; herstart vereist geslaagde cleanup. Alle 32 lokale producenttests
slagen. Bronwerk voor de volgende bundel; geen installatie of B04/B05-vrijgave.

### Begrensde publicatie bij directe MQTT-callbacks

Het publicatieslot wordt vóór de SDK-aanroep gereserveerd. Geneste ontvangst kan
geen tweede publicatie starten; stoppen vanuit de SDK wacht op het oorspronkelijke
resultaat, ook bij afwijzing. Vier voor/na-regressies toegevoegd; alle 36
producenttests slagen. Dit blijft bronwerk voor de volgende gezamenlijke bundel,
zonder installatie of fysieke kwalificatie.

## Automatische updatecontrole — voorbereid, niet geïnstalleerd

Vanaf vijf minuten na opstarten iedere twaalf uur controleren, uitsluitend met
netwerk/geldige tijd en buiten update/herstart/bootvalidatie. Ook fouten wachten
tot de volgende automatische periode; handmatige controle blijft mogelijk.
Geslaagde resultaten worden vijf minuten in RAM hergebruikt. Het dashboard toont
een numeriek nieuwere compatibele alpha en opent de updatepagina. Geen extra
GitHub-aanvraag vanuit het dashboard, geen automatische installatie of flashwrites
voor de cache. EN/NL-uitleg toegevoegd. Herstel van de oude upload-watchdog blijft
een afzonderlijk onderzoek; deze voorbereiding bewijst dat herstel niet.

### Onderzoek: native GitHub-route apart beoordelen

Vers read-only bewijs bevat native alpha28→31-`boot_slot_selected`, HTTP200 en
alle bytes. Dit past bij het publieke alpha31-manifest en de huidige bevestigde
alpha31-boot. De GitHub-route is aanwezig; een losse commit is pas installeerbaar
na gepubliceerde build en manifest. De onbekende multipart-watchdog en een
nieuwe native installatievrijgave blijven afzonderlijke beoordelingen.
Zie [onderzoek](E32-GITHUB-UPDATE-ONDERZOEK-20261025.nl.md).

De CI-dashboardproef vond een fixturefout: de nieuwe knop opende de updatepagina,
maar de HTTP-fixture gaf daar404 op lokale updatestatus. Die fixture levert nu
het expliciete updaterantwoord; de proef wacht ook op versie-readback en behoudt
de zichtbaarheid-/GET-only-asserties. Geen productie404 of herstelde uploadclaim.

### Achtergrondcontrole wacht op een actieve ketelproef

De hoofdloop geeft de bestaande proefstatus door aan de updateplanner. Een
achtergrondcontrole start niet zolang de controller ontbreekt of de ketelproef
actief is; die controle kan daardoor geen keepalive van de proef blokkeren.
Uitstel verbruikt geen poging en start geen wachtrij. 45 gerichte native gevallen
en de E32-build slagen. Geen ketelproef of firmwareactie voor deze broncontrole.

## Verplichte flash- en nacontrolepoort

Vanaf nu geen volgende reguliere E32-release zonder bewezen native GitHub-update
en afzonderlijke nacontrole van de vorige release. Exacte nieuwe versie/bron/ELF/
web, bevestigde boot, stijgende uptime, back-up en instellingenbehoud zijn
verplicht. CI-publicatie controleert het versiegebonden acceptatierapport; een
build of HTTP202 is onvoldoende. [Proces](E32-UPDATE-PROCES.nl.md).

## Duidelijke releasenotities — aangepast op GitHub

De actuele E32 alpha36- en HA48-beschrijvingen beginnen nu met **Nieuw**,
**Opgelost** en **Bijwerken en gebruik**, gevolgd door een Engelse samenvatting.
Technische oorspronkelijke notities blijven uitklapbaar beschikbaar. De
release-organizer bewaart deze gebruikerstekst boven de downloadtabel; de
publicatiecontrole vereist deze opbouw voor volgende versies. Twaalf gerichte
tests slagen. Beide publieke teksten zijn exact teruggelezen; programmabestanden,
tags en releasestatus zijn behouden, evenals de overige 63 releasebeschrijvingen.
Zie [het notitieproces](RELEASE-NOTES-PROCES.nl.md).

De private Bluetooth-opslag controleert vóór schrijven de verse NVS-statistieken, inclusief ruimte voor regelconfiguratievervanging, garbage collection en een bestaande modelreservering. Onbekende of onvoldoende opslag weigert de wijziging; er wordt niets automatisch gewist. Deze controle activeert geen leer- of regelroute.

### Bluetooth koppelen gebruiksvriendelijker (25 oktober, voorbereid)

Gevonden apparaten tonen hun uitgezonden naam, adres en signaalsterkte. Eén klik op **Dit apparaat toevoegen** vult naam en adres in; reeds toegevoegde apparaten zijn gemarkeerd. Gebruiker controleert het profiel en vult bij versleuteling de bindkey in, slaat op en herstart via Settings. Geen automatische fysieke koppeling, herstart of kraanopdracht. Apparaten zonder naam blijven zichtbaar met hun adres. De lijst bewaart invoer/focus bij verversen en blijft begrensd op 32 apparaten; maximaal 8 opgeslagen apparaten blijft gelden. Zie de volgende gezamenlijke release notes. Nog niet geïnstalleerd.
