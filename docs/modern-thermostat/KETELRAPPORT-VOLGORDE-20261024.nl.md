# Ketelrapporten: oorspronkelijke volgorde en blijvende intrekking

## Afgewerkt voor B07–B08 en R15

De Classic-monitor bewaakte eerder de oorspronkelijke ontvangstdatum, maar een
later verwerkt ouder telegram kon een nieuwere waarde overschrijven. Daardoor
kon een ouder uit-bericht een nieuwere lopende branderstatus verbergen en een
stopbevestiging veroorzaken. Ook kon een ouder bericht actuele DHW-prioriteit
verbergen vóór de laatste proef-dispatchcontrole. Dit is een gereproduceerde
softwarefout, geen bewijs dat het eerdere gemelde pendelen hierdoor kwam.

De monitor beoordeelt nu ieder veld afzonderlijk:

- Een ouder veld overschrijft geen nieuwere waarde of acquisitietijd.
- Een ouder deeltelegram kan nog wel een tot dan toe ontbrekend veld aanvullen,
  met zijn eigen oorspronkelijke tijd en levensduur. Er is geen globaal leesfilter.
- Tegenstrijdige waarden op dezelfde acquisitietijd worden voor dat veld ongeldig.
  Een herhaling van één van beide waarden herstelt het veld niet; strikt nieuwer
  bewijs is vereist. Een eerder ongeldig sentinel krijgt evenmin een geldige
  waarde door een conflicterend bericht met dezelfde tijd.
- Ieder toegelaten rapport blijft meetellen. De meest recente ontvangst en
  telegrammetadata lopen niet terug door een ouder verwerkt bericht.

De bestaande proefpolicy en poll-executor gebruiken deze monitor. Tests via die
productiepaden bewijzen dat oude/tegenstrijdige berichten geen positieve vraag
kunnen toelaten of baseline/stop kunnen bevestigen. Een werkelijk nieuw uit-
rapport kan de bestaande stopvoorwaarden nog steeds vervullen.

## HA-overdracht eveneens gecorrigeerd

HA kon een veranderde veldgroep afwijzen, maar de oude waarde later weer tonen
wanneer een andere veldgroep het globale invalid-vlaggetje wiste. Dat is nu
voorkomen met intrekking per opgeslagen acquisitie. Na ongeldige velddata moet
ieder betrokken veld strikt nieuw bewijs krijgen; een andere groep of hogere
publicatiesequentie herstelt oude waarden niet.

Een geldige firmware-intrekking naar null op dezelfde acquisitietijd wordt als
beperking geaccepteerd, met behoud van de oorspronkelijke deadline. Alleen de
betrokken entiteit wordt onbeschikbaar; overige geldige velden blijven zichtbaar.
De nulwaarde, eenheid, bronmarkeringen, 69 entiteitidentiteiten en het bestaande
schema blijven behouden. Er worden geen opdrachten of extra subscriptions gemaakt.

## Verificatie

Negen nieuwe native regressies faalden vóór de reparatie. Een extra C++-contracttest
controleert dat de null-intrekking met oorspronkelijke acquisitietijd via het
bestaande veldgroepschema geldig blijft. Zes nieuwe HA-regressies faalden tegen
de oude cache; de gerichte HA-set telt 31 geslaagde gevallen. Twee bestaande
native loops hebben nu ieder een eigen monitor, passend bij hun onafhankelijke
synthetische sessies, in plaats van de tijd van dezelfde monitor terug te zetten.

De volledige HA/FW-proef vond ook een regressie uit de vorige veiligheidswijziging:
uptime nul was als ontbrekende acquisitie behandeld. Uptime nul kan echt zijn;
de bestaande bekende-statusvlaggen blijven bepalend. Afzonderlijke interne
markeringen onderscheiden nu een lege van een ingevulde/ingetrokken tijdgrens.
Twee extra native tests bewaken geldige én ingetrokken nul-acquisities. Twee HA-
interopproeven dateren gewijzigde veiligheidsfeiten nu als nieuwe acquisities;
de eis dat zomer/all-off/DHW een boost tegenhouden blijft behouden.

De definitieve native suite telt 689 geslaagde tests. E32- en ESP32-firmwarebuilds
zijn geslaagd. Op elk van HA Core 2026.10.2 en 2026.10.3 slagen 2195 gevallen, zonder fouten of
overgeslagen tests. De geïsoleerde localhost-testbroker is na beide suites gestopt
en verwijderd. De volledige HA/Core-resultaten staan in het resultaatmanifest:
`out/boiler-report-order-20261024/RESULT.json`. Voorproeven: `before-final.log`
en `ha-before.xml`; definitief: `final-native.log` en de beide Core-XML's.

## Grenzen

Geen ketel-, kraan- of UART-opdrachten, update, herstart of runtimewijziging
uitgevoerd. De laatste gecontroleerde installatie blijft HA dev38/E32 alpha28;
deze correctie is voorbereid voor de volgende gezamenlijke bundel. B07–B09
vereisen nog een beoordeeld profiel, adres/masker, elektrische zender, exclusief
bus-eigenaarschap, afgifte-/minimumflow-/naloopvoorwaarden en fysieke stopproef.
Alle E32-zend- en actuatoruitgangen blijven geblokkeerd. De watchdogoorzaak en
het gemelde pendelen blijven afzonderlijke open onderzoeken.
