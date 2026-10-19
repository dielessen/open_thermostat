# WP03 — bron-/sessie-/tijdkern (in uitvoering)

20 oktober 2026. Deze pure firmwarecomponenten zijn geïmplementeerd en
host-getest, **nog niet als nieuwe MQTT-/HA-regelketen ingeschakeld**.
Het volledige [contract](CONTRACT.nl.md), persistente configuratietransactie,
native transportkoppeling en productacceptatie zijn hiermee niet afgerond.

## Concrete componenten

- `control/Measurement.h`: bronneutrale temperatuur in honderdsten°C;
  expliciete°Fconversie/kalibratie, eindige waarden/grenzen, werkelijk
  opgegeven bronouderdom plus conservatieve transportvertraging, onbekend/
  ongeldig/gerestored/onbeschikbaar/onbevestigd/verouderd apart. Een gelijk
  nieuw fysiek report kan vers zijn; cache, last_seen of willekeurige HA-
  statewrite is zonder gevalideerd profiel niet genoeg. Uitlezen vernieuwt
  niets. Leeftijd gebruikt64bit monotone tijd; overflow of teruglopende klok
  maakt een waarde niet bruikbaar. Geen globale herstart bij één slechte bron.
- `control/SessionAdmission.h`: lokale toelating na geauthenticeerde
  handshake, gebonden aan controller/boot/adapter/sessie/epoch/revisie en
  vooraf geconfigureerde binding+berichtsoort. Beide ontvangstrichtingen
  krijgen hun **eigen ontvanger-issued grant** en lokale deadline.
- Per stream één gecachte uitkomst met blijvende high-water sequence voor
  de hele sessie-epoch. Duplicaat past niets toe en behoudt de oorspronkelijke
  deadline; een ouder bericht na cache-eviction blijft oud. Andere payload
  onder dezelfde sequence is een fout. Grantrotatie reset deze teller niet.
- Iedere grant heeft bovendien een oplopende `grant_sequence`, naast het
  token. Daardoor maakt zelfs A→B→A-tokenhergebruik een oud ongezien bericht
  niet opnieuw vers. Een herverbinding vereist een nieuwe epoch; dezelfde
  boot kan geen oudere/gelijkblijvende epoch opnieuw openen. Een onbevestigde
  eigenaar of configuratierevisie0 geeft geen normale observatie/actuatievrijgave.
- `control/UtcSchedule.h`: één begrensde firmwarekalender-evaluator van
  UTC-overgangen. Gehele kandidaat eerst valideren, oude tabel behouden bij
  ongeldige invoer. Geen actie-/retrybijwerking door een statusread of NTPsprong.
  Zonder gevalideerde tijd of buiten de geldigheid geen normale schemavraag.
- `control/BoundedJson.h`: beperkte v1-controlsubset boven de bestaande cJSON
  library. Vóór boomallocatie maximaal8192bytes,8nestings,512tokens/nodes en
  64bytes per string; alleen printable ASCII zonder escapes in controlvelden.
  Menselijke labels/HA-entitynamen blijven buiten dit wireprofiel. JSONgetallen
  krijgen correcte lexicale syntax; dubbele keys, NUL/escapealiases en niet-
  eindige waarden worden geweigerd. Dit is geen nieuwe algemene JSONlibrary,
  en nog niet als normale MQTTingang aangesloten.

`SessionAdmission` authenticeert zelf geen MQTT-client en verwerkt geen
willekeurige HA-servicecall. De transportadapter moet JSON-vorm/waarden/
payloadhash en topicscope controleren vóór toelating. Begin/bind/grant zijn
vertrouwde lokale API's, geen te publiceren onbeschermde beheeracties.
Ook een logische lease kan een uitgevallen controller niet fysiek laten
stoppen: ketel-/klep-/naloopveiligheid blijft apart fysiek te bewijzen.

## Vastgelegde schema-/DSTkeuze

HA2026.10.2 heeft publieke `schedule.get_schedule` met volledige weekexport,
native subentries/selectors en changed+reported listeners. Geen eigen
weekeditor of extra schedulerdaemon nodig. De HA-adapter compileert week,
basisdoel en IANAzone naar een **begrensde UTC-horizon**; alleen firmware
evalueert de effectieve planning. Ruwe helper-/entityidentiteit blijft in HA.

