"""The Learning view looks like the owner's sketch (rc.5, P19: Leren.dc.html and Leren-desktop.dc.html).

Seven sections in the sketch's order and with its headings: what the E32 knows (the ring), your boiler (one sentence
behind a flame), water temperature by outdoor temperature (the curve, under its own heading), yesterday in figures,
what stood out yesterday (an information icon per line), the free heat per room (a sun per line) and Smart warm-up and
weather compensation (the switches and the water temperature in hard frost as rows, no chart). After them the rest of
the view in its order: what the thermostat learned (three sections) and who controls the boiler. Each section hides
as a whole while it has nothing to show, so no heading stands over nothing; on a wide screen yesterday spans two rows,
so the curve and what stood out stack in one column beside it, as the sketch's two columns.
"""
import pytest
from homeassistant.helpers.template import Template

from custom_components.open_thermostat.dashboard import TEXT, _settings_section
from test_dashboard_redesign import shown
from test_dashboard_tidy import live

HEADINGS = {
    "en": ["What the E32 knows", "Your boiler", "Water temperature by outdoor temperature", "Yesterday in figures",
           "Noticed", "Free heat", "Smart warm-up and weather compensation",
           "What the thermostat has learned", "House and boiler", "What it changed by itself", "Who controls the boiler"],
    "nl": ["Wat de E32 weet", "Je ketel", "Watertemperatuur bij buitentemperatuur", "Gisteren in cijfers",
           "Opgevallen", "Gratis warmte", "Slim opwarmen en weerafhankelijke regeling",
           "Wat de thermostaat heeft geleerd", "Huis en ketel", "Wat hij zelf heeft aangepast", "Wie regelt de ketel"],
    "pl": ["Co wie E32", "Twój kocioł", "Temperatura wody a temperatura zewnętrzna", "Wczoraj w liczbach",
           "Spostrzeżenia", "Darmowe ciepło", "Inteligentne nagrzewanie i sterowanie pogodowe",
           "Czego nauczył się termostat", "Dom i kocioł", "Co zmienił sam", "Kto steruje kotłem"]}
ICONS = ["mdi:home-analytics", "mdi:water-boiler", "mdi:chart-bell-curve-cumulative", "mdi:scoreboard-outline",
         "mdi:information-outline", "mdi:weather-sunny", "mdi:cog-outline",
         "mdi:school-outline", "mdi:home-thermometer-outline", "mdi:history", "mdi:water-boiler"]
INSIGHTS = [{"text": "Yesterday used 12 % less gas per degree of cold than usual.",
             "meaning": "Sun, a cooler setting or fewer hours at home can cause this."},
            {"text": "Yesterday Slaapkamer warmed up 40 % more slowly than usual.", "meaning": None}]
# Two rooms with free heat (learned_overview.free_heat_lines), one of them without a line on what it means.
FREE_HEAT = [{"name": "Woonkamer", "text": "'s Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of "
              "mensen).", "meaning": "Slim opwarmen houdt hier rekening mee als het op dat moment van de dag opwarmt."},
             {"name": "Keuken", "text": "'s Avonds warmt deze ruimte vanzelf op, ongeveer 0,3 °C per uur (zon, koken of "
              "mensen).", "meaning": ""}]


def learning_view(hass, language="en"):
    config, rooms, sensors, hub, fields, flow = live(hass, language)
    return next(v for v in config["views"] if v["path"] == "learned"), hub, flow


def render(hass, card):
    return Template(card["content"], hass).async_render(parse_result=False)


def placed(sections, columns):
    """Where Home Assistant's sections view puts each section: a CSS grid of ``columns`` columns filled in order with
    "grid-auto-flow: dense" (each section at the first place, row by row, where its column span and row span fit), as
    the view's own styles do (hui-sections-view: .content.dense, grid-column/grid-row span). [(row, column)]."""
    taken, spots = set(), []
    for section in sections:
        span, rows = min(section.get("column_span", 1), columns), section.get("row_span", 1)
        row = 0
        while True:
            fits = [column for column in range(columns - span + 1)
                    if not {(row + r, column + c) for r in range(rows) for c in range(span)} & taken]
            if fits:
                break
            row += 1
        taken |= {(row + r, fits[0] + c) for r in range(rows) for c in range(span)}
        spots.append((row, fits[0]))
    return spots


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_the_seven_sections_of_the_sketch_come_first_in_its_order(hass, language):
    learning, *_ = learning_view(hass, language)
    assert [s["cards"][0]["heading"] for s in learning["sections"]] == HEADINGS[language]
    # One icon per concept (ICONS of dashboard.py), every heading a title as the rest of the dashboard.
    assert [s["cards"][0].get("icon") for s in learning["sections"]] == ICONS
    assert {s["cards"][0]["heading_style"] for s in learning["sections"]} == {"title"}


