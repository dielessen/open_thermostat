# Boiler display codes: sources

OpenThermostat shows the boiler's display code (EMS telegram 0x18: two ASCII
characters at offset 18, the cause or service number at offset 20) in words:
what it means, how serious it is and what to do. The tables are part of the
boiler profiles in this folder; `scripts/generate_display_codes.py` validates
them and compiles them for Home Assistant
(`ha/config/custom_components/open_thermostat/display_code_table.py`) and the
E32 web pages (`data/html/display-codes.js`).

- `nefit-ecomline-classic-hrc-22h.json`, block `display_codes`: the Nefit
  EcomLine Classic HR/HRC table (letter service codes, no cause numbers), used
  for the boiler-model selections `nefit-ecomline-classic` and
  `nefit-ecomline-classic-hrc-22h`.
- `ems-display-codes.json`: the generic table for EMS boilers that report a
  display code with a three-digit cause number, plus the shared severity and
  advice texts and the document registry below. It applies when no model with
  its own table is selected.

## Rules

- Only official manufacturer documents (Nefit, Buderus, Bosch). Each row names
  its document and page; `ems-display-codes.json` records the SHA-256 of every
  PDF that was read. EMS-ESP, forums and repair sites were not used as a source.
- Meanings and advice are short summaries in our own words (English, Dutch,
  Polish), not quotations.
- A model table is authoritative for its family. A code it does not list is
  shown as the raw code with "unknown code, see your boiler manual"; it is never
  looked up in another family's table.
- A code-only row in the generic table (used when the boiler sends no cause
  number, or one the table does not list) exists only where every reviewed
  document, Classic and newer, gives that code the same meaning: `-H`, `=H`,
  `0H`, `0A`, `0Y`, `0L`, `4U`, `4Y`, `6A`, `6C`, `6L`, `EA`, `EC`, `EF`, `EH`,
  `EL`. `0C`, `2F`, `3C` and `7H`, for example, mean different things on the
  EcomLine Classic and on newer boilers and have no code-only row.
- Severity: `normal`, `waiting`, `service`, `blocking` (restarts by itself),
  `locking` (needs a reset) and `fault` (the document does not say which, or
  lists the code as both). Classic boilers show a lockout only by a blinking
  display, which is not on the bus, so their faults are `fault`.

## Documents

| Id | Document | Models | Pages | Where |
|----|----------|--------|-------|-------|
| `nefit-ecomline-classic-705428a` | Nefit B.V., *Installatie-instructie Nefit EcomLine HR* (EcomLine Classic HR-toestellen), 705.428A-4200, 03/2005, Dutch | EcomLine HR 22/30/43/65, HRC 22 H/V, HRC 30 H/V | 4-1 to 4-8 (sections 4.1 and 4.2; PDF pages 31-38) | <https://www.smarthomesupply.nl/handleiding/nefit/instalecomlineclassic.pdf> (archive copy; Nefit imprint and number on the last page) |
| `nefit-proline-6720646227` | Bosch Thermotechniek B.V., *Installatie-instructie Nefit ProLine HRC 24/CW3, HRC 24/CW4, HRC 30/CW5*, 6 720 646 227, 2013/04, Dutch | ProLine HRC 24/CW3, 24/CW4, 30/CW5 | 31-34 (chapter 10, table 25) | <https://www.nefit-bosch.nl/media/country_pool/professioneel/installateurs/installatie-instructie_proline.pdf> |
| `nefit-trendline-ii-6720882261` | Bosch Thermotechniek B.V., *Installatie-instructie Nefit TrendLine II*, 6720882261, 2021/03, Dutch | TrendLine II HRC25 CW4, HRC30 CW5 | 32-37 (chapter 11, table 20) | <https://portal.insmart.nl/downloads/nefit_trendline_ii_Installatie%2BTrendLine.pdf> (installer portal copy) |
| `nefit-topline-6720615811` | Nefit B.V., *Service-instructie Nefit TopLine HR, TopLine AquaPower HRC, TopLine AquaPower Plus HRC*, 6 720 615 811, 07/2008, Dutch | TopLine HR, AquaPower HRC, AquaPower Plus HRC | 19-22 and 31-49 (symptoms and diagnosis frames) | <https://portal.insmart.nl/downloads/nefit_topline_aquapower_Service-instructie%2BTopline%2BAquapower.pdf> (installer portal copy) |
| `buderus-gb172-6720619596` | Buderus, *Montage- und Wartungsanleitung Logamax plus GB172-14/20/24/24K*, 6 720 619 596, 02/2011, German | Logamax plus GB172-14, -20, -24, -24K | 68-72 (section 15.3, tables 24-26) | <https://www.kesselheld.de/content/uploads/2019/07/wartungsanleitung-buderus-logamax-plus.pdf> (retailer copy) |

