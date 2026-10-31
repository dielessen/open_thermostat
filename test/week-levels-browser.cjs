// beta.23 week planner levels in Chromium: Comfort, Eco and Night set independently (equal values and any
// order), stored marks, step-by-step undo, the visible "Copy…" and the phone block list; and the E32 rooms
// page sending "levels" and "schedule_levels" only to firmware that names "plan.levels.v1". No device.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),assets=path.join(root,'data/html');
const editor=fs.readFileSync(path.join(assets,'week-editor.js'),'utf8');
// The fixture of test_room_plan_levels.cpp / test_room_levels.py: Eco and Night are both 18.5 °C.
const LEVELS={comfort:2100,eco:1850,night:1850},MARKS='1213.13....0.';
const WEEK=[[[390,2100],[510,1850],[1020,2100],[1350,1850]],[[390,2100],[1350,1850]],[],[],[],[[480,2050]],[]];
const pass=name=>console.log('PASS '+name);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{
  for(const width of [1280,360]){
   const page=await browser.newPage({viewport:{width,height:900},isMobile:width<720,hasTouch:true}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.setContent('<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;padding:0 16px;font:15px system-ui}</style><main></main>');
   await page.addScriptTag({content:editor});
   await page.evaluate(([week,levels,marks])=>{window.states=[];window.ed=OTWeekEditor.mount(document.querySelector('main'),
    {week,levels,scheduleLevels:marks,min:500,max:2500,lang:'nl',onChange:(w,s)=>states.push(s)});},[WEEK,LEVELS,MARKS]);
   const main=page.locator('main'),state=()=>page.evaluate(()=>ed.state());
   // Stored marks decide between equal temperatures: Monday's 08:30 block is Eco, its 22:30 block Night.
   assert.equal(await main.locator('[data-k="seg0-510"]').getAttribute('class'),'wpe-seg lv-eco');
   assert.equal(await main.locator('[data-k="seg0-1350"]').getAttribute('class'),'wpe-seg lv-night');
   assert.equal(await main.locator('[data-k="seg5-480"]').getAttribute('class'),'wpe-seg lv-custom');
   for(const name of ['Comfort 21 °C','Eco 18,5 °C','Nacht 18,5 °C'])await main.getByText(name,{exact:true}).waitFor();
   assert.equal(await main.getByText('Afwezig').count(),0,'"Away" is no planner level any more');
   assert.equal((await state()).schedule_levels,MARKS);
   pass(width+': stored levels and marks, equal Eco and Night');
   // Night warmer than Comfort: allowed, with a soft hint; every Night block follows, Eco blocks stay.
   for(let i=0;i<8;i++)await main.locator('[data-k="lv-night+"]').click();
   await main.getByText(/Nacht is nu warmer dan Comfort/).waitFor();
   let s=await state();
   assert.deepEqual(s.levels,{comfort:2100,eco:1850,night:2250});
   assert.deepEqual(s.schedule[0],[[390,2100],[510,1850],[1020,2100],[1350,2250]]);
   assert.equal(s.schedule_levels,MARKS,'the marks stay with their blocks');
   // Eco set equal to Comfort: still two levels, the blocks keep their own level.
   for(let i=0;i<5;i++)await main.locator('[data-k="lv-eco+"]').click();
   s=await state();
   assert.equal(s.levels.eco,2100);assert.equal(await main.locator('[data-k="seg0-510"]').getAttribute('class'),'wpe-seg lv-eco');
   pass(width+': levels are independent, equal values and any order');
   // Undo, step by step, back to the stored levels.
   for(let i=0;i<13;i++)await main.locator('[data-k="undo"]').click();
   s=await state();
   assert.deepEqual(s.levels,LEVELS);assert.deepEqual(s.schedule,WEEK);assert.equal(s.schedule_levels,MARKS);
   assert.equal(await main.locator('[data-k="undo"]').count(),0,'nothing left to undo');
   assert.equal(await page.evaluate(()=>ed.changes()),0);
   pass(width+': undo step by step');
   // The day button says what it does.
   assert.match(await main.locator('[data-k="day0"]').innerText(),/^ma\s+Kopieer…$/);
   await main.locator('[data-k="day0"]').click();await main.getByText('Maandag kopiëren naar').waitFor();
   await main.locator('[data-k="copy-cancel"]').click();
   pass(width+': a visible "Copy…" per day');
   // Phone: the blocks of one day as a list with large rows; a row opens the block panel.
   const list=main.locator('.wpe-list');
   if(width<560){
    await list.waitFor();
    await main.locator('[data-k="listday1"]').click();
    const rows=list.locator('button[data-k^="row1-"]');
    assert.equal(await rows.count(),3,'Tuesday: Night from Monday, Comfort, Night');
    assert.match(await rows.nth(1).innerText(),/06:30–22:30\s+Comfort\s+21 °C/);
    for(const b of await rows.all()){const box=await b.boundingBox();assert(box.height>=44&&box.width>=200,JSON.stringify(box));}
    await rows.nth(1).click();await main.locator('.wpe-panel [data-k="set-comfort"][aria-pressed="true"]').waitFor();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll');
    pass('360: the phone block list');
   }else assert.equal(await list.count(),0,'wide screens keep the bars only');
   // A level on a block: Monday's own temperature becomes Eco.
   await main.locator('[data-k="seg5-480"]').click();await main.locator('[data-k="set-eco"]').click();
   s=await state();assert.deepEqual(s.schedule[5],[[480,1850]]);assert.equal(s.schedule_levels,'1213.13....2.');
   assert.deepEqual(errors,[]);
   await page.close();
  }
  // The E32 rooms page: levels and marks go with the room only for firmware that names plan.levels.v1.
  for(const features of [['plan.levels.v1'],undefined]){
   const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[],posts=[];
   let plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,...(features?{features}:{}),rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',
    inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'climate.woonkamer'}],setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500,
    schedule:WEEK,...(features?{levels:LEVELS,schedule_levels:MARKS}:{})}]};
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('http://opth.test/**',async route=>{
    const request=route.request(),p=new URL(request.url()).pathname,json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
    if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
    if(p==='/status/heating')return json({schema:1,revision:plan.revision,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},rooms:[{id:'woonkamer',name:'Woonkamer',
     state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint:21,temperature:20.4,demand:false,comfort:{window:'open'}}],
     ha:{input_age_s:null,broker_connected:false}});  // an E32 that never had HA input: the rooms are edited here
    if(p==='/config/heating'){if(request.method()==='POST'){const body=request.postDataJSON();posts.push(body);plan={...body,...(features?{features}:{}),revision:plan.revision+1};}return json(plan);}
    const file=path.join(assets,p==='/'?'index.html':p);
    if(!file.startsWith(assets+path.sep)&&!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
    let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
    return route.fulfill({contentType:/\.js(\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
   });
   await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
   await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
   await page.evaluate(()=>loadNativePage('heating'));
   const room=page.locator('[data-heating-room="woonkamer"]');await room.waitFor();await room.evaluate(e=>e.open=true);
   // The fixed room blocks, in the order of the Home Assistant room settings.
   const headings=await room.locator('h3').allInnerTexts();
   assert.deepEqual(headings.filter(h=>['Algemeen','Temperatuur','Weekprogramma','Ramen en deuren','Personen'].includes(h)),
    ['Algemeen','Temperatuur','Weekprogramma','Ramen en deuren','Personen']);
   await room.locator('[data-heating-window]').getByText('Nu: een raam of deur staat open; de ruimte pauzeert na haar vertraging.').waitFor();
   const planner=room.locator('[data-heating-planner]');await planner.locator('.wpe-seg').first().waitFor();
   await planner.locator('[data-k="lv-comfort+"]').click();
   await page.locator('[data-heating-discard]').waitFor();
   await page.locator('[data-heating-save]').click();await page.getByText(/Ruimtes opgeslagen\. ✓ \d\d:\d\d/).waitFor();
   const saved=posts.at(-1).rooms[0];
   if(features){
    assert.deepEqual(saved.levels,{comfort:2150,eco:1850,night:1850});assert.equal(saved.schedule_levels,MARKS);
    assert.deepEqual(saved.schedule[0],[[390,2150],[510,1850],[1020,2150],[1350,1850]]);
    pass('E32 page: levels and marks saved with plan.levels.v1; fixed room blocks; window state');
   }else{
    assert(!('levels' in saved)&&!('schedule_levels' in saved),'older firmware gets plain programs');
    assert.deepEqual(saved.schedule[0],[[390,2150],[510,1850],[1020,2150],[1350,1850]]);
    pass('E32 page: no levels for firmware without plan.levels.v1');
   }
   // Discard goes back to what the E32 stores.
   await room.evaluate(e=>e.open=true);await page.locator('[data-heating-room="woonkamer"] [data-k="lv-comfort+"]').click();
   await page.locator('[data-heating-discard]').click();await page.getByText('Wijzigingen weggegooid.').waitFor();
   assert.equal(await page.locator('[data-heating-discard]').isHidden(),true);
   assert.deepEqual(errors,[]);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
