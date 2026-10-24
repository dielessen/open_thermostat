# Volgende gezamenlijke release

Bijgewerkt: 24 oktober 2026. Dit is het korte releaseoverzicht.
Het [werkbord](WORKBOARD.nl.md) bevat de enige actuele checklist en prioriteiten;
het [masterplan](PLAN.nl.md) bewaart alle 31 producteisen en acceptatievoorwaarden.

## 1. Wat draait er nu?

| Onderdeel | Geïnstalleerd | Stand |
| --- | --- | --- |
| E32 | `v0.1.0-e32v2-alpha.27`, bron `dd6a9635865c6ecd2bf1c553c3292ae13dfb53ae` | Passief EMS uitlezen; TX, forwarding en fysieke uitvoer geblokkeerd |
| Home Assistant | `0.4.0.dev36`, bron `c41b7a6e12730f88eb98960299be3236c6494457` | Geladen op Core 2026.10.3; frontend dev35/v35 |
| Actieve regelaar | Tado | Geen automatische ketel- of kraansturing door OpenThermostat |

Bron/pakket/ELF/web, alle 83 HA-bestanden en behoud van instellingen, programma's
en identiteiten zijn gecontroleerd. Zie [installatieverslag](INSTALLATIE-HA36-ALPHA27-20261024.nl.md).
De uitgebreide geleverde bundel staat in de [werkbordhistorie](WORKBOARD-HISTORIE-20261024.nl.md).

### Laatste controle van de geïnstalleerde omgeving

24 oktober 17:00–17:01 CEST: HA geladen, E32 dezelfde boot/uptime +70 s,
19 nieuwe EMS-rapporten, ontvangstfouten/TX/polls 0. Vrij geheugen circa 77–80 kB,
CPU circa 53 °C. De onderzochte web-/statusroutes werken en instellingen zijn behouden.
Oorspronkelijke TV02-temperatuurontvangst is nu bevestigd; doelecho en kraanwerking
blijven ongekwalificeerd. De gekozen kamerbron heeft nog geen bruikbaar meetprofiel.

Korte runtimecontrole geslaagd binnen deze grenzen; geen lange-duurproef of
actieve verwarmingsacceptatie. Geen update/herstart/aansturing uitgevoerd.
Bewijs: `out/stability-check-20261024/SAFE-RESULT.json`.

## 2. Klaar om in de volgende release mee te nemen

| Onderdeel | Wat verandert er? |
| --- | --- |
| Settings → EMS-apparaten | Per ontvangen afzender identiteit indien bekend, telegramtypen en entiteiten met waarde/kwaliteit/ouderdom; EN/NL, zoekfilter en behouden openklapstatus |
| E32-klokbewaking | Verlopen grant/lease kan bij teruggaande klok niet herleven; ook diagnostische lezingen gecontroleerd |
| HA-klokbewaking | Ongeldige/teruggaande monotone klok trekt sessie, wachtende opdrachten en bewijzen in; oude rechten herstellen niet door reconnect |
| Herhalen na vertraagde verzending | Deadline/lease en SOURCE opnieuw controleren na wachten; geen herhaling van ingetrokken of vervangen opdrachten, geen heartbeat op verlopen sessie |
| HA-opstart en annulering | Vroege fouten ruimen eigen resources op; een oude setup verwijdert geen nieuwe eigenaar |
| Kamereditor | Te grote numerieke kraanmetadata wordt afgewezen zonder editorcrash |
| Webnavigatie | Vertraagde pagina-antwoorden kunnen een nieuwere pagina niet overschrijven of oude scripts uitvoeren |
| EMS-tabel | Bestaande rijen hergebruikt, adressen correct geordend, waarden gecontroleerd en getallen volgens EN/NL weergegeven |
| Keteltestplan | Concrete volgorde en criteria voor toekomstige stop-, zend-, naloop- en uitvalproeven |

**Gebouwd en getest, nog niet geïnstalleerd.** Broncheckpoint
`34aa3e8b0525e41d0ae93e5afd299d59f238595f`: alle zeven CI-jobs geslaagd;
2154 HA-tests op zowel Core 2026.10.2 als Core 2026.10.3, zonder fouten of skips.
Bewijs: `out/ha-session-clock-20261024/FINAL-REVIEW.json`. De aanvullende
wachtrijfix heeft 13 nieuwe regressiegevallen; haar eigen bron-/test-/CI-bewijs staat
in `out/retry-await-fence-20261024/FINAL-REVIEW.json`. Nog niet geïnstalleerd.

