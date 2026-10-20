# HA–E32 graph capability/apply — reviewvoorstel, geen actieve API

20 oktober 2026. Basis daf5347. **Status: voorstel + HA desired-roombron;
geen firmware-implementatie, capabilityadvertentie of test-/verwarmingsvrijgave.**
TEST-WIRE blijft schema1/api1 exact ongewijzigd. CONTRACT is architectuur;
TEST-WIRE is de daadwerkelijk gebouwde beperkte shadowvariant.

## 1. Geleverde lokale migratie

Native kamerflow heeft expliciete outputmodus:
- climate_trv (standaard, ook voor alle oude records zonder discriminator);
  minimaal één climate-TRV, oude as_dict/mapping/wirevorm exact behouden.
- graph_only_draft: geen climate-TRV selecteren; kamer bestaat met eigen sensor,
  permanent ID, doelen/grenzen, optionele doelbron en week. Actuatoren worden
  apart in de bestaande gewenste Heating graph gekoppeld. Een lege graph is
  onvolledig gewenst, geen impliciet bedienbare vloer.

Modewisseling vereist expliciete bevestiging én runtime uit, inclusief werkelijk
nog actieve runtime tijdens reload. Oude TRVs worden alleen door de expliciet
lege selectie ontkoppeld; echte entities blijven bestaan. Omgekeerde migratie
vereist echte TRVs opnieuw selecteren. Kamer-ID/week/bounds/central/groups en
graphoutputrecords blijven behouden. De graph behoudt dezelfde logische
kamerreferentie, niet een tweede executor. Native remove gebruikt de bestaande
begrensde cascade: alleen die kameractuatoren, groepen/central blijven.

Opslag is native ConfigSubentry/Store. CAS voorkomt dat een oud kamerformulier
nieuwe data overschrijft. Weekeditor valideert mode/eigendom opnieuw op Save.
Geen HA config-entryversiebump: oude recordvorm blijft letterlijk geldig; alleen
nieuwe graph-only records hebben binding_mode=graph_only_draft en
actuator_profile=graph_draft_not_applied. Dit is lokale opslag, geen wirekey.

Gemengde entry met één graph-only kamer: **hele huidige shadowexport geblokkeerd**,
niet graphkamers overslaan en rest stil toepassen. Options weigert enable/legacy,
setup weigert dit ook bij extern gewijzigde options; runtime weigert listeners en
transportattach; MQTT configuratiebouw faalt vóór Store/subscriptions/publish.
Disabled gewenste klimaatentiteit blijft unavailable, niet fictief toegepast.

## 2. Voorgesteld contract (firmware-review vereist)

Besluitvoorstel: aparte api2/schema2 graph-shadowprofile, onder bestaand prefix
maar versiepad /v2/. Geen automatische fallback naar api1. Hergebruik owner-,
boot/session/grantsequence/lease en canonical-byte-hashsemantiek uit TEST-WIRE;
geen nieuw cryptografisch authmechanisme en geen extra configschrijver.

HA blijft eigenaar van registry-/device-/actionmapping en gewenste configuratie.
Firmware beheert accepted config, effectieve doelen, kalender, regel-/EMSstatus.
Een ondersteunde firmware advertentie moet exact melden:
- api_major=2, config_schemas=[2], modes=[shadow_graph];
- capabilities: versioned tokens voor daadwerkelijk geïmplementeerde functies
  (namen uit required_capabilities in fixture), nooit uit HA-selectie afgeleid;
- limits: config_bytes, message_bytes, json_nodes, json_depth, string_bytes,
  rooms, groups, actuators, schedule_transitions en admission_streams;
- controller_id, boot_id, connection_epoch, config_revision/digest,
  mapping_revision/digest, firmware/build/protocol-profile-ID.

Capabilities zijn exact overeengekomen ASCIIliteral-tokens (max64bytes),
geen willekeurige HA-input of kanaal-ID; onbekende REQUIRED tokens blokkeren apply.
Alle limits zijn door firmware vastgestelde bovengrenzen voor deze build. Ontbreken,
onbekende schema/capability, onbekende veiligheidsprofielen: geen apply. HA draft
limits8groepen/64actuatoren zijn géén firmwarebelofte. Huidige firmware meldt deze
api2 capabilityset niet en moet als unsupported worden behandeld.

### Exact gewenste configroot en veldbetekenis

Het reviewfixture ha/tests_native/fixtures/graph-contract-proposal.json bevat
volledige integer-JSONconfig plus bijbehorende mapping. Root EXACT:
schema, mode, revision, mapping_revision, mapping_digest, required_capabilities,
central, groups, actuators, rooms, qualification.

- schema2, mode shadow_graph; revision volgende uint32 van firmware accepted.
- mapping_revision volgende immutable HA mappinggeneratie, digest SHA256 van
  compact sorted recursive ASCII integer-JSON (zelfde canonieke procedure).
  Identieke mapping mag dezelfde generatie behouden; andere bytes nooit.
