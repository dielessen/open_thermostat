# Laatste verzendcontrole — aanvullende broncorrectie

25 oktober 2026. Vervolg op de gepubliceerde HA45/alpha32-bron `3f12d8b` en
het installatieverslag op `224950f`. Dit is werk voor de volgende grotere bundel;
geen nieuwe tag, firmware-upload, HA-installatie of fysieke opdracht.

## Bevestigde afwijkingen

`ActuatorChannels::beforeHandoff()` controleerde beschikbaarheid en tijd zonder
eigen herintredebewaking. De algemene operatiebewaking kan hier niet rechtstreeks
worden gebruikt: de normale zendcallback roept deze grens al tijdens een lopende
operatie aan.

Drie begrensde hostreproducties bevestigen dat de oude code:

- een geneste eindcontrole vanuit beschikbaarheid toeliet;
- vanuit beschikbaarheid een extra kanaal kon aanmaken;
- een geneste eindcontrole vanuit de klok toeliet.

De testcallbacks roepen maximaal één keer terug. De proef gebruikt geen
stackoverflow om een fout aan te tonen. Alle drie gevallen falen met concrete
asserties op de oude productieheader. De positieve proef voor de normale
zendcallback en een verstreken deadline slaagt ook op die oude code.

Een aanvullende review van de eerste broncorrectie `b482de4` toont dezelfde
herintrede ook vanuit de normale kanaaltoelating: beschikbaarheid of klok kan
vóór een reeds lopende eindcontrole die eindcontrole opnieuw binnengaan. Twee
extra begrensde proeven falen op `b482de4`, met onterecht toegelaten kanalen.
Daarom worden beschikbaarheid en klok ook elk op hun eigen callbackgrens bewaakt.

## Correctie

De eindcontrole heeft nu een eigen bewaakte scope. Geneste aanroep trekt alle
bestaande kanaaleigenaren blijvend in en retourneert onbeschikbaar. Een exception
verlaat deze boolean-grens eveneens als onbeschikbaar. De beschikbaarheidsfunctie
loopt onder de bestaande callbackbewaking, zodat zij geen extra kanaal kan
toelaten. De scope wordt ook bij vroege return en exceptions vrijgegeven.

Geen nieuwe client, verbinding, wachtrij, retry, timer of thread. De bestaande
normale zendcallback mag nog steeds de eindcontrole uitvoeren; een verlopen
deadline wordt geweigerd zonder een later venster te creëren.

## Verificatie

- 773 native kerngevallen geslaagd, inclusief zes nieuwe kanaalgevallen.
- 77 van die kerngevallen slagen afzonderlijk onder ASan/UBSan met lekdetectie
  en onder strikte debugiteratoren; dit zijn geen extra unieke gevallen.
- 5 aanvullende lokale socketadaptergevallen slagen onder ASan/UBSan. De nieuwe
  socketproef schrijft met de oude header aantoonbaar één byte door de ongeldige
  herintrede heen; met de correctie blijft dezelfde socket leeg (`EAGAIN`).
- E32-firmwarebuild geslaagd: RAM 75.520/327.680 bytes, flash
  2.599.709/3.670.016 bytes. Dit is een lokale compilatiecontrole, geen nieuw
  gepubliceerd pakket of runtime-/hardwareproef.
- Release-inventaris: alle 23 onderdelen, 279 bronverwijzingen en 31 eisen behouden.

De bestaande CI voert de extra socketproef voortaan ook uit, met dezelfde
cJSON-header/objectafhankelijkheid als de kanaalkern. Geen nieuwe CI-job of route.
De reproduceerbare voor-/na-proeven en volledige logs staan in
`out/large-beta-handoff-20261025/`. De exacte publieke CI-uitkomst wordt per broncommit bewaard in dat bewijsdossier;
oude tags en downloads blijven ongewijzigd.

## Open releasegrens

De product-SOURCE-fabriek blijft gesloten. Geschikte oorspronkelijke
kamermetingen, causale kraanecho, fysieke stop-/uitvalproeven en het eerdere
updaterherstel blijven open. De correctie verklaart geen watchdogreset of
ketelpendelen en bewijst geen fysieke kraansluiting. HA45 en E32alpha31 blijven
de laatst onafhankelijk gecontroleerde runtimebasis.

**English:** The final handoff predicate now rejects callback recursion and
prevents channel admission from availability callbacks. Five bounded channel regressions
fail before the respective fixes; normal handoff remains possible. This is an unpublished
source correction with no runtime or physical commands. Product-source and
physical qualification remain open.
