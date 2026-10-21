# Gecontroleerde VS Code-overdracht — 21 oktober 2026

## Start en eigenaarschap

Geschikt voor **bronreview en verdere ontwikkeling**, niet voor installatie of verwarmingsbedrijf. Onafhankelijk geaccepteerde firmware én HA-bron: **c7d9f8c3cfda63019a230562d564a5ef53bf2e2a**. Beide zitten in dezelfde Gitrepository; geen aparte HA-upstreamsync.

Open via bestaande VS Code Remote SSH de map **/home/dielessen/projects/open_thermostat-vscode-20261021**, of daarin `docs/modern-thermostat/OpenThermostat-reviewed.code-workspace`. De parent maakt deze aparte branch/worktree `review/mark-vscode-20261021` vanaf de acceptatie inclusief deze instructies. Geen automatische taken/autofetch. VS Code zelf is hier niet gestart (`code` ontbreekt); folder-/Git-/werkruimtecontrole is wel uitgevoerd.

- Firmware: `/home/dielessen/projects/open_thermostat-vscode-20261021/src`, webbron `data/html`.
- HA: `/home/dielessen/projects/open_thermostat-vscode-20261021/ha/config/custom_components/open_thermostat`.
- Tests: `ha/tests_native`, `test/interop/graph_session_runner.cpp`.
- OpenClaw canonical: `/home/dielessen/projects/open_thermostat-wp01-20261019`, branch `work/wifi-onboarding-20261020`.
- **Eigenaarschap:** Marks VS Code-branch blijft exclusief voor zijn wijzigingen; automation/specialist schrijft daar niet. Parent blijft sole canonical WORKBOARD-/integratieschrijver. Specialist mag uitsluitend een eigen begrensde kandidaat bewerken. Geen wederzijdse automatische merges of edits. Het hele-planmandaat blijft actief.

## Wat geaccepteerd is

Het bestaande 17-padenpakket ondersteunt expliciete lokale SOURCE-profiel-/sensorbindingswissel zonder apparaatboot: dezelfde controller/opslag/transport, oude sessies ongeldig, oud plan alleen readback, nieuwe expliciete planapply en exacte readback nodig. HA-journal en laatste-await-conflicten blijven begrensd; safety UNKNOWN en fysieke outputs false.

Parentreview op canonicalbasis `8a00e96` plus exacte specialistdelta `c49acfd`:

- Alle 17 bronafterhashes en pakket-/archive-/bundle-/bewijshashes gecontroleerd; 519 overige canonicalbestanden bij bronmerge ongewijzigd, bestaande niet-gecommitteerde bord-/Copilotwijzigingen behouden.
- 76 gerichte native HA-/werkelijke C++ketengevallen onafhankelijk PASS; geen fysieke of echte MQTTproef.
- 20 geleverde JSactie-/loadergevallen PASS met nagebootste grenzen.
- 10 Chromiumgevallen in desktop1440×1000 en mobiel390×844 PASS: werkelijke markup/loader/liveactie + lokale jQuery/Bootstrap, HTTP en weerseam gesimuleerd. Succes, annuleren, conflict, netwerkfout, dubbelklik; één POST en overige onopgeslagen formuliervelden niet verstuurd. **Geen volledige HAfrontend-, apparaatHTTP/auth/NVS- of E32performanceacceptatie.**
- 33 notice-/shipped-/SDK-auditregressies PASS; geen licentieclosure of nieuw imagebewijs.

Primair onafhankelijk bewijs: `/home/dielessen/artifacts/open-thermostat-native-live-source-parent-20261021` (TASKFLOW, SOURCE-POSTCHECK, native/COMMANDS en HA.xml, JS.json, CHROMIUM.json, screenshots, COMMANDS.host.json). Specialistfinale receipts blijven in `/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020`; die zijn niet opgeteld bij parenttests en niet opnieuw volledig herhaald.

## Reproduceerbare opdrachten

Vanaf de nieuwe VS Code-checkout eerst `git status --short` en `git log -2 --oneline`. Pin bron via bovenstaande commit; de documentatiecommit staat erboven.

### E32-buildvoorbereiding — op deze bron nog OPEN

Bestaand hostgereedschap: PlatformIO6.2.0, Arduino2.0.17, bestaande cache `/home/dielessen/.platformio`; geen nieuwe toolchain/provider nodig. Serieel, geen upload/flash/monitor/erase:

