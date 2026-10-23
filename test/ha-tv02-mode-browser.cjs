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
   window.card=document.createElement('openthermostat-room-editor-v25');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   card.hass={language,user:{is_admin:true},callWS:async request=>{
    calls.push(request.type);if(request.type!=='open_thermostat/room/get')throw Error('Unexpected write');
    return structuredClone(model);
   }};
  },{initial,language});
  const card=page.locator('openthermostat-room-editor-v25'),review=card.locator('.target-review[aria-label]');
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
  await card.locator('#base_centi_c').fill('21.5');
  assert((await review.textContent()).includes(language==='nl'?'Na Alles opslaan':'Save all'));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(await page.evaluate(()=>[...new Set(calls)]),['open_thermostat/room/get']);
  assert.deepEqual(errors,[]);
  results.push({width,language,result:'PASS',readOnly:true,noModeRepair:true,physicalReadinessClaimed:false});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify({status:'PASS',results},null,2)+'\n');
 console.log(JSON.stringify({status:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
