// The E32 menu (beta.23) with simulated HTTP: one fixed order Overview · Rooms · Home · Boiler · System, the System
// menu groups the technical pages (network and Home Assistant, password, backup, Bluetooth sensors, update,
// diagnostics, About, restart), old links keep opening the right page, and the menu fits a phone.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const words={
 en:{top:['Overview','Rooms','Home','Boiler','System'],
  system:['Network and Home Assistant','Password','Backup and restore','Bluetooth sensors','Firmware update','Diagnostics and system log','About']},
 nl:{top:['Overzicht','Ruimtes','Huis','Ketel','Systeem'],
  system:['Netwerk en Home Assistant','Wachtwoord','Back-up en terugzetten','Bluetooth-sensoren','Firmware bijwerken','Diagnose en systeemlog','Over']}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [lang,width,scheme] of [['en',1280,'light'],['nl',360,'dark']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme}),errors=[];
  page.on('pageerror',e=>errors.push(e.message+' @ '+String(e.stack).split(String.fromCharCode(10)).slice(1,3).join(' | ')+' hash='+page.url().split('#')[1]));
  await page.route('http://opth.test/**',async r=>{
   const p=new URL(r.request().url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'b'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p.startsWith('/status/')||p.startsWith('/config/')||p.startsWith('/updates/')||p.startsWith('/ble'))return json({});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  if(lang==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.locator('#auth-sign-out').waitFor();
  // 1. Top level in one fixed order; Sensors and Settings are no longer next to Rooms.
  const top=await page.locator('#navbarNavDropdown > ul > li:not([hidden]) > a.nav-link').allInnerTexts();
  assert.deepEqual(top.map(t=>t.trim()),words[lang].top);
  // 2. System groups the technical pages, in this order, with Restart at the end.
  const items=await page.locator('ul[aria-labelledby="navbarDropdownMenuLink"] > li:not([hidden]) > a.dropdown-item').allInnerTexts();
  assert.deepEqual(items.map(t=>t.trim()),words[lang].system);
  // 3. The menu fits a phone: opened, nothing scrolls sideways.
  // On a phone the menu slides open: under load a click during that animation is lost, so wait and retry.
  if(await page.locator('.navbar-toggler').isVisible()){
   await page.locator('.navbar-toggler').click();
   await page.waitForFunction(()=>{const c=document.getElementById('navbarNavDropdown');return c.classList.contains('show')&&!c.classList.contains('collapsing');});
  }
  const backupItem=page.locator('ul[aria-labelledby="navbarDropdownMenuLink"] a[data-page="backup"]');
  for(let i=0;i<3&&!(await backupItem.isVisible());i++){
   await page.locator('#navbarDropdownMenuLink').click();
   await backupItem.waitFor({state:'visible',timeout:5000}).catch(()=>{});
  }
  await backupItem.waitFor({state:'visible'});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll with the menu open');
  // 4. System → Backup and restore opens that panel on the settings page, and System is the active menu.
  await page.locator('ul[aria-labelledby="navbarDropdownMenuLink"] a[data-page="backup"]').click();
  await page.waitForFunction(()=>document.getElementById('ConfigBackup')?.open===true);
  assert.equal(await page.evaluate(()=>location.hash),'#backup');
  assert.equal(await page.evaluate(()=>document.getElementById('navbarDropdownMenuLink').classList.contains('active')),true);
  // 5. Old links and hashes keep opening the right page.
  const visit=async(hash,ready)=>{await page.evaluate(h=>{location.hash=h;},hash);await page.waitForFunction(ready,null,{timeout:10000});};
  await visit('#overview',()=>!document.getElementById('ConfigBackup'));
  await visit('#network',()=>!!document.getElementById('WiFiSettings'));
  await visit('#overview',()=>!document.getElementById('WiFiSettings'));
  await visit('#settings',()=>!!document.getElementById('WiFiSettings'));
  await visit('#password',()=>document.getElementById('settings-password')&&location.hash==='#password');
  await visit('#sensors',()=>!!document.getElementById('bluetooth-page'));
  await visit('#boiler-limits',()=>!!document.getElementById('house-settings'));
  await visit('#log',()=>!!document.getElementById('system-log'));
  await visit('#ems_devices',()=>location.hash==='#ems_devices'&&!!document.querySelector('a[data-nav="boiler_test"][aria-current="page"]'));
  assert.deepEqual(errors,[]);results.push({lang,width,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exit(1);});
