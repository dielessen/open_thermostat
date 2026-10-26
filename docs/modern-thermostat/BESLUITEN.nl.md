# OpenThermostat — besluitenlog

Gedateerde productbesluiten van Mark. [PLAN](PLAN.nl.md) bevat het ontwerp en de
acceptatievoorwaarden; [WORKBOARD](WORKBOARD.nl.md) blijft de enige actuele
afvinklijst. Een besluit hier is geen code-, installatie- of verwarmingsvrijgave.

## 23 oktober 2026 — eerste bèta en alle voorbereide software bundelen

Mark vraagt het hele plan opnieuw langs te lopen, gestructureerd te werken en
alle eerder voorbereide onderdelen in de volgende samenhangende release mee te
nemen. Doel: eerste bèta voor ketelkoppeling, uitlezen en begrensde aansturing.

- Eén actuele afvinklijst in WORKBOARD; historische checkpoints niet als huidige
  open punten laten concurreren. Alle 31 eisen en oorspronkelijke acceptatie blijven.
- Inventaris met bestaande code, geleverde versie, open aansluiting/kwalificatie
  en releaseactie; software aanwezig is niet hetzelfde als werkende praktijkfunctie.
- Voorbereide models/comfort-/vloer-/menger-/metrics-/CSVcode behouden, zonder
  ontbrekende productpaden automatisch vrij te geven of nieuwe F9/F10-stages vóór M2.
- Eén bevroren gezamenlijke kandidaat en release, met behoud van instellingen,
  volledige passende verificatie en normale update-/herstelroute.

## 22 oktober 2026 — direct de normale productconfiguratie op ontkoppelde E32

Mark bevestigt dat de E32 fysiek los van de ketel staat en dit project geen
productie draait. Hij wil direct configureren zoals het eindproduct eruit komt
te zien; een aparte schaduwconfiguratie maakt de inrichting onduidelijk.

- Eén gewone OpenThermostat-installatie, centrale instellingen en ruimtes met
  wizard. Geen verplichte keuze tussen legacy/shadow, tweede testinstallatie of
  later opnieuw in te voeren productieconfiguratie.
- Bestaande OpenThermostat-testconfiguratie mag na gerichte back-up worden
  vervangen of samengevoegd. Behoud van wegwerpbare testgegevens is geen
  verplichte productiemigratie; de overige HA-installatie valt buiten deze scope.
- Niet aangesloten/nog niet toegepast is een begrijpelijke toestand binnen
  dezelfde installatie, geen tweede configuratiesysteem. Afzonderlijke interne
  tests blijven mogelijk; bron-/profielvalidatie en uitvoerstatus krijgen een
  gewone begeleide route in het product.
- Bestaande shadowmodi doen technisch meer dan alleen een naam tonen. De bouwfase
  moet de echte configuratie-/uitvoerroute aanpassen; hernoemen of blind activeren
  is onvoldoende. Dit besluit wijzigt zelf nog geen geïnstalleerde code of runtime.
- Ontkoppeling is Marks actuele hardware-informatie, geen eigen fysieke proef.
  Ketel aansluiten en veilige ketelregeling bewijzen blijven latere stappen.

Dit besluit vervangt eerdere gebruikersinstructies om eerst een aparte
shadowconfiguratie te maken. [PLAN](PLAN.nl.md) en [HA-inrichting](HA-INRICHTING-UX.nl.md)
zijn daarop aangescherpt; historische bewijsrapporten blijven historisch.

## 22 oktober 2026 — één centrale inrichting en begeleide ruimtes

Mark vindt de huidige integratie rommelig en de losse toevoeg-/configuratiekeuzes
onduidelijk. Hij vraagt om één centrale ketelconfiguratie en zone-/ruimteregeling
via een wizard: verwarmingstype, sensoren en radiatorkranen/vloerkleppen per ruimte.
Geavanceerde functies staan uit het standaardpad. Iedere instelling verklaart haar
werking én impact; gewone fouten worden voorkomen of begrijpelijk hersteld.

