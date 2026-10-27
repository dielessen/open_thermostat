# Grote ontwikkelbundel — opdracht 27 oktober

De eigenaar vraagt doorlopend werken aan één zo compleet mogelijke release,
zonder onderbrekende routinevragen. De echte ketelproef en installatieherstel
zijn naar morgen verplaatst. Deze opdracht staat brede software-implementatie
uit het bestaande plan toe, ook waar de eerdere volgorde nieuwe F9/F10/P2-
voorbereiding vóór M2 uitstelde. Fysieke kwalificatie wordt niet vooruit afgetekend.

Bronversies: E32 beta.6 en HA0.4.0b4. Beta.5 blijft gepubliceerd maar niet
geïnstalleerd; de acceptatiepoort blijft beta.4 accepted / beta.5 pending.
De later afzonderlijk toegestane eenmalige herstelherstart is uitgevoerd; ook
de tweede native cataloguscontrole faalde vóór HTTP. Geen installatie verstuurd.
Geen verdere herstart, firmware-/HA-installatie, ketel- of kraanopdracht tijdens
dit ontwikkelwerk. Snelheid van de E32-webinterface en de later expliciet
gevraagde vereenvoudiging van Keteltest hebben nu prioriteit: één tabel per
ontvangen apparaat, één gedeelde momentopname en een duidelijke proefvolgorde.
De modelcatalogus blijft als bronreferentie bewaard, niet als tweede waardenlijst.

## Uitvoeringsbundels

1. Kamercontext: meerdere raam-/deurcontacten, externe doelbron, comfortstanden;
   normale editor, bewaren/verwijderen, identiteit, actualiteit, fail-safe hervatten,
   runtime/wire en duidelijke status met betekenisvolle regressies.
2. Centrale instellingen en zones: buitenbron/weer, emitter-/regelprofielen,
   meerdere kranen en schaalbare begrensde planning/configuratie.
3. Ketel: volledige lees-/schrijfcatalogus verbinden met werkelijk ondersteunde
   model-/telegramhandlers; guarded bediening en terugmelding zonder live TX.
4. Sensoren/actuatoren en lokale bediening: oorspronkelijke rapportketen,
   Bluetooth-/standalone-uitbreidingen volgens de bestaande bronplannen.
5. Metrics, historie, comfort en leren: bestaande implementaties aansluiten,
   opslag/herstel/rollback en gebruikersstatus; geen verzonnen meet- of leerwinst.
6. Gezamenlijke regressie/build/pakketcontrole, Engelse hoofd-/releasetekst en
   opslagopschoning. Eén reviewbare kandidaat, geen tag per deelreparatie.

De 31 producteisen en 14 fysieke/productchecks uit WORKBOARD blijven behouden.
Elke bundel krijgt concrete implementatie- en testbewijzen; ontbrekend fysiek
bewijs blijft afzonderlijk open. Geen nieuwe externe dienst of langlopende watcher.

## Ontwikkelvoortgang

- Performance en Keteltest: gecomprimeerde/cachebare webbestanden, luie modules,
  één gedeelde telemetrieaanvraag, herbruikbaar PSRAM en een proefvolgorde met één
  korte opstellingsverklaring. Checkpoint `e1376f5` slaagt voor alle negen
  GitHub-validatiejobs. Niet geïnstalleerd; snelheidswinst op het apparaat nog meten.
- Raam/deur: maximaal acht expliciet gekozen contacten per kamer, bewaren en
  verwijderen in normale editor/wizard, instelbare reactietijden, ouderdom en
  status. Ook actieve native plannen gebruiken dezelfde save/reload/readbackroute.
  De contactfunctie kan gewone kamervraag alleen beperken en activeert geen
  extra comfort- of vorststand. C++-beleid, UI en oorspronkelijke leeftijden worden
  met gesimuleerde transporten en echte native HA-/C++-code getoetst.
- Extra kamerdoelbron: ingebouwde HA-temperatuurhelper met uitsluitend nieuwe
  rechtstreekse gebruikersacties, eindige override, begrensde wachtrij, eigen
  firmwarecapability en native save/readback. Bestaande waarden/automatiseringen
  worden niet afgespeeld; fysieke wandbediening blijft ongekwalificeerd.
- Nog softwarematig uit te bouwen: fysieke externe kamerdoelbron met echoherkenning,
  centrale instellingen en schaalbare
  zones/kranen, verdere modelwriters en de overige bron-/leer-/standaloneketens.
  Oorspronkelijke fysieke bronkwalificatie en hardwareproeven blijven apart.
