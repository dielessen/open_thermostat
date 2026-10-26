> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# HA ↔ OpenThermostat — contractontwerp v1

Companion bij [masterplan](PLAN.nl.md), ontwerp19oktober2026. **Nog geen vrijgegeven volledige v1-product-API.** Op20oktober is naast de pure bron-/UTC-/sessiekern een echte E32/HA-shadowkoppeling gebouwd: bounded wire/admission, NVSconfigcommit/readback, native HAflow/lifecycle/Store en gedeelde ketentests. Het exacte geïmplementeerde deelprofiel staat in [TEST-WIRE.md](TEST-WIRE.md), met [testgrens/open checks](INTEGRATED-TEST.nl.md). Dat profiel voert geen actuator-/ketelcommands uit en vervangt niet alle onderstaande producttopics. Bestaande legacymeldingen behouden hun eigen betekenis. De onderstaande algemene berichten blijven ontwerpschema's; niet stil als geïmplementeerde productie-API gebruiken.

## 1. Transport en grenzen

- Eén bestaand lokaal MQTT-broker; geen sidecar, losse protocolbridge of eigen scheduler.
- Namespace: `<base>/v1/<richting>/<kanaal>`, met één gecontroleerd baseprefix per controller. Huidige prefixconfiguratie accepteert één topicniveau; behouden/migreren expliciet, niet stilzwijgend veranderen.
- Stabiele `controller_id`, bestaande `zone_id`, stabiele lokale `binding_id` en schema/configrevision. Namen en HA-entity-ID's zijn geen firmware-identiteit.
- Application-level bevestiging en deduplicatie zijn verplicht. QoS vervangt deze niet. De huidige PubSubClient/dependencychain wordt op echte publish/subscribe/QoS/retain-/bufferlimieten gecontroleerd; **geen QoS1/2- of MQTT5-expirygarantie aannemen**. Indien publish alleen QoS0 biedt, werken bounded retry + command-ID + statusreconciliatie ook daarboven. Een librarywissel is een aparte beslissing, niet een verborgen voorwaarde.
- Alleen expliciet toegestane actions van de lokaal opgeslagen HA-binding uitvoeren. Een MQTTbericht kan nooit een willekeurig HA-servicepad, entity of ruwe EMSwrite kiezen.
- Per soort maximumlengte, aantal velden/kanalen, numerieke grenzen, UTF-8/IDregels en parserbudget vastleggen en vóór allocatie controleren. Meetwaarden zijn eindige getallen, geen bool/NaN/Infinity. °C is de wire-unit; intern mag bestaande honderdste-°C-integer blijven na gevalideerde conversie.

## 2. Topics en retainbeleid

`HA→FW` en `FW→HA` zijn de toegestane publicatierichtingen. Iedere client krijgt een minimaal broker-ACL voor zijn kant. Retained status is nooit op zichzelf een warmtevraag.

