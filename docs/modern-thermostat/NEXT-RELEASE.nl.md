# Beta.7 + HA0.4.0b6 — volledige ketelproef met eigen aanvraagwaarde

**Actuele opdracht:** de aparte door de E32 verzonden aanvoeraanvraag leveren en
daarna één volledige bijgewoonde50°C/600s-proef uitvoeren. De bestaande opdracht
voor release, commit en installatie blijft van kracht. Beta.6 + HA0.4.0b4 staan
geïnstalleerd; beta.7/HA0.4.0b6 is softwarematig voorbereid en wacht op exacte CI.
[Opdracht](BETA7-OWNER-INSTRUCTION-20261027.json), [freezeplan](BETA7-KANDIDAAT.json).

De eerste proef liet daadwerkelijk pomp/branderbedrijf zien. De eigenaar
stopte zelf na ongeveer375s; daarnaast werd een transportfout vastgelegd.
Mijn eerdere conclusie dat de transportfout de automatische stop veroorzaakte
was te stellig. De stop is daarna teruggelezen en fysiek bevestigd.
Een volledige tienminutenproef is daarmee niet afgetekend.
[Oorspronkelijk bewijs en correctie](BETA6-ATTENDED-HEAT-20261027.json).

Beta.7 houdt de gevraagde50°C en de ketelterugmelding apart. Het E32-veld en de
nieuwe HA-uitleesentiteit volgen een werkelijk voltooide UART-verzending;
voor verzending/herstart blijft de waarde onbekend, een verzonden stop wordt0.
Ontvangen curflowtemp/selflowtemp worden niet overschreven. De oude60°C-poort
is vervangen door afzonderlijke5–<90°C-bewaking; een50°C-aanvraag mag bij66°C
water beginnen. Druk, toezicht, nulbaseline, looptijd en stop blijven vereist.
Een eerdere handmatige stop blijft als aanleiding behouden bij een latere fout.
De laatste UART-foutsoort/tijd blijft beschikbaar voor de vervolgdiagnose.
[Betekenis van de aparte waarde](E32-CONTROLLER-REQUEST.md).

**Historische beta.6-uitvoering hieronder:**

**Installatie27 oktober:** beta.6 is gepubliceerd en via de bestaande beveiligde
LAN-appupload geïnstalleerd. Nieuwe boot en bron/ELF/web kloppen; twaalf
instellingenexports zijn bytegelijk gebleven. De eerste upload brak af met een
watchdogreset naar beta.5; één na diagnose begrensde upload gaf HTTP200 success.
Dit is geen native GitHub-acceptatie: de laatste volledige native basis blijft
beta.4. HA0.4.0b4 is gepubliceerd en wordt normaal geïnstalleerd. De badkamerthermostaat
is sinds01:00 unavailable doordat het bestaande planherstel een beoordeling
vraagt, terwijl die bestaande functie uit alle productmenu’s ontbrak.
Een kleine HA0.4.0b5-vervolgfix maakt de normale planreview/status zichtbaar
bij een bestaande native verbinding. Dezelfde controles, afzonderlijke bevestiging
en echte readback blijven vereist. Geen geforceerde opslagwijziging of nieuwe
fysieke toestemming.22 gerichte echte HA/C++-proeven slagen; exacte-tag-CI volgt.
[Herstelfix](HA-RECOVERY-MENU-20261027.json).
[Installatiebewijs en grenzen](BETA6-INSTALLATION-20261027.json).

**Oorspronkelijke opdracht27 oktober:** de eigenaar vraagt de huidige bundel te
committeren, publiceren en op E32 en HA te installeren. Verdere functie-uitbreiding
is voor deze freeze gestopt. Eerst exacte CI/pakketcontrole, verse back-ups,
daarna normale installatie en afzonderlijke nacontrole. Geen echte ketelproef
of kraanopdracht als onderdeel van de installatie.
[Opdracht](BETA6-OWNER-INSTRUCTION-20261027.json) en [freezeplan](BETA6-KANDIDAAT.json).

