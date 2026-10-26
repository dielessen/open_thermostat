# Releasenotities die gebruikers begrijpen

Elke nieuwe firmware- en Home Assistant-release krijgt een korte **Engelse**
beschrijving. Ook GitHub-releasetitels, downloadtabellen, README, commits en PR's
blijven Engels, volgens de gebruikersvoorkeur van 26 oktober 2026. Het gesprek
en interne Nederlandse ontwerpdocumenten mogen Nederlands blijven. De tekst
beschrijft wat iemand na bijwerken merkt; gebruik de Engelse menunamen.

De vaste opbouw is:

- **New:** concrete functies en waar je ze vindt. Is er niets nieuws, zeg dan
  dat het een onderhoudsupdate is. Noem voorbereiding in code geen beschikbare functie.
- **Fixed:** welk probleem de gebruiker had en wat nu beter gaat. Alleen een
  werkelijk herstelde fout noemen; een extra test is op zichzelf geen productfix.
- **Updating:** welke versie/component nodig is, instellingenbehoud
  en hoogstens de relevante gebruiksbeperking. Geen interne opleverchecklist.
- **Limitations:** de relevante resterende beperkingen, zonder voorbereide code
  als vrijgegeven functie voor te stellen.

Geen tellers van tests, brondigests, interne protocoltermen, geheugenadressen of
lange opsommingen van projecteisen in de hoofdtekst. Technisch bewijs blijft
beschikbaar onder een uitklapbaar onderdeel of een aparte documentatielink.
Releasenotes staan vóór de downloadtabel.

De bron staat in `RELEASE-NOTES.md` en `HA-RELEASE-NOTES.md`. De actuele sectie
begint met de eigen versie en de marker `user-release-notes:v2:en`. De
publicatiecontrole ondersteunt deze vier Engelse onderdelen en weigert een
onvolledige tekst. Bestaande gepubliceerde `v1`-notities en hun tweetalige
historie blijven geldig; ze worden niet achteraf als nieuwe release herschreven.
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

## GitHub-hoofdpagina bij iedere release

Werk bij iedere release de Engelse `README.md` inhoudelijk na: beschikbare
functies, voorbereiding, roadmap, installatie, beperkingen en screenshots.
Een softwarevoorbereiding is geen fysieke acceptatie. Houd gepubliceerde
downloads en laatst vastgelegde installatieacceptatie afzonderlijk zichtbaar.

`scripts/sync_readme_releases.py --write` ververst lokaal het gemarkeerde blok
met de nieuwste werkelijk gepubliceerde E32- en HA-versie, hun links en de
bijbehorende clone-opdracht. Conceptreleases tellen niet mee. Met `--check`
controleer je de links vóór afronding.

De twee publicatiejobs voeren na publicatie automatisch `--apply` uit. Dat
werkt uitsluitend dit blok in de README op de standaardbranch bij, samen met
de bijbehorende README-checksum in de broninventaris. Beide staan in één commit
met een fast-forward-only branchupdate en herlezing tegen gelijktijdige wijzigingen. De overige tekst en
firmwarebron worden niet overschreven. Dit is ook nodig zolang de nieuwste
firmwaretags verder zijn dan `main`. De workflow `Refresh project page` dekt
handmatig gepubliceerde releases en biedt een handmatige herhaalactie.
GitHub start bij publicatie met `GITHUB_TOKEN` geen nieuwe release-workflow;
daarom blijft de expliciete stap in beide publicatiejobs noodzakelijk.

Nieuwe versielinks worden automatisch bijgewerkt; inhoudelijke functieclaims
blijven een bewuste controle bij iedere release. De tests controleren selectie
van publieke versies, behoud van de rest van de pagina en gelijktijdig bewerken.
