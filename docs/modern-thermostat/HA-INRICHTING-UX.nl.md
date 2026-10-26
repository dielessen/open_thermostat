> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Eén installatie, duidelijke ruimtes — HA-inrichting

## Keuze 22 oktober: één kamerprogramma

Mark laat de alternatieve HA Schedule-helper weg. Het normale toevoegen,
aanpassen en het grafische kamerscherm bieden uitsluitend het ingebouwde
weekprogramma, met temperatuur per blok en de basistemperatuur erbuiten.
Geen programmabronselectie of Schedule-entity onder Geavanceerd. Bestaande
opgeslagen externe koppelingen worden behouden en expliciet als bestaand
extern programma getoond; deze UI-keuze verwijdert geen HA-helper of historie.


Productaanvulling van Mark, 22 oktober 2026. Onderdeel van [PLAN](PLAN.nl.md),
vooral R01/R04/R06/R18/R27/R29. Dit document beschrijft de gewenste inrichting;
het [klikbare schermontwerp](ontwerp/ha-inrichting.html) gebruikt alleen fictieve
voorbeeldgegevens en voert geen HA- of apparaatopdrachten uit. Het is geen
geïnstalleerde integratie of besluit om een tweede frontend te bouwen.
De native radiator-/centrale route en het grafische kamerscherm zijn inmiddels
geïmplementeerd; actuele
bron-/installatiebewijzen en resterende grenzen staan in de
[testkandidaat](TESTKANDIDAAT-20261022.nl.md).
Het volledige gewenste product hieronder is daarmee nog niet geaccepteerd.

## Direct de normale productinrichting — correctie van Mark

De E32 staat volgens Mark los van de ketel; dit project draait geen productie.
We configureren daarom direct de normale OpenThermostat-installatie zoals het
eindproduct bedoeld is. Geen aparte schaduwwizard, shadowentry of latere tweede
productie-inrichting. De hieronder beschreven route is dezelfde route voor de
huidige ontkoppelde ontwikkelopstelling en het uiteindelijke product.

Een niet aangesloten regelaar of ketel krijgt status zoals **Niet verbonden** of
**Configuratie nog niet toegepast** met een begrijpelijke vervolgstap. Kamers,
programma's en centrale instellingen kunnen wel worden ingericht. Bestaande
testentries mogen na gerichte back-up plaatsmaken voor één schone projectinrichting;
bruikbare apparaten hoeven daarvoor niet opnieuw aan HA toegevoegd te worden.

Technische bron-/versiecontrole en gewenste/toegepaste configuratie blijven in
de gewone productroute geïntegreerd. De huidige `v1_shadow`-/`shadow_enabled`-
mechaniek stuurt ook werkelijk gedrag; alleen schermnamen veranderen is geen
implementatie. Keteluitvoer en fysieke aansluiting worden afzonderlijk beproefd.

## Historische probleemanalyse vóór dev3

De bron biedt in `async_get_supported_subentry_types` tegelijk `room_setup`,
`zone` en `heating` aan. De gewone radiatorwizard, technische kamerbindingen en
centrale verwarmings-/groepseditor verschijnen dus naast elkaar als toevoegkeuze.
De radiatorwizard ondersteunt nog geen vloerkamer en verwijst complexe kamers
naar de geavanceerde route. Die tussenstand is geen gebruiksvriendelijk eindproduct.

Oude kamers volgen een andere route: `climate.py` maakt ze vanuit MQTT
`<prefix>/room_data` aan; ze zijn geen verwijderbare HA-kamersubentries. Verdwenen
kamers worden daar alleen onbeschikbaar gemarkeerd. Een losse entity verwijderen
beëindigt de bron niet en een volgend bericht kan haar opnieuw laten verschijnen.
Dit verklaart een mogelijke oorzaak; de identiteit van Marks oude kamer moet
afzonderlijk uit verse HA-gegevens worden vastgesteld.

