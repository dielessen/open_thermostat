"""What the E32 knows, how the boiler responds and what stood out yesterday (E32 rc.5).

The E32 sends ``fw/telemetry/insight`` (retained, every 5 minutes), which the heating hub merges into
the summary as ``insight`` (heating_link.decode_insight):

- ``knowledge``: {"pct": 0..100, "missing": [keys], "more": n}: how much of what it needs the E32 has
  learned (how fast each room warms up and cools down, the morning check, Weather compensation, the
  boiler's minimum and response, the house) and what is still missing. Keys: ``warmup:<room>``,
  ``cooling:<room>``, ``arrival:<room>``, ``curve``, ``boiler_minimum``, ``boiler_response``, ``house``;
  at most 8, ``more`` counts the rest (a key this version does not know counts there too);
- ``boiler``: the boiler's response (BoilerResponse): ``held`` (today's held temperatures), ``rest_s``
  (the boiler's own rest after one), ``ceiling_c`` (the most the E32 asks at this outdoor temperature),
  ``absorbed_kw``, ``kw_per_k`` and ``state`` (collecting, learned, no_return, not_driving). The flow
  document (fw/telemetry/flow) carries the same object; the insight's wins;
- ``house``: the house model (heat loss, emitter output, the curve it implies); not shown on its own;
- ``insights``: yesterday against the house's own usual days, at most 4: {"kind", "pct", "room"?}.

On the product device, no new device: the sensor "Knowledge" (the percentage; the missing items as
sentences and ``more``) and the sensor "Boiler response" (its state; held today, rest, ceiling, absorbed
kW, kW per K and one sentence). Both read ``unknown`` while the E32 sends no insight (firmware before
rc.5, or none for 16 minutes while it is heard) and are unavailable while the E32 is silent.

Each insight is a persistent notification (information, never a Repairs item): replaced when it
changes, dismissed when it is gone. One the owner dismissed stays dismissed until it changes, also
over a restart of Home Assistant (a small store per installation). The texts follow the Home Assistant
language (English, Dutch or Polish), as the learned overview does; the E32 Home page says the same.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import callback

from .const import DOMAIN
from .heating_link import ROOM_ID, HubEntity, label, number
from .learned_overview import duration, language, number as decimal

# Missing keys: the house-wide ones, and the per-room ones as "<kind>:<room id>".
HOUSE_KEYS = ("curve", "boiler_minimum", "boiler_response", "house")
ROOM_KEYS = ("warmup", "cooling", "arrival")
INSIGHT_KINDS = ("gas_per_dd_up", "gas_per_dd_down", "starts_up", "hours_per_dd_up", "warmup_slower")
MAX_INSIGHTS = 8  # the E32 sends at most 4
BOILER_STATES = ["collecting", "learned", "no_return", "not_driving"]
# hass.data: per installation, the notifications this Home Assistant run shows (kept over an entry reload).
_SHOWN = DOMAIN + "_insight_shown"
_STORE_VERSION = 1

TEXT = {
    "en": {
        "missing.warmup": "It still has to see how fast {room} warms up.",
        "missing.cooling": "It still has to see how fast {room} cools down.",
        "missing.arrival": "It still has to check whether {room} is warm on time.",
        "missing.curve": "It is still learning how much warmer the water must be when it gets colder outside.",
        "missing.boiler_minimum": "It is still finding out from which water temperature your boiler starts heating.",
        "missing.boiler_response": "It is still listening to how your boiler holds its temperature.",
        "missing.house": "It is still working out how fast your house loses heat.",
        "boiler.learned_both": "Your boiler rests about {rest} each time it reaches its temperature; the E32 asks at most "
                               "{ceiling} °C now, so it starts less often.",
        "boiler.learned_ceiling": "The E32 asks your boiler at most {ceiling} °C now, so it starts less often.",
        "boiler.learned_rest": "Your boiler rests about {rest} each time it reaches its temperature.",
        "boiler.learned": "The E32 has learned how your boiler holds its temperature.",
        "boiler.collecting": "The E32 is still listening to how your boiler holds its temperature.",
        "boiler.no_return": "Your boiler does not report the water coming back, so the E32 cannot see how much heat your "
                            "house takes; everything else works as usual.",
        "boiler.not_driving": "The E32 listens to your boiler once it controls the boiler itself.",
        "insight.gas_per_dd_up": "Yesterday used {pct} % more gas per degree of cold than usual.",
        "insight.gas_per_dd_down": "Yesterday used {pct} % less gas per degree of cold than usual.",
        "insight.starts_up": "Yesterday the burner started {pct} % more often per heating hour than usual.",
        "insight.hours_per_dd_up": "Yesterday the heating ran {pct} % longer per degree of cold than usual.",
        "insight.warmup_slower": "Yesterday {room} warmed up {pct} % more slowly than usual.",
        "title.gas_per_dd_up": "More gas than usual",
        "title.gas_per_dd_down": "Less gas than usual",
        "title.starts_up": "More burner starts than usual",
        "title.hours_per_dd_up": "Longer heating than usual",
        "title.warmup_slower": "{room} warmed up more slowly",
        "mean.gas_per_dd_up": "A window or door left open, or a room set warmer, can cause this.",
        "mean.gas_per_dd_down": "Sun, a cooler setting or fewer hours at home can cause this.",
        "mean.starts_up": "Fewer, longer burns are gentler on the boiler; the thermostat watches this.",
        "mean.hours_per_dd_up": "A window or door left open, or a room set warmer, can cause this.",
        "mean.warmup_slower": "A window left open, a closed radiator valve or furniture in front of the radiator can "
                              "slow a room down.",
        "note": "The E32 compares each day with your house's own usual days, corrected for how cold it was. This is "
                "information; you do not need to do anything.",
    },
    "nl": {
        "missing.warmup": "Hij moet nog zien hoe snel {room} opwarmt.",
        "missing.cooling": "Hij moet nog zien hoe snel {room} afkoelt.",
        "missing.arrival": "Hij moet nog nagaan of {room} op tijd warm is.",
        "missing.curve": "Hij leert nog hoeveel warmer het water moet zijn als het buiten kouder wordt.",
        "missing.boiler_minimum": "Hij zoekt nog uit vanaf welke watertemperatuur je ketel gaat verwarmen.",
        "missing.boiler_response": "Hij luistert nog hoe je ketel zijn temperatuur vasthoudt.",
        "missing.house": "Hij rekent nog uit hoe snel je huis warmte verliest.",
        "boiler.learned_both": "Je ketel rust ongeveer {rest} telkens als hij zijn temperatuur bereikt; de E32 vraagt nu "
                               "hooguit {ceiling} °C, zodat hij minder vaak start.",
        "boiler.learned_ceiling": "De E32 vraagt je ketel nu hooguit {ceiling} °C, zodat hij minder vaak start.",
        "boiler.learned_rest": "Je ketel rust ongeveer {rest} telkens als hij zijn temperatuur bereikt.",
        "boiler.learned": "De E32 heeft geleerd hoe je ketel zijn temperatuur vasthoudt.",
        "boiler.collecting": "De E32 luistert nog hoe je ketel zijn temperatuur vasthoudt.",
        "boiler.no_return": "Je ketel meldt het terugkomende water niet, dus de E32 kan niet zien hoeveel warmte je huis "
                            "opneemt; al het andere werkt gewoon.",
        "boiler.not_driving": "De E32 luistert naar je ketel zodra hij de ketel zelf regelt.",
        "insight.gas_per_dd_up": "Gisteren ging er {pct} % meer gas per graad kou door dan normaal.",
        "insight.gas_per_dd_down": "Gisteren ging er {pct} % minder gas per graad kou door dan normaal.",
        "insight.starts_up": "Gisteren startte de brander {pct} % vaker per stookuur dan normaal.",
        "insight.hours_per_dd_up": "Gisteren stookte de verwarming {pct} % langer per graad kou dan normaal.",
        "insight.warmup_slower": "Gisteren warmde {room} {pct} % langzamer op dan normaal.",
        "title.gas_per_dd_up": "Meer gas dan normaal",
        "title.gas_per_dd_down": "Minder gas dan normaal",
        "title.starts_up": "Meer branderstarts dan normaal",
        "title.hours_per_dd_up": "Langer gestookt dan normaal",
        "title.warmup_slower": "{room} warmde langzamer op",
        "mean.gas_per_dd_up": "Een raam of deur die openstond, of een ruimte die warmer is ingesteld, kan dit veroorzaken.",
        "mean.gas_per_dd_down": "Zon, een lagere instelling of minder uren thuis kan dit veroorzaken.",
        "mean.starts_up": "Minder en langer branden is beter voor de ketel; de thermostaat houdt dit in de gaten.",
        "mean.hours_per_dd_up": "Een raam of deur die openstond, of een ruimte die warmer is ingesteld, kan dit veroorzaken.",
        "mean.warmup_slower": "Een open raam, een dichte radiatorkraan of meubels voor de radiator kunnen een ruimte "
                              "vertragen.",
        "note": "De E32 vergelijkt elke dag met de gewone dagen van je eigen huis, gecorrigeerd voor hoe koud het was. Dit "
                "is informatie; je hoeft niets te doen.",
    },
    # Polish: a room name stands after "pomieszczenie" (docs/UX-GLOSSARY.md), so the sentence fits any name.
    "pl": {
        "missing.warmup": "Musi jeszcze zobaczyć, jak szybko nagrzewa się pomieszczenie {room}.",
        "missing.cooling": "Musi jeszcze zobaczyć, jak szybko stygnie pomieszczenie {room}.",
        "missing.arrival": "Musi jeszcze sprawdzić, czy pomieszczenie {room} jest ciepłe na czas.",
        "missing.curve": "Wciąż się uczy, o ile cieplejsza musi być woda, gdy na zewnątrz robi się zimniej.",
        "missing.boiler_minimum": "Wciąż sprawdza, od jakiej temperatury wody Twój kocioł zaczyna grzać.",
        "missing.boiler_response": "Wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę.",
        "missing.house": "Wciąż oblicza, jak szybko Twój dom traci ciepło.",
        "boiler.learned_both": "Twój kocioł odpoczywa około {rest} za każdym razem, gdy osiągnie swoją temperaturę; E32 "
                               "zadaje teraz najwyżej {ceiling} °C, więc kocioł rzadziej się uruchamia.",
        "boiler.learned_ceiling": "E32 zadaje teraz kotłowi najwyżej {ceiling} °C, więc kocioł rzadziej się uruchamia.",
        "boiler.learned_rest": "Twój kocioł odpoczywa około {rest} za każdym razem, gdy osiągnie swoją temperaturę.",
        "boiler.learned": "E32 nauczył się, jak Twój kocioł utrzymuje swoją temperaturę.",
        "boiler.collecting": "E32 wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę.",
        "boiler.no_return": "Twój kocioł nie zgłasza temperatury wody powrotnej, więc E32 nie widzi, ile ciepła pobiera "
                            "Twój dom; wszystko inne działa normalnie.",
        "boiler.not_driving": "E32 zacznie wsłuchiwać się w Twój kocioł, gdy sam będzie nim sterował.",
        "insight.gas_per_dd_up": "Wczoraj zużyto o {pct} % więcej gazu na stopień zimna niż zwykle.",
        "insight.gas_per_dd_down": "Wczoraj zużyto o {pct} % mniej gazu na stopień zimna niż zwykle.",
        "insight.starts_up": "Wczoraj palnik uruchamiał się o {pct} % częściej na godzinę grzania niż zwykle.",
        "insight.hours_per_dd_up": "Wczoraj ogrzewanie pracowało o {pct} % dłużej na stopień zimna niż zwykle.",
        "insight.warmup_slower": "Wczoraj pomieszczenie {room} nagrzewało się o {pct} % wolniej niż zwykle.",
        "title.gas_per_dd_up": "Więcej gazu niż zwykle",
        "title.gas_per_dd_down": "Mniej gazu niż zwykle",
        "title.starts_up": "Więcej startów palnika niż zwykle",
        "title.hours_per_dd_up": "Dłuższe grzanie niż zwykle",
        "title.warmup_slower": "Pomieszczenie {room} nagrzewało się wolniej",
        "mean.gas_per_dd_up": "Może to wynikać z otwartego okna lub drzwi albo z wyższej temperatury ustawionej w "
                              "pomieszczeniu.",
        "mean.gas_per_dd_down": "Może to wynikać ze słońca, niższego ustawienia lub krótszego pobytu w domu.",
        "mean.starts_up": "Rzadsza, dłuższa praca oszczędza kocioł; termostat to obserwuje.",
        "mean.hours_per_dd_up": "Może to wynikać z otwartego okna lub drzwi albo z wyższej temperatury ustawionej w "
                                "pomieszczeniu.",
        "mean.warmup_slower": "Otwarte okno, zamknięty zawór grzejnika lub meble przed grzejnikiem mogą spowolnić "
                              "nagrzewanie.",
        "note": "E32 porównuje każdy dzień ze zwykłymi dniami Twojego domu, z uwzględnieniem tego, jak było zimno. To "
                "informacja; nie musisz nic robić.",
    },
}


def insight_status(summary):
    """The summary's insight (fw/telemetry/insight), or None on firmware without it."""
    insight = summary.get("insight") if type(summary) is dict else None
    return insight if type(insight) is dict else None


