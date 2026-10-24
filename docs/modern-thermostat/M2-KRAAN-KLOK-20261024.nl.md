# M2/B05 — kloklevensduur van de kraanadapter

24 oktober 2026. Broncorrectie voor de volgende gezamenlijke bundel; niet
geïnstalleerd. De productie blijft HA39/E32alpha28. Geen fysieke opdracht,
bronwijziging, MQTT-actie of updaterproef uitgevoerd.

## Wat is opgelost in de bron?

De bestaande Profile-C-adapter controleerde deadlines met losse kloklezingen.
Bij een teruggaande klok konden oude budgetten langer gelden; NaN kon een
vergelijking omzeilen. De adapter bewaart nu de laatst waargenomen monotone tijd.
Een teruggaande, negatieve, niet-eindige of ongeldige klok trekt deze eigenaar
blijvend in. Ook overgrote integers worden gecontroleerd afgewezen.

De controle geldt bij nieuwe opdrachten, na wachten op de bestaande lock,
na elke autorisatiecallback (ook bij weigering of exception), direct vóór
verzenden en na de geawaitte HA-service. Een herstelde klok, nieuwe doelwaarde
of herstelde callback maakt deze adapter niet opnieuw bruikbaar. Herbouw blijft
onderdeel van afzonderlijk beoordeelde eigenaar-/bronkwalificatie.

Bij klokverlies vóór dispatch wordt niets verzonden. Tijdens een al verzonden
opdracht wordt de fysieke uitkomst unknown en blijven nieuwe opdrachten
geblokkeerd. Een historische exacte duplicate mag het oorspronkelijke
service-acceptatiereceipt lezen; dat veroorzaakt geen IO en blijft zonder
bevestigde kraanontvangst, readiness of regelkwalificatie.

## Bewijs en grenzen

14 nieuwe regressiegevallen: op de oude bron falen er 13; één bestaande
inflight-inf-afwijzing was al correct. Na reparatie slagen alle 141 gerichte
gevallen op echte Core 2026.10.2 en 2026.10.3, inclusief bestaande intake-,
levensduur-, binding-, modus- en capabilityproeven. De tests gebruiken echte
HA-registers/services met synthetische handlers en een uitsluitend lokale
klokproxy; eventloopklok, netwerk en hardware worden niet gewijzigd.

Bewijs: `out/m2-actuator-clock-20261024/`. De module blijft standaard gesloten;
er komt geen nieuwe instelling, taak, subscriber, opslag of fysieke vrijgave bij.
Dit bouwt geen nieuwe FW→HA-ontvangstroute, causale kraanecho of exclusieve
apparaatregie. Die B05/M2-voorwaarden en de E32-herstelblokkade blijven open.