De uitlezing vóór deze installatie toonde beta.5 uit `a4237cd` op de E32, met juiste
openbare ELF/web-identiteit, bevestigde boot, stijgende uptime en nul TX.
Het oorspronkelijke beta.5-installatiebewijs ontbreekt; de oude native checkpoint
noemt nog beta.4. De laatste volledige native acceptatie blijft daarom beta.4.
De expliciete nieuwe releaseopdracht is vastgelegd als een eenmalige publicatie-
uitzondering voor beta.6. Dit vult geen oud bewijs fictief aan.
[Actuele beta.5-waarneming en bewijsgrens](BETA5-RECOVERED-STATE-20261027.json).

**Begeleide ketelproef:** de kandidaat toont vier stappen: opstelling →
voorbereiden → verwarmen → uitslag. Per stap staat welke knop aan de beurt is,
wat er gebeurt en wat de vervolgstap is. Eén opstellingsbevestiging en een nieuwe
manometerwaarde blijven vereist; de warmtestart heeft één afzonderlijke
bevestiging. Standaard50°C/600s, resterende tijd uit de E32 en direct Stop.
De E32 bewaart per proefsessie of de gewenste temperatuur en CV-bedrijf ná een
verzonden warmteopdracht zijn teruggemeld en of de volledige duur is verstreken.
De uitslag onderscheidt geslaagde terugmelding, vroegtijdig/onvolledig,
onbevestigd, alleen nulvraag en fout. Heropenen bewaart de uitslag in dezelfde
boot/proefsessie, zonder de bediening te hervatten. Dit is geen fysieke B14-
afhandeling. De E32-code is inmiddels geïnstalleerd; de echte ketelproef blijft open.
[Softwarecontrole en bewijsgrens](GUIDED-BOILER-TRIAL-20261027.json).

**Actuele codeprioriteit:** een snellere webinterface en een opgeruimde Keteltest.
De kandidaat gebruikt build-time gzip, herbruikbare browsercache, kleine luie
paginamodules en één gedeelde telemetrieaanvraag. De ketelpagina toont ontvangen
entiteiten eenmaal per herkend apparaat. De proef staat bovenaan met één korte
opstellingsbevestiging en de stappen ophalen → voorbereiden → apart starten →
stoppen. Softwareproeven gebruiken gesimuleerde HTTP-/ketelantwoorden; er is
deze softwareproeven geen echte warmtevraag verstuurd. De latere installatie
staat apart hierboven.
[Review en meetgrens](E32-PERFORMANCE-AND-BOILER-REVIEW.md).
De native MQTT-route gebruikt daarnaast begrensde socketwrites en asynchrone
DNS via de bestaande lwIP-netwerktaak. Een DNS-storing houdt de hoofdloop niet
meer vijftien seconden vast. Ook TCP verbinden verloopt in stappen tussen de
normale looptaken, binnen dezelfde oorspronkelijke drie seconden. De MQTT-
CONNACK-/leeswacht blijft afzonderlijk reviewwerk.
Uitgeschakelde projectlogregels voeren hun dure argumenten niet meer uit;
web/syslog en seriële uitvoer houden hun eigen filters. De netwerkroute-refresh
wacht niet op een volle netwerkmailbox.
Systeemlog bevat nu lichte looptijdtellers in dezelfde statusaanvraag, met een
uitklapbare uitleg. Verborgen logpagina’s stoppen hun uitlezing; reeds verstuurde
instellingenwijzigingen worden door navigatie niet afgebroken of herhaald.
Ook het dashboard breekt een lopende uitlezing af zodra de pagina verborgen
wordt. Terugkeren start direct één nieuwe aanvraag; late/verlopen antwoorden
vervangen die niet en navigatie hervat geen oude dashboarduitlezing.
Bluetooth pauzeert eveneens zijn automatische statusuitlezing in verborgen tabs.
Laden/bewaren en automatische statusreads lopen niet door elkaar. Conceptinvoer,
getypte sleutel en open panelen blijven bij tabwisselen bewaard; verlaten wist
de sleutel. Een ingediende save/scan houdt zijn eigen deadline, zonder herhaling
of readback door een verlaten pagina. Leesherstel wist alleen de oude leesfout;
een onbevestigde save blijft zichtbaar.
Het dashboard bouwt zijn statusantwoord nu in dezelfde vaste64KiB-PSRAM-buffer
als de keteltelemetrie. Geen tweede buffer of groeiende hoofdbody op de interne
heap. De eerste dashboardaanvraag reserveert die buffer; allocatiefout of een te
grote/onvolledige body geeft één volledige503 in plaats van een afgekapt antwoord.
Ook de syslogzender heeft een lichte uitgeschakelde route: geen klok-/
instellingenwerk per hoofdlus en alleen bij verbindingswisseling de wachtrijlock.
Lokale/seriële logging houdt eigen filters; de bestaande honderd-millisecondengrens,
MARK, verliesregistratie en geen-herhaling bij herverbinden blijven behouden.
De gedeelde browsersessiecontrole houdt haar bestaande tiensecondenlimiet nu
ook tijdens het lezen/valideren van de antwoordbody. Een stilgevallen body blokkeert
paginadata niet onbeperkt; een laat antwoord geeft wachtende acties niet alsnog
vrij. Een volgende aanvraag kan normaal herstellen, zonder oude writes te herhalen.
Ook de WiFi-setup leest status-, scan- en afrondings-JSON binnen de bestaande
vijfsecondenlimiet. Een geaccepteerde afronding met verloren body wordt via de
volgende actuele status herkend, zonder opnieuw af te ronden. De bestaande
tekstbevestigingen voor scannen/verbinden blijven behouden. Geen WiFi-actie uitgevoerd.
Debuginstellingen worden pas bij uitklappen opgehaald. Dicht laten scheelt één
API-aanvraag per bezoek aan Instellingen; in-/uitklappen bewaart conceptkeuzes.
Sluiten/navigeren trekt lopende reads in. Opslaan gebruikt de bestaande direct
toegepaste filters, zonder herstartvraag; onbekende save wordt niet herhaald.
Een reeds verlaten instellingenformulier begint geen uitgestelde initialisatie.
De daadwerkelijke paginasnelheid moet na installatie worden gemeten.

