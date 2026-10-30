"""The dashboard cards' JavaScript is registered at domain level, once, whatever the installation's state.

Live problem (HA 0.4.0b11): the "Week program" view showed only "Configuration error"
when the card module was registered late (only from the dashboard start of a loaded
product entry). Now async_setup registers it before any entry; the card waits for the
E32 itself and explains a stale page instead of failing.
"""
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import frontend
from homeassistant.components.frontend import UrlManager
from homeassistant.config_entries import ConfigEntryDisabler

import custom_components.open_thermostat as integration
from custom_components.open_thermostat import e32_week, week_planner
from custom_components.open_thermostat.e32_week import CARD_URL, EDITOR_URL, WeekError, read_week
from test_e32_room_flow import product
from test_room_plan import FakeE32

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"
CARD = (COMPONENT / "frontend/e32-week-card.js").read_text(encoding="utf-8")


def browser_side(hass):
    """What HA's frontend component and http server provide: the module URL list and static routes."""
    events = []
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = UrlManager(lambda change, url: events.append((change, url)), [])
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    return events


def modules(hass):
    return set(hass.data[frontend.DATA_EXTRA_MODULE_URL].urls)


@pytest.mark.asyncio
async def test_async_setup_registers_the_cards_once_without_any_installation(hass):
    events = browser_side(hass)
    assert hass.config_entries.async_entries("open_thermostat") == []
    assert await integration.async_setup(hass, {}) is True
    # The card and the room editor modules, before any entry or dashboard exists.
    assert modules(hass) == {CARD_URL, week_planner.URL}
    served = {path.url_path for call in hass.http.async_register_static_paths.await_args_list for path in call.args[0]}
    assert {CARD_URL, EDITOR_URL, week_planner.URL, *week_planner.LEGACY_URLS} <= served
    handlers = hass.data["websocket_api"]
    assert {"open_thermostat/e32_week/get", "open_thermostat/e32_week/save", "open_thermostat/week/get"} <= set(handlers)
    # A dashboard start later (or a second installation) adds nothing twice.
    await week_planner.async_setup_planner(hass)
    await week_planner.async_setup_planner(hass)
    assert events == [("added", CARD_URL), ("added", week_planner.URL)]
    assert hass.http.async_register_static_paths.await_count == 5  # one route per URL, once


@pytest.mark.asyncio
async def test_a_module_already_listed_is_not_announced_again(hass):
    events = browser_side(hass)
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = UrlManager(lambda change, url: events.append((change, url)), [CARD_URL])
    await week_planner.async_setup_planner(hass)
    assert events == [("added", week_planner.URL)] and modules(hass) == {CARD_URL, week_planner.URL}


@pytest.mark.asyncio
async def test_a_failing_card_setup_never_blocks_the_installations_and_is_retried(hass, monkeypatch, caplog):
    events = browser_side(hass)
    # The first two files are served, the third fails: a retry serves only what is missing.
    hass.http.async_register_static_paths = AsyncMock(side_effect=[None, None, None, RuntimeError("busy"), None, None])
    assert await integration.async_setup(hass, {}) is True
    assert "dashboard cards could not be registered" in caplog.text and modules(hass) == set()
    await week_planner.async_setup_planner(hass)  # the dashboard start tries again
    assert modules(hass) == {CARD_URL, week_planner.URL} and len(events) == 2
    urls = [call.args[0][0].url_path for call in hass.http.async_register_static_paths.await_args_list]
    assert urls == [week_planner.URL, *week_planner.LEGACY_URLS, CARD_URL, CARD_URL, EDITOR_URL], "no duplicate route"
    await week_planner.async_setup_planner(hass)
    assert hass.http.async_register_static_paths.await_count == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["planner", "store"])
