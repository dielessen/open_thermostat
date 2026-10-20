# E32 V2 alpha.5 — Normal web login and independent browser sessions

Experimental bench-test prerelease. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This release is not approved for heating.**

- The local E32 web interface now opens an ordinary English sign-in page instead
  of the browser's HTTP authentication dialog. Existing configured credentials
  and stored room/program/network settings are unchanged.
- Desktop and mobile can keep independent sessions. The browser stays signed in
  for up to seven days on the same running boot; a device restart requires one
  new form login. Four independent browsers can be active without evicting each
  other; signing out affects only that browser.
- Native cookies are host-only, HttpOnly and SameSite=Strict. Configuration and
  upload mutations also require a session-specific CSRF proof. No session tokens
  are written to NVS, no extra service is introduced and failed writes are never
  automatically replayed.
- The existing physical-interface-only setup exception, firmware/update recovery,
  HA-managed writer fences, method/origin checks and output/TX locks remain.
- The version endpoint now reports the actual embedded source commit and UI hash.
- The earlier Digest implementation's shared challenge nonce can invalidate
  another pending challenge. That mechanism was verified in source; the precise
  mobile incident was not captured and is not claimed as proven root cause.

## Update

Use the existing device updater to select this compatible testrelease, or upload
only `firmware.bin` from this release. The web interface is embedded in the app.
**Do not erase flash, install the factory image or upload SPIFFS for this update.**
Existing alpha.4 schedules its own restart after a successful app update; earlier
versions may still need one manual restart. No automatic installation is performed
by publishing this release.

Software/build and simulated-browser tests are not real phone/desktop acceptance.
After updating, verify both browsers, settings retention and independent logout.
Keep the device disconnected from EMS and retain the previous immutable release.

Normal local HTTP is unchanged; this release does not add TLS. Use the device on
your trusted local network. Remote API clients must migrate from Digest to the
cookie/CSRF API documented in AUTH-LOGIN.md. HA MQTT contracts are unchanged.
