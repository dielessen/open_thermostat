# Eerste centrale configuratiebron — desired draft, geen regelvrijgave

Mark11706/11709, bron ea54c256f4116b8995c03030138a47eb8e26c17a. Alleen bronkandidaat.

## Wat dit pakket toevoegt

- Eén native heating-subentry per expliciet v1_shadow-entry, uitsluitend bewerkbaar wanneer runtime uit staat. Native create/reconfigure/delete en officiële ConfigEntries-opslag; geen helper, YAML, sidecar, database of scheduler.
- Engelse centrale buitenbronselectie (temperatuursensor of weather-temperatureattribuut), gewenste weerscompensatie, eigen bronmaxleeftijd, expliciet stale-beleid, watergrenzen en bestaande 9-puntsas +20,+15,+10,+5,0,-5,-10,-15,-20 °C. Geen nieuwe weersregelaar in HA.
- Data is ondubbelzinnig draft_not_applied. Geen firmware-ACK, actualiteit, veiligheid of apparaatcompatibiliteit wordt uit een Save afgeleid. Zonder bron mag weersregeling niet geselecteerd zijn. Een verlopen bron heeft expliciet block-normal-demand of begrensde vaste aanvoer als toekomstige gewenste policy; er wordt nu niets uitgevoerd.
- Pure volledige-graphvalidatie voor radiator/vloergroepen, pompkanalen en tijden, TRV-kamerdoel/binaire-TPI/proportionele-klepdeclaraties, aparte 3-punts- en analoge0–10V-mengerdeclaraties. Dit zijn declaraties, GEEN ondersteunde runtimeprofielen.
- Dubbele outputeigenaars en ontbrekende room/groupreferenties, modeldomeinen, NC/NO, TPI-minimum-/looptijden, grenzen/curve en mengeruitgangsaantallen worden structureel gecontroleerd. Vloer zonder menging moet dezelfde beperkte centrale bovengrens verdragen. Dit vervangt geen fysieke menger/highlimit/flowbeveiliging.
- HA entity/registrybindings blijven HA-lokaal. control_proposal() is een deterministisch, entity-vrij reviewartifact. transport_document() weigert altijd: huidige TEST-WIRE ondersteunt dit niet. Geen nieuwe actieve topics/configkeys of wijziging van mapping/schema/revision in de bestaande shadowketen.

## Grenzen / nog te bouwen

Dit is het eerste samenhangende bronpakket, niet de hele F3/F4/F8. Centrale GUI is een bronkandidaat, niet geïnstalleerd of op een scherm geaccepteerd. Groep-/actuator-/menger-GUI, configuratierevisie/apply/conflictstatus naar E32, capabilityonderhandeling, budgetproeven, firmwaredecoding/supervisor, fysieke feedback/readiness en echte deviceprofielen ontbreken nog. Een centrale draft buiten dit pakket in een bestaande actieve shadowconfig injecteren heeft GEEN effect: de huidige runtime exporteert uitsluitend rooms zoals voorheen.

Een toekomstig protocol moet deze centrale/groepsconfig atomair met de relevante room/mappingrevision aan E32 leveren en teruglezen. Geen globale mutable boilerinstellingen naast een afzonderlijke kamerschrijver; geen raw HA-serviceproxy. Vorige firmware en onbekende capability mogen nooit stil op deze gewenste instellingen overstappen. Draft-schema1 is HA-lokaal en geen geratificeerde firmware-schema1.

0–10V is elektrische uitgang, geen bewijs van mengfunctie. Driepuntsmenger vraagt later werkelijke OPEN/CLOSE-vergrendeling, referentie/homing, eigen aanvoerlus en foutbeleid; dit pakket voert dat NIET uit. Analoge richting/kalibratie, modelgebonden feedback, vaste mechanische mengers, floor-surfacegrenzen en onafhankelijke limieten moeten nog als profielwerk worden uitgewerkt. Max8groepen/64actuatoren zijn alleen declaratiegrenzen, geen bewezen4096-byte/NVS/pakketcapaciteit.

Bronkwalificatie blijft ongewijzigd: cached HA state, last_reported/device_seen of checkbox kwalificeert geen fysieke sample. Een offline bron mag als gewenste binding bewaard worden, maar wordt nooit daardoor geldig.

## Bewijs en rollback

107 gerichte tests op echte HA2026.10.2/Python3.14.8: native flowmanager/schema, Store flush/reload, singleton/eigendom, optional behouden/wissen, invalid atomiciteit, draftverwijdering met roombehoud, resourcebackend en ongewijzigde room/week/shadowconfig. Geen fullsuite-/broker-/hardwareclaim. Tijdelijke API-discovery-/testfouten zijn gecorrigeerd; finale log is leidend.

Niet deployen zonder afzonderlijke review. Lokale coderollback: gerichte patch reverse tegen afterhashes; uitsluitend nieuwe eigen modules/test/doc verwijderen en exacte gewijzigde flow/resources/workboard herstellen. Er is geen runtime-/configmigratie uitgevoerd. Voor een later ooit geïnstalleerde heating-subentry geldt: eerst die eigen draft natively exporteren/verwijderen of compatibel laten; een code-rollback zonder plan mag geen orphan-subentry achterlaten. Dit pakket levert geen productie-rollbackactie omdat niets is geïnstalleerd.

Volgende bewijsactie: parent source/contractreview en scoped merge; daarna volledige groeps-/profiel-GUI en expliciet gecoördineerd E32 applycontract in een volgend pakket. Werkbord houdt fysieke/productgates open.
