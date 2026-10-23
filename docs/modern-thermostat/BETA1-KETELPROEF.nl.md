# Eerste bèta: ketel aansluiten, gegevens ontvangen en aansturing beproeven

Opdracht van 23 oktober 2026: doorwerken tot één samenhangende eerste bèta voor
het koppelen van de ketel, terugmelden van gegevens en testen van de aansturing.
De geïnstalleerde basis is E32 alpha17 / HA dev23, broncommit
`86f99a96a9673424425d752f582ca4361e2f2b4c`. Nieuwe ontwikkeling gebeurt apart
op `work/beta-boiler-20261023`. Deze tekst is geen bèta-vrijgave.

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
Bosch iRT↔EMS-converter → iRT → HRC22H/UBA. Twee actieve masters tegelijk zijn
geen proefopstelling. Exact convertermodel/revisie en gedrag bij verlies van EMS,
convertervoeding en iRT zijn nog niet vastgesteld.

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

Actuele uitvoerbestanden: `out/beta-boiler-evidence-20261023/` in de hoofdwerkmap.
Nog geen nieuwe release gepubliceerd, geen firmware geïnstalleerd en geen echte
ketelopdracht verstuurd voor deze ontwikkeltak.
