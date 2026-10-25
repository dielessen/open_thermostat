# Eén grote eerste bèta — uitvoering

Opdracht van 25 oktober 2026: alle uitvoerbare planpunten meenemen in één grote
bèta. Geen losse alpha37-publicatie en geen tussentijdse E32-flash of
HA-installatie. De draaiende basis blijft E32 alpha36 / HA dev48. Dit document
is de uitvoeringsvolgorde; WORKBOARD.nl.md blijft de actuele acceptatiechecklist
voor alle 31 eisen, 23 componenten en 14 bèta-controles.

## Eerst gereed voor een actieve ketelbèta

| Volgorde | Planpunten | Benodigd resultaat |
| --- | --- | --- |
| 1 | B04 / R03 | Oorspronkelijke kamermeting van het juiste apparaat, aantoonbare meetleeftijd, identiteit, constante verse waarden en uitval. Een beschikbaar HA-state of interne apparaattemperatuur is onvoldoende. |
| 2 | B05 / R04–R05 | Eén volledige kraantransactie: normale firmware→HA-route, juiste eigenaar, oorspronkelijke doelecho, readiness en uitval. Eerst een begrensde kraanproef zonder ketel. Groepsbediening pas met afzonderlijke terugmelding. |
| 3 | B06 / R07,R22–R24 | Werkelijke, gedateerde veiligheidsinformatie en installatieprofiel: afgiftepad, waterlimieten, DHW-prioriteit, naloop en onafhankelijke stop. Ontbrekende informatie blijft onbekend. |
| 4 | B07–B09 / R08 | Classic-proefpad, gecontroleerde UART-zender, adres/arbitrage en stopketen voor de concrete Ecomline/EasyControl-installatie. Tado en E32 krijgen geen gelijktijdige regelbevoegdheid. |
| 5 | B10 / R01,R15–R18,R25,R27,R29 | Normale kamerbediening, programma/override, entiteiten, diagnose en historie integraal controleren; dezelfde betekenis in Nederlands en Engels. Geen oude waarden als actuele feedback. |
| 6 | B11–B14 / R28,R30 | Eén bronfreeze, volledige firmware/HA/browser/bron/licentie/pakketcontrole, daarna één uiteindelijke uitrol met back-up en onafhankelijke nacontrole. Fysieke start/stop en uitval afzonderlijk vastleggen. |

Fysieke feiten kunnen niet uit code worden afgeleid. Daarvoor wordt geen
trustschakelaar, synthetisch veilig signaal of automatisch gekozen vervangende
sensor toegevoegd. Dat houdt de implementatie niet tegen: softwarewerk loopt
verder, terwijl de bijbehorende fysieke acceptatie open blijft.

## Verder in dezelfde bundel afwerken

- R02/R18: externe doelbediening, exacte éénmalige override, echopreventie,
  weekprogramma, reconnect en afloop via dezelfde controller-eigenaar.
- R04/R06/R30: meerdere actuatoren en afgiftegroepen, expliciete gedeeltelijke
  beschikbaarheid en resourcegrenzen; acht zones zijn nog geen bewezen installatie.
- R09–R11: normale instellingen voor buitenbron en stooklijn, bronouderdom,
  bronverlies en begrensde terugval; geen stille bronvervanging.
- R12–R14: per ruimte conservatief leren, gevalideerde modellen en parameters
  blijvend bewaren/herstellen, reset en rollback. Tijdelijke I-correctie mag bij
  herstart of bronverlies veilig vervallen. Optimum-start en uitlopen blijven
  afzonderlijke functies met eigen voldoende meetdata en comfortcontrole.
- R17/R26: Recorder, CSV en historie met behouden identiteit, gaten, eenheden en
  heldere scheiding tussen gerapporteerde waarden, modellen en echte meters.
- R19–R22/R27/R31: comfortmodi, aanwezigheid, raamcontact, vorst/zomer en meldingen
  via de normale gebruikersroute; tapwaterwrites alleen voor apart ondersteunde
  modellen. Geen automatische ketelreset of wijziging van legionellabeveiliging.
