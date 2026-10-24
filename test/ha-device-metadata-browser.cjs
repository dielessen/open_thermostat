// Shipped HA editor in Chromium; synthetic authenticated WS, never live HA.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const output=path.resolve(process.env.OPENTHERMOSTAT_METADATA_EVIDENCE||path.join(root,'out/ha-metadata-browser'));
const source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const days=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const initial={entry_id:'fixture-entry',room_id:'fixture-room',supported:true,editable:true,
 measurement:{status:'profile_missing',usable:false,original_report:{status:'received_unqualified',control_qualified:false,acquisition_age_verified:false}},
 rooms:[{room_id:'fixture-room',name:'Fixture room'}],token:'0'.repeat(64),time_zone:'Europe/Amsterdam',
 choices:{sensor:[{value:'sensor.fixture',label:'Room sensor',status:'available'}],climate:[{value:'climate.fixture',label:'Room valve',status:'available'}],schedule:[]},
 settings:{name:'Fixture room',emitter:'radiator',temperature_entity:'sensor.fixture',radiator_entities:['climate.fixture'],base_centi_c:2100,minimum_centi_c:500,maximum_centi_c:3000,maximum_age_ms:120000,program_source:'local',schedule_entity:'',week:Object.fromEntries(days.map(d=>[d,[]]))}};