The SHA-256 of each PDF as read on 1 November 2026 is in
`ems-display-codes.json` (`sources`).

## The owner's boiler: Nefit EcomLine Classic HRC 22H

On the bus the Classic display code and its letter service code arrive as one
code ("0" and "H" = `0H`). From 705.428A-4200:

- Normal operation (page 4-2): `-H` heating, `=H` hot water, `0H` standby (no
  heat demand), `0A` waiting (anti-cycle programme), `0C` waiting for the 3-way
  valve, `0L` ignition, `0U` fan purge before or after burning, `0Y` waiting
  (water warmer than set), `2F` adapting to a small water volume, `P`, `C`, `d`
  control unit starting up, restarting or reading boiler data.
- Not working correctly (page 4-3): `-A` and `-Y` (fixed power, the test switch
  may be on), `0P` (does not start).
- Faults (pages 4-4, 4-5): `1C`, `2C`, `2P`, `2U`, `3C`, `4A`, `4C`, `4F`,
  `4L`, `4P`, `4U`, `4Y`, `5A`, `5C`, `5F`, `5Y`, `6A`, `6C`, `6H`, `6L`, `7A`,
  `7C`, `7F`, `7H`, `7L`, `8L`, `9A`, `9C`, `9F`, `9H`, `9L`, `9P`, `9U`, `EA`,
  `EC`, `EF`, `EH`, `EP`, `EL`; the advice follows the causes in section 4.2.2
  (pages 4-5 to 4-8).

The owner's boiler is on the bus through a Bosch EasyControl Adapter (EMS
address 0x08). Whether the adapter passes every boiler code through unchanged
has not been checked on site (compare the boiler display with the reported
code in rest, heating and hot water; see `EMS-INSTELBARE-WAARDEN.nl.md`).

## Not covered (left out)

- Bosch/Junkers Heatronic boilers (Cerapur and others): no official code table
  was reviewed; their codes (for example `EA`, `C6`, `A7`) use another scheme.
  They use the generic table, so most of their codes show as unknown.
- Rows found in a single document are included only where that document is
  explicit (for example `2F 338`). Left out: the service-tool and diagnosis
  rows of TrendLine II only (`5A 606`, `5F 601`, `5Y 602`, `5P 552`, `5H 323`),
  the rarer internal rows (`6C 509`, `6H 607`, `6P 269`, `7A 550`, `7A 608`,
  `7C 609`, `7H 356`, `8C 373`, `8C 374`, `9A`, `9C`, `9F`, `9H`, `9U` with cause
  numbers, `EE`), and the TopLine-only `3F 272`. The control unit codes `EA`,
  `EC`, `EF`, `EH` and `EL` are covered by code-only rows; `E1`, `EP` and `EY`
  with cause numbers show as unknown.
- Maintenance messages (`H01`, `H03`, `H07` and others) are three characters
  and are not the two-character display code.
- Nefit EcomLine HR Economy/Excellent and Buderus GB162: no table was reviewed
  for this release; they use the generic table.
