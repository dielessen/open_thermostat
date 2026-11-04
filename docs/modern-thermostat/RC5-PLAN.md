# rc.5 — the self-learning thermostat listens to the boiler, knows the house and says what it knows

Owner's decision, 4 November 2026: "ik wil top of the build self learning voor de 1.0 erin hebben zitten",
"het moet voor alle ketels ook kunnen werken natuurlijk", "zet het maar in gang". rc.5 is the release
candidate whose code becomes v1.0.0; it is installed **with** the acceptance capture (tools/acceptance), the
14 days run on rc.5. E32 `v1.0.0-e32v2-rc.5`, HA `1.0.0rc6`.

Everything here follows the project rules: universal (only standard EMS values that every EMS Classic and
EMS+ boiler reports; every input optional with a fallback to today's behaviour; nothing tuned to the owner's
house), no new knobs (the thermostat decides, the owner reads plain language), comfort before savings,
safety limits untouched, learned values survive restarts and updates, and every change proven on the
owner's recording (tools/replay), the soak test and the native suite before it ships.

## 1. What rc.5 adds, in one table

| # | Addition | Module (new unless noted) | Control effect | Package |
|---|---|---|---|---|
| 1 | Listening to the boiler: held targets, the boiler's own rest rhythm, absorbed heat from flow−return | `BoilerResponse` | a learned ceiling on the requested flow per outdoor band; a floor under the burner rest | P1 |
| 2 | A house model: heat loss per K outside, emitter output per K of flow; an early curve from the model | `HouseModel` (on FlowLearner's HeatModel) | the curve slope before CurveLearner has 6 windows | P2 |
| 3 | Knowing what it does not know: one knowledge figure with what is still missing | `Knowledge` | none (information) | P2 |
| 4 | Insights: yesterday against the house's own baselines, in plain language | `Insights` (baselines in the Scoreboard record) | none (information) | P2 |
| 5 | Free heat: sun, cooking and people warm a room without the boiler; shorter warm-up starts | `FreeHeat` | the optimum-start lead per room and daypart | P3 |
| — | Proof: boiler profiles for the soak test, replay scoring and a synthetic held-target recording | test/soak, tools/replay | — | P4 |
| — | Home Assistant and E32 pages: the new topic, the knowledge line, the boiler line, insights | HA integration, data/html | — | P5 |
| — | Release tooling for rc.5 / 1.0.0rc6 and a diagnosable publish step | tools/dev, scripts | — | P6 |
| — | Docs and release notes (after the code lands) | docs/ | — | P7 |

Deliberately not in rc.5 (after 1.0, no new structure needed): the weather forecast as an input, a
whole-day plan, presence patterns.

## 2. Contracts between the packages

The packages run in parallel. These contracts are fixed so that each one can code and test against them;
a package that needs to deviate says so in its report and the integrator decides. All new classes are
pure (no IO, no clock of their own, `sample()` every 10 s like the other learners), single-threaded,
header-only in `src/control/`, with GoogleTest unit tests in `test/test_native/`, and documented in a header
comment in the same voice as `FlowLearner.h` and `AutoTuner.h`.

### 2.1 BoilerResponse (P1)

```cpp
class BoilerResponse {
public:
    struct Params { /* every threshold below, with these defaults */ };
    struct Sample {
        uint64_t now = 0;
        std::optional<int64_t> utc;                 // trusted clock only
        uint8_t requestC = 0;                       // the request handed to the boiler, 0 = no heat
        bool ownRequest = false;                    // the E32 drives the boiler (active mode, confirmed)
        bool demand = false;                        // at least one usable room asks heat (RoomDemand)
        std::optional<int16_t> flowCentiC, returnCentiC, outdoorCentiC, roomMeanCentiC;
        std::optional<bool> burnerOn, hotWater;
        std::optional<uint8_t> modulationPct;
        float nominalKw = 22, kwhPerM3 = 9.77f;      // FlowLearner::Params (HA may report the boiler's)
    };
    void sample(const Sample& s);
    // The learned ceiling for the outdoor band of `outdoorCentiC` (nullopt: unknown outdoor or not learned).
    std::optional<uint8_t> ceilingC(std::optional<int16_t> outdoorCentiC) const;
    std::optional<uint32_t> restS() const;          // the boiler's own rest after a held target (median)
    std::optional<float> absorbedKw() const;        // now, from flow-return and the learned pump flow
    std::optional<float> kwPerFlowK() const;        // emitter output per K of flow above the rooms' mean
    uint16_t heldToday() const;                     // held-target events today (local day via utc)
    const char* state() const;                      // "collecting" | "learned" | "no_return" | "not_driving"
    bool addJson(cJSON* parent) const;              // "boiler":{held,rest_s,ceiling_c,absorbed_kw,kw_per_k,state} <= 140 B
    std::string stored() const; bool restore(std::string_view);  // LearnedState frame kind 'B' version 1, <= 48 B
};
```

Rules (defaults in Params):

- **Held target.** While `ownRequest && requestC > 0 && hotWater == false && demand`, an on→off edge of the
  burner with the measured flow at or above `requestC × 100 − heldMarginCentiC (200)` opens a held event; it
  closes when the burner comes back on (that off time is one *rest* observation, counted when 60..1800 s) or
  when the request ends. The first `settleMs` (10 min) of a request and a request whose lead room still has
  a shortfall ≥ 100 centi K (a warm-up) do not count: a boiler that overshoots once while filling the circuit
  is not over-asked. **Minimum modulation and still rising** counts as a held event too: `modulationPct` at
  or below `minModulationPct` (25, or the lowest value seen this boot when lower) for ≥ 3 min while the flow
  rises ≥ 200 centi K above the request.
- **Ceiling.** A request with ≥ 2 held events ("over-asked") yields the candidate `requestC − 2` for the
  outdoor band of the request's mean outdoor (6 bands of 5 K from −10 °C: <−5, −5..0, 0..5, 5..10, 10..15,
  ≥15; unknown outdoor: band 3). The band's ceiling is an EMA (α 0.3) of its candidates, raised by 1 K per 6
  heating hours in that band at a request at or above the ceiling without a held event (the season or the
  house changed: it is found out again). Never below `BoilerMinimumFlow::effective` or the plan minimum,
  never above the plan maximum. Learned from 1 over-asked request (the figure is the boiler's own
  statement), reported as "learned" from 2.
