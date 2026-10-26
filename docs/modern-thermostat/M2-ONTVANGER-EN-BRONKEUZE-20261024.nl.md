# M2/B04/B05 — ontvangerkern en zichtbare bronkeuze

24 oktober 2026. Geleverd in HA43, bron `97eb9a0`, gepubliceerd en geïnstalleerd.
Afzonderlijke nacontrole 21:17:50 UTC: 38 checks geslaagd. E32alpha28 behouden;
geen fysieke handeling of M2-/ketelvrijgave. [Installatieverslag](INSTALLATIE-HA43-20261024.nl.md).

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

55 ontvangertests; 9 bronkeuzetests (zes oorspronkelijke gevallen reproduceren
ontbrekende uitleg op de oude bron, drie aanvullende metadatafoutgevallen).
Vier extra eigenaarsgrensgevallen faalden in de eerste nieuwe ontvangerkern en
zijn vóór enige installatie hersteld: intrekken tijdens een callback en hergebruik
van dezelfde adapter kunnen geen grant of dispatch meer doorlaten.
Gerichte en volledige HA-regressies, koude browserupgrade in drie kaartversies,
Nederlands/Engels en desktop/mobiel zijn gecontroleerd in de definitieve kandidaat.
Definitief: 2281 gevallen per Core 2026.10.2/2026.10.3 zonder fout/skip, alle
zeven softwarepoorten en tag-CI geslaagd. Leveringsbewijs staat in
`out/ha-dev43-release-20261024/`; gericht voor/na-bewijs blijft in
`out/m2-release-candidate-20261024/`.

Geen volledige M2- of actieve bèta-vrijgave. E32-watchdogherstel, echte geschikte
kamerbron, normale ontvangstroute en causale kraan-/ketelproeven blijven open.
Alle eerder voorbereide functies en 31 producteisen blijven behouden.

## Definitieve kandidaat na dev41-CI

Dev41 is niet gepubliceerd of geïnstalleerd: de tag-CI faalde in een bestaande
kamerstoptest. Twaalf gerichte herhalingen slaagden; de exacte oorspronkelijke
CI-oorzaak is zonder trace onbekend. Een gerichte verloren-opstartberichtproef
reproduceert dezelfde vraagassertie: de minimum-uit-wachttijd begon vóór de eerste
werkelijke vloerkamermeting. De fixture wacht nu begrensd op beide oorspronkelijke
firmwaremetingen en telt daarna de ongewijzigde 121 seconden. Alle bestaande
asserties en 120-secondenbeleid blijven staan. De nieuwe regressie faalt vóór
en slaagt na deze wijziging; 39 gerichte kamer-/HVAC-proeven slagen.
De opvolgende kandidaat heet HA42; frontend blijft dev41/v41. Oude tag behouden,
geen geforceerde verplaatsing of vervanging van assets.

## Controle vóór HA43

De extra begincontrole sluit de afzonderlijke verloren-opstartberichtregressie,
maar de kamerassertie faalde ook daarna in de HA42-bron-CI. HA42-tag-CI is daarom
vóór publicatie geannuleerd. Geen HA41/HA42-release gepubliceerd of geïnstalleerd.
Gerichte testinstrumentatie bewaart nu de volledige eindige kunstmatige
C++-invoer, inclusief klokwaarden, bij acht herhalingen. Native uitgangen blijven
in iedere replay uit. Een onafhankelijke bronreview beoordeelde deze beperkte
diagnostiek vóór de Git-push.

De volgende diagnostische CI vond een andere fout: het optellen van 4,9 en 0,1
seconden landde één floating-point-eenheid vóór de verwachte grens. Klokoorsprong
123,456 reproduceert dit. De test gebruikt nu het oorspronkelijke anker plus exact
vijf seconden; de productiegrens en uitvoercode zijn niet gewijzigd. Voor echte
HA-serviceafhandeling wordt de kunstmatige testklok weer voorwaarts op de native
loop-epoch aangesloten. 101 gerichte lokale proeven slagen; ook 46 kamer-/HVAC-
gevallen met een opnieuw gebouwde C++-runner. Exacte definitieve CI blijft de
leveringsvoorwaarde. Eerdere onbekende CI-kameroorzaak niet als gerepareerd claimen.

