# Eerste bèta: ketel aansluiten, gegevens ontvangen en aansturing beproeven

**Latere proefwaarneming:** na de installatieacceptatie toont een nieuwe directe
lezing een afgeronde configuratie-uitlezing en nulvraagproef met gemelde stop:
3 voltooide buswisselingen, 0 antwoordfouten, 2 nulframes en 0 positieve frames.
De hoofdagent gaf deze proefcommando's niet; de status identificeert de bediener
niet. De aanvoer was62°C, waardoor warmte terecht op `flow_outside_trial_limits`
bleef geblokkeerd (vereist5–<50°C). [Oorspronkelijke waarneming en hashes](BETA4-FIRST-ZERO-OBSERVATION-20261026.json).
Dit actualiseert de eerdere tekst “nog geen proef”: de nulvraag is nu in software
als afgerond gezien; fysieke waarneming en positieve warmte-/stopproef blijven open.


**Daarna werkelijk uitgevoerd op opdracht:** de CV-instellingen zijn opnieuw
uitgelezen en de nulvraagproef is met latere stopmelding voltooid. De aanvoer
bleef54°C; er is geen positieve warmtevraag verstuurd. De gebruiker heeft daarna
50°C voor tien minuten gevraagd. Dat vereist de gewijzigde beta.5-proefsoftware;
de onderstaande beta.4-grenzen beschrijven de geïnstalleerde versie.
[Uitvoeringsbewijs](BETA4-ATTENDED-ZERO-20261026.json) en
[actuele vervolgstap](NEXT-RELEASE.nl.md#actuele-proef-nulvraag-uitgevoerd-tien-minuten-warmte-gevraagd).

## Actuele beta.4-voorbereiding: bediende commissioningproef

Beta.4 is gepubliceerd, native geïnstalleerd en onafhankelijk geaccepteerd op
26 oktober. [Installatiebewijs](update-acceptance/e32-beta4-20261026.json).
De afzonderlijke handmatige proefroute is aanwezig; er is nog geen fysieke proef
uitgevoerd. De onderstaande oudere checkpoints beschrijven de passieve
voorbereiding; de actuele proefvoorwaarden zijn:

1. Controleer na de toegelaten installatie de exacte versie/bron en bevestigde
   boot; dit is voor beta.4 afgerond. De eerdere beta.3-installatieacceptatie
   blijft als historische lacune afzonderlijk open.
2. Bedien de proef lokaal en houd een onafhankelijke fysieke stop beschikbaar.
   Koppel Tado als schrijver los en houd de vereiste radiatoren/afgifte open.
   Bevestig uitsluitend voorwaarden die op dat moment werkelijk gelden.
3. Open **Keteltest**, bevestig exclusief busbezit en onafhankelijke stop, en
   gebruik **CV-instellingen uitlezen** als de originele Classic-instellingen
   ontbreken of ouder dan tien minuten zijn. Er volgt één begrensde leesopdracht.
4. Voer eerst de **nulvraagproef** uit. Kijk naar de echte latere stopmelding;
   een verzonden frame, HTTP-antwoord of oude nulwaarde is geen stopbewijs.
5. Voor warmte moet de gemeten aanvoer onder50°C liggen (profielvenster5–<50°C).
   Wacht bij een hete ketel op afkoeling; niet door de blokkade heen bedienen.
   Verklaar het open afgiftepad, lees de ketelmanometer en voer de
   waarde in bar in (1,1–2,5). Bereid bijvoorbeeld **40 °C, 10 seconden** voor.
   Deze voorbereiding doet opnieuw een nulvraag en wacht op een latere stopmelding.
   De manometerverklaring geldt maximaal twee minuten en moet per proef opnieuw.
6. Druk pas daarna afzonderlijk op **Start** en bevestig. Houd de proefpagina
   zichtbaar: de operatorlease is vijf seconden; maximale duur is zestig seconden.
   **Stop** blijft een afzonderlijke actie. Controleer de latere ketelmelding
   en naloop; bij onduidelijkheid gebruik je de onafhankelijke lokale stop.
7. Leg werkelijke telegrammen, ontvangsttijden, ketelgedrag en stop/herstel vast.
   Draag gecontroleerd terug over aan Tado. B07–B09/B14 zijn pas met het echte
   bewijs af te tekenen; deze instructie is geen uitgevoerde proef.

Automatische zones, kraanuitvoer en blijvende ketelinstellingen blijven uit.
De manometerwaarde is een operatorwaarneming, geen digitale keteltelemetrie.

## Oudere voorbereidingscheckpoints

Opdracht van 23 oktober 2026: doorwerken tot één samenhangende eerste bèta voor
het koppelen van de ketel, terugmelden van gegevens en testen van de aansturing.
De huidige geïnstalleerde passieve basis is E32 **v0.1.0-e32v2-beta.1** en
HA **0.4.0b1**, bron `5e3ed30653d93b09dd65b5305accd65d079c0c06`.
[Installatie en onafhankelijke nacontrole](INSTALLATIE-BETA1-20261025.nl.md).
Alpha28/dev37 is een historische voorganger. Nieuwe bronverbeteringen zijn nog
niet geïnstalleerd; actieve ketelsturing blijft geblokkeerd. Vervolgontwikkeling gebeurt op
`work/beta-boiler-20261023`. De actuele afvinklijst staat in
[WORKBOARD](WORKBOARD.nl.md); deze tekst is geen actieve bèta-vrijgave.

## Wat de bèta moet opleveren

1. Via Settings → Keteltest zien of EMS aanstaat en verse ketelberichten
   binnenkomen. Geen seriële monitor nodig voor de normale ontvangstcontrole.
   Protocolfamilie, ouderdom, wachtrijverlies, afgekeurde telegrammen en
   UART-fouten helpen onderscheid maken tussen geen ontvangst en onbruikbare data.
2. Aanvoer, retour en gemeld brandervermogen tonen met bronkwaliteit en leeftijd.
   Ontbrekende of verouderde waarden worden geen nulmetingen. Afgeleide CV/DHW
   blijven afgeleid; historisch onbetrouwbare brander/pomp/ventilatorbits worden
   geen fysieke bevestiging. Een tegenstrijdige protocolfamilie blokkeert bruikbare
   waarden in de proefweergave. Een download bevat ontvangstbewijs, geen vrijgave.
3. Een expliciet gestarte, eindige actieve proef met begrensde temperatuur en
   looptijd, exclusief eigenaarschap, altijd bereikbare stopactie en afzonderlijke
   terugmelding van opdracht, verzending en waargenomen ketelreactie. Gewone
   kamerregeling mag niet tegelijk opdrachten naar de ketel sturen.
4. Eerst stop in rust, daarna positieve vraag en expliciete stop, gevolgd door
   controle van CV/DHW en naloop. Geen terugmelding is geen geslaagde stop.
   Een softwaretijdslimiet geldt niet als bescherming bij stroomuitval van de E32.
5. Eén gekoppeld pakket met firmware, HA waar nodig, testverslag, update- en
   herstelpad. Niet telkens een nieuwe alpha installeren voor een losse wijziging.

## Afzonderlijke nulvraagproef — software voorbereid

De ontwikkelversie bevat onder Settings → Keteltest een afzonderlijke knop
**Nulvraagproef uitvoeren**. Dit is een expliciete fysieke opdracht zodra een
beoordeelde zender is aangesloten; openen van de pagina voert niets uit. De
geïnstalleerde passieve firmware en de fysieke TX-lock worden hierdoor niet veranderd.

Deze proef accepteert geen aanvoertemperatuur of warmteduur en kan nooit een
positieve warmtevraag selecteren. Beoordeelde stop-/feedback-/operator-/zendtiming,
exclusief eigenaarschap, een onafhankelijke stopmogelijkheid en verse Classic-
rapporten blijven vereist. Warmteprofiel en warmte-afgiftegoedkeuring zijn voor
deze uitsluitend intrekkende proef geen vereiste. Dat kwalificeert ze niet.

Pas na een werkelijk verzonden nulvraag én strikt latere gemelde CV-uit/0%
modulatie wordt de proef afgerond. Deze twee velden zijn ketelrapporten, geen
onafhankelijke fysieke warmtemeting. Een timeout of onzekere verzending geldt
als fout; positieve vraag kan niet worden hervat. Een latere warmteproef vereist
nieuwe expliciete voorbereiding met warmtevoorwaarden en een nieuwe stopbasis.
Het vervangen van Tado, de passende fysieke uitvoering en het productieprofiel
blijven onderdeel van de pre-TX-acceptatie; dit document start geen proef.

## Bekende aansluiting en ontbrekend bewijs

Bekende keten uit de bestaande onderzoeksnotities: Tado **of** E32 → EMS →
Bosch EasyControl Adapter 8737908035 V2.3 → iRT → Nefit Ecomline Classic
HRC 22H/UBA. Model en adapterrevisie zijn door de gebruiker opgegeven. Twee actieve
masters tegelijk zijn geen proefopstelling. Het gedrag bij verlies van EMS,
convertervoeding en iRT is nog niet fysiek vastgesteld. Zolang Tado actief blijft,
blijft de E32 uitsluitend passief.

Het opgeslagen historische nulcommando bevestigt een latere gerapporteerde CV-stop
en nul brandervermogen; het bewijst geen autonome stop bij communicatiewegval.
De E32-bron houdt TX daarom nog geblokkeerd. De fysieke voorwaarden in
`docs/BBQKEES_E32V2.md` (polariteit, bias, EMS/HT3-timing, arbitrage/echo en
herstel) zijn geen gevolg van een geslaagde softwarebuild. Een gemeten juiste
interface en een concrete onafhankelijke stop/herstelmogelijkheid zijn nodig
voordat de actieve proef gekoppeld kan worden aan echte TX.

Het bestaande onderzoek staat in de hoofdwerkmap onder
`docs/modern-thermostat/KETELSTOP-VOORPROEF.nl.md`, met bewijs onder
`out/critical-path-20261022/SAVED-STOP-RECHECK.json`. Dat onderzoek is geen nieuw
fysiek proefresultaat. De eerste bèta mag geen algemene EMS+-opdrachten naar deze
Classic-keten sturen. Een verwisselbare compileervlag is geen TX-vrijgave.

## Uitvoering en bewijs bijhouden

- Ontvangstdiagnose: software aanwezig in deze ontwikkeltak; native regressie
  omvat opgeslagen CRC-geldige telegrammen, verkeerde afzenders, requests/echo's,
  onvolledige velden, invalid/stale, 64-bit tijd en protocolconflict.
- Webproef: echte meegeleverde pagina met fixture-HTTP op 1280, 390 en 320 pixels;
  alleen GET, onbetrouwbare/oude/onbekende waarden onderdrukt, fout wist vorige
  weergave, downloaden bevat geen configuratie/credentials, navigatie stopt polling.
  Dit bewijst geen fysieke busontvangst.
- De eindige proefpolicy, controller/HTTP/webbediening, gedeelde poll-executor
  en Classic 0x1A-flow/nulencoder zijn inmiddels gebouwd en getest. De standaard
  adresseerstructuur/proefvoorwaarden weigeren nog alle verzending; board-TX blijft
  geblokkeerd. Beoordeeld installatieprofiel, bronadres/masker, fysieke UART-/stop-/
  flowvoorwaarden en gezamenlijke releaseverificatie blijven open. Ontvangstdiagnose
  alleen voldoet niet aan de gevraagde eerste bèta. Actuele status: WORKBOARD B04–B14.
- Voor de normale ruimteketen blijven de fysieke temperatuurbron, TRV en
  SOURCE/config-ACK-acceptatie open. Een diagnostische apparaattemperatuur of
  ontbrekend meetprofiel wordt niet stilzwijgend een gekwalificeerde ruimtesensor.

De passieve gezamenlijke release alpha23/dev29 is gepubliceerd en via de normale
updater geïnstalleerd; bewijs staat onder `out/next-release-20261024/`.
Vervolgbron en deadlinecontroles staan onder `out/pre-tx-preparation-20261024/`.
Er is geen actieve bèta vrijgegeven of fysieke zendopdracht uitgevoerd.

## Grens vóór de eerste fysieke zendproef

De softwareketen heeft afzonderlijke grenzen: oorspronkelijke meet-/kraanontvangst,
profiel-/eigenaarschapstoets, proefpolicy, laatste pollcontrole, UART-voltooiing en
strikt latere stopwaarneming. Een groene test bij één grens heft de andere niet op.
Bij vertraagde verwerking blijven warmtevraag-, lease- en stopdeadlines absoluut;
een late uitmelding maakt een verlopen proef niet alsnog geslaagd.

Vóór een nulvraag naar de echte installatie ontbreken nog het beoordeelde
adres/masker en proefprofiel, elektrische TX-kwalificatie, één actieve eigenaar,
het afgifte-/nalooppad en een onafhankelijke stopmogelijkheid. Ook een nulvraag is
een zendopdracht en valt buiten de huidige uitsluitend passieve toestemming.
De eerste positieve vraag volgt pas na een gecontroleerde nulproef met verse
gemelde stop. Voor automatische kamerregeling zijn daarnaast de oorspronkelijke
ruimtebron en kraan, causale echo/readiness en uitval/fallback afzonderlijk nodig.
Geen van deze fysieke voorwaarden wordt door modelselectie of een compileervlag
ingevuld.


De modelgebonden [pre-TX-acceptatiekaart](ECOMLINE-PRE-TX-ACCEPTATIE.nl.md) bevat
de op 24 oktober opnieuw beoordeelde fabrikantbronnen en de nog benodigde
installatiegegevens. Zij vult geen adres, proefgrens of gegarandeerde stoptermijn
in en autoriseert geen verlies- of zendproef.

## Praktisch testplan voor de actieve bèta — 24 oktober 2026

Dit is het gevraagde toekomstige draaiboek, geen opdracht om nu te zenden.
De melding van voortdurend pendelen wordt eerst afzonderlijk onderzocht met
actuele zendstatus en ketel-/Tado-geschiedenis. Een onverklaarde instabiele
begintoestand is geen geschikte nulmeting voor een zendproef.

### Volgorde en voorwaarden

| Stap | Uitvoering | Vereiste uitkomst vóór de volgende stap |
| --- | --- | --- |
| 0. Pendelen onderzoeken | Alleen lezen: geïnstalleerde versies, TX-/polltellers, uitgangsblokkades, aanvoer/retour, gemeld vermogen, CV/DHW en beschikbare Tado-vraag naast de gemelde start-/stoptijden leggen | Actueel zendgedrag vastgesteld; werkelijke starts onderscheiden van onbetrouwbare statusbits. Oorzaak of een concrete vervolgmeting vastgelegd, stabiele beginsituatie beoordeeld |
| 1. Passieve nulmeting | Onder bestaande Tado-regeling gedurende een afgesproken observatievenster ketelreactie registreren; geen kraan-/ketelopdracht. Bij voorkeur minstens één volledige vraag-/rustovergang waarnemen | Ontvangstkwaliteit/leeftijd bekend; CV en tapwater gescheiden; bestaande starts en temperaturen als referentie opgeslagen |
| 2. Fysieke proefkaart beoordelen | B09/pre-TX-kaart invullen: werkelijke interface/polariteit/arbitrage, aantoonbaar iRT aan de ketelzijde van de adapter (groene led alleen volstaat niet; zie pre-TX-kaart), adres/masker, één actieve eigenaar, open afgiftepad/minimumflow/naloop, onafhankelijke stop en herstel | Passende bron-/interface-/installatievoorwaarden vóór de actieve kandidaat beoordeeld; daadwerkelijke overdracht volgt pas bij stap4. Geen automatische keuze van zendadres of grenswaarden uit modelnaam/ontvangst |
| 3. Softwarekandidaat bevriezen en installeren | Alle voorbereide onderdelen bundelen; volledige CI, firmwarebuild en pakket-/bronhashes controleren. Na kandidaatacceptatie één installatie via de bestaande HA-specialist, met back-up, herstelgegevens en onafhankelijke readback | Exacte proefkandidaat herkenbaar; regressie geslaagd; algemene uitgangen geblokkeerd. Een handmatige zendvariant vereist de bij stap2 beoordeelde bronvrijgave. Installatie is geen startopdracht of geslaagde ketelproef |
| 4. Stopproef in rust | Na afzonderlijke fysieke proefvrijgave Tado gecontroleerd als schrijver overdragen; één eindige nulproef via de normale testbediening. Verzending en strikt latere stopwaarneming apart registreren | Geen onverwachte warmtevraag; echte zendvoltooiing en verse gerapporteerde CV-stop binnen vooraf beoordeelde termijn. Geen serviceacceptatie of oude nul als bewijs |
| 5. Eén begrensde warmtevraag | Alleen na stap4: één lage, vooraf beoordeelde temperatuurvraag met korte eindige looptijd, toezicht en open afgiftepad. Geen gewone kamerregeling tegelijk | Gevraagde waarde, werkelijk verzonden telegram en latere ketelreactie aantoonbaar verbonden; geen ongewenste starts of overschrijding |
| 6. Expliciete stop en naloop | Warmtevraag intrekken via dezelfde normale route; CV-stop, vermogen, temperaturen en beoordeelde naloop volgen | Strikt latere stop binnen de vastgelegde termijn; afgiftepad tijdens naloop behouden; geen spontane hervatting of achtergebleven positieve vraag |
| 7. Uitval apart beproeven | Pas na geslaagde normale stop en beoordeelde onafhankelijke stopvoorziening: HA-uitval, MQTT-uitval, bronverlies en E32-/communicatieverlies afzonderlijk volgens hun eigen proefkaart | Elke route heeft eigen gemeten stop-/terugvaluitkomst. Een geslaagde softwarelease bewijst geen stop bij E32-voedingsverlies |
| 8. Terugzetten en beoordelen | Proef beëindigen, positieve opdrachten ongeldig maken, E32 weer RX-only en gecontroleerd Tado als enige schrijver herstellen | Versies, TX-blokkades, normaal regelgedrag en bewaarde configuratie teruggelezen; verslag met PASS/FAIL/UNKNOWN per proef |

Stap4–8 worden niet uitgevoerd zolang de proefkaart niet compleet is. Fysieke
bedrading of overdracht gebeurt door een geschikte uitvoerder; dit document
bevat geen instructie om nu aansluitingen los te nemen. De grenzen voor maximale
temperatuur, proefduur, feedbackouderdom, stoptermijn en naloop worden vooraf
uit het beoordeelde installatieprofiel overgenomen en in het verslag gezet.
Ontbreekt één grens of de onafhankelijke stoproute, dan start de proef niet.
Een willekeurige temperatuur of een software-timeout vult dit niet in.

### Direct afbreken

Bij onverwacht starten/pendelen, te hoge temperatuur, verlies van het afgiftepad,
conflicterend eigenaarschap, foutstatus, verouderde feedback of uitblijvende stop
wordt de proef afgebroken via de vooraf beoordeelde stoproute. Geen automatische
herhaling na een onzeker resultaat. Daarna pas de vastgelegde herstelroute naar
Tado uitvoeren en controleren; niet aannemen dat herverbinden oude vraag wist.

### Kraanproef en vrijgave van automatische kamers

De begrensde handmatige ketelproef is een aparte mijlpaal. Voor automatische
ruimteregeling blijven M2 en B04–B06 vereist: echte geschikte kamerbron, normale
FW→HA-opdrachtroute met HA-ontvangergrant, oorspronkelijke native kraantransactie
en causale echo, beoordeelde modus/eigenaarschap en actuele hydraulische feiten.
Een handmatig reagerende ketel sluit die poorten niet. De kraanproef gebruikt
haar eigen opstelling en veroorzaakt geen ketelvraag.

### Wanneer kan de bèta uit?

De volgende gezamenlijke softwarekandidaat kan vóór fysieke TX worden geleverd
met de uitgangen geblokkeerd. De actieve bèta voor keteltesten volgt pas na de
software-, installatie- en stopvoorwaarden hierboven; automatische kamerregeling
pas na de aanvullende M2-poorten. Een kalenderdatum is nu niet onderbouwd omdat
het pendelonderzoek, fysieke TX-/stopkwalificatie en native kraanbevestiging nog
openstaan. De resultaten bepalen de datum, niet een nieuwe alpha-naam.

Het verslag bevat minimaal: exact pakket/bron, tijdlijn van opdracht →
zendvoltooiing → verse ketelreactie → stop/naloop, beoordeelde grenzen,
telemetriekwaliteit, feitelijke operatorwaarneming en herstelcontrole. Ruwe
privé-identiteiten en credentials komen niet in het openbare verslag.
