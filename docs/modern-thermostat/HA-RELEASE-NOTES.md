# HA 0.4.0.dev34 — voorbereiding volgende bundel

Nog niet gepubliceerd of geïnstalleerd. De gecontroleerde installatie blijft dev33.

- Ontvangstouderdom van de alleen-lezen supervisordiagnose vergelijkt direct met de vervaldeadline. Daarmee blijft een exact verlopen rapport niet zichtbaar door afronding bij het aftrekken van twee klokwaarden.
- Een deterministische proef met een fractioneel klokbegin toont de oorspronkelijke fout en het herstel. Regelbevoegdheid, opdrachten, leases, bronkwalificatie en fysieke uitgangen veranderen niet.

# HA 0.4.0.dev33 — ESP-eigen diagnose via native MQTT

Herstelt vrije/minimaal vrije heap, grootste vrije blok, CPU-temperatuur en uptime samen met E32 alpha25. Bestaande entity unique IDs en geschiedenis blijven behouden. De HA-entiteiten bestaan ook vóór het eerste rapport. Live rapporten zijn elke 15 seconden beschikbaar; na 45 seconden zonder geldig rapport of bij offline wordt beschikbaarheid ingetrokken. Een HA-only herstart vereist geen E32-herstart. Uitgeschakelde RTC-temperatuur blijft onbekend. Legacy modus blijft intact.

Instellingen en status maken in Engels en Nederlands duidelijk dat schaduwmodus alleen uitleest en berekent. Een bevestigde configuratie en passende kraandoelen worden apart uitgelegd; zij worden niet gepresenteerd als bewijs van kraanbeweging of veilig ketelstoppen.

Dit gebruikt dezelfde native verbinding en bestaande HA-runtime voor verval; er worden geen kraan- of ketelopdrachten toegevoegd. Alle functies en correcties uit dev32 zijn meegenomen. Zonder bijbehorende E32 alpha25 blijven deze native diagnosewaarden niet beschikbaar.

# HA 0.4.0.dev32 — rapportlevensduur en verklaarbare transportafwijzingen

Bundelt alle HA-correcties sinds dev31. E32 alpha24 blijft staan; deze uitgave
verleent geen fysieke meet-, kraan- of ketelkwalificatie.

- Oorspronkelijke temperatuur- en TV02-rapporten blijven gebonden aan de gekozen
  maximale rapportleeftijd. Een policywijziging trekt de oude ontvanger in;
  terugzetten hergebruikt geen oude rapporten. Een nieuwe eigenaar begint leeg.
- Ongeldige klokwaarden en overlopende tijdsdelta's worden veilig afgehandeld.
- De bestaande ontvanger bewaart maximaal één historische afwijzing voor een
  actuele, aangevraagde reply. HA-diagnostiek toont alleen vaste stroom-, status-
  en redencodes met ontvangstouderdom. Onbekende peer-tekst wordt niet uitgevoerd
  of geëxporteerd. Een latere gezonde status maakt dit geen actuele storing.
  Een sessiewissel of geconstateerde klokfout verwijdert deze diagnose.
- Native configuratieafwijzingen met het optionele `rejection_reason`-veld worden
  correct als afwijzing verwerkt; zij verdwijnen niet door een te strikt schema.
  Succes blijft uitsluitend via de bestaande readback-/SOURCE-controles geldig.

Kamers, programma's, koppelingen, accepted SOURCE/journal, registry, dashboard,
privé TV02-pins en ontvangende producent blijven behouden. Geen extra client,
watcher, automatische retry of apparaatopdracht. De frontendbytes en bestaande
dev28/v28-kaartidentiteit blijven gelijk. Natuurlijke TV02-ontvangst, causale
opdrachtbevestiging en fysieke acceptaties blijven afzonderlijke open checks.

# HA 0.4.0.dev31 — TV02-ontvangst voor native installatiekamers

Herstelt de oorspronkelijke TV02-ontvanger voor kamers waarvan de gekozen kraan
in de centrale installatieconfiguratie staat. De ontvanger valideert dezelfde
native configuratie-eigenaar als de kamereditor. Ontbrekende, dubbele, gewijzigde
of ongeldige koppelingen worden afgewezen; een ingetrokken bron herleeft niet
vanzelf. Identiteits-, ouderdoms- en replaycontroles blijven behouden.

