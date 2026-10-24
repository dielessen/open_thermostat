# Volgende gezamenlijke release — inhoud en resterende poorten

## Geïnstalleerde basis

E32 alpha26 en HA dev34 zijn gepubliceerd en onafhankelijk gecontroleerd.
Hun bron, pakketten en instellingen worden niet vervangen door een main-CI-build
met hetzelfde versienummer. De volgende software hieronder is voorbereid; er is
nog geen nieuwe publieke tag, flash, HA-herstart of fysieke vrijgave uitgevoerd.

## Gebundelde wijzigingen

| Onderdeel | Concrete wijziging | Controle |
| --- | --- | --- |
| Automatische update onderzoeken | Eén blijvend native updatecontrolepunt, actuele reset-/bootpartitiegegevens en EN/NL-diagnose; geen opslag per pakket/poll | Native opslag-/reconstructiegevallen, updaterbrowser, echte E32-build; echte powerloss nog open |
| HA-uitval | Bestaande lokale15s-lease wordt ook bij stille HA en werkende broker exact ingetrokken; geen oude heartbeat als herstel | Echte C++-controller met synthetische bronfeiten |
| Netwerkuitval / naloop | Lokale offline ticks blijven de oorspronkelijke naloopdeadline volgen, zonder publish of externe observers, ook na native SOURCE-lockout | Pure supervisor en echte controller; geen fysiek pomp-/klepbewijs |
| Teruggaande klok | Een verlopen, eerder behouden pad-/pompintentie kan niet herleven door een oudere timestamp | Deterministische bestaande bron faalt, gecorrigeerde bron slaagt |
| Duidelijke uitvalbediening | Uitklapbare EN/NL-uitleg op Home, behouden tijdens verversen | Echte Chromiumbrowser op desktop en mobiel |
| Kraanopdracht bij verlies van eigenaarschap | Bevoegdheid, native binding, bedrijfsmodus en capability worden ook na de lopende HA-service gecontroleerd; onzeker resultaat blokkeert vervolgdoelen | Native HA-regressies met geblokkeerde synthetische service; geen echte zendbevestiging |
| TV02-ontvangst | Ontvangstmetadata blijft na verval inspecteerbaar zonder oude datapointwaarden, privé-ID's of regelbevoegdheid | Native HA-tests met echte Node-producent en lifecycle |
| HA-kraanontvangst in EN/NL | Laatste berichttype, ontvangstouderdom en aanwezige gegevensnamen ook na verval; geen oude waarden of fysieke bevestiging | Zes browserprofielen plus native HA-keten |
| Bijgewerkte HA-editor | Eigen module-URL en kaarttag v35; bestaande v28 kan de nieuwe beheerde kaart niet verdringen, handmatige kaarten blijven compatibel | Koude/preloaded browserproeven en native editor-/dashboardtests |
| Incrementele systeemlog | Hele batch valideren vóór cursor/historie; ongeldige suffix verbruikt geen geldige prefix, eigen cursor na bootwissel | Oude bron faalt op cursor3 versus2; vier EN/NL-browserprofielen slagen |
| Betrouwbare instellingenopslag | Onzekere log-/ketelopslag blokkeert herhaalde submit met behoud van concept; ketelkeuze heeft afzonderlijke GET-readback en begrensde verzoeken | Echo zonder opslag en verloren readback tonen geen succes en veroorzaken geen retry |
| Actualiteit van meet- en buitenbronnen | Verlopen waarnemingen blijven ingetrokken; herhaalde weerberekeningen vernieuwen hun oorspronkelijke geldigheid niet | Twee regressies vóór/na, 625 native tests en E32-build; fysieke bronkwalificatie blijft open |
| Eigen ketelprofiel | Nieuwe passieve HRC22H-momentopname met69 gedefinieerde velden en expliciete kwaliteitsgroepen | Gescheiden diagnostisch snapshot; geen leesfilter, kalibratie of regeling |

Alle 23 voorbereide inventarisonderdelen blijven meegenomen. De bestaande
kamerplanner, configuratie-/readbackketen, EMS-decoders, regulator, supervisor,
groep-/vloer-/mengerpolicies, historie-/CSV-, comfort- en leerbasis blijven intact.
Onvolledige of fysiek ongekwalificeerde code wordt hierdoor niet aangezet.

## Wat kan niet worden afgevinkt met een softwarebuild?

- **B04:** de geselecteerde RTCGQ11LM levert diagnostische apparaattemperatuur.
  Er ontbreekt nog een geschikte oorspronkelijke kamermeting met beoordeeld
  meetprofiel. Geen automatische sensorwissel of trustvinkje.
- **B05:** eerdere oorspronkelijke TV02-ontvangst is nu afgeleid uit de bestaande
  `stale`-ontvangerstatus. Verse ontvangst, unieke native zendtransactiereceipt,
  causale echo, exclusief schema-eigenaarschap en fysieke kraanproef blijven open.
  Een HA-serviceacceptatie of gelijke doelwaarde is geen opdrachtbevestiging.
- **B06–B09:** werkelijke limiet-/DHW-/water-/kraan-/flowproducenten,
  installatieprofiel, UART-interface/adressering, onafhankelijke stop, minimumflow
  en fysieke HA-/broker-/E32-/EMS-uitval moeten nog worden afgerond/beoordeeld.
- **B10–B14:** finale productcontrole, nieuwe ongebruikte versies/tagfreeze,
  publieke bron-/ELF-/web-/pakketcontrole en gecoördineerde uitrol/acceptatie horen
  bij de exacte gezamenlijke eindkandidaat. Niet op basis van een losse reparatie.

De automatische HTTPS-afwijking is nog onverklaard. De nieuwe diagnose is
voorbereiding op gericht onderzoek; zij repareert de oude poging niet en geeft
geen toestemming om dezelfde route blind te herhalen. De eerste installatie
van nieuwe diagnose vanuit oude firmware heeft zelf nog geen nieuwe checkpoint-
registratie. De bestaande app-only herstelroute blijft afzonderlijk beoordeeld.

## Vast vervolg en bewijs

Volg de bestaande M2-volgorde: oorspronkelijke bron en native actuatortransactie,
begrensde supervisor, Classic-zender/stop, dan pas de gezamenlijke freeze en uitrol.
Geen F9/F10-ontwikkelstage vóór M2. De definitieve versie blijft per ruimte leren
met blijvend bewaarde, gevalideerde parameters vereisen; dit wordt niet geschrapt.

Bron- en testbewijs voor deze bundel:
`out/update-diagnostics-20261024/` en
`out/next-release-completion-20261024/` en
`out/source-freshness-20261024/` en
`out/actuator-owner-loss-20261024/` en
`out/release-diagnostics-bundle-20261024/`. De volledige CI-uitkomst wordt gekoppeld
aan de exacte bevroren broncommit in `FINAL-REVIEW.json`; lokale checks alleen
sluiten de publieke release- of fysieke poorten niet.

Het [werkbord](WORKBOARD.nl.md) blijft de enige afvinklijst; dit document is de
releaseoverdracht. [Uitvalaanpak](FAILSAFE.nl.md) beschrijft het gewenste gedrag,
de geïmplementeerde softwarecontroles en de nog ontbrekende fysieke terugval.
