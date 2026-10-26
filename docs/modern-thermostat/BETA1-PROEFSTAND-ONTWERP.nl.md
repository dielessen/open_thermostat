> **Nieuwste Classic-bronstap:** flow-/nulformaat 0x1A/offset0/één byte is
> geïmplementeerd en aan de pollcallback gekoppeld. 72 native ASan/UBSan-gevallen
> PASS. Adres/masker ontbreken bewust zolang die niet beoordeeld zijn; default
> formatter weigert alle frames. TX-lock en profiel-/hydraulische gates behouden.
> Fysieke UART-/stop-/flowkwalificatie en het ketenprofiel blijven open.

> **Nieuwste bronstap:** de E32-pollroute is aangesloten op de gedeelde
> `BoilerTestPollDriver`. 66 native ASan/UBSan-gevallen PASS, inclusief 9
> pollgevallen. Geen oude positieve queue-intentie: opnieuw toelaten na encoderen,
> IO-resultaat apart registreren, legacyqueue uitsluiten tijdens proefbezit.
> Reset/RX-overloop/decodefout trekken positieve intentie in. Beoordeeld profiel,
> Classic-encoder, elektrische UART-kwalificatie en fysieke acceptatie blijven open.
> De E32-TX-lock en ontbrekende encoder verhinderen fysieke opdrachten.
>
> Onderstaande checkpoints zijn historisch; de actuele afvinklijst staat in WORKBOARD.

> **Vervolgbron:** controller/status en cookie+CSRF-POST-/webbediening zijn nu
> aangesloten op de pure policy. 57 native ASan/UBSan-gevallen en drie control-
> viewports PASS. Toelaten vóór IO en registreren na werkelijke voltooiing zijn
> gescheiden; oude positieve voltooiing na stop/deadline vertraagt nul niet.
> Open blijven het beoordeelde profiel, hydraulische gates, echte poll/UART-driver
> en fysieke acceptatie. Geen nieuwe fysieke bevoegdheid of afzonderlijke release.

> **Bronvoortgang 23 oktober:** de pure policy `src/EMS/BoilerTestSession.h`
> en behoud van UART-ontvangsttijd in de echte RX-queue zijn geïmplementeerd.
> 40 unieke native gevallen onder ASan/UBSan PASS. Dit document beschrijft
> ook de nog open HTTP-/profiel-/pollzenderintegratie; de actieve ketelproef
> is nog niet aangesloten of fysiek vrijgegeven. Alles blijft in dezelfde
> grotere bètabatch, zonder afzonderlijke publicatie/installatie.

# Begrensde ketelproef: te implementeren contract

Ontwerpcheckpoint 23 oktober 2026. Dit contract is nog geen aangesloten
opdrachtpad. De huidige E32 blijft RX-only. Het doel is een eindige, expliciete
proef; niet het vrijgeven van onbeheerd verwarmen.

## Eén eigenaar, geen automatisch hervatten

De proef krijgt een eigen vluchtige sessie met boot-ID en eenmalige sessie-ID.
Er wordt niets opgeslagen waarmee een reboot de proef kan hervatten. Zowel
HA-ruimteaansturing als de oude ketelregeling blijven uitgesloten tijdens de proef.
De proef gebruikt geen generieke telegramzender en geen bronprofielwijziging.
Een dubbele start met dezelfde ID verlengt geen deadline en herhaalt geen vraag.

Start en stop lopen via de bestaande geauthenticeerde HTTP/CSRF-route. Een
live-start ontbreekt totdat de afzonderlijk gereviewde TX-interface beschikbaar
is en de concrete aansluit-/stopvoorwaarden zijn ingevuld. Een normale
statusaanvraag, MQTT-heartbeat of opgeslagen instelling kan geen start zijn.

## Toestanden en waarneming

| Toestand | Toegestane positieve opdracht | Overgang |
|---|---|---|
| Niet vrijgegeven | Geen | Geldige proefvoorwaarden en expliciete lokale start |
| Stopbasis controleren | Geen; alleen toegestane nulvraag | Verse gemelde CV-uit, nul brandervermogen en nul gevraagde aanvoertemperatuur na nulvraag |
| Klaar voor eindige vraag | Eén begrensde vraag, expliciet gestart | Deadline vastleggen vóór het bericht aangeboden wordt |
| Vraag actief | Alleen herhaling binnen dezelfde vaste deadline | Stopactie, deadline, feedbackverlies, conflict of verlies proefvoorwaarden → stoppen |
| Stop controleren | Alleen nulvraag | Verse gemelde CV-uit, nul brandervermogen en nul gevraagde aanvoertemperatuur ná stopopdracht → gemelde stop bevestigd |
| Stop onzeker / fout | Geen positieve vraag; geen automatische nieuwe eigenaar | Onafhankelijke stop/herstel uitvoeren en nieuw, expliciet proefbesluit |
| Afgerond | Geen | Nieuwe sessie vereist voor een nieuwe proef |

