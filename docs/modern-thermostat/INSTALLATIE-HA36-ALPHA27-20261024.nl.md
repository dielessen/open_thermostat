# Geleverde gezamenlijke bundel — 24 oktober 2026

## Werkelijk geladen versies

- HA0.4.0.dev36, bron `c41b7a6e12730f88eb98960299be3236c6494457`, ZIP508967bytes, SHA256 `88713ae2ee282b26702401b16fd992ab0622ec5587355a8fad5162ba9baeedd1`.
- E32v0.1.0-e32v2-alpha.27, bron `dd6a9635865c6ecd2bf1c553c3292ae13dfb53ae`, app2574720bytes, SHA256 `2bd7b9c68b1c75bc3d731bddf1fe1181448588b207899f9353d5a6609b487b6e`.
- E32 ELF `28af06f4be6ca18a8b7712fb9176896b8d9675dc32406ee7fd9472ffdf3aff5b`; web `baa95e3f15f9d5e69ebc24ea796f2cab18d9aef0afe2cc1403300ab5dec29238`; boot_pending=false, normale boot bevestigd.

## Herstel en controles

De live Core bleek2026.10.3 terwijl dev34/dev35 alleen exact2026.10.2 toestonden.
Dat veroorzaakte setup_error en ontbrekende room/get-registratie. Dev35 is daarom
niet geïnstalleerd. Dev36 accepteert expliciet2026.10.2 en2026.10.3 via dezelfde
vijf guards, met alle overige controles behouden. De gebruikte zeven upstream
kern-API-bronnen zijn byte-identiek. Beide volledige2109-testsets slagen; alle
vereiste CI-jobs en onafhankelijke bron-/pakketreviews slagen.

Na één normale Core-herstart: entry geladen, room/get geslaagd, shadow_ready,
alle83 live componenthashes exact. Frontend dev35/v35,63990bytes, SHA256
`475125ed2d0378ce2bb2bb9f9c43d62340c2792523eb56a286577f10f6d61fdc`, werkelijk geserveerd.
De compatibiliteitscorrectie wijzigt geen firmwarebron: alpha27 blijft het eerder
gecontroleerde pakket. De verschillende broncommits zijn dus bewust.

Er is precies één app-only POST /ota uitgevoerd. De managementproxy liep na30s
vast op een time-out; de oorspronkelijke backend voltooide de upload na ongeveer43s.
Eerst is de onzekerheid vastgelegd, daarna alleen de bestaande receipt gelezen:
HTTP200/success en exacte stabiele nieuwe boot. Geen tweede upload, handmatige
herstart, factoryflash, erase, SPIFFS-upload of native HTTPS-installatie.
Dit bewijst geen herstel van de eerdere onverklaarde HTTPS-workerfout.

## Behoud en grens

Verse93-bestandenbackup, hashinventaris vóór en na gelezen; private back-up blijft
op de bestaande HA-back-uplocatie. Alle105 registryrecords,2devices, entries/
subentries, programma's, koppelingen, SOURCErev4, journal en privé pins/producer
behouden. E32-instellingen/netwerk/model/syslog exact behouden. Alleen de bedoelde
frontend-/kaartversie verandert. Vijf ESP-diagnosewaarden numeriek, RTCunknown.
Geen nieuwe startupfouten voor deze integratie in de beperkte system_log-lezing.

Tado blijft ongemoeid; EMS-TX/forwarder/GPIO/ketel-/kraanuitvoer blijven geblokkeerd,
verzonden EMS-frames en polls nul. De gekozen bron blijft profile_missing en
niet bruikbaar voor regeling; TV02-ontvangst wacht na herverbinden. Niets hiervan
wordt als ACK, valve_ready of fysieke kwalificatie opgevat. De normale zendroute
en fysieke acceptaties blijven open. Deze levering is een passieve prerelease.

Bewijs: `out/combined-dev35-alpha27-20261024/`, met exacte publieke pakketten,
CI-/bronreviews, XML per Core-versie en `SAFE36-INSTALL-RESULT.json`.
De bestaande eenmalige nachtcontrole behoudt tijd/eigenaar/scope en verwacht nu
deze daadwerkelijk geverifieerde versies; er is geen nieuwe job gemaakt.