```sh
PLATFORMIO_CORE_DIR=/home/dielessen/.platformio /home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/official-build-tools/pio-venv/bin/python -m platformio run -e e32v2 -j 1
PLATFORMIO_CORE_DIR=/home/dielessen/.platformio /home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-restart-graph-11774-20261020/official-build-tools/pio-venv/bin/python -m platformio run -e e32v2 -t buildfs -j 1
```

Niet gelijktijdig met een andere build in dezelfde checkout. Gewone finale compile/link/app/FS is nog niet aangetoond op deze bron; eerdere images/typechecks niet herlabelen. Gegevens/config/pin-/partition-/TXlocks niet wijzigen om te passen.

### Gerichte HA/C++acceptatie

Werkelijke hostcommando’s inclusief compilerflags en Pythonpad staan in `/home/dielessen/artifacts/open-thermostat-native-live-source-parent-20261021/COMMANDS.host.json` en `native/COMMANDS.json`; uitvoer in COMMAND-0/1/2.log. Vervang alleen de bronroot door de VS Code-checkout en kies een verse bewijsuitvoermap; maak eerst dezelfde C++peer met echte cJSON. Stel daarna:

```sh
export PYTHONPATH=/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-ha-candidate-20261020/.runtime/venv/lib/python3.14/site-packages
export OPENTHERMOSTAT_GRAPH_SESSION_RUNNER=/absoluut/verse-bewijsmap/graph-session-runner
export OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE=/absoluut/verse-bewijsmap/ROWS.jsonl
/home/dielessen/.openclaw/workspaces/home-assistant/artifacts/open-thermostat-ha-candidate-20261020/.runtime/python/cpython-3.14.8-linux-x86_64-gnu/bin/python3.14 -B -m pytest -q ha/tests_native/test_native_live_source.py ha/tests_native/test_native_profile_evolution.py --tb=short
```

Gepind: echte HA2026.10.2/Python3.14.8, testdeps in `ha/requirements-test-native.txt`. Geen importalias/shim of productieHA nodig. Ongewijzigde bron niet automatisch opnieuw testen; bovenstaande is reproduceerinformatie.

## Host-/containerpadverschil

Specialistpaden `/workspace/...` gelden alleen binnen zijn bestaande sandbox. De bevroren kandidaat bevat een `.git`-worktreepointer naar die mount en kan op de host niet direct met Git worden geopend. Parent heeft de geleverde Gitbundle naar `/home/dielessen/artifacts/open-thermostat-native-live-source-parent-20261021/frozen-review` hersteld en daarna de volledige `--check-source` succesvol uitgevoerd. Dit is opgelost voor de nieuwe native VS Code-worktree; de frozen specialistcheckout niet repareren/herschrijven.

## Open gates en vervolg

Huidig pakket: normale exacte samengestelde firmware/app+FS en bijbehorende releasechecks; volledige gepinde HAfrontend desktop/mobiel en werkelijke apparaatHTTP/settings/NVS blijven OPEN. Target-callgraph/gelijktijdige stack/peakheap/NVS-GC en volledige notice/licentie/source-buildclosure ontbreken. Geen snelheidsverbetering geclaimd.

Hele plan daarnaast: volledige week boven8totaleUTCtransities/veiligehorizonrefresh; >2kamers/eightzone; echte meet-/veiligheidsproducers; overige F0–F10gates uit WORKBOARD. Alle14F9modellen blijven afgewezen/defaultdisabled. Hardware/powerloss/72h/EMS/Tado/actuatoren/TX/verwarming afzonderlijk NIET vrijgegeven.

Volgende specialistactie is uitsluitend de resterende product-/GUI-/releasebewijsclosure van dit pakket op de geaccepteerde bron; geen featureuitbreiding vóór overdrachtsregistratie. Automatische projectcontrole blijft15min zolang uitvoerbare software openstaat; een controle kan later eindigen.

## Rollback

Alleen broncommit `c7d9f8c3cfda63019a230562d564a5ef53bf2e2a` terugnemen vóór afhankelijken. Bestaande SOURCE/config/journal/identiteiten/modellen/Recorder/DHW/historie behouden. Geen runtimeerase, geforceerde downgrade, installatie of upstream/publicatie uit deze overdracht afleiden.