- central: huidige normalized control_proposal.central exact, geen HAentity.
- groups: huidige normalized control_proposal.groups zonder menselijke name.
- actuators: huidige normalized control_proposal.actuators exact.
- rooms: zone_id, sensor_id, base_centi_c, minimum_target_centi_c,
  maximum_target_centi_c, max_age_ms, report_profile_id, report_evidence,
  schedule (bestaande finite UTC ScheduleDocument of null).
  Identiteiten uniek; verwijzingen bestaan; huidige grens5..35C, base/week binnen
  kamermin/max; geen fictief actuator_id voor een kamer zonder TRV.
- qualification: record_digest (HA immutable profiel-/commissioningmanifesthash
  of null), outputs_ready=false, boiler_ready=false. In shadow zijn deze flags
  verplicht false; ze zijn GEEN vrijgaveknoppen voor actief bedrijf.

Fixture is **opzettelijk NIET applybaar**: report_profile_id/report_evidence en
record_digest zijn null. Voorstellen zijn zo reviewbaar zonder fysieke feiten te
verzinnen. Een latere complete graph-shadowconfig mag pas applied heten na
overeengekomen schema, echte rapportkwalificatie en geïmplementeerde validators.
Geen entity/service/token/namen in de wireconfig; mapping blijft uitsluitend HA.
Huidige control_proposal heeft nog groepsnamen en is dus NIET rechtstreeks wire.

### Exact mutatie- en readbackvoorstel

Onder /v2/: ha/config, fw/config_result, ha/snapshot_request,
fw/config_snapshot, fw/hello, fw/session. Niet in deze patch geregistreerd.
Common envelope = TEST-WIRE identities/grant/counters, maar api=2.
ha/config extras EXACT expected_revision, config_digest, config.
Eén atomaire set/apply/ack zoals huidige shadowwire, GEEN extra prepare/commit-
protocol of distributed database. staged is een HA Storestatus, niet al FWapply.

HA Storejournal: accepted record plus maximaal één immutable staged record;
record={config,config_digest,mapping}. Staging moet duurzaam slagen vóór publish.
FW valideert schema/caps/ref/limits/safety/whole hash vóór enig effect. Commit
bestaande native NVSblob, native commit én exacte readback vóór activeren.
FWresponse: common result identity+binding_id+sequence, status,
config_revision,config_digest,mapping_revision,mapping_digest. Toegestane status:
applied,duplicate,conflict,rejected,storage_fault. Rejected heeft bounded error_code
(unsupported_schema,unsupported_capability,incomplete_configuration,budget_exceeded,
invalid_reference,unsafe_profile). Geen ruwe input echo.
Conflicts veranderen niets en tonen expected/accepted apart in HA.

Na apply sessie/samples/overrides/readiness intrekken. Nieuw admitted handshake
met exacte accepted revision/configdigest/mappinggeneration/digest, verse bronnen
en actuatorterugmelding vereist; output blijft uit in shadow_graph.
Reconnectsnapshot bevat accepted CONFIG, niet een claim dat HA mapping aanwezig is.
Onbekende snapshot/mapping vraagt zichtbare reconciliatie; geen mapping op naam
reconstrueren en geen oude backup stil winnen.

HA zichtbare staten: desired_draft → staged → awaiting_readback → accepted_shadow;
of unsupported_capability / revision_conflict / mapping_conflict / storage_fault.
Een GUI-save betekent alleen desired_draft. accepted_shadow blijft outputs=false,
niet physically_ready/heating. Geen voorspelde toegepaste waarde vóór FWreadback.

Verloren ACK: immutable staged bewaren, eerst snapshot. Exacte staged config+hash
en passende mapping → accepted. Exact vorige accepted → retry uitsluitend huidige
toegelaten grant met nieuwe reconciliatie (geen oude TTL/boost herstarten).
Andere config → conflict, geen automatische overwrite. Retry binnen dezelfde
grant gebruikt exact bytes/sequence. storage_fault kan al commit hebben gedaan:
geen oude geheugenconfig blijven gebruiken; runtime geblokkeerd tot herstelreadback.
Rollback is opnieuw gevalideerde volledige vorige inhoud met NIEUWE next revision,
niet teller terugzetten. HA rollbackmapping eerst stagen. Hardwareveilige stop/
naloop is aparte vrijgave; opslagrollback belooft die niet.

## 3. Freshness en apparaatveiligheid: niet door schema wegpoetsen

Per sample bronprofiel, echte sample-age/evidence plus receiver grant-delay;
healthy heartbeat/cache/last_changed/last_reported/device_seen zijn geen fysieke
sample. Firmware eigen monotone validity, HA state alleen metadata. Buitenbron
heeft apart profiel/cadans; weerattribuut is niet vanzelf gekwalificeerd.

Voor actief bedrijf ontbreken nog echte profielvelden/validatie en commissioning:
- binary: NC/NO is fysieke spanningsloze toestand; softwarepolariteit/inversie
  apart, command/standterugmelding, travel/open-close verschillen, retrybudget,
  readinessniveau, stale/uitvalbeleid; TPI grens is geen minimumflowbewijs.
