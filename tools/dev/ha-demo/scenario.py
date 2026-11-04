"""The demo house: what the fake E32 reports and the last 24 hours behind it.

A Dutch house like the owner's (E32 in control, "active"): the living room (floor heating, a tado-style HA
thermostat plus a Bluetooth thermometer) switched on at 20.4 °C aiming at 21 °C; two radiator rooms
switched off; a Nefit EcomLine-type boiler on the EMS bus (the owner's field set: no pressure, no counters,
no DHW flow). The values follow the firmware's own documents (rc.5 telemetry, the shapes of
ha/tests_native/e32_telemetry.py and the E32 web API), with invented but plausible numbers. Nothing here
comes from a real installation.

Everything is computed from one deterministic timeline (Timeline), so the current documents, the history
written into the recorder and the statistics agree with each other.
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Amsterdam")
PREFIX = "openthermostat"
CONTROLLER_ID = "e32_0c8b95d1a2f4"
FIRMWARE = "v1.0.0-e32v2-rc.5"
SOURCE = "5d1e0c4b9a8f7e6d5c4b3a291807f6e5d4c3b2a1"
SHA256 = "3f6c2b1a9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b"
WEB_SHA256 = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
BLE_LIVING = "a4c1380d5e21"
TADO = "climate.tado_woonkamer"
BATHROOM_THERMOSTAT = "climate.thermostaat_badkamer"
OUTDOOR = "sensor.buitentemperatuur"

COMFORT, ECO, NIGHT = 2100, 1950, 1850
# Weather compensation: the standard line reaches 50 °C at -10 °C outside; the house learned a flatter one.
DESIGN_FLOW_C, SLOPE = 50, 0.85
REQUEST_NOW, STARTS_TODAY = 42, 14


def curve_flow(outdoor, room=21.0):
    """The learned line: water = room + slope x (room - outdoor), within 30..60 °C (the plan's limits)."""
    return min(60.0, max(30.0, room + SLOPE * max(0.0, room - outdoor)))
# Monday first (RoomSchedule.h: (tm_wday + 6) % 7). Weekdays up at 06:30, the weekend at 08:00.
WEEKDAY = [[0, NIGHT], [390, COMFORT], [1350, NIGHT]]
WEEKEND = [[0, NIGHT], [480, COMFORT], [1380, NIGHT]]
LIVING_PROGRAM = [WEEKDAY] * 5 + [WEEKEND] * 2
BATH_PROGRAM = [[[0, 1700], [375, 2150], [465, 1700], [1170, 2050], [1290, 1700]]] * 7
SLEEP_PROGRAM = [[[0, 1600], [1290, 1750], [1410, 1600]]] * 7


def plan_document(revision=3, mode="active"):
    """GET /config/heating: the E32 room plan (plan.levels.v1)."""
    def room(room_id, name, state, emitter, sources, setpoint_entity, schedule, levels):
        doc = {"id": room_id, "name": name, "state": state, "inactive_until": 0, "emitter": emitter,
               "sources": sources, "setpoint_entity": setpoint_entity, "fallback_centi_c": 2000,
               "minimum_centi_c": 500, "maximum_centi_c": 2500, "schedule": schedule}
        if levels:
            doc["levels"] = levels
            doc["schedule_levels"] = ".".join("".join(
                next((str(n + 1) for n, key in enumerate(("comfort", "eco", "night")) if levels[key] == t), "0")
                for _, t in day) for day in schedule)
        return doc
    return {"schema": 1, "revision": revision, "mode": mode, "minimum_flow_c": 30, "maximum_flow_c": 60,
            "features": ["plan.levels.v1"],
            "rooms": [
                room("woonkamer", "Woonkamer", "active", "floor",
                     [{"type": "ha", "id": TADO}, {"type": "ble", "id": BLE_LIVING}], TADO, LIVING_PROGRAM,
                     {"comfort": COMFORT, "eco": ECO, "night": NIGHT}),
                room("badkamer", "Badkamer", "inactive", "radiator", [{"type": "ha", "id": BATHROOM_THERMOSTAT}],
                     "", BATH_PROGRAM, None),
                room("slaapkamer", "Slaapkamer", "inactive", "radiator", [{"type": "ble", "id": "a4c1380d7b90"}],
                     "", SLEEP_PROGRAM, None),
            ]}


def program_target(local):
    """The living room's program temperature (°C) at a local time."""
    day = LIVING_PROGRAM[local.weekday()]
    minute = local.hour * 60 + local.minute
    target = day[0][1]
    for at, value in day:
        if minute >= at:
            target = value
    return target / 100


def next_switch(local):
    """(local datetime, target °C) of the living room's next program switch."""
    for days in range(0, 8):
        d = (local + timedelta(days=days)).date()
        for at, value in LIVING_PROGRAM[d.weekday()]:
            when = datetime(d.year, d.month, d.day, at // 60, at % 60, tzinfo=ZONE)
            if when > local and value / 100 != program_target(local):
                return when, value / 100
    return local + timedelta(hours=8), COMFORT / 100


class Timeline:
    """The house minute by minute, from 30 hours before ``now`` to ``now`` (UTC, whole minutes)."""

    def __init__(self, now=None, hours=30):
        now = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
        self.now = now
        self.start = now - timedelta(hours=hours)
        self.rng = random.Random(now.date().toordinal())
        self.minutes = int((now - self.start).total_seconds() // 60) + 1
        self.t = [self.start + timedelta(minutes=i) for i in range(self.minutes)]
        self.local = [t.astimezone(ZONE) for t in self.t]
        self._simulate()

    def _outdoor(self, local):
        hour = local.hour + local.minute / 60
        return round(4.0 + 3.0 * math.sin((hour - 9.0) / 24 * 2 * math.pi) + 0.15 * math.sin(hour * 3.1), 1)

    def _simulate(self):
        n, rng = self.minutes, self.rng
        self.outdoor = [self._outdoor(x) for x in self.local]
        self.target = [program_target(x) for x in self.local]
        # The hot-water day: taps (minutes) and the boiler keeping its 25 l store warm.
        taps = [(7, 5, 9), (7, 32, 2), (8, 10, 1), (12, 40, 1), (13, 15, 2), (18, 10, 4), (19, 45, 1), (21, 15, 6)]
        keep = [(1, 20), (3, 50), (5, 55), (10, 35), (15, 20), (17, 5), (23, 40)]
        self.dhw_kind = [None] * n
        for i, x in enumerate(self.local):
            for h, m, length in taps:
                if 0 <= (x.hour * 60 + x.minute) - (h * 60 + m) < length:
                    self.dhw_kind[i] = "tapping"
            for h, m in keep:
                if 0 <= (x.hour * 60 + x.minute) - (h * 60 + m) < 3:
                    self.dhw_kind[i] = "keep_warm"
        # The living room: floor heating, a smart warm-up before each comfort switch, a dip shortly before now.
        temp, heating = [0.0] * n, [False] * n
        t, on = 20.9, False
        for i, x in enumerate(self.local):
            target = self.target[i]
            switch, switch_target = next_switch(x)
            lead = (switch - x).total_seconds() / 60
            warm_up = switch_target > target and lead <= 150 and t < switch_target - 0.1
            if warm_up:
                on = True
            elif t < target - 0.2:
                on = True
            elif t > target + 0.1 or (target < 20 and not warm_up):
                on = False
            rise = 0.75 if self.dhw_kind[i] is None else 0.3
            fall = 0.22 + 0.01 * (8 - self.outdoor[i])
            t += (rise if on else -fall) / 60 + rng.uniform(-0.004, 0.004)
            temp[i], heating[i] = t, on
        # The last hour: a window was open for a while; heating again since 25 minutes, 20.4 °C now.
        dip0, dip1, heat0 = n - 75, n - 50, n - 25
        base = temp[dip0]
        for i in range(dip0, n):
            if i < dip1:
                temp[i] = base - 0.035 * (i - dip0)
                heating[i] = False
            elif i < heat0:
                temp[i] = temp[dip1 - 1] - 0.004 * (i - dip1)
                heating[i] = False
            else:
                temp[i] = temp[heat0 - 1] + (20.4 - temp[heat0 - 1]) * (i - heat0 + 1) / (n - heat0)
                heating[i] = True
        self.room = [round(v, 2) for v in temp]
        self.room[-1] = 20.4
        self.heating = heating
        # What the boiler does: hot water first (priority), else heating, else idle.
        self.activity = [self.dhw_kind[i] or ("heating" if heating[i] else "idle") for i in range(n)]
        flow, ret, mod, dhw = [], [], [], []
        f, r, w = 32.0, 28.0, 58.0
        for i in range(n):
            a = self.activity[i]
            if a == "heating":
                want = curve_flow(self.outdoor[i]) + 3.5 + rng.uniform(-0.6, 0.6)
                f += (want - f) * 0.25
                r += ((f - 8.0) - r) * 0.2
                m = 30 + 2.0 * (8 - self.outdoor[i]) + rng.uniform(-3, 3)
            elif a in ("tapping", "keep_warm"):
                f += (68.0 - f) * 0.3
                r += (46.0 - r) * 0.25
                m = 78 + rng.uniform(-8, 8)
            else:
                f += (self.room[i] + 6 - f) * 0.04
                r += (self.room[i] + 3 - r) * 0.04
                m = 0
            if a == "tapping":
                w += (44.0 - w) * 0.25
            elif a == "keep_warm":
                w += (60.0 - w) * 0.35
            else:
                w -= 0.012
            flow.append(round(f, 1))
            ret.append(round(r, 1))
            mod.append(int(max(0, min(100, m))))
            dhw.append(round(w, 1))
        # Now: water 41 °C to the floor, 33 °C back.
        flow[-1], ret[-1] = 41.0, 33.0
        mod[-1] = 38
        self.flow, self.ret, self.mod, self.dhw = flow, ret, mod, dhw
        # The E32's request: the learned water temperature while the room heats.
        self.request = [round(curve_flow(self.outdoor[i]) + 4.5) if heating[i] else 0 for i in range(n)]
        self.request[-1] = REQUEST_NOW

    # -- figures of today ---------------------------------------------------------------------------------
    def today_index(self):
        midnight = self.now.astimezone(ZONE).replace(hour=0, minute=0)
        return max(0, int((midnight.astimezone(timezone.utc) - self.start).total_seconds() // 60))

    def starts_since(self, i0):
        """Burner starts from index i0: every change from idle to burning."""
        count, burning = 0, False
        for a in self.activity[i0:]:
            now = a != "idle"
            if now and not burning:
                count += 1
            burning = now
        return count

    def changes(self, series, i0=0):
        """(UTC time, value) at i0 and at every change after it."""
        out, last = [], object()
        for i in range(i0, self.minutes):
            if series[i] != last:
                out.append((self.t[i], series[i]))
                last = series[i]
        return out


# -- the E32's documents --------------------------------------------------------------------------------
def room_documents(tl, mode):
    now_local = tl.now.astimezone(ZONE)
    switch, switch_target = next_switch(now_local)
    program = program_target(now_local)
    if program >= 21:
        comfort = {"mode": "program", "target_c": 21.0, "until": int(switch.timestamp()), "override": "none"}
    else:  # a run at night: the living room was set to 21 °C until its next switch
        comfort = {"mode": "temporary", "target_c": 21.0, "until": int(switch.timestamp()), "override": "temporary"}
    living = {"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0,
              "fallback_centi_c": 2000, "minimum_centi_c": 500, "maximum_centi_c": 2500, "status": "ok",
              "source": TADO, "temperature": 20.4, "setpoint": 21.0, "setpoint_source": "schedule",
              "demand": True, "comfort": comfort}
    off = {"state": "inactive", "inactive_until": 0, "fallback_centi_c": 2000, "minimum_centi_c": 500,
           "maximum_centi_c": 2500, "status": "inactive", "source": None, "temperature": None, "setpoint": None,
           "setpoint_source": "fallback", "demand": False}
    return [living, {"id": "badkamer", "name": "Badkamer", **off}, {"id": "slaapkamer", "name": "Slaapkamer", **off}]


def heating_status(tl, mode="active", uptime_s=86000):
    """The compact /status/heating the E32 splits into its fw/state and fw/config topics."""
    i = tl.minutes - 1
    activity = tl.activity[i]
    starts_hour = tl.starts_since(max(0, i - 59))
    status = {
        "schema": 1, "revision": 3, "mode": mode,
        "request": {"heat": True, "flow_c": tl.request[i], "reason": "heating", "capped_by": None},
        "ha_entities": [TADO, BATHROOM_THERMOSTAT],
        "rooms": room_documents(tl, mode),
        "away": {"on": False, "source": "none", "target_c": 15, "until": None, "presence": "unknown",
                 "mode": "auto", "holidays": [], "holiday_temperature_c": 15},
        "ble_sensors": [
            {"id": BLE_LIVING, "name": "Thermometer woonkamer", "profile": "pvvx_thermometer",
             "temperature": 20.46, "humidity": 52.8, "battery": 100, "age_s": 21},
            {"id": "a4c1380d7b90", "name": "Thermometer slaapkamer", "profile": "pvvx_thermometer",
             "temperature": 17.62, "humidity": 58.4, "battery": 83, "age_s": 47}],
        "burner": {"starts_last_hour": starts_hour, "heating_starts_last_hour": max(0, starts_hour - 1),
                   "short_cycling": False, "activity": activity},
        "ha": {"input_age_s": 18, "broker_connected": True},
    }
    if mode == "active":
        status["active"] = {"state": "heating", "awaiting_confirmation": False,
                            "command": {"send": True, "flow_c": tl.request[i], "why": "heating"},
                            "last_sent": {"flow_c": tl.request[i], "age_s": 24}, "foreign_controller": None,
                            "confirmation": None, "warnings": [], "enabled": True, "confirmation_stored": True,
                            "thermostat_seen": False, "taken_over_before": True, "reconfirm_required": False,
                            "boiler_limit": {"flow_c": 75, "age_s": 300, "reads": 12}}
    return status


def learned_room(tl):
    """fw/telemetry/learned/woonkamer: the living room learned (floor), its warm-up plan and free heat."""
    now_local = tl.now.astimezone(ZONE)
    switch, target = next_switch(now_local)
    if target < 21:  # the next switch lowers the room: plan the comfort switch after it
        later, later_target = next_switch(switch + timedelta(minutes=1))
        switch, target = later, later_target
    start = switch - timedelta(minutes=165)
    return {"schema": 1, "id": "woonkamer",
            "learned": {"emitter": "floor", "readiness": "ready", "readiness_timing": "ready", "segments": 41,
                        "periods": 38, "loss_per_h": 0.0176, "capacity_kwh_per_k": 26.4,
                        "advice": [{"shortfall_c": 1, "required_c_per_h": 0.5, "flow_c": 42, "warmup_h": 1.9,
                                    "reason": "learned", "rule_flow_c": 40, "rule_warmup_h": 2.2,
                                    "rule": "lower_too_slow"}],
                        "now": {"shortfall_c": 0.6, "required_c_per_h": 0.3, "flow_c": 41, "warmup_h": 1.3,
                                "reason": "learned", "rule_flow_c": 38, "rule_warmup_h": 1.6, "rule": "agrees"},
                        "free_heat": {"rate": [1.2, 0.9, 0.6, 1.8, 2.4, 1.1], "n": [14, 12, 9, 16, 18, 11],
                                      "applied_min": 35}},
            "plan": {"optimum_start": {"reason": "planned", "next_switch": {"utc": int(switch.timestamp()),
                                                                             "target_c": target},
                                       "predicted_start_utc": int(start.timestamp()), "lead_minutes": 165,
                                       "flow_c": 44, "confidence": "learned", "reachable": True,
                                       "start_now": False, "applies": True, "estimate": False},
                     "night": {"reason": "estimated", "recommended": "program", "recommended_night_c": 18.5,
                               "saving_m3": 0.4, "saving_eur": 0.52},
                     "arrival": {"factor": 1.05, "events": 9, "last_error_min": 6,
                                 "last_at_utc": int((tl.now - timedelta(hours=14)).timestamp())}}}


def telemetry(tl, mode="active", uptime_s=86000, heat_today_s=None):
    """[(topic suffix, payload)] of the E32 now, all retained (the heartbeat is sent apart)."""
    from e32_split import split_status  # ha/tests_native/e32_telemetry.py, the firmware's split
    i0, i = tl.today_index(), tl.minutes - 1
    heating_s = 60 * sum(1 for a in tl.activity[i0:] if a == "heating")
    tap_count = sum(1 for k in range(i0 + 1, tl.minutes) if tl.dhw_kind[k] == "tapping" and tl.dhw_kind[k - 1] != "tapping")
    tap_s = 60 * sum(1 for k in range(i0, tl.minutes) if tl.dhw_kind[k] == "tapping")
    keep_count = sum(1 for k in range(i0 + 1, tl.minutes) if tl.dhw_kind[k] == "keep_warm" and tl.dhw_kind[k - 1] != "keep_warm")
    keep_s = 60 * sum(1 for k in range(i0, tl.minutes) if tl.dhw_kind[k] == "keep_warm")
    messages = [(suffix, doc) for suffix, doc in split_status(heating_status(tl, mode, uptime_s))]
    yesterday = (tl.now.astimezone(ZONE) - timedelta(days=1)).date().isoformat()
    today = tl.now.astimezone(ZONE).date().isoformat()
    summary = {"schema": 1,
               "learned": {"schema": 1, "applied": True, "status": "ready", "heating_periods": 38,
                           "inputs": {"gas_meter": False, "gas_price": False, "outdoor": "ha", "boiler_kw": 22,
                                      "boiler_kw_source": "ha", "gas_kwh_per_m3": 9.77,
                                      "gas_kwh_per_m3_source": "default"},
                           "gas": {"status": "estimate", "confidence": "low", "factor": 1, "kw_at_full_modulation": 22,
                                   "kw_source": "boiler_kw"}},
               "dhw": {"method": "dhw_temperature_fall", "clock_known": True,
                       "today": {"tapping": {"count": tap_count, "s": tap_s},
                                 "keep_warm": {"count": keep_count, "s": keep_s},
                                 "unknown": {"count": 0, "s": 0}, "charging": {"count": 0, "s": 0},
                                 "burner_s": tap_s + keep_s, "peak_flow_l_min": None}}}
    flow = {"schema": 1,
            "flow": {"curve": {"state": "applied", "flow_c": REQUEST_NOW, "base_c": round(curve_flow(tl.outdoor[i]), 1),
                               "slope": SLOPE, "slope_source": "learned", "design_flow_c": DESIGN_FLOW_C, "windows": 23},
                     "learned": {"state": "applied", "flow_c": REQUEST_NOW},
                     "source": "learned", "rule_flow_c": REQUEST_NOW - 2, "applied_flow_c": REQUEST_NOW, "ceiling_c": None,
                     "optimum_start": "applied",
                     "yesterday": {"rule_mean_c": 39.6, "applied_mean_c": 41.8, "curve_mean_c": 41.9,
                                   "learned_mean_c": 41.8}},
            "night_gas": {"nights": 6, "model_ratio": 1.04,
                          "last": {"switch_utc": int((tl.now - timedelta(hours=20)).timestamp()), "status": "measured",
                                   "heating_m3": 0.62, "hot_water_m3": 0.11, "predicted_program_m3": 0.6,
                                   "recommended": "program"}},
            "boiler": {"held": 0, "rest_s": 600, "ceiling_c": None, "absorbed_kw": 6.8, "kw_per_k": 0.42,
                       "state": "learned", "return": True}}
    tuning = {"schema": 1,
              "tuning": {"state": "applied",
                         "values": {"min_on_s": 900, "min_off_s": 900, "heat_start_c": 0.2, "heat_stop_c": 0.1,
                                    "flow_per_degree_c": 6, "curve_correction_pct": 96, "floor_lead_min_per_c": 140,
                                    "radiator_lead_min_per_c": 60, "learned_accept_pct": 100,
                                    "night_saving_min_pct": 20},
                         "manual": [], "yesterday": {"starts": 21, "heating_h": 7.4},
                         "today": {"starts": STARTS_TODAY, "heating_h": round(heating_s / 3600, 1)},
                         "would": [], "log": []}}
    scoreboard = {"schema": 1,
                  "scoreboard": {"yesterday": {"day": yesterday, "heating_h": 7.4, "heating_starts_per_h": 2.8,
                                               "short_cycle_h": 0, "heating_kwh": 27.4, "degree_days": 14.2,
                                               "rooms": [{"id": "woonkamer", "on_time_min": 4, "overshoot_c": 0.2}]},
                                 "today": {"day": today, "heating_h": round(heating_s / 3600, 1),
                                           "heating_starts_per_h": 2.5, "short_cycle_h": 0,
                                           "heating_kwh": 15.8, "degree_days": 13.6}}}
    insight = {"schema": 1,
               "knowledge": {"pct": 78, "missing": ["night:woonkamer", "curve:cold"], "more": 0},
               "house": {"ua_kw_per_k": 0.21, "kw_per_flow_k": 0.42, "slope": SLOPE, "state": "learned"},
               "boiler": {"held": 0, "rest_s": 600, "ceiling_c": None, "absorbed_kw": 6.8, "kw_per_k": 0.42,
                          "state": "learned", "return": True},
               "insights": [{"kind": "warmup_faster", "pct": 12, "room": "woonkamer"},
                            {"kind": "night_saving", "pct": 6, "room": "woonkamer"}]}
    messages += [("fw/telemetry/summary", summary), ("fw/telemetry/flow", flow), ("fw/telemetry/tuning", tuning),
                 ("fw/telemetry/scoreboard", scoreboard), ("fw/telemetry/insight", insight),
                 ("fw/telemetry/learned/woonkamer", learned_room(tl))]
    if mode != "active":
        messages.append(("fw/telemetry/shadow", {"schema": 1, "today": None, "days": []}))
    messages += boiler_documents(tl, uptime_s)
    return [(suffix, doc if isinstance(doc, str) else json.dumps(doc, separators=(",", ":"))) for suffix, doc in messages]


# -- the boiler on the bus (boiler.fields.v1, the integration's own catalog in boiler_fields.py) ---------
# The owner's field set (EcomLine HRC behind an EasyControl adapter, dashboard spec: no pressure, no outdoor
# sensor, no counters, no DHW flow); in active mode no thermostat talks on the bus, so no thermostat_* fields.
SUPPORTED = [0, 1, 2, 4, 5, 10, 11, 12, 13, 14, 16, 17, 24, 25, 28, 29, 32, 40, 41, 52, 53, 54, 55, 56, 57,
             58, 59, 62]
NOT_FITTED = [3, 6, 15, 30, 31, 38, 39, 60]
_CATALOG = None


def catalog():
    """ha/config/custom_components/open_thermostat/boiler_fields.py (FIELDS, QUALITIES, GROUPS), loaded by path."""
    global _CATALOG
    if _CATALOG is None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[3] / "ha/config/custom_components/open_thermostat/boiler_fields.py"
        spec = importlib.util.spec_from_file_location("openthermostat_boiler_fields", path)
        _CATALOG = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CATALOG)
    return _CATALOG


def text_code(code):
    return (ord(code[0]) << 8) | ord(code[1])


def boiler_values(tl, i=None):
    """{field index: raw value} of the boiler at minute i (now by default), scaled as the E32 sends them."""
    i = tl.minutes - 1 if i is None else i
    a = tl.activity[i]
    burning = a != "idle"
    dhw = a in ("tapping", "keep_warm")
    return {0: (6000 if dhw else int(tl.request[i] * 100)) if burning else 0,
            1: int(tl.flow[i] * 100), 2: int(tl.ret[i] * 100), 4: tl.mod[i], 5: 100,
            10: 0b1011 if burning else 0, 11: 1 if a == "heating" else 0, 12: 1 if dhw else 0,
            13: 5500, 14: int(tl.dhw[i] * 100), 16: 1, 17: 1,
            24: text_code("=H" if dhw else "-H" if burning else "0H"), 25: 201 if dhw else 200 if burning else 203,
            28: 7500, 29: 5500, 32: 48 if burning else 0, 40: int((tl.flow[i] - 1.2) * 100),
            41: 64 if burning else 0, 52: 5, 53: 1, 54: 0, 55: 0, 56: 1, 57: 7000, 58: 1, 59: 1, 62: 3}


def boiler_documents(tl, uptime_s):
    cat = catalog()
    values = boiler_values(tl)
    ms = uptime_s * 1000
    seen = ms - 1500

    def row(index):
        if index in values:
            return [index, values[index], seen, cat.QUALITIES[index], cat.FIELDS[index][4]]
        if index in NOT_FITTED:  # the boiler answers, without this value
            return [index, None, seen, cat.QUALITIES[index], cat.FIELDS[index][4]]
        return [index, None, None, 0, 0]  # never observed
    docs = [("fw/config/boiler_profile", {
        "schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
        "supported": SUPPORTED, "not_fitted": NOT_FITTED,
        "not_reported": [f for f in range(len(cat.FIELDS)) if f not in SUPPORTED + NOT_FITTED],
        "settled": True, "display_model": "nefit-ecomline-classic-hrc-22h"})]
    for group in range(cat.GROUPS):
        indexes = range(group * cat.PER_GROUP, min(len(cat.FIELDS), group * cat.PER_GROUP + cat.PER_GROUP))
        docs.append((f"fw/state/boiler_fields/{group}", {"schema": 1, "group": group, "values": {
            "schema": 1, "sampled_at_ms": ms - 1000, "profile": "classic_observed",
            "fields": [row(index) for index in indexes]}}))
    main = [1, 2, 4, 11, 12, 14, 24, 25]
    docs.append(("fw/state/boiler", {"schema": 1, "values": {"schema": 1, "sampled_at_ms": ms - 800,
                                                              "profile": "classic_observed",
                                                              "fields": [row(index) for index in main]}}))
    return docs


def heartbeat(uptime_s):
    return json.dumps({"schema": 1, "uptime_s": uptime_s, "heap_free": 61200, "heap_min_free": 22400,
                       "heap_max_alloc": 40100, "cpu_deci_c": 452, "internal_min_free": 17000,
                       "mqtt": {"messages": 0, "bytes": 0, "queue_peak_bytes": 640, "latency_avg_ms": 2,
                                "latency_max_ms": 5, "rejected": 0, "telemetry_dropped": 0}}, separators=(",", ":"))
