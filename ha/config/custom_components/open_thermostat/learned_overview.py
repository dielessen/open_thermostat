"""What the thermostat has learned: everything the E32 learned and tuned, in plain language (E32 rc.2).

One sensor on the product device ("What the thermostat learned"). Its state is the newest change
the self-tuning made (or what it is doing), its attributes the whole overview in the Home Assistant
language (English, Dutch or Polish), each figure with a line on what it means:

- ``rooms``: per room its learning progress and what was learned (how fast it warms and cools,
  the lowest water temperature that still warms it in time, Smart warm-up's start for the next
  program step, how the last morning went and what Smart warm-up changes for it (E32 rc.4), the
  night advice, and the heat it gets for free from sun, cooking and people (E32 rc.5)), from
  ``fw/telemetry/learned/<room>``;
- ``house``: the heating curve, the burner (starts and burn time yesterday) and, once learned, the
  lowest water temperature the boiler starts heating at, from the summary; that last figure is
  also the attribute ``boiler_minimum_flow_c`` (absent until learned);
- ``changes``: the self-tuning's changes, newest first. The E32 sends its newest four
  (``fw/telemetry/tuning``); this sensor keeps the last ten over restarts;
- ``settings``: the knobs in effect by their plain names, "(automatic)" or "(set by you)";
- ``insights``: yesterday against the house's own usual days, each with what can cause it (E32 rc.5,
  insight.py; also a notification each);
- ``free_heat``: the rooms that get heat for free from sun, cooking and people, each with its free-heat line
  of ``rooms`` and the room's name (E32 rc.5), for the dashboard's "Free heat".

Read only: the knobs are changed in Configure → Home → Comfort and boiler care (e32_care.py) or on
the E32 page (Home -> Comfort and boiler care).
"""
import time
from datetime import datetime, timedelta, timezone

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import DOMAIN

LOG_KEPT = 10
STATE_MAX = 255
REFERENCE_OUTDOOR_C, REFERENCE_ROOM_C = 5, 20  # "loses about .. per hour at 5 °C outside"
WARMUPS_TO_LEARN = 6                           # FlowLearner::Params::roomSegments

