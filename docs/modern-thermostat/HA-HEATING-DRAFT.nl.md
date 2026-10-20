# Centrale en gewenste graph-configuratiebron — geen regelvrijgave

Centrale basis Mark11706/11709 is samengevoegd; deze native graph-vervolgstap is gebouwd tegen76cef4f168c674d52bbd9f4d01b538bc7573fbf1. Nog steeds alleen bronkandidaat, niet geïnstalleerd.

## Wat dit pakket toevoegt

- Eén native heating-subentry per expliciet v1_shadow-entry, uitsluitend bewerkbaar wanneer runtime uit staat. Native create/reconfigure/delete en officiële ConfigEntries-opslag; geen helper, YAML, sidecar, database of scheduler.
- Engelse centrale buitenbronselectie (temperatuursensor of weather-temperatureattribuut), gewenste weerscompensatie, eigen bronmaxleeftijd, expliciet stale-beleid, watergrenzen en bestaande 9-puntsas +20,+15,+10,+5,0,-5,-10,-15,-20 °C. Geen nieuwe weersregelaar in HA.
- Data is ondubbelzinnig draft_not_applied. Geen firmware-ACK, actualiteit, veiligheid of apparaatcompatibiliteit wordt uit een Save afgeleid. Zonder bron mag weersregeling niet geselecteerd zijn. Een verlopen bron heeft expliciet block-normal-demand of begrensde vaste aanvoer als toekomstige gewenste policy; er wordt nu niets uitgevoerd.
- Pure volledige-graphvalidatie voor radiator/vloergroepen, pompkanalen en tijden, TRV-kamerdoel/binaire-TPI/proportionele-klepdeclaraties, aparte 3-punts- en analoge0–10V-mengerdeclaraties. Dit zijn declaraties, GEEN ondersteunde runtimeprofielen.
- Dubbele outputeigenaars en ontbrekende room/groupreferenties, modeldomeinen, NC/NO, TPI-minimum-/looptijden, grenzen/curve en mengeruitgangsaantallen worden structureel gecontroleerd. Vloer zonder menging moet dezelfde beperkte centrale bovengrens verdragen. Dit vervangt geen fysieke menger/highlimit/flowbeveiliging.
- HA entity/registrybindings blijven HA-lokaal. control_proposal() is een deterministisch, entity-vrij reviewartifact. transport_document() weigert altijd: huidige TEST-WIRE ondersteunt dit niet. Geen nieuwe actieve topics/configkeys of wijziging van mapping/schema/revision in de bestaande shadowketen.

## Grenzen / nog te bouwen

Dit is het eerste samenhangende bronpakket, niet de hele F3/F4/F8. Centrale GUI is een bronkandidaat, niet geïnstalleerd of op een scherm geaccepteerd. De native groep-/actuator-/mengerdeclaratie-GUI is nu gebouwd voor de daadwerkelijk gemodelleerde velden. Configuratierevisie/apply/conflictstatus naar E32, capabilityonderhandeling, budgetproeven, firmwaredecoding/supervisor, fysieke feedback/readiness en volledige device-/veiligheidsprofielen ontbreken nog. Een centrale draft buiten dit pakket in een bestaande actieve shadowconfig injecteren heeft GEEN effect: de huidige runtime exporteert uitsluitend rooms zoals voorheen.

Een toekomstig protocol moet deze centrale/groepsconfig atomair met de relevante room/mappingrevision aan E32 leveren en teruglezen. Geen globale mutable boilerinstellingen naast een afzonderlijke kamerschrijver; geen raw HA-serviceproxy. Vorige firmware en onbekende capability mogen nooit stil op deze gewenste instellingen overstappen. Draft-schema1 is HA-lokaal en geen geratificeerde firmware-schema1.

0–10V is elektrische uitgang, geen bewijs van mengfunctie. Driepuntsmenger vraagt later werkelijke OPEN/CLOSE-vergrendeling, referentie/homing, eigen aanvoerlus en foutbeleid; dit pakket voert dat NIET uit. Analoge richting/kalibratie, modelgebonden feedback, vaste mechanische mengers, floor-surfacegrenzen en onafhankelijke limieten moeten nog als profielwerk worden uitgewerkt. Max8groepen/64actuatoren zijn alleen declaratiegrenzen, geen bewezen4096-byte/NVS/pakketcapaciteit.

