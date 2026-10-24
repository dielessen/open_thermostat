# M2 — kraanberichten op de bestaande HA-worker

25 oktober 2026. Bronvoorbereiding voor de grotere bèta; geen installatie,
fysieke kwalificatie of bèta-vrijgave.

## Wat is aangesloten?

De normale `NativeShadowConnection` herkent nu grantaanvragen en kraanopdrachten
binnen het bestaande `fw/#`-abonnement. De bestaande begrensde worker verwerkt ze;
antwoorden gebruiken dezelfde MQTT-verbinding, QoS0 en `retain=False`.
Er zijn geen extra abonnementen, clients, workers, timers of opslagbestanden.

De productconstructor levert **geen actuatorfabriek**. Zonder die afzonderlijke
lokale SOURCE-fabriek worden deze berichten genegeerd, zonder een shadow-sessie
te resetten of `last_rx`, metingen, heartbeat of lease te vernieuwen. Een
GUI-keuze, ontvangen grant of geldige verbinding maakt geen fysieke bevoegdheid.

Een toekomstige beoordeelde fabriek krijgt de actuele lokale scope en moet
zelf een onafhankelijk gekwalificeerde `ActuatorReceiver` en `ProfileCActuator`
leveren. De route voegt beperkingen toe aan beide oorspronkelijke autorisaties;
zij schakelt geen profiel in en maakt een geweigerde autorisatie niet waar.
De fabriek is een begrensde lokale bouwfunctie, geen netwerkactie of servicecall.

## Berichtcontract

Alle onderwerpen vallen onder de bestaande `<prefix>/v1/`-verbinding.

| Onderwerp | Inhoud / betekenis |
| --- | --- |
| `fw/actuator_grant_request/<binding_id>` | Exact `api:1`, de acht scopevelden, `command_kind:room_target`, `request_sequence` 1–4294967295 |
| `ha/actuator_grant/<binding_id>` | Bestaande 13-velden-grant van de HA-ontvanger; nominale bovengrens `grant_ms:5000` |
| `fw/actuator_command/<binding_id>` | Bestaande begrensde `room_target`-envelop van `ActuatorIntent` |
| `ha/actuator_result/<binding_id>` | Lokale scope plus serviceontvangstbewijs met volgnummer, doel en werkelijke native eenheid/waarde; geen fysieke ACK |

De acht scopevelden zijn controller, boot, epoch, adapter, adaptersessie,
configuratierevisie, configuratiedigest en binding. Ze worden vergeleken met
de eigen actuele `ShadowClient` en diens geverifieerde configuratierecord.
Een onbekende binding of scope uit een brokerbericht vervangt dat record niet.

Berichten zijn maximaal 2048 tekens, ASCII zonder escapes, dubbele JSON-sleutels
of onbegrensde nesting. Retained of te grote berichten gaan niet in de workerqueue.
Er worden maximaal acht lokale binding-eigenaren bijgehouden.
Een uitgeschakelde of ingetrokken route neemt geen gedeelde queuecapaciteit in.
Bij druk op een ingeschakelde route wordt uitsluitend die optionele route
ingetrokken en blijft minstens de helft van de bestaande queue vrij voor gewone
berichten. Een optionele burst reset geen shadow-sessie of diagnosecache.

## Oorspronkelijke tijd en herhaling

Het ontvangsttijdstip wordt vóór enqueue vastgelegd. Vijf seconden wachttijd in
de bestaande worker maakt een bericht onbruikbaar. Het grantvenster eindigt
uiterlijk vijf seconden na oorspronkelijke ontvangst, of eerder bij de bestaande
lokale sessiegrant/lease. De HA-ontvanger behoudt die eigen absolute deadline;
`grant_ms:5000` belooft geen nieuw venster vanaf latere ontvangst door firmware.

