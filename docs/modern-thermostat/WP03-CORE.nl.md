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
voert geen tweede kamer-/ketelregelaar uit. Compilerlevering/tests zijn nog
onder uitvoering bij de HA-specialist.

## Softwarebewijs en nog open

`wp03-admission.log`: **103/103 native tests PASS** (alle eerdere81 +22
bron-/kalender-/sessiegevallen). Onder meer source-age/overflow/cache/restore,
NTPsprongen, beide folds, lease versus grant, duplicaten zonder verlenging,
cache-eviction, verkeerde identiteit/revisie/major/stream, beide ontvangers
en vertraagde actuatoropdracht. Dit zijn pure tests, geen MQTT-/HA-/deviceproef.

Ontbreekt nog: gedeelde JSON/wirefixtures en echte transportvalidatie,
persistente configuratie en revisionrecovery aan beide kanten, HAflow/
lifecycleintegratie, daadwerkelijke bronprofielen, actuatorcallbacks,
resource-/bufferproeven en end-to-endketen. Legacy BLE-/curve-/MQTTcode is
nog niet vervangen door deze kern. De oude synthetische-20°Cfallback en
BLEherstart zijn dus nog geen opgelost runtimeprobleem; bij integratie
moeten ze door het afgesproken per-bron-/zonebeleid worden vervangen.

De limieten48streams/128transities zijn broncodegrenzen, geen bewezen
hardwarecapaciteit. E32/PSRAM/netwerkprofiel, originele backup/herstel,
fysieke TRV-/sensorvalidatie en de cumulatieve P0-/securitygates blijven open.
