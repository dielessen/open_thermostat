// Real shipped page/scripts with HTTP fixtures; no device or physical commands.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const output=path.resolve(process.env.OPENTHERMOSTAT_CONFIRM_EVIDENCE||'out/boiler-confirm-browser');
const limits={minimum_flow_c:40,maximum_flow_c:45,maximum_duration_s:60,operator_lease_ms:5000};
function initial(){return {schema:1,boot_id:'000000000000002a',revision:0,state_sequence:1,observed_at_ms:100,
 available:true,blocked_reason:'',phase:'idle',reason:'not_prepared',owned:false,can_prepare:true,can_prepare_zero:true,
 zero_test_available:true,site_confirmation_required:true,operator_lease_ms:5000,can_start:false,can_stop:false,
 reported_stop_confirmed:false,positive_frames:0,zero_frames:0,operator_remaining_ms:0,heat_remaining_ms:0,
 requested_flow_c:null,limits,physical_validation:false};}
(async()=>{
 fs.mkdirSync(output,{recursive:true});const results=[];
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{for(const width of [1280,390])for(const language of ['en','nl']){
  const page=await browser.newPage({viewport:{width,height:950}});let state=initial(),posts=[];const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const until=async condition=>{for(let i=0;i<200&&!condition();++i)await page.waitForTimeout(25);assert(condition(),'fixture condition did not arrive');};
  const reply=(route,data)=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  await page.route('http://confirmation.test/**',async route=>{
   const request=route.request(),name=new URL(request.url()).pathname;
   if(name==='/auth/session')return reply(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(name==='/status')return reply(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(name==='/status/ems/telemetry')return reply(route,{reception:{state:'no_boiler_reports'},transport:{transmit_compiled:false},fields:{},test:state});
   if(name.startsWith('/boiler/test/')){
    assert.equal(request.method(),'POST');assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    posts.push(name);const body=request.postDataJSON();
    state={...state,revision:body.revision,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+100,
     phase:'ready',owned:true,can_prepare:false,can_prepare_zero:false,can_start:true,can_stop:true,reported_stop_confirmed:true};
    if(name.endsWith('/prepare_zero'))state={...state,phase:'baseline',zero_only:true,can_start:false,reported_stop_confirmed:false};
    if(name.endsWith('/close_fault'))state={...state,phase:'closed',restart_required:true,can_start:false,can_stop:false,can_close_fault:false};
    return reply(route,{accepted:true,test:state});
   }
   const file=path.join(assets,name==='/'?'index.html':name);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(name.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:name.endsWith('.js')||name.includes('.js.gz')?'application/javascript':name.includes('.css')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_session',value:'b'.repeat(64),url:'http://confirmation.test'},
   {name:'ot_ui_lang',value:language,url:'http://confirmation.test'}]);
  await page.goto('http://confirmation.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  for(const action of ['start','prepare_zero','close_fault'])for(const interruption of ['cancel','confirm','hidden','brief','pagehide','detach']){
   state=initial();posts=[];
   if(action==='close_fault')state={...state,revision:1,phase:'fault',can_prepare:false,can_prepare_zero:false,can_stop:true,can_close_fault:true,reported_stop_confirmed:true,zero_frames:1};
   await page.evaluate(()=>{delete document.visibilityState;return loadNativePage('boiler_test');});
   if(action==='close_fault')await page.waitForFunction(()=>!document.querySelector('[data-test-close-fault]').disabled);
   else {
    await page.waitForFunction(()=>!document.querySelector('[data-test-flow]').disabled);
    await page.locator('[data-site-confirm]').check();
   }
   if(action==='start'){
    await page.locator('[data-test-flow]').fill('40');await page.locator('[data-test-duration]').fill('1');
    await page.locator('[data-test-prepare]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-test-start]').disabled);
   }
   if(action==='prepare_zero')await page.locator('#boiler-test-reception > summary').click();
   const before=posts.length;
   await page.evaluate(({action,interruption})=>{
    const original=window.confirm;
    window.confirm=()=>{
     if(interruption==='hidden'||interruption==='brief'){
      Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});
      document.dispatchEvent(new Event('visibilitychange'));
      if(interruption==='brief'){
       Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});
       document.dispatchEvent(new Event('visibilitychange'));
      }
     }
     if(interruption==='pagehide')window.dispatchEvent(new Event('pagehide'));
     if(interruption==='detach')document.querySelector('#boiler-test').remove();
     return interruption!=='cancel';
    };
    document.querySelector(action==='start'?'[data-test-start]':action==='close_fault'?'[data-test-close-fault]':'[data-test-zero]').click();
    window.confirm=original;
   },{action,interruption});
   if(interruption==='confirm')await until(()=>posts.length>before);
   await page.waitForTimeout(200);
   const submitted=posts.slice(before);
   assert.deepEqual(submitted,interruption==='confirm'?['/boiler/test/'+action]:[],`${language}/${width}/${action}/${interruption}: revalidate after confirmation`);
   results.push({width,language,action,interruption,result:'PASS',physicalProof:false});
  }
  assert.deepEqual(errors,[]);await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'BROWSER.json'),JSON.stringify({result:'PASS',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
