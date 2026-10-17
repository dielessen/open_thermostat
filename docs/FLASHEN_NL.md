# E32 V2 flashen — eenvoudig stappenplan

**We gebruiken een USB-C-datakabel en een browser. Geen Python, PlatformIO of losse programmer nodig.**

> Dit stappenplan is voor **testrelease v0.1.0-e32v2-alpha.1** op een **BBQKees E32 V2 met 16 MB flash**.
> Deze versie kan de ketel **niet aansturen**; EMS-zenden is geblokkeerd en volledige klassieke EMS-ondersteuning ontbreekt nog.
> Laat de gateway tijdens deze proef **los van de ketel/EMS-bus**. Flashen wist de huidige firmware en instellingen.

## Wat heb je nodig?

- De E32 V2 en een **USB-C-kabel die data ondersteunt**, niet alleen opladen.
- Een computer met **Chrome of Edge**. Safari en Firefox zijn niet geschikt voor deze browserroute.
- De gratis, open-source browsertool [ESPConnect openen](https://thelastoutpostworkshop.github.io/ESPConnect/).
- Een map op je computer, bijvoorbeeld **E32-test**, voor de firmware en back-ups.

Gebruik de gewone ESPConnect-pagina, **niet de previewversie**. De knopnamen hieronder zijn Engels.

## 1. Bewaar eerst je huidige instellingen

1. Open de bestaande **EMS-ESP-webinterface** terwijl deze nog normaal bereikbaar is.
2. Ga naar **Settings → Upload/Download** en download de configuratie. De benaming kan per EMS-ESP-versie verschillen.
3. Bewaar ook je huidige EMS-ESP-versie en boardprofiel: maak een schermafbeelding van de systeeminformatie.
4. Bewaar de passende officiële **EMS-ESP ESP32-16MB+ herstelsoftware** en de [herstelprocedure](BBQKEES_E32V2.md#backup-before-any-future-physical-experiment).

**Let op:** een instellingenexport is nog geen volledige firmwareback-up. Die maken we in stap 3.

## 2. Sluit de gateway aan op je computer

1. Haal de **EMS-/ketelkabel en eventuele losse voeding** van de gateway af.
2. Verbind de **USB-C-aansluiting aan de buitenkant** van de E32 V2 met je computer.
   De E32 V2 krijgt tijdens het flashen voeding via USB; een extra adapter is niet nodig.
3. Open [ESPConnect](https://thelastoutpostworkshop.github.io/ESPConnect/) in Chrome of Edge.
4. Kies zo mogelijk **115200** als baudrate en klik op **Connect**.
5. Selecteer de USB-/seriële poort van de gateway en bevestig met **Connect**.
6. Controleer bij **Device Info**: **ESP32** en **16 MB flash**. Niet ESP32-S3 en niet 4 MB.

Bij beveiligingsinformatie moeten **Flash Encryption** en **Secure Boot** uit staan.
Zijn deze aan, of kun je dit niet vaststellen? **Stop vóór wissen of schrijven** en laat eerst de herstelroute controleren.

## 3. Maak twee volledige back-ups

Dit is de belangrijkste voorbereiding. **Klik hier nog nergens op Erase of Flash Firmware.**

1. Open links **Flash Tools**.
2. Zoek het blok **Flash Backup & Erase** en vul in:

   | Veld | Invullen |
   | --- | --- |
   | Start offset | `0x0` |
   | Length (bytes) | `0x1000000` |

3. Klik op **Download Flash Region** en wacht tot het downloaden helemaal klaar is.
4. Bewaar het bestand in **E32-test** als **e32-backup-a.bin**.
5. Klik **opnieuw** op **Download Flash Region** met dezelfde waarden. Bewaar dit als **e32-backup-b.bin**.
   Kopieer dus niet het eerste bestand: het moet een tweede uitlezing zijn. Laat de gateway tussendoor niet normaal opstarten.
   Een volledige uitlezing kan lang duren, zeker op 115200 baud; laat de computer niet slapen en trek de kabel niet los.
6. Beide bestanden moeten precies **16.777.216 bytes** groot zijn. Controleer bij bestandseigenschappen de werkelijke grootte, niet “grootte op schijf”.
7. Controleer dat de inhoud gelijk is. Hieronder staat het enige korte computercommando voor deze back-upcontrole; je hoeft er niets voor te installeren.

**Windows:** open de map **E32-test** in Verkenner, klik in de adresbalk, typ `powershell` en druk op Enter. Plak:

```powershell
Get-FileHash .\e32-backup-a.bin, .\e32-backup-b.bin -Algorithm SHA256
```

De twee waarden onder **Hash** moeten **precies hetzelfde** zijn.

<details>
<summary>Gebruik je macOS of Linux? Klik hier.</summary>

Open een terminal in de map met de back-ups.

macOS:

```sh
shasum -a 256 e32-backup-a.bin e32-backup-b.bin
```

Linux:

```sh
sha256sum e32-backup-a.bin e32-backup-b.bin
```

De twee hashes moeten identiek zijn.

</details>

**Alleen doorgaan bij twee volledige, identieke back-ups én een vastgelegde herstelroute.**
Bewaar een extra kopie buiten deze computer. De back-ups bevatten mogelijk wachtwoorden: zet ze **niet op GitHub**.
Gebruik niet alleen **Download Flash Backup** of **Download All Partitions**: voor dit stappenplan gebruiken we expliciet het volledige bereik hierboven.

## 4. Download onze firmware

1. Open [de E32 V2-testrelease op GitHub](https://github.com/dielessen/open_thermostat/releases/tag/v0.1.0-e32v2-alpha.1).
2. Download onder **Assets**: **open-thermostat-e32v2-v0.1.0-e32v2-alpha.1.zip**.
   Kies niet de automatisch gemaakte **Source code**-bestanden.
3. Pak de ZIP uit in **E32-test**. Het bestand dat je straks kiest is **e32v2-factory.bin**.

Dat ene bestand bevat de bootloader, partitie-indeling, firmware en webinterface.
Je hoeft de andere `.bin`-bestanden **niet afzonderlijk te flashen**.
Dit bestand is **niet** voor de bestaande EMS-ESP-webupdater of een flasher die automatisch EMS-ESP-partities toevoegt.

## 5. Flash één bestand

**Vanaf deze stap worden de huidige firmware en instellingen gewist.** De back-ups en herstelroute uit stap 1–3 moeten gereed zijn.

1. Ga in ESPConnect naar **Flash Tools → Flash Firmware**.
2. Kies bij **Firmware binary (.bin)** het uitgepakte **e32v2-factory.bin**.
3. Vul bij **Flash offset** exact **`0x0`** in. Kies **geen app-/OTA-offsetpreset**.
4. Vink **Erase entire flash before writing** aan.
5. Klik op **Flash Firmware** en controleer in de bevestiging nogmaals de bestandsnaam en **`0x0`**.
6. Bevestig met **Flash** en wacht op de voltooiingsmelding zonder foutmelding.

Laat de kabel aangesloten en de browser open. **Herstart de gateway nog niet:** eerst stap 6.
Bij een fout of onderbreking: niet op de ketel aansluiten; bewaar het log en herstel of herhaal pas na controle.

## 6. Controleer of de firmware goed geschreven is

Ga, nog vóór de eerste normale herstart, naar **Flash Tools → Flash Integrity**:

| Veld | Invullen |
| --- | --- |
| Start offset | `0x0` |
| Length (bytes) | `0xB80000` |

Klik op **Compute MD5**. Voor **alpha.1** moet de uitkomst exact zijn:

```text
3b8e061b32ea05f1886a4993028bfc8c
```

Dit controleert alle **12.058.624 bytes** van het gecombineerde installatiebestand op de chip.
Bij een andere uitkomst: **stop**; het schrijven is niet bewezen correct.
Deze waarde geldt alleen voor deze release. Na normaal opstarten kunnen instellingen wijzigen; daarom doen we dit vóór de eerste herstart.

## 7. Start de testfirmware

1. Klik op **Disconnect**. Haal de USB-kabel los en sluit hem weer aan.
2. Laat de gateway nog steeds **los van de ketel/EMS-bus**.
3. Zoek op je computer het wifi-netwerk **IntuiBaseHeating**.
4. Verbind met het tijdelijke wachtwoord **IntuiBaseHeating**.
5. Open **http://10.10.10.1/** in je browser.
6. Vervang het voorbeeldwachtwoord voordat je de gateway verder op een netwerk gebruikt.

**De webpagina moet bereikbaar worden.** De led hoeft niet te knipperen: led-aansturing staat in deze testfirmware uit.
Deze eerste proef is voor opstarten en de webinterface, niet voor werkende verwarming.

## Terug naar de oude firmware

Dit kan alleen met de volledige, gecontroleerde back-up van **dezelfde gateway** en zonder flash-encryptie/secure boot.

1. Laat de gateway los van de ketel en verbind hem weer met ESPConnect via USB-C.
2. Kies **e32-backup-a.bin** bij **Flash Firmware**.
3. Zet **Flash offset** op **`0x0`** en vink **Erase entire flash before writing** aan.
4. Flash en wacht op foutloze voltooiing. Lees vóór herstart de hele teruggeschreven 16 MB tweemaal terug via **Download Flash Region**, met start `0x0` en lengte `0x1000000`.
   Bewaar de nieuwe bestanden als **e32-herstel-a.bin** en **e32-herstel-b.bin**. **Overschrijf de originele back-ups niet.**
   Vergelijk de hashes met de originele back-up; op Windows vanuit dezelfde map:

   ```powershell
   Get-FileHash .\e32-backup-a.bin, .\e32-herstel-a.bin, .\e32-herstel-b.bin -Algorithm SHA256
   ```

   Alle drie de hashes moeten identiek zijn. Op macOS/Linux gebruik je het commando uit stap 3 met deze drie bestandsnamen.
5. Herstart pas na een gelijke hash. Controleer daarna de oude EMS-ESP-webinterface, instellingen, boardprofiel en netwerk.

**Niet blind weer op de ketel aansluiten.** De oude back-up bevat ook de oude zendinstellingen; laat die en het herstel eerst controleren voordat je de bus opnieuw verbindt.
Lukt herstellen niet? Gebruik de vooraf vastgelegde [officiële herstelroute](BBQKEES_E32V2.md#backup-before-any-future-physical-experiment).

## Als verbinden niet lukt

- Gebruik een andere **datakabel**, sluit rechtstreeks aan op de computer en druk de USB-C-stekker goed in de iets verzonken aansluiting.
- Sluit andere seriële programma's en browservensters die dezelfde poort gebruiken.
- Ontkoppel en verbind opnieuw met **115200** baud. Geen poort zichtbaar? Controleer de USB-driver volgens de fabrikant.
- Verbindt de bootloader nog niet? Volg de BOOT/RESET-instructie voor jouw exacte board; verbind geen willekeurige pinnen met elkaar.

## Controle en bronnen

Deze handleiding is gecontroleerd tegen de releasebestanden, de fabrikantdocumentatie en de broncode van **ESPConnect v1.1.23**.
De browsertool is van een onafhankelijke ontwikkelaar; we bouwen hiervoor geen eigen flasher.
**Een echte flash-/herstelproef op een E32 V2 is nog niet uitgevoerd.** De stappen zijn dus geen claim dat deze firmware al op hardware werkt.

- [BBQKees: E32 V2 via externe USB-C, zonder extra voeding](https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2)
- [ESPConnect: gebruik en mogelijkheden](https://github.com/thelastoutpostworkshop/ESPConnect/tree/v1.1.23)
- [Uitgebreide technische installatiegids](BBQKEES_E32V2_TEST_RELEASE.md)
- [Hardware, volledige back-up en herstel](BBQKEES_E32V2.md)
