# OpenThermostat user guide

For E32 V2 beta.18, optionally with Home Assistant integration 0.4.0b10. If
you use Home Assistant, install both together. Installing on a new E32, the
Home Assistant setup, updates and troubleshooting are described step by step
in the [installation guide](INSTALL.md).

In this beta the E32 runs in **shadow mode**: it calculates what it would ask
of the boiler and, if a thermostat is connected to the boiler, compares that
with it. Your existing thermostat keeps controlling the boiler. Nothing in
this guide makes the E32 control the boiler.

**Supported boilers:** EMS Classic (EMS 1.0), directly on the bus or through an
adapter such as the Bosch EasyControl Adapter. EMS+ (EMS 2.0) is planned.

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
| Week program per room | E32: Rooms | Same room editor |
| Lowest and highest flow temperature for the boiler request | E32: Rooms → Boiler flow limits | Configure → Rooms → Flow temperature limits |
| Gas meter, gas price, outdoor temperature, boiler power (all optional) | — | Configure → Energy and outdoor temperature |
| Pairing Bluetooth sensors (address, profile, encryption key) | E32: Sensors | E32: Sensors |
| Boiler model | E32: Boiler | E32: Boiler |
| Network, MQTT broker, time and time zone | E32: System → Network | E32: System → Network |
| Firmware updates | E32: System → Firmware update | The firmware update entity, or the E32 page |
| Backup and restore of the settings | E32: System → Network → Backup and restore | E32: System → Network → Backup and restore |
| Restart | E32: System → Restart device | E32: System → Restart device |

The room plan is stored on the E32, and the E32 runs it. With Home Assistant,
the HA room editor is the main place to edit it; it reads the plan from the
E32 and writes it back. Bluetooth sensors stay paired on the E32, so they keep
working without Home Assistant; the E32 shares them with Home Assistant,
where each sensor appears as its own device and can be chosen as a room
source.

## First start (no Home Assistant needed)

