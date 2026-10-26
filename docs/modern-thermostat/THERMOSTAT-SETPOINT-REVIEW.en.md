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

Our5–<50°C measured-temperature window in `ClassicHeatTrialEnvelope` is a
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
separate choice from confirming the correct thermostat control model. This
review does not silently expand the installed physical trial profile, change
its source gates or authorize a boiler command. The current UI explicitly calls
the limits commissioning limits and separates the target from burner ignition.
