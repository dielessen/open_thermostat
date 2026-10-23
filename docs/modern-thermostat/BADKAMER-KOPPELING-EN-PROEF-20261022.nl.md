> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# Badkamer: actuele koppeling en eerstvolgende proef

Dit is de voorbereiding van M2, geen afgeronde fysieke proef. Mark bevestigt
dat de E32 los van de ketel staat. De koppelingen worden in Home Assistant
beheerd; onderstaande technische controles zijn ontwikkelwerk.

## Wat daadwerkelijk is uitgelezen

| Onderdeel | Bewijs van 22 oktober | Nog te bewijzen |
| --- | --- | --- |
| Kamersensor | `sensor.motion_badkamer_device_temperature`, Aqara RTCGQ11LM, beschikbaar en 20 °C om 16:25 CEST. | Herkomst en leeftijd van ieder echt temperatuurdragend rapport; uitval en cache/herstartgedrag. |
| Radiatorkraan | `climate.thermostaat_badkamer`, Tuya TV02-Zigbee; lokaal 18,3 °C, doel 21 °C, preset auto. HA meldt 5–30 °C, stap 0,5 °C. | Exclusieve doelregeling, modelgebonden modus/echo, echte reactie, uitval en herstel. |
| Gewenste kamerconfiguratie | Basis 21 °C, grenzen 5–35 °C, maximale meetleeftijd 120 s; behouden bij dev5. Week nog leeg. | Grenzen/afronding van de actuator expliciet verenigen met de kamerdoelen. Geen stilzwijgende begrenzing. |
| E32 | Gebruikersadres `http://192.168.1.206/`; inlogpagina bereikbaar, status HTTP 401 om 17:06 CEST. | Geauthenticeerde firmware-/profiel-/sessiereadback en vervolgens HA→E32→ACK. |
| HA | Dev5 geladen en gezond; één installatie, Badkamer, twee apparaten en 36 entiteiten om 16:58 CEST. | Een opgeslagen instelling bevestigt nog geen toepassing op de E32. |

Er ontbreekt geen gekoppelde sensor. De keuze van deze tijdelijke testbron is
expliciet door Mark gemaakt. Representatieve kamertemperatuur en rapportversheid
zijn afzonderlijke meetvragen, geen conclusie uit de entitynaam.

## Concrete volgorde van het vervolg

1. Gebruik de gewone E32-authenticatie om de huidige firmware-identiteit,
   controller-/adapteridentiteit en beschikbare contracten uit te lezen. Mark
   heeft het regelen van beheerstoegang geautoriseerd. Geen wachtwoordreset of
   uitschakelen van authenticatie; een login geeft geen uitvoerbevoegdheid.
2. Vergelijk het werkelijke contract met `NativePlanSource` en het bestaande
   `control.plan.week.v1`-pad. Dat bronpad ondersteunt één radiatorruimte;
   het oudere vloer-DATA-pad en de tweekamerprojectie zijn hiervoor geen vervanging.
   Controleer de bestaande owner, opslag, profielreferenties en exacte readback.
   Geen firmware-update aannemen voordat de huidige firmware is vastgesteld.
3. Bereid voor **de gekozen RTCGQ11LM-bron** een begrensde rapportproef voor.
   De bestaande `v1_bench_source.py` is expliciet gepind op WSDCGQ11LM en de
   JSON-eigenschap `temperature`; deze bron gebruikt `device_temperature`.
   Start die oude proef niet met verwisselde modelnamen of een trustvlag.
   Eerst actuele producer/converterversie en Discovery verifiëren, daarna een
   gericht getest modelpad. Een actuele HA-weergave bewijst geen acquisitietijd.
4. Leg voor de TV02 de ondersteunde lokale regelmodus en het effect van
   doelwijzigingen vast. De huidige preset auto kan de eigen kraanagenda uitvoeren.
   Bewijs daarom één doeleigenaar en behoud de bestaande agenda/instellingen
   vóór een eventuele tijdelijke moduswisseling. Het bronprofiel
   `ProfileCActuator` doet alleen een begrensde `set_temperature`; dat is op
   zichzelf geen TV02-modus-, sluitstand- of klepfeedbackkwalificatie.
