# Zelf leren dat echt werkt — plan voor de volgende firmware-release (3 november 2026)

Beoordeling van het zelflerende deel van de E32 op de code van rc.3
(`FlowLearner`, `WarmupPlanner`, `FlowPolicy`, `AutoTuner`, `CurveLearner`,
`BoilerMinimumFlow`) naast de stand in het huis van de eigenaar op 3 november,
2,5 dag na de overstap: woonkamer 3 van 6 opwarmingen, 2 periodes; afkoeling
onbekend; stooklijn 1 van 6 rustige periodes; ketelminimum 37 °C geleerd;
zelf bijstellen "nog niets veranderd"; Slim opwarmen alleen advies.

## Kort

De basis is goed: alles leert lokaal, elke stap is begrensd, alles wordt
bewaard, elk onderdeel is los te testen en de afspeelbank
([tools/replay](../../tools/replay/README.md)) draait het op echte data.

Het leren is te zuinig met bewijs. Het leert alleen van zeldzame "schone"
stukjes, en bij een ketel met een warmwatervoorraad komen die bijna niet.
Daardoor doet de belangrijkste functie, Slim opwarmen, in dit huis na 2,5 dag
nog niets. Vier concrete blokkades, allemaal firmware:

| # | Blokkade | Waar | Gevolg |
| --- | --- | --- | --- |
| B1 | Elke warmwaterronde of tap zet de afkoelmeting terug op nul: `if (!heat && (… \|\| hotWater)) offSince_ = now;` en `coasted` eist `!hotWater` | `FlowLearner::sample` | Afkoeling (verliesfactor b) wordt met een voorraadvat praktisch nooit geleerd. `WarmupPlanner::Start::applicable()` eist `coolingLearned` → Slim opwarmen past zich nooit toe |
| B2 | Vóór het leren past Slim opwarmen niets toe: `apply` eist `start_.learned` | `FlowPolicy::optimumStart` | De standaardschatting (voorlooptijd per °C, sinds rc.2 vanaf de huidige kamertemperatuur) wordt alleen getoond; de kamer begint op de programmatijd en is te laat warm |
| B3 | "Klaar" eist 2 gevulde aanvoerbakken (elk 3 metingen in 2 periodes) | `FlowLearner::readiness`, `Params::roomBins = 2` | Met de weerafhankelijke regeling aan vraagt de E32 bijna altijd dezelfde watertemperatuur (nu 30–37 °C); de tweede bak vult zich in weken |
| B4 | 24 uur wachttijd na elke herstart, elk opgeslagen plan en elke afstelwijziging; `restart()` wist de dagtellers (alleen RAM) | `AutoTuner::graceMs`, `HeatingController.h` regels 349 en 456 | Met de updates van 1–3 november is er nog nooit een dag beoordeeld |

Wat structureel ontbreekt: **terugkoppeling op de uitkomst**. Nergens wordt
gemeten of de kamer op tijd warm was. De eerdere analyse
([LEREN-ANALYSE.nl.md](LEREN-ANALYSE.nl.md), §5) vond de geleerde
opwarmsnelheid ~15 % te optimistisch; niets corrigeert dat.

De eigenaar: "in de weekplanner ga je ervan uit dat je op die tijd de gewenste
temperatuur wilt." Te vroeg is dus beter dan te laat, en het leren moet
binnen dagen zichtbaar zijn, niet binnen weken.

## Maatregelen, in volgorde

Elke maatregel heeft een meetbaar doel op de afspeelbank (opname 30 oktober –
2 november plus de opname vanaf 4 november met de nieuwe driewegklep) en in HA.
Pas als de afspeelbank het doel haalt, gaat het naar de firmware.

### L1. Afkoelen leren ondanks warm water (klein)

- Een warmwaterronde tijdens afkoelen pauzeert de meting, zoals bij opwarmen
  al gebeurt (`Kind::pause`), tot hooguit 30 minuten; `offSince_` wordt niet
  meer teruggezet op warm water terwijl er niet verwarmd wordt.
- De bestaande veiligheid blijft: een kamer die tijdens "afkoelen" warmer wordt
  (lekkende driewegklep, pomp-naloop) wordt afgekeurd (`cooling_unexplained`).