**Centrale instellingen bij actieve E32-verbinding:** via Installatie instellen
kun je nu de installatienaam, dashboardkeuze en gedeelde watergrenzen wijzigen.
Gekoppelde radiatorcircuits volgen de grenzen; eigen circuitgrenzen blijven
behouden. Opgeslagen stooklijnpunten worden binnen de nieuwe grenzen gehouden.
Een botsende vloer-/maatwerkgrens wordt vóór bewaren geweigerd. De normale
SOURCE-/verbindingsroute past het volledige plan toe met echte C++-readback;
een grenswijziging kan een gecontroleerde E32-herstart vragen. Alleen hernoemen
of het dashboard wijzigen schrijft geen apparaatinstellingen. Weerregeling is
in dit verbonden profiel nog niet ondersteund en wordt niet als bedienbare
optie aangeboden. Bij onbevestigde toepassing blijft de opgeslagen wijziging
herkenbaar wachten op de gewone E32-verbindingsroute. Geen nieuwe eigenaar,
opslag, automatische retry of fysieke uitvoervrijgave.
[Softwarecontrole en bewijsgrens](ACTIVE-INSTALLATION-20261027.json).

**Nieuwe kamerfunctie in dezelfde bundel:** maximaal acht raam-/deurcontacten
kiezen, wijzigen en verwijderen via de normale kamereditor én kamerwizard.
Opent één gekozen contact, dan pauzeert de kamervraag; hervatten vereist geldige
gesloten meldingen en de ingestelde wachttijd. Ontbrekende/verlopen berichten
houden de vraag gepauzeerd. Bij actieve native plannen loopt bewaren via dezelfde
reload en gecontroleerde C++-readback. Een contact activeert geen extra comfort-
of vorststand en verandert geen temperatuurgrens. De feitelijke sensor-/uitvalproef
en modelspecifieke oorspronkelijke rapportkwalificatie blijven afzonderlijk open.

