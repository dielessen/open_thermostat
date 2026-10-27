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