- X01: Bluetoothapparaatbeheer, Shelly/Xiaomi-sensorprofielen en lokale E32-modus
  aanvullend op HA. Voorbereide decoder is geen gekoppeld apparaat; sleutels,
  echte ontvangst en bronkwalificatie moeten afzonderlijk kloppen.

## Reeds voorbereid en onverkort meenemen

Automatische updatecontrole om de twaalf uur, vijfminutencache, dashboardmelding,
uitstel tijdens een ketelproef en Zigbee-producentcorrecties uit de ongepubliceerde
alpha37-voorbereiding gaan mee in deze bèta, zonder eigen tussenrelease.
Alle overige geïnventariseerde brononderdelen blijven behouden.

## Uitvoering van deze bundel

- P0 HA-opstart: de gemelde Core4-versieblokkade is lokaal gereproduceerd.
  Presentatiegroep en private opslagtransactie zijn ontkoppeld; Core2026.10.4
  wordt expliciet toegevoegd/getest naast .2/.3. De live dev48 blijft volgens
  de laatste alleen-lezen controle in setup_error; geen tussentijdse uitrol.
  [Onderzoek en acceptatie](HA-CORE4-OPSTART.nl.md).

- Ontvangstdiagnose: verkeerd getypeerde retained-/sessiemetadata wordt geweigerd;
  extreem grote klokwaarden en millisecondenoverloop veroorzaken geen crash of
  hernieuwde meetkwalificatie. Gerichte native HA-regressies zijn uitgevoerd.
- Kamermeetketen: een teruggaande, ongeldige of overlopende klok trekt
  gekwalificeerde metingen in en blijft voor die runtime afgewezen. Een andere
  profielcallback herstelt geen oude bevoegdheid. Wachtrijvertraging gebruikt
  dezelfde klokwaarde voor leeftijd en tijdanker, zodat verwerking de meting
  niet jonger maakt.
- Kamermeldingen: een falende UI-luisteraar onderbreekt geen intrekking.
  Synchroon vervangen van een bronprofiel kan geen oude gekwalificeerde meting
  opnieuw in de verzendwachtrij zetten. Een ongeldige lokale meetklok geeft een
  installatiegebonden NL/EN-melding in HA Repairs; alleen een gezonde nieuwe
  eigenaar kan deze wissen. Meldingsfouten blokkeren geen intrekking.
  Dezelfde klok bewaakt raamcontact en aanwezigheid, inclusief de conservatieve
  state-leeftijdroute; klokherstel of een nieuw bericht herstelt die oude eigenaar niet.
- Bestaande kamerweergave: ongeldige getallen en booleans worden geen temperatuur,
  vochtigheid of batterijpercentage. Ongeldige vochtigheidssentinels en waarden
  buiten 0–100% blijven onbekend. Ongeldige doelen worden vóór verzending geweigerd.
- Bluetoothapparaten: normale E32-instellingen en lokale SBHT-103C-
  diagnoseontvangst zijn aangesloten met acht bindings, echte AES-CCM,
  verborgen sleutels in één afzonderlijke privéblob (ook buiten bereik van de
  oudere netwerkreader bij rollback), onafhankelijke formulier-ETags, duurzame
  terugleescontrole en expliciete
  herstart. Vaste wachtrij, oorspronkelijke ontvangstleeftijden en boot-lokale
  tellers; geen HA-/kamerregelbron, kraanwrite of fysieke kwalificatie.
  [Bediening, softwarebewijs en open proeven](BLUETOOTH-APPARATEN.nl.md).
- Xiaomi Monitor3: een apart MiBeacon v4/v5-profiel met twee expliciete
  productdeclaraties en eigen nonce/AAD, strikte gehele-/float-TLV's en
  oorspronkelijke veldleeftijden. 893 native/39 parser-eigenaar-/24 echte
  cryptogevallen en acht browserprofielen slagen. Geen kamerregelbron of
  fysieke sensorclaim; sleutelverkrijging, acquisitie en praktijk blijven open.