def knowledge(summary):
    """{"pct", "missing", "more"} of the insight's knowledge, checked, or None without one."""
    part = (insight_status(summary) or {}).get("knowledge")
    if type(part) is not dict:
        return None
    pct = number(part.get("pct"), 0, 100)
    more = part.get("more")
    return {"pct": round(pct) if pct is not None else None,
            "missing": part["missing"] if type(part.get("missing")) is list else [],
            "more": more if type(more) is int and 0 <= more <= 1000 else 0}


def missing_item(key):
    """(kind, room id or None) of a missing key this version knows, else None."""
    if type(key) is not str:
        return None
    if key in HOUSE_KEYS:
        return key, None
    kind, colon, room = key.partition(":")
    return (kind, room) if colon and kind in ROOM_KEYS and ROOM_ID.fullmatch(room) else None


def missing_sentences(part, names, lang):
    """(sentences, more): each missing item in words, in the E32's order; an unknown key counts in more."""
    t, sentences = TEXT[lang], []
    more = part["more"] if part else 0
    for key in (part or {}).get("missing") or []:
        item = missing_item(key)
        if item is None:
            more += 1
            continue
        kind, room = item
        sentences.append(t["missing." + kind].format(room=names.get(room, room) if room else ""))
    return sentences, more


def boiler_response(summary):
    """The boiler's response (BoilerResponse): the insight's, else the flow document's, or None."""
    summary = summary if type(summary) is dict else {}
    flow = summary.get("flow") if type(summary.get("flow")) is dict else {}
    for part in ((insight_status(summary) or {}).get("boiler"), flow.get("boiler"), summary.get("boiler")):
        if type(part) is dict:
            return part
    return None


