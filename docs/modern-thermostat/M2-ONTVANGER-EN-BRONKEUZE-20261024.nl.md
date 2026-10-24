# M2/B04/B05 — ontvangerkern en zichtbare bronkeuze

24 oktober 2026. Bronwerk voor één grotere HA-releasekandidaat; nog niet
geïnstalleerd. Huidige productie: HA40/E32alpha28. Geen fysieke handeling.

## Eén oorspronkelijk ontvangervenster

De nieuwe `ActuatorReceiver` vult de ontbrekende HA-ontvangertoelating als
voorbereide kern in. De native shadowfabriek selecteert deze kern **niet**;
er is geen nieuwe subscriber, publicatie, timer, opslag, service of GUI-vrijgave.
Dit is nog geen aangesloten normale FW→HA-kraanroute.

Een toekomstige beoordeelde eigenaar moet een afzonderlijk gekwalificeerd
Profile-C-adapterobject, lokale actuele controller-/boot-/sessie-/config-/binding-
identiteit en een actuele autorisatiecallback leveren. Beide lagen staan standaard
uit. Metadata, een brokerbericht of een trustvinkje kan dit niet instellen.

- De HA-ontvanger maakt een uniek grant met een venster van vijf seconden op zijn eigen monotone klok. Herhaald uitlezen behoudt ID en oorspronkelijke deadline; ontvangst van een opdracht start geen nieuw budget.
- Het exacte vlakke wirebericht is maximaal 2048 ASCII-tekens. De bestaande parser weigert dubbele/escaped sleutels, diepte, ongeldige getallen en te grote bomen. Alle contextvelden, types, grant en doel moeten passen.
- Eén lopende actie/resultaat; nieuwe doelen worden tijdens uitvoering geweigerd, niet achter een onbegrensde wachtrij geplaatst. Een pending exacte duplicate deelt alleen de oorspronkelijke future.
- Een exact historisch duplicate-resultaat kan na grantverval worden gelezen zonder IO. Een gewijzigde payload, vervangen grant of oudere sequence kan geen nieuwe actie starten. Hoge sequencewatermerken lopen niet terug bij grantvernieuwing.
- De lokale scope en autorisatie worden opnieuw gecontroleerd rond dispatch en na de bestaande geawaitte HA-service. Een nieuwe boot/config/binding, klokverlies, annulering of mislukte toegelaten actie trekt deze eigenaar in. Geen retry; serviceacceptatie is geen kraan-ACK of open afgiftepad.

De kern bevat geen verzendtransactie, MQTT-publisher of fysieke readback.
De normale bronfabriek, FW-wireafzender, huidige leasebinding, causale oorspronkelijke
Tuya-echo en fysieke/exclusieve eigenaar blijven afzonderlijk uit te werken en te
kwalificeren. Deze grenzen mogen niet verdwijnen door alleen de kern te construeren.

## De gekozen temperatuurbron uitleggen

De kamereditor toont bij laden een vaste, alleen-lezen `temperature_source_review`.
Een native diagnostische entiteit krijgt een zichtbaar label en uitleg. Als de
bestaande native Zigbee2MQTT-discovery de geselecteerde property exact als
`device_temperature` beschrijft, wordt direct uitgelegd dat dit interne
apparaattemperatuur is en een ruimteluchtsensor nodig is. De gebruiker hoeft
hiervoor niet eerst de optionele metadataweergave te openen.

Een gewone beschikbare getalwaarde wordt hierdoor niet gekwalificeerd.
Ontbrekende/corrupte optionele metadata blijft onbekend en kan de kamerweergave
niet laten mislukken. Een disabled/verwijderde bron blijft unresolved; geen
vervanging op basis van naam of hergebruikt entity-ID. Er zijn geen brokerrequests,
nieuwe subscriptions, kunstmatige rapporten, bronpin- of meetdeadlinewijzigingen.

Nederlands/Engels; de actuele waarschuwing volgt de huidige conceptselectie.
Een waarschuwing over de opgeslagen interne sensor blijft niet op een nieuw
gewone-sensorconcept plakken. De bestaande meetstatus blijft afzonderlijk zichtbaar.
Frontend dev41/v41 behoudt expliciete v38- en v35-subklassealiases, zodat bestaande
kaarten ook met alleen de nieuwe module blijven laden.

## Verificatie en grenzen

54 ontvangertests; 9 bronkeuzetests (zes oorspronkelijke gevallen reproduceren
ontbrekende uitleg op de oude bron, drie aanvullende metadatafoutgevallen).
Vier extra eigenaarsgrensgevallen faalden in de eerste nieuwe ontvangerkern en
zijn vóór enige installatie hersteld: intrekken tijdens een callback en hergebruik
van dezelfde adapter kunnen geen grant of dispatch meer doorlaten.
Gerichte en volledige HA-regressies, koude browserupgrade in drie kaartversies,
Nederlands/Engels en desktop/mobiel worden in de kandidaat gecontroleerd.
Bewijs: `out/m2-release-candidate-20261024/`; definitieve aantallen na testafronding.

Geen volledige M2- of actieve bèta-vrijgave. E32-watchdogherstel, echte geschikte
kamerbron, normale ontvangstroute en causale kraan-/ketelproeven blijven open.
Alle eerder voorbereide functies en 31 producteisen blijven behouden.
