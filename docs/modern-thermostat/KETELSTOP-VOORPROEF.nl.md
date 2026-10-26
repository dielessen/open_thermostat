> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# F6-voorproef — ketelstop en terugval, 22 oktober 2026

Onderdeel van [PLAN §14](PLAN.nl.md#14-gefaseerde-uitvoering-en-acceptatiepoorten).
Read-only onderzoek van documentatie en bewaard bewijs. Geen nieuwe ketelproef,
TX, HA-/brokerbediening, configuratiewijziging of fysieke overdracht uitgevoerd.
Dit rapport is bewijs bij het werkbord, geen tweede afvinklijst.

## Uitkomst en installatieketen

**Stop bij wegvallen van de EMS-regelaar is nog niet bewezen.** Dat houdt de
vrijgave voor zelfstandig ketelbedrijf geblokkeerd. M1/M2-bronwerk zonder ketel,
F4-supervisor en F6-security kunnen volgens de WIP-limiet doorgaan.

Mark bevestigt op 22 oktober: de Bosch is een iRT↔EMS-converter en de Tado praat
EMS. De beschreven keten is dus Tado of E32 → EMS → Bosch-converter → iRT →
HRC22H/UBA. Tado en E32 zijn alternatieve regelaars; dit diagram vraagt geen
gelijktijdige aansluiting of tweede schrijver. Het protocol aan de E32-kant is
EMS; eigen native iRT op de E32 is hiervoor geen voorwaarde.

Dit is gebruikersbevestiging van de protocolketen. Exact onderdeel-/versienummer,
aansluitroute (rechtstreeks of extension kit) en het uitvalgedrag zijn nog niet
onafhankelijk vastgesteld. Busidentiteiten `09 EASY CONNECT/Ecomline` en
`17 Generic Thermostat` uit het oude dossier identificeren die fysieke details
niet. Er wordt geen model of bedrading uit die namen afgeleid.

## Wat bestaand bewijs wel vastlegt

De primaire commandolijst en complete Recorder-export van de proef op 16 oktober
zijn opnieuw rechtstreeks uitgelezen; de eerdere rapportconclusie is niet alleen
overgenomen. De herberekening staat in
[SAVED-STOP-RECHECK.json](../../out/critical-path-20261022/SAVED-STOP-RECHECK.json),
met SHA256 van de acht gelezen bewijsbestanden en het lokale controlescript.

| Waarneming op 16 oktober | Herberekend resultaat | Betekenis |
| --- | --- | --- |
| Verzonden opdrachten | Tien keer 50 °C, daarna één expliciete nul | Dit was een actieve start-/stopproef met werkende communicatie |
| Nulopdracht | 22:42:06 CEST | Een HA-opdracht, op zichzelf geen fysieke stop |
| CV-status naar uit | 22:42:17,825845 CEST, 11,825845 s na nul | Afzonderlijke keteltelemetrie ondersteunt het beëindigen van CV |
| Gemeld brandervermogen naar nul | 13,811910 s na nul | Aanvullende telemetrie; geen onafhankelijke vlamsensor |
| Geschiedenis | Twaalf entiteiten, geen ontbrekende vervolgpagina | Compleet voor het bewaarde proefvenster |
| Gepubliceerde `selflowtemp` | Blijft nul tijdens de proef | Dit terugmeldveld bewijst noch afwijzing noch stop |

Er is in deze proef **geen** gecontroleerde communicatiewegraking na de laatste
positieve vraag gemeten. Het laatste positieve bericht zomaar laten verlopen is
daarom niet gelijk aan de bewezen expliciete nul. Het handmatig terugplaatsen van
Tado is bovendien een herstelroute, geen automatische stop bij controlleruitval.
Marks latere melding dat Tado normaal werkt blijft een gebruikersbevestiging;
de historische proef wordt niet als nieuwe fysieke herstelproef herlabeld.

## Primaire documentatie en grenzen

- De [Bosch-handleiding 6720821559, Nederlandse pagina's 46–48](https://www.nefit-bosch.nl/media/country_pool/professioneel/documenten/thermostaten/6720821559.pdf)
  beschrijft omzetting tussen EMS en onder andere iRT. Zij onderscheidt
  communicatiestoringen aan thermostaat- en ketelzijde. In dit geraadpleegde deel
  staat geen gekwantificeerde veilige CV-stop na verlies van de EMS-regelaar.
  Dit is een relevante productfamiliebron; het exacte geïnstalleerde model is
  daarmee niet bewezen.
- De [officiële EMS-ESP-storingsdocumentatie](https://docs.emsesp.org/Troubleshooting#changing-a-value-works-at-first-but-is-then-reset-to-its-original-value)
  beschrijft overschrijven door andere regelaars en herstel van lokale
  ketelinstellingen bij sommige toestellen. Dat onderbouwt de noodzaak om de
  echte keten te kwalificeren, niet een HRC22H-timeout of herhaalinterval.
- De bewaarde `periodic-demand-research.md` van 16 oktober noemt evenmin een
  bewezen Classic-timeout. De daarin genoemde circa-minuutherhaling wordt niet
  tot veilige lease of stopgarantie verheven.

De online bronnen zijn op 22 oktober opnieuw geraadpleegd. De fabrikant-PDF was
via de webreader leesbaar; rechtstreeks downloaden gaf HTTP403. Er wordt daarom
geen nieuwe lokale PDF-hash of volledige offline bronarchivering geclaimd.

## Beslispunt nu en eerstvolgende bewijsactie

De onbekende uitkomst uit PLAN §12 is nu expliciet bereikt: voor autonome
verwarming is een passende, onafhankelijke uitvaloplossing nog niet aangetoond.
Een kortere softwarelease, extra MQTT-stop, watchdog of vaker nul sturen kan
uitval van de E32 zelf niet afdekken.

De eerstvolgende stap is het vaststellen van het exacte convertertype en de
bijbehorende fabrikantsemantiek voor verlies van EMS, verlies van de
convertervoeding en verlies van iRT. Daarna kan een geschikte fysieke uitvoerder
beoordelen of de bestaande keten een aantoonbare stop heeft of een onafhankelijke
hardwareoplossing nodig is. Een relais is hier slechts een te beoordelen optie;
er is geen relais-/aansluitontwerp of aanschafbesluit genomen.

Een latere afzonderlijke commissioningkaart moet per uitvalroute vastleggen:
ketel/adapter/softwareversie, laatst geldige vraag, tijd tot werkelijke CV-stop,
onderscheid CV/DHW, afgiftepad/pompnaloop, hersteld gedrag zonder oude vraag en
gecontroleerde terugkeer naar Tado. Geen verliesproef uitvoeren zolang stop,
toezicht en herstelroute niet concreet zijn. Dit document autoriseert die proef
niet en bevat geen uitvoerende busopdrachten.

## M1-softwarestap in dezelfde VS Code-branch

De native HA-opties tonen nu een specifieke fout wanneer het opgeslagen plan de
bestaande grens van acht totale UTC-overgangen of 4096 configuratiebytes
overschrijdt. De normale weekeditor kan meer bevatten dan dit eerste
ControlPlan-contract accepteert; de foutmelding maakt dat onderscheid zichtbaar.
Native preparefouten spreken over het tweekamerplan, in plaats van alleen DATA.

Tests gebruiken echte HA2026.10.2-opties/Store en de actuele C++-peer. Ze toetsen
ook behoud van leeg, geaccepteerd en staged journal, ongewijzigde kamerdata,
geen verzonden configuratie bij weigering en afscherming van onbekende fouttekst.
**151 verschillende gerichte native HA/C++-gevallen slagen:** 105 overige
regressiegevallen, 35 bruggevallen en 11 nieuwe controles. Twee oude
tekstverwachtingen in de brugtests zijn bijgewerkt naar de al bestaande
SOURCE-waarschuwing; een mislukte proef op ongewijzigd HEAD55bdf84 bevestigt de
oude mismatch. De veiligheids-/regelasserties zijn behouden. Logs, commands en
de samenvoeging zonder dubbeltelling staan in
[POSTCHECK.json](../../out/critical-path-20261022/POSTCHECK.json).
Dit sluit volledige weken/horizonrefresh, frontendbrowser of M2 niet af.

Rollback van dit lokale pakket: uitsluitend de gewijzigde HA-foutpresentatie,
bijbehorende tests en documentatie terugnemen vóór afhankelijke inzet. Geen
config-/journal-/NVS-/historiewisactie. De OpenClaw-canonical en productie zijn
door deze uitvoering niet gewijzigd.
