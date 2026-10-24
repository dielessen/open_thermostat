# OpenThermostat — actuele overdracht

Bijgewerkt 24 oktober 2026 na geleverde alpha23/dev29 en de publicatiemetadatareparatie.

1. Lees [WORKBOARD](WORKBOARD.nl.md): de enige actuele afvinklijst met alle 31
   eisen, 11 fasen, 8 werkpakketten en B01–B14-releasechecklist.
2. [PLAN](PLAN.nl.md) bewaart het ontwerp en alle oorspronkelijke acceptatie.
3. [Release-inventaris](BETA1-RELEASE-INVENTARIS.json): 23 voorbereide onderdelen,
   200 bronverwijzingen met hashes. Alles blijft in de eerste bètabasis, ook
   begrensde code die nog niet als complete productfunctie is aangesloten.

## Actuele bron en installatie

**Geïnstalleerd en onafhankelijk gecontroleerd:** E32 alpha23 + HA dev29, beide
bron `5f31dd780a5b98d81048f9d592f8209e657d7305`. Publicatiebeheer/capaciteitscorrectie
staat aanvullend op `aaeba7d`; dit verandert de geïnstalleerde firmwarebytes niet.
Bewijs: `out/next-release-20261024/LIVE-INDEPENDENT-REVIEW.json`.

De gezamenlijke batch levert systeemlog/optionele syslog, incrementeel dashboard
en oorspronkelijke TV02-ontvangst/lifecycle plus NL/EN-weergave. De module draait
na één normale app-only HTTPS-update; HA is via de bestaande specialist met een
verse scoped back-up en één Core-herstart geplaatst. Alle 80 HA-bestanden en de
running-ELF/web/source-hashes komen overeen met de openbare onveranderlijke tag.

Systeemlog is echt uitgelezen: 32 RAM-regels, beschermde GET-routes HTTP 200, niveaus/
filter/pauze/download en native Arduino/IDF-capture. Syslog staat uit zonder
bestemming. Collector-/lange heap-/stackproeven blijven open: zie LOGGING.nl.md.

De normale updater kon de 33.010-byte release-API niet in zijn buffer van 32.768 bytes
opnemen. Alleen de dubbele samenvatting is verwijderd; alle volledige originele
notities/tags/assets behouden. Actuele API: 30.621 bytes. Nieuwe publicaties krijgen
begrensde versienotities plus onveranderlijke bronlink en kop-/UTF-8-controle.
Zes regressies plus volledige CI van de publicatiecorrectie groen. Een gewone
releasecontrole op alpha23 zelf is ook PASS (alpha23/alpha21, checked, geen fout).
De oorspronkelijke +6h/+24h-jobs zijn met behoud van IDs/tijden/overige velden via
de bestaande native root-/admin-eigenaarsroute van de actuele basis voorzien;
de HA-specialist had daarvoor onvoldoende sessiescope. Geen nieuwe planning.

SOURCE was bij nacontrole revisie4/digest `78012d7e…`, HA/E32 gelijk, vers/ready,
zonder staged restant. Week/bindings/credentials/105 registryrecords en HRC22H-
model behouden. Dit is geen permanente revisiefence: lees voor een volgende
mutatie steeds de verse geaccepteerde staat en reconcilieer normale UTC-horizon.

Laatste meetmoment: 27 native ketelvelden beschikbaar, 25 reported + 2 inferred,
nul vergelijkingsverschillen; 20 unsupported/invalid/stale unavailable en 22
onbetrouwbare velden uitgeschakeld. Beschikbaarheid blijft momentafhankelijk en
modelkeuze begrenst de ontvangst nooit.

