# Systeemlog en externe syslog

Status: voorbereid voor de gezamenlijke volgende bèta; nog niet op de E32
geïnstalleerd. De huidige installatie blijft alpha21 / HA dev27. Deze functie
verandert geen kamerbinding, SOURCE, weekprogramma of ketelvrijgave.

## Gebruik

Open **Settings → System log / Instellingen → Systeemlog** op de E32.
De pagina is Nederlands of Engels volgens de bestaande taalkeuze.

- Bekijk recente gebeurtenissen, kies een maximaal logniveau en filter op module
  of bericht. Pauzeren bevriest de weergave; hervatten haalt nieuwe regels op.
- Download de zichtbare, gefilterde browserhistorie als tekst. Dit is een
  momentopname met mogelijke gaten, geen volledige opname van de bedrijfstijd.
- Wis alleen de lokale RAM-historie. De externe sysloghistorie wordt niet gewist.
- Kies afzonderlijke niveaus voor web en syslog: uit, fout, waarschuwing, info,
  debug en trace. Bestaande module-/debugflags blijven gelden.
- Voor langere bewaring: schakel syslog in, vul het IPv4-adres van je eigen
  collector en de UDP-poort in, standaard **514**. Een hostnaam/IPv6-adres wordt
  in deze eerste versie niet ondersteund. Er is geen standaard serverbestemming.
- Stel optioneel een markeringsinterval in, 0–86.400 seconden; 0 schakelt markers
  uit. MARK is INFO en volgt ook het gekozen niveau.

De webbuffer bevat maximaal 32 regels. Elke regel heeft een oplopend volgnummer,
module, ernst en uptime in milliseconden; een nieuwe boot heeft een andere
bootidentiteit. De browser bewaart maximaal 256 werkelijk ontvangen regels en
haalt maximaal acht regels per antwoord op. Bij overschrijving, drukte, afkappen
of syslogverlies staan tellers in het scherm. De browser pollt iedere twee
seconden en stopt bij pauzeren of het verlaten van de pagina.

## Externe opslag

De collector bepaalt bewaartermijn, doorzoekbaarheid en back-up. Het apparaat
schrijft geen logregels naar flash, NVS of SPIFFS. Alleen gewijzigde instellingen
worden na expliciet opslaan bewaard, in de afzonderlijke namespace `ot_logging`.
NVS-commit en teruglezing moeten slagen voordat de nieuwe instellingen actief
worden. Bij een onzekere teruglezing kan de opslagtoestand onbekend zijn; de
lopende configuratie wordt niet als succesvol gewijzigd aangeboden.

Syslog gebruikt RFC5424, UDP, facility local0. Ernst wordt uit het werkelijke
logniveau afgeleid. De RFC-timestamp is NILVALUE; het bericht bevat de uptime en
het volgnummer. De collector kan de eigen ontvangsttijd vastleggen. Het apparaat
verzint geen absolute tijd wanneer tijdsynchronisatie nog niet betrouwbaar is.
UDP heeft geen ontvangstbevestiging: **verzonden** betekent alleen dat de lokale
netwerkstack het pakket aannam. Het bewijst geen opgeslagen regel op de server.

Er kunnen maximaal acht syslogberichten wachten. Na regelwerk wordt hoogstens
één pakket per 100 ms verstuurd via een nonblocking socket, zonder DNS, TCP,
retry of herpublicatie van de RAM-historie. Tijdens waargenomen offlinebedrijf
worden oude wachtende berichten en nieuwe externe regels weggegooid en geteld.
Bij opstart staat de externe ontvangstroute eerst offline; lokale startupregels
kunnen dus wel in de webbuffer staan en niet op de collector. Verandert de
bestemming, dan worden oude wachtende berichten niet naar de nieuwe server gestuurd.

## Wat wordt vastgelegd?

De bestaande applicatielogger levert het juiste niveau en de module. Gewone
Arduino-logmeldingen, bijvoorbeeld van `ssl_client`, worden via de gepinde
`log_printf`/`log_printfv`-route meegenomen. ESP-IDF gebruikt zijn bestaande
`esp_log_set_vprintf`-hook. De oorspronkelijke seriële uitvoer blijft behouden,
ook wanneer de diagnostische kopie te lang is. De native capture is idempotent
en verricht geen netwerk-I/O. IRQ-/ROM-/vroege boot-/panic-uitvoer kan de normale
hooks omzeilen en blijft buiten deze web/sysloggarantie. Weggecompileerde native
debugregels worden niet teruggebracht door een hogere weergave-instelling.

Veelvoorkomende credential-, header-, URL- en configuratie/payloadberichten worden
als hele regel onderdrukt in de web/syslogkopie. Te lange printf-kopieën worden
ook onderdrukt; tel deze als afgekapt/afgeschermd. Regelovergangen en terminal-
controlcodes kunnen geen extra logregels of terminalkleuren injecteren.
De webweergave gebruikt tekstnodes en geen HTML uit berichten. De lokale
USB-uitvoer van setup-/admincredentials loopt niet via de nieuwe logcapture.

Lezen vereist de bestaande E32-sessie. Opslaan/wissen gebruikt dezelfde
CSRF-, origin-, methode-, update- en actieve-proefguards als andere beheeracties.
Er wordt geen tweede loggernetwerkclient met eigen taak, timer of service gestart.
De bestaande oude TCP-logbestemming in netwerkconfiguratie is een afzonderlijke
historische functie; die is geen RFC5424-syslogcollector en wordt niet automatisch
gewijzigd of omgezet.

## Instellingen die er al zijn en vervolg

Hostnaam, netwerkkeuze, MQTT, NTP-server/tijdzone, diagnose van vrij geheugen en
update/herstel bestaan al. Deze batch voegt de web/syslogniveaus, filtering,
export, markeringen, resetreden en verliesdiagnose toe. De productie-installatie,
ontvangst op een werkelijk gekozen collector, runtime-heap/stack en gedrag
bij langdurige hoge logbelasting horen bij de gezamenlijke release-nacontrole.

Referentie voor de protocolkeuze en praktische instellingen:
[EMS-ESP configuratie](https://docs.emsesp.org/Configuring). De implementatie is
projecteigen en gebruikt de bestaande gepinde logger en ESP-netwerk-API's;
er is geen EMS-ESP-implementatie overgenomen.

## Bronverificatie

De native suite slaagt in 573 gevallen, inclusief 18 nieuwe logging-/settings-/
HTTP-policygevallen. Vier Chromiumprofielen (NL/EN, desktop/320 px) controleren
filter/pauze/export, opslag/readback/foutbehoud, bootwissel en stoppen na navigatie.
46 bestaande auth-/root-/herstart-/managed-UI-/taaltests blijven groen.
De echte firmware-storage/logger/transport- en native-hookcode is ook uitgevoerd
met foutinjectie aan NVS en echte loopback-UDP, onder ASan/UBSan met leakcontrole.
Dit zijn software-/fixtureproeven; geen nieuwe firmware-installatie of echte
collector-/langdurige runtimeacceptatie. Zie `out/logging-20261024/`.

De E32-linkercontrole bevestigt ook dat de bestaande SDK-wrapper daadwerkelijk
naar de nieuwe `log_printfv`-capture doorstuurt en dat de originele UART-functie
behouden is. De onafhankelijke firmwarecontrole blijft slagen voor partities,
dubbele OTA/SPIFFS, inert/defaultveilig gedrag en geen project-EMS-UART-TX.
