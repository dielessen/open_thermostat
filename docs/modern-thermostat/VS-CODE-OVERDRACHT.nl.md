# OpenThermostat — actuele overdracht

Bijgewerkt 24 oktober 2026 na de oorspronkelijke TV02-rapportproducer.

1. Lees [WORKBOARD](WORKBOARD.nl.md): de enige actuele afvinklijst met alle 31
   eisen, 11 fasen, 8 werkpakketten en B01–B14-releasechecklist.
2. [PLAN](PLAN.nl.md) bewaart het ontwerp en alle oorspronkelijke acceptatie.
3. [Release-inventaris](BETA1-RELEASE-INVENTARIS.json): 23 voorbereide onderdelen,
   125 bronverwijzingen met hashes. Alles blijft in de eerste bètabasis, ook
   begrensde code die nog niet als complete productfunctie is aangesloten.

## Actuele bron en installatie

- Geïnstalleerd/gecontroleerd: E32 alpha18 + HA dev24, bron `6ef01d0`.
- Actueel uitrolbewijs: `out/prepared-rollout-20261023/FINAL-REVIEW.json`.
- Bij de latere README-opname zijn verse Classic-berichten ontvangen; TX/actuatoruitgangen blijven geblokkeerd.
- Het huidige bronwerk loopt vóór op de geïnstalleerde passieve release; publiceer/installeer geen actieve bèta op basis van alleen een geslaagde bronbuild.
- Broncheckpoint `60c548f`: volledige GitHub CI 40027429946 PASS; 69-velden-HA-projectie voorbereid, nog niet geïnstalleerd.
- Nieuwste bronstap: originele Zigbee-temperatuurproducer plus native HA-ontvanger/room-status; broncontract in ORIGINAL-ZIGBEE-REPORTS.nl.md. Producent/ontvangstdiagnose zijn gebouwd en getest; echte acquisitie-/bronkwalificatie en fysieke validatie staan open. Niet geïnstalleerd, geen QualifiedReport.
- HA-ontvangstcheckpoint `0e2793b`: volledige GitHub CI 40030592815 PASS.
- Nieuwe expliciet gevraagde gebruikersfunctie: Settings → Mijn ketel, NVS-persistente modelkeuze en SVG op Home. Eerste model Nefit Ecomline Classic; presentatie geeft geen technische vrijgave. Nog niet geïnstalleerd.
- Nieuwste B05-bronstap: oorspronkelijke TV02-datapuntproducer, 13 nieuwe + 11 bestaande producenttests PASS. Native echo-consument/causale doelkoppeling en fysieke proef blijven open; zie ORIGINAL-TV02-REPORTS.nl.md. Niet geïnstalleerd.
- Eerst B04 echt meetprofiel/bronvalidatie en B05 verse kraanecho afronden, daarna B06–B09 proefketen en installatievoorwaarden; pas dan gezamenlijke freeze/uitrol.
- Onderstaande bronstappen zijn historische checkpoints; zie WORKBOARD voor hun actuele status.
- Laat de bevroren `out/plan-batch-20261023` intact.
- Werk verder in `out/beta-boiler-20261023`, branch `work/beta-boiler-20261023`.
- `cebb0a2`: ontvangstdiagnose en Settings → Keteltest met downloadrapport;
  18 native, 43 GUI, 3 Chromiumviewports en normale E32-build geslaagd.
  Geen nieuwe release/installatie/fysieke ketelopdracht voor dit checkpoint.
- Planherijking voegt actuele PLAN/WORKBOARD en inventaris aan de kandidaat toe;
  de kandidaat-HEAD kan daardoor nieuwer zijn dan het ontvangstcheckpoint.

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
