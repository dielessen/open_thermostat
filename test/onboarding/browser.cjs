// Run the shipped setup UI in Chromium; API responses are explicit simulations.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
let passed=0; const pass=name=>{passed++;console.log('PASS '+name);};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try {
  async function scene(rows=[],scanState='done'){
   const page=await browser.newPage({viewport:{width:390,height:844}});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   const sim={rows,scanState,status:'ready',connected:false,station_ip:'0.0.0.0',posts:[],scans:0,finishes:0,dropPost:false,statusDrops:0};
   await page.route('http://opth.test/**',async route=>{
    const req=route.request(),url=new URL(req.url()),body={contentType:'application/json'};
    if(url.pathname==='/setup.html')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'data/html/setup.html'),'utf8')});
    if(url.pathname==='/setup.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'data/html/setup.js'),'utf8')});
    if(url.pathname==='/setup/status'){
     if(sim.statusDrops-->0)return route.abort();
     return route.fulfill({...body,json:{status:sim.status,connected:sim.connected,station_ip:sim.station_ip,setup_active:true,remaining_seconds:880}});
    }
    if(url.pathname==='/setup/scan'){
     if(req.method()==='POST'){sim.scans++;return route.fulfill({...body,status:202,json:{status:'scanning'}});}
     return route.fulfill({...body,json:{status:sim.scanState,networks:sim.rows}});
    }
    if(url.pathname==='/setup/network'){
     sim.posts.push(req.postDataJSON());sim.status='connecting';
     if(sim.dropPost)return route.abort();
     return route.fulfill({...body,status:202,json:{status:'connecting'}});
    }
    if(url.pathname==='/setup/finish'){sim.finishes++;return route.fulfill({...body,status:202,json:{ok:true}});}
    return route.fulfill({status:404,body:'Not found'});
   });
   await page.goto('http://opth.test/setup.html');
   await page.waitForFunction(()=>!document.getElementById('scan').disabled);
   return {page,sim,errors};
  }
  let {page,sim,errors}=await scene([{ssid:'home',rssi:-70},{ssid:'home',rssi:-35},{ssid:'<img src=x onerror=alert(1)>',rssi:-40}]);
  assert.equal(await page.locator('#networks option').count(),3);assert.equal(await page.locator('#networks option').nth(1).textContent(),'home (-35 dBm)');
  assert.equal(await page.locator('#networks img').count(),0);assert.equal(sim.scans,1);pass('automatic scan, strongest SSID deduplication and injection-safe options');
  await page.selectOption('#networks','home');assert.equal(await page.inputValue('#ssid'),'home');assert.deepEqual(errors,[]);pass('network selection fills editable SSID in real mobile-sized UI');await page.close();
  ({page,sim,errors}=await scene());
  assert.match(await page.locator('#scan-status').textContent(),/Geen 2,4/);pass('empty scan explains manual and hidden-network path');
  await page.fill('#ssid','hidden home');await page.fill('#password','wrong-pass');await page.click('#connect');
  assert.equal(sim.posts.length,1);assert.equal(sim.posts[0].ssid,'hidden home');assert.equal(await page.locator('#connect').isDisabled(),true);pass('manual join sends form, fences duplicate connect and scan');
  sim.status='connection_failed';await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Verbinding mislukt'));
  assert.equal(await page.inputValue('#ssid'),'hidden home');assert.equal(await page.inputValue('#password'),'wrong-pass');assert.equal(await page.locator('#connect').isDisabled(),false);pass('wrong-password result preserves input and permits retry');
  sim.dropPost=true;await page.fill('#password','correct-test');await page.click('#connect');sim.statusDrops=2;
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Tijdelijk'));
  assert.equal(await page.locator('#handoff').isHidden(),true);pass('lost POST and status responses never produce false success');
  sim.connected=true;sim.station_ip='192.168.1.90';sim.status='connected_saved';
  await page.waitForFunction(()=>!document.getElementById('handoff').hidden);
  assert.equal(await page.getAttribute('#home','href'),'http://192.168.1.90/');assert.equal(await page.inputValue('#password'),'');assert.equal(sim.posts.length,2);pass('automatic recovery shows confirmed DHCP handoff and clears password');
  sim.connected=false;await page.waitForFunction(()=>document.getElementById('status').textContent.includes('weggevallen'));
  assert.equal(await page.locator('#handoff').isHidden(),true);pass('post-save station loss retracts stale success link');
  sim.connected=true;await page.waitForFunction(()=>!document.getElementById('handoff').hidden);
  if(process.env.ONBOARDING_SCREENSHOT)await page.screenshot({path:process.env.ONBOARDING_SCREENSHOT,fullPage:true});
  await page.click('#finish');await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Opgeslagen.'));
  assert.equal(sim.finishes,1);assert.equal(await page.locator('#scan').isDisabled(),true);assert.deepEqual(errors,[]);pass('explicit finish waits for accepted API response before handoff');await page.close();
  ({page,sim,errors}=await scene([],'failed'));
  assert.match(await page.locator('#scan-status').textContent(),/Scannen mislukt/);sim.scanState='done';sim.rows=[{ssid:'recovered',rssi:-42}];await page.click('#scan');
  await page.waitForFunction(()=>document.getElementById('networks').options.length===2);pass('failed scan has distinct retry and recovers');
  await page.fill('#ssid','recovered');await page.fill('#password','test-password');await page.click('#connect');sim.status='storage_error';
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('opslaan niet bevestigd'));
  assert.equal(await page.locator('#handoff').isHidden(),true);assert.equal(await page.locator('#connect').isDisabled(),false);assert.deepEqual(errors,[]);pass('storage failure is not success and remains retryable');await page.close();
  console.log(passed+' browser scenarios passed (simulated API, not ESP32 RF proof)');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
