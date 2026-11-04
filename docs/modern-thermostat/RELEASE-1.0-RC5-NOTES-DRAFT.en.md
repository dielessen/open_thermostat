# E32 V2 1.0.0-rc.5 — the fifth 1.0 candidate: the E32 listens to your boiler, knows your house and says what it knows
<!-- user-release-notes:v2:en -->

The fifth 1.0 candidate, with the last self-learning planned for 1.0. The E32
now listens to how your boiler answers it, works out how your house loses and
takes heat, says how much it already knows and what is still missing, and
starts a warm-up later when sun or people warm a room for free. There is
nothing new to set: it tunes itself and the pages say in plain words what it
found. If it runs 14 days unchanged and without problems with the E32
controlling the boiler, the same code becomes 1.0.0. Install it with HA
1.0.0rc6, whose dashboard has been redesigned (details in its release
notes).

## New

- **Listening to the boiler:** when your boiler keeps reaching the water
  temperature the E32 asked and stops by itself while a room still wants heat,
  the E32 asked for more than the house takes. After this happens twice in one
  request, the E32 learns a ceiling for the water temperature at that outdoor
  temperature and asks no more: cooler water and fewer burner starts. A room
  that is 1 °C or more below its target still gets the full water temperature,
  so a cold morning is not slowed by yesterday's holds. The E32 also learns how
  long the boiler itself rests after such a stop and keeps its own burner rest
  at least as long, unless a room is clearly cold (comfort first).
  With a return temperature it also sees how much heat the house absorbs. It
  uses only values every EMS boiler reports and changes no boiler setting. It
  listens while the E32 controls the boiler; the ceiling also needs Smart
  warm-up on (the default). The Home page says it in one sentence: "Your
  boiler rests about 6 min each time it reaches its temperature; the E32 asks
  at most 41 °C now, so it starts less often."
- **The house, and the curve earlier:** from how fast the rooms warm up and
  cool down, or from gas per degree of cold, the E32 works out how fast your
  house loses heat and how much heat the radiators or floor give per degree of
  water temperature. With that it estimates your Weather compensation line
  before it has seen its six steady periods, never less than half as steep as
  the standard line.
- **What it knows and what it still lacks:** one figure ("The E32 knows your
  house: 70 %") and, in words, what is still missing ("It still has to see how
  fast the living room warms up"), on the Home page under What the thermostat
  has learned. It rises by itself while the heating runs.
- **Yesterday against your own usual days:** from the fifth day, a day that
  stands out by more than 30 % (gas per degree of cold, burner starts per
  heating hour, heating time per degree of cold, a room that warmed up more
  slowly) gets one plain sentence with what can cause it. It is information:
  never a problem, never a repair.
- **Free heat:** sun, cooking and people warm a room without the boiler. The
  E32 learns that per room and part of the day, and Smart warm-up starts later
  for it, never less than half the usual lead; the morning check keeps
  correcting it. The room's details say it in words: "In the afternoon this
  room warms up by itself, about 0.4 °C per hour".
- **A chart of the water temperature:** "Water temperature by outdoor
  temperature" on the Home page, under Heating settings: the standard line
  (dashed), the line learned for your house (solid), the point of now and the
  water temperature at −10 °C.
- Everything it learns is kept over restarts and updates.

## Fixed

- Publishing a release: the publish step now waits for GitHub to list a
  release or a file it has just created, the likely reason the first attempt
  failed for rc.3 and rc.4 and needed a re-run, and its log names every step.

## Updating

From 1.0.0-rc.4, while someone is home. First install HA 1.0.0rc6 (HACS,
Pre-release on) and restart Home Assistant, then press Install on the E32's
Firmware entity. Then confirm the takeover again: a firmware change clears it,
and until then the E32 keeps only frost protection. Repair "Confirm again that
the E32 may control the boiler", or Rooms on the E32.

- Settings, rooms, programs, sensors, valves and everything it learned are
  kept. What it learns from the boiler, the house and free heat starts at once
  and fills in over the first days of heating, so the knowledge figure rises
  over those days.

## Limitations

A boiler that does not report the return temperature learns no absorbed heat;
everything else works. The boiler is listened to only while the E32 controls
it, and what it learned from the boiler is not in a settings backup (it is
learned again within days). rc.5 becomes 1.0.0 after 14 days unchanged; a code
change starts the 14 days again. Radiator valve control is not yet verified on
real valves. Behind an EMS adapter that leaves byte 7 of telegram 0x18 empty
(such as the Bosch EasyControl Adapter) the three-way valve position cannot be
seen. EMS Classic boilers only; EMS+ comes in 1.1. Writing boiler settings
comes after 1.0. Pairing Bluetooth sensors is done on the E32.