5. Bewijs eerst de configuratieketen en effectieve doelen met fysieke uitvoer
   geblokkeerd. Voer daarna de afzonderlijke begeleide kraanproef zonder ketel uit:
   passend doel, ontvangst/echo, werkelijke reactie, bron-/actuatoruitval en herstel.
   Herstel de gemeten uitgangssituatie. Een geslaagde HA-service is geen bewijs
   van een open klep; bij ontbrekende fysieke feedback blijft die zekerheid onbekend.

De officiële [RTCGQ11LM-beschrijving](https://www.zigbee2mqtt.io/devices/RTCGQ11LM.html)
benoemt `device_temperature` als apparaatgegeven zonder `/get`-ondersteuning.
De [TV02-beschrijving](https://www.zigbee2mqtt.io/devices/TV02-Zigbee.html) noemt
lokale presets, een eigen agenda en doelen van 5–30 °C. Dit is protocolinformatie,
geen bewijs van de werkelijk geïnstalleerde converter of van fysiek gedrag.

## Bewijs en grenzen

De verse specialistuitlezingen staan onder
`openthermostat-m2-preflight-20261022` en
`openthermostat-e32-direct-preflight-20261022` in de bestaande HA-artifactmap.
De lokale dev5-nacontrole en kopie van de bordvoorcontrole staan in
`out/ha-week-planner-20261022`. Beheerstoegang krijgt een afzonderlijk receipt.

Runtime/actuatie zijn niet geactiveerd, SOURCE is niet geselecteerd en er zijn
geen kraan- of ketelcommando's verstuurd in deze controles. De SDK-releasepoort,
echte producer-/actuatoracceptatie en ketelstop-/uitvalproeven blijven open.

## Actualisatie na dev7 — 22 oktober, onderhoud loopt bewust

De eerdere tabel/metingen hierboven zijn gedateerde uitlezingen, geen nieuwe
live-toestand. **HA laatst live bevestigd: 0.4.0.dev7.** De gekozen motion-
temperatuursensor is gekoppeld; geen nieuwe uitlezing, gebrek- of defectclaim
in deze stap. Geschiktheid en versheid zijn nog afzonderlijke meetvragen.

Dev8 is uitsluitend bron/pakket: leescontrole van opgeslagen kamerdoelen tegenover
HA-kraanbereik en stapgrootte. Dit maakt het eerder gemeten verschil kamer5–35 /
kraan5–30 zichtbaar, zonder die gegevens als actueel te presenteren of instellingen
te wijzigen. Externe programma's zijn niet gecontroleerd; metadata zijn geen
fysieke klepfeedback. Native1380 PASS/2 SKIP en onafhankelijke pakketcontrole PASS.
Zie de actuele testkandidaat voor checksum en bewijs; **dev8 niet geïnstalleerd**.

De E32 is publiek bereikbaar op 192.168.1.206: `/login`200, `/status`401 bij de
controle van 22:27:24 CEST. Mark heeft “E32-invoer staat klaar” bevestigd. De
beschermde invoer is niet gelezen en er zijn nul loginpogingen: de beheerroute
stopte vóór provideruitvoering door onderhoud. Mark bevestigt dat dit onderhoud
bewust loopt. Geen beheerconfiguratie wijzigen of herhaald proberen. Toestemming
blijft bewaard; na onderhoud eerst bestaande sessie/receipts controleren, dan de
voorbereide eerste login/uitlezing en verse HA-kamer/kraan/sensorcontrole uitvoeren.
De concrete proefvolgorde hierboven blijft van kracht; niets fysiek vrijgegeven.

## E32 rechtstreeks gecontroleerd — 22 oktober, 22:33 CEST

Mark gaf vervolgens de normale lokale inloggegevens. Daarmee is **rechtstreeks
op de E32 ingelogd**, zonder HA-beheer of onderbreking van OpenClaw-onderhoud.
Dit nieuwe bewijs vervangt de eerdere conclusie dat de E32-uitlezing op de
beheerroute moest wachten. Het beschermde eenmalige HA-invoerbestand bleef
ongemoeid; geen credential- of sessiemateriaal opgeslagen.

- Eén login HTTP200, sessie bevestigd; `/status` en `/status/version` HTTP200.
- Gemelde firmware **v0.1.0-e32v2-alpha.6**, bronreferentie
  `b6b57df18afdfd916b9d32465ac699a670400614`, ELF-identiteit
  `ddc0a9c07931dbdaa96741244c487b19f4bb6334ab41c60e89cde939c948aff8`.
- Actuele **controlMode legacy**, nul lokale kamers; geen modern `control`-
  statusdeel in de respons. Dit zegt niets over de bestaande HA-kamer Badkamer.
- Herhaalde firmware- en statusuitlezing bevestigt dezelfde identiteit/modus.
  Daarna uitgelogd; nieuwe `/status` krijgt weer HTTP401. Geen configuratie,
  SOURCE, firmware, apparaatdoel of ketelaansturing gewijzigd.

De gemelde bronreferentie bevat niet het latere `nativeSourceCurrent`-pad dat
in de huidige ontwikkelbron aanwezig is. Dat is een bronvergelijking, geen bewijs
dat de draaiende image exact die commit bevat. **Het huidige native SOURCE-/
weekplancontract op het apparaat is nog niet bewezen.** Niet zonder verdere
controle omschakelen of een nieuwere firmware aannemen. De SDK-releasepoort
voor nieuwe firmware blijft open. HA-dev8 blijft bron/pakket, live laatst dev7.

Bewijs: `out/plan-resume-m2-20261022/E32-DIRECT-READ.json` en
`E32-DIRECT-REVIEW.json`. Volgende stap: na onderhoud verse HA-bindingen/broker-
identiteit via de specialist, exacte contractvergelijking en dan de ondersteunde
configuratie-/ACK-proef. Geen nieuwe ontbrekende/defecte-sensorclaim uit deze stap.

## Rechtstreekse E32-contractcontrole — 22 oktober 23:09 CEST

De geselecteerde E32-configuratie is nu daadwerkelijk gelezen met de normale
login: firmware meldt nog alpha.6, controlMode legacy en nul lokale kamers.
`/config/device` HTTP200 met MQTTobject: enabled true, modern_shadow false,
broker192.168.1.130:1883, base ib-therm, adapter_id leeg. De huidige native-source-
readbackvelden worden niet aangeboden: `native_source_device_id`,
`native_source_live_apply` en `native_shadow_source` ontbreken. De oude gemelde
bronreferentie bevat die actuele code evenmin. Dit is geen attestatie dat de
draaiende binary exact die commit bevat; het nieuwe contract mag niet worden
aangenomen op basis van alleen de versienaam of een HA-save.

Bronnen: `out/ha-device-selection-20261022/E32-CONTRACT-READ.json` en de
onafhankelijke `E32-CONTRACT-REVIEW.json`. Herhaalde versie-/modusuitlezing gelijk;
uitgelogd en `/status`401 bevestigd. Geen settingsPOST, MQTTpublicatie, SOURCE-
selectie, firmwareflash of apparaatcommando. Geen wachtwoord/sessie opgeslagen;
het beschermde HA-invoerbestand bleef ongelezen.

Na de HA-update: de geselecteerde HA broker-/prefix-/adapteridentiteit vergelijken
met deze deviceconfig en het werkelijk ondersteunde firmwarecontract vaststellen.
Niet blind de oude modus activeren of een firmware-/SDKpoort omzeilen.

## Laatste uitlezing na dev11 — softwareklaar, M2 nog open

Dev11 is live met verse Core-start23:26:08CEST en onafhankelijke bron/data/module-
nacontrole. De officiële HA IntFlag wordt nu correct als kraaneigenschap gelezen.
Laatste twee gerichte kameruitlezingen: grenzen5–30°C, basis21, zeven lokale blokken
07:00–23:30/doel21, dezelfde motion-sensor/kraan, review compatible en geen issues.
De grens stond bij het begin van die laatste controle al op30; geen room/save of
herstart uitgevoerd. De eerdere dev11-nacontrole had nog35 gemeld; de herkomst van
het verschil tussen die controlemomenten is niet vastgesteld. Geen onuitgevoerde
wijziging aan de agent toeschrijven.

Dit is metadata-/configuratiebewijs, geen nieuwe acquisitietijd, sensorlocatie- of
fysieke kraankwalificatie. Runtime/transport/actuatie blijven uit. De actuele
HA/E32-broker-/prefixinstellingen zijn vergeleken en passen als configuratieroute;
E32 staat nog legacy met lege adapter-ID en zonder nieuwe native SOURCE-velden.
Volgende stap is de passende firmware/het regelcontract en daarna de M2 ACK-/
bron-/kraanproef. Zie testkandidaat en out/ha-native-capabilities-20261022.
