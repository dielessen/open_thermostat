> **Ontwerp-/bewijsnotitie.** De enige actuele software-, installatie- en releasevoortgang staat in [WORKBOARD](WORKBOARD.nl.md). Gedateerde versies en toenmalige open punten hieronder blijven historisch; technische acceptatievoorwaarden blijven gelden.

# E32-bronbewijs — voortgang nacht 22 op 23 oktober 2026

**Actuele updaterlevering 23 oktober — alpha.14 werkelijk via GitHub geïnstalleerd:**
De E32 draait `v0.1.0-e32v2-alpha.14`, bron
`b4e2704c56bfe4e6d1649f9751992c30ca8d7d21`. Alpha.13 is eerst via de normale
app-upload geplaatst; daarna heeft het bord zelf alpha.14 via de ingebouwde
GitHub-updater gevonden, gedownload en geïnstalleerd. Ontvangst van
1.503.726/2.380.560 bytes is tussentijds uitgelezen; de nieuwe opstart is daarna
bevestigd. Versie/bron/webhash komen overeen met de publieke release.
Alle zeven vooraf/achteraf gelezen configuratie-/programmabestanden zijn gelijk;
native SOURCE-beleid, configuratierevisie en digest ook. Alle fysieke uitgangen
blijven false. Geen factorybeeld, wisactie, filesystem-upload of HA-herstart.

De seriële fout `FFFFBD70` is RSA_PUBLIC_FAILED + MPI_ALLOC_FAILED: onvoldoende
geheugen tijdens certificaatverificatie. Alleen de tijdelijke updatetaak gebruikt
nu expliciet PSRAM voor TLS; andere taken behouden de SDK-allocator. De werkelijke
ELF-allocatorpointer is gecontroleerd. Certificaat-/hostname-/download-/image-/
readbackcontroles blijven ingeschakeld. Een buffer-only tussencorrectie is niet
als voldoende oplossing geaccepteerd; alpha.12 is ongepubliceerd gebleven.
470 native tests, app/FS-build, bordverificatie en volledige CI slagen. Beide
publieke pakketten zijn onafhankelijk op 1029 pakketcontroles, 548 Git-bronfiles,
checksums en bijbehorende CI-ELF gecontroleerd. Alpha.13 CI39950927499 PASS;
alpha.14 CI39951336252 PASS in poging2. Poging1 had één HA-native klimaat-/
vraagtestfout; dezelfde ongewijzigde testbron slaagde bij de gerichte jobherhaling.
Geen gate of assertion omzeild; de eerste fout is bewaard als afzonderlijk bewijs.

Ook een verse HTTPS-controle op de geïnstalleerde alpha.14 is zonder fout
afgerond: alpha.14 en alpha.13 worden aangeboden.
Normale in-device HTTPS-ontdekking én update zijn nu fysiek aangetoond. Dit is
geen acceptatie van spanningsuitval/USB-herstel, 72h-bedrijf of verwarming.
Bewijs: `out/ota-tls-diagnostics-20261023/FINAL-REAL-UPDATE-REVIEW.json`,
`ALPHA*-PACKAGE-REVIEW.json`, `ALPHA*-SOURCE-REVIEW.json`,
`ALPHA*-CI-LINK-REVIEW.json`; privé-uitlezingen blijven in dezelfde 0700-map.

**Actuele vervolglevering 23 oktober:** alpha.10 en alpha.11 zijn publiek
geleverd via de bestaande volledige CI. De onafhankelijk gedownloade alpha.11
uit bron `7e3889bd8316ded1e91c6fefda125700241d42f4` slaagt op 1029
pakketcontroles en 544 Git-bronbestanden; de werkelijke CI-ELF en appdescriptor
zijn gelijk. Volledige publicatie-CI39916118166 slaagt. De cataloguscorrectie
heeft 466 native C++-proeven. Geen verruiming van toelating, rechten,
instellingenschema of globale frameworkclosure.

