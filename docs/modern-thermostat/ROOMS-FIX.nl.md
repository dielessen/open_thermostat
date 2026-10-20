# Kamerbeheerherstel — 20 oktober 2026

De eerdere E32-installatie maakte de kamerlijst leeg, maar liet een
voorbeeldprogramma met zeven niet-bestaande kamer-ID's achter. Dit veroorzaakte
`Room not found` en blokkeerde het opslaan van de kamerlijst. Nieuwe E32-images
beginnen nu met zowel een lege kamerlijst als lege programma's. De buildcontrole
wijst achtergebleven voorbeelden af.

## Gebruik

- **Rooms**: kamer toevoegen, naam wijzigen en **Save rooms**. Een kamer-ID blijft
  gelijk bij hernoemen. Succes wordt pas na teruglezen gemeld.
- **Programs**: bij oude verwijzingen verschijnt een waarschuwing met
  **Remove missing rooms**. Dit verwijdert uitsluitend instellingen van ontbrekende
  kamers uit het gekozen programma. Kies daarna **Save program**. Herhaal voor
  andere programma's met de waarschuwing; echte kamers blijven behouden.
- **Delete room**: sla kamerwijzigingen eerst op. De bevestiging noemt de
  programma's waaruit de kamerinstellingen ook worden verwijderd. Na bevestigen
  worden die programma's één voor één opgeslagen en teruggelezen, daarna pas de
  kamer. Andere kamers en hun programma-instellingen blijven staan.
- Een fout is geen succesmelding. Bij gedeeltelijke uitvoering noemt de melding
  reeds aangepaste programma's. Herlaad de pagina en controleer voordat je
  opnieuw probeert. Opslag is geen transactie over meerdere bestanden.

De oudere firmware krijgt dit herstel niet vanzelf. Een firmware- én
bestandssysteemupdate is nodig voor de nieuwe interface en servermelding.
Een factory-installatie met volledig wissen begint leeg en verwijdert bestaande
instellingen; voer dat niet uit om alleen oude programma's op te ruimen.

Wifi-herstel en gevraagde toegangsgegevens blijven behouden. Geen wijziging aan
de EMS-/TRV-uitvoerblokkades. Softwareproeven vervangen de fysieke kamer-, wifi-
en herstartproef op Marks bord niet. Houd EMS los tijdens deze testversie.

## Home Assistant

De meegeleverde integratie herstelt ook een aparte legacy-fout: verdwenen kamers
blijven onbeschikbaar na een algemeen online-bericht. Historische entiteiten,
unieke ID's en tellers blijven behouden; dezelfde kamer opnieuw toevoegen maakt
geen duplicaten. Een verwijderde kamer kan geen temperatuurcommando meer sturen.
Native shadow-kamers zijn afzonderlijk getest op aanmaken, wijzigen, verwijderen
en onbekende ID's. De integratie is niet automatisch in productie geïnstalleerd.
