# Codecontrole en optimalisaties — 24 oktober 2026

Status: nieuwe bron voor de volgende gezamenlijke bundel, nog niet geïnstalleerd.
De gecontroleerde live basis blijft HAdev36/E32alpha27; alle zendblokkades blijven.

## Bereik en bewijsgrens

511 projectcodebestanden geïnventariseerd onder firmware, HA, webinterface,
integraties, buildscripts en tests. 260 syntaxiscontroles slagen: echte
Python3.14-AST, Node-checks voor JS/CJS/MJS en inline HTML-scripts, shellsyntax waar
van toepassing. Voor de productiebron afzonderlijk242bestanden:69Python,
10JS,26C++,121headers en16HTML. Dit is geen uitspraak dat elke regel formeel
foutvrij is. De inhoudelijke controle richtte zich op lifecycle/ownership,
annulering, sessie-/metadatalimieten, late antwoorden, decoder-/queuegrenzen,
opslag en begrensde UI-resources. C++-compile/regressie blijft een aparte CI-check.

## Gerepareerd en geoptimaliseerd

| Gebied | Gevonden probleem | Concrete wijziging en bewijs |
| --- | --- | --- |
| HA setup/unwind | Groepsfout vóór bestaande try liet een runtime achter; CancelledError sloeg cleanup over; een nog niet gekoppelde connection werd niet gesloten | Standaard AsyncExitStack registreert de inverse vóór iedere start, ook voor platforms. Acht gerichte echte HA-lifecyclegevallen dekken legacy/shadow, vroege/gedeeltelijke startup, annulering en cleanupfout. Geen nieuwe task/client/evaluator. |
| HA eigenaar | Opruimen van een oude setup keek opnieuw via entry_id en kon vervangende toestand wissen | Opruimen van eigen objecten; state en bench worden met objectidentiteit begrensd. Vier oorspronkelijke gevallen faalden vóór de fix; de nieuwe gevallen slagen. |
| Kamereditor | Een integer met500cijfers in min/max/stap veroorzaakte OverflowError buiten het normale onbruikbaar-pad | Metadata wordt strikt numeriek en eindig gevalideerd, inclusief overflow. Drie nieuwe regressies falen vóór/slagen na; geen metadata verleent actuatietoestemming. |
| Webnavigatie | jQuery.load injecteerde een oud antwoord en voerde scripts uit nadat een andere pagina geselecteerd was | Afzonderlijk bounded ophalen, abort bij navigatie en generatiecontrole vóór HTML-injectie. Echte vertraagde HTTP-reproductie verliest About vóór de fix; desktop/mobiel behouden de gekozen pagina na de fix. HTTP-fout geeft zichtbaar falen. |
| EMS-tabel | Iedere refresh/filter maakte alle zichtbare rijen opnieuw | Maximaal één gecachete rij per bekend veld, hergebruik van rijen, alleen benodigde celtekst bijwerken; verdwenen velden verwijderen uit de cache. Rij-identiteit getest. Geen ongefundeerde milliseconde-/heapwinstclaim. |
| EMS-diagnose | Nieuw lager adres kwam achter bestaande hogere adressen; tekst off kon als boolean Aan verschijnen | Bestaande apparaatnodes op adres ordenen zonder opbouw van de hele pagina. Ongeldige boolean-/waardecombinaties en geldige status zonder waarde worden afgewezen vóór enige snapshotmutatie. Numerieke waarden volgen de gekozen EN/NL-locale. |

## Uitgevoerde controles

178 gerichte tests op de echte Core2026.10.3,40webunittests en18 echte Chromium-
profielen:2navigatie,6EMS-apparaten,2dashboard,4systeemlog en4ketelkeuze. Allemaal
zonder broker-/apparaatopdrachten. Echte E32-build geslaagd. De complete CI op
beide ondersteunde HA-versies en alle boards wordt aan dezelfde commit gekoppeld.

In de bekeken bestaande C++-sessie-/ringbuffer-/tekstbuffer-/decodergrenzen is voor
deze batch geen aanvullende bewezen fout vastgesteld; bestaande checks blijven
in de volledige CI meelopen. Er is geen library-, protocol-, opslag- of
actuatoruitbreiding en geen deployment toegevoegd.

Bewijs: `out/code-review-20261024/`, met oorspronkelijke mislukte proeven,
nieuwe XML/logs, repository-syntaxinventaris en exacte CI-/bronreview.
M2-bronkwalificatie, native kraanreceipt/echo, echte veiligheidssignalen en fysieke
ketel-/uitvalacceptatie blijven open. Codecontrole vervangt die proeven niet.
