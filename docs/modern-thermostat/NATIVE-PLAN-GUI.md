# Native plan GUI — bestaande flow, eerlijke status

Vervolg op a8408b7 (twee complete logische shadowkamerrecords), geen heraanbod van het afzonderlijk geaccepteerde Stage48 éénkamer-SOURCE-increment. Dezelfde optiesflow en dezelfde prepare/review/apply/status-methodes blijven; geen tweede applyflow, controller, worker, Store, scheduler of readinesspad.

## Bewezen gebreken en gerichte correctie

Drie echte native Engelse vertalings-/C++proeven faalden vóór de bronfix: review noemde een compleet tweekamerplan uitsluitend DATA; na exact geverifieerd readback zei de GUI nog 'Fresh plan readback required'; een echte C++config-ACK was niet zichtbaar omdat die nieuwe revisie/oudesessie niet door de algemene same_config-filter hoort. Eerste onjuiste testloader-run is apart als harnessfout bewaard, niet productbewijs.

Review toont nu de werkelijke scope, permanente kamer-ID’s, namen, twee doelen in °C en de daadwerkelijk gecompileerde UTCschemaovergangen/afloop. De bestaande versiegrens van acht overgangen wordt zichtbaar genoemd, niet verborgen. Annuleren blijft niet verzenden. Status geeft heldere staged/pending/ACK/readback/conflict/offline/onbekend-teksten; technisch onderscheid DATA versus shadowcontrol en fysieke outputs uit blijft expliciet. Een verlopen verificatie kan niet door een gecachete 'shadow_ready'-code als actueel worden beschreven.

De ACK-indicatie is één niet-persistent enum in de bestaande client. Alleen exact veldschema, bekende requestsequence, huidige session/boot/owner-SOURCE, passende targetrevisie/digest en oorspronkelijke send/deadline mogen acknowledged_unverified tonen. Een ACK promoveert nooit journal/readback/ready en vernieuwt geen last_rx/grant/lease/sample. Ongeldige/replayed/retained/late/extra-private waarden worden niet als gebruikersprose weerspiegeld. Bestaande failure/STOP-afhandeling blijft. Reconnect/configsessiewissel wist ACK; de GUI zegt eerlijk 'geen huidige ACK bewaard', niet 'nooit ontvangen'.

Refresh leest bestaande status, doet geen extra publish/save/reload en kan niets heractiveren. Een gesloten bestaande client/worker toont offline met False, niet de oude geverifieerde toestand. Graph-DATA blijft nooit SOURCE-/actuatorvrijgave. Alleen Engelse strings en EN-vertaling zijn in deze stap herzien; andere taalresources zijn historisch behouden, geen nieuwe meertalige productacceptatieclaim.

## Bewijs en grenzen

Actuele native HA2026.10.2 loader/OptionsManager/vertalingen/Store/registry/lifecycle en echte C++ finite peer, waarbij SOURCE/report/safety/MQTT/clock/reload expliciete synthetische grenzen blijven. Gerenderde echte Engelse formteksten en states worden als JSONL opgeslagen voor controle. Dat is GEEN echte HAfrontend/browser of mobiele/desktop screenshot/performancebewijs.

Sandbox heeft geen Node/Chromium/hass_frontend of callable browser. Visuele acceptatie moet op de bestaande parenthost met echte native HAfrontend volgen; geen nieuw framework/custom renderer/browserinstallatie om PASS te simuleren. Fysieke/producer/factory/image/resource/licensegates en alle14F9afwijzingen blijven intact.

Rollback alleen dit nieuwe bronpakket vóór dependents; geen journal/config/roomidentity/model/Recorder/history/noticewijziging of erase. Canonical PLAN/WORKBOARD uitsluitend parent. Geen installatie/publicatie/login/broker/device/EMS/TX/actuator/verwarmingsactie. Hele PLAN IN_PROGRESS; daarna oude journal-/profielevolutie en werkelijke ondersteunde productiebronbinding verder afwerken.
