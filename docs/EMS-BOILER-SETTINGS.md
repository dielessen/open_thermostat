# Boiler settings EMS-ESP can change

The Boiler page of the E32 lists everything your boiler reports. Some values carry
the label **"Configurable in EMS-ESP · Read only on E32"**. That means: the
open-source project [EMS-ESP](https://emsesp.org) has a command to change this
value on boilers of this type. The E32 only reads it. OpenThermostat does not
change any of these settings today.

This page explains each of those settings in plain words: what it does, what we
expect to happen when it changes, and what can go wrong. It prepares a later
feature (after version 1.0): changing proven boiler settings from the E32 and
Home Assistant. The plan for that feature is in
[EMS-INSTELBARE-WAARDEN.nl.md](modern-thermostat/EMS-INSTELBARE-WAARDEN.nl.md)
(Dutch).

On the Boiler page, open **About this setting** under such a value to read the
short version of the text below. The short texts come from
[`public/ems/setting-descriptions.json`](../public/ems/setting-descriptions.json).

## Read this first

- **"EMS-ESP can write it" does not mean your boiler accepts it.** EMS-ESP lists
  the same 27 settings for almost every boiler family. A boiler may ignore a
  value, refuse it, or put it back later. Before OpenThermostat offers a
  setting, it must be tested on that boiler model: sent, read back, still there
  later, and with a visible effect (see the plan).
- **Settings are stored in the boiler.** A change stays after a restart of the
  E32. Write down the old value before you change anything.
- **Change one thing at a time** and wait at least a day before you judge the
  effect on gas use.
- **Boilers behind an adapter.** Some boilers do not speak EMS themselves. A
  Bosch EasyControl Adapter (or a similar module) then translates. The value you
  see may be the adapter's copy. A change may never reach the boiler.
- **User or installer.** *User* settings are normal choices like the hot water
  temperature. *Installer* settings are what a heating engineer sets once. They
  will sit under **Advanced**, with a clear "at your own risk" warning.
- **Never offered.** Some values are part of the live heat request, or only
  matter for other kinds of boilers. They are explained here, but they will not
  become settings.

## Words used on this page

- **Water to the heating (flow temperature):** the water the boiler sends to the
  radiators and floor.
- **Switching margin (hysteresis):** how far the water may drift from its target
  before the burner switches on or off.
- **Short cycling (pendelen):** the burner switching on and off many times per
  hour. It costs gas and wears the boiler.
- **Condensing:** a modern boiler gets extra heat out of its flue gas when the
  water coming back is cool (below about 55 °C). Cooler water usually means less
  gas.
- **Store (boiler, cylinder):** a tank of hot tap water that the boiler keeps
  warm. A **combi** boiler heats tap water as it flows instead, sometimes with a
  small store inside.
- **Legionella:** bacteria that can grow in lukewarm tap water (roughly 25 to
  50 °C). Keeping stored hot water at 55 to 60 °C limits that.

## Overview

| Setting | EMS-ESP id | Level | Offer | Main effect |
| --- | --- | --- | --- | --- |
| Heating on the boiler | `heatingactivated` | User | Candidate | Allows or blocks all heating |
| Maximum heating temperature (boiler) | `heatingtemp` | User | Candidate | Caps the water to the heating |
| Water temperature target (thermostat) | `selflowtemp` | – | **Never** | The live heat request itself |
| Requested burner power | `selburnpow` | – | **Never** | Part of the live heat request |
| Maximum heating power | `burnmaxpower` | Installer | Candidate | Caps burner power for heating |
| Burner rest between starts | `burnminperiod` | Installer | Candidate | Fewer burner starts |
| Switching margin: restart below target | `boilhyston` | Installer | Candidate | Fewer burner starts |
| Switching margin: stop above target | `boilhystoff` | Installer | Candidate | Longer burns, warmer water |
| Second stage switching margin: restart | `boil2hyston` | Installer | **Never** | Two-stage burners only |
| Second stage switching margin: stop | `boil2hystoff` | Installer | **Never** | Two-stage burners only |
| Highest pump speed | `pumpmodmax` | Installer | Candidate | Noise, electricity, flow |
| Lowest pump speed | `pumpmodmin` | Installer | Candidate | Flow at low power |
| Pump mode | `pumpmode` | Installer | Candidate | How the pump is controlled |
| Pump run-on | `pumpdelay` | Installer | Candidate | Uses heat left in the boiler |
| Pump start temperature | `pumpontemp` | Installer | **Never** (for now) | Low-temperature floor-standing boilers only |
| Hot water on the boiler | `dhw.activated` | User | Candidate | Allows or blocks hot water |
| Hot water temperature | `dhw.seltemp` | User | Candidate | Gas for hot water, legionella |
| Hot water comfort or eco | `dhw.comfort1` | User | Candidate | Keep-warm runs per day |
| Boiler water boost for hot water | `dhw.flowtempoffset` | Installer | Candidate | How fast the store charges |
| Store charge optimisation | `dhw.chargeoptimization` | Installer | Candidate (unclear) | Slightly less gas per charge |
| Circulation pump fitted | `dhw.circpump` | Installer | Candidate | Allows the circulation pump |
| Circulation pump schedule | `dhw.circmode` | Installer | Candidate | Heat lost in hot water pipes |
| Run the circulation pump now | `dhw.circ` | User | Command | One-off command |
| Hot water switching margin | `dhw.hyston` | Installer | Candidate | Keep-warm runs per day |
| Disinfection temperature | `dhw.disinfectiontemp` | Installer | Candidate | Anti-legionella runs |
| Heat hot water once now | `dhw.onetime` | User | Command | One-off command |
| Start a disinfection now | `dhw.disinfecting` | Installer | **Never** (for now) | One-off command, hard to stop |

"Candidate" means: it may be offered once tests on that boiler model prove it
works. "Command" means a one-off action, not a stored setting; it could later
become a button.

Typical values below come from two manufacturer manuals, for two specific boilers
([T] Nefit TopLine and [B] Buderus GB172). Other boilers can differ. Where a
statement is our own reasoning and not written in a source, it says
**(inferred)**.

## Heating

### Heating on the boiler — `heatingactivated`

- **Row on the Boiler page:** Heating enabled (`heating_enabled`).
- **Unit and range:** on / off.
- **What it does:** allows or blocks central heating on the boiler itself. Hot
  water has its own switch.
- **What we expect when you change it:** off: the boiler ignores every heat
  request, including OpenThermostat's, until you switch it on again. Good as a
  summer switch. On: nothing changes until a thermostat asks for heat.
- **Typical value / factory default:** on [T p.17].
- **Level:** user.
- **Risk:** while it is off, only the boiler protects itself against frost, not
  the house or the pipes [B §7.4.2 p.36].
- **OpenThermostat today:** stops asking for heat by itself when no room needs
  it. It cannot override this switch. This is one of the four Classic settings
  the E32 firmware can read back after a change; changing it is switched off in
  the released firmware.
- **Sources:** [L] 0x16 offset 0 ("CH switch on/off"); [T] frame 26 p.16;
  [B] §7.4.2 p.36 ("no heating" cannot be overridden by a controller);
  [C] `set_heating_activated`.

### Maximum heating temperature (boiler) — `heatingtemp`

- **Row on the Boiler page:** Configured heating temperature
  (`configured_heating_temperature`).
- **Unit and range:** °C. EMS-ESP 0–90. Bus specification 30–90 [L]. Nefit
  TopLine 20–90 [T]. Buderus GB172 30–82 [B].
- **What it does:** the highest water temperature the boiler sends to the
  heating, whatever a thermostat asks for.
- **What we expect when you change it:** lower: radiators and floor stay cooler
  and the boiler condenses more, so it uses a little less gas (inferred from how
  condensing works). On very cold days the house warms up more slowly or not
  fully. On a Nefit TopLine a fresh change can make the boiler show code 0A
  (anti-cycling) until it is restarted [T frame 36 p.31].
- **Typical value / factory default:** 90 °C on the TopLine [T p.17]. Guide
  values: about 50 °C for floor heating, about 75 °C for radiators [B Tab. 10
  p.36].
- **Level:** user, but never above a system maximum that you set in
  OpenThermostat (for example 50 to 60 °C with floor heating).
- **Risk:** too low: rooms stay cold in winter. Too high: unsafe for floor
  heating without its own mixing valve and safety thermostat.
- **OpenThermostat today:** keeps its own lowest and highest water temperature
  per installation. Its request never goes above this boiler limit when the
  boiler reports it (`FlowDemand`). Readable after a change like
  `heatingactivated`.
- **Sources:** [L] 0x16 offset 1; [T] frame 26 p.16, frame 27 p.17; [B] §7.4.2
  and Tab. 10 p.36; [C] `set_heating_temp`; [O] `src/control/FlowDemand.h`.

### Water temperature target (thermostat) — `selflowtemp` — never offered

- **Row on the Boiler page:** Reported selected flow temperature
  (`reported_selected_flow_temperature`); labelled "Manual Classic trial only".
- **Unit and range:** °C, 0–90.
- **What it does:** the water temperature a thermostat asks for right now. It is
  a live request (telegram 0x1A), not a stored setting. The boiler keeps the
  highest request it receives [L].
- **What we expect when you change it:** heating starts or stops at once. The
  next request from OpenThermostat or another thermostat overwrites it within
  minutes.
- **Level:** not a setting.
- **Risk:** two devices sending different requests make the boiler switch on
  and off.
- **OpenThermostat today:** this *is* OpenThermostat's own heat request (in
  active control) and the attended boiler test. It will never be a second way to
  steer the boiler.