**Extra kamerbediening in ontwikkeling:** een expliciet gekozen HA-temperatuurhelper
kan door een nieuwe rechtstreekse gebruikerswijziging één tijdelijke override
aanvragen. Bewaren neemt de huidige helperwaarde niet over; automatische wijzigingen,
opstartwaarden en echo's worden geweigerd. Duur één minuut tot twaalf uur, met
afloop uit de regelaar en behoud van raamblokkering/programma/temperatuurbron.
De echte HA-helperdienst en C++-afloop worden softwarematig gecontroleerd.
Fysieke wandbediening heeft nog een eigen oorspronkelijk actieprofiel nodig.
[Werking en grenzen](MANUAL-ROOM-TARGET.md).

**Comfort en aanwezigheid in dezelfde bundel:** normale editor/wizard voor
comfortstanden, afwezigheidsdoel, standaard tijdelijke duur en een optionele
persoon. Actieve plannen bewaren via dezelfde SOURCE en C++-readback.
Oorspronkelijke HA-persoonsmeldingen houden de ouderdom van hun trackerbron;
opnieuw melden van een gecachete bron vernieuwt niets. De bestaande grens is
twee minuten en ontbrekende/verlopen aanwezigheid blijft onbekend. De native
bron behoudt zijn vorstdoel5°C; een nieuw onverenigbaar profiel wordt vóór
bewaren geweigerd. [Werking en afbakening](ROOM-COMFORT.md).

**Batterijstatus bij gekoppelde apparaten:** de normale kamereditor toont onder
Geavanceerde instellingen de HA-batterijpercentages en eigen lage-batterijflags
van de opgeslagen sensor/kranen, eenmaal per apparaat. De oorspronkelijke HA-
meldtijd en ouderdom blijven zichtbaar; onbekend, dubbelzinnig en verlopen
blijven herkenbaar. Dit is gecachete HA-informatie bij laden, geen gekwalificeerd
hardwarebericht of automatische batterijmelding. Geen extra uitleeslus of
nieuwe HA-entiteiten. [Werking](DEVICE-BATTERY-SNAPSHOT.md).

**Vakantie-einddatum aangesloten:** datum/tijd in de HA-tijdzone, expliciete keuze
bij dubbele zomertijdkloktijden en weigeren van niet-bestaande tijden. Starten of
terugkeren naar programma gebruikt de bestaande eindige comfortservice, met
gecontroleerde kamer-/configuratiescope en uitsluitend gemelde actuele status.
Geen automatisch herhalen bij een time-out. De keuze blijft sessielokaal en
vervalt bij herstart/herverbinding/kamerreload; fysieke bron-/gedragsproeven
blijven open. [Gebruikersroute en grenzen](ROOM-VACATION.md).

**Uitleg op het E32-dashboard:** Details per kamer toont de effectieve doelbron,
geselecteerde comfortstand en gemelde resterende tijd of vakantie-einde (UTC).
Raam-/deur- en aanwezigheidsmeldingen krijgen herkenbare redenen. De bestaande
regelaarmomentopname blijft de enige bron; geen extra aanvragen of eigen
aftelklok in de browser. Ontbrekende/verouderde regelstatus toont deze waarden niet.

**Laatste passieve nacontrole:** de huidige proef is `closed` met
`restart_required`, nul positieve warmteframes en gemelde stop. Daarom kan de
geïnstalleerde firmware geen nieuwe proef voorbereiden. Herstarten blijft
uitgesteld. De kandidaat benoemt dit direct bovenaan de pagina en hergebruikt
de bestaande bevestigde herstartknop. De ketel heeft nog geen volledig
product-identificatietelegram gemeld. Een afzonderlijke, expliciete knop kan in
de kandidaat één begrensde identiteitsleesopdracht aanvragen; openen/verversen
van de pagina stuurt niets. Dezelfde korte opstellingsverklaring geldt, zonder
extra vinkje of extra voorwaarde voor verwarmen. Niet-geïdentificeerde andere
busafzenders blijven in ingeklapte diagnostiek zichtbaar.

