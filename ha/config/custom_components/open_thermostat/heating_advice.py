"""Central-heating tuning advice: what to change in the boiler, the E32 or the rooms.

ADVICE ONLY. Nothing here writes a setting: boiler writes stay disabled and
the E32 keeps its own plan. Each rule is a small pure function over a bounded
rolling window of five-minute samples (24 h, in memory) and a few per-day
aggregates (14 days, kept in Home Assistant's restore state), with its
thresholds as named constants. A rule only advises with enough evidence; it
reports what is missing instead of guessing.

One sensor on the product device ("Heating advice" / "CV-advies") holds the
current advice: its state is the number of items, the attribute ``items``
the items ({id, severity, title, observed, why, action, where, confidence,
since}) in the Home Assistant language (English or Dutch), and
``not_evaluated`` the rules that lack data, with the reason. The attribute
``weekly_summary`` holds the last seven days (weekly_summary.py) for the
opt-in weekly notification blueprint.
"""
import math
import time
from datetime import date, datetime, timedelta, timezone

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .boiler_fields import INDEXES, BoilerFieldCache, spec
from .const import DOMAIN
from .energy_input import CONF_BOILER_KW, CONF_GAS_METER, currency, energy_options, gas_price, kwh_per_m3

# -- sampling ------------------------------------------------------------------
SAMPLE_SECONDS = 300
HISTORY_SECONDS = 24 * 3600
MAX_SAMPLES = HISTORY_SECONDS // SAMPLE_SECONDS + 12
# Two samples further apart than this are not one continuous observation.
MAX_GAP_SECONDS = 2 * SAMPLE_SECONDS + 60
DAYS_KEPT = 14

# -- rule thresholds -----------------------------------------------------------
# 1. Short cycling
SHORT_CYCLE_STARTS_PER_HOUR = 6
SHORT_CYCLE_HOURS = 2
SHORT_CYCLE_HIGH_HOURS = 4
SHORT_CYCLE_WARNING_STARTS = 10
MINIMUM_BURNER_PERIOD_TARGET_MIN = 10
MINIMUM_BURNER_PERIOD_STEP_MIN = 5
MINIMUM_BURNER_PERIOD_MAX_MIN = 30
# 2. Maximum CH temperature much higher than needed
MAX_CH_SETTING_C = 65
MAX_CH_LOW_REQUEST_C = 50
MAX_CH_DAYS = 3
MAX_CH_HIGH_DAYS = 7
MAX_CH_WINDOW_DAYS = 7
MAX_CH_MARGIN_C = 10
MAX_CH_LOWEST_SUGGESTION_C = 55
DAY_MIN_SAMPLES = 144           # 12 h observed
DAY_MIN_HEAT_SAMPLES = 6        # 30 min with a heat request
HEAT_REQUEST_C = 20             # a flow request at or above this means heat is asked
# 3. Return too warm for condensing
RETURN_CONDENSING_C = 55
RETURN_MIN_SAMPLES = 12         # 1 h of heating
RETURN_HIGH_SAMPLES = 48
# 4. Flow versus the learned need
LEARNED_HOLD_SECONDS = 3600
LEARNED_HIGH_SECONDS = 6 * 3600
# 5. Night setback
NIGHT_MIN_SAVING_M3 = 0.05
NIGHT_HIGH_SAVING_M3 = 0.2
NIGHT_HOLD_SECONDS = 1800
GAS_KWH_PER_M3 = 9.77           # default calorific value (the E32's own); configurable
# 6. Hot water
DHW_HIGH_C = 60
DHW_SUGGESTED_C = 55
DHW_LOW_C = 50
DHW_HOLD_SECONDS = 6 * 3600     # longer than a disinfection run
# 7. Pressure
PRESSURE_LOW_BAR = 1.0
PRESSURE_HIGH_BAR = 2.5
PRESSURE_PLAUSIBLE_BAR = 0.2    # below: no sensor rather than an empty system
PRESSURE_LOW_HOLD_SECONDS = 1800
PRESSURE_HIGH_HOLD_SECONDS = 3600
# 8. Pump run-on
PUMP_RUN_ON_LONG_MIN = 10
PUMP_RUN_ON_SHORT_MIN = 2

SEVERITIES = ("warning", "suggestion", "info")
CONFIDENCES = ("low", "medium", "high")
PRESSURE_ISSUE = "low_boiler_pressure"

INDEX = {spec(index)[0]: index for index in INDEXES}


class Missing:
    """A rule that cannot be evaluated: the reason (a text key) and its values."""

    def __init__(self, reason, **values):
        self.reason, self.values = reason, values


def advice(item_id, rule, severity, confidence, values=None, parts=()):
    return {"id": item_id, "rule": rule, "severity": severity, "confidence": confidence,
            "values": dict(values or {}), "parts": tuple(parts)}


# -- window helpers ------------------------------------------------------------


def latest(samples, key):
    """The newest value of a key in the window, or None."""
    for sample in reversed(samples):
        if sample.get(key) is not None:
            return sample[key]
    return None


def runs(samples, predicate):
    """The stretches of consecutive samples for which predicate holds (a time gap ends a stretch)."""
    result, current, previous = [], [], None
    for sample in samples:
        if predicate(sample) and (not current or sample["t"] - previous <= MAX_GAP_SECONDS):
            current.append(sample)
        elif predicate(sample):
            result.append(current)
            current = [sample]
        else:
            if current:
                result.append(current)
            current = []
        previous = sample["t"]
    if current:
        result.append(current)
    return result


def span(run):
    """Seconds a stretch covers (each sample stands for one sample period)."""
    return run[-1]["t"] - run[0]["t"] + SAMPLE_SECONDS if run else 0


def current_run(samples, predicate):
    """The stretch that ends with the newest sample, or []."""
    found = runs(samples, predicate)
    return found[-1] if found and samples and found[-1][-1] is samples[-1] else []


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def round5_up(value):
    return int(5 * math.ceil(value / 5))


def one(value, digits=1):
    value = round(value, digits)
    return int(value) if value == int(value) else value


# -- the rules (pure) ----------------------------------------------------------


def rule_short_cycling(samples, ctx):
    """1. Burner starts too often: the E32 flag, or >= 6 heating starts per hour, for >= 2 h."""
    if not any(s.get("sc") is not None or s.get("hs") is not None for s in samples):
        return Missing("no_burner_count")
    stretches = runs(samples, lambda s: s.get("sc") is True or (s.get("hs") or 0) >= SHORT_CYCLE_STARTS_PER_HOUR)
    best = max(stretches, key=span, default=[])
    if span(best) < SHORT_CYCLE_HOURS * 3600:
        return []
    starts = max((s["hs"] for s in best if s.get("hs") is not None), default=None)
    minimum = latest(samples, "mb")
    target = MINIMUM_BURNER_PERIOD_TARGET_MIN if minimum is None else min(
        max(minimum + MINIMUM_BURNER_PERIOD_STEP_MIN, MINIMUM_BURNER_PERIOD_TARGET_MIN), MINIMUM_BURNER_PERIOD_MAX_MIN)
    values = {"hours": one(span(best) / 3600), "starts": starts, "mbp": minimum, "mbp_target": one(target, 0),
              "hyst_on": latest(samples, "hn"), "hyst_off": latest(samples, "hf"), "max_ch": latest(samples, "mx")}
    parts = ["flagonly"] if starts is None else []
    parts += [part for part, keys in (("mbp", ("mbp",)), ("hyst", ("hyst_on", "hyst_off")), ("maxch", ("max_ch",)))
              if all(values[key] is not None for key in keys)]
    if minimum is not None and minimum >= MINIMUM_BURNER_PERIOD_MAX_MIN:
        parts.append("mbpmax")
    severity = "warning" if starts is not None and starts >= SHORT_CYCLE_WARNING_STARTS else "suggestion"
    confidence = "high" if span(best) >= SHORT_CYCLE_HIGH_HOURS * 3600 else "medium"
    return [advice("short_cycling", "short_cycling", severity, confidence, values, parts)]