TEXT = {
    "en": {
        "h_m": "{h} h {m} min", "h": "{h} h", "m": "{m} min", "at_least": "at least {d}", "per_c": "{d} per °C",
        "gain": "{v} °C warmer water per °C too cold", "automatic": "(automatic)", "yours": "(set by you)",
        "standard": "(standard value)", "your_rooms": "A typical room",
        "knob.min_off_s": "Burner rest between starts", "knob.min_on_s": "Burner run time",
        "knob.heat_start_c": "Start heating when the room is this much below its target",
        "knob.heat_stop_c": "Stop heating when the room is this much above its target",
        "knob.flow_per_degree_c": "How strongly the water temperature reacts to a cold room",
        "knob.floor_lead_min_per_c": "Warm-up time for floor heating", "knob.radiator_lead_min_per_c": "Warm-up time for radiators",
        "knob.curve_correction_pct": "Room correction on weather compensation",
        "knob.learned_accept_pct": "Accepted warm-up time with the learned water temperature",
        "knob.night_saving_min_pct": "Smallest night saving worth advising",
        "why.many_starts": "The burner now rests at least {to} before it starts again, because it started {figure} times yesterday. Fewer starts are gentler on the boiler.",
        "why.cold_during_rest": "The burner rest is now {to}, because {subject} cooled {figure} °C below its target while the burner rested. Comfort comes first.",
        "why.short_burns": "Each burner run now lasts at least {to}, because {figure} runs yesterday were very short. Longer runs are gentler on the boiler.",
        "why.boiler_cycling": "The boiler switches on and off by itself ({figure} times yesterday); longer pauses would only delay heat, so this is now {to} again.",
        "why.overshoot": "{subject} got {figure} °C warmer than its target; the thermostat now stops heating a little earlier.",
        "why.overshoot_gain": "{subject} still got {figure} °C warmer than its target; the thermostat now heats a little more gently.",
        "why.settled": "{room} hardly gets too warm any more ({figure} °C); the thermostat stops heating a little later again, so the burner starts less often.",
        "why.hovering": "Heating now starts when a room is {to} below its target, because it started {figure} times yesterday for small dips. Fewer starts are gentler on the boiler.",
        "why.few_starts": "Heating now starts sooner again, at {to} below the target: with only {figure} starts yesterday there is room for more comfort.",
        "why.room_response_up": "{room} warms about 1 °C in {figure}; the thermostat now reacts a little more strongly to a cold room.",
        "why.room_response_down": "{room} warms about 1 °C in {figure}; the thermostat now reacts a little more gently to a cold room.",
        "why.learned_warmup": "{room} warms about 1 °C in {figure}; mornings are planned with that.",
        "would": "Would change: {text}",
        "state.waiting": "After a restart or a change the thermostat first watches a whole day before it adjusts anything.",
        "state.collecting": "Yesterday there was too little heating to learn from; the settings stay as they are.",
        "state.shadow": "Your current thermostat or the boiler's own control is still in charge, so the E32 only shows what it would change.",
        "state.active": "The thermostat adjusts its settings itself, at most one small step a day.",
        "state.none": "Nothing changed yet: the start values still fit, or there is not enough to go on.",
        "learned": "Learned", "learning": "Learning: {n} of {m} warm-ups seen",
        "learning_seen": "Learning: {n} warm-ups seen; it still needs warm-ups on other days or at another water temperature",
        "learning_timing": "Warm-up time learned; the coolest water is still being learned",
        "learning_more": "It needs a few more warm-ups, on other days or at other water temperatures.",
        "learning_first": "It learns from every warm-up while the heating runs.",
        "learning_mean": "Until then it uses safe standard times.",
        "warms": "Warms about 1 °C in {d} with water of {flow} °C.",
        "warms_mean": "The thermostat plans the start of every warm-up with this.",
        "lowest": "The lowest water temperature that still warms it in time: {flow} °C.",
        "lowest_mean": "Cooler water lets the boiler condense better, so it uses less gas.",
        "cools": "Loses about {rate} °C per hour at {out} °C outside.",
        "cools_mean": "This is how fast it cools when the heating is off, for example at night.",
        "free_heat": "{when} this room warms up by itself, about {rate} °C per hour (sun, cooking or people).",
        "free_heat_applied": "Its next warm-up starts {m} min later, so Smart warm-up does not heat what comes for free.",
        "free_heat_mean": "Smart warm-up takes this into account when it plans a warm-up at that time of day.",
        "daypart.0": "At night", "daypart.1": "Early in the morning", "daypart.2": "In the morning",
        "daypart.3": "In the afternoon", "daypart.4": "In the evening", "daypart.5": "Late in the evening",
        "start_only": "Starts heating at {start} for the next program step.",
        "start_mean": "So the room is warm on time, without heating longer than needed.",
        "warmup_on": "Smart warm-up: starts at {start} so it is {target} °C at {time}.",
        "warmup_now": "Smart warm-up: heating now so it is {target} °C at {time}.",
        "warmup_late": "Smart warm-up: heating now; {target} °C may come a little after {time}.",
        "warmup_ready": "Smart warm-up: warm enough for {target} °C at {time}, no early start needed.",
        "warmup_learning": "Smart warm-up is still learning: for now heating starts at {time} (estimate: from {start} it would be {target} °C on time).",
        "warmup_learning_mean": "Until the room has been learned, it does not start early on an estimate.",
        "warmup_off": "Smart warm-up is off: heating starts at {time}.",
        "warmup_off_mean": "Turn Smart warm-up on to be warm on time.",
        "warmup_estimate": "Smart warm-up: starts at {start} (estimate; it learns from every morning) so it is {target} °C at {time}.",
        "timing_learned": "The warm-up time is learned; the coolest water is still being learned.",
        "timing_learned_mean": "Smart warm-up already plans with it; the coolest water needs a few more warm-ups at other water temperatures.",
        "arrival": "{when} warm at {time} ({how}).",
        "arrival_earlier": "{when} warm at {time} ({how}); next time it starts a little earlier.",
        "arrival_later": "{when} warm at {time} ({how}); next time it starts a little later.",
        "arrival_mean": "It checks every morning whether the room was warm on time and adjusts its warm-up time.",
        "how_late": "{d} late",
        "how_early": "{d} early",
        "how_on_time": "on time",
        "when_today": "Today",
        "when_yesterday": "Yesterday",
        "when_date": "On {date}",
        "months": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        "saving_eur": "about {m3} m³ gas ({eur}) a night", "saving": "about {m3} m³ gas a night",
        "night_hold": "Keeping it at {night} °C at night is cheaper than letting it cool down: {saving}.",
        "night_program": "Letting it cool down at night, as your program does, is the cheapest.",
        "night_mean": "This is advice: your week program stays as it is.",
        "curve_status_off": "Weather compensation: off, the water temperature follows the rooms only.",
        "curve_status_no_outdoor": "Weather compensation: no outdoor temperature right now, so the water temperature follows the rooms only.",
        "curve_status_learned": "Weather compensation: learned for your house.",
        "curve_status_learning": "Weather compensation: standard for now, learning from your house ({n} of {m} steady periods).",
        "curve_status_learning_plain": "Weather compensation: standard for now, learning from your house.",
        "curve_status_house": "Weather compensation: estimated from your house for now, learning more ({n} of {m} steady periods).",
        "curve_status_house_plain": "Weather compensation: estimated from your house for now, learning more.",
        "curve_status_mean": "The E32 decides by itself when what it learned is good enough to use.",
        "flow_status_collecting": "Coolest water: still learning from each warm-up.",
        "flow_status_ready": "Coolest water: learned for your house.",
        "flow_status_advice": "Coolest water: learned; used when Smart warm-up is on.",
        "flow_status_mean": "Cooler water lets the boiler condense better, so it uses less gas.",
        "curve_learned": "Weather compensation, learned from your house: the water gets about {s} °C warmer for every degree colder outside.",
        "curve_house": "Weather compensation, estimated from your house: the water gets about {s} °C warmer for every degree colder outside.",
        "curve": "Weather compensation: the water gets about {s} °C warmer for every degree colder outside.",
        "curve_on": "Weather compensation sets the water temperature, so the boiler runs as cool as the weather allows.",
        "curve_off": "Weather compensation is not switched on; this is shown as advice.",
        "burner": "Yesterday the burner started {n} times for heating; a burn lasted {d} on average.",
        "burner_starts": "Yesterday the burner started {n} times for heating.",
        "burner_often": "That is often. Fewer, longer burns are gentler on the boiler; the thermostat works on that.",
        "burner_mean": "Fewer, longer burns are gentler on the boiler and use gas more efficiently.",
        "boiler_minimum": "Your boiler only starts heating from about {flow} °C water; the thermostat asks at least that much.",
        "boiler_minimum_mean": "It learned this when the boiler did not start for cooler water.",
        "house_none": "Nothing yet: this appears after the first heating days.",
        "unavailable": "The E32 has not reported what it learned yet.",
        # rc7: the sentences review (R1, R3). {subject}: the room as the subject of a sentence (Polish: "pomieszczenie X").
        "room_subject": "{room}", "your_rooms_subject": "a typical room",
        "warmup_now_estimate": "Smart warm-up: heating now (estimate; it learns from every morning) so it is {target} °C at {time}.",
        "warmup_trial": "Smart warm-up in the trial run: it would start at {start} so it is {target} °C at {time}.",
        "warmup_trial_now": "Smart warm-up in the trial run: it would be heating now so it is {target} °C at {time}.",
        "free_heat_later": "So the warm-up starts {m} min later than without the free heat.",
        "arrival_not_warm": "{when} not warm within 3 hours after {time}.",
        "arrival_not_warm_earlier": "{when} not warm within 3 hours after {time}; next time it starts a little earlier.",
        "saving_eur_once": "about {m3} m³ gas ({eur})",
        "saving_once": "about {m3} m³ gas",
        "night_hold_until": "Keeping it at {night} °C until {time} is cheaper than letting it cool down: {saving}.",
        "night_program_until": "Letting it cool down until {time}, as your program does, is the cheapest.",
        "burner_one": "Yesterday the burner started once for heating; the burn lasted {d}.",
        "burner_starts_one": "Yesterday the burner started once for heating.",
        "burner_none": "Yesterday the burner did not start for heating.",
        "why.few_starts_one": "Heating now starts sooner again, at {to} below the target: with only 1 start yesterday there is room for more comfort.",
        "would_set": "Would set “{knob}” to {to}, because {because}.",
        "because.many_starts": "the burner started {figure} times yesterday",
        "because.cold_during_rest": "{subject} cooled {figure} °C below its target while the burner rested",
        "because.short_burns": "{figure} burner runs yesterday were very short",
        "because.boiler_cycling": "the boiler switches on and off by itself ({figure} times yesterday)",
        "because.overshoot": "{subject} got {figure} °C warmer than its target",
        "because.overshoot_gain": "{subject} still got {figure} °C warmer than its target",
        "because.settled": "{room} hardly gets too warm any more ({figure} °C)",
        "because.hovering": "the burner started {figure} times yesterday for small dips",
        "because.few_starts": "there were only {figure} starts yesterday",
        "because.few_starts_one": "there was only 1 start yesterday",
        "because.room_response_up": "{room} warms about 1 °C in {figure}",
        "because.room_response_down": "{room} warms about 1 °C in {figure}",
        "because.learned_warmup": "{room} warms about 1 °C in {figure}",
        "learned_warms": "warms about 1 °C in {d} with water of {flow} °C",
        "curve_slope": "The water gets about {s} °C warmer for every degree colder outside.",
    },
    "nl": {
        "h_m": "{h} u {m} min", "h": "{h} u", "m": "{m} min", "at_least": "minstens {d}", "per_c": "{d} per °C",
        "gain": "{v} °C warmer water per °C te koud", "automatic": "(automatisch)", "yours": "(door jou ingesteld)",
        "standard": "(standaardwaarde)", "your_rooms": "Een gemiddelde ruimte",
        "knob.min_off_s": "Rust van de brander tussen starts", "knob.min_on_s": "Brandtijd",
        "knob.heat_start_c": "Begin met verwarmen als de ruimte zoveel onder de gewenste temperatuur is",
        "knob.heat_stop_c": "Stop met verwarmen als de ruimte zoveel boven de gewenste temperatuur is",
        "knob.flow_per_degree_c": "Hoe sterk de watertemperatuur reageert op een koude ruimte",
        "knob.floor_lead_min_per_c": "Opwarmtijd voor vloerverwarming", "knob.radiator_lead_min_per_c": "Opwarmtijd voor radiatoren",
        "knob.curve_correction_pct": "Ruimtecorrectie op de weerafhankelijke regeling",
        "knob.learned_accept_pct": "Toegestane opwarmtijd met de geleerde watertemperatuur",
        "knob.night_saving_min_pct": "Kleinste nachtbesparing die een advies waard is",
        "why.many_starts": "De brander rust nu minstens {to} voordat hij weer start, omdat hij gisteren {figure} keer startte. Minder starts zijn beter voor de ketel.",
        "why.cold_during_rest": "De rust van de brander is nu {to}, omdat {subject} {figure} °C onder de gewenste temperatuur afkoelde terwijl de brander rustte. Comfort gaat voor.",
        "why.short_burns": "Elke keer branden duurt nu minstens {to}, omdat {figure} keer branden gisteren heel kort was. Langer branden is beter voor de ketel.",
        "why.boiler_cycling": "De ketel schakelt zelf aan en uit ({figure} keer gisteren); langere pauzes zouden de warmte alleen vertragen, dus dit is nu weer {to}.",
        "why.overshoot": "{subject} werd {figure} °C warmer dan gewenst; de thermostaat stopt nu iets eerder met verwarmen.",
        "why.overshoot_gain": "{subject} werd nog steeds {figure} °C warmer dan gewenst; de thermostaat verwarmt nu iets rustiger.",
        "why.settled": "{room} wordt bijna niet meer te warm ({figure} °C); de thermostaat stopt weer iets later met verwarmen, zodat de brander minder vaak start.",
        "why.hovering": "Het verwarmen start nu als een ruimte {to} onder de gewenste temperatuur is, omdat het gisteren {figure} keer startte voor kleine dalingen. Minder starts zijn beter voor de ketel.",
        "why.few_starts": "Het verwarmen start nu weer eerder, bij {to} onder de gewenste temperatuur: met maar {figure} starts gisteren is er ruimte voor meer comfort.",
        "why.room_response_up": "{room} warmt ongeveer 1 °C op in {figure}; de thermostaat reageert nu iets sterker op een koude ruimte.",
        "why.room_response_down": "{room} warmt ongeveer 1 °C op in {figure}; de thermostaat reageert nu iets rustiger op een koude ruimte.",
        "why.learned_warmup": "{room} warmt ongeveer 1 °C op in {figure}; de ochtenden worden daarmee gepland.",
        "would": "Zou aanpassen: {text}",
        "state.waiting": "Na een herstart of een wijziging kijkt de thermostaat eerst een hele dag voordat hij iets aanpast.",
        "state.collecting": "Gisteren werd er te weinig verwarmd om van te leren; de instellingen blijven zoals ze zijn.",
        "state.shadow": "Je huidige thermostaat of de eigen regeling van de ketel is nog de baas, dus de E32 laat alleen zien wat hij zou aanpassen.",
        "state.active": "De thermostaat past zijn instellingen zelf aan, hooguit één kleine stap per dag.",
        "state.none": "Nog niets aangepast: de beginwaarden passen nog, of er is nog te weinig om op af te gaan.",
        "learned": "Geleerd", "learning": "Aan het leren: {n} van {m} keer opwarmen gezien",
        "learning_seen": "Aan het leren: {n} keer opwarmen gezien; hij moet nog opwarmen zien op andere dagen of bij een andere watertemperatuur",
        "learning_timing": "Opwarmtijd geleerd; het koelste water leert hij nog",
        "learning_more": "Hij heeft nog een paar keer opwarmen nodig, op andere dagen of bij andere watertemperaturen.",
        "learning_first": "Hij leert van elke keer opwarmen terwijl de verwarming aan staat.",
        "learning_mean": "Tot dan gebruikt hij veilige standaardtijden.",
        "warms": "Warmt ongeveer 1 °C op in {d} met water van {flow} °C.",
        "warms_mean": "Hiermee plant de thermostaat de start van elke keer opwarmen.",
        "lowest": "De laagste watertemperatuur die nog op tijd opwarmt: {flow} °C.",
        "lowest_mean": "Met koeler water condenseert de ketel beter, dus verbruikt hij minder gas.",
        "cools": "Verliest ongeveer {rate} °C per uur bij {out} °C buiten.",
        "cools_mean": "Zo snel koelt de ruimte af als de verwarming uit is, bijvoorbeeld 's nachts.",
        "free_heat": "{when} warmt deze ruimte vanzelf op, ongeveer {rate} °C per uur (zon, koken of mensen).",
        "free_heat_applied": "De volgende opwarming begint daardoor {m} min later, zodat Slim opwarmen niet verwarmt wat "
                             "gratis komt.",
        "free_heat_mean": "Slim opwarmen houdt hier rekening mee als het op dat moment van de dag opwarmt.",
        "daypart.0": "'s Nachts", "daypart.1": "Vroeg in de ochtend", "daypart.2": "'s Ochtends",
        "daypart.3": "'s Middags", "daypart.4": "'s Avonds", "daypart.5": "Laat op de avond",
        "start_only": "Begint om {start} met verwarmen voor de volgende stap van het programma.",
        "start_mean": "Zo is de ruimte op tijd warm, zonder langer te verwarmen dan nodig.",
        "warmup_on": "Slim opwarmen: begint om {start}, zodat het om {time} {target} °C is.",
        "warmup_now": "Slim opwarmen: verwarmt nu, zodat het om {time} {target} °C is.",
        "warmup_late": "Slim opwarmen: verwarmt nu; {target} °C wordt misschien pas iets na {time} gehaald.",
        "warmup_ready": "Slim opwarmen: warm genoeg voor {target} °C om {time}, eerder beginnen is niet nodig.",
        "warmup_learning": "Slim opwarmen leert nog: voorlopig begint verwarmen om {time} (schatting: vanaf {start} zou het op tijd {target} °C zijn).",
        "warmup_learning_mean": "Zolang de ruimte niet geleerd is, begint hij niet eerder op een schatting.",
        "warmup_off": "Slim opwarmen staat uit: verwarmen begint om {time}.",
        "warmup_off_mean": "Zet Slim opwarmen aan om op tijd warm te zijn.",
        "warmup_estimate": "Slim opwarmen: begint om {start} (schatting; hij leert van elke ochtend), zodat het om {time} {target} °C is.",
        "timing_learned": "De opwarmtijd is geleerd; het koelste water leert hij nog.",
        "timing_learned_mean": "Slim opwarmen plant daar al mee; voor het koelste water zijn nog een paar keer opwarmen bij andere watertemperaturen nodig.",
        "arrival": "{when} warm om {time} ({how}).",
        "arrival_earlier": "{when} warm om {time} ({how}); de volgende keer begint het iets eerder.",
        "arrival_later": "{when} warm om {time} ({how}); de volgende keer begint het iets later.",
        "arrival_mean": "Hij kijkt elke ochtend of de ruimte op tijd warm was en past zijn opwarmtijd daarop aan.",
        "how_late": "{d} te laat",
        "how_early": "{d} te vroeg",
        "how_on_time": "op tijd",
        "when_today": "Vandaag",
        "when_yesterday": "Gisteren",
        "when_date": "Op {date}",
        "months": "jan feb mrt apr mei jun jul aug sep okt nov dec",
        "saving_eur": "ongeveer {m3} m³ gas ({eur}) per nacht", "saving": "ongeveer {m3} m³ gas per nacht",
        "night_hold": "'s Nachts op {night} °C houden is goedkoper dan laten afkoelen: {saving}.",
        "night_program": "'s Nachts laten afkoelen, zoals je programma doet, is het goedkoopst.",
        "night_mean": "Dit is een advies: je weekprogramma blijft zoals het is.",
        "curve_status_off": "Weerafhankelijke regeling: uit, de watertemperatuur volgt alleen de ruimtes.",
        "curve_status_no_outdoor": "Weerafhankelijke regeling: nu geen buitentemperatuur, dus de watertemperatuur volgt alleen de ruimtes.",
        "curve_status_learned": "Weerafhankelijke regeling: geleerd voor je huis.",
        "curve_status_learning": "Weerafhankelijke regeling: voorlopig standaard, hij leert van je huis ({n} van {m} rustige periodes).",
        "curve_status_learning_plain": "Weerafhankelijke regeling: voorlopig standaard, hij leert van je huis.",
        "curve_status_house": "Weerafhankelijke regeling: voorlopig geschat uit je huis, hij leert nog bij ({n} van {m} rustige periodes).",
        "curve_status_house_plain": "Weerafhankelijke regeling: voorlopig geschat uit je huis, hij leert nog bij.",
        "curve_status_mean": "De E32 beslist zelf wanneer wat hij leerde goed genoeg is om te gebruiken.",
        "flow_status_collecting": "Koelste water: leert nog van elke keer opwarmen.",
        "flow_status_ready": "Koelste water: geleerd voor je huis.",
        "flow_status_advice": "Koelste water: geleerd; wordt gebruikt als Slim opwarmen aan staat.",
        "flow_status_mean": "Met koeler water condenseert de ketel beter, dus verbruikt hij minder gas.",
        "curve_learned": "Weerafhankelijke regeling, geleerd van je huis: het water wordt ongeveer {s} °C warmer voor elke graad kouder buiten.",
        "curve_house": "Weerafhankelijke regeling, geschat uit je huis: het water wordt ongeveer {s} °C warmer voor elke graad kouder buiten.",
        "curve": "Weerafhankelijke regeling: het water wordt ongeveer {s} °C warmer voor elke graad kouder buiten.",
        "curve_on": "De weerafhankelijke regeling bepaalt de watertemperatuur, zodat de ketel zo koel draait als het weer toelaat.",
        "curve_off": "De weerafhankelijke regeling staat niet aan; dit is een advies.",
        "burner": "Gisteren startte de brander {n} keer voor verwarmen; hij brandde gemiddeld {d}.",
        "burner_starts": "Gisteren startte de brander {n} keer voor verwarmen.",
        "burner_often": "Dat is vaak. Minder en langer branden is beter voor de ketel; de thermostaat werkt daaraan.",
        "burner_mean": "Minder en langer branden is beter voor de ketel en gebruikt gas zuiniger.",
        "boiler_minimum": "Je ketel begint pas te verwarmen vanaf water van ongeveer {flow} °C; de thermostaat vraagt minstens zoveel.",
        "boiler_minimum_mean": "Dat leerde hij toen de ketel voor koeler water niet aansloeg.",
        "house_none": "Nog niets: dit verschijnt na de eerste dagen met verwarming.",
        "unavailable": "De E32 heeft nog niet gemeld wat hij geleerd heeft.",
        # rc7: the sentences review (R1, R3).
        "room_subject": "{room}", "your_rooms_subject": "een gemiddelde ruimte",
        "warmup_now_estimate": "Slim opwarmen: verwarmt nu (schatting; hij leert van elke ochtend), zodat het om {time} {target} °C is.",
        "warmup_trial": "Slim opwarmen in de proefperiode: het zou om {start} beginnen, zodat het om {time} {target} °C is.",
        "warmup_trial_now": "Slim opwarmen in de proefperiode: het zou nu verwarmen, zodat het om {time} {target} °C is.",
        "free_heat_later": "Daardoor begint het opwarmen {m} min later dan zonder de gratis warmte.",
        "arrival_not_warm": "{when} niet warm binnen 3 uur na {time}.",
        "arrival_not_warm_earlier": "{when} niet warm binnen 3 uur na {time}; de volgende keer begint het iets eerder.",
        "saving_eur_once": "ongeveer {m3} m³ gas ({eur})",
        "saving_once": "ongeveer {m3} m³ gas",
        "night_hold_until": "Tot {time} op {night} °C houden is goedkoper dan laten afkoelen: {saving}.",
        "night_program_until": "Tot {time} laten afkoelen, zoals je programma doet, is het goedkoopst.",
        "burner_one": "Gisteren startte de brander 1 keer voor verwarmen; hij brandde {d}.",
        "burner_starts_one": "Gisteren startte de brander 1 keer voor verwarmen.",
        "burner_none": "Gisteren startte de brander niet voor verwarmen.",
        "why.few_starts_one": "Het verwarmen start nu weer eerder, bij {to} onder de gewenste temperatuur: met maar 1 start gisteren is er ruimte voor meer comfort.",
        "would_set": "Zou ‘{knob}’ op {to} zetten, omdat {because}.",
        "because.many_starts": "de brander gisteren {figure} keer startte",
        "because.cold_during_rest": "{subject} {figure} °C onder de gewenste temperatuur afkoelde terwijl de brander rustte",
        "because.short_burns": "{figure} keer branden gisteren heel kort was",
        "because.boiler_cycling": "de ketel zelf aan en uit schakelt ({figure} keer gisteren)",
        "because.overshoot": "{subject} {figure} °C warmer werd dan gewenst",
        "because.overshoot_gain": "{subject} nog steeds {figure} °C warmer werd dan gewenst",
        "because.settled": "{room} bijna niet meer te warm wordt ({figure} °C)",
        "because.hovering": "het verwarmen gisteren {figure} keer startte voor kleine dalingen",
        "because.few_starts": "er gisteren maar {figure} starts waren",
        "because.few_starts_one": "er gisteren maar 1 start was",
        "because.room_response_up": "{room} ongeveer 1 °C opwarmt in {figure}",
        "because.room_response_down": "{room} ongeveer 1 °C opwarmt in {figure}",
        "because.learned_warmup": "{room} ongeveer 1 °C opwarmt in {figure}",
        "learned_warms": "warmt ongeveer 1 °C op in {d} met water van {flow} °C",
        "curve_slope": "Het water wordt ongeveer {s} °C warmer voor elke graad kouder buiten.",
    },
    "pl": {
        "h_m": "{h} godz. {m} min", "h": "{h} godz.", "m": "{m} min", "at_least": "co najmniej {d}", "per_c": "{d} na °C",
        "gain": "woda cieplejsza o {v} °C na każdy °C za zimno", "automatic": "(automatycznie)", "yours": "(ustawione przez Ciebie)",
        "standard": "(wartość standardowa)", "your_rooms": "Przeciętne pomieszczenie",
        "knob.min_off_s": "Przerwa palnika między uruchomieniami", "knob.min_on_s": "Czas pracy palnika",
        "knob.heat_start_c": "Zacznij grzać, gdy w pomieszczeniu jest o tyle chłodniej niż zadana temperatura",
        "knob.heat_stop_c": "Przestań grzać, gdy w pomieszczeniu jest o tyle cieplej niż zadana temperatura",
        "knob.flow_per_degree_c": "Jak mocno temperatura wody reaguje na zimne pomieszczenie",
        "knob.floor_lead_min_per_c": "Czas nagrzewania dla ogrzewania podłogowego", "knob.radiator_lead_min_per_c": "Czas nagrzewania dla grzejników",
        "knob.curve_correction_pct": "Korekta pomieszczenia przy kompensacji pogodowej",
        "knob.learned_accept_pct": "Dopuszczalny czas nagrzewania przy wyuczonej temperaturze wody",
        "knob.night_saving_min_pct": "Najmniejsza nocna oszczędność warta porady",
        "why.many_starts": "Palnik odpoczywa teraz co najmniej {to}, zanim znów się uruchomi, bo wczoraj uruchomił się {figure} razy. Mniej uruchomień oszczędza kocioł.",
        "why.cold_during_rest": "Przerwa palnika wynosi teraz {to}, bo {subject} ochłodziło się o {figure} °C poniżej zadanej temperatury, gdy palnik odpoczywał. Komfort jest najważniejszy.",
        "why.short_burns": "Każda praca palnika trwa teraz co najmniej {to}, bo wczoraj {figure} razy pracował bardzo krótko. Dłuższa praca oszczędza kocioł.",
        "why.boiler_cycling": "Kocioł sam włącza się i wyłącza ({figure} razy wczoraj); dłuższe przerwy tylko opóźniłyby ciepło, więc teraz znów jest to {to}.",
        "why.overshoot": "{subject} nagrzało się o {figure} °C powyżej zadanej temperatury; termostat kończy teraz grzanie nieco wcześniej.",
        "why.overshoot_gain": "{subject} wciąż nagrzało się o {figure} °C powyżej zadanej temperatury; termostat grzeje teraz nieco łagodniej.",
        "why.settled": "{room} prawie już się nie przegrzewa ({figure} °C); termostat znów kończy grzanie nieco później, więc palnik rzadziej się uruchamia.",
        "why.hovering": "Grzanie zaczyna się teraz, gdy w pomieszczeniu jest o {to} chłodniej niż zadana temperatura, bo wczoraj uruchomiło się {figure} razy przy małych spadkach. Mniej uruchomień oszczędza kocioł.",
        "why.few_starts": "Grzanie zaczyna się znów wcześniej, przy {to} poniżej zadanej temperatury: przy zaledwie {figure} uruchomieniach wczoraj jest miejsce na większy komfort.",
        "why.room_response_up": "{room} nagrzewa się o około 1 °C w {figure}; termostat reaguje teraz nieco mocniej na zimne pomieszczenie.",
        "why.room_response_down": "{room} nagrzewa się o około 1 °C w {figure}; termostat reaguje teraz nieco łagodniej na zimne pomieszczenie.",
        "why.learned_warmup": "{room} nagrzewa się o około 1 °C w {figure}; poranki są planowane według tego.",
        "would": "Zmieniłby: {text}",
        "state.waiting": "Po ponownym uruchomieniu lub zmianie termostat najpierw obserwuje cały dzień, zanim coś zmieni.",
        "state.collecting": "Wczoraj grzano za mało, by się czegoś nauczyć; ustawienia pozostają bez zmian.",
        "state.shadow": "Nadal decyduje Twój obecny termostat lub własna regulacja kotła, więc E32 tylko pokazuje, co by zmienił.",
        "state.active": "Termostat sam dostosowuje swoje ustawienia, najwyżej o jeden mały krok dziennie.",
        "state.none": "Jeszcze nic nie zmieniono: wartości początkowe nadal pasują albo jest za mało danych.",
        "learned": "Wyuczone", "learning": "Uczy się: widziano {n} z {m} nagrzewań",
        "learning_seen": "Uczy się: widziano {n} nagrzewań; potrzebuje jeszcze nagrzewań w inne dni lub przy innej temperaturze wody",
        "learning_timing": "Czas nagrzewania wyuczony; najchłodniejszej wody wciąż się uczy",
        "learning_more": "Potrzebuje jeszcze kilku nagrzewań, w inne dni lub przy innych temperaturach wody.",
        "learning_first": "Uczy się z każdego nagrzewania, gdy ogrzewanie pracuje.",
        "learning_mean": "Do tego czasu używa bezpiecznych czasów standardowych.",
        "warms": "Nagrzewa się o około 1 °C w {d} przy wodzie o temperaturze {flow} °C.",
        "warms_mean": "Według tego termostat planuje początek każdego nagrzewania.",
        "lowest": "Najniższa temperatura wody, która jeszcze nagrzewa na czas: {flow} °C.",
        "lowest_mean": "Chłodniejsza woda pozwala kotłowi lepiej kondensować, więc zużywa mniej gazu.",
        "cools": "Traci około {rate} °C na godzinę przy {out} °C na zewnątrz.",
        "cools_mean": "Tak szybko stygnie, gdy ogrzewanie jest wyłączone, na przykład w nocy.",
        "free_heat": "{when} to pomieszczenie samo się nagrzewa, o około {rate} °C na godzinę (słońce, gotowanie lub ludzie).",
        "free_heat_applied": "Następne nagrzewanie zaczyna się dzięki temu {m} min później, więc Inteligentne nagrzewanie "
                             "nie grzeje tego, co przychodzi za darmo.",
        "free_heat_mean": "Inteligentne nagrzewanie uwzględnia to, gdy planuje nagrzewanie o tej porze dnia.",
        "daypart.0": "W nocy", "daypart.1": "Wcześnie rano", "daypart.2": "Rano",
        "daypart.3": "Po południu", "daypart.4": "Wieczorem", "daypart.5": "Późnym wieczorem",
        "start_only": "Zaczyna grzać o {start} przed następnym krokiem programu.",
        "start_mean": "Dzięki temu pomieszczenie jest ciepłe na czas, bez grzania dłużej niż trzeba.",
        "warmup_on": "Inteligentne nagrzewanie: start o {start}, aby o {time} było {target} °C.",
        "warmup_now": "Inteligentne nagrzewanie: grzeje teraz, aby o {time} było {target} °C.",
        "warmup_late": "Inteligentne nagrzewanie: grzeje teraz; {target} °C może być dopiero nieco po {time}.",
        "warmup_ready": "Inteligentne nagrzewanie: jest dość ciepło na {target} °C o {time}, wcześniejszy start nie jest potrzebny.",
        "warmup_learning": "Inteligentne nagrzewanie wciąż się uczy: na razie grzanie zaczyna się o {time} (szacunek: od {start} byłoby {target} °C na czas).",
        "warmup_learning_mean": "Dopóki pomieszczenie nie zostanie wyuczone, nie zaczyna grzać wcześniej na podstawie szacunku.",
        "warmup_off": "Inteligentne nagrzewanie jest wyłączone: grzanie zaczyna się o {time}.",
        "warmup_off_mean": "Włącz Inteligentne nagrzewanie, aby było ciepło na czas.",
        "warmup_estimate": "Inteligentne nagrzewanie: start o {start} (szacunek; uczy się z każdego poranka), aby o {time} było {target} °C.",
        "timing_learned": "Czas nagrzewania jest wyuczony; najchłodniejszej wody wciąż się uczy.",
        "timing_learned_mean": "Inteligentne nagrzewanie już z tego korzysta; do najchłodniejszej wody potrzeba jeszcze kilku nagrzewań przy innych temperaturach wody.",
        "arrival": "{when} ciepło o {time} ({how}).",
        "arrival_earlier": "{when} ciepło o {time} ({how}); następnym razem nagrzewanie zacznie się nieco wcześniej.",
        "arrival_later": "{when} ciepło o {time} ({how}); następnym razem nagrzewanie zacznie się nieco później.",
        "arrival_mean": "Każdego ranka sprawdza, czy pomieszczenie było ciepłe na czas, i dostosowuje czas nagrzewania.",
        "how_late": "{d} za późno",
        "how_early": "{d} za wcześnie",
        "how_on_time": "na czas",
        "when_today": "Dziś",
        "when_yesterday": "Wczoraj",
        "when_date": "Dnia {date}",
        "months": "sty lut mar kwi maj cze lip sie wrz paź lis gru",
        "saving_eur": "około {m3} m³ gazu ({eur}) na noc", "saving": "około {m3} m³ gazu na noc",
        "night_hold": "Utrzymywanie {night} °C w nocy jest tańsze niż wychładzanie: {saving}.",
        "night_program": "Wychładzanie w nocy, tak jak robi to Twój program, jest najtańsze.",
        "night_mean": "To porada: Twój program tygodniowy pozostaje bez zmian.",
        "curve_status_off": "Kompensacja pogodowa: wyłączona, temperatura wody zależy tylko od pomieszczeń.",
        "curve_status_no_outdoor": "Kompensacja pogodowa: teraz brak temperatury zewnętrznej, więc temperatura wody zależy tylko od pomieszczeń.",
        "curve_status_learned": "Kompensacja pogodowa: wyuczona dla Twojego domu.",
        "curve_status_learning": "Kompensacja pogodowa: na razie standardowa, uczy się Twojego domu ({n} z {m} stabilnych okresów).",
        "curve_status_learning_plain": "Kompensacja pogodowa: na razie standardowa, uczy się Twojego domu.",
        "curve_status_house": "Kompensacja pogodowa: na razie oszacowana na podstawie Twojego domu, wciąż się uczy ({n} z {m} stabilnych okresów).",
        "curve_status_house_plain": "Kompensacja pogodowa: na razie oszacowana na podstawie Twojego domu, wciąż się uczy.",
        "curve_status_mean": "E32 sam decyduje, kiedy to, czego się nauczył, jest wystarczająco dobre, by tego używać.",
        "flow_status_collecting": "Najchłodniejsza woda: wciąż uczy się z każdego nagrzewania.",
        "flow_status_ready": "Najchłodniejsza woda: wyuczona dla Twojego domu.",
        "flow_status_advice": "Najchłodniejsza woda: wyuczona; używana, gdy Inteligentne nagrzewanie jest włączone.",
        "flow_status_mean": "Przy chłodniejszej wodzie kocioł lepiej kondensuje, więc zużywa mniej gazu.",
        "curve_learned": "Kompensacja pogodowa wyuczona z Twojego domu: woda jest cieplejsza o około {s} °C na każdy stopień zimniej na zewnątrz.",
        "curve_house": "Kompensacja pogodowa oszacowana na podstawie Twojego domu: woda jest cieplejsza o około {s} °C na każdy stopień zimniej na zewnątrz.",
        "curve": "Kompensacja pogodowa: woda jest cieplejsza o około {s} °C na każdy stopień zimniej na zewnątrz.",
        "curve_on": "Kompensacja pogodowa ustala temperaturę wody, więc kocioł pracuje tak chłodno, jak pozwala pogoda.",
        "curve_off": "Kompensacja pogodowa nie jest włączona; to tylko porada.",
        "burner": "Wczoraj palnik uruchomił się {n} razy do ogrzewania; praca trwała średnio {d}.",
        "burner_starts": "Wczoraj palnik uruchomił się {n} razy do ogrzewania.",
        "burner_often": "To często. Rzadsza, dłuższa praca oszczędza kocioł; termostat nad tym pracuje.",
        "burner_mean": "Rzadsza, dłuższa praca oszczędza kocioł i zużywa gaz wydajniej.",
        "boiler_minimum": "Twój kocioł zaczyna grzać dopiero od wody o temperaturze około {flow} °C; termostat zadaje co najmniej tyle.",
        "boiler_minimum_mean": "Nauczył się tego, gdy kocioł nie uruchamiał się przy chłodniejszej wodzie.",
        "house_none": "Jeszcze nic: pojawi się po pierwszych dniach ogrzewania.",
        "unavailable": "E32 jeszcze nie przekazał, czego się nauczył.",
        # rc7: the sentences review (R1, R3).
        "room_subject": "pomieszczenie {room}",
        "your_rooms_subject": "przeciętne pomieszczenie",
        "warmup_now_estimate": "Inteligentne nagrzewanie: grzeje teraz (szacunek; uczy się z każdego poranka), aby o {time} było {target} °C.",
        "warmup_trial": "Inteligentne nagrzewanie w okresie próbnym: start byłby o {start}, aby o {time} było {target} °C.",
        "warmup_trial_now": "Inteligentne nagrzewanie w okresie próbnym: grzałoby teraz, aby o {time} było {target} °C.",
        "free_heat_later": "Dlatego nagrzewanie zaczyna się {m} min później niż bez darmowego ciepła.",
        "arrival_not_warm": "{when} nie było ciepło w ciągu 3 godz. po {time}.",
        "arrival_not_warm_earlier": "{when} nie było ciepło w ciągu 3 godz. po {time}; następnym razem nagrzewanie zacznie się nieco wcześniej.",
        "saving_eur_once": "około {m3} m³ gazu ({eur})",
        "saving_once": "około {m3} m³ gazu",
        "night_hold_until": "Utrzymywanie {night} °C do {time} jest tańsze niż wychładzanie: {saving}.",
        "night_program_until": "Wychładzanie do {time}, tak jak robi to Twój program, jest najtańsze.",
        "burner_one": "Wczoraj palnik uruchomił się 1 raz do ogrzewania; praca trwała {d}.",
        "burner_starts_one": "Wczoraj palnik uruchomił się 1 raz do ogrzewania.",
        "burner_none": "Wczoraj palnik nie uruchomił się do ogrzewania.",
        "why.few_starts_one": "Grzanie zaczyna się znów wcześniej, przy {to} poniżej zadanej temperatury: przy zaledwie 1 uruchomieniu wczoraj jest miejsce na większy komfort.",
        "would_set": "Zmieniłby ustawienie „{knob}” na {to}, bo {because}.",
        "because.many_starts": "wczoraj palnik uruchomił się {figure} razy",
        "because.cold_during_rest": "{subject} ochłodziło się o {figure} °C poniżej zadanej temperatury, gdy palnik odpoczywał",
        "because.short_burns": "wczoraj palnik {figure} razy pracował bardzo krótko",
        "because.boiler_cycling": "kocioł sam włącza się i wyłącza ({figure} razy wczoraj)",
        "because.overshoot": "{subject} nagrzało się o {figure} °C powyżej zadanej temperatury",
        "because.overshoot_gain": "{subject} wciąż nagrzało się o {figure} °C powyżej zadanej temperatury",
        "because.settled": "{room} prawie już się nie przegrzewa ({figure} °C)",
        "because.hovering": "wczoraj grzanie uruchomiło się {figure} razy przy małych spadkach",
        "because.few_starts": "liczba uruchomień wczoraj wyniosła tylko {figure}",
        "because.few_starts_one": "wczoraj było tylko 1 uruchomienie",
        "because.room_response_up": "{room} nagrzewa się o około 1 °C w {figure}",
        "because.room_response_down": "{room} nagrzewa się o około 1 °C w {figure}",
        "because.learned_warmup": "{room} nagrzewa się o około 1 °C w {figure}",
        "learned_warms": "nagrzewa się o około 1 °C w {d} przy wodzie o temperaturze {flow} °C",
        "curve_slope": "Woda jest cieplejsza o około {s} °C na każdy stopień zimniej na zewnątrz.",
    },
}
# The knobs (control/ControlTuning.h): automatic (AutoTuner) or fixed, the built-in value and how a value reads.
KNOBS = (("min_off_s", True, 300, "rest"), ("min_on_s", True, 300, "run"), ("heat_start_c", True, 0.2, "c"),
         ("heat_stop_c", True, 0.2, "c"), ("flow_per_degree_c", True, 10, "gain"), ("floor_lead_min_per_c", True, 120, "lead"),
         ("radiator_lead_min_per_c", True, 45, "lead"), ("curve_correction_pct", False, 50, "pct"),
         ("learned_accept_pct", False, 100, "pct"), ("night_saving_min_pct", False, 2, "pct"))
