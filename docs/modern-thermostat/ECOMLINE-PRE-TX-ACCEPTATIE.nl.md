# Ecomline Classic HRC 22H — acceptatie vóór fysieke TX

Bijgewerkt 24 oktober 2026. Onderdeel van WORKBOARD B09, geen tweede afvinklijst
of uitvoeringsopdracht. Status: **niet vrijgegeven**. Tado blijft de actieve
regelaar; E32 blijft RX-only. Ook een nulvraag valt buiten deze stap.

## Vastgesteld en begrensd

De gebruiker heeft de Ecomline Classic HRC 22H en Bosch EasyControl Adapter
8737908035 V2.3 opgegeven. De fysieke printrevisie van de E32, UBA-revisie en
actuele bedrading zijn hiermee niet geïnspecteerd.

De [fabrikantpagina](https://www.nefit-bosch.nl/producten/thermostaten/slimme-thermostaten/easycontrol/easycontrol-adapter/)
noemt de EcomLine Classic HR(C)-familie als adaptertoepassing. De
[compatibiliteitsmatrix 6720882620, oktober 2024, pagina 1](https://www.nefit-bosch.nl/media/country_pool/products/thermostaten/6720882620.pdf)
plaatst EcomLine HR(C) onder iRT met adapter. Dat is familiedocumentatie voor
EasyControl; geen certificering van onze E32-software of individuele installatie.
De matrix gebruikt verkoopnummer 7736701654. De relatie met het opgegeven
onderdeelnummer 8737908035 is in deze review niet onafhankelijk vastgesteld.

De [adapterhandleiding 6720888197, juli 2019, pagina 33](https://www.bosch-homecomfort.com/pl/media/country_pool/dokumenty/wsparcie/apps/6720888197.pdf)
beschrijft onder meer iRT voor UBA 1.5 en waarschuwt dat protocolomzetting
functies kan beperken. Pagina 35, tabel 7 onderscheidt communicatieverlies met
ketel, communicatieverlies met temperatuurregelaar en voedingsverlies. De
beoordeelde tabel geeft geen maximale tijd tot CV-stop voor deze situaties.
Een storingsindicatie geldt daarom niet als bewezen warmte-intrekking.

## Resterende installatiegegevens

De volgende tabel legt het benodigde bewijs vast. Lege gegevens worden geen
instellingen, veilige standaardwaarden of goedgekeurd proefprofiel.

| Onderdeel | Huidige stand | Benodigd vóór passende fysieke proef |
| --- | --- | --- |
| Fysieke identiteit | Ketel/adapter door gebruiker opgegeven; E32-print-/UBA-revisie niet geïnspecteerd | Vastgelegde type-/revisiecontrole zonder openbare unieke serienummers |
| Elektrische TX-route | GPIO4/5 komen uit gepinde E32V2-boardprofielen; TX blijft input/geblokkeerd | Beoordeling van echte interface, rustniveau, polariteit, timing, echo/arbitrage en voeding door geschikte fysieke uitvoerder |
| Busadres en masker | Niet ingevuld; ontvangen namen identificeren geen vrije zendidentiteit | Expliciet beoordeelde Classic-adressering en exclusief eigenaarschap; niets automatisch kiezen uit telemetrie |
| Afgifte en naloop | Geen gekwalificeerd installatieprofiel | Beoordeeld open afgiftepad, minimumflow, begrenzing en pomp-/naloopgedrag, ook bij kraan- of regelaarverlies |
| Onafhankelijke stop | Historische expliciete nul ondersteunt latere gemelde CV-stop; geen uitvalgarantie | Concrete stop-/herstelmogelijkheid die ook zonder werkende E32/MQTT beschikbaar blijft |
| Proefgrenzen | Eindige softwarepolicy gebouwd; productieprofiel leeg | Vastgelegde passende temperatuur-/duur-/feedback-/stopgrenzen en verantwoordelijke toezichthouder |
| Overdracht | Tado actief; E32 passief | Vastgelegde overdracht naar één actieve eigenaar en herstel naar Tado zonder oude positieve vraag |

## Bewijskaart voor een later afzonderlijk toegelaten proef

Geen uitvoerend draaiboek: pas invullen nadat bovenstaande voorwaarden zijn
beoordeeld en de passende fysieke proef is toegelaten. Uitvalroutes afzonderlijk
beoordelen; niet aannemen dat één route de andere afdekt.

| Vast te leggen gegeven | Vereiste registratie |
| --- | --- |
| Identiteit en tijd | Ketel/adapter/E32-revisie, firmwarebron, operator, monotone meettijd en wandklok |
| Uitvalroute | Verlies van EMS-regelaar, adaptervoeding of iRT afzonderlijk; feitelijk beproefde route expliciet noemen |
| Laatste vraag | Werkelijk verzonden opdracht en voltooiingstijd; intentie en SDK-acceptatie apart houden |
| CV-stop | Onafhankelijke waarneming en strikt latere ketelrapporten; ontbrekende waarden niet als nul behandelen |
| Tapwater/naloop | CV versus DHW onderscheiden; toestand van afgiftepad/pomp tijdens en na intrekking |
| Termijn | Gemeten duur en toegestane grens met bron; geen termijn invullen uit een herhaalinterval of softwarelease |
| Herstel | Geen automatische hervatting/oude vraag; gecontroleerde terugkeer naar bestaande regeling |
| Uitkomst | Geslaagd, mislukt of onbekend; ruwe bewijslocatie en beoordelaar |

Tot dit bewijs bestaat blijven B09 en de actieve bèta open. Het normale
uitleespad blijft alle ontvangen ondersteunde velden verwerken; het ketelprofiel
beperkt geen decoder, stelt geen ontbrekende sensoren aanwezig en ontgrendelt
geen uitvoer. Softwarepakketcheckpoint `fbed431` is geen fysieke vrijgave.
