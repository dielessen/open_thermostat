// Shipped date UI, isolated native WS/service/state fixture; no device IO.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/room-vacation-20261027/browser');
const choice=value=>({value,label:value,status:'available',identity:{platform:'fixture',unique_id:value}});
const model={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,
 status_identity:{entry_id:'fixture',room_id:'a1b2c3d4'},comfort_actions:{contract:'room.comfort.command.v1',supports_vacation_dates:true},
 contact_status_entity:'climate.room',token:'0'.repeat(64),rooms:[{room_id:'a1b2c3d4',name:'Room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 choices:{sensor:[choice('sensor.room')],climate:[choice('climate.valve')],schedule:[],binary_sensor:[],input_number:[],person:[]},
 settings:{name:'Room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,minimum_centi_c:500,maximum_centi_c:3000,
 maximum_age_ms:120000,program_source:'local',schedule_entity:'',contact_entities:[],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 setpoint_entity:'',setpoint_duration_ms:3600000,comfort:{away_centi_c:1700,frost_centi_c:500,temporary_ms:600000},presence_entity:'',
 week:Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(d=>[d,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950},timezoneId:'America/Los_Angeles'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({model,lang})=>{
   window.model=structuredClone(model);window.calls=[];window.services=[];window.previewMode='ok';window.serviceMode='ok';
   window.attributes={entry_id:model.entry_id,room_id:model.room_id,comfort_mode:'auto',firmware_reason:'shadow_demand',vacation_until_utc:0,vacation_ends_at:null};
   window.preview=request=>{
    if(previewMode==='gap')throw {code:'vacation_nonexistent_time'};
    const normal=request.local_end.length===16?request.local_end+':00':request.local_end;
    const candidates=(request.local_end==='2026-10-25T02:30'?['+02:00','+01:00']:['+01:00']).map(offset=>({iso:normal+offset,until_utc:Date.parse(normal+offset)/1000,utc_offset:offset.replace(':','')}));
    if(previewMode==='fold_remaining')candidates.splice(0,1);
    const result={entry_id:model.entry_id,room_id:model.room_id,entity_id:model.contact_status_entity,token:model.token,time_zone:model.time_zone,local_end:request.local_end,candidates};
    if(previewMode==='wrong_owner')result.room_id='ffffffff';
    if(previewMode==='wrong_token')result.token='f'.repeat(64);
    if(previewMode==='wrong_utc')result.candidates[0].until_utc+=3600;
    if(previewMode==='wrong_iso')result.candidates[0].iso='2026-10-31T18:00:00+01:00';
    return result;
   };
   const card=window.card=document.createElement('openthermostat-room-editor-v42');document.querySelector('main').append(card);card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   window.hass={language:lang,user:{is_admin:true},states:{'climate.room':{state:'heat',attributes:structuredClone(attributes)}},callWS:async request=>{
    calls.push(structuredClone(request));if(request.type.endsWith('/get'))return structuredClone(window.model);
    if(request.type!=='open_thermostat/room/vacation_preview')throw Error('Unexpected mutation');
    const result=preview(request);if(previewMode==='hold')return new Promise(resolve=>window.releasePreview=()=>resolve(result));return result;
   },callService:async(domain,service,data)=>{
    services.push({domain,service,data:structuredClone(data)});
    if(serviceMode==='uncertain')throw Error('Unconfirmed fixture');
    if(serviceMode==='hold')return new Promise(resolve=>window.releaseService=resolve);
   }};card.hass=hass;
  },{model,lang});
  const card=page.locator('openthermostat-room-editor-v42'),start=card.locator('.room-vacation button').nth(0),cancel=card.locator('.room-vacation button').nth(1),end=card.locator('#vacation_local_end'),status=card.locator('.vacation-status');
  await card.locator('.room-comfort').waitFor();await card.locator('.room-comfort > summary').click();
  assert.equal(await start.isDisabled(),true);assert.equal(await cancel.isDisabled(),true);assert.equal(await page.evaluate(()=>services.length),0);
  await end.fill('2026-10-30T18:00');await start.click();await page.waitForFunction(()=>!card._vacationBusy&&services.length===1);
  const requested=await page.evaluate(()=>services[0]);assert.equal(requested.domain,'open_thermostat');assert.equal(requested.service,'set_comfort');
  assert.deepEqual(requested.data,{entity_id:'climate.room',mode:'vacation',vacation_until:'2026-10-30T18:00:00+01:00',expected_entry_id:model.entry_id,expected_room_id:model.room_id,expected_token:model.token,expected_time_zone:model.time_zone});
  assert.equal(await cancel.isDisabled(),true,'Service return never invents confirmed vacation state');
  await page.evaluate(()=>{hass.states['climate.room'].attributes={...attributes,comfort_mode:'vacation',vacation_until_utc:Date.parse('2026-10-30T18:00:00+01:00')/1000,vacation_ends_at:'2026-10-30T18:00:00+01:00'};card.hass={...hass};});
  assert.match(await status.innerText(),/18:00:00\+01:00/);await cancel.click();await page.waitForFunction(()=>!card._vacationBusy&&services.length===2);
  assert.equal((await page.evaluate(()=>services[1].data)).mode,'auto');assert.match(await status.innerText(),/18:00:00\+01:00/);
  await page.evaluate(()=>{hass.states['climate.room'].attributes=structuredClone(attributes);card.hass={...hass};});
  await end.fill('2027-03-28T02:30');await page.evaluate(()=>{previewMode='gap'});await start.click();await page.waitForFunction(()=>!card._vacationBusy);
  assert.match(await status.innerText(),lang==='nl'?/bestaat niet/:/does not exist/);assert.equal(await page.evaluate(()=>services.length),2);
  await page.evaluate(()=>{previewMode='ok'});await end.fill('2026-10-25T02:30');await start.click();await page.waitForFunction(()=>!card._vacationBusy);
  assert.equal(await page.evaluate(()=>services.length),2);assert.equal(await start.isDisabled(),true);
  await card.locator('#vacation_occurrence').selectOption('2026-10-25T02:30:00+01:00');await start.click();await page.waitForFunction(()=>!card._vacationBusy&&services.length===3);
  assert.equal(await page.evaluate(()=>services.at(-1).data.vacation_until),'2026-10-25T02:30:00+01:00');
  // A previously chosen occurrence becoming past never selects the other fold silently.
  await end.fill('2026-10-25T02:30');await start.click();await page.waitForFunction(()=>!card._vacationBusy);
  await card.locator('#vacation_occurrence').selectOption('2026-10-25T02:30:00+02:00');
  await page.evaluate(()=>{previewMode='fold_remaining'});await start.click();await page.waitForFunction(()=>!card._vacationBusy);
  assert.equal(await page.evaluate(()=>services.length),3);assert.equal(await start.isDisabled(),true);
  await card.locator('#vacation_occurrence').selectOption('2026-10-25T02:30:00+01:00');await start.click();await page.waitForFunction(()=>!card._vacationBusy&&services.length===4);
  await page.evaluate(()=>{previewMode='ok'});
  // Dirty settings and a reused canonical entity ID cannot issue a command.
  await card.locator('#name').fill('Unsaved room');assert.equal(await start.isDisabled(),true);const before=await page.evaluate(()=>calls.length);
  await page.evaluate(()=>card.requestVacation('vacation'));assert.equal(await page.evaluate(()=>calls.length),before);await card.locator('#name').fill('Room');
  await page.evaluate(()=>{hass.states['climate.room'].attributes.room_id='ffffffff';card.hass={...hass};});assert.equal(await start.isDisabled(),true);
  await page.evaluate(()=>{hass.states['climate.room'].attributes=structuredClone(attributes);card.hass={...hass};});
  await end.fill('2026-10-30T18:00');for(const mode of ['wrong_owner','wrong_token','wrong_utc','wrong_iso']){
   await page.evaluate(mode=>{previewMode=mode},mode);await start.click();await page.waitForFunction(()=>!card._vacationBusy);assert.equal(await page.evaluate(()=>services.length),4);
  }
  // A hidden page or changed config token while date resolution waits sends no action.
  for(const fault of ['hidden','token']){
   await page.evaluate(()=>{previewMode='hold'});await start.click();await page.waitForFunction(()=>typeof releasePreview==='function');
   await page.evaluate(fault=>{if(fault==='hidden')Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});else card._model.token='f'.repeat(64);releasePreview();delete window.releasePreview;},fault);
   await page.waitForFunction(()=>!card._vacationBusy);assert.equal(await page.evaluate(()=>services.length),4);
   await page.evaluate(async()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});await card.load();});
  }
  await page.evaluate(()=>{previewMode='ok';serviceMode='uncertain'});await start.click();await page.waitForFunction(()=>!card._vacationBusy&&card._vacationUncertain===true);
  const count=await page.evaluate(()=>services.length);await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>services.length),count);assert.equal(await start.isDisabled(),true);
  assert.match(await status.innerText(),lang==='nl'?/niet bevestigd/:/not confirmed/);
  await page.evaluate(async()=>{serviceMode='hold';await card.load();});await start.click();await page.waitForFunction(()=>typeof releaseService==='function');
  const held=await page.evaluate(()=>services.length);await page.evaluate(()=>card.requestVacation('vacation'));assert.equal(await page.evaluate(()=>services.length),held);
  assert.equal(await end.isDisabled(),true);await page.evaluate(()=>releaseService());await page.waitForFunction(()=>!card._vacationBusy);
  // UI deadlines do not leave a form locked or allow a late result to dispatch.
  await page.evaluate(()=>{const schedule=window.setTimeout;window.setTimeout=(fn,delay,...args)=>schedule(fn,[10000,15000].includes(delay)?50:delay,...args);previewMode='hold';serviceMode='ok';});
  await start.click();await page.waitForFunction(()=>!card._vacationBusy);const afterPreviewTimeout=await page.evaluate(()=>services.length);
  await page.evaluate(()=>{releasePreview();delete window.releasePreview;});await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>services.length),afterPreviewTimeout);
  await page.evaluate(()=>{previewMode='ok';serviceMode='hold';});await start.click();await page.waitForFunction(()=>!card._vacationBusy&&card._vacationUncertain===true);
  const afterServiceTimeout=await page.evaluate(()=>services.length);await page.evaluate(()=>releaseService());await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>services.length),afterServiceTimeout);assert.equal(await start.isDisabled(),true);
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`VACATION-${lang}-${width}.png`),fullPage:true});results.push({lang,width,result:'PASS',browserTimezone:'America/Los_Angeles',haTimezone:'Europe/Amsterdam',explicitFold:true,gapRejected:true,expectedRoomScope:true,noOptimisticState:true,noReplay:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