def rule_max_ch(samples, ctx):
    """2. Max CH setting >= 65 °C while the highest requested flow stayed <= 50 °C for >= 3 days (floor present)."""
    setting = latest(samples, "mx")
    if setting is None:
        return Missing("no_max_ch")
    if setting < MAX_CH_SETTING_C or not ctx.get("floor"):
        return []
    today = ctx["today"]
    recent = [day for key, day in ctx.get("days", {}).items()
              if 0 <= (today - date.fromisoformat(key)).days < MAX_CH_WINDOW_DAYS]
    good = [day for day in recent if day["n"] >= DAY_MIN_SAMPLES and day["heat"] >= DAY_MIN_HEAT_SAMPLES]
    if len(good) < MAX_CH_DAYS:
        return Missing("few_days", days=len(good), needed=MAX_CH_DAYS)
    peak = max(day["max"] for day in recent if day.get("max") is not None)
    if peak > MAX_CH_LOW_REQUEST_C:
        return []
    suggestion = round5_up(max(peak + MAX_CH_MARGIN_C, MAX_CH_LOWEST_SUGGESTION_C))
    if suggestion >= setting:
        return []
    confidence = "high" if len(good) >= MAX_CH_HIGH_DAYS else "medium"
    return [advice("max_ch_high", "max_ch_high", "suggestion", confidence,
                   {"max_ch": one(setting), "days": len(good), "peak": one(peak), "suggest": suggestion})]


def rule_return(samples, ctx):
    """3. While heating, the median return temperature >= 55 °C: too warm to condense."""
    if latest(samples, "rn") is None or latest(samples, "ha") is None:
        return Missing("no_return")
    heating = [s for s in samples if s.get("ha") is True and s.get("da") is not True and s.get("rn") is not None]
    if len(heating) < RETURN_MIN_SAMPLES:
        return Missing("few_heating")
    value = median([s["rn"] for s in heating])
    if value < RETURN_CONDENSING_C:
        return []
    flows = [s["fl"] for s in heating if s.get("fl") is not None]
    values = {"median": one(value), "hours": one(len(heating) * SAMPLE_SECONDS / 3600),
              "flow": one(median(flows)) if flows else None}
    confidence = "high" if len(heating) >= RETURN_HIGH_SAMPLES else "medium"
    return [advice("return_too_warm", "return_too_warm", "suggestion", confidence, values,
                   ["flow"] if flows else [])]


def rule_learned_flow(samples, ctx):
    """4. Per learned room (readiness ready), the 1 °C advice against the E32's own rule."""
    rooms = (samples[-1].get("rooms") or {}) if samples else {}
    if not any(s.get("rooms") for s in samples):
        return Missing("no_learning")
    if not any(room.get("r") == "ready" for room in rooms.values()):
        return Missing("not_learned")
    items = []
    max_flow = ctx.get("max_flow")
    for room_id, room in rooms.items():
        rule = room.get("rule")
        if room.get("r") != "ready" or rule not in ("higher_wasteful", "lower_too_slow") or room.get("need") is None:
            continue
        if rule == "higher_wasteful" and samples[-1].get("ap") is True:
            continue  # the E32 already asks the learned flow
        run = current_run(samples, lambda s, i=room_id, r=rule: (s.get("rooms") or {}).get(i, {}).get("r") == "ready"
                          and (s.get("rooms") or {}).get(i, {}).get("rule") == r)
        if span(run) < LEARNED_HOLD_SECONDS:
            continue
        need, current = room["need"], room.get("rf")
        values = {"room": ctx.get("names", {}).get(room_id, room_id), "need": need, "rule": current,
                  "lower_by": one(current - need, 0) if current is not None else None, "max_flow": max_flow}
        parts = []
        if max_flow is not None:
            parts.append("maxflow")
        if rule == "lower_too_slow" and max_flow is not None and need > max_flow:
            parts.append("cap")
        if current is None:
            parts.append("norule")
        confidence = "high" if span(run) >= LEARNED_HIGH_SECONDS else "medium"
        items.append(advice(f"flow_{rule}:{room_id}", f"flow_{rule}", "suggestion", confidence, values, parts))
    return items


def night_saving(night, ctx):
    """(values, parts, confidence) of one night estimate.

    m³ (and money with a price) with a gas meter, kWh without; without the
    boiler's power the estimate is rough (the E32 then assumes a default).
    """
    m3 = night["m3"]
    gas = ctx.get("gas_meter", False)
    price = ctx.get("price")
    values = {"saving_m3": one(m3, 2), "saving_kwh": one(m3 * ctx.get("kwh_per_m3", GAS_KWH_PER_M3)),
              "currency": ctx.get("currency", "EUR")}
    parts = []
    if gas:
        money = night.get("eur") if price is not None else None
        if money is None and price is not None:
            money = m3 * price
        if money is not None:
            values["saving_money"] = one(money, 2)
            parts.append("money")
    else:
        parts += ["kwh", "no_gas"]
    calibrated = night.get("conf") == "calibrated"
    if calibrated:
        confidence = "high" if m3 >= NIGHT_HIGH_SAVING_M3 else "medium"
    elif gas and night.get("conf") is None and boiler_kw_known(ctx):
        confidence = "medium"
    else:
        confidence = "low"
        if gas and night.get("conf") is not None:
            parts.append("calibrating")
    if not boiler_kw_known(ctx) and not calibrated:
        confidence = "low"
        parts.append("rough")
    return values, parts, confidence


def rule_night(samples, ctx):
    """5. The E32's night recommendation, when it saves >= 0.05 m³ a night."""
    nights = (samples[-1].get("nights") or {}) if samples else {}
    if not any(s.get("nights") for s in samples):
        return Missing("no_plans")
    items = []
    for room_id, night in nights.items():
        if night.get("c") is None or night.get("m3") is None or night["m3"] < NIGHT_MIN_SAVING_M3:
            continue
        if night.get("name") in (None, "program"):
            continue
        run = current_run(samples, lambda s, i=room_id, c=night["c"]: ((s.get("nights") or {}).get(i) or {}).get("c") == c
                          and (((s.get("nights") or {}).get(i) or {}).get("m3") or 0) >= NIGHT_MIN_SAVING_M3)
        if span(run) < NIGHT_HOLD_SECONDS:
            continue
        values, parts, confidence = night_saving(night, ctx)
        values.update(room=ctx.get("names", {}).get(room_id, room_id), night=night["c"])
        severity = "info" if confidence == "low" else "suggestion"
        items.append(advice(f"night_setback:{room_id}", "night_setback", severity, confidence, values, parts))
    return items


