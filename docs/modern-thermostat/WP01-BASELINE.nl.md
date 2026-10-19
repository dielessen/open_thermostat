# WP01 — gecontroleerde upstream- en E32-basis

Softwareacceptatie WP01 geslaagd op 19 oktober 2026. Dit document is softwarebewijs, geen
vrijgave van een thermostaat of hardwareproef. Hoofdplan: [PLAN.nl.md](PLAN.nl.md).
Werkbranch: `work/wp01-upstream-e32-20261019`; `main` en alpha1 blijven intact.

## Bronbasis en besluiten

Uitgangspunt: `f1bdcc85b2299f9fab148922d6dfed943e07c735` (documentatie bovenop
firmware `a5fc6b84`). Verse upstream: `4bcf1bfd9df4b2810518529cb7212972388e2ce4`.
Sinds het eerdere bouwplan is een vierde wijziging verschenen.

| Upstreamcommit | Besluit | Reden en afbakening |
| --- | --- | --- |
| `b2a6df8995a6c59f1006bfb41056d0b2dc020f93` statistiek | Uitgesteld tot WP07 | Nieuwe HA-code herstelt een teller en telt EMS-delta's op; dat is niet hetzelfde als een firmwaretotaal met identiteit, replay-/dedupbeleid en expliciete historische migratie. Kamerenergie blijft een modelschatting. Niet als betrouwbare gemeten verbruiksketen uitrollen. Dashboard/select/vertalingen later met het gekozen meetcontract beoordelen. |
| `fe256952724a5c0ef9b092869f0725597e3c1d65` Arduino3/platform8 | Niet overgenomen als platformmigratie | Externe librarypatch in de commit; actuele esp32_utilities heeft nog `class WiFiClient;`. E32 heeft bovendien specifieke Arduino2 Ethernet-/lwIP-aanroepen. Geen eigen extra librarypatch of onbewezen Arduino3 Ethernetport. Nieuwere upstream kiest zelf weer platform7.1.3. Het generieke factory-only partitieschema wordt evenmin overgenomen. |
| `67b76391f2f81d5d5acd5a8d4675067fddc74448` EMS-queues | Overgenomen met behoudsresolutie | Kopiëren van RX-frames naar een begrensde SPSC-queue; decodering/logging buiten de UART-taak; vooraf gecodeerde TX-frames. Nieuwe resetfunctie houdt expliciet de bestaande compile-time break/TX-blokkade. Ook de verplaatste enqueue-functie blijft op E32 geblokkeerd. |
| `4bcf1bfd9df4b2810518529cb7212972388e2ce4` platform7/NTP | Selectief overgenomen, buildacceptatie hieronder | Platform7.1.3 met behoud van de reeds expliciete Arduino2.0.17-packagepin; geen Arduino3-hook. NTP-hostconfig krijgt blijvende opslag; callback geeft alleen een atomisch signaal door en RTC-afhandeling gebeurt in loop(). E32-netwerk- en RTC-beveiligingen blijven staan. |

De eerdere Arduino3-commitnaam beschrijft niet de definitieve buildbasis:
de platform7.1.3-manifest bevat `framework-arduinoespressif32 ~4.20017.0`.
Onze bestaande expliciete packagepin blijft `3.20017.241212+sha.dcc1105b`
(Arduino2.0.17 / IDF4.4.7). Een succesvolle softwarebuild bewijst niet dat
GPIO0-klok, WiFi/EMAC-combinatie of de specifieke E32-hardware stabiel werkt.

## Vastgezette afhankelijkheden

`platformio.ini` bevat exacte native/platform-, library- en Git-bronversies:
native1.2.1, Espressif32 7.1.3, bestaande Arduino2-packagepin, PubSubClient2.8.0,
ESPPubSubClientWrapper1.0.2, RTClib2.1.4, Adafruit BusIO1.17.4,
NimBLE-Arduino2.5.1, googletest1.17.0, esp32_utilities
`9186b65fa1e598dfe93582126f97569700dc3a50` en cJSON
`6d9f2443ab071f86e5d9b43025a40929ec41c46c`.
Dat zijn de daadwerkelijk opgehaalde versies van de eerste WP01-bouwproef,
nu zonder zwevende Git-HEADs of libraryranges. PlatformIO Core6.2.0, conform CI.

