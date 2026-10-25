# Oorspronkelijke Zigbee-rapporten — onderdeel van dezelfde bèta

Dit optionele bronpakket hoort bij dezelfde broncommit en HA-versie als de
integratie. Het bevat de twee bestaande ontvangstextensies voor WSDCGQ11LM en
TV02, plus een hulpmiddel om privé installatiepins gecontroleerd te behouden.
De extensies maken geen extra MQTT-client en versturen geen apparaatopdrachten.
Alle meet-/actuatorkwalificaties blijven onwaar. Dit is geen zelfstandige
verwarmingsregeling of bewijs van fysieke geschiktheid.

Gebruik het gewone `OpenThermostat-HA-….zip` voor de HA-integratie. Alleen een
installatie die deze oorspronkelijke Z2M-rapporten gebruikt, heeft daarnaast dit
companionpakket nodig. Het wordt niet automatisch door HA geïnstalleerd. Kopieer
deze bestanden niet in `custom_components`. Bluetoothontvangst op E32 gebruikt
dit pakket niet.

## Bestaande installatie bijwerken

De bestaande HA-specialist voert een uiteindelijke installatie uit met verse
back-up en afzonderlijke nacontrole. Tijdens de huidige releasevoorbereiding
wordt niets geïnstalleerd of herstart.

1. Controleer pakketchecksums en de gelijke broncommit in beide `SOURCE.json`-
   bestanden. Lees de werkelijke bestaande extensies via de toegestane route;
   bewaar hun hashes en privé pins in de beperkte back-up.
2. Haal de **exacte vorige openbare templates** uit het bijbehorende geverifieerde
   bronpakket. Een willekeurige oude versie volstaat niet. De publieke nieuwe
   templates hebben bewust lege `DEVICE_BINDINGS`; overschrijven daarmee zou
   de installatiebindingen verliezen.
3. Gebruik `tools/prepare_original_report_pins.py` uitsluitend voor lokale
   voorbereiding in de bestaande Linux-beheerwerkruimte. Geef vorige template, bestaande privé bron, nieuwe template,
   profiel en alle drie onafhankelijk gecontroleerde SHA256-hashes op. Het
   hulpmiddel accepteert alleen de bekende JSON-pinvelden, weigert gewijzigde
   code buiten die pins en voert geen JavaScript uit. Het schrijft één nieuw
   bestand met modus 0600 en weigert een bestaand uitvoerbestand. De receipt
   bevat hashes en aantallen, geen pins. Onbekende syntaxis/bronverschillen
   vereisen beoordeling; er is geen automatische default, herstel of wisactie.
4. Vergelijk de voorbereide bron met de nieuwe template: alleen de gevalideerde
   pins mogen afwijken. Vergelijk ook de bewaarde pins met de back-up.
5. Pas de bestaande goedgekeurde installatie-/herlaadroute één keer toe, met een
   eindige observatietermijn. Bij een onzekere uitkomst geen blinde herhaling.
   Controleer daarna bronhash, behouden pins, native laadmelding en oorspronkelijke
   ontvangst. Alleen bestandsaanwezigheid bewijst geen runtime-load. Een ontbrekend
   rapport bewijst geen defect en een doelwaarde bewijst geen causale opdracht-ACK.

Een nieuwe installatie zonder expliciet beoordeelde bindings laat de templates
leeg. Er wordt geen apparaat gezocht of automatisch gekozen. Geleverde software,
installatieacceptatie en fysieke meet-/kraanacceptatie blijven afzonderlijk.

## English

This optional archive accompanies the same HA beta and source commit. It carries
the two existing receive-only Zigbee2MQTT original-report extensions and an offline
private-pin preparation tool. Install the normal HA ZIP separately; this archive
is not a custom component and does not install itself. Public templates contain
no device bindings, credentials or live HA data. No device command, heating grant,
new MQTT client or recurring scheduler is introduced.

The existing HA specialist performs the final update with a fresh backup and
independent checks. Preserve and verify private bindings. The Linux/POSIX preparation tool
requires all three independently checked input hashes and the exact previous
public template; only validated JSON pins may differ. It never executes JavaScript,
changes inputs or installs anything, creates only a new private 0600 output, and
prints only hashes/counts. Unknown code or syntax is rejected. Verify the staged
source and preserved pins before the existing controlled install/reload route,
then check exact installed bytes, native loading and original reception. Neither
a file hash nor a matching target proves runtime readiness or causal command
confirmation. No interim deployment is performed during beta preparation.