def rule_dhw(samples, ctx):
    """6. Selected hot-water temperature > 60 °C (gas) or < 50 °C (legionella), held for 6 h."""
    if latest(samples, "dw") is None:
        return Missing("no_dhw")
    disinfection = latest(samples, "ds")
    for rule, predicate, severity in (("dhw_high", lambda s: s.get("dw") is not None and s["dw"] > DHW_HIGH_C,
                                       "suggestion"),
                                      ("dhw_low", lambda s: s.get("dw") is not None and s["dw"] < DHW_LOW_C, "info")):
        run = current_run(samples, predicate)
        if span(run) >= DHW_HOLD_SECONDS:
            values = {"dhw": one(samples[-1]["dw"]), "suggest": DHW_SUGGESTED_C, "disinfection": disinfection}
            return [advice(rule, rule, severity, "high", values, ["disinfection"] if disinfection is not None else [])]
    return []


def rule_pressure(samples, ctx):
    """7. System pressure < 1.0 bar (refill) or > 2.5 bar (expansion vessel / relief valve)."""
    if latest(samples, "p") is None:
        return Missing("no_pressure")
    for rule, predicate, hold in (
            ("pressure_low", lambda s: s.get("p") is not None and PRESSURE_PLAUSIBLE_BAR <= s["p"] < PRESSURE_LOW_BAR,
             PRESSURE_LOW_HOLD_SECONDS),
            ("pressure_high", lambda s: s.get("p") is not None and s["p"] > PRESSURE_HIGH_BAR,
             PRESSURE_HIGH_HOLD_SECONDS)):
        run = current_run(samples, predicate)
        if span(run) >= hold:
            return [advice(rule, rule, "warning", "high",
                           {"pressure": one(samples[-1]["p"]), "minutes": one(span(run) / 60, 0)})]
    return []


def rule_pump_run_on(samples, ctx):
    """8. Pump run-on >= 10 min with floor heating, or < 2 min while short cycling (only if reported)."""
    run_on = latest(samples, "pr")
    if run_on is None:
        return Missing("no_pump_run_on")
    if run_on >= PUMP_RUN_ON_LONG_MIN and ctx.get("floor"):
        return [advice("pump_run_on_long", "pump_run_on_long", "suggestion", "medium", {"run_on": one(run_on)})]
    if run_on < PUMP_RUN_ON_SHORT_MIN and ctx.get("short_cycling"):
        return [advice("pump_run_on_short", "pump_run_on_short", "suggestion", "medium", {"run_on": one(run_on)})]
    return []


def boiler_kw_known(ctx):
    """Whether the E32 estimates with a real boiler power.

    Newer firmware says which power it uses (``inputs.boiler_kw_source``:
    ``default`` or ``ha``); older firmware only has the energy option to go by.
    """
    source = ctx.get("boiler_kw_source")
    if source in ("default", "ha"):
        return source == "ha"
    return bool(ctx.get("boiler_kw"))


def rule_boiler_power(samples, ctx):
    """The E32 estimates with a default boiler power until one reaches it from the energy options."""
    if boiler_kw_known(ctx) or not ctx.get("learning"):
        return []
    return [advice("boiler_power_missing", "boiler_power_missing", "info", "high")]


RULES = (("short_cycling", rule_short_cycling), ("max_ch_high", rule_max_ch), ("return_too_warm", rule_return),
         ("learned_flow", rule_learned_flow), ("night_setback", rule_night), ("dhw", rule_dhw),
         ("pressure", rule_pressure), ("pump_run_on", rule_pump_run_on), ("boiler_power", rule_boiler_power))


def evaluate(samples, ctx):
    """(advice items, [(rule, Missing)]) for a window of samples (oldest first) and its context."""
    items, missing = [], []
    ctx = dict(ctx)
    for name, rule in RULES:
        result = rule(samples, ctx)
        if isinstance(result, Missing):
            missing.append((name, result))
            continue
        items.extend(result)
        if name == "short_cycling":
            ctx["short_cycling"] = bool(result)
    items.sort(key=lambda item: SEVERITIES.index(item["severity"]))
    return items, missing


# -- texts (English and Dutch; placeholders filled from the data) ---------------
#
# Per rule: title, observed, why, action, where. "<field>+<part>" is appended
# when the rule reports that part; "<field>@<part>" replaces the field.