async def test_a_failing_optional_dashboard_never_fails_the_installation(hass, monkeypatch, caplog, failure):
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from custom_components.open_thermostat import dashboard as module
    parent, _ = product(hass, FakeE32())
    hass.data[LOVELACE_DATA] = SimpleNamespace(dashboards={})
    if failure == "planner":
        monkeypatch.setattr(week_planner, "async_setup_planner", AsyncMock(side_effect=RuntimeError("no http")))
    else:
        monkeypatch.setattr(week_planner, "async_setup_planner", AsyncMock())
        monkeypatch.setattr(module.LovelaceStorage, "async_save", AsyncMock(side_effect=OSError("disk full")))
    board = module.RoomDashboard(hass, "fixture", parent.entry_id)
    await board.async_start()  # no exception: the entry's setup goes on
    assert "dashboard could not be started" in caplog.text
    assert hass.data[LOVELACE_DATA].dashboards == {} and board._store is None
    await board.async_stop()


@pytest.mark.asyncio
async def test_removing_the_last_installation_removes_the_modules_and_a_new_one_adds_them_again(hass):
    events = browser_side(hass)
    await integration.async_setup(hass, {})
    first, _ = product(hass, FakeE32())
    second = SimpleNamespace(entry_id="other", domain="open_thermostat")
    hass.config_entries.async_entries = lambda domain=None: [first, second]
    await integration.async_remove_entry(hass, first)
    assert modules(hass) == {CARD_URL, week_planner.URL}, "another installation still uses the cards"
    hass.config_entries.async_entries = lambda domain=None: [second]
    await integration.async_remove_entry(hass, second)
    assert modules(hass) == set()
    assert events[-2:] == [("removed", CARD_URL), ("removed", week_planner.URL)]
    await integration.async_remove_entry(hass, second)  # nothing left to remove: no error, no event
    assert len(events) == 4
    # A new installation's dashboard start brings them back (HA keeps the static files served).
    await week_planner.async_setup_planner(hass)
    assert modules(hass) == {CARD_URL, week_planner.URL}


@pytest.mark.asyncio
async def test_the_card_waits_while_the_installation_is_not_loaded_and_names_a_disabled_one(hass):
    e32 = FakeE32()
    parent, hub = product(hass, e32)
    state = hass.data["open_thermostat"].pop(parent.entry_id)
    with pytest.raises(WeekError, match="^not_ready$"):
        await read_week(hass, parent.entry_id)
    hass.data["open_thermostat"][parent.entry_id] = state
    hub.plan = None
    with pytest.raises(WeekError, match="^not_ready$"):
        await read_week(hass, parent.entry_id)
    object.__setattr__(parent, "disabled_by", ConfigEntryDisabler.USER)
    with pytest.raises(WeekError, match="^disabled$"):
        await read_week(hass, parent.entry_id)
    with pytest.raises(WeekError, match="^unavailable$"):
        await read_week(hass, "no-such-entry")


@pytest.mark.asyncio
async def test_a_busy_e32_and_a_failed_setup_get_their_own_codes(hass, monkeypatch):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import HomeAssistantError
    from custom_components.open_thermostat.room_plan import SIGN_IN_ERRORS
    assert set(SIGN_IN_ERRORS.values()) <= set(e32_week.FAILURES), "every sign-in failure has a card code"
    parent, hub = product(hass, FakeE32())
    for key, code in (("e32_session_capacity", "session_capacity"), ("e32_try_again_later", "try_again_later")):
        monkeypatch.setattr(hub.plan, "async_read", AsyncMock(side_effect=HomeAssistantError(
            translation_domain="open_thermostat", translation_key=key)))
        # A read from the E32 itself (the card's Reload, or no current plan in HA).
        with pytest.raises(WeekError, match=f"^{code}$"):
            await read_week(hass, parent.entry_id, fresh=True)
    object.__setattr__(parent, "state", ConfigEntryState.SETUP_ERROR)
    with pytest.raises(WeekError, match="^setup_error$"):
        await read_week(hass, parent.entry_id)


