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
  const failed=[];page.on('requestfailed',request=>failed.push(new URL(request.url()).pathname));
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.__dashboardVisibility='visible';
   Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__dashboardVisibility});
  });
  const awaitPendingStatus=async()=>{
   for(let attempt=0;attempt<200&&!pendingStatus;attempt++)await page.waitForTimeout(10);
   assert.equal(typeof pendingStatus,'function','fixture status request did not arrive');
  };
  const visibility=value=>page.evaluate(v=>{window.__dashboardVisibility=v;document.dispatchEvent(new Event('visibilitychange'));},value);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/updates/status')return route.fulfill({contentType:'application/json',json:{
    installed:'v0.1.0-e32v2-alpha.31',phase:'checked',error:'',busy:false,
    can_check:true,boot_pending:false,reboot_required:false,reboot_scheduled:false,
    rollback_available:false,received:0,total:0,
    releases:[{tag:'v0.1.0-e32v2-alpha.99',prerelease:true}],
   }});
   if(p==='/status'){
    const answer=structuredClone(status);
    if(holdStatus)await new Promise(resolve=>pendingStatus=resolve);
    return route.fulfill({status:failStatus?503:200,contentType:'application/json',body:JSON.stringify(answer)});
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
  // Only reliable reported boiler values: no read-back setpoint tile, no tile for a
  // value the boiler did not report, and no unreliable flame/pump/fan rows.
  const facts=await page.locator('.pd-facts').innerText();
  assert.doesNotMatch(facts,/Keteldoel/);assert.match(facts,/43,2|43\.2/);assert.match(facts,/Installatiedruk/);
  assert.doesNotMatch(facts,/Retour/);
  const details=await page.locator('.pd-lower > details:not(.pd-build)').textContent();
  assert.doesNotMatch(details,/Vlamstatus|Pomp|Ventilator|Protocolprofiel/);assert.match(details,/0A/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(requests.some(r=>r.path.includes('chart')),false);assert.equal(requests.some(r=>r.method!=='GET'),false);
  const initialRequests=structuredClone(requests);
  assert.match(await page.locator('.pd-build').innerText(),/Koppeling met Home Assistant/);
  await page.locator('.pd-build summary').click();
  assert.match(await page.locator('.pd-build').innerText(),/nog geen herkenbare softwareondersteuning/);
  // Drive the actual ten-second poll, not a replacement renderer or fixture-only function.
  await page.locator('.pd-room-detail summary').first().click();
  await page.locator('.pd-lower > details:not(.pd-build) > summary').click();
  await page.locator('[data-dashboard-key="connection-fallback-help"] > summary').click();
  assert.match(await page.locator('[data-dashboard-key="connection-fallback-help"]').innerText(),/15 seconden/);
  await page.evaluate(()=>{
   window.keptDashboard=document.querySelector('.product-dashboard');
   window.keptRoom=document.querySelector('.pd-room');
   window.keptDetails=keptRoom.querySelector('details');
   window.keptBuild=document.querySelector('.pd-build');
   window.keptFallback=document.querySelector('[data-dashboard-key="connection-fallback-help"]');
   window.keptBoilerDetails=document.querySelector('.pd-lower > details:not(.pd-build)');
   window.keptBoiler=document.getElementById('boiler-home');
   keptDetails.querySelector('summary').focus();
   window.scrollTo(0,120);window.keptScroll=scrollY;
  });
  status.ems.currentFlowTemperature=487;status.ems.currentReturnTemperature=412;delete status.ems.pressure;status.control.state.zones[0].temperature_centi_c=2025;
  status.control.captured_at_ms+=10000;
  await page.clock.runFor(10000);
  await page.waitForFunction(()=>document.querySelector('.pd-facts').textContent.includes('48.7'));
  assert.match(await page.locator('.pd-facts').innerText(),/Retour/);
  assert.doesNotMatch(await page.locator('.pd-facts').innerText(),/Installatiedruk/);
  assert.equal(await page.evaluate(()=>keptDashboard===document.querySelector('.product-dashboard') &&
   keptRoom===document.querySelector('.pd-room') && keptDetails.open && keptBuild.open && keptBoilerDetails.open && keptFallback.open &&
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
  const beforeUpdateRequests=requests.length;
  status.firmware_update={known:true,available:true,version:'v0.1.0-e32v2-alpha.99'};
  await page.evaluate(s=>updateRooms(s),status);
  assert.match(await page.locator('[data-dashboard-key="firmware-update"]').innerText(),/Firmware-update beschikbaar: v0.1.0-e32v2-alpha.99/);
  assert.equal(await page.locator('[data-dashboard-key="firmware-update"] button').innerText(),'Update bekijken');
  assert.equal(requests.length,beforeUpdateRequests);
  status.firmware_update.available=false;
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.locator('[data-dashboard-key="firmware-update"]').count(),0);
  status.firmware_update.available=true;status.firmware_update.known=false;
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.locator('[data-dashboard-key="firmware-update"]').count(),0);
  status.firmware_update.known=true;status.firmware_update.version='<img src=x onerror=alert(1)>';
  await page.evaluate(s=>updateRooms(s),status);
  assert.equal(await page.locator('[data-dashboard-key="firmware-update"]').count(),0);
  status.firmware_update.version='v0.1.0-e32v2-alpha.99';
  await page.evaluate(s=>updateRooms(s),status);
  // Exercise the shipped legacy tile too: names are data, never inline JS.
  for (const name of ["Guest's \"room\"\\floor\nZoë", 'x");window.__roomInjection=1;//']) {
   await page.evaluate(name=>{
    window.legacyPriorStatus=lastLoadedStatus;window.legacyPriorMode=controlUiMode;
    controlUiMode='legacy';lastLoadedStatus={rooms:[{name,tempSet:2100}]};
    $('#temporaryTempModal').removeClass('fade');
    const tile=showRoom({name,tempSet:2100,enabled:true},{boiler:false},'default');
    tile.id='legacy-room-check';document.body.append(tile);
   },name);
   await page.locator('#legacy-room-check > div').click();
   assert.equal(await page.locator('#temporaryTempModalRoomName').textContent(),name);
   assert.equal(await page.locator('#temporaryTempModalTemperature').inputValue(),'21');
   assert.equal(await page.evaluate(()=>window.__roomInjection),undefined);
   await page.evaluate(()=>{
    $('#temporaryTempModal').modal('hide');document.getElementById('legacy-room-check').remove();
    lastLoadedStatus=window.legacyPriorStatus;controlUiMode=window.legacyPriorMode;
   });
  }
  const legacyClockText=await page.evaluate(()=>{
   const tile=showRoom({name:'Clock check',tempSet:2100,enabled:true,controlStatus:'clock_unavailable'},{boiler:false},'default');
   return tile.textContent;
  });
  assert.match(legacyClockText,/Wachten op de apparaattijd; verwarming is gepauzeerd/);
  // A hidden dashboard retires its pending GET. Resume does not wait on that
  // request's 15-second deadline or allow its response to overwrite current data.
  holdStatus=true;pendingStatus=undefined;await page.evaluate(()=>showRooms());
  await page.waitForFunction(()=>statusPoll!==null);await awaitPendingStatus();
  const releaseHidden=pendingStatus,failedBefore=failed.length;
  await visibility('hidden');await page.waitForFunction(()=>statusPoll===null);
  await page.waitForTimeout(50);assert(failed.slice(failedBefore).includes('/status'));
  const hiddenCount=requests.filter(r=>r.path==='/status').length;
  await page.clock.runFor(30000);assert.equal(requests.filter(r=>r.path==='/status').length,hiddenCount);
  holdStatus=false;status.control.state.zones[0].name='Resumed owner';
  await visibility('visible');await visibility('visible');
  await page.waitForFunction(()=>document.querySelector('.pd-room h3')?.textContent==='Resumed owner');
  assert.equal(requests.filter(r=>r.path==='/status').length,hiddenCount+1);
  releaseHidden();await page.waitForTimeout(50);
  assert.equal(await page.locator('#dashboard-poll-error').count(),0);
  assert.equal(await page.locator('.pd-room h3').first().innerText(),'Resumed owner');
  // Real fetch deadline still displays failure. A late body is not a recovery.
  holdStatus=true;pendingStatus=undefined;await page.evaluate(()=>showRooms());
  await awaitPendingStatus();
  await page.clock.runFor(15000);await page.locator('#dashboard-poll-error').waitFor();
  const deadlineCount=requests.filter(r=>r.path==='/status').length;
  holdStatus=false;pendingStatus();await page.waitForTimeout(50);
  assert.equal(requests.filter(r=>r.path==='/status').length,deadlineCount);
  assert.equal(await page.locator('#dashboard-poll-error').count(),1);
  await page.clock.runFor(5000);await page.waitForFunction(()=>!document.getElementById('dashboard-poll-error'));
  // Navigation retires root polling; visibility events cannot start it on About.
  holdStatus=true;pendingStatus=undefined;await page.evaluate(()=>showRooms());
  await awaitPendingStatus();
  await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();
  const navigationCount=requests.filter(r=>r.path==='/status').length;
  holdStatus=false;pendingStatus();await visibility('hidden');await visibility('visible');
  await page.clock.runFor(30000);
  assert.equal(requests.filter(r=>r.path==='/status').length,navigationCount);
  assert.equal(await page.locator('.pd-room').count(),0);
  await page.evaluate(()=>mainScreen());await page.locator('.pd-room').first().waitFor();
  await page.locator('[data-dashboard-key="firmware-update"] button').click();
  await page.locator('#updateHeading').waitFor();
  await page.waitForFunction(()=>document.getElementById('installedVersion')?.textContent==='v0.1.0-e32v2-alpha.31');
  assert.equal(await page.locator('#githubUpdate').isVisible(),true);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  assert.deepEqual(errors,[]);results.push({viewport:label,result:'PASS',rooms:8,initialRequests,compiledSupportReadback:!!buildCapabilities,automaticPollPreservesNodesOpenFocusScroll:true,keyedRoomReorder:true,replacedRoomStartsClosed:true,transientFailureRecovery:true,singleInflightPoll:true,hiddenAbortsRead:true,resumeOneFreshRead:true,trueDeadlineVisible:true,navigationRetiresRootRead:true,staleSuppressed:true,safeText:true,legacyRoomNamesAreData:true,horizontalOverflow:false,deviceProof:false});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',source:'shipped index.html and local assets, fixture HTTP',cases:results},null,2)+'\n');console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