De HA-specialist heeft op **22 oktober 2026, 13:23 CEST** alleen lezend twee
entries vastgesteld: de legacy `ib-therm` en de testentry met Badkamer en één
centrale verwarmingssubentry. Runtime en kameractuatie staan uit. De legacy hub
heeft 40 telemetrie-entiteiten; er is geen actuele oude kamer-ID/naam vastgesteld.
De tekst `woonkamer_` in entity-ID's is daarvoor geen bewijs. Er is niets
verwijderd of gewijzigd. Die specifieke bronidentificatie blijft dus open vóór
een echte opruimactie; de algemene ontwerp-/bronbevinding hierboven blijft geldig.

## De gewone structuur

```text
OpenThermostat — mijn installatie
├── Overzicht: toestand, wat gebeurt er en waarom?
├── Installatie instellen: ketel en gedeelde verwarmingsinstellingen
├── Ruimtes
│   ├── Ruimte toevoegen → begeleide wizard
│   └── Bestaande ruimte → aanpassen / weekprogramma / verwijderen
└── Geavanceerd en diagnose
    └── Alleen relevante technische instellingen en oude configuratie opruimen
```

Er is één centrale installatieconfiguratie per regelaar, geen handmatig toe te
voegen tweede ketelconfiguratie. Het standaard toevoegmenu heeft één begrijpelijke
actie: **Ruimte toevoegen**. Centrale instellingen openen via **Installatie
instellen**; bestaande ruimtes hebben een duidelijke wijzig- en verwijderroute.
Interne zones, verwarmingsgroepen, MQTT-contracten en technische modi zijn geen
keuze die een gewone gebruiker eerst moet begrijpen.

Gebruik native HA-config/options/subentryflows en selectors waar zij passen.
De bestaande centrale configuratie blijft de enige eigenaar van haar gegevens;
verplaats de toegang en presentatie, maak geen tweede opslagmodel. De wizard
bouwt de interne ruimte-/actuator-/circuitkoppeling automatisch op. Bestaande
verwarmingssubentries worden gemigreerd of hergebruikt, nooit naast een nieuwe
tweede centrale configuratie gezet. Bij een expliciet schone testinrichting mogen
oude projectsubentries na back-up worden vervangen in plaats van gemigreerd.

## Installatie instellen

| Instelling | Wat doet dit? | Impact en presentatie |
| --- | --- | --- |
| Naam installatie | Herkenbare naam in HA. | Alleen presentatie; verandert geen regeling of apparaatidentiteit. |
| Ketel/verbinding | Koppelt één bestaande regelaar en toont herkend profiel en verbindingsstatus. | Onbekende of nog niet geteste ondersteuning wordt benoemd; kiezen is geen fysieke kwalificatie of vrijgave. |
| Weersafhankelijk regelen | Past het waterdoel aan het buitenweer aan. | Geldt centraal voor gekoppelde circuits; alleen instelbaar met passend profiel en bruikbare bron. Uit betekent geen weerinvloed, niet automatisch geen warmtevraag. |
| Buitentemperatuurbron | Kiest de bron voor weersafhankelijke regeling. | Leg uit welke waarde wordt gebruikt en wat bij uitval gebeurt. Toon herkomst en actuele beschikbaarheid. |
| Centrale grenzen en stooklijn | Begrenzen en bepalen de gevraagde watertemperatuur. | Onder Geavanceerd, met installatieprofiel en effect op alle betrokken ruimtes; geen universele veilige getallen suggereren. |
| Uitvalbeleid en bronleeftijd | Bepalen wanneer data ongeldig is en welk begrensd beleid volgt. | Onder Geavanceerd; korte begrijpelijke tijdseenheden, geen invoer in milliseconden. Benoem comfort-/beschikbaarheidsgevolg en installatievoorwaarden. |

Eén gedeelde ketel betekent niet dat radiatoren en een lage-temperatuurvloer
dezelfde watergrenzen mogen krijgen. Alleen indien werkelijk aanwezig kan een
mengcircuit eigen grenzen hebben. De wizard vraagt daarvoor herkenbare
installatiekenmerken en toont zo nodig dat controle ontbreekt; hij verzint geen
mengklep, pomp, doorstroming of temperatuurbeveiliging.

