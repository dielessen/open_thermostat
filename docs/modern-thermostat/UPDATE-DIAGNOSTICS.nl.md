# Updatediagnose na een herstart

Status: voorbereid voor de volgende gezamenlijke release; nog niet geïnstalleerd.
De gecontroleerde apparaten blijven E32 alpha26 en HA dev34. De onverklaarde
HTTPS-poging op alpha26 wordt hiermee niet achteraf verklaard of gerepareerd.

Onder firmware bijwerken staat **Updatediagnose / Update diagnostics**. Dit
uitklapbare onderdeel blijft open bij de bestaande statusverversing. Dezelfde
informatie is beschikbaar via de bestaande beveiligde `/updates/status`-route.
Er komt geen extra verbinding, poller of achtergrondtaak bij.

## Wat blijft bewaard?

Eén begrensd native NVS-blob van 164 bytes onder `ot_update_diag/last` bewaart het
laatste succesvol opgeslagen controlepunt van een **native HTTPS-installatie**:

- teller, oorspronkelijke versie/broncommit en gekozen doelversie;
- fase: manifest ophalen, downloaden, verifiëren, opstartpartitie gekozen of fout;
- ontvangen/verwachte bytes op dat controlepunt en het laatste HTTP-resultaat.

Er worden hoogstens vijf controlepunten per normale installatie opgeslagen,
alleen op faseovergangen. Geen opslag per downloadpakket, webpoll of gewone
opstart; geen groeiende historie. Releasecontroles en handmatige app-uploads
vervangen dit bewijs niet. Er worden geen download-URL's, tijdelijke GitHub-tokens,
wachtwoorden, netwerkgegevens of vrije foutteksten bewaard.

De huidige ESP-IDF-resetreden en adressen van de draaiende en ingestelde
opstartpartitie komen rechtstreeks uit de native SDK. De resetreden wordt in de
webdiagnose als ESP-IDF-code getoond; de partitieadressen staan in het statusrapport.
Deze waarden horen bij de huidige boot, het opgeslagen controlepunt kan ouder zijn.

## Wat bewijst dit niet?

`boot_slot_selected` betekent uitsluitend dat de native verificatie en selectie
waren geslaagd voordat dit controlepunt werd opgeslagen. Het bewijst geen
succesvolle nieuwe boot, automatische rollback, stabiele werking of oorzaak van
een reset. Versie, bron, ELF/webidentiteit en normale bootbevestiging blijven de
installatiecontrole. Een reset tussen een handeling en het volgende opslagpunt
kan alleen het eerdere controlepunt achterlaten. Er is geen acquisitietijd of
blijvend onderscheid tussen meerdere stroomonderbrekingen toegevoegd.

Een ontbrekend, anders gevormd of incompatibel blob geeft **geen controlepunt**.
Bij een schrijffout meldt de huidige boot `checkpoint_save_failed=true`; de
laatste eerder bevestigde snapshot kan nog worden getoond. Na een opslagfout is
de werkelijke flashuitkomst niet op basis van de RAM-snapshot bewezen. De
volgende boot leest opnieuw het werkelijk beschikbare valide blob. Na telleromloop
begint de teller op 1; hij is geen wereldwijd unieke transactie-identiteit.

Opslagfalen verandert geen firmwareselectie, herstartbeleid, checksumcontrole of
herstelactie. De diagnose start nooit automatisch een nieuwe poging. Een oudere
firmware kan het nieuwe veld missen; dat is geen bewijs dat nooit een poging
is gedaan. De eerste installatie van deze diagnose vanuit oude firmware kan
zelf nog geen nieuw opgeslagen controlepunt opleveren.

## Controles en vervolg

De native regressie controleert reconstructie na herstart, onbekende/corrupte
opslag, schrijffouten, grenzen en telleromloop. De browser gebruikt gesimuleerde
HTTP-antwoorden en controleert alleen uitlezen, EN/NL, openblijvende details en
het onderscheid tussen partitieselectie en bevestigde installatie. De echte
E32-build controleert de native NVS-/SDK-integratie.

Deze softwarecontroles zijn geen fysieke flash-, powerloss- of updateproef.
Voor een latere gecontroleerde installatie blijven exact pakket, verse back-up,
instellingenbehoud, normale boot-/broncontrole en afzonderlijke beoordeling van
de bekende fout nodig. Geen blinde herhaling van de oude HTTPS-poging; geen
actieve ketel-/kraanopdracht, SOURCE-aanpassing of nieuwe achtergrondjob.