Deze gerichte vervolgupdate maakt ontvangstacceptatie mogelijk na de gezamenlijke
alpha24/dev30-bundel. E32 alpha24 blijft staan. Geen apparaatopdracht, automatische
kraanmoduswijziging of bronkwalificatie. De al geplaatste privé ontvangstpins en
ontvangende Zigbee2MQTT-extension blijven behouden; het pakket bevat geen privé
pins. Kamers, programma's, SOURCE, registry en historie blijven behouden.
Frontendbytes en dev28/v28-kaartidentiteit blijven gelijk.

# HA 0.4.0.dev30 — supervisor, eindige kraandoelen en privé ontvangstpins

Gezamenlijke kandidaat met E32 alpha24; bundelt alle HA-wijzigingen sinds dev29.
De standaard fysieke uitvoer blijft geblokkeerd. Dit is geen actieve ketelbèta.

- Read-only supervisordiagnose toont gemelde fase en regelintenties met beperkte
  ontvangstouderdom. Verlopen, ontbrekende of ongeldige status wordt ingetrokken;
  diagnose verleent geen bevoegdheid en verwerpt geen geldige kamerbeslissingen.
- De voorbereide kraanadapter begrenst wachttijd én serviceaanroep binnen dezelfde
  actiedeadline. Een nieuwer wachtend doel vervangt een ouder. Een onzekere afloop
  na dispatch blokkeert vervolgacties binnen dezelfde adapter, zonder retry.
- Oorspronkelijke TV02-ontvangstpins kunnen uit het privébestand
  `.openthermostat-original-tv02.json` op de HA-configroot worden gelezen bij
  normale native opstart. Strikt schema, privérechten, identiteitsbinding en
  foutisolatie; geen Store, watcher, extra MQTT-client of apparaatopdracht.
  Ontbrekend/ongeldig bestand laat normale controlleropstart werken.

De update installeert geen Zigbee2MQTT-producent, verandert geen meetselectie of
kraanmodus en kent geen bron-/flow-/klepkwalificatie toe. Werkelijke originele
ontvangst vereist afzonderlijk beoordeelde private pins en producentinstallatie.
Kamers, programma's, SOURCE, registry-identiteiten en historie blijven behouden.
De frontendbytes veranderen niet: de bestaande dev28/v28-resource-/kaartidentiteit
blijft geldig en wordt niet op basis van het manifestnummer vervangen.

# HA 0.4.0.dev29 — oorspronkelijke TV02-ontvangst zichtbaar

Bundelt de voorbereide oorspronkelijke TV02-datapointontvangst via de bestaande
native MQTT-verbinding en registry-lifecycle. Ontvangst is begrensd, controleert
de expliciet vastgelegde apparaatidentiteit en bronleeftijd en maakt verouderde,
retained, herhaalde of verkeerd gekoppelde rapporten niet opnieuw actueel.
De standaard bronpinlijst blijft leeg. Productiebronpins, Zigbee2MQTT-extension
installatie en echte oorspronkelijke rapportontvangst moeten apart beoordeeld
worden; de update schakelt deze niet automatisch in.

De kamereditor toont beschikbare oorspronkelijke rapporten in Nederlands of
Engels: gemeld doel, eigen kraantemperatuur, programma, verwarmingsstop en
vorstbeveiliging. De ontvangstouderdom geldt bij laden. Ontvangst is geen
opdrachtbevestiging, klepstand, bewezen warmteafgifte of aansturingsvrijgave.
Verlopen, onderbroken of ongeldige rapporten tonen geen oude datapointwaarden.
Conceptwijzigingen gebruiken niet de diagnose van een oude opgeslagen koppeling.

De gewijzigde editor heeft de eigen dev28/v28-cache-/kaartidentiteit; dev29
behoudt diezelfde frontendbytes en voegt complete pakketnotities toe.
Bestaande handmatige kaarten blijven compatibel. Er is geen extra polling,
MQTT-client, automatische kraanmodusreparatie of setpointopdracht toegevoegd.
Bestaande meetentiteiten, historie, kamers, weekprogramma's, SOURCE en apparaat-
identiteiten blijven behouden. Dit is de gezamenlijke passieve testbatch met
E32 alpha23 (logging/syslog en stabiele dashboardverversing). Fysieke
ketel-/kraanuitgangen blijven geblokkeerd en de actieve bèta blijft open.