## Ruimte toevoegen of wijzigen

1. **Ruimte:** kies een bestaande HA-ruimte of geef een naam. Bestaande koppelingen
   worden herkenbaar aangeboden; hernoemen behoudt de identiteit.
2. **Verwarming:** kies Radiator, Vloerverwarming of Combinatie. De keuze bepaalt
   volgende velden en een passend beschikbaar profiel. Niet ondersteunde profielen
   zijn herkenbaar onbeschikbaar met reden, nooit een werkende belofte.
3. **Sensor en bediening:** kies de representatieve temperatuursensor en één of
   meerdere radiatorkranen, vloerkleppen of beide. Toon alleen passende apparaten,
   met vriendelijke naam, ruimte en beschikbaarheid. Een knop/wandbediening kan
   optioneel worden toegevoegd; een losse sensor is geen bedieningsknop.
4. **Temperatuur en programma:** basisdoel, optioneel weekprogramma en later
   wijzigbare comfortkeuzes. Elk weekblok toont tijd en temperatuur. Geavanceerde
   grens-/kalibratie-/broninstellingen blijven standaard dichtgeklapt.
5. **Controleren en opslaan:** samenvatting in gewone taal van ruimte, type,
   bronnen, kranen/kleppen, programma en effect. Eén opslagactie, terug om te
   wijzigen en annuleren zonder gedeeltelijk opgeslagen ruimte of losse groep.

Bij aanpassen staan bestaande waarden en eventueel ontbrekende apparaten zichtbaar.
De wizard behoudt onbekende geavanceerde instellingen of toont dat een begeleide
migratie nodig is; hij wist ze niet om de eenvoudige route te laten slagen.
Instellingen wijzigen tijdens bedrijf blijft het productdoel: de bestaande
validatie, configuratietransactie en exacte toegepaste terugmelding moeten daarvoor
eerst bewezen zijn. Opslaan mag niet ongemerkt de regeling activeren.

## Uitleg bij iedere instelling

Iedere zichtbare instelling heeft bij het veld een korte uitleg **wat het doet**
en **wat veranderen betekent**. Een infopictogram mag verdieping bieden maar
vervangt de noodzakelijke uitleg niet. Dit geldt ook voor Geavanceerd.

| Voorbeeld | Uitleg die de gebruiker moet krijgen |
| --- | --- |
| Temperatuursensor | “Deze sensor meet hoe warm deze ruimte is. De regeling vergelijkt deze met je doeltemperatuur. Kies een representatieve kamersensor; apparaattemperatuur kan afwijken.” |
| Radiatorkranen | “Deze kranen verwarmen deze ruimte. Alle gekozen kranen horen bij hetzelfde ruimtedoel. Een kraan die al bij een andere ruimte hoort, kun je hier niet tegelijk gebruiken.” |
| Vloerkleppen | “Deze kleppen openen de vloerverwarming van deze ruimte. Het profiel moet passen bij kleptype, looptijd en eventuele pomp/menggroep; verkeerde instellingen kunnen de warmteafgifte verstoren.” |
| Basisdoel | “Deze temperatuur geldt buiten je weekblokken. Een hoger doel kan meer warmtevraag geven; een tijdelijke afwijking verandert je weekprogramma niet.” |
| Weekbloktemperatuur | “Dit is de gewenste temperatuur voor dit tijdvak. Voorverwarmen kan eerder beginnen als deze functie beschikbaar en ingeschakeld is.” |
| Maximale meetleeftijd | “Na deze tijd zonder geldige meting telt deze sensor als uitgevallen. Te kort geeft onnodige onderbrekingen; te lang laat de regeling oude informatie gebruiken.” |

Geen kale foutcodes: “Deze kraan is al gekoppeld aan Slaapkamer. Kies een andere
kraan of wijzig eerst die ruimte.” Vermeld het betreffende veld en behoud overige
invoer. Een ontbrekende of ongeschikte sensor mag geen groene gereedstatus krijgen.

## Oude E32-kamers en verwijderen

