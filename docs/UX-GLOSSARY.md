# UX glossary

One set of words for the same thing on the E32 pages (English, Dutch) and in the
Home Assistant integration (English, Dutch, Polish). Labels say what something
does for the user; a technical term stays only where users meet it elsewhere
(on the boiler, in a manual, in Home Assistant), and is then explained once,
usually in brackets.

Polish texts quote the English E32 labels, because the E32 pages exist in
English and Dutch only.

| English | Nederlands | Polski | Meaning |
| --- | --- | --- | --- |
| Water temperature to heating (flow temperature) | Watertemperatuur naar verwarming (aanvoertemperatuur) | Temperatura wody do ogrzewania (zasilanie) | The temperature of the water the boiler sends to the radiators and floor. Short form on tiles and charts: "Water to heating" / "Water naar verwarming". |
| Water temperature back (return temperature) | Watertemperatuur terug (retour) | Temperatura wody powrotnej (powrót) | The temperature of the water coming back to the boiler. Short form: "Water back" / "Water terug". |
| Water temperature limits | Grenzen watertemperatuur | Limity temperatury wody | The lowest and highest water temperature the E32 may ask of the boiler, for all rooms together (were: flow temperature limits). |
| Lowest / highest water temperature | Laagste / hoogste watertemperatuur | Najniższa / najwyższa temperatura wody | The two water temperature limits. |
| Water temperature target (boiler / thermostat) | Doel watertemperatuur (ketel / thermostaat) | Docelowa temperatura wody (kocioł / termostat) | The water temperature the boiler aims for, or the thermostat asked for (was: selected / target flow temperature). |
| Boiler request (E32) | Ketelvraag (E32) | Żądanie do kotła (E32) | What the E32 asks (or, during the trial run, would ask) of the boiler: a water temperature, or off. |
| Target temperature | Gewenste temperatuur | Temperatura docelowa (zadana) | The room temperature you want (was: setpoint). |
| Burner power | Brandervermogen | Moc palnika | How hard the burner works, as a percentage of its maximum, as the boiler reports it (was: modulation). Not kW and not measured gas. |
| Pump speed | Pompsnelheid | Prędkość pompy | How fast the heating pump runs, in % (was: pump modulation). |
| Switching margin (hysteresis) | Schakelmarge (hysterese) | Margines przełączania (histereza) | A boiler setting: how far the water may drift from its target before the burner switches on or off. |
| Burner rest between starts (minimum burner period) | Rusttijd brander tussen starts (anti-pendeltijd) | Przerwa palnika między startami | A boiler setting: the burner stays off at least this long before it starts again, so the boiler switches on and off less often. |
| Burner finishing its shortest run | Brander maakt zijn kortste brandtijd af | Palnik kończy najkrótszą pracę | Room status: once started, the burner runs a minimum time, even when the room is warm enough. |
| Burner resting before the next start | Brander rust voor de volgende start | Palnik odpoczywa przed kolejnym startem | Room status: the E32 waits before it asks for heat again, to spare the boiler. |
| Burner switching on and off too often (short cycling) | Brander slaat te vaak aan en uit (pendelen) | Palnik zbyt często się włącza | More burner starts per hour than is good for gas use and wear. |
| Trial run (shadow mode) | Proefperiode (schaduwmodus) | Okres próbny | The E32 works out what it would ask of the boiler and compares it with your thermostat, but sends nothing to the boiler. Home Assistant does set each room's setting device. |
| Active control | Actieve regeling | Aktywne sterowanie | The E32 controls the boiler itself; your old thermostat is disconnected. |
| Switch over / switch-over (takeover) | Overstappen (overname) | Przełączenie (przejęcie) | The one attended step from the trial run to active control, while you are at home. |
| Ready for E32 control | Klaar voor regeling door de E32 | Gotowość do sterowania przez E32 | The E32's own check whether the trial run shows it is ready to control the boiler. |
| Give control back to my thermostat | Regeling teruggeven aan mijn thermostaat | Oddanie sterowania termostatowi | Back from active control to the trial run; the E32 first asks the boiler for no heat for a minute. |
| Backup sensor (fallback source) | Reservesensor (terugvalbron) | Czujnik zapasowy | A second temperature sensor of a room, used when the first one stops reporting. |
| Heating curve | Stooklijn | Krzywa grzewcza | The water temperature follows the outdoor temperature: colder outside, warmer water. The switch is called "Follow outdoor temperature (heating curve)". |
| Water temperature at −10 °C outside | Watertemperatuur bij −10 °C buiten | Temperatura wody przy −10 °C na zewnątrz | The heating curve's setting: how warm the water gets on a very cold day (was: design flow). |
| Smart warm-up | Slim opwarmen | Inteligentne nagrzewanie | On by default (rc.3): a time in the week program means "warm at that time". Uses what the E32 learned per room: an early start so it is warm at the program time, with the coolest water that still does it (was: Warm on time with the coolest water; before that: learned flow and optimum start). Off: heating starts at the program time. Not "Eco": that is a week-planner level. |
| Learned water temperature | Geleerde watertemperatuur | Wyuczona temperatura wody | The water temperature the E32 learned a room needs (was: learned flow). |
| Warm on time (early start) | Op tijd warm (vroege start) | Ciepło na czas (wczesny start) | Heating starts early enough to reach the next program temperature on time (was: optimum start). |
| Recommended water temperature | Geadviseerde watertemperatuur | Zalecana temperatura wody | The coolest water that still warms a room 1 °C in time (was: recommended flow). |
| Room control | Ruimteregeling | Regulacja pokojowa | The E32's normal control from the room temperature (was: PI / rule). |
| Keeping hot water warm (keep-warm) | Warm water warmhouden | Podtrzymanie ciepłej wody | The boiler reheating its hot water store or exchanger without a tap open. |
| Hot water (DHW) | Warm water | Ciepła woda (c.w.u.) | Tap water heated by the boiler. |
| Boiler bus (EMS) | Ketelbus (EMS) | Magistrala kotła (EMS) | The two-wire connection over which the E32 hears and talks to the boiler. "EMS" stays in brackets because boiler manuals use it. |
| Boiler message (telegram) | Ketelbericht | Komunikat kotła | One message on the boiler bus. |
| What your boiler reports (boiler profile) | Wat je ketel meldt | Co zgłasza Twój kocioł | The Boiler page list of values this boiler sends. |
| Setting device | Instelapparaat | Urządzenie nastawcze | A thermostat, radiator valve or number helper in Home Assistant you set a room with. |
| Home Assistant entity | Home Assistant-entiteit | Encja Home Assistant | Kept: Home Assistant's own word for one of its items, for example `climate.living_room`. |
| Room | Ruimte | Pomieszczenie | One heated space of the E32 room plan. In Polish texts a room name stands after "Pomieszczenie" or before a colon, so the sentence fits any name. |
| Week program | Weekprogramma | Program tygodniowy | The switch points of a room for the seven days of the week. |
| Switch point (switch time) | Schakeltijd | Punkt przełączenia | One time in the week program from which a temperature applies until the next one. |
| Comfort / Eco / Night | Comfort / Eco / Nacht | Komfort / Eko / Noc | The three temperature levels of the week planner. |
| Tapping (hot water) | Tappen | Pobór (ciepłej wody) | Hot water used at a tap, as opposed to keeping hot water warm. |
| Missed comfort | Gemiste comfort | Utracony komfort | Minutes a room asked for heat but stayed clearly below its target. |
| Night setback | Nachtverlaging | Nocne obniżenie | A lower target temperature at night. |
| Maximum heating temperature (boiler) | Maximale cv-temperatuur | Maksymalna temperatura c.o. | The boiler's own upper limit for the water to the heating. |
| Pump run-on | Pompnaloop | Wybieg pompy | A boiler setting: how long the pump keeps running after the burner stops. |
| Expansion vessel | Expansievat | Naczynie wzbiorcze | The vessel that takes up the water's expansion; it keeps the pressure steady. |