De oude uit de E32 afkomstige configuratie krijgt expliciete bronherkenning en een
beheerde overname-/opruimroute, met behoud van apparaten/historie en zonder
terugkeer door discovery of een tweede schrijver. Dit geeft geen toestemming om
een onbekende actieve bron als snelle cosmetische oplossing te verwijderen.

Vastgelegd in [PLAN §5](PLAN.nl.md#5-domeinmodel-en-configuratie-eigenaarschap) en
[de concrete gebruikersroute](HA-INRICHTING-UX.nl.md), met een interactief lokaal
ontwerp. De ontwerpstap wijzigt geen HA-inrichting of productcode. Vertaling naar
de bestaande native HA-integratie volgt als afzonderlijke afgebakende bouwfase.

## 22 oktober 2026 — gebruiksvriendelijk eindproduct en vernieuwde E32-GUI

Mark vraagt in VS Code om het plan aan te scherpen: een zeer gebruiksvriendelijk,
duidelijk product met de reeds besproken moderne slimme thermostaatfuncties.
De 31 eisen blijven de functionele basis. Gebruiksgemak, grafische presentatie en
snelheid krijgen aantoonbare acceptatievoorwaarden in [PLAN §1/§9/§11/§13](PLAN.nl.md).

- **HA is de gewone configuratie en bediening:** eenvoudige kamerinrichting en
  begrijpelijke doelen/programma's; technische groeps-/contractdetails zijn geen
  verplichte gebruikersstappen.
- **Weekplanner:** ieder blok toont tijd en temperatuur in °C; blok openen en
  temperatuur wijzigen is direct herkenbaar. Dagen kopiëren, opslaan/annuleren,
  basisdoel buiten blokken en tijdelijke override met hervatten zijn duidelijk.
  Het bestaande temperatuurveld in de native editor is geen bewijs dat de gewenste
  grafische gebruikservaring al is bereikt.
- **E32-startpagina:** aantrekkelijk grafisch dashboard met relevante betrouwbare
  ketelgegevens, opdrachten richting ketel en de warmtevraag per kamer. Gevraagd,
  verzonden, bevestigd en werkelijk gemeten worden herkenbaar onderscheiden.
- **E32 opschonen en versnellen:** bestaande functionaliteit mag worden aangepast
  of vervangen. Ongebruikte/achterhaalde functies en dubbele configuratiepaden
  verdwijnen na gecontroleerde migratie uit het betreffende product/build, met
  behoud of getoetste vervanging van de afgesproken functies en recovery.
  Snelheid wordt vóór/na op de E32 gemeten zonder regel-/veiligheidstiming te schaden.

Dit is een aanvullende producteis, geen gerealiseerde GUI of fysieke acceptatie.
Het bestaande herschrijfmandaat geldt; HA blijft configuratie-eigenaar en E32
regelbrein. Werkvolgorde, WIP-limiet, migratie-/release-/hardwarepoorten blijven
gelden. Na deze planfase is het voorstel om de concrete schermindeling van
weekplanner en startdashboard met Mark af te stemmen vóór de volgende bouwfase.

## 22 oktober 2026 — Tado V3/V3+ vervalt als regelaar

- Zodra OpenThermostat de ketel regelt, vervalt de bestaande Tado V3/V3+ als
  thermostaat. Er blijft één schrijver op de ketel.
- De Tado mag daarna een gewone, in de HA-GUI kiesbare kamertemperatuurbron zijn,
  met de voorwaarden uit [PLAN §6.3](PLAN.nl.md#63-bestaande-tado-v3v3).
- Tot en met de F6/F7-commissioning blijft de Tado intact als werkende verwarming;
  daarna is hij de gedocumenteerde rollbackregelaar.
- Tegelijk aanvaard: haalbaarheidsvoorproef van de ketelstop en een WIP-limiet
  vóór nieuwe F9/F10/P2-stages ([PLAN §14](PLAN.nl.md#14-gefaseerde-uitvoering-en-acceptatiepoorten)).

## 21 oktober 2026 — productrichting, herschrijfmandaat en architectuurroute

Onderstaande tekst stond tot 22 oktober letterlijk in PLAN §1.

#### Productrichting bevestigd door Mark — 21 oktober 2026 (Telegram11883)

We ontwikkelen een **zelfstandig eigen softwareproject**. OpenThermostat is de
historische codebasis, niet de eigenaar van onze productkoers of releaseplanning.
Onze regelkern, HA-integratie, configuratiecontracten en GUI worden als één eigen
product onderhouden. Na Marks aanvullende besluit van 21 oktober 14:07 nemen
we geen nieuwe wijzigingen meer over uit `intuibase/open_thermostat`; geen
upstream-pull/merge/rebase of bijtrekwerk als projecttaak. De historische afkomst
en licentie-erkenning blijven; de remote wordt niet zonder opdracht verwijderd.

Zelfstandig betekent niet dat alle bestaande code opnieuw moet worden geschreven
of dat beproefde libraries/platformen moeten verdwijnen. De afgesproken E32- en
HA/MQTT-architectuur blijft staan, inclusief de werkelijke HA-/brokerafhankelijkheid
voor via HA aangesloten apparaten. Geen extra afhankelijkheid van een extern
thermostaatproject als regelbrein. Afkomst, copyright en toepasselijke licenties
van hergebruikte onderdelen blijven aantoonbaar behouden. Een nieuwe productnaam
is nog niet gekozen; dit besluit autoriseert geen repository-/pakketrenaming.

Dit is een product-/onderhoudsbesluit, geen bewijs van runtimezelfstandigheid.
De huidige integratie- en acceptatiepunten in WORKBOARD worden systematisch
afgemaakt; de onderstaande herschrijfbevoegdheid geldt waar dat noodzakelijk is.

#### Herschrijven toegestaan bij functionaliteitsbehoud — Mark11944, 21 oktober

Mark geeft expliciet toestemming om **alle projectcode zo nodig te herschrijven**.
De gewenste functionaliteit is leidend, niet behoud van de oude implementatie,
klasse-indeling, interne API of compatibiliteit met het oorspronkelijke project.
Dit omvat firmware en onze HA-integratie; wijzigingen hoeven niet tot kleine
patches beperkt te blijven als een gerichte vervanging beter bij het doel past.

De 31 eisen en afgesproken gebruikersfuncties blijven de acceptatiebasis. Geen
stilzwijgend verlies van functies om gemakkelijker te bouwen. Bewaarde
configuratie/historie en apparaatidentiteiten krijgen zo nodig een expliciete
migratie en terugvalroute; fysieke veiligheids- en releasechecks worden niet
door herschrijftoestemming vervangen. Hergebruikte code behoudt zijn notices.

Dit is toestemming indien nodig, geen opdracht om automatisch opnieuw te
beginnen. Bij een concrete blokkade mag dezelfde uitvoeringseigenaar de
betreffende structuur vervangen, met korte technische reden, afgebakende diff,
functionele toetsing en rollback. Benut reeds bruikbaar werk en blijf de volledige
gebruikersketen afronden; geen parallelle tweede implementatie of nieuwe zijfase
alleen omdat volledige herschrijving nu is toegestaan. Er is geen nieuwe
publicatie/installatie/verwarmingsvrijgave of bewezen tijdwinst uit dit besluit.

Mark11950 bevestigt ook vrijheid voor een andere framework-/basisopzet als dat
de beste oplossing oplevert en vraagt om actief kritisch advies. Vergelijk
behouden, gericht vervangen en bredere herbouw op concrete bronfeiten,
functievolledigheid, onderhoudbaarheid, complexiteit, migratie en bewijsrisico.
Geen extra goedkeuringsronde voor al geautoriseerd bronwerk; geen automatische
big-bang of nieuw lang ontwerptraject. [Architectuuradvies](ARCHITECTURE-ADVICE.nl.md)
en de [specialistschets](ARCHITECTURE-DECISION.nl.md) zijn na brongebonden parentreview
bevestigd als uitvoeringsrichting: gerichte vervanging van de productkoppellaag,
één versiecontract/accepted ControlPlan met onafhankelijke installatiekwalificatie
en vluchtige runtimebevoegdheid apart. Eerste verticale oplevering: twee volledige
kamers via normale HA-apply duurzaam opslaan en exact in dezelfde C++-owner/
controller teruglezen, wijzigen en herstellen. Geen extra projectie als productpad.
Dit is ontwerpacceptatie, geen code-/resource-/GUI-/fysieke acceptatie of einddatum.
Mark11956 (21 oktober 14:51) aanvaardt dit advies als werkroute: gerichte herbouw
van de eigen configuratie-/runtimekoppeling waar nodig. Voer uit binnen de lopende
integratie; specialisttoets is technische verificatie, geen nieuwe toestemming-
of ontwerpwachtfase. Bij tegenbewijs het advies eerlijk herzien; alle functies
blijven en bredere herbouw blijft toegestaan indien aantoonbaar noodzakelijk.


### Bekende uitvoering voortzetten — Mark, 22 oktober

Mark vraagt het plan door te blijven uitvoeren zonder na iedere fase op een
antwoord te wachten. Echt ontbrekende informatie wordt uitgevraagd, terwijl
onafhankelijk uitvoerbare taken doorgaan; resterende vragen mogen aan het eind.
Dit vervangt de eerdere wens om elke vervolgstap eerst af te stemmen. De normale
HA-inrichting en projecttestconfiguratie mogen binnen de bestaande back-upscope
worden bijgewerkt. Fysieke proeven, WIP-limiet en releasevoorwaarden blijven apart.


## 23 oktober — GitHub-releases en vooraf geautoriseerde E32-upgrades

Mark: “Zorg ook dat je netjes releases maakt op github en de e32 mag je upgraden wanneer nodig.”
Testreleases krijgen vaste tags/commits, downloadbare bestanden, notes, checksums
en testbewijs. HA-only `ha-v*` bevat geen firmware; E32-versie/tag volgt
`release.json`. Gewone passende E32-app-updates mogen zonder herhaalde toestemmingsvraag
worden uitgevoerd na de bestaande controles en met configuratiebehoud/terugval.
Geen bestaande tag/release overschrijven, geen privébeheerdata publiceren en geen
fysieke of bronvoorwaarde als afgetekend beschouwen op basis van deze toestemming.

### 23 oktober — afzonderlijke releases en aantoonbare testklokken

HA-only pakketten gebruiken een eigen `ha-v…`-tag en dezelfde native HA/MQTT-
en browsercontroles. Ze bevatten geen firmware. Mislukte tags blijven ongewijzigd;
een volgende kandidaat krijgt een nieuwe versie. GitHub-publicatie maakt geen
installatie of fysieke acceptatie waar. HA-dev11 blijft de laatste live uitlezing.

Bij dev12 bleek de native proef twee monotone klokdomeinen te combineren:
HA-loopontvangst tegenover een virtuele protocolklok van100…221s. Hostuptime kon
daardoor de geschatte rapportleeftijd veranderen. Dev13 maakt de runtimeklok
expliciet injecteerbaar, standaard onveranderd de HA-loopklok. Beide virtuele
HA/C++proeven delen die bron. Nieuwe regressie controleert identieke ontvangst-
en protocoltijd, exact2000ms wachtrijleeftijd en weigering op de kamerleeftijdsgrens.
Oude code faalt; nieuwe code en87 gerichte proeven slagen. Geen versheidscontrole
verwijderd of ketel-/TRVbevoegdheid toegevoegd.

De nieuwe E32-releasezoeker doorloopt maximaal twaalf één-release-antwoorden om
maximaal twee passende firmwarekeuzes te vinden. HA-tags, drafts, ontbrekende
assets en ongeschikte manifests tellen niet mee. Netwerk-/parsefouten behouden
de oude lijst.21 native updaterproeven en een nieuwe schone app/FS/bordbuild
slagen; geen flash. Bestaande bron-/notice-/leveringsvoorwaarden blijven open.
