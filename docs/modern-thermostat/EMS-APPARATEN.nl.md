# EMS-apparaten en ontvangen entiteiten

Status: bron voor de volgende gezamenlijke bundel; nog niet geïnstalleerd.
De live basis blijft HAdev36/E32alpha27. Geen versiebump of fysieke vrijgave.

## Bediening

Onder Settings → EMS devices / Instellingen → EMS-apparaten staat een overzicht
naar het voorbeeld van de apparaten- en entiteitentabellen in de
[officiële EMS-ESP-webinterface](https://docs.emsesp.org/WebUI).
Dit is eigen UI-bron boven onze bestaande decoder, geen geïmporteerde EMS-ESP-runtime.

Per werkelijk waargenomen afzender: busadres, berichtaantal, ouderdom van het
laatste rapport, ontvangen product-ID/versie/merk-ID indien aanwezig, telegramtypen
en aantal ontvangen entiteiten. Openklappen toont naam, stabiele veld-ID, waarde/
eenheid, status, kwaliteit, telegramtype en ouderdom. Zoeken en optioneel ook
nog niet ontvangen decoder­velden tonen. Standaard alleen ontvangen velden;
`unknown` bewijst geen unsupported apparaat. Verlopen/ongeldige waarden blijven
leeg, onbetrouwbare ruwe waarden houden hun expliciete kwaliteitslabel.

De ketel op adres0x08 gebruikt alle69 bestaande velddefinities zonder modelfilter.
Andere waargenomen afzenders zijn zichtbaar, met de melding dat entiteitsdecodering
nog ontbreekt wanneer daarvoor geen decoder is aangesloten. Er worden geen
modelnamen afgeleid uit de handmatig gekozen ketelillustratie of adresconventies.
Een nog niet ontvangen product-/versierapport blijft onbekend. Dit is geen claim
op alle apparaatdecoders uit de EMS-ESP-database.

Vernieuwen leest één lokale momentopname. Geen bus-scan, forced report, query,
control-actie of achtergrondpoller. Opengeklapte apparaten en filters blijven
staan; de pagina wordt niet vervangen. Bij een fout blijft het vorige snapshot
zichtbaar met de duidelijke melding dat dit oude gegevens zijn. Navigeren trekt
een lopende leesaanvraag in; een laat antwoord schrijft niet in een andere pagina.

## Bron en grenzen

De bestaande CRC-gevalideerde UART-decode voegt onder dezelfde telemetry-mutex
metadata toe aan een vaste tabel: maximaal16 afzenders en8 telegramtypen per
apparaat. Geen payloadopslag of extra allocatie per pakket. Capaciteitsverlies
wordt geteld, bestaand bewijs wordt niet verdrongen. Lege berichten, leesvragen
en teruggedateerde rapporten creëren/verjongen geen apparaatbewijs. Een versie
wordt alleen uit één voldoende compleet0x02-rapportfragment opgebouwd.

De bestaande beveiligde HTTP-routewrapper bedient GET `/status/ems/devices`.
Die leest voorraad/decoder onder dezelfde mutex. Er is geen writer toegevoegd.
De data toont ontvangst, geen sensor-/actuator-/ketelkwalificatie. HA-configuratie,
MQTT-wire, SOURCE, syslog, instellingen, TX-locks en fysieke uitgangen veranderen
niet. Verschillende apparaten op dezelfde fysieke busadresidentiteit worden
zonder zelfstandig geverifieerde identiteit niet als afzonderlijke modellen
verzonnen.

Controles:649native tests inclusief4inventaris- en7nieuwe sessieklokgevallen;
zes echte Chromiumprofielen EN/NL op1280/390/320px,17webunittests en E32-build.
Dit is gesimuleerd/passief softwarebewijs; echte live apparaatontvangst en volledige
veldpariteit blijven B04–B09/B14. Bewijs in `out/plan-priorities-ems-devices-20261024/`.