Productbeleid `wall-clock-membership/v1`: lokale intervallen [start,eind).
Een geheel niet-bestaand lenteblok wordt overgeslagen; een deels passend
blok begint op het eerste geldige passende tijdstip. Beide herhaalde
najaarstijdstippen tellen afzonderlijk, inclusief basisdoel in een tussengat
waarin de teruggezette lokale klok buiten het blok valt. Niet zonder bewijs
gelijkstellen aan de volledige native HAtimerruntime.

Elke tabel begint met het werkelijk geldende doel op `valid_from_utc` en
eindigt exclusief op `valid_until_utc`. Normaal compileervenster15UTCdagen
vanaf de UTCdaggrens; hard maximaal16dagen,128transities per zone. Verlopen
horizon toont `expired`, geen belofte van onbeperkte HA-onafhankelijkheid.
Een dagelijkse native HA-refresh materialiseert alleen de kalender; hij
voert geen tweede kamer-/ketelregelaar uit. De pure HAcompiler en publieke
readadapter zijn nu opgenomen in de integratiebron, maar nog niet aangesloten
op de normale integratielifecycle. Alleen UTC/Europe/Amsterdam en2000–2099
zijn ondersteund; andere zones/datums worden expliciet geweigerd.

## Softwarebewijs en nog open

`wp03-admission.log`: **103/103 native tests PASS** (alle eerdere81 +22
bron-/kalender-/sessiegevallen). Onder meer source-age/overflow/cache/restore,
NTPsprongen, beide folds, lease versus grant, duplicaten zonder verlenging,
cache-eviction, verkeerde identiteit/revisie/major/stream, beide ontvangers
en vertraagde actuatoropdracht. Dit zijn pure tests, geen MQTT-/HA-/deviceproef.

De HAcompiler van de specialist is met alle5 manifestentries gecontroleerd
en ongewijzigd opgenomen. Parent `wp03-ha-compiler-parent.log`:34/34 offline
Pythonunittests PASS, inclusief echte zoneinfo/second-by-second oracle en
executorjob. Publieke HA-action wordt alleen aan de unitgrens gemockt; geen
live HAactie of volledige HA/Python3.14-load getest.

`wp03-schedule-interop.log`:106/106 native PASS. Nieuwe gedeelde JSONfixtures
gaan via `ScheduleDocument.h` naar de **echte** firmwarekalender; iedere
seconde in beide DSTvensters wordt tegen onafhankelijke verwachtingen
getoetst. Booleans, verkeerde vormen/units/extra of dubbele fields,
geteste niet-integrale tijdwaarden en ongeldige overgangsvolgorde vervangen
niets gedeeltelijk. cJSON bevat al geparseerde doubles: exacte lexicale
integerzekerheid vóór eventuele afronding is hiermee niet universeel bewezen.
De documentdecoder krijgt een reeds begrensde/gevalideerde cJSONboom;
`parseControlJson` is de toegevoegde ruwe inputgrens voor deze beperkte
controlsubset. Echte topic-/identiteits-/sessietoelating en eventuele nieuwe
payloadprofielen moeten hier nog correct aan worden gekoppeld. Dit maakt de
bestaande legacy MQTT/RESTparsers niet automatisch begrensd of beveiligd.

HA gedeeldefixturetests:38/38 parentPASS (`wp03-ha-fixtures-parent.log`),
inclusief hercompilatie, canonicalSHA256 en2038/2100bounds. Native na de
source/runtime- en parsergevallen:118/118 PASS (`wp03-bounded-json.log`).
Zie [werkelijke legacybronwijzigingen](WP03-SOURCES.nl.md) voor de strikt
begrensde koppeling die wél in de bestaande firmwarecallpath is gewijzigd.

Ontbreekt nog: overige sessie-/measurement-/config-/actuatorwirefixtures en echte transportvalidatie,
persistente configuratie en revisionrecovery aan beide kanten, HAflow/
lifecycleintegratie, daadwerkelijke bronprofielen, actuatorcallbacks,
resource-/bufferproeven en end-to-endketen. Legacy BLE-/curve-/MQTTcode is
nog niet volledig vervangen door deze kern. De oude synthetische−20°Cfallback
en globale BLEherstart zijn wél uit de werkelijke runtime verwijderd, zoals
WP03-SOURCES documenteert; dat bewijst geen fysieke stop. De aanvullende
[BLE-inputvalidatie](WP03-BLE.nl.md) gebruikt nu eveneens de echte runtimecallpath.
Bronprovenance/samplecadans en volledige HA-koppeling blijven open.