KNOB = {key: (auto, default, kind) for key, auto, default, kind in KNOBS}
MINUTE_REASONS = ("room_response", "learned_warmup")


def language(hass):
    """English, Dutch or Polish by the Home Assistant language (English otherwise)."""
    value = (getattr(getattr(hass, "config", None), "language", None) or "en").lower().replace("_", "-").split("-")[0]
    return value if value in TEXT else "en"


def number(value, lang, digits=1):
    """A short decimal: 0.15, 7.5, 21 (a decimal comma in Dutch and Polish)."""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".") if digits else str(round(float(value)))
    return text.replace(".", ",") if lang != "en" else text


def _ok(value):
    return type(value) in (int, float) and value == value and abs(value) < 1e12  # times are unix seconds


def duration(minutes, lang):
    """Minutes in words: "7.5 min" (half minutes below an hour), "1 h 30 min", "2 h"."""
    t = TEXT[lang]
    if minutes < 57.5:
        return t["m"].format(m=number(max(0.5, round(minutes * 2) / 2), lang))
    rounded = int(round(minutes / 5) * 5)
    hours, rest = divmod(rounded, 60)
    return t["h_m"].format(h=hours, m=rest) if rest else t["h"].format(h=hours)


def knob_value(key, value, lang):
    """A knob's value in words, as the E32 page shows it."""
    t, kind = TEXT[lang], KNOB[key][2]
    if kind == "rest":
        return duration(value / 60, lang)
    if kind == "run":
        return t["at_least"].format(d=duration(value / 60, lang))
    if kind == "c":
        return number(value, lang, 2) + " °C"
    if kind == "gain":
        return t["gain"].format(v=number(value, lang, 0))
    if kind == "lead":
        return t["per_c"].format(d=duration(value, lang))
    return number(value, lang, 0) + " %"


