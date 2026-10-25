# Eerste grote bèta — concept voor gebruikers

Deze bundel is nog in voorbereiding en niet gepubliceerd. De geïnstalleerde
basis blijft E32 alpha36 en Home Assistant dev48. De definitieve versies en
pakketten volgen na de gezamenlijke bronfreeze en releasecontroles.

## Nieuw

- **Bluetoothapparaten onder Instellingen.** Je kunt een Shelly BLU H&T Display
  toevoegen op adres en de ontvangst lokaal bekijken, met of zonder
  versleuteling. Sleutels blijven verborgen; temperatuur, vochtigheid, batterij
  en ontvangstdiagnose verversen zonder je invoer te overschrijven.
  Dit is nog geen meetbron voor de verwarmingsregeling; praktijkproeven,
  Xiaomi en TRV-aansturing blijven open. [Uitleg](BLUETOOTH-APPARATEN.nl.md).

- **Historie exporteren per dag, week of maand.** De gewone HA-actie ondersteunt
  maximaal 31 dagen, met een installatiekeuze en Nederlandse/Engelse uitleg.
  De export gebruikt bestaande Recorder-historie; ontbrekende gegevens blijven
  ontbreken. [Gebruiken en grenzen](HISTORIE-EXPORT.nl.md).
- **Automatisch controleren op firmware-updates.** De E32 controleert iedere
  twaalf uur en meldt een beschikbare update op het dashboard. Herhaalde
  controles kunnen vijf minuten lang hetzelfde recente resultaat gebruiken.
  Installeren blijft een afzonderlijke handeling; tijdens een ketelproef wacht
  de automatische controle.
- **Duidelijke klokmelding.** HA meldt een defecte lokale meetklok via Repairs.
  De oude E32-kamerweergave vertelt wanneer de regeling op apparaattijd wacht.
  De uitleg is beschikbaar in Nederlands en Engels.

## Opgelost

- OpenThermostat kan weer opstarten op Home Assistant Core **2026.10.4**.
  Een versiecontrole blokkeerde onbedoeld het maken van de weergavegroep
  ‘Installatie en ketel’. Instellingen en bestaande entiteitidentiteiten blijven
  behouden. Dit is in de bètabron hersteld; nog niet op je HA geïnstalleerd.

- Een fout bij het bijwerken van het scherm onderbreekt geen meetintrekking.
  Ook het vervangen van een sensorprofiel kan geen oude meting terugbrengen.
- Ongeldige of teruglopende lokale meettijd maakt ook raam- en
  aanwezigheidssignalen onbekend. Een nieuw bericht herstelt geen defecte
  meeteigenaar.
- Bluetooth kan na een mislukte scan opnieuw proberen. De ontdeklijst groeit
  niet onbeperkt; een volle lijst houdt een al ingestelde sensor niet tegen.
- Ongeldige temperatuur-, vochtigheids- en batterijwaarden worden geen echte
  meetwaarden. Een ontbrekende vochtigheid of gemiddelde temperatuur wordt
  niet als 0 getoond. Ongeldige doelen worden vóór verzending geweigerd.
- Namen met aanhalingstekens, apostroffen of regeleinden blijven leesbaar en
  bedienbaar in de bestaande kamerweergave. Statusberichten blijven geldige JSON.
- Bij ontbrekende apparaattijd gebruikt de oude kamerregeling geen oningevulde
  tijd of willekeurige weekdag. De warmtevraag wordt ingetrokken en de UI toont
  de pauze. De klokaanvraag gebruikt een time-out van 100 ms in plaats van de
  SDK-standaard van vijf seconden per kamer.
- Een wijziging van eigenaar of entiteit tijdens CSV-export breekt de export af;
  gegevens verschijnen niet onder een inmiddels andere koppeling.
- Fouten bij het bewaren van leermodellen worden opgevangen. Een onzekere
  schrijfactie wordt niet automatisch herhaald.

## Wat blijft nog open?

De bestaande functies en voorbereide onderdelen blijven behouden. Dit concept
geeft nog geen actieve ketel-, kraan- of zelfstandig-Bluetoothregeling vrij.
Oorspronkelijke metingen, causale kraanterugmelding, installatie-/stopveiligheid,
de normale leerroute, Xiaomi/TRV en zelfstandige Bluetoothregeling moeten nog
worden afgemaakt of in de praktijk worden gekwalificeerd. Het
[werkbord](WORKBOARD.nl.md) blijft de actuele checklist.

## English

This single beta bundle is still being prepared. It also repairs startup on
Home Assistant Core 2026.10.4 without replacing existing settings or entity IDs. It adds day/week/month Recorder
CSV exports, automatic firmware-update checks with a dashboard notice, and clearer
clock-failure messages in English and Dutch. A new Bluetooth settings page connects
local Shelly BLU H&T Display reception with encrypted bindings, write-only keys
and bounded diagnostics; these readings are not qualified heating inputs. It fixes retired measurements being
requeued, failing screen callbacks, invalid numeric readings, bounded BLE scan
recovery and discovery, and names that broke JSON or room controls. The legacy
room controller pauses when device time is unavailable and uses a 100 ms SDK clock
timeout. CSV export rechecks ownership; model-storage failures cannot trigger
blind retries. Missing history or measurements are never invented. Active boiler,
valve, learning and standalone Bluetooth acceptance remain open; no intermediate
release or device installation has been performed.
