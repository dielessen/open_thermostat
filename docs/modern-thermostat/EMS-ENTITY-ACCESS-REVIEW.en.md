# EMS entity access and the consolidated boiler page

Reviewed 26 October 2026 against EMS-ESP source commit
`ac570d3ca747a57d0ead6cdad91ef98371693b65`.

EMS-ESP registers an entity together with its type, unit, options, bounds and an
optional command handler. A handler establishes command capability. Its
per-entity read-only customization can suppress that capability at runtime.
The web response exposes an editable command only when a handler exists and
the read-only flag is absent. Boolean/enum options and numeric bounds determine
the input. Command-only entities are distinct from readable values. The write
endpoint requires administrator authorization and dispatches the registered
command; displaying a value alone does not provide a setter.

Primary sources:

- [Entity types, command capability and read-only flag](https://github.com/emsesp/EMS-ESP32/blob/ac570d3ca747a57d0ead6cdad91ef98371693b65/src/core/emsdevicevalue.h).
- [Runtime web/API access and customization generation](https://github.com/emsesp/EMS-ESP32/blob/ac570d3ca747a57d0ead6cdad91ef98371693b65/src/core/emsdevice.cpp).
- [Administrative write dispatch](https://github.com/emsesp/EMS-ESP32/blob/ac570d3ca747a57d0ead6cdad91ef98371693b65/src/web/WebDataService.cpp).

No upstream executable driver or web implementation is imported. The existing
pinned factual catalogue remains the data source, documented by
`public/ems/SOURCES.json`. It records base command capabilities; it does not
export the owner's old EMS-ESP instance's customization mask.

## Applied on the E32

| Layer | Meaning |
| --- | --- |
| Received E32 values | Actual snapshots, preserving quality, source telegram and age. Local read-only values, four prepared Classic settings and the manual flow command have separate access labels. |
| EMS-ESP catalogue | All 258 distinct boiler definitions across 31 model groups; 252 entity names. 137 read-only definitions, 117 configurable variants and 4 command variants. The 117 writable names in BOILER-WRITE-INVENTORY include command names and model variants. |
| E32 implementation | Four guarded Classic settings (`heatingactivated`, `heatingtemp`, `burnminperiod`, `pumpdelay`); `selflowtemp` only through the bounded manual Classic trial. Other setters are explicitly not implemented. |
| Current permission | Backend settings availability and fresh metadata control the existing guarded editor. Catalogue metadata never creates controls or changes backend authority. Standard persistent setting writes remain disabled. |

The catalogue has independent search, access and model filters, with explicit
counts and a Show more action. Every definition is reachable even when the
connected product ID is unknown. Reference definitions are never presented as
measured values or confirmed device support. A read-only catalogue entry is not
confused with an E32 setting whose implementation exists but is currently blocked.

## Page preservation and lifecycle

The sole navigation entry is Boiler test. It contains the existing manual
controls, reception report/download, measurement quality, protocol profile,
69 native fields, device inventory/identity, four-setting overview/editor,
per-product EMS-ESP references and the complete telegram byte-offset library.
Device/module source assets are retained as a shared panel, not a second menu
page. Existing loadNativePage('ems_devices') links resolve to Boiler test.

Panel loading is bounded and independent of the reception/test-control fetch.
A missing reference or panel does not authorize writes or hide the separate
reception controls. Navigation detaches the panel and cancels its requests;
late HTML cannot mount a stale editor. Refresh/filter/catalogue actions only
read local snapshots. Existing guarded writes keep their auth, confirmation,
range checks, stale-data fencing, single submission and observed-readback logic.
No new wire encoder, board-write permission, physical trial, HA update or device
installation is introduced by this page consolidation.
