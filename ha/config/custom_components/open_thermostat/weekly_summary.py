"""The weekly summary: the last seven days of gas for heating and hot water, the night setback and the advice.

ADVICE ONLY: a text for a notification, nothing is changed. The "Heating
advice" sensor carries it as the attribute ``weekly_summary`` (title,
message and the figures), in the Home Assistant language (English or
Dutch); the blueprint ``blueprints/weekly_summary.yaml`` sends it once a
week when the owner creates that automation. Figures come from the day
records of ``energy_use`` (gas meter or estimate) and the current advice.
"""
from datetime import date

from .heating_advice import fmt

WEEK_DAYS = 7
# A week counts as complete for a comparison with at least 5.5 days observed.
FULL_WEEK_SECONDS = int(5.5 * 86400)
TOP_ADVICE = 3

TEXT = {
    "en": {
        "title": "OpenThermostat: your week",
        "period": "The last 7 days ({start} to {end}):",
        "heating_m3": "Heating: {m3} m³ of gas ({kwh} kWh), burner {hours} h.",
        "heating_kwh": "Heating: {kwh} kWh of gas, burner {hours} h.",
        "hot_water_m3": "Hot water: {m3} m³ of gas ({kwh} kWh), burner {hours} h.",
        "hot_water_kwh": "Hot water: {kwh} kWh of gas, burner {hours} h.",
        "taps": " {taps} taps.",
        "share": "Heating was {share} % of the boiler's gas.",
        "less": "That is {change} % less than the week before.",
        "more": "That is {change} % more than the week before.",
        "same": "That is about the same as the week before.",
        "no_gas": "No gas use counted yet: the E32 has not reported the boiler's burner modulation.",
        "night_saving": "Night setback: a different night temperature could have saved about {m3} m³ of gas "
                        "this week.",
        "night_money": " That is about {money} {currency}.",
        "night_best": "Night setback: your week program's night temperature is already the most economical "
                      "choice.",
        "advice": "Advice:",
        "no_advice": "No advice right now: the heating looks fine.",
        "gas_meter": "Measured with your gas meter; the split between heating and hot water follows what the "
                     "boiler did.",
        "estimate": "Estimated from the burner modulation and the boiler's power. Add your gas meter in the "
                    "integration options for real values.",
        "rough": " The boiler's power is not set, so the estimate is rough.",
        "mixed": "Partly measured with your gas meter, partly estimated.",
        "partial": "Counted over {days} days so far.",
        "advice_only": "Advice only: nothing is changed automatically.",
    },
    "nl": {
        "title": "OpenThermostat: je week",
        "period": "De afgelopen 7 dagen ({start} tot en met {end}):",
        "heating_m3": "Verwarmen: {m3} m³ gas ({kwh} kWh), brander {hours} uur.",
        "heating_kwh": "Verwarmen: {kwh} kWh gas, brander {hours} uur.",
        "hot_water_m3": "Warm water: {m3} m³ gas ({kwh} kWh), brander {hours} uur.",
        "hot_water_kwh": "Warm water: {kwh} kWh gas, brander {hours} uur.",
        "taps": " {taps} keer getapt.",
        "share": "Verwarmen was {share} % van het gas van de ketel.",
        "less": "Dat is {change} % minder dan de week ervoor.",
        "more": "Dat is {change} % meer dan de week ervoor.",
        "same": "Dat is ongeveer evenveel als de week ervoor.",
        "no_gas": "Nog geen gasverbruik geteld: de E32 heeft de brandermodulatie van de ketel nog niet gemeld.",
        "night_saving": "Nachtverlaging: een andere nachttemperatuur had deze week ongeveer {m3} m³ gas "
                        "kunnen besparen.",
        "night_money": " Dat is ongeveer {money} {currency}.",
        "night_best": "Nachtverlaging: de nachttemperatuur van je weekprogramma is al de zuinigste keuze.",
        "advice": "Advies:",
        "no_advice": "Op dit moment geen advies: de verwarming ziet er goed uit.",
        "gas_meter": "Gemeten met je gasmeter; de verdeling tussen verwarmen en warm water volgt wat de ketel "
                     "deed.",
        "estimate": "Geschat uit de brandermodulatie en het vermogen van de ketel. Voeg je gasmeter toe in de "
                    "opties van de integratie voor echte waarden.",
        "rough": " Het vermogen van de ketel is niet ingesteld, dus de schatting is grof.",
        "mixed": "Deels gemeten met je gasmeter, deels geschat.",
        "partial": "Tot nu toe over {days} dagen geteld.",
        "advice_only": "Alleen advies: er wordt niets automatisch veranderd.",
    },
}


def _round(value, digits):
    value = round(value, digits)
    return int(value) if value == int(value) else value


def _days(records, end, count, offset=0):
    keys = {date.fromordinal(end.toordinal() - offset - i).isoformat() for i in range(count)}
    return [day for key, day in records.items() if key in keys]


