// Shipped editor + isolated canonical climate projection; no HA/device writes.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/room-status-ownership-20261027/browser');
const choice=(value,platform='fixture')=>({value,label:value,status:'available',identity:{platform,unique_id:'pin_'+value}});
const model={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,
 status_identity:{entry_id:'fixture',room_id:'a1b2c3d4'},contact_status_entity:'climate.fixture_room',token:'0'.repeat(64),
 rooms:[{room_id:'a1b2c3d4',name:'Room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 choices:{sensor:[choice('sensor.room')],climate:[choice('climate.valve')],schedule:[],binary_sensor:[choice('binary_sensor.window')],input_number:[choice('input_number.target','input_number')],person:[]},
 settings:{name:'Room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,minimum_centi_c:500,maximum_centi_c:3000,
 maximum_age_ms:120000,program_source:'local',schedule_entity:'',contact_entities:['binary_sensor.window'],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 setpoint_entity:'input_number.target',setpoint_duration_ms:600000,comfort:{away_centi_c:1700,frost_centi_c:500,temporary_ms:600000},presence_entity:'',
 week:Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(d=>[d,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({model,lang})=>{
   window.model=structuredClone(model);window.calls=[];window.attributes={entry_id:model.entry_id,room_id:model.room_id,
    comfort_context_sources:{contacts:{count:1,reason:'contact_open',pending_ms:0}},manual_target_source:{status:'request_accepted'},target_source:'temporary',override_remaining_minutes:9,comfort_mode:'boost',firmware_reason:'bounded_override'};
   const card=window.card=document.createElement('openthermostat-room-editor-v42');document.querySelector('main').append(card);card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   window.hass={language:lang,user:{is_admin:true},states:{'climate.fixture_room':{state:'heat',attributes:structuredClone(attributes)}},callWS:async request=>{
    calls.push(structuredClone(request));if(request.type!=='open_thermostat/room/get')throw Error('Unexpected mutation');return structuredClone(window.model);
   }};card.hass=hass;
  },{model,lang});
  const card=page.locator('openthermostat-room-editor-v42');await card.locator('.room-comfort').waitFor();await card.locator('.room-comfort > summary').click();
  const statuses=async()=>Promise.all(['.contact-status','.manual-target-status','.comfort-status'].map(css=>card.locator(css).innerText()));
  let text=await statuses();assert.match(text[0],lang==='nl'?/gepauzeerd/:/paused/);assert.match(text[1],/9/);assert.equal(text[2],'Boost');
  for(const fault of ['other_entry','other_room','missing_owner','unavailable','model_mismatch']){
   await page.evaluate(fault=>{
    const state={state:'heat',attributes:structuredClone(attributes)};
    if(fault==='other_entry')state.attributes.entry_id='another_installation';
    if(fault==='other_room')state.attributes.room_id='ffffffff';
    if(fault==='missing_owner'){delete state.attributes.entry_id;delete state.attributes.room_id;}
    if(fault==='unavailable')state.state='unavailable';
    card._model.status_identity=fault==='model_mismatch'?{entry_id:'foreign',room_id:'a1b2c3d4'}:{entry_id:'fixture',room_id:'a1b2c3d4'};
    hass={...hass,states:{'climate.fixture_room':state}};card.hass=hass;
   },fault);
   text=await statuses();for(const item of text)assert.match(item,lang==='nl'?/niet beschikbaar/:/unavailable|not available/);
   assert.doesNotMatch(text[1],/9/);assert.notEqual(text[2],'Boost');
  }
  assert.equal(await page.evaluate(()=>calls.length),1,'Projection changes never trigger reads/writes');
  await page.evaluate(async()=>{
   model.contact_status_entity='climate.renamed_room';hass={...hass,states:{'climate.renamed_room':{state:'heat',attributes:structuredClone(attributes)}}};card.hass=hass;await card.load();
  });
  text=await statuses();assert.match(text[1],/9/);assert.equal(text[2],'Boost');assert.equal(await page.evaluate(()=>calls.length),2);
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`OWNER-${lang}-${width}.png`),fullPage:true});results.push({lang,width,result:'PASS',foreignOrMissingOwnerHidden:true,noStaleCountdown:true,explicitRenameRecovery:true,noProjectionRequests:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