Bronkwalificatie blijft ongewijzigd: cached HA state, last_reported/device_seen of checkbox kwalificeert geen fysieke sample. Een offline bron mag als gewenste binding bewaard worden, maar wordt nooit daardoor geldig.

## Bewijs en rollback

107 gerichte tests op echte HA2026.10.2/Python3.14.8: native flowmanager/schema, Store flush/reload, singleton/eigendom, optional behouden/wissen, invalid atomiciteit, draftverwijdering met roombehoud, resourcebackend en ongewijzigde room/week/shadowconfig. Geen fullsuite-/broker-/hardwareclaim. Tijdelijke API-discovery-/testfouten zijn gecorrigeerd; finale log is leidend.

Niet deployen zonder afzonderlijke review. Lokale coderollback: gerichte patch reverse tegen afterhashes; uitsluitend nieuwe eigen modules/test/doc verwijderen en exacte gewijzigde flow/resources/workboard herstellen. Er is geen runtime-/configmigratie uitgevoerd. Voor een later ooit geïnstalleerde heating-subentry geldt: eerst die eigen draft natively exporteren/verwijderen of compatibel laten; een code-rollback zonder plan mag geen orphan-subentry achterlaten. Dit pakket levert geen productie-rollbackactie omdat niets is geïnstalleerd.

Volgende bewijsactie: parentreview/merge van de graphkandidaat, daarna expliciet gecoördineerd E32 capability/revisie/applycontract en latere GUI/deviceacceptatie. Werkbord houdt fysieke/productgates open.

## Native graph-vervolgpakket — bronacceptatie

In Heating settings kies Configuration section → Edit groups and actuator declarations. Eén native heating-subentry blijft eigenaar van centrale instellingen plus graph; geen losse configuratieschrijver. Menus Add/Edit/Delete group en actuator declaration werken met gewone selectors, niet JSON/YAML. Alle graphhandelingen zijn in-memory staged tot Save desired graph (not applied); Cancel gooit alle staged veranderingen weg. Centrale velden kunnen mee als draft worden bewerkt maar worden bij Cancel niet opgeslagen.

Groepvelden: naam, radiator/vloer, watergrenzen, optionele pumpswitch/startdelay/naloop en gedeclareerd mengertype. Mengervelden alleen het gemodelleerde type: aanvoersensor, looptijd en OPEN/CLOSE-switches of één analoge-number-uitgang. Actuator: bestaande room/group, TRV-kamerdoel of binaire NC/NO/hysterese/TPI of proportionele stand, daarbij uitsluitend relevante modelvelden/outputdomeinen. Niet-gemodelleerde homing, interlockimplementatie, analoge kalibratie/richting, feedbackzekerheid, mechanische mengers en onafhankelijke fysieke beveiligingen blijven expliciet OPEN; de interface waarschuwt dat niets wordt uitgevoerd.

Lege groepen zijn incomplete gewenste drafts en staan apart als incomplete_group_ids. Er is geen automatische complete/ready-status of verborgen actuator. Een groepsdelete met kinderen vereist expliciete cascadebevestiging en verwijdert alleen zijn staged actuatorverklaringen; room/source/device/andere groep/centrale velden blijven intact. Verwijderen van één actuator vraagt bevestiging. Final Save valideert alle references opnieuw via actuele registry-identiteit, room/groupcatalog en outputeigendom. Een oude editor kan nieuw graph-/centrale werk niet overschrijven; ontbrekende/disabled entity blokkeert Save. Offline geselecteerde hardware blijft alleen een niet-toegepaste verklaring.

Een exact dezelfde TRV in de bestaande room en zijn graphverklaring mag alleen voor DIEZELFDE room als één gewenste eigenaar worden overgenomen. Dat is geen extra schrijver: er is geen tweede executor/listener en de graph gaat niet naar de huidige shadowwire. Cross-room/controller, tweede actuator, pump/menger of andere outputrollen op hetzelfde kanaal worden afgewezen. De latere applycontractimplementatie moet deze ene fysieke eigenaar behouden, niet beide representaties zelfstandig aansturen. Een roomflow mag een graphuitgang evenmin stelen.

