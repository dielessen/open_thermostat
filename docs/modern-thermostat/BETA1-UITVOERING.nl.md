# Eén grote eerste bèta — uitvoering

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

## Uitvoeringsopdracht

Alle uitvoerbare verbeteringen bundelen. De expliciet goedgekeurde gezamenlijke
passieve testrelease is geïnstalleerd; werk door aan de actieve bèta zonder
losse tussenreleases. WORKBOARD.nl.md blijft de checklist voor 31 eisen,
23 componenten en 14 bèta-controles. Verdere broncommits veranderen de
geïnstalleerde bron5e3ed30 niet. Oudere checkpointbeschrijvingen hieronder
blijven historisch bewijs, geen actuele installatiestatus.

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

- P0 HA-opstart: hersteld en live bevestigd in HA0.4.0b1/Core2026.10.4,
  met 87 exacte bestanden en 45 onafhankelijke nacontroles. De eerdere
  Core2/3/4-tests horen bij bron5e3ed30; nieuwe HA-bron vereist nieuwe checks.
  [Installatiebewijs](INSTALLATIE-BETA1-20261025.nl.md).

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

De uitgiftehulpmiddelen herkennen nu ook canonieke HA-versies met `a`, `b`, `rc` en zonder ontwikkelsuffix. De eerste bètaverpakking test verplicht de ongewijzigde alpha36-parser met het werkelijke manifest/image; bewijs gaat mee in de checksums. 18 releasenotitiegevallen, 4 voorgangercompatibiliteitsgevallen en 59 gerichte releasescriptgevallen slagen. Dit was een broncheckpoint vóór het vastzetten van de kandidaatversies; er is niets gepubliceerd of geïnstalleerd.

Bij verdere broncontrole is een integer-overloop bij een extreem grote monotone tijdsprong in het opwarmmodel gereproduceerd onder UBSan en hersteld vóór de rekenstappen. 893 native en 58 model-/opslaggevallen onder sanitizers slagen; de uitloop-/curveguards begrenzen de tijd al vóór rekenen. De werkelijke NVS-configuratieopslag is afzonderlijk testbaar gemaakt: 32 gedeelde SDK-opslaggevallen, inclusief allocatiefout en reservering, slagen. Drie boards en de bestaande E32-layout/default/no-TX-controle slagen. Dit activeert geen leermodel of keteluitvoer.

De HA-packager vereist voortaan broncommit, bronhash, schone en ongewijzigde testbron en werkelijke beoordeelde HA-Core-versie in de native XML-uitslag. Ontbrekend, verouderd of dubbel bewijs en negatieve testtellingen worden geweigerd. Tien packagergevallen slagen; acht echte Core4-groepsgevallen tonen dat een ongeschone ontwikkelrun correct als ongeschikt voor verpakken wordt gemarkeerd. Een nieuwe volledige schone testrun volgt vóór de eindverpakking.

De volledige HA-hercontrole bij broncheckpoint `be56dd9` slaagt op de echte Cores .4/.3/.2 met ieder 2.431 gevallen (2.363 tests + 68 subtests), nul fouten/errors/skips. De brongebonden XML-rapporten bevestigen schone/ongewijzigde bron en de echte Core; de eigen MQTT-fixture is gestopt en onafhankelijk afwezig. Deze checkpointuitslagen vervangen de definitieve globale freeze niet.

Shelly BLU TRV-diagnose is aan dezelfde instellingen/ontvanger gekoppeld: apart gemeld doel, berekende TRV-temperatuur, optionele externe temperatuur en ruwe statusrevisie, met onafhankelijke leeftijd/intrekking. Expliciete profiel-/sleutelkeuze, geen GATT- of kraanwrite. Fysieke variant/ontvangst en actuatorbediening blijven open. De HA-packager gebruikt dezelfde canonieke versiegrammatica als de releasenotities; 11 pakketgevallen slagen. CI geeft de drie volledige HA-suites samen 30 minuten zonder hun individuele tijd-/foutcontroles te versoepelen.

De geïntegreerde drie-profielenbundel slaagt met 906 native gevallen, 52 parser-/instellingen-/eigenaargevallen onder ASan/UBSan/leakcontrole, 25 echte cryptogevallen en twaalf Bluetooth-browserprofielen. Daarnaast slagen 47 JavaScriptgevallen, twee navigatie-/twee dashboard- en vier taalprofielen, drie boardbuilds, verse SPIFFS en de E32-layout/default/no-TX-controle. Alle 33 actuele ingebedde UI-assets komen exact overeen. Er is geen fysieke TRV-proef of installatie uitgevoerd.