Het bord draait nog alpha.9. De alpha.10-upload gaf een verbindingsreset; nieuwe
uitlezing bevestigde dezelfde alpha.9/configuratie en uitgangen uit. De oorzaak
is onbekend; geen herhaalde upload tot de latere USB-/seriële diagnose. Alpha.11
is niet geïnstalleerd. Bewijs: `ALPHA11-PUBLISHED-ROOT-REVIEW.json` en
`E32-ALPHA10-FAILED-UPLOAD-READBACK.json` onder `out/plan-execution-20261023/`.

**Actuele levering23oktober:** E32-alpha.7,alpha.8 enalpha.9 zijn via de
bestaande volledige GitHub Actions uitgebracht met overeenkomstige bron-/notice-
levering en onafhankelijke pakketcontrole. Alpha.9bron `63da355` draait werkelijk
op de E32;1025 pakketcontroles en535 bronbestanden zijn onafhankelijk vergeleken.
De globale frameworkclosure is niet gewijzigd en inputloze verpakking blijft
geweigerd. Actuele details en bewijspaden staan bovenaan de testkandidaat.
De eerdere voortgang hieronder beschrijft de historische tussenstappen.

**Vervolg 23 oktober — herhaalbare levering en actuele badkamercontrole:**
De bronrelease `sources-e32v2-20261023.2` is gepubliceerd; de gedownloade bytes zijn
onafhankelijk gecontroleerd. De herbruikbare E32-tools leggen echte compileer- en
linkcommando's vast, controleren de huidige3257 frameworkbestanden,593 gebruikte
externe bronbestanden en762 behouden vendorinputs, en herlinken de actuele app
exact én met een gewijzigde Arduino-bibliotheek. Ze veranderen geen uitvoerrechten.

De geleverde bronnen zijn opnieuw naar een lege werkmap uitgepakt met veilige
archiefcontrole. Alle346 C/C++-SDK-,11 assembler-,269 runtime- en3 startupunits
zijn opnieuw gebouwd en onafhankelijk tegen echte oorspronkelijke archiefleden
en bronhashes gecontroleerd. GitHub run39881549821 herhaalt dit succesvol vanuit
schone commit8295d47; de gedownloade629-objectbewijsset is exact gelijk aan de
lokale beoordeling. De bijbehorende recepten en configuratieheaders staan nu in
de gewone projectbron onder `docs/third-party/e32v2-reproduction/`.

De volgende verpakkingswijziging koppelt deze bewijzen aan de daadwerkelijke
bron-/notice-/objectlevering, met afzonderlijke payloadcontrole. De globale
frameworkclosure blijft ongewijzigd; zonder alle E32-materialen weigert het
bestaande verpakkingspad nog steeds.40 gerichte bron-/gatecontroles,10 bestaande
noticecontroles en6 CA-controles slagen lokaal. Volledige huidige verpakkings-CI
loopt nog; de eerste nieuwe CI-run vond een ontbrekende CA-toolafhankelijkheid,
die gericht wordt vastgelegd. Er is nog geen alpha.7-firmware gepubliceerd of
op de E32 geplaatst. Fysieke M2 en herstelacceptatie blijven open.

De HA-specialist las om02:54CEST dezelfde installatie en badkamerbindings opnieuw:
dev11 gezond, gekozen Aqara-sensor beschikbaar21°C, gekozen Tuya-TRV beschikbaar
18,3°C/doel23°C/presetauto. De kamersensor is aanwezig en gekoppeld. Geschiktheid
van `device_temperature` als kamermeting, originele acquisitietijd en geïnstalleerde
converter/exposes blijven afzonderlijk onbewezen. Nul services, publicaties of
herstarts; het gesaneerde resultaat is privé bewaard met0600.

Bewijs: `out/plan-execution-20261023/PORTABLE-REPRODUCTION-ROOT-REVIEW.json`,
`github-sdk-reproduction-8295/source-reproduction.json`,
`REPRODUCTION-MATERIALS-PUSH-REVIEW.json`, `SCOPED-PACKAGING-PUSH-REVIEW.json`
en het privébestand `HA-CURRENT-SANITIZED.json`. Het WORKBOARD is niet gewijzigd.