def _figure(value, low, high, digits):
    value = number(value, low, high)
    if value is None:
        return None
    value = round(value, digits)
    return int(value) if value == int(value) else value


def boiler_values(boiler):
    """The boiler's figures, each checked (None: not reported or implausible)."""
    boiler = boiler if type(boiler) is dict else {}
    state, held, rest = boiler.get("state"), boiler.get("held"), number(boiler.get("rest_s"), 1, 7200)
    return {"state": state if state in BOILER_STATES else None,
            "held_today": held if type(held) is int and 0 <= held <= 10000 else None,
            "rest_min": round(rest / 60, 1) if rest is not None else None,
            "ceiling_c": _figure(boiler.get("ceiling_c"), 10, 90, 0),
            "absorbed_kw": _figure(boiler.get("absorbed_kw"), 0, 200, 1),
            "kw_per_k": _figure(boiler.get("kw_per_k"), 0, 20, 2)}


def boiler_sentence(values, lang):
    """The boiler's response in one sentence, or None while its state is unknown."""
    t, state = TEXT[lang], values.get("state")
    if state != "learned":
        return t["boiler." + state] if state in BOILER_STATES else None
    rest = duration(values["rest_min"], lang) if values.get("rest_min") else None
    ceiling = decimal(values["ceiling_c"], lang, 0) if values.get("ceiling_c") is not None else None
    key = "learned_both" if rest and ceiling else "learned_ceiling" if ceiling else "learned_rest" if rest else "learned"
    return t["boiler." + key].format(rest=rest, ceiling=ceiling)


