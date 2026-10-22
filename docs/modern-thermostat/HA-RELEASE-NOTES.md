# OpenThermostat Home Assistant 0.4.0.dev12 — testrelease

Eén installatie met centrale instellingen en kamers. Nieuwe kamers gebruiken
een wizard; bestaande kamers hebben één direct configuratiescherm met gekoppelde
apparaten, temperaturen en een grafisch weekprogramma met temperatuurblokken.
Apparaatidentiteit, beschikbaarheid en kraangrenzen worden bij de kamer getoond.
Deze versie herkent de officiële Home Assistant-featureflags van een klimaatapparaat
correct; geldige temperatuurgrenzen hoeven daardoor niet onbekend te lijken.

Dit is een ontwikkelrelease. De complete HA→E32→bevestiging-/kraanproef en
verwarmingsvrijgave zijn nog niet afgerond. De optionele externe kamerdoelbron,
raamcontact en meerdere gekwalificeerde kraanprofielen zijn nog vervolgwerk.
De nieuwe E32-firmware wordt afzonderlijk getest en uitgebracht; deze release
bevat uitsluitend de Home Assistant-integratie. Een opgeslagen instelling is
nog geen bevestigde uitvoering op de E32.

Download `OpenThermostat-HA-0.4.0.dev12.zip` en controleer de SHA256 met
`HA-SHA256SUMS.txt`. Maak vóór installatie een back-up van de bestaande
integratie/configuratie. Kopieer `custom_components/open_thermostat` uit de ZIP
naar de Home Assistant-configuratiemap, controleer de configuratie en herstart
Home Assistant. Bestaande gebruikers hoeven de integratie niet opnieuw toe te
voegen. Controleer na herstart versie, kamers, apparaatkoppelingen en programma.
Behoud het vorige pakket als terugvalmogelijkheid.

Dev12 heeft dezelfde integratiewerking als dev11. De releasepipeline bouwt nu
ook beide benodigde C++-testprobes in een schone CI-omgeving. De mislukte
`ha-v0.4.0.dev11`-tag is behouden en heeft geen gepubliceerde release.
Als dev11 al gezond is geïnstalleerd, is deze versiewissel niet nodig voor gebruik.
Het pakket bevat `SOURCE.json`, oorspronkelijke projectlicentie en checksums.
Geen live HA-opslag, firmware, ketelvrijgave of apparaatcommando's zijn inbegrepen.