Dev28 bleef een ongepubliceerde pakketkandidaat; de bestaande tag blijft
behouden. Dev29 bevat de volledige bijgewerkte Nederlandstalige pakketnotities.

# HA 0.4.0.dev27 — actuele ketelvelden zichtbaar in het overzicht

Het beheerde keteloverzicht gebruikt nu de native ketelsensoren die met
alpha20/dev26 beschikbaar zijn gekomen. Aanvoer, retour, gerapporteerde
modulatie en tapwatertemperaturen krijgen eigen historiekaarten. Alle
beschikbare velddefinities worden via de geregistreerde entiteits-ID opgenomen;
hernoemen, uitschakelen en installatie-eigendom blijven gerespecteerd.
Gerapporteerde velden en afgeleide activiteit staan afzonderlijk. Ingeschakelde
onbetrouwbare ruwe diagnostiek blijft bij Diagnostics en wordt geen vlam- of
pompbewijs. Er worden geen oude statistieken samengevoegd of counters aangevuld.

Dit rondt de HA-presentatie van de uitleesupdate af; E32 alpha20 blijft staan.
Geen SOURCE-, kamer-, programma-, regelaar- of uitgangswijzigingen. De bestaande
kamereditor en zijn dev25-cache-identiteit veranderen niet.

# HA 0.4.0.dev26 — native meetkoppeling voor de productinstallatie

Bundelt alle voorbereide dev25-functies met de correctie voor bestaande v2-
meetentiteiten. De productinstallatie gebruikt nu dezelfde gevalideerde native
MQTT-cache als de native sensorplatformtests. Eén eigenaar per meetidentiteit
voorkomt dubbele sensoren door legacy-berichten. Entiteitsidentiteiten,
statistiekdefinities en installatiegroep blijven behouden; verlopen of niet
ondersteunde waarden blijven onbeschikbaar. De frontend blijft op dezelfde
reeds vernieuwde dev25-kaartversie omdat de frontendbytes niet veranderen.

Samen met E32 alpha20 worden beschikbare Classic-ketelvelden zichtbaar.
Uitgangen blijven geblokkeerd; geen wijziging van SOURCE, kamers of programma’s.

# HA 0.4.0.dev25 — actuele ketelvelden en consistente EN/NL-bediening

Samen met E32 alpha19 worden beschikbare Classic-ketelvelden via de bestaande
native MQTT-sessie als leessensoren op de bestaande installatie aangeboden.
De bronleeftijd, kwaliteit, eenheid en geldigheid blijven zichtbaar. Dit herstelt
het ontbrekende moderne uitleespad; oude legacy-aliassen en hun historie worden
behouden en worden niet met nieuwe meetdefinities samengevoegd. Niet door de
ketel geleverde waarden blijven onbekend; onbetrouwbare diagnostiek blijft
standaard uitgeschakeld.

De volledige EN/NL-formuliercatalogi zijn aangevuld. De kamereditor volgt de
HA-profieltaal, met nieuwe cache-/kaartidentiteit en behoud van oudere kaarten.
Opgeslagen native dashboardteksten gebruiken de afgesproken Engelse terugval.
Alle voorbereide apparaat-/meetdiagnostiek, weekplanner- en opslagcorrecties
blijven meegenomen. Er worden geen kamerkoppelingen, programma’s, kraanmodi of
verwarmingsvrijgaven gewijzigd. Fysieke uitgangen blijven geblokkeerd.

# HA 0.4.0.dev24 — gezamenlijke bron- en apparaatcontroles

Deze release bundelt de voorbereide bronwijzigingen met E32 alpha18. Meetkwalificatie wordt ingetrokken bij vervanging van een observer of wijziging/uitschakeling van de native sensor of het apparaat. Wachtende metingen worden opnieuw gecontroleerd vóór overdracht; cache en herregistratie maken een oude meting niet vers.

De kraanadapter controleert identiteit en actuele temperatuurcapaciteit vlak vóór dispatch. TV02 auto-/vakantie-/uit-/onbekende modus wordt als conflict getoond en verleent geen doelautorisatie. De apparaatcontrole toont expliciet gemelde Zigbee2MQTT- en converterpakketversies. De frontend krijgt een nieuwe cache- en kaartidentiteit.

Programma, kameridentiteiten, bindings en SOURCE blijven behouden. Deze installatie wijzigt geen profiel, kraanmodus of fysieke uitgang. Het productiemeetprofiel en fysieke kraan-/ketelacceptatie blijven open; ontbrekende kwalificatie blijft zichtbaar. Alle eerdere planner-, koude-start-, inrichting- en verbindingsfixes blijven behouden.