def insight_items(summary):
    """Yesterday's insights as the E32 reported them, checked: [{"kind", "pct", "room"}]."""
    items = (insight_status(summary) or {}).get("insights")
    result = []
    for item in items if type(items) is list else []:
        if type(item) is not dict or item.get("kind") not in INSIGHT_KINDS:
            continue  # a kind this version does not know is left out, never half a sentence
        pct, room = number(item.get("pct"), 0, 10000), item.get("room")
        room = room if type(room) is str and ROOM_ID.fullmatch(room) else None
        if pct is None or (item["kind"] == "warmup_slower" and room is None):
            continue
        result.append({"kind": item["kind"], "pct": round(pct), "room": room})
    return result[:MAX_INSIGHTS]


def insight_text(item, names, lang):
    """(title, text, meaning) of one insight in words."""
    t, kind = TEXT[lang], item["kind"]
    values = {"pct": item["pct"], "room": names.get(item["room"], item["room"]) if item["room"] else ""}
    return t["title." + kind].format(**values), t["insight." + kind].format(**values), t["mean." + kind]


def insight_lines(summary, names, lang):
    """[{text, meaning}] of yesterday's insights, for the learned overview and the Learning view."""
    return [{"text": text, "meaning": meaning}
            for _, text, meaning in (insight_text(item, names, lang) for item in insight_items(summary))]


