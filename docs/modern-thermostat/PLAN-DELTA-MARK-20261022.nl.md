# PLAN-delta van Mark — 22 oktober 2026

**Voor:** OpenClaw (parent), enige canonieke schrijver van PLAN en WORKBOARD.
**Bron:** Marks branch `review/mark-vscode-20261021`, op basis van `defd2ae`.
**Aard oorspronkelijke planwijziging:** alleen documentatie. De latere lokale
software-uitvoering staat apart hieronder; geen installatie, publicatie of
verwarmingswijziging. Eisen R01–R31 en de acceptatiecriteria van
F0–F10 zijn inhoudelijk ongewijzigd; er zijn alleen verwijzingen bijgekomen.

## Nieuwe besluiten van Mark

1. **Tado V3/V3+ vervalt als regelaar** zodra OpenThermostat de ketel regelt. De
   ketelkoppeling wordt fysiek losgekoppeld (één schrijver). De Tado mag een
   kiesbare kamertemperatuurbron worden, bij voorkeur lokaal via HomeKit Controller.
   Tot en met de F6/F7-commissioning blijft hij de werkende verwarming en daarna de
   gedocumenteerde rollbackregelaar. PLAN §6.3, §12, §16 en §17.
2. **Kritisch pad:** een haalbaarheidsvoorproef van de ketelstop/timeout van de
   HRC22H en de fysieke terugval, zonder TX of ketelwrites, vóór verdere
   verbreding. Een negatieve of onbekende uitkomst legt het besluit uit §12 nu terug.
3. **WIP-limiet:** geen nieuwe F9-, F10- of P2-bronstages tot M2 bewezen is;
   lopend werk mag worden afgerond. PLAN §14, begin.

## Opschoning van PLAN.nl.md

- De kop bevat geen status meer; die staat alleen in WORKBOARD.
- Het besluitenlog van §1 (Mark11883/11944/11950/11956) is letterlijk verplaatst naar
  het nieuwe [BESLUITEN.nl.md](BESLUITEN.nl.md); §1 heeft een korte samenvatting.
- Eenduidige mijlpalen: **M1** = de softwareketen met twee kamers
  (ARCHITECTURE-DECISION §5), **M2** = de eerste fysieke kamerketen (één kamer, echte
  bron → E32 → configACK, plus een echte kraan zonder ketel).
- §9: het genomen schemabesluit vastgelegd (lokale weekeditor standaard, HA
  Schedule-helper als alternatief, precies één per kamer).
- §13 verwijst naar route B en het herbouwmandaat.
- De statusalinea in §15 is vervangen door een verwijzing naar WORKBOARD §6.

## Gevraagd aan OpenClaw voor WORKBOARD

- F0, woningprofiel: open punt voor de Tado V3/V3+ (koppeltype, ontkoppelen,
  werking als sensor, lokale HomeKit-route, gemeten meetfrequentie).
- §6, uitvoeringsvolgorde: mijlpalen M1/M2 en de WIP-limiet opnemen.
- F6: de haalbaarheidsvoorproef van de ketelstop als eerste concrete bewijsactie.
- Deze delta canoniek integreren of gemotiveerd afwijzen; Marks branch niet
  overschrijven.

Rollback: de commit met deze delta op Marks branch terugdraaien.

## Uitvoering in VS Code — 22 oktober, na deze planwijziging

- Mark bevestigt de Bosch iRT↔EMS-converter en dat Tado EMS spreekt. Deze
  protocolketen is gebruikersinformatie; exacte fysieke uitvoering en veilige
  timeout blijven apart te bewijzen.
- De vroege [F6-documentatie-/bewijsvoorproef](KETELSTOP-VOORPROEF.nl.md) is
  uitgevoerd zonder device-IO. Primaire historische commands/Recorder opnieuw
  gecontroleerd: expliciete nul → CV uit na11,825845s. Geen bewijs voor veilige
  stop bij communicatie-/controlleruitval. Het §12-beslispunt staat daarmee nu
  expliciet open; een handmatige Tado-rollback is geen automatische uitvalstop.