## Werkelijk geleverd

HA43 is gepubliceerd en geladen op Core 2026.10.3. Alle 84 livebestanden zijn
afzonderlijk gelijk aan de openbare ZIP en bevroren Git-bron bevonden. De werkelijke
kamerweergave geeft `internal_device_temperature` en `authorizes_control=false`;
de geselecteerde meting blijft `profile_missing`. Twee eigen kamerkaarten
migreren v38→v41, handmatige kaarten/resources en overige dashboardvelden blijven
behouden. Verse HA40-back-up met 93 payloads en alle 38 onafhankelijke nacontroles
slagen. Geen E32-upload/herstart of kraan-/ketelopdracht. De normale M2-bedrading,
oorspronkelijke echo en fysieke kwalificatie blijven open. De eerdere incidentele
CI-kamerassertie blijft expliciet onderzoek vóór actieve M2; geen reparatieclaim.

## Volgende bundel: één klokdomein in de eindige kamerfixture

25 oktober2026; bronvoorbereiding, geen productie- of apparaatwijziging. De
fixture gaf de HA-wireclient de kunstmatige C++-klok100..221s, maar liet de
ontvanger observaties stempelen met de werkelijke host-uptime. Het aftrekken
van die twee domeinen kon dezelfde verse synthetische rapporten kunstmatig oud
maken. De fixture koppelt nu ook de runtimeklok aan haar bestaande peerklok,
inclusief een normale fixture-reload. Globale HA-/loopklokken veranderen niet.

Vier nieuwe gevallen oefenen het volledige bestaande service/ACK/stop/hervatpad
met geïnjecteerde begin-epochs50/100/150/500. Op ongewijzigde fixturecode falen
de eerste twee en slagen de laatste twee; na correctie slagen alle50 gerichte
kamer-/HVAC-gevallen per echte Core2026.10.2 en2026.10.3. De bestaande acht
herhalingen, 121s-warmup, 120s-minimum-uit en alle demand-/stopasserties blijven
behouden. De bestaande eindige replaytrace bewaart voortaan ook beide gebruikte
klokwaarden, hostloopwaarde en oorspronkelijke observatietijden. Laatste
metadata-uitbreiding is afzonderlijk herspeeld; de volledige gecombineerde
bundel slaagt lokaal met2.356 gevallen per Core (2.288tests+68subtests), nul
fouten/errors/skips. Beide onafhankelijke offline bronreviews slagen zonder
bevindingen. Exacte releasefreeze, pakket-/tag-CI en installatie blijven aparte
poorten; deze bronstap publiceert geen nieuwe versie.

Dit bewijst de klokdomeinfout in de fixture. De negatieve proef eindigt met
`sensor_unavailable`; de historische CI-afwijking had
`shadow_low_load_or_satisfied`. Zonder de toenmalige volledige trace is de
oorspronkelijke CI-oorzaak hiermee **niet** bewezen of afgevinkt. Er is geen
reparatieclaim voor pendelen, de updater-watchdog of fysieke regeling.
Bewijs: `out/climate-ci-causality-20261025/`, inclusief oorspronkelijke XML en
alle vier voor/na-traces. Productie blijft HA47/E32alpha31.

**English:** The finite two-room fixture now uses the same monotonic domain
for observation stamps and wire-age calculation. Four host-epoch regressions
exercise the unchanged native service path; two fail before correction and
all pass afterwards. Original timing/safety assertions remain. This is a
test-fixture repair; the older CI incident has a different final reason and
its historical cause remains unproven. No production or device action.