- Doel: op de opname ≥ 3 afkoelstukken binnen een week; in HA `loss_per_h`
  gevuld. Test naast `KeepWarmStoreBlocksLearningUnlessBridged`.

### L2. Terugkoppeling op aankomsttijd (klein–middel)

- Nieuw, puur onderdeel (`ArrivalLearner`): per ruimte een correctiefactor
  f (0,5–2,0, start 1,0), bewaard in `LearnedState` (ontbreekt → 1,0).
- Per programmastap omhoog: aankomst = eerste meting ≥ doel − 0,1 °C na de
  geplande start, binnen 3 uur na de schakeltijd (anders: te laat). Fout =
  aankomst − schakeltijd.
- Te laat (> 10 min): f × 1,10. Te vroeg (> 15 min vóór de schakeltijd, en
  de start was toegepast): f × 0,92. Daartussen: ongewijzigd. (Uitvoering: de
  grens voor "te vroeg" is 15 in plaats van 20 min, anders eindigt een 2× te
  lange voorlooptijd op 19 min te vroeg en haalt het doel hieronder niet.)
- De planner gebruikt f op de standaard- én de geleerde voorlooptijd
  (`WarmupPlanner::lead`), binnen de bestaande maxima.
- Telemetrie per ruimte: laatste fout in minuten, f, aantal ochtenden. HA en
  E32: "Gisteren warm om 09:12 (12 min te laat); morgen 10 % eerder."
- Doel: in een simulatie met een standaardvoorlooptijd die 2× te lang of te
  kort is binnen 8 ochtenden op ±15 min; op de opname geven de ochtenden van
  31 oktober en 1 november (74 en 109 min te laat) "te laat"-gebeurtenissen.

### L3. Slim opwarmen vanaf dag één toepassen (klein)

- `FlowPolicy::optimumStart` past een start ook toe met `confidence ==
  "default"`: de standaardvoorlooptijd vanaf de huidige kamertemperatuur
  (regel van rc.2), vermenigvuldigd met f uit L2, met een plafond zolang f nog
  niet geleerd is (vloer 3 uur, radiator 90 min).
- De bestaande bewakingen blijven: alleen terwijl de kamer onder het komende
  doel ligt, binnen de aanvoergrenzen, en de start laat los zodra de kamer
  warm is.
- Tekst: "Begint om 07:40 (schatting; leert van elke ochtend)".
- Doel: op de opname in actieve modus met `--apply-learned` komt elke
  ochtendstap vanaf dag 2 op tijd binnen 0,2 °C; de duurtest houdt zijn
  invarianten (geen warmte zonder kamer onder doel).

### L4. "Klaar" voor de tijdschatting bij één bak (klein)

- `readyForTiming(room)`: één gevulde bak (3 metingen in 2 periodes) is genoeg
  om de opwarmtijd te schatten bij de watertemperatuur die de regeling toch al
  gebruikt. Het kiezen van de laagste watertemperatuur (`advise`) houdt 2
  bakken.
- HA-tekst: "3 van 3 opwarmingen gezien bij één watertemperatuur — de
  opwarmtijd is geleerd; het koelste water leert hij nog."
- Doel: op de opname `confidence: learned` na dagen in plaats van nooit.

### L5. Zelf bijstellen dat echt draait (klein–middel)

- De dagtellers van `AutoTuner` elk uur en bij de dagwissel in het bestaande
  NVS-record (`AutoTunerNvs`, ~120 bytes extra; de ringen van rust en
  doorschieten mogen bij een herstart leeg beginnen).
- Wachttijd na een herstart met hersteld record: 2 uur. Na een planwijziging
  die de regeling raakt (ruimtes, afgiftetype, bronnen, programma,
  aanvoergrenzen): 24 uur, zoals nu. Een cosmetische wijziging (namen,
  afwezigheidstemperatuur, personen, kranen, contacten, "uit tot"): geen
  herstart van de tuner. Een handmatige afstelwijziging: 24 uur, zoals nu.
- Doel: op de opname (zonder `--no-grace`) een beoordeling op dag 2; in HA
  binnen twee dagen na installatie een eerste stap of een onderbouwd "past
  nog".

### L6. Scorebord per dag (middel, vooral HA)

