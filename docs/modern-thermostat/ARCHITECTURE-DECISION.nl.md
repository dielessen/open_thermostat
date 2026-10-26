> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Architectuurbesluit — één HA↔E32-productketen

**21 oktober 2026 · Mark11950 · specialistadvies, onafhankelijke parentreview volgt.**
Bronanalyse: `407f7097f46f9a3dd6d04aa3f65c2b65d13d557a`.
Dit document wijzigt geen runtime, geeft geen fysieke/releasevrijgave en verklaart
het volledige plan niet voltooid. De eigen fork is autoritatief: geen upstream-sync;
credits, licenties en notices blijven. Mark staat óók volledige frameworkherbouw
toe wanneer die de betere oplossing blijkt; hieronder is de afweging, geen verbod.

## 1. Wat bestaat werkelijk, en wat blokkeert het product?

De huidige bewezen **native testketen** is:

`HA-kamers → expliciet vloer-DATA-apply → C++-opslag/exact readback → aparte SOURCE-selectie → API1-STAGED/readback → twee shadowdoelen`.

Daarvoor bestaan één vloerrecord van **3629 B** en een projectie van **466 B**
met 21/19 °C-doelen. **Niet** twee duurzaam opgeslagen API2-DATA-kamers.
HA bewaart daarnaast de radiatorconfiguratie. Het samengevoegde profiel heet
`graph-floor-native-trv.v1`; SOURCE-factory is standaard `NONE`, fysieke outputs
zijn `false`. Publieke MQTT/reload-, bron- en safetygrenzen zijn testfixtures,
geen gekwalificeerde installatie of werkende fysieke HA/E32-proef.

Concrete blokkades in de huidige code:

- `GraphShadowValidation.h` ondersteunt één vloer/binaire klep; de Storegrens
  is 4096 B, wiregrens 8192 B. Parserlimieten verhogen is geen implementatie.
- `GraphFloorControlStoreView.h`/`graph_floor_bridge.py` vertalen dat record naar
  een ander regelcontract. `ModernTransport.h` kiest DATA óf control; dit maakt
  normaal configureren afhankelijk van een expliciete fase-/factorywissel.
- `ControllerPolicySourceProfile.config_digest` en de SOURCE-review pinnen óók
  de gewenste configuratie. Normale doelen/schema-/mappingwijzigingen kunnen
  daardoor een nieuwe SOURCE-pin verlangen. Die grens zomaar loslaten is onveilig;
  haar blijven omzeilen met projecties is evenmin een goede productarchitectuur.
- De owner-awaitprobe liet een oude STAGED mirror achter ondanks latere weigering.
  Correctie `407f7097` heeft **81 gerichte checks + dezelfde 81 met echte C++/cJSON
  ASan/UBSan**, en de ongewijzigde parentprobe in beide uitvoeringen groen.
  Dit bewijst de correctie, niet dat de tussenarchitectuur de eindoplossing is.

Er is geen gemeten bewijs dat Arduino/HA-frameworkkeuze deze blokkades veroorzaakt.

## 2. Drie routes kritisch vergeleken

| Route | Onderhoud/functiedekking | Complexiteit, migratie en bewijs | Doorlooptijdrisico |
| --- | --- | --- | --- |
| A. Bestaande bruggen verder uitbreiden | Snel nog een proef; voor schema's, gemengde groepen en 8 zones steeds meer uitzonderingen. Geen geloofwaardige eindbasis. | Kleine wijzigingen afzonderlijk, maar stapelende pins/projecties/fasefences; gedrag moeilijker te volgen. | Laag tot volgende deeltest, hoog tot een af product. **Niet aanbevolen als eindroute.** |
| B. Koppellaag gericht vervangen; bestaande native HA/MQTT/Store en regel-/veiligheidskern hergebruiken | Eén gebruikersconfiguratie en expliciet productcontract; alle 31 eisen blijven adresseerbaar. | Middelgrote, afgebakende wijziging met codec-/migratiewerk en echte end-to-endtests. Oude interne klassen/API's mogen verdwijnen. | Drie concrete verticale increments; resource-/profielwerk kan begrenzen. **Aanbevolen.** |
| C. Brede firmware-/frameworkherbouw | Kan structureel schoner worden, maar levert niet vanzelf deviceprofielen, veiligheid of ontbrekende functies. | Hoog: opnieuw netwerk/OTA/bus/timing/opslag/GUI-koppeling integreren en veiligheidsgedrag aantonen. Datamigratie blijft nodig. | Hoog/onbekend; nu geen aangetoond frameworkvoordeel. Alleen kiezen bij een concrete gemeten blokkade die B niet behoorlijk oplost. |

