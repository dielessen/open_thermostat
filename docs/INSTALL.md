# Install OpenThermostat from scratch

This guide takes you from a new BBQKees E32 V2 gateway to a working
OpenThermostat: firmware installed, connected to your network and boiler,
rooms set up, and, if you want, linked to Home Assistant. It is written for
E32 firmware beta.18 or newer and the Home Assistant integration 0.4.0b10 or
newer. If a newer release changes a step, its release notes say so.

**What you get:** the E32 measures your rooms, follows a week program per room
and calculates what it would ask of the boiler. In the current releases it
runs in **shadow mode**: your existing thermostat keeps controlling the
boiler, and the E32 sends no heat request. Nothing in this guide makes the E32
control your boiler.

**Time needed:** about an hour without Home Assistant, plus about half an hour
for Home Assistant.

**Contents**

1. [What you need](#1-what-you-need)
2. [Install the firmware on a new E32 (USB)](#2-install-the-firmware-on-a-new-e32-usb)
3. [First start: connect the E32 to your network](#3-first-start-connect-the-e32-to-your-network)
4. [Basic settings](#4-basic-settings)
5. [Connect the E32 to the boiler](#5-connect-the-e32-to-the-boiler)
6. [Pair a Bluetooth thermometer](#6-pair-a-bluetooth-thermometer)
7. [Rooms without Home Assistant](#7-rooms-without-home-assistant)
8. [Home Assistant (optional)](#8-home-assistant-optional)
9. [Updates](#9-updates)
10. [Forgotten password and Wi-Fi recovery over USB](#10-forgotten-password-and-wi-fi-recovery-over-usb)
11. [Troubleshooting](#11-troubleshooting)

## 1. What you need

The full list is in the [requirements](../README.md#requirements). In short:

- A **BBQKees E32 V2** gateway (ESP32, 16 MB flash). Other boards are not
  supported by the release files.
- An **EMS Classic (EMS 1.0) boiler**, directly or through an adapter such as
  the Bosch EasyControl Adapter. EMS+ (EMS 2.0) boilers are not supported yet.
- A **2.4 GHz Wi-Fi** network, or an Ethernet cable to your router.
- A **USB-C cable that carries data** (not a charge-only cable) and a
  computer, for the first installation.
- At least one **temperature source per room**: a supported Bluetooth
  thermometer, or a temperature sensor in Home Assistant.
- For Home Assistant: **Home Assistant 2026.10.2, 2026.10.3 or 2026.10.4**
  (the integration checks the exact version before it changes its
  configuration), an **MQTT broker** such as the Mosquitto broker add-on, and
  Home Assistant's **MQTT integration**.

## 2. Install the firmware on a new E32 (USB)

You do this once. Later updates go over the network and keep your settings
(see [Updates](#9-updates)).

> **This erases the E32.** A BBQKees gateway usually comes with EMS-ESP
> installed. Installing OpenThermostat replaces it and deletes its settings.
> If you may want to go back, first export your EMS-ESP settings and make a
> full backup as described in [backup and recovery](FLASHING.md#make-a-full-backup-first).

### 2.1 Download the release

1. Open the [releases page](https://github.com/dielessen/open_thermostat/releases)
   and choose the newest **E32 V2** release (its tag starts with `v` and
   contains `e32v2`, for example `v0.1.0-e32v2-beta.18`).
2. Under **Assets**, download `open-thermostat-e32v2-<version>.zip`. Do not use
   the automatically generated "Source code" files.
3. Extract the ZIP into a new folder. You need two files from it:
   - `e32v2-factory.bin`: the complete installation image (bootloader,
     partition table, firmware and web interface in one file, written at
     address `0x0`);
   - `FACTORY-CHECK.txt`: the image length and the MD5 checksum to check the
     written image.

   `firmware.bin` in the same release is for updates only. The factory image
   is for a first installation or a clean reinstall only.

### 2.2 Connect the E32 to your computer

1. Disconnect the E32 from the boiler (the EMS cable) and from any other power
   supply.
2. Connect the E32's USB-C port to your computer. USB powers the E32 while you
   install.
3. If your computer shows no new serial port (COM port on Windows), install
   the USB driver that BBQKees recommends for the gateway; see the
   [BBQKees firmware update guide](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2).

Choose one of the two routes below.

### 2.3 Route A: in the browser with ESPConnect

[ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/) is a free,
open-source flashing tool that runs in **Chrome or Edge** (not Safari or
Firefox). It is made by an independent developer, not by this project.

1. Open ESPConnect, choose **115200** baud if offered, click **Connect** and
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
   `FACTORY-CHECK.txt` (a number of bytes; current releases use 12,058,624
   bytes = `0xB80000`). Click **Compute MD5**. The result must equal the
   "MD5 before first boot" in `FACTORY-CHECK.txt`. If it differs, flash again.
   Do this check before the first start: the E32 writes its own settings at
   the first start, and the checksum no longer matches after that.
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

If either tool cannot connect, try another data cable and plug directly into
the computer, close other programs that use the same port, and follow
BBQKees' instructions for starting the board in download mode. Do not bridge
pins on the board.

## 3. First start: connect the E32 to your network

1. Power the E32 (USB is fine for now). Without saved Wi-Fi settings it opens
   its own setup Wi-Fi network **`OpenThermostat-xxxxxx`**, where `xxxxxx` is
   the end of its MAC address. The setup Wi-Fi password is
   **`openthermostat`**.
2. Join that network with your phone or laptop. The setup page usually opens
   by itself; if not, open `http://10.10.10.1/`. If your phone asks whether to
   stay connected to a network without internet, choose yes.
3. Choose your **2.4 GHz** home network (5 GHz networks are not shown) or type
   its name, enter its password and choose **Connect**. The test takes up to
   30 seconds. The settings are saved only after a successful connection; if
   it fails, the setup network stays available and you can try again.
4. When it succeeds, the page shows the E32's address on your home network
   and closes the setup network after a few seconds. Reconnect your phone or
   laptop to your home network and open that address. Save it as a bookmark.
   A new E32 is also reachable by its name, for example
   `http://openthermostat-a1b2c3.local/`, where your network supports `.local`
   names.
5. Sign in with user **`admin`** and password **`admin`**.
6. Choose your own password right away: **System → About → Password**, 8 to 64
   characters. The user name stays `admin`. Until you change it, the Overview
   reminds you. Home Assistant asks for this password later.

The setup network stays open for about 15 minutes. If it closes before you are
done, unplug the E32 and plug it in again: it opens again as long as no Wi-Fi
network is saved.

## 4. Basic settings

All of these are on **System → Network**. Choose **Save settings** at the
bottom when you are done; the E32 asks whether to restart so the changes take
effect. Choose yes.

- **Time zone** (section *Time*): week programs, "today" and the daily figures
  follow the E32's own clock. Pick your time zone from the list, or choose
  **Use this time zone** when the page suggests the time zone of your browser.
  For a time zone that is not listed, choose "Other" and enter its POSIX text
  under Advanced, for example `EST5EDT,M3.2.0,M11.1.0`. Keep the time server
  (`pool.ntp.org` by default) unless your network needs another one.
- **EMS bus** (section *Advanced settings → Hardware services*): tick **EMS bus
  enabled**. A newly installed E32 starts with it off; without it the E32
  receives no boiler data. Enabling it does not let the E32 send heat
  requests.
- **Ethernet instead of Wi-Fi (optional)** (section *Connection*): set **E32
  network** to **Ethernet only**, save, restart and connect the network cable.
  Your router then gives the E32 a new address; look it up in the router. In
  Ethernet mode the setup Wi-Fi does not open by itself; use the USB `setup`
  command if you ever need it (see [section 10](#10-forgotten-password-and-wi-fi-recovery-over-usb)).
- **MQTT** is only needed for Home Assistant; it is set in
  [section 8.2](#82-let-the-e32-use-the-broker).

To change the Wi-Fi network later, use **Start WiFi setup (restart)** on the
same page; the old network settings stay until a new connection works.

## 5. Connect the E32 to the boiler

> **Safety first.** Switch the boiler off (and disconnect its power) before
> you connect or disconnect anything on the EMS bus. Follow BBQKees'
> instructions for your gateway and boiler: see the
> [BBQKees wiki](https://bbqkees-electronics.nl/wiki/) and the
> [gateway hardware details](https://bbqkees-electronics.nl/wiki/gateway/hardware-details.html).
> If you are not sure how your boiler is wired, ask an installer.

1. Connect the E32 to the boiler's EMS bus as BBQKees describes, and power it
   the way BBQKees describes for your setup.
2. Leave your existing thermostat connected and in control. In shadow mode the
   E32 only listens and calculates.
3. Switch the boiler on again.
4. Open **Boiler** on the E32 and choose your boiler brand and model. The
   page should show temperatures and a status within a few minutes. "EMS
   reception is off" means the EMS bus setting from section 4 is still off.

Values depend on what your boiler and adapter actually report: not every
boiler reports water pressure, for example. Nothing is made up for a value
that is not reported.

## 6. Pair a Bluetooth thermometer

Supported: **Shelly BLU H&T Display**, **Xiaomi Monitor 3 (MJWSD05MMC)** with
its bindkey, and thermometers with **pvvx firmware** (BTHome v2, plain or with
a bindkey, or the older PVVX Custom format).

1. Place the sensor in the room, away from radiators, windows and direct sun,
   and within Bluetooth range of the E32.
2. On the E32, open **Sensors** and choose **Search nearby**. The list shows up
   to 32 of the strongest nearby devices.
3. Click your sensor, give it a clear name (for example "Living room
   thermometer") and choose the right profile. Enter the encryption key only
   if the sensor uses one; Xiaomi Monitor 3 always needs its bindkey. Keys are
   stored on the E32 and never shown again.
4. Choose **Save Bluetooth settings**. The E32 restarts by itself about 30
   seconds later.
5. After the restart the sensor shows a temperature. "Waiting" means nothing
   has been received yet.

Up to eight sensors can be paired. A reading stays valid for 15 minutes. The
[user guide](USER-GUIDE.md#4-pair-a-bluetooth-thermometer) has a worked
example for a pvvx thermometer.

## 7. Rooms without Home Assistant

Without Home Assistant, rooms are set up on the E32 **Rooms** page: name,
heating type, up to four temperature sources, a temperature without Home
Assistant, limits, a week program and the boiler flow limits. Follow
[Add your first room on the E32](USER-GUIDE.md#5-add-your-first-room-on-the-e32)
in the user guide. If you plan to use Home Assistant, you can skip this: you
will manage rooms there.

## 8. Home Assistant (optional)

Home Assistant adds its own sensors and thermostats as room sources, a
dashboard, heating advice, energy inputs and one-click firmware updates. The
E32 keeps working when Home Assistant is offline.

### 8.1 MQTT broker and MQTT integration

The E32 and Home Assistant exchange all live values over MQTT.

1. If you have no MQTT broker yet: in Home Assistant, go to **Settings →
   Add-ons → Add-on store**, install the **Mosquitto broker** add-on and start
   it.
2. Home Assistant then offers the **MQTT** integration under **Settings →
   Devices & services**. Add it. (If you use another broker, add the MQTT
   integration and enter that broker.)
3. Create a login for the E32 on the broker. With the Mosquitto add-on, the
   simplest way is a separate Home Assistant user, for example `e32`, under
   **Settings → People → Users** (this tab appears when advanced mode is on in
   your Home Assistant profile). The E32 needs a user name and password for
   the broker; Home Assistant refuses to connect an E32 without one.

### 8.2 Let the E32 use the broker

On the E32, open **System → Network**, section **MQTT**:

1. Tick **Enabled**.
2. **Broker address**: the IP address or name of the broker; with the
   Mosquitto add-on, the address of your Home Assistant.
3. **Broker port**: `1883` unless your broker uses another port.
4. **User name** and **Password**: the login from step 8.1.
5. Leave **Base** (`ib-therm` on a new E32) and the other advanced fields as
   they are; Home Assistant fills in what it needs when it connects.
6. Choose **Save settings** and let the E32 restart.

### 8.3 Install the integration package

The integration is installed by hand; it is not offered through HACS.

1. On the [releases page](https://github.com/dielessen/open_thermostat/releases),
   choose the Home Assistant release that its notes pair with your E32
   firmware (its tag starts with `ha-v`, for example `ha-v0.4.0b10`) and download
   `OpenThermostat-HA-<version>.zip`.
2. Extract the ZIP on your computer. Copy the folder
   `custom_components/open_thermostat` into your Home Assistant configuration
   folder (the folder that contains `configuration.yaml`), so that you end up
   with `custom_components/open_thermostat/manifest.json` inside it. Any way of
   copying files to Home Assistant works, for example the Samba share or
   File editor add-on.
3. Restart Home Assistant (**Settings → System → Restart**).

The other files in the ZIP (licence, checksums, release notes, `SOURCE.json`)
do not need to be copied. The optional Zigbee2MQTT companion in the same
release is not needed for OpenThermostat.

### 8.4 Add OpenThermostat

1. Go to **Settings → Devices & services → Add integration** and choose
   **OpenThermostat**.
2. **Set up your heating installation:** give it a name and choose whether to
   add the OpenThermostat dashboard (your own dashboards are kept). Under
   **Advanced**, keep the controller MQTT prefix `ib-therm`, the same as the
   E32's MQTT Base. (Only a second E32 needs another prefix.) Choose **Add
   installation**.

### 8.5 Add one starter room (current integration versions)

Before Home Assistant can connect to the E32, the current integration needs
one room in Home Assistant itself.

1. On the OpenThermostat integration page, choose **Add room**.
2. Give it a name and keep the heating type **Radiators** (the other types are
   not available in this step).
3. Choose a **room temperature sensor** from Home Assistant and at least one
   **radiator valve** (a climate entity). If you have no radiator valves in
   Home Assistant, you can choose an existing thermostat's climate entity.
   Saving this room does not switch on heating control and sends nothing to
   the chosen devices.
4. Set a temperature and save the room.

If Home Assistant has no climate entity at all, this step cannot be completed
with the current integration; keep using the E32 on its own (sections 6 and
7) until a later integration version.

After the connection, the rooms the E32 actually uses are managed under
**Configure → Rooms** (section 8.7). The starter room stays listed as an older
Home Assistant room record and is not used by the E32's heating calculation.

### 8.6 Connect the E32

1. On the OpenThermostat integration page, choose **Configure → Connect E32**.
2. **E32 web address:** the address you use in the browser, including
   `http://`, for example `http://192.168.1.50` or
   `http://openthermostat-a1b2c3.local`. An IP address or a local name ending
   in `.local`, `.lan`, `.home`, `.internal`, `.localdomain`, `.fritz.box` or
   `.home.arpa` works.
3. **E32 password:** your E32 web password from section 3.
4. Submit. Home Assistant checks the E32, sends the room plan and waits until
   the E32 confirms it. The E32 may restart once. When it says **E32
   connected**, close the window.

Home Assistant stores the password. If you change it on the E32 later, Home
Assistant asks for the new one (Re-authenticate on the integration page).

### 8.7 Set up your rooms

Go to **Configure → Rooms**. Rooms you already created on the E32 appear here
unchanged. Choose **Add a room** and fill in:

- **Temperature sources from Home Assistant** and/or **Bluetooth sensors on the
  E32** (1 to 4 in total; the first fresh one leads, the others are fallback),
  and whether to **use the Bluetooth sensors first**;
- optionally a **target temperature from Home Assistant** (leave empty to
  follow the week program);
- the **temperature without Home Assistant**, the temperature limits and the
  **week program on the E32**, one line per group of days, for example

  ```text
  mon-fri: 06:30 20.5, 22:30 18
  sat-sun: 08:00 20.5, 23:00 18
  ```

Check **Flow temperature limits** in the same menu (default 30–60 °C). Floor
heating fed without a mixing valve usually needs at most 45–50 °C. The E32
never asks for more than the boiler's own maximum heating temperature.

From now on the E32 Rooms page shows the rooms read-only ("Managed in Home
Assistant"), with **Edit here anyway** for when Home Assistant is not
reachable. The [user guide](USER-GUIDE.md#adding-home-assistant) explains the
fields and what happens when Home Assistant is offline.

### 8.8 Energy and outdoor temperature (optional)

Under **Configure → Energy and outdoor temperature** you can choose a gas
meter (m³ or kWh), a gas price sensor or a fixed price, the calorific value of
your gas, an outdoor temperature sensor or weather entity, and your boiler's
heating power. Every field is optional. With them, the gas and cost estimates
and the heating advice become more accurate.

### 8.9 Check it

- The OpenThermostat device shows the E32's values, and each room and
  Bluetooth sensor appears as its own device.
- The **OpenThermostat** dashboard in the sidebar (if you chose it) shows the
  rooms, the calculated boiler request and the advice.
- The **Heating problem** sensor is off when all is well.

## 9. Updates

Updates keep your network settings, rooms, programs and paired sensors. Never
use the factory image for an update.

**E32 firmware from Home Assistant (recommended).** Once the E32 is connected
(section 8.6), the OpenThermostat device has a **Firmware** update entity.
Home Assistant checks GitHub every 6 hours. A new version appears under
**Settings → Updates**, like an ESPHome device; choose **Install**. Home
Assistant downloads `firmware.bin` from the release, checks its SHA-256, size
and version, uploads it to the E32 over your network and waits until the E32
reports the new version. The ESPHome integration is not needed.

**E32 firmware without Home Assistant.** Open **System → Firmware update** on
the E32:

- **Check for updates** lets the E32 look for a new release itself and
  **Download and install** it. If that check fails, use the manual upload.
- **Manual upload / recovery:** download `firmware.bin` of the release
  (**Look up latest release on GitHub** helps you find it and check the file
  against its published SHA-256), choose it and **Upload firmware**. Use the
  app firmware only, never `e32v2-factory.bin`.

**Automatic rollback.** A new firmware confirms itself after it has run
normally for about a minute and the network has worked. Until then other
restarts wait. If the new firmware fails to start, or gets no working network
connection within 10 minutes (router, MQTT broker or web page answering), the
E32 goes back to the previous version by itself.

**Home Assistant integration.** Download the new `OpenThermostat-HA-<version>.zip`,
replace the `custom_components/open_thermostat` folder with the new one and
restart Home Assistant. Keep your existing OpenThermostat entry; there is no
need to remove and add it again. The E32 firmware update does not update the
integration. Install firmware and integration versions that their release
notes pair together.

## 10. Forgotten password and Wi-Fi recovery over USB

Two commands work over the USB cable. They need physical access to the E32.

1. Connect the E32 to a computer with a USB-C data cable.
2. Open a serial terminal at **115200 baud** that sends a line ending when you
   press Enter, for example the Arduino IDE Serial Monitor, PuTTY, or
   `python -m serial.tools.miniterm PORT 115200` (from the `pyserial` package).
3. At start-up the E32 prints the setup Wi-Fi password and a reminder of these
   commands. Type one and press Enter:
   - **`password-reset`** restores the web password to `admin`. Sign in with
     `admin` / `admin` and choose a new password under System → About. Home
     Assistant then asks for the new password.
   - **`setup`** restarts the E32 into the setup Wi-Fi network
     `OpenThermostat-xxxxxx` for 15 minutes, also when a Wi-Fi network is
     saved or the E32 uses Ethernet. Use it after a router or Wi-Fi password
     change. The saved network stays until a new connection works.

## 11. Troubleshooting

### The E32 is not reachable

- Make sure your phone or computer is on the same home network as the E32.
- Look up the E32's address in your router (its name starts with
  `openthermostat-`), or try `http://openthermostat-xxxxxx.local/`.
- Wi-Fi must be 2.4 GHz. If the Wi-Fi name or password changed, use the USB
  `setup` command ([section 10](#10-forgotten-password-and-wi-fi-recovery-over-usb)).
- In Ethernet mode, check the cable and the router; the setup Wi-Fi does not
  open by itself.
- Never configured yet? Look for the `OpenThermostat-xxxxxx` network and open
  `http://10.10.10.1/`.

### No values in Home Assistant

The live values come over MQTT.

- In Home Assistant, check that the MQTT integration is set up and connected.
- On the E32, check System → Network → MQTT: **Enabled** ticked, the right
  broker address and port, and a user name and password the broker accepts.
  Save and restart after a change. The system log (System → System log) shows
  connection errors.
- The Base on the E32 and the controller MQTT prefix of the integration must
  match; Connect E32 sets this up.
- The **Heating problem** sensor reports when the E32 has sent nothing for 10
  minutes.

### Connect E32 does not work

The form says what is wrong. The most common messages:

- *Enter the local E32 web address*: include `http://` and use an IP address
  or a local name (section 8.6).
- *The E32 did not accept this password*: use the E32 web password (user
  `admin`).
- *The E32 needs a working MQTT connection first*: complete section 8.2,
  including a broker user name.
- *Add a room with its temperature sensor and radiator valves first*: see
  section 8.5.
- *The saved rooms or programs do not fit the current E32 connection
  profile*: also check that your Home Assistant version is 2026.10.2,
  2026.10.3 or 2026.10.4.
- *The E32 is updating, restarting or has a conflicting configuration*: wait
  until the E32 has finished and try again.

### A Bluetooth sensor is not found or stays "Waiting"

- Bring it closer to the E32 and check its battery. Search lists only the 32
  strongest devices nearby.
- Check the profile and the encryption: an encrypted sensor needs its key;
  Xiaomi Monitor 3 needs its bindkey. A pvvx thermometer must advertise in
  BTHome v2 or PVVX Custom format.
- After saving, wait for the automatic restart (about 30 seconds).
- At most eight sensors can be paired.

### A room shows no measurement

- **"Last value (source lost)"**: none of the room's sources delivered a fresh
  reading. The room keeps its last value for 30 minutes.
- **"No measurement: no heat request"**: still no reading after 30 minutes;
  the room stops asking for heat.

Check the sources: a Bluetooth reading is valid for 15 minutes, so the sensor
must be heard at least that often. A Home Assistant source needs Home
Assistant and MQTT running; Home Assistant forwards it on every change and
every five minutes, and it must report a temperature in °C or °F. Adding a
second source (for example a Bluetooth sensor as fallback) keeps the room
measured when one source drops out.

### An update was rolled back

The E32 still shows the previous version after an update when the new
firmware did not start properly or did not reach the network within 10
minutes. Check that the router and the MQTT broker were available, then try
again. **System → Firmware update → Update diagnostics** and the system log
show what happened. If Home Assistant reports that the E32 did not report the
new version within 3 minutes, check the version on the E32 itself before
trying again.

### Something else

The [user guide](USER-GUIDE.md) explains every setting. For recovery to the
original firmware, see [backup and recovery](FLASHING.md). When you report a
problem on GitHub, include the firmware and integration versions and the
relevant part of the system log; remove passwords and keys first.
