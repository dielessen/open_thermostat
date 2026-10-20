# Firmware bijwerken via jouw GitHub Releases

Bron: https://github.com/dielessen/open_thermostat/releases.
Deze releases zijn nog **experimentele testreleases**. EMS-/TRV-/GPIO-uitvoer
blijft geblokkeerd; dit is geen vrijgave voor verwarming. Houd EMS los.

## Eenmalige overstap vanuit de vorige testbuild

De oudere builds hebben deze releasekeuze nog niet. Download **firmware.bin**
uit de nieuwe GitHub-release en controleer de SHA256 tegen
`RELEASE-SHA256SUMS.txt` / `e32v2-update.json`.

1. Open het bestaande apparaatadres op je thuisnetwerk en log in.
2. Open **Firmware update**, kies bestandstype **Firmware** en upload de
   nieuwe **firmware.bin**. Kies NIET SPIFFS of `e32v2-factory.bin`.
3. Wacht op de bevestiging en herstart via de apparaatinterface.
4. Herlaad de pagina. Firmware en de bijpassende webinterface komen nu samen
   uit de applicatiepartitie. Je wifi, kamers, programma’s en overige
   instellingen zijn niet overschreven.

Er is voor deze overstap **geen volledige wisactie of SPIFFS-upload nodig**.
Dit veronderstelt de bestaande E32 V2-testbuild met onze ongewijzigde
16MB/dual-app-partitie-indeling. Niet toepassen op EMS-ESP of andere borden.
De aparte ZIP bevat ook een factorybeeld voor nieuwe, schone USB-installaties:
**dat factorybeeld wist instellingen** en is nooit een gewone OTA-upload.

## Voortaan vanuit het apparaat

1. Ga naar **Firmware bijwerken** en kies **Controleer op updates**.
2. Het apparaat haalt de laatste twee GitHub-releases op en controleert hun
   updategegevens. Alleen passende E32 V2 app-only releases verschijnen.
   Een testrelease is zichtbaar als zodanig gemarkeerd.
3. Selecteer de gewenste versie en kies **Downloaden en installeren**.
   Bevestig de keuze. Er worden nooit automatisch releases geïnstalleerd.
4. Houd het apparaat onder stroom. De pagina toont de ontvangen bytes en
   de controlefase. De gewone webserver/main loop blijven actief; zwaar
   netwerk-/flashwerk loopt in een tijdelijke native FreeRTOS-taak.
5. Pas na geslaagde controles verschijnt **Herstarten en update toepassen**.
   Herstart, wacht op opnieuw verbinden en controleer de getoonde versie.
6. Controleer je wifi, kamers en programma’s na de herstart. Bewaar voor de
   fysieke proef vóór/na dezelfde configuratie zodat behoud aantoonbaar is.

Een werkend thuisnetwerk, internet en geldige netwerktijd zijn nodig. NTP
moet ingeschakeld/bereikbaar zijn. De setup-wifi is niet de updaterroute.
Publieke GitHub-verzoeken hebben een API-limiet; er staat geen GitHub-token
op het apparaat. Alleen een handmatige controle gebruikt die API.

## Controle- en herstelgrenzen

- HTTPS met Mozilla CA-roots, hostnamecontrole en klokcontrole. Geen
  `setInsecure` of willekeurige downloadadressen; alleen vaste repository-
  paden en expliciete GitHub-downloadhosts/omleidingen.
- Manifestversie1 controleert bord, partitie-indeling, instellingenformaat1,
  app-only/ingebouwde UI, bestandsgrootte, SHA256 en bron-/UI-versie.
- Alleen de inactieve applicatiepartitie wordt beschreven. NVS en SPIFFS
  worden niet gemigreerd of overschreven. Een toekomstig ander schema
  vereist eerst een apart beoordeeld migratiepad; deze updater weigert dat.
- Exacte downloadlengte, echte ESP32/16MB-imageheader, ingebouwde
  release-/bron-/UI-marker, streaming SHA256, native imagevalidatie en een
  onafhankelijke SHA256-readback van de flash moeten slagen voordat de
  nieuwe bootpartitie wordt geselecteerd.
- Bij een fout of onvolledige download is er geen succesmelding en wordt
  niet bewust naar de onvolledige app omgeschakeld. Tijdens de download
  worden concurrerende OTA-uploads, reboot en setup-herstart geweigerd.
- De nieuw gestarte app bevestigt zijn OTA-boot pas na twintig seconden
  stabiele netwerk-/toegangs-/bestandssysteemgereedheid. Bij een
  onbevestigde boot volgt na twee minuten een herstart voor de native
  rollbackroute. De vastgepinde SDK heeft bootloaderrollback ingeschakeld;
  het echte terugvalgedrag en de op het bord aanwezige bootloader blijven
  fysiek te verifiëren. Twee slots op zichzelf zijn geen herstelbewijs.
- **Vorige firmware terugzetten** verschijnt alleen als de andere app-slot
  bij de native OTA-administratie als VALID bekend is. Dit is een aparte
  bevestigde herstelactie, geen willekeurige downgrade naar corrupte flash.
  Houd de USB-herstelroute en vorige release beschikbaar.

## Releases maken

Versie/compatibiliteit staan in `release.json`; verhoog de versie voordat
je een nieuwe tag maakt. Het E32-buildscript gebruikt de native PlatformIO
binary-embeddingfunctie voor uitsluitend `data/html` plus publieke CA-roots.
Gebruikersconfiguratie wordt nooit in de applicatie ingebouwd.

`scripts/package_e32v2_release.py` maakt app, manifest, checksums en een
afzonderlijk gemarkeerd installatiepakket uit een **schone, exacte commit**.
Een onafhankelijke verifier controleert bronarchief, echte ingebouwde UI,
manifest, ELF-identiteit, alle factorycomponenten en alle payloadchecksums.

Een `v*`-tag start de normale GitHub Actions. Publicatie van die tag als
testrelease gebeurt pas na build/native/browser/HA-CI, met immutable assets
`firmware.bin`, `e32v2-update.json`, checksums, softwarebewijs en installatie-ZIP.
De workflow overschrijft geen bestaande release. Een release-tag moet exact
de versie uit `release.json` zijn. GitHub-rechten blijven alleen bij Actions
en de operator; er gaan geen credentials naar het apparaat of de broncode.

## Nog fysiek te bewijzen

Eerste niet-wissende bootstrap -> releasecontrole -> echte download/update ->
herstart/versie/UI -> wifi/kamers/programmaconfiguratie behouden. Daarnaast:
verbroken download, afgewezen/corrupte upload, vorige-slotterugkeer en
USB-herstel. Browserfixtures en host-foutinjecties zijn geen fysieke OTA-proef.
