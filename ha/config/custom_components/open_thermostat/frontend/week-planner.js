/* One native room configuration, one draft, one save. HA authenticates; E32 controls. */
const DAYS=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const TEXT={
 nl:{deviceStates:{available:'beschikbaar in Home Assistant',unknown:'status onbekend',unavailable:'niet beschikbaar',no_state:'nog geen status',disabled:'uitgeschakeld in Home Assistant',missing:'opgeslagen koppeling ontbreekt',identity_changed:'oorspronkelijk apparaat ontbreekt',invalid_temperature:'geen bruikbare temperatuurwaarde'},deviceHint:'Kies bij een ontbrekende koppeling opnieuw het juiste apparaat. Bij een uitgeschakeld apparaat kun je het ook eerst in Home Assistant inschakelen en opnieuw laden.',sensorState:'Sensorstatus bij laden',devicesChanged:'De apparaatkoppeling is gewijzigd. Laad opnieuw en kies het juiste apparaat; je concept blijft behouden.',days:['Maandag','Dinsdag','Woensdag','Donderdag','Vrijdag','Zaterdag','Zondag'],title:'Ruimte instellen',room:'Ruimte',name:'Naam',emitter:'Verwarming',radiator:'Radiatoren',floor:'Vloerverwarming — binnenkort',combined:'Radiatoren en vloer — binnenkort',emitterHelp:'Het verwarmingstype bepaalt de aansturing. Deze versie ondersteunt radiatoren.',sensor:'Temperatuursensor',sensorHelp:'Deze meting gebruikt de regelaar voor de kamer. Kies een sensor die de kamertemperatuur goed weergeeft.',valves:'Radiatorkranen',valvesHelp:'Koppel alle radiatoren die deze ruimte verwarmen. Een kraan kan bij één ruimte horen.',base:'Basistemperatuur (°C)',baseHelp:'Deze temperatuur geldt buiten de gekleurde blokken.',advanced:'Geavanceerde instellingen',min:'Minimumtemperatuur (°C)',max:'Maximumtemperatuur (°C)',limitsHelp:'Begrenst de doelen die je in deze ruimte kunt instellen.',age:'Meting maximaal oud (seconden)',ageHelp:'Een oudere meting blokkeert de normale warmtevraag. Dit verandert niet hoe vaak de sensor meet.',source:'Programmabron',local:'Eigen weekprogramma',helper:'Home Assistant Schedule-helper',helperEntity:'Schedule-helper',helperHelp:'De helper levert het programma. Je wijzigt die helper in Home Assistant.',sourceConfirm:'De programmabron wijzigen? Bij opslaan met een helper vervallen de lokale weekblokken. De helper zelf wordt niet aangepast.',week:'Weekplanner',pickBlock:'Blok kiezen',hint:'Klik op een leeg tijdvak of sleep om een blok te tekenen. Klik op een blok om tijden en temperatuur hieronder te wijzigen.',empty:'Geen blokken · basistemperatuur',add:'Blok toevoegen',copy:'Dag kopiëren',copyTo:'Kopieer naar',copyHelp:'Dit vervangt de blokken van de gekozen dagen in je concept.',applyCopy:'Dagen kopiëren',day:'Dag',start:'Van',end:'Tot',temp:'Temperatuur (°C)',remove:'Blok verwijderen',selected:'Geselecteerd blok',pick:'Klik of sleep in de planner om een temperatuurblok te maken.',save:'Alles opslaan',cancel:'Wijzigingen annuleren',reload:'Opnieuw laden',saved:'Alle wijzigingen opgeslagen',draft:'Niet-opgeslagen wijzigingen',saving:'Opslaan…',done:'Opgeslagen. Toepassing op de regelaar wordt afzonderlijk bevestigd.',load:'Kamerinstellingen laden…',failed:'Laden is niet gelukt. Probeer Opnieuw laden.',admin:'Meld je aan als beheerder om deze instellingen te bekijken en te wijzigen.',active:'Wijzigen is momenteel geblokkeerd omdat de regeling actief is.',unsupported:'Deze ruimte gebruikt een ander of uitgebreid profiel. De gegevens worden behouden; deze radiator-editor kan ze nog niet wijzigen.',external:'Deze bestaande ruimte gebruikt nog een extern programma. De koppeling blijft behouden; de lokale weekplanner is voor deze ruimte niet bewerkbaar.',invalid:'Controleer de ingevulde waarden. Een blok moet binnen één dag liggen (eindtijd mag 24:00 zijn).',overlap:'Blokken mogen niet overlappen. Aansluitende blokken mogen wel.',range:'Kies temperaturen binnen de ingestelde kamergrenzen.',limit:'Je kunt maximaal 28 blokken per week instellen.',changed:'De configuratie is ondertussen gewijzigd. Je concept blijft zichtbaar. Laad eerst de opgeslagen versie opnieuw.',missing:'Een opgeslagen apparaatkoppeling ontbreekt of is gewijzigd. Kies het juiste apparaat opnieuw; verwijder bij kranen eerst de ontbrekende keuze.',ownership:'Een geselecteerd apparaat is al aan een andere ruimte of functie gekoppeld.',uncertain:'Opslaan kon niet worden bevestigd. Je concept blijft zichtbaar. Laad de opgeslagen versie voordat je opnieuw opslaat.',discard:'Niet-opgeslagen wijzigingen vervangen?',choose:'Kies een apparaat',copyInvalid:'Kies minstens één andere dag.',learning:'Geleerd voorverwarmen is nog niet beschikbaar.',unsupportedEmitter:'Dit verwarmingstype is nog niet beschikbaar.'},
 en:{deviceStates:{available:'available in Home Assistant',unknown:'status unknown',unavailable:'unavailable',no_state:'no state yet',disabled:'disabled in Home Assistant',missing:'saved binding missing',identity_changed:'original device missing',invalid_temperature:'no usable temperature value'},deviceHint:'Select the correct device again if a binding is missing. For a disabled device, you can also enable it in Home Assistant, then reload.',sensorState:'Sensor status when loaded',devicesChanged:'A device binding changed. Reload and choose the correct device; your draft is retained.',days:['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],title:'Room settings',room:'Room',name:'Name',emitter:'Heating',radiator:'Radiators',floor:'Underfloor heating — coming later',combined:'Radiators and floor — coming later',emitterHelp:'Heating type determines control. This version supports radiators.',sensor:'Temperature sensor',sensorHelp:'This measurement is used for the room. Choose a sensor that represents room temperature.',valves:'Radiator valves',valvesHelp:'Select every radiator in this room. A valve can belong to one room.',base:'Base temperature (°C)',baseHelp:'Used outside the coloured blocks.',advanced:'Advanced settings',min:'Minimum temperature (°C)',max:'Maximum temperature (°C)',limitsHelp:'Limits the targets you can choose for this room.',age:'Maximum measurement age (seconds)',ageHelp:'Older measurements inhibit normal demand. This does not change sensor reporting frequency.',source:'Program source',local:'Local week program',helper:'Home Assistant Schedule helper',helperEntity:'Schedule helper',helperHelp:'The helper supplies the program. Edit that helper in Home Assistant.',sourceConfirm:'Change the program source? Saving with a helper removes the local week blocks. The helper itself is not changed.',week:'Week planner',pickBlock:'Choose a block',hint:'Click an empty time or drag to draw a block. Select a block to edit its time and temperature below.',empty:'No blocks · base temperature',add:'Add block',copy:'Copy day',copyTo:'Copy to',copyHelp:'This replaces the selected days in your draft.',applyCopy:'Copy days',day:'Day',start:'From',end:'Until',temp:'Temperature (°C)',remove:'Delete block',selected:'Selected block',pick:'Click or drag in the planner to add a temperature block.',save:'Save all',cancel:'Discard changes',reload:'Reload',saved:'All changes saved',draft:'Unsaved changes',saving:'Saving…',done:'Saved. Application on the controller is confirmed separately.',load:'Loading room settings…',failed:'Loading failed. Try Reload.',admin:'Sign in as an administrator to view and edit these settings.',active:'Editing is blocked while control is active.',unsupported:'This room uses another or extended profile. Its data is retained; this radiator editor cannot edit it yet.',external:'This existing room still uses an external program. Its binding is retained; the local week planner cannot edit it.',invalid:'Check the values. Blocks must stay within one day (end time may be 24:00).',overlap:'Blocks must not overlap. Adjacent blocks are allowed.',range:'Choose temperatures within the room limits.',limit:'A week can contain at most 28 blocks.',changed:'Configuration changed meanwhile. Your draft is retained. Reload the saved version first.',missing:'A saved device binding is missing or changed. Select the correct device again; for valves, remove the missing selection first.',ownership:'A selected device is already assigned to another room or function.',uncertain:'Saving could not be confirmed. Your draft is retained. Reload the saved version before retrying.',discard:'Replace unsaved changes?',choose:'Choose a device',copyInvalid:'Choose at least one other day.',learning:'Learned preheating is not available yet.',unsupportedEmitter:'This heating type is not available yet.'}
};
Object.assign(TEXT.en,{
 contacts:'Windows and doors',contactsHelp:'Room demand pauses when a selected contact opens. It resumes after all contacts report closed. Missing or expired reports keep demand paused.',
 contactsChoose:'Choose window and door contacts',contactsNone:'No contacts selected',contactsSettings:'Contact response and report age',
 contactOpenDelay:'Opening delay (seconds)',contactCloseDelay:'Resume delay after closing (seconds)',contactAge:'Maximum report age (seconds)',
 contactAgeHelp:'Older reports become unknown. Reading the page does not make a report newer.',contactDraft:'Save to apply the contact changes.',
 contactWaiting:'Contact status is not available yet.',contactInvalid:'Check contact selections, delays and maximum report age.',
 contactReasons:{contact_open:'A window or door is open; room demand is paused.',contacts_closed:'All selected contacts report closed.',contact_open_delay:'Opening delay is running.',contact_close_delay:'Waiting before resuming after closing.',contact_state_unknown:'A contact is unavailable or its report has expired; room demand is paused.',contact_clock_invalid:'Contact report age cannot be established.',contact_clock_reversed:'Contact timing must be re-established.'},
 contactRemaining:'Remaining',contactSeconds:'seconds',contactsUnsupported:'Update the controller before adding window and door contacts. No room settings were saved.'
});
Object.assign(TEXT.nl,{
 contacts:'Ramen en deuren',contactsHelp:'De kamervraag pauzeert zodra een gekozen contact opent. Hervatten kan nadat alle contacten gesloten melden. Ontbrekende of verlopen berichten houden de vraag gepauzeerd.',
 contactsChoose:'Raam- en deurcontacten kiezen',contactsNone:'Geen contacten gekozen',contactsSettings:'Reactietijd en berichtouderdom',
 contactOpenDelay:'Vertraging na openen (seconden)',contactCloseDelay:'Wachttijd na sluiten (seconden)',contactAge:'Maximale berichtouderdom (seconden)',
 contactAgeHelp:'Oudere berichten worden onbekend. De pagina uitlezen maakt een bericht niet nieuwer.',contactDraft:'Sla op om de contactwijzigingen toe te passen.',
 contactWaiting:'De contactstatus is nog niet beschikbaar.',contactInvalid:'Controleer de gekozen contacten, vertragingen en maximale berichtouderdom.',
 contactReasons:{contact_open:'Een raam of deur is open; de kamervraag is gepauzeerd.',contacts_closed:'Alle gekozen contacten melden gesloten.',contact_open_delay:'De openingsvertraging loopt.',contact_close_delay:'Wachten voordat de vraag na sluiten wordt hervat.',contact_state_unknown:'Een contact is niet beschikbaar of zijn bericht is verlopen; de kamervraag is gepauzeerd.',contact_clock_invalid:'De ouderdom van het contactbericht kan niet worden vastgesteld.',contact_clock_reversed:'De contacttiming moet opnieuw worden vastgesteld.'},
 contactRemaining:'Resterend',contactSeconds:'seconden',contactsUnsupported:'Werk de regelaar bij voordat je raam- en deurcontacten toevoegt. Er zijn geen kamerinstellingen opgeslagen.'
});
Object.assign(TEXT.en,{
 powerTitle:'Batteries when loaded',powerHelp:'A snapshot of cached Home Assistant reports for the saved sensor and valves. It does not confirm an original hardware report or change heating. Reload to refresh.',
 powerPending:'Save or discard the changed device bindings before inspecting their batteries.',powerUnknown:'No matching battery snapshot is available.',powerUnresolved:'Some saved sources have no matching enabled native device.',
 powerBattery:'Battery',powerLow:'Device low-battery flag',powerYes:'Reported on',powerNo:'Reported off',powerAge:'HA report age',powerMinutes:'min',powerReported:'Last HA report',
 powerStates:{reported:'HA report available',stale:'HA report is at least 24 hours old',missing:'Not reported in HA',disabled:'Battery entity disabled in HA',ambiguous:'Multiple battery entities; no source selected',unavailable:'HA entity unavailable',restored:'Restored value; no received report confirmed',clock_unknown:'HA report time unknown',invalid:'HA battery report invalid'}
});
Object.assign(TEXT.nl,{
 powerTitle:'Batterijen bij laden',powerHelp:'Een momentopname van gecachete Home Assistant-meldingen voor de opgeslagen sensor en kranen. Dit bevestigt geen oorspronkelijk hardwarebericht en verandert geen verwarming. Laad opnieuw om te verversen.',
 powerPending:'Bewaar of verwerp de gewijzigde apparaatkoppelingen voordat je hun batterijen bekijkt.',powerUnknown:'Er is geen bijpassende batterijmomentopname beschikbaar.',powerUnresolved:'Sommige opgeslagen bronnen hebben geen bijpassend ingeschakeld native apparaat.',
 powerBattery:'Batterij',powerLow:'Lage-batterijmelding van apparaat',powerYes:'Aan gemeld',powerNo:'Uit gemeld',powerAge:'Ouderdom HA-melding',powerMinutes:'min',powerReported:'Laatste HA-melding',
 powerStates:{reported:'HA-melding beschikbaar',stale:'HA-melding is minstens 24 uur oud',missing:'Niet gemeld in HA',disabled:'Batterijentiteit uitgeschakeld in HA',ambiguous:'Meerdere batterijentiteiten; geen bron gekozen',unavailable:'HA-entiteit niet beschikbaar',restored:'Herstelde waarde; geen ontvangst bevestigd',clock_unknown:'Tijdstip HA-melding onbekend',invalid:'HA-batterijmelding ongeldig'}
});
const clone=x=>JSON.parse(JSON.stringify(x));
Object.assign(TEXT.nl,{
 valveReceptionTitle:'Laatste ontvangst',valveReceptionProperties:'Aanwezige gegevens',valveReceptionAgeUnknown:'Ontvangstouderdom onbekend',valveReceptionKinds:{commandDataResponse:'Apparaatantwoord',commandDataReport:'Apparaatrapport',commandActiveStatusReport:'Actueel apparaatrapport',commandActiveStatusReportAlt:'Actueel apparaatrapport'},
 valveReportTitle:'Oorspronkelijk kraanbericht',valveReportAge:'Ontvangstouderdom bij laden',valveReportSeconds:'s',
 valveReportDisclaimer:'Een ontvangen doel is geen bevestiging van een opdracht, klepstand of geleverde warmte. De fysieke werking is nog niet bevestigd.',
 valveReportUnavailable:'De oorspronkelijke kraanontvangst is niet beschikbaar of kon niet worden beoordeeld.',
 valveReportStates:{metadata_unavailable:'Wachten op apparaatmetadata; de oorspronkelijke kraanberichten worden nog niet ontvangen.',unavailable:'De ontvangst van kraanberichten is niet beschikbaar.',waiting:'Nog geen oorspronkelijk kraanbericht ontvangen.',received_unqualified:'Een oorspronkelijk kraanbericht is ontvangen; de fysieke werking is nog niet bevestigd.',stale:'Het laatste oorspronkelijke kraanbericht is te oud.',disconnected:'De ontvangst van kraanberichten is onderbroken.',binding_changed:'De oorspronkelijke kraankoppeling is gewijzigd; laad opnieuw.',clock_invalid:'De ouderdom van het kraanbericht kan niet worden vastgesteld.',run_limit:'De kraanbron moet opnieuw worden gecontroleerd.',closed:'De ontvangst van kraanberichten is gestopt.'},
 valveReportFields:{target_centi_c:'Gemeld doel',local_temperature_centi_c:'Eigen kraantemperatuur',preset:'Gemeld programma',heating_stop:'Verwarmingsstop',frost_protection:'Vorstbeveiliging'},
 valveReportPresets:{auto:'Eigen weekprogramma',manual:'Handmatig',holiday:'Vakantie'},valveReportOn:'Aan',valveReportOff:'Uit',

 measurementTitle:'Meetstatus bij laden',measurementStates:{pending:'Sla de nieuwe sensorkoppeling op om de meetstatus te controleren.',inactive:'De meting wordt nog niet door de regeling gevolgd.',profile_missing:'De sensor is gekoppeld; een getoetst meetprofiel ontbreekt nog.',qualified:'Een gekwalificeerde meting is beschikbaar.',stale:'De laatste gekwalificeerde meting is te oud.',unverified:'De meetactualiteit is nog niet bevestigd.',unavailable:'De meetbron is niet beschikbaar.',invalid:'De meetwaarde is ongeldig.',profile_error:'Het meetprofiel kon de meting niet verwerken.',out_of_order:'Een ouder meetbericht is ontvangen.',binding_changed:'De sensorkoppeling is gewijzigd; laad opnieuw.',disabled:'De meting is niet actief.'},

 originalReportStates:{unavailable:'De ontvangst van sensorberichten kon niet worden beoordeeld.',waiting:'Nog geen oorspronkelijk sensorbericht ontvangen.',received_unqualified:'Een oorspronkelijk sensorbericht is ontvangen; het meetprofiel is nog niet bevestigd.',stale:'Het laatste oorspronkelijke sensorbericht is te oud.',disconnected:'De ontvangst van sensorberichten is onderbroken.',binding_changed:'De oorspronkelijke sensorkoppeling is gewijzigd; laad opnieuw.',clock_invalid:'De ouderdom van het sensorbericht kan niet worden vastgesteld.',run_limit:'De meetbron moet opnieuw worden gecontroleerd.',closed:'De ontvangst van sensorberichten is gestopt.'},
 metadataVersions:'Gemelde softwareversies',metadataConverters:'Converterpakket',metadataVersionMissing:'niet gemeld',
 metadataTitle:'Apparaatmogelijkheden',metadataRead:'Apparaatinformatie controleren',metadataWait:'Apparaatinformatie ophalen…',
 metadataHelp:'Leest de door Zigbee2MQTT gemelde mogelijkheden voor de opgeslagen sensor en kranen. Dit wijzigt geen instellingen en bevestigt geen fysieke werking.',
 metadataUnknown:'Deze informatie kon niet worden vastgesteld. De bestaande apparaatkoppelingen blijven behouden.',
 metadataDraft:'Sla wijzigingen eerst op om de bijbehorende apparaten te controleren.',metadataMissing:'Geen apparaatdefinitie ontvangen.',
 metadataDiagnostic:'Deze bron levert apparaattemperatuur. Of deze meting geschikt is als kamertemperatuur moet nog worden gecontroleerd.',
 metadataAbsent:'niet vermeld in de apparaatdefinitie',metadataDeclared:'instelbaar gemeld',metadataReadOnly:'alleen uitlezen gemeld',metadataOptions:'MQTT-opties',
 metadataRoles:{device_temperature:'Apparaattemperatuur',temperature:'Temperatuur',local_temperature:'Eigen temperatuurmeting',calibration:'Meetcorrectie',external_temperature:'Externe temperatuurinvoer',temperature_source:'Temperatuurbron',setpoint:'Doeltemperatuur',valve_position:'Klepstand',system_mode:'Verwarmingsmodus',preset:'Programmamodus',running_state:'Werkingsstatus',local_schedule:'Eigen kraanprogramma'},
 nameHelp:'Deze naam verschijnt bij de ruimte. Hernoemen behoudt de koppelingen en het weekprogramma.',
 valveReview:'Controle gekoppelde kranen',reviewScope:'Opgeslagen doelen en gemelde kraaneigenschappen en bedrijfsmodus bij laden.',
 reviewModes:{local_schedule_active:'De TV02 meldt een eigen weekprogramma. Dat kan het kamerdoel overschrijven.',holiday_mode_active:'De TV02 meldt een vakantieprogramma. Dat kan het kamerdoel overschrijven.',heating_disabled:'De TV02 meldt verwarming uit; de software schakelt de kraan niet automatisch in.',operating_mode_unknown:'De bedrijfsmodus van de TV02 is niet bevestigd. Controleer de kraan en laad opnieuw.'},
 reviewLimits:'De kamergrenzen zijn ruimer dan deze kraan ondersteunt. Pas zo nodig Minimum- en Maximumtemperatuur aan onder Geavanceerde instellingen.',
 reviewUnknown:'Bereik of temperatuurstap is niet beschikbaar of onbruikbaar. Controleer de kraan in Home Assistant en laad opnieuw.',
 reviewUnavailable:'De kraancontrole is nog niet beschikbaar. Laad opnieuw nadat de integratie is bijgewerkt.',
 reviewPending:'Je hebt kranen, temperatuurgrenzen of programmadoelen gewijzigd. Na Alles opslaan worden deze opnieuw gecontroleerd.',
 reviewFits:'De opgeslagen lokale doelen passen bij de gemelde kraaneigenschappen.',
 reviewExternal:'Het bestaande externe programma is niet gecontroleerd.',
 reviewDisclaimer:'Deze controle wijzigt niets. Passende doelen bewijzen geen klepstand of fysieke werking.',
 reviewStep:'stap',reviewOutside:'valt buiten het kraanbereik',reviewRounds:'wordt afgerond naar',reviewDetails:'Temperaturen die aandacht vragen',reviewBase:'Basistemperatuur'
});
Object.assign(TEXT.en,{
 valveReceptionTitle:'Last reception',valveReceptionProperties:'Present data',valveReceptionAgeUnknown:'Reception age unknown',valveReceptionKinds:{commandDataResponse:'Device response',commandDataReport:'Device report',commandActiveStatusReport:'Current device report',commandActiveStatusReportAlt:'Current device report'},
 valveReportTitle:'Original valve report',valveReportAge:'Reception age when loaded',valveReportSeconds:'s',
 valveReportDisclaimer:'A received target does not confirm a command, valve position or delivered heat. Physical operation is not confirmed yet.',
 valveReportUnavailable:'Original valve reception is unavailable or could not be assessed.',
 valveReportStates:{metadata_unavailable:'Waiting for device metadata; original valve reports are not being received yet.',unavailable:'Original valve report reception is unavailable.',waiting:'No original valve report has been received yet.',received_unqualified:'An original valve report was received; physical operation is not confirmed yet.',stale:'The last original valve report is too old.',disconnected:'Valve report reception was interrupted.',binding_changed:'The original valve binding changed; reload.',clock_invalid:'The age of the valve report could not be established.',run_limit:'The valve source needs to be checked again.',closed:'Valve report reception has stopped.'},
 valveReportFields:{target_centi_c:'Reported target',local_temperature_centi_c:'Own valve temperature',preset:'Reported program',heating_stop:'Heating stop',frost_protection:'Frost protection'},
 valveReportPresets:{auto:'Own week program',manual:'Manual',holiday:'Holiday'},valveReportOn:'On',valveReportOff:'Off',

 measurementTitle:'Measurement status when loaded',measurementStates:{pending:'Save the new sensor binding to check its measurement status.',inactive:'Control is not monitoring this measurement yet.',profile_missing:'The sensor is linked; a reviewed measurement profile is still missing.',qualified:'A qualified measurement is available.',stale:'The last qualified measurement is too old.',unverified:'Measurement freshness has not been confirmed.',unavailable:'The measurement source is unavailable.',invalid:'The measurement is invalid.',profile_error:'The measurement profile could not process the report.',out_of_order:'An older measurement report was received.',binding_changed:'The sensor binding changed; reload.',disabled:'Measurement monitoring is inactive.'},

 originalReportStates:{unavailable:'Sensor report reception could not be assessed.',waiting:'No original sensor report has been received yet.',received_unqualified:'An original sensor report was received; its measurement profile is not confirmed yet.',stale:'The last original sensor report is too old.',disconnected:'Sensor report reception was interrupted.',binding_changed:'The original sensor binding changed; reload.',clock_invalid:'The age of the sensor report could not be established.',run_limit:'The measurement source needs to be checked again.',closed:'Sensor report reception has stopped.'},
 metadataVersions:'Reported software versions',metadataConverters:'Converter package',metadataVersionMissing:'not reported',
 metadataTitle:'Device capabilities',metadataRead:'Check device information',metadataWait:'Reading device information…',
 metadataHelp:'Reads Zigbee2MQTT declarations for the saved sensor and valves. It changes no settings and does not confirm physical operation.',
 metadataUnknown:'This information could not be established. Existing device bindings are retained.',
 metadataDraft:'Save changes before checking the corresponding devices.',metadataMissing:'No device definition received.',
 metadataDiagnostic:'This source reports device temperature. Its suitability as room temperature still needs checking.',
 metadataAbsent:'not listed in the device definition',metadataDeclared:'declared settable',metadataReadOnly:'declared read-only',metadataOptions:'MQTT options',
 metadataRoles:{device_temperature:'Device temperature',temperature:'Temperature',local_temperature:'Own temperature measurement',calibration:'Measurement correction',external_temperature:'External temperature input',temperature_source:'Temperature source',setpoint:'Target temperature',valve_position:'Valve position',system_mode:'Heating mode',preset:'Program mode',running_state:'Operating state',local_schedule:'Own valve program'},
 nameHelp:'This name identifies the room. Renaming keeps its bindings and week program.',
 valveReview:'Linked valve check',reviewScope:'Saved targets and reported valve capabilities and operating mode when loaded.',
 reviewModes:{local_schedule_active:'The TV02 reports automatic scheduling, which can override the room target.',holiday_mode_active:'The TV02 reports a holiday program, which can override the room target.',heating_disabled:'The TV02 reports heating off; software will not turn the valve on automatically.',operating_mode_unknown:'The TV02 operating mode is unconfirmed. Check the valve, then reload.'},
 reviewLimits:'The room limits exceed this valve’s range. Adjust Minimum and Maximum temperature under Advanced settings if needed.',
 reviewUnknown:'The temperature range or step is unavailable or unusable. Check the valve in Home Assistant, then reload.',
 reviewUnavailable:'The valve check is not available yet. Reload after the integration is updated.',
 reviewPending:'You changed valves, temperature limits or program targets. Save all to check them again.',
 reviewFits:'Saved local targets fit the reported valve capabilities.',
 reviewExternal:'The existing external program has not been checked.',
 reviewDisclaimer:'This check changes nothing. Compatible targets do not prove valve position or physical operation.',
 reviewStep:'step',reviewOutside:'is outside the valve range',reviewRounds:'is rounded to',reviewDetails:'Temperatures needing attention',reviewBase:'Base temperature'
});
const scaled=(text,scale)=>{const x=Number(text)*scale;return text!==''&&Number.isFinite(x)&&Math.abs(x-Math.round(x))<1e-7?Math.round(x):NaN;};
const el=(tag,text=null,attrs={})=>{const n=document.createElement(tag);if(text!==null)n.textContent=text;for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
Object.assign(TEXT.nl,{

 profileCapacity:'Deze regelaar ondersteunt momenteel één radiatorknop per ruimte.',
 profileConnected:'Je kunt de kamerinstellingen en apparaatkoppelingen wijzigen. Bij een apparaat- of grenswijziging wordt de regeling tijdelijk gestopt en opnieuw verbonden met het nieuwe profiel.',
 profilePending:'De nieuwe kamerinstellingen zijn opgeslagen, maar nog niet bevestigd door de regelaar. Controleer de verbinding en pas de opgeslagen instellingen opnieuw toe.',
 profileReapply:'Opgeslagen instellingen toepassen',
 programConnected:'De regelaar is verbonden. Je kunt de naam, basistemperatuur en weekblokken aanpassen. Bij gewijzigde temperaturen of blokken wordt een tijdelijke temperatuur beëindigd zodra de regelaar het nieuwe programma bevestigt. Apparaatkoppelingen en grenzen kunnen in deze versie nog niet worden gewijzigd terwijl de regeling actief is.',
 programPending:'De ruimte is opgeslagen, maar het programma is nog niet bevestigd door de regelaar.',
 programReapply:'Programma opnieuw toepassen',
 programDone:'De ruimte is opgeslagen en het programma is bevestigd door de regelaar.',
 reloadUnconfirmed:'Opnieuw laden toont wat er nu is opgeslagen en vervangt je huidige concept. Doorgaan?',
 applyUnconfirmed:'De toepassing is nog niet bevestigd. Je concept blijft behouden. Laad de opgeslagen ruimte opnieuw voordat je het programma opnieuw toepast.',
 readbackUnconfirmed:'De actuele configuratie van de regelaar kon niet worden uitgelezen. Er is niets opgeslagen; je concept blijft behouden.',
 controllerPending:'De regelaar is nog niet klaar om deze wijziging te bevestigen. Je concept is behouden; laad opnieuw zodra de verbinding is hersteld.',
 profileChange:'Apparaten of grenzen wijzigen bij een actieve regeling is nog niet beschikbaar. Laad de opgeslagen ruimte opnieuw.',
 programCapacity:'Dit programma past nog niet op de regelaar. Gebruik minder temperatuurblokken.'
});
Object.assign(TEXT.en,{

 profileCapacity:'This controller currently supports one radiator valve per room.',
 profileConnected:'You can change room settings and device bindings. A device or limit change temporarily stops control and reconnects using the new profile.',
 profilePending:'The new room settings are saved but the controller has not confirmed them. Check the connection and apply the saved settings again.',
 profileReapply:'Apply saved settings',
 programConnected:'The controller is connected. You can edit the name, base temperature and week blocks. Changed temperatures or blocks end a temporary temperature when the controller confirms the new program. Device bindings and limits cannot yet be changed while control is active.',
 programPending:'The room is saved, but the controller has not confirmed its program yet.',
 programReapply:'Apply program again',
 programDone:'The room is saved and its program is confirmed by the controller.',
 reloadUnconfirmed:'Reloading shows what is currently saved and replaces your current draft. Continue?',
 applyUnconfirmed:'Application has not been confirmed. Your draft is retained. Reload the saved room before applying its program again.',
 readbackUnconfirmed:'The current controller configuration could not be read. Nothing was saved; your draft is retained.',
 controllerPending:'The controller is not ready to confirm this change. Your draft is retained; reload once the connection is restored.',
 profileChange:'Changing devices or limits while control is active is not available yet. Reload the saved room.',
 programCapacity:'This program does not fit on the controller yet. Use fewer temperature blocks.'
});
Object.assign(TEXT.nl,{
 diagnosticSourceLabel:'diagnostiek',
 temperatureSourceReasons:{internal_device_temperature:'Dit is de interne apparaattemperatuur. Kies voor de ruimte een sensor die de luchttemperatuur meet.',diagnostic_entity:'Deze temperatuursensor is als diagnostiek gemarkeerd. Controleer of hij de ruimtelucht meet; hij is niet automatisch geschikt voor de regeling.',binding_unavailable:'De opgeslagen temperatuurbron is niet beschikbaar. Kies zelf een vervangende sensor; de koppeling wordt niet automatisch gewijzigd.'}
});
Object.assign(TEXT.en,{
 diagnosticSourceLabel:'diagnostic',
 temperatureSourceReasons:{internal_device_temperature:'This is the internal device temperature. Choose a sensor that measures room air temperature.',diagnostic_entity:'This temperature sensor is marked as diagnostic. Check whether it measures room air; it is not automatically suitable for control.',binding_unavailable:'The saved temperature source is unavailable. Choose a replacement yourself; its binding is not changed automatically.'}
});
const clock=n=>n===86400?'24:00':`${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n%3600/60)).padStart(2,'0')}${n%60?':'+String(n%60).padStart(2,'0'):''}`;
Object.assign(TEXT.en,{
 manualTarget:'Extra room target control',manualTargetHelper:'Temperature helper',manualTargetNone:'No extra target source',
 manualTargetHelp:'Choose a Home Assistant number helper with °C or °F units. Only a new manual user change requests a temporary room target; the helper is never written by the controller.',
 manualTargetDuration:'Temporary target duration (minutes)',manualTargetDraft:'Save to apply the target-source changes.',
 manualTargetInvalid:'Choose a temperature helper and an override duration between 1 and 720 minutes.',
 manualTargetOwner:'This target helper already belongs to another room.',manualTargetUpdate:'Update the controller before adding this target source. Nothing was saved.',
 manualTargetRemaining:'Override remaining',manualTargetMinutes:'minutes',
 manualTargetStates:{not_configured:'No extra target source selected.',awaiting_manual_change:'Waiting for a new manual change; the current helper value is not applied automatically.',manual_action_required:'The last change was not a usable direct manual action.',old_or_repeated_action:'An old or repeated action was ignored.',controller_unavailable:'The controller was unavailable; the action will not be replayed.',request_pending:'Sending the temporary target request.',request_accepted:'The last target request was accepted by the controller.',request_unconfirmed:'The last request was not confirmed. Check the current target before a new manual action.',request_withdrawn:'The pending request expired or its owner/binding changed.',binding_unavailable:'The selected target helper is unavailable. The room program remains independent.',device_action_profile_required:'This physical device needs a reviewed original-action profile.'}
});
Object.assign(TEXT.nl,{
 manualTarget:'Extra kamerbediening',manualTargetHelper:'Temperatuurhelper',manualTargetNone:'Geen extra doelbron',
 manualTargetHelp:'Kies een Home Assistant-getalhelper met °C of °F. Alleen een nieuwe handmatige gebruikerswijziging vraagt een tijdelijk kamerdoel aan; de regelaar schrijft nooit naar de helper.',
 manualTargetDuration:'Duur tijdelijk doel (minuten)',manualTargetDraft:'Sla op om de gewijzigde doelbron toe te passen.',
 manualTargetInvalid:'Kies een temperatuurhelper en een duur tussen 1 en 720 minuten.',
 manualTargetOwner:'Deze doelhelper hoort al bij een andere ruimte.',manualTargetUpdate:'Werk de regelaar bij voordat je deze doelbron toevoegt. Er is niets opgeslagen.',
 manualTargetRemaining:'Override resterend',manualTargetMinutes:'minuten',
 manualTargetStates:{not_configured:'Geen extra doelbron gekozen.',awaiting_manual_change:'Wachten op een nieuwe handmatige wijziging; de huidige helperwaarde wordt niet automatisch toegepast.',manual_action_required:'De laatste wijziging was geen bruikbare directe gebruikersactie.',old_or_repeated_action:'Een oude of herhaalde actie is genegeerd.',controller_unavailable:'De regelaar was niet beschikbaar; de actie wordt niet later herhaald.',request_pending:'Het tijdelijke kamerdoel wordt aangevraagd.',request_accepted:'De laatste doelaanvraag is door de regelaar geaccepteerd.',request_unconfirmed:'De laatste aanvraag is niet bevestigd. Controleer het huidige doel voordat je opnieuw bedient.',request_withdrawn:'De aanvraag is verlopen of de eigenaar/koppeling is gewijzigd.',binding_unavailable:'De gekozen doelhelper is niet beschikbaar. Het kamerprogramma blijft onafhankelijk.',device_action_profile_required:'Dit fysieke apparaat vereist een getoetst profiel voor de oorspronkelijke bedienactie.'}
});
Object.assign(TEXT.en,{
 comfortTitle:'Comfort and presence',comfortEnabled:'Use comfort modes',comfortAway:'Away target (°C)',comfortFrost:'Frost target (°C)',comfortDuration:'Default temporary duration (minutes)',
 comfortPresence:'Presence source',comfortNoPresence:'No automatic presence control',
 comfortHelp:'Enable Away, temporary targets and frost mode in the room climate control. An optional person source uses Home or Away only; unknown, stale and other named locations remain unknown. The person needs a new HA report at least every two minutes; reading its current value does not count. Window contacts keep their separate pause policy.',
 comfortInvalid:'Check comfort targets, duration and presence. Targets must fit the room limits.',comfortUpdate:'Update the controller before enabling comfort modes. Nothing was saved.',
 comfortFrostProfile:'This controller uses a 5 °C frost target. Keep that target and allow 5 °C in the room limits; the source protection policy is unchanged.',
 comfortDraft:'Save to apply these comfort settings.',comfortDisabled:'Comfort modes are not enabled.',comfortConfigured:'Comfort modes configured; current operation is shown by the room climate control.',
 comfortUnavailable:'Current comfort status is unavailable.',comfortReasons:{presence_away:'Away target selected by presence.',presence_state_unknown:'Presence is unknown or stale; no automatic target is available.',window_open:'Room demand is paused by a window or door.',window_state_unknown:'Window or door status is unknown; room demand remains paused.'},comfortModes:{auto:'Automatic programme',temporary:'Temporary target',boost:'Boost',away:'Away',vacation:'Vacation',frost:'Frost mode',off:'Off'}
});
Object.assign(TEXT.nl,{
 comfortTitle:'Comfort en aanwezigheid',comfortEnabled:'Comfortstanden gebruiken',comfortAway:'Afwezigheidsdoel (°C)',comfortFrost:'Vorstdoel (°C)',comfortDuration:'Standaard tijdelijke duur (minuten)',
 comfortPresence:'Aanwezigheidsbron',comfortNoPresence:'Geen automatische aanwezigheidsregeling',
 comfortHelp:'Schakel Afwezig, tijdelijke doelen en vorststand in op de kamerthermostaat. Een optionele persoonbron gebruikt alleen Thuis of Afwezig; onbekende, verlopen en andere benoemde locaties blijven onbekend. De persoon heeft minstens elke twee minuten een nieuw HA-bericht nodig; de huidige waarde uitlezen telt niet. Raamcontacten houden hun eigen pauzebeleid.',
 comfortInvalid:'Controleer comfortdoelen, duur en aanwezigheid. De doelen moeten binnen de kamergrenzen vallen.',comfortUpdate:'Werk de regelaar bij voordat je comfortstanden inschakelt. Er is niets opgeslagen.',
 comfortFrostProfile:'Deze regelaar gebruikt een vorstdoel van 5 °C. Behoud dat doel en laat 5 °C toe in de kamergrenzen; de bronbeveiliging verandert niet.',
 comfortDraft:'Sla op om deze comfortinstellingen toe te passen.',comfortDisabled:'Comfortstanden zijn niet ingeschakeld.',comfortConfigured:'Comfortstanden ingesteld; de kamerthermostaat toont de huidige werking.',
 comfortUnavailable:'De huidige comfortstatus is niet beschikbaar.',comfortReasons:{presence_away:'Afwezigheidsdoel gekozen door de aanwezigheidsbron.',presence_state_unknown:'Aanwezigheid is onbekend of verlopen; er is geen automatisch doel beschikbaar.',window_open:'De kamervraag is gepauzeerd door een raam of deur.',window_state_unknown:'Raam- of deurstatus is onbekend; de kamervraag blijft gepauzeerd.'},comfortModes:{auto:'Automatisch programma',temporary:'Tijdelijk doel',boost:'Boost',away:'Afwezig',vacation:'Vakantie',frost:'Vorststand',off:'Uit'}
});
Object.assign(TEXT.en,{
 vacationTitle:'Vacation',vacationEnd:'End date and time',vacationStart:'Start or change vacation',vacationCancel:'Return to programme',vacationChoose:'Choose the first or second clock time',
 vacationHelp:'Uses the saved away target until this time in the Home Assistant time zone. This is a separate explicit action; saving room settings does not start vacation. Restart, reconnect or room reload clears this temporary selection.',
 vacationIdle:'Choose an end date and start vacation explicitly.',vacationSave:'Save room changes and wait for their confirmation before using vacation.',vacationUnavailable:'Current room control is unavailable. Reload when the controller is connected.',
 vacationChecking:'Checking the local end time…',vacationSending:'Requesting the comfort change…',vacationRequested:'Request accepted. Check the current room status.',
 vacationUncertain:'Request not confirmed. Inspect the current room status and reload before trying again. Nothing is retried automatically.',vacationStopped:'Action cancelled before dispatch; reload the current room.',
 vacationChanged:'The chosen occurrence is no longer valid. Choose a remaining time explicitly, or select another date.',vacationAmbiguous:'This clock time occurs twice. Choose the intended UTC offset, then press Start again.',vacationGap:'This clock time does not exist when daylight saving time begins. Choose another time.',
 vacationTimeout:'Date check timed out. No comfort command was sent.',vacationRange:'Choose a future end within 366 days.',vacationInvalid:'Choose a valid local date and time.',vacationZone:'The time zone changed or is unavailable. Reload the room.',vacationUntil:'Vacation end reported by the controller'
});
Object.assign(TEXT.nl,{
 vacationTitle:'Vakantie',vacationEnd:'Einddatum en tijd',vacationStart:'Vakantie starten of wijzigen',vacationCancel:'Terug naar programma',vacationChoose:'Kies de eerste of tweede kloktijd',
 vacationHelp:'Gebruikt het opgeslagen afwezigheidsdoel tot dit tijdstip in de Home Assistant-tijdzone. Dit is een afzonderlijke bewuste actie; kamerinstellingen bewaren start geen vakantie. Herstart, herverbinding of kamerreload wist deze tijdelijke keuze.',
 vacationIdle:'Kies een einddatum en start vakantie afzonderlijk.',vacationSave:'Bewaar kamerwijzigingen en wacht op bevestiging voordat je vakantie gebruikt.',vacationUnavailable:'De huidige kamerbediening is niet beschikbaar. Herlaad zodra de regelaar verbonden is.',
 vacationChecking:'Lokale eindtijd controleren…',vacationSending:'Comfortwijziging aanvragen…',vacationRequested:'Aanvraag geaccepteerd. Controleer de huidige kamerstatus.',
 vacationUncertain:'Aanvraag niet bevestigd. Controleer de huidige kamerstatus en herlaad voordat je opnieuw probeert. Er wordt niets automatisch herhaald.',vacationStopped:'Actie vóór verzending geannuleerd; herlaad de huidige kamer.',
 vacationChanged:'De gekozen kloktijd is niet meer geldig. Kies een overgebleven tijdstip afzonderlijk, of selecteer een andere datum.',vacationAmbiguous:'Deze kloktijd komt tweemaal voor. Kies de bedoelde UTC-offset en druk opnieuw op Start.',vacationGap:'Deze kloktijd bestaat niet bij het begin van de zomertijd. Kies een ander tijdstip.',
 vacationTimeout:'De datumcontrole duurde te lang. Er is geen comfortopdracht verstuurd.',vacationRange:'Kies een toekomstige eindtijd binnen 366 dagen.',vacationInvalid:'Kies een geldige lokale datum en tijd.',vacationZone:'De tijdzone is gewijzigd of niet beschikbaar. Herlaad de kamer.',vacationUntil:'Door de regelaar gemelde vakantie-eindtijd'
});
function validVacationPreview(preview,model,token,localEnd,timeZone,entityId){
 if(!preview||preview.entry_id!==model.entry_id||preview.room_id!==model.room_id||preview.entity_id!==entityId||preview.token!==token||preview.time_zone!==timeZone||preview.local_end!==localEnd)return false;
 const rows=preview.candidates,normalized=localEnd.length===16?localEnd+':00':localEnd;
 if(!Array.isArray(rows)||rows.length<1||rows.length>2)return false;
 for(const row of rows){
  if(!row||typeof row.iso!=='string'||row.iso.length>40||!row.iso.startsWith(normalized)||!/^[-+]\d{2}:\d{2}$/.test(row.iso.slice(normalized.length)))return false;
  if(!Number.isSafeInteger(row.until_utc)||row.until_utc<=0||row.until_utc>=4102444800||Date.parse(row.iso)/1000!==row.until_utc)return false;
  if(typeof row.utc_offset!=='string'||!/^[-+]\d{4}$/.test(row.utc_offset)||row.iso.slice(normalized.length).replace(':','')!==row.utc_offset)return false;
 }
 return rows.length===1||rows[0].until_utc<rows[1].until_utc;
}
const seconds=s=>{if(s==='24:00'||s==='24:00:00')return 86400;const m=/^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(s);if(!m||+m[1]>23||+m[2]>59||+(m[3]||0)>59)throw Error('invalid');return +m[1]*3600 + +m[2]*60 + +(m[3]||0);};
function validate(s){
 if([s.temperature_entity,...s.radiator_entities,s.schedule_entity,...(s.contact_entities||[])].some(x=>x?.startsWith('unresolved:')))throw Error('missing');
 if(!s.name.trim()||s.name.length>80||!s.temperature_entity||!s.radiator_entities.length)throw Error('invalid');
 if(![s.base_centi_c,s.minimum_centi_c,s.maximum_centi_c,s.maximum_age_ms].every(Number.isInteger)||s.minimum_centi_c<500||s.maximum_centi_c>3500||s.minimum_centi_c>=s.maximum_centi_c||s.base_centi_c<s.minimum_centi_c||s.base_centi_c>s.maximum_centi_c||s.maximum_age_ms<1000||s.maximum_age_ms>86400000)throw Error('range');
 if(s.contact_entities!==undefined){const p=s.contact_policy;if(!Array.isArray(s.contact_entities)||s.contact_entities.length>8||new Set(s.contact_entities).size!==s.contact_entities.length||!p||Object.keys(p).sort().join(',')!=='close_delay_ms,maximum_age_ms,open_delay_ms'||!Object.values(p).every(Number.isSafeInteger)||p.maximum_age_ms<1000||p.maximum_age_ms>86400000||p.open_delay_ms<0||p.close_delay_ms<0||Math.max(p.open_delay_ms,p.close_delay_ms)>600000||Math.max(p.open_delay_ms,p.close_delay_ms)>=p.maximum_age_ms)throw Error('contactInvalid');}
 if(s.setpoint_entity!==undefined&&(typeof s.setpoint_entity!=='string'||(s.setpoint_entity&&!s.setpoint_entity.startsWith('input_number.'))||s.setpoint_entity.startsWith('unresolved:')||!Number.isSafeInteger(s.setpoint_duration_ms)||s.setpoint_duration_ms<60000||s.setpoint_duration_ms>43200000))throw Error('manualTargetInvalid');
 if(Object.hasOwn(s,'comfort')){
  const c=s.comfort;if(typeof s.presence_entity!=='string'||s.presence_entity.startsWith('unresolved:')||(s.presence_entity&&!s.presence_entity.startsWith('person.'))||(!c&&s.presence_entity))throw Error('comfortInvalid');
  if(c!==null&&(!c||typeof c!=='object'||Array.isArray(c)||Object.keys(c).sort().join(',')!=='away_centi_c,frost_centi_c,temporary_ms'||!Object.values(c).every(Number.isSafeInteger)||c.away_centi_c<s.minimum_centi_c||c.away_centi_c>s.maximum_centi_c||c.frost_centi_c<s.minimum_centi_c||c.frost_centi_c>s.maximum_centi_c||c.temporary_ms<60000||c.temporary_ms>43200000))throw Error('comfortInvalid');
 }
 let count=0;for(const d of DAYS){let end=0;for(const b of [...s.week[d]].sort((a,b)=>a.start-b.start)){if(![b.start,b.end,b.target_centi_c].every(Number.isInteger)||b.start<0||b.end>86400||b.start>=b.end)throw Error('invalid');if(b.target_centi_c<s.minimum_centi_c||b.target_centi_c>s.maximum_centi_c)throw Error('range');if(b.start<end)throw Error('overlap');end=b.end;if(++count>28)throw Error('limit');}}
 return s;
}
// HA installs its scoped custom-element registry during frontend startup.
// Register only after its root is defined, so an early extra-JS import cannot
// register into the native registry that HA is about to replace. Unlike
// ha-card, the root is loaded independently of opening a Lovelace view.
await customElements.whenDefined('home-assistant');
class OpenThermostatRoomEditor extends HTMLElement{
 constructor(){super();this.attachShadow({mode:'open'});this._generation=0;}
 get t(){return TEXT[this._hass?.language?.startsWith('nl')?'nl':'en'];}
 get dirty(){return !!this._model&&JSON.stringify(this._settings)!==JSON.stringify(this._model.settings);}
 get needsApply(){return !!this._model?.apply_pending;}
 get canRetryProfile(){return !!this._model?.profile_apply_pending&&!this._loading&&!this._saving&&!this._uncertain;}
 get locked(){return !this._model?.editable||this._loading||this._saving||this._uncertain||this._vacationBusy;}
 getCardSize(){return 18;}
 setConfig(config){if(!config.entry_id||!config.room_id)throw Error('entry_id and room_id required');if(this._config?.entry_id===config.entry_id&&this._config.room_id===config.room_id)return;this._config={entry_id:config.entry_id,room_id:config.room_id};this._generation++;this._model=null;this._loading=false;this._saving=false;this._uncertain=false;this._vacationBusy=false;this._vacationUncertain=false;this._vacationLocal='';this._vacationCandidates=[];this._vacationChoice='';this._vacationNeedsChoice=false;this._vacationMessage='';this._metadata=null;this._metadataPending=false;this._metadataError=false;this.render();this.load();}
 set hass(hass){this._hass=hass;if(!this._model&&!this._loading)this.load();else{this.renderContactStatus();this.renderManualTargetStatus();this.renderComfortStatus();this.renderVacationStatus();}}
 button(text,fn,disabled=false){const b=el('button',text,{type:'button'});b.disabled=disabled;b.onclick=fn;return b;}
 async load(){if(!this._hass||!this._config||this._loading||this._vacationBusy)return;if(!this._hass.user?.is_admin){this._message=this.t.admin;this.render();return;}const generation=this._generation;this._loading=true;this._message=this.t.load;this.render();try{const m=await this._hass.callWS({type:'open_thermostat/room/get',...this._config});if(generation!==this._generation)return;this._model=m;this.reset();this._message='';}catch{if(generation===this._generation)this._message=this.t.failed;}finally{if(generation===this._generation){this._loading=false;this.render();}}}
 reset(){this._settings=clone(this._model.settings);this._selected=null;this._blockInvalid=false;this._uncertain=false;this._vacationUncertain=false;this._vacationCandidates=[];this._vacationChoice='';this._vacationNeedsChoice=false;this._vacationMessage='';this._copyDay=null;this._metadata=null;this._metadataError=false;}
 renderDevicePower(){
  const box=this._powerBox,m=this._model,s=this._settings;if(!box||!m||!s)return;
  const changed=s.temperature_entity!==m.settings.temperature_entity||JSON.stringify(s.radiator_entities)!==JSON.stringify(m.settings.radiator_entities);
  const data=m.device_power,previous=this._powerRendered;
  if(previous?.box===box&&previous.data===data&&previous.changed===changed&&previous.text===this.t)return;
  this._powerRendered={box,data,changed,text:this.t};box.replaceChildren();box.append(el('h3',this.t.powerTitle),el('small',this.t.powerHelp));
  if(changed){box.append(el('p',this.t.powerPending));return;}
  const text=value=>typeof value==='string'&&value.length>0&&value.length<=255;
  const age=value=>Number.isSafeInteger(value)&&value>=0;
  const utc=value=>{if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/.test(value))return false;const stamp=Date.parse(value);return Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,19)===value.slice(0,19);};
  const report=(r,kind)=>{
   if(!r||!Object.hasOwn(this.t.powerStates,r.status)||!(r.entity_id===null||text(r.entity_id)&&r.entity_id.startsWith(kind==='battery'?'sensor.':'binary_sensor.'))||!(r.reported_at===null||utc(r.reported_at))||!(r.age_ms===null||age(r.age_ms)))return false;
   if(!['reported','stale'].includes(r.status))return r.value===null;
   return r.entity_id!==null&&utc(r.reported_at)&&age(r.age_ms)&&(r.status==='stale'?r.age_ms>=86400000:r.age_ms<86400000)&&(kind==='battery'?typeof r.value==='number'&&Number.isFinite(r.value)&&r.value>=0&&r.value<=100:typeof r.value==='boolean');
  };
  const saved=new Set([m.settings.temperature_entity,...m.settings.radiator_entities]);
  const valid=data?.schema===1&&data.scope==='native_ha_cached_state_only'&&data.physical_control_qualified===false&&Array.isArray(data.devices)&&data.devices.length<=9&&Array.isArray(data.unresolved_sources)&&data.unresolved_sources.length<=9&&data.unresolved_sources.every(text)
   &&data.devices.every(d=>d&&text(d.label)&&d.label.length<=160&&Array.isArray(d.selected_entities)&&d.selected_entities.length>0&&d.selected_entities.length<=9&&d.selected_entities.every(id=>text(id)&&saved.has(id))&&report(d.battery,'battery')&&report(d.battery_low,'battery_low'));
  const selected=valid?data.devices.flatMap(d=>d.selected_entities):[];
  if(!valid||new Set(selected).size!==selected.length){box.append(el('p',this.t.powerUnknown));return;}
  if(data.unresolved_sources.length)box.append(el('p',this.t.powerUnresolved));
  if(!data.devices.length)box.append(el('p',this.t.powerUnknown));
  for(const device of data.devices){
   const article=el('article');article.append(el('strong',device.label));
   for(const [kind,title]of [['battery',this.t.powerBattery],['battery_low',this.t.powerLow]]){
    const r=device[kind],known=['reported','stale'].includes(r.status);
    const value=known?(kind==='battery'?`${(this.t===TEXT.nl?String(r.value).replace('.',','):String(r.value))}%`:r.value?this.t.powerYes:this.t.powerNo):null;
    article.append(el('p',`${title}: ${value===null?'':value+' · '}${this.t.powerStates[r.status]}`));
    if(known)article.append(el('small',`${this.t.powerAge}: ${Math.floor(r.age_ms/60000)} ${this.t.powerMinutes} · ${this.t.powerReported}: ${r.reported_at.replace('T',' ')}`));
   }
   box.append(article);
  }
 }
 async readMetadata(){if(this.dirty||this._metadataPending||this._saving||!this._hass.user?.is_admin)return;const generation=this._generation,token=this._model.token;this._metadataPending=true;this._metadataError=false;this.renderMetadata();try{const result=await this._hass.callWS({type:'open_thermostat/room/device_metadata',...this._config,token});if(generation!==this._generation||token!==this._model.token||this.dirty)return;if(result.metadata_only!==true||result.physical_control_qualified!==false||!Array.isArray(result.devices))throw Error('invalid metadata');this._metadata=result;}catch{if(generation===this._generation)this._metadataError=true;}finally{if(generation===this._generation){this._metadataPending=false;this.renderMetadata();}}}
 renderMetadata(){const box=this._metadataBox;if(!box)return;box.replaceChildren();box.append(el('h3',this.t.metadataTitle),el('small',this.t.metadataHelp));const disabled=this.dirty||this._metadataPending||this._loading||this._saving;box.append(this.button(this._metadataPending?this.t.metadataWait:this.t.metadataRead,()=>this.readMetadata(),disabled));if(this.dirty){box.append(el('p',this.t.metadataDraft));return;}if(this._metadataError){box.append(el('p',this.t.metadataUnknown,{role:'status'}));return;}if(!this._metadata)return;const bridge=this._metadata.bridge;const version=value=>typeof value==='string'&&value.length>0&&value.length<=160?value:this.t.metadataVersionMissing;box.append(el('p',`${this.t.metadataVersions}: Zigbee2MQTT ${version(bridge?.version)} · ${this.t.metadataConverters} ${version(bridge?.zigbee_herdsman_converters_version)}`,{class:'metadata-versions'}));for(const device of this._metadata.devices){const article=el('article');const choice=Object.values(this._model.choices).flat().find(x=>x.value===device.entity_id);article.append(el('strong',choice?.label||device.entity_id));if(device.sensor_property==='device_temperature')article.append(el('p',this.t.metadataDiagnostic,{class:'attention'}));if(!device.definition_observed){article.append(el('p',this.t.metadataMissing));box.append(article);continue;}article.append(el('p',[device.vendor,device.model].filter(Boolean).join(' · ')));for(const [key,title]of [['declared_features',null],['declared_options',this.t.metadataOptions]]){const features=device[key]||[];if(title&&features.length)article.append(el('h4',title));const list=el('ul');for(const feature of features){const label=this.t.metadataRoles[feature.role];if(!label)continue;const bounds=Number.isFinite(feature.value_min)&&Number.isFinite(feature.value_max)?` · ${feature.value_min}–${feature.value_max}${feature.unit?' '+feature.unit:''}`:'';list.append(el('li',`${label}: ${feature.settable_declared?this.t.metadataDeclared:this.t.metadataReadOnly}${bounds}`));}if(key==='declared_features'&&device.entity_id.startsWith('climate.'))for(const role of ['external_temperature','valve_position'])if(!features.some(x=>x.role===role))list.append(el('li',`${this.t.metadataRoles[role]}: ${this.t.metadataAbsent}`));article.append(list);}box.append(article);}}
 errorKey(error){return({setup_changed:'changed',room_changed:'changed',installation_unavailable:'missing',binding_missing:'missing',invalid_contacts:'contactInvalid',not_contact_sensor:'contactInvalid',invalid_contact_policy:'contactInvalid',contact_binding_conflict:'contactInvalid',contact_capability_unavailable:'contactsUnsupported',unsupported_manual_target:'manualTargetInvalid',invalid_manual_target:'manualTargetInvalid',invalid_manual_target_duration:'manualTargetInvalid',manual_target_has_multiple_rooms:'manualTargetOwner',manual_target_capability_unavailable:'manualTargetUpdate',invalid_comfort_profile:'comfortInvalid',invalid_comfort_selection:'comfortInvalid',comfort_window_requires_contacts:'contactInvalid',comfort_capability_unavailable:'comfortUpdate',native_comfort_frost_profile:'comfortFrostProfile',not_temperature:'missing',unsupported_unit:'missing',loop_binding:'ownership',output_has_multiple_owners:'ownership',input_output_loop:'ownership',duplicate_actuator:'ownership',program_overlap:'overlap',program_limit:'limit',invalid_target_range:'range',invalid_integer_or_bounds:'range',invalid_program:'invalid',invalid_program_time:'invalid',invalid_name:'invalid',select_radiators:'invalid',runtime_active:'active',advanced_room_required:'unsupported',emitter_not_available:'unsupportedEmitter',confirm_program_source_change:'invalid',program_source_conflict:'invalid',save_uncertain:'applyUnconfirmed',controller_plan_pending:'controllerPending',controller_readback_unconfirmed:'readbackUnconfirmed',room_profile_change_required:'profileChange',native_group_limit:'profileCapacity',native_target_limits:'range',native_sensor_binding:'missing',native_resource_binding:'missing',native_config_budget:'programCapacity',native_schedule_limit:'programCapacity'})[error?.code]||'uncertain';}
 async save(){if((this.locked&&!this.canRetryProfile)||(!this.dirty&&!this.needsApply)||this._blockInvalid)return;try{validate(this._settings);}catch(e){this._message=this.t[e.message]||this.t.invalid;this.refreshStatus();return;}const generation=this._generation;this._saving=true;this._message=this.t.saving;this.render();try{const m=await this._hass.callWS({type:'open_thermostat/room/save',...this._config,token:this._model.token,settings:clone(this._settings),...(this.selectionIdentities()?{binding_identities:this.selectionIdentities()}:{})});if(generation!==this._generation)return;this._model=m;this.reset();this._message=m.program_only&&!m.apply_pending?this.t.programDone:this.t.done;}catch(e){if(generation!==this._generation)return;const key=this.errorKey(e);this._message=this.t[key];this._uncertain=['changed','uncertain','missing','active','unsupported','applyUnconfirmed','profileChange'].includes(key);}finally{if(generation===this._generation){this._saving=false;this.render();}}}
 field(parent,key,label,input,help){const wrap=el('div',null,{class:'field'});input.id=key;input.disabled=this.locked||(this._model?.program_only&&(key==='emitter'||(!this._model.profile_editable&&['temperature_entity','minimum_centi_c','maximum_centi_c','maximum_age_ms'].includes(key))));wrap.append(el('label',label,{for:key}),input);if(help)wrap.append(el('small',help));parent.append(wrap);return input;}
 choiceLabel(choice){const status=this.t.deviceStates[choice.status];return choice.label+(status&&choice.status!=='available'?` · ${status}`:'')+(choice.temperature_role==='diagnostic'?` · ${this.t.diagnosticSourceLabel}`:'');}
 selectionIdentities(){const ids=[this._settings.temperature_entity,...this._settings.radiator_entities,...(this._settings.schedule_entity?[this._settings.schedule_entity]:[]),...(this._settings.contact_entities||[]),...(this._settings.setpoint_entity?[this._settings.setpoint_entity]:[]),...(this._settings.presence_entity?[this._settings.presence_entity]:[])];const choices=Object.values(this._model.choices).flat();const selected=ids.map(id=>choices.find(x=>x.value===id));return selected.every(x=>x?.identity)?Object.fromEntries(selected.map(x=>[x.value,clone(x.identity)])):null;}
 select(choices,value,placeholder=this.t.choose){const select=el('select');select.append(el('option',placeholder,{value:''}));for(const x of choices)select.append(el('option',this.choiceLabel(x),{value:x.value}));if(value&&!choices.some(x=>x.value===value))select.append(el('option',value,{value}));select.value=value;return select;}
 number(parent,key,label,value,scale=100,help){const input=el('input',null,{type:'number',step:scale===100?'.1':'.001',required:''});input.value=String(value/scale);input.oninput=()=>{this._settings[key]=scaled(input.value,scale);this._message='';this.refreshStatus();};return this.field(parent,key,label,input,help);}
 // Re-rendering keeps open sections from the shown DOM; a toggle event may still be queued.
 render(){this._vacationStatus=null;this._powerBox=null;const root=this.shadowRoot;const advancedShown=root.querySelector('details.advanced'),comfortShown=root.querySelector('details.room-comfort');if(advancedShown)this._advancedOpen=advancedShown.open;if(comfortShown)this._comfortOpen=comfortShown.open;root.replaceChildren();root.append(el('style',STYLE));const card=el('ha-card');root.append(card);const top=el('header');top.append(el('span','OpenThermostat',{class:'eyebrow'}),el('h1',this.t.title));card.append(top);
 if(!this._model){card.append(el('p',this._message||this.t.load,{role:'status'}),this.button(this.t.reload,()=>this.load(),this._loading));return;}
 const m=this._model,s=this._settings;
 if(m.rooms.length>1){const picker=this.select(m.rooms.map(x=>({value:x.room_id,label:x.name})),this._config.room_id);this.field(card,'room-picker',this.t.room,picker);picker.querySelector('option[value=""]').disabled=true;picker.disabled=this._saving||this._vacationBusy;picker.onchange=()=>{if(this.dirty&&!confirm(this.t.discard)){picker.value=this._config.room_id;return;}this.setConfig({...this._config,room_id:picker.value});};}
 if(m.program_only||m.profile_apply_pending)card.append(el('p',m.profile_apply_pending?this.t.profilePending:m.profile_editable?this.t.profileConnected:this.t.programConnected,{class:'notice'}));
 if(!m.editable)card.append(el('p',m.supported?this.t.active:this.t.unsupported,{class:'notice'}));
 const layout=el('div',null,{class:'layout'}),settings=el('section',null,{class:'settings','aria-label':this.t.title}),planner=el('section',null,{class:'planner','aria-label':this.t.week});layout.append(settings,planner);card.append(layout);
 const name=el('input',null,{type:'text',maxlength:'80',required:''});name.value=s.name;name.oninput=()=>{s.name=name.value;this._message='';this.refreshStatus();};this.field(settings,'name',this.t.name,name,this.t.nameHelp);
 const emitter=el('select');for(const[value,label]of [['radiator',this.t.radiator],['floor',this.t.floor],['combined',this.t.combined]]){const option=el('option',label,{value});option.disabled=value!=='radiator';emitter.append(option);}emitter.value=s.emitter;this.field(settings,'emitter',this.t.emitter,emitter,this.t.emitterHelp);
 const sensor=this.field(settings,'temperature_entity',this.t.sensor,this.select(m.choices.sensor,s.temperature_entity),this.t.sensorHelp);sensor.onchange=()=>{s.temperature_entity=sensor.value;this._message='';this.refreshStatus();};this._sensorState=el('small',null,{class:'binding-state',role:'status'});settings.append(this._sensorState);
 this._temperatureSourceReview=el('small',null,{class:'binding-state temperature-source-review attention',role:'status'});settings.append(this._temperatureSourceReview);
 this._measurementState=el('small',null,{class:'binding-state measurement-state',role:'status'});settings.append(this._measurementState);
 const valves=el('details',null,{class:'valves'});const valveLabel=ids=>ids.map(id=>this.choiceLabel(m.choices.climate.find(x=>x.value===id)||{label:id})).join(', ')||this.t.choose;valves.append(el('summary',valveLabel(s.radiator_entities)));const selected=new Set(s.radiator_entities);for(const x of [...m.choices.climate,...s.radiator_entities.filter(x=>!m.choices.climate.some(y=>x===y.value)).map(x=>({value:x,label:x}))]){const check=el('input',null,{type:'checkbox',value:x.value});check.checked=selected.has(x.value);check.disabled=this.locked||(m.program_only&&!m.profile_editable);const label=el('label',null,{class:'check'});label.append(check,document.createTextNode(this.choiceLabel(x)));check.onchange=()=>{if(check.checked)selected.add(x.value);else selected.delete(x.value);s.radiator_entities=[...selected];valves.querySelector('summary').textContent=valveLabel(s.radiator_entities);this._message='';this.refreshStatus();};valves.append(label);}settings.append(el('label',this.t.valves),valves,el('small',this.t.valvesHelp));this._valveState=el('small',null,{class:'binding-state',role:'status'});settings.append(this._valveState);
 this._review=el('aside',null,{class:'target-review','aria-label':this.t.valveReview});settings.append(this._review);
 this.renderContacts(settings);
 this.renderManualTarget(settings);
 this.renderComfort(settings);
 this.number(settings,'base_centi_c',this.t.base,s.base_centi_c,100,this.t.baseHelp);
 const advanced=el('details',null,{class:'advanced'});advanced.open=!!this._advancedOpen;advanced.append(el('summary',this.t.advanced));settings.append(advanced);
 this.number(advanced,'minimum_centi_c',this.t.min,s.minimum_centi_c,100,this.t.limitsHelp);this.number(advanced,'maximum_centi_c',this.t.max,s.maximum_centi_c,100,this.t.limitsHelp);this.number(advanced,'maximum_age_ms',this.t.age,s.maximum_age_ms,1000,this.t.ageHelp);
 this._powerBox=el('aside',null,{class:'device-power target-review',style:'overflow-wrap:anywhere'});advanced.append(this._powerBox);
 this._metadataBox=el('aside',null,{class:'device-metadata target-review',style:'overflow-wrap:anywhere'});advanced.append(this._metadataBox);
 planner.append(el('h2',this.t.week),el('p',s.program_source==='helper'?this.t.external:this.t.hint,{class:'help'}));this._timeline=el('div',null,{class:'timeline'});planner.append(this._timeline);this._inline=el('div',null,{class:'inline'});planner.append(this._inline);this.renderTimeline();this.renderInline();
 const actions=el('footer');this._save=this.button(this.t.save,()=>this.save());this._save.className='primary';this._cancel=this.button(this.t.cancel,()=>{this.reset();this._message='';this.render();});this._reload=this.button(this.t.reload,()=>{if(!this.dirty||confirm(this._uncertain?this.t.reloadUnconfirmed:this.t.discard))this.load();});this._status=el('p','',{class:'status',role:'status','aria-live':'polite'});actions.append(this._status,this._save,this._cancel,this._reload);card.append(actions,el('small',`${this.t.learning} · ${m.time_zone}`,{class:'fine'}));this.refreshStatus();
 }
 refreshStatus(){this.renderDevicePower();this.renderContactStatus();this.renderManualTargetStatus();this.renderComfortStatus();this.renderVacationStatus();this.renderTemperatureSourceReview();this.renderMeasurementStatus();this.renderBindingStatus();this.renderTargetReview();this.renderMetadata();if(!this._status)return;this._status.textContent=this._message||(this.dirty?this.t.draft:this.needsApply?this.t.programPending:this.t.saved);this._save.textContent=this.canRetryProfile?this.t.profileReapply:this.needsApply&&!this.dirty?this.t.programReapply:this.t.save;this._save.disabled=(this.locked&&!this.canRetryProfile)||(!this.dirty&&!this.needsApply)||this._blockInvalid;this._cancel.disabled=this._loading||this._saving||this._vacationBusy||(!this.dirty&&!this._blockInvalid);this._reload.disabled=this._saving||this._loading||this._vacationBusy;}
 roomStatusState(){
  const m=this._model,state=m?.contact_status_entity?this._hass?.states?.[m.contact_status_entity]:null;
  if(!state)return null;
  const owner=m.status_identity;
  if(owner!==undefined&&(!owner||typeof owner!=='object'||Array.isArray(owner)||owner.entry_id!==m.entry_id||owner.room_id!==m.room_id||state.attributes?.entry_id!==owner.entry_id||state.attributes?.room_id!==owner.room_id))return null;
  return state;
 }
 renderComfort(parent){
  this._comfortStatus=null;const s=this._settings,m=this._model;
  if(!Object.hasOwn(s,'comfort')||!Array.isArray(m.choices.person))return;
  const box=el('details',null,{class:'room-comfort'});box.open=!!this._comfortOpen;
  box.append(el('summary',this.t.comfortTitle),el('p',this.t.comfortHelp,{class:'help'}));
  const enabled=el('input',null,{type:'checkbox',id:'comfort_enabled'});enabled.checked=s.comfort!==null;enabled.disabled=this.locked;
  const label=el('label',null,{class:'check'});label.append(enabled,document.createTextNode(this.t.comfortEnabled));box.append(label);
  let draft=clone(s.comfort||{away_centi_c:1700,frost_centi_c:500,temporary_ms:3600000});
  const fields=el('div');fields.hidden=s.comfort===null;box.append(fields);
  for(const [key,label,scale]of [['away_centi_c',this.t.comfortAway,100],['frost_centi_c',this.t.comfortFrost,100],['temporary_ms',this.t.comfortDuration,60000]]){
   const input=el('input',null,{type:'number',min:scale===100?'5':'1',max:scale===100?'35':'720',step:scale===100?'0.1':'1'});input.value=draft[key]/scale;
   this.field(fields,'comfort_'+key,label,input);input.oninput=()=>{if(s.comfort){s.comfort[key]=scaled(input.value,scale);this._message='';this.refreshStatus();}};
  }
  const presence=this.field(fields,'presence_entity',this.t.comfortPresence,this.select(m.choices.person,s.presence_entity,this.t.comfortNoPresence));
  presence.onchange=()=>{s.presence_entity=presence.value;this._message='';this.refreshStatus();};
  enabled.onchange=()=>{if(enabled.checked)s.comfort=clone(draft);else{draft=clone(s.comfort);s.comfort=null;s.presence_entity='';presence.value='';}fields.hidden=s.comfort===null;this._message='';this.refreshStatus();};
  this._comfortStatus=el('p',null,{class:'comfort-status',role:'status','aria-live':'polite'});box.append(this._comfortStatus);parent.append(box);this.renderComfortStatus();
  this.renderVacation(box);
 }
 renderComfortStatus(){
  const box=this._comfortStatus,s=this._settings,m=this._model;if(!box)return;
  if(JSON.stringify(s.comfort)!==JSON.stringify(m.settings.comfort)||s.presence_entity!==m.settings.presence_entity){box.textContent=this.t.comfortDraft;return;}
  if(s.comfort===null){box.textContent=this.t.comfortDisabled;return;}
  const state=this.roomStatusState();
  if(m.contact_status_entity&&(!state||['unknown','unavailable'].includes(state.state))){box.textContent=this.t.comfortUnavailable;return;}
  const mode=state?.attributes?.comfort_mode,reason=state?.attributes?.firmware_reason;box.textContent=Object.hasOwn(this.t.comfortReasons,reason)?this.t.comfortReasons[reason]:Object.hasOwn(this.t.comfortModes,mode)?this.t.comfortModes[mode]:this.t.comfortConfigured;
 }
 vacationReady(){
  const m=this._model,state=this.roomStatusState();
  return !!(m?.comfort_actions?.contract==='room.comfort.command.v1'&&m.comfort_actions.supports_vacation_dates===true&&m.status_identity&&this._hass?.user?.is_admin&&typeof this._hass.callService==='function'&&m.settings.comfort&&state&&!['unknown','unavailable'].includes(state.state)&&!this.dirty&&!this.needsApply&&!this.locked);
 }
 renderVacation(parent){
  this._vacationStatus=null;const m=this._model;if(m.comfort_actions?.contract!=='room.comfort.command.v1')return;
  const box=el('section',null,{class:'room-vacation'});box.append(el('h4',this.t.vacationTitle),el('p',this.t.vacationHelp,{class:'help'}));
  const end=el('input',null,{type:'datetime-local',step:'60'});end.value=this._vacationLocal||'';
  this.field(box,'vacation_local_end',this.t.vacationEnd+' · '+m.time_zone,end);
  end.oninput=()=>{this._vacationLocal=end.value;this._vacationCandidates=[];this._vacationChoice='';this._vacationNeedsChoice=false;this._vacationMessage='';this.renderVacationStatus();};
  const choices=(this._vacationCandidates||[]).map(c=>({value:c.iso,label:c.iso.replace('T',' ')+' · UTC'+c.utc_offset.replace(/^([+-]\d{2})(\d{2})$/,'$1:$2')}));
  const choose=this.field(box,'vacation_occurrence',this.t.vacationChoose,this.select(choices,this._vacationChoice||''));
  choose.parentNode.hidden=!(this._vacationNeedsChoice||choices.length===2);choose.onchange=()=>{this._vacationChoice=choose.value;this.renderVacationStatus();};
  this._vacationEnd=end;this._vacationOccurrence=choose;
  this._vacationStart=this.button(this.t.vacationStart,()=>this.requestVacation('vacation'));this._vacationCancel=this.button(this.t.vacationCancel,()=>this.requestVacation('auto'));
  box.append(this._vacationStart,this._vacationCancel);
  this._vacationStatus=el('p',null,{class:'vacation-status',role:'status','aria-live':'polite'});box.append(this._vacationStatus);parent.append(box);this.renderVacationStatus();
 }
 renderVacationStatus(){
  if(!this._vacationStatus)return;const ready=this.vacationReady(),state=this.roomStatusState(),until=state?.attributes?.vacation_until_utc;
  this._vacationEnd.disabled=!ready||this._vacationUncertain;
  this._vacationOccurrence.parentNode.hidden=!(this._vacationNeedsChoice||(this._vacationCandidates||[]).length===2);
  this._vacationOccurrence.disabled=!ready||this._vacationUncertain;
  this._vacationStart.disabled=!ready||this._vacationUncertain||!this._vacationLocal||((this._vacationNeedsChoice||(this._vacationCandidates||[]).length===2)&&!this._vacationChoice);
  this._vacationCancel.disabled=!ready||!Number.isSafeInteger(until)||until<=0;
  const base=this._vacationMessage||(this.dirty||this.needsApply?this.t.vacationSave:!ready?this.t.vacationUnavailable:this.t.vacationIdle);
  const reported=state?.attributes?.vacation_ends_at;
  this._vacationStatus.textContent=base+(ready&&Number.isSafeInteger(until)&&until>0&&typeof reported==='string'&&reported.length<=40?' '+this.t.vacationUntil+': '+reported.replace('T',' ')+' · '+this._model.time_zone+'.':'');
 }
 async vacationResult(promise,timeout){
  let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject({code:'vacation_timeout'}),timeout);})]);}finally{clearTimeout(timer);}
 }
 async requestVacation(mode){
  if(!this.vacationReady()||(mode==='vacation'&&(this._vacationUncertain||!this._vacationLocal||((this._vacationNeedsChoice||(this._vacationCandidates||[]).length===2)&&!this._vacationChoice))))return;
  const m=this._model,generation=this._generation,token=m.token,local=this._vacationLocal,zone=m.time_zone,entity=m.contact_status_entity,choice=this._vacationChoice;
  const current=()=>generation===this._generation&&this._model===m&&this._model.token===token&&!this.dirty&&this.isConnected&&document.visibilityState!=='hidden'&&this.roomStatusState()&&!['unknown','unavailable'].includes(this.roomStatusState().state);
  let dispatched=false;this._vacationBusy=true;this._vacationMessage=this.t.vacationChecking;this.render();
  try{
   let iso;
   if(mode==='vacation'){
    const p=await this.vacationResult(this._hass.callWS({type:'open_thermostat/room/vacation_preview',...this._config,token,local_end:local,time_zone:zone}),10000);
    if(!current()){if(generation===this._generation)this._vacationMessage=this.t.vacationStopped;return;}
    if(!validVacationPreview(p,m,token,local,zone,entity))throw {code:'vacation_date_invalid'};
    this._vacationCandidates=p.candidates;
    if(choice&&!p.candidates.some(c=>c.iso===choice)){this._vacationChoice='';this._vacationNeedsChoice=true;this._vacationMessage=this.t.vacationChanged;return;}
    iso=choice||(p.candidates.length===1?p.candidates[0].iso:null);
    if(!iso){this._vacationMessage=this.t.vacationAmbiguous;return;}
   }
   if(!current()){this._vacationMessage=this.t.vacationStopped;return;}
   this._vacationMessage=this.t.vacationSending;this.renderVacationStatus();dispatched=true;
   await this.vacationResult(this._hass.callService('open_thermostat','set_comfort',{entity_id:entity,mode,...(iso?{vacation_until:iso}:{}),expected_entry_id:m.entry_id,expected_room_id:m.room_id,expected_token:token,expected_time_zone:zone}),15000);
   if(current()){this._vacationMessage=this.t.vacationRequested;this._vacationUncertain=false;}else if(generation===this._generation){this._vacationMessage=this.t.vacationUncertain;this._vacationUncertain=true;}
  }catch(error){
   if(generation!==this._generation)return;
   if(dispatched){this._vacationMessage=this.t.vacationUncertain;this._vacationUncertain=true;}
   else {const messages={vacation_timeout:this.t.vacationTimeout,vacation_nonexistent_time:this.t.vacationGap,vacation_date_range:this.t.vacationRange,vacation_date_invalid:this.t.vacationInvalid,vacation_timezone_changed:this.t.vacationZone,vacation_timezone_unavailable:this.t.vacationZone,comfort_controller_unavailable:this.t.vacationUnavailable,setup_changed:this.t.changed,controller_plan_pending:this.t.controllerPending};this._vacationMessage=Object.hasOwn(messages,error?.code)?messages[error.code]:this.t.vacationUnavailable;}
  }finally{if(generation===this._generation){this._vacationBusy=false;this.render();}}
 }
 renderManualTarget(parent){
  this._manualTargetStatus=null;
  const s=this._settings,m=this._model;if(s.setpoint_entity===undefined||!Array.isArray(m.choices.input_number))return;
  const box=el('section',null,{class:'manual-target'});box.append(el('h3',this.t.manualTarget));
  const select=this.field(box,'setpoint_entity',this.t.manualTargetHelper,this.select(m.choices.input_number,s.setpoint_entity,this.t.manualTargetNone),this.t.manualTargetHelp);
  const duration=el('input',null,{type:'number',min:'1',max:'720',step:'1'});duration.value=s.setpoint_duration_ms/60000;
  this.field(box,'setpoint_duration_ms',this.t.manualTargetDuration,duration);duration.disabled=this.locked||!s.setpoint_entity;
  select.onchange=()=>{s.setpoint_entity=select.value;duration.disabled=this.locked||!select.value;this._message='';this.refreshStatus();};
  duration.oninput=()=>{s.setpoint_duration_ms=Number(duration.value)*60000;this._message='';this.refreshStatus();};
  this._manualTargetStatus=el('p',null,{class:'manual-target-status',role:'status','aria-live':'polite'});box.append(this._manualTargetStatus);parent.append(box);this.renderManualTargetStatus();
 }
 renderManualTargetStatus(){
  const box=this._manualTargetStatus,s=this._settings,m=this._model;if(!box||!s||!m)return;
  if(s.setpoint_entity!==m.settings.setpoint_entity||s.setpoint_duration_ms!==m.settings.setpoint_duration_ms){box.textContent=this.t.manualTargetDraft;return;}
  if(!s.setpoint_entity){box.textContent=this.t.manualTargetStates.not_configured;return;}
  const state=this.roomStatusState();
  const status=m.contact_status_entity?(state&&!['unknown','unavailable'].includes(state.state)?state.attributes?.manual_target_source:null):m.manual_target_status;
  box.textContent=typeof status?.status==='string'&&Object.hasOwn(this.t.manualTargetStates,status.status)
   ?this.t.manualTargetStates[status.status]:this.t.manualTargetStates.binding_unavailable;
  const remaining=state?.attributes?.override_remaining_minutes;
  if(state&&!['unknown','unavailable'].includes(state.state)&&state.attributes?.target_source==='temporary'&&Number.isSafeInteger(remaining)&&remaining>0&&remaining<=720)
   box.textContent+=' '+this.t.manualTargetRemaining+': '+remaining+' '+this.t.manualTargetMinutes+'.';
 }
 renderContacts(parent){
  const s=this._settings,m=this._model;
  if(!Array.isArray(s.contact_entities)||!s.contact_policy||!Array.isArray(m.choices.binary_sensor))return;
  const box=el('section',null,{class:'room-contacts'});box.append(el('h3',this.t.contacts),el('small',this.t.contactsHelp));
  const list=el('details',null,{class:'valves contacts'}),selected=new Set(s.contact_entities);
  const label=()=>s.contact_entities.map(id=>this.choiceLabel(m.choices.binary_sensor.find(x=>x.value===id)||{label:id})).join(', ')||this.t.contactsNone;
  list.append(el('summary',label()));
  const options=[...m.choices.binary_sensor,...s.contact_entities.filter(id=>!m.choices.binary_sensor.some(x=>x.value===id)).map(value=>({value,label:value}))];
  for(const item of options){
   const input=el('input',null,{type:'checkbox',value:item.value,'data-contact-choice':''});input.checked=selected.has(item.value);
   input.disabled=this.locked;
   const row=el('label',null,{class:'check'});row.append(input,document.createTextNode(this.choiceLabel(item)));list.append(row);
   input.onchange=()=>{if(input.checked)selected.add(item.value);else selected.delete(item.value);s.contact_entities=[...selected];list.querySelector('summary').textContent=label();this._message='';this.refreshStatus();};
  }
  box.append(list);this._contactStatus=el('p',null,{class:'contact-status',role:'status','aria-live':'polite'});box.append(this._contactStatus);
  const optionsBox=el('details',null,{class:'contact-options'});optionsBox.append(el('summary',this.t.contactsSettings));
  for(const [key,title,min,max] of [['open_delay_ms',this.t.contactOpenDelay,0,600],['close_delay_ms',this.t.contactCloseDelay,0,600],['maximum_age_ms',this.t.contactAge,1,86400]]){
   const input=el('input',null,{type:'number',step:'1',min:String(min),max:String(max)});input.value=s.contact_policy[key]/1000;
   this.field(optionsBox,'contact_'+key,title,input,key==='maximum_age_ms'?this.t.contactAgeHelp:null);
   input.disabled=this.locked;
   input.oninput=()=>{s.contact_policy[key]=Number(input.value)*1000;this._message='';this.refreshStatus();};
  }
  box.append(optionsBox);parent.append(box);this.renderContactStatus();
 }
 renderContactStatus(){
  const box=this._contactStatus,m=this._model,s=this._settings;if(!box||!m||!s)return;
  if(JSON.stringify(s.contact_entities)!==JSON.stringify(m.settings.contact_entities)||JSON.stringify(s.contact_policy)!==JSON.stringify(m.settings.contact_policy)){box.textContent=this.t.contactDraft;return;}
  if(!s.contact_entities?.length){box.textContent=this.t.contactsNone;return;}
  const state=this.roomStatusState();
  const status=m.contact_status_entity?(state&&!['unknown','unavailable'].includes(state.state)?state.attributes?.comfort_context_sources?.contacts:null):m.contact_status;
  const valid=status&&Number.isInteger(status.count)&&status.count===s.contact_entities.length&&Object.hasOwn(this.t.contactReasons,status.reason)&&Number.isSafeInteger(status.pending_ms)&&status.pending_ms>=0&&status.pending_ms<=600000;
  box.textContent=valid?this.t.contactReasons[status.reason]:this.t.contactWaiting;
  if(valid&&status.pending_ms)box.textContent+=' '+this.t.contactRemaining+': '+Math.ceil(status.pending_ms/1000)+' '+this.t.contactSeconds+'.';
 }
 renderTemperatureSourceReview(){
  const box=this._temperatureSourceReview;if(!box||!this._model)return;
  const saved=this._settings.temperature_entity===this._model.settings.temperature_entity;
  const choice=this._model.choices.sensor.find(x=>x.value===this._settings.temperature_entity);
  const reason=(saved?this._model.temperature_source_review?.reason:null)||(choice?.temperature_role==='diagnostic'?'diagnostic_entity':null);
  box.textContent=this.t.temperatureSourceReasons[reason]||'';box.hidden=!box.textContent;
 }
 renderMeasurementStatus(){
  if(!this._measurementState)return;
  const m=this._model,changed=this._settings.temperature_entity!==m.settings.temperature_entity;
  const status=changed?'pending':m.measurement?.status,text=this.t.measurementStates[status];
  const report=changed?null:m.measurement?.original_report;
  const original=report?.control_qualified===false&&report?.acquisition_age_verified===false?this.t.originalReportStates[report.status]:null;
  this._measurementState.textContent=(text?`${this.t.measurementTitle}: ${text}`:'')+(original?' '+original:'');
 }
 renderBindingStatus(){if(this._valveState)this._valveState.textContent=this._settings.radiator_entities.some(id=>id.startsWith('unresolved:'))?this.t.deviceHint:'';if(!this._sensorState)return;const item=this._model.choices.sensor.find(x=>x.value===this._settings.temperature_entity);this._sensorState.textContent=item?.status?`${this.t.sensorState}: ${this.t.deviceStates[item.status]||this.t.deviceStates.unknown}.`+(item.value.startsWith('unresolved:')?' '+this.t.deviceHint:''):'';}
 renderTargetReview(){
  const box=this._review;if(!box||!this._model)return;box.replaceChildren();
  box.append(el('h3',this.t.valveReview),el('small',this.t.reviewScope));
  const saved=this._model.settings,draft=this._settings;
  const fields=['radiator_entities','minimum_centi_c','maximum_centi_c','base_centi_c','program_source','schedule_entity','week'];
  if(this._blockInvalid||fields.some(k=>JSON.stringify(saved[k])!==JSON.stringify(draft[k]))){
   box.append(el('p',this.t.reviewPending,{class:'attention'}));
  }else{
   const review=this._model.actuator_target_review;
   if(!review||review.scope!=='saved_local_room_targets'||review.authorizes_actuation!==false||!review.actuators?.length){
    box.append(el('p',this.t.reviewUnavailable));
   }else{
    const format=x=>new Intl.NumberFormat(this._hass.language||'en',{maximumFractionDigits:2}).format(x);
    for(const row of review.actuators){
     const article=el('article');
     article.append(el('strong',this.choiceLabel(this._model.choices.climate.find(x=>x.value===row.entity_id)||{label:row.entity_id})));
     const cap=row.capability;
     if(row.status==='unknown'||!cap){article.append(el('p',this.t.reviewUnknown,{class:'attention'}));}
     else{
      article.append(el('p',`${format(cap.minimum)}–${format(cap.maximum)} ${cap.unit} · ${this.t.reviewStep} ${format(cap.step)} ${cap.unit}`));
      if(row.issues.includes('room_limits_exceed_actuator'))article.append(el('p',this.t.reviewLimits,{class:'attention'}));
      if(row.targets.length){
       const details=el('details'),list=el('ul');details.append(el('summary',`${this.t.reviewDetails} (${row.targets.length})`));
       for(const target of row.targets){
        const[day,index]=target.where.split('/'),block=saved.week[day]?.[Number(index)];
        const label=target.where==='base'?this.t.reviewBase:block?`${this.t.days[DAYS.indexOf(day)]} ${clock(block.start)}–${clock(block.end)}`:target.where;
        const outcome=target.issue==='target_will_round'?`${this.t.reviewRounds} ${format(target.native_result)} ${target.unit}`:this.t.reviewOutside;
        list.append(el('li',`${label}: ${format(target.requested_celsius)} °C ${outcome}.`));
       }
       details.append(list);article.append(details);
      }
     }
     const mode=row.operating_mode;
     if(mode?.profile==='TV02-Zigbee'&&mode.scope==='reported_ha_operating_mode'&&mode.authorizes_actuation===false&&Array.isArray(mode.issues)){
      for(const reason of mode.issues)article.append(el('p',this.t.reviewModes[reason]||this.t.reviewModes.operating_mode_unknown,{class:'attention'}));
     }
     if(mode?.profile==='TV02-Zigbee'||row.original_report)this.renderOriginalValveReport(article,row.original_report);
     box.append(article);
    }
    if(review.external_program_present)box.append(el('p',this.t.reviewExternal,{class:'attention'}));
    if(review.status==='compatible'&&!review.external_program_present)box.append(el('p',this.t.reviewFits));
   }
  }
  box.append(el('small',this.t.reviewDisclaimer));
 }
 renderOriginalValveReport(parent,report){
  const box=el('section',null,{class:'original-valve-report'});parent.append(box);
  box.append(el('h4',this.t.valveReportTitle));
  const recognized=report&&report.command_correlated===false&&report.valve_ready===false&&report.control_qualified===false&&
   typeof report.status==='string'&&Object.hasOwn(this.t.valveReportStates,report.status);
  let valid=!!recognized;
  const fresh=recognized&&report.status==='received_unqualified',fields=report?.fields;
  const number=(value,min,max,step=1)=>Number.isSafeInteger(value)&&value>=min&&value<=max&&value%step===0;
  const validators={target_centi_c:value=>number(value,500,3000,50),local_temperature_centi_c:value=>number(value,0,6000,10),
   preset:value=>typeof value==='string'&&Object.hasOwn(this.t.valveReportPresets,value),
   heating_stop:value=>typeof value==='boolean',frost_protection:value=>typeof value==='boolean'};
  if(fresh)valid=number(report.received_age_ms,0,86400000)&&fields&&typeof fields==='object'&&!Array.isArray(fields)&&
   Object.keys(fields).length>=1&&Object.keys(fields).length<=5&&
   Object.entries(fields).every(([key,value])=>Object.hasOwn(validators,key)&&validators[key](value));
  box.append(el('p',valid?this.t.valveReportStates[report.status]:this.t.valveReportUnavailable));
  if(fresh&&valid){
   const format=value=>new Intl.NumberFormat(this._hass.language||'en',{maximumFractionDigits:2}).format(value);
   box.append(el('small',`${this.t.valveReportAge}: ${format(report.received_age_ms/1000)} ${this.t.valveReportSeconds}`));
   const list=el('dl');
   for(const key of Object.keys(this.t.valveReportFields)){
    if(!Object.hasOwn(fields,key))continue;
    const value=fields[key];
    const text=key.endsWith('_centi_c')?`${format(value/100)} °C`:key==='preset'?this.t.valveReportPresets[value]:value?this.t.valveReportOn:this.t.valveReportOff;
    list.append(el('dt',this.t.valveReportFields[key]+':'),el('dd',text));
   }
   box.append(list);
  }
  // Optional reception-only metadata survives expiry; field values do not.
  const reception=report?.last_reception;
  if(valid&&['received_unqualified','stale'].includes(report.status)&&reception&&reception.scope==='reception_only'&&
   typeof reception.message_kind==='string'&&Object.hasOwn(this.t.valveReceptionKinds,reception.message_kind)&&
   (reception.received_age_ms===null||number(reception.received_age_ms,0,Number.MAX_SAFE_INTEGER))&&
   Array.isArray(reception.properties)&&reception.properties.length>=1&&reception.properties.length<=5&&
   new Set(reception.properties).size===reception.properties.length&&
   reception.properties.every(key=>typeof key==='string'&&Object.hasOwn(this.t.valveReportFields,key))){
   const details=el('div',null,{class:'valve-reception-metadata'});
   details.append(el('h4',this.t.valveReceptionTitle),el('p',this.t.valveReceptionKinds[reception.message_kind]));
   const age=reception.received_age_ms;
   details.append(el('p',age===null?this.t.valveReceptionAgeUnknown:
    `${this.t.valveReportAge}: ${new Intl.NumberFormat(this._hass.language||'en',{maximumFractionDigits:2}).format(age/1000)} ${this.t.valveReportSeconds}`));
   details.append(el('p',`${this.t.valveReceptionProperties}: ${reception.properties.map(key=>this.t.valveReportFields[key]).join(', ')}`));
   box.append(details);
  }
  box.append(el('small',this.t.valveReportDisclaimer));
 }
 renderTimeline(){const box=this._timeline;box.replaceChildren();if(this._settings.program_source==='helper')return;const axis=el('div',null,{class:'axis'});axis.append(el('span'));const times=el('div');for(const n of ['00','06','12','18','24'])times.append(el('span',n));axis.append(times,el('span'));box.append(axis);
 DAYS.forEach((day,i)=>{const row=el('div',null,{class:'day'});row.append(el('strong',this.t.days[i],{class:'day-name'}));const track=el('div',null,{class:'track',tabindex:this.locked?'-1':'0',role:'button','aria-label':`${this.t.days[i]} · ${this.t.add}`});row.append(track);const blocks=this._settings.week[day];for(const b of blocks){const chosen=this._selected?.block===b;const button=this.button('',()=>this.choose(day,b),this.locked);button.className='block'+(chosen?' selected':'');button.style.left=`${b.start/864}%`;button.style.width=`${(b.end-b.start)/864}%`;const label=`${this.t.days[i]} ${clock(b.start)}–${clock(b.end)} · ${b.target_centi_c/100} °C`;button.setAttribute('aria-label',label);button.title=label;button.append(el('b',`${b.target_centi_c/100}°`),el('small',`${clock(b.start)}–${clock(b.end)}`));button.onpointerdown=e=>{e.stopPropagation();if(!this.locked)this.gesture(e,track,day,b);};track.append(button);}if(!blocks.length)track.append(el('span',this.t.empty,{class:'empty'}));track.onpointerdown=e=>{if(!this.locked)this.gesture(e,track,day);};track.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target===track){e.preventDefault();this.add(day);}};const copy=this.button('⧉',()=>{this._copyDay=day;this.renderInline();},this.locked);copy.setAttribute('aria-label',`${this.t.copy}: ${this.t.days[i]}`);copy.title=this.t.copy;row.append(copy);box.append(row);});
 const add=this.button(this.t.add,()=>this.add('monday'),this.locked);add.className='add';box.append(add);
 }
 choose(day,block){this._selected={day,block};this._copyDay=null;this._blockInvalid=false;this.renderTimeline();this.renderInline();this.refreshStatus();}
 add(day){if(this.locked)return;const blocks=[...this._settings.week[day]].sort((a,b)=>a.start-b.start);let start=7*3600;for(let n=0;n<25;n++){if(start>=86400)start=0;const end=Math.min(start+3600,86400);if(!blocks.some(b=>start<b.end&&end>b.start)){this.insert(day,{start,end,target_centi_c:this._settings.base_centi_c});return;}start+=3600;}this._message=this.t.overlap;this.refreshStatus();}
 insert(day,b){const candidate=clone(this._settings);candidate.week[day].push(b);try{validate(candidate);}catch(e){this._message=this.t[e.message]||this.t.invalid;this.refreshStatus();return;}this._settings.week[day].push(b);this._settings.week[day].sort((a,b)=>a.start-b.start);this._message='';this.choose(day,b);}
 gesture(event,track,day,block){if(event.button!==0)return;event.preventDefault();const rect=track.getBoundingClientRect(),snap=x=>Math.max(0,Math.min(86400,Math.round((x-rect.left)/rect.width*96)*900)),origin=snap(event.clientX),old=block?{...block}:null;// Keep a move area in every block. On touch, narrow blocks move as a whole;
 // their exact start/end remain editable in the selected-block fields.
 const width=old?(old.end-old.start)/86400*rect.width:0;
 const edgeSize=event.pointerType==='touch'&&width<44?0:Math.min(10,width/4);
 const edge=block?(edgeSize>0&&event.clientX-(rect.left+block.start/86400*rect.width)<edgeSize?'start':edgeSize>0&&(rect.left+block.end/86400*rect.width)-event.clientX<edgeSize?'end':'move'):'new';const ghost=el('span',null,{class:'ghost'});track.append(ghost);track.setPointerCapture(event.pointerId);let last=origin,moved=false;
 const preview=()=>{let start,end;if(!old){start=Math.min(origin,last);end=Math.max(origin,last);if(start===end){start=Math.min(start,85500);end=Math.min(start+3600,86400);}}else if(edge==='start'){start=Math.min(last,old.end-900);end=old.end;}else if(edge==='end'){start=old.start;end=Math.max(last,old.start+900);}else{start=Math.max(0,Math.min(86400-(old.end-old.start),old.start+last-origin));end=start+old.end-old.start;}return {start,end,target_centi_c:old?.target_centi_c??this._settings.base_centi_c};};
 const show=()=>{const b=preview();ghost.style.left=`${b.start/864}%`;ghost.style.width=`${(b.end-b.start)/864}%`;ghost.textContent=`${clock(b.start)}–${clock(b.end)}`;};show();
 const move=e=>{last=snap(e.clientX);if(Math.abs(e.clientX-event.clientX)>4)moved=true;show();};
 const cleanup=()=>{track.removeEventListener('pointermove',move);track.removeEventListener('pointerup',up);track.removeEventListener('pointercancel',cancel);if(track.hasPointerCapture(event.pointerId))track.releasePointerCapture(event.pointerId);ghost.remove();};
 const cancel=()=>cleanup();const up=e=>{cleanup();if(old&&!moved){this.choose(day,block);return;}const b=preview();if(!old){this.insert(day,b);return;}const settings=clone(this._settings),idx=this._settings.week[day].indexOf(block);settings.week[day][idx]=b;try{validate(settings);Object.assign(block,b);this._settings.week[day].sort((a,b)=>a.start-b.start);this._message='';this.choose(day,block);}catch(err){this._message=this.t[err.message]||this.t.invalid;this.refreshStatus();}};track.addEventListener('pointermove',move);track.addEventListener('pointerup',up);track.addEventListener('pointercancel',cancel);
 }
 renderInline(){const box=this._inline;box.replaceChildren();if(this._settings.program_source==='helper')return;
 if(this._copyDay){box.append(el('h3',`${this.t.copy}: ${this.t.days[DAYS.indexOf(this._copyDay)]}`),el('small',this.t.copyHelp));const checks=[];const days=el('div',null,{class:'copy-days'});DAYS.forEach((d,i)=>{if(d===this._copyDay)return;const c=el('input',null,{type:'checkbox',value:d});c.disabled=this.locked;const label=el('label',null,{class:'check'});label.append(c,document.createTextNode(this.t.days[i]));checks.push(c);days.append(label);});box.append(days,this.button(this.t.applyCopy,()=>{const targets=checks.filter(x=>x.checked).map(x=>x.value);if(!targets.length){this._message=this.t.copyInvalid;this.refreshStatus();return;}const s=clone(this._settings);for(const d of targets)s.week[d]=clone(s.week[this._copyDay]);try{validate(s);for(const d of targets)this._settings.week[d]=s.week[d];this._selected=null;this._copyDay=null;this._message='';this.renderTimeline();this.renderInline();this.refreshStatus();}catch(e){this._message=this.t[e.message]||this.t.invalid;this.refreshStatus();}},this.locked));return;}
 if(!this._selected){box.append(el('p',this.t.pick,{class:'help'}));const entries=[];DAYS.forEach((d,i)=>this._settings.week[d].forEach((b,j)=>entries.push({value:d+':'+j,label:`${this.t.days[i]} ${clock(b.start)}–${clock(b.end)} · ${b.target_centi_c/100} °C`})) );if(entries.length){const picker=this.field(box,'pick-block',this.t.pickBlock,this.select(entries,'',this.t.pickBlock));picker.onchange=()=>{if(picker.value){const[d,i]=picker.value.split(':');this.choose(d,this._settings.week[d][+i]);}};}return;}
 const{day,block}=this._selected;box.append(el('h3',`${this.t.selected} · ${this.t.days[DAYS.indexOf(day)]}`));const fields=el('div',null,{class:'block-fields'});box.append(fields);const start=el('input',null,{type:'text',inputmode:'numeric',placeholder:'07:00'}),end=el('input',null,{type:'text',inputmode:'numeric',placeholder:'09:00'}),temperature=el('input',null,{type:'number',step:'.1',min:this._settings.minimum_centi_c/100,max:this._settings.maximum_centi_c/100});start.value=clock(block.start);end.value=clock(block.end);temperature.value=String(block.target_centi_c/100);this.field(fields,'block-start',this.t.start,start);this.field(fields,'block-end',this.t.end,end);this.field(fields,'block-temperature',this.t.temp,temperature);
 const update=()=>{try{const next={start:seconds(start.value),end:seconds(end.value),target_centi_c:scaled(temperature.value,100)},s=clone(this._settings),idx=this._settings.week[day].indexOf(block);s.week[day][idx]=next;validate(s);Object.assign(block,next);this._settings.week[day].sort((a,b)=>a.start-b.start);this._blockInvalid=false;this._message='';this.renderTimeline();}catch(e){this._blockInvalid=true;this._message=this.t[e.message]||this.t.invalid;}this.refreshStatus();};for(const input of [start,end,temperature])input.oninput=update;
 const remove=this.button(this.t.remove,()=>{this._settings.week[day]=this._settings.week[day].filter(b=>b!==block);this._selected=null;this._blockInvalid=false;this._message='';this.renderTimeline();this.renderInline();this.refreshStatus();},this.locked);remove.className='danger';box.append(remove);
 }
}
const STYLE=`:host{display:block;color:var(--primary-text-color,#233044);--accent:#e67638;--soft:color-mix(in srgb,var(--accent) 10%,var(--card-background-color,#fff))}*{box-sizing:border-box}ha-card{display:block;background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:22px;padding:26px;max-width:1440px;margin:auto}header{margin-bottom:24px}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:.7rem;font-weight:700;color:var(--secondary-text-color,#657388)}h1{margin:6px 0;font-size:1.7rem;letter-spacing:-.03em}h2{font-size:1.25rem;margin:0 0 8px}h3{font-size:.95rem;margin:0 0 12px}.layout{display:grid;grid-template-columns:minmax(210px,290px) minmax(0,1fr);gap:30px}.settings{padding-right:24px;border-right:1px solid var(--divider-color,#e4e9ef)}.field{margin-bottom:18px}label{display:block;font-size:.85rem;font-weight:600;margin-bottom:7px}small,.help{display:block;font-size:.8rem;line-height:1.5;color:var(--secondary-text-color,#637184)}.field small{margin-top:6px}.binding-state{margin:-10px 0 18px;line-height:1.5;overflow-wrap:anywhere}.help{margin:0 0 18px}input,select{font:inherit;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#cbd5df);padding:10px 11px;border-radius:10px;width:100%;min-height:44px}input:disabled,select:disabled{opacity:.6}button{font:inherit;border:1px solid var(--divider-color,#d5dee7);background:transparent;color:inherit;border-radius:10px;padding:9px 13px;min-height:44px;cursor:pointer}button:hover{background:var(--soft)}button:disabled{opacity:.45;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible,[tabindex]:focus-visible,summary:focus-visible{outline:3px solid var(--primary-color,#079cc2);outline-offset:2px}details{border:1px solid var(--divider-color,#e1e7ed);border-radius:12px;padding:11px;margin:8px 0 16px}.target-review{border:1px solid var(--divider-color,#e1e7ed);border-radius:12px;padding:14px;margin:16px 0 20px;overflow-wrap:anywhere}.target-review h3{margin:0 0 8px}.target-review p{font-size:.8rem;line-height:1.5;margin:8px 0}.target-review article+article{border-top:1px solid var(--divider-color,#e1e7ed);padding-top:8px;margin-top:12px}.original-valve-report{border-top:1px solid var(--divider-color,#e1e7ed);margin-top:12px;padding-top:10px}.original-valve-report h4{font-size:.82rem;margin:0 0 8px}.original-valve-report dl{font-size:.78rem;line-height:1.5;margin:8px 0}.original-valve-report dt{font-weight:600}.original-valve-report dd{margin:0 0 7px}.target-review strong{font-size:.85rem}.target-review .attention{border-left:3px solid var(--accent);padding-left:9px}.target-review details{padding:8px;margin:10px 0}.target-review li{font-size:.78rem;line-height:1.5;margin:7px 0}.target-review ul{padding-left:18px;margin:8px 0}.target-review small{font-size:.72rem}summary{cursor:pointer;font-size:.85rem;font-weight:600;min-height:24px}.advanced{margin-top:22px}.advanced[open] summary{margin-bottom:18px}.check{display:flex;gap:9px;align-items:center;font-weight:400;margin:10px 0}.check input{width:20px;min-height:20px;flex:none}.axis,.day{display:grid;grid-template-columns:83px minmax(0,1fr) 38px;gap:7px;align-items:center}.axis>div{display:flex;justify-content:space-between;font-size:.7rem;color:var(--secondary-text-color,#708094)}.axis{margin:20px 0 8px}.day{margin-bottom:8px}.day-name{font-size:.78rem}.day>button{border:0;padding:4px;min-width:34px;font-size:1.3rem}.track{height:62px;border-radius:9px;position:relative;background:repeating-linear-gradient(to right,transparent 0,transparent calc(25% - 1px),var(--divider-color,#dce4ed) calc(25% - 1px),var(--divider-color,#dce4ed) 25%),var(--secondary-background-color,#f2f5f8);touch-action:pan-y;cursor:crosshair;overflow:hidden}.block{position:absolute;top:5px;bottom:5px;min-height:0;padding:4px 2px;border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);border-radius:6px;background:var(--soft);overflow:hidden;cursor:ew-resize;color:var(--primary-text-color,#243449);user-select:none}.block b{font-size:.88rem;display:block}.block small{font-size:.59rem;white-space:nowrap;overflow:hidden;color:inherit}.block.selected{background:var(--accent);color:#fff;border-color:var(--accent)}.empty{position:absolute;left:9px;top:22px;font-size:.72rem;color:var(--secondary-text-color,#8b98a8);pointer-events:none}.ghost{position:absolute;top:0;bottom:0;background:#e6763866;border:2px dashed var(--accent);font-size:.65rem;pointer-events:none;z-index:3;padding:6px;white-space:nowrap}.add{margin:10px 0 0}.inline{background:var(--secondary-background-color,#f5f7fa);padding:17px;border-radius:14px;margin-top:20px}.block-fields{display:grid;grid-template-columns:1fr 1fr 1.15fr;gap:10px}.block-fields .field{margin-bottom:12px;min-width:0}.danger{color:var(--error-color,#b54335);background:var(--card-background-color,#fff)}.copy-days{display:flex;flex-wrap:wrap;gap:4px 15px}footer{display:flex;gap:10px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--divider-color,#e1e7ed);padding-top:18px;margin-top:25px}.status{flex:1 1 260px;font-size:.85rem;line-height:1.5;font-weight:600;margin:0}.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}.primary:hover{background:#d5662c}.fine{margin-top:13px;font-size:.72rem}.notice{padding:14px;border-radius:12px;background:var(--soft);line-height:1.5}@media(max-width:720px){ha-card{padding:18px;border-radius:16px}.layout{grid-template-columns:1fr;gap:25px}.settings{border:0;border-bottom:1px solid var(--divider-color,#e1e7ed);padding:0 0 15px}.axis,.day{grid-template-columns:64px minmax(0,1fr) 30px;gap:4px}.day-name{font-size:.7rem}.block small{display:none}.block b{font-size:.72rem}.empty{font-size:.61rem;left:5px}.block-fields{gap:7px}.block-fields label{font-size:.72rem}.block-fields input{padding:9px 5px}footer{padding-bottom:10px}footer .primary{flex:1}footer .status{flex-basis:100%}.fine{margin-top:6px}}`;
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws.
const ensureDefined = (name, cls) => {
 let own = cls;
 const check = () => {
  try { if (!customElements.get(name)) { customElements.define(name, own); own = class extends cls {}; } }
  catch (e) { own = class extends cls {}; }
 };
 check();
 if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', check, {once: true});
 if (document.readyState !== 'complete') window.addEventListener('load', check, {once: true});
 for (const ms of [0, 250, 1000, 3000, 10000]) setTimeout(check, ms);
 window.addEventListener('location-changed', check);
 return check;
};
// Versioned managed tag prevents an already registered old editor winning after an update.
ensureDefined('openthermostat-room-editor-v42',OpenThermostatRoomEditor);
// Older tags and manually created old cards (openthermostat-week-planner); the managed dashboard uses the v42 tag.
for(const name of ['openthermostat-room-editor-v41','openthermostat-room-editor-v38','openthermostat-room-editor-v35',
 'openthermostat-room-editor-v28','openthermostat-room-editor-v25','openthermostat-room-editor-v24',
 'openthermostat-room-editor','openthermostat-week-planner'])ensureDefined(name,class extends OpenThermostatRoomEditor{});