**Uitvoeringsupdate 23 oktober — firmwarebouw en bronlevering:**
De generieke ESP32 past weer in de bestaande OTA-partities: werkelijk beeld
1.700.880 bytes bij 1.703.936 bytes per slot. Acht uitvoerstreams gebruiken nu
`ostringstream`; de bestaande Xtensa-linkermaatregel `--size-opt` geldt uitsluitend
voor `esp32dev`. De partities, E32/S3-linkinstellingen en uitvoerblokkades zijn
behouden. Native C++456 PASS; GitHub bevestigt generiek, S3, native en browser PASS
op commit `7dddd6f` (run39878720662). De afzonderlijke E32-releasegate is nog open.

De schone E32-alpha.7-app uit dezelfde commit bouwt en doorstaat de bordcontrole:
2.373.712 bytes, SHA256
`10aff9b8d14403123cf6c0c9f1545e19ec5d423d0cf2ac27c6411c157053c911`.
Alle behouden SDK-/runtime-identiteiten zijn gelijk aan de beoordeelde set.
De huidige applicatieobjecten zijn exact herlinkt; een bewust aangepaste Arduino-
bibliotheek linkt ook en wijzigt aantoonbaar de behouden `millis()`-code.
De aangepaste proefbeelden worden niet geïnstalleerd of als firmware aangeboden.

Het officiële PlatformIO-frameworkarchief is op de gepubliceerde checksum
gecontroleerd: alle1.020 Arduino-bronbestanden en2.237 ESP32-SDK-bestanden komen
overeen. De zeven verschillen met de Arduino-Gitbron zitten dus ook exact in het
officiële pakket; hun pakketuitgever is vastgesteld, auteurs worden niet verzonnen.
Een apart bronpakket bevat12 bronarchieven en52 originele bron-/noticepayloads;
2.311 verplichte bronpaden en alle payloadchecksums zijn getoetst. Negen controles,
ook op corruptie, ontbrekende notices en onveilige archiefpaden, slagen.
De afzonderlijke bronrelease `sources-e32v2-20261023.2` is via GitHub Actions
run39879346054 gepubliceerd. De gedownloade204.384.360 bytes komen exact overeen
met SHA256 `4ffa03e6704c440763ef09a27234cd6c2a4f809fb62bece3a2a3190c8b71166c`.
Dit pakket keurt op zichzelf geen firmware goed. Volledige huidige firmwareverpakking,
notice-/bron-/herlinkvrijgave en app-only installatie blijven open. Geen E32-update,
HA-wijziging of fysieke M2-aftekening in deze stap.

Bewijs: `out/plan-execution-20261023/` met `FIRMWARE-CI-FIX-PRECHECK.json`,
`E32-CLEAN-ROOT-REVIEW.json`, `CURRENT-APPLICATION-RELINK-ROOT-REVIEW.json`,
`FRAMEWORK-OFFICIAL-SOURCE-COMPARISON.json` en `SOURCE-INPUT-VERIFY.json`.


Dit is een begrensde technische uitkomst voor de actuele E32-build. Het hele
productplan, de firmware-release en de fysieke badkamerproef zijn nog open.
Er is in deze stap geen firmware geplaatst en geen HA-instelling gewijzigd.

## Wat nu daadwerkelijk is bewezen

De actuele ELF/linkmap gebruikt dezelfde **52 SDK-archieven** als de bestaande
inventaris. Alle **2.237 bestanden** van de geïnstalleerde ESP32-SDK, inclusief
de gebruikte headers en configuratiebestanden, zijn exact gekoppeld aan de
oorspronkelijke Git-blobs in Arduino2.0.17-commit
`5e19e086c43d0fa5e5a596497ff8f11a0a43f6c2`.

Van de gebruikte open SDK-bron zijn **346 C/C++-objecten en 11 assemblerobjecten**
opnieuw gecompileerd. Na uitsluitend verwijderen van debuggegevens en `.comment`
zijn de volledige relocatable objectbestanden byte voor byte gelijk aan de
oorspronkelijke objecten. De finale controle gebruikt geen hernoeming van
symbolen of secties en geen wijziging van instructies/data. De oorspronkelijke
GNU-ar-leden zijn onafhankelijk opnieuw uit de echte archieven gelezen,
inclusief gelijknamige efuse-objecten uit verschillende bronmappen.

