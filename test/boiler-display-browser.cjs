// Real shipped root/settings/SVG; isolated authenticated HTTP and device storage.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const output=path.resolve(process.env.OPENTHERMOSTAT_BOILER_DISPLAY_EVIDENCE||path.join(__dirname,'../out/boiler-display-browser'));
const catalog=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../public/boilers/catalog-v1.json')));
const imageURL=catalog.models.find(m=>m.id==='emsesp-product-122').image;
const status={controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}};
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}],['narrow',{width:320,height:844}],['narrow-wide-font',{width:320,height:844}]]){
  const page=await browser.newPage({viewport});const errors=[],requests=[],imageRequests=[];let stored='none',failSave=false,invalidRead=false,echoOnly=false,holdReadback=false,heldReadback=null,imagesOffline=false;
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('https://**/*',route=>{
   imageRequests.push({url:route.request().url(),offline:imagesOffline});
   const model=catalog.models.find(m=>m.image===route.request().url());assert(model,'Unexpected external request');
   assert.equal(route.request().method(),'GET');assert.equal(route.request().headers().referer,undefined);
   return imagesOffline?route.abort():route.fulfill({contentType:'image/svg+xml',body:fs.readFileSync(path.resolve(__dirname,'../public/boilers/images/nefit-ecomline.svg'))});
  });
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;
   requests.push({path:p,method:request.method(),csrf:request.headers()['x-openthermostat-csrf']});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify(status)});
   if(p==='/config/boiler-display'){
    if(holdReadback&&request.method()==='GET'){heldReadback=route;return;}
    if(request.method()==='POST'){
     if(failSave)return route.fulfill({status:503,body:'storage failure'});
     const body=request.postDataJSON();assert.deepEqual(Object.keys(body),['model']);
     assert(catalog.models.some(m=>m.id===body.model));if(echoOnly)return route.fulfill({contentType:'application/json',body:JSON.stringify({model:body.model})});stored=body.model;
    }
    return route.fulfill({contentType:'application/json',body:JSON.stringify({model:invalidRead?'<img src=https://foreign.test/p.png>':stored})});
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.svg')?'image/svg+xml':p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.locator('#boiler-home').waitFor();
  if(name==='narrow-wide-font')await page.addStyleTag({content:'body{font-family:DejaVu Sans,sans-serif;letter-spacing:.5px}'});
  assert.match(await page.locator('#boiler-home').innerText(),/Nog geen ketel gekozen/);
  assert.equal(await page.locator('#boiler-home img').count(),0);
  await page.locator('#boiler-home .boiler-setup-link').click();await page.locator('#boiler-model:enabled').waitFor();
  assert.equal(await page.locator('#boiler-model option').count(),catalog.models.filter(m=>m.selectable!==false).length);
  const labels=await page.locator('#boiler-model option').allTextContents();
  assert.equal(new Set(labels).size,labels.length,'Duplicate model choices');
  assert.deepEqual(labels.slice(1),[...labels.slice(1)].sort((a,b)=>a.localeCompare(b,'en')));
  for(const m of catalog.models.filter(m=>m.selectable===true)) assert(m.name.startsWith(m.brand+' '));
  await page.locator('#boiler-model').selectOption('nefit-ecomline-classic-hrc-22h');
  assert.match(await page.locator('figure img').getAttribute('src'),/^data:image\/svg\+xml/);
  assert.equal(await page.locator('figure img').getAttribute('alt'),'Algemene ketelillustratie');
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Ketelkeuze opgeslagen'}).waitFor();
  assert.equal(stored,'nefit-ecomline-classic-hrc-22h');
  await page.evaluate(()=>mainScreen());await page.getByRole('heading',{name:'Nefit Ecomline Classic HRC 22H',exact:true}).waitFor();
  assert.match(await page.locator('#boiler-home h2').innerText(),/Nefit Ecomline Classic HRC 22H/);
  assert.match(await page.locator('#boiler-home img').getAttribute('src'),/^data:image\/svg\+xml/);
  await page.waitForFunction(()=>document.querySelector('#boiler-home img')?.naturalWidth>0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,JSON.stringify(await page.evaluate(()=>({viewport:innerWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,100)})).slice(0,12)}))));
  await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
  // A full page reload reads the saved device setting, with no localStorage.
  await page.reload();await page.getByRole('heading',{name:'Nefit Ecomline Classic HRC 22H',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  await page.locator('#boiler-home .boiler-setup-link').click();await page.locator('#boiler-model:enabled').waitFor();
  assert.equal(await page.locator('#boiler-model').inputValue(),'nefit-ecomline-classic-hrc-22h');
  failSave=true;await page.locator('#boiler-model').selectOption('none');
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Opslaan kon niet worden bevestigd'}).waitFor();
  assert.equal(stored,'nefit-ecomline-classic-hrc-22h');
  assert.equal(await page.locator('#boiler-model').inputValue(),'none');
  assert(await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).isDisabled());
  const writesBeforeRetry=requests.filter(r=>r.method==='POST').length;
  await page.evaluate(()=>document.querySelector('#boiler-model').closest('form').requestSubmit());
  assert.equal(requests.filter(r=>r.method==='POST').length,writesBeforeRetry);
  failSave=false;echoOnly=true;
  await page.evaluate(()=>loadNativePage('boiler_display'));await page.locator('#boiler-model:enabled').waitFor();
  await page.locator('#boiler-model').selectOption('none');
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Opslaan kon niet worden bevestigd'}).waitFor();
  assert.equal(stored,'nefit-ecomline-classic-hrc-22h','POST echo is not persisted readback');
  assert(await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).isDisabled());
  echoOnly=false;await page.evaluate(()=>loadNativePage('boiler_display'));await page.locator('#boiler-model:enabled').waitFor();
  await page.locator('#boiler-model').selectOption('none');
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Ketelkeuze opgeslagen'}).waitFor();
  await page.evaluate(()=>mainScreen());await page.locator('#boiler-home').waitFor();
  assert.equal(await page.locator('#boiler-home img').count(),0);
  if(name==='desktop'){
   await page.locator('#boiler-home .boiler-setup-link').click();await page.locator('#boiler-model:enabled').waitFor();
   await page.locator('#boiler-model').selectOption('nefit-ecomline-classic-hrc-22h');
   holdReadback=true;const beforeTimeout=requests.filter(r=>r.method==='POST').length;
   await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
   await page.getByRole('status').filter({hasText:'Opslaan kon niet worden bevestigd'}).waitFor({timeout:8000});
   assert(heldReadback,'independent readback was not attempted');
   assert.equal(stored,'nefit-ecomline-classic-hrc-22h','timeout must not assume the write failed');
   assert(await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).isDisabled());
   assert.equal(requests.filter(r=>r.method==='POST').length,beforeTimeout+1,'lost readback retried a mutation');
   holdReadback=false;await heldReadback.fulfill({contentType:'application/json',body:JSON.stringify({model:stored})});
  }
  // A newly catalogued model persists without fetching any remote profile or image.
  await page.evaluate(()=>loadNativePage('boiler_display'));await page.locator('#boiler-model:enabled').waitFor();
  await page.locator('#boiler-model').selectOption('bosch-condens-5000i');
  assert.match(await page.locator('figure').innerText(),/nog niet gecontroleerd/);
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Ketelkeuze opgeslagen'}).waitFor();
  await page.reload();await page.getByRole('heading',{name:catalog.models.find(m=>m.id==='bosch-condens-5000i').name,exact:true}).waitFor();
  assert.match(await page.locator('#boiler-home img').getAttribute('src'),/^data:image\/svg\+xml/);
  // Exact family imagery appears only on its own selection, with provenance.
  await page.locator('#boiler-home .boiler-setup-link').click();await page.locator('#boiler-model:enabled').waitFor();
  await page.locator('#boiler-model').selectOption('nefit-proline');
  assert.equal(await page.locator('figure img').getAttribute('src'),imageURL);
  assert.match(await page.locator('figure').innerText(),/Bron productafbeelding: BBQKees/);
  await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Ketelkeuze opgeslagen'}).waitFor();
  await page.reload();await page.waitForFunction(()=>document.querySelector('#boiler-home img')?.naturalWidth>0);
  assert.equal(await page.locator('#boiler-home img').getAttribute('src'),imageURL);
  assert.equal(await page.locator('#boiler-home img').getAttribute('alt'),'Nefit ProLine HRC (EMS)');
  // Unavailable public image never disables selection or the local dashboard.
  imagesOffline=true;stored='emsesp-doc-nefit-smartline';await page.reload();
  await page.getByRole('heading',{name:'Nefit SmartLine',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('#boiler-home img')?.src.startsWith('data:image/svg+xml') && document.querySelector('#boiler-home img').naturalWidth>0);
  assert.equal(await page.locator('#boiler-home img').getAttribute('alt'),'Algemene ketelillustratie');
  assert.equal(await page.locator('#boiler-home [data-image-source]').count(),0);
  await page.locator('#boiler-home .boiler-setup-link').click();await page.locator('#boiler-model:enabled').waitFor();
  await page.waitForFunction(()=>document.querySelector('figure img')?.src.startsWith('data:image/svg+xml') && document.querySelector('figure img').naturalWidth>0);
  assert.equal(await page.locator('figure [data-image-source]').count(),0);
  assert.equal(await page.locator('#boiler-model').inputValue(),'emsesp-doc-nefit-smartline');
  assert.equal(await page.locator('#boiler-model option[value=emsesp-doc-nefit-smartline]').count(),1);
  const legacyLabels=await page.locator('#boiler-model option').allTextContents();
  assert.equal(new Set(legacyLabels).size,legacyLabels.length,'Legacy selection must not duplicate its canonical label');
  assert.equal(await page.locator('#boiler-model option[value=emsesp-product-195]').count(),0,'Unselected legacy group must stay hidden');
  assert.equal(await page.getByRole('button',{name:'Ketelkeuze opslaan',exact:true}).isEnabled(),true);
  assert(imageRequests.some(r=>r.offline),'Offline case must intercept an actual failed image request');
  invalidRead=true;await page.reload();
  await page.getByRole('heading',{name:'Ketelkeuze niet beschikbaar'}).waitFor();
  assert.equal(await page.locator('#boiler-home img').count(),0);
  assert(!requests.some(r=>r.path.includes('foreign.test')));
  assert(requests.filter(r=>r.method==='POST').every(r=>r.path==='/config/boiler-display'&&r.csrf==='a'.repeat(64)));
  assert.deepEqual(errors,[]);results.push({viewport:name,result:'PASS',saved_model_display:true,readback_after_reload:true,save_failure_preserves_draft:true,uncertain_save_no_replay:true,post_echo_not_readback:true,unknown_model_not_rendered:true,control_writes:0});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'BROWSER.json'),JSON.stringify({result:'PASS',scope:'Shipped UI and SVG; simulated HTTP/storage, no physical device change',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
