"""The demo house's past in a stopped demo Home Assistant: 24 hours of states, 8 days of statistics.

Home Assistant has no API to record states in the past, so this writes the recorder's SQLite database the way
the recorder itself does (states, states_meta, state_attributes; statistics and statistics_short_term with
their statistics_meta and statistics_runs), plus the integration's own day stores (gas per post, burner
starts and burner time per day), all from the same scenario timeline as the fake E32's live documents. Only
for entities the integration already created (the first, short run of the demo), matched by unique id.

    python history.py <ha config dir> <entry id>        (Home Assistant must be stopped)
"""
import json
import math
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenario  # noqa: E402

PREFIX = scenario.PREFIX + "_"
# Days before today, oldest first: heating m³, tapping m³, keeping warm m³, burner starts, burner hours,
# missed comfort minutes (plausible November days for a 22 kW condensing boiler and a floor-heated room).
PAST = [(3.4, 0.27, 0.19, 22, 8.1, 0), (2.9, 0.22, 0.19, 19, 7.0, 6), (3.1, 0.31, 0.21, 20, 7.4, 0),
        (3.6, 0.25, 0.19, 24, 8.6, 12), (2.7, 0.21, 0.18, 18, 6.6, 0), (3.0, 0.28, 0.20, 21, 7.2, 0),
        (2.8, 0.24, 0.19, 21, 7.4, 4)]
TODAY_HEATING, TODAY_TAPPING, TODAY_KEEP, TODAY_STARTS = 1.62, 0.22, 0.16, scenario.STARTS_TODAY
HEAT_PROFILE = [0, 0, 0, 0, 1.2, 1.6, 1.8, 1.2, 0.8, 0.6, 0.5, 0.5, 0.4, 0.4, 0.4, 0.5, 0.6, 0.8, 0.9, 0.9, 0.8,
                0.7, 0.4, 0]
WATER_PROFILE = [0.1, 0.1, 0, 0.1, 0, 0.1, 0.3, 2.5, 1.0, 0.2, 0.2, 0.1, 0.6, 0.5, 0.2, 0.2, 0.2, 0.3, 1.0, 0.6,
                 0.4, 1.4, 0.3, 0.2]


def series(tl, unique):
    """The timeline value list for an entity of the integration (by unique id), or None."""
    values = scenario.boiler_values
    bv = None

    def field(index, scale=100):
        nonlocal bv
        if bv is None:
            bv = [values(tl, i) for i in range(tl.minutes)]
        return [round(v[index] / scale, 1) for v in bv]
    room = [round(v, 1) for v in tl.room]
    heating = tl.heating
    table = {
        "e32_room_woonkamer_temperature": lambda: room,
        "e32_room_woonkamer_setpoint": lambda: tl.target,
        "e32_room_woonkamer_demand": lambda: ["on" if h else "off" for h in heating],
        "e32_room_woonkamer_reason": lambda: ["heating" if h else "warm_enough" for h in heating],
        f"e32_ble_{scenario.BLE_LIVING}_temperature": lambda: [round(v + 0.06, 1) for v in tl.room],
        f"e32_ble_{scenario.BLE_LIVING}_humidity": lambda: [round(53 + 1.2 * math.sin(i / 180), 1) for i in range(tl.minutes)],
        "hub_boiler_activity": lambda: tl.activity,
        "hub_heat_request": lambda: tl.request,
        "boiler_fields_v1_reported_selected_flow_temperature": lambda: field(0),
        "boiler_fields_v1_measured_flow_temperature": lambda: tl.flow,
        "boiler_fields_v1_measured_return_temperature": lambda: tl.ret,
        "boiler_fields_v1_reported_burner_modulation": lambda: tl.mod,
        "boiler_fields_v1_heating_active": lambda: ["on" if a == "heating" else "off" for a in tl.activity],
        "boiler_fields_v1_dhw_active": lambda: ["on" if a in ("tapping", "keep_warm") else "off" for a in tl.activity],
        "boiler_fields_v1_measured_dhw_temperature": lambda: tl.dhw,
        "boiler_fields_v1_selected_dhw_temperature": lambda: [55.0] * tl.minutes,
        "boiler_fields_v1_reported_dhw_target": lambda: [55.0] * tl.minutes,
    }
    make = table.get(unique)
    return make() if make else None


