"""Configure → Home → Heating and boiler → Boiler model (rc.3): the E32 Boiler page's choice from Home Assistant.

The list is the shipped boiler catalog (selectable models, the current one, "no boiler"), the
request is the page's own ``POST /config/boiler-display {"model": id}`` with its answer as the
read-back, and the boiler device is renamed at once through ems_devices.
"""
import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.open_thermostat import controller_link as link_module
from custom_components.open_thermostat import e32_boiler_model as module
from custom_components.open_thermostat.controller_link import ControllerLinkError
from custom_components.open_thermostat.ems_devices import MODEL_CHOSEN, products
from test_controller_link import BASE, Response, login_responses, setup
from nav_helpers import is_again  # noqa: E402
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32 as PlanE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


class FakeE32(PlanE32):
    def __init__(self, model="none"):
        super().__init__()
        self.model, self.posts, self.reads_model = model, [], 0
        self.answer = None
        self.fail = None

    def client(self, address):
        client = super().client(address)
        e32 = self

        async def display(model=None):
            if e32.fail:
                raise e32.fail
            if model is None:
                e32.reads_model += 1
                return {"model": e32.model}
            e32.posts.append((model, e32.logins))
            e32.model = model
            return e32.answer if e32.answer is not None else {"model": e32.model}
        client.async_boiler_display = display
        return client


async def model_form(manager, parent):
    await manager.hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    menu = await manager.async_configure(flow["flow_id"], {"next_step_id": "heating_boiler"})
    assert menu["menu_options"] == ["heating_boiler_limits", "comfort_care", "boiler_model", "back"]
    return await manager.async_configure(menu["flow_id"], {"next_step_id": "boiler_model"})


def choices(form):
    key = next(iter(form["data_schema"].schema))
    return form["data_schema"].schema[key].config["options"], key.default()


def test_the_choice_list_is_the_catalog_s_selectable_models_and_the_current_one():
    catalog = products()["boiler_models"]
    assert catalog["nefit-ecomline-classic-hrc-22h"]["selectable"] is True
    assert catalog["emsesp-product-206"]["selectable"] is False
    listed = [o["value"] for o in module.options("none", "en")]
    assert listed[0] == "none" and module.options("none", "nl")[0]["label"] == "Nog geen ketel gekozen"
    assert "nefit-ecomline-classic-hrc-22h" in listed and "emsesp-product-206" not in listed
    assert set(listed[1:]) == {k for k, v in catalog.items() if v["selectable"]}
    labels = [o["label"].casefold() for o in module.options("none", "en")[1:]]
    assert labels == sorted(labels)
    # A choice made earlier that a new choice may no longer pick stays shown.
    assert "emsesp-product-206" in [o["value"] for o in module.options("emsesp-product-206", "en")]


@pytest.mark.asyncio
async def test_the_boiler_model_is_saved_on_the_e32_and_names_the_boiler_at_once(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    renamed = []
    hass.data["open_thermostat"][parent.entry_id][MODEL_CHOSEN] = renamed.append
    form = await model_form(manager, parent)
    assert form["step_id"] == "boiler_model" and form["description_placeholders"]["current"] == "No boiler selected yet"
    options, default = choices(form)
    assert default == "none" and options[0] == {"value": "none", "label": "No boiler selected yet"}
    logins = e32.logins
    done = await manager.async_configure(form["flow_id"], {"model": "nefit-ecomline-classic-hrc-22h"})
    assert is_again(done)
    assert "Nefit Ecomline Classic HRC 22H" in done["description_placeholders"]["saved"]
    assert e32.posts == [("nefit-ecomline-classic-hrc-22h", logins + 1)]  # one sign-in for the change
    assert renamed == ["nefit-ecomline-classic-hrc-22h"]
    # The same model again: nothing is written.
    form = await model_form(manager, parent)
    assert choices(form)[1] == "nefit-ecomline-classic-hrc-22h"
    done = await manager.async_configure(form["flow_id"], {"model": "nefit-ecomline-classic-hrc-22h"})
    assert is_again(done, "unchanged") and len(e32.posts) == 1


@pytest.mark.asyncio
async def test_a_model_off_the_list_or_an_unconfirmed_save_is_never_claimed(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await model_form(manager, parent)
    with pytest.raises(InvalidData):
        await manager.async_configure(form["flow_id"], {"model": "emsesp-product-206"})  # not for a new choice
    assert e32.posts == []
    e32.answer = {"model": "none"}  # the E32 did not keep it
    done = await manager.async_configure(form["flow_id"], {"model": "buderus-gb162"})
    assert done["reason"] == "e32_settings_unconfirmed"
    e32.answer, e32.fail = None, ControllerLinkError("controller_settings_invalid")
    form = await model_form(manager, parent)
    assert form["type"] == FlowResultType.ABORT and form["reason"] == "e32_settings_unreachable"
    e32.fail = ControllerLinkError("controller_update_required")
    form = await model_form(manager, parent)
    assert form["reason"] == "e32_settings_update_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(400, "controller_settings_invalid"), (404, "controller_update_required"),
                                         (503, "controller_settings_unconfirmed")])
async def test_the_client_posts_exactly_the_model_and_names_refusals(monkeypatch, status, code):
    session, _ = setup(monkeypatch, *login_responses(), Response(raw=b"Invalid boiler model", status=status),
                       Response({"authenticated": False}))
    async with link_module.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(ControllerLinkError, match="^" + code + "$"):
            await client.async_boiler_display("buderus-gb162")
    sent = session.calls[2]
    assert sent[1] == BASE + "/config/boiler-display" and json.loads(sent[2]["data"]) == {"model": "buderus-gb162"}


def test_every_boiler_model_text_exists_in_every_language():
    files = {name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
             for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json")}
    assert files["strings.json"] == files["translations/en.json"]
    for name, data in files.items():
        step = data["options"]["step"]
        assert set(step["heating_boiler"]["menu_options"]) >= {"heating_boiler_limits", "boiler_model"}, name
        assert step["boiler_model"]["data"]["model"] and "{current}" in step["boiler_model"]["description"]
        assert data["options"]["error"]["boiler_model_invalid"]
        assert "{model}" in data["options"]["abort"]["boiler_model_saved"]