TEXT = {
    "en": {
        "rules": {
            "short_cycling": {
                "title": "The boiler switches on and off too often",
                "observed": "The burner started up to {starts} times per hour for heating, for {hours} h "
                            "(counted by the E32 on the bus).",
                "observed@flagonly": "The E32 saw the burner short cycling for {hours} h.",
                "observed+mbp": " Minimum burner period: {mbp} min.",
                "observed+hyst": " Switch hysteresis: on {hyst_on} K, off {hyst_off} K.",
                "observed+maxch": " Maximum heating temperature of the boiler: {max_ch} °C.",
                "why": "Every start costs extra gas (purging and warming up), wears the ignition and fan, "
                       "and makes the room temperature less steady.",
                "action": "Raise the boiler's minimum burner period (anti-cycling time), for example to "
                          "{mbp_target} min. Also consider lowering the maximum heating temperature on your "
                          "boiler, so it reaches its switch-off point less quickly.",
                "action@mbpmax": "The minimum burner period is already long; consider lowering the maximum heating "
                                 "temperature on your boiler, so it reaches its switch-off point less quickly.",
                "action+hyst": " A wider switch hysteresis (about 2 K more) also reduces the starts.",
                "where": "Boiler service menu (installer level). The maximum heating temperature: on many "
                         "models a knob, on others the boiler menu or its app.",
            },
            "max_ch_high": {
                "title": "The boiler's maximum heating temperature is higher than needed",
                "observed": "The boiler's maximum heating temperature is {max_ch} °C, but over the last {days} days with "
                            "heating the highest flow requested (thermostat and E32) was {peak} °C.",
                "why": "A lower maximum keeps the return water cooler, so the boiler condenses more (less gas), "
                       "and it limits overshoot and cycling. Floor heating usually has its own valve that limits "
                       "its water to about 50 °C, so a higher boiler maximum only serves the radiators.",
                "action": "Lower the maximum heating temperature on your boiler to {suggest} °C — on many "
                          "models a knob, on others the boiler menu or its app. The E32 never asks for more than "
                          "this maximum. If a room no longer gets warm on cold days, raise it again by 5 °C.",
                "where": "On the boiler: on many models a knob, on others the boiler menu or its app.",
            },
            "return_too_warm": {
                "title": "Return water too warm to condense",
                "observed": "While heating, the median return temperature was {median} °C over {hours} h of "
                            "heating.",
                "observed+flow": " Median flow: {flow} °C.",
                "why": "A condensing boiler only condenses (recovers the heat in its flue gas, about 10% more "
                       "efficient) when the return water stays below about 55 °C.",
                "action": "Lower the flow temperature: the maximum heating temperature or heating curve on "
                          "your boiler, or the E32's maximum flow temperature. If flow and return are close "
                          "together, a lower pump speed gives a cooler return.",
                "where": "On the boiler: on many models a knob, on others the boiler menu or its app. Home Assistant: OpenThermostat → Configure → Rooms → Flow temperature limits (or on the E32: Rooms → Boiler flow limits).",
            },
            "flow_higher_wasteful": {
                "title": "{room}: a lower flow is enough",
                "observed": "The E32 learned that {need} °C flow warms {room} by 1 °C in time; its current rule "
                            "would ask {rule} °C.",
                "observed@norule": "The E32 learned that {need} °C flow warms {room} by 1 °C in time, less than "
                                   "its current rule asks.",
                "why": "A lower flow temperature gives a cooler return, more condensing and a steadier burner: "
                       "less gas for the same comfort.",
                "action": "No action needed now. Once the E32 controls the boiler, it will ask this lower "
                          "temperature itself. If every room shows this advice, you can already lower the E32's "
                          "maximum flow temperature by about {lower_by} °C.",
                "action@norule": "No action needed now. Once the E32 controls the boiler, it will ask this lower "
                                 "temperature itself.",
                "action+maxflow": " It is now {max_flow} °C.",
                "where": "Home Assistant: OpenThermostat → Configure → Rooms → Flow temperature limits (or on the E32: Rooms → Boiler flow limits).",
            },
            "flow_lower_too_slow": {
                "title": "{room} needs a higher flow",
                "observed": "The E32 learned that {room} needs {need} °C flow to warm up 1 °C in time; its current "
                            "rule would ask only {rule} °C.",
                "observed@norule": "The E32 learned that {room} needs {need} °C flow to warm up 1 °C in time, more "
                                   "than its current rule asks.",
                "why": "With too low a flow the room warms up slowly after a setback, so it reaches its comfort "
                       "temperature too late.",
                "action": "Check that the E32's maximum flow temperature and the maximum heating temperature on "
                          "your boiler allow {need} °C, or start heating earlier in the week program.",
                "action+cap": " The E32's maximum flow ({max_flow} °C) is below what this room needs.",
                "where": "Home Assistant: OpenThermostat → Configure → Rooms → Flow temperature limits (or on the E32: Rooms → Boiler flow limits). The week program: Configure → Rooms → Edit or remove a "
                         "room.",
            },
            "night_setback": {
                "title": "{room}: a different night temperature saves gas",
                "observed": "The E32 estimates that a night temperature of {night} °C saves about {saving_m3} m³ "
                            "of gas per night and still gets the room warm on time.",
                "observed@kwh": "The E32 estimates that a night temperature of {night} °C saves about "
                                "{saving_kwh} kWh per night and still gets the room warm on time.",
                "observed+money": " That is about {saving_money} {currency} per night.",
                "why": "A night setback saves gas, but one that is too deep costs extra to warm up again in the "
                       "morning; the E32 compared the options with what it learned about this room.",
                "action": "Set the night temperature of {room} to {night} °C in the week program.",
                "action+no_gas": " This is an estimate from the burner modulation and the boiler's power, not "
                                 "from a gas meter: add your gas meter under Energy and outdoor temperature to "
                                 "calibrate it.",
                "action+calibrating": " The E32 calibrates the estimate once it has seen a few gas meter "
                                      "readings.",
                "action+rough": " Without your boiler's power this is only a rough estimate: set it under "
                                "Energy and outdoor temperature.",
                "where": "Home Assistant: OpenThermostat → Configure → Rooms → the room's week program.",
            },
            "dhw_high": {
                "title": "Hot water hotter than needed",
                "observed": "The selected hot water temperature is {dhw} °C.",
                "observed+disinfection": " Weekly disinfection: {disinfection} °C.",
                "why": "Every degree above about 55 °C costs gas to keep the water warm, adds limescale and "
                       "raises the scalding risk.",
                "action": "Set the hot water temperature to {suggest} °C. With a hot water tank, keep the "
                          "boiler's weekly disinfection (thermal legionella protection) switched on.",
                "where": "Boiler display (hot water temperature) or the hot water setting of your thermostat.",
            },
            "dhw_low": {
                "title": "Hot water below 50 °C",
                "observed": "The selected hot water temperature is {dhw} °C.",
                "observed+disinfection": " Weekly disinfection: {disinfection} °C.",
                "why": "Legionella bacteria can grow in stored water between about 25 and 50 °C. For a combi "
                       "boiler without a tank the risk is small; with a hot water tank it matters.",
                "action": "With a hot water tank, set at least {suggest} °C or make sure the weekly disinfection "
                          "runs (60 °C or more). With a combi boiler without a tank you can keep this setting.",
                "where": "Boiler display (hot water temperature) or the hot water setting of your thermostat.",
            },
            "pressure_low": {
                "title": "Water pressure low",
                "observed": "The system pressure has been {pressure} bar for at least {minutes} min.",
                "why": "Below about 1 bar the boiler can lock out, and air can get into the highest radiators.",
                "action": "Top up the system at the filling tap to 1.5–2.0 bar (with the system cold). If you "
                          "have to top up often, look for a leak or have the expansion vessel checked.",
                "where": "Filling tap or filling loop at the boiler.",
            },
            "pressure_high": {
                "title": "Water pressure high",
                "observed": "The system pressure has been {pressure} bar for at least {minutes} min.",
                "why": "Near 3 bar the safety relief valve opens. A high pressure while warm usually means the "
                       "expansion vessel has lost its pre-charge.",
                "action": "Have the expansion vessel and the relief valve checked. A cold system should be at "
                          "1.5–2.0 bar; if it is much higher when cold, let some water out at a radiator.",
                "where": "Expansion vessel and relief valve at the boiler (installer).",
            },
            "pump_run_on_long": {
                "title": "Pump keeps running long after heating",
                "observed": "The boiler's pump run-on time is {run_on} min.",
                "why": "Floor heating mostly has its own pump at the manifold; a long boiler pump run-on then "
                       "mainly costs electricity and moves lukewarm water around after the heat demand ended.",
                "action": "Shorten the pump run-on to about 3–5 min.",
                "where": "Boiler service menu (installer level).",
            },
            "pump_run_on_short": {
                "title": "Pump stops very soon after the burner",
                "observed": "The boiler's pump run-on time is {run_on} min while the burner is short cycling.",
                "why": "When the pump stops right after the burner, the heat left in the boiler stays there and "
                       "the boiler warms up again quickly; that adds to the cycling.",
                "action": "Lengthen the pump run-on to about 3–5 min.",
                "where": "Boiler service menu (installer level).",
            },
            "boiler_power_missing": {
                "title": "Set your boiler's power for accurate estimates",
                "observed": "The E32 estimates heat and gas from the burner modulation with a default boiler "
                            "power, because none is set.",
                "why": "The flow and night estimates scale with the boiler's power; a wrong power gives wrong "
                       "savings.",
                "action": "Enter the boiler's nominal heating power in kW (on the type plate or in the manual).",
                "where": "Home Assistant: OpenThermostat → Configure → Energy and outdoor temperature.",
            },
        },
        "missing": {
            "no_burner_count": "The E32 reports no burner starts yet (needs E32 firmware that counts them).",
            "no_max_ch": "The boiler does not report its maximum heating temperature.",
            "few_days": "Needs at least {needed} days with heating; {days} so far.",
            "no_return": "The boiler does not report a return temperature while heating.",
            "few_heating": "Needs at least 1 h of heating with a return temperature.",
            "no_learning": "The E32 reports no learned rooms (needs E32 firmware that learns).",
            "not_learned": "No room is learned yet.",
            "no_plans": "The E32 has no night estimate yet (needs a trusted clock and learned rooms).",
            "no_dhw": "The boiler does not report its hot water temperature.",
            "no_pressure": "The boiler does not report its water pressure.",
            "no_pump_run_on": "The boiler does not report its pump run-on time.",
        },
    },
    "nl": {
        "rules": {
            "short_cycling": {
                "title": "De ketel slaat te vaak aan en af (pendelen)",
                "observed": "De brander startte tot {starts} keer per uur voor verwarming, {hours} uur lang "
                            "(geteld door de E32 op de bus).",
                "observed@flagonly": "De E32 zag de brander {hours} uur lang pendelen.",
                "observed+mbp": " Minimale branderlooptijd: {mbp} min.",
                "observed+hyst": " Schakelhysterese: aan {hyst_on} K, uit {hyst_off} K.",
                "observed+maxch": " Maximale cv-temperatuur van de ketel: {max_ch} °C.",
                "why": "Elke start kost extra gas (voorspoelen en opwarmen), slijt de ontsteking en ventilator, "
                       "en maakt de kamertemperatuur onrustiger.",
                "action": "Verhoog de minimale branderlooptijd (anti-pendeltijd) van de ketel, bijvoorbeeld naar "
                          "{mbp_target} min. Overweeg ook de maximale cv-temperatuur op je ketel te verlagen, zodat "
                          "de ketel minder snel zijn uitschakelpunt bereikt.",
                "action@mbpmax": "De minimale branderlooptijd is al lang; overweeg de maximale cv-temperatuur op je "
                                 "ketel te verlagen, zodat de ketel minder snel zijn uitschakelpunt bereikt.",
                "action+hyst": " Een ruimere schakelhysterese (ongeveer 2 K meer) vermindert de starts ook.",
                "where": "Servicemenu van de ketel (installateursniveau). De maximale cv-temperatuur: bij veel "
                         "modellen een draaiknop, bij andere het ketelmenu of de app van de ketel.",
            },
            "max_ch_high": {
                "title": "Maximale cv-temperatuur van de ketel hoger dan nodig",
                "observed": "De maximale cv-temperatuur van de ketel staat op {max_ch} °C, maar de afgelopen {days} "
                            "dagen met verwarming was de hoogste gevraagde aanvoer (thermostaat en E32) {peak} °C.",
                "why": "Een lager maximum houdt het retourwater koeler, zodat de ketel meer condenseert (minder "
                       "gas), en beperkt doorschieten en pendelen. Vloerverwarming heeft meestal een eigen klep "
                       "die het water op ongeveer 50 °C begrenst; een hoger ketelmaximum dient dan alleen de "
                       "radiatoren.",
                "action": "Verlaag de maximale cv-temperatuur op je ketel naar {suggest} °C — bij veel modellen "
                          "een draaiknop, bij andere het ketelmenu of de app van de ketel. De E32 vraagt nooit meer "
                          "dan dit maximum. Wordt een ruimte op koude dagen niet meer warm, verhoog dan weer met "
                          "5 °C.",
                "where": "Op de ketel: bij veel modellen een draaiknop, bij andere het ketelmenu of de app van de ketel.",
            },
            "return_too_warm": {
                "title": "Retourwater te warm om te condenseren",
                "observed": "Tijdens verwarmen was de mediane retourtemperatuur {median} °C over {hours} uur "
                            "verwarmen.",
                "observed+flow": " Mediane aanvoer: {flow} °C.",
                "why": "Een HR-ketel condenseert alleen (haalt de warmte uit zijn rookgas, ongeveer 10% zuiniger) "
                       "als het retourwater onder ongeveer 55 °C blijft.",
                "action": "Verlaag de aanvoertemperatuur: de maximale cv-temperatuur of stooklijn op je ketel, of "
                          "de maximale aanvoertemperatuur van de E32. Liggen aanvoer en retour dicht bij elkaar, "
                          "dan geeft een lagere pompstand een koelere retour.",
                "where": "Op de ketel: bij veel modellen een draaiknop, bij andere het ketelmenu of de app van de ketel. Home Assistant: OpenThermostat → Configureren → Ruimtes → Grenzen aanvoertemperatuur (of op de E32: Ruimtes → Grenzen aanvoertemperatuur).",
            },
            "flow_higher_wasteful": {
                "title": "{room}: een lagere aanvoer is genoeg",
                "observed": "De E32 heeft geleerd dat {need} °C aanvoer {room} op tijd 1 °C opwarmt; de huidige "
                            "regel zou {rule} °C vragen.",
                "observed@norule": "De E32 heeft geleerd dat {need} °C aanvoer {room} op tijd 1 °C opwarmt, minder "
                                   "dan de huidige regel vraagt.",
                "why": "Een lagere aanvoertemperatuur geeft een koelere retour, meer condensatie en een rustiger "
                       "brander: minder gas voor hetzelfde comfort.",
                "action": "Nu niets doen. Zodra de E32 de ketel regelt, vraagt hij zelf deze lagere temperatuur. "
                          "Geeft elke ruimte dit advies, dan kun je de maximale aanvoertemperatuur van de E32 nu al "
                          "ongeveer {lower_by} °C verlagen.",
                "action@norule": "Nu niets doen. Zodra de E32 de ketel regelt, vraagt hij zelf deze lagere "
                                 "temperatuur.",
                "action+maxflow": " Die staat nu op {max_flow} °C.",
                "where": "Home Assistant: OpenThermostat → Configureren → Ruimtes → Grenzen aanvoertemperatuur (of op de E32: Ruimtes → Grenzen aanvoertemperatuur).",
            },
            "flow_lower_too_slow": {
                "title": "{room} heeft een hogere aanvoer nodig",
                "observed": "De E32 heeft geleerd dat {room} {need} °C aanvoer nodig heeft om op tijd 1 °C op te "
                            "warmen; de huidige regel zou maar {rule} °C vragen.",
                "observed@norule": "De E32 heeft geleerd dat {room} {need} °C aanvoer nodig heeft om op tijd 1 °C "
                                   "op te warmen, meer dan de huidige regel vraagt.",
                "why": "Met te lage aanvoer warmt de ruimte na een verlaging langzaam op, zodat de "
                       "comforttemperatuur te laat bereikt wordt.",
                "action": "Controleer of de maximale aanvoertemperatuur van de E32 en de maximale cv-temperatuur "
                          "op je ketel {need} °C toelaten, of begin eerder met verwarmen in het weekprogramma.",
                "action+cap": " De maximale aanvoer van de E32 ({max_flow} °C) ligt onder wat deze ruimte nodig "
                              "heeft.",
                "where": "Home Assistant: OpenThermostat → Configureren → Ruimtes → Grenzen aanvoertemperatuur (of op de E32: Ruimtes → Grenzen aanvoertemperatuur). Het weekprogramma: Configureren → Ruimtes → Ruimte "
                         "bewerken of verwijderen.",
            },
            "night_setback": {
                "title": "{room}: een andere nachttemperatuur bespaart gas",
                "observed": "De E32 schat dat een nachttemperatuur van {night} °C ongeveer {saving_m3} m³ gas per "
                            "nacht bespaart en de ruimte toch op tijd warm krijgt.",
                "observed@kwh": "De E32 schat dat een nachttemperatuur van {night} °C ongeveer {saving_kwh} kWh "
                                "per nacht bespaart en de ruimte toch op tijd warm krijgt.",
                "observed+money": " Dat is ongeveer {saving_money} {currency} per nacht.",
                "why": "Een nachtverlaging bespaart gas, maar een te diepe verlaging kost 's ochtends extra om "
                       "weer op te warmen; de E32 vergeleek de mogelijkheden met wat hij van deze ruimte leerde.",
                "action": "Zet de nachttemperatuur van {room} in het weekprogramma op {night} °C.",
                "action+no_gas": " Dit is een schatting uit de brandermodulatie en het ketelvermogen, niet uit een "
                                 "gasmeter: voeg je gasmeter toe onder Energie en buitentemperatuur om haar te "
                                 "kalibreren.",
                "action+calibrating": " De E32 kalibreert de schatting zodra hij een paar gasmeterstanden heeft "
                                      "gezien.",
                "action+rough": " Zonder het vermogen van je ketel is dit maar een ruwe schatting: stel het in "
                                "onder Energie en buitentemperatuur.",
                "where": "Home Assistant: OpenThermostat → Configureren → Ruimtes → het weekprogramma van de "
                         "ruimte.",
            },
            "dhw_high": {
                "title": "Warm water heter dan nodig",
                "observed": "De gekozen warmwatertemperatuur is {dhw} °C.",
                "observed+disinfection": " Wekelijkse desinfectie: {disinfection} °C.",
                "why": "Elke graad boven ongeveer 55 °C kost gas om het water warm te houden, geeft meer kalk en "
                       "een groter risico op verbranden.",
                "action": "Zet de warmwatertemperatuur op {suggest} °C. Laat bij een warmwaterboiler de wekelijkse "
                          "desinfectie (thermische legionellabescherming) van de ketel aan staan.",
                "where": "Ketelscherm (warmwatertemperatuur) of de warmwaterinstelling van je thermostaat.",
            },
            "dhw_low": {
                "title": "Warm water onder 50 °C",
                "observed": "De gekozen warmwatertemperatuur is {dhw} °C.",
                "observed+disinfection": " Wekelijkse desinfectie: {disinfection} °C.",
                "why": "Legionellabacteriën kunnen groeien in stilstaand water tussen ongeveer 25 en 50 °C. Bij een "
                       "combiketel zonder voorraadvat is het risico klein; met een warmwaterboiler telt het wel.",
                "action": "Zet bij een warmwaterboiler minstens {suggest} °C of zorg dat de wekelijkse desinfectie "
                          "draait (60 °C of meer). Bij een combiketel zonder voorraadvat kun je deze instelling "
                          "houden.",
                "where": "Ketelscherm (warmwatertemperatuur) of de warmwaterinstelling van je thermostaat.",
            },
            "pressure_low": {
                "title": "Waterdruk laag",
                "observed": "De waterdruk is al minstens {minutes} min {pressure} bar.",
                "why": "Onder ongeveer 1 bar kan de ketel in storing gaan en kan er lucht in de hoogste radiatoren "
                       "komen.",
                "action": "Vul de installatie bij via de vulkraan tot 1,5–2,0 bar (met de installatie koud). Moet "
                          "je vaak bijvullen, zoek dan een lek of laat het expansievat nakijken.",
                "where": "Vulkraan of vulslang bij de ketel.",
            },
            "pressure_high": {
                "title": "Waterdruk hoog",
                "observed": "De waterdruk is al minstens {minutes} min {pressure} bar.",
                "why": "Bij ongeveer 3 bar gaat het overstortventiel open. Een hoge druk als de installatie warm "
                       "is, betekent meestal dat het expansievat zijn voordruk kwijt is.",
                "action": "Laat het expansievat en het overstortventiel nakijken. Koud hoort de druk 1,5–2,0 bar "
                          "te zijn; is hij koud veel hoger, laat dan wat water weglopen bij een radiator.",
                "where": "Expansievat en overstortventiel bij de ketel (installateur).",
            },
            "pump_run_on_long": {
                "title": "Pomp draait lang na",
                "observed": "De pompnaloop van de ketel is {run_on} min.",
                "why": "Vloerverwarming heeft meestal een eigen pomp bij de verdeler; een lange naloop van de "
                       "ketelpomp kost dan vooral stroom en pompt lauw water rond nadat de warmtevraag stopte.",
                "action": "Verkort de pompnaloop tot ongeveer 3–5 min.",
                "where": "Servicemenu van de ketel (installateursniveau).",
            },
            "pump_run_on_short": {
                "title": "Pomp stopt vlak na de brander",
                "observed": "De pompnaloop van de ketel is {run_on} min terwijl de brander pendelt.",
                "why": "Stopt de pomp direct na de brander, dan blijft de restwarmte in de ketel en is hij snel "
                       "weer warm; dat versterkt het pendelen.",
                "action": "Verleng de pompnaloop tot ongeveer 3–5 min.",
                "where": "Servicemenu van de ketel (installateursniveau).",
            },
            "boiler_power_missing": {
                "title": "Stel het ketelvermogen in voor betere schattingen",
                "observed": "De E32 schat warmte en gas uit de brandermodulatie met een standaard ketelvermogen, "
                            "omdat er geen is ingesteld.",
                "why": "De aanvoer- en nachtschattingen schalen met het ketelvermogen; een verkeerd vermogen geeft "
                       "een verkeerde besparing.",
                "action": "Vul het nominale verwarmingsvermogen van de ketel in kW in (op het typeplaatje of in de "
                          "handleiding).",
                "where": "Home Assistant: OpenThermostat → Configureren → Energie en buitentemperatuur.",
            },
        },
        "missing": {
            "no_burner_count": "De E32 meldt nog geen branderstarts (vereist E32-firmware die ze telt).",
            "no_max_ch": "De ketel meldt zijn maximale cv-temperatuur niet.",
            "few_days": "Vereist minstens {needed} dagen met verwarming; tot nu toe {days}.",
            "no_return": "De ketel meldt geen retourtemperatuur tijdens verwarmen.",
            "few_heating": "Vereist minstens 1 uur verwarmen met een retourtemperatuur.",
            "no_learning": "De E32 meldt geen geleerde ruimtes (vereist E32-firmware die leert).",
            "not_learned": "Nog geen ruimte is uitgeleerd.",
            "no_plans": "De E32 heeft nog geen nachtschatting (vereist een betrouwbare klok en geleerde ruimtes).",
            "no_dhw": "De ketel meldt zijn warmwatertemperatuur niet.",
            "no_pressure": "De ketel meldt zijn waterdruk niet.",
            "no_pump_run_on": "De ketel meldt zijn pompnaloop niet.",
        },
    },
}
FIELDS = ("title", "observed", "why", "action", "where")