**Eerstvolgende uitvoering:** B04/B05, echte bronpins/extension/ontvangst en
fysieke kraanproef zonder ketel. De HA-ontvangers en frontend zijn nu geïnstalleerd;
de Z2M-producent/pins en causale ACK/readiness zijn nog niet gekwalificeerd.
Diagnostische motion-device-temperature wordt geen ambient meting. Daarna de
complete hydraulische/zend-/start-stopketen. TX en alle fysieke uitgangen blijven
false; actieve bèta-GO blijft NOT_READY. Oude checkpoints hieronder zijn historie.

## Historisch checkpoint: poll-executor

Controller/status en beveiligde HTTP/webbediening blijven behouden. De echte
E32-pollroute is nu aangesloten op een gedeelde executor met hercontrole vlak
voor IO, uitsluiting van de legacyqueue tijdens proefbezit en intrekking bij
reset/RX-overloop/decodefout. 66 native ASan/UBSan-gevallen slagen, waaronder
9 pollgevallen. Eerdere HTTP/web-browserbewijzen blijven geldig voor ongewijzigde
webassets; deze bronstap is geen nieuwe fysieke proef.
De default E32 blijft TX-geblokkeerd, zonder beoordeeld proefprofiel/adressering. De later voorbereide Classic-encoder staat hieronder.
De poll-executor is geen kwalificatie van elektrische timing of daadwerkelijke
ketelstop. B04–B09 blijven open voor de beschreven eindacceptatie.
Geen nieuwe release/installatie/fysieke opdracht. Bewijs in
`out/beta-boiler-evidence-20261023/poll/REVIEW.json`.

## Historisch checkpoint: nieuwe ha-runtimebron

`set_report_profile` trekt de vorige kwalificatie bij vervanging direct lokaal in
en retourneert een scoped opruimcallback. Oude callbacks/timers/observerresultaten
kunnen een nieuwe eigenaar of nieuw rapport niet raken. Replay-watermerken blijven
staan; registratie/cleanup maakt nooit een vers sample. Oude bron reproduceert de
fout, 31 gerichte HA-tests en de volledige suite (1.637 tests + 68 subtests) PASS,
geen skips. Alle 8 C++-peers zijn opnieuw gebouwd en de tijdelijke MQTT-broker is
na de proef opgeruimd. Geen firmwarecode/webassets veranderd sinds `0b3aabc`;
het eerdere drie-boardbewijs hoort bij dat firmwarecheckpoint, niet bij een nieuwe
gezamenlijke bevroren release. Geen installatie of fysieke opdracht.
Bewijs: `out/beta-boiler-evidence-20261023/source-lifecycle/REVIEW.json`.
B04 is nog open voor de modelspecifieke productiebron; geen profile_missing-omweg.

## Historisch checkpoint: nieuwe classic-encoderbron

Vast UBASetPoints 0x1A/offset0/één flowbyte + checksum, nul als aparte expliciete
intentie. `ClassicBoilerTestEncoder` is aan de echte pollcallback gekoppeld, maar
onbeoordeelde/ontbrekende adres-/maskerkeuze weigert alle frames. Geen runtimevlag
of HTTP-invoer vult de adresstructuur. De board-TX-lock, ontbrekende installatie-
en hydraulische kwalificatie zijn behouden. 72 unieke native ASan/UBSan-gevallen
PASS, waaronder 6 nieuwe encodergevallen met gouden bytes, corruptie en finale
poll/deadlinecontrole. Beoordeeld ketenprofiel, bronadres/masker, fysieke UART-
voltooiing/timing/arbitrage en onafhankelijke stop/flow blijven open. Er is geen
live of fysieke opdracht uitgevoerd. HA-bron is sinds `6503299` ongewijzigd;
het HA-regressiebewijs met 1705 checks blijft aan dat checkpoint gekoppeld.
Bewijs: `out/beta-boiler-evidence-20261023/classic-encoder/REVIEW.json`.

## Historisch checkpoint: nieuwe tv02-moduscontrole

