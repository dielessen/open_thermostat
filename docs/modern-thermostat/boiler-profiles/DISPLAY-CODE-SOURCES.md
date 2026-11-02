# Boiler display codes: sources

OpenThermostat shows the boiler's display code (EMS telegram 0x18: two ASCII
characters at offset 18, the cause or service number at offset 20; on EMS+
boilers telegram 0xE4) in words: what it means, how serious it is and what to
do. The tables are part of the boiler profiles in this folder;
`scripts/generate_display_codes.py` validates them and compiles them for Home
Assistant (`ha/config/custom_components/open_thermostat/display_code_table.py`)
and the E32 web pages (`data/html/display-codes.js`).

- One profile per boiler family, block `display_codes`: that family's own
  table, the manual it comes from and the boiler-model selections (E32 Boiler
  page, `public/boilers/catalog-v1.json`) it covers. See "Family tables" below.
- `ems-display-codes.json`: the generic table for EMS boilers that report a
  display code with a three-digit cause number, plus the shared severity and
  advice texts and the document registry below. It applies when no model with
  its own table is selected.

Lookup, in this order: the display code with its cause number; in a family
table, the cause number with any display code (a row without `code`, see
below); the display code alone. Cause numbers run from 100 to 9999.

## Rules

- Only official manufacturer documents (Nefit, Buderus, Bosch, Worcester
  Bosch), downloaded from the manufacturer's own site or document portal where
  possible. Each row names its document and page; `ems-display-codes.json`
  records the SHA-256 of every PDF that was read. EMS-ESP, forums and repair
  sites were not used as a source.
- Meanings and advice are short summaries in our own words (English, Dutch,
  Polish), not quotations. Families share a summary where their manuals say the
  same thing.
- A model table is authoritative for its family. A code it does not list is
  shown as the raw code with "unknown code, see your boiler manual"; it is never
  looked up in another family's table (`fallback` is empty for every family).
- A row without `code` (family tables only) is a number the manual lists
  without a display code: the Bosch operating messages shown as "-" (the
  manuals say the subcode identifies a message uniquely) and the Greenstar 4000,
  whose display shows a number only. It matches that number with any code the
  bus carries; a row with the code and the same number wins (`D4 341` blocks,
  the operating message `341` only limits the output).
- A code-only row in the generic table (used when the boiler sends no cause
  number, or one the table does not list) exists only where every reviewed
  document gives that code the same meaning: `-H`, `=H`, `0H`, `0A`, `0L`, `4U`,
  `4Y`, `6A`, `6C`, `6L`, `EC`, `EF`, `EH`, `EL`. `0C`, `2F`, `3C` and `7H`
  mean different things on the EcomLine Classic and on newer boilers; `EA` (a
  flame fault) and `0Y` (an overheat) mean different things on the Bosch
  letter-code families. None of these has a code-only row.
- Severity: `normal`, `waiting`, `service`, `blocking` (restarts by itself),
  `locking` (needs a reset) and `fault` (the document does not say which, or
  lists the code as both). Classic boilers show a lockout only by a blinking
  display, which is not on the bus, so their faults are `fault`.

## Documents