const metadata={bridge:{version:'2.14.2',zigbee_herdsman_converters_version:'26.115.1'},metadata_only:true,physical_control_qualified:false,measurement_acquisition_verified:false,
 devices:[{entity_id:'sensor.fixture',sensor_property:'device_temperature',definition_observed:true,vendor:'Fixture',model:'Sensor',declared_features:[{role:'device_temperature',published:true,settable_declared:false}],declared_options:[]},
 {entity_id:'climate.fixture',definition_observed:true,vendor:'Fixture',model:'<img src=x onerror=alert(1)>',declared_features:[{role:'setpoint',published:true,settable_declared:true,value_min:5,value_max:30,unit:'°C'}],declared_options:[{role:'calibration',settable_declared:true}]}]};
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [viewportName,viewport]of [['desktop',{width:1440,height:1100}],['mobile',{width:390,height:844}],['narrow',{width:320,height:844}]])for(const language of ['nl','en']){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<style>body{margin:0;font:14px Arial,sans-serif}</style><main></main>');
  await page.evaluate(()=>{customElements.define('ha-card',class extends HTMLElement{});customElements.define('openthermostat-room-editor-v15',class extends HTMLElement{});});
 await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({initial,metadata,language})=>{
   window.model=structuredClone(initial);window.metadata=structuredClone(metadata);window.calls=[];window.mode='ok';
   const card=window.card=document.createElement('openthermostat-room-editor-v28');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   card.hass={language,user:{is_admin:true},callWS:async request=>{
    calls.push(structuredClone(request));
    if(request.type==='open_thermostat/room/get')return {...structuredClone(model),room_id:request.room_id};
    if(request.type==='open_thermostat/room/device_metadata'){
     if(mode==='failure')throw Error('private remote response');
     if(mode==='hold')return new Promise(resolve=>window.releaseMetadata=()=>resolve(structuredClone(window.metadata)));
     return structuredClone(window.metadata);
    }
    throw Error('Unexpected or write request');
   }};
  },{initial,metadata,language});
  const nl=language==='nl',card=page.locator('openthermostat-room-editor-v28');await card.locator('#name').waitFor();
  assert.match(await card.locator('.measurement-state').innerText(),nl?/oorspronkelijk sensorbericht is ontvangen/:/original sensor report was received/);
  assert.match(await card.locator('.measurement-state').innerText(),nl?/getoetst meetprofiel ontbreekt/:/reviewed measurement profile is still missing/);
  await page.evaluate(()=>{card._model.measurement.original_report.status='stale';card.renderMeasurementStatus();});
  assert.match(await card.locator('.measurement-state').innerText(),nl?/sensorbericht is te oud/:/sensor report is too old/);
  await page.evaluate(()=>{card._model.measurement.original_report.status='<img src=x onerror=alert(1)>';card.renderMeasurementStatus();});
  assert.equal(await card.locator('img').count(),0);
  assert(!((await card.locator('.measurement-state').innerText()).includes('<img')));
  await page.evaluate(()=>{card._model.measurement.original_report.status='received_unqualified';card._settings.temperature_entity='sensor.draft';card.renderMeasurementStatus();});
  assert(!((await card.locator('.measurement-state').innerText()).includes(nl?'oorspronkelijk sensorbericht is ontvangen':'original sensor report was received')));
  assert.match(await card.locator('.measurement-state').innerText(),nl?/Sla de nieuwe sensorkoppeling op/:/Save the new sensor binding/);
  await page.evaluate(()=>{card._settings.temperature_entity=model.settings.temperature_entity;card.renderMeasurementStatus();});
  assert.equal(await page.evaluate(()=>calls.length),1); // Never automatic broker reads.
  await card.locator('.advanced summary').first().click();
  const read=()=>card.getByRole('button',{name:nl?'Apparaatinformatie controleren':'Check device information',exact:true});
  await read().click();await card.locator('.device-metadata article').first().waitFor();
  assert.equal(await card.locator('.device-metadata article').count(),2);
  assert.match(await card.locator('.device-metadata').innerText(),nl?/apparaattemperatuur/:/device temperature/);
  assert.match(await card.locator('.device-metadata').innerText(),nl?/niet vermeld in de apparaatdefinitie/:/not listed in the device definition/);
  assert.equal(await card.locator('.device-metadata img').count(),0);
  assert.match(await card.locator('.metadata-versions').innerText(),/2\.14\.2.*26\.115\.1/);
  await page.evaluate(()=>{metadata.bridge={version:'<img src=x onerror=alert(1)>',zigbee_herdsman_converters_version:null};});
  await read().click();await card.locator('.metadata-versions').filter({hasText:nl?'niet gemeld':'not reported'}).waitFor();
  assert.equal(await card.locator('.device-metadata img').count(),0);
  await page.evaluate(()=>{metadata.bridge={version:'2.14.2',zigbee_herdsman_converters_version:'26.115.1'};});
  await read().click();await card.locator('.metadata-versions').filter({hasText:'26.115.1'}).waitFor();
  assert.match(await card.locator('.device-metadata').innerText(),/MQTT/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,`${viewportName}-${language}.png`),fullPage:true});
  await page.evaluate(()=>window.mode='failure');await read().click();
  await card.getByText(nl?'Deze informatie kon niet worden vastgesteld.':'This information could not be established.',{exact:false}).waitFor();
  assert.equal(await card.locator('#name').inputValue(),'Fixture room');
  assert(!((await card.innerText()).includes('private remote response')));
  await page.evaluate(()=>window.mode='hold');await read().click();
  await card.locator('#name').fill('Keep my draft');
  await page.evaluate(()=>releaseMetadata());
  await card.getByText(nl?'Sla wijzigingen eerst op':'Save changes before checking',{exact:false}).waitFor();
  assert.equal(await card.locator('#name').inputValue(),'Keep my draft');
  assert.equal(await card.locator('.device-metadata article').count(),0);
  await card.getByRole('button',{name:nl?'Wijzigingen annuleren':'Discard changes',exact:true}).click();
  await page.evaluate(()=>{mode='ok';model.editable=false;});
  await card.getByRole('button',{name:nl?'Opnieuw laden':'Reload',exact:true}).click();
  await card.locator('#name:disabled').waitFor();await read().click();await card.locator('.device-metadata article').first().waitFor();
  assert.equal(await card.locator('#name').isEnabled(),false); // Observations work during runtime.
  await page.evaluate(()=>{mode='hold';});await read().click();
  await page.evaluate(()=>card.setConfig({entry_id:model.entry_id,room_id:'other-room'}));
  await read().waitFor();assert.equal(await read().isEnabled(),true);
  await page.evaluate(()=>releaseMetadata());
  assert.equal(await card.locator('.device-metadata article').count(),0);
  assert.equal(await page.evaluate(()=>calls.every(c=>['open_thermostat/room/get','open_thermostat/room/device_metadata'].includes(c.type))),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  results.push({viewport:viewportName,language,result:'PASS',versioned_upgrade:true,manual_reads_only:true,
   diagnostic_sensor_visible:true,declarations_not_qualification:true,xss_text_only:true,failed_read_preserves_draft:true,
   late_reply_does_not_replace_draft_or_room:true,read_available_during_runtime:true,writes:0});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'BROWSER.json'),JSON.stringify({result:'PASS',scope:'Real shipped JS/Chromium; synthetic admin WS; no live device qualification',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