def change_text(change, names, lang, proposal=False):
    """One change ([knob, from, to, reason, figure, room]) in words, or None when it is not understood.

    proposal: a change the trial run only proposes (``tuning.would``): "Would set “Burner rest between starts” to
    10 min, because the burner started 25 times yesterday.", never the "now rests" of a change made. A Polish room
    name with a neuter past tense stands after "pomieszczenie" ({subject}); the sentence starts with a capital.
    """
    if type(change) is not list or len(change) != 6:
        return None
    key, old, new, reason, figure, room = change
    if key not in KNOB or not all(_ok(v) for v in (old, new, figure)) or type(reason) is not str or type(room) is not str:
        return None
    t = TEXT[lang]
    if reason == "room_response":
        reason = "room_response_up" if new > old else "room_response_down"
    if reason == "few_starts" and figure == 1:  # "with only 1 start", not "1 starts"
        reason = "few_starts_one"
    template = t.get(("because." if proposal else "why.") + reason)
    if template is None:
        return None
    shown = (duration(figure, lang) if reason.startswith("room_response") or reason == "learned_warmup"
             else str(figure) if float(figure).is_integer() else number(figure, lang, 2))
    name = names.get(room, room) if room else t["your_rooms"]
    if not room:
        subject = t.get("your_rooms_subject", name)
    else:
        subject = t["room_subject"].format(room=name) if "room_subject" in t else name
    values = {"to": knob_value(key, new, lang), "figure": shown, "room": name, "subject": subject}
    text = template.format(**values)
    if proposal:
        text = t["would_set"].format(knob=t["knob." + key], to=values["to"], because=text)
    return text[:1].upper() + text[1:]