| Id | Document | Models | Pages | Where |
|----|----------|--------|-------|-------|
| `nefit-ecomline-classic-705428a` | Nefit B.V., *Installatie-instructie Nefit EcomLine HR* (EcomLine Classic HR-toestellen), 705.428A-4200, 03/2005, Dutch | EcomLine HR 22/30/43/65, HRC 22 H/V, HRC 30 H/V | 4-1 to 4-8 (sections 4.1 and 4.2; PDF pages 31-38) | <https://www.smarthomesupply.nl/handleiding/nefit/instalecomlineclassic.pdf> (archive copy; Nefit imprint and number on the last page) |
| `nefit-ecomline-excellent-705427a` | Nefit B.V., *Installatie-instructie Nefit EcomLine HR* (EcomLine Excellent HR-toestellen), 705.427A-4200, 03/2005, Dutch | EcomLine Excellent HR and HRC | 4-1 to 4-8 (sections 4.1 and 4.2; PDF pages 31-38) | <https://nefit-nl-nl-b.boschhc-documents.com/download/pdf/file/70542700> (manufacturer document portal) |
| `nefit-proline-6720646227` | Bosch Thermotechniek B.V., *Installatie-instructie Nefit ProLine HRC 24/CW3, HRC 24/CW4, HRC 30/CW5*, 6 720 646 227, 2013/04, Dutch | ProLine HRC 24/CW3, 24/CW4, 30/CW5 | 31-34 (chapter 10, table 25) | <https://www.nefit-bosch.nl/media/country_pool/professioneel/installateurs/installatie-instructie_proline.pdf> |
| `nefit-trendline-ii-6720882261` | Bosch Thermotechniek B.V., *Installatie-instructie Nefit TrendLine II*, 6720882261, 2021/03, Dutch | TrendLine II HRC25 CW4, HRC30 CW5 | 32-37 (chapter 11, table 20) | <https://portal.insmart.nl/downloads/nefit_trendline_ii_Installatie%2BTrendLine.pdf> (installer portal copy) |
| `nefit-topline-6720615811` | Nefit B.V., *Service-instructie Nefit TopLine HR, TopLine AquaPower HRC, TopLine AquaPower Plus HRC*, 6 720 615 811, 07/2008, Dutch | TopLine HR, AquaPower HRC, AquaPower Plus HRC | 19-23 and 31-49 (frame 29 and the diagnosis frames) | <https://portal.insmart.nl/downloads/nefit_topline_aquapower_Service-instructie%2BTopline%2BAquapower.pdf> (installer portal copy) |
| `nefit-smartline-basic-71652200` | Nefit B.V., *Installatie-instructie Nefit SmartLine Basic HR 24, HRC 24/CW3 en HRC 24/CW4*, 7165 2200, 06/2009, Dutch | SmartLine Basic HR 24, HRC 24/CW3, HRC 24/CW4 | 52-57 (section 13.3) | <https://nefit-nl-nl-b.boschhc-documents.com/download/pdf/file/71652200> (manufacturer document portal) |
| `buderus-gb172-6720619596` | Buderus, *Montage- und Wartungsanleitung Logamax plus GB172-14/20/24/24K*, 6 720 619 596, 02/2011, German | Logamax plus GB172-14, -20, -24, -24K | 68-72 (section 15.3, tables 24-26) | <https://www.kesselheld.de/content/uploads/2019/07/wartungsanleitung-buderus-logamax-plus.pdf> (retailer copy) |
| `buderus-gb162-6720614965` | Bosch Thermotechnology Corp. (Buderus), *Service Instructions Logamax plus GB162-80 kW/100 kW*, 6 720 614 965, 11/2012, English (US/CA) | Logamax plus GB162-80 kW, -100 kW (UBA 3, BC10) | 21-28 (section 5, display codes and other symptoms) | <https://www.bosch-homecomfort.com/us/media/country_pool/documents/download-buderus-products/buderus-manuals/6720614965_05_gb162_service_instructions_en_11.2012_us-2.pdf> |
| `bosch-gc7000iw-6720882461` | Bosch, *Installatie- en onderhoudsinstructie Condens 7000iW GC7000iW 14-28*, 6720882461, 2021/10, Dutch (Belgium) | Condens 7000i W, GC7000iW 14, 24, 28 C | 47-51 (chapter 16, table 74) | <https://www.bosch-homecomfort.com/web-etk/documents/doc?id=365401> (manufacturer document library) |
| `bosch-cerapur-6720889855` | Bosch Thermotechnik GmbH, *Installations- und Wartungsanleitung Cerapur ZSB 14-5.2C 21/23*, 6720889855, 2023/07, German | Cerapur ZSB 14-5.2C | 59-63 (chapter 16, table 81) | <https://bosch-de-de.boschhc-documents.com/download/pdf/file/6720889855> (manufacturer document portal) |
| `worcester-greenstar-4000-6720891161` | Worcester, Bosch Group, *Installation and Maintenance Instructions Greenstar 4000 GR4700iW C*, 6 720 891 161, 2021/10, English (UK/IE) | Greenstar 4000 combi | 71-79 (section 10.1.2) | <https://www.worcester-bosch.co.uk/support/literature/download/6720891161> |

The SHA-256 of each PDF as read on 1 November 2026 is in
`ems-display-codes.json` (`sources`). The ProLine, TrendLine II and TopLine
manuals are also on the Nefit document portal under the same document numbers;
those PDF builds have other hashes, so the registry keeps the copies that were
read.

## Family tables