Een identieke aanvraag met hetzelfde `request_sequence` krijgt uitsluitend het
oorspronkelijke grant binnen zijn oorspronkelijke deadline. Na die deadline
wordt dezelfde aanvraag niet opnieuw uitgegeven. Lagere nummers en gewijzigde
duplicaten veroorzaken geen nieuwe actie. Een hoger aanvraagnummer kan het
eerdere ongebruikte grant niet verlengen. Een verbruikt grant vereist voor een
nieuwe opdracht een nieuw grant; exacte commandoduplicaten blijven historische
serviceacceptatie zonder extra serviceaanroep.

De normale lokale context wordt ook in de adapterautorisatie gecontroleerd,
vóór en na de oorspronkelijke SOURCE-callback. Daardoor kan een opdracht die
op de bestaande servicelock wacht niet alsnog versturen na sessieverlies.
Disconnect, firmware-availability, waargenomen scope-/configuratieverlies en
queue-overloop trekken bestaande eigenaren onmiddellijk in, vóór de bijbehorende taak
achter een wachtende opdracht in de workerqueue terechtkomt. Herstel van een
callback of reconnect activeert deze eigenaar niet opnieuw. Een nieuwe eigenaar
vereist expliciete herkwalificatie en een nieuwe verbindingseigenaar.
Een opstartmelding vóórdat enige eigenaar/grant bestaat verleent niets en
blokkeert de latere eerste kwalificatie na een verse handshake niet. Deze
uitzondering kan een reeds ingetrokken eigenaar niet herstellen.

Een onzekere producer-/transportuitkomst geeft geen automatische retry. Een al
gestarte servicecall kan na intrekking zijn uitgevoerd; deze code kan die
fysieke uitkomst niet ongedaan maken of afleiden. De ontvangstbewijzen blijven
`service_acceptance_only`, met `device_reported`, `valve_ready` en
`control_qualified` alle false.

## Bewijs en resterend werk

Native HA-tests controleren tijd, duplicaten, bron-/sessieverlies tijdens wachten,
permanente intrekking en de standaard gesloten productroute. De echte bestaande
worker en echte HA-registries worden ook met een expliciete synthetische lokale
fabriek beproefd. Een door die worker afgegeven grant gaat door de werkelijke
C++-encoder; zijn bytes gaan terug door dezelfde worker naar de bewaakte
HA-serviceadapter. Het importeren van de scope uit dat grant is uitsluitend een
expliciete `--fixture-scope`-optie van de finite stdin/stdout-testrunner. Productie
moet haar scope uit de lokale controller halen.

Een afzonderlijke regressie reproduceert de ontbrekende onmiddellijke fence bij
een firmware-offlinemelding: de bestaande worker wacht op de adapterlock terwijl
de offlinemelding binnenkomt. Vóór de callbackaanpassing faalt die test; daarna
slagen alle 179 gerichte gevallen. De baselineproef trekt zijn synthetische
eigenaar ook bij falen in vóór vrijgave van de lock; er is geen fysieke opdracht.

De onafhankelijke eerste review vond twee open punten: gewijzigde firmware-scope
achter een lockwachtende opdracht en queue-overloop door optioneel verkeer.
Vier aanvullende regressies falen vóór herstel; na herstel slagen zij. Dezelfde
echte callback/worker krijgt hiervoor een vervangende bootidentiteit en bursts
van honderd berichten met fabriek uit, route ingetrokken en route onder druk.
Een ongewijzigd periodiek hello trekt de eigenaar niet in en verlengt geen grant.

Dit sluit de HA-workerbedrading, niet de volledige normale zendketen. De echte
product-SOURCE-fabriek en geschikte kamerbron, firmware-MQTT-grantaanvraag en
antwoordbedrading, oorspronkelijke causale Tuya-zendtransactie/echo, fysieke
kwalificatie en E32-herstel blijven open. Er is geen kraan- of ketelopdracht naar
een echt apparaat uitgevoerd. Alle oorspronkelijke releasevoorwaarden blijven
op het werkbord staan; B05 is niet afgevinkt.

Reproduceerbare testuitvoer, inventaris en TaskFlow:
`out/large-beta-wire-20261025/` in de bronwerkboom.
