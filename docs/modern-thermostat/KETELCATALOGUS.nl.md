# Ketelcatalogus, publieke afbeeldingen en lokale profielen

25 oktober 2026. De modellenkeuze bevat nu 60 selecties: drie bestaande keuzes,
alle 31 BOILER-productgroepen uit de vastgelegde EMS-ESP-database en aanvullende
vermeldingen uit de officiële ketellijst, plus twee specifieke fotokeuzes. Overlappende familienamen zijn bewust
herkenbaar gehouden: een marketingnaam is geen uniek EMS-product-ID. Wildcards
worden niet uitgebreid tot verzonnen uitvoeringen. Dit is geen lijst van alle
ooit geproduceerde EMS-apparaten en geen verklaring dat onze drivers ieder model
al volledig ondersteunen. Warmtepompen en modules hebben aparte keuzegroepen.

Bronnen en exacte commits/hashes staan in
[public/boilers/catalog-v1.json](../../public/boilers/catalog-v1.json).
De [EMS-ESP-ketellijst](https://docs.emsesp.org/Boilers) en productdatabase zijn
verschillende bronnen; er worden geen onbewezen product-ID's aan documentatie-
vermeldingen gekoppeld. De bestaande Ecomline Classic HRC22H-keuze blijft bestaan.

## Geïmplementeerd

- Eén publieke JSON-catalogus in Git, met bron, naam, stabiele sleutel, categorie,
  eventueel upstreamproduct-ID en optionele afbeeldings-URL.
- Een kleine gegenereerde offlineweergave in de bestaande browser-JS en een
  firmware-allowlist uit dezelfde catalogus. De generator controleert exactheid
  in CI. De E32 haalt de catalogus niet tijdens normaal gebruik van internet.
- Alleen de geselecteerde sleutel wordt opgeslagen in de bestaande NVS-namespace;
  expliciete opslag en onafhankelijke readback blijven behouden. Geen losse
  cloudbestanden of nieuwe caches op de ESP.
- Afbeeldingsverwijzingen staan in de publieke catalogus; de originele bestanden
  blijven op de fabrikant-/specialisthost, buiten de ingebedde webassets.
  De browser haalt ze rechtstreeks via HTTPS op, zonder referrer. De E32 maakt
  daarvoor geen TLS-verbinding en slaat geen afbeeldingen op.
- Bij een ontbrekende/offline afbeelding verdwijnt het afbeeldingselement;
  modelnaam, instellingen en lokale bediening blijven beschikbaar.
- Nieuwe vermeldingen tonen in EN/NL dat OpenThermostat-ondersteuning nog niet
  is gecontroleerd. Kiezen verandert geen EMS-driver, busadres, protocol,
  berichtfilter, aanvoertemperatuurgrens of zendbevoegdheid. Read-all blijft
  onafhankelijk van de gekozen presentatienaam.

Vier oorspronkelijke modelafbeeldingen zijn gecontroleerd en gekoppeld aan vijf
selecties: Nefit TrendLine II en Buderus GB162 van de fabrikant; ProLine HRC en
SmartLine uit de modeltabel van BBQKees. ProLine en SmartLine zijn productrenders,
geen fotografische opname. De bronlink staat bij de afbeelding in de UI; exact
model/jaargang/vermogen wordt niet afgeleid uit een familiefoto.

De generieke Ecomline-illustratie wordt niet meer geselecteerd. Het bestand blijft
alleen als bestaande projectbron en geïsoleerde browsertestfixture bewaard.
Voor EcomLine Classic HRC22H is nog geen originele, verifieerbare productafbeelding
gevonden: de officiële oude archiefhost resolveert hier niet; de leveranciers-
vermelding is gevonden maar de bijbehorende foto kon niet worden geverifieerd.
Er worden geen afbeeldingen van een ander model of particuliere advertenties
voor in de plaats gezet. Overige onzekere familiegroepen blijven zonder foto.

## Hostingbesluit

GitHub blijft de bron van waarheid: catalogus en profielen krijgen schema- en
versienummers en kunnen samen met een release worden beoordeeld. De eerste
publieke catalogus bevat originele HTTPS-afbeeldingsverwijzingen en vastgelegde
bronpagina's, uitgever, afgebeeld model, controlesom, datum en variantbeperking.
De browser laadt de afbeelding direct van de oorspronkelijke publieke host.
Er zijn geen nieuwe fabrikant- of derdenafbeeldingen naar de repository gekopieerd;
herpublicatierechten worden niet geclaimd. Geen nieuwe account/cloud nodig.

Bij een grotere mediacollectie kan alleen de afbeeldingsbasis naar een eigen
statische host/CDN verhuizen. GitHub Pages is een mogelijke vervolgstap, maar
is niet ingeschakeld door deze wijziging. GitHub documenteert onder meer een
sitegrens van 1GB en een zachte bandbreedtegrens van 100GB/maand:
[GitHub Pages-limieten](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
Een database, dynamische API of andere cloudprovider is hiervoor nu niet nodig.

Het bestaande [Ecomline-waarnemingsprofiel](boiler-profiles/nefit-ecomline-classic-hrc-22h.json)
blijft behouden in de documentatie. Dit bevat gedateerde installatieobservaties,
geen generiek vrijgegeven zendprofiel; zulke installatiegegevens worden niet
stilzwijgend als universele eigenschappen in de publieke catalogus opgenomen.

## Werkelijke regelprofielen — ontwerp, nog geen downloader of activatie

Presentatiemetadata en regelprofielen moeten afzonderlijk blijven. Een toekomstige
profielrelease kan per familie een klein JSON-bestand onder `public/boilers/profiles/`
leveren met profiel-ID, schema, versie, expliciete protocolvariant, bewezen
identificatiekenmerken, herkomst en onderbouwde capaciteiten. Ontbrekende waarden
blijven onbekend; EMS-ESP-ondersteuning is geen lokale activeringsvrijgave.

De gekozen, beoordeelde profielversie moet lokaal beschikbaar blijven voor
standalonebedrijf. Een toekomstige import downloadt uitsluitend op expliciet
verzoek, begrensd op grootte en schema, controleert een vastgelegde hash en
compatibiliteit en bewaart pas na volledige validatie atomair naast de vorige
werkende versie. Hashes uit dezelfde onbeveiligde bron vormen geen aparte
handtekening: de vertrouwde herkomst/pinning moet onderdeel van de import zijn.
Netwerkverlies, afgebroken download of catalogusverandering mogen het actieve
profiel niet wijzigen of verwijderen. Geen automatische wisseling bij een
ander gedetecteerd model; toon een verschil en vereis herbeoordeling.

Nog te bouwen: profielschema voor concrete protocol-/hardwarevarianten,
begrensde import en opslag met readback/rollback, versiepinning en migratie,
EN/NL-beheer in HA/E32 en fysieke kwalificatie van ontvangst, opdrachten en stop.
Er zijn nu geen nieuwe functionele regelprofielen of zendopdrachten geactiveerd.

## Controle en levering

Native NVS-foutproeven en opslag/readback van alle catalogussleutels, exacte
catalogusgeneratie en bestaande browserproeven met publieke afbeeldingen,
ontbrekende afbeelding en nieuw model worden uitgevoerd vóór oplevering.
Dit is bronwerk voor de volgende release; geen firmware-upload of HA-wijziging.
