# HA-opstart — één eigenaar over async-leesgrenzen

25 oktober 2026. Geleverd in HA47, samen met de gepubliceerde
[alpha34-updatercheckpoints](UPDATE-VERIFICATIE-CHECKPOINTS-20261025.nl.md).
HA47 is geïnstalleerd en onafhankelijk nagecontroleerd; E32 blijft alpha31.
[Installatie en grenzen](INSTALLATIE-HA47-ALPHA34-20261025.nl.md).

## Reproduceerbaar probleem

De native verbinding las eerst programma/configuratie en de bestaande Store-
journal. Bij afsluiten tijdens die await kon de oude opstart daarna alsnog een
transport koppelen, een worker maken en subscriptions/timers registreren.
Annuleren tijdens die vroege lezing doorliep de opruiming nog niet. Een tweede
start kon daarnaast de toestand van dezelfde verbinding opnieuw opbouwen.

De oorspronkelijke temperatuurdiagnose had ook geen begrensd aanmeldbudget.
Een laat teruggekomen unsubscribe-handle kon na afsluiten worden toegevoegd,
waarna opstart alsnog de periodieke timer zette. TV02 had al een afzonderlijk
begrensde aanmeldroute; de opstart hervatte daarna nog zonder afsluitcontrole.

## Wat is gecorrigeerd

- De bestaande verbinding heeft één opstart. Een tweede gelijktijdige of reeds
  voltooide start wordt geweigerd zonder de eerste eigenaar te sluiten. Een
  afgesloten object begint niet opnieuw; een echte reload gebruikt nieuwe objecten.
- Na configuratie-, Store- en graph-leesgrenzen wordt afsluiten gecontroleerd
  vóór transportkoppeling, nieuwe worker, listeners of timers.
- Annuleren en fouten over de hele opstart doorlopen dezelfde bestaande teardown.
- Een unsubscribe-handle die pas na afsluiten terugkomt wordt direct uitgevoerd.
  Een vervangen temperatuurontvanger blijft behouden; de oude verbinding sluit.
- Alle oorspronkelijke temperatuurtopics delen één timeoutbudget van één seconde.
  Optionele diagnosefouten geven `unavailable` en laten de bestaande besturings-
  eigenaar werken. Ze creëren geen nieuw abonnement, retry, worker of timer.
- Na TV02-aanmelding wordt afsluiten opnieuw gecontroleerd vóór schema-/timeropbouw.

Dit verandert geen kamerbronkeuze, acquisitiekwalificatie, SOURCE-/profiel-/grant-
inhoud, fysieke uitvoerroute of gebruikersconfiguratie. Er wordt geen kraan- of
ketelopdracht toegevoegd.

## Betekenis van de proeven

Alle tien nieuwe gevallen falen op de bewaarde oude bron en slagen met de
correctie. Ze gebruiken echte native HA-objecten/registries/Store-routes met
expliciet beheerste async-randen: configuratie, journal, subscribe, cancel,
dubbele start en ontvangervervanging. Een reeds bestaande andere diagnose-
eigenaar moet behouden blijven; de proef controleert dat expliciet.

In de lokaal onderzochte ondersteunde Core 2026.10.3 rondt `mqtt.async_subscribe`
normaal direct af. De subscribe-stall en late-handlegevallen injecteren daarom
een vertraagde async-grens; zij bewijzen geen vastgelopen broker of productie-
incident. De programma-/Store-lezingen kunnen wel echt yielden. De timeout vergt
coöperatieve async-annulering en is geen garantie tegen blokkerende threadcode.

De eerdere incidentele CI-kamerassertie, historische uploader-watchdog en het
pendelen krijgen hiermee geen oorzaak toegewezen of herstelclaim. Geschikte
kamerbron, oorspronkelijke TV02-echo en fysieke start-/stop-/uitvalproeven blijven
open. Actieve bèta blijft **NOT_READY**.

## Afzonderlijke alleen-lezen productiecontrole

De bestaande HA-agent heeft op 25 oktober **05:46:49 UTC** één verse normale
HA-diagnostiekdownload en bestaande native states gelezen, zonder productie-
wijziging, subscription, E32-request, updatecheck of apparaatopdracht.
Acht checks slagen; SOURCE5/config-/profieldigests zijn met de vorige baseline
vergeleken en behouden. HA46 is geladen en `shadow_ready`. De broncorrecties
van deze volgende bundel zijn niet geïnstalleerd.

De huidige TV02-diagnose-eigenaar toont één callback, één enqueue en één
workeracceptatie, nul drops/afwijzingen/fouten, bij één geconfigureerd topic.
Het oorspronkelijke bericht is `commandDataResponse` met
`local_temperature_centi_c` en is inmiddels stale (ontvangstmetadata circa
1010 seconden oud). Berichttype is geen bewijs van een opdracht door ons.
De vorige momentopname had nul tellers; continuïteit van dezelfde RAM-eigenaar
is niet afzonderlijk bewezen. Er wordt dus geen volledig brokerverkeer of
ononderbroken lifetime-delta geclaimd.

De temperatuurgroep heeft nul oorspronkelijke topics. De gekozen interne
sensorwaarde blijft `profile_missing`/onbruikbaar, zonder acquisitieouderdom.
TV02 blijft ongekwalificeerd: `command_correlated`, `valve_ready` en
`control_qualified` zijn false. Vijf bestaande ESP-metrieken zijn numeriek en
niet restored; RTC blijft verwacht onbekend. HA-uitgangsvlaggen zijn false.
Dit is geen directe nieuwe E32-versie-/boot-/TX-audit; die beperkte snapshot
rechtvaardigt geen nieuwe uitspraken over niet-uitgelezen devicevelden.
Werkelijke externe helperbytes/startup en een upstreamoorzaak blijven onbekend.

## Verificatie

- Tien nieuwe negatieve baselinegevallen: alle tien falen met de bewaarde oude bron.
- 139 gerichte ontvangst-/lifecyclegevallen geslaagd.
- Volledige native HA-regressie: 2.349 gevallen per Core 2026.10.3 en 2026.10.2
  (2.281 tests + 68 subtests), nul failures/errors/skips.
- Zeven HA-pakketunittests en bron-/diffcontrole geslaagd.

De opstartproef gebruikte eerst een onjuiste verwachting over een reeds bestaande
andere diagnose-eigenaar. De definitieve proef controleert behoud van die eigenaar;
de productiecode verwijdert die niet. De eerdere foutuitvoer en de gereproduceerde
oude-codefouten blijven bewaard. Dit is geen extra productieincident.

Bewijs: `out/native-startup-ownership-20261025/`. De oorspronkelijke falende XML's
blijven bewaard. De vaste localhost-MQTT-fixture gebruikt alleen synthetische
proeven; geen productiebron, ketel, kraan of andere fysiek gekoppelde broker.

**English:** Native HA startup now retains one connection owner across async
configuration, journal and subscription boundaries. Close/cancel cannot revive
an old worker/listener/timer; duplicate startup cannot replace the first owner.
Optional original-temperature subscription uses one bounded total wait and
late listener handles are removed. All ten new cases fail against the old
source and pass after correction. Delayed subscribe boundaries are injected
fixtures, not a diagnosed production broker failure. HA47 deployment is recorded
separately; physical qualification remains open.