De **negen oorspronkelijke prebuilt archieven** hebben eveneens een exacte
Git-blobherkomst in de gepinde IDF/vendorrepositories. Dit is een herkomstbewijs,
geen claim dat hun ontbrekende bron opnieuw gebouwd is. De oorspronkelijke
vendorlicenties zijn afzonderlijk en ongewijzigd behouden; een algemene
juridische vrijgave wordt hiermee niet geclaimd.

Belangrijke reproductiedetails:

- De gedeclareerde IDF-bron is commit
  `38eeba213aa695aabfd6d89aa9f5078dbe5a94c3`; submodules zijn aan de echte gitlinks
  gekoppeld. Zeven SDK-bronsnapshots bevatten samen12.094 gecontroleerde Git-blobs.
- De compileerinstellingen volgen de oorspronkelijke DWARF-informatie en CMake-
  bestanden. Onder meer de globale POSIX-reader/writerlockdefinitie, private
  includes, WPA-configuratie en macro-prefixmappen waren nodig voor exacte bytes.
- Het SDK-appdescriptorobject is gereproduceerd met zijn **oorspronkelijke**
  project-/datum-/tijdinvoer uit maart2024. Dat is geen verse apparaatmeting of
  nieuwe firmwarebouwdatum. De actuele app/buildidentiteit blijft afzonderlijk.
- Twee generieke assemblerleden gebruiken de oorspronkelijke QIO-configuratie;
  met de DIO-header verschilden twee PSRAM/cachevertragingsconstanten. De passende
  oorspronkelijke configuratie reproduceert ook die objecten exact. Er is geen
  project-, CPU-, flash- of PSRAM-instelling gewijzigd en geen fysieke klokfout
  opgelost verklaard.

## Compiler-runtime: exacte objectreproductie bewezen

De compiler, gebruikte runtimebestanden en oorspronkelijke licentiebestanden
zijn tegen de officiële toolchainrelease vergeleken: **93 bestanden exact**,
waaronder81 oorspronkelijke licentiebestanden. De twee gedownloade originele
releasearchieven voldoen aan de gepubliceerde SHA256-controlesommen.

De publieke GCC-, Newlib- en crosstool-bronsnapshots zijn aan vaste commits
gekoppeld. Hun volledige Git-rootbomen zijn uit de archieven opnieuw berekend en
gelijk aan de oorspronkelijke commitmetadata. Ook de oorspronkelijke Xtensa-
overlays zijn via de echte crosstool-gitlink opgehaald en aan de volledige
Git-rootboom gekoppeld.

Alle **269 gebruikte runtimeobjecten en de drie gebruikte startup-objecten**
zijn exact gereproduceerd na uitsluitend verwijderen van debuggegevens en
`.comment`. De onafhankelijke verifier leest de echte archiefleden opnieuw,
vergelijkt de bron met de oorspronkelijke GCC-/Newlib-archieven en toetst de
objecten opnieuw. De 402 gebruikte/geïnstalleerde compiler-pluginheaders zijn
aan de oorspronkelijke officiële compilerrelease gekoppeld. Er blijven in deze
objectproef geen byteverschillen of compilatieproblemen over. Eerdere mislukte
pogingen blijven als onderzoeksspoor bewaard. Een complete source/relink-offer
en de overige firmware-releasevoorwaarden blijven afzonderlijk open.

## CA-bron, oorspronkelijke notices en conversie bewezen

De bestaande PEM-bundel is exact gelijk aan het gepubliceerde historische
`cacert-2026-09-25.pem` en zijn gepubliceerde SHA256. De oorspronkelijke Mozilla-
`certdata.txt` is aan commit `f6dd0159931e536991eaaa02d839bdffb92c3f22` en Git-blob
`0a451693c675b9dba2805271516d672db913a204` gekoppeld. De bijbehorende oorspronkelijke
MPL-tekst en converter-/generatornotices zijn ongewijzigd behouden.

De oorspronkelijke curl-converter 1.33 uit vaste commit
`0ada20387c31c638cfd7f6b4ae7e5cab5b318caf` reproduceert de volledige PEM-bytes. De
oorspronkelijke Espressif-generator reproduceert ook de volledige ingebouwde
binaire bundel. Een nieuwe offline repositorycontrole toetst de 121 certificaten
tegen de echte Mozilla-server-auth-trustobjecten en bouwt de bundel opnieuw.
Zes gerichte controles inclusief notice-, bron-, trust- en binaire corruptie
slagen; de bestaande release-noticeregressie blijft slagen.