| Voorgesteld suffix | Richting | Retain | Semantiek |
| --- | --- | --- | --- |
| `fw/availability` | FW→HA | Ja, met LWT | Transportbeschikbaarheid; offline/online bevat bootidentity. Online is niet bewijs van geldige samples of werkende ketel |
| `ha/availability` | HA→FW | Ja, applicatiestatus | Integratieonline/nette unload offline; geen eigen Will via de gedeelde HA-MQTT-client. Firmwarelease blijft beslissend; globale HA-birth/will is hoogstens extra transportindicatie |
| `fw/hello` | FW→HA | Ja of op aanvraag | Firmwareversie, APImajor/minor, capabilities, limits, huidige configrevision, boot-ID en actuele handshakechallenge |
| `ha/open_session` | HA→FW | Nee | Owner-admission voor huidige boot/challenge, capabilities en teruggelezen revision |
| `fw/session` | FW→HA | Nee | Toegekende adaptersessie/epoch, geldigheidsvoorwaarden en leases; oude sessie ongeldig |
| `ha/heartbeat` | HA→FW | Nee | Adapterlevendigheid; geen verversen van ontbrekende sensorobservaties |
| `ha/config` | HA→FW | Nee | Gevalideerde prepare/commit/aborttransactie met expectedrevision; config niet door retained replay activeren |
| `fw/config_result` | FW→HA | Nee | Accepted/rejected/conflict + toegepaste revision/digest; snapshot van acceptedconfig op aanvraag |
| `ha/observations/<binding_id>` | HA→FW | Nee | Meting, bronavailability, echte sample-age en observerkwaliteit |
| `ha/user_command` | HA→FW | Nee | Setpoint/mode/override vanuit geautoriseerde HA-/lokale bediening |
| `fw/user_command_result` | FW→HA | Nee | Validatie/applicatie met request-ID en nieuwe effectieve revision; toegepast doel daarna in zone-state |
| `fw/actuator_command/<binding_id>` | FW→HA | Nee | Gewenste genormaliseerde toestand binnen huidig profiel en lease |
| `ha/actuator_result/<binding_id>` | HA→FW | Nee | Afzonderlijke accepted/device-reported/assumed/confirmed/failureinformatie |
| `fw/state/zones` | FW→HA | Nee; snapshot herhaalbaar | Volledige huidige zone-state met revision, boot/sequence, age/quality; geen actuatorcommand |
| `fw/state/boiler` | FW→HA | Nee; snapshot herhaalbaar | Vraag én afzonderlijke echte ketelmetingen met bronmetadata |
| `fw/state/diagnostics` | FW→HA | Nee | Redenen/resources/kwaliteit, rate-limited, geen secrets |
| `ha/snapshot_request` | HA→FW | Nee | Huidige config/state opvragen; uitlezen heeft geen energie-/actuatiebijwerking |

Na reconnect vraagt de integratie actuele snapshots op. Oude retained hellos/availability kunnen de UI helpen een device te vinden, maar maken geen sessie geldig. Geen QoSsessie met onbeperkte oude actuatoropdrachten laten vollopen.

## 3. Boot, sessie en onafhankelijke geldigheid

1. Bij iedere firmwareboot ontstaat een nieuwe `boot_id`. Bij elke transportherverbinding komt een nieuwe handshakechallenge/verbindingsepoch. Opstart/reconnect trekt actuator- en bronreadiness in; oude pending commands worden weggegooid.
2. De integratie bewijst vers contact door de actuele challenge te beantwoorden. Firmware antwoordt voor die aanmelding met een nieuwe `adapter_session_id`/epoch. Alleen één geconfigureerde adapter mag eigenaar zijn. Een tweede HA-instantie kan niet zomaar een actieve owner verdringen; herconfiguratie/expliciete takeover is zichtbaar en wordt geauthenticeerd.
3. Ieder control-/samplebericht noemt controller, boot, epoch, session, configrevision, binding en sequence. Verkeerde/ontbrekende waarden worden geweigerd; een retained oud bericht heeft nooit de huidige toelating.
4. De transportlease houdt alleen het **adapterpad** levend. Iedere sensor heeft daarnaast een eigen sample-age/quality; iedere actuator zijn eigen readiness-/commanddeadline. Een gezond HAheartbeat kan geen kapotte sensor of verdwenen kraan vers maken.
5. Een doorlopende TCPverbinding kan alsnog vertraagde/gebufferde data leveren. Een nieuwe monotonesequence alleen is niet genoeg: observation-age en leveringsvertraging tellen mee. **Iedere ontvanger**, dus zowel de E32 voor inputs als HA voor actuatoropdrachten, accepteert alleen binnen een ontvangerbekend, niet door ontvangst verlengd monotone geldigheidsvenster. F2 kiest één eenvoudige symmetrische oplossing: aantoonbaar bounded clockmapping óf wederzijdse korte grants/challenges voor begrensde batches. Geen extra challenge per meetsample nodig. Een uitsluitend firmware-issued challenge bewijst geen verse FW→HA-opdracht.
6. Iedere ontvanger bepaalt de toelating op zijn eigen monotone klok. Waar een betrouwbaar UTCtijdstip bestaat: afwijzen bij te oud, te ver in toekomst of onacceptabele skew. Als dat niet aantoonbaar betrouwbaar is: de gekozen grant-/age-route, of geen nieuwe positieve actuatie. Het simpelweg opnieuw aankomen van een oud bericht start nooit een nieuwe volledige TTL. Adapterlease, samplegeldigheid en commandfreshness zijn afzonderlijke voorwaarden.