Native kraancontrole/room-editor melden TV02 auto/vakantie/uit/onbekend zonder
configuratie- of serviceactie. De voorbereide profiel-C-adapter weigert conflicten
vóór een doelactie, ook bij wachten op de eigenaar, veranderde modus in de laatste
autorisatiecallback of gewijzigde modelclassificatie. Geen automatische preset- of
modusreparatie. Een passende gemelde modus is geen verse kraanecho/fysieke readiness;
default actuation blijft uit. Andere modellen erven deze regels niet uit een naam.
64 gerichte HA-tests, volledige 1658 tests + 68 subtests, 6 nieuwe en 8 bestaande
browserprofielen PASS. Acht C++-peers opnieuw gebouwd; tijdelijke broker verwijderd.
Firmwarecode is sinds `d4eadea` ongewijzigd, dus geen nieuwe drie-board- of gezamenlijke
freezeclaim. Bewijs: `out/beta-boiler-evidence-20261023/tv02-mode/REVIEW.json`.
B04/B05 blijven open voor de echte modelspecifieke bron-/echo-/readinessroute.
Geen installatie, fysieke bediening of wijziging van bestaande apparaatkoppelingen.

## Historisch checkpoint: nieuwe actuatorbinding

De adapter bewaart de exacte native registry-/apparaatidentiteit en controleert
na de laatste autorisatie opnieuw identiteit en doelcapaciteit. Een vervanger met
dezelfde entity-ID, gewijzigde eenheid/grens of onbeschikbaarheid ontvangt geen
opdracht met oude autorisatie. Een andere weergavenaam blijft toegestaan.
Tien nieuwe regressies: negen fouten op de vorige bron, alle tien PASS na herstel;
74 gerichte HA-tests en volledige 1.736 checks (1.668 tests + 68 subtests) PASS,
nul fouten/overslagen. Zeven pakkettests PASS, tijdelijke broker onafhankelijk
afwezig bevestigd. Cumulatieve releasenotes staan in BETA1-RELEASE-NOTES-DRAFT.nl.md.
Standaardactuatie blijft uit; geen fysieke echo of
readiness afgeleid. Bewijs in `out/beta-boiler-evidence-20261023/actuator-dispatch/REVIEW.json`.

## Herbevestigde productiebronbeperking

Nieuw read-only HA-onderzoek bevestigt de geselecteerde diagnostische RTCGQ11LM-
bron en TV02 in auto; oorspronkelijk property-acquisitiebewijs en gecorreleerde
kraanecho zijn niet aangetoond. Primaire Z2M-bron traceert de ontbrekende grens
vóór cachemerge; een state-update zelf onderscheidt nog geen rapport/read/optimistic
write. Werk de modelspecifieke producer op die grens uit, zonder HA-last_reported
als acquisitietijd te gebruiken. Latere native bridge/info-controle
meldt converters 26.115.1 / Z2M 2.14.2 / herdsman 10.10.0; dat is expliciete
broker-metadata, geen directe packagebron-/hashcontrole. Bewijs in het actuator-dispatch-dossier:
HA-SOURCE-READONLY.json en PRODUCER-SOURCE-TRACE.json. Geen live wijzigingen.

## Nieuwe gedeelde UART-voltooiingscontrole

Hoofd-UART en forwarder controleren nu byteacceptatie, idle bij nul-tick SDK-probe,
BREAK-invoer en normale polariteitsherstelling via dezelfde zendschakel. Null/lege/
te grote invoer blijft zonder SDK-call; vectorlengte wordt niet naar uint8 afgekapt.
80 native ASan/UBSan-gevallen PASS, waarvan acht nieuwe UART-gevallen. De bestaande
HT3-pacing is behouden; dit kwalificeert geen Classic-golfvorm, arbitrage, totale
looptijd of fysieke stop. SDK-write kan intern nog blokkeren. Default E32-TX blijft
uit en er is niets geïnstalleerd. Bewijs in uart-completion/REVIEW.json onder het
bètabewijsdossier. Geen nieuwe HA- of browserassets voor deze bronstap.