Manifest: `docs/third-party/ca-provenance.json`; oorspronkelijke bytes onder
`docs/third-party/ca-originals`; verifier: `scripts/verify_ca_snapshot.py`. De
vertrouwde certificaten zelf zijn niet veranderd. Dit bewijst geen Firefox-
constraints, actuele beveiligingsreview of vrijgave van de hele firmware.

## Verse badkameruitlezing

De HA-specialist heeft de bestaande native leesroute gebruikt. Dev11 is gezond
en geladen; dezelfde kamer en bindings bestaan. De gekozen Aqara-meting is
beschikbaar en meldde20°C. De gekozen Tuya-TRV is beschikbaar en meldde18,4°C,
doel23°C, presetauto, bereik5–30°C/stap0,5. De opgeslagen kamer-/weekdoelen
blijven21°C. De herkomst van een eventuele eerdere doelwijziging is niet bepaald.

De aanvullende specialistbeurt heeft bestaand, werkelijk gelezen modelbewijs
teruggewonnen nadat de eerste beurt zijn uitvoertijdlimiet bereikte: Aqara
**RTCGQ11LM** (`lumi.sensor_motion.aq2`) en Tuya **TV02-Zigbee** (`TS0601`,
`_TZE200_hue3yfsn`). Dit is geen nieuwe actuele waardemeting. De geïnstalleerde
converter/exposes, originele acquisitietiming en inhoud van het lokale
TRV-programma blijven onbekend. Volgens de officiële Zigbee2MQTT-modelpagina
is `device_temperature` de apparaattemperatuur; geschiktheid als kamermeting
wordt dus niet uit de beschikbare waarde afgeleid. De sensor is hiermee niet als
defect of ontbrekend bestempeld. Runtime/transport/actuatie zijn uit. De specialist
deed nul services, MQTT-publicaties, SOURCE-selecties, E32-logins of herstarts.

## Schone kandidaat en daadwerkelijk bruikbaar herlinkmateriaal

Een afzonderlijke, schone broncheckout is vastgelegd als commit
`56e7d94c15adca50aba88482a7e6fa4c88378c31`. De gewone native app- en FS-build slagen.
De app is 2.374.672 bytes, SHA256
`2b3c8e1e02a86886c2b5ac2c79528a4900fc36583f11a8098efdbf7b4e34c7b2`.
De onafhankelijke bordcontrole bevestigt partities, OTA-/FS-ruimte, veilige
fabrieksinstellingen en afwezigheid van projectverwijzingen naar UART-TX.
De ingebedde bron-/webidentiteit hoort bij de schone commit. De historische
SDK-appdescriptor blijft afzonderlijk; zijn producent-/versietekst is geen
nieuwe apparaatuitlezing.

Alle SDK-/runtimeobjecten zijn bovendien nogmaals met de definitieve recepten
gecompileerd zonder eerder geslaagde resultaten over te nemen: 346 C/C++-SDK-
objecten en 269 runtimeobjecten exact, opnieuw onafhankelijk getoetst. De complete
SDK-ledencontrole dekt alle 490 werkelijk behouden archiefleden: 352 unieke
nagebouwde leden plus 138 leden uit de negen exact oorspronkelijke prebuilt
archieven. Gelijknamige objecten kunnen meerdere bronunits vertegenwoordigen.

De werkelijk gebruikte Arduino-bron bevat 1.020 bestanden: 1.012 zijn gelijk aan
de oorspronkelijke Git-blobs; zeven bestanden wijken af en één versieheader is
gegenereerd. De zeven verschillen zijn expliciet geëxporteerd en zonder fuzz
op de oorspronkelijke bron opnieuw toegepast. De actuele bronbytes zijn als
preferred-form-bron bewaard. De herkomst/auteurs van die bestaande wijzigingen
wordt niet verzonnen en die bestanden worden niet upstream-identiek genoemd.

