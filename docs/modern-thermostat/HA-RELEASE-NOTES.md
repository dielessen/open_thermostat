# OpenThermostat Home Assistant 0.4.0.dev17 — testrelease

Eén installatie met centrale instellingen en kamers. Nieuwe kamers gebruiken
een wizard; bestaande kamers hebben één direct configuratiescherm met gekoppelde
apparaten, temperaturen en een grafisch weekprogramma met temperatuurblokken.
Apparaatidentiteit, beschikbaarheid en kraangrenzen worden bij de kamer getoond.
Deze versie herkent de officiële Home Assistant-featureflags van een klimaatapparaat
correct; geldige temperatuurgrenzen hoeven daardoor niet onbekend te lijken.

Dev17 herkent Zigbee2MQTT-klimaatapparaten zonder algemeen `state_topic`.
De prefix wordt uitsluitend afgeleid uit zowel de gepubliceerde bridge- als
de exacte apparaatbeschikbaarheid, gekoppeld aan de bestaande apparaatidentiteit.
Ontbrekende, ongeldige en tegenstrijdige gegevens blijven geweigerd. Deze versie
verandert geen apparaatinstellingen of fysieke aansturing.

Dev16 herstelt de uitlezing voor Home Assistants eigen `MQTTDiscoveryPayload`-
object. De regressietest gebruikt nu dat echte native object, ook samen met de
werkelijke HA-MQTT-client en een lokale testbroker. De eerdere dev15-tag en
bestanden blijven behouden; installeer dev16 voor deze apparaatcontrole.

Aanwezig sinds dev15: in het kamerscherm staat onder **Geavanceerde instellingen**
**Apparaatinformatie controleren**. Dit leest uitsluitend op verzoek de laatst
gemelde Zigbee2MQTT-definities voor de opgeslagen sensor en kranen. Doeltemperatuur,
externe temperatuurinvoer, klepstand en converteropties worden apart getoond.
Ontbrekende informatie blijft onbekend. Een diagnostische apparaattemperatuur
krijgt een duidelijke toelichting; die is niet automatisch een gekwalificeerde
kamermeting. Dit is informatie over apparaatmogelijkheden, geen geslaagde fysieke
kraanproef. Er worden geen instellingen, interviews of verwarmingscommando’s verstuurd.
Deze uitlezing gebruikt de bestaande HA-MQTT-verbinding, twee exacte topics en
een korte wachttijd. Andere apparaten en ruwe discovery-/brokergegevens worden
niet naar het scherm gestuurd. Andere apparaatbronnen blijven normaal gekoppeld;
ze kunnen deze specifieke Zigbee2MQTT-uitlezing niet altijd aanbieden.

Ook aanwezig sinds dev14: kies **E32 verbinden** in de centrale integratie-instellingen.
Vul het lokale webadres en beheerderswachtwoord in. De integratie controleert de
werkelijke E32, bewaart de bestaande netwerkinstellingen en synchroniseert het
kamerprogramma via de bestaande verbinding. Alleen ontvangst van een opdracht
is geen succes: de E32 moet de juiste configuratie en actuele kamerstatus teruggeven.
Een eerste koppeling kan de E32 eenmaal herstarten. E32-alpha.9 of nieuwere
compatibele firmware is nodig; het huidige profiel ondersteunt één of twee kamers.
Het beheerderswachtwoord wordt in de bestaande HA-integratie bewaard; cookies en
controlecodes blijven tijdelijk. Gewone kamerschermen en diagnoses exporteren
het wachtwoord niet. Bij een onderbroken koppeling wordt geen bevestigde uitvoering
voorgewend; controleer de installatiestatus voordat je opnieuw probeert.

Dit is een ontwikkelrelease. De normale HA→E32-configuratieketen is met dev14
live bevestigd; de fysieke sensor-/kraan-/ketelproef en verwarmingsvrijgave
zijn nog niet afgerond. Deze testversie blokkeert de kamereditor nog bij een
actieve koppeling. Live wijzigen van de kamerinstellingen blijft vervolgwerk. De optionele externe kamerdoelbron,
raamcontact en meerdere gekwalificeerde kraanprofielen zijn nog vervolgwerk.
De nieuwe E32-firmware wordt afzonderlijk getest en uitgebracht; deze release
bevat uitsluitend de Home Assistant-integratie. Een opgeslagen instelling is
nog geen bevestigde uitvoering op de E32.

Download `OpenThermostat-HA-0.4.0.dev16.zip` en controleer de SHA256 met
`HA-SHA256SUMS.txt`. Maak vóór installatie een back-up van de bestaande
integratie/configuratie. Kopieer `custom_components/open_thermostat` uit de ZIP
naar de Home Assistant-configuratiemap, controleer de configuratie en herstart
Home Assistant. Bestaande gebruikers hoeven de integratie niet opnieuw toe te
voegen. Controleer na herstart versie, kamers, apparaatkoppelingen en programma.
Behoud het vorige pakket als terugvalmogelijkheid.

Dev14 behoudt de bestaande dagelijkse bediening en neemt de eerdere klokcorrectie mee. Voor reproduceerbare proeven
hebben ontvangst, wachtrij en protocol nu één expliciete monotone klokbron;
standaard blijft dat de bestaande HA-loopklok. De tests gebruiken dezelfde
virtuele klok als hun C++-peer, onafhankelijk van hoe lang de testmachine draait.
De proef bewaakt ook dat vertraagde metingen hun echte leeftijd behouden en
op de ingestelde leeftijdsgrens worden geweigerd. Versheidscontroles blijven staan.

De pipeline bouwt beide benodigde C++-testprobes in een schone CI-omgeving.
De mislukte `ha-v0.4.0.dev11`- en `ha-v0.4.0.dev12`-tags blijven behouden;
daarvan is geen release gepubliceerd. Als dev11 al gezond is geïnstalleerd,
is opnieuw installeren niet nodig voor de bestaande kamerbediening.
Het pakket bevat `SOURCE.json`, oorspronkelijke projectlicentie en checksums.
Geen live HA-opslag, firmware, ketelvrijgave of apparaatcommando's zijn inbegrepen.
