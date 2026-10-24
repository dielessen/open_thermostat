# M2 — firmware-intentie en daadwerkelijke HA-interoperabiliteit

24 oktober 2026. Voorbereiding van de grotere bèta; niet gepubliceerd of
geïnstalleerd. Bestaande HA43/E32alpha28-runtime blijft behouden.

## Wat is toegevoegd?

`src/control/ActuatorIntent.h` vult de ontbrekende firmware-encoder voor de
bestaande HA-ontvangertoelating in. De lokale eigenaar krijgt een onveranderlijke
controller-/boot-/epoch-/adapter-/sessie-/config-/binding-scope. Een inkomend
bericht kan die identiteit of bevoegdheid niet vervangen. Standaard ontbreekt
bevoegdheid en blijft de eigenaar gesloten.

De bestaande canonieke v1-transportcodering en begrensde cJSON-validator worden
hergebruikt. Grants zijn maximaal 2048 bytes, hebben exacte velden/types en
vijf seconden budget. Het C++-venster begint bij de **oorspronkelijke lokale
aanvraag**, begrensd door de **oorspronkelijke lokale lease**. De HA-ontvanger
bewaakt daarnaast zijn eigen oorspronkelijke deadline; de C++-klok vervangt deze
niet. Een vertraagd of herhaald grant kan geen nieuw HA-budget maken.

Eén grant levert maximaal één intentie op, zonder automatische herverzending.
Een hogere grantsequence wist het commandowatermerk niet. Oude/gewijzigde grants,
retained berichten, onbekende scope en ongeldige doelen veroorzaken geen opdracht.
Scopeverlies, waargenomen leaseverlies, klokterugloop, autorisatieverlies en
re-entrante autorisatie trekken de eigenaar blijvend in. Herstel van een callback
of later aanleveren van een langere lease kan dat niet ongedaan maken.

## Wat is daadwerkelijk getoetst?

De eindige `actuator_intent_runner.cpp` gebruikt alleen stdin/stdout. Een werkelijk
door de bestaande HA-ontvanger gemaakt grant gaat naar dit C++-proces. De
geproduceerde bytes gaan terug naar dezelfde native HA-ontvanger en vervolgens
naar de bestaande bewaakte Profile-C-serviceadapter. De tests gebruiken de echte
HA-registries en services, zonder fysieke apparaten of netwerkroute naar productie.

- 13 nieuwe C++-grensproeven; totale native firmwaretestset: 702 geslaagd.
- 61 gerichte HA-/C++-ontvangstproeven per Core 2026.10.2 en 2026.10.3 geslaagd.
- Voor/na-regressie: een callback die tijdens toelating de actuele sessie verandert
  kon in de eerste nieuwe encoder nog worden toegelaten. De expliciete nacontrole
  weigert dit nu en trekt de eigenaar in. Het eerdere falende bewijs blijft bewaard.
- De CI bouwt de exacte C++-tegenhanger vóór de native HA-testsets. Geen skip of
  vervangende Python-encoder als de runner ontbreekt.

Lokaal bewijs: `out/large-beta-20261024/`. Volledige HA-regressies op de huidige bron: 2.287 gevallen per Core
2026.10.2/2026.10.3 (2.219 tests en 68 subtests), nul fouten/errors/skips.
De tijdelijke eigen localhost-MQTT-fixture is gestopt en verwijderd. De
onafhankelijke bronreview v2 slaagt; dit is geen finale CI-/pakket-/livecontrole.

De volledige regressie vond aanvankelijk een verboden afhankelijkheid op de
specifieke graph-validator. De encoder gebruikt nu de bestaande algemene
`BoundedJson`-parser; de architectuurcontrole is ongewijzigd en slaagt. Het
falende resultaat blijft als `full-before-dependency.*` bewaard.

## Wat blijft open?

Dit is een voorbereide protocoltegenhanger, **geen normale aangesloten kraanroute**.
Er is geen productie-import/selectie, nieuwe MQTT-subscriptie/publicatie,
commandowachtrij, timer, opslag of GUI-vrijgave. De echte SOURCE-eigenaar moet de
huidige scope, oorspronkelijke aanvraag, lease en exclusieve bevoegdheid leveren
via het bestaande beoordeelde transport. Die verbinding blijft uit te werken.

Serviceacceptatie blijft serviceacceptatie: geen oorspronkelijke Tuya-echo,
bevestigde motorbeweging, open afgiftepad of regelbevoegdheid. Causale oorspronkelijke
zendtransactie/echo, verse geschikte ruimtemeting, profielkwalificatie en fysieke
proeven blijven vereist. Het gemelde pendelen en de E32-watchdogoorzaak zijn
hiermee niet verklaard of gerepareerd. Alle actieve uitgangen blijven geblokkeerd.

De lokale C++-tijd en lease zijn snapshots van de aanroeper. De synchrone
encoder bemonstert die niet opnieuw na zijn autorisatiecallback en voert geen
transportdispatch uit. De toekomstige normale eigenaar moet daarom actuele
bron-/leasefeiten opnieuw controleren op het echte verzendmoment. De afzonderlijke
HA-ontvanger bewaakt zijn eigen klok en toelating; dit is geen afgeronde
postcallback-/verzendtijdcontrole in de firmware.
