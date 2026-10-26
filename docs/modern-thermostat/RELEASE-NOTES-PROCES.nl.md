# Releasenotities die gebruikers begrijpen

Elke firmware- en Home Assistant-release krijgt een korte Nederlandse beschrijving
met een Engelse samenvatting. De tekst beschrijft wat iemand na bijwerken merkt.
Gebruik de zichtbare Nederlandse menunamen in het Nederlandse deel.

De vaste opbouw is:

- **Nieuw:** concrete functies en waar je ze vindt. Is er niets nieuws, zeg dan
  dat het een onderhoudsupdate is. Noem voorbereiding in code geen beschikbare functie.
- **Opgelost:** welk probleem de gebruiker had en wat nu beter gaat. Alleen een
  werkelijk herstelde fout noemen; een extra test is op zichzelf geen productfix.
- **Bijwerken en gebruik:** welke versie/component nodig is, instellingenbehoud
  en hoogstens de relevante gebruiksbeperking. Geen interne opleverchecklist.
- **English:** dezelfde veranderingen en beperkingen, kort in het Engels.

Geen tellers van tests, brondigests, interne protocoltermen, geheugenadressen of
lange opsommingen van projecteisen in de hoofdtekst. Technisch bewijs blijft
beschikbaar onder een uitklapbaar onderdeel of een aparte documentatielink.
Releasenotes staan vóór de downloadtabel.

De bron staat in `RELEASE-NOTES.md` en `HA-RELEASE-NOTES.md`. De actuele sectie
begint met de eigen versie en de marker `user-release-notes:v1`. De bestaande
publicatiecontrole weigert een nieuwe publicatie zonder de vier onderdelen.
Een versie ophogen zonder bijpassende notities blijft eveneens geblokkeerd.

De release-organizer leest deze bewust geschreven tekst uit de bron en bewaart
haar bovenaan. Daardoor vervangt later opruimen de duidelijke tekst niet weer
door een technische samenvatting. Hij verzint zelf geen features uit code of
oude bewijsregels. Bestaande oorspronkelijke notities blijven ongewijzigd in het
uitklapbare archief. Tags, downloads en gepubliceerde programmabestanden worden
bij een tekstcorrectie niet vervangen.

Controleer vóór aanpassen op GitHub de volledige bewerkplanning, versies en
claimdekking. Bewaar de oude metadata. Lees na aanpassing de echte publieke
beschrijvingen terug, controleer tags/status/downloadidentiteiten, de JSON-omvang
voor de updater en een tweede organizerplanning zonder wijzigingen.

Historische releases hebben daarnaast een per-versie geredigeerde samenvatting in
`USER-RELEASE-NOTES.json`, inclusief de SHA256 van de oorspronkelijke notities.
De CLI gebruikt deze samenvattingen ook voor archieven en bronpakketten. Als de
onderliggende historische tekst verandert, stopt hij voor herbeoordeling. Bekende
fouten blijven zichtbaar bij de versie waarin ze voorkomen, met verwijzing naar
de latere oplossing. Een bronpakket blijft uitdrukkelijk geen installatiebestand.