`boot/session/challenge` voorkomt replay en volgordefouten, **geen ongeauthenticeerde aanvaller**. Auth en topic-ACL blijven nodig. Een digest bewijst coherentie van config, niet wie hem heeft gestuurd.

## 4. Freshness: een constante temperatuur kan wel vers zijn

Firmware heeft twee tijden: lokaal ontvangen en werkelijk geobserveerd, plus de leeftijd die bij ontvangst al bestond. De integratie houdt daarnaast bronbereikbaarheid/laatste echte rapportage bij. Toestandswijziging is niet hetzelfde als een nieuwe meting.

- `last_changed` is geen sensorheartbeat. Een kamer kan 20,0 °C blijven terwijl de thermometer keurig rapporteert.
- `last_updated` of `last_reported` van een HA-state bewijst niet zonder meer een nieuwe **fysieke** sample. Gebruik waar mogelijk apparaattimestamp, `last_seen`/availability of een gedocumenteerde device-/integratiereportgarantie.
- Een `state_changed`listener ziet mogelijk geen ongewijzigde report. Gebruik de ondersteunde HA-API voor de gepinde versie waar nodig; geen private globale eventtap zonder doelbinding of nep-samples met iedere integratietimer.
- Een bestaand device met alleen state-on-change kan een constant level niet eeuwig levend bewijzen. Kies een aantoonbare native availability/reportbron, configureer een ondersteund maximumreportinterval of label deze bron met beperktere zekerheid; verleng niet stilzwijgend actualiteit.
- Een HAherstart/RestoreEntity/retained MQTTwaarde krijgt `restored/unverified`; pas nieuwe bronvalidatie maakt de meting bruikbaar. Een kunstmatige reread uit HA's statecache is niet die validatie.
- Sensorfreshnessbeleid is per model/bron en doel: kamer, buiten, batterij, klepfeedback en ketelveld hebben verschillende normale cadans. Stale temperatuur beëindigt normale zonevraag volgens masterplan; oude batterijwaarde hoeft niet dezelfde reactie te geven.

### Illustratief observationbericht

De velden illustreren de betekenis; waarden zijn verzonnen en geen livebewijs.

```json
{
  "api": 1,
  "controller_id": "e32-lab",
  "boot_id": "boot-7",
  "epoch": "link-4",
  "adapter_session_id": "ha-3",
  "challenge_id": "fresh-19",
  "config_revision": 12,
  "zone_id": "a1b2c3d4",
  "binding_id": "room-sensor-1",
  "sequence": 43,
  "temperature_c": 20.3,
  "source_available": true,
  "source_sample_age_ms": 2400,
  "freshness_evidence": "device_report",
  "quality": "valid"
}
```

Een maxleeftijd komt uit geaccepteerde profielconfiguratie, niet uit een willekeurig inkomend bericht. Eventueel langere werkelijke transportvertraging wordt aanvullend afgetrokken/bewaakt; bovenstaande age alleen is geen volledige netwerkvertrouwensgarantie.

## 5. Commands, bevestiging en feedback

