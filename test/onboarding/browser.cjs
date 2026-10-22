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
   const sim={rows,scanState,status:'ready',connected:false,station_ip:'0.0.0.0',station_port:80,posts:[],scans:0,finishes:0,dropPost:false,statusDrops:0,closing:false,closeMs:8000,dropFinish:false,finishError:false};
   await page.clock.install();
   await page.route('http://192.168.1.90/**',route=>route.fulfill({contentType:'text/html',body:'<h1>Simulated home-network device</h1>'}));
   await page.route('http://opth.test/**',async route=>{
    const req=route.request(),url=new URL(req.url()),body={contentType:'application/json'};
    if(url.pathname==='/setup.html')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'data/html/setup.html'),'utf8')});
    if(url.pathname==='/setup.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'data/html/setup.js'),'utf8')});
    if(url.pathname==='/setup/status'){
     if(sim.statusDrops-->0)return route.abort();
     return route.fulfill({...body,json:{status:sim.status,connected:sim.connected,station_ip:sim.station_ip,station_port:sim.station_port,setup_active:true,remaining_seconds:880,closing:sim.closing,close_after_ms:sim.closing?sim.closeMs:0}});
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
    if(url.pathname==='/setup/finish'){
     sim.finishes++;
     if(sim.finishError)return route.fulfill({status:409,body:'Not confirmed'});
     sim.closing=true;
     if(sim.dropFinish){sim.dropFinish=false;return route.abort();}
     return route.fulfill({...body,status:202,json:{close_after_ms:sim.closeMs}});
    }
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
  assert.equal(await page.getAttribute('#home','href'),'http://192.168.1.90/');assert.equal(await page.inputValue('#password'),'');assert.equal(sim.posts.length,2);
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));assert.equal(sim.finishes,1);pass('automatic recovery shows DHCP address, clears password and automatically confirms finish');
  assert.equal(await page.locator('#network-fields').isHidden(),true);assert.ok((await page.locator('#home').boundingBox()).y<844);pass('mobile success replaces the form and keeps the new address in the first screen');
  sim.connected=false;sim.closing=false;await page.waitForFunction(()=>document.getElementById('status').textContent.includes('weggevallen'));
  assert.equal(await page.locator('#handoff').isHidden(),true);pass('post-save station loss retracts stale success link');
  sim.connected=true;await page.waitForFunction(()=>!document.getElementById('handoff').hidden);
  if(process.env.ONBOARDING_SCREENSHOT)await page.screenshot({path:process.env.ONBOARDING_SCREENSHOT,fullPage:true});
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  assert.equal(sim.finishes,2);assert.equal(await page.locator('#scan').isDisabled(),true);
  await page.clock.fastForward(11000);await page.waitForURL('http://192.168.1.90/');
  assert.deepEqual(errors,[]);pass('recovered connection automatically navigates to home URL without a Finish click');await page.close();
  ({page,sim,errors}=await scene([],'failed'));
  assert.match(await page.locator('#scan-status').textContent(),/Scannen mislukt/);sim.scanState='done';sim.rows=[{ssid:'recovered',rssi:-42}];await page.click('#scan');
  await page.waitForFunction(()=>document.getElementById('networks').options.length===2);pass('failed scan has distinct retry and recovers');
  await page.fill('#ssid','recovered');await page.fill('#password','test-password');await page.click('#connect');sim.status='storage_error';
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('opslaan niet bevestigd'));
  assert.equal(await page.locator('#handoff').isHidden(),true);assert.equal(await page.locator('#connect').isDisabled(),false);assert.deepEqual(errors,[]);pass('storage failure is not success and remains retryable');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';sim.dropFinish=true;
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  assert.equal(sim.finishes,1);await page.clock.fastForward(11000);await page.waitForURL('http://192.168.1.90/');pass('lost finish acknowledgement recovers deadline via status without duplicate completion');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';sim.finishError=true;
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('nog niet bevestigd'));
  await page.clock.fastForward(12000);assert.equal(page.url(),'http://opth.test/setup.html');assert.equal(sim.closing,false);pass('rejected finish never triggers an unconfirmed redirect');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';sim.closing=true;sim.closeMs=3000;
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  assert.equal(sim.finishes,0);await page.clock.fastForward(5500);await page.waitForURL('http://192.168.1.90/');pass('page reload during handoff resumes existing deadline without another Finish POST');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='999.168.1.90';
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('weggevallen'));
  assert.equal(sim.finishes,0);assert.equal(await page.locator('#handoff').isHidden(),true);pass('invalid station address cannot become a redirect target');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';sim.station_port=8080;
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  assert.equal(await page.getAttribute('#home','href'),'http://192.168.1.90:8080/');pass('handoff link preserves the actual device HTTP port');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  sim.connected=false;sim.closing=false;await page.waitForFunction(()=>document.getElementById('status').textContent.includes('weggevallen'));
  await page.clock.fastForward(12000);assert.equal(page.url(),'http://opth.test/setup.html');assert.equal(await page.locator('#network-fields').isVisible(),true);pass('station loss cancels scheduled navigation and restores the form beyond the old deadline');await page.close();
  ({page,sim,errors}=await scene());sim.status='connected_saved';sim.connected=true;sim.station_ip='192.168.1.90';
  await page.waitForFunction(()=>document.getElementById('transition').textContent.includes('seconden'));
  sim.statusDrops=99;await page.clock.fastForward(11000);await page.waitForURL('http://192.168.1.90/');pass('acknowledged handoff still navigates after the setup AP disappears');await page.close();
  console.log(passed+' browser scenarios passed (simulated API, not ESP32 RF proof)');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