def language(hass):
    """Dutch for a Dutch Home Assistant, English otherwise (like the dashboard)."""
    value = (getattr(hass.config, "language", None) or "en").lower().replace("_", "-")
    return "nl" if value.split("-")[0] == "nl" else "en"


def fmt(value, lang):
    if type(value) is float:
        text = f"{value:g}"
    elif type(value) is int:
        text = str(value)
    else:
        return "?" if value is None else str(value)
    return text.replace(".", ",") if lang == "nl" else text


def render(item, lang):
    """One advice item in a language: the texts with their placeholders filled."""
    template = TEXT[lang]["rules"][item["rule"]]
    values = {key: fmt(value, lang) for key, value in item["values"].items()}
    result = {"id": item["id"], "severity": item["severity"]}
    for field in FIELDS:
        text = template[field]
        for part in item["parts"]:
            text = template.get(f"{field}@{part}", text)
        for part in item["parts"]:
            text += template.get(f"{field}+{part}", "")
        result[field] = text.format(**values)
    result["confidence"] = item["confidence"]
    return result


def render_missing(name, missing, lang):
    values = {key: fmt(value, lang) for key, value in missing.values.items()}
    return {"id": name, "reason": TEXT[lang]["missing"][missing.reason].format(**values)}


# -- samples from Home Assistant --------------------------------------------------


