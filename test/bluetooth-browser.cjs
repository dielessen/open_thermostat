// Shipped Settings assets, mocked HTTP only; no radio, device or broker actions.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(__dirname,'../out/bluetooth-browser');
const publicFixtureKey='231d39c1d7cc1ab1aee224cd096db932';
function snapshot(profile='shelly_ht_display'){const result={schema:1,pending_restart:false,config_error:'none',queue_drops:0,scan_pending:false,discovery_full:false,nearby:['5448e68f80a5'],devices:[{address:'5448e68f80a5',profile:'shelly_ht_display',name:'Room <img src=x onerror=alert(1)>',encryption:'bthome_v2',key_stored:true,control_qualified:false,measurement_qualified:false,message_integrity:true,status:'received',temperature:2350,humidity:4500,battery:80,temperature_age_ms:100,humidity_age_ms:100,battery_age_ms:100,last_accepted_age_ms:100,target_temperature:null,external_temperature:null,state_revision:null,target_temperature_age_ms:null,external_temperature_age_ms:null,state_revision_age_ms:null,counter:4,rssi:-60,declared_device_type:12,firmware_32:1,firmware_24:2,light_level:1,button:null,battery_low:false,light:true,old_counter_drops:0}]};if(profile==='xiaomi_monitor_3')Object.assign(result.devices[0],{profile,encryption:'mibeacon_v4_v5',declared_device_type:0x2832,firmware_32:null,firmware_24:null,light_level:null,light:null,battery_low:null});if(profile==='shelly_blu_trv')Object.assign(result.devices[0],{profile,target_temperature:2200,external_temperature:2110,state_revision:63,target_temperature_age_ms:100,external_temperature_age_ms:100,state_revision_age_ms:100,humidity:null,declared_device_type:null,firmware_32:null,firmware_24:null,light_level:null,light:null,battery_low:null});return result;}
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,320])for(const profile of ['shelly_ht_display','xiaomi_monitor_3','shelly_blu_trv']){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],requests=[];let data=snapshot(profile),fail=false,conflict=false,storageFull=false,readbackFailure=false,readbackMismatch=false,postTransportFailure=false;
  page.on('pageerror',e=>errors.push(e.message));await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.addInitScript(()=>{const original=window.setTimeout;window.setTimeout=(fn,ms,...args)=>original(fn,ms===5000?80:ms,...args);});
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method(),body:req.postData()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(p==='/config/bluetooth'||p==='/bluetooth/status'){
    if(req.method()==='POST'){
      if(postTransportFailure)return route.abort('failed');
      assert.equal(req.headers()['if-match'],'"'+'b'.repeat(64)+'"');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
      if(storageFull)return route.fulfill({status:507,contentType:'application/json',body:'{\"error\":\"bluetooth_storage_full\"}'});
      if(conflict)return route.fulfill({status:412,contentType:'application/json',body:'{"error":"device_settings_changed"}'});
      const payload=JSON.parse(req.postData());if(payload.reset_invalid===true){assert.equal(payload.devices.length,0);data.config_error='none';data.pending_restart=true;return route.fulfill({status:201,contentType:'application/json',body:'{"changed":true,"pending_restart":true}'});}assert.equal(payload.devices.length,1);assert.equal(payload.devices[0].bindkey,publicFixtureKey);assert.equal(payload.devices[0].profile,profile);
      data.devices[0].name=payload.devices[0].name;data.pending_restart=true;data.devices[0].status='pending_restart';for(const key of ['temperature','humidity','battery','battery_low','light','light_level','button','target_temperature','external_temperature','state_revision'])data.devices[0][key]=null;
      return route.fulfill({status:201,contentType:'application/json',body:'{"changed":true,"pending_restart":true}'});
    }
    if(readbackFailure&&p==='/config/bluetooth')return route.fulfill({status:503,contentType:'application/json',body:'{"error":"fixture_failure"}'});
    if(fail)return route.fulfill({status:503,contentType:'application/json',body:'{"error":"fixture_failure"}'});
    const reported=readbackMismatch&&p==='/config/bluetooth'?{...data,devices:data.devices.map(d=>({...d,name:'Different stored name'}))}:data;
    const body=JSON.stringify(reported);assert(!body.includes(publicFixtureKey));return route.fulfill({contentType:'application/json',headers:{ETag:'"'+'b'.repeat(64)+'"'},body});
   }
   if(p==='/config/bluetooth/scan'){assert.equal(req.method(),'POST');return route.fulfill({status:202,contentType:'application/json',body:'{"scan_started":true}'});}
   const file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  data.nearby.push('aabbccddeeff');data.nearby_devices=[{address:data.nearby[0],name:'Saved sensor',rssi:-60},{address:'aabbccddeeff',name:'Sensor <img src=x>',rssi:-72}];
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor();if(await page.locator('.navbar-toggler').isVisible())await page.locator('.navbar-toggler').click();await page.locator('#navbarDropdownMenuLink').click();await page.locator('a[data-page="bluetooth"]').click();
  const root=page.locator('#bluetooth-page'),status=page.locator('#ble-status'),box=page.locator('#ble-rows fieldset');await box.waitFor();
  await page.waitForFunction(()=>document.querySelector('#ble-save')?.disabled===false);
  const found=page.locator('#ble-nearby');
  assert.equal(await found.locator('img').count(),0);
  assert.equal(await found.locator('[data-ble-address="5448e68f80a5"]').isDisabled(),true);
  const addFound=found.locator('[data-ble-address="aabbccddeeff"]');await addFound.click();
  const added=box.nth(1);await added.waitFor();
  assert.equal(await added.locator('[data-ble-field=address]').inputValue(),'aa:bb:cc:dd:ee:ff');
  assert.equal(await added.locator('[data-ble-field=name]').inputValue(),'Sensor <img src=x>');
  assert.equal(await addFound.isDisabled(),true);
  const newProfile=added.locator('[data-ble-field=profile]'),newKey=added.locator('input[type=password]');
  await newProfile.selectOption('xiaomi_monitor_3');
  assert.equal(await added.locator('[data-ble-field=key_action]').inputValue(),'set');
  assert.equal(await newKey.isVisible(),true);await newKey.fill(publicFixtureKey);
  await newProfile.selectOption('shelly_blu_trv');
  assert.equal(await newKey.inputValue(),'');assert.equal(await newKey.isVisible(),true);

  assert.equal(requests.filter(r=>r.method==='POST').length,0);
  await added.locator('button').click();assert.equal(await addFound.isDisabled(),false);
  // A refreshed discovery list removes old cards without disturbing saved rows.
  const hints=data.nearby_devices;data.nearby_devices=[hints[0]];data.nearby=[hints[0].address];
  await addFound.waitFor({state:'detached'});assert.equal(await box.count(),1);
  data.nearby_devices=hints;data.nearby=hints.map(d=>d.address);await addFound.waitFor();

  assert.equal(await box.locator('input[type=password]').inputValue(),'');assert.equal(await root.locator('img').count(),0);assert.equal(await box.locator('input').nth(1).inputValue(),data.devices[0].name);
  if(profile==='shelly_blu_trv'){
    assert.match(await box.locator('[data-readings]').innerText(),lang==='nl'?/Berekende TRV-temperatuur/:/Calculated TRV temperature/);
    const extra=await box.locator('[data-extra]').textContent();assert.match(extra,lang==='nl'?/Gemeld doel \(°C\): 22/:/Reported target \(°C\): 22/);assert.match(extra,/21.1/);assert.match(extra,/63/);
    assert(!String(await box.locator('[data-readings]').innerText()).includes(lang==='nl'?'Luchtvochtigheid':'Humidity'));
  }
  const name=box.locator('input').nth(1);await name.fill('Draft – Zoë');await name.focus();
  const details=root.locator('details').first();await details.locator('summary').click();await name.focus();
  data.devices[0].temperature=2410;await page.waitForFunction(()=>document.querySelector('[data-readings]')?.textContent.includes('24'));
  assert.equal(await name.inputValue(),'Draft – Zoë');assert.equal(await name.evaluate(e=>e===document.activeElement),true);assert.equal(await details.getAttribute('open'),'');
  if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)){await page.screenshot({path:path.join(output,`overflow-${profile}-${lang}-${width}.png`),fullPage:true});console.log(await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,width:e.getBoundingClientRect().width,text:e.textContent.slice(0,90)})).slice(-15)));}assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,`${profile}-${lang}-${width}.png`),fullPage:true});
  const mac=box.locator('input').nth(0),choice=box.locator('[data-ble-field=profile]');
  await mac.fill('54:48:e6:8f:80:a6');await page.waitForTimeout(160);assert.match(await box.locator('[data-readings]').innerText(),lang==='nl'?/Sla op en herstart/:/Save and restart/);assert.equal(await box.locator('[data-extra]').textContent(),'—');
  await mac.fill('54:48:e6:8f:80:a5');await page.waitForFunction(()=>document.querySelector('[data-readings]')?.textContent.includes('24'));
  await choice.selectOption(profile==='shelly_ht_display'?'xiaomi_monitor_3':'shelly_ht_display');assert.match(await box.locator('[data-readings]').innerText(),lang==='nl'?/Sla op en herstart/:/Save and restart/);
  if(profile==='shelly_ht_display')assert.equal(await box.locator('[data-ble-field=encryption] option').count(),1);
  await choice.selectOption(profile);await page.waitForFunction(()=>document.querySelector('[data-readings]')?.textContent.includes('24'));
  if(profile!=='xiaomi_monitor_3'){
    await box.locator('[data-ble-field=encryption]').selectOption('none');assert.equal(await box.locator('[data-ble-field=key_action]').isDisabled(),true);assert.equal(await box.locator('input[type=password]').isVisible(),false);
    await box.locator('[data-ble-field=encryption]').selectOption('bthome_v2');assert.equal(await box.locator('[data-ble-field=key_action]').inputValue(),'keep');await page.waitForFunction(()=>document.querySelector('[data-readings]')?.textContent.includes('24'));
  }
  fail=true;await page.waitForFunction(()=>document.querySelector('[data-readings]')?.textContent.includes(document.cookie.includes('ot_ui_lang=nl')?'niet beschikbaar':'unavailable'));
  assert.equal(await name.inputValue(),'Draft – Zoë');fail=false;
  await box.locator('[data-ble-field=key_action]').selectOption('set');const key=box.locator('input[type=password]');await key.fill(publicFixtureKey);
  // Polling never changes the key action, typed key, name, focus or panel state.
  await key.focus();const before=requests.filter(r=>r.path==='/bluetooth/status').length;await page.waitForTimeout(200);assert(requests.filter(r=>r.path==='/bluetooth/status').length>before);
  assert.equal(await key.inputValue(),publicFixtureKey);assert.equal(await key.evaluate(e=>e===document.activeElement),true);
  storageFull=true;await page.locator('#ble-save').click();await status.filter({hasText:lang==='nl'?'Onvoldoende apparaatopslag':'Not enough device storage'}).waitFor();assert.equal(data.pending_restart,false);assert.equal(await name.inputValue(),'Draft – Zoë');await page.waitForFunction(()=>document.querySelector('#ble-rows input[type=password]')?.value==='');storageFull=false;await key.fill(publicFixtureKey);
  conflict=true;await page.locator('#ble-save').click();await status.filter({hasText:lang==='nl'?'elders gewijzigd':'changed elsewhere'}).waitFor();assert.equal(await name.inputValue(),'Draft – Zoë');assert.equal(await key.inputValue(),'');
  conflict=false;readbackFailure=true;await key.fill(publicFixtureKey);await page.locator('#ble-save').click();
  await page.waitForFunction(()=>document.querySelector('#ble-save').disabled&&document.querySelector('#ble-rows input[type=password]').value==='');
  assert.equal(await name.inputValue(),'Draft – Zoë');
  assert.match(await status.textContent(),lang==='nl'?/niet.*bevestigd/:/not.*confirmed/);
  const postsBeforeRecovery=requests.filter(r=>r.method==='POST'&&r.path==='/config/bluetooth').length;
  await page.waitForTimeout(180);assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/config/bluetooth').length,postsBeforeRecovery);
  readbackFailure=false;page.once('dialog',dialog=>dialog.accept());await page.locator('#ble-reload').click();
  await page.waitForFunction(()=>document.querySelector('#ble-save').disabled===false);
  await box.locator('[data-ble-field=key_action]').selectOption('set');
  await key.fill(publicFixtureKey);await page.locator('#ble-save').click();await page.waitForFunction(()=>document.querySelector('#ble-rows input[type=password]')?.value==='');assert.equal(data.pending_restart,true);
  assert.equal(await page.locator('#ble-rows input[type=password]').inputValue(),'');assert.equal(await page.locator('#ble-rows input').nth(1).inputValue(),'Draft – Zoë');
  for(const mode of ['mismatch','transport']) {
    await box.locator('[data-ble-field=key_action]').selectOption('set');await key.fill(publicFixtureKey);
    readbackMismatch=mode==='mismatch';postTransportFailure=mode==='transport';
    await page.locator('#ble-save').click();
    await page.waitForFunction(()=>document.querySelector('#ble-save').disabled&&document.querySelector('#ble-rows input[type=password]').value==='');
    assert.equal(await name.inputValue(),'Draft – Zoë');
    await page.waitForTimeout(180);
    assert.match(await status.textContent(),lang==='nl'?/niet.*bevestigd/:/not.*confirmed/);
    const writes=requests.filter(r=>r.path==='/config/bluetooth'&&r.method==='POST').length;
    await page.waitForTimeout(180);assert.equal(requests.filter(r=>r.path==='/config/bluetooth'&&r.method==='POST').length,writes);
    readbackMismatch=false;postTransportFailure=false;
    page.once('dialog',dialog=>dialog.accept());await page.locator('#ble-reload').click();
    await page.waitForFunction(()=>document.querySelector('#ble-save').disabled===false);
  }
  assert.equal(await page.evaluate(()=>Object.values(localStorage).some(s=>s.includes('231d39c1d7cc1ab1aee224cd096db932'))),false);
  await page.locator('#ble-scan').click();assert(requests.some(r=>r.path==='/config/bluetooth/scan'&&r.method==='POST'));
  data.config_error='invalid_bluetooth_settings';data.devices=[];await page.locator('#ble-reload').click();await page.locator('#ble-reset').waitFor({state:'visible'});assert.equal(await page.locator('#ble-add').isDisabled(),true);page.once('dialog',dialog=>dialog.accept());await page.locator('#ble-reset').click();await page.locator('#ble-reset').waitFor({state:'hidden'});assert.equal(data.config_error,'none');
  const writesBeforeLeaving=requests.filter(r=>r.method==='POST').length;
  await page.evaluate(()=>{
    const original=OpenThermostatAuth.headers;let release;
    OpenThermostatAuth.headers=()=>new Promise(resolve=>{release=resolve;});
    document.querySelector('#ble-form').requestSubmit();
    BluetoothPage.unmount();document.querySelector('#bluetooth-page').remove();
    OpenThermostatAuth.headers=original;release({});
  });
  await page.waitForTimeout(180);assert.equal(requests.filter(r=>r.method==='POST').length,writesBeforeLeaving);
  await page.evaluate(()=>loadNativePage('about'));await root.waitFor({state:'detached'});const count=requests.filter(r=>r.path==='/bluetooth/status').length;await page.waitForTimeout(220);assert.equal(requests.filter(r=>r.path==='/bluetooth/status').length,count);
  assert(!requests.some(r=>/test\/start|updates\/(install|reboot)|config\/temporary/.test(r.path)));assert.deepEqual(errors,[]);
  results.push({lang,width,profile,result:'PASS',mock_http_only:true,keys_write_only:true,draft_preserved_during_poll:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
