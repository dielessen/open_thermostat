# Dynamische HA-kamerconfiguratie

## Productgrens

Normale bediening en configuratie hoort in de integratie: bestaande entiteiten
selecteren, kamers toevoegen/wijzigen/verwijderen en instellingen bewaren. Geen
verplichte YAML, helpers/automations of wijzigingen aan bronintegraties als normale
inrichtingsroute. HA beheert gebruikersconfiguratie; E32 behoudt de regelkern.
De oude optionele Schedule-helperbinding blijft compatibel, maar is geen bewijs
van een helpervrije eigen programma-editor: die ontbreekt nog.

## In deze wijziging

- Native kamersubentry toont minimum/maximumdoeltemperatuur, standaard5–35°C.
- Grenzen zijn persistent; oude kamers behouden defaults en identiteit.
- Basisdoel moet binnen de kamergrenzen liggen; minimum moet lager zijn dan maximum.
- Climate toont dezelfde grenzen; ongeldige handmatige doelen of schema-export
  worden vóór transport geweigerd, niet stilzwijgend begrensd.
- Optionele setpoint-/schemakeuzes gebruiken suggested_value, niet een schema-
  default die een bewust gewiste keuze opnieuw invoegt.
- Geen nieuwe firmware-wirevelden, E32-veiligheidslimiet, regelkernwijziging of
  versoepeling van bronversheid. Een mappingwijziging volgt normale admission.

## Softwarebewijs en belangrijke testles

HA2026.10.2/Python3.14.8:69gerichte native regressies geslaagd bij grenzenpatch;
na live gevonden selectorprobleem33gerichte regressies geslaagd, deels overlappend.
Deze aantallen niet optellen als102unieke tests. Zie
`ha/tests_native/test_v1_room_target_bounds.py` en
`ha/tests_native/test_v1_optional_clear_schema.py`.

Flow-callbacktests alleen zijn onvoldoende: de native manager valideert eerst het
formschema en vult defaults in. De optionele-clearregressie moet deze echte
schemastap vóór de callback uitvoeren. Ook echte HAStoreflush/reload, onveranderde
IDs, invalid-input-immutability en core-registryverwijdering worden getest.

20oktober geïsoleerde native APIproef: kamercreate, bron-/TRVwissel, grenswijziging
en ongeldige-grenzenrollback geslaagd; leegmaken vond de bovenstaande echte bug.
Daarna precies één runtimebestand gerepareerd, officiële check_config exit0 en
alleen bestaande testHA herstart. Native postrestart/clear/deleteacceptatie9/9PASS.
Vervolgens echte hostChromium-GUIcreate/edit/sensor+TRVwissel/grensfout/optional-
clear/delete10/10softwarechecksPASS, met screenshots, heropende formwaarden en
afscheiden native REST/WSreadbacks. Gerichte opruiming van eigen5bronfixtures
en aparte native eindreadback zijn geslaagd (nulzones/MQTTsubentries, runtimeuit). APIflows alleen waren geen GUIbewijs; de latere zichtbare bediening
is apart uitgevoerd. MQTTfixtureentities bewijzen geen fysieke meetversheid of
ondersteund actuatorprofiel.

## Uitrolgrens

Alleen bestaande geïsoleerde testHA is aangepast, met privésnapshot en bronhashes.
Productie/E32/broker/bronopties/actuatie niet gewijzigd. Voor productie blijven
review, passend backup/rollback en de daadwerkelijke native/GUIacceptatie nodig.
Volledige shadowketen/fysieke proeven, helpervrije programma-editor en gekwalificeerde
fysieke setpointprofielen zijn aparte open punten; deze wijziging voltooit die niet.