## 3. Aanbevolen architectuur: één plan, drie onderscheiden waarheden

**Kies B.** Stop de brug niet weg achter nog een adapter: vervang haar als
productpad, terwijl ze voorlopig een begrensde regressie-/migratiereferentie blijft.

```text
Native HA-config → review/expliciet apply → één versiecontract/MQTT-owner
                → E32 validate/atomair accepted ControlPlan → bestaande regelkern
                ← exact readback + effectieve status/redenen
```

Houd drie zaken strikt apart:

1. **Gewenste/geaccepteerde configuratie:** zones, groepen, kanalen, doelen en
   begrensde UTC-schema's; immutable revision + digest + mapping. HA beheert
   gewenst, E32 is autoriteit voor geaccepteerd en werkelijk effectief.
2. **Installatie-/bronprofiel:** onafhankelijk geprovisioneerde identiteit,
   apparaatsemantiek, toegestane bindings/limieten, ondersteunde capabilities en
   herstelbeleid. Geen GUI-checkbox of binnenkomend manifest kan dit kwalificeren.
3. **Actuele bevoegdheid/readiness:** verse bron-/feedbackbewijzen, exclusieve
   owner/session/boot/grant/lease en stopvoorwaarden. Nooit uit configuratie,
   ACK, capabilitylabel of opgeslagen profiel afleiden; niet herstellen na boot.

Een normale wijziging binnen een gekwalificeerd profiel krijgt dus een **nieuw
gevalideerd plan**, niet aangepaste SOURCE-code. Bindings/profielwijzigingen buiten
het toegestane bereik vereisen expliciete herkwalificatie. Dit is een **nieuw,
expliciet onderhandeld contract**, geen verzwakking/herinterpretatie van huidige
exacte pins. Oud/onbekend contract weigert zichtbaar; geen stille fallback.

Eén bestaande transport-/Store-eigenaar draagt zowel transactie als controller-
readback. Geen tweede MQTT-worker, scheduler, service of database. Safety heeft
voorrang, ook als interne session-/controllerklassen daarvoor herschreven worden.

## 4. Behouden, vervangen en migreren

- **Behouden als gedrag en bewijs:** TX-/outputlocks, EMS-stop en ketelprioriteit,
  verse bronkwalificatie, leases/monotone deadlines, begrensde naloop, eigenaren,
  auth/CSRF/ACL/redactie, atomair commit/readback en herstel. Hergebruik de huidige
  pure regelaars en foutfixtures; ook bij andere implementatie opnieuw bewijzen.
- **Behouden als productbasis:** native HA-subentries/registries/climate/Recorder,
  stabiele kamer-/entry-ID's, bestaande apparaatdrivers, MQTT, E32-hardware-/OTA-
  basis, bruikbare EMS/metrics/comfortcode. Geen reden nu een nieuw UI-framework,
  brokerdienst, database of tweede regelaar te introduceren.
- **Gericht vervangen:** DATA→API1-projectie als productpad, per-config SOURCE-
  pin/factorywissel en overlappende configuratie-/mirrorrepresentaties. Eén
  begrensd typed `ControlPlan` met gedeelde contractfixtures aan Python/C++-zijde;
  status onderscheidt draft, staged, accepted/readback, conflict én runtime-inhibit.
- **Migratie:** oude records eerst alleen lezen/valideren en als voorstel tonen;
  geen automatisch adopteren/verzenden. Exacte mapping/owner/profielversie meenemen.
  Onderbreking vóór commit behoudt oud; ambigue commit vraagt readback, geen retry
  of terugschrijven. Secrets, ID's, Recorderhistorie en modeldata niet herschrijven.
- **Rollback eerlijk:** behoud oude readers/exports zolang nodig. Oude firmware
  die een nieuw schema niet kent moet veilig weigeren; automatisch hervatten na
  downgraden is niet beloofd. Restore van een compatibele export gaat via dezelfde
  expliciete review en nieuwe sessie, nooit via erase/factory-reset.

De huidige 4096/8192-B-, NVS-, queue- en OTAgrenzen worden niet verruimd om PASS
te halen. Eerst complete twee-kamerpayload, codec, piekallocaties en commit/readback
meten; bij overschrijding representatie gericht verkleinen, niet veiligheidsvelden
of gewenste functies stil schrappen. Acht zones krijgen pas support na eigen bewijs.