Alle 23 voorbereide onderdelen met 245 bronverwijzingen blijven in de
[release-inventaris](BETA1-RELEASE-INVENTARIS.json). Bestaande regeling,
supervisor, groepen/vloer/menger, historie/CSV, comfort en leren blijven behouden.
Hun ontbrekende verbindingen en fysieke acceptatie staan op het werkbord.

## 3. Wat doen we hierna?

| Volgorde | Werk | Gereed wanneer |
| --- | --- | --- |
| P0 vóór fysieke proef | Gemeld pendelen verklaren en passieve nulmeting beoordelen | Oorzaak of concrete vervolgmeting vastgelegd; geschikte stabiele proefbeginsituatie |
| P0 software, B04 | Echte geschikte kamerbron met oorspronkelijk rapport en meetprofiel | Werkelijke acquisitie/actualiteit en uitval bewezen; geen diagnostische device_temperature als ruimtemeting |
| P0 software, B05/M2 | Normale FW→HA-kraanroute met HA-ontvangergrant en bestaande adapter afronden | Native zendtransactie aan oorspronkelijke kraanecho gekoppeld; profiel, modus, eigenaarschap en fallback getoetst |
| P0 software, B06 | Werkelijke veiligheids-/DHW-/water-/kraan-/flowfeiten aansluiten | Iedere bron met eigen geldigheid en beoordeeld installatieprofiel; geen generieke flowaanname |
| P1, B07–B09 | Classic-TX-/stopketen afronden en installatievoorwaarden beoordelen | Adres/masker, interface/polariteit/arbitrage, afgifte/naloop, onafhankelijke stop en één actieve schrijver vastgesteld |
| Release, B10–B13 | Eén gezamenlijke kandidaat bevriezen, verifiëren, publiceren en installeren | Exacte bron/pakketten, volledige CI, checksums, herstelroute, backup en nacontrole |
| Fysiek, B14 | Afzonderlijk toegelaten stop-/zend-/uitvalproeven uitvoeren | Gemeten reactie en stop binnen beoordeelde grenzen; gecontroleerd herstel vastgelegd |

Onafhankelijk softwarewerk kan doorgaan terwijl fysieke gegevens ontbreken.
Een begrensde handmatige ketelproef en automatische kamerregeling hebben
verschillende voorwaarden: die laatste vereist ook de volledige M2-kamer-/kraanketen.

## 4. Pendelen: wat weten we?

De passieve controle van 24 oktober 16:26 CEST bevestigt **0 EMS-verzendingen,
0 polls en alle uitgangen geblokkeerd**. Geen UART-fouten of ongeldige telegrammen;
geen bewijs van OpenThermostat-aansturing. De beschikbare geschiedenis toont
warmwatergerelateerde vermogensperiodes van ongeveer 3–4 minuten met 10–12 minuten
tussen starts, ook nadat Tado voor de kamer idle meldde.

**Oorzaak nog onbekend.** Warmwatergebruik/bijwarmen is de onderzoeksrichting.
Telemetrie bewijst geen exact aantal fysieke ontstekingen en sluit indirecte
elektrische invloed niet volledig uit. Geen instellingen gewijzigd of zendproef
gedaan. Bewijs: `out/boiler-cycling-20261024/SAFE-RESULT.json`.

De latere controle van 17:00–17:01 CEST toont in de voorafgaande 30 minuten alleen
code 0H/0% gemeld vermogen en afkoeling, zonder nieuwe positieve vermogensperiode.
De eerdere oorzaak blijft onbekend; dit is geen bewijs van een reparatie.

## 5. Wanneer is de actieve bèta gereed?

Er is nog geen onderbouwde kalenderdatum. De softwarekandidaat kan met
geblokkeerde uitgangen worden geleverd; actieve proeven volgen pas na de
bijbehorende installatie- en stopvoorwaarden. Het [testplan](BETA1-KETELPROEF.nl.md)
beschrijft nulmeting → fysieke proefkaart → stop in rust → één begrensde vraag →
stop/naloop → afzonderlijke uitval → terugkeer naar Tado.

De oudere native HTTPS-updaterfout blijft onverklaard; checkpointdiagnose is
geleverd, maar bewijst geen reparatie. Geen blinde herhaling van de mislukte route.

## 6. Blijvend in het productplan

Alle 31 eisen blijven gelden, inclusief per ruimte leren en blijvend bewaarde,
gevalideerde parameters. Nieuwe F9/F10-ontwikkeling volgt na M2. Acht zones,
vloer/menger, grafiek-/historieacceptatie, comfort en onbeheerd verwarmingsbedrijf
houden hun eigen acceptatievoorwaarden. Niets wordt op basis van alleen aanwezige
code of een geslaagde build als werkende fysieke functie afgevinkt.
