// Real shipped E32 root/assets; fixture HTTP/auth/state, no board or boiler control.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(process.env.OPENTHERMOSTAT_DASHBOARD_EVIDENCE||path.join(__dirname,'../out/e32-dashboard-20261022'));
const buildCapabilities=process.env.OPENTHERMOSTAT_BUILD_CAPABILITIES?JSON.parse(fs.readFileSync(process.env.OPENTHERMOSTAT_BUILD_CAPABILITIES,'utf8')):null;
function fixture(){return {controlMode:'shadow',ems:{heatingActive:false,warmWaterActive:false,currentFlowTemperature:432,selectedFlowTemperature:55,pressure:14,currentBurnerPower:0,outdoorTemperature:-550,displayCode:'0A'},control:{fresh:true,age_ms:150,captured_at_ms:10000,state:{boot_id:'synthetic-boot',boiler_output_enabled:false,actuator_output_enabled:false,supervisor:{reason:'hydraulic_profile_unqualified',requested_heat:true},zones:Array.from({length:8},(_,i)=>({zone_id:i.toString(16).padStart(8,'0'),temperature_centi_c:1925+i*25,target_centi_c:2100,demand:i<3,reason:i<3?'shadow_demand':'shadow_idle'}))}}};}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [label,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});let status=fixture(),requests=[],errors=[],failStatus=false,holdStatus=false,pendingStatus;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status'){
    if(holdStatus)await new Promise(resolve=>pendingStatus=resolve);
    return route.fulfill({status:failStatus?503:200,contentType:'application/json',body:JSON.stringify(status)});
   }
   let file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.css.gz')?'text/css':p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.clock.install();
  await page.goto('http://opth.test/');await page.locator('.pd-room').first().waitFor();
  assert.equal(await page.locator('.pd-room').count(),8);assert.match(await page.locator('.pd-flow').innerText(),/3 vragen warmte/);
  assert.equal(await page.locator('[data-legacy-editor]:visible').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(requests.some(r=>r.path.includes('chart')),false);assert.equal(requests.some(r=>r.method!=='GET'),false);
  const initialRequests=structuredClone(requests);
  assert.match(await page.locator('.pd-build').innerText(),/Koppeling met Home Assistant/);
  await page.locator('.pd-build summary').click();
  assert.match(await page.locator('.pd-build').innerText(),/nog geen herkenbare softwareondersteuning/);
  // Drive the actual ten-second poll, not a replacement renderer or fixture-only function.
  await page.locator('.pd-room-detail summary').first().click();
  await page.locator('.pd-lower > details:not(.pd-build) > summary').click();
  await page.evaluate(()=>{
   window.keptDashboard=document.querySelector('.product-dashboard');
   window.keptRoom=document.querySelector('.pd-room');
   window.keptDetails=keptRoom.querySelector('details');
   window.keptBuild=document.querySelector('.pd-build');
   window.keptBoilerDetails=document.querySelector('.pd-lower > details:not(.pd-build)');
   window.keptBoiler=document.getElementById('boiler-home');
   keptDetails.querySelector('summary').focus();
   window.scrollTo(0,120);window.keptScroll=scrollY;
  });
  status.ems.currentFlowTemperature=487;status.control.state.zones[0].temperature_centi_c=2025;
  status.control.captured_at_ms+=10000;
  await page.clock.runFor(10000);
  await page.waitForFunction(()=>document.querySelector('.pd-facts').textContent.includes('48.7'));
  assert.equal(await page.evaluate(()=>keptDashboard===document.querySelector('.product-dashboard') &&
   keptRoom===document.querySelector('.pd-room') && keptDetails.open && keptBuild.open && keptBoilerDetails.open &&
   keptBoiler===document.getElementById('boiler-home') && document.activeElement===keptDetails.querySelector('summary') && scrollY===keptScroll),true);
  status.control.state.zones.reverse();
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.evaluate(()=>keptRoom===document.querySelector('.pd-room:last-child') && keptDetails.open && document.activeElement===keptDetails.querySelector('summary')),true);
  status.control.state.zones.reverse();
  await page.evaluate(s=>updateRooms(s),status);
  // Transient failures retain the same open UI, but never silently imply a successful refresh.
  failStatus=true;
  await page.clock.runFor(10000);await page.locator('#dashboard-poll-error').waitFor();
  assert.equal(await page.evaluate(()=>keptDashboard.isConnected && keptDetails.open && keptBuild.open),true);
  failStatus=false;
  await page.clock.runFor(10000);await page.waitForFunction(()=>!document.getElementById('dashboard-poll-error'));
  assert.equal(await page.evaluate(()=>keptDetails.open && keptBuild.open),true);
  // A slow HTTP request is shared across refresh attempts, rather than racing responses.
  holdStatus=true;const beforeSlow=requests.filter(r=>r.path==='/status').length;
  await page.evaluate(()=>{showRooms();showRooms();});
  await page.waitForFunction(()=>statusPoll!==null);
  await page.waitForTimeout(20);
  assert.equal(requests.filter(r=>r.path==='/status').length,beforeSlow+1);
  holdStatus=false;pendingStatus();
  await page.waitForFunction(()=>statusPoll===null);
  if(buildCapabilities){
   status.control_build=buildCapabilities;
   await page.evaluate(s=>updateRooms(s),status);assert.equal(await page.locator('.pd-build').getAttribute('open'),'');
   assert.match(await page.locator('.pd-build').innerText(),/maximaal 2 ruimtes/);
   assert.match(await page.locator('.pd-build').innerText(),/nog niet dat Home Assistant gekoppeld is/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.evaluate(()=>{for(let i=0;i<3;i++){lastLoadedStatus.control.captured_at_ms+=2000;lastLoadedStatus.control.state.zones[0].temperature_centi_c+=10;updateRooms(lastLoadedStatus);}});
  assert.equal(await page.locator('svg.pd-trend').count(),8);
  await page.screenshot({path:path.join(out,'DASHBOARD-'+label+'.png'),fullPage:true});
  status.control.state.zones[0].zone_id='deadbeef';
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.evaluate(()=>!keptRoom.isConnected && !document.querySelector('.pd-room details').open && keptBuild.open),true);
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
  assert.deepEqual(errors,[]);results.push({viewport:label,result:'PASS',rooms:8,initialRequests,compiledSupportReadback:!!buildCapabilities,automaticPollPreservesNodesOpenFocusScroll:true,keyedRoomReorder:true,replacedRoomStartsClosed:true,transientFailureRecovery:true,singleInflightPoll:true,staleSuppressed:true,safeText:true,horizontalOverflow:false,deviceProof:false});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',source:'shipped index.html and local assets, fixture HTTP',cases:results},null,2)+'\n');console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