- **Sources:** [L] 0x1A offset 0; [C] `set_flow_temp`;
  [O] `src/EMS/ClassicBoilerTestEncoder.h`.

### Requested burner power — `selburnpow` — never offered

- **Row on the Boiler page:** Reported requested power limit
  (`reported_requested_power_limit`).
- **Unit and range:** %, 0–254 in EMS-ESP. Above 100 % is used for a hot water
  boost on some boilers [L 0x18 offset 3].
- **What it does:** the burner power a thermostat asks for right now, as part of
  the same live heat request as the water temperature.
- **What we expect when you change it:** the boiler follows the highest power
  or temperature request it receives [L]. A value set by hand is replaced by the
  next request.
- **Level:** not a setting.
- **Risk:** a stray power request can keep the burner running when no room
  needs heat (inferred from [L]: "the highest is used").
- **OpenThermostat today:** sends only the water temperature (one byte at
  offset 0) and leaves this part of the request alone.
- **Sources:** [L] 0x1A offset 1; [C] `set_burn_power`;
  [O] `src/EMS/ClassicBoilerTestEncoder.h`.

## Burner and pump

### Maximum heating power — `burnmaxpower`

- **Row on the Boiler page:** Maximum burner power (`maximum_burner_power`).
- **Unit and range:** %, 0–100 [L] (EMS-ESP accepts 0–254). TopLine: from the
  boiler's minimum power to 100 % [T].