## 5. Eerstvolgende verticale oplevering — geen nieuw ontwerptraject

Drie uitvoerbare increments in dezelfde codebase/eigendom:

1. **Contract + opslag:** werkelijk twee kamers (radiator/vloer) in één accepted
   plan, volledige mapping/profielreferenties, compatibele bounded serializer en
   echte Python↔C++-roundtrip. Exacte resourcegrenzen en onbekend-schemaweigering.
2. **Dezelfde owner → controller:** native HA-review/apply → persist → exact
   readback → twee verschillende doelen/schema's/stop, zonder per-wijziging
   compiled SOURCE-pin of DATA/control-factorywissel. Lost ACK, Store-await,
   mapping/owner/profielconflict, retained/stale, reconnect/reboot en powerloss
   behouden config maar herstellen geen grant/override/learning. Outputs blijven
   false; ontbrekende echte producer-/installatiekwalificatie blijft expliciet open.
3. **Productafwerking:** dezelfde native schermen, mobiel/desktop werkelijk
   renderen en bedienen; loading/offline/conflict/annuleren/herladen zonder verlies.
   Daarna normale gezamenlijke HA/E32-build-, migratie- en releasechecks.

**Acceptatie van de eerste softwareketen:** de normale HA-gebruiker configureert
beide kamers en wijzigt één doel/schema; de echte C++-core bewaart hetzelfde plan,
herleest exact en levert geïsoleerde shadowbijdragen. Geen vooraf geladen review
of test-only tweede configbron als productvervanger. Native testtransport blijft
wel onderscheiden van apparaat-/browserbewijs; hier is geen installatie toegestaan.

Dit is middelgroot integratiewerk, niet nog een kleine adapterpatch. De eerdere
6–12 uur betrof alleen een begrensde codec-/contractschatting, **niet** de complete
keten of 31 eisen. Zonder payload-/profieluitkomst is een nieuwe einddatum niet
verantwoord. B heeft een korter herbewijspad dan C; fysieke profielen/72u-soak en
licentiesluiting hebben eigen afhankelijkheden, geen softwaredeadlinebelofte.

## 6. De 31 eisen blijven staan — wat volgt daarna?

| Eisen | Bestaande basis behouden; resterende productacceptatie |
| --- | --- |
| R01–R07, R18 | Verticale kamer-/binding-/schema-integratie; meerdere kranen, echte bron-/bedienings-/actuatorprofielen en gemengde afgifte nog kwalificeren. |
| R08, R15–R16 | EMS/telemetrie/paritywerk behouden; Classic/Plus strikt gescheiden, echte keteldata/stop-/timingbewijs en ontbrekende velden afwerken. |
| R09–R14 | Weather/thermal/coast/curvekern behouden; echte productcaller/coverage/comfortbewijs ontbreekt. Alle 14 F9-kandidaten blijven afgewezen/onvoldoende, geen modelwinst claimen. |
| R17, R25–R27 | Recorder/units/counters/diagnose/CSV/Repairs behouden; actuele ketenbinding, historie-/datavolume-/UI/deviceacceptatie en meet-/schattingslabels afwerken. |
| R19–R24 | Comfort-/context-/seasonal-/supervisorbeleid aansluiten op hetzelfde plan; bronuitval, hydrauliek, minimumflow, vorst/zomer/DHW en stop fysiek én softwarematig bewijzen. |
| R28–R30 | Security/herstel/native GUI behouden; verzorgde echte browserproef, 8-zone/heap/NVS/72u en samengestelde builds/licenties blijven gates. Generic-size heeft een aparte bestaande eigenaar en blokkeert E32-bronwerk niet. |
| R31 | Werkelijke DHW-capabilities presenteren; alleen gekwalificeerde writes/profielen, prioriteit en fabrikantbescherming aantonen. |

**Besluit:** gericht de productkoppeling vervangen is nu de beste route; niet uit
loyaliteit aan oude interne API's, maar omdat de gemeten blokkade daar zit.
Een brede frameworkwissel blijft toegestaan als nieuwe feiten haar beter maken.
Geen functieverlies, upstream-overname, fysieke GO of claim dat losse admission
het complete product oplevert. Canonical PLAN/WORKBOARD integreert uitsluitend de parent.
