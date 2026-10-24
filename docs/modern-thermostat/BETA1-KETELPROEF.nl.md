# Eerste bèta: ketel aansluiten, gegevens ontvangen en aansturing beproeven

Opdracht van 23 oktober 2026: doorwerken tot één samenhangende eerste bèta voor
het koppelen van de ketel, terugmelden van gegevens en testen van de aansturing.
De geïnstalleerde passieve basis is E32 alpha23 / HA dev29, broncommit
`5f31dd780a5b98d81048f9d592f8209e657d7305`. Vervolgontwikkeling gebeurt op
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
