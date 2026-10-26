# Historie exporteren als CSV

De grote bètakandidaat ondersteunt een dag, week of maand, tot maximaal 31 dagen.
Dit is broncode voor de volgende bundel; de geïnstalleerde HA dev48 heeft nog de
oude limiet van 24 uur. Er is voor deze uitbreiding niets geïnstalleerd.

## Gebruiken

Open in Home Assistant **Ontwikkelaarshulpmiddelen → Acties** en kies
**OpenThermostat: Historie exporteren als CSV**. Kies je installatie in de keuzelijst.
Vul de begin- en einddatum met tijdzone in. De einddatum ligt in het verleden.
Voorbeelden: een dag van 1 tot 2 oktober, een week van 1 tot 8 oktober of een maand
van 1 september tot 1 oktober. Gebruik bij een zomer-/wintertijdwisseling de juiste
tijdzone-offset voor beide datums. De limiet is 31 × 24 uur, gemeten in UTC;
een lokale periode van 31 dagen kan bij de wintertijdwisseling dus één uur te
lang zijn. Verdeel die periode dan in twee aanvragen. De uitvoer gebruikt UTC.

Kies desgewenst alleen de sensoren die je nodig hebt. Laat je de selectie leeg,
dan gebruikt de actie de beschikbare entiteiten van deze installatie. De actie
geeft de CSV terug als antwoord; er wordt geen bestand op de E32 of HA geschreven.
Alleen beheerders kunnen deze actie uitvoeren.

## Omvang en betekenis

Maximaal 64 entiteiten, 5.000 rijen en 1 MiB CSV per aanvraag. De bestaande standaard
is 1.000 rijen. Bij een afgekapt resultaat staat `truncated: true` in het antwoord.
Kies dan minder entiteiten of een kortere periode. `queried_entities` en
`unqueried_entities` laten zien welke selectie is verwerkt. De rijen zijn op UTC
en entiteit gesorteerd; een afgekapt resultaat is geen volledige tijdlijn voor
alle gekozen entiteiten.

Elke rij bevat tijd, entiteit, opgeslagen waarde, definitiekwaliteit en eventueel
de destijds opgeslagen eenheid. **Opgeslagen eenheden meenemen** staat standaard
uit. Een ontbrekende eenheid blijft leeg; de actuele eenheid wordt niet ingevuld.
Schattingen blijven als schatting gelabeld. Een afgeleide branderindicatie is geen
onafhankelijke vlamdetectie en een modulatieschatting is geen echte gasmeter.

Alleen werkelijk aanwezige Recorder-wijzigingen worden geëxporteerd. De actie
herstelt geen gewiste historie, verlengt de Recorder-bewaartermijn niet en vult
gaten niet op. Een maand kunnen opvragen bewijst dus geen maand aan opgeslagen
gegevens. Er worden geen statistieken, instellingen of historische waarden gewijzigd.

Wordt een gekozen entiteit tijdens het uitlezen hernoemd, uitgeschakeld,
verwijderd, vervangen of aan een andere installatie toegewezen, dan wordt de
export afgebroken. Kies de actuele selectie en probeer opnieuw. Ook het ontladen
van de integratie breekt het resultaat af.

## English

The beta candidate supports day, week and month exports, up to 31 days, using the
existing read-only Recorder action. Choose the installation and enabled entities;
explicit timezone-aware dates are required. Output is UTC. Limits remain 64 entities,
5,000 rows and 1 MiB. Truncation and unqueried entities are explicit. Recorded units
are optional; absent history or units are never inferred. Export does not change
retention, statistics or recorded values. Ownership changes during the query abort
the response. Installed HA dev48 still has its original 24-hour limit.