De begintemperatuur, maximale temperatuur, proefduur en stopobservatieduur komen
uit de concrete beoordeelde proefopstelling; een willekeurige standaardtemperatuur
is geen bewijs van voldoende debiet of passende ketelgrenzen. Een waarde uit
EMS Classic `0x18` kan gemeld CV-bedrijf of gemeld brandervermogen bevestigen,
maar wordt geen onafhankelijke vlam- of stromingsmeting.

Acceptatie gebeurt op afzonderlijke gebeurtenissen: vraag berekend, toegelaten,
aangeboden, werkelijk verzonden, verse reactie ontvangen en gemelde stop gezien.
Een succesvolle HTTP-respons, poll, eigen echo, geselecteerde aanvoertemperatuur
of onbetrouwbaar branderbit is geen vervanging voor die laatste waarneming.
Oude feedback van vóór de stop telt niet mee. DHW-activiteit wordt apart getoond;
de proef verandert geen tapwaterinstellingen om een CV-stop af te dwingen.

## Deadline ook op het laatste verzendpunt

Iedere positieve opdracht draagt sessie-ID, boot-ID en monotone absolute deadline.
De zender controleert die opnieuw wanneer de ketel pollt. Stop, conflict,
verbindingsverlies, reset en verlopen deadline verwijderen eerder klaargezette
positieve opdrachten vóór een volgende verzendpoging. Een verzadigde wachtrij
mag geen stop achter positieve opdrachten zetten. Herhaald starten of terugkeren
van HA/broker/HTTP heractiveert geen verlopen opdracht.

Een nulvraag heeft een eigen bevestigingsstatus. Niet verzonden, alleen eigen
echo, geen verse feedback of timeout wordt zichtbaar als onzeker/fout en nooit
als geslaagde stop. Een softwarelease kan een reeds verzonden opdracht bij
E32-voedingsverlies niet intrekken. Daarom wordt de onafhankelijke stopmogelijkheid
vóór fysieke vrijgave vastgesteld; terugschakelen naar Tado is herstel en geen
automatisch bewezen fail-safe.

## Eerst softwarebewijs, dan fysieke acceptatie

Volgende implementatiecontrole: echte queue-/pollgrens met gesimuleerde monotone
klok. Minimaal aantonen: geen positieve opdracht vóór stopbasis; geen verzending
na deadline; stop vóór een al klaargezette positieve opdracht; dubbel verzoek
verlengt niets; reboot hervat niets; vertraagde oude feedback bevestigt geen stop;
CRC-fout, protocolconflict, UART-reset en volle queue geven geen positieve vraag;
CV/DHW-inferentie blijft onderscheiden van fysieke bevestiging.

Daarna pas kunnen de correcte Classic-commandocodering en elektrische zendmodus
voor de bekende converterketen beoordeeld worden. De huidige EMS+-schrijfroute
is daarvoor niet herbruikbaar als algemene keteltestknop. De bèta is pas gereed
wanneer dit contract daadwerkelijk is aangesloten en de noodzakelijke fysieke
voorwaarden een concrete proef toestaan.

## Bronaanvulling — fout bewust afsluiten na stop

De gedeelde Classic-policy vereist voor stopbewijs ook een verse gerapporteerde
nul gevraagde aanvoertemperatuur (0x18), strikt na werkelijk verzonden nul.
Branderpauze met positieve vraag blijft wachten. De bronacceptatie is geen
fysieke adapterkwalificatie.

POST `/boiler/test/close_fault` accepteert exact schema1, actuele boot_id/revision
en `local_stop_confirmed:true`, na normale authenticatie/CSRF. Alleen een fout met
voldoende verse stopterugmelding, zonder lopende verzending en met toegelaten
zender/eigenaar/stopmogelijkheid kan naar `closed`. Er worden geen telegrammen
verzonden door de afsluitactie. De oorspronkelijke foutreden blijft behouden;
oude tickets en nieuwe voorbereidingen blijven geblokkeerd tot een nieuwe boot.
De gesloten proef houdt het normale geautoriseerde updateproces niet langer
tegen. Afsluiten is geen automatisch geslaagde proef, update of herstart.