- **Rest rhythm.** The median of the last 8 rest observations (ring), reported as `rest_s`.
- **Absorption.** With the return reported: at a steady burn (burner on ≥ 5 min, no hot water, modulation
  known, ΔT = flow − return ≥ 200 centi K) the pump mass flow `m = modulation/100 × nominalKw ×
  FlowLearner::efficiency(return) / (4.186 × ΔT_K)` kg/s joins an EMA (α 0.2); from then `absorbedKw = m ×
  4.186 × ΔT_K` whenever the burner is on for heating, also when the modulation is not reported. `kwPerFlowK`
  = EMA (α 0.2) of `absorbedKw / ((flow − roomMean) / 100)` over steady burns with `flow − roomMean ≥ 500`.
  Without the return the state is "no_return" and both stay nullopt; nothing else degrades.
- A boiler product id change (FlowLearner forgets its minimum) also forgets this state; the integrator wires
  that. Hot water, a gap > 60 s and a request of another controller (not `ownRequest`) close open events
  without counting.

Consumption, wired by P1 in minimal hunks that the integrator merges:

- `FlowPolicy::apply()`: after `want` is chosen and before `bound()`:
  `if (settings_.applyLearned && in.ownRequest && ceiling) want = std::min(want, std::max<int>(*ceiling, lo));`
  with a new `Inputs` field `bool ownRequest` and `std::optional<uint8_t> ceilingC`. The flow document
  (`addStatus`/`addSummary`, "flow") gains `"ceiling_c": n|null` and the learned state `"held"` when the
  ceiling was the binding bound. `optimumStart()` leads and learned flows respect the same cap.