De oudere voorbereidingsnotities staan ongewijzigd in de
[beta.4-planhistorie](NEXT-RELEASE-HISTORY-BETA4-20261026.nl.md) en de
[eerdere planhistorie](NEXT-RELEASE-HISTORY-20261026.nl.md).

## Wat draait er en wat staat klaar?

| Onderdeel | Laatst vastgelegde stand |
| --- | --- |
| E32 | Openbare beta.4, bron`9ecb4da`, geïnstalleerd via één native GitHub-update |
| Installatieacceptatie | Alle 13 checks PASS; twaalf beperkte API-back-ups nagelezen; versie/bron/ELF/web, nieuwe boot en behoud onafhankelijk beoordeeld |
| HA | Core2026.10.4, geladen integratie0.4.0b1, SOURCE 6. Nieuwste openbare HA-download blijft0.4.0b3; voor deze E32-onderhoudsbron is geen HA-update nodig |
| Handmatige proef | Configuratie opnieuw uitgelezen en nulvraag met latere gemelde stop uitgevoerd; positieve warmtevraag nog niet uitgevoerd |
| Automatische uitvoer | Automatische ketel-/kraanregeling en blijvende ketelinstellingenwrites blijven uit |
| Gepubliceerde bron, installatie open | Beta.5: uitleg bij geblokkeerde proefknoppen en onderscheid tussen mislukte updatecontrole, installatie, verbinding, TLS en HTTP |

Het [beta.4-installatiebewijs](update-acceptance/e32-beta4-20261026.json),
[openbare pakketrapport](BETA4-VERSIONED-PREVIEW.json) en de
[waargenomen nulvraag](BETA4-FIRST-ZERO-OBSERVATION-20261026.json) zijn de bronnen.
De acceptatiepoort staat op geaccepteerde beta.4 en pending beta.5, zonder actieve uitzondering.
De historische beta.3-installatieacceptatie blijft INCOMPLETE; de expliciete
uitzondering voor de afgeronde beta.4-publicatie is bewaard. Zij blokkeert de
geaccepteerde beta.4 niet opnieuw.

## Actuele proef: nulvraag uitgevoerd, tien minuten warmte gevraagd

Op verzoek van de gebruiker zijn de CV-instellingen op de geïnstalleerde beta.4
opnieuw uitgelezen en is een echte nulvraagproef uitgevoerd. De gebruiker bevestigt
Tado los, 2 bar op de manometer en aanwezig bij de ketel met onafhankelijke stop.
Er zijn één configuratieleesopdracht en zeven nulframes verzonden; een strikt
latere ketelmelding bevestigt nulvraag/0%/CV uit. De ketel meldde vóór de proef
ook al nulvraag en0%; dit bewijst geen stop vanuit een brandende ketel.
[Oorspronkelijk bewijs en afbakening](BETA4-ATTENDED-ZERO-20261026.json).

Er is **geen positieve warmtevraag** gestart. Beta.4 blokkeerde bij54°C aanvoer
omdat zijn eerste proefvenster5–<50°C is. Daarna vraagt de gebruiker expliciet
**50°C gedurende tien minuten**. Beta.5 wordt hiervoor aangepast:

- Vraagbereik40–50°C, maximaal600 seconden; standaard50°C/600 seconden.
- Gemeten water blijft een afzonderlijke proefbewaking5–<60°C. Deze eigen
  proefgrens laat een doel van50°C en enige hysterese toe. Het is geen EMS-eis.
- CV-instellingen moeten bij voorbereiding/start jonger zijn dan tien minuten.
  Tijdens de eenmaal gestarte proef blijven die instellingen maximaal één
  proefduur langer geldig; nieuwe instellingen en verse liveberichten blijven
  leidend. Geen automatische configuratie-uitlezing tijdens warmte.
- Een manometerwaarde1,1–2,5bar moet per voorbereiding opnieuw worden opgegeven
  en bij de start jonger zijn dan twee minuten. De verklaring geldt daarna
  voor die eindige proef; een keepalive vernieuwt haar niet.
