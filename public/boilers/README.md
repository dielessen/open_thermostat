# Public boiler metadata

`catalog-v1.json` is the source of truth for presentation selections. It records
pinned upstream references. EMS-ESP listings are not OpenThermostat driver or
control qualification. Product families and marketing groups may overlap.

Run `python3 scripts/generate_boiler_catalog.py` after reviewing changes, and
`python3 scripts/generate_boiler_catalog.py --check` before release. Only compact
names/IDs/image links are embedded; the full catalog and images stay outside
`data/html`. Do not add executable code, credentials, local telemetry or implicit
control defaults to catalog entries.

`images/nefit-ecomline.svg` is the existing project illustration, relocated without
changing its bytes. It is not a manufacturer photograph. Other image fields are
null pending an appropriate image and documented provenance/permission. Browser
images are optional; failure must not affect device operation.

Functional control profiles are not implemented by this catalog. See
[the design and acceptance boundaries](../../docs/modern-thermostat/KETELCATALOGUS.nl.md).
