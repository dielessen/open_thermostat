# Install OpenThermostat

This guide takes you from a new BBQKees E32 V2 gateway to a working
OpenThermostat with Home Assistant: firmware installed, connected to your
network and boiler, linked to Home Assistant, and your rooms set up with a
week program. You do not need to be a developer. You do need to be
comfortable copying files to Home Assistant and, once, connecting the E32 to
your boiler.

It matches E32 firmware **beta.19 or newer** and the Home Assistant
integration **0.4.0b11 or newer**. Always install the firmware and the
integration versions that the release notes pair together: a firmware and an
integration from different releases may not understand each other.

> **Beta software in shadow mode.** OpenThermostat is still in beta. In the
> current releases the E32 runs in **shadow mode**: it measures your rooms,
> follows your week programs and calculates what it *would* ask of the boiler,
> but it does not send that request. Your existing thermostat keeps
> controlling the boiler. Nothing in this guide makes the E32 control your
> boiler. The one thing that does act on your home is an optional *setting
> device* (a valve or thermostat that Home Assistant sets to your week
> program); see [What shadow mode does](#12-what-shadow-mode-does-and-does-not-do).

**Time needed:** about one hour for the E32, plus about half an hour for Home
Assistant.

## Contents

1. [What you need](#1-what-you-need)
2. [Install the firmware on the E32 (first time, over USB)](#2-install-the-firmware-on-the-e32-first-time-over-usb)
3. [First start: connect the E32 to your Wi-Fi](#3-first-start-connect-the-e32-to-your-wi-fi)
4. [Sign in and change the admin password](#4-sign-in-and-change-the-admin-password)
5. [Basic settings: time zone and boiler reception](#5-basic-settings-time-zone-and-boiler-reception)
6. [Connect the E32 to the boiler](#6-connect-the-e32-to-the-boiler)
7. [Pair Bluetooth thermometers (optional)](#7-pair-bluetooth-thermometers-optional)
8. [MQTT: let the E32 talk to Home Assistant](#8-mqtt-let-the-e32-talk-to-home-assistant)
9. [Install the Home Assistant integration](#9-install-the-home-assistant-integration)
10. [Add the integration and connect the E32](#10-add-the-integration-and-connect-the-e32)
11. [Add your rooms](#11-add-your-rooms)
12. [What shadow mode does and does not do](#12-what-shadow-mode-does-and-does-not-do)
13. [Updates](#13-updates)
14. [Backup and restore](#14-backup-and-restore)
15. [Forgotten password and Wi-Fi recovery over USB](#15-forgotten-password-and-wi-fi-recovery-over-usb)
16. [Troubleshooting](#16-troubleshooting)

## 1. What you need

**Hardware**

- A **BBQKees E32 V2** gateway (ESP32 with 16 MB flash). The release files
  are built for this board only; the original E32 and the ESP32-S3 gateways
  are different boards.
- A boiler that speaks **EMS Classic (EMS 1.0)**, connected directly or
  through an adapter such as the Bosch EasyControl Adapter. Boilers that only
  speak **EMS+ (EMS 2.0) are not supported yet**; EMS+ support is planned for
  version 1.1.
- A **USB-C cable that carries data** (not a charge-only cable) and a
  computer, for the first installation.
- At least one **temperature source per room**: a supported Bluetooth
  thermometer, or a temperature sensor or thermostat that is already in Home
  Assistant.

**Network**

- A **2.4 GHz Wi-Fi** network (the E32 cannot use 5 GHz), or an Ethernet
  cable to your router.

**Home Assistant**

- **Home Assistant 2026.10.0 or newer** (tested with 2026.10.2 to 2026.10.4).
- An **MQTT broker**, for example the Mosquitto broker add-on, and Home
  Assistant's **MQTT integration**. All live values travel between the E32 and
  Home Assistant over MQTT. Section 8 explains how to set it up.
- Internet access for Home Assistant, so it can fetch firmware updates from
  GitHub.

**Not needed:** a cloud account, HACS or the ESPHome integration.

## 2. Install the firmware on the E32 (first time, over USB)

You do this only once. Later updates go over your network and keep your
settings (see [Updates](#13-updates)).

> **This erases the E32.** A BBQKees gateway usually comes with EMS-ESP
> installed. Installing OpenThermostat replaces it and deletes its settings.
> If you might want to go back, first export your EMS-ESP settings and make a
> full backup as described in [USB backup and recovery](FLASHING.md#make-a-full-backup-first).

### 2.1 Download the release

1. Open the [releases page](https://github.com/dielessen/open_thermostat/releases)
   and choose the newest **E32 V2** release. Its tag starts with `v` and
   contains `e32v2`, for example `v0.1.0-e32v2-beta.19`.
2. Under **Assets**, download `open-thermostat-e32v2-<version>.zip`. Do not
   use the "Source code" downloads that GitHub adds automatically.
3. Extract the ZIP into a new folder. You need two files from it:
   - `e32v2-factory.bin`: the complete installation image, written at address
     `0x0`;
   - `FACTORY-CHECK.txt`: the image length and the checksum (MD5) you use to
     check that the image was written correctly.

   The `firmware.bin` in the same release is for updates only. The factory
   image is only for a first installation or a clean reinstall.

### 2.2 Connect the E32 to your computer

1. Disconnect the E32 from the boiler (the EMS cable) and from any other power
   supply.
2. Connect the E32's USB-C port to your computer. USB powers the E32 while you
   install.
3. If your computer shows no new serial port (a COM port on Windows), install
   the USB driver that BBQKees recommends; see the
   [BBQKees firmware update guide](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2).

Then choose one of the two routes below. Route A needs no installation on
your computer.

### 2.3 Route A: in the browser with ESPConnect

[ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/) is a free,
open-source flashing tool that runs in **Chrome or Edge** (not Safari or
Firefox). It is made by an independent developer, not by this project.

1. Open ESPConnect, choose **115200** baud if it asks, click **Connect** and
   pick the E32's serial port.
2. Check **Device Info**: it must show an **ESP32** (not ESP32-S3) with
   **16 MB** flash. If it does not, stop: this is not an E32 V2.
3. Go to **Flash Tools → Flash Firmware** and select `e32v2-factory.bin`.
4. Set the **flash offset** to exactly `0x0` and tick **Erase entire flash
   before writing**.
5. Click **Flash Firmware**, check the file name and `0x0` in the
   confirmation, and wait until it reports success. Keep the cable connected.
6. Before the first restart, check the result under **Flash Tools → Flash
   Integrity**: start offset `0x0`, length = the `Length` from
   `FACTORY-CHECK.txt` (a number of bytes). Click **Compute MD5**. The result
   must equal the "MD5 before first boot" in `FACTORY-CHECK.txt`. If it
   differs, flash again.
   *Why now:* at its first start the E32 writes its own settings, after which
   the checksum no longer matches.
7. Click **Disconnect**, unplug the USB cable and plug it in again. The E32
   starts OpenThermostat.

### 2.4 Route B: on the command line with esptool

For people who prefer a terminal. Install Python, then run these commands in
the folder with the extracted files. Replace `PORT` with the E32's port, for
example `COM5` on Windows or `/dev/ttyUSB0` on Linux.

```sh
python -m pip install esptool==4.5.1
python -m esptool --chip esp32 --port PORT flash_id
# Continue only if this reports an ESP32 with 16MB flash.
python -m esptool --chip esp32 --port PORT --after no_reset erase_flash
python -m esptool --chip esp32 --port PORT --baud 115200 --after no_reset write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 e32v2-factory.bin
python -m esptool --chip esp32 --port PORT --after no_reset verify_flash 0x0 e32v2-factory.bin
```

`--after no_reset` keeps the E32 from starting before the check. When
`verify_flash` succeeds, unplug the USB cable and plug it in again.

**If neither tool can connect:** try another data cable, plug directly into
the computer (not through a hub), close other programs that use the same
port, and follow BBQKees' instructions for starting the board in download
mode. Do not bridge pins on the board.

## 3. First start: connect the E32 to your Wi-Fi

A new E32 has no Wi-Fi settings yet, so it opens its own temporary setup
network for you to connect to.

1. Power the E32 (USB is fine for now). After a few seconds a Wi-Fi network
   called **`OpenThermostat-xxxxxx`** appears, where `xxxxxx` is the end of the
   E32's hardware address. Its password is **`openthermostat`**.
2. Join that network with your phone or laptop. The page **Connect to your
   WiFi** usually opens by itself; if not, open `http://10.10.10.1/` in a
   browser. If your phone asks whether to stay on a network without internet,
   choose to stay.
3. Choose **Find networks**, pick your home network under **Networks found**
   (only 2.4 GHz networks are listed), or type its name under **WiFi name**.
   Enter the **WiFi password** and choose **Connect**.
4. The E32 tests the connection; this takes up to 30 seconds. Your settings
   are saved only after a successful connection. If it fails, the page says
   so, the setup network stays available, and you can try again.
5. When it succeeds, the page shows **WiFi connected** and the E32's address
   on your home network, then closes the setup network after a few seconds.
   Reconnect your phone or laptop to your home network and open that address.
   **Save it as a bookmark**: you will need it again for Home Assistant.

A new E32 is also reachable by its name, for example
`http://openthermostat-a1b2c3.local/`, if your network supports `.local`
names. Your router's list of connected devices shows it too (its name starts
with `openthermostat-`).

The setup network stays open for about 15 minutes. If it closes before you
are done, unplug the E32 and plug it in again: it opens again as long as no
Wi-Fi network has been saved.

**Ethernet instead of Wi-Fi (optional):** after signing in, open **Settings**,
section **Connection**, set **E32 network (active after restart)** to
**Ethernet only**, choose **Save settings**, let the E32 restart and plug in
the network cable. Your router then gives the E32 a new address; look it up in
the router.

## 4. Sign in and change the admin password

1. Open the E32's address. Sign in with user **`admin`** and password
   **`admin`**.
2. Choose your own password straight away: open **Settings → Password**
   (the Overview also shows a reminder with a **Change password** button while
   the default password is in use). Enter the **Current password** (`admin`),
   your **New password** (8 to 64 characters) twice, and choose **Change
   password**. The user name stays `admin`.

*Why it matters:* with the default password, anyone on your network can
change your heating. Home Assistant also shows a repair message until you
change it. Write the new password down: Home Assistant asks for it in
section 10. If you ever forget it, you can reset it over USB
([section 15](#15-forgotten-password-and-wi-fi-recovery-over-usb)).

The E32 menu reads **Overview, Rooms, Boiler, Sensors, Settings** and
**System** (Firmware update, System log, About, Restart device).

## 5. Basic settings: time zone and boiler reception

Both are on the **Settings** page. When you are done, choose **Save settings**
at the bottom. The E32 then asks whether to restart so the changes take
effect; choose **OK**.

1. **Time zone** (section **Time**). Week programs follow the E32's own clock,
   so it must know your time zone. Pick yours under **Time zone**, or choose
   **Use this time zone** when the page suggests your browser's time zone.
   Keep the time server (`pool.ntp.org`) unless your network needs another.
   For a time zone that is not listed, choose "Other (enter POSIX text under
   Advanced)" and enter it under **Advanced**, for example
   `EST5EDT,M3.2.0,M11.1.0` for US Eastern.
2. **Boiler reception** (section **Advanced settings → Hardware services**):
   tick **EMS bus enabled**. A newly installed E32 starts with this off, so it
   receives no boiler data until you turn it on. Turning it on only lets the
   E32 *listen* to the boiler; it does not let it send heat requests.

Leave the other settings as they are for now. MQTT follows in section 8.

## 6. Connect the E32 to the boiler

> **Safety first.** Switch the boiler off (and disconnect its power) before
> you connect or disconnect anything on the EMS bus. Follow BBQKees'
> instructions for your gateway and boiler: see the
> [BBQKees wiki](https://bbqkees-electronics.nl/wiki/) and the
> [gateway hardware details](https://bbqkees-electronics.nl/wiki/gateway/hardware-details.html).
> If you are not sure how your boiler is wired, ask an installer.

1. Connect the E32 to the boiler's EMS bus and power it the way BBQKees
   describes for your setup.
2. **Leave your existing thermostat connected and in control.** In shadow mode
   the E32 only listens and calculates; your thermostat keeps heating the
   house.
3. Switch the boiler on again.
4. On the E32, open **Boiler**. Within a few minutes it shows live values such
   as flow and return temperature and the burner status. "EMS reception is
   off." means the **EMS bus enabled** setting from section 5 is still off.
5. Open **Boiler model**, choose your boiler and choose **Save boiler
   selection**. This only changes the name and picture shown; it does not
   change how the E32 talks to the boiler.

Not every boiler reports every value; water pressure, for example, is missing
on many models. The E32 never makes up a value that the boiler does not
report. See [Boiler values are missing](#boiler-values-are-missing).

## 7. Pair Bluetooth thermometers (optional)

Skip this section if all your room temperatures come from Home Assistant.
Bluetooth thermometers have one advantage: the E32 receives them itself, so
they keep working when Home Assistant is offline.

Supported: **Shelly BLU H&T Display**, **Xiaomi Monitor 3 (MJWSD05MMC)** with
its bindkey, and thermometers with **pvvx firmware** (BTHome v2, plain or with
a bindkey, or the older PVVX Custom format).

1. Place the sensor in the room, away from radiators, windows and direct sun,
   and within Bluetooth range of the E32.
2. On the E32, open **Sensors** and choose **Search nearby**. The list shows
   up to 32 of the strongest nearby devices.
3. Click your sensor. Give it a clear name (for example "Living room
   thermometer") and check its profile. Enter the encryption key only if the
   sensor uses one; Xiaomi Monitor 3 always needs its bindkey. Keys are stored
   on the E32 and never shown again.
4. Choose **Save Bluetooth settings**. The E32 restarts by itself about 30
   seconds later to apply them.
5. After the restart the sensor shows a temperature under **Your sensors**.
   "Waiting" means nothing has been received yet.

Up to eight sensors can be paired. A reading stays valid for 15 minutes. The
[user guide](USER-GUIDE.md#4-pair-a-bluetooth-thermometer) has a worked
example for a pvvx thermometer.

## 8. MQTT: let the E32 talk to Home Assistant

MQTT is the messenger between the E32 and Home Assistant: the E32 sends its
room temperatures, boiler values and calculations through an MQTT *broker*,
and Home Assistant reads them there. Home Assistant's own setup step
([section 10](#10-add-the-integration-and-connect-the-e32)) refuses to
continue until MQTT is on, so do this first.

### 8.1 A broker and Home Assistant's MQTT integration

Skip this if Home Assistant already uses an MQTT broker.

1. In Home Assistant, go to **Settings → Add-ons → Add-on store**, install
   the **Mosquitto broker** add-on and start it. (Add-ons exist on Home
   Assistant OS and Supervised installations. On other installation types, run
   an MQTT broker yourself.)
2. Home Assistant then offers the **MQTT** integration under **Settings →
   Devices & services**. Add it. If you use another broker, add the MQTT
   integration and enter that broker.

### 8.2 A login for the E32 on the broker

The E32 needs its own user name and password on the broker; it does not
connect to Home Assistant through a broker without a login.

With the Mosquitto add-on, the simplest way is a separate Home Assistant user,
for example `e32`: **Settings → People → Users → Add user**. (The **Users** tab
appears when **Advanced mode** is on in your Home Assistant user profile.) The
user does not need to be an administrator.

### 8.3 MQTT settings on the E32

On the E32, open **Settings**, section **MQTT**:

1. Tick **Enabled**.
2. Leave **Publish Home Assistant MQTT Discovery** ticked; it lets Home
   Assistant find the E32's values automatically.
3. **Broker address**: the IP address or name of the broker. With the
   Mosquitto add-on, this is the address of your Home Assistant, for example
   `192.168.1.10`.
4. **Broker port**: `1883`, unless your broker uses another port.
5. **User name** and **Password**: the login from section 8.2.
6. Leave everything under **Advanced** as it is. The **Base** is
   `openthermostat` on a new E32 (an E32 set up before beta.19 keeps
   `ib-therm`); Home Assistant fills in what it needs when it connects.
7. Leave the **Home Assistant** section above it alone as well. Home Assistant
   fills in **HA adapter ID** and the shadow-mode tick itself in section 10.
8. Choose **Save settings** and let the E32 restart.

After the restart, the **System → System log** page shows whether the E32
reached the broker.

## 9. Install the Home Assistant integration

The integration is installed by hand; it is not available through HACS yet.

1. On the [releases page](https://github.com/dielessen/open_thermostat/releases),
   choose the **Home Assistant** release that the release notes pair with your
   E32 firmware. Its tag starts with `ha-v`, for example `ha-v0.4.0b11`.
   Download `OpenThermostat-HA-<version>.zip`.
2. Extract the ZIP on your computer. It contains a folder
   `custom_components/open_thermostat`.
3. Copy that `open_thermostat` folder into the `custom_components` folder of
   your Home Assistant configuration folder (the folder that contains
   `configuration.yaml`). Create `custom_components` if it does not exist yet.
   When you are done, this file must exist:
   `<config>/custom_components/open_thermostat/manifest.json`.
   Any way of copying files to Home Assistant works, for example the
   **Samba share** or **File editor** add-on.
4. Restart Home Assistant (**Settings → System → Restart**). *Why:* Home
   Assistant only loads new integrations at start-up.

The other files in the ZIP (licence, checksums, release notes, `SOURCE.json`)
do not need to be copied. The optional Zigbee2MQTT companion in the same
release is not needed.

## 10. Add the integration and connect the E32

### 10.1 Add OpenThermostat

1. Go to **Settings → Devices & services → Add integration** and choose
   **OpenThermostat**.
2. The form **Set up your heating installation** opens:
   - **Installation name**: any name you recognise, for example "Home".
   - **Show the OpenThermostat dashboard**: tick it. The dashboard holds the
     visual week planner, so it makes the next steps easier. Your own
     dashboards are kept.
   - **Advanced → Controller MQTT prefix**: keep `openthermostat`. Change it
     only if the **Base** on your E32's MQTT settings is different (for
     example `ib-therm` on an older E32). The two must match.
3. Choose **Add installation**.

Home Assistant then tells you the next step: **Configure → Connect E32**.
You do not need to add a room yet; that comes right after connecting.

### 10.2 Connect the E32

Before you start, check that MQTT on the E32 is on with a broker user name and
password (section 8.3). Without it, this step stops with a message.

1. Go to **Settings → Devices & services → OpenThermostat** and choose
   **Configure** (the gear icon).
2. Choose **Connect E32**.
3. **E32 web address**: the address you use in your browser, including
   `http://`, for example `http://192.168.1.50` or
   `http://openthermostat-a1b2c3.local`. An IP address or a home-network name
   ending in `.local`, `.lan`, `.home`, `.internal`, `.localdomain`,
   `.fritz.box` or `.home.arpa` works.
4. **E32 password**: the password you chose in section 4.
5. Choose **Submit**. Home Assistant checks the E32, points its MQTT link to
   Home Assistant and waits for the E32's first report over MQTT. This can
   take up to two minutes, and the E32 may restart once.
6. When **E32 connected** appears, continue with **Add the first room**
   (section 11).

Home Assistant stores the E32 password. If you change it on the E32 later,
Home Assistant asks for the new one (a **Re-authenticate** prompt on the
integration).

The E32's **Overview** now shows **Home Assistant: connected**.

## 11. Add your rooms

Every room has:

- **one to four temperature sources**: Home Assistant sensors or thermostats,
  and/or Bluetooth sensors paired on the E32. The first one with a fresh value
  is used; the others are a backup;
- **a week program**: the temperatures the room should have through the week.
  The E32 stores it and runs it, also when Home Assistant is offline;
- **optionally a setting device**: a thermostat, radiator valve or number in
  Home Assistant that shows the program's temperature and lets you turn it up
  or down by hand.

### 11.1 Add a room

Right after connecting, choose **Add the first room**. Later, go to
**Configure → Rooms → Add a room**. Fill in the **E32 room** form:

1. **Room name**, for example "Living room" (up to 40 letters).
2. **Heating**: **On**. (**Off (no heat demand)** keeps the room in the plan
   but it never asks for heat.)
3. **Heating type**: **Radiators** or **Floor heating**. Each type gets its own
   flow temperature.
4. **Temperature sources from Home Assistant**: choose one or more sensors or
   thermostats that measure this room. Drag them to change the order.
5. **Bluetooth sensors on the E32**: choose the sensors from section 7, if
   any. Tick **Use the Bluetooth sensors first** to make them lead and keep the
   Home Assistant sources as backup.
6. **Setting device (optional)**: see [11.3](#113-the-setting-device).
7. **Temperature without Home Assistant**: a safe fixed temperature, for
   example 19 °C. The E32 uses it only in the rare case that the room has no
   usable week program, for example when the E32 has no valid clock.
8. **Week program on the E32**: the form fills in the **Workdays and weekend**
   template. You can keep it and fine-tune it later in the visual planner
   (11.2), or type your own: one line per group of days, for example

   ```text
   mon-fri: 06:30 20.5; 22:30 18
   sat-sun: 08:00 20.5; 23:00 18
   ```

   Each temperature holds until the next switch point; a line without days
   applies to every day; up to six switch points per day.
9. **Temperature limits** (folded section): the lowest and highest target this
   room may get. The program and any manual change stay within them.
10. Choose **Submit**. The room is saved on the E32 right away. Choose **Add a
    room** for the next one, or close the window.

The "Workdays and weekend" template is: on workdays 20 °C from 06:30, 18 °C
from 08:30, 20 °C from 17:00 and 16 °C from 22:30; at the weekend 20 °C from
08:00 and 16 °C from 23:00.

To change or remove a room later: **Configure → Rooms → Edit or remove a
room**.

### 11.2 Edit the week program in the visual planner

The easiest way to change a program is the **Week program** view of the
**OpenThermostat** dashboard in the Home Assistant sidebar. Pick a level
(comfort, night, away), drag the edges of the blocks, copy a day to other days
or start from a template. The same planner is on the E32's **Rooms** page.
Both edit the same program on the E32, and neither overwrites a change the
other made in the meantime.

### 11.3 The setting device

The setting device is how you turn a room up or down by hand. Choose what fits
the room:

| Your room has | Choose as setting device | What happens |
| --- | --- | --- |
| A radiator valve (TRV) in Home Assistant | The valve's thermostat entity | The valve shows the program's temperature; turning it changes the room. |
| A smart thermostat such as tado | Its thermostat entity | The same, on the tado. |
| A number or input number with a target (for example a sensor with a settable temperature) | That number | The number shows the program's temperature; changing it changes the room. |
| None of these | Leave the field empty | You use the room's own **thermostat in Home Assistant** (one per room, created by the integration) or the E32 Overview as a virtual thermostat. |

How it works:

- At **every switch point** of the week program, Home Assistant sets the
  setting device to the program's temperature. It also does this when the
  room changes and when the E32 or Home Assistant comes back.
- **Turning the device yourself is an override until the next switch point.**
  At that switch point the program takes over again. Example: the program says
  18 °C from 08:30; you turn the tado to 21 °C at 10:00; the room aims for
  21 °C until the program's next switch point at 17:00, and then follows the
  program again.
- **Turn off the device's own schedule** (put it in manual mode, for example
  in the tado or valve app). Otherwise the device changes its temperature by
  itself and every change counts as an override. Home Assistant shows a repair
  message when it notices that a device runs its own schedule.
- Home Assistant writes only to the device you chose, at most once a minute,
  and never while the room is off or paused for an open window.
- If a temperature source of the room is a thermostat or valve, the form may
  suggest it as setting device. Clear the field if you do not want that.

The setting device is a convenience, not a requirement. It needs Home
Assistant: without Home Assistant the E32 keeps running the program, but
changes on the device are not seen until Home Assistant is back.

### 11.4 Flow temperature limits

The flow temperature is how warm the boiler water is that the E32 would ask
for. Check the limits under **Configure → Heating and boiler** (also shown on
the E32 **Boiler** page). The default is 30–60 °C. Floor heating fed without a
mixing valve usually needs at most 45–50 °C; radiators often need 60–75 °C on
cold days. The E32 never asks for more than the maximum heating temperature
set on the boiler itself.

### 11.5 More options (optional)

- **Configure → Comfort: window sensors, away and presence**: window and door
  sensors per room that pause the room while open, and who-is-home presence.
- **Configure → Energy and outdoor temperature**: a gas meter, gas price,
  outdoor temperature and your boiler's power. All optional; they make the gas
  and cost estimates and the heating advice more accurate.
- Notification blueprints: see the [user guide](USER-GUIDE.md).

### 11.6 Check it

- The **OpenThermostat** dashboard in the sidebar shows each room with its
  temperature, its target and a 24-hour graph, and the calculated boiler
  request.
- Each room has its own group on the integration page, with a thermostat
  (climate entity).
- The **Heating problem** sensor is off when all is well.
- On the E32, the **Rooms** page shows the rooms read-only with "Managed in
  Home Assistant". **Edit here anyway** unlocks editing on the E32 for when
  Home Assistant is not reachable.

**Without Home Assistant**, rooms are set up on the E32 **Rooms** page
instead; see [Add your first room on the E32](USER-GUIDE.md#5-add-your-first-room-on-the-e32).

## 12. What shadow mode does and does not do

**The E32 does:**

- measure every room and follow each room's week program, temporary changes,
  away mode and open-window pauses;
- calculate whether the house needs heat and at what flow temperature, and
  show that as the **calculated boiler request**;
- learn how fast each room warms up (shown as advice only);
- compare its decisions with your current thermostat where that thermostat
  talks to the boiler over EMS (on the E32 **Rooms** page and in Home
  Assistant);
- set your setting devices (valves, tado) to the program's temperature
  through Home Assistant.

**The E32 does not (yet):**

- send any heat request to the boiler. Your existing thermostat keeps
  controlling the boiler. The Overview says **Shadow mode** and **Your
  thermostat controls the boiler**;
- change any boiler setting;
- open or close valves itself.

**Watch out: setting devices are real devices.** Home Assistant really sets
them, also in shadow mode:

- A **radiator valve** chosen as setting device opens and closes by its own
  logic towards the program's temperature, so that radiator follows the week
  program.
- A **thermostat that controls your boiler** (for example a tado) chosen as
  setting device gets the program's temperature, so the week program now
  decides, through that thermostat, when the boiler heats.

That is usually what you want, but it means your heating can change on the
day you set it up. If you only want to watch in shadow mode first, leave the
setting device empty and add it later.

Active control is built into the firmware but locked. It will be opened in a
later release, together with an attended switch-over procedure in which
someone is present at the boiler; see the [switch-over procedure](SWITCHOVER.md)
(draft). Until then, keep your existing thermostat connected.

## 13. Updates

Updates keep your network settings, rooms, programs and paired sensors.
**Never use the factory image (`e32v2-factory.bin`) for an update**; it
erases everything.

### 13.1 Update order

When a new release pair comes out, read its release notes first. They say
which integration goes with which firmware. Usually: **update the integration
first, then the firmware.**

### 13.2 Update the integration

1. Download the new `OpenThermostat-HA-<version>.zip` from the releases page.
2. Delete the old `custom_components/open_thermostat` folder in your Home
   Assistant configuration folder and copy the new one in its place.
3. Restart Home Assistant.

Keep your existing OpenThermostat entry; there is no need to remove and add
it again. If you copied blueprints, copy them again.

### 13.3 Update the E32 firmware from Home Assistant (recommended)

1. The OpenThermostat device has an update entity called **Firmware**. Home
   Assistant checks GitHub for a new version every 6 hours.
2. A new version appears under **Settings → Updates**, like an ESPHome device.
   Choose it and choose **Install**.
3. Home Assistant downloads `firmware.bin`, checks its checksum, size and
   version, uploads it to the E32 and waits until the E32 reports the new
   version. Keep the E32 powered.

### 13.4 Update the E32 firmware without Home Assistant

On the E32, open **System → Firmware update**:

- **Check for updates** lets the E32 look for a new release itself; then
  choose **Download and install**.
- **Manual upload / recovery**: download `firmware.bin` from the release
  (**Look up latest release on GitHub** helps you find it and check it),
  choose it with **Choose firmware file...** and choose **Upload firmware**.

### 13.5 Automatic rollback

A new firmware confirms itself after it has run normally for about a minute
and the network has worked. If it fails to start, or gets no working network
connection within 10 minutes (router, MQTT broker or the web page answering),
the E32 goes back to the previous version by itself.

## 14. Backup and restore

Make a backup once your setup works, and again after big changes. It saves
your network and time settings, MQTT and the Home Assistant link, rooms and
week programs, Bluetooth sensors, flow settings, boiler model and language.

### 14.1 Make a backup

1. On the E32, open **Settings** and unfold **Backup and restore**.
2. Optionally tick **Include passwords and Bluetooth keys, encrypted with a
   passphrase** and enter a **Passphrase** (8 to 64 characters) twice. Without
   it the file holds no secrets, and the page lists what you would need to
   enter again after a restore (the MQTT password and the Bluetooth sensor
   keys).
3. Choose **Download backup** and keep the file somewhere safe. Keep the
   passphrase too: nobody can recover it.

The Wi-Fi password and the E32 web password are never in a backup.

### 14.2 Restore a backup

Use this on a new or reset E32, or to undo a change.

1. First connect the E32 to your network (section 3) and sign in.
2. Open **Settings → Backup and restore**, section **Restore a backup**.
   Choose the **Backup file**, enter the **Passphrase of this backup** if it
   has one, and choose **Check backup**.
3. The E32 shows what will change, what it skips and what you need to enter
   again. Nothing is saved yet.
4. Choose **Restore these settings**. If network or Bluetooth settings change,
   the E32 restarts about 10 seconds later; sign in again afterwards.
5. If the backup had no passphrase, enter the MQTT password again under
   **Settings → MQTT**. *Why:* MQTT stays off until you do, so Home Assistant
   receives nothing.

A restore never changes the Wi-Fi network or the web page port, and it always
puts the rooms back in shadow mode. It is refused while a boiler test runs.

Home Assistant's own backup (Settings → System → Backups) covers the
integration's settings in Home Assistant, including the copied
`custom_components` folder.

## 15. Forgotten password and Wi-Fi recovery over USB

Two commands work over the USB cable. They need physical access to the E32,
so nobody can use them over the network.

1. Connect the E32 to a computer with a USB-C data cable.
2. Open a serial terminal at **115200 baud** that sends a line ending when you
   press Enter, for example the Arduino IDE Serial Monitor, PuTTY, or
   `python -m serial.tools.miniterm PORT 115200` (from the `pyserial`
   package).
3. Type one of these commands and press Enter:
   - **`password-reset`** sets the web password back to `admin`. Sign in with
     `admin` / `admin` and choose a new password under **Settings →
     Password**. Home Assistant then asks for the new password.
   - **`setup`** restarts the E32 into the setup network
     `OpenThermostat-xxxxxx` for 15 minutes, also when a Wi-Fi network is
     saved or the E32 uses Ethernet. Use it after a router or Wi-Fi password
     change. The old network settings stay until a new connection works.

While the E32 still works on your network, you can also change Wi-Fi from
**Settings → Set up WiFi → Start WiFi setup (restart)**.

## 16. Troubleshooting

### The E32 is not reachable

- Make sure your phone or computer is on the same home network as the E32.
- Look up the E32's address in your router (its name starts with
  `openthermostat-`), or try `http://openthermostat-xxxxxx.local/`.
- Wi-Fi must be 2.4 GHz. If the Wi-Fi name or password changed, use the USB
  `setup` command ([section 15](#15-forgotten-password-and-wi-fi-recovery-over-usb)).
- In Ethernet mode, check the cable and the router; the setup network does not
  open by itself.
- Never set up yet? Look for the `OpenThermostat-xxxxxx` network and open
  `http://10.10.10.1/`.

### I cannot sign in on the E32

- The user name is always `admin`. Forgot the password? Use `password-reset`
  over USB (section 15).
- "Four saved web sessions occupy all sign-in slots": the E32 remembers up to
  four signed-in browsers. Tick **End previous web sessions and sign in** and
  enter your password again. A sign-in ends by itself after 30 minutes
  without use, after seven days, or when the E32 restarts.

### Connect E32 does not work

The form says what is wrong. The most common messages:

- *Enter the local E32 web address*: include `http://` and use an IP address
  or a home-network name; no paths or login details.
- *The E32 did not accept this password*: use the E32 web password (user
  `admin`), not your Home Assistant or MQTT password.
- *The E32 could not be reached*: check the address in a browser on the same
  network as Home Assistant.
- *The E32 needs its own MQTT login first*: MQTT is off on the E32, or has no
  user name or password. Complete [section 8.3](#83-mqtt-settings-on-the-e32)
  and let the E32 restart.
- *Home Assistant received nothing from it over MQTT within 90 seconds*: the
  E32 and Home Assistant do not use the same broker, or the broker refused
  the E32's login. Compare **Settings → MQTT** on the E32 with Home
  Assistant's MQTT integration, check the E32's **System → System log**, and
  try again.
- *This integration needs Home Assistant 2026.10.0 or newer*: update Home
  Assistant.
- *The E32 is updating, restarting or has a conflicting configuration*: wait
  a minute until the E32 is finished and try again.
- *This E32 or installation is already assigned to a different
  configuration*: the E32 is still linked to another OpenThermostat entry in
  Home Assistant (for example an old one). Remove the old entry, or connect
  from the entry it is linked to.

### No values in Home Assistant

All live values come over MQTT.

1. In Home Assistant, check that the MQTT integration is set up and connected.
2. On the E32, check **Settings → MQTT**: **Enabled** ticked, the right
   broker address and port, and a user name and password the broker accepts.
   Save and restart after a change. **System → System log** shows connection
   errors.
3. The **Base** on the E32 (Settings → MQTT → Advanced) and the controller
   MQTT prefix of the integration must match. Connect E32 sets this up; if you
   changed either by hand, run **Configure → Connect E32** again.
4. Check that the firmware and integration versions are a pair from the same
   release notes. An older integration does not understand newer firmware, and
   the other way round.

Values become unavailable only when the E32 reports itself offline or about 3
minutes pass without its heartbeat. The **Heating problem** sensor turns on
when the E32 has sent nothing for 10 minutes.

### The link between Home Assistant and the E32 does not come back

The E32 and Home Assistant keep a running session over MQTT. It restarts by
itself after a restart of Home Assistant, the broker or the E32, or after a
Wi-Fi outage. The E32 **Overview** shows its state: **Home Assistant:
connected**, or "last connected ... ago".

If it stays disconnected for more than a few minutes:

1. Check MQTT as in [No values in Home Assistant](#no-values-in-home-assistant).
2. If the E32 changed its password, Home Assistant shows a **Re-authenticate**
   prompt on the integration. Enter the new E32 password there.
3. If Home Assistant's clock jumped, a repair message "Room measurements
   paused: the clock of Home Assistant jumped" appears. Check the time of the
   Home Assistant host, then reload the integration (**Settings → Devices &
   services → OpenThermostat → ⋮ → Reload**).
4. Otherwise reload the integration, or run **Configure → Connect E32** again
   with the same address and password. Your rooms on the E32 stay as they
   are.

The E32 keeps running its rooms and week programs while the link is down.

### Boiler values are missing

The E32 learns which values your boiler really reports and Home Assistant only
creates entities for those. This keeps Home Assistant free of empty sensors,
but it can look as if something is missing.

- On the E32, open **Boiler → Boiler profile**. It lists:
  - **Values available**: what your boiler reports;
  - **Not fitted on this boiler**: the boiler always answers "no sensor" for
    these, for example a water pressure sensor it does not have;
  - **Not reported (yet)**: messages that only come in certain situations, or
    only when another controller asks for them.
- A value that appears later is added automatically.
- If you know your boiler has a value that is listed as not fitted, choose
  **Show anyway** next to it.
- In Home Assistant, values the boiler never reported are created disabled.
  You can enable them on the device page.
- No boiler values at all? Check that **EMS bus enabled** is ticked
  (section 5) and that the Boiler page does not say "EMS reception is off.".

### A room shows no measurement

- **"Last value (source lost)"**: none of the room's sources delivered a fresh
  reading. The room keeps its last value for 30 minutes.
- **"No measurement: no heat request"**: still no reading after 30 minutes;
  the room stops asking for heat.

A Bluetooth reading is valid for 15 minutes, so the sensor must be heard at
least that often. A Home Assistant source needs Home Assistant and MQTT
running and must report a temperature in °C or °F. Adding a second source
keeps the room measured when one drops out.

### A Bluetooth sensor is not found or stays "Waiting"

- Bring it closer to the E32 and check its battery. **Search nearby** lists
  only the 32 strongest devices.
- Check the profile and the key: an encrypted sensor needs its key; a pvvx
  thermometer must advertise in BTHome v2 or PVVX Custom format.
- After saving, wait for the automatic restart (about 30 seconds).
- At most eight sensors can be paired.

### The setting device changes the temperature by itself

The device runs its own schedule. Put it in manual mode (in its own app or
on the device). Home Assistant shows a repair message "{device} seems to run
its own schedule" when it notices this.

### Remove an old Home Assistant room

Installations set up with integration 0.4.0b10 or older had to create a room
in Home Assistant before the E32 could connect. That room is no longer used:
your rooms live on the E32 now. Home Assistant offers to remove it:

1. Go to **Settings → System → Repairs**.
2. Open **Old Home Assistant room no longer used** and follow the steps. The
   same is available under **Configure → Advanced and diagnostics → Remove old
   Home Assistant rooms**.
3. Home Assistant updates the E32 room plan first and then removes the old
   room's devices and entities. Your own sensors, thermostats and valves stay
   as they are, and so do the rooms on the E32. The E32 may restart once
   (about 30 seconds).

If an E32 room used the old room's thermostat as its only temperature source,
a repair **Choose a temperature source for ...** asks you to pick a new one.

### An update was rolled back

The E32 shows the previous version after an update when the new firmware did
not start properly or did not reach the network within 10 minutes. Check
that the router and the MQTT broker were available, then try again.
**System → Firmware update → Update diagnostics** and the system log show
what happened. If Home Assistant says the E32 did not report the new version
in time, check the version on the E32 itself before trying again.

### Something else

The [user guide](USER-GUIDE.md) explains every setting. For a return to the
original firmware, see [USB backup and recovery](FLASHING.md). When you
report a problem on GitHub, include the firmware and integration versions,
the relevant part of the E32 system log and, if you can, Home Assistant's
**Download diagnostics** file of the integration (it leaves out passwords,
keys, addresses and Wi-Fi names). Remove any passwords from logs before you
share them.
