# Losse graph-shadowvalidators — gedeelde testspecificatie

20 oktober2026, basis e16c4e6. **Bron-/testpakket; niet aangesloten op MQTT,
Store, applyGUI, actuatoren of firmware capabilityadvertentie.** Het is een
begrensde verdere uitwerking van HA-GRAPH-APPLY-PROPOSAL, geen wijziging van
actieve TEST-WIRE/api1. valid_shadow_candidate is NIET accepted/applied/ready.

## Exacte eerste testvorm

Python: graph_shadow_validation.py; C++: control/GraphShadowValidation.h.
Beide lezen dezelfde raw envelope+raw mapping+vertrouwde context uit
test/fixtures/graph-shadow-validation.jsonl. Geen Pythonclone voor C++:
test/interop/graph_validation_runner.cpp compileert echte C++ met project-pinned
ongewijzigde cJSON6d9f2443 en publieke OpenSSL SHA256 testABI.

**Conservatief testlayout**: exact1kamer/1ongemengde vloergroep/1binaire TPIklep;
max8transities per kamer én totaal8. Vaste native GraphShadowCandidate-array,
geen HA8groepen/64actuatoren-capaciteit extrapoleren. Streambegroting7:
adapter/config/snapshot3 + roomsample/doel2 + actuatorcommand/feedback2.
Deze streamrollen worden alleen geteld, niet aangemaakt/toegelaten/verzonden.
Andere kamer-/groepaantallen, TRV/proportionele/menger/pompprofielen en actieve
weerbron expliciet unsupported/test_layout_limit. Bestaande desired draft-GUI
mag zulke onvolledige/wijdere doelen blijven opslaan; hij roept deze validator
niet aan en wordt hierdoor niet actiever.

Herkenbare required-capabilitytokens moeten precies de gesorteerde unieke
synthetische tokenlijst in de fixtures zijn. Dit zijn **validator-testtokens**,
geen werkelijk door een E32 geadverteerde uitvoeringscapabilities. Bijvoorbeeld
central_weather beschrijft hier alleen het centrale schema; weather_enabled=true
wordt nog geweigerd. Capabilityadvertentie pas in gezamenlijk volgende pakket.

## Wirevorm en mappingcoherentie (review, geen geregistreerde topics)

Rootconfigschema2/mode shadow_graph en common api2envelope zoals het voorstel.
De complete envelope heeft exact:
api,controller_id,boot_id,epoch,adapter_id,adapter_session_id,grant_id,
grant_sequence,config_revision,binding_id,sequence,expected_revision,config_digest,config.

Context komt van de toekomstige eigenaar/admission/journal, NIET uit een
inkomend request of GUIcheckbox. Identiteiten/grantnummers moeten exact matchen;
sequence nonzero uint32. Deze pure validator doet GEEN tijdlease-, highwater-,
dedup-, grant-rotatie-, auth- of echte sample-admissioncontrole. Die bestaande
veiligheidslagen blijven noodzakelijk vóór ooit aansluiten.

expected_revision=envelope.config_revision=context.current_revision en
candidate.revision=current+1. Current UINT32_MAX → revision_exhausted; laatste
geldige UINT32_MAX mag eenmaal vanaf MAX-1. Geen wrap.
mapping_schema2, mapping_revision, channels zijn exact de lokale sidecarvorm.
Per kanaal: channel_id,owner_id,direction=input|output,resource_id64hex.
resource_id representeert de door HA vastgestelde registryresource-identiteit,
niet een HA-serviceproxy. Duplicaten ook tussen input/output worden conservatief
geweigerd. Adapter/config/snapshot zijn gereserveerd; topology- en kanaalIDs uniek.
Room/actuator/group/output/feedbackverwijzingen en richting/eigendom moeten matchen.
Werkelijke registry/devicealiascontrole blijft óók HA-eigenaarstaak, geen hashbewijs.

mapping_digest bindt de hele immutable lokale mapping. Identieke bytes behouden
generatie/digest; andere bytes vereisen exact volgende generatie. Ontbrekende
accepted digest bij nonzero generatie blokkeert. Exhaustion blokkeert verandering.
Gehele config_digest bindt hele canonicalconfig. Alle keys recursief gesorteerd,
geen whitespace/escapes/niet-ASCII/float/exponent/NaN/Infinity/duplicatekeys.
Bool is geen integer; alle numerieke tokens binnen signed±uint32 waarna
semantische exacte veldgrenzen gelden. Er wordt niets afgekapt/coerced.

## Expliciete minimale kwalificatievelden

