// Exercise the actual settings-page WiFi entry in Chromium. HTTP is simulated.
const {chromium}=require('playwright-core'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.resolve(__dirname,'../../data/html/network.html'),'utf8');
const source=html.slice(html.indexOf('async function loadWiFiSettings()'),html.indexOf('\n\tfunction loadLegacyWiFiSettings()'));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});let passed=0;
 const pass=name=>{passed++;console.log('PASS '+name);};
 try {
  const page=await browser.newPage();let status=200,active=false,reentries=0;
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const p=new URL(route.request().url()).pathname;
   if(['/ui-language.js','/ui-messages.js'].includes(p))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.resolve(__dirname,'../../data/html',p.slice(1)),'utf8')});
   if(p==='/setup/status')return route.fulfill({status,contentType:'application/json',json:{setup_active:active}});
   if(p==='/setup/reenter'){reentries++;return route.fulfill({status:202,body:'accepted'});}
   return route.fulfill({contentType:'text/html',body:'<script src="/ui-messages.js"></script><script src="/ui-language.js"></script><div id="WiFiSettings"><input id="WiFiSSID"></div>'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/settings');

  await page.addScriptTag({content:'const hostName="http://opth.test"; window.legacyLoads=0; function loadLegacyWiFiSettings(){window.legacyLoads++;}\n'+source});
  await page.evaluate(()=>loadWiFiSettings());
  assert.equal(await page.locator('#WiFiSSID').count(),0);await page.click('#WiFiSettings button');
  await page.waitForFunction(()=>document.getElementById('WiFiSettings').textContent.includes('10.10.10.1'));
  assert.equal(reentries,1);pass('normal E32 settings route requests deliberate setup reboot and shows recovery address');
  active=true;await page.evaluate(()=>loadWiFiSettings());await page.click('#WiFiSettings button');await page.waitForURL('http://opth.test/setup');
  assert.equal(reentries,1);pass('active AP settings route opens the same onboarding without another reboot');
  await page.addScriptTag({content:'const hostName="http://opth.test"; window.legacyLoads=0; function loadLegacyWiFiSettings(){window.legacyLoads++;}\n'+source});
  status=404;await page.evaluate(()=>loadWiFiSettings());assert.equal(await page.evaluate(()=>window.legacyLoads),1);pass('generic boards retain legacy WiFi configuration path');
  status=503;await page.evaluate(()=>loadWiFiSettings());assert.match(await page.locator('#WiFiSettings button').textContent(),/opnieuw laden/);
  status=200;await page.click('#WiFiSettings button');await page.waitForFunction(()=>document.querySelector('#WiFiSettings button').textContent==='Open wifi-installatie');
  assert.deepEqual(errors,[]);pass('failed E32 status read offers working retry instead of broken legacy controls');
  console.log(passed+' settings-entry browser scenarios passed (simulated HTTP)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
