// Real shipped EN/NL UI, isolated HTTP. No device/installation claim.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_LANGUAGE_EVIDENCE||'out/ui-language-browser');
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const language of ['en','nl'])for(const width of [1280,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],writes=[];
  let model='none';page.on('pageerror',e=>errors.push(e.message));
  if(language==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(req.method()!=='GET')writes.push({path:p,body:req.postDataJSON()});
   const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:true,captured_at_ms:1000,state:{boot_id:'language-test',zones:[{zone_id:'12345678',name:'Settings',temperature_centi_c:2000,target_centi_c:2100,demand:false}],supervisor:{requested_heat:false,reason:'shadow_idle'}}}});
   if(p==='/config/boiler-display'){if(req.method()==='POST')model=req.postDataJSON().model;return json({model});}
   if(p==='/setup/status')return json({setup_active:true,remaining_seconds:600,status:'ready',connected:false,station_ip:'0.0.0.0'});
   if(p==='/setup/scan')return json({status:'done',networks:[{ssid:'Settings',rssi:-40}]});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file)||!fs.statSync(file).isFile())return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':/\.css(?:\.gz)?$/.test(p)?'text/css':p.endsWith('.svg')?'image/svg+xml':'text/html',body});
  });
  const choose=(en,nl)=>language==='nl'?nl:en;
  await page.goto('http://opth.test/');await page.locator('#boiler-home').waitFor();
  assert.equal(await page.locator('html').getAttribute('lang'),language);
  assert.equal(await page.locator('.pd-room h3').innerText(),'Settings'); // User data matches a translated label.
  assert.equal(await page.locator('.product-dashboard h1').innerText(),choose('Your heating system','Je verwarmingsinstallatie'));
  assert.match(await page.locator('#boiler-home').innerText(),new RegExp(choose('No boiler selected yet','Nog geen ketel gekozen')));
  await page.evaluate(()=>loadNativePage('boiler_display'));await page.locator('#boiler-model:enabled').waitFor();
  assert.equal(await page.locator('#boiler-model option').first().getAttribute('value'),'none');
  assert.equal(await page.locator('#boiler-model option').first().innerText(),choose('No boiler selected yet','Nog geen ketel gekozen'));
  await page.locator('#boiler-model').selectOption('nefit-ecomline-classic');
  await page.getByRole('button',{name:choose('Save boiler selection','Ketelkeuze opslaan'),exact:true}).click();
  await page.getByRole('status').filter({hasText:choose('Boiler selection saved','Ketelkeuze opgeslagen')}).waitFor();
  assert.deepEqual(writes,[{path:'/config/boiler-display',body:{model:'nefit-ecomline-classic'}}]);
  await page.evaluate(()=>loadNativePage('about'));await page.locator('.ot-about').waitFor();
  assert.match(await page.locator('.ot-about-badge').innerText(),new RegExp(choose('In development & testing','In ontwikkeling en test')));
  await page.screenshot({path:path.join(out,language+'-'+width+'.png'),fullPage:true});
  await page.goto('http://opth.test/login.html');
  assert.equal(await page.locator('h2').innerText(),choose('Sign in','Aanmelden'));
  assert.equal(await page.locator('#username').inputValue(),'admin');
  await page.goto('http://opth.test/setup.html');await page.locator('#networks option').nth(1).waitFor({state:'attached'});
  assert.equal(await page.locator('#networks option').nth(1).getAttribute('value'),'Settings');
  assert.match(await page.locator('#networks option').nth(1).innerText(),/Settings/);
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  // Language reload is explicit and keeps no stale draft; no control/config write is made.
  await page.locator('#ssid').fill('Unsent draft');let dialogText='';
  page.once('dialog',async dialog=>{dialogText=dialog.message();await dialog.dismiss();});
  await page.locator('#ui-language-choice').selectOption(language==='en'?'nl':'en');
  assert.equal(await page.locator('#ssid').inputValue(),'Unsent draft');
  assert.equal(await page.locator('#ui-language-choice').inputValue(),language);
  assert.match(dialogText,new RegExp(choose('Unsaved changes','Niet-opgeslagen wijzigingen')));
  page.once('dialog',dialog=>dialog.accept());
  await Promise.all([page.waitForEvent('load'),page.locator('#ui-language-choice').selectOption(language==='en'?'nl':'en')]);
  assert.equal(await page.locator('html').getAttribute('lang'),language==='en'?'nl':'en');
  await page.reload();assert.equal(await page.locator('html').getAttribute('lang'),language==='en'?'nl':'en');
  assert.deepEqual(errors,[]);assert.deepEqual(writes.filter(write=>write.path!=='/setup/scan'),[{path:'/config/boiler-display',body:{model:'nefit-ecomline-classic'}}]);
  results.push({language,width,result:'PASS',defaultEnglish:language==='en',userLabelsPreserved:true,identifiersPreserved:true,reloadPreference:true,draftCancel:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',cases:results},null,2)+'\n');console.log(JSON.stringify({result:'PASS',profiles:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