def boiler_field(client, name, low, high):
    """A usable boiler field value (boiler-fields cache), or None."""
    cache = getattr(client, "boiler_fields", None)
    if (not isinstance(cache, BoilerFieldCache) or not getattr(client, "ready", False)
            or not getattr(client, "boiler_fields_supported", False)):
        return None
    reading = cache.reading(INDEX[name], client.clock())
    if not reading or not reading["usable"] or reading["raw"] is None:
        return None
    _, unit, divisor, _ = spec(INDEX[name])
    if unit == "bool":
        return bool(reading["raw"])
    value = reading["raw"] / divisor
    return value if low <= value <= high else None


def _either(client, names, low, high):
    for name in names:
        if (value := boiler_field(client, name, low, high)) is not None:
            return value
    return None


def boiler_maximum(client):
    """The boiler's own maximum heating temperature (°C, its 0x16 telegram), or None when not reported.

    A knob on some boilers (the boiler reports its position), a menu or app
    setting on others: the real ceiling of every flow request either way.
    """
    value = _either(client, ("configured_heating_temperature", "plus_heating_temperature"), 20, 95)
    return round(value) if value is not None else None


def take_sample(hub, client, now):
    """One five-minute sample: the boiler fields and the E32 telemetry that the rules read."""
    from .heating_link import _count, burner_status, flow_advice, number
    sample = {"t": now,
              "fl": _either(client, ("measured_flow_temperature", "plus_flow_temperature"), 5, 95),
              "rn": _either(client, ("measured_return_temperature", "plus_return_temperature"), 5, 95),
              "ha": boiler_field(client, "heating_active", 0, 1),
              "da": _either(client, ("dhw_active", "plus_dhw_valve"), 0, 1),
              "p": _either(client, ("pressure", "plus_pressure"), 0, 6),
              "dw": _either(client, ("selected_dhw_temperature", "plus_dhw_selected_temperature"), 30, 85),
              "mx": _either(client, ("configured_heating_temperature", "plus_heating_temperature"), 20, 95),
              "rt": boiler_field(client, "thermostat_requested_flow_temperature", 0, 100),
              "mb": boiler_field(client, "minimum_burner_period", 0, 120),
              "hn": boiler_field(client, "heating_hysteresis_on", -30, 30),
              "hf": boiler_field(client, "heating_hysteresis_off", -30, 30),
              "pr": boiler_field(client, "pump_run_on", 0, 1440),
              "ds": boiler_field(client, "dhw_disinfection_temperature", 40, 90)}
    if hub is not None and hub.fresh:
        status = hub.status
        request = status["request"]
        sample["re"] = request["flow_c"] if request["heat"] else 0
        burner = burner_status(status) or {}
        sample["sc"] = burner.get("short_cycling") if type(burner.get("short_cycling")) is bool else None
        sample["hs"] = _count(burner.get("heating_starts_last_hour"))
        sample["ap"] = (hub.learned_header or {}).get("applied") is True
        rooms = {}
        for room_id, learned in hub.learned.items():
            items = learned.get("advice")
            advice_one = next((a for a in (flow_advice(item) for item in items) if a and a["shortfall_c"] == 1),
                              None) if type(items) is list else None
            rooms[room_id] = {"r": learned.get("readiness"), "rule": (advice_one or {}).get("rule"),
                              "need": (advice_one or {}).get("flow_c"), "rf": (advice_one or {}).get("rule_flow_c")}
        sample["rooms"] = rooms
        nights = {}
        for room_id, plan in hub.warmup.items():
            night = plan.get("night") if type(plan.get("night")) is dict else {}
            if night.get("reason") != "estimated":
                continue
            nights[room_id] = {"c": number(night.get("recommended_night_c", night.get("recommended_c")), 5, 30),
                               "m3": number(night.get("saving_m3"), 0, 100),
                               "eur": number(night.get("saving_eur"), 0, 1000),
                               "name": night.get("recommended") if type(night.get("recommended")) is str else None,
                               "conf": night.get("confidence") if type(night.get("confidence")) is str else None}
        sample["nights"] = nights
    return {key: value for key, value in sample.items() if value is not None}