def merge_changes(kept, incoming):
    """The newest LOG_KEPT changes ([utc, knob, from, to, reason, figure, room]) of both, newest first."""
    seen, merged = set(), []
    for change in sorted([c for c in list(incoming) + list(kept) if type(c) is list and len(c) == 7 and _ok(c[0])],
                         key=lambda c: -c[0]):
        key = (change[0], change[1])
        if key in seen:
            continue
        seen.add(key)
        merged.append(change)
    return merged[:LOG_KEPT]


def settings(values, manual, lang):
    """{plain name: "10 min (automatic)"} for the knobs in effect."""
    t, out = TEXT[lang], {}
    for key, auto, default, _ in KNOBS:
        value = values.get(key) if type(values) is dict else None
        if not _ok(value):
            continue
        mine = key in manual if auto else value != default
        out[t["knob." + key]] = knob_value(key, value, lang) + " " + t["yours" if mine else "automatic" if auto else "standard"]
    return out


def _line(text, meaning):
    return {"text": text, "meaning": meaning}


def smart_warm_up_line(start, on, lang, clock, trial=False, later_min=0, now=None):
    """(text, meaning) for the room's next program step with Smart warm-up (E32 rc.3), or None.

    ``start``: the room's ``optimum_start``; ``on``: the stored option (``apply_learned``; None: not
    known, on by default). ``applies``: the E32 uses this start (older firmware: a learned warm-up);
    otherwise it is an estimate and heating starts at the program time. The E32 page says the same
    (``data/html/index.html`` smartWarmupLine), "heating now (estimate; ...)" too.

    trial: the trial run (the heat request's mode ``shadow``): the E32 heats nothing early, so the line says what
    it would do. later_min: the minutes the free heat moves the start later (``free_heat.applied_min``,
    FreeHeat::shorten in FlowPolicy; the telemetry's ``predicted_start_utc`` is the start without it), so the
    line names the start the E32 really uses; now: unix seconds (for "heating now" once the later start passed).
    """
    t = TEXT[lang]
    start = start if type(start) is dict else {}
    switch = start.get("next_switch") if type(start.get("next_switch")) is dict else {}
    if (start.get("reason") != "planned" or not _ok(start.get("predicted_start_utc"))
            or not _ok(switch.get("utc")) or not _ok(switch.get("target_c"))):
        return None
    shift = later_min * 60 if type(later_min) is int and later_min > 0 and on is not False else 0
    begin = start["predicted_start_utc"] + shift
    values = {"start": clock(begin), "time": clock(switch["utc"]), "target": number(switch["target_c"], lang)}
    applies = start["applies"] if type(start.get("applies")) is bool else start.get("confidence") == "learned"
    # With the free heat the E32 starts later: "heating now" only once that later start has come.
    heating = start.get("start_now") is True and (not shift or begin <= (time.time() if now is None else now))
    if on is False:
        return t["warmup_off"].format(**values), t["warmup_off_mean"]
    if not applies:
        return t["warmup_learning"].format(**values), t["warmup_learning_mean"]
    if start.get("lead_minutes") == 0 and start.get("start_now") is not True:
        key = "warmup_ready"
    elif heating:
        key = ("warmup_trial_now" if trial else "warmup_late" if start.get("reachable") is False
               else "warmup_now_estimate" if start.get("estimate") is True else "warmup_now")
    elif trial:
        key = "warmup_trial"
    else:  # E32 rc.4: a start from the standard warm-up time is applied too, as an estimate
        key = "warmup_estimate" if start.get("estimate") is True else "warmup_on"
    return t[key].format(**values), t["state.shadow" if trial and key != "warmup_ready" else "start_mean"]


