# Oorspronkelijke ontvangst — begrensde HA-diagnostiek

25 oktober 2026. Bronbasis voor HA46 / alpha33, samen met de
[verzendcontroles](M2-LAATSTE-VERZENDCONTROLE-20261025.nl.md). Actuele leveringsstand:
[NEXT-RELEASE](NEXT-RELEASE.nl.md). De eerdere passieve controle zag TV02 `waiting`
en een gekozen interne apparaattemperatuur; de oorzaak van ontbrekende
originals of de werkelijke externe producentstart is daarmee niet vastgesteld.

## Waar te vinden na installatie van de volgende bundel

Gebruik de bestaande Home Assistant-actie **Diagnostiek downloaden / Download
diagnostics** bij de integratie. `read_only_original_ingress` bevat de momentopname
van precies de huidige native verbindingseigenaar. Geen extra pagina, API-route,
MQTT-abonnement of uitvoercommando. De bestaande kamer-/firmwareberichten en
frontend blijven ongewijzigd. De getoonde meetstatus verandert niet door lezen.

Een ontbrekende of niet-bijbehorende verbinding geeft `available: false` en
`snapshot: null`; dat betekent niet nul ontvangen berichten. `receiver_initialized`
en `closed` onderscheiden voorbereiding en een gesloten eigenaar.

## Wat de tellers betekenen

Er zijn twee vaste groepen: `temperature` en `tv02`. Ze tellen alleen aanroepen
van de bestaande callback en worker voor geconfigureerde oorspronkelijke
topics. Ze zijn **niet per apparaat** en bewijzen niet hoeveel berichten een
broker of Zigbee-apparaat in totaal heeft verstuurd.

| Veld | Nederlands | English |
| --- | --- | --- |
| `callback` | Aanroepen voor een bekend oorspronkelijk topic | Callbacks for a known original topic |
| `enqueued` | In de bestaande wachtrij geplaatst | Added to the existing queue |
| `dropped_closed` | Verbindingseigenaar al gesloten | Connection owner already closed |
| `dropped_busy` | Eén bericht wacht al, of halve wachtrij gereserveerd | A report is pending or half-queue reservation reached |
| `dropped_retained` | Bewaard brokerbericht geweigerd | Retained broker message rejected |
| `dropped_payload` | Verkeerd payloadtype of te groot | Wrong payload type or oversized |
| `dropped_queue_full` | Wachtrij weigerde plaatsing | Queue refused insertion |
| `dropped_timestamp` | Registratie van ontvangsttijd gaf een exception | Arrival-time capture raised an exception |
| `worker_accepted` | Bestaande ontvanger accepteerde het oorspronkelijke rapport | Existing receiver accepted the original report |
| `worker_rejected` | Bestaande ontvanger wees het rapport af | Existing receiver rejected the report |
| `worker_error` | Bestaande observerafhandeling gaf een exception | Existing observer handling raised an exception |
| `unrouted_callbacks` | Callback zonder bekend oorspronkelijk topic | Callback without a known original topic |
| `configured_topics` | Aantal topics in de bronbinding, geen bewijs van werkend abonnement | Configured topic count, not proof of a working subscription |

Een JSON-/identiteits-/ouderdoms-/epoch-/replayafwijzing valt onder
`worker_rejected`; deze bundel verzint geen fijnere afwijsreden. Een exception
na ontvangeracceptatie, bijvoorbeeld in een listener, kan zowel
`worker_accepted` als `worker_error` verhogen. De bestaande invalidatie blijft
dan gelden. Optellen van alle kolommen levert dus geen aantal unieke berichten.
In-flight berichten kunnen bij sluiten worden opgeruimd zonder workeruitkomst.

## Behoud, begrenzing en betekenis

- Iedere teller stopt bij 2.147.483.647. `saturated` meldt zodra verdere
  waarnemingen niet meer exact konden worden geteld; niets loopt terug naar nul.
- Tellers leven in RAM zolang dezelfde verbindingseigenaar leeft. Disconnect
  vernieuwt geen bewijs en reset ze niet automatisch. Een nieuwe eigenaar na
  herladen/herstarten begint opnieuw. Er is geen opslagschema of NVS-schrijfactie.
- De snapshot is een kopie. Downloaden verandert geen teller, ontvangsttijd,
  bronprofiel, lease, programma, MQTT-publicatie of apparaatinstelling.
- Er worden geen topics, unieke apparaat-/kamer-ID's, payloads, exceptionteksten,
  brokergegevens, berichttijdstempels of grantgegevens bewaard of geëxporteerd.
- Eén wachtend bericht en de bestaande reservering van de halve wachtrij
  blijven gelden. Diagnoseverkeer wordt niet opnieuw geprobeerd.

`worker_accepted` is ontvangstdiagnose: geen geschikte kamerbron,
`command_correlated`, `valve_ready`, fysieke kraan-ACK of regelbevoegdheid.
`control_qualified` blijft false. Ook nul tellers bij nul geconfigureerde topics
bewijzen geen kapotte sensor. Actieve bèta en eerdere updaterherstelvoorwaarden
blijven open.

## Verificatie

De tests gebruiken de echte native HA-worker en de bestaande ontvangers, met
uitsluitend synthetische MQTT-randen. Ze controleren temperatuur én TV02,
replay, retained, wachtrijreservering, timestamp-/workerfouten, privéscheiding,
begrensde tellers, losse snapshots en levensduur. Bewijs en definitieve
suite-uitkomsten: `out/original-ingress-diagnostics-20261025/`. Geen productie-
installatie of fysieke proef uitgevoerd.

**English:** The existing HA diagnostics download gains bounded, nonpersistent
original-ingress counters for temperature and TV02. They distinguish callback
drops from worker acceptance, rejection and errors, without identifiers or raw
payloads. Counts describe the current connection owner, not per-device or
broker-wide traffic. Snapshots do not refresh evidence or authorize control.
Delivery status is tracked separately in NEXT-RELEASE; this source does not grant physical qualification.