def text(value):
    if isinstance(value, float):
        return f"{value:.1f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    return str(value)


def write_states(db, tl, entities, extra):
    """[(entity id, values)] before the first state the demo's first run recorded for it."""
    written = 0
    for entity_id, values in entities + extra:
        meta = db.execute("select metadata_id from states_meta where entity_id=?", (entity_id,)).fetchone()
        if meta is None:
            continue
        metadata_id = meta[0]
        first = db.execute("select min(last_updated_ts) from states where metadata_id=?", (metadata_id,)).fetchone()[0]
        attributes = db.execute("select attributes_id from states where metadata_id=? and attributes_id is not null "
                                "order by state_id limit 1", (metadata_id,)).fetchone()
        end = (first - 1) if first else tl.now.timestamp()
        rows, last = [], None
        for when, value in tl.changes(values):
            ts = when.timestamp()
            if ts >= end or value is None:
                continue
            value = text(value)
            if value == last:
                continue
            rows.append((value, ts, ts, metadata_id, attributes[0] if attributes else None))
            last = value
        db.executemany("insert into states (state, last_updated_ts, last_changed_ts, metadata_id, attributes_id, "
                       "origin_idx) values (?, ?, ?, ?, ?, 0)", [(v, a, b, m, at) for v, a, b, m, at in rows])
        written += len(rows)
    return written


def hour_profile(tl, day_start, kinds):
    """Minutes per local hour of today with the boiler in one of kinds (from the timeline)."""
    minutes = [0] * 24
    for i, local in enumerate(tl.local):
        if tl.t[i] >= day_start and tl.activity[i] in kinds:
            minutes[local.hour] += 1
    return minutes


def spread(total, weights):
    s = sum(weights)
    return [total * w / s if s else 0 for w in weights]


