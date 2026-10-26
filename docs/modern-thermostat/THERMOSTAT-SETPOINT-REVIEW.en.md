# Thermostat demand, measured flow and commissioning limits

The owner correctly distinguishes a requested flow-temperature target from
the boiler's measured water temperature. A thermostat can derive a target from
room demand and an outside-temperature curve. Receiving a low measured flow
temperature is not an EMS protocol prerequisite for sending `selflowtemp`.
Measured temperatures may still be used as feedback or diagnostics.

The boiler regulates its burner relative to the requested target and hysteresis.
An already-hot boiler can accept a lower target without immediately igniting.
A lack of ignition alone therefore does not establish a failed setpoint command.
Primary source: [EMS-ESP's boiler-control explanation](https://emsesp.org/tips-and-tricks#controlling-the-boiler-heating).

The installed beta.4 firmware's5–<50°C measured-temperature window is a
project-selected starting/continuation condition for the first supervised heat
trial. It is not a manufacturer-defined thermostat rule or an EMS/iRT encoding
requirement. It must not be presented as the normal room-demand algorithm.
The previous advice to wait below50°C described that implemented trial profile,
not what a normal thermostat must do before sending its target.

There are separate observations to record:

1. The intended target, actual transmitted telegram and subsequent target
   readback. An HTTP admission or local echo alone is insufficient.
2. The boiler's response: it can wait, modulate or heat depending on its actual
   temperature, hysteresis and current operating mode. Ignition is not an
   automatic success condition for a setpoint-transfer test.
3. A later zero target and actual stop feedback, with the independent local stop
   and the installation-specific heat path still assessed separately.

A lower setpoint does not instantly cool water already in the appliance. As an
engineering consideration, removing a measured-temperature trial limit is a
separate choice from confirming the correct thermostat control model. The
initial review did not change that profile. The later explicitly requested
source change is recorded below; it still requires new firmware on the device.
The UI identifies commissioning limits separately from normal thermostat logic.

## Owner-requested ten-minute trial

After the beta.4 zero-demand trial, the owner explicitly requested50°C for ten
minutes. The beta.5 candidate therefore supports40–50°C for at most600 seconds,
with50°C/600s as defaults and a separate measured-water window of5–<60°C.
This replaces the initial narrow commissioning profile; it is source work until
new firmware is installed. A warm boiler may accept50°C while waiting to cool.

Configuration is still required within ten minutes before starting. During the
finite heating phase, its age allowance includes at most one trial duration;
new reports can still withdraw permission. A new gauge observation is required
per preparation and must be less than two minutes old at start. It remains valid
for that finite run, without being renewed by keepalives. Live feedback, the
five-second supervision lease, fixed heat deadline and explicit stop remain.

[EMS-ESP documents refreshing the target at least once per minute](https://emsesp.org/tips-and-tricks#controlling-the-boiler-heating).
The trial transmitter's existing one-second interval is retained. The same
source warns about fallback to the panel setpoint: neither its cadence nor this
manual trial proves autonomous shutdown of the Classic/adapter on controller loss.