Oude kamers worden tijdens de overgang apart herkenbaar als **Oude E32-configuratie**,
met hun herkomst. Ze verschijnen niet als nieuwe normaal ingerichte ruimtes.
Bied een beheerde route om ze over te nemen, in de nieuwe weergave te negeren of
de oude bronconfiguratie op te ruimen. Alleen HA-entities wissen is geen oplossing.

- **Overnemen:** vergelijk bron-ID, bindings en programma; voorkom dubbele
  climate/actuator-eigenaren. Behoud identiteit/historie waar mogelijk en laat
  afwijkingen zien vóór opslag. Geen impliciete overname van een oude writer.
- **Negeren:** expliciete uitsluiting op stabiele identiteit binnen dezelfde
  configuratie-eigenaar, zodat herhaalde discovery haar niet opnieuw activeert.
  Dit stopt geen bestaande fysieke aansturing; die betekenis staat erbij.
- **Verwijderen:** toon welke ruimte, bindingen, programma en oude bron worden
  verwijderd en wat behouden blijft. Eerst bron/writer uitsluiten of gecontroleerd
  migreren, dan afhankelijke configuratie en verweesde entiteiten opruimen. Een
  configuratie op de E32 verwijderen is een aparte benoemde bronwijziging.

Een actieve ruimte verwijderen vraagt eerst gecontroleerd beëindigen van haar
bijdrage en opdrachten via de bestaande eigenaar, met herberekening van de overige
ruimtes en bewezen stopgedrag. Bij ontbrekende veilige bevestiging blijft de
verwijdering geblokkeerd met uitleg. Een configuratie-only ruimte kan zonder die
fysieke stap verdwijnen. Gedeelde circuits/apparaatintegraties en Recorderhistorie
worden niet automatisch verwijderd. Annuleren wijzigt niets; een fout laat geen
halve configuratie achter. Eén expliciete bevestiging toont concrete gevolgen;
geen reeks technische bevestigingsformulieren.

## Toetsbare oplevering

- Gewone gebruikers zien één installatieroute en één ruimtewizard. Geavanceerde
  editors verdwijnen uit het standaard toevoegmenu, met behoud van hun gegevens.
- Test radiator, vloer en combinatie alleen voor de werkelijk ondersteunde
  profielen. Niet ondersteund, niet beschikbaar en nog niet getest zijn duidelijke
  afzonderlijke toestanden.
- Gebruiker kan zonder documentatie centrale instellingen vinden, ruimte maken,
  wijzigen en verwijderen, bloktemperatuur aanpassen en een fout herstellen.
  Iedere getoonde instelling heeft werking en impact; Geavanceerd start gesloten.
- Test dubbele apparaattoewijzing, ongeschikte/verlopen sensor, verkeerde grenzen,
  annuleren, hernoemen, teruggaan, conflict tijdens opslaan, herstart en herstel.
  Geen dubbele ruimte, verloren programma of onbedoelde activering.
- Test oude discovery na overname/uitsluiting/verwijderen opnieuw. Geen herleving
  van verwijderde bronnen, tweede schrijver of ongemerkte historie-reset.
- Verifieer native HA-frontend op desktop/mobiel en de werkelijke configuratie
  achter de schermen. Het losse prototype bewijst alleen de ontwerpinteractie.

Uitvoering valt onder de bestaande F3/F5-/migratieroute en WIP-limiet. Geen nieuwe
F9/F10/P2-stage vóór M2, geen HA-/E32-update of fysieke vrijgave door dit ontwerp.
De native centrale-/radiatorroute is als eerste begrensde implementatie gebouwd
en geïnstalleerd. Het grafische kamerscherm met inline weekraster is in dev6-bron
en echte browserproeven bewezen en live geïnstalleerd. De onafhankelijke live
nacontrole van 19:07 CEST bevestigt de nieuwe editor/dashboardroute en exacte
publieke module, met behoud van configuratie en registries; zie de testkandidaat. Volledige onboarding/toepassing, vloerprofielen en fysieke
gebruikersproeven blijven open. Mark autoriseert
verdere uitvoering zonder verplichte afstempauze na iedere fase.

