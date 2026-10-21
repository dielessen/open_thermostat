# PLAN-delta van Mark — 22 oktober 2026

**Voor:** OpenClaw (parent), enige canonieke schrijver van PLAN en WORKBOARD.
**Bron:** Marks branch `review/mark-vscode-20261021`, op basis van `defd2ae`.
**Aard:** alleen documentatie. Geen code-, runtime-, configuratie-, installatie-,
publicatie- of verwarmingswijziging. Eisen R01–R31 en de acceptatiecriteria van
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
