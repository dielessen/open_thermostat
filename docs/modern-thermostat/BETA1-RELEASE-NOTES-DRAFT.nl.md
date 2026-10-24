# Eerste gezamenlijke bèta — conceptreleasenotes

Status: **niet vrijgegeven**. Versie en definitieve broncommit worden pas bij de
gezamenlijke freeze ingevuld. Dit document is geen installatie-instructie of
fysieke ketelvrijgave. De enige actuele afvinklijst blijft WORKBOARD.nl.md.

Deze release bundelt de voorbereide firmware- en HA-wijzigingen. Doel is de
ketelgegevens in de webinterface te kunnen beoordelen en vervolgens een expliciete,
begrensde start-/stopproef uit te voeren zodra de installatievoorwaarden zijn
vastgesteld. Ontvangstdiagnose alleen voldoet niet aan dit releasedoel.

## Gebruik en bediening

- Settings → Mijn ketel bewaart de modelkeuze op de E32 en toont een lokale
  illustratie op Home. Eerste model: Nefit Ecomline Classic. Deze presentatiekeuze
  verandert geen aansluit-, regel- of ketelvrijgave-instellingen.

- Settings → Keteltest toont protocolfamilie, ouderdom van berichten, aanvoer,
  retour en gemeld vermogen. Ontbrekende of oude gegevens worden als onbekend
  weergegeven. Wachtrijverlies, afgekeurde berichten en UART-fouten staan in de
  diagnose. Een ontvangstverslag is downloadbaar zonder configuratie of geheimen.
- De proefbediening onderscheidt voorbereiden, start, toezicht en stop. Eerst
  moet een verzonden nulvraag door latere ketelberichten worden bevestigd. Start
  is een afzonderlijke bewuste actie; herladen, heropenen en herhaalde start
  verlengen de proef niet. Een onzekere stop wordt geen geslaagde stopmelding.
- De HA-kamereditor en configuratiestatus melden conflicten met het eigen
  TV02-weekprogramma, vakantie, uit of onbekende bedrijfsmodus, in Nederlands en
  Engels. De software wijzigt daarbij geen preset of kraanmodus.
- De apparaatcontrole toont ook de door Zigbee2MQTT gemelde software- en
  converterversie. Niet gemelde versies blijven onbekend; configuratie en
  geheime gegevens worden daarbij niet getoond.
- De bestaande weekplanner, korte aanraakblokken, kamer-/apparaatinrichting,
  gecontroleerde profielsave, echte kamernamen, About, uitloggen rechtsboven en
  herstart onder Settings blijven behouden. De eerdere koude-startreparatie en
  normale automatische update blijven onderdeel van de basis.

## Gebundeld sinds de geïnstalleerde passieve basis

- Het E32-dashboard ververst afzonderlijke onderdelen. Opengeklapte kaarten,
  invoerfocus en scrollpositie blijven behouden. Verzoeken overlappen niet en
  late antwoorden kunnen een nieuwere pagina niet overschrijven.
- Settings bevat een begrensd lokaal logboek en optionele UDP-syslog naar een
  ingesteld IPv4-adres. Syslog staat standaard uit; de webinterface biedt
  Nederlands en Engels. Gevoelige logregels worden vóór opslag/verzending
  afgeschermd, ook bij opmaakcodes of lange regels.
- De normale HA-opstart kan bron-eigen TV02-rapportontvangers selecteren zonder
  een algemene instellingenoptie die fysieke kwalificatie toekent. Een foutieve
  optionele bronpin verhindert de gewone controlleropstart niet.
- De echte shadow-controller is verbonden met de hydraulische supervisor.
  Limieten, storing, tapwater, waterdoel, kraanfeedback en onafhankelijke flow
  behouden afzonderlijke leeftijden en zijn aan boot/eigenaar/sessie/revisie
  gebonden. Warmtevraag alleen bewijst geen open kraan of flow. Na een fout
  volgt geen automatische hervatting; lokale bevestiging en nieuwe feedback
  zijn nodig. De standaard bronselectie blijft leeg en fysieke uitvoer geblokkeerd.
- De eindige ketelproef bewaakt ook te late stop- en basisbevestigingen. Een
  verlopen deadline wordt niet vernieuwd door een later bericht of leaseverlies.
- De EMS-encoder weigert te grote frames en READ-opdrachten met overtollige
  payload; lengteafkapping kan geen andere opdracht construeren.

Deze punten zijn bronvoorbereiding; de definitieve freeze vermeldt de exacte
gezamenlijke commit en de bijbehorende volledige checks.

## Correctheid van rapporten en opdrachten

- Een voorbereide TV02-producent bewaart originele doel-/temperatuur-/preset-/
  stop-/vorstbeveiligingsdatapoints met type en raw bytes. Ontbrekende velden
  worden niet uit de cache aangevuld. Dit is nog geen causale doel-echo,
  klepstand, readiness of fysieke kraanvrijgave. De native HA-ontvanger en
  lifecycle zijn gebouwd/getest; concrete bronpins en producentinstallatie blijven open.