def floor_present(hub):
    """Whether any room (learned, planned or reported) is floor heating."""
    if hub is None:
        return False
    rooms = list(hub.learned.values()) + list(hub.rooms.values())
    plan = getattr(hub.plan, "plan", None) if hub.plan is not None else None
    if type(plan) is dict and type(plan.get("rooms")) is list:
        rooms += [room for room in plan["rooms"] if type(room) is dict]
    return any(room.get("emitter") == "floor" for room in rooms)


def plan_max_flow(hub):
    plan = getattr(hub.plan, "plan", None) if hub is not None and hub.plan is not None else None
    value = plan.get("maximum_flow_c") if type(plan) is dict else None
    return value if type(value) in (int, float) and not type(value) is bool and 20 <= value <= 90 else None


class AdviceHistory:
    """The bounded window of samples (24 h, memory) and per-day aggregates (14 days, restored)."""

    def __init__(self):
        self.samples = []
        self.days = {}

    def add(self, sample, day):
        self.samples.append(sample)
        cutoff = sample["t"] - HISTORY_SECONDS
        self.samples = [s for s in self.samples if s["t"] > cutoff][-MAX_SAMPLES:]
        aggregate = self.days.setdefault(day.isoformat(), {"n": 0, "heat": 0, "max": None})
        aggregate["n"] += 1
        requests = [sample[key] for key in ("re", "rt") if sample.get(key) is not None]
        peak = max(requests, default=None)
        if peak is not None and peak >= HEAT_REQUEST_C:
            aggregate["heat"] += 1
            aggregate["max"] = peak if aggregate["max"] is None else max(aggregate["max"], peak)
        for key in sorted(self.days)[:-DAYS_KEPT]:
            del self.days[key]

    def export(self):
        return {"schema": 1, "days": {key: dict(value) for key, value in self.days.items()}}

    def restore(self, data):
        days = data.get("days") if type(data) is dict and data.get("schema") == 1 else None
        for key, value in (days.items() if type(days) is dict else ()):
            try:
                date.fromisoformat(key)
            except (TypeError, ValueError):
                continue
            if (type(value) is dict and type(value.get("n")) is int and type(value.get("heat")) is int
                    and (value.get("max") is None or type(value["max"]) in (int, float))):
                self.days[key] = {"n": value["n"], "heat": value["heat"], "max": value["max"]}
        for key in sorted(self.days)[:-DAYS_KEPT]:
            del self.days[key]