- Comfort/aanwezigheid: normale editor en wizard, actieve native save/readback,
  oorspronkelijke HA-persoonsmeldingen met behoud van trackerouderdom en
  zichtbare onbekende/verlopen status. De native vorstpolicy blijft5°C; geen
  nieuwe fysieke kwalificatie of automatische bronpolling.
- Vakantie: normale lokale einddatumflow over bestaande comfortservice, strikte
  HA-tijdzone en zomertijdkeuze, pre/post-dispatch kamerscope en zichtbare
  onbevestigde uitkomst zonder automatische herhaling. Geen blijvende
  programmawijziging of herstel van oude sessiekeuzes na herstart/herverbinding.

- Netwerkperformance: gewone MQTT-writes hebben één totale100ms-grens; DNS
  wordt asynchroon afgehandeld in de bestaande netwerktaak, met vaste opslag,
  oorspronkelijke deadline en isolatie van late callbacks na transportvervanging.
  Ook TCP verbinden verloopt nu in stappen binnen dezelfde drie seconden;
  MQTT-CONNACK-/bytelezen blijft apart reviewwerk. Geen meting/installatie op E32.

- Batterijdiagnose: normale kamereditor groepeert opgeslagen sensor/kranen per
  native HA-apparaat en toont gecachete procent-/lage-batterijmeldingen met
  oorspronkelijke HA-tijd en ouderdom. Laden of bevestigde kamerbewaring geeft een nieuwe momentopname;
  geen extra entiteiten, subscriptions of fysieke meetkwalificatie.

- Kameruitleg op E32: doelbron, gekozen comfortstand en de door de regelaar
  gemelde tijdelijke duur/vakantie-eindtijd onder de bestaande kamerdetails.
  Raam-/deurpauzes en aanwezigheid krijgen eigen leesbare redenen. Dezelfde
  actuele momentopname wordt hergebruikt; geen nieuwe collector of aftelklok.

- Dashboardlevensduur: verborgen pagina annuleert de actieve GET; terugkeren
  leest één verse status. Gepensioneerde/verlopen antwoordbodies mogen geen
  nieuwe status of pagina vervangen. Echte time-outs houden hun foutmelding
  en de gewone tiensecondenherhaling. Geen apparaatopdrachten.

- Bluetoothlevensduur: één zichtbare statuspoll, geen polling tijdens
  configuratie laden/bewaren, direct hervatten zonder concepten/sleutel/focus
  te vervangen. Verlaten wist de invoersleutel. Ingediende save/scan behoudt
  de oorspronkelijke deadline; geen herhaling of late readback door de oude
  pagina. Leesfoutherstel en onbevestigde schrijfacties houden eigen status.

- Statusantwoordbuffer: dashboard en keteltelemetrie delen dezelfde vaste64KiB
  PSRAM-opslag op de synchrone HTTP-eigenaar. De hoofdbody groeit niet meer op
  de interne heap; geen tweede buffer, waardencache of schemawijziging. Eerste
  dashboardgebruik reserveert de PSRAM. Onbeschikbaar/te groot geeft volledige503.

- Syslog-hoofdlus: uitgeschakeld/offline vraagt de zender geen klok of volledige
  instellingen meer op. De bereikbaarheid wordt alleen bij overgang onder de
  wachtrijlock verwerkt. Lokale/seriële filters, MARK, verliesregistratie en de
  bestaande begrensde UDP-uitvoer blijven intact.300.000 inactieve polls en echte
  loopback/NVS/loggerproeven slagen; geen meting op de E32.

- Browsersessie: oorspronkelijke tiensecondenlimiet dekt ook antwoordbody en
  bewijsvalidatie. Trage/late bodies mogen geen wachtende writes vrijgeven;
  een volgende aanvraag herstelt zonder herhaling. Echte gestreamde HTTP-body
  en vervangende late-body/headersfixtures dekken deze grens in EN/NL.

- WiFi-setup: dezelfde vijfseconden-deadline dekt nu status-, scan- en
  afrondings-JSON. Een stilgevallen body blokkeert de bestaande uitleeslus niet
  meer; bevestigde afronding wordt uit actuele status hervat. Tekstbevestigingen
  voor verbinden/scannen en de bestaande navigatiedeadline blijven behouden.
  Alle WiFi-/AP-gedragingen in deze proeven zijn gesimuleerd.

- Debuginstellingen: uitklapbare luie lijst, één aanvraag minder bij gewoon
  instellingenbezoek, complete expliciet gelezen booleanflags en veilige eigen
  checkbox-ID's. Geen herstartvraag voor reeds direct werkende filters. Reads
  hebben vijfseconden-deadline en eigen paneellevensduur; ingediende save blijft
  begrensd geldig na navigatie, zonder herhaling of late paginawijziging.
