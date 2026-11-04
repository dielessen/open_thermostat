# OpenThermostat user guide

For E32 V2 beta.23 or newer, optionally with the Home Assistant integration
that its release notes pair with it. If you use Home Assistant, install both
together. Installing on a new E32, the
Home Assistant setup, updates and troubleshooting are described step by step
in the [installation guide](INSTALL.md).

The E32 controls the boiler only after you confirm the takeover, best through
the guided **Boiler test and takeover** on the Rooms page; nothing else in this
guide makes it do so. A new E32 picks its route from the boiler bus: while your
old thermostat still asks the boiler for heat, it first runs a **trial run**
(shadow mode) beside it and compares; without one it goes straight to the
boiler test. You can always choose the other route (see
[The attended switch-over](#the-attended-switch-over)).

**Supported boilers:** EMS Classic (EMS 1.0), directly on the bus or through an
adapter such as the Bosch EasyControl Adapter. EMS+ (EMS 2.0) is planned for
version 1.1.

**Home Assistant is optional.** The room plan, week programs and Bluetooth
sensors live on the E32 and work without it. Home Assistant adds its own
sensors and thermostats as room sources, a dashboard, heating advice and
energy inputs.

## Where do I set what?

| What | Without Home Assistant | With Home Assistant |
| --- | --- | --- |
| Rooms: add, rename, remove, active or off | E32: Rooms | Settings → Devices & services → OpenThermostat → Configure → Rooms |
| Temperature sources per room and their order | E32: Rooms (Bluetooth sensors) | Same room editor (HA entities and the E32's Bluetooth sensors) |
| Target, temperature without Home Assistant, minimum and maximum | E32: Rooms | Same room editor |
| Week program per room | E32: Rooms (visual planner) | Same room editor, or the Week program tab of the OpenThermostat dashboard |
| Setting device per room (valve, tado, number) | — | Same room editor |
| House mode: automatic, at home, away, holiday | E32: Home | Configure → House → House mode and holiday → House mode, or the House mode control (E32 device, dashboard) |
| Planned holidays (up to 8), the temperature on holiday, stopping a holiday | E32: Home → Holidays | Configure → House → House mode and holiday → Plan a holiday, Change or remove a holiday, Temperature on holiday; Configure → House → Stop holiday while one runs |
| Who lives here (presence), how long before the house counts as away, and the away temperature | E32: Home (away temperature) | Configure → House → Presence and away temperature |
| Who uses a room (persons per room) | E32: Rooms (shown, read-only) | Same room editor → Persons |
| Away temperature of a single room | E32: Rooms → the room → Persons | Same room editor → Persons |
| Window and door contacts per room | — | Same room editor → Windows and doors |
| Levels of a room without a week program, default window pause, length of a manual change | — | Configure → House → Comfort defaults for rooms |
| Radiator valves per room | E32: Rooms → the room → Radiator valves | Same room editor → Radiator valves |
| Lowest and highest water temperature for the boiler request | E32: Home → Water temperature limits | Configure → Heating and boiler → Water temperature limits |
| Smart warm-up and Weather compensation, both on by default | E32: Home → Heating settings → Advanced | Configure → Heating and boiler → Smart warm-up and Weather compensation, or the switches on the E32 device |
| Water temperature in hard frost (−10 °C), for Weather compensation | E32: Home → Heating settings → Advanced | Configure → Heating and boiler → Weather compensation → Advanced, or the selection on the E32 device |
| Gas meter, gas price, outdoor temperature, boiler power, water meter (all optional) | — | Configure → Energy and outdoor temperature |
| Pairing Bluetooth sensors (address, profile, encryption key) | E32: System → Bluetooth sensors | E32: System → Bluetooth sensors |
| Boiler model (name, picture and the display code table) | E32: Boiler → Boiler model | E32: Boiler → Boiler model |
| Network, MQTT broker, time and time zone | E32: System → Network and Home Assistant (page "Settings") | E32: System → Network and Home Assistant (page "Settings") |
| Admin password of the E32 | E32: System → Password | E32: System → Password |
| Firmware updates | E32: System → Firmware update | The firmware update entity, or the E32 page |
| Backup and restore of the settings | E32: System → Backup and restore | Daily and automatic; restore under Configure → Advanced and diagnostics → Restore settings to this E32 (or on the E32 page) |
| Restart | E32: System → Restart device | E32: System → Restart device |
| Sign out of the E32 page | E32: System → Sign out (last item, once you are signed in) | E32: System → Sign out |
| Logs, diagnostics console and syslog | E32: System → Diagnostics and system log | E32: System → Diagnostics and system log |
| Shorter entity IDs (optional) | — | Configure → Advanced and diagnostics → Tidy entity IDs |

The room plan is stored on the E32, and the E32 runs it. With Home Assistant,
the HA room editor is the main place to edit it; it reads the plan from the
E32 and writes it back. Bluetooth sensors stay paired on the E32, so they keep
working without Home Assistant; the E32 shares them with Home Assistant,
where each sensor appears as its own device and can be chosen as a room
source.

Configure (**Settings → Devices & services → OpenThermostat →** the gear
icon) has six items. Every submenu has **← Back**; after you save you are
back in the menu, and **Done** closes Configure.

| Item | What is in it |
| --- | --- |
| Rooms | Add a room, edit or remove a room |
| House | Presence and away temperature, house mode and holiday, comfort defaults for rooms |
| Heating and boiler | Water temperature limits, boiler model, Smart warm-up, Weather compensation, comfort and boiler care |
| Energy and outdoor temperature | Gas meter, gas price, outdoor temperature, boiler power, water meter |
| E32 connection | The E32's address and password |
| Advanced and diagnostics | Dashboard and name, Bluetooth sensor names, the E32 system log and time zone, restoring a backup, tidying entity IDs, checks |

The **OpenThermostat** dashboard in the Home Assistant sidebar has these tabs:

- **Overview**: the house (its mode, the next planned holiday, the rooms that
  want heat and the boiler request) and one **status card** per room. The card shows the room's
  temperature and target and, in one line, why it heats or not: window open,
  away, warm enough, Smart warm-up heating early, and so on. The same line is
  the **Reason** sensor of the room. A problem tile appears only while there is
  a problem, and a tap on it opens Repairs.
- **Rooms**: per room its thermostat, a 24-hour graph, its sensors, windows and
  people, and what it learned for that room.
- **Week program**: the visual week planner for all rooms.
- **Boiler**: what the boiler does in words, the display code, burner starts,
  hot water, the heating advice, the values the boiler reports, the gas per
  day and yesterday.
- **Learning and settings**: what the thermostat learned about your house and
  boiler, **Yesterday** in figures, Smart warm-up, Weather compensation, the
  burner as information and the check before the E32 takes over.
- **Diagnostics**: the E32 itself, hot water, the energy and hot water counters
  and the raw boiler data.

During a trial run a **Comparison** page opens from the **Learning and
settings** tab.

## First start (no Home Assistant needed)

A new E32 first needs the OpenThermostat firmware over USB; see
[installing the firmware](INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb).

### 1. Connect the E32 to your Wi-Fi

1. Power the E32. Without Wi-Fi settings it opens its own setup network
   **OpenThermostat-xxxxxx** (password `openthermostat`).
2. Join that network with a phone or laptop. The setup page opens by itself;
   otherwise open `http://10.10.10.1/`.
3. Choose your **2.4 GHz** home network and enter its password. Settings are
   saved only after a successful connection.
4. Open the address the page shows on your home network. A new E32 is also
   reachable by its name `openthermostat-xxxxxx` (the end of its MAC address),
   for example `http://openthermostat-a1b2c3.local/` where your network
   supports `.local` names.
5. Sign in with user `admin` and password `admin`. Then choose your own
   password (8–64 characters) under **System → Password**; until you do,
   the Overview reminds you. Home Assistant asks for this password when you
   connect it. A forgotten password can be reset to `admin` with the
   `password-reset` command over USB.

### 2. Set the time zone

Week programs, "today" and the daily comparison use the E32's own clock. Go
to **System → Network and Home Assistant**, section **Time**, check the time server and choose
your time zone from the list. When the page suggests the time zone of your
browser, **Use this time zone** fills it in. For a time zone that is not in
the list, choose "Other" and enter its POSIX text under Advanced, for example
`EST5EDT,M3.2.0,M11.1.0` (US Eastern); any time zone and summer-time rule
works. Choose **Save settings** and let the E32 restart. Without a valid clock
the week program is not used and the room keeps its temperature without Home
Assistant.

### 3. Choose your boiler

A newly installed E32 does not listen to the boiler yet. Under **System → Network and Home Assistant →
Advanced settings → Hardware services**, tick **Boiler bus (EMS) on**,
save and let the E32 restart. This only lets the E32 receive boiler data; it
does not send heat requests. Connect the E32 to the boiler's EMS bus as
described in the [installation guide](INSTALL.md#6-connect-the-e32-to-the-boiler)
(switch the boiler off first).

Then open **Boiler** and check that boiler values arrive (temperatures,
status). Under **Boiler model**, choose your boiler and **Save boiler
selection**; this changes the name and picture shown and which table explains
the display code. Only EMS Classic boilers are supported; EMS+ is planned for
version 1.1.

The **Display code** on the Boiler page and the Overview is shown in words,
with the raw code next to it, for example a blocking fault with what to do.
The words come from the manufacturer's manual for the chosen boiler model, or
from a general EMS table; a code that is not in the table stays the raw code.
A fault or lockout is marked as a warning or an error. In Home Assistant the
**Display code** sensor keeps the raw code as its state, with the meaning,
severity and advice as attributes, and the **Boiler** tab of the dashboard
shows the meaning.

Not every boiler reports every value. **Boiler → What your boiler reports** shows which
values your boiler has (**Values available**), which it does not have (**Not
fitted on this boiler**) and which have not come in yet (**Not reported
(yet)**). Home Assistant only creates entities for values the boiler has;
**Show anyway** reveals a value the boiler marks as not fitted.
A value that stays 0 for at least 10 minutes while the boiler is working (the Bosch EasyControl Adapter, for example, leaves the selected flow temperature and the burner and 3-way valve bits at 0) is listed as **not reported** ("stays 0 while the boiler works") and shown as "Not reported" instead of 0 or "off"; Home Assistant hides its entity.

### 4. Pair a Bluetooth thermometer

This example uses a thermometer with pvvx firmware; Shelly BLU H&T and Xiaomi
Monitor 3 work as well.

1. In the pvvx configuration page, set the advertising format to **BTHome
   v2**. Unencrypted is simplest; if you enable encryption, note the
   32-character bindkey. The older PVVX Custom format also works.
2. Place the sensor in the room, away from radiators, windows and direct sun,
   within Bluetooth range of the E32.
3. On the E32, open **System → Bluetooth sensors** and choose **Search nearby**. The list shows up
   to 32 of the strongest nearby devices.
4. Click your sensor and give it a clear name such as "Living room
   thermometer". Choose the profile **Thermometer with pvvx firmware
   (BTHome)**. Enter the bindkey only if you enabled encryption; keys are
   stored on the E32 and never shown again.
5. Choose **Save Bluetooth settings**. The E32 restarts by itself after about
   30 seconds to apply them.
6. After the restart the sensor shows a temperature. "Waiting" means nothing
   has been received yet: check distance, battery and address.

Up to eight Bluetooth sensors can be paired. Readings stay valid for 15
minutes, so a sensor that sends every few minutes is fine.

### 5. Add your first room on the E32

An E32 that was never linked to Home Assistant says "Not linked to Home
Assistant — you edit rooms here." on the **Rooms** page.

1. Choose **Add room** and give it a name, for example Living room. A new
   room opens fully. A saved room is a card that opens with a click, and its
   blocks **Temperature**, **Week program**, **Windows and doors** and
   **Persons** fold open separately; a closed block shows a one-line summary.
   The page remembers in this browser which blocks you opened.
2. Set the **State** to **Active** and the **Heating type** (radiators or
   floor heating). **Inactive until** switches a room off until a date.
3. Under **Temperature sources**, choose the Bluetooth sensor. Up to four
   sources in order: the first fresh one leads, the others are fallback.
4. Set the **Temperature without Home Assistant** (for example 19 °C) and the
   room's **Minimum** and **Maximum**.
5. Turn on **Use a week program**. Choose a template under **Start from a
   template**, set the **Comfort**, **Eco** and **Night** temperatures, and
   adjust the blocks per day (up to six switch points per day). Each
   temperature holds until the next switch point.
6. Choose **Save rooms**.
7. Then check the **Water temperature limits** on the **Home** page and
   choose **Save limits** after a change (default 30–60 °C; the maximum can
   be set up to 80 °C). Floor heating fed directly without a mixing valve
   usually needs at most 45–50 °C. The page shows your boiler's own maximum
   heating temperature; the E32 never asks for more than that.

The E32 stores large week programs in a compact form, so 8 rooms with four
switch points a day fit. A plan that is still too large is refused with a
message, and nothing changes.

### 6. Check it

On the **Rooms** page the room shows its temperature, its target and where the
target comes from (for example "Target temperature from the week program"),
and the calculated boiler request. The status reads "Measured". The
**Overview** shows the same rooms at a glance. Each room's card there says in
one line why the room heats or not, in the same words as Home Assistant: off,
window open, no reading, hot water, boiler rest, holiday, away, Smart warm-up
heating early, warm enough. This works without Home Assistant too.

## Adding Home Assistant

The [installation guide](INSTALL.md#8-mqtt-let-the-e32-talk-to-home-assistant) describes
each step in detail. In short:

You need Home Assistant 2026.10.0 or newer (tested with 2026.10.2 to
2026.10.4).

1. Set up Home Assistant's MQTT integration with a local MQTT broker, and
   enter the same broker under E32 **System → Network and Home Assistant → MQTT**: tick
   **Enabled** and enter a broker user name and password. The E32 does not
   connect to Home Assistant through a broker without a login.
2. Install the OpenThermostat integration package, restart Home Assistant and
   add OpenThermostat under Settings → Devices & services. You do not need to
   add a room in Home Assistant first.
3. Choose **Configure → E32 connection** and enter the E32 address and password.
   The address may be an IP address or a local name such as
   `http://openthermostat-a1b2c3.local`, `http://e32.fritz.box` or
   `http://e32.home.arpa`. Home Assistant switches the E32's MQTT connection
   to Home Assistant and waits for its first report (up to two minutes); the
   E32 may restart once.
4. From then on, rooms are managed in Home Assistant under **Configure →
   Rooms**. Your existing E32 rooms appear there unchanged.

Installed with an earlier integration version that needed a starter room in
Home Assistant? That room is no longer used. Remove it with **Settings →
System → Repairs → "Old Home Assistant room no longer used"** (or Configure →
Advanced and diagnostics → Remove old Home Assistant rooms); see
[the installation guide](INSTALL.md#remove-an-old-home-assistant-room).

### A room with a Home Assistant thermostat and a Bluetooth fallback

This example uses an existing thermostat in Home Assistant as the main source
and the paired Bluetooth thermometer as fallback.

1. Go to Settings → Devices & services → OpenThermostat → **Configure** →
   **Rooms**, and add a room or choose an existing one to edit.
2. Fill in the form:
   - **Temperature sources from Home Assistant:** your thermostat's climate
     entity or a temperature sensor. Sources in °C, °F or K are converted to
     °C for the E32.
   - **Bluetooth sensors on the E32:** the thermometer.
   - **Use the Bluetooth sensors first:** off, so the HA source leads and the
     Bluetooth sensor is the fallback.
   - **Setting device (optional):** your thermostat, if you want to turn the
     room up or down on it. Home Assistant then sets it to the week program's
     temperature at every switch point; see
     [Week program and setting device](#week-program-and-setting-device).
     Leave it empty to use the room's own thermostat in Home Assistant.
   - **Temperature without Home Assistant:** for example 19 °C.
   - **Week program on the E32:** the form starts with the "Workdays and
     weekend" template. Keep it and adjust it in the visual planner (the
     **Week program** tab of the OpenThermostat dashboard), or type one line
     per group of days, for example

     ```text
     mon-fri: 06:30 20.5; 22:30 18
     sat-sun: 08:00 20.5; 23:00 18
     ```

     A line without days applies to every day. Up to six switch points per day.
   - **Temperature limits** (folded section): the lowest and highest target
     this room may get.
   - **Windows and doors** and **Persons** (folded sections, optional): see
     [Temporary changes, open windows and away](#temporary-changes-open-windows-and-away)
     and [Away: the whole house and single rooms](#away-the-whole-house-and-single-rooms).
3. Choose **Submit**. Home Assistant forwards the selected entities to the
   E32 on every change and every five minutes.

The E32 in turn reports to Home Assistant calmly, in small messages: a room's
temperature (from 0.1 °C), the requested flow (from 1 °C) and the boiler
(flow and return from 0.5 °C, modulation from 5 %, burner, hot water and
faults at once) when they really change, at most every 10 seconds and
otherwise every 5 minutes; other boiler values at most once a minute; what it
learned every 15 minutes. The values are kept by the MQTT broker, so a
restarted Home Assistant shows them at once. They only become unavailable when
the E32 reports itself offline or about 3 minutes pass without its heartbeat.

With Home Assistant in °F, the editor shows and accepts °F; the plan on the
E32 stays in °C.

To test the fallback, temporarily disable the thermostat's integration in
Home Assistant. After its value expires, the room status changes to "Fallback
source" and the Bluetooth sensor leads.

### The E32 Rooms page once Home Assistant is linked

The page then shows the rooms read-only and says "Managed in Home Assistant".
**Edit here anyway** unlocks editing on the E32 for the current browser
session. After about ten minutes without contact the page says "Home
Assistant is not reachable — you can change rooms here." Every saved change
goes to the same plan, and Home Assistant shows it too. The plan carries a
revision number: if Home Assistant changed it in the meantime, the E32
refuses your save, reloads the plan and asks you to make your change again.
Nothing is overwritten silently.

### What happens when Home Assistant is offline

- Room temperatures from Home Assistant entities stop arriving. The next fresh
  source in the room's list takes over, for example a Bluetooth sensor the E32
  receives itself. The room card shows which source leads.
- Without a target from Home Assistant, the room follows its **week program**
  on the E32. Without a week program (or without a valid clock) it keeps its
  **temperature without Home Assistant**.
- If no source of a room delivers a usable reading, the room keeps its last
  value for 30 minutes and then stops asking for heat.

### Temporary changes, open windows and away

These work on top of the room plan and never change it. They only change a
room's **target**: the water temperature limits, the boiler's own limit and frost
protection stay as they are. During the trial run they are computed and shown, like
everything else.

- **Change temporarily** (E32 overview page, on each active room card, or the
  room's thermostat in Home Assistant): **Boost** heats to the room's maximum
  for an hour; a temperature can hold for 1, 2 or 4 hours or **until the next
  switch point** of the room's week program. The E32 ends it itself and the
  room returns to its week program, also after a restart. After a restart the
  E32 waits for a valid clock before it applies a stored change; until then
  the room follows its plan. A change made while the E32 has no valid clock
  lasts its duration and is not kept across a restart.
- **Window and door contacts** (Home Assistant: in the room form under
  Configure → **Rooms**, section **Windows and doors**; choose up to 8 per
  room: after you choose one, an empty field appears below it for the next):
  while any contact of a room is open for longer than its **Pause after**
  delay (2 minutes by default, set per room), the room pauses and only heats
  below 8 °C. When all are closed it resumes at once. The room card and the
  thermostat show the pause and its reason. On the E32 Rooms page the room's
  **Windows and doors** block shows whether a window or door is open; the
  contacts themselves are chosen in Home Assistant.
- **House mode** (E32: **Home**; Home Assistant: Configure → **House** →
  **House mode and holiday**, or the **House mode** control on the E32 device
  and on the dashboard):
  - **Automatic**: the people of the house decide. Choose them under
    Configure → **House** → **Presence and away temperature** (several person
    entities, or a group, zone or switch). When everyone has been away for the away delay (15
    minutes by default), every room is at most the away temperature. Someone
    home, or someone whose place is not known, keeps the house warm.
    A room can have **persons of its own** (the room editor in Home
    Assistant, section **Persons** → **Persons of this room**, for example a
    bedroom and its occupants). Such a room goes to its own away temperature
    (or the house one) when all of its persons have been away for the same
    delay, also while others are home. A room without persons of its own
    follows the house. The E32's room card shows what Home Assistant reports
    for the room's persons. See
    [Away: the whole house and single rooms](#away-the-whole-house-and-single-rooms).
  - **At home**: the week programs always, also when everyone is away (guests,
    a babysitter).
  - **Away**: every room is at most the away temperature until you switch back.
  - **Holiday**: away from now until a date and time, at the **Temperature on
    holiday** (Home Assistant: **Holiday ends** in Configure → House → House
    mode and holiday → House mode, or the **Holiday until** entity; E32 Home
    page: **Away until**, then **Start holiday**). Afterwards the house returns
    to Automatic. To plan holidays ahead, see the
    [holiday planner](#holiday-planner). The E32 starts
    warming up early enough to be at the week program's temperature when you
    are back (from what it learned, else 45 minutes per °C for radiators and 2
    hours per °C for floor heating).

  The away temperature is **Temperature when nobody is home** (15 °C by
  default): on the E32 device, on the E32 Home page and in Configure → House →
  Presence and away temperature, all three the same setting. Frost protection always stays on.
  On holiday the **Temperature on holiday** counts instead (see the
  [holiday planner](#holiday-planner)).

In Home Assistant each E32 room has a thermostat: current temperature,
target, mode *Auto* (week program), *Heat* (a temporary change) or *Off* (the
room is inactive in the plan), and the presets Comfort, Eco, Night and Boost.
Away is the house mode, not a preset of one room. Comfort, Eco and Night are
the room's three week-program levels, the same as in the week planner, where
each is set on its own. A new target on the thermostat lasts until the next
switch point; a room without a week program keeps it for the **Length of a
manual change** under Configure → **House** → **Comfort defaults for rooms**,
and a room with only a fixed target changes that fixed target in
the plan.

### Away: the whole house and single rooms

OpenThermostat turns rooms down while people are out. It does this for the
whole house, and for single rooms.

**The three rules**

1. **Everyone is away.** Every room goes to the house away temperature
   (**Temperature when nobody is home**, 15 °C by default). The house mode
   **Away** does the same. On **Holiday** every room goes to the
   **Temperature on holiday** instead, which is the away temperature until you
   set another.
2. **Only the people of one room are away.** A room can have its own people.
   When all of them are away, that room goes to its own away temperature,
   even while others are home. A room with two people only cools down when
   both are out.
3. **A room without its own people** follows the house. It only cools down
   when everyone is away (rule 1).

A room with its own people but without its own away temperature uses the
house away temperature in rule 2.

| Situation | Room without its own people | Room with its own people and its own value | Room with its own people, no own value |
| --- | --- | --- | --- |
| Someone home, the room's people home | Week program | Week program | Week program |
| Someone home, the room's people away | Week program | Its own away temperature | House away temperature |
| Everyone away | House away temperature | House away temperature | House away temperature |
| House mode Away | House away temperature | House away temperature | House away temperature |
| House mode Holiday (or a planned holiday running) | Temperature on holiday | Temperature on holiday | Temperature on holiday |
| House mode At home | Week program | Week program | Week program |

**Examples** (house away temperature 17 °C, living room 21 °C)

- **Jolien's study.** The study has one person: Jolien. Its own away
  temperature is 16 °C. Jolien goes out and Mark stays home. The study goes
  to 16 °C. The living room has no people of its own, so it stays at 21 °C.
- **Both out.** Jolien and Mark both leave, so everyone is away. Every room
  goes to the house value of 17 °C, the study too. When everyone is out, the
  house value counts for every room.
- **A room for two.** The bedroom belongs to Jolien and Mark. Jolien leaves,
  Mark is still home: the bedroom stays warm. It cools down only when both
  are out.

**Good to know**

- The away temperature is an upper limit. A room whose program is already
  cooler stays cooler.
- **At home** ignores who is home. No room cools down, also when everyone is
  out (for guests or a babysitter).
- An open window still pauses the room. That always comes first.
- Frost protection always stays on: any room below 8 °C asks for heat.
- A person counts as away only after the away delay (15 minutes by
  default). Someone whose place is not known counts as home: in doubt, the
  room stays warm.

**Coming home**

When one of the room's people comes back, the room follows its week program
again at once and starts to heat. The E32 cannot know in advance when you
come back, so the room needs some time: roughly 45 minutes per °C with
radiators and about 2 hours per °C with floor heating. A floor-heated room
that went 4 °C down can need most of a working day. For floor heating,
choose an own away temperature only 1 or 2 °C below the normal temperature.

A **Holiday** has an end date. Then the E32 starts warming up early enough to
be warm when you are back (see the [holiday planner](#holiday-planner)).

**How to set it up** (in Home Assistant)

1. Choose who lives in the house: Settings → Devices & services →
   OpenThermostat → **Configure** → **House** → **Presence and away
   temperature**.
2. Give a room its own people: **Configure** → **Rooms** → **Edit or remove a
   room** → choose the room → section **Persons** → **Persons of this
   room**.
3. In the same section, fill in **Temperature when this room's people are
   away**, for example 16 °C. Leave it empty to use the house away
   temperature.
4. Choose **Submit**.

The E32 **Rooms** page shows the same value in the room's **Persons** block,
and you can change it there too, also without Home Assistant. The people
themselves are chosen in Home Assistant, because Home Assistant knows where
they are.

The value is stored on the E32 with the room. It is part of the E32's
settings backup and comes back with a restore.

**Where you see it**

- The E32 **Overview**, in the room's reason line: "Away: nobody of this room
  is home (16 °C)" or "Away: everyone is away (17 °C)". On holiday the line
  says "Holiday until …" with the temperature on holiday.
- The E32 **Rooms** page, in the room's **Persons** block.
- The room's thermostat in Home Assistant shows the lower target. Its
  attributes `away_reason` (`room_persons`, `everyone` or `house_mode`) and
  `own_away_temperature` tell why.

E32 firmware up to 1.0.0-rc.2 has no away temperature per room. Home
Assistant and the E32 page then do not show the field, and every room uses
the house value.

### Holiday planner

Plan holidays ahead, up to 8, each with a start and an end (back home). A
holiday starts and ends by itself. During it every room stays at most the
**Temperature on holiday** (5–25 °C); until you set one, that is the away
temperature (**Temperature when nobody is home**). Frost protection always
stays on. The E32 warms the rooms up before the end, so the house is warm when
you are back, and afterwards the house mode is what it was before the holiday.

**In Home Assistant:** Configure → House → **House mode and holiday**. The
menu lists the planned holidays and has:

- **Plan a holiday**: choose **Starts** and **Ends (back home)**. A start in the
  past starts the holiday now; the end is at most a year ahead. Holidays that
  overlap become one.
- **Change or remove a holiday** (shown while a holiday is planned): choose the
  holiday, change its times, or tick **Remove this holiday**.
- **Temperature on holiday**: the same setting as the number *Temperature on
  holiday* on the E32 device and on the E32's Home page.
- **House mode**: the house mode itself, as before.

While a holiday runs, Configure → House also has **Stop holiday**: it ends the
holiday now and the house goes back to its mode. The **Overview** tab of the
dashboard shows the next holiday ("Holiday from 20 Dec to 3 Jan", and "On
holiday until 3 Jan" while it runs).

**On the E32:** the **Home** page has a block **Holidays**: the list with
**Change** and **Remove**, **Add a holiday** (**From**, **Until**, **Save
holiday**), **Temperature on holiday (°C)** with **Save**, and, while a holiday
runs, "On holiday until …" with **Stop holiday**. Home Assistant and the E32
page edit the same list.

Good to know:

- Saving a holiday needs the E32's clock. Without a valid time the E32 says
  "The E32 clock is not set yet, so a holiday date cannot be used. Try again in
  a minute."
- Choosing **Automatic**, **At home** or **Away** as the house mode ends a
  running holiday; holidays planned for later stay.
- A holiday that is over leaves the list by itself.
- Planned holidays and the temperature on holiday are part of the E32's
  settings backup. A restore leaves out holidays that are already over.
- A "Holiday until" date set before rc.4 was converted once into a planned
  holiday with the away temperature.

### Week program and setting device

Every room runs its own week program on the E32, also without Home Assistant.
A new room starts with "Workdays and weekend" (about 20 °C, 18 °C during the
day on workdays, 16 °C at night); change it in the week planner. The planner
works with three levels, **Comfort**, **Eco** and **Night**; set each
temperature on its own (equal values and any order are allowed) and paint the
days with them. **Copy…** copies a day, **Undo** takes back a step, and
**Advanced: edit as text** shows the program as text. If rooms have
no program yet, Settings → System → Repairs offers to give them one.

Optionally each room has a **setting device** (the room editor's "Setting
device" field): a thermostat or radiator valve in Home Assistant (for example a
tado or a TV02), or a number with a target. Home Assistant then shows the
program's temperature on that device at every switch point, and when the room
or the E32 changes or comes back. Turning the device changes the room until the
next switch point, like a change on the room's thermostat in Home Assistant or
on the E32 page. Turn off the device's own schedule (manual mode); otherwise it
changes the temperature by itself, and Repairs says so when it notices.
Without a setting device the room's thermostat in Home Assistant and the E32
page set the room. Only the device you chose is ever written to, never while
the room is off or paused for an open window, and at most once a minute.

Without Home Assistant the E32 keeps running the program; changes on the
device are not seen until Home Assistant is back, and then the program's
temperature is shown on the device again.

A setting device is a real device, also during the trial run: a radiator valve then
follows the week program, and a thermostat that controls your boiler (such as
a tado) gets the program's temperature, so the program decides through it
when the boiler heats. Leave the field empty if you only want to watch
first.

Bluetooth window sensors (for example Shelly BLU Door/Window) paired on the
E32 itself are not supported yet; connect them through Home Assistant.

### Warm on time (Smart warm-up)

A time in the week program means "warm at that time": with 21 °C at 09:00 the
room should be 21 °C at 09:00, not start warming then. **Smart warm-up** does
that by itself. The E32 learns how fast each room warms up and cools down, and
starts heating early enough, with the coolest water that still gets the room
warm in time (cooler water lets the boiler condense, so it uses less gas). It
never asks for water below the lowest or above the highest water temperature
you set, nor above the boiler's own maximum, and it starts at most 8 hours
ahead.

**From the first morning.** A room that is not learned yet does not wait for
the program time. The E32 starts early at once, as an **estimate**: 2 hours
per °C that the room is still below its coming target for floor heating, 45
minutes per °C for radiators, and at most 3 hours (floor) or 90 minutes
(radiators) ahead. The pages say so: "starts at 07:40 (estimate; it learns from
every morning)". The warm-up time counts as learned after one water
temperature; until the coolest water is learned too, the pages say "The
warm-up time is learned; the coolest water is still being learned."

**It checks every morning.** After each rise of the program the E32 looks at
whether the room was warm at that time (within 0.1 °C of the target). More than
10 minutes late: the warm-up time grows by 10 %, so the next start is earlier.
More than 15 minutes early: it shrinks by 8 %, so the next start is later. A
room that is not warm within 3 hours counts as late. Only starts the E32 really
made are judged. The E32 keeps the result for each room over a restart and
when you reorder or rename rooms.

*What to expect in the first days:* the first starts are a guess, so a room can
be warm a little early or late. Every morning moves the next start by 10 % or
8 %, so it gets closer with each morning, and the pages tell you how it went.

The room card on the E32 Overview, the Home page's "What the thermostat has
learned" and Home Assistant (the learned overview, and the attribute
`smart_warm_up` of the room's thermostat) say what it does, for example:

- "Smart warm-up: starts at 07:20 so it is 21 °C at 09:00." (learned)
- "Smart warm-up: starts at 07:40 so it is 21 °C at 08:50 (estimate; it learns
  from every morning)." (an estimate)
- "Smart warm-up: heating early for 08:00 (21 °C)" (the room's reason line
  while it heats early)
- "Yesterday warm at 09:12 (12 min late); tomorrow 10 % earlier." (the morning
  check. The second part says how much earlier or later than its standard the
  room now starts, "tomorrow 8 % later" for example; the steps build on each
  other, and the part is left out while the start is at its standard.)

Weather compensation is on by default too: colder outside means warmer water,
before the rooms cool down. (Earlier releases called it "Follow outdoor
temperature" or "heating curve".) The E32 starts with a standard setting and
learns your house's own from steady heating periods of three hours. The
learned overview in Home Assistant says which it uses ("Weather compensation:
standard for now, learning from your house (2 of 6 steady periods)" or
"Weather compensation: learned for your house"); the E32 Home page says the
same. Without an outdoor temperature (from the boiler or Home Assistant) the
water temperature follows the rooms only, and the status says so. The coolest
water per room is used once learned ("Coolest water: still learning from each
warm-up" until then).

**Water temperature in hard frost (−10 °C)** says how warm the water to your
heating gets when it is −10 °C outside. In milder weather the E32 picks less.
Not sure? Leave it on **Automatic** (floor heating 40 °C, radiators 55 °C):
the E32 learns it for your house. You find it in Home Assistant under
Configure → Heating and boiler → Weather compensation → Advanced, as a
selection on the E32 device, and on the E32's Home page under Heating settings
→ Advanced.

Both are on for every installation. An installation that had the former
option "Warm on time with the coolest water" or weather compensation (then the
heating curve) off (their default) has them on after the update; what you
switch off yourself stays off. Switch them off under E32 **Home → Heating
settings → Advanced**, under **Configure → Heating and boiler** in Home
Assistant (**Smart warm-up** and **Weather compensation**), or with the
switches on the E32 device. Without Smart warm-up heating starts at the program
time: it may be cooler for a while after each program time, and floor heating
can take an hour or more.

### Energy inputs and heating advice

Under **Configure → Energy and outdoor temperature** you can choose a gas
meter (m³ or kWh), a gas price sensor or a fixed price, the calorific value of
your gas, an outdoor temperature sensor or weather entity, your boiler's
heating power and a water meter (a flow in L/min, or a meter reading in m³ or
L). All fields are optional; leave a field empty to not use it. With a gas
meter the E32 calibrates its heat and gas estimates. The water meter stays in
Home Assistant: it tells tapping from keeping warm (see below).

The **Heating advice** sensor and its dashboard section list what could be
tuned: short cycling, a maximum heating temperature far above what the house
needs, a return too warm for condensing, the flow your rooms really need,
night setback, hot-water temperature and water pressure. Each item says what
was seen, why it matters, what to change and where, with its confidence. It
is advice only and never changes a setting; a rule without enough data says
what is missing.

### Daily summary and warnings

The **Heating problem** sensor answers "is my heating OK?". It turns on only
for real problems that last:

- a room without a usable measurement for 30 minutes;
- no report from the E32 for 10 minutes;
- low or high water pressure;
- a room that asks for heat but stays more than 0.5 °C below its target for
  3 hours (a gap in the E32's data starts the wait again);
- the E32 online but without a working link to Home Assistant for 15 minutes;
- after the switch-over: a warning of the E32's active control for 5 minutes,
  or the E32 waiting 10 minutes for you to confirm the switch-over again. A new
  installation that never let the E32 control its boiler is not a problem while
  it waits: its next step is the boiler test on the Rooms page.

The burner switching on and off often is not on this list: the E32 lengthens
the burner rest step by step, and Home Assistant and the E32 show it as
learning information.

Each problem except the water pressure (which has its own message) also
appears under **Settings → System → Repairs** as **Heating needs attention**,
and clears itself once the cause is gone. The sensor's `problems` and
`reasons` attributes say what is wrong, so you can use it in your own
notification automation.

The **Daily summary** sensor on the OpenThermostat device shows the last
finished day; its attributes hold the last two weeks (three weeks are kept).
Per day: burner time, burner starts and short runs (under 10 minutes), gas
for heating and hot water (and tapping and keeping warm), the outdoor
temperature when one is set, and per room how long it asked for heat, how
long it took to reach a raised target (late after 2 hours) and the missed
comfort minutes. Only time with E32 data counts; a day with less than 20
hours of data is marked partial. **Burner time**, **Burner starts** and
**Missed comfort time** are running totals with long-term statistics, so
their change per day is the daily figure. The **Boiler** tab of the dashboard
shows yesterday in words and the last days as bars.

### Radiator valves

Radiator valves (TRVs) follow their room in one of two ways:

- **Zigbee2MQTT valves** on the same MQTT broker: the E32 drives them itself.
  Home Assistant is not needed for it; it only shows and configures the valves.
- **Any other valve Home Assistant controls** (ZHA, Z-Wave, Shelly, a cloud
  integration, and so on): it is a `climate` entity in Home Assistant, and
  Home Assistant drives it on the E32's behalf, with the same rules.

Supported models:

| Model | What is sent | What is read back |
| --- | --- | --- |
| Bosch BTH-RA (recommended) | setpoint, room temperature (`remote_temperature`), manual mode | valve position (`pi_heating_demand`), battery % |
| Sonoff TRVZB | setpoint, heat mode (`system_mode`), room temperature (`external_temperature_input`, then the sensor set to it) | battery % |
| Sonoff TRV Gen2 (TRV-ZBT) | the same as the TRVZB (5–30 °C); needs Zigbee2MQTT 2.12.1 or later | battery % |
| Tuya TV02 | setpoint (manual preset) | low-battery flag |
| Other | setpoint (`occupied_heating_setpoint`) | battery % or low flag |
| Home Assistant climate entity | by Home Assistant: setpoint (`climate.set_temperature`), heat mode (`climate.set_hvac_mode`) | from the valve's device in Home Assistant: battery % or low flag, opening when it reports one |

The Zigbee2MQTT keys come from the Zigbee2MQTT device pages; check them on
your own valve before you rely on them.

For the Sonoff valves the E32 first sends the room temperature and only then
selects it as the valve's sensor, because Zigbee2MQTT refuses that choice
without a value. It reads which sensor the valve reports: older Zigbee2MQTT
versions call the choice `external`, newer ones `remote_temperature`, and the
E32 uses whichever your valve reports. If the valve still uses its own sensor
10 minutes later, the E32 asks again. The heat mode keeps the valve off its own
week schedule; the E32's program is the only one. The valves' own settings,
such as the opening limits, window detection and child lock, stay yours to set
in Zigbee2MQTT.

**Choosing the valves.** In Home Assistant: Configure → **Rooms** → *Edit or
remove a room* → *Edit room*, section **Radiator valves** of the room form
(also when you add a room). Just pick the valves' climate entities, of any
brand; OpenThermostat's own thermostats, the room's thermostat source and the
valves of other rooms are not offered. OpenThermostat works out the route of
each valve itself and shows it in plain words:

- *works without Home Assistant*: a Zigbee2MQTT valve of a model the E32
  knows (Bosch BTH-RA, Sonoff TRVZB, Sonoff TRV Gen2, Tuya TV02) on the E32's
  Zigbee2MQTT base topic. Its Zigbee2MQTT friendly name comes from the
  device's MQTT topics, so a device renamed in Home Assistant still works.
- *through Home Assistant*: every other valve, including a Zigbee2MQTT valve
  whose model is not recognised.

Under **Choose the models myself (advanced)** you can still choose the model
of a Zigbee2MQTT valve (or *Through Home Assistant*) after saving. A valve that
was set up before keeps its model. A valve set up *through Home Assistant*
that the E32 can drive itself moves to the E32 the next time you save the room
(the form shows it first); only choosing *Through Home Assistant* for it under
Advanced keeps it there, and that choice is remembered. A stored Zigbee2MQTT
valve Home Assistant does not know is listed under **Kept valves** and keeps
working.
On the E32 itself: the room card
on the Rooms page has a **Radiator valves** block with its own *Save valves*
button; Home Assistant valves show there read-only, as *Home Assistant climate
entity (set in Home Assistant)*. At most 4 valves per room and 16 in all.

**Nothing happens until you switch it on.** Each room has a **Valve control**
switch (entity ID ending in `_valve_control`), off by default. The E32 sends
to a room's valves only while that switch is on **and** the E32 controls the
boiler itself (active control after the attended switch-over). During the trial run,
or with the switch off, nothing is sent to any valve, and a room without valves
behaves exactly as before. The session field `actuator_output_enabled` says
whether the E32 drives valves right now.

**What the E32 does with them.** It sends the room's target as the valve's
setpoint and, where the valve takes one, the room's own measured temperature;
the valve's own regulator then sets its opening. Valves that report their
position feed back into the boiler flow: when every valve that asks for heat is
only partly open the flow goes down a step, when one is fully open while its
room is still more than 0.5 °C too cold it goes up a step; at most 1 °C per
10 minutes and 8 °C in all. The water temperature limits and the boiler's own
maximum still apply.

**All valves closed.** When every room that asks for heat has only valves that
report themselves closed (5 % or less) for 10 minutes, the E32 stops its boiler
request (reason `valves_closed`): there is no open circuit to heat. A room
without valve control (for example the floor heating) keeps the request going,
and a valve that stopped reporting never counts as closed.

**Battery saving.** A new setpoint only on a change of at least 0.5 °C (at
most once a minute, refreshed every 6 hours); the room temperature at most
every 10 minutes and at least every 25 minutes. A simulated two weeks with four
valves costs well under 2 % battery per valve.

**Home Assistant valves.** Home Assistant sends such a valve the room's target
(8 °C while the room is off), rounded to the valve's step and within its own
limits, on the same rules: only while the room's valve control is on and the
E32 controls the boiler itself, a new setpoint only on a change of at least
0.5 °C, at most once a minute and again after 6 hours. Once per control period
it sets the valve to `heat` when the valve has that mode; it never turns a
valve off. It does not send the room temperature, and these valves do not feed
back into the boiler flow (a room with one never counts as all closed).
Health: a valve that is unavailable for 2 hours is offline; the battery comes
from a battery sensor on the valve's device in Home Assistant (or its
low-battery sensor). The valve counts in the room's *Valve position*, *Valve
battery* and *Valve problem* entities and in Repairs, like a Zigbee2MQTT valve;
on the E32 page its state reads *Driven by Home Assistant*. A failing service
call is logged once and tried again a minute later at the earliest.

**When something fails.**

- A battery at about 20 % or less: a Repair in Home Assistant and a red badge
  on the dashboard; the valve is still driven.
- A valve that has not reported for 2 hours: a Repair; the room is shown as
  degraded but keeps heating on its other temperature sources. When the valve
  is back it gets its mode, setpoint and room temperature again.
- No room measurement (Home Assistant down, a sensor gone): the E32 stops
  sending the room temperature, so the valve falls back to its own sensor, and
  after 30 minutes the room stops asking for heat. The E32 never heats blind.
- A room whose valve control is on but that has only one temperature source:
  a Repair advising a separate sensor, for example a Bluetooth thermometer.
- The E32, the broker or Zigbee2MQTT gone: the valves keep regulating on their
  last setpoint.
- Home Assistant gone: Zigbee2MQTT valves stay driven by the E32 (as long as
  the broker runs); Home Assistant valves keep their last setpoint until Home
  Assistant is back.

**MQTT broker.** The E32's broker user must be allowed to subscribe to
`zigbee2mqtt/<valve name>` and to publish to `zigbee2mqtt/<valve name>/set`
(or the base topic you use in Zigbee2MQTT).

## Reading the trial run comparison

If a thermostat controls your boiler over the EMS bus, the comparison puts the
E32's decision next to what that thermostat actually asked of the boiler. You
find it on the E32 Rooms page under "Comparison with your thermostat (today)".
Home Assistant adds today's figures as sensors (heating time and burner
starts today for the E32 and the thermostat, and their agreement) once it has
seen such a thermostat; a home without one gets no comparison sensors. The
generated dashboard links to the comparison from the **Learning and settings**
tab ("E32 compared with your thermostat") only during the trial run, and only while that thermostat is
heard. Once the E32 controls the boiler and hears no thermostat any more, the
link and the Comparison page disappear, and after about ten minutes Home
Assistant removes the comparison sensors (their history is kept; a sensor you
renamed or changed stays). They come back by themselves if you return to a
trial run with a thermostat on the bus.

| Line | Meaning |
| --- | --- |
| Compared time | How long both sides were observed today. |
| Heating time E32 / thermostat | How long each side asked for heat. |
| Burner starts E32 / thermostat | How often each side would start or started the burner. Fewer starts is gentler on the boiler. |
| Agreement (both on or both off) | Share of the compared time in which both sides made the same choice. |
| E32 water temperature range / Thermostat water temperature range | Lowest, highest and mean requested water temperature (flow temperature). |
| E32 starts within 5 min of a thermostat start | How many of the thermostat's starts the E32 matched closely. |
| Without thermostat data | Time in which the thermostat's request was not seen; excluded from the agreement. |

The table below shows the last seven days.

### Ready for the E32 to control the boiler?

Right above the comparison, the Rooms page shows the check **Ready for the E32
to control the boiler?**. The E32 judges its own trial run, so you need no Home Assistant,
token or script for it. Each line is green (passed), orange (waiting for more
data, with the progress so far, such as "51 of 72 h") or red (with what to do):

| Line | Passes when |
| --- | --- |
| Stable for 72 hours | 72 hours without a hang or unexpected restart. A planned restart (a firmware update, the restart button, restoring settings) does not reset it; a crash, a watchdog or supervisor restart or a power cut does. |
| Heating periods compared | At least 10 heating periods of the thermostat, among them a night setback, a morning warm-up and an hour without heat demand. |
| Heat at the same moments | At least 20 starts and stops of the thermostat; 80 % of them with an E32 start or stop within 30 minutes, half within 5 minutes and 90 % within 15 minutes. |
| Water temperature stays below the safe maximum | The E32 never asked for more than the lowest of the plan maximum, the boiler's own heating limit and 80 °C. Judged after an hour of heat requests; a single request above it fails. |
| Not more burner starts than the thermostat | After 10 thermostat periods, the E32 has no more heating periods than the thermostat. |
| Room sensors work | Every active room has a fresh reading, and a backup sensor has stepped in at least once. While no room has a backup sensor this line stays red. |

Only when every line passes does it say "Ready: start the boiler test and takeover
above"; that test is the last step (see [The attended switch-over](#the-attended-switch-over)).
The trial run is optional. The figures cover the last seven days and are kept
over restarts. In active mode the check is hidden.

Without an EMS thermostat on the bus there is nothing to compare. The check
says so and lists only the stability, the room sources, the boiler heard on
the bus (in the last 5 minutes) and the boiler maximum known (the E32 read the
boiler's heating limit itself).

Home Assistant shows the same check as the sensor *Ready for E32 control* on the
E32 device (Ready, Waiting for more data, Not ready, or Not applicable once the
E32 controls the boiler), with each line's result and figures as attributes,
and on the **Learning and settings** tab of the generated dashboard (next to the
comparison during a trial run). It adds one thing the
E32 cannot see of itself: when Home Assistant did not hear the E32 for five
minutes or more, the 72 hours count from the moment it was heard again. The
sensor raises no repair issue.

The trial run does not show how the boiler and its adapter react to the E32's
request; that is tested during the switch-over.

### Learning results

Each room device in Home Assistant also has three learning sensors. With
**Smart warm-up** on (the default, see "Warm on time" above) the E32 uses what
they show once a room has been learned; switched off they are advice only.
During the trial run nothing is sent to the boiler either way.

| Sensor | Meaning |
| --- | --- |
| Learning status | Collecting data, Learning or Ready. Learning uses stable heating periods without hot water and with fresh readings, so it takes several heating periods. |
| Recommended water temperature (1 °C) | The coolest water (flow temperature) that warms the room by 1 °C in an acceptable time. Unknown until learned. Its attributes show what the room control asks now, for comparison. |
| Predicted heating start | When the E32 would start heating to reach the next higher week-program temperature on time. Its attributes compare night strategies (holding a night temperature versus letting it drop) in kWh, m³ and €. |

What the E32 has learned is kept when it restarts, loses power or gets a
firmware update, so learning carries on where it was (it is saved every 6
hours, at midnight and before a restart or update; a power cut loses at most
the last few hours).

The predictions need a valid clock; the night-setback estimate also needs an
outdoor temperature (from the boiler or from Home Assistant). The product
device also shows hot water today (taps, keeping warm, burner time) and
whether the burner switches on and off too often (information, not a fault).

### Yesterday in figures

Once the E32 has measured a day, **Yesterday** shows how that day went, so you
can see whether the thermostat gets better. The figures are kept over a
restart; whatever the E32 did not measure is left out.

| Figure | Meaning |
| --- | --- |
| Heating time | How many hours the heating ran. |
| Burner starts per heating hour | How often the burner started for each hour of heating. Fewer starts are gentler on the boiler. |
| Short burner runs | The hours in which the burner switched on and off too often. |
| Gas for heating (estimate) | kWh; an estimate, not a meter reading. |
| Degree days (how cold it was) | A measure of how cold the day was (base 18 °C), so you can compare days. |
| Per room | How many minutes late or early the room was warm ("warm 12 min late", "warm 5 min early" or "warm on time") and how far it went above its target ("0.3 °C too warm"). |

In Home Assistant it is a section of the **Learning and settings** tab ("Living
room: warm 12 min late · 0.3 °C too warm", "Burner: 2.1 starts per heating
hour", "Gas for heating: 8.4 kWh"). On the E32 it is on the **Home** page, under
**What the thermostat has learned**. The **Boiler** tab of the dashboard has its
own **Yesterday** section, the daily summary (see above); this one is the
thermostat's scoreboard.

Each figure is also a sensor, so Home Assistant keeps its history: per room
**Warm on time** (minutes) and **Overshoot** (°C), and on the OpenThermostat
device **Burner starts per heating hour**, **Short cycling hours**, **Heating
gas yesterday** and **Gas per degree-day**. The state is yesterday's figure. A
sensor appears once the E32 has a figure for it; with firmware before rc.4 there
are none.

### Gas for heating, hot water and keeping warm

With a gas meter in the energy options, *Gas for heating* and *Gas for hot
water* share the meter by what the boiler did (without a meter they are an
estimate from the burner power the boiler reports). Hot water is split once more:
*Gas for tapping hot water* is what taps used, *Gas for keeping hot water
warm* is the boiler reheating its store or exchanger without a tap, nothing
more. Their attributes show per day the rounds, burner minutes and gas. The
E32 decides per hot-water episode with the most direct signal the boiler
reports (the attribute `dhw_method`):

- `flow`: a DHW flow meter. Flow during the round is a tap.
- `storage`: a boiler with a cylinder reports charging. The E32 cannot tell a
  tap from a reheat there, so its hot water stays in *Gas for hot water* only.
- `dhw_temperature_fall`: neither, so the DHW temperature. A tap brings cold
  mains water, so the temperature falls deep or stays down. A small tap
  (washing hands) may only cool the sensor before the round, so a round also
  counts as a tap when the sensor fell before it faster than it does before
  this boiler's own rounds at night (01:00-05:00, when nobody taps). The
  sensor sits where heat enters the store and falls fast after each reheat
  while the heat mixes through, so this is only a comparison with the nights,
  not a heat loss. The attribute `dhw_baseline` says `night` once the E32 has
  seen four night rounds since its last restart, and `default` before that
  (then only a fall faster than 2 °C a minute counts).
- `water_meter`: with a water meter in the energy options, Home Assistant
  decides instead, for every boiler. A round with water flowing during it, or
  in the 2 minutes before it, is tapping; one without is keeping warm. A round
  the meter did not cover (no reading) stays in *Gas for hot water* only. A
  water meter also sees cold water (a toilet flush), so a round at the same
  time as one counts as tapping. On the owner's boiler the temperatures alone
  missed many small taps: on 31 Oct 2026, 23 of 56 rounds were keeping warm by
  the meter, against 40 by the temperature rule.

Add heating and hot water to the Energy dashboard; tapping and keeping warm
are parts of hot water, so leave them out there.

*Boiler activity* says what the boiler does now: idle, heating, tapping,
keeping warm, charging the cylinder, or hot water it cannot sort. A tap shows
as keeping warm until its fall is clear, usually within half a minute. On the
dashboard's **Boiler** tab, the hot-water section shows this as a 24-hour timeline next to
the boiler's heating state, and, once tapping or keeping warm has counted gas,
the gas per day for heating, tapping and keeping warm over the last week. On
the E32's own Overview, the boiler history has a hot-water strip: the share of
each 5 minutes tapping and keeping warm (a cylinder's charging counts as
keeping warm there).

## Backup and restore

System → **Backup and restore** saves the settings of the E32 in
one file: network and time (host name, time zone, time server), MQTT and the
Home Assistant link, the room plan with its week programs, the planned
holidays, the Bluetooth sensors, the flow options, the boiler model and the
page language. It also
holds what the thermostat has learned about your rooms, so a replacement E32
carries on learning where the old one was. If that part of a backup cannot be
read, the restore skips it with a note and the E32 learns from the start.

- **Passwords and keys.** By default the file holds no secret. The page lists
  what you need to enter again after a restore: the MQTT password, the
  OpenWeather key and the Bluetooth sensor keys. Tick *Include passwords and
  Bluetooth keys* and choose a passphrase (8 to 64 characters) to keep them in
  the file, encrypted (AES-128-CCM, key from the passphrase with
  PBKDF2-SHA256). The Wi-Fi password and the web page password are never in
  the file.
- **Restore** on a new or reset E32: first connect it to your network (Wi-Fi
  setup or Ethernet) and sign in, then choose the file and **Check backup**.
  The E32 checks the whole file and shows what will change, what it skips and
  what you need to enter again. Nothing is saved until you choose **Restore
  these settings**. A backup without a passphrase holds no MQTT password, and
  MQTT stays off until you enter it again under System → Network and Home Assistant → MQTT. If saving one part fails, the E32 puts the earlier
  settings back. When network or Bluetooth settings change, the E32 restarts
  about 10 seconds later; sign in again afterwards.
- **What a restore never does.** It does not change the Wi-Fi network or the
  port of the web page, it switches from Wi-Fi to Ethernet only while an
  Ethernet cable is connected and never from Ethernet to Wi-Fi, and it
  restores the takeover confirmation: the rooms keep the mode of the backup, but a new or reset E32 sends
  nothing to the boiler until you confirm the takeover on its Rooms page. A restore is refused while the E32
  controls the boiler or a boiler test is running.

### Automatic backups in Home Assistant

With the Home Assistant integration you do not need to download files
yourself. Once the E32 is connected (Configure → E32 connection), Home
Assistant fetches the same backup file from the E32 every day, and once
shortly after Home Assistant starts when the last backup is older than 24
hours.

- **Passwords and keys** are always included, encrypted with a random
  passphrase that Home Assistant makes once for this installation and keeps
  with the integration. You never type it. The Wi-Fi password and the E32
  password are still never in a backup.
- **Where they are.** Home Assistant keeps them in its own `.storage` folder,
  so its own backups (Settings → System → Backups) contain them too: the
  newest backup of each of the last 7 days, plus the one made right before the
  last restore.
- **On the E32 device** in Home Assistant: the button **Back up E32 settings
  now** makes a backup at once, and the diagnostic sensor **Last E32 backup**
  shows when the last one succeeded (its attributes: how many backups are kept
  and the size of the newest).
- **When it fails.** If no backup succeeds for 3 days, Settings → Repairs
  shows *No recent backup of the E32 settings*. Check that the E32 is on and its
  web page opens, and that its password in Home Assistant is still right. The
  message goes away after the next successful backup.

To put a backup back: Configure → **Advanced and diagnostics** → **Restore
settings to this E32**. Choose the backup by date. The E32 checks it first, and
Home Assistant shows what changes, what is skipped and what you need to enter
again. Nothing changes until you tick the confirmation. Right before the
restore, Home Assistant also backs up the E32 as it is now. The rules are the
same as on the E32 page. The rooms keep the mode of the backup; a new or reset
E32 controls the boiler only after you confirm the takeover on its page
(Rooms → Boiler test and takeover). A restore is refused while the E32 controls the
boiler or a boiler test is running. When the network or Bluetooth settings
change, the E32 restarts, and Home Assistant waits until it answers again.

### Replacing a broken E32

1. **Flash the firmware** on the new E32 over USB, as for a first
   installation (see the README).
2. **Join the network**: connect the new E32 to your Wi-Fi with its setup
   access point, or plug in Ethernet, and note its address. Sign in on its web
   page once and change the default password (System → Password).
3. **Connect it to the integration**: in Home Assistant open Configure →
   Advanced and diagnostics → **Restore settings to this E32**. Enter the new
   E32's address and password there. The old E32's saved password is never
   sent to another address.
4. **Restore**: choose the newest backup, read the summary, tick the
   confirmation and submit. The E32 gets the network and time settings, MQTT
   and the Home Assistant link (with the MQTT password), the rooms and week
   programs, the Bluetooth sensors with their keys, the flow options and the
   boiler model. It restarts, and Home Assistant links this installation to
   the new E32 (its address, password and identity). Your entities, history
   and dashboards stay as they were.

After the restore, enter what the summary lists (for example a Bluetooth key
that was not in the backup). If the old E32 controlled the boiler, follow
[the switch-over procedure](SWITCHOVER.md) again before you confirm the
takeover.

## Logs and the diagnostics console

System → **Diagnostics and system log** shows what the E32 is doing. It keeps the last 512 log
lines in its external memory (PSRAM); they are gone after a restart. Filter by
source (ESP or EMS), level or text, pause the view or download it.

The **diagnostics console** on the same page answers a fixed list of
read-only commands. Type `help` for the list:

| Command | Shows |
| --- | --- |
| `status` | All sections below at once |
| `version` | Firmware version and build |
| `memory` | Internal memory and PSRAM |
| `tasks` | Tasks and their lowest free stack |
| `nvs` | How full the settings storage is |
| `mqtt` | MQTT connection and its counters |
| `sessions` | Signed-in web sessions (age and idle time, never their keys) |
| `restarts` | The last restart reason and the previous run |
| `bluetooth` | The Bluetooth sensors |
| `rooms` | Rooms, targets and the heating request |
| `boiler-profile` | Which boiler values this boiler has |
| `log 50` | The last 50 log lines (1 to 100) |

The console never changes a setting and cannot run anything else. Two
actions sit below it, each with a confirmation: **End idle web sessions** signs out
the browsers and Home Assistant sessions that have not been used for 2
minutes (yours stays), and **Restart device**. Neither runs during a boiler
test, a boiler settings write or a firmware update.

The same data is available to scripts with a signed-in session:
`GET /status/diagnostics` (all sections) or
`GET /status/diagnostics?section=memory,mqtt` (sections: `memory`, `tasks`,
`nvs`, `mqtt`, `sessions`, `restarts`, `log`), and `GET /status/logs?tail=50`.

### Keeping logs after a restart: syslog

The E32 can also send its log to a syslog server on your network (RFC 5424
over UDP). It is off by default. Under **Logging settings** on the
**Diagnostics and system log** page, tick *Enable syslog*, enter the
server's **Syslog server IPv4 address** and **UDP port**
(usually 514), and choose the level. Messages that might hold a password,
key or other private content are left out. The E32 sends at most ten
messages a second and never waits for the server, so a slow or missing server
cannot hold it up; dropped messages are counted on the page.

To receive the log next to Home Assistant, run a syslog server on any machine
on your network: for example a syslog server app (add-on) in Home Assistant
OS, rsyslog or syslog-ng on a Linux machine or NAS, or the log centre of your
NAS. Give it a fixed IPv4 address and enter that address on the E32. Syslog
over UDP is not encrypted and not acknowledged; keep it on your home network.

## The attended switch-over

The firmware can control the boiler, but it never starts on its own: it sends
nothing to the boiler until you confirm the takeover. Switch over only with
someone present at the boiler.

**Which route the Rooms page offers.** A new E32 without a stored room plan
listens to the boiler bus for two minutes. When another thermostat still asks
the boiler for heat, it starts with the trial run ("Your boiler still gets
requests from another thermostat, so the E32 first runs alongside it"); when
none is heard, it starts in active control with the boiler test ("No other
thermostat was found on the boiler bus, so you can go straight to the boiler
test"). Until it knows, it says "Checking the boiler bus…" and stays in the
trial run. Choose the other route at any time with **Trial run first (compare
with your thermostat)** or **Go straight to the boiler test**. A stored plan
keeps its mode.

**Boiler test and takeover (recommended).** Rooms → **Boiler test and
takeover**: no other thermostat on the boiler (an old one disconnected),
confirm the takeover, start heating, hot water while heating, stop heating,
done. It is the only boiler test (the attended heating test of the Boiler page
is retired since rc.3), and no existing thermostat is required: the page
speaks of an old thermostat only when the E32 has heard one. The E32 checks every step
from the boiler's reports and shows each as passed, waiting or failed in plain
words; the details and pass criteria are in
[INSTALL.md section 12](INSTALL.md#12-what-the-trial-run-does-and-does-not-do).
Its temporary room target has an end time and never changes the week
program. When a safety rule stops it, the page says "Stop and give control
back to your thermostat" (without a thermostat the E32 ever heard: "Stop E32
control") with the steps. The E32 remembers the result over restarts and
updates ("Last test: passed on 1 Nov 2026, 21:12."). **I have already done
this test** keeps your own mark with its date, shown as a mark and never as a
passed test; **Undo my mark** takes it back. An E32 that has controlled this
boiler before shows the test as not needed, folded away, with **Run the test
anyway**. The Boiler page shows the same in one line with a link ("Boiler
test: passed on … · Open"), and Home Assistant on the sensor *Ready for E32
control* (`boiler_test_summary` and the other `boiler_test` attributes).

**By hand**, following [the switch-over procedure](SWITCHOVER.md), it involves:

1. Physically disconnecting the existing thermostat from the boiler bus. Two
   controllers must never send boiler requests at the same time.
2. Confirming on the Rooms page: "My thermostat is disconnected from the
   boiler — let the E32 take over". The E32 then waits for fresh room readings
   and the boiler bus before it takes over.
3. Tests with someone at the boiler: start, stop and modulation; hot water
   while heating; an E32 restart; loss of Wi-Fi, Home Assistant and room
   measurements; and the boiler adapter's behaviour when the E32 stops sending.
4. Handing back with **Give control back to my thermostat** (without a thermostat the
   E32 ever heard: **Stop E32 control**): the E32 asks the boiler for zero for one
   minute, then you reconnect the thermostat if there is one.

Safeguards in active mode: the E32 stops and warns when another controller
still sends boiler requests; without room measurements it asks for no heat
until a reading returns; frost protection switches on below 8 °C; the flow
request never exceeds the plan maximum (at most 80 °C) or the boiler's own
maximum heating temperature setting. While the E32 controls the boiler, the
installer check on the Boiler page (readings, zero-only check) is refused; the
boiler test does not start while that check or a boiler settings change uses
the connection to the boiler.

After the switch-over follow one to two weeks of active mode with daily
checks; the **Daily summary** in Home Assistant gives the figures for each
day.

## Tidy entity IDs (optional)

Home Assistant gives every entity an ID, and some of OpenThermostat's are
long. **Configure → Advanced and diagnostics → Tidy entity IDs** proposes the
IDs Home Assistant itself would give these entities today, lists how many
are used in your automations, scripts or dashboards, and renames them only
after you tick **I have read the list and want to rename these entities**.
Under **Which entities**, *Only entities that are not used anywhere* is the
safe choice. History and statistics move along, and the OpenThermostat
dashboard follows by itself, but an automation, script or dashboard of your
own that uses an old ID stops working until you change it; templates in YAML
and other integrations are not searched. Entities you renamed yourself are
skipped. **Undo the entity ID tidy** puts the old IDs back (where still free)
for 30 days.
