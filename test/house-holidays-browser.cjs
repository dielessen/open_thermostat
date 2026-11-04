// Home page (E32 rc.4, F8) with simulated HTTP: the holiday planner (house.holidays.v1). Holidays are added, changed and
// removed as one list (POST /config/heating/comfort {"holidays":[..]}), the running one is stopped, the holiday temperature
// saved; local date and time become unix seconds with the offset of that date (summer and winter time). English at 1280 px,
// Dutch at 390 px; older firmware (no away.holidays) shows no block.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]};
const texts={
 en:{heading:'Holidays',empty:'No holidays planned.',add:'Plan a holiday',saved:'Holiday saved.',removed:'Holiday removed.',stopped:'Holiday stopped.',
  temperature:'Temperature saved.',dates:'Check the dates: a holiday ends after it starts.',past:'This holiday is already over. Choose an end in the future.',
  many:'At most 8 holidays can be planned. Remove one first.',change:'Change',remove:'Remove',stop:'Stop holiday',
  running:/^On holiday until .+\.$/,mode:/^Holiday until .+: every room at most 12\.0 °C, and warm again in time\.$/,to:' to '},
 nl:{heading:'Vakanties',empty:'Geen vakanties gepland.',add:'Vakantie plannen',saved:'Vakantie opgeslagen.',removed:'Vakantie verwijderd.',
  stopped:'Vakantie gestopt.',temperature:'Temperatuur opgeslagen.',dates:'Controleer de data: een vakantie eindigt na het begin.',
  past:'Deze vakantie is al voorbij. Kies een einde in de toekomst.',many:'Er kunnen hooguit 8 vakanties gepland worden. Verwijder er eerst een.',
  change:'Wijzigen',remove:'Verwijderen',stop:'Vakantie stoppen',running:/^Op vakantie tot .+\.$/,
  mode:/^Vakantie tot .+: elke ruimte hooguit 12,0 °C, en op tijd weer warm\.$/,to:' tot '}};