def _sum(days, key):
    return sum(day.get(key, 0) for day in days)


def figures(records, today, *, unit="m³", rough=False, price=None, currency="EUR"):
    """The week's figures (no texts) from the energy day records ending today."""
    week, before = _days(records, today, WEEK_DAYS), _days(records, today, WEEK_DAYS, WEEK_DAYS)
    observed = _sum(week, "observed_s")
    result = {"period_start": date.fromordinal(today.toordinal() - WEEK_DAYS + 1).isoformat(),
              "period_end": today.isoformat(), "days_observed": _round(observed / 86400, 1), "unit": unit}
    meter, estimate = any(day.get("meter") for day in week), any(day.get("estimate") for day in week)
    result["method"] = ("mixed" if meter and estimate else "gas_meter" if meter else "estimate" if estimate
                        else "none")
    result["rough"] = bool(rough and estimate)
    for kind in ("heating", "hot_water"):
        result[f"{kind}_m3"] = _round(_sum(week, f"{kind}_m3"), 2)
        result[f"{kind}_kwh"] = _round(_sum(week, f"{kind}_kwh"), 1)
        result[f"{kind}_hours"] = _round(_sum(week, f"{kind}_s") / 3600, 1)
    boiler = _sum(week, "heating_m3") + _sum(week, "hot_water_m3")
    result["heating_share_pct"] = _round(100 * _sum(week, "heating_m3") / boiler, 0) if boiler > 0 else None
    previous = _sum(before, "heating_m3") + _sum(before, "hot_water_m3")
    full = observed >= FULL_WEEK_SECONDS and _sum(before, "observed_s") >= FULL_WEEK_SECONDS
    result["change_pct"] = _round(100 * (boiler - previous) / previous, 0) if full and previous > 0 else None
    taps = [day["taps"] for day in week if type(day.get("taps")) is int]
    result["hot_water_taps"] = sum(taps) if taps else None
    nights = [value for day in week for value in (day.get("nights") or {}).values()]
    result["night_saving_m3"] = _round(sum(m3 for m3, _ in nights), 2) if nights else None
    money = [money for m3, money in nights if m3 and money is not None]
    if nights and money:
        result["night_saving_money"] = _round(sum(money), 2)
    elif nights and price is not None and result["night_saving_m3"]:
        result["night_saving_money"] = _round(result["night_saving_m3"] * price, 2)
    else:
        result["night_saving_money"] = None
    result["currency"] = currency
    return result


def message(result, advice_titles, lang):
    """The notification text of figures() and the current advice titles, in English or Dutch."""
    t = TEXT[lang]

    def n(value):
        return fmt(value, lang)
    lines = [t["period"].format(start=result["period_start"], end=result["period_end"])]
    if result["method"] == "none":
        lines.append(t["no_gas"])
    else:
        kwh = result["unit"] == "kWh"
        for kind in ("heating", "hot_water"):
            line = t[f"{kind}_{'kwh' if kwh else 'm3'}"].format(
                m3=n(result[f"{kind}_m3"]), kwh=n(result[f"{kind}_kwh"]), hours=n(result[f"{kind}_hours"]))
            if kind == "hot_water" and result["hot_water_taps"] is not None:
                line += t["taps"].format(taps=n(result["hot_water_taps"]))
            lines.append(line)
        if result["heating_share_pct"] is not None:
            share = t["share"].format(share=n(result["heating_share_pct"]))
            change = result["change_pct"]
            if change is not None:
                share += " " + (t["same"] if abs(change) < 3 else
                                t["less" if change < 0 else "more"].format(change=n(abs(change))))
            lines.append(share)
    if result["night_saving_m3"] is not None:
        if result["night_saving_m3"] > 0:
            line = t["night_saving"].format(m3=n(result["night_saving_m3"]))
            if result["night_saving_money"] is not None:
                line += t["night_money"].format(money=n(result["night_saving_money"]), currency=result["currency"])
            lines.append(line)
        else:
            lines.append(t["night_best"])
    if advice_titles:
        lines.append(t["advice"] + "\n" + "\n".join(f"- {title}" for title in advice_titles[:TOP_ADVICE]))
    else:
        lines.append(t["no_advice"])
    if result["method"] != "none":
        basis = t[result["method"]]
        if result["rough"]:
            basis += t["rough"]
        if result["days_observed"] < WEEK_DAYS - 0.5:
            basis += " " + t["partial"].format(days=n(result["days_observed"]))
        lines.append(basis)
    lines.append(t["advice_only"])
    return "\n\n".join(lines)


def weekly_summary(records, today, advice_titles, lang, **context):
    """figures() with the advice titles, a title and the message."""
    result = figures(records, today, **context)
    result["advice"] = list(advice_titles[:TOP_ADVICE])
    result["title"] = TEXT[lang]["title"]
    result["message"] = message(result, advice_titles, lang)
    return result