- Iedere mutatie: uniek `command_id`, origin, doelrevisie, huidige sessie/epoch, bounded deadline en gevalideerde waarde.
- Firmware en HA onthouden een begrensde recente dedupcache per epoch. Duplicaat retourneert dezelfde uitkomst, start geen nieuwe boost/dutycycle en verlengt geen override.
- Daarnaast bewaren beide ontvangers per binding/berichtstroom de high-water sequence voor de hele actieve epoch. Een oud command waarvan het resultaat al uit de cache verdwenen is wordt stale/rejected, niet opnieuw toegepast. Command-ID/sequence binden aan een onveranderlijke payload; een gewijzigde payload onder dezelfde ID is een fout.
- Een HA-gebruikerscommand heeft `override_until`/beleid of begrensde relatieve duur; runtime deadline wordt eenmaal vastgelegd. Bij reset zonder betrouwbare wandklok geen oude boost opnieuw beginnen.
- Een actuatorcommand beschrijft een **genormaliseerde capability** (`valve_position`, `room_setpoint`, `binary_open` of `external_temperature`) en nooit een willekeurige servicecall. Het profile vertaalt dat lokaal naar toegestane entity/actions. Geen `target=all`.
- Verschillende eigenschappen van één TRV (doel, externe temperatuur, stand) krijgen consistente profielsynchronisatie. Niet toevallig de lokale regelmodus veranderen door actionvolgorde.
- Statusniveaus zijn expliciet: `rejected`, `ha_action_accepted`, `device_reported`, `travel_time_assumed`, `physically_confirmed`, `failed`, `expired`. Waar echte eindstand ontbreekt blijft dat zo.
- Per fysiek apparaat/profiel één geserialiseerde uitvoerder, geen overlappende conflicterende actions. Feedback heeft commandcorrelatie, observatieleeftijd en zekerheid. Oude callbacks/pre-command statecache/HVAC_ACTION leveren geen nieuwe open-readiness. Waar causaliteit ontbreekt blijft het hoogstens `travel_time_assumed` volgens het geaccepteerde installatieprofiel.
- De supervisor gebruikt alleen het readinessniveau dat voor die installatie is geaccepteerd. Tijdelijk aangenomen openstand is geen onafhankelijk bewijs van flow. Minimumflow moet daarnaast fysiek veilig zijn.
- Bij timeout: fout + bekende veilige toestand/stopbeleid, geen oneindige retries. Stop-/faultcommands niet achter een lange setpointqueue; oudste superseded commands vervallen.
- Een al verstuurde deviceactie kan niet altijd geannuleerd worden en kan na stop/leaseverlies nog voltooien. Houd ketelvraag geremd, reconcilieer echte device-state en voer waar bereikbaar de nieuwste veilige intent uit. Een geannuleerde coroutine is geen bewijs dat een fysieke oude openactie weg is.
- Deviceactiontimeout heeft een begrensde wachttijd en wordt native in HA afgehandeld. Uitval van HA kan niet worden opgelost door een command naar datzelfde HA te blijven sturen.

## 6. Configuratie en schema

Transactionele volgorde: HA stage/persisteert de immutable **bindingmapping én firmwareconfig** met transaction-ID/revisie/digest → `prepare` met verwachte huidige revisie → valideer hele nieuwe configuratie → `prepared` met digest → expliciete `commit` → atomair opslag/activatie → `applied` + state. Kleine configuratie kan één atomaire set/ack zijn als dat aantoonbaar dezelfde garanties geeft; geen onnodige meerfasenlaag bouwen.

Verificatie omvat ID-uniciteit, ontbrekende/verwijderde zones, capabilities, toegestane grenzen, wijzigingen aan actieve hydraulische groepen, schema/timezone en bekende geheugen-/payloadlimits. De oude configuratie blijft actief tot succesvolle commit. Een afgewezen wijziging schakelt de productie niet gedeeltelijk om. Onderbreking vóór commit houdt oud actief; tijdens/na de atomaire commit is oud óf volledig nieuw mogelijk, nooit half. Bij verloren applied-ACK vraagt HA eerst readback; firmware kan nieuw al duurzaam toegepast hebben.