- Nulbasis, afzonderlijke start, exclusief busbezit, open afgifte, lokale stop,
  vijfseconden-operatorlease, verse Classic-terugmelding en expliciete stop blijven.

De langere proef vereist nieuwe firmware; de bronwijziging past de geïnstalleerde
beta.4 niet aan. Ook tien minuten50°C garandeert geen ontsteking: warmer ketelwater
kan eerst afkoelen. Setpoint, reactie en latere stop worden apart vastgelegd.
Autonome stop bij communicatieverlies is hiermee niet bewezen; B14 blijft open.

## Leesbare en instelbare entiteiten samen op Keteltest

**Regelprincipe verduidelijkt:** een normale thermostaat kan de gewenste
`selflowtemp` uit kamervraag/stooklijn afleiden. De eerdere eis5–<50°C was
een eigen grens voor deze eerste handmatige commissioningproef, geen EMS/iRT-
voorwaarde. Setpointoverdracht en zichtbare brander-/warmtereactie moeten
afzonderlijk worden beoordeeld. Een al warme ketel kan terecht niet ontsteken
bij een lagere vraag. [Onderbouwing en afbakening](THERMOSTAT-SETPOINT-REVIEW.en.md).
De later expliciet gevraagde verruiming naar50°C/600s staat hierboven afzonderlijk.

Op verzoek van de gebruiker zijn de apparaat-/entiteitentabel, vier Classic-
instellingen en alle protocolreferenties opgenomen op Keteltest. De aparte
EMS-apparatenmenuoptie vervalt; bestaande paginalinks komen op Keteltest uit.
Leeswaarden, instelbare waarden en commando’s hebben eigen labels/filters.
In de gepubliceerde beta.5 blijft de volledige vastgelegde EMS-ESP-ketelcatalogus bereikbaar, ook zonder
herkend product-ID: 258 definitievarianten, 252 entiteitsnamen en 31 modelgroepen.
Per item zijn EMS-ESP-mogelijkheid en de werkelijke E32-implementatie/toelating
apart zichtbaar. Vier Classic-instellingen zijn voorbereid, blijvend schrijven
blijft in de standaardfirmware uit; overige writers zijn zichtbaar als nog niet
geïmplementeerd. Er worden geen schrijfrechten uit de catalogus afgeleid.
[Onderzoek naar de officiële EMS-ESP-implementatie](EMS-ENTITY-ACCESS-REVIEW.en.md).
Dit zit in de gepubliceerde beta.5; installatie is nog geblokkeerd en er is geen
positieve ketelproef uitgevoerd.

De beta.6-kandidaat vervangt deze dubbele referentieweergave door één tabel met
ontvangen waarden per apparaat, inclusief toegang en E32-ondersteuning. De
volledige protocolreferentie blijft als bron bewaard; de pagina downloadt alleen
de kleine metadata die nodig is om deze waarden te benoemen.

## Eerstvolgende softwarewerk, in volgorde

| Prioriteit | Werk | Vereist resultaat |
| --- | --- | --- |
| P0 — begrijpelijke proefbediening | Bij de uitlees- en nulvraagknop tonen welke bevestiging, terugmelding of tapwaterconditie ontbreekt; bij een te hete ketel de werkelijke temperatuur en proefgrens tonen | EN/NL, smal/breed scherm; geen automatische proefopdracht of versoepelde toelating |
| P1 — GitHub-diagnose | Een negatieve HTTP-clientcode is geen HTTP-antwoord. Native TLS-code vóór sluiten bewaren; alleen toegestane hostnaam en codes in diagnose | Verbinding/TLS/HTTP/overdracht onderscheiden; geen ondertekende download-URL, tokens of automatische retries in de status |
| P1 — updatebediening | Een mislukte cataloguscontrole onderscheiden van een mislukte firmware-installatie | De geïnstalleerde versie blijft herkenbaar; geen onterechte succes-/herstartmelding |
| P1 — broncontrole | Native tests, gerichte browsergevallen, E32-build en passende CI op de exacte onderhoudsbron | Bewijs bij de nieuwe bron; beta.4-pakketten en installatiebewijs blijven intact |
| Later — ketelproef | Positieve warmte/stop/naloop en onafhankelijke fysieke waarneming | B07–B09/B14 alleen op echt bewijs aftekenen |