def write_statistics(db, tl, units):
    """Hourly and 5-minute sum statistics for the gas, burner starts, burner time and missed comfort."""
    now_local = tl.now.astimezone(scenario.ZONE)
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    last_hour = tl.now.replace(minute=0)  # rows up to (not including) the hour that runs now
    # Per local hour of every day: increments of each statistic.
    increments = {key: {} for key in units}
    for back, (heat, tap, keep, starts, hours, missed) in enumerate(PAST):
        day = midnight - timedelta(days=len(PAST) - back)
        for h in range(24):
            when = day.replace(hour=h)
            for key, value in (("heating_gas", spread(heat, HEAT_PROFILE)[h]),
                               ("tapping_gas", spread(tap, WATER_PROFILE)[h]),
                               ("keep_warm_gas", spread(keep, [1] * 24)[h]),
                               ("daily_burner_starts", spread(starts, [w + 0.3 for w in HEAT_PROFILE])[h]),
                               ("daily_burner_time", spread(hours, HEAT_PROFILE)[h]),
                               ("daily_missed_comfort", missed if h == 6 else 0)):
                increments.setdefault(key, {})[when] = value
    day_start = midnight.astimezone(timezone.utc)
    heat_minutes = hour_profile(tl, day_start, ("heating",))
    tap_minutes = hour_profile(tl, day_start, ("tapping",))
    keep_minutes = hour_profile(tl, day_start, ("keep_warm",))
    burn_minutes = [a + b + c for a, b, c in zip(heat_minutes, tap_minutes, keep_minutes)]
    start_hours = [0] * 24
    for i in range(1, tl.minutes):
        if tl.t[i] >= day_start and tl.activity[i] != "idle" and tl.activity[i - 1] == "idle":
            start_hours[tl.local[i].hour] += 1
    for h in range(now_local.hour + 1):
        when = midnight.replace(hour=h)
        increments["heating_gas"][when] = spread(TODAY_HEATING, heat_minutes)[h]
        increments["tapping_gas"][when] = spread(TODAY_TAPPING, tap_minutes)[h]
        increments["keep_warm_gas"][when] = spread(TODAY_KEEP, keep_minutes)[h]
        increments["daily_burner_starts"][when] = spread(TODAY_STARTS, [s or 0.01 for s in start_hours])[h]
        increments["daily_burner_time"][when] = burn_minutes[h] / 60
        increments["daily_missed_comfort"][when] = 0
    for key in ("tapping_gas", "keep_warm_gas"):
        for when, value in increments[key].items():
            increments.setdefault("hot_water_gas", {})[when] = increments["hot_water_gas"].get(when, 0) + value
    totals = {}
    now_ts = time.time()
    for key, unit in units.items():
        statistic_id = unit["entity_id"]
        meta = db.execute("select id from statistics_meta where statistic_id=?", (statistic_id,)).fetchone()
        if meta is None:
            unit_class = {"m³": "volume", "kWh": "energy", "h": "duration", "min": "duration"}.get(unit["unit"])
            db.execute("insert into statistics_meta (statistic_id, source, unit_of_measurement, unit_class, has_mean, "
                       "has_sum, name, mean_type) values (?, 'recorder', ?, ?, 0, 1, null, 0)",
                       (statistic_id, unit["unit"], unit_class))
            meta = db.execute("select id from statistics_meta where statistic_id=?", (statistic_id,)).fetchone()
        metadata_id = meta[0]
        db.execute("delete from statistics where metadata_id=?", (metadata_id,))
        db.execute("delete from statistics_short_term where metadata_id=?", (metadata_id,))
        hours = sorted(increments[key].items())
        cumulative, hourly, tail = 0.0, [], []
        daily = key in ("daily_burner_starts",)
        for when, value in hours:
            start = when.astimezone(timezone.utc)
            if start >= last_hour:
                # The hour that runs now: 5-minute rows up to the last whole 5 minutes, spread evenly.
                minutes = int((tl.now - start).total_seconds() // 300)
                for k in range(minutes):
                    part = value * (k + 1) / max(1, (tl.now - start).total_seconds() / 300)
                    tail.append((start + timedelta(minutes=5 * k), cumulative + part))
                cumulative += value if minutes else 0
                continue
            cumulative += value
            hourly.append((start, cumulative))
        scale = (lambda v: round(v)) if daily else (lambda v: round(v, 3))
        db.executemany("insert into statistics (created_ts, metadata_id, start_ts, state, sum) values (?, ?, ?, ?, ?)",
                       [(now_ts, metadata_id, s.timestamp(), scale(c), scale(c)) for s, c in hourly])
        # The last two hours also as 5-minute rows (the cards read today's tail from them).
        short = []
        for s, c in hourly[-2:]:
            previous = next((c0 for s0, c0 in reversed(hourly) if s0 < s), 0.0)
            for k in range(12):
                short.append((s + timedelta(minutes=5 * k), previous + (c - previous) * (k + 1) / 12))
        short += tail
        db.executemany("insert into statistics_short_term (created_ts, metadata_id, start_ts, state, sum) "
                       "values (?, ?, ?, ?, ?)", [(now_ts, metadata_id, s.timestamp(), scale(c), scale(c)) for s, c in short])
        final = short[-1][1] if short else (hourly[-1][1] if hourly else 0.0)
        totals[key] = final
    # The recorder compiles the 5-minute periods after the newest run it finds: the rows above are its own.
    last = tl.now.replace(minute=tl.now.minute - tl.now.minute % 5) - timedelta(minutes=5)
    db.execute("insert into statistics_runs (start) values (?)", (last.strftime("%Y-%m-%d %H:%M:%S.000000"),))
    return totals


def write_stores(config, entry_id, tl, totals):
    """The integration's day stores: gas per post and burner figures per day, totals equal to the statistics."""
    now_local = tl.now.astimezone(scenario.ZONE)
    today = now_local.date()
    store = config / ".storage" / f"open_thermostat.energy_use.{entry_id}"
    if store.exists():
        doc = json.loads(store.read_text(encoding="utf-8"))
        data = doc["data"]
        data["totals"] = {"heating": round(totals["heating_gas"], 3), "hot_water": round(totals["hot_water_gas"], 3),
                          "tapping": round(totals["tapping_gas"], 3), "keep_warm": round(totals["keep_warm_gas"], 3)}
        days = {}
        for back, (heat, tap, keep, starts, hours, missed) in enumerate(PAST):
            key = (today - timedelta(days=len(PAST) - back)).isoformat()
            days[key] = {"heating_m3": heat, "heating_kwh": round(heat * 9.77, 2), "hot_water_m3": round(tap + keep, 3),
                         "hot_water_kwh": round((tap + keep) * 9.77, 2), "keep_warm_m3": keep,
                         "keep_warm_kwh": round(keep * 9.77, 2), "tapping_m3": tap, "tapping_kwh": round(tap * 9.77, 2),
                         "hot_water_burner_kwh": round((tap + keep) * 9.77, 2), "keep_warm_burner_kwh": round(keep * 9.77, 2),
                         "tapping_burner_kwh": round(tap * 9.77, 2), "other_m3": 0.0, "heating_s": int(hours * 3300),
                         "hot_water_s": 2400, "keep_warm_s": 1100, "tapping_s": 1300, "observed_s": 86400,
                         "meter": False, "estimate": True, "water": False}
        days[today.isoformat()] = {**days[max(days)], "heating_m3": TODAY_HEATING,
                                   "heating_kwh": round(TODAY_HEATING * 9.77, 2),
                                   "hot_water_m3": round(TODAY_TAPPING + TODAY_KEEP, 3),
                                   "hot_water_kwh": round((TODAY_TAPPING + TODAY_KEEP) * 9.77, 2),
                                   "keep_warm_m3": TODAY_KEEP, "tapping_m3": TODAY_TAPPING,
                                   "observed_s": int((tl.now - now_local.replace(hour=0, minute=0)).total_seconds())}
        data["days"] = days
        store.write_text(json.dumps(doc), encoding="utf-8")
    store = config / ".storage" / f"open_thermostat.daily_summary.{entry_id}"
    if store.exists():
        doc = json.loads(store.read_text(encoding="utf-8"))
        data = doc["data"]
        data["totals"] = {"burner_s": round(totals["daily_burner_time"] * 3600, 1), "starts": round(totals["daily_burner_starts"]),
                          "missed_s": round(totals["daily_missed_comfort"] * 60, 1)}
        days = {}
        for back, (heat, tap, keep, starts, hours, missed) in enumerate(PAST):
            key = (today - timedelta(days=len(PAST) - back)).isoformat()
            low = 4.5 + back % 3
            days[key] = {"observed_s": 86400.0, "burner_s": hours * 3600, "starts": starts, "short_runs": 0,
                         "rooms": {"woonkamer": {"name": "Woonkamer", "demand_s": hours * 3400, "missed_s": missed * 60.0,
                                                 "steps": [], "late": 0, "not_reached": 0}},
                         "outdoor": {"min": low, "max": low + 5.5, "sum": (low + 2.7) * 1440, "n": 1440}}
        data["days"] = {**data.get("days", {}), **days}
        store.write_text(json.dumps(doc), encoding="utf-8")


def main():
    config, entry_id = Path(sys.argv[1]), sys.argv[2]
    registry = json.loads((config / ".storage" / "core.entity_registry").read_text(encoding="utf-8"))
    by_unique = {e["unique_id"]: e["entity_id"] for e in registry["data"]["entities"] if e["platform"] == "open_thermostat"}
    tl = scenario.Timeline()
    entities = []
    for unique, entity_id in by_unique.items():
        if unique.startswith(PREFIX):
            values = series(tl, unique[len(PREFIX):])
            if values is not None:
                entities.append((entity_id, values))
    extra = [(scenario.OUTDOOR, tl.outdoor), (scenario.TADO, None)]
    extra = [(e, v) for e, v in extra if v is not None]
    db = sqlite3.connect(config / "home-assistant_v2.db")
    written = write_states(db, tl, entities, extra)
    units = {}
    for key in ("heating_gas", "hot_water_gas", "tapping_gas", "keep_warm_gas", "daily_burner_starts",
                "daily_burner_time", "daily_missed_comfort"):
        entity_id = by_unique.get(f"{PREFIX}hub_{key}")
        if entity_id:
            row = db.execute("select a.shared_attrs from states s join states_meta m on s.metadata_id=m.metadata_id "
                             "left join state_attributes a on s.attributes_id=a.attributes_id where m.entity_id=? "
                             "order by s.state_id desc limit 1", (entity_id,)).fetchone()
            attrs = json.loads(row[0]) if row and row[0] else {}
            units[key] = {"entity_id": entity_id, "unit": attrs.get("unit_of_measurement")}
    totals = write_statistics(db, tl, units) if units else {}
    db.commit()
    db.close()
    if totals:
        write_stores(config, entry_id, tl, totals)
    print(f"{written} past states for {len(entities) + len(extra)} entities, statistics for {len(units)} sums: "
          + ", ".join(f"{k} {v:.2f}" for k, v in totals.items()))


if __name__ == "__main__":
    main()
