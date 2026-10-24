# Uitval van Home Assistant, verbinding of voeding

Dit is de uitvalaanpak voor de volgende gezamenlijke release. De software rekent
nu mee in schaduwmodus: fysieke ketel-/kraanuitvoer is geblokkeerd. De hier geteste
intenties zijn geen bewijs dat een aangesloten ketel of kraan werkelijk stopt.

## Home Assistant is niet bereikbaar

Een onbereikbare HA-webpagina zegt niet automatisch dat HA of MQTT is gestopt.
De E32 beoordeelt de bestaande, geauthenticeerde heartbeatverbinding. Geen nieuwe
pingdienst of internetverbinding wordt als regeltoestemming gebruikt.

Na de laatste geaccepteerde heartbeat verloopt de toestemming op de E32 na
15 seconden, op zijn eigen monotone klok. Verdwenen HA, een gestopte integratie
of een eenzijdig geblokkeerde berichtverbinding kan de oude toestemming niet
vernieuwen. Een duplicate heartbeat, gewone telemetrie of een nieuw geopende
webpagina doet dat ook niet. Een gedetecteerde broker-/netwerkdisconnect trekt
de bestaande sessie meteen in.

Dit is een softwaredeadline. De bestaande lokale eventloop moet de controles
uitvoeren; een blokkerende driver of vastgelopen processor kan geen harde
fysieke stoptermijn garanderen. Een heartbeat bewijst bovendien alleen dat het
bestaande protocolpad reageert, niet dat iedere bron of actuator gezond is.
Metingen, kraanfeedback, limieten, tapwaterstatus en flow behouden eigen deadlines.

## Wat doet de regeling dan?

1. Geen normale warmtevraag uit oude kamermetingen of oude opdrachten.
2. De ketelvraagintentie wordt ingetrokken. Een eventuele fysieke nul-/stopopdracht
   moet later via de afzonderlijk gekwalificeerde lokale zender verlopen; een
   MQTT-stopbericht naar een onbereikbare HA-installatie is geen oplossing.
3. Alleen een eerder aangevraagd, voor deze installatie beoordeeld nalooppad mag
   tijdelijk behouden blijven. De lokale bewaking blijft ook zonder netwerk
   doorlopen en verlengt de oorspronkelijke eindtijd niet. Dit opent geen nieuwe
   klep en kent geen doorstroming toe op basis van een doelwaarde.
4. Verlopen naloopintenties kunnen door een teruggaande klok niet opnieuw actief
   worden. Lokale fouten blijven vergrendeld waar het bestaande profiel dat vereist.
5. Herverbinden herstelt geen oude metingen, overrides, readiness of opdrachten.
   Een nieuwe sessie, actuele brongegevens en alle toepasselijke profiel-/
   foutbevestigingen blijven nodig. Er is geen automatische hervatting van een
   afgebroken proef.

De software kiest dus niet generiek “alle kranen dicht” of “pomp uit”. Bij een
ketel die naloopt kan daarmee juist de benodigde doorstroming verdwijnen.
De bestaande profielpolicies beschrijven alleen logische intenties. Een beoordeeld
fysiek nalooppad, onafhankelijke begrenzing en hun concrete aansturing ontbreken
nog als productieacceptatie.

## Andere uitvalgevallen

| Uitval | Softwaregedrag / vereiste fysieke terugval |
| --- | --- |
| Alleen browser of internet weg | Lokale HA/MQTT-keten kan blijven werken; geen onnodige omschakeling op een mislukte browserrequest. Kalender-/weerbronnen hebben aparte actualiteitscontroles. |
| Sensor oud of onbeschikbaar | Afhankelijke zone zonder normale vraag; geen leren uit oude data. Geen diagnostische apparaattemperatuur als vervangende kamermeting. |
| Eén kraan onbereikbaar | Geen gefingeerde openstand/readiness. Groeps-/flowvoorwaarden kunnen de gezamenlijke vraag blokkeren. Bereikbaar zijn van andere kranen bewijst geen veilig afgiftepad. |
| HA/MQTT/netwerk weg | Bovenstaande lokale intrekking en eindige naloopintentie; draadloze HA-kranen zijn vanaf de E32 dan niet betrouwbaar bestuurbaar. Hun interne gedrag moet apart worden ingesteld, teruggelezen en beproefd. |
| E32 vastgelopen of zonder voeding | Een E32 zonder voeding kan niets versturen. De ketel moet zelfstandig een bewezen vraagtimeout hebben of er moet een geschikte onafhankelijke fysieke onderbreking/terugval bestaan. Een watchdog alleen lost stroomuitval niet op. |
| EMS of converter weg | Geen blind nieuwe positieve opdracht. Het beoordeelde fysieke stop-/timeoutgedrag moet ook bij busonderbreking gelden. |
| Alles komt terug | Verse sessie en bronnen; geen retained oude warmtevraag, geen herhaalde oude actie. Fysieke vrijgave volgt uitsluitend de toepasselijke commissioning. |

Vorstbescherming in één radiatorkraan beschermt niet automatisch alle leidingen.
Ook de ketel-eigen vorstbescherming is hier geen bewezen woningbrede terugval.
Een automatische overname door Tado wordt niet verondersteld: daarvoor zou een
beoordeelde exclusieve regelaaroverdracht nodig zijn. Tado blijft tijdens de
huidige passieve fase de bestaande regelaar en wordt niet door deze wijziging bediend.

## Wat is nu bewezen en wat blijft open?

Softwarebewijs: echte C++-controller met synthetische bronfeiten, stilgevallen HA
terwijl broker/observers blijven werken, exact lokaal lease-einde, offline naloop,
geen publish/observeraanroep zonder verbinding, uitblijven van automatisch herstel
en regressie vóór/na de klokcorrectie. EN/NL-uitleg op de E32 blijft uitgeklapt bij
verversen. Bestaande bron-/opdracht-/stopproeven blijven behouden.

Voor actieve ingebruikname blijven fysieke proeven nodig: HA-stop, brokerstop,
eenzijdige netwerkuitval, E32-powerloss, EMS-onderbreking, concrete ketelvraagtimeout,
kraan-/vloerklepfallback, minimumflow en pompnaloop, plus gecontroleerd herstel.
Die worden eerst zonder ketelvraag en daarna als begrensde proef onder toezicht
beoordeeld. Dit document voert geen proef of omschakeling uit.

Bronnen: [PLAN §12](PLAN.nl.md#12-uitval-afhankelijkheid-en-veiligheid),
[werkbord](WORKBOARD.nl.md), `SessionAdmission.h`, `HydraulicSupervisor.h`,
`ShadowController.h`, `ModernTransport.h` en het bewijs in
`out/next-release-completion-20261024/`.
