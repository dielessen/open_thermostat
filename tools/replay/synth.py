#!/usr/bin/env python3
"""A synthetic holding boiler driven by a recording's requests (tools/replay/README.md "Synthetic data").

    python3 -I tools/replay/synth.py <house.csv> <out.csv> [--driver e32|recorded] [--hot-water none|recorded]
        [--nominal-kw 22] [--min-modulation 25] [--hold-k 5] [--anti-cycle-s 600]
        [--water-kwh-per-k 0.03] [--emitter-kw-per-k 0.25] [--pump-kg-s 0.15]

The owner's recording has few held targets, so the effect of BoilerResponse (rc.5) cannot be
measured on it. This writes the same rows (room temperatures and targets, outdoor, the requests)
with the boiler columns of a "0Y" boiler instead: flow_c, return_c, burner, modulation_pct,
heating_active and dhw_active. The boiler cannot modulate below min-modulation of nominal-kw;
when the emitters take less than that, the water rises past the request, and at the request +
hold-k the burner stops and the boiler's own anti-cycle keeps it off for anti-cycle-s, whatever
is asked meanwhile; it fires again once the water is below the request. The emitters take
emitter-kw-per-k x (mean water - room) at a pump flow of pump-kg-s; the water around the flow
sensor holds water-kwh-per-k (0.03: a few minutes at the minimum to +5 K, as a real 0Y boiler
cycles). Without a request the pump stops and the water cools slowly.

--driver e32 (default): the recorded E32 request (e32_heat, e32_flow_c) drives the boiler in
every row, as if the E32 had driven it all along: mode is "active" and thermostat_flow_c empty.
--driver recorded: per row the controller that drove the real boiler (the E32 in "active" rows,
else the old thermostat's thermostat_flow_c); mode and thermostat_flow_c are kept.
--hot-water none (default) drops the recording's hot-water runs: every held target is one of the
heating, the case BoilerResponse learns from. --hot-water recorded keeps them (the boiler heats
its store at 65 C then and the heating circuit gets nothing): with a store kept warm every few
minutes, as the owner's, the boiler is mostly hot from it and holds right after hot water, which
BoilerResponse must not count. A gap longer than 120 s between rows restarts the boiler cold.
Deterministic: the same input gives the same output.
"""
import argparse
import csv
import sys

BOILER_COLUMNS = ['flow_c', 'return_c', 'burner', 'heating_active', 'dhw_active', 'modulation_pct']
SUBSTEP_S = 10
GAP_S = 120
WATER_C = 4.186  # kJ/(kg K)


def number(text):
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float('inf'), float('-inf')) else None


def flag(text):
    if text in ('1', 'true', 'on'):
        return True
    if text in ('0', 'false', 'off'):
        return False
    v = number(text)
    return None if v is None else v > 0


def read(path):
    """(comment lines, header, rows as dicts) of a replay CSV."""
    comments, header, rows = [], None, []
    with open(path, encoding='utf-8', newline='') as fh:
        for line in fh:
            line = line.rstrip('\r\n')
            if not line:
                continue
            if line.startswith('#'):
                if header is None:
                    comments.append(line)
                continue
            fields = line.split(',')
            if header is None:
                header = fields
                if 'utc' not in header:
                    raise SystemExit(f'synth.py: {path}: no utc column')
                continue
            row = dict(zip(header, fields + [''] * (len(header) - len(fields))))
            if number(row['utc']) is None:
                raise SystemExit(f'synth.py: {path}: a row without utc')
            rows.append(row)
    if header is None or len(rows) < 2:
        raise SystemExit(f'synth.py: {path}: fewer than two rows')
    rows.sort(key=lambda r: number(r['utc']))
    return comments, header, rows


def request(row, driver):
    """The flow the boiler is asked for in this row (0: no heat)."""
    if driver == 'recorded' and row.get('mode', '') != 'active':
        t = number(row.get('thermostat_flow_c'))
        return t if t is not None and t >= 20 else 0.0
    heat = flag(row.get('e32_heat', ''))
    f = number(row.get('e32_flow_c'))
    if heat is None:
        heat = f is not None and f > 0
    return f if heat and f is not None and f >= 20 else 0.0


def room_temperature(row, rooms):
    values = [number(row.get(f'{r}.temp_c')) for r in rooms]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


class Boiler:
    def __init__(self, a):
        self.a = a
        self.cold()

    def cold(self):
        self.water, self.on, self.rest_until, self.modulation = 25.0, False, -1.0, 0.0
        self.absorbed = 0.0

    def emitters(self, room):
        """kW the emitters take at the current water temperature (mean of flow and return)."""
        g, mc = self.a.emitter_kw_per_k, self.a.pump_kg_s * WATER_C
        return max(0.0, g * (self.water - room) / (1 + g / (2 * mc)))

    def step(self, t, dt, req, hot_water, room):
        """Advances dt seconds; returns True when the burner stopped at its held target ("0Y")."""
        a, dt_h, held = self.a, dt / 3600.0, False
        if hot_water:  # the store: the burner heats it, the heating circuit gets nothing
            self.on, self.modulation, self.absorbed = True, 70.0, 0.0
            self.water += (65 - self.water) * min(1.0, dt_h / 0.05)
            return False
        if req < 20:  # no heat asked: the pump stops, the water cools slowly
            self.on, self.modulation, self.absorbed = False, 0.0, 0.0
            self.water += (room + 5 - self.water) * min(1.0, dt_h / 1.0)
            return False
        self.absorbed = self.emitters(room)
        if self.on and self.water >= req + a.hold_k:
            self.on, self.rest_until, held = False, t + a.anti_cycle_s, True
        elif not self.on and t >= self.rest_until and self.water < req:
            self.on = True
        if self.on:  # the boiler's own control: towards the request, never below its minimum
            needed = self.absorbed + a.water_kwh_per_k * (req - self.water) / 0.05
            self.modulation = min(100.0, max(a.min_modulation, needed / a.nominal_kw * 100))
            self.water += (self.modulation / 100 * a.nominal_kw - self.absorbed) * dt_h / a.water_kwh_per_k
        else:
            self.modulation = 0.0
            self.water -= self.absorbed * dt_h / a.water_kwh_per_k
        return held

    def returned(self, req, hot_water):
        if hot_water:
            return self.water - 10
        if req < 20:
            return self.water - 1
        return self.water - self.absorbed / (self.a.pump_kg_s * WATER_C)


