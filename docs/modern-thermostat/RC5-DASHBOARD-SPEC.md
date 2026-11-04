# Dashboard redesign spec (HA 1.0.0rc6 / E32 rc.5) — implementation notes for an agent

Companion of `dashboard-voorstel.nl.md` (the owner's proposal). Scope: the generated Lovelace dashboard in
`ha/config/custom_components/open_thermostat/dashboard.py`, its text tables (EN/NL/PL), one new custom card, the
dashboard tests and the browser fixture. No entity ID changes, no E32 changes, no new HACS resources.

Base: branch `rc5-ha-pages` (worktree `open_thermostat-rc5-ha-pages`), which already adds to the Learning view the
knowledge card (`custom:openthermostat-knowledge`), the boiler sentence, the insights list and the heating-curve card
(`custom:openthermostat-heating-curve`, module `frontend/heating-curve-card.js`, URL
`/open_thermostat/heating-curve-card-1.0.0rc5.js`). Keep all of it. Line numbers below are those of `rc5-integrate`
(`dashboard.py`, 2006 lines); in `rc5-ha-pages` the same code sits about +17 lines lower up to line 820 and +49 to +54
lines lower after it (the TEXT additions and `_knowledge_section`).

## 0. Findings the spec answers

1. **Gas per day is on the Boiler view twice (confirmed).**
   - `_hot_water_use_cards`, lines 980–987: `statistics-graph` titled `t["gas_per_post"]` ("Gas per day: heating,
     tapping, keeping warm"), entities `heating_gas` + `tapping_gas` + `keep_warm_gas`, bar, period day, 7 days;
     appended to the Boiler view's "Hot water" section at lines 1892–1897; visible once tapping or keep-warm gas > 0.
   - `_energy_section`, lines 823–836: section heading `t["gas_per_day"]` ("Gas per day") with a `statistics-graph`
     of `heating_gas` + `hot_water_gas` + `keep_warm_gas`, bar, period day, 7 days; added to `boiler_tail` at lines
     1608–1610; always shown with the sensors.
   - Gas also appears as text in `_yesterday_section` (line 853–854, "Gas: heating X, hot water Y") on the Boiler
     view and in `_scoreboard_section` (line 922, "Gas for heating (estimate)") on the Learning view.
2. **Two "Yesterday" sections** with the same heading key `t["yesterday"]`: `_yesterday_section` (Boiler view, the
   daily summary, line 865) and `_scoreboard_section` (Learning view, line 931).
3. **Lone headings (holes).** Sections whose heading stays while every card under it hides: the boiler groups
   (`_boiler_sections`, lines 1881–1885: the entities card hides with `_any_known`, the heading has no visibility),
   "Last 24 hours" (lines 1898–1909: each graph hides unless *all* its series are known, `shown()`), the "Boiler" now
   section (lines 1596–1603) and the note `dhw_use_note` (line 989: shown even when the timeline and chart are
   hidden). Sections that already hide as a whole (do the same everywhere): `_advice_section`, `_learned_sections`,
   `_scoreboard_section`, `_knowledge_section`.
4. **Clutter.** The Boiler view has up to 10 sections, 7 charts and 3 notes; the glance figures (is it heating, water
   temperatures) are rows in the third section; "Thermostat on the bus" is trial-run material.
5. **Owner's boiler (Bosch EasyControl Adapter in front of a Nefit EcomLine HRC 22).** No pressure, no selected flow
   temperature, no burner/3-way-valve bits, no boiler counters, no EMS+ counters, no DHW flow, no outdoor from the
   boiler (`test_dashboard_redesign.LIVE_FIELDS`, USER-GUIDE.md line 168). Nothing may be built that can only show
   "unknown" for such a boiler without hiding as a whole.
6. Stale text: `estimates_empty` says "The Heating page estimates the gas per day" — there is no Heating page; the
   view is "Overview" (path `heating`) and the gas is on the Boiler tab.

## 1. Cross-cutting rules (apply in every view)

- **Section visibility.** Every section gets `section["visibility"] = _any_known([...])` over the entities its cards
  depend on, built by a new helper `_section_known(entities, *cards)` (= `_section(*cards)` plus the visibility).
  A heading never stands over nothing. The layout test keeps its two scenarios (all shown / all conditional hidden).
- **Half-width cards come in pairs that share one visibility condition list** (as `_tiles` does today). The odd one
  out is wide (`_wide`). Half-width card types now: `tile`, `button`, `statistic`, `gauge`. Always set
  `grid_options` explicitly on `statistic` (`{"columns": 6, "rows": 2}`) and `gauge` (`{"columns": 6, "rows": 2}`).
- **Wide cards may hide individually** (a hidden 12-column card leaves no hole).
- **One icon per concept**, extend `ICONS`: `heating` `mdi:fire`, `hot_water` `mdi:faucet`, `gas` `mdi:meter-gas`,
  `burner_starts` `mdi:counter`, `burner_time` `mdi:timer-outline`, `house` `mdi:home-thermometer`, `learning`
  `mdi:school-outline`, `boiler` `mdi:water-boiler`, `week` `mdi:chart-bar`, `now` `mdi:water-boiler`; keep `flow`,
  `return`, `modulation`, `pressure`, `dhw`, `code`, `max_ch`. Use the table, never ad-hoc icons.
- **Notes:** at most one per section, first sentence shown, the rest behind "More" (`_note`), and a note carries the
  visibility of the card it explains.
- **Colours:** native tiles use theme colour names (`deep-orange` heating, `blue` hot water, `grey` idle, `red`
  problem, `teal` learning). Custom cards: status colours from HA's CSS variables as in `room-status-card.js`
  (`--state-climate-heat-color`, `--info-color`, `--error-color`, `--disabled-text-color`); chart series colours from
  the E32 palette as in `heating-curve-card.js` (`#00876f/#b5600c/#5b57d1`, dark `#239c8a/#c97a2c/#7f7be6`); dark
  mode via `hass.themes.darkMode` (the `ha-card.dark` pattern). Status colours never colour a series and vice versa.
- **Texts:** all headings/names via `TEXT[lang]`; every new key in EN, NL and PL; the key-set test extended to PL.
  Card-internal texts of a custom card live in `strings.json` + `translations/{en,nl,pl}.json` under the primary
  entity's `state_attributes.card.state.*` (the pattern of the knowledge card), EN fallback inside the JS.
- **Glossary:** docs/UX-GLOSSARY.md words only ("E32", "Smart warm-up", "Weather compensation", "water temperature",
  "trial run"); never "shadow", "digest", "schema", "flow setpoint".

New TEXT keys (EN / NL / PL):

| key | EN | NL | PL |
| --- | --- | --- | --- |
| `today_week` | Today and this week | Vandaag en deze week | Dziś i w tym tygodniu |
| `gas_heating_today` | Gas for heating today | Gas verwarmen vandaag | Gaz na ogrzewanie dziś |
| `gas_hot_water_today` | Gas for hot water today | Gas warm water vandaag | Gaz na ciepłą wodę dziś |
| `starts_today` | Burner starts today | Branderstarts vandaag | Starty palnika dziś |
| `burner_today` | Burner time today | Brandertijd vandaag | Czas pracy palnika dziś |
| `boiler_values` | What the boiler reports | Wat de ketel meldt | Co zgłasza Twój kocioł |
| `who_controls` | Who controls the boiler | Wie regelt de ketel | Kto steruje kotłem |
| `yesterday_figures` | Yesterday in figures | Gisteren in cijfers | Wczoraj w liczbach |
| `dhw_target_short` | Hot water target | Doel warm water | Cel ciepłej wody |
| `other_rooms` | Other rooms | Overige ruimtes | Pozostałe pomieszczenia |

Removed keys: `gas_per_post` (and its chart), `control` (replaced by `who_controls`), `learning_how` (folded into a
note). `estimates_empty`: replace "The Heating page" by "The Boiler tab" (EN/NL/PL). Keep every other key (the
merged Yesterday card reuses `day_*`, `scoreboard_*`, `day_none`).

## 2. Overview (path `heating`)

Sections (both `column_span: 2`, as today):

**House** (`t["house"]`, icon `house`):
1. `heading` House.
2. **House card** (new, §7): `{"type": "custom:openthermostat-house", "grid_options": {"columns": 12}, ...keys}`.
   Config keys, each present only when the entity is in the registry (the card draws what it has):
   `request` (hub `heat_request`), `activity` (hub `boiler_activity`), `heating` (field `heating_active`),
   `flow` (`essential("flow")`), `hot_water` (field `dhw_active`), `taps` (hub `dhw_taps_today`),
   `gas` ([hub `heating_gas`, hub `hot_water_gas`] — those that exist), `starts` (hub `daily_burner_starts`),
   `mode` (select `house_mode`), `problem` (hub `heating_problem`),
   `rooms` ([{"entity": room reason sensor, "name": room name}] — **only when exactly one E32 room is active**;
   otherwise omitted). The card needs at least `request` or `activity`; without both, no house card and the
   existing `_wanting_card` stays as the fallback.
3. `tile` house mode, wide, `features: [{"type": "select-options"}]`, color teal (unchanged).
4. `_holiday_card` (unchanged).
Deleted from this section: `_wanting_card` (absorbed by the house card's status strip and Heating figure), the
problem `tile` and the "All reasons" markdown (absorbed: the strip turns red, shows the first `reasons` item, a tap
navigates to `/config/repairs`, "All reasons" is a `<details>` inside the card).
Section visibility: none needed (the house mode tile and the card are always built when their entities exist).

**Rooms** (`t["rooms"]` or, when one room is inlined, `t["other_rooms"]`):
- one `custom:openthermostat-room-status` per E32 room **not** inlined in the house card (unchanged card); the tile
  fallback for a registry without the Reason sensor stays.
- Rule: `active = [rooms whose hub status state != "inactive"]`; if `len(active) == 1` that room goes into the house
  card's `rooms` and the Rooms section lists only the remaining rooms (heading `other_rooms`); the section is
  omitted when none remain. Add `room.get("state")` to `_signature` (line 1302) so switching a room on or off
  rebuilds the dashboard.

Phone order: House card → house mode → holiday → other rooms. Desktop: the same, both columns wide.

Effort: 2.0 days (1.25 card + browser test, 0.5 generator + Python tests, 0.25 translations).

## 3. Rooms (path `rooms`)

Unchanged structure (`_room_section`). Two changes:
1. The "Measured by E32" tile (line 1804) only when the E32 measures something other than the thermostat shown:
   `measured_elsewhere = thermostat is not None and any(s for s in plan_room.sources if not (s.type == "ha" and
   s.id == thermostat))`; a room whose only source is the thermostat it follows shows the number once (the dial).
2. `heading` badges capped to the order demand, status, off, valve problem, battery (as today) — no change in code,
   but the tests pin that no new badge is added.
Effort: 0.25 day.

## 4. Week program (path `week-program`)

Unchanged (panel view with `custom:openthermostat-e32-week`).

## 5. Boiler (path `boiler`) — section list and cards

Order of sections (phone top to bottom; desktop 2 columns, `dense_section_placement` as today):

### 5.1 Now (`t["now"]`, icon `now`)
1. `heading` Now.
2. `_boiler_status_card` (the display code in words; visibility `_known(code)`) — unchanged.
3. Activity tiles, **wide**, exactly one visible by state of hub `boiler_activity` (entity `activity`):
   - `{"type": "tile", "entity": activity, "name": t["boiler_now"], "icon": "mdi:fire", "color": "deep-orange",
     "visibility": [{"condition": "state", "entity": activity, "state": ["heating"]}]}`
   - same with icon `mdi:faucet`, color `blue`, states `["tapping", "keep_warm", "charging", "hot_water"]`
   - same with icon `mdi:water-boiler`, color `grey`, states `["idle"]`
   Without `boiler_activity` (older integration): two wide tiles on field `heating_active` (`on` deep-orange / `off`
   grey, name `t["state_heating"]`).
4. Pair `[flow tile | return tile]`: `_tile(flow, t["flow_short"], ICONS["flow"])`, `_tile(return, t["return_short"],
   ICONS["return"])`, both `visibility: _known(flow)`; no return entity → flow wide.
5. Pair `[gauge | starts last hour tile]`: `{"type": "gauge", "entity": modulation, "name": t["modulation"], "min": 0,
   "max": 100, "needle": false, "grid_options": {"columns": 6, "rows": 2}}` (no `severity`: burner power carries no
   good/bad meaning) and `_tile(hub["burner_starts_last_hour"], t["starts_hour"], ICONS["burner_starts"])` with
   `grid_options: {"columns": 6, "rows": 2}` so the pair is one row; both `visibility: _known(modulation)`. No
   starts entity → gauge paired with the pressure tile where the boiler reports pressure, else the gauge wide.
Section visibility: `_any_known([code, activity or heating_active, flow, modulation])`.
Deleted: the `entities` card with the starts row (line 1600), the "Hot water today" subtitle and rows (→ 5.4).

### 5.2 Advice (`_advice_section`) — unchanged, second.

### 5.3 Today and this week (`t["today_week"]`, icon `week`)
1. `heading`.
2. Pair of `statistic` cards (period calendar day, `stat_type: change`):
   `{"type": "statistic", "entity": heating_gas, "name": t["gas_heating_today"], "icon": ICONS["gas"],
   "period": {"calendar": {"period": "day"}}, "stat_type": "change", "grid_options": {"columns": 6, "rows": 2}}` and
   the same for `hot_water_gas` with `t["gas_hot_water_today"]`; both `visibility: _known(heating_gas)`; only
   heating gas → wide.
3. Pair of `statistic` cards: hub `daily_burner_starts` (`t["starts_today"]`, icon `burner_starts`) and hub
   `daily_burner_time` (`t["burner_today"]`, icon `burner_time`), period day, change; both
   `visibility: _known(daily_burner_starts)`.
4. `statistics-graph` **Gas per day** (the one gas chart): `title: t["gas_per_day"]`, `chart_type: bar`, `period:
   day`, `days_to_show: 7`, `stat_types: ["change"]`, entities = `[heating_gas, tapping_gas, keep_warm_gas]` named
   `gas_heating`/`gas_tapping`/`gas_keeping_warm` when all three exist, else `[heating_gas, hot_water_gas]` named
   `gas_heating`/`gas_hot_water`; `visibility: _known(heating_gas)`.
5. `statistics-graph` **Burner hours per day**: `daily_burner_time`, `title: t["burner_per_day"]`, bar, day, 7,
   change; `visibility: _known(daily_burner_time)`.
6. `_note`: the existing measured/estimate template (`gas_measured` / `gas_estimate` by the `estimate` attribute) with
   `gas_note` behind More; `visibility: _known(heating_gas)`.
Section visibility: `_any_known([heating_gas, daily_burner_starts])`.
Deleted: `_energy_section` as a section (rewrite it into this section's builder, keep the function name for
`test_energy_use`/`test_dhw_keep_warm` or update those tests), the `gas_per_post` chart in `_hot_water_use_cards`
(lines 980–987), the "Yesterday" section on this view (`_yesterday_section` moves, §6).

### 5.4 Hot water (`t["group_dhw"]`, icon `hot_water`)
1. `heading`.
2. Pair `[measured dhw temperature tile | target tile]`: `_tile(field measured_dhw_temperature, t["dhw"],
   ICONS["dhw"])` and `_tile(field reported_dhw_target or selected_dhw_temperature, t["dhw_target_short"],
   "mdi:thermometer-water")`; both `visibility: _known(measured_dhw)`; no target → measured wide.
3. `_known_entities_card([dhw_taps_today, dhw_keep_warm_today, dhw_burner_time_today])` (rows, as today).
4. `history-graph` 24 h: `boiler_activity` (name `t["activity"]`) + field `heating_active` (name
   `t["state_heating"]`), `title: t["activity_timeline"]`; `visibility: _known(activity)`.
5. `_note(t["dhw_use_note"], visibility=_known(activity))`.
Section visibility: `_any_known([measured_dhw, dhw_taps_today, activity])`.

### 5.5 Last 24 hours (`t["history_24h"]`, icon `mdi:chart-line`)
The three graphs as today (`flow_graph`, `modulation_graph`, `dhw_graph`), each `visibility: _any_known(series)`
instead of all-known (`shown()`), so one missing series no longer hides a graph; section visibility
`_any_known(all series)`. Legacy (no boiler fields) branch unchanged.

### 5.6 What the boiler reports (`t["boiler_values"]`, icon `boiler`)
One section, three `entities` cards with a `title` (`group_heating`, `group_dhw`, `group_status`), the conditional
rows of `boiler_group()` as today (`HIDDEN_STATES` kept), each card `visibility: _any_known(rows)`; the first card
followed by `_note(t["boiler_note"])` with the same visibility. Section visibility `_any_known(all rows)`. The
`counters` group (boilers that report counters) is a fourth card here with title `group_counters`.

### 5.7 Boiler settings (`t["group_settings"]`, icon `mdi:cog-outline`)
`_known_entities_card(settings rows)`; section visibility `_any_known(rows)`. Last on the view.

Moved out: group `thermostat` → Diagnostics (§8); `_boiler_sections` returns `(sections, raw, thermostat_rows)`.

Resulting heading list for the owner's boiler (all known): Now, Advice (when any), Today and this week, Hot water,
Last 24 hours, What the boiler reports, Boiler settings. Effort: 1.0 day.

## 6. Learning and settings (path `learned`)

Order:
1. `_knowledge_section` (rc.5) — unchanged, first.
2. **Yesterday in figures** (`t["yesterday_figures"]`, icon `mdi:scoreboard-outline`): one section built by a new
   `_yesterday_figures(t, rooms, names, house, summary, burner_time?, missed, gas_unit)` that concatenates the
   scoreboard template (`_scoreboard_section` content) and the daily-summary template (`_yesterday_section` content
   without the `**{{ d.date }}**` header; keep `day_partial`, `day_none` only when the scoreboard has nothing either),
   then the `statistics-graph` **Missed comfort per day** (`daily_missed_comfort`, `t["missed_per_day"]`, bar, day,
   7, change, `visibility: _known(missed)`), then `_note(t["scoreboard_note"])`. Section visibility:
   `_any_known(scoreboard entities + [daily_summary])`. Delete `_yesterday_section` and `_scoreboard_section` as
   separate sections (keep their template builders as functions the merged card calls).
3. `_learned_sections` (three sections) — unchanged, except the "How it learns" note (`learning_note` +
   `advice_only` details, lines 1663–1669) becomes the last card of the first learned section ("What the thermostat
   has learned"), with its `_known(learning_entity)` visibility; no separate section.
4. Smart warm-up and weather compensation — unchanged (switches, design flow, heating-curve card, source, links).
5. **Who controls the boiler** (`t["who_controls"]`): the former "Boiler control" section unchanged in content
   (explain card, cycling card, readiness tile, comparison link).
Effort: 0.5 day.

## 7. The new custom card: `frontend/house-card.js`

- Type `custom:openthermostat-house`; constants `HOUSE_CARD_URL = "/open_thermostat/house-card-1.0.0rc5.js"` and
  `HOUSE_CARD_TYPE` in `room_overview.py` beside the room card's `CARD_URL` (version string = `manifest.json`
  version, bumped with every release like the other card URLs; old URLs go to the legacy list when renamed).
  Register in `week_planner.card_modules()` (line 132–137) and the static path tuple (lines 205–207:
  `(HOUSE_CARD_URL, "house-card.js")`). `getGridOptions() → {columns: 12, min_columns: 12}`, `getCardSize() → 5`.
- **Draws** (one `ha-card`, padding 16 px, 12 px under 480 px):
  1. Status strip: a 6 px left bar + icon + one line in the state colour: heating (`--heat`): "Heating · water
     {flow} °C" (flow from `flow` when known); hot water (`--info`): the activity's own translated state
     (`hass.formatEntityState`); idle (`--off`): "Boiler resting"; problem (`--error`, wins): "Attention: {first
     reason}", `cursor: pointer`, tap → `history.pushState(null, "", "/config/repairs")` + `location-changed`
     event; a `<details>` "All reasons" with every `reasons` item. Right-aligned chip: the house mode's translated
     state (`mode`), tap → more-info of the select (`hass-more-info`). Second line when `request` has rooms wanting
     heat and the room is not inlined: "{n} rooms want heat" / "1 room wants heat" + "Boiler request {flow} °C".
  2. Figures row (2 columns on phones, 4 on ≥ 720 px): optional **Room** (when `rooms` has one entry: name,
     `temperature → setpoint` from the Reason sensor's attributes as the room card does, value ≥ 2.2 rem semibold,
     proportional figures, the reason sentence under it in the room card's wording via
     `entity.sensor.room_reason.state_attributes.line.state.*`, presence/window icons); **Heating** ("on · {flow} °C"
     / "off", from `activity`/`heating`/`request`); **Hot water** ("{n} taps today" from `taps`, "running now" while
     the activity is tapping/charging/hot_water); **Gas today** (sum of today's `change` of the `gas` entities, unit
     from the entity, 1 decimal, with a 7-day sparkline: 2 px line in `--oth-1`, last point r=4 with a 2 px surface
     ring, no grid); **Burner starts today** (today's `change` of `starts`). A figure without its entity is left out;
     one whose value is not known yet shows "—".
  3. Today strip: a 14 px bar from local midnight to now, segments by `activity` history: heating `--heat`, tapping
     `--info`, keep_warm/charging the same hue lighter (`color-mix(in srgb, var(--info) 55%, var(--card-background-color))`),
     hot_water `--info`, idle = surface; 2 px surface gaps between touching segments; ticks 00 · 06 · 12 · 18; a
     legend line "Today: heating · hot water · keeping warm". `title` tooltips per segment with start–end times; the
     same in an `aria-label` sentence.
- **Data:** states from `hass.states` (render only on a state/locale/theme change of its entities, as the other
  cards); history through `hass.callWS({type: "history/history_during_period", start_time: <local midnight ISO>,
  entity_ids: [activity], minimal_response: true, no_attributes: true})`, refreshed when `activity` changes state
  and at most once per 5 minutes; statistics through `hass.callWS({type: "recorder/statistics_during_period",
  start_time: <today − 6 days, local midnight>, period: "day", statistic_ids: [gas…, starts], types: ["change"]})`,
  refreshed at most once per 10 minutes and on a day change. Abort both on `disconnectedCallback`. Nothing talks to
  the E32 (E32 session hygiene: no pollers).
- **Texts:** `strings.json` `entity.sensor.heat_request.state_attributes.card.state.*` (+ `translations/en,nl,pl`):
  `title` "Your house", `heating` "Heating", `heating_on` "on · water {flow} °C", `heating_off` "off", `request`
  "Boiler request {flow} °C", `wants` "{n} rooms want heat", `wants_one` "1 room wants heat", `hot_water` "Hot
  water", `taps` "{n} taps today", `taps_one` "1 tap today", `taps_none` "no taps yet today", `running` "running
  now", `gas_today` "Gas today", `starts_today` "Burner starts today", `idle` "Boiler resting", `attention`
  "Attention", `all_reasons` "All reasons", `today` "Today", `legend` "Today: heating · hot water · keeping warm",
  `waiting` "The E32 has not reported yet.", `no_stats` "—". Dutch and Polish as in the proposal and glossary
  ("Verwarmt · water {flow} °C", "Gas vandaag", "Branderstarts vandaag", "Ketel in rust", "Let op").
- **Accessibility:** figures are text; the strip has an `aria-label`; the card is keyboard-focusable only where it
  acts (the problem line, the mode chip); contrast of labels ≥ 4.5:1 via `--primary-text-color`/`--secondary-text-color`.
- **Fallbacks:** entity missing → that part is left out; `activity` unknown → strip hidden, status from `request`;
  no statistics yet (first day) → "—" and no sparkline; `hass.localize` empty → EN fallback table in the JS.
- Reuse the `ensureDefined` guard and the `window.customCards` registration of the other cards.

## 8. Diagnostics (path `diagnostics`)

Order: E32 (rows) · **Thermostat on the bus** (`group_thermostat`, the rows moved from the Boiler view,
`_known_entities_card`, section visibility `_any_known`) · Energy and hot water counters (rows + charts as today;
`estimates_empty` text corrected to "The Boiler tab") · Raw boiler data · Hot water capability (the `dhw_capabilities`
card and note, moved last) · Rooms (older setup). Effort: 0.25 day.

## 9. Comparison subview — unchanged.

## 10. Tests

Python (`ha/tests_native`):
- `test_dashboard_heating.py`: `test_the_views_are_overview_rooms_boiler_learning_and_diagnostics` — Overview
  sections `["House", "Rooms"]` (two rooms, one inactive in the fixture → the living room is inlined: assert the house
  card's `rooms` is the living room's Reason sensor when present and the Rooms section lists the bathroom; without a
  Reason sensor the fixture keeps both cards); Boiler first section heading `"Now"`, its activity tiles and pairs;
  Learning heading `"Who controls the boiler"`. `test_each_room_says_why_in_one_status_card_on_the_overview`: the
  inline rule. `test_learning_area_per_room_and_hot_water_today_only_once_reported`: the hot-water rows under
  `"Hot water"`. `test_the_problem_tile_names_the_problem_and_leads_to_the_fix_only_while_there_is_one`: replace by
  "the house card carries `problem` and no native problem tile exists"; Advice stays second. Key-set test: add PL.
- New `test_dashboard_house.py`: house card config per entity presence (full, no gas, no activity, no boiler fields →
  no card and `_wanting_card` fallback), the one-active-room rule, `_signature` includes room state.
- `test_dashboard_redesign.py`: `test_the_boiler_view_groups_the_values_and_shows_only_rows_with_a_value` → new
  heading list `["Now", "Advice"?, "Today and this week", "Hot water", "Last 24 hours", "What the boiler reports",
  "Boiler settings"]`, three titled entities cards under "What the boiler reports", graphs `_any_known`;
  `test_diagnostics_shows_each_value_once...` → `["E32", "Thermostat on the bus", "Energy and hot water counters",
  "Raw boiler data"]`; `test_dutch_headings_for_the_new_groups` → Dutch list.
- `test_dashboard_tidy.py`: `test_the_comparison_is_a_link...` section name; `test_boiler_values_are_hidden...`
  unchanged semantics (rows conditional).
- `test_dashboard_daily_summary.py`: Yesterday → Learning view `"Yesterday in figures"`; burner hours chart under
  Boiler "Today and this week"; missed comfort chart under Learning; `test_no_yesterday_section_without_the_summary`
  → no "Yesterday in figures" without summary *and* scoreboard.
- `test_dashboard_display_code.py`: `card()` → heading in `("Now", "Nu")`.
- `test_dashboard_layout.py`: `HALF = {"tile", "button", "statistic", "gauge"}`; regenerate
  `test/fixtures/ha-dashboard-views.json` with `OPENTHERMOSTAT_WRITE_DASHBOARD_FIXTURE=1`; the gap test must pass in
  both scenarios for EN/NL/PL.
- `test_dhw_keep_warm.py` (lines 200–207, 288–328) and `test_energy_use.py` (293–295): `_hot_water_use_cards` returns
  timeline + note only; `_energy_section` builds "Today and this week"; section list at line 328 updated.
- A section-visibility test: every section of every view has `visibility` or contains at least one card without
  `visibility` (no heading can stand alone), run over `live()` in EN/NL/PL.

Browser (`test/`):
- `test/dashboard-views-browser.cjs`: `HEIGHT` gains `'custom:openthermostat-house': 260, statistic: 120, gauge: 120`;
  half-width set gains `statistic`, `gauge`.
- New `test/ha-house-card-browser.cjs` (Playwright, pattern of `ha-room-status-card-browser.cjs`): full data, partial
  data, unknown states, one-room inline, problem state (band text, `location-changed` fired), light and dark, 390 and
  1280 px; no horizontal overflow; strip segments and tooltips; a11y label.
- Add both to `test/browser-tests.txt`.

## 11. Risks and how the design covers them

| Risk | Cover |
| --- | --- |
| Entities absent on other installations (no gas without modulation + hot-water state; no `boiler_activity`, `dhw_*_today`, `daily_*` on older firmware; `heating_active` not on every boiler; `knowledge`/`boiler_response` before rc.5) | every card is built only from registry entities; sections hide as a whole; pairs share one visibility; the house card draws only configured keys and has the `_wanting_card` fallback |
| `statistic` cards and the sparkline need long-term statistics; nothing on the first day | hide `statistic` cards while the sensor is unknown; the card shows "—" until statistics exist |
| Websocket load from the house card | throttled (5/10 min) and event-driven; aborted on disconnect; never the E32 |
| A room switched on/off changes the inline rule | `_signature` includes the room state → rebuild |
| Activity tile states not exhaustive → no tile visible | the flow/return pair shares `_known(activity)`; unknown activity hides the whole row; the sentence card still speaks |
| `statistics-graph` draws grouped (not stacked) bars | accepted; the hero's strip and figures tell the story |
| HA version: sections views (2024.3+), heading card (2024.10+) already required; `statistic` card, `entities` section rows, tile colours are older | no new minimum |
| Translations drift (EN/NL/PL, strings.json + translations/*.json) | key-set tests for TEXT and the card's `card.state` keys |
| Fixture/browser snapshots pin the old structure | regenerate the fixture; update the HEIGHT map; keep the gap rule |

## 12. Effort

| View / item | Effort |
| --- | --- |
| Overview: house card (JS + browser test + translations) and generator | 2.0 d |
| Boiler: sections 5.1–5.7, deletions, tests | 1.0 d |
| Learning: merged Yesterday, note fold, rename, tests | 0.5 d |
| Rooms: measured tile rule, tests | 0.25 d |
| Diagnostics: moved thermostat rows, order, text fix | 0.25 d |
| Cross-cutting: `_section_known`, ICONS, TEXT EN/NL/PL, fixture, HEIGHT map, key-set tests | 0.5 d |
| Verification: EN/NL/PL dashboards at 390/1280 px, light/dark screenshots, `python -m pytest ha/tests_native -k dashboard`, browser tests | 0.5 d |
| **Total** | **5.0 days** |

## 13. Docs to touch afterwards (P7)

`docs/USER-GUIDE.md` lines 79–102 (tab descriptions: the house card, Boiler order, one Yesterday on Learning,
Thermostat on the bus under Diagnostics), line 726 ("The Boiler tab shows yesterday in words" → Learning),
line 1219 (hot-water section: timeline only; the gas chart under Today and this week); `docs/UX-GLOSSARY.md` row
"Yesterday" (drop "The Boiler tab's own Yesterday"); the module docstring of `dashboard.py` (view list).

## 14. Definition of done

- No section heading can stand over an empty section in any state (test §10, last bullet) in EN, NL and PL.
- Gas per day: one chart (Boiler, Today and this week), one figure on the Overview, one line on Learning (Yesterday).
- "Yesterday" appears once, on Learning.
- The owner's boiler profile (`LIVE_FIELDS` minus the not-reported ones) yields no card that can only show unknown.
- All dashboard tests and the two browser tests pass; the fixture is regenerated; entity IDs unchanged.