## Nieuwe versieprojectie in HA-apparaatcontrole

Metadata behoudt nu expliciet gemelde converter-/herdsmanversies uit hetzelfde
begrensde bridge/info-abonnement. De kamereditor toont Z2M en converterpakket
in NL/EN; ontbrekende/lege/onjuiste versies blijven onbekend. Geen benchpin als
fallback, geen extra client of instelling, geen fysieke kwalificatie.
Twaalf nieuwe native gevallen, volledige 1.748 HA-checks (1.680 tests + 68
subtests, nul fouten/overslagen) en twintig browserprofielen PASS. Een gerichte
read-only HA-specialistproef heeft converters 26.115.1 uit bridge/info bevestigd;
unsubscribe en sluiting eigen WS uitgevoerd. Zie bridge-versions/REVIEW.json in
het bètabewijsdossier. Originele meetrapporten/echo blijven open.

## Nieuwe native identiteit van meetrapportprofielen

Native sensor-/apparaatbinding wordt bij registratie vastgelegd en vóór/na de
observercallback en vóór pending transport opnieuw gecontroleerd. Native model- of
apparaatwissel/uitschakelen trekt de oude kwalificatie en registratie in; lezen
meldt onmiddellijk onbruikbaar. Dezelfde rij hernoemen en displaylabels behouden
identiteit zonder nieuwe sampleleeftijd. De gedeelde private identityfunctie wordt
ook door de actuator gebruikt. Tien nieuwe regressies (acht fouten op de vorige
bron), 116 gerichte HA-tests inclusief comfort/context PASS. De bestaande
synthetische comfort-fixture registreert ook een native rapportprofieleigenaar;
de productiecontrole is niet versoepeld. Volledige 1.758 HA-checks PASS (1.690
tests + 68 subtests), nul fouten/overslagen. Tijdelijke brokers verwijderd.
B04-productieproducer/fysieke bron blijven open;
geen nieuwe firmware-/webassets of fysieke actie. Zie report-binding/REVIEW.json.

## Eerstvolgende uitvoering

Volg B04–B09 uit het werkbord: modelspecifieke productie-meetrapportproducent,
passende native kraanroute, bestaande supervisor aansluiten en eindige expliciete
ketelproef met vaste deadline/stopprioriteit/verse terugmelding. Classic-commandopad
en elektrische TX-/stopvoorwaarden apart beoordelen. De bestaande bronbench mag
niet op SOURCE worden gestart. Een kamer-save/metadata/HA-last_reported kwalificeert
geen fysieke meting. Huidige RTCGQ11LM-bron is diagnostische device_temperature;
alternatieve WSDCGQ11LM was laatst unavailable. Geen defect of sensorwissel verzinnen.

Geen nieuwe F9/F10/P2-stage vóór M2. Bestaande models/comfort-/vloer-/CSVcode
blijft behouden; niet opnieuw als ongeprogrammeerd opvoeren. Geen algemene TX-vlag
of Plus-commandoknop inzetten als Classic-proef. Pas na één bevroren complete
kandidaat volledige checks, publicatie en één gecoördineerde installatie.

## Werkafspraken en bewijs

HA-updates altijd via bestaande bevoegde HA-agent, met back-up en nacontrole.
Vragen voor later; onafhankelijk werk gaat door. Instellingen/programma/identiteit
behouden. Geen claim van onbeheerde verwarming, acht zones of leerwinst zonder
passende acceptatie. Geen eigen watcher/scheduler.