- Bluetooth: een mislukte scanstart blokkeert latere scans niet blijvend;
  opruimen blijft exclusief en afsluiten kan niet door een late callback worden
  teruggedraaid. De bestaande scanner bewaart geen onbeperkte SDK-resultaten.
- Herstel-AP van de oudere ESP32-borden wacht niet meer in een eigen lus op
  een Bluetooth-eindcallback. De reader sluit zijn ontvangst vóór de normale
  NimBLE-afsluiting. De drie boardbuilds slagen; een echte AP-proef staat apart.
  De E32 gebruikte deze lus niet: dit verklaart geen eerdere E32-flashstoring.
- Bluetoothontdekking gebruikt een vaste lijst van maximaal 32 adressen zonder
  heapgroei. Een volle ontdeklijst verhindert geen verwerking van een reeds
  ingestelde kamersensor; handmatig adres invoeren blijft mogelijk.
- Updatecatalogus en releasebeschrijvingen herkennen alpha, beta, rc en stabiele
  firmware. Een melding beveelt geen minder rijp kanaal dan de geïnstalleerde
  versie aan; manifest-/bron-/imagecontrole blijft verplicht.
- Leermodelopslag: laden en bewaren van opwarm-, uitloop- en stooklijnmodellen
  vangen ook exceptions op. Een onzekere schrijfactie sluit de gedeelde eigenaar
  en wordt niet herhaald. Dit bewaart de bestaande gegevensformaten en verleent
  geen automatische leer- of regelbevoegdheid.
- Bestaande kamerstatus gebruikt correcte JSON-strings voor namen, programma's,
  ID's en kleplabels. De browser geeft de kamernaam als gegevens door aan de
  klikhandler. Quote-/apostrof-/regeleindnamen blijven bedienbaar; onbekende
  vochtigheid, batterij en gemiddelde temperatuur worden niet als nul verzonnen.
- De oude kamerregeling trekt warmtevraag in bij een ongeldige lokale tijd,
  toont de reden in EN/NL en gebruikt een SDK-kloktime-out van 100 ms per kamer.
  Uren/minuten/weekdagen worden vóór gebruik gecontroleerd. Dit is de legacy-
  regelroute, geen verklaring voor eerder pendelen onder de moderne E32-route.
- De nieuwe native tests compileren de echte Room.cpp en RoomConfig.cpp en de
  echte tijdelijke override. De SDK-klok blijft een expliciete testgrens;
  een native uitslag bewijst geen fysieke klok-/ketel-/stopwerking.
- CSV-export ondersteunt nu dag/week/maand tot 31 dagen met dezelfde limieten
  van 64 entiteiten, 5.000 rijen en 1 MiB. De normale HA-actie heeft een
  installatiekeuzelijst en volledige NL/EN-velduitleg. De echte native
  SQLite/Recorder-route en vertaalresources zijn getoetst.
- CSV-export controleert na Recorder-wachttijd opnieuw de exacte entiteiten en
  geladen eigenaar. Verwijderen, vervangen, hernoemen, uitschakelen of verplaatsen
  tijdens export levert geen gedeeltelijk resultaat onder de oude identiteit op.

Het [concept voor gebruikers](BETA1-RELEASE-NOTES.nl-en.md) wordt met de bundel bijgehouden.

Bewijs wordt verzameld onder `out/large-beta-20261025/`. Volledige tests gelden
alleen voor de daarbij vastgelegde bronstand; een latere wijziging vereist de
passende aanvullende controle. Deze lijst is geen publicatie-, installatie- of
fysieke acceptatieclaim. De grote bèta is nog in bewerking.

De uitgiftehulpmiddelen herkennen nu ook canonieke HA-versies met `a`, `b`, `rc` en zonder ontwikkelsuffix. De eerste bètaverpakking test verplicht de ongewijzigde alpha36-parser met het werkelijke manifest/image; bewijs gaat mee in de checksums. 18 releasenotitiegevallen, 4 voorgangercompatibiliteitsgevallen en 59 gerichte releasescriptgevallen slagen. Versies zijn nog niet bevroren en er is niets gepubliceerd of geïnstalleerd.