def synthesize(rows, header, a):
    rooms = sorted({c[:-len('.temp_c')] for c in header if c.endswith('.temp_c')})
    boiler = Boiler(a)
    stats = {'rows': len(rows), 'heating_s': 0, 'starts': 0, 'held': 0, 'resting_s': 0}
    out, last_t, last_on, room = [], None, False, 20.0
    for row in rows:
        t = number(row['utc'])
        req = request(row, a.driver)
        hot_water = a.hot_water == 'recorded' and bool(flag(row.get('dhw_active', '')))
        room = room_temperature(row, rooms) or room
        if last_t is None or t - last_t > GAP_S:
            boiler.cold()
            last_on = False
        else:
            elapsed = t - last_t
            while elapsed > 0:  # integrate in 10 s steps over the time since the previous row
                dt = min(SUBSTEP_S, elapsed)
                elapsed -= dt
                stats['held'] += boiler.step(t - elapsed, dt, req, hot_water, room)
                if req >= 20 and not hot_water:
                    stats['heating_s'] += dt
                    if not boiler.on and t - elapsed < boiler.rest_until:
                        stats['resting_s'] += dt
        if boiler.on and not last_on and not hot_water:
            stats['starts'] += 1
        last_on, last_t = boiler.on, t
        new = dict(row)
        new['flow_c'] = f'{boiler.water:.1f}'
        new['return_c'] = f'{boiler.returned(req, hot_water):.1f}'
        new['burner'] = '1' if boiler.on else '0'
        new['modulation_pct'] = f'{boiler.modulation:.0f}' if boiler.on else '0'
        new['heating_active'] = '1' if req >= 20 and not hot_water else '0'
        new['dhw_active'] = '1' if hot_water else '0'
        if a.driver == 'e32':
            new['mode'] = 'active'
            new['thermostat_flow_c'] = ''
        out.append(new)
    return out, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('house')
    ap.add_argument('out')
    ap.add_argument('--driver', choices=('e32', 'recorded'), default='e32')
    ap.add_argument('--hot-water', choices=('none', 'recorded'), default='none')
    ap.add_argument('--nominal-kw', type=float, default=22)
    ap.add_argument('--min-modulation', type=float, default=25)
    ap.add_argument('--hold-k', type=float, default=5)
    ap.add_argument('--anti-cycle-s', type=float, default=600)
    ap.add_argument('--water-kwh-per-k', type=float, default=0.03)
    ap.add_argument('--emitter-kw-per-k', type=float, default=0.25)
    ap.add_argument('--pump-kg-s', type=float, default=0.15)
    a = ap.parse_args(argv)
    for name in ('nominal_kw', 'water_kwh_per_k', 'emitter_kw_per_k', 'pump_kg_s'):
        if not getattr(a, name) > 0:
            ap.error(f'--{name.replace("_", "-")} must be above 0')
    if not 0 < a.min_modulation <= 100 or a.hold_k < 0 or a.anti_cycle_s < 0:
        ap.error('--min-modulation in (0, 100], --hold-k and --anti-cycle-s at least 0')
    comments, header, rows = read(a.house)
    out, stats = synthesize(rows, header, a)
    columns = header + [c for c in BOILER_COLUMNS + ['mode', 'thermostat_flow_c'] if c not in header]
    name = a.house.replace('\\', '/').rsplit('/', 1)[-1]
    with open(a.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(f'# synthetic (tools/replay/synth.py) from {name}: a holding boiler, {a.nominal_kw:g} kW, minimum {a.min_modulation:g} %, '
                 f'holds the request + {a.hold_k:g} K, anti-cycle {a.anti_cycle_s:g} s, water {a.water_kwh_per_k:g} kWh/K, '
                 f'emitters {a.emitter_kw_per_k:g} kW/K, pump {a.pump_kg_s:g} kg/s\n')
        fh.write(f'# driver {a.driver}, hot water {a.hot_water}; the boiler columns are synthetic, the rest is the input\n')
        for c in comments:
            fh.write(f'# input: {c.lstrip("#").strip()}\n')
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(columns)
        for row in out:
            w.writerow([row.get(c, '') for c in columns])
    hours = stats['heating_s'] / 3600
    print(f'{stats["rows"]} rows -> {a.out}: heat asked {hours:.1f} h, {stats["starts"]} heating starts'
          f' ({stats["starts"] / hours:.2f} per hour), {stats["held"]} held targets, resting {stats["resting_s"] / 3600:.1f} h'
          if hours else f'{stats["rows"]} rows -> {a.out}: no heat asked')
    return 0


if __name__ == '__main__':
    sys.exit(main())