- Actuele passieve release: `out/prepared-rollout-20261023/FINAL-REVIEW.json`.
- Vorige alpha17/dev23: `out/combined-release-evidence-20261023/FINAL-REVIEW.json`.
- Nieuwe ontvangstbasis: `out/beta-boiler-evidence-20261023/CHECKPOINT.json`.
- Herijking: `out/plan-audit-20261023/AUDIT.json`.
- Oude overdracht en alle historische receipts blijven ongewijzigd bewaard als
  `out/plan-audit-20261023/VS-CODE-OVERDRACHT.nl.md.before`; niet als huidige
  installatie-/opdrachtstatus lezen. Oude vragen niet opnieuw als vereiste stellen.

## Adapteridentiteit ontvangen

Bosch EasyControl Adapter **8737908035 V2.3**; volledig etiket en officiële
protocolreferentie staan in WORKBOARD onder “Bevestigde ketencomponent”. De
modelvraag is beantwoord. B09 blijft open voor werkelijke TX-interface,
telegrammen/terugmelding, hydrauliek en onafhankelijk stopgedrag.

## Uitrol alpha18/dev24 gecontroleerd

Volledige CI/pakketcontrole PASS; normale E32-OTA met zeven behouden
configuratieparen; HA-agentinstallatie met back-up, 76 exacte bronbestanden en
24 nacontroles. Echte E32-Keteltest/rapportdownload op drie breedtes PASS.
De keten met HA is na de E32-reboot vers/actief en SOURCE rev3 blijft behouden.
Bij uitrol stond ontvangst uit; de latere README-opname bevestigt inmiddels
passieve Classic-ontvangst, zonder volledige veldpariteit of actieve werking. Volg voor
de eerstvolgende passieve praktijkstap het actuele werkbord; B04–B09 blijven
open voor de actieve bèta, geen automatische verwarmingsvrijgave.

24 oktober: tweetalige UI voorbereid in dezelfde bètabasis. E32 heeft centrale
EN/NL-catalogus, Engelse standaard/terugval en browsercookie-keuze in menu,
aanmelden en wifiherstel. HA volgt de profieltaal voor de kamereditor en native
vertalingen; opgeslagen native dashboardteksten vallen terug op Engels. Geen
apparaatinstallatie gedaan. Bewijs: `out/bilingual-ui-20261024/`.

24 oktober: algemene EMS-eis bevestigd: altijd alle beschikbare ketelvelden,
onafhankelijk van modelkeuze; 69 Classic-velden zijn geen maximum. Zie
EMS-DISCOVERY-POLICY.md. Persoonlijke Ecomline HR 22H-waarneming via bestaande
HA-specialist; native eenmalige controles na 1/6/24 uur geregistreerd en
onafhankelijk teruggelezen, zonder levering naar chat of ketelwijzigingen.
Bewijs en persoonlijk veldprofiel blijven lokaal in
`out/ecomline-observation-20261024/`; de 24-uursbeoordeling is nog niet afgerond.

CI op f9009eb: firmware/source-reproductie/native PASS, maar bestaande
HA-test verwachtte nog afwezigheid Nederlandse geavanceerde formulieren en
smalle ketelkaart liep op de runner buiten beeld. Test nu met echte EN/NL-
resources en tekstomloop voor bredere fonts; afzonderlijke regressies getest.
Nieuwe openbare eindrun nog controleren; oude rode run nooit groen noemen.

### Herstel unavailable productmetingen (2026-10-24)

Live oorzaak bevestigd door de HA-agent: shadow-firmware start de legacy publishers niet; de HA-producttak sloeg de gevalideerde native metrics-cache over. De productplatform-regressie faalde vóór de correctie en slaagt erna; 41 gerichte native HA-tests slagen. De producttak gebruikt nu één native eigenaar voor v2-metrics en behoudt installatiegroep/identiteiten. Alle voorbereide Classic-veld-, taal- en UI-wijzigingen blijven gebundeld in alpha20/dev26. De alpha19-tag heeft een native CI-headerfout en is niet live geïnstalleerd; tags blijven ongewijzigd. Installatie en verse HA-ketelmetingen zijn nog te bewijzen; geïnstalleerd blijft alpha18/dev24.