A new E32 first needs the OpenThermostat firmware over USB; see
[installing the firmware](INSTALL.md#2-install-the-firmware-on-a-new-e32-usb).

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
   password (8–64 characters) under **System → About**; until you do, the
   Overview reminds you. Home Assistant asks for this password when you
   connect it. A forgotten password can be reset to `admin` with the
   `password-reset` command over USB.

### 2. Set the time zone

Week programs, "today" and the daily comparison use the E32's own clock. Go
to **System → Network**, section **Time**, check the time server and choose
your time zone from the list. When the page suggests the time zone of your
browser, **Use this time zone** fills it in. For a time zone that is not in
the list, choose "Other" and enter its POSIX text under Advanced, for example
`EST5EDT,M3.2.0,M11.1.0` (US Eastern); any time zone and summer-time rule
works. Choose **Save settings** and let the E32 restart. Without a valid clock
the week program is not used and the room keeps its temperature without Home
Assistant.

### 3. Choose your boiler

A newly installed E32 does not listen to the boiler yet. Under **System →
Network → Advanced settings → Hardware services**, tick **EMS bus enabled**,
save and let the E32 restart. This only lets the E32 receive boiler data; it
does not send heat requests. Connect the E32 to the boiler's EMS bus as
described in the [installation guide](INSTALL.md#5-connect-the-e32-to-the-boiler)
(switch the boiler off first).

Then, under **Boiler**, choose your boiler brand and model and check that
boiler values arrive (temperatures, status). Only EMS Classic boilers are
supported in this beta.

### 4. Pair a Bluetooth thermometer

This example uses a thermometer with pvvx firmware; Shelly BLU H&T and Xiaomi
Monitor 3 work as well.

1. In the pvvx configuration page, set the advertising format to **BTHome
   v2**. Unencrypted is simplest; if you enable encryption, note the
   32-character bindkey. The older PVVX Custom format also works.
2. Place the sensor in the room, away from radiators, windows and direct sun,
   within Bluetooth range of the E32.
3. On the E32, open **Sensors** and choose **Search nearby**. The list shows up
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

1. Choose **Add room** and give it a name, for example Living room.
2. Set the state to active and the heating type (radiators or floor heating).
3. Under **Temperature sources**, choose the Bluetooth sensor. Up to four
   sources in order: the first fresh one leads, the others are fallback.
4. Set the **temperature without Home Assistant** (for example 19 °C) and the
   room's minimum and maximum.
5. Turn on **Use a week program** and add switch points per day (time and
   temperature, up to six per day). Each temperature holds until the next
   switch point.
6. Check **Boiler flow limits** (default 30–60 °C; the maximum can be set up
   to 80 °C). Floor heating fed directly without a mixing valve usually needs
   at most 45–50 °C. The page
   shows your boiler's own maximum heating temperature; the E32 never asks for
   more than that.
7. Choose **Save rooms**.

The E32 stores large week programs in a compact form, so 8 rooms with four
switch points a day fit. A plan that is still too large is refused with a
message, and nothing changes.

### 6. Check it

On the **Rooms** page the room shows its temperature, its target and where the
target comes from (for example "Target temperature from the week program"),
and the calculated boiler request. The status reads "Measured". The
**Overview** shows the same rooms at a glance.

## Adding Home Assistant

The [installation guide](INSTALL.md#8-home-assistant-optional) describes
each step in detail. In short:

You need Home Assistant 2026.10.0 or newer (tested with 2026.10.2 to
2026.10.4).

1. Set up Home Assistant's MQTT integration with a local MQTT broker, and
   enter the same broker under E32 **System → Network → MQTT**: tick
   **Enabled** and enter a broker user name and password. The E32 does not
   connect to Home Assistant through a broker without a login.
2. Install the OpenThermostat integration package, restart Home Assistant and
   add OpenThermostat under Settings → Devices & services. You do not need to
   add a room in Home Assistant first.
3. Choose **Configure → Connect E32** and enter the E32 address and password.
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
[the installation guide](INSTALL.md#9-updates).

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
   - **Target temperature from Home Assistant:** optional. Choose your
     thermostat to make the E32 follow its target. Leave it empty to follow the
     week program.
   - **Temperature without Home Assistant:** for example 19 °C.
   - **Week program on the E32:** one line per group of days, for example

     ```text
     mon-fri: 06:30 20.5, 22:30 18
     sat-sun: 08:00 20.5, 23:00 18
     ```

     A line without days applies to every day. Up to six switch points per day.
   - **Temperature limits:** the lowest and highest target this room may get.
3. Save. Home Assistant forwards the selected entities to the E32 on every
   change and every five minutes.

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
room's **target**: the flow limits, the boiler's own limit and frost
protection stay as they are. In shadow mode they are computed and shown, like
everything else.

- **Change temporarily** (E32 overview page, on each active room card, or the
  room's thermostat in Home Assistant): **Boost** heats to the room's maximum
  for an hour; a temperature can hold for 1, 2 or 4 hours or **until the next
  switch point** of the room's week program. The E32 ends it itself and the
  room returns to its week program, also after a restart. After a restart the
  E32 waits for a valid clock before it applies a stored change; until then
  the room follows its plan. A change made while the E32 has no valid clock
  lasts its duration and is not kept across a restart.
- **Window and door sensors** (Home Assistant: Configure → **Comfort** →
  Window and door sensors per room): while any sensor of a room is open for
  longer than the delay (120 s by default), the room pauses and only heats
  below 8 °C. When all are closed it resumes at once. The room card and the
  thermostat show the pause and its reason.
- **Away** (E32 overview page, or the action *Away* / the thermostat's *Away*
  preset in Home Assistant): every room is at most the away temperature,
  optionally until a date and time. With a date, the E32 starts warming up
  early enough to be at the week program's temperature when you are back
  (from what it learned, else 45 minutes per °C for radiators and 2 hours per
  °C for floor heating). Optionally, *Who is home* (a person, group, zone or
  switch) makes the house away while everyone is out.

In Home Assistant each E32 room has a thermostat: current temperature,
target, mode *Auto* (week program), *Heat* (a temporary change) or *Off* (the
room is inactive in the plan), and the presets Comfort, Night (Home
Assistant's "Eco"), Away and Boost. Comfort and Night are the warmest and the
coolest temperature of the room's week program, the same levels as in the week
planner. A new target on the thermostat lasts until the next switch point; a room
without a week program keeps it for the time set under Configure → Comfort,
and a room with only a fixed target changes that fixed target in the plan.

Bluetooth window sensors (for example Shelly BLU Door/Window) paired on the
E32 itself are not supported yet; connect them through Home Assistant.

### Energy inputs and heating advice

Under Configure → **Energy and outdoor temperature** you can choose a gas
meter (m³ or kWh), a gas price sensor or a fixed price, the calorific value of
your gas, an outdoor temperature sensor or weather entity, and your boiler's
heating power. All fields are optional; leave a field empty to not use it.
With a gas meter the E32 calibrates its heat and gas estimates.

The **Heating advice** sensor and its dashboard section list what could be
tuned: short cycling, a maximum heating temperature far above what the house
needs, a return too warm for condensing, the flow your rooms really need,
night setback, hot-water temperature and water pressure. Each item says what
was seen, why it matters, what to change and where, with its confidence. It
is advice only and never changes a setting; a rule without enough data says
what is missing.

The **Heating problem** sensor answers "is my heating OK?". It turns on only
for real problems that last: a room without a usable measurement for 30
minutes, no report from the E32 for 10 minutes, low or high water pressure,
or burner short cycling for 2 hours. Its `reasons` attribute says what is
wrong, so you can use it in your own notification automation.

## Reading the shadow comparison

If a thermostat controls your boiler over the EMS bus, the comparison puts the
E32's decision next to what that thermostat actually asked of the boiler. You
find it on the E32 Rooms page under "Comparison with your thermostat (today)".
Home Assistant adds today's figures as sensors (heating time and burner
starts today for the E32 and the thermostat, and their agreement) once it has
seen such a thermostat; a home without one gets no comparison sensors.

| Line | Meaning |
| --- | --- |
| Compared time | How long both sides were observed today. |
| Heating time E32 / thermostat | How long each side asked for heat. |
| Burner starts E32 / thermostat | How often each side would start or started the burner. Fewer starts is gentler on the boiler. |
| Agreement (both on or both off) | Share of the compared time in which both sides made the same choice. |
| E32 flow range / Thermostat flow range | Lowest, highest and mean requested flow temperature. |
| E32 starts within 5 min of a thermostat start | How many of the thermostat's starts the E32 matched closely. |
| Without thermostat data | Time in which the thermostat's request was not seen; excluded from the agreement. |

The table below shows the last seven days. A good shadow period, before a
switch-over is considered, looks like this:

- at least 72 hours without a hang or restart;
- at least 10 compared heating periods, including night setback, morning
  warm-up and a period without heat demand;
- heat demand at about the same moments (a few minutes apart), flow
  temperatures in the same range, and not more burner starts than the
  thermostat;
- the sources work, and a fallback source has taken over at least once.

Shadow mode does not show how the boiler and its adapter react to the E32's
request; that is tested during the switch-over.

### Learning results

Each room device in Home Assistant also has three learning sensors. They are
advice only in this beta and are not applied to the boiler request.

| Sensor | Meaning |
| --- | --- |
| Learning status | Collecting data, Learning or Ready. Learning uses stable heating periods without hot water and with fresh readings, so it takes several heating periods. |
| Recommended flow (1 °C) | The lowest flow temperature that warms the room by 1 °C in an acceptable time. Unknown until learned. Its attributes show the current rule's flow for comparison. |
| Predicted heating start | When the E32 would start heating to reach the next higher week-program temperature on time. Its attributes compare night strategies (holding a night temperature versus letting it drop) in kWh, m³ and €. |

The predictions need a valid clock; the night-setback estimate also needs an
outdoor temperature (from the boiler or from Home Assistant). The product
device also shows hot water today (taps, keeping warm, burner time) and a
burner short-cycling warning.

## Backup and restore

System → Network → **Backup and restore** saves the settings of the E32 in
one file: network and time (host name, time zone, time server), MQTT and the
Home Assistant link, the room plan with its week programs, the Bluetooth
sensors, the flow options, the boiler model and the page language.

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
  these settings**. If saving one part fails, the E32 puts the earlier
  settings back. When network or Bluetooth settings change, the E32 restarts
  about 10 seconds later; sign in again afterwards.
- **What a restore never does.** It does not change the Wi-Fi network or the
  port of the web page, it switches from Wi-Fi to Ethernet only while an
  Ethernet cable is connected and never from Ethernet to Wi-Fi, and it
  restores the rooms in shadow mode, so it never starts active boiler control. A restore is refused while the E32
  controls the boiler or a boiler test is running.

## The attended switch-over (not in this beta)

Active control is built into beta.18 but locked in the firmware; the Active
control section on the Rooms page says "Active control is not enabled in this
firmware." It is opened only in a later release, with someone present at the
boiler. See [the switch-over procedure](SWITCHOVER.md). It will involve:

1. Physically disconnecting the existing thermostat from the boiler bus. Two
   controllers must never send boiler requests at the same time.
2. Confirming on the Rooms page: "My thermostat is disconnected from the
   boiler — let the E32 take over". The E32 then waits for fresh room readings
   and the boiler bus before it takes over.
3. Tests with someone at the boiler: start, stop and modulation; hot water
   while heating; an E32 restart; loss of Wi-Fi, Home Assistant and room
   measurements; and the boiler adapter's behaviour when the E32 stops sending.
4. Handing back with **Hand back to the thermostat**: the E32 asks the boiler
   for zero for one minute, then you reconnect the thermostat.

Safeguards in active mode: the E32 stops and warns when another controller
still sends boiler requests; without room measurements it asks for no heat
until a reading returns; frost protection switches on below 8 °C; the flow
request never exceeds the plan maximum (at most 80 °C) or the boiler's own
maximum heating temperature setting. While the E32 controls the boiler, the
attended boiler test is refused.

After the switch-over follow one to two weeks of active mode with daily
checks before a first non-beta release.
