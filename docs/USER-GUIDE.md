# OpenThermostat user guide

For E32 V2 beta.18, optionally with Home Assistant integration 0.4.0b10. If
you use Home Assistant, install both together; see the
[project page](../README.md#installation) for updating.

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
| Restart | E32: System → Restart device | E32: System → Restart device |

The room plan is stored on the E32, and the E32 runs it. With Home Assistant,
the HA room editor is the main place to edit it; it reads the plan from the
E32 and writes it back. Bluetooth sensors stay paired on the E32, so they keep
working without Home Assistant; the E32 shares them with Home Assistant,
where each sensor appears as its own device and can be chosen as a room
source.

## First start (no Home Assistant needed)

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
to **System → Network**, check the time server and set your time zone. The
field takes a POSIX time zone, for example `CET-1CEST,M3.5.0,M10.5.0/3`
(Central Europe), `GMT0BST,M3.5.0/1,M10.5.0` (UK) or
`EST5EDT,M3.2.0,M11.1.0` (US Eastern). Any time zone and summer-time rule
works. Without a valid clock the week program is not used and the room keeps
its temperature without Home Assistant.

### 3. Choose your boiler

Under **Boiler**, choose your boiler brand and model and check that boiler
values arrive (temperatures, status). Only EMS Classic boilers are supported
in this beta.

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

The whole room plan must fit in 4 KB. Many rooms with full week programs may
not fit; the E32 then refuses the save with a message.

### 6. Check it

On the **Rooms** page the room shows its temperature, its target and where the
target comes from (for example "Target temperature from the week program"),
and the calculated boiler request. The status reads "Measured". The
**Overview** shows the same rooms at a glance.

## Adding Home Assistant

1. Set up Home Assistant's MQTT integration with a local MQTT broker, and
   enter the same broker under E32 **System → Network**.
2. Install the OpenThermostat integration, then add it under Settings →
   Devices & services. The E32 address may be an IP address or a local name
   such as `openthermostat-a1b2c3.local`, `e32.fritz.box` or `e32.home.arpa`.
3. From then on, rooms are managed in Home Assistant. Your existing E32 rooms
   appear there unchanged.

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
