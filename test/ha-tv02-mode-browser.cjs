// Shipped editor, synthetic authenticated WS; no live HA or device control.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright-core');
const fixture=fs.readFileSync(path.join(__dirname,'ha-room-program-browser.cjs'),'utf8');
const {initial,source}=vm.runInNewContext(fixture.split('(async()=>{')[0]+';({initial,source});',{require,__dirname,process});
const output=path.resolve(process.env.OPENTHERMOSTAT_TV02_EVIDENCE||path.join(__dirname,'../out/ha-tv02-mode-browser'));
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const width of [1440,390,320])for(const language of ['nl','en']){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({initial,language})=>{
   window.model=structuredClone(initial);window.calls=[];
   window.setMode=(issue,preset='manual',state='heat')=>{
    model.actuator_target_review={status:issue?'review_required':'compatible',scope:'saved_local_room_targets',
     external_program_present:false,external_program_checked:false,authorizes_actuation:false,
     actuators:[{entity_id:'climate.valve',status:issue?'review_required':'compatible',issues:issue?[issue]:[],targets:[],
      capability:{minimum:5,maximum:30,step:.5,unit:'°C'},
      operating_mode:{profile:'TV02-Zigbee',scope:'reported_ha_operating_mode',preset,system_mode:state,
       issues:issue?[issue]:[],authorizes_actuation:false}}]};
   };
   setMode('local_schedule_active','auto');
   window.card=document.createElement('openthermostat-room-editor-v38');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   card.hass={language,user:{is_admin:true},callWS:async request=>{
    calls.push(request.type);if(request.type!=='open_thermostat/room/get')throw Error('Unexpected write');
    return structuredClone(model);
   }};
  },{initial,language});
  const card=page.locator('openthermostat-room-editor-v38'),review=card.locator('.target-review[aria-label]');
  await review.waitFor();
  assert((await review.textContent()).includes(language==='nl'?'eigen weekprogramma':'automatic scheduling'));
  await review.screenshot({path:path.join(output,`AUTO-${width}-${language}.png`)});
  for(const [reason,preset,state,nl,en]of [
   ['holiday_mode_active','holiday','heat','vakantieprogramma','holiday program'],
   ['heating_disabled','manual','off','verwarming uit','heating off'],
   ['operating_mode_unknown',null,'heat','niet bevestigd','unconfirmed']]){
   await page.evaluate(async({reason,preset,state})=>{setMode(reason,preset,state);await card.load();},{reason,preset,state});
   assert((await review.textContent()).includes(language==='nl'?nl:en));
  }
  await page.evaluate(async()=>{setMode(null);await card.load();});
  const text=await review.textContent();
  assert(text.includes(language==='nl'?'Passende doelen bewijzen geen klepstand':'Compatible targets do not prove valve position'));
  assert(!text.includes(language==='nl'?'eigen weekprogramma':'automatic scheduling'));
  await page.evaluate(async()=>{
   model.actuator_target_review.actuators[0].original_report={status:'received_unqualified',received_age_ms:1250,
    fields:{target_centi_c:2150,local_temperature_centi_c:0,preset:'manual',heating_stop:false,frost_protection:true},
    command_correlated:false,valve_ready:false,control_qualified:false};await card.load();
  });
  const original=card.locator('.original-valve-report');await original.waitFor({timeout:3000});
  let originalText=(await original.textContent()).replace(/:/g,': ');
  assert(originalText.includes(language==='nl'?'Oorspronkelijk kraanbericht':'Original valve report'));
  assert(originalText.includes(language==='nl'?'geen bevestiging':'does not confirm'));
  assert(originalText.includes(language==='nl'?'Ontvangstouderdom bij laden':'Reception age when loaded'));
  assert(originalText.includes(language==='nl'?'21,5':'21.5'));assert(originalText.includes('0 °C'));
  assert(originalText.includes(language==='nl'?'Verwarmingsstop: Uit':'Heating stop: Off'));
  assert(originalText.includes(language==='nl'?'Vorstbeveiliging: Aan':'Frost protection: On'));
  await original.screenshot({path:path.join(output,`ORIGINAL-${width}-${language}.png`)});
  for(const state of ['metadata_unavailable','waiting','stale','disconnected','binding_changed','clock_invalid','run_limit','closed','unavailable']){
   await page.evaluate(async state=>{model.actuator_target_review.actuators[0].original_report.status=state;await card.load();},state);
   assert(!(await original.textContent()).includes(language==='nl'?'21,5':'21.5'));
   assert.equal(await original.locator('dl').count(),0);
   if(state==='metadata_unavailable')assert((await original.innerText()).includes(language==='nl'?'Wachten op apparaatmetadata':'Waiting for device metadata'));
   if(state==='unavailable')assert((await original.innerText()).includes(language==='nl'?'De ontvangst van kraanberichten is niet beschikbaar.':'Original valve report reception is unavailable.'));
  }
  // Expired values stay hidden while the bounded reception summary is useful.
  await page.evaluate(async()=>{
   model.actuator_target_review.actuators[0].original_report={status:'stale',received_age_ms:null,fields:{},
    command_correlated:false,valve_ready:false,control_qualified:false,
    last_reception:{scope:'reception_only',message_kind:'commandDataReport',received_age_ms:125000,
     properties:['target_centi_c','preset']}};await card.load();
  });
  const reception=original.locator('.valve-reception-metadata');
  assert.equal(await reception.count(),1);
  assert((await reception.innerText()).includes(language==='nl'?'Apparaatrapport':'Device report'));
  assert((await reception.innerText()).includes('125'));
  assert((await reception.innerText()).includes(language==='nl'?'Aanwezige gegevens':'Present data'));
  assert.equal(await original.locator('dl').count(),0);
  await original.screenshot({path:path.join(output,`STALE-RECEPTION-${width}-${language}.png`)});
  await page.evaluate(async()=>{model.actuator_target_review.actuators[0].original_report.last_reception.received_age_ms=null;await card.load();});
  assert((await reception.innerText()).includes(language==='nl'?'ouderdom onbekend':'age unknown'));
  for(const patch of [{scope:'qualified'},{message_kind:{toString:7}},{message_kind:'<img src=x>'},{received_age_ms:-1},
   {received_age_ms:Number.MAX_SAFE_INTEGER+1},{properties:['target_centi_c','target_centi_c']},
   {properties:['private_device_ieee']},{properties:[]},{properties:['<img src=x>']}]){
   await page.evaluate(async patch=>{model.actuator_target_review.actuators[0].original_report.last_reception={
    scope:'reception_only',message_kind:'commandDataReport',received_age_ms:125000,properties:['preset'],...patch};await card.load();},patch);
   assert.equal(await reception.count(),0);assert.equal(await original.locator('dl,img,script').count(),0);
  }
  for(const state of ['waiting','disconnected','binding_changed','clock_invalid','run_limit','closed']){
   await page.evaluate(async state=>{model.actuator_target_review.actuators[0].original_report.status=state;
    model.actuator_target_review.actuators[0].original_report.last_reception={scope:'reception_only',message_kind:'commandDataReport',received_age_ms:1,properties:['preset']};await card.load();},state);
   assert.equal(await reception.count(),0);
  }
  // A malformed/unknown payload never becomes a readiness claim or arbitrary HTML.
  for(const patch of [{status:{toString:7}},{status:'<img src=x onerror=alert(1)>'},{command_correlated:true},{valve_ready:true},
   {control_qualified:true},{received_age_ms:-1},{fields:{target_centi_c:'2150'}},
   {fields:{local_temperature_centi_c:6001}},{fields:{preset:'<img src=x>'}},
   {fields:{heating_stop:'false'}},{fields:{frost_protection:0}},{fields:{unexpected:'payload'}}]){
   await page.evaluate(async patch=>{
    model.actuator_target_review.actuators[0].original_report={status:'received_unqualified',received_age_ms:0,
     fields:{target_centi_c:2150},command_correlated:false,valve_ready:false,control_qualified:false,...patch};
    await card.load();
   },patch);
   assert.equal(await original.locator('dl,img,script').count(),0);
  }
  await page.evaluate(async()=>{
   const row=model.actuator_target_review.actuators[0];row.original_report={status:'received_unqualified',received_age_ms:0,
    fields:{target_centi_c:500},command_correlated:false,valve_ready:false,control_qualified:false};await card.load();
  });
  assert.equal(await original.locator('dl').count(),1);
  await card.locator('#base_centi_c').fill('21.5');
  assert((await review.textContent()).includes(language==='nl'?'Na Alles opslaan':'Save all'));
  assert.equal(await card.locator('.original-valve-report').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(await page.evaluate(()=>[...new Set(calls)]),['open_thermostat/room/get']);
  assert.deepEqual(errors,[]);
  results.push({width,language,result:'PASS',readOnly:true,noModeRepair:true,originalReportStates:true,typedFieldsAndZeroFalse:true,invalidReportsHidden:true,staleReceptionMetadata:true,invalidReceptionHidden:true,draftIsolated:true,physicalReadinessClaimed:false});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify({status:'PASS',results},null,2)+'\n');
 console.log(JSON.stringify({status:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