De GitHub/HTTPS-code-1 is na de geslaagde beta.4-installatie bij een automatische
cataloguscontrole waargenomen. De oorzaak is nog niet vastgesteld. De nieuwe
onderhoudsbron verbetert de diagnose; zij claimt geen bewezen netwerkreparatie.
[Bèta.5-kandidaatplan](BETA5-KANDIDAAT.json).

## Actuele uitbreiding: uitvoerbare proef en Bluetoothscrollvak

Beta.4 levert de afzonderlijke bijgewoonde Classic-proefroute: configuratie lezen,
nulvraag en latere stop, afzonderlijke warmtestart40–45 °C / maximaal 60 s,
operatorlease van 5 s en nieuwe manometerwaarde per warmtevoorbereiding.
Automatische regeling en blijvende instellingenwrites blijven uit.
Bluetoothontdekking heeft een scrollvak met maximaal 128 ontvangen adressen,
ook naamloze/ongesteunde apparaten, aantal en overloopmelding. Acht opgeslagen
sensorkoppelingen blijven een afzonderlijke limiet.
De exacte beta.4-tag slaagde voor alle negen CI-validatiejobs en 2250 onafhankelijke
pakketcontroles. De volgende bron is een afzonderlijk ontwikkelcheckpoint.

## Bekende opstelling — niet opnieuw uitvragen

- Ketel: Nefit Ecomline Classic HRC 22H.
- Adapter: Bosch EasyControl Adapter 8737908035 V2.3.
- Gateway: BBQKees E32 V2/V2.2 met ethernet; Tado is voor deze proef door de gebruiker bevestigd losgekoppeld.
- De gebruiker kan Tado losnemen en de ketel onafhankelijk uitschakelen.
  Displayreset is geen normale proefstop of automatische uitvalgarantie.
- Meerdere radiatoren staan volgens de gebruiker open; TV02 zit op een radiator.
- Werkelijke Tado-overdracht en gemeten minimumflow/naloop zijn nog niet bewezen.
  Voor deze bijgewoonde nulvraag is Tado wel expliciet bevestigd los.

Het eerdere pendelen is niet causaal verklaard. De historische samenloop met
warmwaterbedrijf bewijst geen oorzaak of reparatie. Een stabiele passieve
beginsituatie en CV/DHW-onderscheid blijven onderdeel van de fysieke proef.

Bij overdracht en herstel moet ook het ketelzijdige adapterprotocol worden
vastgesteld: Bosch documenteert terugval naar aan/uit bij mislukte iRT/OT-detectie.
Alleen een groene led of EMS-ontvangst is hiervoor geen bewijs. De
[pre-TX-kaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) bevat de fabrikantbronnen;
Keteltest geeft hierover NL/EN-uitleg zonder herstart- of configuratieactie.

## Productroadmap en behoud

Het [werkbord](WORKBOARD.nl.md) bewaakt alle 31 producteisen en 14 eindcontroles;
de [broninventaris](BETA1-RELEASE-INVENTARIS.json) bewaakt alle 23 voorbereide
onderdelen. Raam- en deurcontacten, alle schrijfbare EMS-ESP-entiteiten,
BLE-proxy, automatische zones en zelfleren blijven op hun eigen roadmap staan.
Deze onderhoudsbron claimt die functies niet als geleverd of fysiek vrijgegeven.
Alle voorbereide bron en bestaande acceptatiegrenzen blijven behouden.

## Vaste releaseafspraken

- Grotere samenhangende bundels; geen tag of installatie per losse reparatie.
- Voor publicatie: exacte bron/versie, volledige passende controles en openbare
  pakketten; daarna één native update met oorspronkelijke receipts en nacontrole.
- GitHub-hoofdpagina, commits en releasenotities in het Engels bijwerken.
- Na release/grote preflight gegenereerde opslag opruimen; broncode, werkbomen,
  back-ups, receipts, logs en geleverde herlinkinputs behouden.