Het eerdere voorstel had opzettelijk qualification={record_digest:null,
outputs_ready:false,boiler_ready:false}. Dat is ONVOLLEDIG en wordt nu geweigerd.
Voor deze testsubset wordt qualification uitgebreid met sources,devices,installation.
record_digest=SHA256(canonical {devices,installation,sources}); moet ook EXACT de
afzonderlijke caller-owned qualification_digest zijn. Zelf hash meesturen bewijst
geen kwalificatie: zonder vertrouwde anchor altijd reject. Alle positieve anchors
in fixtures zijn **synthetisch/test-only**, geen bewijs over Marks apparaten.

- sources[1]: channel_id,profile_id,evidence (physical_report of expliciet
  gevalideerd integrationreport), maximum_report_interval_ms,
  maximum_transport_delay_ms, restore_policy=reject,evidence_record_id,
  producer_path_record_id. Room report_profile/evidence matchen. Cadans+maxdelay
  moet strikt kleiner dan max_age zijn; cache/last_seen/last_reported/restored
  vormt nooit vanzelf zo'n manifest of sample.
- devices[1]: output_channel,profile_id,deenergized_position NC/NO,
  energized_position,command_polarity,feedback_channel,feedback_profile_id,
  feedback_maximum_age_ms,readiness,opening_deadline_ms,failure_policy_id,
  reference_policy,evidence_record_id,power_loss_position,safe_position,
  failure_action,stale_feedback_policy,safe_position_record_id.
  Eerste testprofiel ondersteunt expliciet on_energizes, end_switch_open,
  binary_endstops, withdraw_heat_deenergize en withdraw_heat bij stale feedback.
  NC/NO, richting en spanningsloze/safe positie moeten onderling overeenkomen.
  Dit zijn vereiste expliciete profielwaarden, GEEN voorgestelde defaults voor
  een werkelijk onbekend apparaat. Andere hardware krijgt later apart profiel.
- installation: group_id,minimum_flow_record_id,postrun_record_id,
  high_limit_record_id,maximum_supply_centi_c,high_limit_kind,
  floor_limit_kind,maximum_floor_centi_c,floor_limit_record_id.
  Voor deze synthetische subset expliciet onafhankelijke water- én vloerbegrenzer
  gemodelleerd, met eigen records. Geen claim dat die in de woning aanwezig zijn.
  Ongemengde groepmaximum moet centraal gedeeld maximum zijn; temperatuurgrenzen
  blijven structurele ranges, geen installatieadvies.
- outputs_ready en boiler_ready verplicht false, ook bij valide testmanifest.
  Ontbrekend/null/ongekwalificeerd bewijs wordt nooit door een standaard NC,
  assumed-open of safe-closed ingevuld. Mengklep/homing/kalibratie/0–10V krijgen
  hier géén impliciete support. Geen defaultsafeactie voor elk woningtype.

**Werkelijk nog ontbrekend:** kwalificatie van bestaand sensormodel/producerpad,
echte device-/installatiegegevens en onafhankelijke veiligheidsreview, verdere
profielschemas en actuele feedback-/sampleadmission. Synthetische records leveren
dat niet. De validators voeren geen action uit, ook niet bij geldige records.

## Budget- en foutsemantiek

Voor deze losse test hetzelfde plafond als huidige E32bron:
complete config4096bytes, complete envelope8192bytes,512lexicale nodes inclusief
objectkeys, containerdiepte8, ieder string/key64bytes. Mapping is lokale HA-sidecar,
apart eveneens raw-budgetgevalideerd; niet als tweede NVSblob geïntroduceerd.
Per-kamer én totale schedulelimiet8, finite≤16dagen,128transities uit oude v1
geven geen verruiming. Roomlimits/weekwaarden5..35C; UTC2000..2100, endexclusive.
Geen truncatie/chunking/verkorte horizon/buffer- of partitionverhoging.

Stabiele primaire foutcategorieën in de gedeelde fixtures:
json_format,json_integer,json_duplicate,json_canonical,budget_exceeded,
unsupported_schema,identity,schema,bounds,revision_exhausted,revision_conflict,
config_digest,unsupported_capability,mapping_conflict,reference,
output_owner_conflict,test_layout_limit,qualification,schedule,schedule_budget.
stream_budget en allocation zijn failclosed reserveringen; de begrensde layout
heeft altijd exact7streams. Meer kanalen/topology faalt eerder ref/layout, niet
een onbeproefd flexibel admissionbudget.
Negatieve C++resultaten bevatten een lege kandidaat met outputflagsfalse; Python
werpt een fout en retourneert geen gedeeltelijke configuratie.

## Native geheugenbegroting — geen ESP32proof

