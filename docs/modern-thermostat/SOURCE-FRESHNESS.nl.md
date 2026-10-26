# Actualiteit van kamer- en buitenbronnen

Status: bronwerk voor de volgende gezamenlijke release, niet geïnstalleerd.
De bestaande bronidentiteit-/reportkwalificatie, lokale leases, fysieke
uitvoerblokkades en alle open M2-poorten blijven gelden.

## Een verlopen waarneming blijft verlopen

De gedeelde `TemperatureSample` bewaart nu per huidige waarneming dat verval
is vastgesteld. Een volgende waarde-, status- of diagnoseread met een oudere
tijd kan diezelfde waarneming niet opnieuw geldig maken. Ook verval dat tijdens
het opvragen van de ouderdom wordt vastgesteld, trekt de bruikbaarheid in.
De oorspronkelijke ouderdom blijft als diagnose beschikbaar waar berekenbaar.

Een nieuwe, al door de bron-eigenaar toegelaten waarneming kan de oude vervangen,
ook als de temperatuur gelijk blijft. Een cache-read, device-seen of restored
waarde wordt daardoor niet tot oorspronkelijke meting verheven. Deze kern
verifieert zelf geen bron-ID of Zigbee-transactie: dat blijft de bestaande
admission-/obserververantwoordelijkheid vóór `observe()`.

De tijdelijke vervalvlag volgt een kopie van dezelfde waarneming mee. Ze is
uitsluitend RAM-status van de bestaande, geserialiseerde bron-eigenaar; geen
nieuwe opslag, timer, client of worker. De EMS-buitenbron en OpenWeather gebruiken
hun bestaande mutex; de native kamerbron blijft in dezelfde controller-eigenaar.

## Herhaalde OpenWeather-antwoorden

OpenWeather beschrijft `dt` in de Current Weather API als het tijdstip waarop de
gegevens zijn berekend, in Unix-UTC. Het is dus geen bewijs van de acquisitietijd
van een fysieke buitensensor. [Officiële veldbeschrijving](https://openweathermap.org/api/current).

De bestaande OpenWeather-eigenaar bewaart daarom één begrensd ontvangstrecord
met de laatst geaccepteerde berekeningstijd, temperatuur en lokale klokgrens.
De totale ontvangstkern blijft maximaal 128 bytes. URL, credentials, instellingen,
netwerkclient en fetchtaak zijn niet gewijzigd of geactiveerd.

- Hetzelfde `dt` met dezelfde temperatuur behoudt de oorspronkelijke lokale
  geldigheidsgrens. Een teruglopende of stilstaande UTC-klok geeft geen extra
  uur vanaf het opnieuw ontvangen antwoord.
- Een voorwaartse UTC-correctie kan de resterende geldigheid verkorten, nooit
  verlengen. De bestaande grens van één uur blijft behouden.
- Hetzelfde `dt` met een andere temperatuur en oudere berekeningen worden
  geweigerd; een oud duplicaat herstelt de ingetrokken bron niet.
- Na verval of onbeschikbaar maken is een werkelijk nieuwere berekening nodig.
  Een teruggaande lokale monotone klok trekt deze eigenaar in tot reconstructie;
  een nieuw HTTP-antwoord wist die klokfout niet.
- Weergegevens krijgen binnen deze numerieke kern integratierapportherkomst;
  ze worden niet voorgesteld als een rechtstreeks ontvangen fysiek sensorrapport.

Deze controles bewijzen geen gekalibreerde lokale buitentemperatuur en kiezen
geen nieuwe productiebron of fallback-waterdoel. De HA-weerbron, bronprioriteit,
volledige configuratie en fysieke bron-/uitvalacceptatie blijven afzonderlijke
R10/R11-werkzaamheden. De bestaande transportbeveiliging is hiermee evenmin
opnieuw gekwalificeerd.

## Bewijs

Twee afzonderlijke kleine programma's reproduceren op de bevroren oude bron
het herleven van een verlopen meting en het opnieuw toelaten van een oud
weerantwoord bij afwijkende kloktijd. Beide falen vóór en slagen na de correctie.
De native regressie controleert daarnaast diagnoseverval, brononafhankelijkheid,
nieuwe echte waarnemingen, dubbele/afwijkende/oudere weerdata, UTC-correcties,
bronintrekking en lokale klokfouten.

Bewijs: `out/source-freshness-20261024/`. Dit is softwarebewijs; geen nieuwe
live bronwaarneming, sensorvervanging, kraan-/ketelopdracht of uitvalproef.
