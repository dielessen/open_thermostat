// Real UI/auth wrapper; isolated HTTP only. No broker/device traffic.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(__dirname,'../out/boiler-settings-browser');
function metadata(){return {schema:1,boot_id:'000000000000002a',revision:0,available:true,active:false,transport_fault:false,
 owned_by_requester:false,request:null,phase:'idle',response_at_ms:null,write_attempted:false,physical_validation:false,reason:'not_requested',settings:[
 ['heatingactivated','bool',1,0],['heatingtemp','degC',90,1],['burnminperiod','min',120,6],['pumpdelay','min',60,8]
 ].map(([entity,unit,maximum,offset])=>({entity,unit,minimum:0,maximum,offset,telegram_type:22}))};}
const devices={enabled:true,inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:3,age_ms:100,product_id:211,version:'2.3',brand_id:1,untracked_types:0,telegram_types:[2,22]}]},boiler:{fields:Object.fromEntries([
 ['heating_enabled',1,'bool'],['configured_heating_temperature',50,'degC'],['minimum_burner_period',5,'min'],['pump_run_on',3,'min']
].map(([id,value,unit])=>[id,{value,unit,state:'valid',quality:'reported',source_type:22,source_address:8,age_ms:100}]))}};
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],posts=[];let state=metadata(),mode='accepted',held=null;
  await page.clock.install();
  page.on('pageerror',e=>errors.push(e.message));await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(req.method()!=='GET'){
    assert.equal(p,'/boiler/settings/write');assert.equal(req.method(),'POST');
    assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    const body=req.postDataJSON();posts.push(body);
    assert.deepEqual(Object.keys(body).sort(),['schema','boot_id','revision','entity','value','exclusive_owner_confirmed','independent_stop_confirmed'].sort());
    assert.equal(body.exclusive_owner_confirmed,true);assert.equal(body.independent_stop_confirmed,true);
    if(mode==='network')return route.abort('failed');
    if(mode==='hold'){held=route;return;}
    if(mode==='rejected')return route.fulfill({status:409,contentType:'application/json',body:'{"accepted":false,"error":"settings_request_unavailable"}'});
    if(mode==='malformed')return route.fulfill({status:202,contentType:'application/json',body:'{"accepted":true}'});
    state={...state,revision:body.revision,available:false,active:true,phase:'queued_write',request:{entity:body.entity,value:body.value},owned_by_requester:mode!=='other',reason:'awaiting_write_poll'};
    return route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({accepted:true,duplicate:false,error:'',settings:state})});
   }
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:'{"controlMode":"shadow","ems":{},"control":{"fresh":false,"reason":"waiting"}}'});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(p==='/status/ems/telemetry')return route.fulfill({json:{reception:{state:'classic_reports_received'},transport:{enabled:true},inventory:devices.inventory,fields:devices.boiler.fields,settings:state}});
   const file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor();
  const button=page.locator('#ems-setting-submit'),note=page.locator('#ems-settings-operation');
  async function reset(next='accepted'){
   state=metadata();mode=next;held=null;
   await page.evaluate(()=>{if(window.originalSettingsConfirm)window.confirm=window.originalSettingsConfirm;});
   await page.evaluate(()=>loadNativePage('ems_devices'));
   await page.locator('[data-field="configured_heating_temperature"] button').click();
   await page.locator('#ems-settings-editor').waitFor({state:'visible'});
   await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
   await page.evaluate(()=>{window.originalSettingsConfirm??=window.confirm;window.confirm=()=>true;});
  }
  async function prepare(value='45'){
   await page.locator('#ems-setting-entity').selectOption('heatingtemp');
   await page.locator('#ems-setting-value').fill(value);
   await page.locator('#ems-setting-exclusive').check();await page.locator('#ems-setting-stop').check();
  }
  async function refresh(){await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);}
  async function settled(){await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);}
  await reset();await prepare('91');assert(await button.isDisabled());
  await page.locator('#ems-setting-value').fill('45.5');assert(await button.isDisabled());
  await page.locator('#ems-setting-value').fill('45');assert(await button.isEnabled());
  await page.evaluate(()=>{window.confirm=()=>false;});let before=posts.length;await button.click();await settled();
  assert.equal(posts.length,before);assert.equal(await page.locator('#ems-setting-exclusive').isChecked(),false);
  await reset();await prepare();before=posts.length;await refresh();
  assert.equal(await page.locator('#ems-setting-exclusive').isChecked(),false);assert.equal(posts.length,before);
  // Ordinary explicit preparation submits exactly once, and admission is not readback.
  await reset();await prepare();before=posts.length;
  await page.screenshot({path:path.join(output,`${lang}-${width}.png`),fullPage:true});
  await button.evaluate(b=>{b.click();b.click();});await note.filter({hasText:lang==='nl'?'geaccepteerd':'accepted'}).waitFor();await settled();
  assert.equal(posts.length,before+1);assert.equal(posts.at(-1).value,45);assert.equal(posts.at(-1).revision,1);
  await refresh();assert(!(await note.innerText()).includes(lang==='nl'?'is van de ketel teruggelezen':'was read back'));
  state={...state,active:false,phase:'completed',write_attempted:true,response_at_ms:123,reason:'setting_read_back',available:true};await refresh();
  assert.match(await note.innerText(),lang==='nl'?/van de ketel teruggelezen/:/read back from the boiler/);assert(await button.isDisabled());
  await page.locator('[data-field="configured_heating_temperature"] button').click();
  await page.locator('#ems-setting-entity').selectOption('heatingtemp');
  assert.equal(await note.innerText(),'');assert.equal(await page.getByRole('spinbutton',{name:lang==='nl'?'Nieuwe waarde':'New value',exact:true}).count(),1);
  // Boolean zero is an explicit typed value, with its own accessible label.
  await reset();await page.locator('#ems-setting-entity').selectOption('heatingactivated');
  await page.getByRole('combobox',{name:lang==='nl'?'Nieuwe waarde':'New value',exact:true}).selectOption('0');
  await page.locator('#ems-setting-exclusive').check();await page.locator('#ems-setting-stop').check();before=posts.length;
  await button.click();await note.filter({hasText:lang==='nl'?'geaccepteerd':'accepted'}).waitFor();await settled();
  assert.equal(posts.length,before+1);assert.equal(posts.at(-1).entity,'heatingactivated');assert.equal(posts.at(-1).value,0);
  // Lost/malformed/foreign acknowledgments remain uncertain, including after a stale GET.
  for(const fault of ['network','malformed','other']){
   await reset(fault);await prepare();before=posts.length;await button.click();
   await note.filter({hasText:lang==='nl'?'onzeker':'uncertain'}).waitFor();await settled();
   if(fault==='other')state={...state,active:false,phase:'completed',write_attempted:true,reason:'setting_read_back',response_at_ms:123,available:true};
   await refresh();assert.equal(posts.length,before+1);assert(await button.isDisabled());
   assert.match(await note.innerText(),lang==='nl'?/onzeker/:/uncertain/);
  }
  await reset('rejected');await prepare();before=posts.length;await button.click();
  await note.filter({hasText:lang==='nl'?'geweigerd':'rejected'}).waitFor();await settled();
  assert.equal(posts.length,before+1);assert(await button.isDisabled());await refresh();assert.equal(await page.locator('#ems-setting-stop').isChecked(),false);
  // Losing visibility or changing the value inside confirmation cannot send a request.
  for(const action of ['hidden','changed','unmount']){
   await reset();await prepare();before=posts.length;
   await page.evaluate(action=>{window.confirm=()=>{
    if(action==='hidden'){
     Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'));
     Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});document.dispatchEvent(new Event('visibilitychange'));
    }else if(action==='changed')document.querySelector('#ems-setting-value').value='46';
    else window.EMSDevicesPage.unmount();
    return true;
   };},action);
   await button.click();await page.waitForTimeout(60);assert.equal(posts.length,before);
  }
  // A prepared draft expires locally; expiration performs no network mutation.
  await reset();await prepare();before=posts.length;await page.clock.fastForward(30001);
  assert(await button.isDisabled());assert.equal(posts.length,before);
  // An interrupted in-flight POST is never replayed by returning or refreshing.
  await reset('hold');await prepare();before=posts.length;await button.click();await page.waitForFunction(()=>document.querySelector('#ems-setting-submit').disabled);
  await page.waitForTimeout(100);
  await page.evaluate(()=>{
   Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'));
   Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});document.dispatchEvent(new Event('visibilitychange'));
  });
  await note.filter({hasText:lang==='nl'?'onzeker':'uncertain'}).waitFor();await settled();if(held)await held.abort().catch(()=>{});
  await refresh();assert.equal(posts.length,before+1);assert(await button.isDisabled());
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',simulated_http_only:true,no_auto_retry:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