| Profile | Selections | Document | Rows | Notes |
|---------|------------|----------|------|-------|
| `nefit-ecomline-classic-hrc-22h.json` | `nefit-ecomline-classic`, `nefit-ecomline-classic-hrc-22h` | `nefit-ecomline-classic-705428a` | 54 | Letter service codes, no cause numbers (see below). |
| `nefit-ecomline-excellent.json` | `nefit-ecomline-excellent` | `nefit-ecomline-excellent-705427a` | 54 | Section 4 is the same as the Classic manual line by line, except that the wiring-link fault is `8Y` instead of `8L`; the Classic texts are reused. |
| `nefit-proline-hrc.json` | `nefit-proline` | `nefit-proline-6720646227` | 94 | Type column: 2 blocking, 3 locking, 2+3 fault, blank operating. `5F`, `5Y` and `9Y` have no cause number in the table and are code-only rows; `8C 373`/`374` are permanent lockouts. ProLine NxT and Eco were not reviewed. |
| `nefit-trendline-ii.json` | `nefit-trendline-ii` | `nefit-trendline-ii-6720882261` | 124 | Rows marked "-" that describe a defect (for example `1U 317`, `4U 350`) are `fault`: the table does not say blocking or locking. The earlier TrendLine (`nefit-trendline`) was not reviewed. |
| `nefit-topline-aquapower.json` | `nefit-topline` | `nefit-topline-6720615811` | 61 | Each row names its class. The ranges "9H 233 to 9U 272" and "E. 242 to 287" are not split into rows; `4A 332` is above 110 °C on this family. |
| `nefit-smartline-basic.json` | `nefit-smartline` | `nefit-smartline-basic-71652200` | 61 | The reset column separates blocking from locking. The 2002 SmartLine HR(C) manual on the portal has no code table. |
| `buderus-logamax-plus-gb172.json` | `buderus-logamax-plus-gb172` (new selection) | `buderus-gb172-6720619596` | 43 | Operating (table 24), blocking (25) and locking (26); a code in both 25 and 26 is `fault`. A new exact selection, because `buderus-gb-72` and `buderus-gbx72` also cover other GB*72 boilers. |
| `buderus-logamax-plus-gb162.json` | `buderus-gb162` | `buderus-gb162-6720614965` | 68 | From the US/CA GB162-80/100 kW manual; the smaller GB162 sizes use the same UBA 3 but were not reviewed. That manual swaps the words blocking and locking in its introduction; the reset column in the table is consistent and was used. |
| `bosch-condens-7000i-w.json` | `bosch-condens-7000i-w` (new selection) | `bosch-gc7000iw-6720882461` | 57 | Letter fault code plus subcode (`EA 227`, `C6 215`); class O, B, V; operating messages as number-only rows. |
| `bosch-cerapur-zsb-5c.json` | `bosch-cerapur-zsb-zwb-5c` (new selection), `junkers-cerapur` | `bosch-cerapur-6720889855` | 56 | Same scheme as the Condens 7000i W (no `EH 258`). Older Junkers Cerapur generations were not reviewed; a code without a listed subcode shows as unknown. |
| `worcester-bosch-greenstar-4000.json` | `worcester-bosch-greenstar-4000` (new selection) | `worcester-greenstar-4000-6720891161` | 72 | Three- and four-digit numbers only (number-only rows). Left out: maintenance messages (class W), rows without a class (`362`, `1010`, `2914`, `2969`), `357` (its text in the table repeats another row) and the controller codes from `3071`. |

The new selections are appended to the catalogue (`src/BoilerDisplayModels.h`
keeps the earlier indices), so firmware from before this change does not offer
or accept them.

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

- No official manual with a code table was found in this pass for: Nefit EcomLine Elite
  (the portal only has its parts book), Buderus Logamax plus GB192i (the public
  installation manuals have no code table; the service manual is not public),
  Bosch Condens 2300i W (GC2300iW), and the older Worcester Greenstar i, Si
  and ErP. These use the generic table.
- The generic table keeps only rows found in more than one family manual, or
  explicit in one (for example `2F 338`); single-family rows such as the
  TrendLine II service-tool rows (`5A 606`, `5F 601`) are in that family's
  table only.
- Maintenance messages (`H01`, `H03`, `H07` and others) and controller codes
  (`A01`, `A11` and others) are three characters and are not the two-character
  display code.
- A boiler that sends no display code at all (blank) with a number gets no
  description; that case was not seen on a bus yet.