# HA 0.4.0.dev23 — gebundelde kamer- en verbindingsverbeteringen

Deze release hoort bij de gezamenlijke testbatch met E32 alpha17.

- De kamerpagina wacht bij opstarten op het HA-hoofdelement. Zo blijft de kaart geregistreerd nadat HA zijn custom-elementregister heeft ingericht; herhaald verversen hoort niet nodig te zijn.
- Bij een normaal gekoppelde native regelaar kunnen de temperatuursensor, radiatorknop en kamergrenzen via de kamerpagina worden gewijzigd. Het complete toekomstige plan wordt vooraf gecontroleerd; kamer, graph en nieuw profiel worden samen opgeslagen en via de bestaande beveiligde controllerverbinding toegepast.
- Als toepassing niet kan worden bevestigd, blijven de opgeslagen instellingen behouden. De pagina blokkeert verdere wijzigingen en biedt een expliciete knop om precies die opgeslagen instellingen opnieuw toe te passen. Er is geen automatische herhaling of terugzetten van een oud profiel.
- De bestaande native heartbeat kan begrensde UTF-8-kamernamen aan een ondersteunende E32 doorgeven. Oude firmware blijft compatibel.
- De oude tijdelijke bronbench wordt geweigerd bij een door SOURCE beheerd regelplan, voordat hij configuratie, timers of eigendom kan wijzigen.

Bestaande kameridentiteiten, programma's en bindings worden bij de update behouden. Apparaatwijzigingen gebeuren alleen na expliciet opslaan. Eén radiatorknop per native kamer blijft de huidige contractgrens; programmabronwissels blijven een afzonderlijke inrichting. Beschikbaarheid van een HA-entiteit bewijst geen gekwalificeerde temperatuurmeting. Een ontbrekend meetprofiel blijft zichtbaar en krijgt door deze update geen automatische kwalificatie of verwarmingsvrijgave.

Verificatie omvat native HA-opslag/herlaadcycli, de normale controller-provisioning met gecontroleerde externe HTTP-antwoorden, echte MQTT-pakketuitwisseling met de C++-controller en desktop/mobiele browserregressies. Fysieke apparaatacceptatie staat daar los van.

# HA 0.4.0.dev22 — meetstatus in de kamerbediening

Bij de gekoppelde sensor staat nu afzonderlijk of de regeling een gekwalificeerde meting heeft, op een nog ontbrekend meetprofiel wacht, of een onbevestigde/verlopen meting heeft. De status is een momentopname bij laden. Hij verandert geen sensorinstellingen en schrijft geen programma of actuatoropdrachten.

Beschikbaarheid in Home Assistant en meetactualiteit blijven afzonderlijk. Een leesactie vernieuwt nooit de leeftijd van een meting. Rapport-ID's en andere bronpayloads worden niet in deze samenvatting opgenomen. De bestaande planner- en koude-startcorrecties blijven behouden.

# HA 0.4.0.dev21 — korte weekblokken betrouwbaar verplaatsen

Een kort temperatuurblok wordt op een aanraakscherm bij slepen nu als geheel verplaatst, met behoud van duur en temperatuur. De vaste randzone kon voorheen het hele blok innemen en daardoor onbedoeld de begintijd wijzigen. Op muisbediening houdt ieder blok een middengebied om te verplaatsen; grotere blokken blijven aan de randen te verlengen of in te korten. Exacte tijden blijven in de velden onder de planner instelbaar.

De browserregressie gebruikt echte Chromium-aanraakgebeurtenissen op 320, 390 en 1440px, Nederlands en Engels. Deze controleert korte blokken, muisbediening, tijdvelden, overlap, daggrenzen, annuleren en afwezigheid van automatisch opslaan. Dit is schermemulatie, geen fysieke telefoonacceptatie.

De koude-startoplossing uit dev20 blijft behouden. Deze HA-update bevat geen firmware en verandert geen opgeslagen kamerprogramma of apparaatbindingen.

# Home Assistant 0.4.0.dev20 — room page registration on direct opening

The room editor previously waited for ha-card before registering its own custom
element. A direct room URL can load before that built-in component, leaving the
editor unregistered and showing a Lovelace Configuration error. The editor
extends HTMLElement and has no dependency on the ha-card definition.