De twee Z2M-ontvangstextensies wachten bij stop niet meer onbeperkt op een SDK-publicatie. Een vijfseconden-eventloopdeadline weigert een nieuwe eigenaar zolang oud SDK-werk nog openstaat; late afronding hervat niets automatisch. Beide fouten blijven zichtbaar bij gelijktijdige listener-/drainfout. 40 Nodegevallen slagen; twee deadlinegevallen faalden vóór de reparatie. Geen broker-/wire-/regelbevoegdheidswijziging en geen productie-installatie.

De HA-specialist bevestigt op 25 oktober omstreeks 17:40–17:45 UTC alleen-lezen dat Z2M-add-on 2.14.2-1 als started staat; de bekende bridgeversie 2.14.2 is gecachet. Het bestaande privé ingestelde TV02-projectbestand is via begrensde reads gehasht. Runtime-load, daadwerkelijke convertersversie en Tuya-modulebytes blijven onbekend binnen de bestaande leesnamespace. Geen helper geïnstalleerd, toegang uitgebreid, herstart, publicatie of apparaatopdracht. De openbare ongeconfigureerde bronhash vervangt geen vergelijking met private installatiepins.

De twee oorspronkelijke Z2M-rapportproducenten gaan voortaan mee als afzonderlijk optioneel companionarchief binnen dezelfde HA-release, met gelijke broncommit, originele licentie, exacte bron-/ZIP-/checksumcontrole en lege publieke bindings. Het gewone HA-archief blijft een afzonderlijke integratie-installatie. Een offline voorbereidingshulpmiddel bewaart gevalideerde privé pins alleen wanneer alle drie bronhashes kloppen en de bestaande code buiten die pins exact de vorige openbare template volgt. Geen JavaScript-uitvoering, automatische installatie of regelbevoegdheid. 14 pakkettests en 9 pinvoorbereidingstests slagen. CI controleert het extra archief onafhankelijk tegen de tagbron. [Gebruik](Z2M-RELEASE-COMPANION.nl-en.md).

De echte publicatieverificatie is ook met een geïsoleerd fixturepakket uitgevoerd: de correcte bundel slaagt; een opnieuw gechecksummede gewijzigde companion en een ZIP met dubbele leden worden geweigerd. De HA-ZIP wordt eveneens tegen de tagbestanden, brongebonden testidentiteit en volledige interne/buitenste checksumlijsten gecontroleerd. Pinvoorbereiding weigert daarnaast symlinks, FIFO’s en te grote inputs en schrijft alleen een nieuwe private 0600-uitvoer. Geen live private pins gelezen door de lokale packager en geen installatie.

Vervolg alleen-lezen bronbewijs op 25 oktober 18:11:44 UTC: de bestaande TV02-producent bevat precies één geldige JSON-pin. Na uitsluitend in-memory vervangen van die array door `[]` komen alle overige bytes exact overeen met de openbare alpha36-template (SHA256 `3df0f75521338f614345c2d460b8150c796b2361d8571508273328e3c71beb73`). De templatevoorwaarde voor gecontroleerd pinbehoud is daarmee bewezen. Er zijn geen privéwaarden geëxporteerd, bestanden gewijzigd of apparaatopdrachten uitgevoerd. Runtime-load, convertersversie en causale/fysieke kwalificatie blijven onbekend.

## Gezamenlijke softwarekandidaat vastzetten

De kandidaatversies zijn E32 `v0.1.0-e32v2-beta.1` en HA `0.4.0b1`, inclusief het optionele Z2M-bronpakket uit dezelfde commit. Dit bevriest de software-identiteit voor de volledige lokale controles en verpakking; het is geen publicatie, installatie of fysieke vrijgave. De geïnstalleerde basis blijft alpha36/dev48 en de laatste HA-startstatus blijft setup_error. B04–B14 blijven afzonderlijk open op het werkbord; ontbrekende bron-/veiligheids-/zenderkwalificatie wordt niet als gereed afgevinkt. Bron/versies en alle daadwerkelijke controle-uitkomsten worden in de kandidaatbewijzen gekoppeld, vóór eventuele uitgifte.

De volledige E32-kit bewaart nu ook het exacte firmware-ELF, de linkerkaart en
ingebedde webidentiteit onder `symbols/`. De ELF-SHA256 moet overeenkomen met de
app-descriptor in het echte OTA-bestand; gekopieerde symbolen worden onafhankelijk
nagelezen. Zes negatieve/positieve pakketgevallen controleren verkeerde/stale
identiteit, gewijzigde bestanden, symlinks en onbedoelde onderzoeksbestanden.
De bestaande volledige releaseverifier blijft ongewijzigd verplicht.
De opstartlog gebruikt de SDK-hexrepresentatie in plaats van een binaire hash
als C-string te behandelen. De gezamenlijke eindcontrole wordt na deze wijziging
opnieuw uitgevoerd; eerdere checkpointbewijzen blijven afzonderlijk bewaard.
