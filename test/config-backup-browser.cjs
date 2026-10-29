// Backup and restore panel on the network page (data/html/backup.js) against a
// simulated E32 over isolated HTTP. No device actions; all values are fixtures.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),vm=require('node:vm'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const config={hostname:'Fixture',interface_mode:'wifi',listenPort:80,emsEnabled:false,emsForwarderEnabled:false,rtcEnabled:false,
 ntpEnabled:true,ntpHost:'pool.ntp.org',ntpUtcOffset:0,ntpDaylightUtcOffset:0,timeZone:'UTC',loggerEnabled:false,loggerHost:'',loggerPort:0,loggerTimeoutMs:1000,
 bt:{scanTime:10,scanInterval:30},mqtt:{enabled:false,modern_shadow:true,adapter_id:'fixture',brokerAddress:'127.0.0.1',brokerPort:1883,
  username:'',password:'',clientId:'fixture',base:'fixture',keepAlive:30,interval:10}};
const backup=(sealed)=>({format:'openthermostat-e32-backup',schema:1,firmware:'0.1.0-e32v2-beta.19',board:'e32v2',created:'2026-10-29T20:00:00Z',
 secrets:sealed?{cipher:'aes-128-ccm',kdf:'pbkdf2-sha256',iterations:4096,box:'ab'.repeat(60)}:null,
 not_included:sealed?['wifi_password','web_password']:['wifi_password','web_password','mqtt_password','bluetooth_keys'],
 network:{hostname:'heating-home',mqtt:{brokerAddress:'192.0.2.10'}},bluetooth:{devices:[{address:'5448e68f80a5',profile:'shelly_ht_display',encryption:'bthome_v2',name:'Living'}]},
 heating:{schema:1,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]},flow:{weather_curve:true,apply_learned:false,curve_design_flow_c:0},
 boiler_display:{model:'none'},ui:{language:'nl'}});
const summary={valid:true,fingerprint:'f'.repeat(64),restart:true,secrets_sealed:true,secrets_restored:true,language:'nl',
 changes:[{section:'network',field:'hostname',from:'',to:'heating-home'},{section:'network',field:'mqtt.password',hidden:true},
  {section:'heating',field:'rooms',from:[],to:['<img src=x onerror=alert(1)>','Bath']},{section:'flow',field:'weather_curve',from:false,to:true}],
 warnings:['wifi_not_restored','unknown_key:network.future','other_firmware:0.1.0-e32v2-beta.18'],reenter:['bluetooth_key:Living']};
