// rc.4 review fixes of the Rooms, Home and Overview pages (RC4-CODE-REVIEW.md R3), with simulated HTTP and a fake clock:
// R3-02 no polling in a hidden tab, R3-03 one "Save rooms" during the boiler bus check that keeps edits made meanwhile,
// R3-06 a typed away temperature or holiday date survives the 10 s refresh, R3-17 failed refreshes are not silent,
// R3-24 "Inactive until" uses the time zone offset of its own date, R3-25 "$&" in a room name stays literal,
// R3-34 the Overview's boiler card retries a failed selection read, R3-14 Sign out (now a System menu item) appears
// also when the first session check failed.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
// 2027-03-20 12:00 in Amsterdam (CET); the summer time starts on 28 March, so 2 April 10:00 is CEST.
const start=new Date('2027-03-20T11:00:00Z'),afterSwitch=Date.parse('2027-04-02T08:00:00Z')/1000;
const heatingStatus=()=>({schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},ble_sensors:[],
  shadow:{today:{s:0},days:[]},ha:{input_age_s:null,broker_connected:false},active:{state:'shadow',command:{send:false,flow_c:0,why:'shadow'},
  last_sent:null,confirmation:null,warnings:[],enabled:false},rooms:[],
  away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'}});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Europe/Amsterdam'});
  const page=await context.newPage(),errors=[],requests=[],posts=[],dialogs=[];
  let status=heatingStatus(),failStatus=0,boilerDisplayFails=1,dismiss=false,failSession=0;
  let plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>{dialogs.push(d.message());dismiss?d.dismiss():d.accept();});
  await page.addInitScript(()=>{
   window.__visibility='visible';
   Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__visibility});
  });
  const visibility=value=>page.evaluate(v=>{window.__visibility=v;document.dispatchEvent(new Event('visibilitychange'));},value);
  const count=p=>requests.filter(r=>r===p).length;
  const until=async(condition,what)=>{for(let i=0;i<400&&!condition();++i)await page.waitForTimeout(10);assert(condition(),what);};
  // Page time in steps of 2 s: a request started by a timer gets its answer before its own 8 s deadline passes.
  const tick=async ms=>{for(let left=ms;left>0;left-=2000){await page.clock.runFor(Math.min(2000,left));await page.waitForTimeout(30);}};
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname;requests.push(p);
   const json=(body,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session'){if(failSession>0){failSession--;return json({error:'busy'},503);}return json({authenticated:true,csrf:'c'.repeat(64)});}
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating'){if(failStatus>0){failStatus--;return json({error:'busy'},500);}return json(status);}
   if(p==='/config/boiler-display'){
    if(boilerDisplayFails>0){boilerDisplayFails--;return route.fulfill({status:503,body:'busy'});}
    return json({model:'nefit-ecomline-classic-hrc-22h'});
   }
   if(p==='/config/heating'){
    if(request.method()==='POST'){
     const body=request.postDataJSON();posts.push(body);
     if(body.revision!==plan.revision)return json({error:'plan_changed'},409);
     plan={...body,revision:plan.revision+1};
    }
    return json(plan);
   }
   if(p==='/config/heating/comfort'&&request.method()==='POST'){
    const body=request.postDataJSON();posts.push(body);const a=status.away;
    a.mode=body.house_mode;if(typeof body.temperature==='number')a.target_c=body.temperature;
    a.on=body.house_mode==='away'||body.house_mode==='holiday';a.source=a.on?'manual':'none';a.until=body.house_mode==='holiday'?body.until:null;
    return json({schema:1,away:a,rooms:[]});
   }
   if(['/config/heating/flow','/config/heating/trv','/status/ems/telemetry','/week-editor.js'].includes(p))return route.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.clock.install({time:start});
  // R3-34: the first boiler selection read fails (a busy E32); the card retries with a poll after 30 s.
  await page.goto('http://opth.test/');await page.locator('#boiler-home').getByText('Boiler selection unavailable').waitFor();
  const pause=async()=>{for(;;){const at=await page.evaluate(()=>Date.now())+500;
   try{await page.clock.pauseAt(at);return;}catch(e){if(!/past/.test(e.message))throw e;}}};
  await pause();
  await tick(20000);await page.waitForTimeout(100);
  assert.equal(count('/config/boiler-display'),1,'no retry within 30 s');
  await tick(21000);
  await page.locator('#boiler-home h2').getByText('Nefit Ecomline Classic HRC 22H').waitFor();
  assert.equal(count('/config/boiler-display'),2,'one retry');
  await tick(30000);await page.waitForTimeout(100);
  assert.equal(count('/config/boiler-display'),2,'no more reads once the selection is known');

  // Rooms: a saved room that is off until 2 April (after the switch to summer time), and one called "Hall $&".
  plan={...plan,rooms:[{id:'zolder',name:'Zolder',state:'inactive',inactive_until:afterSwitch,emitter:'radiator',sources:[{type:'ha',id:'climate.zolder'}],
   setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500},
   {id:'hall',name:'Hall $&',state:'inactive',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'climate.hall'}],
   setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500}]};
  status.rooms=[{id:'zolder',name:'Zolder',state:'inactive',status:'inactive',source:null,temperature:null,setpoint:null,demand:false},
   {id:'hall',name:'Hall $&',state:'inactive',status:'inactive',source:null,temperature:null,setpoint:null,demand:false}];
  // Loading a page needs flowing time (jQuery resolves its requests with timers); each part pauses it again.
  await page.clock.resume();
  await page.evaluate(()=>{sessionStorage.setItem('ot-rooms-edit','1');loadNativePage('heating');});
  const root=page.locator('#heating-plan');await root.locator('[data-heating-room="zolder"]').waitFor();await pause();
  // R3-24: 2 April 10:00 local, not 09:00 (the offset of 20 March).
  assert.equal(await root.locator('[data-heating-room="zolder"] input[type="datetime-local"]').inputValue(),'2027-04-02T10:00');
  // R3-25: the confirmation names the room exactly.
  dismiss=true;await root.locator('[data-heating-room="hall"] [data-heating-unused] .btn-outline-danger').click();dismiss=false;
  assert.match(dialogs.at(-1),/^Remove the room Hall \$&\? /);
  // R3-02: a hidden tab does not poll; showing it again reads once.
  await visibility('hidden');const hidden=count('/status/heating');
  await tick(35000);await page.waitForTimeout(100);
  assert.equal(count('/status/heating'),hidden,'no reads while hidden');
  await visibility('visible');await until(()=>count('/status/heating')===hidden+1,'one read when shown');
  await page.waitForTimeout(100);assert.equal(count('/status/heating'),hidden+1);

  // R3-03: the first plan waits for the boiler bus check; Save is one save, and an edit made meanwhile is saved.
  plan={...plan,rooms:[]};status.rooms=[];status.new_plan={stored:false,reason:'checking',mode:'shadow'};
  await page.clock.resume();await page.evaluate(()=>loadNativePage('heating'));await root.locator('[data-heating-add-first]').click();await pause();
  const card=root.locator('[data-heating-room]').last();
  await card.locator('[data-heating-source]').first().locator('select').first().selectOption('ha');
  await card.locator('[data-heating-source]').first().locator('input').fill('climate.woonkamer');
  await card.getByLabel('Name').fill('Living room');
  const save=root.locator('[data-heating-save]'),before=posts.length;
  await save.evaluate(b=>{b.click();b.click();});
  await root.getByText('Checking the boiler bus…').waitFor();
  assert.equal(await save.isDisabled(),true,'Save waits for the first save');
  assert.equal(await root.locator('[data-heating-discard]').isVisible(),false,'Discard hidden while saving');
  await card.getByLabel('Heating type').selectOption('floor');
  assert.equal(await root.locator('[data-heating-discard]').isVisible(),false,'an edit during the wait keeps Discard hidden');
  await tick(5000);await page.waitForTimeout(100);
  status.new_plan={stored:false,reason:'ready',mode:'shadow'};
  await tick(5000);
  await root.getByText(/^Rooms saved\./).waitFor();
  assert.equal(posts.length,before+1,'exactly one save');
  assert.equal(posts.at(-1).rooms[0].emitter,'floor','the edit made during the wait is saved');
  assert.equal(await root.getByText(/changed elsewhere/).count(),0);
  assert.equal(await save.isDisabled(),false);delete status.new_plan;

  // Home page.
  await page.clock.resume();await page.evaluate(()=>openPage('house'));
  const house=page.locator('#house-settings'),awayC=house.locator('[data-house-away-c]'),now=house.locator('[data-house-now]');
  await now.getByText('Automatic: someone is home, so the rooms follow their week programs.').waitFor();await pause();
  // R3-06: typed, focus elsewhere, two refreshes later still there; saved, then the stored value.
  await awayC.fill('18');await house.locator('h1').click();
  let reads=count('/status/heating');await tick(21000);await until(()=>count('/status/heating')>=reads+2,'refreshes');
  await page.waitForTimeout(100);
  assert.equal(await awayC.inputValue(),'18','the typed away temperature stays');
  await house.locator('[data-house-away-save]').click();await house.getByText('Temperature saved.').waitFor();
  assert.deepEqual(posts.at(-1),{house_mode:'auto',temperature:18});
  status.away.target_c=16;reads=count('/status/heating');await tick(10000);await until(()=>count('/status/heating')>reads,'refresh');
  await until(()=>true);await page.waitForFunction(()=>document.querySelector('[data-house-away-c]').value==='16');
  // The holiday date: a typed date stays too.
  Object.assign(status.away,{mode:'holiday',on:true,source:'manual',until:afterSwitch});
  await tick(10000);await house.locator('[data-house-holiday]').waitFor();
  const holidayUntil=house.locator('[data-house-until]');
  await page.waitForFunction(()=>document.querySelector('[data-house-until]').value==='2027-04-02T10:00');
  await holidayUntil.fill('2027-04-05T18:00');await house.locator('h1').click();
  reads=count('/status/heating');await tick(11000);await until(()=>count('/status/heating')>reads,'refresh');
  await page.waitForTimeout(100);assert.equal(await holidayUntil.inputValue(),'2027-04-05T18:00','the typed holiday date stays');
  // R3-17: two failed refreshes in a row: the alert, and the controls wait for a fresh answer.
  failStatus=1;reads=count('/status/heating');await tick(10000);await until(()=>count('/status/heating')>reads,'failed read');
  await page.waitForTimeout(100);assert.equal(await house.locator('[data-house-error]').isVisible(),false,'one failure is not shown yet');
  failStatus=1;reads=count('/status/heating');await tick(10000);
  await house.locator('[data-house-error]').waitFor();
  assert.equal(await now.innerText(),'Status unavailable');
  assert.equal(await house.getByRole('button',{name:'Automatic',exact:true}).isDisabled(),true);
  assert.equal(await awayC.isDisabled(),true);
  await tick(10000);await house.locator('[data-house-error]').waitFor({state:'hidden'});
  assert.equal(await house.getByRole('button',{name:'Automatic',exact:true}).isDisabled(),false);
  // R3-02 on the Home page.
  await visibility('hidden');const quiet=count('/status/heating');
  await tick(35000);await page.waitForTimeout(100);
  assert.equal(count('/status/heating'),quiet,'no reads while hidden');
  await visibility('visible');await until(()=>count('/status/heating')===quiet+1,'one read when shown');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // R3-14: the first session check fails (a busy E32); Sign out appears with the next good one, without a reload.
  failSession=1;await page.clock.resume();await page.goto('http://opth.test/');await page.locator('#dashboard-poll-error').waitFor();
  assert.equal(await page.locator('[data-sign-out-item]:not([hidden])').count(),0);
  await pause();await tick(12000);
  await page.locator('[data-sign-out-item]:not([hidden]) #auth-sign-out').waitFor({state:'attached'});
  assert.deepEqual(errors,[]);
  results.push({width,result:'PASS'});await context.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