Geen nieuwe sidecar, scheduler, firmwareframework of librarypatch toegevoegd.
De bestaande E32-buildmiddleware blijft onveranderd en heeft zijn bestaande
bronhashcontrole; uitfasering daarvan is geen onderdeel van deze wijziging.

## Behoud en verificatie

- `Board.h`, E32-boarddefinitie, E32-partities, buildmiddleware en veilige
  bestandssysteemdefaults blijven ongewijzigd ten opzichte van de startbasis.
- Twee appslots en twee SPIFFS-slots blijven beschikbaar; geen factory-only
  layout overnemen. Dit bewijst op zichzelf geen automatische rollback.
- Geen E32 UART-TX, forwarderstart, reset-break, lokale GPIO/I2C/RTC-uitvoer
  vrijgeven. De bestaande verifier controleert ook gecompileerde objecten.
- Bestaande baseline: 62/62 native tests PASS. Na queue-integratie:
  66/66 PASS, inclusief 100.000 SPSC-frames met twee threads.
- Finale matrix: **alle zeven controleonderdelen geslaagd**.

| Controle | Uitkomst |
| --- | --- |
| `pio test -e native --verbose` | 66/66 PASS, inclusief 100.000 frames tussen twee threads |
| `pio run -e e32v2` | PASS; ELF flash1.743.509/3.670.016 bytes, RAM64.416; firmwarebestand1.750.080 bytes |
| `pio run -e esp32dev` | PASS; ELF flash1.695.421/1.703.936 bytes, RAM64.296 |
| `pio run -e esp32s3` | PASS; ELF flash1.587.129/3.670.016 bytes, RAM59.308 |
| `pio run -e e32v2 -t buildfs` | PASS; SPIFFS4.653.056 bytes |
| `python scripts/verify_e32v2.py` | PASS; gecompileerde slots/defaults/PSRAM/netwerkgate en geen project-UART-TX-referenties |
| `python scripts/test_e32v2_verifier.py` | 5/5 PASS; opzettelijke fouten in flashheader, partities, GPIOdefaults en gecompileerde TX-code worden afgewezen |

Daarnaast: 16/16 statische behoudschecks PASS en de bestaande CI-`esptool
merge_bin`-route met esptool4.11 werkt. Eerste platform7-build ontbrak
`intelhex`; exact2.3.0 in de bestaande afzonderlijke buildvenv en CI toegevoegd,
conform upstream. Installeer voor herhaling PlatformIO6.2.0 en intelhex2.3.0
in een geschikte Pythonvenv; alle overige buildcommando's staan hierboven.
Gitcompilebasis: `ce654f0`; latere wijzigingen zijn uitsluitend documentatie.

De generieke4MB-build heeft nog maar8.515 bytes ELF-flashruimte. Geen
partitieaanpassing gedaan om dit te verbergen; uitbreidingen vereisen daar
een nieuw resource-/layoutbesluit. Dit is niet de16MB-E32 met grotere appslots.

Volledige TaskFlow en logs:
`/home/dielessen/artifacts/open-thermostat-wp01-20261019/`.

## Grenzen en vervolg

Geen flash, HA-installatie, fysieke apparaatbediening, EMS-write, release,
push of wijziging van de werkende Tado-installatie. Eerste installatie via
eigen wifi, live kamerconfiguratie, GUI-entiteitskeuze en OTA/herstel zijn
producteisen voor vervolgwerk; niet door deze softwaretests bewezen.

Na een geaccepteerde WP01-basis volgt WP02: Classic-capabilities en passieve
frame-/veldpariteit, nog zonder TX. F0 als geheel blijft open wegens het
fysieke installatie-/boardprofiel. Voor echte proefneming blijven firmwarebackup,
herstel, exclusieve overdracht, stop-/powerloss- en hydraulische gates nodig.
