# Testkandidaat 22 oktober 2026

Deze kandidaat richt zich op de volledige lokale softwareketen en de voorbereiding
van de badkamerproef. Mark kiest later zelf de temperatuursensor en TRV via de
native HA-formulieren. Er staan geen woningentiteiten in de productbron.

Softwarebewijs:249verschillende gerichte native HA/C++-gevallen met sanitizers,
34release-auditgevallen, echte gepinde HA2026.10.2-frontend desktop/mobiel en een
geïsoleerde echte MQTT-keten met één exacte1888Bopslagtransactie. De normale
E32-app/FS op de eerste bron `63be9bc` zijn succesvol gebouwd en teruggelezen;
de finale exacte bron-/imagehashes staan in `out/release-candidate-20261022`.
De firmwarepakketcontrole blijft geblokkeerd op SDKbron-/licentieclosure.

## Wat je kunt controleren

1. Maak een shadow-installatie en laat runtime eerst uit.
2. Voeg de badkamer toe met de gewenste temperatuursensor en binding
   **Heating graph draft**. Kies basisdoel, grenzen en lokaal weekprogramma.
   Een HA Schedule-helper is een alternatief; per kamer precies één schemabron.
3. Configureer de centrale verwarmingsdraft zonder weerregeling, pomp of mixer.
   Voeg één radiatorgroep en één `trv_room_setpoint`-actuator toe met de gekozen
   climate-entiteit. Bewaar de draft.
4. Open **Independent local shadow profile (runtime off)**. Vul de echte E32-ID
   in en kies **Use the complete-week shadow contract**. Controleer kamer,
   resourcekoppeling, grenzen en fingerprint. Het oude achtpuntsprofiel blijft
   een afzonderlijke keuze en vereist twee kamers.
5. De bijbehorende lokale E32-descriptor en brokerinstellingen moeten apart
   overeenkomen. Deze HA-review installeert of herstart de E32 niet.
6. Pas na die voorbereiding: schakel shadow-runtime in; kies prepare, lees het
   volledige plan en bevestig apply eenmaal. Alleen **exact current plan readback
   verified** bewijst dat het plan is teruggelezen. Een ACK alleen is onvoldoende.
7. Controleer annuleren, gewijzigd doel, dubbele bevestiging, herladen en offline.
   Een concept mag niet zelfstandig worden toegepast; onbekende configuratie
   of onzekere verzending moet zichtbaar blokkeren.

Voor deze softwarekandidaat blijven fysieke uitgangen uitgeschakeld. Een echte
kraan bewegen hoort bij de afzonderlijke M2-acceptatie en vereist een bewezen
meet-/actuatorprofiel; het kiezen van een climate-entiteit is dat bewijs niet.
De Tado blijft de werkende verwarmingsregelaar zolang de commissioning openstaat.

## Grenzen voor oplevering

De pakketbouwer controleert SDK-notices/bronclosure vóór hij een firmwarepakket
maakt. De bekende closureblokkade wordt niet omzeild door een handmatige zip of
andere naam voor hetzelfde firmwarepakket. Lokale buildresultaten zijn wel
inspecteerbaar bewijs, geen vrijgegeven download of flashopdracht.

E32-stack/peakheap/NVS-GC, echte HTTP/NVS/update/recovery, continue gekwalificeerde
metingen en veiligheidsproducers, fysieke kraan, ketelstop bij uitval en72uurproef
blijven afzonderlijk te bewijzen. Zie ook
[de ketelstopvoorproef](KETELSTOP-VOORPROEF.nl.md) en het canonieke werkbord.

Lokale bewijsmap: `out/release-candidate-20261022`. Deze bevat ook strikt lokale
testaccounts en browserstate; deel of archiveer die map nooit integraal.
Alleen expliciet geselecteerde bron-/bewijsbestanden mogen naar een overdracht.

Rollback vóór installatie: alleen deze bronwijzigingen terugnemen. Geen HA-journal,
NVS, kamerdata, modellen, Recorder of historie wissen. Na een werkelijk toegepast
nieuw contract vraagt teruggaan compatibele bron en expliciete migratie.
