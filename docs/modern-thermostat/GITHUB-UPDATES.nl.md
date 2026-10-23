## Actueel op 23 oktober — alpha17/dev23 geleverd, eerste bèta in voorbereiding

De gezamenlijke alpha17/dev23-release is gepubliceerd, geïnstalleerd en
gecontroleerd. De normale HTTPS-updater/certificaatcontrole en huidige/archief-
indeling werken. Oudere versie- en installatieregels hieronder zijn historische
receipts. De nieuwe eerste bèta is nog niet gepubliceerd; zie WORKBOARD §6.
Geen bestaande tag/download vervangen of per losse reparatie opnieuw flashen.

## E32 alpha15 uitgevoerd — 2026-10-23

De E32 draait nu `v0.1.0-e32v2-alpha.15`, bron `043862c154eb314ad70f96c88062a716962c2a5e`. Het apparaat heeft de release zelf via HTTPS ontdekt, gedownload en app-only geïnstalleerd; de nieuwe boot is bevestigd. Alle zeven instellingen-/programmasnapshots zijn gelijk gebleven; SOURCE-policy/configrevision/digest en uitgeschakelde uitgangen zijn behouden. HA blijft de reeds geïnstalleerde dev20.

About, Sign out rechtsboven en Restart onder Settings staan nu live. Rechtstreekse Chromium-controle op het apparaat op 1280/390/320px PASS: exacte HTML-bron, About/credits, geen horizontale overflow, herstartbevestiging annuleren zonder opdracht. De bestaande 42 Node-tests en samengestelde browserproeven PASS. Volledige CI `39959955216` PASS, openbare downloads onafhankelijk geverifieerd: 1030 pakketcontroles/552 Gitbronbestanden plus echte ELF/embeddedweb/TLS-allocatoridentiteit PASS.

De publicatieworkflows op deze kandidaat bevatten nu `scripts/organize_releases.py`. De echte alpha15-publicatie heeft automatisch alpha15 als Actueel en alpha14 als Archief gelabeld, en de actuele downloadtabellen bijgewerkt. Catalogus idempotent; alle 22 publieke records passen in de firmwareparser. Voor toekomstige publicaties verdergaan vanaf deze schone kandidaat; de oudere GitHub-main bevat deze workflowwijzigingen nog niet. Tags en bestaande downloads niet vervangen.

Bewijs: `out/e32-alpha15-evidence-20261023/FINAL-REVIEW.json`, inclusief onafhankelijke deelcontroles en live screenshots. Dit sluit de voorbereide About/navigatie/releasebeheerwerkzaamheden af. Afzonderlijke langdurige/hardware-/verwarmingskwalificatie wordt hiermee niet geclaimd.

# Firmware bijwerken via jouw GitHub Releases

**Release-indeling:** kies in het overzicht bovenaan een release tussen
**E32-firmware** en **Home Assistant**. De nieuwste versies dragen `Actueel`;
oudere software heeft het voorvoegsel `Archief`. Bronpakketten zijn afzonderlijk
gelabeld. Historische toelichtingen blijven uitklapbaar beschikbaar. Tags en
publieke downloadlinks blijven behouden.

**Actueel 23 oktober:** alpha.14 is werkelijk via de ingebouwde GitHub-updater
vanuit alpha.13 geïnstalleerd, met behouden configuratie en bevestigde opstart.
De HTTPS-geheugenfout is gericht verholpen met taakgebonden externe TLS-allocatie;
certificaatcontrole blijft ingeschakeld. Oude firmware kan voor deze correctie
nog één normale app-only upload nodig hebben; Marks E32 is al bijgewerkt.

**Gepubliceerd23okt:** [HA0.4.0.dev13](https://github.com/dielessen/open_thermostat/releases/tag/ha-v0.4.0.dev13).
Afzonderlijke integratie-ZIP; bron en werkelijk gedownloade checksums gecontroleerd.
De HA/MQTT- en browser-CI zijn geslaagd. Dit is geen E32-firmware-update.
De live HA-dev11-installatie hoeft voor de bestaande bediening niet opnieuw te
worden geïnstalleerd. Dev11/dev12-tags hebben na hun CI-fout geen releaseassets.


Mark heeft op 23 oktober expliciet opdracht gegeven geteste wijzigingen als
GitHub-releases uit te brengen en de E32 waar nodig te upgraden. Normale passende
testupdates hebben daarmee voorafgaande toestemming. De controle van bron,
pakket, herstelmogelijkheid en configuratiebehoud blijft onderdeel van uitvoering.

Home Assistant krijgt afzonderlijke `ha-v<integratieversie>`-testreleases met een
integratie-ZIP, broncommit, native testresultaat en `HA-SHA256SUMS.txt`. Die bevatten
geen E32-firmware en vereisen geen nieuwe installatie als dezelfde HA-versie al
gezond is geïnstalleerd. De onderstaande E32-route en voorwaarden blijven apart.

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
3. Wacht op de bevestiging. Vanuit alpha.3 of ouder herstart je nog één keer
   via de apparaatinterface: de oude updater voert deze overstap uit.
   Vanaf alpha.4 herstart de E32 na een geslaagde app-update automatisch.
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
2. Vanaf alpha.7 doorzoekt het apparaat maximaal twaalf releaseberichten, één
   begrensd antwoord per keer. Het toont maximaal twee passende E32 V2 app-only
   releases na controle van hun updategegevens. HA-releases en releases zonder
   passend firmwarepakket tellen niet mee. Een testrelease is als zodanig gemarkeerd.
   Als geen passende release binnen deze zoekgrens is gevonden, meldt de interface
   dat oudere berichten niet zijn gecontroleerd. Alpha.6 en ouder bekijken alleen
   de twee nieuwste berichten; gebruik daar zo nodig de handmatige app-upload.
3. Selecteer de gewenste versie en kies **Downloaden en installeren**.
   Bevestig de keuze. Er worden nooit automatisch releases geïnstalleerd.
4. Houd het apparaat onder stroom. De pagina toont de ontvangen bytes en
   de controlefase. De gewone webserver/main loop blijven actief; zwaar
   netwerk-/flashwerk loopt in een tijdelijke native FreeRTOS-taak.
5. Vanaf alpha.4 plant het apparaat na geslaagde controles zelf een herstart
   met drie seconden respijt voor de HTTP-bevestiging/status. Dit werkt ook
   als de browser sluit. De pagina meldt de herstart, wacht op opnieuw verbinden
   en ververst de interface na uitlezen van de nieuwe versie. Controleer die versie.
   Dit geldt ook voor een handmatige app-upload, niet voor SPIFFS.
   Op alpha.3 of ouder blijft voor deze eerste overstap de knop
   **Herstarten en update toepassen** nodig.
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
- Alleen een geslaagde imagevalidatie en bootpartitiekeuze plannen de
  automatische herstart. Een actieve GitHub-flashtaak kan niet door deze
  timer onderbroken worden; herhaalde statusverzoeken verschuiven hem niet.
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
