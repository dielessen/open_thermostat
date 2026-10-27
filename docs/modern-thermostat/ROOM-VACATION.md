# Vacation end date in the room editor

Prepared for HA 0.4.0b4 with the beta.6 development bundle. No installation or
live device command was performed during this work.

Save and confirm the room's comfort profile first. In **Comfort and presence →
Vacation**, choose an end date/time in the displayed Home Assistant time zone,
then press **Start or change vacation**. The existing away target applies until
that UTC instant. **Return to programme** explicitly selects the automatic mode.
Saving ordinary room settings does not start vacation.

The end must be in the future and at most 366 days away. Home Assistant resolves
the entered civil time using its own IANA time zone. The browser's time zone is
not used. A daylight-saving gap is rejected instead of shifting the time. A
repeated clock time presents both explicit UTC offsets; choose one and press
Start again. The choice is checked again immediately before the normal command.

Date resolution is an admin-only, read-only WebSocket request. It checks the
current installation, room, configuration token, time zone and canonical climate
entity. The command then goes through the existing `open_thermostat.set_comfort`
entity service with the expected room scope. The service checks that scope before
dispatch and after awaiting the result. Renames, reused entity IDs, reloads,
changed settings or a different runtime cannot turn an old request into another
room's command. Existing ordinary service calls remain compatible.

There is one UI operation at a time. Unsaved room settings and unconfirmed plan
application block the action. Leaving/hiding the page or changing scope while
date resolution waits prevents subsequent dispatch. Date reads have a ten-second
UI deadline; a late result cannot send a command. Service waits have a
fifteen-second UI deadline. A timeout after dispatch is uncertain, not proof that
nothing happened. Submitted commands are not aborted or replayed by the editor;
the existing wire owner retains its bounded identical-byte retries.

The editor reports acceptance separately from actual room state. The displayed
mode and vacation end come from the same canonical climate entity, including a
backend-formatted local end time and explicit offset. A service return does not
optimistically start or clear vacation. Unconfirmed commands require inspection
of current status and an explicit reload before another start attempt.

Vacation remains the core's existing finite, session-local mode. A controller
restart, reconnect or room reload clears that selection. It is not saved as a
new persistent programme and is never silently restored or resent. Physical
outputs and protection remain governed by the existing independent policies.

Software tests cover Amsterdam/London folds, a Lord Howe half-hour transition,
gaps, invalid dates and UTC bounds; real HA service registration with the actual
C++ receiver; pre/post-dispatch owner changes; and English/Dutch browser flows
at 1280, 390 and 320 pixels with a Los Angeles browser time zone. Test services
and trackers are isolated fixtures. Physical holiday behavior, source reporting
and time-loss/reconnect acceptance remain separate work.
