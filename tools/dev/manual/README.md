# Installation manual as a PDF (Dutch)

`make_pdf.py` writes the Dutch installation manual: flashing the gateway, the MQTT link, the Home Assistant
integration, the rooms, the boiler test and the first weeks. The PDF is generated output. Write it to `out/`
(ignored by Git) and attach it to the release by hand; never commit it.

## Build it

The generator needs `reportlab`. In WSL:

```bash
python3 -m venv ~/venvs/pdf && ~/venvs/pdf/bin/pip install reportlab    # once
~/venvs/pdf/bin/python tools/dev/manual/make_pdf.py out/OpenThermostat-Handleiding.pdf
```

Fonts: it uses Arial and Consolas from `C:\Windows\Fonts` (reachable as `/mnt/c/Windows/Fonts` in WSL) and falls
back to DejaVu. `--fonts DIR` names another folder, tried first. If a character is missing in the chosen fonts the
build stops and lists it, instead of printing empty boxes.

To look at a page without a PDF viewer, `pypdfium2` can render it:

```bash
~/venvs/pdf/bin/pip install pypdfium2
~/venvs/pdf/bin/python -c "import pypdfium2 as p; p.PdfDocument('out/OpenThermostat-Handleiding.pdf')[3].render(scale=1.3).to_pil().save('out/page4.png')"
```

## At each release

1. Set `E32_TAG`, `E32_VERSION` and `HA_VERSION` at the top of `make_pdf.py` to the release pair (cover, firmware
   example, HACS step and footer use them). They are not read from the tree, so a release does not change them by itself.
2. Names that Home Assistant shows are written through `ui(...)` and `named(...)`. Run
   `python3 -I -m unittest discover -s tools/dev -p "test_manual_labels.py"`: it looks every such name up in
   `translations/nl.json` and in the Dutch dashboard texts, so a renamed menu fails there. Names of the E32's own
   pages and of Home Assistant itself (Settings, Repairs, HACS) are plain `<b>...</b>` and are not checked.
3. Build the PDF, page through it, and compare the E32 pages it describes with the release.

The text follows `docs/INSTALL.md` and `docs/USER-GUIDE.md`; change the three together.