- **What it does:** caps the burner power for heating, as a percentage of what
  the boiler can deliver.
- **What we expect when you change it:** lower: slower, steadier heating and a
  slightly cooler flue (inferred). This suits a boiler that is much bigger than
  the house needs. It does **not** lower the burner's minimum power, so it does
  not stop on-off cycling when little heat is needed (inferred: the minimum is a
  separate property of the burner). Buderus mentions a practical reason too:
  some gas suppliers charge by maximum power [B 2.1A].
- **Typical value / factory default:** the maximum [B 2.1A p.47].
- **Level:** installer.
- **Risk:** too low: the house cannot be kept warm on the coldest days. On a
  combi boiler hot water often has its own limit (Buderus 2.1b, EMS-ESP
  `dhw.maxpower`), so this setting may not slow down hot water.
- **OpenThermostat today:** does not limit burner power.
- **Sources:** [L] 0x16 offset 2; [T] frame 26 p.16; [B] Tab. 13 2.1A and 2.1b
  p.47; [C] `set_max_power`.

### Burner rest between starts — `burnminperiod`

- **Row on the Boiler page:** Minimum burner period (`minimum_burner_period`).
- **Unit and range:** minutes. EMS-ESP 0–120; bus specification 0–60
  ("anti fast cycle time") [L]; Buderus GB172 3–45 [B].
- **What it does:** the shortest time the burner stays off before it may start
  again for heating (anti-cycling).
- **What we expect when you change it:** longer: fewer burner starts, less wear
  and steadier running. The water cools a bit further before the boiler starts
  again, so radiators get slightly cooler between runs. Shorter: more starts.
  The boiler reports the time left in telegram 0x19 [L], so the effect is
  measurable.
- **Typical value / factory default:** 10 minutes [B 2.3b p.49]. The Nefit
  TopLine uses a fixed 10 minutes after the first start when an on/off or
  ModuLine thermostat asks more than once per 10 minutes (display code 0A)
  [T p.19, frame 36 p.31]. Buderus adds: with a weather-compensated controller
  no setting is needed, the controller optimises it [B 2.3b].
- **Level:** installer (low risk within 5–20 minutes; inferred).
- **Risk:** very short: short cycling. Very long: rooms react slowly, mostly
  with radiators.
- **OpenThermostat today:** keeps its own minimum on and off time for its heat
  request (5 minutes each by default, tunable 2–30 minutes). The boiler's timer
  works *inside* a running request, when the water reaches its target and the
  burner stops. Readable after a change like `heatingactivated`.
- **Sources:** [L] 0x16 offset 6, 0x19 offset 8; [T] p.19 and frame 36 p.31;
  [B] Tab. 13 2.3b p.49; [C] `set_burn_period`;
  [O] `src/control/ControlTuning.h`, `src/control/FlowDemand.h`.

### Switching margin: restart below target — `boilhyston`

- **Row on the Boiler page:** Heating hysteresis on (`heating_hysteresis_on`).
- **Unit and range:** K (kelvin = degrees difference), −20 to 0 in EMS-ESP;
  −15 to −2 in the bus specification [L]. Buderus GB172: 0–30 K [B].