Na commit, reboot of herstelde backup moeten HA-bindingmapping en firmware exact dezelfde revision/digest hebben vóór actuatorwrites/bronreadiness vrijgegeven worden. Een binding hergebruikt voor een ander profiel draagt geen oude pending opdrachten over. Dit is staging/readback met immutable revisies, geen eigen distributed database of consensusdienst.

Entiteitsbindingen blijven in HA; firmwareexport bevat alleen genormaliseerde kanalen. Ontbrekende HAregistrybinding geeft een herstelbare Repairs-melding en geen vervanging door de eerste entity met dezelfde naam.

Schema heeft bronversie, tijdzone, effectieve overgangen/basisdoel en geldigheidsomvang. Ondersteunde weekrepresentatie moet toekomstige targets voor optimum-start bevatten. Bij gebruik van een vooruitgecompileerde beperkte horizon: expliciete `valid_until` en vooraf gekozen afloopgedrag, geen oneindige autonomie claimen. Voorkeur is een volledig lokaal uitvoerbaar weekschema met gecontroleerde tijdzoneregels. Dit is een F2-API-/tijdrepresentatiekeuze, geen twee gelijktijdige schedulers.

Een verandering in HAhelperdata op een aangrenzend `on`-blok telt mee, ook zonder on/offedge. Override heeft zichtbare prioriteit/afloop; schemawijziging maakt niet stilzwijgend ieder handmatig doel ongedaan.

## 7. Ketel- en zonestatus

Minimale zonestatus:

- werkelijk en effectief doel; schema-/overridebron en afloop;
- geldig/onbekend/stale, gekozen sensor en leeftijd;
- zonevraag, gewenst afgifteniveau, actuatorterugmelding en readinesszekerheid;
- supervisorstatus en reden van vraag/remming;
- curve-/waterbijdrage, modelstatus/vertrouwen, voorgesteld/toegepast voorverwarmmoment;
- config-/modelrevision, sample-/eventsequence.

Minimale ketelstatus:

- `requested_flow_temperature` en `heat_request_active` uit de regelaar;
- `reported_selected_flow_temperature`, `measured_flow_temperature`, `measured_return_temperature` en `reported_burner_modulation` afzonderlijk waar de ketel ze werkelijk levert;
- afzonderlijke velden voor `heating_active`, `dhw_active`, `burner_active`, `pump_active`, elk met eigen bron/quality, niet zomaar uit één boolean afgeleid; gescheiden velden zijn niet automatisch onafhankelijke fysieke metingen;
- brontelegram/adres, sampleleeftijd, capability en eventuele bekende onbetrouwbaarheid;
- counters met betekenis/unit/resetepoch; schattingen met methode/versie en expliciete naam;
- bus-/transportdiagnostiek en beschikbaarheid los van request.

Bij conflicterende toestand wordt geen vlam verzonnen. Een gevraagde 45 °C en gerapporteerde 0 °C kan op Marks adapterketen voorkomen; toon beide met uitleg, niet automatisch "ketel staat uit". Een onbekend CV/DHWinterval krijgt geen gefingeerde energietoewijzing.

Als raw `burner_active` niet betrouwbaar is blijft het unreliable/unavailable. Een aparte uit modulatie/code afgeleide branderindicatie en bijbehorende starts/looptijd krijgen `inferred`, methodeversie en datagaten; geen claim van onafhankelijke vlamdetectie.

## 8. Versie/migratie en beveiliging

Major protocolverschil: read-only/geen nieuwe actuatie; bruikbare diagnostiek, herconfiguratiekeuze. Minor uitbreiding: onbekende optionele fields negeren, required capabilities expliciet onderhandelen. Huidige JSONtemperaturen in honderdsten blijven legacy; v1 gebruikt ondubbelzinnige unitnamen. Geen implicit×100 in de adapter zonder contract.

