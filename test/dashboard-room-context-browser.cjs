// Shipped E32 dashboard/assets against isolated HTTP fixtures. No device connection.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_DASHBOARD_CONTEXT_EVIDENCE||path.join(__dirname,'../out/dashboard-room-context-20261027'));
function fixture(){
 const until=Date.parse('2026-10-28T17:30:00Z')/1000;
 return {controlMode:'shadow',ems:{},control:{fresh:true,age_ms:125,captured_at_ms:10000,state:{boot_id:'context-fixture',
  boiler_output_enabled:false,actuator_output_enabled:false,supervisor:{requested_heat:false,reason:'limits_unknown'},
  zones:[
   {target_source:'base',reason:'shadow_idle'},
   {target_source:'schedule',comfort_mode:'auto',reason:'automatic'},
   {target_source:'temporary',override_remaining_ms:3660000,reason:'bounded_override'},
   {target_source:'window',comfort_mode:'boost',override_remaining_ms:599999,reason:'window_open'},
   {target_source:'presence',comfort_mode:'auto',reason:'presence_away'},
   {target_source:'vacation',comfort_mode:'vacation',vacation_until_utc:until,reason:'explicit_away'},
   {target_source:'off',comfort_mode:'off',reason:'explicit_off'},
   {target_source:'frost',comfort_mode:'frost',reason:'explicit_frost'},
  ].map((row,i)=>({zone_id:i.toString(16).padStart(8,'0'),name:'Room '+(i+1),temperature_centi_c:2000,target_centi_c:i===3?null:2100,demand:false,...row}))}}};
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}});let status=fixture();const requests=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;requests.push({path:pathname,method:req.method()});
   if(pathname==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(pathname==='/status')return route.fulfill({json:status});
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.css(?:\.gz)?$/.test(pathname)?'text/css':/\.js(?:\.gz)?$/.test(pathname)?'application/javascript':'text/html'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.clock.install();await page.goto('http://opth.test/');await page.locator('.pd-room-context').first().waitFor({state:'attached'});
  assert.equal(await page.locator('.pd-room-context').count(),8);
  await page.locator('.pd-room-detail summary').nth(3).click();
  const paused=page.locator('.pd-room').nth(3);
  assert.match(await paused.innerText(),lang==='en'?/Heating paused by window\/door status/:/Verwarming gepauzeerd door raam-\/deurstatus/);
  assert.match(await paused.locator('.pd-room-context').innerText(),/Boost/);
  assert.match(await paused.locator('.pd-room-context').innerText(),/10 min/);
  await page.evaluate(()=>{
   window.contextCard=document.querySelectorAll('.pd-room')[3];window.contextDetails=contextCard.querySelector('details');
   contextDetails.querySelector('summary').focus();window.contextScroll=scrollY;
  });
  const initialRequests=requests.length;
  await page.clock.runFor(5000);
  assert.match(await paused.locator('.pd-room-context').innerText(),/10 min/); // No browser countdown or extra poll.
  assert.equal(requests.length,initialRequests);
  status.control.state.zones[3].override_remaining_ms=539999;status.control.captured_at_ms+=10000;
  await page.clock.runFor(5000);
  await page.waitForFunction(()=>document.querySelectorAll('.pd-room-context')[3].textContent.includes('9 min'),null,{timeout:5000});
  assert.equal(await page.evaluate(()=>contextCard===document.querySelectorAll('.pd-room')[3]&&contextDetails.open&&
   document.activeElement===contextDetails.querySelector('summary')&&scrollY===contextScroll),true);
  assert.equal(requests.filter(r=>r.path==='/status').length,2);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  assert.equal(requests.some(r=>/^\/(?:ems|control|boiler|updates)\//.test(r.path)),false);
  await page.locator('.pd-room-detail summary').nth(5).click();
  assert.match(await page.locator('.pd-room-context').nth(5).innerText(),/2026-10-28 17:30:00 UTC/);
  await page.evaluate(()=>document.querySelectorAll('.pd-room-detail').forEach(x=>x.open=true));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`ROOM-CONTEXT-${lang}-${width}.png`),fullPage:true});
  // Optional old/malformed metadata does not manufacture a timer or execute markup.
  Object.assign(status.control.state.zones[3],{name:'<img src=x onerror=alert(1)>',target_source:'__proto__',comfort_mode:'<img>',override_remaining_ms:'60000'});
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.locator('.pd-room').nth(3).locator('.pd-room-context').count(),0);
  assert.equal(await page.locator('.pd-room img').count(),0);
  assert.match(await page.locator('.pd-room h3').nth(3).innerText(),/<img/);
  status.control.fresh=false;status.control.reason='stale';await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.locator('.pd-room-context').count(),0);assert.equal(await page.locator('.pd-room').count(),0);
  assert.equal(await page.evaluate(()=>!contextCard.isConnected),true);
  assert.deepEqual(errors,[]);results.push({language:lang,width,status:'PASS',status_gets:requests.filter(r=>r.path==='/status').length,device_commands:0});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'isolated_shipped_assets_no_device_requests',results},null,2)+'\n');
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