def whole_minutes(minutes, lang):
    """Whole minutes in words, exact: "12 min", "1 h 35 min", "2 h" (duration() rounds above an hour)."""
    t = TEXT[lang]
    if minutes < 60:
        return t["m"].format(m=minutes)
    hours, rest = divmod(minutes, 60)
    return t["h_m"].format(h=hours, m=rest) if rest else t["h"].format(h=hours)


NOT_WARM_MIN = 180   # ArrivalLearner::Params::windowS: a room not warm within 3 h counts as 3 h late
LATE_MIN, EARLY_MIN = 10, -15   # ArrivalLearner lateS (600 s) and earlyS (900 s): the factor changes beyond these
FACTOR_LIMITS = (0.5, 2.0)      # ArrivalLearner minFactor and maxFactor


def arrival_line(arrival, lang, clock, day=None, today=None):
    """(text, meaning) on how the room's last program step up turned out (E32 rc.4), or None.

    ``arrival`` (the room's plan): ``last_at_utc`` the program's switch time of the last judged morning,
    ``last_error_min`` how many minutes after it the room was warm (negative: before it; the room was
    warm at last_at_utc + last_error_min, ArrivalLearner::resolve), ``factor`` what the E32 now does
    with the warm-up time (above 1: it starts earlier). clock: utc -> "09:12"; day: utc -> the local
    date; today: the local date now ("Yesterday warm at 09:12 (12 min late); next time it starts a little earlier.").

    What changes next time follows from this morning alone, with the E32's own thresholds (more than 10 min late:
    earlier; more than 15 min early: later; not beyond its limits), not from the factor, which is the product of
    every morning so far. A room not warm within 3 hours counts as 3 hours late on the E32: "not warm within 3
    hours after 07:00", never a moment it was not warm.
    """
    t = TEXT[lang]
    arrival = arrival if type(arrival) is dict else {}
    at, error, factor = arrival.get("last_at_utc"), arrival.get("last_error_min"), arrival.get("factor")
    if not _ok(at) or at <= 0 or not _ok(error) or not -1440 <= error <= 1440:
        return None
    day = day or (lambda utc: datetime.fromtimestamp(utc, timezone.utc).date())
    today = today or day(time.time())
    on = day(at)
    if on == today:
        when = t["when_today"]
    elif on == today - timedelta(days=1):
        when = t["when_yesterday"]
    else:
        when = t["when_date"].format(date=f"{on.day} {t['months'].split()[on.month - 1]}")
    minutes = round(error)
    factor = factor if _ok(factor) else None
    earlier = minutes >= LATE_MIN and (factor is None or factor < FACTOR_LIMITS[1] - 1e-3)
    later = minutes <= EARLY_MIN and (factor is None or factor > FACTOR_LIMITS[0] + 1e-3)
    if minutes >= NOT_WARM_MIN:
        key = "arrival_not_warm_earlier" if earlier else "arrival_not_warm"
        return t[key].format(when=when, time=clock(at)), t["arrival_mean"]
    how = (t["how_late"].format(d=whole_minutes(minutes, lang)) if minutes > 0
           else t["how_early"].format(d=whole_minutes(-minutes, lang)) if minutes < 0 else t["how_on_time"])
    key = "arrival_earlier" if earlier else "arrival_later" if later else "arrival"
    # The moment the room was warm: the switch time plus the error (the E32's Home page shows the same moment).
    return t[key].format(when=when, time=clock(at + minutes * 60), how=how), t["arrival_mean"]


FREE_HEAT_DAYPARTS = 6        # FreeHeat: six local dayparts of 4 hours from midnight
FREE_HEAT_MIN_COUNT = 5       # FreeHeat::rateKPerH: an expected free rise from 5 windows
FREE_HEAT_MIN_RATE = 0.05     # K/h: below about 0.1 °C an hour it is not worth a line


def free_heat(learned, plan=None):
    """(daypart, rate in °C per hour, minutes Smart warm-up starts later) of the room's strongest free heat, or None.

    ``free_heat`` (E32 rc.5, FreeHeat::addJson) of the learned room, else of its plan: {"rate": [6 x °C per hour
    or null], "n": [6 counts], "applied_min": n}. A daypart counts with 5 windows or more, as on the E32.
    """
    part = learned.get("free_heat") if type(learned) is dict else None
    if type(part) is not dict:
        part = plan.get("free_heat") if type(plan) is dict else None
    if type(part) is not dict:
        return None
    rates, counts = part.get("rate"), part.get("n")
    if (type(rates) is not list or type(counts) is not list or len(rates) != FREE_HEAT_DAYPARTS
            or len(counts) != FREE_HEAT_DAYPARTS):
        return None
    best = None
    for daypart, (rate, count) in enumerate(zip(rates, counts)):
        if (_ok(rate) and FREE_HEAT_MIN_RATE <= rate <= 10 and type(count) is int and count >= FREE_HEAT_MIN_COUNT
                and (best is None or rate > best[1])):
            best = (daypart, rate)
    if best is None:
        return None
    applied = part.get("applied_min")
    return best[0], best[1], applied if type(applied) is int and 0 < applied <= 1440 else 0