Register immediately; a nested ha-card can upgrade later. The frontend module URL
and managed card type advance to dev20/v20 to refresh cached dev19 clients.
Eight desktop/mobile NL/EN browser cases now exercise both cold and preloaded
HA shells, including preserving a draft when ha-card registers later. Four
existing device-metadata cases remain covered. The regression failed against
the original script and passed after removing the unnecessary wait.

No room settings, schedule, SOURCE, sensor bindings or controller admission
rules are changed. No firmware is included. Browser fixtures use simulated
admin WebSocket responses; live deployment and the user's exact browser
session are separate verification steps.

# OpenThermostat Home Assistant 0.4.0.dev19 — testrelease

Dev19 herstelt opslaan na langer geopende kamerinstellingen. Een verse
kamerstatus bewijst niet dat de eerdere configuratie-uitlezing nog actueel is.
Bij Alles opslaan vraagt de bestaande verbinding zo nodig eerst een nieuwe
configuratiebevestiging op. Pas daarna wordt de ruimte opgeslagen en het
gewijzigde plan via dezelfde regelaar bevestigd. De bestaande leeftijdsgrens
blijft gelden; er worden geen bevoegdheden of bronkwalificaties gefabriceerd.
Als die uitlezing ontbreekt, blijft het concept zichtbaar en wordt niets
opgeslagen. Geen automatische herhaling van een wijziging. De live dev18-proef
werd vóór opslaan geweigerd; 21°C en revisie1 bleven daarbij behouden.

Bij een verbonden regelaar kun je nu de **naam, basistemperatuur en lokale
weekblokken** direct in het kamerscherm wijzigen. Alles opslaan bewaart de
ruimte, wacht op de normale HA-herlaadcyclus en bevestigt het werkelijke E32-plan
via de bestaande MQTT-worker. Een ACK alleen geldt niet als voltooiing. Bij
gewijzigde temperaturen/blokken vervalt een tijdelijke temperatuur wanneer het
nieuwe programma wordt toegepast. Apparaatkoppelingen en profielgrenzen blijven
bij een actieve regeling voorlopig zichtbaar maar vergrendeld; hun volledige
profielmigratie is nog open.

Als toepassing niet kan worden bevestigd, blijft het concept behouden en wordt
geen automatische opdracht herhaald. Na opnieuw laden kan de gebruiker het
opgeslagen programma expliciet opnieuw toepassen. De bestaande SOURCE,
credentials, kranen en fysieke bevoegdheden worden niet vervangen. Dit pad
fabriceert geen gekwalificeerde temperatuurbron of fysieke werking. De eerdere
afwijzing van een losse tijdelijke22°C-opdracht blijft afzonderlijk open;
deze versie verklaart of verhelpt die nog niet.

Eén installatie met centrale instellingen en kamers. Nieuwe kamers gebruiken
een wizard; bestaande kamers hebben één direct configuratiescherm met gekoppelde
apparaten, temperaturen en een grafisch weekprogramma met temperatuurblokken.
Apparaatidentiteit, beschikbaarheid en kraangrenzen worden bij de kamer getoond.
Deze versie herkent de officiële Home Assistant-featureflags van een klimaatapparaat
correct; geldige temperatuurgrenzen hoeven daardoor niet onbekend te lijken.

Dev17 herkent Zigbee2MQTT-klimaatapparaten zonder algemeen `state_topic`.
De prefix wordt uitsluitend afgeleid uit zowel de gepubliceerde bridge- als
de exacte apparaatbeschikbaarheid, gekoppeld aan de bestaande apparaatidentiteit.
Ontbrekende, ongeldige en tegenstrijdige gegevens blijven geweigerd. Deze versie
verandert geen apparaatinstellingen of fysieke aansturing.

Dev16 herstelt de uitlezing voor Home Assistants eigen `MQTTDiscoveryPayload`-
object. De regressietest gebruikt nu dat echte native object, ook samen met de
werkelijke HA-MQTT-client en een lokale testbroker. De eerdere dev15-tag en
bestanden blijven behouden; gebruik dev19 voor de actuele apparaatcontrole.