Huidige HAunique-ID's en permanente kamer-ID's worden gemigreerd, niet gereset. Aparte device versus entity registry: fysieke TRV blijft haar echte device; logische zone is OpenThermostatdevice/area. Verwijdering/uitzetten integratie stopt eigen listeners/actions en trekt eigenaarschap/readiness in; een reload is geen nieuwe persistent override.

Legacy Discovery naast custom integratie: expliciete keuze, alleen eigen exact geïdentificeerde retained Discoveryconfig opruimen na export/readback, nooit wildcard alle mqttentities verwijderen. Beide oude en nieuwe commandroutes mogen nooit ongecontroleerd dezelfde zone aansturen.

## 9. Verplichte contractscenario's

Deze checks zijn implementatieacceptatie, nog niet uitgevoerd:

1. Verse gelijke temperatuurreports blijven bruikbaar; stilgevallen source met gezonde heartbeat verloopt.
2. Retained gemeten waarde bij HAboot wordt geen nieuwe fysieke sample.
3. Oud command vóór/na HA-, broker- en firmwareherstart wordt niet uitgevoerd.
4. Duplicaat na een verloren ack verandert niets en verlengt de originele deadline niet.
5. Out-of-order feedback voor vorig setpoint overschrijft de nieuwste opdracht niet.
6. Device rondt anders af; eenmaal juiste genormaliseerde state, geen feedbacklus.
7. Echte fysieke handmatige wijziging na een softwarecommand wordt wel geaccepteerd.
8. Verkeerde controller/zone/binding/configrevision/major versie geeft expliciete rejection, geen fallback naar naam.
9. Powerloss vóór commit houdt oud; tijdens/na commit oud óf volledig nieuw, nooit half. Verloren applied-ACK wordt via readback gereconcilieerd; mismatch met HA-bindingmapping blokkeert writes/readiness.
10. HAserviceaccepted maar deviceoffline geeft geen physicallyconfirmed/open status.
11. Leaseverloop op E32 beëindigt afhankelijk normale vraag, ook bij een nog verbonden TCPsocket.
12. Wandklok achteruit/vooruit, DST en tijdloosboot beïnvloeden monotone lease/stopdeadline niet.
13. Bron °F→°C, ontbrekend, bool/NaN, outlier en herstelde waarde correct behandeld.
14. Veel zones/payloads/events vullen queues niet onbeperkt; fout/stop krijgt voorrang.
15. Telemetrie uitlezen, herhalen of snapshots opvragen verhoogt/verlaagt energietotalen niet.
16. Retained online + uitgevallen firmware wordt na timeout als offline/degraded behandeld; geen infiniteonline.
17. Tweede HAinstantie/oude backup kan niet een actieve owner/config stilzwijgend overnemen.
18. Unauthorized brokerclient/verboden binding kan geen klep-, configuratie-, OTA- of EMSactie uitvoeren.
19. Scheduleblock blijft on maar wijzigt `temperature`: nieuwe overgang precies eenmaal.
20. HAuitval tijdens naloop kan draadloze kleppen niet alsnog commanderen: onafhankelijke hydraulische terugval aantoonbaar, anders geen productie-GO.
21. Zeer oud duplicaat na dedupcache-eviction wordt door high-water sequence afgewezen; dezelfde ID met andere payload wordt rejected.
22. Vertraagde FW→HA-openactie in huidige sessie wordt aan de HA-ontvangstgrens geweigerd; geen verse TTL vanaf ontvangst.
23. Oude, niet-annuleerbare deviceopenactie voltooit ná stop/leaseverlies: geen nieuwe ketelvraag, veilig reconciliëren en laatst geldige veilige intent waar uitvoerbaar.

De definitieve schemas en timer-/capaciteitswaarden worden met de geselecteerde hardware en libraryversies vastgelegd in F2; ongeteste conceptwaarden worden niet als bestaande fail-safe verkocht.