def room_names(hub):
    return {room_id: label(room) for room_id, room in hub.rooms.items()}


# -- the sensors ------------------------------------------------------------------------------------------------


class _InsightSensor(HubEntity, SensorEntity):
    """Mixin: one figure of the insight on the product device; unknown without one, unavailable while silent."""

    @property
    def summary(self):
        return self.hub.summary if self.hub.fresh else None

    @property
    def available(self):
        return self.hub.fresh

    def _lang(self):
        return language(getattr(self, "hass", None))


class KnowledgeSensor(_InsightSensor):
    """How much of what it needs the E32 knows about the house (%), and what it still learns, in words."""

    _attr_translation_key = "knowledge"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    # The sentences are shown, not kept in the history (the percentage is).
    _unrecorded_attributes = frozenset({"missing"})

    def __init__(self, hub):
        self._attach(hub, "hub_knowledge")

    @property
    def native_value(self):
        part = knowledge(self.summary)
        return part["pct"] if part else None

    @property
    def extra_state_attributes(self):
        part = knowledge(self.summary)
        if part is None:
            return None
        missing, more = missing_sentences(part, room_names(self.hub), self._lang())
        return {"missing": missing, "more": more}


class BoilerResponseSensor(_InsightSensor):
    """What the E32 learned from the boiler itself: how long it rests and the most it asks of it now."""

    _attr_translation_key = "boiler_response"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BOILER_STATES
    # The heat the house takes now changes all the time; shown, not kept in the history.
    _unrecorded_attributes = frozenset({"absorbed_kw", "sentence"})

    def __init__(self, hub):
        self._attach(hub, "hub_boiler_response")

    def _values(self):
        boiler = boiler_response(self.summary)
        return boiler_values(boiler) if boiler is not None else None

    @property
    def native_value(self):
        values = self._values()
        return values["state"] if values else None

    @property
    def extra_state_attributes(self):
        values = self._values()
        if values is None:
            return None
        return {**{key: values[key] for key in ("held_today", "rest_min", "ceiling_c", "absorbed_kw", "kw_per_k")},
                "sentence": boiler_sentence(values, self._lang())}


# -- the notifications ------------------------------------------------------------------------------------------


def _signature(item):
    return [item["kind"], item["room"], item["pct"]]


