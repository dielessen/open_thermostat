# Native ControlPlan v1 — begrensde verticale bronketen

## Doel en scheiding

Route B vervangt voor deze expliciete bronkeuze de DATA→configprojectie/factoryfase door één volledig duurzaam `schema:2, mode:shadow_plan`-record. Bestaande native HA subentries/options, MQTT-worker, API1-sessie-envelop, ControlStore/NVS-configkey, ShadowController/regelaars en safetygedrag blijven in dezelfde keten. Geen tweede owner, protocolworker of scheduler.

Drie verschillende zaken blijven gescheiden:

1. **Gewenst en toegepast:** beide kamers, groepen, mapping, doelen, UTCschema en optionele comfortinstellingen in één `control.plan.v1`-configuratie.
2. **Onafhankelijke installatie-SOURCE:** vaste kamer/resource-identiteiten, expliciete profielen en grenzen; geen per-config compiled digest. De vertrouwde HA-bronselectie en C++ constructorargument zijn standaard NONE. Een formulier kan dit niet kwalificeren.
3. **Vluchtige bevoegdheid:** challenge/session/grant/lease, actuele bronrapporten en bestaande safetycallback. Nooit uit config/readback/ACK herstellen. Positieve shadowintenties betekenen geen actuator-/TX-/EMS- of fysieke bescherming.

De oude gepinde `seasonal.shadow.v1`-SOURCE/schema1 en API2-DATA houden hun eigen betekenis. Geen automatische migratie/fallback/adoptie of pinversoepeling.

## Eerste versie: bewust begrensd, niet alle productfuncties afgerond

Precies twee onafhankelijke kamers: één radiator/local-TRV en één ongemengde vloer/slow-binary-PI, twee groepen en vier unieke resourcekanalen. Geen pumps/mixers/weersafhankelijke bronconfig in deze eerste versie. Layout/hydrauliek/resources blijven onafhankelijk SOURCE-gekwalificeerd; wijzigen daarvan vereist opnieuw een passende expliciete bronselectie, niet alleen graph_ready. Basisdoel en native weekschema kunnen binnen dezelfde bestaande profielgrenzen wijzigen zonder SOURCE/factorywissel.

Het volledige record blijft binnen bestaande 4096B config, 8192B wire, 512 JSONnodes en queue64. Maximaal acht UTCovergangen **totaal** voor twee kamers in het bestaande maximaal16daagse venster. Grotere gewone weekprogramma's worden expliciet geweigerd, nooit afgekapt. Dit is dus nog geen volledige R18-schemadekking/acht-zoneoplevering. Volgende noodzakelijke softwarestap is een compact begrensd weekschema-/refreshcontract met passende bestaande evaluator en gemeten resources; geen plafond verhogen om een fixture te laten slagen.

## Gewone HA-bediening en terugmelding

Bestaande optiesflow: prepare → review → expliciet éénmaal apply → pending/exact readback/conflict. Prepare compileert werkelijk opgeslagen subentries en controleert owner/entry/registry/profiel/journal opnieuw na de laatste Store-await, vóór staging. Annuleren verzendt niets; een duurzaam staged concept wordt niet stil gewist. Een review verloopt absoluut na300s; dubbel apply en changed scope weigeren. Eén bestaande worker serialiseert IO.

Een ACK is geen toepassing. Alleen op een eigen actuele snapshotrequest teruggelezen volledige bytes/digest/revisie/mapping onder huidige boot/session/grant bewijzen toepassing. Onbekend remote record wordt niet geadopteerd of overschreven. Een onduidelijke commit bewaart staged/uncertain; na herstel alleen vers exact readback of nieuwe expliciete review, geen optimistische rollback. Oude readback wist geen nieuwere stage. De huidig gewenste config moet overeenkomen voordat controlready kan worden.

Normaal HA-herladen behoudt config maar niet sessiebevoegdheid. Bij een gewijzigde firmwarechallenge vervalt een pending oude openrequest en komt een nieuwe nonce; de onafhankelijke SOURCE blijft gelijk. Wijzigen van eigenaar/entry/registry/SOURCE blokkeert ready en retries. Waargenomen samples en overrides verdwijnen bij reconnect/herstart; geen persistent learning/admission.

## Migratie, behoud en rollback

Nieuwe capability `control.plan.v1` plus onafhankelijke `installation.shadow.v1`-metadata zijn verplicht. Oude peer/schema of verkeerde bron weigert expliciet. Er ontstaat geen nieuwe persistente key/partitie. Bestaande schema1/API2-gegevens worden niet overschreven bij selectie van deze incompatibele nieuwe rol; eerst een afzonderlijk expliciet data-/exportmigratieplan. De huidige eerste versie weigert onbekende journal/device schema's en laat bytes intact.

Rollback alleen eigen nieuwe broncommit vóór afhankelijke inzet; geen NVS/journal/model/Recorder/configgeschiedenis wissen. Een al toegepast schema2-record kan niet veilig met een oude controller worden gebruikt: export/compatible bronherstel is dan een afzonderlijke gate, niet factory reset of stil downgradereadback. Er is niets uitgerold.

## Bewijsgrenzen

Echte native HA2026.10.2/Store/options/registry/lifecycle en opnieuw gebouwde actuele C++ finite peer/controller/cJSON. SOURCE-, physical_report- en safetygegevens zijn expliciet synthetische contractfixtures; geen hardwareproducerbewijs. Sanitizers instrumenteren core/peer/cJSON; host OpenSSL testprovider blijft externe library. Pinned Xtensa object/individuele stackframes zijn geen totale callgraph/heap-/NVS-GC-/8zone-/72u-/fysiekbewijs.

Actual frontendbrowser en gezamenlijke normale firmwarebeelden blijven apart toetsen op exact samengestelde bron na parentreview. Bewaarde oudere E32/S3-buildreceipts worden niet als nieuwe beelden geherlabeld. F9's14kandidaten blijven afgewezen/onvoldoende. SDK/source/licenseclosure blijft BLOCKED zolang exacte bron-/build-/noticekoppeling ontbreekt. Alle31eisen/F0–F10 blijven doel; deze bronstap is geen product- of verwarmingsGO.
