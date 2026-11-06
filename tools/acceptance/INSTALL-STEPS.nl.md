# Installatie met vastlegging: stappen voor Mark

Deze stappen gelden voor de release in `install-config.json` (nu E32 **v1.0.0-e32v2** met HA
**1.0.0**, vanaf rc.5 en 1.0.0rc7). De opdrachten staan in [README.md](README.md).

**Wat er gebeurt:** eerst gaat Home Assistant naar de nieuwe integratie, via HACS. Daarna gaat de E32 naar de
nieuwe firmware, via Home Assistant. Tussendoor maak ik metingen; die vormen samen het acceptatiebewijs.

**Tijd:** ongeveer 45 minuten. Na de E32-update verwarmt het huis zo'n 10 tot 15 minuten niet, tot je stap 7
hebt gedaan. Daarin houdt de E32 alleen de vorstbeveiliging aan. Dat hoort zo.

**Steeds hetzelfde:**
- Bij **[Claude]** maak ik een meting. Jij wacht tot ik "klaar" zeg.
- Moet je een wachtwoord typen, dan opent er een eigen PowerShell-venster op de laptop. Typ het daar; je ziet
  het niet terwijl je typt. Ik zie en bewaar het nooit. Sluit het venster met Enter als het "Klaar" zegt.
- Zolang we bezig zijn: laat de E32-webpagina dicht en verander niets in de OpenThermostat-opties. De E32 kan
  maar 4 aanmeldingen tegelijk aan, en Home Assistant heeft er zelf ook een nodig.
- Druk nooit twee keer op **Installeren**.
- Het Home Assistant-token staat in `tools/acceptance/ha-token.txt` (alleen op de laptop, niet in git).

---

## 1. Vooraf [Claude]

Ik controleer of de E32-release en de HA-release gepubliceerd zijn en of de tag-CI groen is. Daarna maak ik een
**nulmeting van Home Assistant**, nog zonder de E32 aan te raken (`capture_preinstall.py --stage ha-baseline`).
Gaat er iets mis, dan stoppen we hier en verandert er niets.

**Jij:** maak een back-up van HA. Ga naar Instellingen → Systeem → Back-ups → **Nu back-up maken**.

## 2. Home Assistant naar de nieuwe integratie via HACS (jij)

1. Ga naar **HACS** → **OpenThermostat**.
2. Kies de drie puntjes → **Download**.
3. Klap **Need a different version?** open en kies de versie uit `install-config.json` (nu **1.0.0**).
   Druk op **Download**.
4. Verwijder de integratie niet. Er hoeft niets weg: HACS schrijft over dezelfde map heen.
5. Start Home Assistant opnieuw. Gebruik de melding "Opnieuw opstarten vereist", of ga naar Instellingen →
   Systeem → Opnieuw opstarten.

**Wat je moet zien:**
- Bij Instellingen → Apparaten en diensten staat **OpenThermostat precies één keer**.
- Je apparaten en ruimtes zijn hetzelfde als eerst.

**Gaat het mis?** Bijvoorbeeld een tweede OpenThermostat, een foutmelding of een integratie die niet laadt.
Stop dan en roep mij. Druk nog niet op Installeren bij de E32. De verwarming loopt gewoon door op de huidige
firmware.

## 3. Meting vóór de update [Claude]

Ik controleer vier dingen:
- de overstap naar de nieuwe integratie heeft je ene OpenThermostat-item gehouden;
- er zijn geen dubbele of losse entiteiten bijgekomen;
- Home Assistant biedt precies de geplande E32-release aan;
- `firmware.bin` en `e32v2-update.json` van GitHub passen bij elkaar (hash, grootte en versie).

Daarna maak ik een back-up van alle E32-instellingen. Dat kost één aanmelding op de E32, en daarna meld ik weer
af (`capture_preinstall.py --stage e32`).

- Zegt de meting "HA biedt de release nog niet aan"? Ga dan naar Instellingen → **Updates** → de drie puntjes →
  **Controleren op updates**. Daarna meet ik opnieuw.
- Is het E32-wachtwoord nog het fabriekswachtwoord, dan hoef je niets te typen. Anders vraagt het venster om je
  E32-wachtwoord.
- Meldt de meting "niet installeren" (afsluitcode 2), dan druk je niet op Installeren. Ik zeg wat er mis is.

## 4. De E32 bijwerken: één keer Installeren (jij)

1. Ga naar Instellingen → Apparaten en diensten → Apparaten → **Woonkamer E32** → **Firmware**.
2. Controleer dat er de geplande versie staat (nu **v1.0.0-e32v2**).
3. Druk **één keer** op **Installeren**. Zeg me hoe laat het is.
4. Wacht. Home Assistant downloadt de firmware, controleert hem, zet hem op de E32 en wacht op de herstart. Dat
   duurt meestal 1,5 tot 3 minuten. Druk in die tijd nergens op.