### Actueel: HA-overzicht van native ketelvelden

Alpha20/dev26 is live; 69 definities, 27 waarden (25 reported +2 inferred) en behoud van SOURCE/instellingen/identiteiten zijn geverifieerd. De automatische E32 HTTPS-catalogusroute werkt. Het bestaande beheerde boiler-overzicht had nul native veldreferenties; HA dev27 vult de eigen kaarten/grafieken aan. Nieuwe kaarttest faalde vóór de correctie en slaagt erna; 100 gerichte HA-tests PASS. Volgende stap: volledige HA-release-CI, exact pakket en HA-agentupdate zonder nieuwe firmware-upload. Oudere onderstaande/voorgaande “niet geïnstalleerd”-bronnotities zijn historische checkpoints; actieve fysieke kwalificatie blijft open.

### Exacte gebruikersbevestiging ketelmodel (24 oktober 2026)

Gebruiker bevestigt **Nefit Ecomline Classic HRC 22H**; eerdere HR22H/H22-alternatieven zijn hiermee historisch. Bronprofiel: `boiler-profiles/nefit-ecomline-classic-hrc-22h.json`. Exacte keuze op E32 Home/Settings voorbereid voor alpha21; oudere generieke keuze blijft geldig. Originele NVS-opslag/readback met foutinvoer en 4 browserprofielen PASS. Geen nominale specificaties of fysieke controlkwalificatie afgeleid uit de modelnaam; alle beschikbare velden blijven onafhankelijk van de modelkeuze gelezen. HA dev27-overzichtsrelease hoort hierbij en verandert niet door de E32-profieltoevoeging.

### Actueel geleverd: alpha21/HA27 en HRC22H

De uitrol is voltooid en onafhankelijk gecontroleerd: exact geselecteerd model
`nefit-ecomline-classic-hrc-22h`, firmware-ELF/webhash,79 HA-bestanden, gezonde
HA27-opstart,47 native veldreferenties en3 historiekaarten. Alle105 IDs en
gebruikersinstellingen behouden; alleen het gevraagde displaymodel gewijzigd.
SOURCE4 is de juiste huidige baseline na bewezen dagelijkse UTC-horizonverversing;
geen reset naar3. Laatste26 actuele HA/REST-waarden komen overeen na de normale
wire→HA-unitconversie. NOT_READY blijft gelden voor actieve fysieke aansturing.

De eerste+1h-nativejob was FAILED/UNKNOWN door een onjuist gevormde beheeraanroep.
`MONITOR-ROUTE-TEMPLATE.json` in de HA-agentworkspace bewijst de juiste URLencoded
stringbody + form-header, geen poort. HA-registry/current/history eerst; optioneel
E32-supplement mag geslaagde HA-data niet weggooien. Toekomstige+6h/+24h-payloads
zijn hersteld met behouden tijden en overige jobs. Native geïsoleerde retry van
de bestaande uitgeschakelde foutjob is PASS:26 actuele veldwaarden,629 begrensde
Recorder-rijen over67 entiteiten; historie gedeeltelijk, oude1h-gap ongewijzigd.
Retryjob na succes native verwijderd, geen nieuwe joblaag. Vervolgobservaties
blijven op de bestaande+6h/+24h-tijden staan.


Volledige HA-regressie van de TV02-lifecyclebatch: **1.840 tests + 68 subtests =
1.908 checks PASS**, nul fouten/overslagen, met alle acht C++-peers opnieuw uit
actuele bron gebouwd en een tijdelijke localhost-MQTT-broker. Brokerafwezigheid
na afloop onafhankelijk gecontroleerd. De 222 gerichte checks zijn hierin
inbegrepen. Geen fysieke kraan-/ketelproef of nieuwe productie-installatie.
Bewijs: `out/tv02-lifecycle-20261024/HA-ACCEPTANCE.xml` en `BROKER-FINAL.json`.