(async()=>{
 const context={window:{}};vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(assets,'ui-messages.js'),'utf8'),context);vm.runInContext(fs.readFileSync(path.join(assets,'backup.js'),'utf8'),context);
 const catalog=context.window.OT_UI_MESSAGES,missing=context.window.ConfigBackupPage.messages.filter(m=>!Object.hasOwn(catalog,m));
 assert.equal(missing.length,0,'every backup panel message has a Dutch catalog entry: '+missing.join(' | '));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,320]){
  const page=await browser.newPage({viewport:{width,height:900},acceptDownloads:true}),errors=[],posts=[];let dialogs=0,reply=null;
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{++dialogs;d.dismiss();});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   if(url.origin!=='http://opth.test')return route.abort();
   const json=(value,status=200)=>route.fulfill({json:value,status});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/setup/status')return json({setup_active:false});
   if(p==='/config/device')return json(config);
   if(p==='/config/debug')return json({});
   if(p==='/config/backup'){
    assert.equal(req.method(),'POST');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    const body=req.postDataJSON();posts.push(body);
    if(reply)return json(...reply);
    if(body.action==='export')return json(backup(!!body.passphrase));
    if(body.action==='validate')return json(summary);
    if(body.action==='apply')return json({applied:true,restart:true,restart_scheduled:true,restart_in_s:10,language:'nl',reenter:['bluetooth_key:Living']},201);
    return json({error:'invalid_request'},400);
   }
   let file=path.join(assets,p==='/'?'index.html':p);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':/\.css(?:\.gz)?$/.test(p)?'text/css':'text/html'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.locator('.product-dashboard').waitFor();
  await page.evaluate(()=>loadNativePage('network'));await page.waitForFunction(()=>document.getElementById('DeviceHostname')?.value==='Fixture');
  await page.locator('#BackupDownload').waitFor({state:'attached'});assert.equal(posts.length,0,'nothing is requested before the owner acts');
  const panel=page.locator('#ConfigBackup');await panel.locator(':scope > summary').click();
  const status=page.locator('#BackupStatus'),restore=page.locator('#RestoreStatus'),check=page.locator('#RestoreCheck'),apply=page.locator('#RestoreApply');
  assert.match(await panel.locator(':scope > summary').innerText(),lang==='nl'?/Back-up en terugzetten/:/Backup and restore/);
  // Plain export: a downloaded file and the list of what to enter again.
  let wait=page.waitForEvent('download');await page.locator('#BackupDownload').click();let download=await wait;
  assert.match(download.suggestedFilename(),/^openthermostat-e32-backup-2026-10-29\.json$/);
  const saved=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.equal(saved.format,'openthermostat-e32-backup');assert.equal(saved.secrets,null);
  assert.deepEqual(posts.at(-1),{action:'export',language:lang});
  await page.waitForFunction(l=>new RegExp(l==='nl'?'Wifi-wachtwoord.*MQTT-wachtwoord':'Wi-Fi password.*MQTT password').test(document.getElementById('BackupStatus').textContent),lang);
  // Encrypted export: passphrase rules are checked before any request.
  await page.locator('#BackupSecrets').check();await page.locator('#BackupPassphrase').waitFor();
  await page.fill('#BackupPassphrase','short');await page.locator('#BackupDownload').click();
  assert.match(await status.innerText(),lang==='nl'?/8 tot 64/:/8 to 64/);
  await page.fill('#BackupPassphrase','correct horse');await page.fill('#BackupPassphrase2','correct house');await page.locator('#BackupDownload').click();
  assert.match(await status.innerText(),lang==='nl'?/niet gelijk/:/do not match/);assert.equal(posts.length,1);
  await page.fill('#BackupPassphrase2','correct horse');wait=page.waitForEvent('download');await page.locator('#BackupDownload').click();download=await wait;
  assert.equal(posts.at(-1).passphrase,'correct horse');assert.equal(JSON.parse(fs.readFileSync(await download.path(),'utf8')).secrets.cipher,'aes-128-ccm');
  assert.equal(await page.inputValue('#BackupPassphrase'),'');
  // A file that is not a backup never reaches the E32.
  await page.setInputFiles('#RestoreFile',{name:'other.json',mimeType:'application/json',buffer:Buffer.from('{"hello":1}')});
  await page.waitForFunction(l=>new RegExp(l==='nl'?'geen back-up':'not an OpenThermostat').test(document.getElementById('RestoreStatus').textContent),lang);
  assert.equal(await check.isDisabled(),true);
  await page.setInputFiles('#RestoreFile',{name:'big.json',mimeType:'application/json',buffer:Buffer.alloc(30000,32)});
  await page.waitForFunction(l=>new RegExp(l==='nl'?'te groot':'too large').test(document.getElementById('RestoreStatus').textContent),lang);
  // Staged restore: choose, check (summary), then restore.
  await page.setInputFiles('#RestoreFile',{name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup(true)))});
  await page.locator('#RestorePassphrase').waitFor();assert.equal(await check.isEnabled(),true);assert.equal(await apply.isDisabled(),true);
  // A wrong passphrase is reported and nothing can be applied.
  reply=[{error:'wrong_passphrase'},400];await page.fill('#RestorePassphrase','not the one');await check.click();
  await page.waitForFunction(l=>new RegExp(l==='nl'?'wachtzin klopt niet':'passphrase is not correct').test(document.getElementById('RestoreStatus').textContent),lang);
  assert.equal(await apply.isDisabled(),true);
  reply=[{error:'heating_invalid',warnings:['heating:invalid_room_limits']},400];await check.click();
  await page.waitForFunction(()=>/invalid_room_limits/.test(document.getElementById('RestoreStatus').textContent));
  assert.equal(await apply.isDisabled(),true);reply=null;
  await page.fill('#RestorePassphrase','correct horse');await check.click();await page.waitForFunction(()=>document.getElementById('RestoreApply')?.disabled===false);
  const validate=posts.at(-1);assert.equal(validate.action,'validate');assert.equal(validate.passphrase,'correct horse');assert.equal(validate.backup.format,'openthermostat-e32-backup');
  const shown=await page.locator('#RestoreSummary').innerText();
  assert.match(shown,lang==='nl'?/Netwerk · Apparaatnaam: — → heating-home/:/Network · Device name: — → heating-home/);
  assert.match(shown,lang==='nl'?/MQTT-wachtwoord: verandert/:/MQTT password: will change/);
  assert.match(shown,lang==='nl'?/Weersafhankelijke stooklijn: Uit → Aan/:/Weather curve: Off → On/);
  assert.match(shown,lang==='nl'?/Terugzetten verandert de wifi niet/:/Wi-Fi is not changed by a restore/);
  assert.match(shown,lang==='nl'?/onbekend voor deze firmware: network\.future/:/not known by this firmware: network\.future/);
  assert.match(shown,lang==='nl'?/Bluetooth-sleutel van Living/:/Bluetooth key for Living/);
  assert.match(shown,/<img src=x onerror=alert\(1\)>/);assert.equal(await panel.locator('img').count(),0);
  if(lang==='nl')assert.doesNotMatch(shown,/will change|Device name|Wi-Fi is not changed/);
  await apply.click();await page.waitForFunction(l=>new RegExp(l==='nl'?'Instellingen teruggezet':'Settings restored').test(document.getElementById('RestoreStatus').textContent),lang);
  if(process.env.OT_BACKUP_SHOT)await panel.screenshot({path:path.join(process.env.OT_BACKUP_SHOT,`backup-${lang}-${width}.png`)});
  const applied=posts.at(-1);assert.equal(applied.action,'apply');assert.equal(applied.fingerprint,'f'.repeat(64));assert.equal(applied.passphrase,'correct horse');
  assert.match(await restore.innerText(),lang==='nl'?/ongeveer 10 seconden/:/about 10 seconds/);
  assert.equal(await apply.isDisabled(),true,'a restore is applied once');
  const cookies=await page.context().cookies();assert.equal(cookies.find(c=>c.name==='ot_ui_lang').value,'nl','the restored UI language applies on the next page load');
  // A changed device between check and restore is refused without replay.
  await check.click();await page.waitForFunction(()=>document.getElementById('RestoreApply')?.disabled===false);
  reply=[{error:'settings_changed'},409];const before=posts.length;await apply.click();
  await page.waitForFunction(l=>new RegExp(l==='nl'?'na de controle gewijzigd':'changed after the check').test(document.getElementById('RestoreStatus').textContent),lang);
  assert.equal(posts.length,before+1);assert.equal(await apply.isDisabled(),true);reply=null;
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  assert.equal(dialogs,0);assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',exportPlain:true,exportSealed:true,passphraseChecks:true,notABackup:true,tooLarge:true,
   wrongPassphrase:true,invalidReason:true,stagedSummary:true,textOnly:true,appliedOnce:true,languageCookie:true,changedRefused:true});
  await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
