# B06 — ingetrokken veiligheidsfeiten blijven ingetrokken

## Afgewerkt in software

De zes afzonderlijk gedateerde feiten in `HydraulicFeedbackGate` zijn:
limietstatus, foutstatus, warmwaterstatus, watertemperatuurdoel, kraan/readiness-
terugmelding en onafhankelijke flow. Hun oorspronkelijke meettijden blijven apart.

Vóór de reparatie kon een toekomstig meettijdstip eerst worden afgewezen en later,
zonder nieuw bericht, alsnog als vers worden geaccepteerd zodra de klok die tijd
bereikte. Dat gebeurde zowel zonder eerder geaccepteerd feit als na een geldig
vorig feit. Ook kon een teruglopende lokale klok achter de vroege eigenaar-/
sessiestartcontrole verborgen blijven, waarna nieuw bewijs weer werd toegelaten.

Per feit wordt nu apart onthouden tot welke afgewezen meettijd bewijs is ingetrokken.
Een latere klokwaarde herstelt dat bewijs niet. Alleen een strikt nieuwere eigen
acquisitie kan het vervangen. De geaccepteerde acquisitiemarkeerders worden niet
verhoogd door een afgewezen aggregate. Ongewijzigde andere feiten behouden hun
oude deadline. Alle tegelijk afgewezen velden krijgen hun eigen intrekking.
Er wordt niet bij de tijdstempel opgeteld; ook een maximale uint64-tijd kan niet
omklappen naar geldigheid. Zo'n fout kan het betrokken feit geblokkeerd houden;
een verkeerde producerklok moet worden hersteld, niet administratief goedgekeurd.

De lokale monotone klok wordt vóór de eigenaarcontrole beoordeeld. Een vreemde
snapshot kan nog steeds geen inhoud of meettijd als bewijs leveren. Een eenmaal
vastgestelde klokterugloop blijft voor deze gate ongeldig. Bronherstel vereist
bestaande herinitialisatie en nieuwe kwalificatie, geen automatisch hervatten.

De gedeelde veiligheidsmelding in `ShadowController` gebruikt dezelfde controle
bij gewone zonepolicy én bij bevestiging van een storing. Een toekomstige,
ontbrekende, oudere of tegenstrijdige acquisitie trekt het bewijs in. Dezelfde
meettijd met andere waarden is geen nieuwe acquisitie. Een tweede codepad kan
hierdoor geen eerder afgewezen veiligheidsmelding alsnog als toestemming gebruiken.
De oorspronkelijke levensduur van een geldige herhaalde melding blijft behouden.

## Bewijs

Zes nieuwe hydraulische regressietests, waarvan vijf vóór de reparatie faalden:

- Alle zes toekomstige feiten, met en zonder eerder geaccepteerd bewijs.
- Onaangetaste levensduur van andere feiten; vreemde eigenaar kan geen toekomstige
  acquisitiegrens voor deze eigenaar vastleggen.
- Gelijktijdige toekomstige feiten; slechts één vervangen veld herstelt de rest niet.
- Klokterugloop vóór de oorspronkelijke sessiestart.
- Klokterugloop tijdens een afwijzing wegens verkeerde eigenaar.
- De echte ShadowController blijft het afgewezen bericht als reordered rapporteren
  en verleent geen fysieke uitvoer.

Daarnaast zes nieuwe regressies voor zonepolicy en storingsbevestiging:
future catch-up, terugvallen op oudere verse data, ontbrekende acquisitietijd,
afnemende acquisitietijd, veranderde waarden met dezelfde meettijd en hergebruik
via storingsbevestiging. Alle zes faalden tegen het oorspronkelijke gedeelde codepad.
De tests gebruiken expliciete acquisitietijden na de bestaande sessieopbouw;
het fixture-sentinel voor automatisch actuele tijd is geen cachebewijs.
Twee bestaande acceptatieproeven zijn aangescherpt met een nieuwe acquisitietijd
voor gewijzigde zomer-/DHW-feiten; de stop- en niet-automatisch-herstart-eisen blijven.

Na reparatie: 677 native tests; E32- en ESP32-firmwarebuild gecontroleerd. Bewijs:
`out/safety-fact-retirement-20261024/before-final.log`,
`seasonal-original-before-final.log`, `final-native.log`, `e32-build-final.log`,
`esp32dev-build-final.log` en `RESULT.json`. De eerste foutuitvoeren bevatten ook
de native harnasmelding SIGHUP na de expliciete assertionfouten; de definitieve
677-casussuite is zonder fouten afgesloten.

## Nog open voor B06

Dit sluit de softwarefout en regressies, niet de hele praktijkpoort.
Werkelijke gedateerde producenten, bronkwalificatie, beoordeeld installatieprofiel,
onafhankelijke limieten, afgiftepad, minimumflow, DHW-prioriteit en naloop-/stopbewijs
blijven vereist. Nieuwe acquisitie betekent een echte waarneming, niet het opnieuw
dateren van een cachewaarde. Er zijn geen netwerk-/apparaatopdrachten, herstart,
flashpoging of runtimewijziging uitgevoerd. HA dev38 en E32 alpha28 blijven de
laatst gecontroleerde installatie; de nieuwe code is nog niet geïnstalleerd.

## Compatibiliteitscorrectie na volledige HA/FW-proef

Uptime nul kan een echte acquisitietijd zijn. De bekende-statusvlaggen zijn bepalend;
een lege interne tijdgrens wordt nu met een afzonderlijke aanwezigheidsmarkering
onderscheiden van een echte tijd nul. Een ingetrokken nul-acquisitie blijft
net als iedere andere tijd ingetrokken tot strikt nieuwer bewijs beschikbaar is.
Twee extra native regressies en de echte HA/FW-proeven bewaken dit. Details en
actuele gecombineerde resultaten: [ketelrapporten](KETELRAPPORT-VOLGORDE-20261024.nl.md).
