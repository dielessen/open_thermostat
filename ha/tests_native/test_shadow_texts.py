"""Shadow mode is described honestly (since beta.19): the E32 sends nothing to the boiler, but Home
Assistant sets each room's setting device according to its week program."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"
WEB = ROOT / "data/html"
# Claims that were true before beta.19 and are wrong now.
WRONG = re.compile(r"Nothing is sent to valves|sends no valve|niets naar radiatorkranen|stuurt geen kranen|"
                   r"read and calculate only|alleen uitlezen en berekenen|Nic nie jest wysyłane do zaworów", re.I)


@pytest.mark.parametrize("filename, device", [("strings.json", "setting device"), ("translations/en.json", "setting device"),
                                              ("translations/nl.json", "instelapparaat"),
                                              ("translations/pl.json", "urządzeniu nastawczym")])
def test_the_shadow_step_says_ha_sets_the_setting_devices(filename, device):
    text = (COMPONENT / filename).read_text(encoding="utf-8")
    assert not WRONG.search(text)
    shadow = json.loads(text)["config"]["step"]["shadow"]["description"]
    assert device in shadow and ("boiler" in shadow or "ketel" in shadow or "kotła" in shadow)


def test_the_e32_settings_page_says_the_same_in_english_and_dutch():
    for name in ("network.html", "ui-messages-pages.js", "ui-messages.js", *(p.name for p in WEB.glob("*.html"))):
        assert not WRONG.search((WEB / name).read_text(encoding="utf-8")), name
    page = (WEB / "network.html").read_text(encoding="utf-8")
    assert "sends nothing to the boiler" in page and "setting device (radiator valve, tado or number helper)" in page
    messages = (WEB / "ui-messages-pages.js").read_text(encoding="utf-8")
    assert "stuurt niets naar de ketel" in messages and "instelapparaat van elke ruimte" in messages
