# Installatie HA dev37 / E32 alpha28 — 24 oktober 2026

Beide openbare pakketten zijn gepubliceerd en daadwerkelijk geïnstalleerd via
de bestaande HA-specialist. Eindcontrole: **17:30:45 CEST**. Dit is een passieve
onderhoudsrelease, geen vrijgave voor actieve kraan- of ketelregeling.

## Identiteit en controle

| Onderdeel | Gecontroleerde uitkomst |
| --- | --- |
| Bron van beide pakketten | `3efb0a1b5d76a16bb019e082cd6ccbf0bf6a190f` |
| HA | `0.4.0.dev37`, werkelijk geladen op Core 2026.10.3; room/get werkt, shadow_ready; alle 83 live bestanden gelijk aan openbaar pakket |
| HA-ZIP | 510213 bytes; SHA256 `1f51778f92b1a14f8e3befc466ab842683d09591a8a90f37b433afd820ec637b` |
| Frontend | Bestaande dev35/v35 behouden; 63990 bytes, SHA256 `475125ed2d0378ce2bb2bb9f9c43d62340c2792523eb56a286577f10f6d61fdc` |
| E32 | `v0.1.0-e32v2-alpha.28`; werkelijke bron/ELF/web exact, boot_pending=false, updater idle |
| Firmware | 2594864 bytes; SHA256 `f9f55745c185fae757a2055f08896c4956db2bb316682681ff2ea8ca39c7ea0e` |
| ELF | `8d5804611e6cf88940c7b3fd4921f4ed474a519413812324fd93a21906e2f38a` |
| Web | `6ec3c7d46b254dcadf9193c618ce08483c98b8c2d3a771063ab88b8a598ffdac` |
| Nieuwe EMS-weergave | GET/status HTTP 200, twee ontvangen apparaten; index/ems_devices.html/ems-devices.js bytegelijk aan openbaar pakket |

De tag-CI is geslaagd: alle zeven softwarejobs en de eigen publicatiepoorten.
2167 HA-tests op zowel echte Core 2026.10.2 als Core 2026.10.3, zonder fouten/skips.
Alle 83 HA-bestanden, 706 Git-bronbestanden, 1123 pakketcontroles en de werkelijke
CI-ELF/webregistratie zijn onafhankelijk gecontroleerd. De specialist heeft
bovendien de openbare bronverschillen en pakketten zelf opnieuw beoordeeld.

## Back-up, installatie en behoud

Verse rollbackback-up met 93 bestanden, vóór de eerste wijziging gemaakt en via
hash-readback gecontroleerd. Beveiligde opslag onder
`/homeassistant/.openthermostat-backups/20261024-combined-ha37-alpha28-install-owned/backup-20261024T152148167650Z`.
Manifest-SHA256: `587fae1d4630b28c72f69a8e43d9e985ee53935afd11805aa490642be4f659f9`.

Eén normale HA-herstart en één app-only E32-upload. De beheerproxy stopte na 30 s,
maar de oorspronkelijke upload voltooide na 42,78 s met HTTP 200/success. Het
originele ontvangstbewijs én twee echte boot-/runtimecontroles zijn gelezen.
Geen herhaalde upload of extra herstart. Een tussentijds ontvangstbestand had
nog zijn initiële label NOT_UPLOADED; de terminale HTTP- en bootbewijzen bepalen
de werkelijke uitkomst. De native HTTPS-updater is niet opnieuw geprobeerd.

Behoud gecontroleerd: 105 volledige registryrecords, twee apparaten, één entry,
twee subentries, kamers/programma's/bindings, dashboardresources, SOURCE rev4
zonder staged wijziging, journal, privé pins/ontvangstproducent en E32-netwerk-,
hardware-, model- en sysloginstellingen. De back-up is achteraf opnieuw vergeleken.
Tado is niet aangepast. Alle eigen HTTP-/WS-/cookiehandles en tijdelijke
sessiemappen zijn opgeruimd.

E32-uptime 89→343 s en ontvangen EMS-rapporten 23→92 tussen de nacontroles; geen
ontvangstfouten, UART-fouten, TX, polls of proefframes. Vijf ESP-metrics numeriek;
RTC uitgeschakeld/onbekend zoals verwacht. Dit is begrensd runtimebewijs, geen
langdurige lek-/stabiliteitsproef of onafhankelijke fysieke ketelmeting.

## Nog open — niet verbergen achter geslaagde installatie

Na de HA-herstart geeft de optionele oorspronkelijke TV02-ontvangstdiagnose
`source binding unavailable`. De diagnose-eigenaar is leeg; vóór de update was
het eerdere rapport stale/ongekwalificeerd. De pins/producer zijn bytegelijk
bewaard. De bron is niet automatisch vervangen of gekwalificeerd. De verdere
oorzaak is nog niet vastgesteld; beschikbaarheid van deze diagnose is **niet**
afgetekend en staat als concreet vervolg op het werkbord.

De gekozen kamerbron blijft `profile_missing`. M2, causale kraanbevestiging,
werkelijke veiligheidsproducenten en fysieke TX-/stop-/uitvalacceptatie blijven
open. Alle ketel-/kraan-/GPIO-uitgangen, EMS-TX en forwarder blijven geblokkeerd.
De eerdere pendeloorzaak en native HTTPS-afwijking zijn niet als gerepareerd
verklaard. B04–B14 blijven gelden voor hun volledige bèta-uitkomst.

## Bewijs

Veilige lokale samenvattingen onder `out/combined-dev37-alpha28-20261024/`:
`INSTALL-PACKAGE-REVIEW.json`, `AGENT-SOURCE-REVIEW.json`,
`AGENT-PACKAGE-REVIEW.json`, `SAFE-INSTALL-RESULT.json` en `FINAL-REVIEW.json`.
Ruwe beheerontvangsten/back-ups en credentials worden niet gepubliceerd.

**English:** HA dev37 and E32 alpha28 are installed and independently verified against
the immutable public source/packages. Fresh 93-file rollback backup, unchanged
configuration, one HA restart and one app-only upload; original HTTP 200 and actual
stable boot resolve the proxy timeout without replay. EMS inventory works and
all outputs remain blocked. Optional original-TV02 diagnostics are unavailable
after startup and remain an explicit open issue; active heating is not qualified.
