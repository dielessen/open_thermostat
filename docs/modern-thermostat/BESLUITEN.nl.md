# OpenThermostat — besluitenlog

Gedateerde productbesluiten van Mark. [PLAN](PLAN.nl.md) bevat het ontwerp en de
acceptatievoorwaarden; [WORKBOARD](WORKBOARD.nl.md) blijft de enige actuele
afvinklijst. Een besluit hier is geen code-, installatie- of verwarmingsvrijgave.

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
