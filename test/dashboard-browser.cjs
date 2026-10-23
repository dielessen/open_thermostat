// Real shipped E32 root/assets; fixture HTTP/auth/state, no board or boiler control.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(process.env.OPENTHERMOSTAT_DASHBOARD_EVIDENCE||path.join(__dirname,'../out/e32-dashboard-20261022'));
const buildCapabilities=process.env.OPENTHERMOSTAT_BUILD_CAPABILITIES?JSON.parse(fs.readFileSync(process.env.OPENTHERMOSTAT_BUILD_CAPABILITIES,'utf8')):null;
function fixture(){return {controlMode:'shadow',ems:{heatingActive:false,warmWaterActive:false,currentFlowTemperature:432,selectedFlowTemperature:55,pressure:14,currentBurnerPower:0,outdoorTemperature:-550,displayCode:'0A'},control:{fresh:true,age_ms:150,captured_at_ms:10000,state:{boot_id:'synthetic-boot',boiler_output_enabled:false,actuator_output_enabled:false,supervisor:{reason:'hydraulic_profile_unqualified',requested_heat:true},zones:Array.from({length:8},(_,i)=>({zone_id:i.toString(16).padStart(8,'0'),temperature_centi_c:1925+i*25,target_centi_c:2100,demand:i<3,reason:i<3?'shadow_demand':'shadow_idle'}))}}};}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [label,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});let status=fixture(),requests=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify(status)});
   let file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.css.gz')?'text/css':p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('.pd-room').first().waitFor();
  assert.equal(await page.locator('.pd-room').count(),8);assert.match(await page.locator('.pd-flow').innerText(),/3 vragen warmte/);
  assert.equal(await page.locator('[data-legacy-editor]:visible').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(requests.some(r=>r.path.includes('chart')),false);assert.equal(requests.some(r=>r.method!=='GET'),false);
  const initialRequests=structuredClone(requests);
  assert.match(await page.locator('.pd-build').innerText(),/Koppeling met Home Assistant/);
  await page.locator('.pd-build summary').click();
  assert.match(await page.locator('.pd-build').innerText(),/nog geen herkenbare softwareondersteuning/);
  if(buildCapabilities){
   status.control_build=buildCapabilities;
   await page.evaluate(s=>updateRooms(s),status);await page.locator('.pd-build summary').click();
   assert.match(await page.locator('.pd-build').innerText(),/maximaal 2 ruimtes/);
   assert.match(await page.locator('.pd-build').innerText(),/nog niet dat Home Assistant gekoppeld is/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.evaluate(()=>{for(let i=0;i<3;i++){lastLoadedStatus.control.captured_at_ms+=2000;lastLoadedStatus.control.state.zones[0].temperature_centi_c+=10;updateRooms(lastLoadedStatus);}});
  assert.equal(await page.locator('svg.pd-trend').count(),8);
  await page.screenshot({path:path.join(out,'DASHBOARD-'+label+'.png'),fullPage:true});
  status.control.fresh=false;status.control.reason='stale';
  await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-room').count(),0);assert.match(await page.locator('.pd-status').innerText(),/verouderd/);
  status=fixture();status.control.state.zones[0].name_utf8_hex=Buffer.from('Badkamer – Zoë','utf8').toString('hex');
  await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-room h3').first().innerText(),'Badkamer – Zoë');
  status.control.state.zones[0].name_utf8_hex=Buffer.from('<img src=x onerror=alert(1)>','utf8').toString('hex');
  await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-room img').count(),0);assert.match(await page.locator('.pd-room h3').first().innerText(),/<img/);
  status.control.state.zones[0].name_utf8_hex='c080';
  await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-room h3').first().innerText(),'Ruimte 1');
  status=fixture();status.control.state.zones[0].name='<img src=x onerror=alert(1)>';status.ems.displayCode='<script>alert(2)</script>';
  await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-room img').count(),0);assert.match(await page.locator('.pd-room h3').first().innerText(),/<img/);
  assert.deepEqual(errors,[]);results.push({viewport:label,result:'PASS',rooms:8,initialRequests,compiledSupportReadback:!!buildCapabilities,staleSuppressed:true,safeText:true,horizontalOverflow:false,deviceProof:false});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',source:'shipped index.html and local assets, fixture HTTP',cases:results},null,2)+'\n');console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