- Begrensde M1-afwerking: native HA-enable/prepare geeft specifieke uitleg bij
  acht totale UTC-overgangen of4096Boverschrijding, met behoud van opgeslagen
  kamer-/journal-/apparaatdata. Geen capaciteitsverruiming of volledige R18claim.
- Lokale bewijsmap: `out/critical-path-20261022`, inclusief TaskFlow,
  herberekening/hashes, C++-peer en native HA-testlogs.151verschillende gerichte
  HA/C++-gevallen PASS; twee verouderde brugtestlabels bijgewerkt na bevestiging
  van dezelfde mismatch op de ongewijzigde basis. De code is niet geïnstalleerd.
- Aanvulling voor de canonical WORKBOARD-review: leg de protocolbevestiging,
  uitkomst van de F6-voorproef en de concrete volgende converter-/stopbewijsactie
  vast; M2 en F6 blijven open. Geen wijziging aan de andere canonical checkout.

## Lokale testkandidaat — vervolg op Marks hele-planopdracht

- Mark bevestigt de badkamer met zelf later te selecteren sensor en TRV als
  eerste proefkamer. Geen vaste woningentiteiten of verplichte tweede kamer.
- Nieuw expliciet `control.plan.week.v1`-SOURCE/plancontract: één of twee kamers,
  maximaal128UTC-punten per kamer binnen bestaande4096Bconfig/8192Bwire/JSONgrenzen.
  Oude contracten blijven gesloten voor dit formaat. Volledige28blokkenweekschema's
  zijn zonder afkappen opgeslagen en teruggelezen. Geen extra owner/Store/timer.
- Ongewijzigde lokale weken kunnen via de bestaande dagelijkse callback en
  verse exacte readback hun horizon vernieuwen. Oude-vensterhercompilatie bewijst
  dat geen gewijzigd gebruikersplan wordt meegestuurd. Helpers/concepten/onzekerheid/
  verlopen horizon blijven expliciete review vereisen.
-249verschillende gerichte HA2026.10.2/C++-gevallen hebben een groene einduitkomst,
  inclusief ASan/UBSan op controller/cJSON; het nieuwe compacte evaluatorpad is
  eveneens geïnstrumenteerd. DST per seconde, grenzen, oude contracten, uitval,
  ownerwissels tijdens laatste await, storagefouten en éénkamerherladen getest.
  Eerste runs met een verkeerde testfixture blijven als zodanig bewaard; telling
  komt uit unieke eindgevallen, niet uit opgetelde overlappende runs.
- Werkelijke gepinde HA2026.10.2-frontend/Chromium desktop1440×1000 en mobiel390×844:
  native kamer-/week-/groepsinrichting, onafhankelijk profiel, runtime-enable,
 121puntenreview, annuleren en apply via een echte geïsoleerde Mosquitto2.0.22
  naar dezelfde C++-controller/store. Eén write;1888Bconfig exact gelijk aan
  het duurzame native HA-journal. Geen echte deviceHTTP/NVS of bronkwalificatie.
-33release-auditregressies en volledige actuele HA-bron-/import-/notice-inventaris
  PASS. Historische firmware-/SDKreceipts worden niet herlabeld. Kandidaatversie
  `v0.1.0-e32v2-alpha.7`; normale app/FS en guarded packaging worden apart vastgelegd.
- Instructies: [testkandidaat](TESTKANDIDAAT-20261022.nl.md), technische definitie:
  [ControlPlan](NATIVE-CONTROL-PLAN.nl.md). Bewijs: `out/release-candidate-20261022`.
  Die lokale map bevat aparte testcredentials en mag nooit integraal gedeeld worden.
- M2/F6 en normale verwarmingsvrijgave blijven OPEN. Gekwalificeerde continue
  meet-/safetyproducers, fysieke kraan/ketelstop, hardware/update/recovery/resources,
  overige F0–F10 en SDKbron/licentieclosure zijn hiermee niet afgevinkt.