class AdviceStoredData(ExtraStoredData):
    def __init__(self, data):
        self.data = data

    def as_dict(self):
        return self.data


class HeatingAdviceSensor(RestoreEntity, SensorEntity):
    """The current heating advice: state = number of items; attribute ``items``. Advice only."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "heating_advice"
    # The texts are shown, not kept in the history.
    _unrecorded_attributes = frozenset({"items", "not_evaluated", "weekly_summary"})

    def __init__(self, entry, hub, connection, clock=time.time, local_date=None):
        self.entry, self.hub, self.connection, self.clock = entry, hub, connection, clock
        self._local_date = local_date
        self._attr_unique_id = f"{hub.prefix}_hub_heating_advice"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.prefix)})
        self.history = AdviceHistory()
        self.items, self.missing, self.since = [], [], {}
        self._last = None
        self._started = clock()

    # -- evaluation ---------------------------------------------------------

    def _today(self, now):
        if self._local_date is not None:
            return self._local_date(now)
        from homeassistant.util import dt as dt_util
        return dt_util.as_local(datetime.fromtimestamp(now, timezone.utc)).date()

    def context(self, now):
        options = energy_options(self.entry)
        names = {}
        from .heating_link import label, learned_inputs
        for room_id, room in self.hub.rooms.items():
            names[room_id] = label(room)
        hass = getattr(self, "hass", None)
        header = self.hub.learned_header if self.hub.fresh else None
        source = learned_inputs(header).get("boiler_kw_source")
        return {"today": self._today(now), "days": self.history.days, "floor": floor_present(self.hub),
                "max_flow": plan_max_flow(self.hub), "names": names,
                "gas_meter": CONF_GAS_METER in options, "kwh_per_m3": kwh_per_m3(options),
                "price": gas_price(hass, options) if hass is not None else None,
                "currency": currency(hass) if hass is not None else "EUR",
                "boiler_kw": options.get(CONF_BOILER_KW),
                "boiler_kw_source": source if source in ("default", "ha") else None,
                "learning": header is not None or bool(self.hub.learned) or bool(self.hub.warmup)}

    @callback
    def sample(self):
        """Take one sample and evaluate the rules again."""
        now = self.clock()
        self._last = now
        self.history.add(take_sample(self.hub, getattr(self.connection, "client", None), now), self._today(now))
        self.reevaluate()

    @callback
    def reevaluate(self):
        now = self.clock()
        items, missing = evaluate(self.history.samples, self.context(now))
        ids = {item["id"] for item in items}
        self.since = {key: value for key, value in self.since.items() if key in ids}
        for item in items:
            self.since.setdefault(item["id"], now)
        self.items, self.missing = items, missing
        self._sync_issue()
        if getattr(self, "hass", None) is not None and self.entity_id:
            self.async_write_ha_state()

    @callback
    def _maybe_sample(self, _now=None):
        now = self.clock()
        first = self._last is None and (self.hub.fresh or now - self._started >= 60)
        if first or (self._last is not None and now - self._last >= SAMPLE_SECONDS - 5):
            self.sample()

    @callback
    def _sync_issue(self):
        hass = getattr(self, "hass", None)
        if hass is None:
            return
        issue_id = f"{PRESSURE_ISSUE}_{self.entry.entry_id}"
        low = next((item for item in self.items if item["id"] == "pressure_low"), None)
        if low is None:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False,
                              severity=ir.IssueSeverity.WARNING, translation_key=PRESSURE_ISSUE,
                              translation_placeholders={"pressure": fmt(low["values"]["pressure"],
                                                                        language(hass))})

    # -- entity -------------------------------------------------------------

    @property
    def native_value(self):
        return len(self.items)

    @property
    def extra_state_attributes(self):
        lang = language(self.hass) if getattr(self, "hass", None) is not None else "en"
        items = []
        for item in self.items:
            rendered = render(item, lang)
            rendered["since"] = datetime.fromtimestamp(self.since.get(item["id"], self.clock()),
                                                       timezone.utc).isoformat(timespec="seconds")
            items.append(rendered)
        return {"items": items, "not_evaluated": [render_missing(name, missing, lang) for name, missing in self.missing],
                "advice_only": True, "observed_hours": round(len(self.history.samples) * SAMPLE_SECONDS / 3600, 1),
                "observed_days": len(self.history.days),
                "weekly_summary": self.weekly_summary(lang, [item["title"] for item in items])}

    def weekly_summary(self, lang, titles):
        """The last seven days for the weekly notification (blueprint weekly_summary.yaml)."""
        from .weekly_summary import weekly_summary
        hass = getattr(self, "hass", None)
        use = hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get("energy_use") if hass is not None else None
        records = use.data["days"] if use is not None else {}
        options = energy_options(self.entry)
        return weekly_summary(records, self._today(self.clock()), titles, lang,
                              unit=use.unit if use is not None else "m³",
                              rough=use is not None and not use.power()[1],
                              price=gas_price(hass, options) if hass is not None else None,
                              currency=currency(hass) if hass is not None else "EUR")

    @property
    def extra_restore_state_data(self):
        return AdviceStoredData(self.history.export())

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        stored = await self.async_get_last_extra_data()
        if stored is not None:
            self.history.restore(stored.as_dict())
        self.async_on_remove(async_track_time_interval(self.hass, self._maybe_sample, timedelta(seconds=60)))
        self.async_on_remove(self.hub.add_listener(self._maybe_sample))
        self.reevaluate()

    async def async_will_remove_from_hass(self):
        ir.async_delete_issue(self.hass, DOMAIN, f"{PRESSURE_ISSUE}_{self.entry.entry_id}")
        await super().async_will_remove_from_hass()


async def async_setup_heating_advice(hass, entry, async_add_entities, options, hub, connection):
    """Product entries: the advice sensor on the product device; the entity reaches the entry state."""
    sensor = HeatingAdviceSensor(entry, hub, connection)
    hass.data[DOMAIN][entry.entry_id]["heating_advice"] = sensor
    async_add_entities([sensor], **options)
    # Gas for heating and for hot water (Energy dashboard); its sensors appear once the boiler reports.
    from .energy_use import async_setup_energy_use
    await async_setup_energy_use(hass, entry, async_add_entities, options, hub, connection)