def _dismissed(data):
    """The stored dismissals ({notification id: [kind, room, pct]}), the well-formed ones."""
    stored = data.get("dismissed") if type(data) is dict else None
    return {key: value for key, value in (stored.items() if type(stored) is dict else ())
            if type(key) is str and type(value) is list and len(value) == 3}


class InsightNotifier:
    """One persistent notification per insight of yesterday: information, never a Repairs item.

    A new insight shows; a changed one (another percentage, another language or room name) replaces
    its notification; one that is gone is dismissed. While the E32 is silent nothing changes; once an
    insight the E32 had sent is gone (heating_link: HeatingHub.insight_gone) its notifications go.
    """

    def __init__(self, hass, entry_id, hub, dismissed=None, store=None):
        self.hass, self.entry_id, self.hub, self.store = hass, entry_id, hub, store
        self.dismissed = dict(dismissed or {})  # {notification id: signature} the owner dismissed
        # {notification id: (title, message, signature)} shown in this Home Assistant run.
        self.shown = hass.data.setdefault(_SHOWN, {}).setdefault(entry_id, {})

    def notification_id(self, item):
        room = f"_{item['room']}" if item["room"] else ""
        return f"{DOMAIN}_insight_{item['kind']}{room}_{self.entry_id}"

    @callback
    def hub_changed(self):
        if not self.hub.fresh:
            return
        if insight_status(self.hub.summary) is not None:
            self.sync(insight_items(self.hub.summary))
        elif self.hub.insight_gone:
            self.sync([])

    @callback
    def sync(self, items):
        from homeassistant.components import persistent_notification
        lang, names = language(self.hass), room_names(self.hub)
        wanted = {self.notification_id(item): item for item in items}
        for key, item in wanted.items():
            if self.dismissed.get(key) == _signature(item):
                continue
            title, text, meaning = insight_text(item, names, lang)
            shown = ("OpenThermostat: " + title, text + " " + meaning + "\n\n" + TEXT[lang]["note"], _signature(item))
            if self.shown.get(key) != shown:
                self.shown[key] = shown
                persistent_notification.async_create(self.hass, shown[1], title=shown[0], notification_id=key)
        for key in [key for key in self.shown if key not in wanted]:
            del self.shown[key]  # before the dismissal: it is ours, not the owner's (notification_changed)
            persistent_notification.async_dismiss(self.hass, key)
        stale = [key for key, signature in self.dismissed.items()
                 if key not in wanted or signature != _signature(wanted[key])]
        for key in stale:
            del self.dismissed[key]
        if stale:
            self._save()

    @callback
    def notification_changed(self, update_type, notifications):
        """The owner dismissed one of ours: it stays dismissed until the insight changes."""
        if update_type != "removed":
            return
        for key in notifications:
            shown = self.shown.pop(key, None)
            if shown is not None:
                self.dismissed[key] = shown[2]
                self._save()

    @callback
    def _save(self):
        if self.store is not None:
            self.store.async_delay_save(lambda: {"dismissed": dict(self.dismissed)}, 1)


def _store(hass, entry_id):
    from homeassistant.helpers.storage import Store
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.insight_{entry_id}")


async def async_setup_insight(hass, entry, async_add_entities, options, hub):
    """Product entries: the two sensors on the product device and the insight notifications."""
    async_add_entities([KnowledgeSensor(hub), BoilerResponseSensor(hub)], **options)
    from homeassistant.components import persistent_notification
    store = _store(hass, entry.entry_id)
    notifier = InsightNotifier(hass, entry.entry_id, hub, _dismissed(await store.async_load()), store)
    hass.data[DOMAIN][entry.entry_id]["insight_notifier"] = notifier
    entry.async_on_unload(persistent_notification.async_register_callback(hass, notifier.notification_changed))
    entry.async_on_unload(hub.add_listener(notifier.hub_changed))
    notifier.hub_changed()


async def async_remove_insight(hass, entry_id):
    """A removed installation: its insight notifications go, and what the owner dismissed is forgotten."""
    from homeassistant.components import persistent_notification
    for key in list(hass.data.get(_SHOWN, {}).pop(entry_id, {})):
        persistent_notification.async_dismiss(hass, key)
    await _store(hass, entry_id).async_remove()