const utc=(y,m,d,h,min)=>Date.UTC(y,m-1,d,h,min)/1000;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,lang] of [[1280,'en'],[390,'nl']]){
  const t=texts[lang];
  const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Europe/Amsterdam',locale:lang==='nl'?'nl-NL':'en-GB'});
  const page=await context.newPage(),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  // The E32 as RoomOverrides: the whole list, merged (overlapping or touching periods become one), an ended one refused.
  const e32={holidays:[],c:null,awayC:15,announce:true};
  let reject=null;
  const now=()=>Math.floor(Date.now()/1000);
  const merge=list=>{
   const out=[];
   for(const h of [...list].sort((a,b)=>a.from-b.from||a.until-b.until)){
    const last=out.at(-1);
    if(last&&h.from<=last.until)last.until=Math.max(last.until,h.until);else out.push({...h});
   }
   return out;
  };
  const away=()=>{
   const running=e32.holidays.find(h=>h.from<=now()&&now()<h.until);
   const a={on:!!running,source:running?'manual':'none',target_c:e32.awayC,until:running?running.until:null,presence:'home',
    mode:running?'holiday':'auto',room_presence:true};
   if(e32.announce)Object.assign(a,{holiday_temperature_c:e32.c??e32.awayC,holidays:e32.holidays.slice(0,2)});
   return a;
  };
  const comfort=()=>({schema:1,away:away(),rooms:[],holidays:e32.holidays,holiday_temperature:e32.c??e32.awayC});
  await page.route('http://opth.test/**',async r=>{
   const request=r.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'c'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json({schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},rooms:[],ble_sensors:[],
    shadow:{today:{s:0},days:[]},away:away()});
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/flow')return r.fulfill({status:404,contentType:'text/plain',body:'Not found'});
   if(p==='/config/heating/comfort'&&request.method()==='GET')return json(comfort());
   if(p==='/config/heating/comfort'&&request.method()==='POST'){
    assert.equal(request.headers()['x-openthermostat-csrf'],'c'.repeat(64));
    const body=request.postDataJSON();posts.push(body);
    if(reject){const x=reject;reject=null;return json({error:x},400);}
    if(Array.isArray(body.holidays)){
     if(body.holidays.some(h=>!(h.from<h.until)))return json({error:'invalid_holidays'},400);
     if(body.holidays.some(h=>h.until<=now()))return json({error:'holiday_in_past'},400);
     e32.holidays=merge(body.holidays);
    }
    if('holiday_temperature' in body)e32.c=body.holiday_temperature;
    return json(comfort());
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await context.addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>openPage('house'));
  const root=page.locator('#house-settings'),box=root.locator('[data-house-holidays]'),message=box.locator('[data-holiday-message]');
  const items=box.locator('.hh-item'),form=box.locator('[data-holiday-form]');
  await box.getByRole('heading',{name:t.heading}).waitFor();
  await box.getByText(t.empty).waitFor();
  assert.equal(await form.isVisible(),false);
  // Every wait for a message starts from an empty one: the same text twice never matches the previous answer.
  const said=async(action,text)=>{await message.evaluate(e=>{e.textContent='';});await action();await message.getByText(text,{exact:true}).waitFor();};
  const add=async(from,until)=>{
   await box.getByRole('button',{name:t.add}).click();
   assert.equal(await form.isVisible(),true);
   await box.locator('[data-holiday-from]').fill(from);await box.locator('[data-holiday-to]').fill(until);
   await box.locator('[data-holiday-save]').click();
  };
  // Summer time to winter time: each date's own offset (14 Jul 17:00 CEST = 15:00 UTC, 27 Oct 08:00 CET = 07:00 UTC).
  const count=posts.length;
  await said(()=>add('2030-07-14T17:00','2030-10-27T08:00'),t.saved);
  assert.equal(posts.length,count+1);
  assert.deepEqual(posts.at(-1),{holidays:[{from:utc(2030,7,14,15,0),until:utc(2030,10,27,7,0)}]});
  assert.equal(await items.count(),1);
  assert.equal(await form.isVisible(),false);
  assert.match(await items.first().innerText(),new RegExp(t.to));
  // A touching one joins it (the E32 merges); a separate one is listed apart, in date order.
  await said(()=>add('2030-10-27T08:00','2030-11-01T12:00'),t.saved);
  assert.equal(posts.at(-1).holidays.length,2);
  await page.waitForFunction(()=>document.querySelectorAll('#house-settings .hh-item').length===1);
  await said(()=>add('2030-12-19T10:00','2031-01-03T18:00'),t.saved);
  await page.waitForFunction(()=>document.querySelectorAll('#house-settings .hh-item').length===2);
  // Change one: the form shows its own local times; the list is sent with it replaced.
  await items.nth(1).getByRole('button',{name:new RegExp('^'+t.change)}).click();
  assert.equal(await box.locator('[data-holiday-from]').inputValue(),'2030-12-19T10:00');
  assert.equal(await box.locator('[data-holiday-to]').inputValue(),'2031-01-03T18:00');
  await box.locator('[data-holiday-to]').fill('2031-01-05T18:00');
  await said(()=>box.locator('[data-holiday-save]').click(),t.saved);
  assert.deepEqual(posts.at(-1).holidays,[{from:utc(2030,7,14,15,0),until:utc(2030,11,1,11,0)},{from:utc(2030,12,19,9,0),until:utc(2031,1,5,17,0)}]);
  // Checked in the page first: nothing is sent.
  const before=posts.length;
  await said(()=>add('2030-12-01T10:00','2030-11-01T10:00'),t.dates);
  await box.locator('[data-holiday-from]').fill('2020-01-01T10:00');await box.locator('[data-holiday-to]').fill('2020-01-02T10:00');
  await said(()=>box.locator('[data-holiday-save]').click(),t.past);
  assert.equal(posts.length,before);
  // The E32's refusal in plain words; the form stays open with what was entered.
  reject='too_many_holidays';
  await box.locator('[data-holiday-from]').fill('2031-02-01T10:00');await box.locator('[data-holiday-to]').fill('2031-02-08T10:00');
  await said(()=>box.locator('[data-holiday-save]').click(),t.many);
  assert.equal(await form.isVisible(),true);
  await box.locator('[data-holiday-cancel]').click();
  assert.equal(await form.isVisible(),false);
  // Remove one.
  await said(()=>items.nth(1).getByRole('button',{name:new RegExp('^'+t.remove)}).click(),t.removed);
  assert.deepEqual(posts.at(-1).holidays,[{from:utc(2030,7,14,15,0),until:utc(2030,11,1,11,0)}]);
  await page.waitForFunction(()=>document.querySelectorAll('#house-settings .hh-item').length===1);
  // The holiday temperature.
  await box.locator('[data-holiday-c]').fill('12');
  await said(()=>box.locator('[data-holiday-c-save]').click(),t.temperature);
  assert.deepEqual(posts.at(-1),{holiday_temperature:12});
  // A holiday that runs now: the house mode says so with the holiday temperature, and "Stop holiday" ends it.
  e32.holidays=merge([...e32.holidays,{from:now()-3600,until:now()+2*86400}]);
  await page.evaluate(()=>loadNativePage('house'));
  await root.locator('[data-house-now]').getByText(t.mode).waitFor();
  await box.locator('[data-holiday-now]').getByText(t.running).waitFor();
  await said(()=>box.getByRole('button',{name:t.stop}).click(),t.stopped);
  assert.deepEqual(posts.at(-1).holidays,[{from:utc(2030,7,14,15,0),until:utc(2030,11,1,11,0)}]);
  assert.equal(await box.locator('[data-holiday-running]').isVisible(),false);
  // 44 px targets, no horizontal scroll (also with the form open at phone width).
  await box.getByRole('button',{name:t.add}).click();
  for(const b of await box.locator('button:visible').all()){const r=await b.boundingBox();assert(r.height>=44,'44 px target: '+await b.innerText());}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Firmware without the holiday planner: no block.
  e32.announce=false;
  await page.evaluate(()=>loadNativePage('house'));
  await root.locator('[data-house-now]').getByText(lang==='nl'?/^Automatisch/:/^Automatic/).waitFor();
  assert.equal(await root.locator('[data-house-holidays]').isVisible(),false);
  assert.deepEqual(errors,[]);
  results.push({width,lang,result:'PASS'});await context.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