Per ruimte en per dag: op tijd warm (fout in minuten), doorschieten
(mediaan, `AutoTuner` heeft het al), starts per verwarmingsuur, uren
pendelen, gas voor verwarming en per graaddag (gasmeter en buitentemperatuur
uit HA). In `fw/telemetry/heating_summary` (compact) en in HA als sensor plus
een kaart op het tabblad Leren en instellingen. Zo zien eigenaar en
thermostaat of het beter wordt; L2 leest zijn fout uit hetzelfde bord.

### L7. Later (1.1): één natuurkundig huismodel (groot)

Per ruimte een RC-model (warmteverlies UA, massa C, afgifte k) dat van elke
meting van 10 s leert (recursief kleinste kwadraten), niet alleen van losse
stukjes. Eén model geeft de opwarmtijd, de afkoeling, de steady-state
stooklijn (helling UA/k, vervangt `CurveLearner`) en de nachtberekening.
Robuust tegen warm water (die metingen worden gemaskeerd) en de
weersverwachting uit HA past er direct in. De bakken van nu blijven als
controle tot het model zich op de afspeelbank bewezen heeft.

## Pendelen: eerst meten

De code laat de rusttijd terecht niet oplopen als de ketel zelf binnen één
verzoek aan en uit gaat (`boiler_cycling`). Of dat in dit huis zo is, blijkt
pas uit de data met de nieuwe driewegklep (vanaf 4 november); de klep lekte
tot 3 november naar beide kanten. Mogelijke remedie voor een vloer op een
grote ketel: langzame pulsregeling per zone (`ZoneRegulator::slowBinaryPi`
bestaat, staat uit) of een hogere watertemperatuur met langere pauzes. Geen
wijziging vóór de meting.

## Bewijs

1. Dagelijks `tools/switchover/active_review.py` op de HA-geschiedenis
   (alleen lezen), vanaf 4 november: op tijd per ochtend, aanvoer, pendelen,
   gas, afkoelen, leersensoren.
2. Opname ophalen met `tools/replay/from_ha.py` en `from_mqtt.py`; de
   afspeelbank vóór en ná elke maatregel: metingen geleerd, dag van "klaar",
   aankomstfout per ochtend, starts per uur.
3. Unit tests per maatregel; duurtest (`test/soak`) met de invarianten;
   `scripts/final_check.sh` volledig vóór een push.

## Planning

Besluit eigenaar 3 november: **rc.4**. L1–L5 in de firmware, L6 grotendeels in
HA erbij. De 14 dagen naar 1.0.0 beginnen opnieuw bij de installatie van rc.4;
1.0.0 dan op zijn vroegst eind november, mét werkend Slim opwarmen.
Inschatting bouwen + bewijzen op de afspeelbank: 2–3 dagen agentwerk; L6
parallel in HA. Het volledige werkpakket van rc.4 staat in
[RC4-PLAN.nl.md](RC4-PLAN.nl.md).

## In dezelfde firmware-release (uit de lijst van na rc.3)

- E32-overzicht: per ruimte de regel waarom hij wel of niet verwarmt (zoals de
  ruimtekaart in HA 1.0.0rc4; het E32-deel van branch `v11-room-overview`).
- Overzichtslabels: "CH active" en "Heat demand" worden "Verwarming aan"; op
  een telefoon hooguit 2 labels, de rest onder Details.
- "Te vaak aan en uit" op de E32 als leerinformatie, niet als probleem.
- Namen op de E32-pagina's: Weerafhankelijke regeling (menu "Ketel en
  stooklijn", `curve.html`, de geleerd-kaart, `ui-messages.js`) en
  "Watertemperatuur bij strenge vorst (−10 °C)" met uitleg.
- Tellers die een herstart overleven (warm water vandaag en 7 dagen);
  branderstarts en -uren verbergen als de ketel ze nooit meldt.
- Geleerd-kaart korter (2 regels per ruimte, "Meer" voor de rest); Uitloggen
  als menu-item; 10 % marge boven en onder de grafieklijnen.
- Standaardstooklijn alleen op ruimtes die aan staan (bij de eigenaar nu
  vanzelf goed: de badkamer is uit het plan).
- Vakantieplanner met eigen vakantietemperatuur (besluit eigenaar 4 november; RC4-PLAN F8).