De limieten48streams/128transities zijn broncodegrenzen, geen bewezen
hardwarecapaciteit. E32/PSRAM/netwerkprofiel, originele backup/herstel,
fysieke TRV-/sensorvalidatie en de cumulatieve P0-/securitygates blijven open.

## Onafhankelijke ontvangstreview

De HA-specialist heeft de vier exacte kernheaders en een WP03docsnapshot
na5/5 SHA256controle beoordeeld. Geen kritieke bronbug gevonden onder de
gedocumenteerde pure precondities; nadrukkelijk **geen hele-WP03-GO** en geen
live C++-/HA-/deviceproef door die reviewer. Bewijs in de uitvoeringsartefacten:
`ha-review-fixtures/parent-snapshot-review/receiver-review.md`.
De later toegevoegde `BoundedJson.h` en runtimebronwijzigingen zaten niet in
die vijf snapshots; geen onafhankelijke review daarvan claimen.

Voor latere koppeling expliciet: lokale HA-monotone milliseconden en eigen
process-/bootcontext; nooit firmwareuptime of UTC als HAleaseklok gebruiken.
Een begin/newboot is een vertrouwde lokale beslissing ná bewezen verse
handshake, niet iets dat ieder authenticated netwerkpakket mag forceren.
Heartbeat kan in deze primitive na een leasegat met een actuele grant en
nieuwe sequence herstellen; dat geeft **geen** oude source-/actuatorreadiness
terug. Runtime moet op leaseverlies alle betreffende readiness intrekken en
zijn gekozen herstel-/reconciliatiepad bewijzen. Een logische commandretry
houdt dezelfde sequence/digest; hogere sequence is een nieuwe mutatie.
Een gecachte immutable receipt is geen fysieke actuatorterugmelding.

## Eindcheck van dit softwarecheckpoint

Bewijsmappen20oktober: `open-thermostat-build-20261020/` op de ontwikkelhost.
Alle owned resultaten verzameld, geen achtergelaten build-/testproces.

- Native118/118 en HAoffline38/38 PASS;90.000 deterministisch seeded
  raw-byte/mutatiegevallen door echte BoundedJson+cJSON+schemavalidatie onder
  AddressSanitizer/UndefinedBehaviorSanitizer zonder fout/leak. Dat is een
  begrensde robuustheidsproef, geen bewijs tegen alle mogelijke input.
- `wp03-final-matrix.log`:3/3 PASS. E32flash1.750.769/RAM64.416,
  ESP32devflash1.702.221/RAM64.296, S3flash1.593.757/RAM59.308 bytes.
- `wp03-buildfs.log`, ongewijzigde compiled E32-verifier en faultinjectie5/5
  PASS; geen projectobject verwijst naar de gecontroleerde UART-TXprimitieven.
  Board-/partition-/veiligheidsverifierbestanden behouden ten opzichte vanWP01.
- Generieke4MB-app heeft nog **1.715bytes** ELFflashruimte. Nieuwe moderne
  modules vereisen expliciete feature-/resourceafbakening; geen verborgen
  partitiewijziging of beweerde8-zonecapaciteit. E32heeft grotere appslots,
  maar beschikbare PSRAM/heap/netwerk en echte uitvoeringsduur zijn nog fysiek
  te bevestigen. Native ASan en firmwarebuild zijn verschillende bewijzen.

**Checkpoint afgerond, WP03/product nog in uitvoering.** Algemene E32 V2-
specificaties en USB-C-programmeerroute zijn beschikbaar bij BBQKees; geen
bordfoto nodig om onafhankelijke softwarebouw voort te zetten. Exacte
identificatie, backup/herstel en netwerk-/PSRAMprofiel blijven vóór eerste
flash en fysieke validatie vereist. Geen flashbestand vrijgeven voor
aansluiting op de installatie. Resterende contract-/buffer-/config-/HA-/
deviceketenacceptatie blijft open; geen normale ketelbediening op basis
van alleen deze softwarechecks.
