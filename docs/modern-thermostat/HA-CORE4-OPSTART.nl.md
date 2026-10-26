# HA Core 2026.10.4 — opstartblokkade hersteld in beta.1

## Actuele geïnstalleerde basis — 25 oktober 2026, 20:39 UTC

E32 **v0.1.0-e32v2-beta.1** en HA **0.4.0b1** op Core **2026.10.4** zijn
gezamenlijk geïnstalleerd vanaf bron `5e3ed30653d93b09dd65b5305accd65d079c0c06`.
De HA-opstartfout is live hersteld. Installatie24/24 en onafhankelijke
nacontrole45/45 geslaagd; normale GitHub-updatepoort geaccepteerd.
Fysieke uitgangen blijven uit. De actieve ketelbèta blijft **NOT_READY**.
[Installatie, bewijs en grenzen](INSTALLATIE-BETA1-20261025.nl.md).

De hierna gedateerde oudere alpha36/dev48-waarnemingen zijn historische
bron-/installatiebewijzen. Ze beschrijven niet de huidige geïnstalleerde basis.
Nieuwe profiel-/EMS-wijzigingen na bron5e3ed30 zijn nog niet geïnstalleerd.


25 oktober 2026. Dit is bronwerk voor dezelfde grote bèta, **geen tussentijdse
release of installatie**. De draaiende HA-installatie is niet aangepast.

## Wat is waargenomen?

De gebruiker meldde `ValueError: setup_platform_unsupported` vanuit
`ensure_installation_group`, aangeroepen tijdens `async_setup_entry`.
De bestaande native HA-specialist heeft uitsluitend gelezen en bevestigt:

- Home Assistant Core **2026.10.4**;
- OpenThermostat **0.4.0.dev48** volgens het manifest;
- integratiestatus **setup_error**, met dezelfde fout;
- laatste overeenkomende fouttijd **2026-10-25 16:11:31.733**, zoals gelogd.

De geïnstalleerde `product.py` en `installation_group.py` zijn niet uitgelezen;
hun actuele bronhash en de geladen Python-objectidentiteit blijven onbekend.
Er is geen toegang uitgebreid en geen helper op HA gestart. De huidige
waarneming vervangt geen eerdere volledige installatie-/broncontrole.

## Oorzaak en herstel

De gecontroleerde bron accepteerde alleen exact Core 2026.10.2 en 2026.10.3.
Die versiecontrole stond ook vóór het maken van de presentatiegroep
‘Installatie en ketel’. Daardoor kon één Core-patch de hele integratie laten
stoppen, al vóór tracker, verbinding en platformopstart. De fout is lokaal op
de echte Core 2026.10.4 gereproduceerd. Dit is een opstartblokkade; het bewijs
wijst niet op een nieuwe EMS-, ketel- of Bluetoothfout.

De presentatiegroep gebruikt publieke subentry-/registry-API's en erft de
versiepin van de private opslagtransactie niet meer. De bestaande controles op
conflicterende eigenaren/groepen, het verplaatsen van entiteiten vóór het
apparaat en herstel bij fouten blijven behouden. Bestaande entiteit- en
apparaatidentiteiten, gebruikersnamen en kamerrelaties worden niet vervangen.

De native configuratie-/migratietransactie heeft wél een strikte versiegrens.
Core 2026.10.4 is daar expliciet aan toegevoegd na controle van het echte
pakket. `config_entries.py`, beide registries, `data_entry_flow.py` en
`selector.py` zijn byte-identiek aan de al beoordeelde Core 2026.10.3. De vijf
bestanden zijn tegen de distributie-RECORD gecontroleerd; de echte provider
blijft `probatio==0.13.0`. Er is geen versienummer, importmodule of API nagebootst
om de compatibiliteitsproef te laten slagen.

Dit geeft geen algemene ondersteuning voor iedere toekomstige HA-versie:
onbeoordeelde private configuratiewrites blijven geweigerd. Een synthetisch
versielabel in de regressie controleert uitsluitend dat de presentatie niet
meer door die pin stopt; dat is geen test van een toekomstige Core-implementatie.

## Controle en uitrolgrens

Zeven groepsgevallen faalden vóór de correctie op de echte Core 2026.10.4 door
dezelfde versieblokkade. Na correctie slagen 60 gerichte native gevallen; de
extra gewone opstart-/afsluitregressies slagen ook. Zij bewaken cleanup,
identiteiten, onveranderde instellingen, versiegrenzen en nul publishes.
De volledige suites op de echte Core 2026.10.2, 2026.10.3 en 2026.10.4 slagen
ieder met **2.428 gevallen** (2.360 tests en 68 subtests), nul fouten/errors/skips.
Dezelfde Python-bron bleef gedurende de drie suites behouden. Daarna zijn alleen
de NL/EN-foutteksten verduidelijkt, zonder verouderende patchlijst. Die resources
zijn apart op alle drie Cores gecontroleerd; de actuele Core4-startup-/groeps-/
provider-/resourceselectie slaagt met 30 gevallen. De tijdelijke lokale
MQTT-fixture is gestopt en onafhankelijk afwezig gecontroleerd. Zeven pakkettests
slagen; de definitieve globale bronfreeze blijft een latere bèta-releasepoort.
CI krijgt dezelfde drie Core-versies en behoudt de pakket-/broncontroles.

Historische bronstatus vóór de gezamenlijke uitrol: de lokale reparatie was toen nog niet geïnstalleerd. De laatste alleen-lezen
productiewaarneming blijft daarom **setup_error**. Volgens de opdracht volgt
er geen losse hotfixinstallatie: dit herstel gaat mee in de ene grote bèta.
Er is geen reload, herstart, bronwissel, MQTT-publicatie of apparaatopdracht
op de productie-installatie uitgevoerd. Fysieke meet-/kraan-/ketelacceptatie
blijft afzonderlijk open.

**English:** The existing integration failed to start after Core moved to
2026.10.4 because an exact-version guard also blocked optional presentation
grouping. The beta decouples public registry grouping from private Store write
qualification and explicitly tests/adds Core 2026.10.4. Unreviewed private writes
remain blocked. Live read-only evidence reports dev48 in setup_error; installed
Python source hashes were not read. No interim deployment or device operation.

Aanvullende verpakkingscontrole: native pytest schrijft broncommit/hash, schone/ongewijzigde bron en de echte Core-versie naar XML. De packager weigert ontbrekend, verouderd, dubbel of onbeoordeeld bewijs. Tien packagergevallen en acht echte Core4-groepsgevallen slagen; de ontwikkelrun is correct als niet-schoon gemarkeerd en is dus geen verpakkingsbewijs. Definitieve bronfreeze en volledige suites volgen apart.
