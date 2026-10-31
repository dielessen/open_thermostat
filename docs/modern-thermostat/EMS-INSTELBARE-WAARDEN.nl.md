# Instelbare EMS-ketelwaarden — plan (na 1.0)

Opgesteld 30 oktober 2026, op verzoek van de eigenaar. Dit is alleen een plan:
er wordt pas na 1.0 aan gebouwd, naast het lezen van EMS+ (1.1). Niets hierin
verandert de huidige firmware, de schrijfgrenzen of de actieve-regelpoort.

De wens van de eigenaar in eigen woorden: ketels met instelbare (schrijfbare)
entiteiten moeten die in de HA-integratie aangeboden krijgen. Het moet bekend
zijn welke entiteiten voor het model relevant zijn en of ze echt iets doen. Bij
de eigen ketel (iRT, via een adapter op EMS) weten we dat nog niet. Instellingen
die normaal een monteur doet, komen verborgen onder "Geavanceerd", met een
waarschuwing dat aanpassen op eigen risico is.

## Wat we nu weten

**De EMS-ESP-lijst zegt niet wat een model ondersteunt.** In de entiteitenlijst
van EMS-ESP ([All Entities](https://docs.emsesp.org/All-Entities), CSV-download
van 30 oktober, sha256 `760694b0…5d33`) hebben 27 van de 31 ketelproductgroepen
precies dezelfde 121 entiteiten, waarvan 58 schrijfbaar. Daaronder valt ook
product 211, de EasyControl Adapter van de eigenaar. De lijst is dus per
apparaatklasse, niet per model. "Schrijfbaar" betekent alleen dat EMS-ESP er
een commando voor heeft. Het bewijst niet dat de ketel de waarde aanneemt,
bewaart of ernaar handelt.

**Bij veel waarden is het bereik onbekend.** Van de 35 numerieke schrijfbare
waarden bij product 211 hebben er 11 het bereik 0..0, zoals `burnminpower`,
`pumpmodmax`, `dhw.seltemp` en `dhw.hyston`. Grenzen moeten we per model zelf
vaststellen.

**Licentie.** EMS-ESP valt onder LGPL-3.0. We gebruiken de gedocumenteerde
offsets alleen als referentie en schrijven eigen tabellen en code. Dat volgt de
bestaande afspraak in [EMS-ENTITY-ACCESS-REVIEW](EMS-ENTITY-ACCESS-REVIEW.en.md)
en `public/ems/SOURCES.json`.

**Wat de firmware al heeft:**

- Vier Classic-instellingen in telegram 0x16 (UBAParameters):
  `heatingactivated`, `heatingtemp`, `burnminperiod` en `pumpdelay`. Ze staan in
  `src/EMS/ClassicBoilerSettingSpec.h`.
- Per schrijfactie een transactie (`ClassicBoilerSettingTransaction.h`): eerst
  het schrijfbericht, dan de schrijfstatus van de bus, dan een nieuwe leesvraag
  van 0x16, en die moet de nieuwe waarde terugmelden (`setting_read_back`). Een
  echo of busbevestiging geldt uitdrukkelijk niet als bewijs.
- De service (`ClassicBoilerSettingsService.h`) eist login, een bevestiging ter
  plaatse en een geldige `boot_id` en revisie. Blijvend schrijven staat in de
  standaardfirmware uit (`settings_transport_unqualified`).
- [BOILER-WRITE-INVENTORY](BOILER-WRITE-INVENTORY.json) en de catalogus op de
  pagina Keteltest tonen alle EMS-ESP-definities. Er worden nooit schrijfrechten
  uit de catalogus afgeleid.

Dit plan bouwt daarop voort. Het mechanisme schrijven → schrijfstatus →
teruglezen blijft de basis. Er komt een uitgebreidere bewijsketen bij, plus een
profiel per ketel.

## Bewijsniveaus: doet een instelling echt iets?

Per combinatie van product-ID, versie van ketel of adapter en instelling legt
de E32 vast hoe ver het bewijs reikt. Een hoger niveau omvat de lagere.

| Niveau | Naam | Wat is aangetoond | Hoe |
| --- | --- | --- | --- |
| L0 | Verzonden | Het bericht ging de bus op en de bus bevestigde het | Echo en schrijfstatus. **Bewijst niets** over de ketel. |
| L1 | Teruggelezen | Het apparaat meldt de nieuwe waarde | Nieuwe leesvraag na de schrijfactie; de waarde komt overeen (bestaat al voor de 4 Classic-waarden). |
| L2 | Blijvend | De waarde blijft staan | Na een aantal minuten en na minstens twee eigen uitzendcycli van het apparaat nog steeds gelijk; geen terugval. Vangt een adapter die de waarde later vanuit de ketel overschrijft. |
| L3 | Effect gezien | De ketel gedraagt zich ernaar | Onafhankelijke meting van gedrag, zie hieronder. |

Er is ook een negatieve uitkomst: **"niet ondersteund op dit model"**. Dat geldt
bij een afgewezen schrijfstatus, een terugleeswaarde die niet overeenkomt, of
een waarde die binnen de L2-termijn terugspringt. Zo'n uitkomst is ook kennis:
de instelling wordt dan op dat model niet aangeboden.

**Voorbeelden van L3-effecten** (meting met wat de E32 al ontvangt):

| Instelling | Verwacht, meetbaar effect |
| --- | --- |
| `heatingtemp` (max. aanvoer) | Het door de ketel gemelde aanvoersetpoint en de gemeten aanvoer komen niet boven de nieuwe grens |
| `burnminperiod` | Brander-uit-tijden in de `BurnerCycleMonitor` worden niet korter dan de waarde |
| `pumpdelay` | De pompstatus blijft na branderstop ongeveer de ingestelde minuten aan |
| `dhw.seltemp` | Het tapwatersetpoint in de tapwatertelegrammen volgt; de tapwatertemperatuur gaat ernaartoe |
| `dhw.comfort` (comfort/eco) | Over een dag: wel of geen warmhoudcycli zonder tappen (`DhwEpisodes`) |
| `heatingactivated` uit | Geen CV-branderbedrijf terwijl er wel warmtevraag is |
| `summertemp` | Boven de grens geen CV-vraag meer naar de ketel |

Niet elke instelling heeft een meetbaar effect. Die blijven dan op L2 staan, en
in de interface staat duidelijk "effect niet aangetoond".

## Begeleide controle in de firmware

Dit is een nieuwe, bijgewoonde controleroute. Ze doet nooit iets op de
achtergrond.

1. **Één instelling tegelijk.** De gebruiker kiest een instelling en een
   testwaarde. De E32 leest en bewaart eerst de huidige waarde. Zonder geldige
   uitgangswaarde volgt geen schrijfactie.
2. Daarna loopt de bestaande transactie: schrijven, schrijfstatus, teruglezen
   (L1).
3. **Bewaken.** Gedurende een vaste termijn controleert de E32 of de waarde
   blijft staan (L2), en waar dat kan of het verwachte effect optreedt (L3). Voor
   L3 kan een wachttijd nodig zijn, bijvoorbeeld een brandercyclus of een dag
   voor comfort/eco. De pagina toont de voortgang en wat er nog ontbreekt.
4. **Automatisch terugzetten** naar de oorspronkelijke waarde als een stap
   mislukt, de termijn verloopt, de gebruiker afbreekt of de E32 herstart. Een
   herstart wordt hervat vanuit NVS met de bewaarde uitgangswaarde. Behouden
   blijft de waarde alleen als de gebruiker dat aan het eind bevestigt.
5. **Nooit tijdens** een keteltest, een overgang naar of van actieve regeling,
   een update, of terwijl een andere instelling loopt. Dit is dezelfde poort als
   nu (`boilerClaimed`, `boilerSettingsMutationBlocked`).
6. **Uitkomst opslaan** in een **capaciteitsprofiel** op de E32: product-ID,
   versie, instelling, niveau, gemeten grenzen, datum en firmwareversie. Het
   profiel gaat retained naar HA (`fw/config/boiler_capabilities`) en zit in de
   instellingenback-up.
7. **Gedeelde profielen.** Profielen die we beoordeeld hebben, kunnen als tabel
   in de repository worden meegeleverd, zodat andere gebruikers met hetzelfde
   product niet alles zelf hoeven te testen. Ze starten dan op "bekend van een
   ander, nog niet zelf bevestigd". Een export knop levert een JSON zonder
   persoonlijke gegevens, die iemand vrijwillig kan delen. Een meegeleverd profiel
   geeft nooit zelf schrijfrechten: L1 op de eigen ketel blijft nodig.

## Het geval van de eigenaar: iRT-ketel achter een adapter

Opstelling: een Nefit Ecomline Classic HRC 22H met daarop een Bosch EasyControl
Adapter 8737908035. De adapter staat op de EMS-bus als ketel 0x08 (EMS-ESP
product 211). Hij vertaalt EMS naar iRT. Wat de E32 terugleest, kan daardoor
uit het geheugen van de adapter komen en niet uit de ketel. Een L1 is hier dus
zwak bewijs.

- **Eis:** voor elke instelling L2 én L3 voordat ze als gebruikersinstelling
  wordt aangeboden. Zonder meetbaar effect blijft ze verborgen.
- **Stap 1, alleen lezen.** Het display van deze oude ketel toont alleen
  servicecodes, geen instellingen (eigenaar, 30 oktober). Vergelijk daarom de
  servicecode op het display met de servicecode die de adapter in zijn
  monitortelegram meldt, in verschillende toestanden: rust, CV en tapwater.
  Komen ze steeds overeen, dan spiegelt de adapter de ketelstatus echt. De
  betekenis van de codes halen we uit de servicedocumentatie van Nefit. De
  instelwaarden zelf (0x16, tapwater) kunnen we niet met het display
  vergelijken. Voor die waarden telt alleen L3, dus een gemeten effect.
- **Stap 2, één schrijftest.** Bijgewoond, op een instelling met weinig risico
  en een goed meetbaar effect, zoals `pumpdelay` of de tapwatertemperatuur een
  paar graden. Met automatisch terugzetten.
- **Stap 3.** Alleen wat L3 haalt, komt in het profiel van product 211 met de
  aantekening "via iRT-adapter". Bosch documenteert een terugval naar aan/uit als
  de iRT/OT-detectie mislukt. Daarom wordt na elke adapterherstart opnieuw
  gecontroleerd.

**Ketels die direct EMS spreken** (bijvoorbeeld de Classic-productgroepen 64, 95
en 123, en de EMS+-ketels) melden hun eigen parameters terug. Voor
gebruikersinstellingen is daar L1 + L2 meestal genoeg. L3 gebeurt waar het
meetbaar is, en een negatieve L3 overschrijft altijd een positieve L2.

## Indeling: wat bieden we aan, en waar

**Gebruikersinstellingen** (normaal zichtbaar zodra het profiel het vereiste
niveau haalt):

| Instelling | EMS-ESP-naam |
| --- | --- |
| CV aan/uit | `heatingactivated` |
| Tapwater aan/uit | `dhw.activated` / `dhw.tapactivated` |
| Tapwatertemperatuur | `dhw.seltemp` |
| Comfort / eco | `dhw.comfort` of `dhw.comfort1` |
| Eenmalig opwarmen | `dhw.onetime` |
| Zomerstand / zomertemperatuur | `summertemp` |
| Maximale aanvoertemperatuur | `heatingtemp`, nooit boven een ingesteld systeemmaximum. Dat maximum is een eigen E32-instelling, bijvoorbeeld 60 °C bij vloerverwarming, en de E32 dwingt het af. |

**Geavanceerd (monteursinstellingen).** Deze staan in een aparte sectie "Geavanceerd" met een waarschuwing en
expliciete bevestiging ("ik begrijp dat dit monteursinstellingen zijn en pas ze
op eigen risico aan"):

- branderinstellingen: `burnminpower`, `burnmaxpower`, `selburnpow`, `burnminperiod`;
- hysterese: `boilhyston`, `boilhystoff`, `boil2hyston`, `boil2hystoff`;
- pomp: `pumpmode`, `pumpcharacter`, `pumpmodmin`, `pumpmodmax`, `pumpdelay`, `pumpontemp`, pompkick (`pumpkickhour`, `pumpkickday`, `pumpkickdelay`);
- stooklijn van de ketel: `curveon`, `curvebase`, `curveend`;
- vorst en noodbedrijf: `nofrostmode`, `nofrosttemp`, `emergencyops`, `emergencytemp`;
- tapwater: `dhw.maxtemp`, `dhw.maxpower`, `dhw.flowtempoffset`, `dhw.hyston`, `dhw.hystoff`, `dhw.disinfectiontemp`, `dhw.circmode`, `dhw.circ`, `dhw.circpump`, `dhw.dhwprio`, `dhw.chargeoptimization`, `dhw.seltemplow`, `dhw.tempecoplus`, `dhw.seltempsingle`;
- onderhoud: `maintenance`, `maintenancetime`, `maintenancedate`;
- correctie van energietellers: `nrgheat`, `dhw.nrg`, en `nompower` als gegeven voor de energieberekening.

**Nooit als instelling aangeboden:**

- `selflowtemp` en `heatingoff`. Dit is de eigen regelroute van de E32. Ze
  blijven uitsluitend in handen van de regeling en de bestaande keteltest, zodat
  er geen tweede manier is om de ketel aan te sturen.
- `chimneysweeper` en `reset`. Dit zijn servicecommando's, geen instellingen.
  Hooguit later onder Geavanceerd: tijdgebonden, met waarschuwing, en `reset`
  alleen voor "storing resetten" na een expliciete melding.

## Home Assistant

- **Alleen bewezen instellingen.** HA maakt entiteiten alleen voor instellingen
  waarvan het capaciteitsprofiel het vereiste niveau haalt. Dat is L2, en voor
  de iRT-adapter L3. Een instelling die "niet ondersteund" is, krijgt geen
  entiteit. Dit hergebruikt de zichtbaarheid van het ketelprofiel uit de
  hotfix: `supported`, `not_fitted`, `not_reported`.
- **Entiteiten.** Het platform volgt het type: `number` (met eenheid en
  gemeten grenzen), `select` (enum) of `switch` (boolean). Ze krijgen
  `entity_category: config` en hangen onder het ketelapparaat.
- **Geavanceerd.** Deze entiteiten zijn standaard uitgeschakeld
  (`entity_registry_enabled_default: False`). Inschakelen kan alleen via een
  stap in de opties ("Geavanceerde ketelinstellingen") met een expliciet
  bevestigingsvakje en de waarschuwingstekst.
- **Geen optimistische toestand.** De entiteit toont altijd de teruggelezen
  waarde. Tijdens een schrijfactie staat er een attribuut `pending`. Het
  resultaat komt terug via MQTT: geaccepteerd, teruggelezen of afgewezen, met
  een reden. Een mislukte schrijfactie of terugval geeft een melding en een
  Repairs-issue met uitleg.
- **Schrijven** gaat via de bestaande, geauthenticeerde opdrachtroute met
  revisie en `boot_id`. Daarbij gelden dezelfde poorten als op de E32-pagina.
- **Teksten.** Alle teksten volledig in het Engels en het Nederlands, en de
  waarschuwing in gewone taal.

## Testerprogramma: resultaten delen via GitHub

De eigenaar vroeg op 30 oktober om een optie "tester": wie die kiest, deelt de
testresultaten met het project op GitHub.

- **Aanmelden.** In de HA-opties kies je "Tester". De E32 en HA voeren dan de
  begeleide controles uit zodra de gebruiker ze start, nooit ongevraagd.
- **Wat gedeeld wordt.** Alleen het capaciteitsprofiel:
  - productnummer, apparaatklasse en firmwareversies (E32 en ketel);
  - per instelling het bewijsniveau, het gemeten effect en "niet ondersteund";
  - het waargenomen bereik.

  Geen namen van ruimtes, geen IP- of MAC-adressen, geen Wi-Fi-gegevens,
  geen locatie en geen HA-entiteitnamen. De gebruiker ziet de volledige tekst
  voordat er iets verstuurd wordt.
- **Hoe het verstuurd wordt.** Met één klik op "Deel resultaat" in HA opent
  GitHub een vooraf ingevuld issue, via een issueformulier met het profiel als
  JSON. De tester verstuurt het met zijn eigen GitHub-account. Is de tekst te
  lang voor een URL, dan downloadt hij het bestand en voegt het als bijlage toe.
- **Aan onze kant.** Een GitHub Action controleert de JSON tegen het schema,
  geeft het issue labels (ketelgroep, productnummer) en zet resultaten van
  dezelfde ketelgroep naast elkaar. Een profiel gaat pas met de firmware mee
  na beoordeling, en na bevestiging door meerdere testers waar dat kan.
- **Waarom niet volledig automatisch.** Dan zou de E32 of HA zelf met een
  sleutel naar GitHub moeten schrijven. Een sleutel in openbare firmware wordt
  misbruikt (spam). Een eigen tussendienst kost onderhoud en verwerkt
  IP-adressen (privacy). Daar kijken we pas naar bij veel testers.
- **Terugtrekken.** De tester kan de optie altijd uitzetten. Eerdere issues
  blijven van de tester zelf en kan hij zelf sluiten.

## Fasering (na 1.0, naast het lezen van EMS+ in 1.1)

**Bijgesteld op 30 oktober (eigenaar).** Voor de eigen ketel is weinig bruikbaars
te schrijven. `selflowtemp` gebruikt de E32 al voor de regeling. Het doel van dit
plan is ondersteuning voor andere ketels en wat die kunnen. De bewijsketen moet
dus vooral werken voor ketels die rechtstreeks EMS praten. Daarvoor zijn testers
met zo'n ketel nodig, en gedeelde profielen (vraag 4) worden belangrijker.

| Fase | Werk | Klaar wanneer |
| --- | --- | --- |
| W1 | Eigen tabel met schrijfmetadata per apparaatklasse: telegram, offset, type, schaal, catalogusbereik, categorie (gebruiker, geavanceerd of nooit) en het vereiste bewijsniveau. Eén bron voor C++ en HA (`--check` in CI), in het formaat van de geplande tabel voor EMS+-lezen. | Tabel en generator met tests; geen nieuwe schrijfroute |
| W2 | Controleroute voor L0–L3 met terugzetten, capaciteitsprofiel in NVS, back-up en MQTT, getest met ketels die rechtstreeks EMS praten (testers met zo'n ketel). De adapter van de eigenaar krijgt alleen de servicecodevergelijking en hooguit één schrijftest | Profielen met echte uitkomsten per ketelgroep, inclusief "niet ondersteund" |
| W3 | HA: gebruikersinstellingen als entiteiten volgens het profiel | Alleen bewezen instellingen zichtbaar; geen optimistische toestand |
| W4 | Geavanceerde sectie op de E32-pagina en in HA, met waarschuwing en bevestiging | Standaard verborgen en uitgeschakeld |
| W5 | Schrijven op EMS+-ketels (telegramfamilie 0xE3–0xEA) | Dezelfde bewijsketen, eerst met een tester die zo'n ketel heeft |

Voorwaarde blijft dat blijvend schrijven per apparaatklasse dicht blijft totdat
die schrijfroute beoordeeld is. Dat is de bestaande afspraak.

## Open vragen voor de eigenaar

1. Mag de eigen ketel als eerste proefobject dienen, en welke instelling heeft
   de voorkeur voor de eerste schrijftest: `pumpdelay` of de
   tapwatertemperatuur?
2. ~~Kan het ketel display de waarden tonen?~~ Beantwoord op 30 oktober: nee.
   Het display toont alleen servicecodes; zie stap 1.
3. Moet "Geavanceerd" ook voor jezelf achter een extra bevestiging per
   schrijfactie blijven, of is één bevestiging in de opties genoeg?
4. Willen we gedeelde profielen van andere gebruikers verzamelen, bijvoorbeeld
   via GitHub-issues met de export, of alleen eigen beoordeelde profielen
   meeleveren?