Bij verdere broncontrole is een integer-overloop bij een extreem grote monotone tijdsprong in het opwarmmodel gereproduceerd onder UBSan en hersteld vóór de rekenstappen. 893 native en 58 model-/opslaggevallen onder sanitizers slagen; de uitloop-/curveguards begrenzen de tijd al vóór rekenen. De werkelijke NVS-configuratieopslag is afzonderlijk testbaar gemaakt: 32 gedeelde SDK-opslaggevallen, inclusief allocatiefout en reservering, slagen. Drie boards en de bestaande E32-layout/default/no-TX-controle slagen. Dit activeert geen leermodel of keteluitvoer.

De HA-packager vereist voortaan broncommit, bronhash, schone en ongewijzigde testbron en werkelijke beoordeelde HA-Core-versie in de native XML-uitslag. Ontbrekend, verouderd of dubbel bewijs en negatieve testtellingen worden geweigerd. Tien packagergevallen slagen; acht echte Core4-groepsgevallen tonen dat een ongeschone ontwikkelrun correct als ongeschikt voor verpakken wordt gemarkeerd. Een nieuwe volledige schone testrun volgt vóór de eindverpakking.

De volledige HA-hercontrole bij broncheckpoint `be56dd9` slaagt op de echte Cores .4/.3/.2 met ieder 2.431 gevallen (2.363 tests + 68 subtests), nul fouten/errors/skips. De brongebonden XML-rapporten bevestigen schone/ongewijzigde bron en de echte Core; de eigen MQTT-fixture is gestopt en onafhankelijk afwezig. Deze checkpointuitslagen vervangen de definitieve globale freeze niet.

Shelly BLU TRV-diagnose is aan dezelfde instellingen/ontvanger gekoppeld: apart gemeld doel, berekende TRV-temperatuur, optionele externe temperatuur en ruwe statusrevisie, met onafhankelijke leeftijd/intrekking. Expliciete profiel-/sleutelkeuze, geen GATT- of kraanwrite. Fysieke variant/ontvangst en actuatorbediening blijven open. De HA-packager gebruikt dezelfde canonieke versiegrammatica als de releasenotities; 11 pakketgevallen slagen. CI geeft de drie volledige HA-suites samen 30 minuten zonder hun individuele tijd-/foutcontroles te versoepelen.

De geïntegreerde drie-profielenbundel slaagt met 906 native gevallen, 52 parser-/instellingen-/eigenaargevallen onder ASan/UBSan/leakcontrole, 25 echte cryptogevallen en twaalf Bluetooth-browserprofielen. Daarnaast slagen 47 JavaScriptgevallen, twee navigatie-/twee dashboard- en vier taalprofielen, drie boardbuilds, verse SPIFFS en de E32-layout/default/no-TX-controle. Alle 33 actuele ingebedde UI-assets komen exact overeen. Er is geen fysieke TRV-proef of installatie uitgevoerd.

De twee Z2M-ontvangstextensies wachten bij stop niet meer onbeperkt op een SDK-publicatie. Een vijfseconden-eventloopdeadline weigert een nieuwe eigenaar zolang oud SDK-werk nog openstaat; late afronding hervat niets automatisch. Beide fouten blijven zichtbaar bij gelijktijdige listener-/drainfout. 40 Nodegevallen slagen; twee deadlinegevallen faalden vóór de reparatie. Geen broker-/wire-/regelbevoegdheidswijziging en geen productie-installatie.

De HA-specialist bevestigt op 25 oktober omstreeks 17:40–17:45 UTC alleen-lezen dat Z2M-add-on 2.14.2-1 als started staat; de bekende bridgeversie 2.14.2 is gecachet. Het bestaande privé ingestelde TV02-projectbestand is via begrensde reads gehasht. Runtime-load, daadwerkelijke convertersversie en Tuya-modulebytes blijven onbekend binnen de bestaande leesnamespace. Geen helper geïnstalleerd, toegang uitgebreid, herstart, publicatie of apparaatopdracht. De openbare ongeconfigureerde bronhash vervangt geen vergelijking met private installatiepins.
