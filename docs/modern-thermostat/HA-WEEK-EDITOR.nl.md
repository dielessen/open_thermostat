# Native weekprogramma-editor

> **Statusupdate 20 oktober, na onderhoud11686:** de Engelse kamer-/grenzen-/
> weekeditor is inmiddels in productie-HA geïnstalleerd en technisch geverifieerd.
> Runtime/transport/actuatie blijven uit; zichtbare productie-GUI en fysieke
> bron→E32→ACK-acceptatie blijven open. [Actueel werkbord](WORKBOARD.nl.md).
> De oorspronkelijke test-/uitrolbeschrijving hieronder is gedateerd bewijs;
> formuleringen “nog niet in productie” beschrijven die eerdere uitvoeringsronde.


## Native gebruikersroute

1. Open de bestaande OpenThermostat **v1 shadow** integratie, voeg een Room-subentry toe of kies haar bestaande Edit room bindings.
2. Kies eigen sensor/TRV/optionele bediening en kamerbasis/grenzen zoals voorheen. Bij **Week program** kies `Edit a local week program` (`program_action=edit_week`). Laat Optional native Schedule helper leeg. Nog niets wordt opgeslagen.
3. Native menu: Add time block / Edit time block / Delete time block / Save program and room bindings / Cancel without saving.
4. Blok: één of meerdere dagen, native Start time/End time, temperatuur binnen kamergrenzen. Voor de eind-daggrens kies **End at midnight (ignore End time)**; de opgeslagen grens is exact 86400. Overnacht moet als twee blokken worden ingevoerd. Aangrenzende blokken mogen wel. Meerdere dagen zijn expliciete kopieën: zeven geselecteerde dagen tellen als zeven dagblokken van maximaal 28/week.
5. Edit/Delete kiest een bestaand dagblok uit een native selectlijst. Wijzigingen blijven in de draft tot Save. Cancel/flow-abort bewaart de oorspronkelijke kamer; ook eerdere wijzigingen aan de bindings in dezelfde draft worden dan niet opgeslagen.
6. Save valideert opnieuw huidige entityreferenties, uniciteit/roomlimiet, kamergrenzen en een werkelijk compileerbare 15-daagse horizon met max128transities. Native subentry/Core Store bewaart het hele resultaat. Bij conflict/verwijderde bron/ongeldig programma geen gedeeltelijke save.

## Expliciet één bron

Geen lokale week + Schedule-helper tegelijk. Een bestaande gekoppelde helper blijft ondersteund en gebruikt ongewijzigd native get_schedule. Om daarvan naar de lokale editor te wisselen: maak de helperselector leeg en kies Edit local week. Om terug te wisselen: kies **Remove local week program** en kies eventueel de helper in hetzelfde roomformulier. De derde mogelijkheid is geen programma: alleen het bestaande basisdoel. Bestaande kamers zonder week_program houden hun bestaande serialisatie; geen verplichte migratie.

## Tijd/export/uitvoering

De lokaal opgeslagen week gebruikt alleen integer start/eindseconden en centi°C, geen HA-entiteitsnaam in firmwarekanalen. Geen nieuwe wirekeys. De bestaande pure compiler produceert dezelfde timezone/policy/UTC-overgangen; de bestaande duurzame mapping/configtransaction verzorgt ACK/revision. De bestaande native dagelijkse UTC-refresh materialiseert opnieuw; er is geen nieuwe scheduler/daemon. Alleen E32 voert schema en regeling uit. De lokale editor draait niet zelf verwarmingsbeslissingen.

Policy blijft wall-clock-membership/v1: spring-gap niet-bestaande tijden overslaan, gedeeltelijke gap vanaf eerste bestaande passende tijd, beide herfstfolds apart inclusief basisdoel in het tussengat. Alleen UTC en Europe/Amsterdam/2000–2099 zoals de bestaande compiler. Gaten gebruiken het kamerbasisdoel. Export eindigt exclusief na 15 UTCdagen; de firmware stopt normale schemavraag bij expiry/ongeldige tijd.

De bestaande totale 4096-byteconfig/512-node-/8192-bytewiregrenzen blijven doorslaggevend. Een opgeslagen geldige kamerweek is geen garantie dat iedere achtkamerconfig in het totale firmwarebudget past. De compiler-/transportadmissie blijft fail-closed; geen uitbreiding van limieten of fysieke outputs. Deze versie is lokaal én in de geïsoleerde test-HA getest; nog niet in productie geïnstalleerd.

## Uitgevoerde softwareacceptatie en resterende grens

De exacte actuele repo-suite is geverifieerd:143nativePASS,1bestaande broker-
optinSKIP,38compiler/sharedtestsPASS. Bestaande daadwerkelijkeC++runner bewijst
configACK, weekdoel2200 en terugtrekken normale vraag bij exclusieveexpiry.

Echte hostChromium-GUI: multidayblocks, blokedit/delete, midnight86400, Save,
explicietCancel inclroomnaam, zichtbare overlap-/timeorder-/targetrangefouten,
Removeweek en eigenroomDelete. Gecontroleerd met gefilterde officiëleHAStore
en aparte nativeAPI/WSreadbacks. Na echte testHArestart heropent een frisse
browser precies de opgeslagenweek en dezelfdeID. Alle sourcefixtures bleven
eerst behouden; exacte testfixturecleanup wordt apart geverifieerd.

GUItests moeten de multipleDays-popup expliciet sluiten vóór invoer elders,
anders kan de focus-trap invoer naar de popupzoekbalk sturen. Native switches
zijn ook met Space op de echte focusbarecontrol te bedienen; geen forceclick
of DOMsetter gebruiken. Een screenshot is pas bewijs na visuele controle.

Geen Schedulehelper live aangemaakt; dual-sourceconflict is apartnative getest.
Unknown fixtures leveren geen fysiekebronkwalificatie. Geen productie/E32/
actuatievrijgave; actualshadow-/fysieke profielen blijven afzonderlijke gates.