@pytest.mark.asyncio
async def test_each_section_of_the_sketch_hides_while_it_has_nothing_to_show(hass):
    learning, hub, flow = learning_view(hass)
    knows, boiler, curve, yesterday, noticed, free, settings = learning["sections"][:7]
    # The ring, the boiler's sentence and the curve: while their sensor has a value.
    for section, entity in ((knows, hub["knowledge"]), (boiler, hub["boiler_response"]), (curve, flow["curve"])):
        assert not shown(section["visibility"], {entity: "unknown"}) and not shown(section["visibility"], {})
        assert shown(section["visibility"], {entity: "62"})
    # Yesterday in figures (its own rules, P15): hidden while none of its figures has a value.
    assert yesterday["visibility"] and not shown(yesterday["visibility"], {})
    # What stood out and the free heat: lists on the learned overview, read as Home Assistant 2026.10 reads an attribute
    # in a state condition (text: an empty list is "", a missing one "unknown").
    for section, attribute in ((noticed, "insights"), (free, "free_heat")):
        assert section["visibility"] == [{"condition": "state", "entity": hub["learned_overview"], "attribute": attribute,
                                          "state_not": ["unavailable", "unknown", ""]}]
        key = (hub["learned_overview"], attribute)
        assert not shown(section["visibility"], {key: ""}) and not shown(section["visibility"], {})
        assert shown(section["visibility"], {key: "[object Object]"})
        # One card that always has its lines while the section shows (no empty card that hides itself).
        assert [card["type"] for card in section["cards"]] == ["heading", "markdown"]
        assert not any("visibility" in card or "show_empty" in card for card in section["cards"])
    # The settings: rows of the E32's own switches, always there to change; no chart any more.
    assert "visibility" not in settings and [card["type"] for card in settings["cards"]] == ["heading", "entities"]
    assert all(card.get("visibility") is None for card in settings["cards"])


@pytest.mark.asyncio
async def test_noticed_says_each_insight_behind_an_information_icon(hass):
    learning, hub, _ = learning_view(hass)
    card = learning["sections"][4]["cards"][1]
    hass.states.async_set(hub["learned_overview"], "x", {"insights": INSIGHTS})
    icon = '<font color="#039be5"><ha-icon icon="mdi:information-outline"></ha-icon></font>'
    assert render(hass, card) == (
        f"{icon} Yesterday used 12 % less gas per degree of cold than usual. Sun, a cooler setting or fewer hours at home "
        f"can cause this.\n\n{icon} Yesterday Slaapkamer warmed up 40 % more slowly than usual.\n\n"
        "*Yesterday is compared with your house's own usual days; that is information and changes nothing.*")


@pytest.mark.asyncio
async def test_free_heat_names_each_room_behind_a_sun(hass):
    learning, hub, _ = learning_view(hass, "nl")
    card = learning["sections"][5]["cards"][1]
    hass.states.async_set(hub["learned_overview"], "x", {"free_heat": FREE_HEAT})
    sun = '<font color="#ffc107"><ha-icon icon="mdi:weather-sunny"></ha-icon></font>'
    assert render(hass, card) == (
        f"{sun} **Woonkamer** · 's Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of mensen). "
        "Slim opwarmen houdt hier rekening mee als het op dat moment van de dag opwarmt.\n\n"
        f"{sun} **Keuken** · 's Avonds warmt deze ruimte vanzelf op, ongeveer 0,3 °C per uur (zon, koken of mensen).")


@pytest.mark.asyncio
async def test_the_settings_are_rows_of_switches_and_the_water_temperature_in_hard_frost(hass):
    learning, hub, flow = learning_view(hass)
    heading, rows = learning["sections"][6]["cards"]
    assert rows == {"type": "entities", "entities": [
        {"entity": flow["apply_learned"], "name": "Smart warm-up", "icon": "mdi:school-outline"},
        {"entity": flow["weather_curve"], "name": "Weather compensation", "icon": "mdi:sun-thermometer"},
        {"entity": flow["curve_design_flow_c"], "name": "Water temperature in hard frost (−10 °C)",
         "icon": "mdi:thermometer-lines"}]}
    # With an E32 room plan, the rooms editor and the week program under the rows, as before.
    section = _settings_section(TEXT["nl"], flow, "/config/integrations/integration/open_thermostat", "/x/week-program")
    assert [(c.get("heading"), (c.get("tap_action") or {}).get("navigation_path")) for c in section["cards"][2:]] == [
        ("Ruimtes instellen", "/config/integrations/integration/open_thermostat"), ("Weekprogramma", "/x/week-program")]
    # Firmware without the switches (what sets the water temperature is no setting): no section.
    assert _settings_section(TEXT["en"], {"source": flow["source"]}) is None
    assert _settings_section(TEXT["en"], {}) is None


@pytest.mark.asyncio
async def test_on_a_wide_screen_the_sketch_has_two_columns(hass):
    """The sketch's desktop: the curve with what stood out and the free heat under it in one column; your boiler,
    yesterday and the settings in the other. Home Assistant places the sections in the phone's order, so the ring,
    first on the phone, takes the top of the curve's column. Only yesterday spans two rows; nothing spans columns."""
    learning, *_ = learning_view(hass)
    assert (learning["type"], learning["max_columns"], learning["dense_section_placement"]) == ("sections", 2, True)
    spans = [(s.get("column_span", 1), s.get("row_span", 1)) for s in learning["sections"]]
    assert spans == [(1, 1)] * 3 + [(1, 2)] + [(1, 1)] * 7
    knows, boiler, curve, yesterday, noticed, free, settings = placed(learning["sections"], 2)[:7]
    assert [spot[1] for spot in (knows, curve, noticed, free)] == [0, 0, 0, 0]
    assert [spot[1] for spot in (boiler, yesterday, settings)] == [1, 1, 1]
    assert curve[0] < noticed[0] < free[0] and boiler[0] < yesterday[0] < settings[0]
    # Without what stood out (no insights yesterday), the free heat moves up under the curve.
    without = [s for s in learning["sections"] if s["cards"][0]["heading"] != "Noticed"]
    assert placed(without, 2)[4] == (2, 0)
    # A phone stacks every section in the sketch's order.
    assert placed(learning["sections"], 1) == [(row, 0) for row in (0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11)]