def free_heat_later(learned, plan=None):
    """The minutes the free heat moves the room's next warm-up later (``free_heat.applied_min`` of the learned room,
    else of its plan; FreeHeat::shorten), 0 without."""
    for item in (learned, plan):
        part = item.get("free_heat") if type(item) is dict else None
        if type(part) is dict:
            applied = part.get("applied_min")
            return applied if type(applied) is int and 0 < applied <= 1440 else 0
    return 0


def free_heat_line(learned, plan, lang, smart=None, after_start=False):
    """(text, meaning) on the heat the room gets for free (sun, cooking, people), or None.

    smart: the Smart warm-up option (False: off, so no warm-up starts later, whatever the E32 counts);
    after_start: the line follows the Smart warm-up line that already names the later start ("So the warm-up starts
    20 min later than without the free heat.").
    """
    found = free_heat(learned, plan)
    if found is None:
        return None
    t, (daypart, rate, applied) = TEXT[lang], found
    text = t["free_heat"].format(when=t[f"daypart.{daypart}"], rate=number(rate, lang, 1))
    if not applied or smart is False:
        return text, t["free_heat_mean"]
    return text, t["free_heat_later" if after_start else "free_heat_applied"].format(m=applied)


def free_heat_lines(rooms, lang, smart=None):
    """[{name, text, meaning}] of the rooms with free heat (free_heat_line), in order; rooms: [(name, learned, plan)]."""
    return [{"name": name, "text": found[0], "meaning": found[1]} for name, learned, plan in rooms
            if (found := free_heat_line(learned, plan, lang, smart)) is not None]


# The comfort modes that hold the week program on the E32: no early warm-up towards its next rise
# (RoomOverrides::holdsProgram, HeatingController::applyFlowPolicy).
HELD_MODES = ("away", "presence_away", "window_open")
CURRENCY_SIGNS = {"EUR": "€", "GBP": "£", "USD": "$", "PLN": "zł"}
NIGHT_HOURS = range(3, 12)  # a step up between 03:00 and 12:00 ends a night setback


def money(value, lang, currency=None):
    """An amount with exactly two decimals in Home Assistant's currency: "€0.15", "€ 0,15" (Dutch), "0,15 zł"."""
    amount = f"{float(value):.2f}"
    amount = amount.replace(".", ",") if lang != "en" else amount
    if not currency:
        return amount
    sign = CURRENCY_SIGNS.get(currency, currency)
    if lang == "pl" or sign not in ("€", "£", "$"):
        return f"{amount} {sign}"
    return f"{sign} {amount}" if lang == "nl" else f"{sign}{amount}"


def room_overview(name, learned, plan, lang, clock, smart=None, day=None, today=None, room_id=None, comfort=None,
                  trial=False, currency=None, now=None):
    """{name, room_id, progress, summary, lines: [{text, meaning}]} of one room; clock: utc -> "07:10" in local time.

    day: utc -> the local date, today: the local date now (for "Yesterday warm at 09:12", arrival_line).
    comfort: the room's ``comfort`` (its mode: away or an open window holds the program, so no Smart warm-up line);
    trial: the trial run; currency: Home Assistant's (the night advice's money); summary: once learned, how fast it
    warms in a few words (the Learning tab's progress list).
    """
    t = TEXT[lang]
    learned = learned if type(learned) is dict else {}
    ready = learned.get("readiness") == "ready"
    seen = min(WARMUPS_TO_LEARN, learned["segments"]) if _ok(learned.get("segments")) else 0
    lines = []
    if not ready and learned.get("readiness_timing") == "ready":  # E32 rc.4: the warm-up time from one water temperature
        lines.append(_line(t["timing_learned"], t["timing_learned_mean"]))
    elif not ready:
        lines.append(_line(t["learning_more" if seen >= WARMUPS_TO_LEARN else "learning_first"], t["learning_mean"]))
    advice = next((a for a in learned.get("advice") or [] if type(a) is dict and a.get("shortfall_c") == 1), None)
    summary = None
    if ready and advice and _ok(advice.get("rule_warmup_h")) and _ok(advice.get("rule_flow_c")):
        values = {"d": duration(advice["rule_warmup_h"] * 60, lang), "flow": number(advice["rule_flow_c"], lang, 0)}
        lines.append(_line(t["warms"].format(**values), t["warms_mean"]))
        summary = t["learned_warms"].format(**values)
    if ready and advice and _ok(advice.get("flow_c")) and advice.get("reason") in ("learned", "lowest_learned"):
        lines.append(_line(t["lowest"].format(flow=number(advice["flow_c"], lang, 0)), t["lowest_mean"]))
    # A loss that rounds to 0 °C per hour ("loses about 0 °C") says nothing: left out.
    if _ok(learned.get("loss_per_h")) and learned["loss_per_h"] * (REFERENCE_ROOM_C - REFERENCE_OUTDOOR_C) >= 0.01:
        rate = learned["loss_per_h"] * (REFERENCE_ROOM_C - REFERENCE_OUTDOOR_C)
        lines.append(_line(t["cools"].format(rate=number(rate, lang, 2), out=REFERENCE_OUTDOOR_C), t["cools_mean"]))
    plan = plan if type(plan) is dict else {}
    start = plan.get("optimum_start") if type(plan.get("optimum_start")) is dict else {}
    comfort = comfort if type(comfort) is dict else {}
    held = comfort.get("mode") in HELD_MODES or comfort.get("window") == "open"
    later = free_heat_later(learned, plan)
    warm = None if held else smart_warm_up_line(start, smart, lang, clock, trial, later, now)
    if warm is not None:
        lines.append(_line(*warm))
    elif not held and start.get("reason") == "planned" and _ok(start.get("predicted_start_utc")):
        # firmware before rc.2: no next switch
        lines.append(_line(t["start_only"].format(start=clock(start["predicted_start_utc"])), t["start_mean"]))
    # E32 rc.5: sun, cooking and people, after the Smart warm-up line, which names the later start it gives.
    if (free := free_heat_line(learned, plan, lang, False if held else smart, warm is not None)) is not None:
        lines.append(_line(*free))
    if (arrived := arrival_line(plan.get("arrival"), lang, clock, day, today)) is not None:
        lines.append(_line(*arrived))
    night = plan.get("night") if type(plan.get("night")) is dict else {}
    if night.get("reason") == "estimated" and type(night.get("recommended")) is str:
        hold = night["recommended"] not in ("program", "thermostat_like") and _ok(night.get("recommended_night_c"))
        m3 = number(night["saving_m3"] if _ok(night.get("saving_m3")) else 0, lang, 2)
        # The advice is for the setback before the next step up: "at night" only when that step ends a night.
        switch = start.get("next_switch") if type(start.get("next_switch")) is dict else {}
        rise = clock(switch["utc"]) if _ok(switch.get("utc")) else None
        nightly = rise is None or not rise[:2].isdigit() or int(rise[:2]) in NIGHT_HOURS
        once = "" if nightly else "_once"
        saving = (t["saving_eur" + once].format(m3=m3, eur=money(night["saving_eur"], lang, currency))
                  if _ok(night.get("saving_eur")) and night["saving_eur"] > 0 else t["saving" + once].format(m3=m3))
        if hold:
            text = t["night_hold" if nightly else "night_hold_until"].format(
                night=number(night["recommended_night_c"], lang), saving=saving, time=rise)
        else:
            text = t["night_program" if nightly else "night_program_until"].format(time=rise)
        lines.append(_line(text, t["night_mean"]))
    # "6 of 6" read as finished while the E32 still waits for other days or a second water temperature
    # (FlowLearner readiness: 6 warm-ups in 3 heating periods and 2 water temperatures): then say what is missing.
    if ready:
        progress = t["learned"]
    elif learned.get("readiness_timing") == "ready":
        progress = t["learning_timing"]
    elif seen >= WARMUPS_TO_LEARN:
        progress = t["learning_seen"].format(n=learned["segments"])
    else:
        progress = t["learning"].format(n=seen, m=WARMUPS_TO_LEARN)
    return {"name": name, "room_id": room_id, "progress": progress, "summary": summary, "lines": lines}


def boiler_minimum_flow(summary):
    """The lowest water temperature the boiler fires at for heating (°C), as the E32 learned it, or None.

    ``learned.boiler_minimum_flow_c`` of the summary (FlowLearner, E32 rc.2): only there once learned
    above the plan's minimum; older firmware never sends it. A value outside 20..90 °C is not shown.
    """
    learned = summary.get("learned") if type(summary) is dict and type(summary.get("learned")) is dict else {}
    value = learned.get("boiler_minimum_flow_c")
    return value if _ok(value) and 20 <= value <= 90 else None


CURVE_STEPS = 6  # CurveLearner::Params::minWindows: steady 3-hour periods before the learned curve is used


def curve_status(curve, on, lang):
    """(text, meaning) for what the heating curve uses now (E32 rc.3, on by default), or None.

    ``curve``: the summary's ``flow.curve`` (state, slope_source, windows); ``on``: the stored option
    ``weather_curve`` (None: not known, on by default).
    """
    t = TEXT[lang]
    if type(curve) is not dict or curve.get("state") in (None, "no_room"):
        return None
    if on is False:
        return t["curve_status_off"], t["curve_off"]
    if curve.get("state") == "no_outdoor":
        return t["curve_status_no_outdoor"], t["curve_status_mean"]
    if curve.get("slope_source") == "learned":
        return t["curve_status_learned"], t["curve_status_mean"]
    # E32 rc.5: until 6 steady periods, the slope the house model works out (HouseModel), else the standard one.
    key = "curve_status_house" if curve.get("slope_source") == "house" else "curve_status_learning"
    windows = curve.get("windows")
    if type(windows) is int and windows >= 0:
        return t[key].format(n=min(windows, CURVE_STEPS), m=CURVE_STEPS), t["curve_status_mean"]
    return t[key + "_plain"], t["curve_status_mean"]


