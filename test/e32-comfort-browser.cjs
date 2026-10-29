// E32 dashboard comfort controls (beta.19): temporary room override, window pause and away,
// against isolated HTTP fixtures. No device connection.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const until=Math.round(Date.parse('2026-11-02T21:30:00Z')/1000);
function heating(){
 return {schema:1,revision:3,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},ha_entities:[],ble_sensors:[],
  ha:{input_age_s:null,broker_connected:false},active:{state:'shadow',warnings:[],enabled:false},
  away:{on:false,source:'none',target_c:15,until:null,presence:'unknown'},
  rooms:[
   {id:'living',name:'Living',state:'active',status:'ok',source:'a4c138000001',temperature:19.5,setpoint:21,setpoint_source:'schedule',demand:true,
    comfort:{mode:'next',target_c:21,until,override:'next'}},
   {id:'study',name:'Study',state:'active',status:'ok',source:'a4c138000002',temperature:18,setpoint:8,setpoint_source:'fallback',demand:false,
    comfort:{mode:'window_open',window:'open',target_c:8}},
   {id:'bath',name:'Bath',state:'inactive',status:'inactive',source:null,temperature:null,setpoint:null,setpoint_source:'fallback',demand:false}]};
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,360]){
  const page=await browser.newPage({viewport:{width,height:900}});let engine=heating();const posts=[],errors=[];let answer={status:200};
  page.on('pageerror',e=>errors.push(e.message));
  const send=async locator=>{const n=posts.length;await locator.click();for(let i=0;i<100&&posts.length===n;i++)await page.waitForTimeout(20);assert.equal(posts.length,n+1);};
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   if(pathname==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(pathname==='/status')return route.fulfill({json:{controlMode:'shadow',ems:{},control:{}}});
   if(pathname==='/status/heating')return route.fulfill({json:engine});
   if(pathname==='/config/heating/comfort'){
    assert.equal(req.method(),'POST');posts.push(JSON.parse(req.postData()));
    return route.fulfill(answer.status===200?{json:{schema:1,away:engine.away,rooms:[]}}:{status:answer.status,json:{error:answer.error}});
   }
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.css(?:\.gz)?$/.test(pathname)?'text/css':/\.js(?:\.gz)?$/.test(pathname)?'application/javascript':'text/html'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');
  await page.waitForFunction(()=>document.querySelectorAll('.pd-room').length===3&&document.querySelector('.pd-away'),null,{timeout:15000});
  const rooms=page.locator('.pd-room');
  // The state is visible with its reason.
  assert.match(await rooms.nth(0).locator('.ot-chips').innerText(),lang==='en'?/21 °C until/:/21 °C tot/);
  assert.match(await rooms.nth(1).locator('.ot-chips').innerText(),lang==='en'?/Window open: paused/:/Raam open: gepauzeerd/);
  // Controls only for active rooms; "back to the program" only while overriding.
  assert.equal(await page.locator('.pd-room-comfort').count(),2);
  assert.equal(await rooms.nth(0).locator('[data-comfort="none"]').count(),1);
  assert.equal(await rooms.nth(1).locator('[data-comfort="none"]').count(),0);
  // 2 h at 21.5 degC: the typed value and the chosen duration survive the next poll.
  await rooms.nth(1).locator('.pd-room-comfort summary').click();
  await rooms.nth(1).locator('[data-comfort-temp]').fill('21.5');
  await rooms.nth(1).locator('[data-comfort-length]').selectOption('120');
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.equal(await rooms.nth(1).locator('[data-comfort-temp]').inputValue(),'21.5');
  await rooms.nth(1).locator('[data-comfort="set"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-key="comfort-study"] [role=status]'),null,{timeout:5000});
  assert.deepEqual(posts.at(-1),{room:'study',override:'timed',temperature:21.5,minutes:120});
  assert.match(await rooms.nth(1).locator('[role=status]').innerText(),lang==='en'?/Saved/:/Opgeslagen/);
  // Until the next switch point, refused without a clock: a plain message.
  answer={status:409,error:'no_clock'};
  await rooms.nth(1).locator('[data-comfort-length]').selectOption('next');
  await rooms.nth(1).locator('[data-comfort="set"]').click();
  await page.waitForFunction(()=>/time|tijd/.test(document.querySelector('[data-dashboard-key="comfort-study"] [role=status]')?.textContent||''),null,{timeout:5000});
  assert.deepEqual(posts.at(-1),{room:'study',override:'next',temperature:21.5});
  answer={status:200};
  // Boost and back to the program.
  await rooms.nth(0).locator('.pd-room-comfort summary').click();
  await send(rooms.nth(0).locator('[data-comfort="boost"]'));
  assert.deepEqual(posts.at(-1),{room:'living',override:'boost'});
  await send(rooms.nth(0).locator('[data-comfort="none"]'));
  assert.deepEqual(posts.at(-1),{room:'living',override:'none'});
  // Away until a date, for the whole house.
  await page.locator('.pd-away summary').click();
  await page.locator('[data-comfort-away-temp]').fill('16');
  await page.locator('[data-comfort-away-until]').fill('2026-11-08T18:00');
  await send(page.locator('[data-comfort="away"]'));
  const away=posts.at(-1);
  assert.equal(away.away,true);assert.equal(away.temperature,16);
  assert.equal(away.until,Math.round(await page.evaluate(()=>new Date('2026-11-08T18:00').getTime())/1000));
  engine.away={on:true,source:'manual',target_c:16,until:away.until,presence:'unknown'};
  engine.rooms[0].comfort={mode:'away',target_c:16,until:away.until};
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await page.locator('.pd-away summary').innerText(),lang==='en'?/Away until/:/Afwezig tot/);
  await send(page.locator('[data-comfort="home"]'));
  assert.deepEqual(posts.at(-1),{away:false});
  // Firmware without comfort (no "away"): no controls at all.
  const old=heating();delete old.away;old.rooms.forEach(r=>delete r.comfort);engine=old; // also for the next poll
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),old);
  assert.equal(await page.locator('.pd-room-comfort, .pd-away').count(),0);
  // Markup in names or values is never executed.
  const evil=heating();evil.rooms[0].comfort={mode:'<img src=x onerror=alert(1)>',target_c:'<b>'};engine=evil;
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),evil);
  assert.equal(await page.locator('.pd-room img, .pd-room b').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);results.push({language:lang,width,status:'PASS',posts:posts.length});
  await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