- `HeatingController::effectiveTuning()`: a pure helper `RestFloor::apply(ControlTuning&, std::optional<uint32_t> restS, bool coldNow)`
  raises `minOffS` to `min(restS, 900)` unless any usable room is more than 30 centi K below its target
  (comfort first; the floor is never stored, AutoTuner keeps tuning the knob itself).
- `HeatingController::stepHeating`: `boilerResponse_.sample(...)` from the ActiveHeatView (flow, return,
  burner, hot water, modulation, outdoor via `learnerOutdoor`, the guard's command as the request,
  `activeGuard_.outputActive()` as ownRequest, the rooms' mean temperature and any demand).
- Persistence: a new frame kind `'B'` in `LearnedState`/`LearnedStore` (global record), ≤ 48 B; firmware
  before rc.5 skips it. The NVS budget test (`test_control_partition_budget.cpp`, the owner's-unit model)
  must still pass with ≥ 200 free entries.
- Telemetry: the "flow" document (`fw/telemetry/flow`, soft limit 1024 B) carries `"boiler":{...}`; the
  worst-case test in `test_heating_telemetry.cpp` is extended.

### 2.2 HouseModel, Knowledge, Insights and the insight topic (P2)

```cpp
class HouseModel {   // on FlowLearner::HeatModel per room, Scoreboard days and (optional) BoilerResponse
public:
    struct Inputs {
        const FlowLearner* learner = nullptr;               // heatModel(i) per plan room, emitter, readiness
        const Scoreboard* board = nullptr;                   // yesterday's heating kWh and degree-days
        std::optional<float> kwPerFlowK;                     // BoilerResponse::kwPerFlowK(), when learned
        const RoomPlan* plan = nullptr;
    };
    void update(const Inputs&);                              // once per hour and at the day change
    std::optional<float> uaKwPerK() const;                   // house heat loss per K (median of the rooms' UA, else gas/degree-day)
    std::optional<float> kwPerFlowK() const;                 // emitter output per K (BoilerResponse, else P = C(rate + b dT) over heating segments)
    std::optional<float> slope() const;                      // WeatherCurve slope implied by UA / kwPerFlowK, within [minSlope, maxSlope]
    const char* state() const;                               // "collecting" | "learned"
    bool addJson(cJSON* parent) const;                       // "house":{ua_kw_per_k,kw_per_flow_k,slope,state} <= 110 B
};
```

- `FlowPolicy` takes the slope in this order: CurveLearner learned → HouseModel (from 3 local days with gas
  and degree-days, or 2 rooms with a learned UA) → design slope. New `Inputs` field
  `std::optional<float> houseSlope`; `flow.curve.slope_source` gains the value `"house"`.
- `Knowledge::percent(const FlowLearner&, const CurveLearner&, const ArrivalLearner&, const BoilerResponse*, const HouseModel&, const RoomPlan&)`
  → 0..100 and `missing` keys. Weights over the active plan rooms: warm-up rates ready 25, cooling rate
  known 15, curve slope learned 15, arrival trusted 15, boiler minimum learned 10, boiler response learned
  10, house model learned 10. Missing keys: `warmup:<room id>`, `cooling:<room id>`, `arrival:<room id>`,
  `curve`, `boiler_minimum`, `boiler_response`, `house` (at most 8 in the payload, the rest counted in
  `"more": n`).
- `Insights`: baselines as EMAs over local days (α 0.2, judged from the 5th day) of gas per degree-day
  (kWh/DD), heating starts per heating hour, heating hours per degree-day, and per room the warm-up minutes
  per K (AutoTuner's `Learned::minutesPerC`). At the day change yesterday is judged against the baseline
  before it is folded in: a deviation beyond 30 % (floors: 0.5 kWh/DD, 1 start/h, 0.5 h/DD, 15 min/K) makes
  one item `{"kind": "gas_per_dd_up"|"gas_per_dd_down"|"starts_up"|"hours_per_dd_up"|"warmup_slower", "pct": n, "room": id?}`;
  at most 4 items, kept until the next judgement; a day without heating (< 1 heating hour) neither judges nor
  folds. Never a Problem, never a Repair: information only. Baselines live in the Scoreboard record
  (P2 owns `Scoreboard.h`): `storedMaxBytes` may grow to 304 B (16 NVS entries); the budget test is updated.
- Telemetry: a new topic `fw/telemetry/insight` (`HeatingStateTopics`, a fifth summary slot in
  `TelemetryPublisher::summary()` like `scoreboard`, retained, every 5 min):
  `{"knowledge":{"pct":70,"missing":[...],"more":0},"house":{...},"boiler":{...},"insights":[...]}`,
  worst case ≤ 700 B (a new case in `WorstCaseSummaryPartsEachStayWithinTheSoftLimit`). The `"boiler"`
  object is the same `BoilerResponse::addJson`; until P1 lands P2 emits it from a stub with the same shape.
- Persistence beyond the Scoreboard record: none (Knowledge is derived; HouseModel recomputes from the
  learners' state each boot).

### 2.3 FreeHeat (P3)

```cpp
class FreeHeat {   // per plan room, six 4-hour local dayparts
public:
    struct RoomSample { std::optional<int16_t> temperatureCentiC; bool heatDelivered = false; };
    void sample(uint64_t now, std::optional<int64_t> utc, std::optional<int16_t> outdoorCentiC, const RoomSample* rooms, size_t count);
    std::optional<float> rateKPerH(size_t room, int localHour) const;   // expected free rise, count >= 5
    uint32_t shortenLeadS(size_t room, int localHour, uint32_t leadS, float warmupKPerH) const; // lead x max(0.5, 1 - free/warm)
    bool addJson(cJSON* parent, size_t room) const;   // "free_heat":{"rate":[6 x 0.1 K/h or null],"n":[6],"applied_min":n} <= 90 B
    std::string stored() const; bool restore(std::string_view, const RoomPlan&);  // frame kind 'F' v1, rooms by id
};
```

- Evidence: a window in which no heat reached the room (the burner was off for heating, or the request was
  0, for at least the emitter's coast time: floor 2 h, radiator 30 min, as `FlowLearner::Params`) and the
  room rose ≥ 20 centi K over ≥ 30 min with fresh readings and no step > 30 centi K between samples (a
  source change): the rise rate (K/h) joins the daypart's EMA (α 0.3) and count. A fall or a flat window
  counts a zero. Hot water does not deliver heat to a room.
- Applied in `FlowPolicy::optimumStart()` (a minimal hunk): the lead is shortened for the daypart of the
  program's rise, only with `count >= 5`, never below half, reported per room as `applied_min`. The
  ArrivalLearner keeps judging the result, so a wrong estimate is corrected the usual way.
- Per-room telemetry (`learnedRoomTelemetry`, `fw/telemetry/learned/<room>`) gains `"free_heat"`; the
  1000 B budget test, the fuzz and the soak payload checks are extended by P3.
- Persistence: frame kind `'F'`, at most 3 dayparts with evidence per room (the busiest), ≤ 360 B in the
  global record; the NVS budget test must keep ≥ 200 free entries on the owner's unit model.

### 2.4 Proof (P4)

- `test/soak/soak.cpp`: boiler profiles selectable per scenario: `no_return` (no return temperature),
  `holding` (the boiler holds its target up to +5 K, burner off, its own anti-cycle 10 min — the "0Y"
  boiler), `radiators_only`, `floor_only`, and the existing store keep-warm; new scenarios
  `chain-ams-holding` and `chain-ams-no-return` (60 days, both flow options on). Invariants: no request
  above the learned ceiling once learned while the E32 drives; no lead shortened below half; payload bounds.
- `tools/replay/score.py <replay json> [<base json>]`: starts per heating hour, mean request / flow /
  return while heating, heating kWh (the learner's estimate), arrival errors, held events and the ceiling
  per band when present; prints a before/after table. `tools/replay/synth.py`: a CSV in the replay format
  of a holding boiler driven by the recorded requests of `house-*.csv` (the real recording has few held
  events), so P1's effect is measurable. Fixture checks in `tools/replay/test_replay.py`.
- The replay driver (`replay.cpp`) wires `BoilerResponse`, `HouseModel` and `FreeHeat` as
  `HeatingController` does; until the modules exist the hooks compile out (`__has_include`), and the
  integrator switches them on.

### 2.5 Home Assistant and the E32 pages (P5)

- `heating_link.py`: `INSIGHT_TOPIC = "fw/telemetry/insight"`, hub-only, merged into the summary as
  `insight_doc` the way `scoreboard_doc` is.
- Entities (no new devices; cleanup rules of `native_entity_cleanup` apply): on the hub device one sensor
  **Knowledge** (`%`, attributes: the missing items as sentences, `more`), one sensor **Boiler response**
  (state: `collecting` / `learned` / `no_return` / `not_driving`; attributes: held today, rest, ceiling,
  absorbed kW, kW per K, and a plain sentence). Insights: a persistent notification per item (info; replaced
  when the item changes, dismissed when it disappears) and a list on the Learning view. No Repairs.
- Dashboard (`dashboard.py`): Learning view: a knowledge tile ("The E32 knows your house: 70 %") with the
  missing sentences, the boiler sentence, the insights list; Overview: nothing new.
- E32 pages (`heating.html`, `index.html`, `ui-messages*.js`): the Learning card gets the knowledge line
  and the missing sentences, the boiler line, and an insights list; the per-room learned detail shows free
  heat in words ("Afternoon sun warms this room about 0.4 °C per hour").
- Texts (EN source, NL and PL translations, UX-GLOSSARY vocabulary): missing-key sentences, insight
  kinds, boiler states. Examples: `warmup:<room>` → "It still has to see how fast {room} warms up";
  `boiler_response` → "It is still listening to how your boiler holds its temperature"; `gas_per_dd_up` →
  "Yesterday used {pct} % more gas per degree of cold than usual"; the boiler sentence → "Your boiler holds
  about {flow} °C and rests {rest} minutes; the E32 asks at most {ceiling} °C now".
- Tests: fixture payloads for the new topic, entity tests, dashboard tests, browser tests for the pages
  (`test/browser-tests.txt`), translation completeness.
- Owner's wish (4 Nov, "dat is wel mooi om te zien"): a heating-curve chart "Water temperature by outdoor
  temperature" on the E32 Heating page (inline SVG from the flow document) and on the HA Learning view (a
  sixth Lovelace card `heating-curve-card.js`, versioned like the others; P6's card list is data-driven):
  the standard line (dashed, the design slope), the learned line (solid, when `slope_source` is "learned" or
  "house"), the point of now and the frost point at −10 °C; legend EN/NL/PL "Standard", "Learned for your
  house", "Now".

### 2.6 Release tooling (P6)

- `tools/dev/prepare_rc5.py` from `prepare_rc4.py`: E32 `v1.0.0-e32v2-rc.5`, HA `1.0.0rc6`, previous
  rc.4 / 1.0.0rc5; `RC4-UPDATE-GAP-<date>.json` (rc.4 installed by the owner on 4 Nov 2026 at 13:38 UTC
  through the Home Assistant update entity, no capture, no receipt), `RC5-PUBLICATION-EXCEPTION-<date>.json`
  (draft until the owner's statement, `--rebind` as before), `RC5-KANDIDAAT.json`, owner instruction, the
  five card URLs, release.json / manifest.json, the notes prepended from the drafts, inventory refresh. Tests
  on throwaway trees judged by the real gate; **not run on the real tree**.
- `tools/acceptance/install-config.json`: tag rc.5, previous rc.4, HA 1.0.0rc6, previous 1.0.0rc5 — in
  the version commit only (the prepare script writes it).
- `scripts/publish_github_release.py`: `--verbose` (on in the workflow) prints every gh command, its exit
  code and stderr to the job log, so a first-attempt failure like rc.4's is diagnosable; the failure text
  names the step. Tests kept green.
- `tools/replay/README.md`: the rc.5 baseline paragraph template (the integrator fills the figures).

### 2.7 Docs and notes (P7, started by the integrator after P1–P5 landed)

README (what it does: three sentences), USER-GUIDE (Learning section, insights, the boiler line), the
release notes drafts (`RELEASE-1.0-RC5-NOTES-DRAFT.en.md`, `HA-RC6-NOTES-DRAFT.en.md`, ≤ 6000 B rendered),
the Dutch PDF manual (tools/dev/manual), NEXT-RELEASE.nl.md.

### 2.8 The Home Assistant dashboard redesign (P11 house card, P12 views; owner 4 Nov: "alles moet gewoon in de volgende release komen")

The review of 4 Nov (RC5-DASHBOARD-SPEC.md, written on Fable at the owner's request) found the duplicate gas-per-day chart,
a duplicate "Yesterday", lone headings over hidden cards (the owner's "open ruimte") and a cluttered Boiler view, and
proposes a calm, striking dashboard: a house card hero on the Overview (a new custom card `house-card.js`), a Boiler view
ordered by need (Now, Advice, Today and this week, Hot water, Last 24 hours, What the boiler reports, Boiler settings), one
gas story, "Yesterday" once (on Learning), whole-section visibility everywhere, no HACS frontend dependencies and no entity
id changes. P11 builds the house card (section 7 of the spec, its browser test, the registration and the versioned URL
`/open_thermostat/house-card-1.0.0rc5.js`); P12 restructures the views (sections 1-6, 8, 10). Both start from the pages
package's branch `rc5-ha-pages` and keep its Learning additions; the docs follow-ups of spec section 13 go to the
integrator after P5, P11 and P12 landed.

## 3. Proof before integration and before the release

Per package: the native suite green on a WSL-disk copy; new unit tests; the replay on the owner's
recording (`out/replay-data/house-20261030-20261102.csv` + `plan.json` of the main checkout, read-only)
before and after, with the differences explained in the report; soak `smoke` green, and `full` for P1–P4.
Integration (the integrator): the full `final_check.sh` with `--stress 2` and `FUZZ=1`, the telemetry
worst-case tests, the NVS budget test, the 1000 B per-room test, the browser tests under load, the replay
baseline paragraph, HA tests. Release: the version commit, the owner's statement for the exception (the
fourth in the rc series), push, CI, tags, main, HACS; then the attended install with capture.

## 4. Rules for every package

- Work in your own worktree `C:\Users\m.dielessen\Downloads\open_thermostat-rc5-<package>` on branch
  `rc5-<package>` from `rc5-integrate`; build and test on a WSL-disk copy (`/tmp/copytree.sh <worktree>
  ~/.cache/openthermostat-final-check/tree-rc5-<package>`), never on /mnt/c; `pio` at `~/venvs/pio/bin/pio`,
  HA venv `~/venvs/ha`, node `~/node/bin`.
- Never touch the E32, Home Assistant, MQTT or GitHub; no pushes; no bare `git stash`; LF line endings;
  commit with explicit paths and English messages ending in your own `Co-Authored-By` line; a WIP commit at
  least every two hours.
- Own only the files named in your package; a needed change elsewhere goes into a minimal, clearly commented
  hunk and is listed in the report for the integrator.
- Plain-language texts (UX-GLOSSARY.md): no "shadow", "digest", "schema"; "E32", "Smart warm-up", "Weather
  compensation", "water temperature".
- Report in `C:\Users\M28B4~1.DIE\AppData\Local\Temp\claude\c--Users-m-dielessen-Downloads-open-thermostat-vscode-20261021\5e1d91b9-fb77-48ec-a14c-4af0a9640a44\scratchpad\rc5\P<n>-report.md`:
  what was built, the evidence (test counts, replay before/after, soak), what deviates from this plan and why,
  and the hunks outside your files.