Native roomdelete: de bestaande update/reload-lifecycle ruimt alleen graphactuatoren van de verdwenen room op en bewaart de laatste verwijderde configuraties in bounded last_room_cascade-audit. Groepen en centrale configuratie blijven; ze kunnen incomplete worden. Geen eigen watcher/coordinator. Bij unloaded integratie kan een tijdelijk dangling gewenst record pas bij volgende setup worden hersteld; ook een crash tussen de native roomupdate en die cleanup wordt bij startup gerepareerd. Dit zijn twee native configupdates, GEEN bewijs van een cross-update hardware-/powerlosstransactie. Een geopende graph-editor wordt na de cleanup stale en kan de verwijderde room niet terugzetten. Er is geen actieve graphtransport/export om zulke references te activeren.

Bewijs:218 PASS,1 expliciete broker-opt-inSKIP in volledige huidige native HA-suite; echte HA2026.10.2/Python3.14.8 en source-matched echte C++kern. Geen optelsom met eerdere107/106 subsets. Eerdere tijdelijke tests zonder runnerpad hadden setup-errors, geen bronfailure; finale native-full-final.log en runner-verification.json zijn leidend. Native manager/Store-proeven zijn geen screenshots of fysiek apparaatbewijs.

Geen productie/testHA-uitrol, reboot, source/broker/ACL/E32wijziging, actieve serviceexecutor of TXunlock. TEST-WIRE, v1_runtime, v1_wire en MQTT-configexport blijven byte-ongewijzigd. Alleen bestaande HA-configlifecycle krijgt de beschreven gewenste-referentiecleanup vóór zijn normale reload. Code-rollback reverse tegen before/afterhashes; als dit later ooit geïnstalleerd wordt, eerst eventuele nieuw aangemaakte graphdrafts natively exporteren/verwijderen of compatibel houden vóór een terugkeer naar oude code.

Outputeigendom wordt gecontroleerd via stabiele registry-channelidentiteit en actuele entityrefs, over de geconfigureerde OpenThermostat-kamers en graphs heen. Bekende gedeelde device_id van een TRV/climate of valve krijgt bovendien conservatieve exclusiviteit: een afzonderlijke position-number op dezelfde TRV mag geen tweede eigenaar krijgen. Verschillende switch/number-kanalen van een relay/mengercontroller mogen wél één device delen. Dit bewijst niet dat iedere driver-alias of fysieke bekabeling onafhankelijk is; dat blijft de qualified device/profileacceptatie vóór enige uitvoering. Niet-gekwalificeerde multichannel-climateapparaten kunnen daarom bewust worden geblokkeerd.

De runtime-off guard kijkt zowel naar de opgeslagen shadow_enabled-optie als een eventuele nog actieve HA-runtime tijdens reload. Alleen gewenste configuratie mag worden opgesteld; een kort optiereloadvenster geeft geen editvrijgave.

De bestaande roomflow/RoomBinding is in dit pakket bewust behouden en vereist nog een climate-TRVbinding. De nieuwe graph kan vloerklep-/positie-/mengverklaringen aan bestaande logische kamers toevoegen, maar levert dus nog GEEN vloer-only roomtype zonder TRV. Maak daarvoor geen nep-TRV/helper aan. De expliciete graph-only room/migratie en eigendomsoverdracht van legacy roombindings moeten in het volgende gecoördineerde configuratie-/applypakket worden uitgewerkt vóór volledige vloerproductondersteuning wordt geclaimd.


## Aanvulling: gewenste kamers zonder TRV
De native kamerflow ondersteunt nu graph_only_draft naast de bestaande
climate_trv-vorm. Geen verplichte of fictieve climatebinding voor vloer-/klepkamers.
Oude records blijven exact geldig. Modewisseling vraagt bevestiging en runtime uit;
kamer-ID/week/bounds en graphreferenties blijven behouden. Deze mode kan NIET naar
de bestaande TEST-WIRE of legacy runtime. Zie
[concreet applycontractvoorstel](HA-GRAPH-APPLY-PROPOSAL.nl.md).
De huidige graphlimieten blijven alleen HA-draftgrenzen, geen E32capaciteitsclaim.
