// Home page (E32 beta.23) with simulated HTTP: the house mode (automatic, at home, away, holiday until a date), the away
// temperature, presence from Home Assistant, and the menu entry. POST /config/heating/comfort {"house_mode":..}.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]};
const fixture=()=>({schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},rooms:[],ble_sensors:[],shadow:{today:{s:0},days:[]},
  away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'}});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,scheme] of [[1280,'light'],[360,'dark']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme}),errors=[],posts=[];
  let status=fixture(),reject=null;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.route('http://opth.test/**',async r=>{
   const request=r.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'b'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(status);
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/flow')return r.fulfill({status:404,contentType:'text/plain',body:'Not found'});
   if(p==='/config/heating/comfort'&&request.method()==='POST'){
    assert.equal(request.headers()['x-openthermostat-csrf'],'b'.repeat(64));
    const body=request.postDataJSON();posts.push(body);
    if(reject){const x=reject;reject=null;return json({error:x.error},x.code);}
    // The E32 as RoomOverrides::command: the mode and the away temperature.
    const a=status.away;a.mode=body.house_mode;if(typeof body.temperature==='number')a.target_c=body.temperature;
    a.on=body.house_mode==='away'||body.house_mode==='holiday';a.source=a.on?'manual':'none';a.until=body.house_mode==='holiday'?body.until:null;
    return json({schema:1,away:a,rooms:[]});
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  // The menu: Overzicht · Ruimtes · Huis · Ketel ..., and #house opens the page.
  const menu=await page.locator('#navbarNavDropdown > ul > li:not([hidden]) > a.nav-link').allInnerTexts();
  assert.deepEqual(menu.slice(0,4).map(t=>t.trim()),['Overzicht','Ruimtes','Huis','Ketel']);
  await page.evaluate(()=>openPage('house'));
  const root=page.locator('#house-settings'),now=root.locator('[data-house-now]'),message=root.locator('[data-house-message]');
  await now.getByText('Automatisch: er is iemand thuis, dus de ruimtes volgen hun weekprogramma.').waitFor();
  assert.equal(await page.evaluate(()=>location.hash),'#house');
  assert.equal(await page.title(),'Huis · OpenThermostat');
  const button=name=>root.getByRole('button',{name,exact:true});
  assert.equal(await button('Automatisch').getAttribute('aria-pressed'),'true');
  assert.equal(await root.locator('[data-house-presence-now]').innerText(),'Nu: er is iemand thuis.');
  assert.equal(await root.locator('[data-house-away-c]').inputValue(),'15');
  assert.equal(await root.locator('[data-house-holiday]').isVisible(),false);
  // At home: one POST, the E32's answer is shown.
  await button('Thuis').click();
  await message.getByText('Huismodus opgeslagen.').waitFor();
  assert.deepEqual(posts.at(-1),{house_mode:'home'});
  await now.getByText('Thuis: de ruimtes volgen hun weekprogramma, ook als iedereen weg is.').waitFor();
  assert.equal(await button('Thuis').getAttribute('aria-pressed'),'true');assert.equal(await button('Automatisch').getAttribute('aria-pressed'),'false');
  // Away temperature: sent with the current mode.
  await root.locator('[data-house-away-c]').fill('16.5');await root.locator('[data-house-away-save]').click();
  await message.getByText('Temperatuur opgeslagen.').waitFor();
  assert.deepEqual(posts.at(-1),{house_mode:'home',temperature:16.5});
  // Holiday: first a date, refused in the page without one; then sent with the date as unix time.
  const count=posts.length;
  await button('Vakantie').click();
  assert.equal(await root.locator('[data-house-holiday]').isVisible(),true);
  assert.equal(posts.length,count,'choosing holiday sends nothing yet');
  await root.getByRole('button',{name:'Vakantie starten'}).click();
  await message.getByText('Kies een datum en tijd in de toekomst, hooguit een jaar vooruit.').waitFor();
  assert.equal(posts.length,count);
  const local='2030-07-14T17:00',unix=await page.evaluate(v=>Math.floor(new Date(v).getTime()/1000),local);
  await root.locator('[data-house-until]').fill(local);await root.getByRole('button',{name:'Vakantie starten'}).click();
  await message.getByText('Vakantie opgeslagen.').waitFor();
  assert.deepEqual(posts.at(-1),{house_mode:'holiday',until:unix});
  await now.getByText(/^Vakantie tot .+: elke ruimte hooguit 16,5 °C, en op tijd weer warm\.$/).waitFor();
  // Away, and the E32's refusal in plain words.
  reject={code:409,error:'no_clock'};
  await button('Afwezig').click();
  await message.getByText(/De klok van de E32 is nog niet gelijkgezet/).waitFor();
  await button('Afwezig').click();
  await now.getByText('Afwezig: elke ruimte hooguit 16,5 °C, tot je het terugzet.').waitFor();
  assert.deepEqual(posts.at(-1),{house_mode:'away'});
  // Automatic with everyone away, and unknown presence (no report for 15 minutes).
  await button('Automatisch').click();await message.getByText('Huismodus opgeslagen.').waitFor();
  Object.assign(status.away,{on:true,source:'presence',presence:'away'});
  await now.getByText('Automatisch: iedereen is weg, dus elke ruimte is hooguit 16,5 °C.').waitFor({timeout:15000});
  assert.equal(await root.locator('[data-house-presence-now]').innerText(),'Nu: iedereen is weg.');
  Object.assign(status.away,{on:false,source:'none',presence:'unknown'});
  await root.locator('[data-house-presence-now]').getByText(/^Nu: niet bekend/).waitFor({timeout:15000});
  // 44 px targets, no horizontal scroll at phone width, theme tokens.
  for(const name of ['Automatisch','Thuis','Afwezig','Vakantie']){const b=await button(name).boundingBox();assert(b.height>=44,'44 px target: '+name);}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  const bg=await root.locator('[data-house-mode-panel]').evaluate(e=>getComputedStyle(e).backgroundColor);
  assert.equal(bg,scheme==='dark'?'rgb(22, 33, 36)':'rgb(255, 255, 255)');
  // Firmware without house modes (beta.21): "At home" is hidden, the mode follows the away state.
  status=fixture();delete status.away.mode;status.away={...status.away,on:true,source:'manual',until:null};
  await page.evaluate(()=>loadNativePage('house'));
  await now.getByText('Afwezig: elke ruimte hooguit 15,0 °C, tot je het terugzet.').waitFor();
  assert.equal(await button('Thuis').isVisible(),false);
  // The old link to the flow limits opens the Home page there.
  await page.evaluate(()=>{location.hash='#boiler-limits';});
  await page.locator('#house-settings #boiler-limits').waitFor();
  assert.equal(await page.locator('#boiler-test').count(),0);
  assert.deepEqual(errors,[]);
  results.push({width,scheme,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