**Wat je moet zien:**
- De Firmware-entiteit zegt "Up-to-date" met de nieuwe versie.
- E32-waarden zijn even "niet beschikbaar" en komen dan terug.
- Bij Instellingen → Systeem → **Reparaties** verschijnen:
  - **"Bevestig opnieuw dat de E32 de ketel mag regelen"**;
  - als de E32 nog het fabriekswachtwoord heeft: **"E32 gebruikt nog het standaardwachtwoord"**.

**Gaat het mis?**
- Mislukt de update, dan zet Home Assistant niets verkeerds op de E32. Druk dan **niet opnieuw** en roep mij.
- Is de E32 na 10 minuten nog niet terug? Raak dan niets aan en roep mij. Start de nieuwe firmware niet goed
  op, dan valt de E32 terug op de vorige firmware.

## 5. Meting 1, meteen na de update [Claude]

Doe nog niets met de Reparaties. Deze meting laat zien dat de E32 na de herstart veilig wacht op jouw
bevestiging. Het venster vraagt om het **MQTT-wachtwoord**. Dat is het account dat Home Assistant voor de
broker gebruikt. Duurt ongeveer 3 minuten (`capture_post.py`).

## 6. Nieuw E32-wachtwoord (jij, alleen als de melding er staat)

1. Ga naar Reparaties → **"E32 gebruikt nog het standaardwachtwoord"**.
2. Kies een nieuw wachtwoord van minstens 8 tekens. Schrijf het op: je typt het straks in mijn venster.
3. Druk op **Verzenden**.

**Wat je moet zien:** de melding verdwijnt. Met het fabriekswachtwoord weigert de E32 elke wijziging, behalve het
teruggeven aan de thermostaat. Daarom moet deze stap vóór stap 7.

## 7. De regeling opnieuw bevestigen (jij)

**Alleen als de tado nog steeds van de ketel los is.** Sluit nooit twee thermostaten tegelijk aan.

1. Ga naar Reparaties → **"Bevestig opnieuw dat de E32 de ketel mag regelen"** → **Bevestigen**.
   Lukt dat niet? Dan kan het ook op de E32-pagina: **Ruimtes** → **Actieve regeling**. Meld je daarna weer af
   en sluit het tabblad.

**Wat je moet zien:**
- De melding verdwijnt.
- Binnen ongeveer 2 minuten regelt de E32 weer actief. Vraagt de woonkamer om warmte, dan gaat de ketel weer
  stoken.

## 8. Meting 2, minstens 11 minuten na de herstart [Claude]

Ik laat zien:
- dat de E32 weer regelt;
- dat hij stabiel draait en dat alle metingen bij dezelfde opstart horen (geen herstart ertussen);
- dat al je instellingen, programma's en sensoren hetzelfde zijn als eerst.

Het venster vraagt om je **nieuwe E32-wachtwoord** en het MQTT-wachtwoord. Duurt ongeveer 3 minuten.

## 9. Onafhankelijke controle [Claude]

Dit is een apart programma dat alles nog één keer zelf nakijkt (`capture_independent.py`). Het venster vraagt
opnieuw om het E32-wachtwoord. Duurt 1 minuut.

## 10. Klaar [Claude]

Ik maak het bewijsstuk (de acceptatiebon, `write_receipt.py`) en vertel je of alles PASS is. Bij PASS zet ik het in
de poortcontrole en ververs ik de inventaris. Er wordt niets gepusht zonder jouw woord.

---

## Heb je de meting vooraf gemist?

Dan kan het bewijs achteraf alleen onvolledig zijn (`INCOMPLETE`): zie "An install without a pre-install capture"
in [README.md](README.md). Een HA-dagback-up van vóór de installatie en de recorder-geschiedenis (ongeveer 10 dagen)
kunnen een deel vervangen. Voor v1.0.0 bestaat geen uitzondering: daar moet de installatie mét vastlegging zijn.

## Als er iets misgaat: de teruggeefknop

**Gewoon, als de E32-pagina werkt** (zie ook OVERSCHAKELING.nl.md §8.1):

1. Open het adres van de E32 (zie `install-config.json`) en meld je aan.
2. Ga naar **Ruimtes** → **Actieve regeling** → **Regeling teruggeven aan mijn thermostaat**. Dat werkt ook met
   het fabriekswachtwoord.
3. Wacht tot er schaduwmodus staat. Dat duurt hooguit ongeveer 70 seconden.
4. Zet de ketel uit met de hoofdschakelaar.
5. Sluit de tado-draden ("TADO") weer aan zoals op de foto.
6. Zet de ketel weer aan.

**In nood:** de pagina werkt niet of de ketel stookt ongecontroleerd (zie §8.2):

1. Zet de ketel uit.
2. Haal de stroom van de E32.
3. Sluit de tado weer aan.
4. Zet de ketel aan.

Bevestig in Home Assistant daarna niets meer zolang de tado aangesloten is.