@pytest.mark.asyncio
async def test_an_installation_without_the_dashboard_brings_the_cards_back(hass):
    events = browser_side(hass)
    await integration.async_setup(hass, {})
    week_planner.async_remove_card_modules(hass)  # the last installation was removed
    assert modules(hass) == set()
    await week_planner.async_ensure_cards(hass)   # a new E32 installation's setup, no dashboard
    assert modules(hass) == {CARD_URL, week_planner.URL}
    await week_planner.async_ensure_cards(hass)   # idempotent
    assert events.count(("added", CARD_URL)) == 2
    source = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert "await async_ensure_cards(hass)" in source
    hass.http = None
    await week_planner.async_ensure_cards(hass)   # no web server: nothing, no error


@pytest.mark.asyncio
async def test_the_websocket_answer_names_the_card_module_the_backend_serves(hass):
    parent, _ = product(hass, FakeE32())
    sent = []
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=True),
                                 send_result=lambda i, r: sent.append(r), send_error=lambda i, c, m: sent.append(c))
    e32_week.ws_week_get(hass, connection, {"id": 1, "type": "open_thermostat/e32_week/get", "entry_id": parent.entry_id})
    await hass.async_block_till_done()
    assert sent[-1]["card_url"] == CARD_URL and sent[-1]["rooms"][0]["id"] == "woonkamer"


def test_the_card_explains_every_state_in_english_and_dutch_instead_of_failing():
    for language in ("en", "nl"):
        block = re.search(language + r": \{title:(.*?)errors: \{(.*?)\}\}", CARD, re.S)
        texts, errors = set(re.findall(r"(\w+): '", block[1])), set(re.findall(r"(\w+): '", block[2]))
        assert {"waiting", "retrying", "outdated"} <= texts, language
        assert {"not_ready", "disabled", "unknown_command", "editor", "unreachable", "session_capacity",
                "try_again_later", "setup_error", "gave_up"} <= errors, language
    # The reload hint names the key to press; the card retries by itself while it waits.
    assert CARD.count("Ctrl+F5") >= 6
    assert "RETRY = new Set(['not_ready', 'unreachable', 'session_capacity', 'try_again_later'])" in CARD
    assert "const GIVE_UP_MS = 5 * 60000;" in CARD  # then it says so instead of "still starting" forever
    # The URL the editor is imported from is the one the backend serves.
    assert f"const EDITOR = '{EDITOR_URL}';" in CARD


def test_the_asset_urls_follow_the_integration_version():
    import json
    version = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]
    # Every module the browser loads from this integration carries the version: no stale cached module.
    for url in (CARD_URL, EDITOR_URL, week_planner.URL):
        assert url.endswith(f"-{version}.js"), url
    assert f"const EDITOR = '{EDITOR_URL}';" in CARD
    served = {name for name in re.findall(r'"(?:frontend/)?([\w-]+\.js)"', (COMPONENT / "week_planner.py").read_text(encoding="utf-8"))}
    assert served == {path.name for path in (COMPONENT / "frontend").glob("*.js")}, "every frontend file is served"
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert {"frontend", "http"} <= set(manifest["dependencies"])


def test_every_card_element_survives_a_replaced_registry():
    """A HACS card's scoped-registry polyfill may replace customElements after our modules ran: every
    OpenThermostat element goes through ensureDefined, which defines it again (browser case 6 in
    test/week-editor-browser.cjs)."""
    for name in ("e32-week-card.js", "week-planner.js"):
        source = (COMPONENT / "frontend" / name).read_text(encoding="utf-8")
        assert source.count("customElements.define(") == 1, name  # only inside ensureDefined
        assert "const ensureDefined = (name, cls) =>" in source and "'location-changed', check" in source, name
    planner = (COMPONENT / "frontend/week-planner.js").read_text(encoding="utf-8")
    from custom_components.open_thermostat.week_planner import ROOM_CARD_TYPE
    assert f"ensureDefined('{ROOM_CARD_TYPE.removeprefix('custom:')}'" in planner
    assert "ensureDefined('openthermostat-e32-week', OpenThermostatE32Week);" in CARD