- **What it does:** how far the water to the heating must drop below its target
  before the burner starts again.
- **What we expect when you change it:** a larger margin: fewer starts and
  longer burns, but the water temperature swings more. A smaller margin: a
  steadier temperature and more starts.
- **Typical value / factory default:** 6 K [B 2.3C p.49].
- **Level:** installer.
- **Risk:** a margin close to zero makes the boiler short-cycle when little heat
  is needed.
- **OpenThermostat today:** not controlled. Its water temperature request
  changes slowly, which already limits starts.
- **Sources:** [L] 0x16 offset 5; [B] Tab. 13 2.3C p.49; [C] `set_hyst_on`.

### Switching margin: stop above target — `boilhystoff`

- **Row on the Boiler page:** Heating hysteresis off (`heating_hysteresis_off`).
- **Unit and range:** K, 0–20 in EMS-ESP; 2–15 in the bus specification [L].
- **What it does:** how far the water to the heating may rise above its target
  before the burner switches off.
- **What we expect when you change it:** a larger margin: longer burns and fewer
  starts, but hotter water than asked for and a warmer return, so slightly less
  condensing (inferred).
- **Typical value / factory default:** not documented in the sources we found.
- **Level:** installer.
- **Risk:** a large margin can push the water above what a floor heating
  circuit should get (inferred).
- **OpenThermostat today:** not controlled. Keep this margin in mind when you
  set the highest water temperature for floor heating.
- **Sources:** [L] 0x16 offset 4; [C] `set_hyst_off`.

### Second stage switching margins — `boil2hyston`, `boil2hystoff` — never offered

- **Rows on the Boiler page:** Secondary heating hysteresis on / off.
- **Unit and range:** K; −20 to 0 and 0 to 20 in EMS-ESP; ±2 to ±15 [L].
- **What they do:** the same two margins, for the second stage of a two-stage
  burner [L: "switching off limit for two stage burners"].
- **What we expect when you change them:** only two-stage burners use them,
  mostly older floor-standing oil or gas boilers. On a modulating wall-hung
  boiler nothing should change (inferred).
- **Level:** installer.
- **Risk:** as for the first stage: a small margin means many starts of the
  second stage.
- **OpenThermostat today:** not used; not offered for modulating boilers.
- **Sources:** [L] 0x16 offsets 12–13; [C] `set_hyst2_on`, `set_hyst2_off`.

### Highest pump speed — `pumpmodmax`

- **Row on the Boiler page:** Pump modulation maximum (`pump_modulation_maximum`).
- **Unit and range:** %, 0–100 [L]. TopLine: from the lowest pump speed to
  100 % [T]. Buderus GB172: 10–100 % [B].
- **What it does:** the highest speed the boiler's heating pump may run at.
- **What we expect when you change it:** lower: a quieter system and less
  electricity. Nefit names noise complaints as the reason to lower it [T]. Often
  also a cooler return, which helps condensing (inferred). Distant radiators or
  long floor loops may get too little flow.
- **Typical value / factory default:** 100 % [T p.17; B 2.1J p.48].
- **Level:** installer.
- **Risk:** too low: some rooms stay cold, or the boiler reaches its own limit
  sooner and switches on and off more (inferred).
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x16 offset 9; [T] frame 26 p.16; [B] Tab. 13 2.1J p.48
  (only active with pump mode 0); [C] `set_max_pump`.

### Lowest pump speed — `pumpmodmin`

- **Row on the Boiler page:** Pump modulation minimum (`pump_modulation_minimum`).
- **Unit and range:** %, 0–100 [L]. TopLine 50 % up to the highest pump speed
  [T]. Buderus GB172 10–100 % [B].
- **What it does:** the lowest speed the heating pump uses when the boiler runs
  at low power.
- **What we expect when you change it:** higher: more flow at low power. Nefit
  advises raising it when the pump pressure at the lowest speed is too low for
  the installation [T]. Lower: quieter and less electricity.
- **Typical value / factory default:** 50 % on the TopLine [T p.17]; 10 % on
  the GB172 [B 2.1H p.48].
- **Level:** installer.
- **Risk:** too low can give too little flow; the boiler water then heats up
  fast and the burner stops early (inferred).
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x16 offset 10; [T] frame 26 p.16; [B] Tab. 13 2.1H p.48;
  [C] `set_min_pump`.

### Pump mode — `pumpmode`

