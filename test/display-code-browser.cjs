// Release 1.0: the boiler's display code in words on the E32 home page (real shipped assets,
// fixture HTTP): the meaning large with the raw code small, a fault as a warning, a lockout as
// an error, the chosen boiler model's own table, an unknown code never guessed.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(process.env.OPENTHERMOSTAT_DISPLAY_CODE_EVIDENCE||path.join(__dirname,'../out/display-code-browser'));
function status(code,cause){return {controlMode:'shadow',ems:{heatingActive:false,warmWaterActive:false,currentFlowTemperature:432,pressure:14,currentBurnerPower:0,displayCode:code,...(cause===undefined?{}:{serviceCode:cause})},
 control:{fresh:true,age_ms:150,captured_at_ms:10000,state:{boot_id:'synthetic-boot',boiler_output_enabled:false,actuator_output_enabled:false,supervisor:{reason:'hydraulic_profile_unqualified',requested_heat:false},
 zones:[{zone_id:'00000001',temperature_centi_c:2010,target_centi_c:2100,demand:false,reason:'shadow_idle'}]}}};}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{for(const [language,viewport] of [['en',{width:1280,height:900}],['nl',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});const errors=[],failed=[];
  let current=status('6A',227),model='none';
  page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>failed.push(new URL(r.url()).pathname));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   assert.equal(req.method(),'GET',p);
   if(p==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(p==='/status')return route.fulfill({json:structuredClone(current)});
   if(p==='/config/boiler-display')return route.fulfill({json:{model}});
   if(p==='/status/heating')return route.fulfill({status:404,contentType:'application/json',body:'{}'}); // no E32 room engine in this fixture
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://opth.test'}]);
  await page.clock.install();
  await page.goto('http://opth.test/');
  const code=page.locator('.pd-boiler .pd-code');await code.waitFor();
  const nl=language==='nl';
  // A fault: a warning box with the meaning, the raw code and cause small, what to do, and a chip at the top.
  assert.match(await code.getAttribute('class'),/pd-code--warn/);
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Geen vlam na het ontsteken':'No flame detected after ignition');
  assert.equal(await code.locator('[data-code-raw]').innerText(),'6A 227');
  assert.match(await code.locator('.pd-code-more').innerText(),nl?/^Storing\. Controleer of de gaskraan open staat/:/^Fault\. Check that the gas tap is open/);
  assert.match(await page.locator('.pd-status .ot-chips').innerText(),nl?/Ketelstoring 6A/:/Boiler fault 6A/);
  assert.equal(await page.locator('.pd-status .ot-chip--warn').count(),1);
  const size=await code.evaluate(node=>[parseFloat(getComputedStyle(node.querySelector('[data-code-meaning]')).fontSize),parseFloat(getComputedStyle(node.querySelector('[data-code-raw]')).fontSize)]);
  assert(size[0]>size[1],'the meaning is larger than the raw code');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,language+'-fault.png'),fullPage:true});
  const poll=async()=>{await page.clock.runFor(10500);await page.waitForTimeout(50);};
  // A lockout: an error box.
  current=status('3L',214);await poll();
  assert.match(await code.getAttribute('class'),/pd-code--err/);
  assert.equal(await page.locator('.pd-status .ot-chip--err').count(),1);
  // Normal operation: calm, no chip, no advice line.
  current=status('0H',203);await poll();
  assert.equal(await code.getAttribute('class'),'pd-code');
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Stand-by: geen warmtevraag':'Standby: no heat demand');
  assert.equal(await code.locator('.pd-code-more').count(),0);
  assert.equal(await page.locator('.pd-status .ot-chip--warn, .pd-status .ot-chip--err').count(),0);
  // Waiting: the advice as one short line.
  current=status('0A',202);await poll();
  assert.match(await code.locator('.pd-code-more').innerText(),nl?/Geen actie nodig/:/No action needed/);
  // Unknown: the raw code and a pointer to the manual, never a guess.
  current=status('7X',512);await poll();
  assert.match(await code.getAttribute('class'),/pd-code--unknown/);
  assert.equal(await code.locator('[data-code-meaning]').innerText(),(nl?'Displaycode':'Display code')+' 7X 512');
  assert.equal(await code.locator('.pd-code-more').innerText(),nl?'Onbekende code, zie de handleiding van je ketel.':'Unknown code, see your boiler manual.');
  // The owner's EcomLine Classic (chosen on the Boiler page): its own manual, no cause number.
  model='nefit-ecomline-classic-hrc-22h';current=status('0C',0);
  await page.evaluate(()=>BoilerDisplay.load());await poll();
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Wacht op het omschakelen van de driewegklep':'Waiting for the 3-way valve to switch');
  assert.equal(await code.locator('[data-code-raw]').innerText(),'0C');
  // A code that family does not have is unknown, not borrowed from newer boilers.
  current=status('2E',207);await poll();
  assert.match(await code.getAttribute('class'),/pd-code--unknown/);
  // A Bosch letter-code family (Condens 7000i W): its own letters, and the operating messages
  // its manual lists by number only ("-"), whatever code the bus carries with that number.
  model='bosch-condens-7000i-w';current=status('EA',227);
  await page.evaluate(()=>BoilerDisplay.load());await poll();
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Geen vlam na het ontsteken':'No flame detected after ignition');
  assert.equal(await code.locator('[data-code-raw]').innerText(),'EA 227');
  assert.match(await code.getAttribute('class'),/pd-code--warn/);
  current=status('C6',215);await poll();
  assert.match(await code.getAttribute('class'),/pd-code--err/);
  current=status('-H',203);await poll();
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Stand-by: geen warmtevraag':'Standby: no heat demand');
  assert.equal(await code.getAttribute('class'),'pd-code');
  // Greenstar 4000: a four-digit fault number stays a number.
  model='worcester-bosch-greenstar-4000';current=status('EA',2927);
  await page.evaluate(()=>BoilerDisplay.load());await poll();
  assert.equal(await code.locator('[data-code-meaning]').innerText(),nl?'Vlam valt weg tijdens het branden':'Flame lost while burning');
  assert.equal(await code.locator('[data-code-raw]').innerText(),'EA 2927');
  current=status('EA',1013);await poll();  // a maintenance message (class W): not in the table
  assert.match(await code.getAttribute('class'),/pd-code--unknown/);
  assert.equal(await code.locator('[data-code-meaning]').innerText(),(nl?'Displaycode':'Display code')+' EA 1013');
  // No code at all: no box.
  current=status('--');await poll();
  assert.equal(await page.locator('.pd-boiler .pd-code').count(),0);
  await page.screenshot({path:path.join(out,language+'-none.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
  await page.close();
 }}finally{await browser.close();}
 console.log('PASS display code browser: fault, lockout, normal, waiting, unknown, the model tables and number-only codes (en, nl)');
})().catch(error=>{console.error(error);process.exit(1);});
