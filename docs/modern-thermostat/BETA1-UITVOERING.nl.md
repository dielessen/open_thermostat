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
- Bluetooth: een mislukte scanstart blokkeert latere scans niet blijvend;
  opruimen blijft exclusief en afsluiten kan niet door een late callback worden
  teruggedraaid. De bestaande scanner bewaart geen onbeperkte SDK-resultaten.
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
- CSV-export ondersteunt nu dag/week/maand tot 31 dagen met dezelfde limieten
  van 64 entiteiten, 5.000 rijen en 1 MiB. De normale HA-actie heeft een
  installatiekeuzelijst en volledige NL/EN-velduitleg. De echte native
  SQLite/Recorder-route en vertaalresources zijn getoetst.
- CSV-export controleert na Recorder-wachttijd opnieuw de exacte entiteiten en
  geladen eigenaar. Verwijderen, vervangen, hernoemen, uitschakelen of verplaatsen
  tijdens export levert geen gedeeltelijk resultaat onder de oude identiteit op.

Bewijs wordt verzameld onder `out/large-beta-20261025/`. Volledige tests gelden
alleen voor de daarbij vastgelegde bronstand; een latere wijziging vereist de
passende aanvullende controle. Deze lijst is geen publicatie-, installatie- of
fysieke acceptatieclaim. De grote bèta is nog in bewerking.