- **Row on the Boiler page:** Configured pump mode (`configured_pump_mode`).
- **Unit and range:** a choice. Most boilers: proportional, or a fixed pressure
  difference 1–4 (EMS-ESP names `deltaP-1` to `deltaP-4`). Product 95 (HT3) uses
  a different list (`pumpstep`, `const.high`, …). The bus specification allows
  up to 8 values and only for boilers with a "dialog pump" [L]; one boiler
  reported a value EMS-ESP could not name (350 mbar) [#2721].
- **What it does:** how the heating pump is controlled: along with the burner
  power (proportional), or at a fixed pressure.
- **What we expect when you change it:** a lower fixed pressure saves
  electricity and reduces flow noise [B 2.1C]. In the proportional mode the pump
  slows down when the burner does, between the lowest and highest pump speed.
- **Typical value / factory default:** 2 = 200 mbar fixed pressure on the GB172
  [B 2.1C p.47].
- **Level:** installer.
- **Risk:** the wrong mode for the system can leave radiators or floor loops
  short of flow. Not every boiler has a pump that knows these modes.
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x16 offset 11; [B] Tab. 13 2.1C p.47; [C] `set_pumpMode`;
  [#2721].

### Pump run-on — `pumpdelay`

- **Row on the Boiler page:** Pump run on (`pump_run_on`).
- **Unit and range:** minutes, 0–60 in EMS-ESP. The bus specification and both
  manuals also have a "24 hours" step (value 61 on the bus) [L, T, B].
- **What it does:** how long the heating pump keeps running after the heat
  request ends.
- **What we expect when you change it:** longer: heat left in the boiler
  reaches the rooms instead of being lost, for a little pump electricity. The
  24-hour step keeps the pump running all the time.
- **Typical value / factory default:** 5 minutes on the TopLine [T p.17];
  3 minutes on the GB172 [B 2.9F p.50].
- **Level:** installer, but low risk.
- **Risk:** low. A very short time leaves heat behind in the boiler; a very long
  one only costs electricity.
- **OpenThermostat today:** does not run the pump. This is one of the four
  Classic settings the E32 can read back; the boiler's pump bit shows the effect
  after the burner stops. That makes it the safest first test.
- **Sources:** [L] 0x16 offset 8; [T] frame 26 p.16, frame 27 p.17; [B] Tab. 13
  2.9F p.50; [C] `set_pump_delay`.

### Pump start temperature — `pumpontemp` — not offered for now

- **Row on the Boiler page:** Pump start temperature (`pump_start_temperature`).
- **Unit and range:** °C, 0–60 in EMS-ESP; 0–65 in the bus specification, and
  only changeable when the boiler says so [L].
- **What it does:** on low-temperature boilers with a separate boiler controller
  (for example a Buderus MC10 on a floor-standing boiler), the boiler water must
  reach this temperature before the pump starts [#2088].
- **What we expect when you change it:** higher: the boiler first warms itself
  up, but the heat reaches the rooms later (inferred).
- **Level:** installer.
- **Risk:** on such a boiler a value that is too low may let flue gas condense
  inside a boiler that is not built for it (inferred). On wall-hung condensing
  boilers the meaning is unknown.
- **OpenThermostat today:** not used. Not offered until its meaning is confirmed
  per model.
- **Sources:** [L] 0x16 offset 23; [C] `set_pumpOnTemp`; [#2088].

## Hot water

### Hot water on the boiler — `dhw.activated`

- **Row on the Boiler page:** Hot water enabled (`dhw_enabled`).
- **Unit and range:** on / off.
- **What it does:** allows or blocks hot water heating by the boiler.
- **What we expect when you change it:** off: no gas for hot water and no
  keep-warm runs, but also no hot water. A circulation pump stops as well. A
  store keeps its frost protection [L].
- **Typical value / factory default:** on (Comfort) [T p.17].
- **Level:** user.
- **Risk:** a store that stays cold for days can grow legionella. Buderus
  recommends a thermal disinfection after a long standstill [B §8.1 p.40].
- **OpenThermostat today:** does not control hot water.
- **Sources:** [L] 0x33 offset 1; [T] frame 26 p.16; [B] §7.5.1 p.37, §8.1
  p.40; [C] `set_ww_activated`.

### Hot water temperature — `dhw.seltemp`

- **Row on the Boiler page:** Selected hot water temperature
  (`selected_dhw_temperature`).
- **Unit and range:** °C. Bus specification 30–80 [L]. TopLine 30–60 [T].
  GB172 40–60 [B]. EMS-ESP gives no range for most boilers.
- **What it does:** the temperature the boiler keeps the hot water at: the
  store, or the water at the tap on a combi.
- **What we expect when you change it:** lower: less gas to keep a store warm
  and less scale. You get less hot water before it runs lukewarm. With a store
  the number of keep-warm runs per day changes too, which the Boiler page counts.
- **Typical value / factory default:** 60 °C [T p.17]. Buderus recommends at
  least 55 °C against legionella and at most 60 °C in normal use against
  scalding [B §7.5.2 p.38].
- **Level:** user.
- **Risk:** below about 55 °C legionella can grow in a store. Above 60 °C:
  scalding and more scale.
- **OpenThermostat today:** does not control hot water.
- **Sources:** [L] 0x33 offset 2; [T] frame 26 p.16, frame 27 p.17; [B] §7.5.2
  p.38; [C] `set_ww_temp` (EMS-ESP also writes 0x35 offset 3 for some boilers).

### Hot water comfort or eco — `dhw.comfort1`

- **Row on the Boiler page:** Configured hot water comfort mode
  (`configured_dhw_comfort_mode`).
- **Unit and range:** a choice: comfort (EMS-ESP: "high comfort" / "hot") or
  eco; some boilers also "intelligent".
- **What it does:** comfort keeps hot water ready all the time. Eco heats less
  often and first lets the water cool further.
- **What we expect when you change it:** with a store (GB172): comfort reheats
  when the store is 5 K below its target, eco when it is 10 K below [B §7.5.1
  p.37]. With a combi: comfort keeps the boiler warm all the time, so it also
  fires when nobody taps; eco heats only when you tap [B]. The Nefit TopLine
  shows code =H while it keeps hot water warm in comfort mode [T p.19]. Eco
  means fewer keep-warm runs and less gas per day, mostly when little hot water
  is used. Hot water may take longer or run lukewarm sooner.
- **Typical value / factory default:** comfort [T p.17].
- **Level:** user.
- **Risk:** eco together with a low hot water temperature keeps a store longer
  in the range where legionella grows.
- **OpenThermostat today:** does not control hot water. The Boiler page counts
  keep-warm runs, so you can see the effect.
- **Note:** on Classic boilers this value is byte 9 of telegram 0x33. EMS-ESP
  calls it `dhw.comfort` (hot / eco / intelligent) there, and uses
  `dhw.comfort1` (high comfort / eco) for newer EMS+ boilers. The E32 reads the
  Classic byte and links it to `dhw.comfort1`. A write must use the right
  telegram for the boiler family.
- **Sources:** [L] 0x33 offset 9 ("economy"); [T] frame 26 p.16, p.19; [B]
  §7.5.1 p.37; [C] `process_UBAParameterWW`, `set_ww_mode`.

### Boiler water boost for hot water — `dhw.flowtempoffset`

- **Row on the Boiler page:** Hot water flow temperature offset
  (`dhw_flow_temperature_offset`).
- **Unit and range:** K. Bus specification 25–40 [L]; EMS-ESP accepts 0–100.
- **What it does:** how much hotter than the hot water target the boiler makes
  its own water while it charges the store [L: "defines the supply temperature
  setpoint to heat up the storage tank"].
- **What we expect when you change it:** lower: the store charges more slowly,
  but the boiler water is cooler, so it condenses more (inferred). Higher: hot
  water is back sooner after a shower.
- **Typical value / factory default:** 40 K (comment in the EMS-ESP source;
  not from a manual).
- **Level:** installer.
- **Risk:** too low and the store may never reach its target, which also weakens
  the protection against legionella (inferred).
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x33 offset 5; [C] `process_UBAParameterWW`,
  `set_ww_flowTempOffset`.

### Store charge optimisation — `dhw.chargeoptimization`

- **Row on the Boiler page:** Hot water charge optimisation enabled
  (`dhw_charge_optimisation_enabled`).
- **Unit and range:** on / off.
- **What it does:** while the store charges, the burner stops a little early and
  the pump finishes the job with the heat that is left. This is how an RC310
  manual describes "storage charging optimisation" [#2543].
- **What we expect when you change it:** on: slightly less gas per charge. The
  store may end just below its target (inferred).
- **Level:** installer.
- **Risk:** hardly documented. The bus specification calls the same byte "hot
  water rest energy switch" [L], and EMS-ESP read it as a hysteresis before
  [#2543]. Its effect must be checked per model before it is offered.
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x33 offset 4; [C] `set_ww_chargeOptimization`; [#2543].

### Circulation pump fitted — `dhw.circpump`

- **Row on the Boiler page:** Hot water circulation enabled
  (`dhw_circulation_enabled`).
- **Unit and range:** on / off.
- **What it does:** tells the boiler whether a hot water circulation pump is
  fitted and may run [L: "the HW-circulation pump can be switched off"].
- **What we expect when you change it:** off: the circulation pump never runs.
  That saves heat lost in the pipes, but hot water takes longer to reach the
  tap.
- **Level:** installer.
- **Risk:** switching it on without a pump does nothing useful. Long unused
  circulation pipes can hold lukewarm water (inferred).
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x33 offset 6; [C] `set_ww_circulation_pump`.

### Circulation pump schedule — `dhw.circmode`

- **Row on the Boiler page:** Configured hot water circulation mode
  (`configured_dhw_circulation_mode`).
- **Unit and range:** off, 1× to 6× 3 minutes per hour, or continuous [L].
- **What it does:** how often the circulation pump runs.
- **What we expect when you change it:** more often: hot water at the tap
  sooner, but more heat lost from the pipes and more reheating of the store
  (inferred). Continuous costs the most.
- **Typical value / factory default:** 2 × 3 minutes per hour [L].
- **Level:** installer.
- **Risk:** only matters with a circulation pump. Long pauses leave lukewarm
  water standing in the pipes. A comment in the EMS-ESP source says that with
  "off" switching is not possible, and with a schedule switching off is not
  possible [C]; we read that as the one-off command `dhw.circ` (inferred).
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x33 offset 7; [C] `set_ww_circulation_mode`.

### Run the circulation pump now — `dhw.circ` — command

- **Row on the Boiler page:** Raw hot water circulation bit
  (`raw_dhw_circulation_bit`): this row shows whether the circulation relay is
  on.
- **What it does:** switches the circulation pump on or off now (telegram 0x35,
  a command). It is not a stored setting.
- **What we expect:** on: hot water reaches the taps sooner for a while; the
  boiler's own schedule takes over again later (inferred).
- **Level:** user (a button, not a setting).
- **Risk:** little; some heat lost from the pipes.
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x34 offset 7 (circulation status); [C]
  `set_ww_circulation`.

### Hot water switching margin — `dhw.hyston`

- **Row on the Boiler page:** Hot water hysteresis on (`dhw_hysteresis_on`).
- **Unit and range:** K, −20 to −2 [L]. EMS-ESP gives no range.
- **What it does:** how far the water in the store must cool below its target
  before the boiler heats it again.
- **What we expect when you change it:** a larger margin: fewer, longer reheats
  and less gas lost to short keep-warm runs. The store is cooler just before a
  reheat.
- **Typical value / factory default:** −5 K (comment in the EMS-ESP source).
  The GB172 manual describes comfort as 5 K and eco as 10 K [B §7.5.1 p.37];
  comfort/eco and this margin may be linked on some boilers (inferred, not
  verified).
- **Level:** installer.
- **Risk:** a large margin with a low target keeps the store in the range where
  legionella grows. A small one gives many short burner runs.
- **OpenThermostat today:** not controlled. The Boiler page counts keep-warm
  runs.
- **Sources:** [L] 0x33 offset 3; [B] §7.5.1 p.37; [C]
  `process_UBAParameterWW`, `set_ww_hyst_on`.

### Disinfection temperature — `dhw.disinfectiontemp`

- **Row on the Boiler page:** Hot water disinfection temperature
  (`dhw_disinfection_temperature`).
- **Unit and range:** °C, 60–80 [L, C].
- **What it does:** the temperature the boiler uses for a thermal disinfection
  (anti-legionella) of the store. The boiler heats to it, holds it for a time
  that is shorter at higher temperatures, and then runs the circulation pump
  [L].
- **What we expect when you change it:** only matters while a disinfection
  runs. Higher: a shorter hold time, but more gas and more scale.
- **Typical value / factory default:** the GB172 holds 75 °C for 35 minutes
  when its own controller runs it [B §8.2.2 p.40].
- **Level:** installer.
- **Risk:** during and after a disinfection the tap water can scald [B §8 p.40].
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x33 offset 8; [B] §8 p.40; [C] `set_ww_disinfect_temp`.

### Heat hot water once now — `dhw.onetime` — command

- **Row on the Boiler page:** Raw hot water one time bit
  (`raw_dhw_one_time_bit`): shows whether such a charge runs.
- **What it does:** heats the hot water once to its target now (0x35, a
  command), also in eco mode (inferred from "one time loading" [L]).
- **What we expect:** one extra reheat; handy before a bath when eco is on.
- **Level:** user (a button, not a setting).
- **Risk:** little; the gas of one reheat.
- **OpenThermostat today:** not controlled.
- **Sources:** [L] 0x34 offset 5 bit 1 ("one time loading"); [C]
  `set_ww_onetime`.

### Start a disinfection now — `dhw.disinfecting` — not offered for now

- **Row on the Boiler page:** Raw hot water disinfection bit
  (`raw_dhw_disinfection_bit`): shows whether a disinfection runs.
- **What it does:** starts a thermal disinfection now (0x35, a command).
- **What we expect:** much more gas for one run, and very hot water at the taps
  for hours [B §8 p.40].
- **Level:** installer.
- **Risk:** scalding. EMS-ESP notes that switching it off this way does not seem
  to work [C]; the GB172 manual stops it by switching the boiler off and on
  [B §8.2.2 p.40].
- **OpenThermostat today:** not controlled. Not offered while it cannot be
  stopped safely.
- **Sources:** [L] 0x34 offset 5 bit 2; [B] §8 p.40; [C] `set_ww_disinfect`.

## What this means for the owner's installation

The reference installation is a Nefit EcomLine Classic HRC 22 behind a Bosch
EasyControl Adapter at bus address 0x08. The boiler itself speaks iRT, not EMS.
Every value on the Boiler page is the adapter's version. A setting written to the
adapter may be stored only in the adapter, translated to the boiler, or ignored.
That can only be told apart by an effect on the boiler (level L3 in the plan),
not by reading the value back.

The two settings most worth checking there are the hot water ones, because of
the many keep-warm runs of its 25 litre store: **hot water comfort or eco** and
the **hot water switching margin**. The boiler's own panel may offer the same
choice; check the boiler's manual first.

A boiler that speaks EMS directly, such as a Nefit TopLine (product 115), reports
its own values and is the better first test.

## Sources

- **[E]** EMS-ESP, *All Entities*, https://docs.emsesp.org/All-Entities. Pinned
  dump in this repository: `public/ems/entities.csv` (see
  `public/ems/SOURCES.json`). Names, ranges and the writable flag.
- **[L]** EMS-ESP documentation, telegram library, `static/data/telegrams.csv`
  at commit `227c21a`,
  https://raw.githubusercontent.com/emsesp/docs/227c21a942211724f0c481d295fd7f22f976422b/static/data/telegrams.csv.
  Pinned copy: `public/ems/library.csv`. Cited by telegram and offset: 0x16
  (UBAParameters), 0x33 (UBAParameterWW), 0x1A (setpoints), 0x18, 0x19, 0x34.
- **[C]** EMS-ESP source, `src/devices/boiler.cpp` at commit `8f7049b`,
  https://github.com/emsesp/EMS-ESP32/blob/8f7049b47a1641cc22c91c63cfb27c1278b282ed/src/devices/boiler.cpp:
  `process_UBAParameters`, `process_UBAParameterWW` and the `set_*` functions
  named above. Read as reference only (LGPL-3.0); no code is copied.
- **[#2088]** EMS-ESP issue 2088, "Add entity for low-temperature boilers pump
  start temp", https://github.com/emsesp/EMS-ESP32/issues/2088.
- **[#2543]** EMS-ESP issue 2543, "Add entity for storage charging optimization
  option", https://github.com/emsesp/EMS-ESP32/issues/2543.
- **[#2721]** EMS-ESP issue 2721, "Boiler pump mode unavailable …",
  https://github.com/emsesp/EMS-ESP32/issues/2721.
- **[T]** Nefit, *Service-instructie Nefit TopLine HR, TopLine AquaPower HRC en
  TopLine AquaPower Plus HRC*, edition 07/2008 (Dutch). Frame 26 "Instelmenu"
  p.16; frame 27 factory settings p.17; display code table (0A, =H) p.19;
  frame 36 p.31. Copy found at
  https://portal.insmart.nl/downloads/nefit_topline_aquapower_Service-instructie%2BTopline%2BAquapower.pdf
  (a third-party mirror, not Nefit's own site).
- **[B]** Buderus, *Montage- und Wartungsanleitung Logamax plus GB172-14/20/24/24K*,
  6 720 619 596 (02/2011) (German). §7.4.2 and Tab. 10 p.36; §7.5.1 p.37;
  §7.5.2 p.38; §8 p.40; Tab. 13 "Menü 2" pp.47–50 (2.1A, 2.1b, 2.1C, 2.1H, 2.1J,
  2.3b, 2.3C, 2.9F). Copy found at
  https://www.kesselheld.de/content/uploads/2019/07/wartungsanleitung-buderus-logamax-plus.pdf
  (a third-party mirror).
- **[O]** OpenThermostat source: `src/control/FlowDemand.h`,
  `src/control/ControlTuning.h`, `src/EMS/ClassicBoilerTestEncoder.h`,
  `src/EMS/ClassicBoilerSettingSpec.h`, `src/EMS/ClassicBoilerMonitor.h`.

## What we could not verify

- Whether any of these writes reach the boiler behind the owner's EasyControl
  Adapter. Nothing was written to any boiler for this page.
- Factory defaults for `boilhystoff`, `dhw.chargeoptimization`,
  `dhw.circpump` and the exact meaning of `pumpontemp` on wall-hung boilers.
- Whether comfort/eco and the hot water switching margin are one setting or two
  on a given boiler.
- The TopLine and GB172 manuals are older editions found on third-party sites.
  Newer boilers (EMS+, for example the GB192 or Condens 9000) use other telegrams
  and can have other ranges.
