# Gezamenlijke testbèta geïnstalleerd — 25 oktober 2026

De goedgekeurde gezamenlijke testrelease is gepubliceerd en geïnstalleerd:

| Onderdeel | Geïnstalleerd | Bron |
| --- | --- | --- |
| E32 | v0.1.0-e32v2-beta.1 | `5e3ed30653d93b09dd65b5305accd65d079c0c06` |
| Home Assistant-integratie | 0.4.0b1 op Core 2026.10.4 | dezelfde bron |

De HA-opstartfout `setup_platform_unsupported` is live hersteld: integratie geladen,
normale kameropvraag geslaagd. De E32 haalde het firmwarebestand zelf uit GitHub
via één native updateopdracht. Geen USB-, factory- of bestandssysteemflash.

## Bewijs en behoud

- 24 installatiecontroles en 45 afzonderlijke nacontroles geslaagd.
- Exacte publieke firmwarehash, broncommit, ELF en webidentiteit teruggelezen;
  alle 33 geserveerde webbestanden en 87 HA-bestanden vergeleken.
- Nieuwe bevestigde boot, dezelfde bootidentiteit in twee verse waarnemingen;
  uptime 696 naar 701 seconden. Updater niet bezig, geen fout of wachtende boot.
  De eindstatus `checked` betekent een afgeronde controle, geen lopende update.
- Verse back-up vóór schrijven; alle 97 payloads en manifest/metadata daarna
  opnieuw gecontroleerd. Geen volledige raw-flash-/NVS-dump of universele
  stroomuitvalgarantie.
- Projectinstellingen, programma’s, bron-/kamerbindingen en bestaande privé
  TV02-producent/pins behouden. 105 projectentiteiten, twee apparaten, één entry
  en twee subentries behouden. Optionele nieuwe Z2M-companion niet geïnstalleerd.
- Eén normale HA-herstart, één cataloguscontrole, één firmware-installatie.
  Geen configuratiesave, kraan-/ketelopdracht of extra expliciete E32-herstart.
- Fysieke uitgangen, ketel-/kraanaansturing en forwarder bleven uit;
  EMS TX/polls/proefframes bleven nul. Actieve verwarmingskwalificatie: NOT_READY.

De oorspronkelijke cataloguscontrole gaf een niet-JSON-antwoord waarvan de
HTTP-code niet bewaard bleef; de oorspronkelijke body en actieboekhouding wel.
Er is geen controle herhaald om dit bewijs te vervangen. De oorspronkelijke
installatieacceptatie HTTP202 is wel exact bewaard.

Twee onveranderde geheugenminima hadden oudere HA-tijdstempels en zijn met twee
verse directe E32-waarnemingen bevestigd. Niet alle vijf HA-diagnosetijdstempels
waren dus nieuw. De normale CPU-, vrije-geheugen- en uptimeberichten waren recent.

Globale HA-opslag is niet volledig bytegelijk: buiten dit project zijn
vernieuwde tokens/metadata en één verdwenen UniFi device_tracker vastgelegd.
Actor en oorzaak daarvan zijn onbekend. Projectidentiteiten bleven behouden;
er zijn geen oude globale registries of tokens teruggezet.

## Publicatie, updatepoort en vervolg

- [E32-download](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-beta.1)
- [HA-download](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0b1)
- [Hashgebonden acceptatie](update-acceptance/e32-beta1-20261025.json)
- [Verplicht updateproces](E32-UPDATE-PROCES.nl.md)

De native updatepoort voor deze versie is geaccepteerd. Iedere volgende
uitgerolde E32-versie vereist opnieuw een eigen volledige update/nacontrole.
Dit bevestigt de software-installatie; het sluit fysieke kraan-, bron-, ketel-,
stop-, uitval- en leerkwalificatie niet af. Nieuwere broncommits zijn niet
stilzwijgend op de module geïnstalleerd.