- proportional: entity-unit/schaal/richting, min/max/endstops, linearisatie/
  kalibratie, gemeten versus aangenomen positie, feedback/timeout/uitval.
- mixer: aparte aanvoerlus, 3-punts OPEN/CLOSE harde wederzijdse interlock,
  referentie/homing/powerloss; 0–10V schaal/richting/kalibratie, geen universele
  flowklep; eigen aanvoersensoractualiteit en onafhankelijke limiet.
- floor: vloer-/waterlimieten en betrouwbare sensoren, fysieke high-limit,
  menging/hydrauliek, pompvolgorde/naloop/minimumflow en uitval zonder HA/broker.
- TRV: externe meetmodus/cadans/echo/handbediening/readiness/devicefallback.

Voor elk vereist veld zonder bewijs: incomplete/unsupported, NIET standaard NC,
invert=false, feedback=confirmed of safe_closed invullen. Geen actuatorcallbacks
of actieve profilecapabilities in dit pakket. Hardwareacceptatie blijft open.

## 4. Budget: wat de huidige E32 echt begrenst

Bronregels: ShadowController.h66,190–225; BoundedJson.h17–18;
SessionAdmission.h37; UtcSchedule.h21–24; ModernTransport.h66–77;
DeviceNetworkSettings.h17–23; partitions_e32v2.csv2.
Huidig: config4096B; bericht8192B;512lexicale nodes INCLUSIEF objectkeys;
containerdiepte8; strings64B;8shadowzones;128transities per zone;
48admissionstreamslots; MQTTbuffer8448B; NVS20480B; netwerkblob max2048B inclNUL.
**Graph groups=0 / graph actuators=0** in actieve decoder, geen8/64 hardwareclaim.
8zones bevatten vaste8×128=1024 transition slots in Configuration; bij apply
bestaan old/candidateconfig, JSONboom, raw/canonicalbytes en readback tegelijk.
E32 ABI/heap/NVS GC/latency/powerloss niet gemeten: getal8 bewijst geen capaciteit.
Niet 1024transities als transportcapaciteit aanbieden.

Offline audit budget_audit.py + budget-evidence/current-budget.json gebruikt exact
canonicalserialisatie, telt lexicale keys/nodes/containers en bindt bronhashes.
Exacte fixturegetallen (kleine IDs,15UTCdagen,Europe/Amsterdam):
- 0 zone(s), 0 transities/zone: config136B; bericht459B/39nodes/diepte3; budgetfit=True.
- 1 zone(s), 0 transities/zone: config302B; bericht625B/54nodes/diepte4; budgetfit=True.
- 8 zone(s), 0 transities/zone: config1471B; bericht1794B/159nodes/diepte4; budgetfit=True.
- 1 zone(s), 128 transities/zone: config2762B; bericht3085B/450nodes/diepte7; budgetfit=True.
- 8 zone(s), 128 transities/zone: config21151B; bericht21474B/3327nodes/diepte7; budgetfit=False.

Dit zijn parser-/bytesgrenzen, geen fysieke capaciteit. Bij8zones passen in deze
EXACTE IDfixture maximaal9gelijke transities per zone; bij2zones69, bij1zone128.
Andere IDs, profielvelden en envelope veranderen dat. Geen vaste kamer×weekbelofte.
Reviewfixture zonder schema/veiligheidskwalificatie meet1503B config en1826B/
166nodes/diepte5 met huidige kleine voorbeeld-envelope. Dit bewijst uitsluitend
grootte, niet ondersteuning. Capabilityadvertentie en volledige veiligheidsvelden
kosten extra budget en moeten opnieuw worden gemeten.
Nieuwe graphpayload moet altijd HELE config EN HELE envelope budgetteren en
alle build-advertised limits volgen. Geen truncatie/chunking/hoger partitionbudget
als impliciete oplossing.15dagen horizon kan niet passen: expliciet budgeterror,
niet verkorten zonder zichtbare productkeuze.

## 5. Beslispunten voor volgende gezamenlijke firmwarestap

1. Firmware-review api2/schema2/namespace en exacte velden; eerste oplevering alleen
   graph-shadow, niet actieve aansturing. Bestaande api1compat behouden.
2. Minimale werkelijk uitgewerkte bron-/actuatorprofielmanifesten + negatieve
   fixtures vastleggen; incomplete draft mag opgeslagen, nooit applied.
3. Structurele arrays/streams en feitelijke heap/NVS/latency begroten, daarna
   build limits adverteren. Groepen/actuatorcaps niet op HA64 extrapoleren.
4. Beide kanten dezelfde fixtures; actual parser/store fault/replay/reconnect
   en native mappingstage testen. Dan pas GUI/apply koppelen.
5. Fysieke bron/device/doorstroming/stop/uitvalacceptatie blijft eigen latere poort.
Geen Markinput vereist voor bovenstaande bronreview; onbekende installatiefeiten
worden later gericht ingevuld, niet nu verzonnen.