De nieuwe kandidaat gebruikt dezelfde SDK-leden en logisch dezelfde overige
linkinputs. PlatformIO wijzigt alleen zijn interne library-cachemapnamen bij een
andere projectmap; dit is vastgelegd. De verse librarybron komt overeen met de
bewaarde bronhashes. Er is geen code-, data- of symboolnormalisatie gebruikt.

Het bewaarde herlinkmateriaal reproduceert de **volledige ELF exact**. Een
afzonderlijke proef koppelt dezelfde applicatieobjecten ook met een doelbewust
gewijzigde Arduino-library; de gebruikte `millis()`-code verandert aantoonbaar.
Die proef-ELF wordt niet geïnstalleerd of meegeleverd als installatiekandidaat.
De originele library en bron blijven ongewijzigd.

Een lokaal beoordelingspakket bevat 13 bronarchieven, de schone projectbron,
344 echte object-/archiefinputs, recepten, bronmetadata en oorspronkelijke
notices. Alle 512 opgenomen bestanden zijn na ZIP-creatie opnieuw op checksum
gecontroleerd; de 582 projectbronbestanden komen overeen met de schone snapshot.
Pakket: `out/sdk-component-map-20261022/e32-source-review-56e7d94c.zip`,
237.369.530 bytes, SHA256
`0a3ef8f0b329c1e48687d168d15427f4e21c802d6f61ca5e09d3b873cd1352a8`.
Dit is bron-/herlinkmateriaal voor review, geen firmware-releasepakket.

De verbose-build werd onderbroken door een SCons-fout bij het tonen van een
opdracht. De gewone app-build liep daarna door zonder tool- of bronwijziging.
Beide logs zijn behouden; dit wordt niet als een firmwarecompilefout of als
opgelost toolprobleem voorgesteld.

## Vervolg zonder nieuwe gebruikersvraag

1. Het opgebouwde bron-/build-/herlinkmateriaal en de notice-/leveringsvoorwaarden
   voor de exacte E32-kandidaat afronden. De bestaande algemene releaseblokkade
   is niet met een vlag omzeild; andere targets zijn niet door E32-bewijs gedekt.
2. Pas na die review het gewone gecontroleerde firmwarepakket maken. De schone
   kandidaat is al gebouwd; niet opnieuw vanaf losse werkbestanden beginnen.
3. Via de HA-specialist de geïnstalleerde converter en echte rapportbron verder
   kwalificeren; een HA-tijdstempel is geen acquisitietijd. De modelidentiteit
   hoeft niet opnieuw te worden geraden.
4. Pas na passende firmware-/herstelvoorwaarden de E32-kandidaat plaatsen en de
   echte HA→E32→ACK-/kraanproef zonder ketel uitvoeren.

Reproduceerbaar bewijs: `out/sdk-component-map-20261022`, met onder andere
`SDK-ROOT-REVIEW.json`, `verify-sdk-correspondence.py`, `RECOMPILE-FULL.json`,
`RECOMPILE-ASSEMBLY.json`, `FULL-SDK-ORIGINAL-BYTES.json`,
`TOOLCHAIN-ORIGINAL-IDENTITY.json`, `TOOLCHAIN-SOURCE-ARCHIVES.json`,
`RUNTIME-ROOT-REVIEW.json`, `RUNTIME-STARTUP-RECOMPILE.json`,
`CA-ROOT-REVIEW.json`, `CA-TESTS.log` en de geschoonde native HA-voorcontrole/modeluitlezing. De originele
CLI-provideruitvoer blijft privé. Alle bestaande releaseblokkades, E32-uitvoer-
blokkades, partities en de HA-dev11-bron zijn behouden.

Nieuw kandidaat-/pakketbewijs: `CLEAN-CANDIDATE-ROOT-REVIEW.json`,
`SDK-SOURCE-OFFER-ROOT-REVIEW.json`, `RUNTIME-SOURCE-OFFER-ROOT-REVIEW.json`,
`SDK-MEMBER-COVERAGE.json`, `ARDUINO-SOURCE-OFFER-ROOT-REVIEW.json`,
`RELINK-ROOT-REVIEW.json` en `SOURCE-RELINK-MATERIALS-ROOT-REVIEW.json`.