Aanwezig sinds dev15: in het kamerscherm staat onder **Geavanceerde instellingen**
**Apparaatinformatie controleren**. Dit leest uitsluitend op verzoek de laatst
gemelde Zigbee2MQTT-definities voor de opgeslagen sensor en kranen. Doeltemperatuur,
externe temperatuurinvoer, klepstand en converteropties worden apart getoond.
Ontbrekende informatie blijft onbekend. Een diagnostische apparaattemperatuur
krijgt een duidelijke toelichting; die is niet automatisch een gekwalificeerde
kamermeting. Dit is informatie over apparaatmogelijkheden, geen geslaagde fysieke
kraanproef. Er worden geen instellingen, interviews of verwarmingscommando’s verstuurd.
Deze uitlezing gebruikt de bestaande HA-MQTT-verbinding, twee exacte topics en
een korte wachttijd. Andere apparaten en ruwe discovery-/brokergegevens worden
niet naar het scherm gestuurd. Andere apparaatbronnen blijven normaal gekoppeld;
ze kunnen deze specifieke Zigbee2MQTT-uitlezing niet altijd aanbieden.

Ook aanwezig sinds dev14: kies **E32 verbinden** in de centrale integratie-instellingen.
Vul het lokale webadres en beheerderswachtwoord in. De integratie controleert de
werkelijke E32, bewaart de bestaande netwerkinstellingen en synchroniseert het
kamerprogramma via de bestaande verbinding. Alleen ontvangst van een opdracht
is geen succes: de E32 moet de juiste configuratie en actuele kamerstatus teruggeven.
Een eerste koppeling kan de E32 eenmaal herstarten. E32-alpha.9 of nieuwere
compatibele firmware is nodig; het huidige profiel ondersteunt één of twee kamers.
Het beheerderswachtwoord wordt in de bestaande HA-integratie bewaard; cookies en
controlecodes blijven tijdelijk. Gewone kamerschermen en diagnoses exporteren
het wachtwoord niet. Bij een onderbroken koppeling wordt geen bevestigde uitvoering
voorgewend; controleer de installatiestatus voordat je opnieuw probeert.

Dit is een ontwikkelrelease. De normale HA→E32-configuratieketen is met dev14
live bevestigd; de fysieke sensor-/kraan-/ketelproef en verwarmingsvrijgave
zijn nog niet afgerond. Naam, basistemperatuur en lokale weekblokken zijn in
dev18 bij een actieve koppeling bewerkbaar. Apparaten en profielgrenzen wijzigen,
de optionele externe kamerdoelbron, raamcontact en meerdere gekwalificeerde
kraanprofielen blijven vervolgwerk.
De nieuwe E32-firmware wordt afzonderlijk getest en uitgebracht; deze release
bevat uitsluitend de Home Assistant-integratie. Een opgeslagen instelling is
nog geen bevestigde uitvoering op de E32.

Download `OpenThermostat-HA-0.4.0.dev19.zip` en controleer de SHA256 met
`HA-SHA256SUMS.txt`. Maak vóór installatie een back-up van de bestaande
integratie/configuratie. Kopieer `custom_components/open_thermostat` uit de ZIP
naar de Home Assistant-configuratiemap, controleer de configuratie en herstart
Home Assistant. Bestaande gebruikers hoeven de integratie niet opnieuw toe te
voegen. Controleer na herstart versie, kamers, apparaatkoppelingen en programma.
Behoud het vorige pakket als terugvalmogelijkheid.

Dev14 behoudt de bestaande dagelijkse bediening en neemt de eerdere klokcorrectie mee. Voor reproduceerbare proeven
hebben ontvangst, wachtrij en protocol nu één expliciete monotone klokbron;
standaard blijft dat de bestaande HA-loopklok. De tests gebruiken dezelfde
virtuele klok als hun C++-peer, onafhankelijk van hoe lang de testmachine draait.
De proef bewaakt ook dat vertraagde metingen hun echte leeftijd behouden en
op de ingestelde leeftijdsgrens worden geweigerd. Versheidscontroles blijven staan.

De pipeline bouwt beide benodigde C++-testprobes in een schone CI-omgeving.
De mislukte `ha-v0.4.0.dev11`- en `ha-v0.4.0.dev12`-tags blijven behouden;
daarvan is geen release gepubliceerd. Bestaande instellingen en apparaatkoppelingen
blijven bij deze update behouden.
Het pakket bevat `SOURCE.json`, oorspronkelijke projectlicentie en checksums.
Geen live HA-opslag, firmware, ketelvrijgave of apparaatcommando's zijn inbegrepen.
