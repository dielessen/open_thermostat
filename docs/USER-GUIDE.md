# OpenThermostat user guide

For E32 V2 beta.18 with Home Assistant integration 0.4.0b10. Install both
together; see the [project page](../README.md#installation) for updating.

In this beta the E32 runs in **shadow mode**: it calculates what it would ask
of the boiler and compares that with your thermostat, but your thermostat
keeps controlling the boiler. Nothing in this guide makes the E32 control the
boiler.

**Supported boilers:** EMS Classic (EMS 1.0), directly on the bus or through an
adapter such as the Bosch EasyControl Adapter. EMS+ (EMS 2.0) is planned.

## Where do I set what?

| What | Where |
| --- | --- |
| Rooms: add, rename, remove, active or off | **Home Assistant**: Settings → Devices & services → OpenThermostat → Configure → Rooms |
| Temperature sources per room (HA thermostats and sensors, E32 Bluetooth sensors) and their order | Home Assistant, same room editor |
| Target temperature, temperature without Home Assistant, minimum and maximum | Home Assistant, same room editor |
| Week program per room | Home Assistant, same room editor |
| Pairing Bluetooth sensors (address, profile, encryption key) | **E32**: Sensors |
| Boiler model | E32: Boiler |
| Lowest and highest flow temperature for the boiler request | E32: Rooms → Boiler flow limits (after "Edit here anyway") |
| Network, MQTT broker, time | E32: System → Network |
| Firmware updates | Home Assistant firmware update entity, or E32: System → Firmware update |
| Restart | E32: System → Restart device |

The room plan itself is stored on the E32, and the E32 runs it. Home
Assistant is the place where you edit it; it reads the plan from the E32 and
writes it back. Bluetooth sensors stay paired on the E32, so they keep working
without Home Assistant; the E32 shares them with Home Assistant, where each
sensor appears as its own device and can be chosen as a room source.

### The E32 Rooms page is read-only

The E32 Rooms page shows the rooms, their temperatures, where each target
comes from, the calculated boiler request and the comparison with your
thermostat. Because the rooms are managed in Home Assistant, the page is
read-only and says "Managed in Home Assistant".

**Edit here anyway** unlocks editing on the E32 for the current browser
session. Use it when Home Assistant is not available. After about ten minutes
without contact the page says "Home Assistant is not reachable — you can
change rooms here." Every saved change goes to the same plan, and Home
Assistant shows it too. The plan carries a revision number: if Home Assistant
changed it in the meantime, the E32 refuses your save, reloads the plan and
asks you to make your change again. Nothing is overwritten silently.

### What happens when Home Assistant is offline

- Room temperatures from Home Assistant entities stop arriving. The next fresh
  source in the room's list takes over, for example a Bluetooth sensor the E32
  receives itself. The room card shows which source leads.
- Without a target from Home Assistant, the room follows its **week program**
  on the E32. Without a week program (or without a valid clock) it keeps its
  **temperature without Home Assistant**.
- If no source of a room delivers a usable reading, the room keeps its last
  value for 30 minutes and then stops asking for heat.
- You can still change rooms on the E32 Rooms page with "Edit here anyway".

Bluetooth readings stay valid for 15 minutes. A sensor that only sends every
few minutes is therefore not a problem; one that has been silent for longer
no longer counts.

## First room: thermostat via Home Assistant plus a Bluetooth fallback

This example sets up the living room with your existing thermostat (for
example tado) as the main source and a Bluetooth thermometer with pvvx
firmware as fallback.

**Before you start:** E32 beta.18 and HA 0.4.0b10 are installed, the
OpenThermostat integration is connected to the E32, and your thermostat
appears in Home Assistant as a climate entity.

### 1. Prepare the pvvx thermometer

1. Flash the sensor with the pvvx firmware if you have not done so yet.
2. In the pvvx configuration page, set the advertising format to **BTHome
   v2**. Unencrypted is simplest; if you enable encryption, note the
   32-character bindkey. The older PVVX Custom format also works.
3. Place the sensor in the room, away from radiators, windows and direct sun,
   within Bluetooth range of the E32.

### 2. Pair it on the E32

1. Open the E32 web interface and go to **Sensors**.
2. Choose **Search nearby**. The list shows up to 32 of the strongest nearby
   devices.
3. Click your sensor. Its name and address are filled in; give it a clear
   name such as "Living room thermometer".
4. Choose the profile **Thermometer with pvvx firmware (BTHome)**. Enter the
   bindkey only if you enabled encryption. Keys are stored on the E32 and never
   shown again.
5. Choose **Save Bluetooth settings**, then **System → Restart device**.
   Bluetooth changes apply after a restart.
6. After the restart the sensor shows a temperature. "Waiting" means nothing
   has been received yet: check distance, battery and address. "Restart
   required" means a saved change still waits for a restart.

Up to eight Bluetooth sensors can be paired.

### 3. Create the room in Home Assistant

1. Go to Settings → Devices & services → OpenThermostat → **Configure** →
   **Rooms** → **Add a room**.
2. Fill in the form:
   - **Room name:** Living room.
   - **Room state:** Active.
   - **Heating in this room:** radiators or floor heating.
   - **Temperature sources from Home Assistant:** your thermostat's climate
     entity. Only sources in °C are accepted.
   - **Bluetooth sensors on the E32:** the pvvx thermometer.
   - **Use the Bluetooth sensors first:** off, so the thermostat leads and the
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

     A line without days applies to every day. Up to six switch points per day;
     each temperature holds until the next point.
   - **Temperature limits:** the lowest and highest target this room may get.
3. Save. The plan is stored on the E32. Home Assistant forwards the selected
   HA entities to the E32 on every change and every five minutes.

The whole room plan must fit in 4 KB. Many rooms with full week programs may
not fit; the E32 then refuses the save with a message.

### 4. Check it

1. On the E32 **Rooms** page, the living room shows its temperature, the target
   and where the target comes from (for example "Target temperature from Home
   Assistant"). The status reads "Measured".
2. In Home Assistant, the room appears as its own device with temperature,
   target temperature, control status, heat demand and mode.
3. Test the fallback: temporarily disable your thermostat's integration in
   Home Assistant. After its value expires, the room status changes to
   "Fallback source" and the Bluetooth sensor leads. Enable the integration
   again afterwards.

## Reading the shadow comparison

The comparison puts the E32's decision next to what your thermostat actually
asked of the boiler. You find it on the E32 Rooms page under "Comparison with
your thermostat (today)" and, for today, as Home Assistant sensors (heating
time today and burner starts today for the E32 and the thermostat, and their
agreement).

| Line | Meaning |
| --- | --- |
| Compared time | How long both sides were observed today. |
| Heating time E32 / thermostat | How long each side asked for heat. |
| Burner starts E32 / thermostat | How often each side would start or started the burner. Fewer starts is gentler on the boiler. |
| Agreement (both on or both off) | Share of the compared time in which both sides made the same choice. |
| E32 flow range / Thermostat flow range | Lowest, highest and mean requested flow temperature. |
| E32 starts within 5 min of a thermostat start | How many of the thermostat's starts the E32 matched closely. |
| Without thermostat data | Time in which the thermostat's request was not seen; excluded from the agreement. |

The table below shows the last seven days. A good shadow period, before the
switch-over is considered, looks like this:

- at least 72 hours without a hang or restart;
- at least 10 compared heating periods, including night setback, morning
  warm-up and a period without heat demand;
- heat demand at about the same moments (a few minutes apart), flow
  temperatures in the same range, and not more burner starts than the
  thermostat;
- the sources work: the thermostat's value arrives through Home Assistant and
  the Bluetooth fallback has taken over at least once.

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
outdoor temperature. Gas-meter calibration of these estimates is planned.

## The attended switch-over (not in this beta)

Active control is built into beta.18 but locked in the firmware; the Active
control section on the Rooms page says "Active control is not enabled in this
firmware." It is opened only in a later release, with the owner present. That
switch-over will involve:

1. Physically disconnecting the thermostat from the boiler bus. Two
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
request never exceeds the plan limit, 60 °C or the boiler's own limit. While
the E32 controls the boiler, the attended boiler test is refused.

After the switch-over follow one to two weeks of active mode with daily
checks before a first non-beta release.
