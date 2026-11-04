# Field tester pack: OpenThermostat 1.0 rc.4

Thank you for testing. You are the first person other than the developer to
install OpenThermostat, and the first on a **Nefit TopLine**. This page tells
you what to prepare, in which order to install, what the E32 does by itself,
how to get your old thermostat back, and what we would like to learn from your
home.

It is a companion to the [installation guide](INSTALL.md), not a replacement.
Follow the guide and tick off each step in the
[installation checklist](INSTALL-CHECK.md). Every question you have to ask
us is a gap in the guide: please write it down. When you get through the guide
on your own, that meets the 1.0 criterion "an install guide someone else has
followed".

Versions: E32 firmware **1.0.0-rc.4** with Home Assistant integration
**1.0.0rc5**, or a newer pair that the release notes name together.

Already testing rc.3? Do not start over: update with the three steps in
[INSTALL.md section 13.1](INSTALL.md#131-update-order) (integration 1.0.0rc5
first, then the E32's **Firmware** entity, then confirm the takeover again)
and read [What to look at in rc.4](#what-to-look-at-in-rc4).

## 1. Before you start

### What you need

- A **BBQKees E32 V2** gateway.
- A **USB-C cable that carries data** (not a charge-only cable) and a computer
  with Chrome or Edge, for the first firmware install. Later updates go over
  the network.
- **Home Assistant 2026.10.0 or newer**.
- An **MQTT broker**, for example the Mosquitto broker add-on, and Home
  Assistant's MQTT integration.
- **HACS**, to install the integration (or the release ZIP; see step 4 of the
  [install order](#2-install-order)).
- **Zigbee2MQTT** on the same broker, only if your radiator valves are on
  Zigbee2MQTT. Valves on ZHA or another integration work through Home
  Assistant without it.
- Your **room temperature sensors** already in Home Assistant, or Bluetooth
  thermometers the E32 can receive itself.

### Make a Home Assistant backup

**Settings → System → Backups → Back up now.** Keep a copy off the Home
Assistant machine. If anything goes wrong in Home Assistant, you can restore
it.

### Photograph and label the boiler wiring

Before you touch the boiler:

1. Switch the boiler off.
2. Take a clear photo of the wiring of your thermostat at the boiler (or at
   its adapter).
3. Put a label on each of the thermostat's two wires, and later on the E32's
   wires too.
4. Keep the photo on your phone. You need it to reconnect the thermostat (see
   the [card in section 4](#4-the-back-to-your-thermostat-card)).

## 2. Install order

Do the steps in this order. Each link goes to the matching part of the
installation guide; tick the row in [INSTALL-CHECK.md](INSTALL-CHECK.md) when
it is done.

1. **Firmware over USB:**
   [INSTALL.md section 2](INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb).
   This erases what is on the E32. Check the MD5 before the first restart.
2. **Network:** Wi-Fi in
   [section 3](INSTALL.md#3-first-start-connect-the-e32-to-your-wi-fi),
   then your own E32 password in
   [section 4](INSTALL.md#4-sign-in-and-change-the-admin-password),
   the time zone and **Boiler bus (EMS) on** in
   [section 5](INSTALL.md#5-basic-settings-time-zone-and-boiler-reception),
   and MQTT in
   [section 8](INSTALL.md#8-mqtt-let-the-e32-talk-to-home-assistant).
3. **Connect the E32 to the boiler:**
   [section 6](INSTALL.md#6-connect-the-e32-to-the-boiler). Leave your
   thermostat connected. Under **Boiler → Boiler model**, choose
   **Nefit TopLine** and **Save boiler selection**.
4. **Home Assistant integration through HACS:**
   [section 9.1](INSTALL.md#91-with-hacs-recommended). In short:
   1. In Home Assistant open **HACS**, the three dots at the top right,
      **Custom repositories**.
   2. Repository `https://github.com/dielessen/openthermostat-ha`, type
      **Integration**, **Add**.
   3. Release candidates are pre-releases, which HACS does not offer by
      default. In the HACS list, open the three dots of **OpenThermostat**,
      choose **Download**, open **Need a different version?** and pick
      **1.0.0rc5**.
   4. Restart Home Assistant (**Settings → System → Restart**).

   To be offered the next release candidate as an update, switch on the
   **Pre-release** switch of the OpenThermostat device under
   **Settings → Devices & services → HACS** (enable the entity first). The
   manual ZIP install
   ([section 9.2](INSTALL.md#92-without-hacs-the-release-zip)) also works.
5. **Add the integration and connect the E32:**
   [section 10](INSTALL.md#10-add-the-integration-and-connect-the-e32).
   **Settings → Devices & services → Add integration → OpenThermostat**, then
   **Configure → E32 connection**. Wait for **E32 connected**. Configure has
   six items (Rooms, House, Heating and boiler, Energy and outdoor
   temperature, E32 connection, Advanced and diagnostics); every submenu has
   **← Back** and **Done** closes it.
6. **Rooms and sensors:** [section 11](INSTALL.md#11-add-your-rooms).
   **Configure → Rooms → Add a room**. For each room choose its temperature
   sensor under **Temperature sources from Home Assistant**. A second source
   per room is worth it: it keeps the room measured when the first drops out,
   and the readiness check wants one to step in at least once. The valve's
   own thermostat entity can be that second source, but it measures close to
   the radiator, so keep it second.
7. **Radiator valves** ([user guide: Radiator valves](USER-GUIDE.md#radiator-valves)):
   in the room form (**Configure → Rooms → Edit or remove a room → Edit
   room**), section **Radiator valves**, pick the valves' climate entities.
   Each valve then shows its route:
   - *works without Home Assistant*: a Zigbee2MQTT valve the E32 knows; the
     E32 drives it itself, so its broker login must be allowed to read
     `zigbee2mqtt/#` and write `zigbee2mqtt/+/set` (see the ACL in
     [section 15](INSTALL.md#15-secure-your-setup)).
   - *through Home Assistant*: ZHA, Z-Wave, any other integration, or a
     Zigbee2MQTT valve whose model is not recognised (choose it under
     **Choose the models myself (advanced)**).

   Each room has a **Valve control** switch, off by default. Valves are
   driven only while that switch is on **and** the E32 controls the boiler.
   So during a trial run nothing is sent to the valves, even when you set
   them up. Give each valve one job: either the room's **setting device**
   ([section 11.3](INSTALL.md#113-the-setting-device)) or a radiator valve
   the E32 drives. We have not tested one valve in both roles.

## 3. What the E32 does on its own

While the E32 has no rooms yet, it listens to the boiler bus for about two
minutes and picks a route:

- **Your thermostat still asks the boiler for heat over the bus:** the E32
  starts a **trial run** beside it. It measures the rooms, follows the week
  programs and works out what it *would* ask of the boiler, but sends nothing.
  The Rooms page shows the check **Ready for the E32 to control the boiler?**
  (in Home Assistant: the sensor **Ready for E32 control**), which turns
  green line by line over a few days.
- **No thermostat is heard** (none, or one wired to the boiler's on/off
  contacts instead of the bus): the Rooms page goes straight to the guided
  **Boiler test and takeover**.
- **"Checking the boiler bus…"**: it is still listening; wait.

You can always choose the other route on the Rooms page: **Trial run first
(compare with your thermostat)** or **Go straight to the boiler test**.

**The takeover is always your own decision.** The E32 sends nothing to the
boiler until you confirm it, in step 2 of the boiler test. Do the boiler test
with someone at the boiler; it takes about 30 minutes and checks each step for
you ([section 12](INSTALL.md#12-what-the-trial-run-does-and-does-not-do)).
Disconnect your old thermostat before step 1, also when the E32 could not
hear it: step 1 then says **No other thermostat on the boiler** (it names your
old thermostat only once the E32 has heard it on the bus). The E32 remembers
the test's result, so after a restart or an update the Rooms page still says
"Last test: passed on …".

One thing does act on your home before the takeover: a **setting device**.
If you chose a valve or thermostat as a room's setting device, Home Assistant
sets it to the week program's temperature, also during the trial run.

## 4. The "back to your thermostat" card

Print this section and keep it at the boiler. It comes from the
[switch-over procedure](SWITCHOVER.md#hand-back-to-the-old-thermostat).

> **Give control back to your thermostat (normal)**
>
> 1. Open the E32 page, menu **Rooms**, section **Active control**.
> 2. Press **Give control back to my thermostat (the E32 first asks the
>    boiler for no heat for a minute)**. Home Assistant has no button for
>    this; use the E32 page.
> 3. Wait about 70 seconds for **Trial run: your thermostat controls the
>    boiler.** If it keeps saying "Stopping", use the emergency steps.
> 4. Switch the boiler off, reconnect the thermostat's two labelled wires as
>    in the photo, and switch the boiler on.
> 5. Within 2 minutes the thermostat asks for heat again. Check that hot water
>    works.
>
> **Emergency (the page does not open, the E32 misbehaves, or the boiler
> keeps heating)**
>
> 1. Switch the boiler off with its main switch or heating switch. Heating
>    stops at once.
> 2. Unplug the E32's power (or disconnect its two labelled bus wires).
> 3. Reconnect the thermostat's wires as in the photo, switch the boiler on,
>    and check hot water, water pressure and the boiler display.
> 4. Leave the E32 off and tell us what happened. When it comes back with the
>    thermostat connected, it hears the thermostat and stays silent. Then
>    press **Give control back to my thermostat** anyway.
>
> If the boiler test stops by itself, the page says **Stop and give control
> back to your thermostat:** with the same steps.

## 5. What we want to learn from a TopLine

Your TopLine is the first of its kind on OpenThermostat. These are the things
only your home can tell us:

- **Boiler messages.** On the E32 **Boiler** page: the values under **Now**,
  the lists in **What your boiler reports** (*Values available*, *Not fitted
  on this boiler*, *Not reported (yet)*), and whether **All boiler data** or
  **Unidentified EMS traffic** shows anything odd. The console command
  `boiler-profile` under **System → Diagnostics and system log** gives the
  same in text. If the Boiler page stays empty with **Boiler bus (EMS) on**,
  tell us at once: your boiler may speak only EMS+, which comes in 1.1.
- **Display codes.** Does the **Display code** in words on the E32 match what
  the boiler's own display shows, including during hot water and any fault?
  A photo of the boiler display next to a screenshot is ideal.
- **Control.** The boiler test steps: did each pass, how long did it take, and
  what did the boiler do? Especially step 3 (start heating), step 4 (hot water
  while heating) and step 5 (stop heating). The result is kept on the Rooms
  page and in Home Assistant on the sensor **Ready for E32 control**.
- **Valves per room.** Model, Zigbee2MQTT or ZHA, and after the takeover with
  **Valve control** on: does the valve follow the room, does it report its
  position and battery, and does it ever go silent?
- **Sensors.** Which sensors you use, and whether a room on the E32 Rooms page
  ever shows "Backup sensor in use", "Sensor silent: last reading used" or
  "No reading: this room does not ask for heat".
- **Learning after one to two weeks.** In Home Assistant the sensor **What the
  thermostat learned** and the **Learning and settings** tab of the dashboard, or on the E32
  **Home → What the thermostat has learned**: how far each room is, and
  whether the figures make sense for your home. Self-tuning only changes
  settings on days the E32 controlled the boiler.

### What to look at in rc.4

- **The morning line.** Smart warm-up now starts early from the first morning,
  as an estimate ("starts at 07:40 (estimate; it learns from every morning)").
  Every morning the E32 checks whether the room was warm at the program time
  and says so: "Yesterday warm at 09:12 (12 min late); tomorrow 10 % earlier."
  You find it in Home Assistant on the **Learning and settings** tab (and in
  the thermostat's `smart_warm_up` attribute), and on the E32 under **Home →
  What the thermostat has learned**. Follow it for a week: does the start move
  the right way, and is the room warm at the program time after a few
  mornings? Floor heating and radiators are worth telling apart.
- **Yesterday.** Heating hours, burner starts per heating hour, short burner
  runs, gas for heating (an estimate), degree-days and, per room, "warm 12 min
  late · 0.3 °C too warm". It is on the same tab and on the same E32 card. Do
  the figures match what you saw? Is a room often too warm?
- **The holiday planner.** Plan a holiday that starts in the future, with its
  own **Temperature on holiday**: in Home Assistant under **Configure → House →
  House mode and holiday**, on the E32 on the **Home** page in the block
  **Holidays**. Does it start and end by itself, is the house warm again when
  you are back, and is the house mode afterwards what it was? Is the same
  holiday listed in both places? A holiday needs the E32's clock.
- **Why a room heats.** The line on each room's card, on the E32 **Overview**
  and in Home Assistant. Does it say what the room really does?

## 6. How to share data (only if you want to)

Sharing is always your choice. Send files privately, or attach them to a
GitHub issue only after you have looked through them.

- **Home Assistant diagnostics.** **Settings → Devices & services →
  OpenThermostat**, the three dots (⋮) of the entry, **Download diagnostics**.
  The file leaves out passwords, keys, addresses and Wi-Fi names.
- **E32 backup without secrets.** **System → Backup and restore**. Leave
  **Include passwords and Bluetooth keys, encrypted with a passphrase** off
  and choose **Download backup**. Without that tick the file holds no
  passwords or keys. It does hold your room names and settings.
- **E32 log.** **System → Diagnostics and system log → Download log**. Look
  through it before you share it.
- **A read-only MQTT login for a helper (optional).** With it, a helper can
  watch the live values on your broker but change nothing. Create a broker
  login that is only a broker login, for example under the Mosquitto add-on's
  **Configuration → Logins** (a Home Assistant user would also be able to sign
  in to Home Assistant). Then add it to the `accesscontrollist` from
  [Secure your setup](INSTALL.md#15-secure-your-setup):

  ```text
  # A helper: reads OpenThermostat and the valves, writes nothing.
  user helper
  topic read openthermostat/#
  topic read zigbee2mqtt/#
  ```

  Restart the add-on. Give the helper access only through a VPN or remote
  access you control; never open the broker's port to the internet. Remove
  the login when the help is done.
- **A Home Assistant token for an assistant (optional).** In Home Assistant,
  your profile (your name at the bottom left) → **Security** → **Long-lived
  access tokens** → **Create token**. A token can do everything the user that
  made it can do, including changing your heating. Make it from a separate
  user that is not an administrator, share it privately, and delete it when
  the help is done.

**Never share the E32 web password.** It allows changes to your heating. A
read-only E32 key for helpers is planned for a later release.

**Never post tokens or passwords publicly**, not in a GitHub issue, a forum
or a screenshot. If one leaks, delete the token or change the password at
once.

## 7. What to report, and where

Open an issue at
[github.com/dielessen/open_thermostat/issues](https://github.com/dielessen/open_thermostat/issues),
one issue per problem, with a title that starts with "Field test:". Include:

- **Versions:** the E32 firmware (**System → Firmware update**, *Installed:*),
  the integration (HACS, or **Settings → Devices & services →
  OpenThermostat**) and Home Assistant.
- **Your setup:** Nefit TopLine type, your old thermostat (model, and whether
  it is on the bus or on the on/off contacts), the valve models and
  Zigbee2MQTT or ZHA, the sensors.
- **What you did, what you expected and what happened**, with the date and
  time.
- **Screenshots** of the E32 page or Home Assistant, and a photo of the
  boiler display when it matters.
- **Where you were in the guide:** the INSTALL.md section, or the
  INSTALL-CHECK.md row.
- **For the rc.4 items:** the morning line, the **Yesterday** block or the
  holiday list as text or a screenshot, with the date, the room and whether it
  has floor heating or radiators.
- If you are comfortable with it: the diagnostics file and the relevant part
  of the E32 log (section 6).

Notes on the guide itself (a word that did not match, a missing step) are
just as welcome. The filled-in [INSTALL-CHECK.md](INSTALL-CHECK.md) is the
best report of all.

## 8. Known limits in rc.4

- **Radiator valve control is not yet verified on real valves.** You are the
  one verifying it. Switch **Valve control** on one room at a time, after the
  takeover.
- **EMS Classic (EMS 1.0) boilers only.** EMS+ boilers come in 1.1.
- **Writing boiler settings** comes after 1.0; the E32 only reads them.
- **The three-way valve position** cannot be seen behind an adapter that does
  not report it (such as the Bosch EasyControl Adapter).
- **Charts are lost** when the E32 restarts.
- **Smart warm-up starts as an estimate.** Until a room has been checked on a
  few mornings, it can be warm a little early or late; the E32 adjusts it
  every morning.
- **Self-tuning** waits 24 hours after the first start or a change that
  touches the control, and 2 hours after a restart. It only changes settings
  on days the E32 controlled the boiler. During a trial run it only shows what
  it would change.
- **HACS** lists OpenThermostat as a custom repository, not yet in the
  default HACS list.
- **The E32 connects to the broker without TLS** (port 1883); keep the broker
  on your home network.
- **The E32 pages are in English and Dutch**; Home Assistant also has Polish.
- **The TopLine display codes** come from the manufacturer's manuals and have
  not yet been checked on a real TopLine.