- Een voorbereide Z2M-bronbrug bewaart originele WSDCGQ11LM-temperatuurberichten
  los van de state-cache. De native HA-ontvanger en kamerstatus tonen
  de originele ontvangst apart; de brug is nog niet geïnstalleerd of toegelaten
  als regelmeting. Ontvangsttijd blijft onderscheiden van acquisitietijd en
  diagnostische apparaattemperatuur blijft uitgesloten als ruimtemeting.

- De originele UART-ontvangsttijd blijft behouden tijdens wachtrijverwerking.
  Een oud bericht kan daardoor geen verse stopbevestiging worden door later te
  worden gedecodeerd.
- Vervanging of intrekking van een HA-meetrapportobserver trekt diens eerdere
  lokale kwalificatie in. Oude cleanup-callbacks en verlooptimers kunnen een
  nieuwe observer of nieuw rapport niet verwijderen; cache krijgt geen nieuwe
  acquisitietijd door herregistratie.
- Ook een native sensor-/apparaatwissel, gewijzigd model of uitgeschakelde bron
  trekt een bestaande meetkwalificatie in. Wachtende metingen worden vóór
  overdracht opnieuw gecontroleerd. Een nieuwe weergavenaam vernieuwt geen meting.
- De voorbereide kraanadapter controleert native identiteit en temperatuurgrenzen
  opnieuw vlak vóór de doelopdracht. Een andere entiteit/apparaat onder dezelfde
  naam, onbeschikbaarheid, uitschakelen of gewijzigde eenheden kan geen oude
  autorisatie overnemen. Serviceacceptatie is geen fysieke doel-echo of klepstand.
- Het gedeelde ketelpollpad controleert proefvoorwaarden en deadline opnieuw na
  encoderen. Stop, verloren feedback/toezicht, tapwaterbedrijf, transportfouten of
  reset trekken positieve proefintentie in. De legacy-opdrachtwachtrij wordt
  tijdens proefbezit uitgesloten en geleegd.
- Hoofd-UART en forwarder tellen een SDK-fout, niet-idle zender of mislukte
  BREAK-afhandeling niet als geslaagd frame. Te lange vectoren worden vóór
  verzending geweigerd. SDK-voltooiing blijft onderscheiden van elektrische
  buskwaliteit, bevestiging en ketelreactie.
- Het Classic-formaat voor de proef is UBASetPoints 0x1A, offset 0, één flowbyte
  plus checksum. Bronadres en masker moeten apart beoordeeld zijn; de encoder
  kiest die niet automatisch uit ontvangen telemetrie.

## Wat niet als werking wordt beloofd

De model-/comfort-/vloer-/menger-/metrics-/CSV-code blijft in de bronbasis. Dat
betekent geen fysieke vrijgave van die functies, acht zones of bewezen leerwinst.
De geïnstalleerde passieve basis is alpha23/dev29 (broncommit `5f31dd7`).
Aanvullende bronwijzigingen worden in deze grotere batch verzameld; de actieve
bèta uit dit concept blijft niet vrijgegeven.

B04–B09 in het werkbord bevatten nog open implementatie en kwalificatie: de
installatie en kwalificatie van de originele meetrapportproducenten, verse kraanecho/eigenaarschap,
hydraulische voorwaarden en de beoordeelde fysieke zend-/stoproute. De huidige
software heeft daarom geen ingevuld proefprofiel/adressering en houdt E32-TX en
standaardactuatie geblokkeerd. Een diagnostische apparaattemperatuur is geen
stilzwijgend gekwalificeerde ruimtemeting.

## Update, controle en herstel bij uiteindelijke vrijgave

De definitieve publicatie bevat de exact gecontroleerde firmware-/HA-pakketten,
bron, toepasselijke notices, checksums, versies en testresultaten. Firmware gaat
via de bestaande normale updater. HA gaat via de bestaande bevoegde HA-agent met
back-up en nacontrole. Programma, bindings en identiteiten moeten behouden blijven.

De herstelroute en fysieke aansluit-/stopvoorwaarden worden vóór vrijgave aan de
exacte kandidaat gekoppeld. Dit concept verleent zelf geen publicatie- of installatieopdracht. De afzonderlijk
geautoriseerde passieve alpha23/dev29-uitrol staat in WORKBOARD; die bewijst
geen succesvolle fysieke ketelproef.

- Taal: E32-menu en herstelpagina’s bieden English/Nederlands met een onthouden
  browserkeuze; Engels is standaard en terugval. Vaste én dynamische teksten
  gebruiken één catalogus. HA-kamerkaart/weekplanner volgt de HA-profieltaal;
  Nederlandse native vertalingen zijn aangevuld. Statische opgeslagen
  Lovelace-dashboardteksten blijven consequent Engels omdat ze geen taalcontext
  per gebruiker hebben. Eigen namen en technische identifiers blijven behouden.
