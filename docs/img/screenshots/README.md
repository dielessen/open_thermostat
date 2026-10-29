# Interface screenshots

Images used on the GitHub project page.

- **Beta.18 (29 October 2026):** the shipped E32 beta.18 web interface, rendered locally
  in headless Chromium with fictitious demonstration data (mocked HTTP responses). They are
  not captures of a live device and contain no data from a real installation.
  - `e32-overview-beta18.png`: Overview with rooms, trend lines, boiler request and boiler
    values; `e32-overview-phone-beta18.png` shows the same page at phone width (390 px).
  - `e32-rooms-beta18.png` and `e32-rooms-dark-beta18.png`: Rooms page in the light and dark
    theme, read-only because the rooms are managed in Home Assistant, with the
    "Edit here anyway" option, the shadow-mode comparison and the boiler flow limits.
  - `e32-boiler-beta18.png`: Boiler page with current values, burner starts, hot water today
    and all received boiler entities (setting changes are read-only in this firmware).
  - `e32-sensors-beta18.png`: Sensors page with nearby and paired Bluetooth thermometers.
  - `e32-about-beta18.png`: System → About with the password card.
- `ha-room-dev24.png`: the shipped Home Assistant frontend rendered locally with example
  data and an explicit demonstration label; not a live HA capture and no proof of physical
  control.
- `e32-dashboard-alpha18.png`: an actual capture of an installed E32 (alpha.18), cropped to
  the product panel.
- `e32-keteltest-alpha18.png`: actual passive reception diagnostics on the same E32
  (alpha.18). Stale or unreliable fields stay visible; transmitting is blocked.

The screenshots contain no browser address bar, credentials, private sidebar or other
Home Assistant dashboards. Dimensions, versions and hashes are listed in
[screenshots.json](screenshots.json).