def learned_flow_status(learned, smart, lang):
    """(text, meaning) for the learned coolest water (the summary's ``flow.learned``), or None."""
    t = TEXT[lang]
    state = learned.get("state") if type(learned) is dict else None
    # "held" (E32 rc.5): the boiler's own ceiling binds; the boiler sentence (insight.py) says so.
    if type(state) is not str or state in ("no_room", "held"):
        return None
    if state == "not_ready":
        return t["flow_status_collecting"], t["flow_status_mean"]
    return t["flow_status_advice" if smart is False else "flow_status_ready"], t["flow_status_mean"]


def house_overview(summary, lang, options=None):
    """[{text, meaning}] for the heating curve, the burner and the boiler's learned minimum flow, from the summary.

    ``options``: the E32's stored flow options when known (weather_curve, apply_learned).
    """
    t, lines = TEXT[lang], []
    summary = summary if type(summary) is dict else {}
    options = options if type(options) is dict else {}
    flow = summary.get("flow") if type(summary.get("flow")) is dict else {}
    curve = flow.get("curve") if type(flow.get("curve")) is dict else None
    status = curve_status(curve, options.get("weather_curve"), lang)
    slope = number(curve["slope"], lang, 2) if curve is not None and _ok(curve.get("slope")) else None
    # Weather compensation once: what it uses now and, while it is on, how steep its line is, in one line
    # ("Weather compensation: learned for your house. The water gets about 0.85 °C warmer ...").
    on = options.get("weather_curve") is not False and curve is not None and curve.get("state") != "no_outdoor"
    if status is not None and slope is not None and on:
        lines.append(_line(status[0] + " " + t["curve_slope"].format(s=slope),
                           t["curve_on" if curve.get("state") == "applied" else "curve_off"]))
    elif status is not None:
        lines.append(_line(*status))
    elif slope is not None:
        source = curve.get("slope_source")
        key = "curve_learned" if source == "learned" else "curve_house" if source == "house" else "curve"
        lines.append(_line(t[key].format(s=slope), t["curve_on" if curve.get("state") == "applied" else "curve_off"]))
    if (learned := learned_flow_status(flow.get("learned"), options.get("apply_learned"), lang)) is not None:
        lines.append(_line(*learned))
    tuning = summary.get("tuning") if type(summary.get("tuning")) is dict else {}
    yesterday = tuning.get("yesterday") if type(tuning.get("yesterday")) is dict else None
    if yesterday and _ok(yesterday.get("starts")):
        starts, hours = yesterday["starts"], yesterday.get("heating_h") if _ok(yesterday.get("heating_h")) else 0
        one = "_one" if starts == 1 else ""  # "started once", not "1 times"; none: "did not start"
        text = (t["burner_none"] if starts == 0
                else t["burner" + one].format(n=starts, d=duration(yesterday["burn_s"] / 60, lang))
                if _ok(yesterday.get("burns")) and yesterday["burns"] > 0 and _ok(yesterday.get("burn_s"))
                else t["burner_starts" + one].format(n=starts))
        lines.append(_line(text, t["burner_often" if hours > 0 and starts > 3 * hours else "burner_mean"]))
    lowest = boiler_minimum_flow(summary)
    if lowest is not None:
        lines.append(_line(t["boiler_minimum"].format(flow=number(lowest, lang, 0)), t["boiler_minimum_mean"]))
    return lines or [_line(t["house_none"], None)]


def local_clock(hass):
    """utc -> "07:10" in Home Assistant's time zone."""
    from homeassistant.util import dt as dt_util
    return lambda utc: dt_util.as_local(datetime.fromtimestamp(utc, timezone.utc)).strftime("%H:%M")


def local_day(hass):
    """(utc -> the local date, today's local date) in Home Assistant's time zone."""
    from homeassistant.util import dt as dt_util
    return lambda utc: dt_util.as_local(datetime.fromtimestamp(utc, timezone.utc)).date(), dt_util.now().date()


class LearnedStoredData(ExtraStoredData):
    def __init__(self, data):
        self.data = data

    def as_dict(self):
        return self.data


class LearnedOverviewSensor(RestoreEntity, SensorEntity):
    """What the thermostat learned: state = the newest change (or what it does); the overview as attributes."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "learned_overview"
    _attr_icon = "mdi:school-outline"
    # The texts are shown, not kept in the history.
    _unrecorded_attributes = frozenset({"rooms", "house", "changes", "settings", "explanation", "insights", "free_heat"})

    def __init__(self, entry, hub, clock=None):
        self.entry, self.hub = entry, hub
        self._clock = clock
        self._attr_unique_id = f"{hub.prefix}_hub_learned_overview"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.prefix)})
        self.log = []

    def _lang(self):
        return language(getattr(self, "hass", None))

    def _tuning(self):
        summary = self.hub.summary if type(self.hub.summary) is dict else {}
        return summary.get("tuning") if type(summary.get("tuning")) is dict else None

    def _flow_options(self):
        """The E32's flow options as last read (e32_flow.py), or None."""
        from .e32_flow import KEY
        data = getattr(getattr(self, "hass", None), "data", None)
        link = data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get(KEY) if isinstance(data, dict) else None
        return getattr(link, "settings", None)

    def _names(self):
        """The rooms by the name the dashboard shows (renamed in Home Assistant or not; insight.room_names)."""
        from .insight import room_names
        return room_names(self.hub, getattr(self, "hass", None), getattr(self.entry, "entry_id", None))

    @callback
    def _hub_changed(self):
        tuning = self._tuning()
        merged = merge_changes(self.log, tuning.get("log") or []) if tuning else self.log
        if merged != self.log:
            self.log = merged
        if getattr(self, "hass", None) is not None and self.entity_id:
            self.async_write_ha_state()

    @property
    def available(self):
        return self.hub.fresh or bool(self.log)

    @property
    def native_value(self):
        lang, tuning = self._lang(), self._tuning()
        names = self._names()
        for change in self.log:
            text = change_text(change[1:], names, lang)
            if text:
                return text[:STATE_MAX]
        state = tuning.get("state") if tuning else None
        return TEXT[lang].get("state." + state, TEXT[lang]["state.none"])[:STATE_MAX] if state else TEXT[lang]["unavailable"][:STATE_MAX]

    @property
    def extra_state_attributes(self):
        lang, tuning = self._lang(), self._tuning() or {}
        t, names = TEXT[lang], self._names()
        clock = self._clock or (local_clock(self.hass) if getattr(self, "hass", None) is not None else (lambda utc: time.strftime("%H:%M", time.gmtime(utc))))
        changes = []
        # The trial run's proposals first, without a time ("Would set ..."): never the dashboard's "Latest change".
        for proposal in tuning.get("would") or []:
            text = change_text(proposal, names, lang, proposal=True)
            if text:
                changes.append({"time": None, "text": text})
        for change in self.log:
            text = change_text(change[1:], names, lang)
            if text:
                changes.append({"time": datetime.fromtimestamp(change[0], timezone.utc).isoformat(timespec="seconds"), "text": text})
        from .e32_flow import smart_warm_up
        smart = smart_warm_up(self.hass, self.entry.entry_id) if getattr(self, "hass", None) is not None else None
        day, today = local_day(self.hass) if getattr(self, "hass", None) is not None and self._clock is None else (None, None)
        active = [(room_id, name) for room_id, name in names.items() if self.hub.rooms[room_id].get("state") != "inactive"]
        trial = (self.hub.status or {}).get("mode") == "shadow"  # the trial run: the E32 heats nothing early
        currency = getattr(getattr(getattr(self, "hass", None), "config", None), "currency", None)
        rooms = [room_overview(name, self.hub.learned.get(room_id), self.hub.warmup.get(room_id), lang, clock, smart,
                               day, today, room_id, self.hub.rooms[room_id].get("comfort"), trial, currency)
                 for room_id, name in active]
        manual = tuning.get("manual") if type(tuning.get("manual")) is list else []
        from .insight import insight_lines  # E32 rc.5: yesterday against the house's own usual days
        attributes = {"explanation": t.get("state." + str(tuning.get("state")), "") if tuning else t["unavailable"],
                      "rooms": rooms, "house": house_overview(self.hub.summary, lang, self._flow_options()),
                      "changes": changes or [{"time": None, "text": t["state.none"]}],
                      "settings": settings(tuning.get("values"), manual, lang),
                      "insights": insight_lines(self.hub.summary, names, lang),
                      "free_heat": free_heat_lines([(name, self.hub.learned.get(room_id), self.hub.warmup.get(room_id))
                                                    for room_id, name in active], lang, smart)}
        lowest = boiler_minimum_flow(self.hub.summary)
        if lowest is not None:  # only once learned
            attributes["boiler_minimum_flow_c"] = lowest
        return attributes

    @property
    def extra_restore_state_data(self):
        return LearnedStoredData({"log": self.log})

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        stored = await self.async_get_last_extra_data()
        if stored is not None:
            self.log = merge_changes([], (stored.as_dict() or {}).get("log") or [])
        self.async_on_remove(self.hub.add_listener(self._hub_changed))
        self._hub_changed()


async def async_setup_learned_overview(hass, entry, async_add_entities, options, hub):
    """Product entries: the overview sensor on the product device."""
    sensor = LearnedOverviewSensor(entry, hub)
    hass.data[DOMAIN][entry.entry_id]["learned_overview"] = sensor
    async_add_entities([sensor], **options)
