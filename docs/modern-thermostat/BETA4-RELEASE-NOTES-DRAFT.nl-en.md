# E32 V2 beta4 — concept: automatisch sessieverval en toegangsherstel
<!-- user-release-notes:v1 -->

Concept voor de volgende E32-release. Nog niet bevroren, gepubliceerd of
geïnstalleerd. De bestaande beta.3-download blijft ongewijzigd.

## Nieuw

- **Toegang herstellen bij vier bezette sessieplaatsen.** Op de aanmeldpagina
  verschijnt een optie om eerdere websessies te beëindigen en opnieuw aan te
  melden. Vink die bewust aan en voer je gebruikersnaam en wachtwoord opnieuw
  in. Andere browsers worden afgemeld; de apparaatinstellingen blijven behouden.
- **Altijd een ketelillustratie bij een gekozen profiel.** Zonder eigen foto
  verschijnt een algemene, merkloze ketelillustratie. Dat gebeurt ook als een
  productfoto niet laadt. De algemene illustratie werkt lokaal en offline,
  op het startscherm en bij Mijn ketel.

## Opgelost

- **Achtergelaten sessies houden geen plaats zeven dagen bezet.** Na 30 minuten
  zonder geldige aanvragen van die browser vervalt de sessie automatisch. Een
  dashboard dat blijft communiceren behoudt toegang, tot maximaal zeven dagen.
- **Duidelijkere aanmeldmelding.** De uitleg spreekt over opgeslagen sessies,
  niet over vier browsers die op dat moment open zouden staan. Gewoon aanmelden
  meldt andere browsers niet af; herstel vereist een afzonderlijke bewuste keuze.
- **Terugval bij ontbrekende productfoto.** Het algemene beeld vervangt een
  kapotte afbeelding en toont geen bronvermelding van de ontbrekende foto.
  Een beschikbare modelgebonden foto behoudt zijn eigen afbeelding en bron.

## Bijwerken en gebruik

Na publicatie: werk alleen de E32 bij via zijn normale GitHub-updater. Voor deze
wijzigingen is geen nieuwe HA-installatie nodig; de reeds gepubliceerde HA0.4.0b3
blijft ongewijzigd. Controleer na de nieuwe boot versie en instellingenbehoud.

Sessieherstel is geblokkeerd tijdens een ketelproef, een lopende firmware-update
of zolang een nieuwe firmware nog niet is bevestigd. Een apparaatreset of nieuwe
installatie is voor toekomstig sessieherstel niet nodig. Deze release geeft geen
fysieke ketel-/kraansturing vrij. Aanpassing van het warmteproefprofiel voor de
ketel zonder digitale druksensor blijft afzonderlijk open werk.

## English

**New:** explicit recovery when all four saved web sessions are occupied. Select
the recovery option and re-enter the username and password to sign other browsers
out. Device settings are preserved. A local, unbranded boiler illustration appears
when the selected profile has no photo or its photo fails to load.

**Fixed:** abandoned sessions expire after 30 minutes without accepted authenticated
requests. Communicating dashboards remain signed in for up to seven days. Expired
sessions cannot be revived by late requests. Login messages describe saved sessions
rather than currently open browsers. Ordinary login does not evict other sessions.

**Updating:** draft only; after publication use the normal E32 GitHub updater and
verify the new boot and retained settings. These changes need no new HA version.
Recovery is unavailable during an active boiler trial, firmware update or unconfirmed
firmware boot. No boiler/valve control is enabled.
