# Public boiler metadata

`catalog-v1.json` is the source of truth for presentation selections. It records
pinned upstream references. EMS-ESP listings are not OpenThermostat driver or
control qualification. Product families and marketing groups may overlap.

Run `python3 scripts/generate_boiler_catalog.py` after reviewing changes, and
`python3 scripts/generate_boiler_catalog.py --check` before release. Only compact
names/IDs/image links and a neutral SVG fallback are embedded; the full catalog and product images stay outside
`data/html`. Do not add executable code, credentials, local telemetry or implicit
control defaults to catalog entries.

Original model images are referenced directly from public manufacturer/specialist
hosts. `image_provenance` records the source page, publisher, depicted model,
scope and hash/date observed during review; it does not assert redistribution
rights. The browser shows a source link. No third-party image copies are shipped.

`images/nefit-ecomline.svg` remains an archived project illustration and a mock
browser-test fixture. It is no longer selected by the catalog. Ecomline Classic
HRC22H has no verified original model photo yet. Ambiguous multi-model groups
keep null images; never reuse one product's photo for a different product.
For a selected model without a photo, or if its public image fails to load,
`boiler-display.js` renders an original, unbranded generic boiler illustration.
The fallback is embedded locally and works offline on both Home and My boiler.
An unavailable product image's source credit is hidden with that image.
No boiler image is shown when no model is selected or the selection is unknown.

Functional control profiles are not implemented by this catalog. See
[the design and acceptance boundaries](../../docs/modern-thermostat/KETELCATALOGUS.nl.md).