## Aanvulling 22 oktober: toevoegen en aanpassen zijn verschillende routes

Mark verlangt een wizard uitsluitend voor de eerste toevoeging. Bestaande kamers
krijgen één vast grafisch bewerkscherm met naam, type verwarming, sensor, kranen,
basistemperatuur en weekplanner. De native HA-aanpasknop krijgt één formulier en
een directe link naar hetzelfde volledige grafische kamerscherm; geen nieuwe
wizard of apart controlescherm. De grafische route is de normale complete editor.

In de weekplanner: klik of sleep in een tijdvak om een blok te tekenen, kies een
blok om begin/einde en temperatuur inline te wijzigen, verplaats/verleng met de
aanwijzer en gebruik knoppen voor toevoegen, verwijderen en dagen kopiëren.
Geen blokdialoog. Eén concept voor de hele kamer, één knop **Alles opslaan** en
annuleren zonder bijwerkingen. Geavanceerd begint gesloten. Onondersteunde
verwarmingstypes en profielen worden eerlijk benoemd; bestaande data behouden.

Deze aanvulling vervangt ontwerpen waarin aanpassen opnieuw de toevoegwizard
doorloopt of de planner een los configuratiepad is. Bouw- en installatiebewijs
staat in de testkandidaat; dit document is geen bewijs van fysieke regeling.

## Controle van kraandoelen in hetzelfde kamerscherm

De reeds opgeslagen kamergrenzen, basistemperatuur en lokale weekblokken worden
naast de apparaatbindingen met gemelde kraaneigenschappen vergeleken. Toon naam,
bereik en stap; benoem afwijkingen per basisdoel of dag/tijdvak. Leg bij ruimere
kamergrenzen uit waar die aanpasbaar zijn. Ontbrekende/onbruikbare eigenschappen
blijven onbekend; een bestaand extern programma wordt niet als gecontroleerd
voorgesteld. Geen automatische correctie of claim van fysieke klepwerking.

Een controle over de opgeslagen versie is geen beoordeling van een gewijzigd
concept. Bij andere kranen, grenzen of programmadoelen verdwijnt de oude uitslag;
na de gezamenlijke opslag wordt de nieuwe backendcontrole getoond. Ongeldige
blokvelden mogen geen oude positieve melding laten staan. Hernoemen behoudt de
bindingen/het programma en verandert de temperatuurcontrole niet.

Voor beheerde dashboards moeten module-URL en componentidentiteit samen passen,
zodat een al geladen oude editor de bijgewerkte versie niet kan vervangen.
Bron-/browserbewijs voor deze aanvulling staat bij dev9 in de testkandidaat;
geen bewijs van live installatie of fysieke werking.

## Apparaatstatus, verdwenen koppelingen en bewuste vervanging

Het complete kamerscherm moet de opgeslagen selectie herkenbaar houden als een
apparaat onbekend/onbeschikbaar is, geen status heeft, uitgeschakeld is of de
registrykoppeling ontbreekt. Deze toestanden niet samenvoegen tot “gereed” of de
selectie stilzwijgend weglaten. De getoonde status geldt bij laden; zij bewijst
geen fysieke acquisitietijd. Een onbruikbare temperatuurwaarde apart benoemen.

Hernoemen volgt de vaste apparaatidentiteit. Een later hergebruikt entity-ID is
geen toestemming voor vervanging. De gebruiker kiest een vervanger bewust in
hetzelfde scherm; bij kranen eerst de ontbrekende selectie verwijderen. Alleen
volledige, opnieuw gevalideerde kamer-/apparaat-/weekgegevens samen opslaan.
Andere ruimtes/uitvoereigenaars blijven beschermd; een oude verwijderde eigen
referentie mag het herstellen van diezelfde kamer niet onmogelijk maken.
Een wijziging tijdens opslaan laat geen gedeeltelijke configuratie achter en
behoudt het concept. Bron-/testbewijs bij dev10 in de actuele testkandidaat.
