> Dit is het historische publicatieverslag vóór installatie. Alpha36 is daarna
> via GitHub geïnstalleerd en afzonderlijk geaccepteerd; zie
> [het actuele installatieverslag](INSTALLATIE-E32-ALPHA36-20261025.nl.md).

# Alpha36 — gepubliceerd; HA48 actueel, E32-installatie geblokkeerd

25 oktober 2026. [Alpha36](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.36)
is gepubliceerd vanaf onveranderlijke bron `7ddf3410666d814850275433d9dddd266e5d83ba`.
De opdracht om op HA en E32 te installeren is **deels uitgevoerd**: HA48 is reeds
geïnstalleerd en opnieuw exact actueel bevonden; E32 alpha36 is niet geïnstalleerd.
De verse controle ziet de E32 op alpha31. Geen upload, updateprobe of herstart.
De actieve bèta en E32-uploadgate blijven **NOT_READY**.

## Meegeleverde wijzigingen

- About rechts na Settings; alle eerdere navigatie-/sessie-/restartguards behouden.
- 60 presentatiekeuzes met alle 31 vastgelegde EMS-ESP-productgroepen en aanvullende
  documentatievermeldingen. Geen automatische driver-/profiel-/zendvrijgave.
- Vier oorspronkelijke externe modelafbeeldingen voor vijf keuzes met bronlink.
  Geen foto's op de ESP; offline/mislukte afbeeldingen blokkeren de bediening niet.
  Ecomline Classic HRC22H nog zonder gecontroleerde originele foto; geen generieke
  tekening als vervanging. Functionele regelprofielimport blijft ontwerp/open werk.
- ESP / EMS / beide als webfilter en afzonderlijk opgeslagen syslogbronvinkjes.
  Begrensde EMS-RX-framelogging in de decode-lus; oorspronkelijke UART-callback,
  receive-admissie en fysieke uitvoer ongewijzigd. Geen volledige busopname.
- Een oude open logpagina met zes velden bewaart de actuele bronkeuzes; alleen
  expliciete achtveldsinstellingen wijzigen die. NVS-commit/readback blijft vereist.

## Exacte software- en pakketcontrole

[MainCI40179913673](https://github.com/dielessen/open_thermostat/actions/runs/40179913673)
en [tagCI40180869632](https://github.com/dielessen/open_thermostat/actions/runs/40180869632)
slagen met alle zeven toepasselijke softwarejobs; de E32-publicatiejob slaagt.
Alle drie firmwareboards bouwen. De volledige native suite telt 803 geslaagde
gevallen. HA rapporteert per Core 2026.10.2/2026.10.3 telkens 2.356 tests inclusief
subtests, met 2.288 testcase-elementen en nul fouten/errors/skips, zowel main als tag.

De onafhankelijke native bronreview verifieert 773 bronbestanden en 91 ruwe
Git-treeobjecten. De onafhankelijke mainpakketreview slaagt met 1.150 standaard-
verifierchecks plus eigen bron-/ELF-/web-/HA-/SPIFFS-controle. Root voert de
ongewijzigde verifier afzonderlijk met volledige Git/CI-debugcontext uit:
1927 controles op zowel main als tag. Dit zijn verschillende controlescopes.
Alle vijf publieke bestanden zijn volledig vergeleken met hun eigen tagbuild.

App:2619952bytes; SHA256
`e8a242d00288e70172fae90ee006d90d59287d024480505d38a887e99f6eb5d4`.
Werkelijke tag-ELF-SHA256:
`ef313784cdc5e6a83c290225abbdac5a27138c7228890bd804ec9f39d82dc738`.
Web-SHA256:
`2b858b3ed32c9748c4b00c0c4f25e0160d17fbcadbb4b040252c3f9ec47dc505`.
Distributie-ZIP-SHA256:
`7e0944abef45023f196ee237e790b020702e3197fff20cf68f615517c2334bab`.

Alle 727 payloadbestanden zijn gecontroleerd. Main/tag hebben dezelfde app,
manifest, softwareverificatie en source.tar.gz. De overige verschillen zijn afgebakend tot de compileertijdliteral in één SDK-hulpobject, de exact afgeleide
archive-/relink-/notice-/checksumreferenties en SPIFFS/factorybytes. Alle 40 logische
SPIFFS-bestanden komen exact overeen met de bevroren, inerte staging. De oorzaak
van het ruwe SPIFFS-byteverschil blijft onbekend; geen volledige ZIP- of ruwe
SPIFFS-reproduceerbaarheidsclaim. Alleen de daadwerkelijke SPIFFS-slice van de
factoryimage verschilt. Factoryimage is geen OTA-app en niet gebruikt voor uitrol.

## HA en E32 — verse installatievoorcontrole

De bestaande HA-specialist leest op 2026-10-25T09:41:46.873787+00:00 opnieuw de
actuele runtime via de eerder gecontroleerde native Ingressroute. 33 controles
slagen; alle 86 live componentbestanden exact publiekHA48 en kandidaatbron.
Core 2026.10.3, HA0.4.0.dev48 geladen, room_get en shadow_ready bevestigd.

Er zijn geen HA-componentwijzigingen in alpha36. De opnieuw gebouwde HA48-ZIP
verschilt alleen in SOURCE.json.source_commit en de bijbehorende checksum;
alle 86 componentbestanden zijn bytegelijk. De bestaande publieke HA48-release
is niet vervangen. Geen HA-herinstallatie, back-up of Core-herstart uitgevoerd.
De eerdere geverifieerde [HA48-installatie/back-up](INSTALLATIE-HA48-ALPHA35-20261025.nl.md)
blijft het installatiebewijs; deze nieuwe opname is een readonly voorcontrole.

E32: alpha31, bron 659879e, dezelfde gerapporteerde boot en uptime 31.430s.
SOURCE rev5/shadow; uitgangen uit; EMS-TX/poll/testtellers nul, updater idle en
geen bootpending. Instellingen, programma's, registry en frontend onveranderd
teruggelezen. Dit bewijst geen fysieke Tado-regelstatus of nieuwe controlekwalificatie.

De oude alpha28→29-upload liep vast met curl56/HTTP000 en reset6/TASK_WDT.
Taak, stack, oorzaak en herstelroute blijven onbekend; actor/methode van de
latere alpha31-installatie zijn ook onbekend. Bereikbaarheid en idle-status zijn
geen bewijs dat dezelfde uploadroute nu hersteld is. Geen nieuw verifieerbaar
herstelbewijs beschikbaar; dus geen herhaling van upload of HTTPS-updateproef.

Alle productiewrites, firmwareacties, apparaat-/MQTT-opdrachten, herstarts,
back-ups, services en nieuwe gedeployde helpers in deze voorcontrole zijn nul.
Deze opdracht heeft geen firmware geïnstalleerd. De E32-installatie blijft open
voor een aantoonbaar herstelbare en beoordeelde route; geen USB/COM-aanname.


Alle 23 voorbereide onderdelen,294 bronverwijzingen,31 eisen en14 releasepoorten
blijven behouden; fysieke poorten niet afgevinkt. Bewijs lokaal onder
`out/release-alpha36-20261025/`: bron-/pakket-/Git-/CI-/publieke downloadreviews,
main/tag-deltaclassificatie en de verse native voorcontrole met Root-hashvergelijking.