Primaire allocation-evidence.json/budget-evidence.json bevatten echte hostmetingen:
GCC12.2 x86_64 -O0, C++ + cJSONhooks, project-pinned cJSON, geen nagemaakte firmware.
Native sizeof: GraphShadowCandidate344B, Transition16B, Context240B,cJSONnode64B.
Twee kandidaatlayouts (oud/nieuw) betekenen688B aan vaste opslag. Exacte
C++/cJSON requested-allocationpeak voor het8transitievoorbeeld:
26973B; callerrawstrings4110B inclNUL, callercontextheap130B en vaste Context240B
worden apart getoond. De kwalificatiemanifest-deepcopy en tijdelijke canonical-
strings/parsebuffers zitten WEL in de gemeten allocatiepeak. C++scope vernietigt
de hele kandidaat/tree bij reject. Geen partiële mutatie van callercontext.

Deze peak telt NIET libcarenas/fragmentatie, OpenSSLinterne malloc, alle firmware-
taken, transportbuffer, actieve v1config, NVSoud/nieuw/readback of native cJSON-
parserstack als volledige highwater. De16B/probeallocatieheader wordt apart
gerapporteerd en is zelf geen firmwareallocator. Alle98fixture-uitkomsten,
inclusief grootste afgewezen input, zijn gemeten; geen bewijs van absolute
worstcase voor elke denkbare input.

Compiler -fstack-usage: validate3520B, parse352B en recursieve treepasses64B per
native frame; main2336B is alleen de testharness. Dit zijn statische hostframes,
NIET call-chainhighwater en beslist geen ESP32loopstackvrijgave.
De bestaande6096Bloopinstelling mag niet met deze losse getallen worden
goedgekeurd. Werkelijke ESP32ABI/heap/stack/latency/NVS/GC/powerlossmeting blijft
een expliciete toekomstige poort vóór integratie/capadvertentie.

## Testen en volgende stap

98 exactgedeelde rawcases:6 volledig SYNTHETISCH,92 negatief; beide echte
validators geven dezelfde expliciete verdicts en positieve revision/mapping/
transition/streamresultaten. Volledige actuele HA-native suite346PASS/1expliciete
broker-opt-inSKIP, inclusief huidige bron-gematchte v1C++runner. Niet optellen.
Geen broker/prod/testHA/E32verbinding of nieuwe dienst nodig.

Bestaande CI bouwt alleen extra finite graph_validation_runner met gcc/g++ en
de al gepinde cJSONdependency; geen nieuw systeemcomponent. Voor lokaal:
gcc -std=c11 -O0 -g -I.pio/libdeps/native/cJSON -c .pio/libdeps/native/cJSON/cJSON.c -o out/graph-cjson.o
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/graph_validation_runner.cpp out/graph-cjson.o -ldl -o out/graph-validation-runner
OPENTHERMOSTAT_GRAPH_VALIDATOR_RUNNER kan hetzelfde bestaande lokale executablepad
selecteren. Geen fake-fallback; ontbreken van runner is testfout, geen SKIP.

Hierna apart: gezamenlijke firmware/HAreview van deze testsubset en ontbrekende
echte profielen, storage-fault/apply/reconnect/readback, admission en mappingjournal;
pas daarna gecontroleerde capabilityadvertentie en GUIapply. Actuatie/ketel/
elektrische aansluiting/TXunlock en fysieke commissioning blijven buiten scope.


## Bronreviewcorrectie r2 — GV-R1/GV-R2 (geen scope-uitbreiding)
GV-R1: channelidentifier wordt getypeerd gevalideerd vóór dictionarylookup.
De zes exacte parentgevallen (array/object op room.sensor_id, actuator.output_channel
en device.feedback_channel met opnieuw berekende synthetische anchor) geven in
beide talen reference, zonder TypeError of gedeeltelijke kandidaat. De eerste92
rawfixtures zijn byte-identiek behouden; totaal98gedeelde cases.

GV-R2: manifestroot, iedere duplicate en iedere AddItemToObject worden expliciet
gecontroleerd. De duplicate blijft RAII-owned tot geslaagde ownershiptransfer.
De bestaande finite test-runner heeft een uitsluitend lokale fault_sweep-testoptie:
alle556daadwerkelijk bereikbare cJSONallocatiesites(0–555) elk precies eenmaal
laten mislukken; zero leaks/zero valid-on-fault, callerinputs/context intact en
succesvol herstel zonder fault. Oude leakposities416/472/500/526 geven allocation.
Dit zijn556faults + controlvalidaties, niet557bewezen allocatiesites.
De ongewijzigde onafhankelijke parentprobe is ook opnieuw uitgevoerd: zero leakrows.

Nieuwe native frames: validate3520B/parse352B/main2336B(testharness). Candidate344B,
transition16B/context240B en positieve requested-allocationpeak26973B blijven gelijk;
grootste geweigerde input31293B. Geen ESP32-/runtimeveiligheidsvrijgave.
Volledige r2native suite346PASS/1broker-opt-inSKIP, inclusief deze regressies.
