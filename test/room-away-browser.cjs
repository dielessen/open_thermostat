// Away temperature per room ("plan.room_away.v1", after rc.2) on the E32 pages, against isolated HTTP
// fixtures (no device): the Rooms page shows and edits a room's own away temperature in its Persons block
// (empty = the house value), sends it only to firmware that names the feature, refuses a value outside
// 5–25 °C, and says why a room is cooler; the Overview says "this room's people are out" or "everyone".
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const FEATURES=['plan.levels.v1','plan.room_away.v1'];
const pass=name=>console.log('PASS '+name);
const room=(id,name,extra={})=>({id,name,state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'climate.'+id}],
 setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500,...extra});
// Jolien is out, Mark is home: her study at its own 16 °C, the living room warm (no persons of its own).
const studyAway={mode:'presence_away',persons:'away',away_by:'room',target_c:16};
function heating(rooms){
 return {schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},ha_entities:[],ble_sensors:[],
  ha:{input_age_s:null,broker_connected:false},active:{state:'shadow',warnings:[],enabled:false},
  away:{on:false,source:'none',target_c:17,until:null,presence:'home',mode:'auto',room_presence:true},
  rooms:rooms.map(([id,name,comfort,setpoint])=>({id,name,state:'active',inactive_until:0,status:'ok',source:'climate.'+id,temperature:19.5,
   setpoint,setpoint_source:'fallback',demand:false,...(comfort?{comfort}:{})}))};
}
async function open(browser,{lang,features,status}){
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[],posts=[];
 let plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,...(features?{features}:{}),
  rooms:[room('woonkamer','Woonkamer'),room('werkkamer','Werkkamer Jolien',features?{away_centi_c:1600}:{})]};
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://opth.test/**',async route=>{
  const request=route.request(),p=new URL(request.url()).pathname,json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
  if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
  if(p==='/status/heating')return json(status);
  if(p==='/config/heating/trv')return route.fulfill({status:404,body:''});
  if(p==='/config/heating'){
   if(request.method()==='POST'){
    const body=request.postDataJSON();posts.push(body);
    const bad=body.rooms.find(r=>'away_centi_c' in r&&!(r.away_centi_c>=500&&r.away_centi_c<=2500));
    if(bad)return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'invalid_room_away'})});
    plan={...body,...(features?{features}:{}),revision:plan.revision+1};
   }
   return json(plan);
  }
  const file=path.join(assets,p==='/'?'index.html':p);
  if(!file.startsWith(assets+path.sep)&&!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
  let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
  return route.fulfill({contentType:/\.js(\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
 });
 await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
 await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
 return {page,errors,posts};
}
async function roomsPage(page){
 await page.evaluate(()=>loadNativePage('heating'));
 const cards=page.locator('[data-heating-room]');await cards.nth(1).waitFor();
 await page.evaluate(()=>{for(const c of document.querySelectorAll('[data-heating-room]')){c.open=true;for(const d of c.querySelectorAll('[data-heating-section]'))d.open=true;}});
 return {living:page.locator('[data-heating-room="woonkamer"]'),study:page.locator('[data-heating-room="werkkamer"]')};
}
async function save(page,expect){
 await page.locator('[data-heating-room="woonkamer"]').evaluate(e=>e.dataset.old='1');
 await page.locator('[data-heating-save]').click();await page.getByText(expect).waitFor();
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{
  // Dutch: the field, its placeholder (the house value), the reason, saving, clearing and a refused value.
  {
   const status=heating([['woonkamer','Woonkamer',null,20],['werkkamer','Werkkamer Jolien',studyAway,16]]);
   const {page,errors,posts}=await open(browser,{lang:'nl',features:FEATURES,status});
   let {living,study}=await roomsPage(page);
   const own=study.locator('[data-heating-own-away]');
   assert.equal(await own.inputValue(),'16');
   assert.equal(await living.locator('[data-heating-own-away]').inputValue(),'');
   assert.equal(await living.locator('[data-heating-own-away]').getAttribute('placeholder'),'Waarde van het huis (17,0 °C)');
   await study.getByText('Temperatuur als de mensen van deze ruimte weg zijn (°C)').waitFor();
   await study.getByText(/^Geldt als alle personen van deze ruimte weg zijn en iemand anders thuis is\. Leeg: de afwezigheidstemperatuur van het huis\./).waitFor();
   await study.locator('[data-heating-persons]').getByText('Nu: iedereen van deze ruimte is weg; de ruimte gebruikt haar eigen afwezigheidstemperatuur (16,0 °C).').waitFor();
   assert.match(await study.locator('[data-heating-section="persons"] [data-heating-section-brief]').innerText(),/^Afwezig · eigen afwezigheidstemperatuur 16,0 °C$/);
   assert.equal(await living.locator('[data-heating-persons]').innerText(),'Geen eigen personen: de ruimte volgt het huis.');
   // A value for the living room too: both are saved, nothing else changes.
   await living.locator('[data-heating-own-away]').fill('18.5');
   await save(page,/Ruimtes opgeslagen\. ✓ \d\d:\d\d/);
   let sent=posts.at(-1);
   assert.equal(sent.rooms.find(r=>r.id==='woonkamer').away_centi_c,1850);
   assert.equal(sent.rooms.find(r=>r.id==='werkkamer').away_centi_c,1600);
   assert(!('features' in sent),'the page never posts what the firmware can');
   pass('nl: the own away temperature is shown, explained and saved');
   // Cleared: the study uses the house value again (the field leaves the plan).
   await page.locator('[data-heating-room="woonkamer"]:not([data-old])').waitFor({state:'attached'});
   ({living,study}=await roomsPage(page));
   await study.locator('[data-heating-own-away]').fill('');
   await save(page,/Ruimtes opgeslagen\. ✓ \d\d:\d\d/);
   sent=posts.at(-1);
   assert(!('away_centi_c' in sent.rooms.find(r=>r.id==='werkkamer')),'empty: the house value');
   assert.equal(sent.rooms.find(r=>r.id==='woonkamer').away_centi_c,1850);
   pass('nl: an empty field is the house value');
   // Outside 5–25 °C: refused on the page, nothing is sent.
   await page.locator('[data-heating-room="woonkamer"]:not([data-old])').waitFor({state:'attached'});
   ({living,study}=await roomsPage(page));
   await study.locator('[data-heating-own-away]').fill('30');
   const before=posts.length;
   await page.locator('[data-heating-save]').click();
   await page.getByText('Werkkamer Jolien: Kies voor deze ruimte een afwezigheidstemperatuur tussen 5 en 25 °C, of laat het veld leeg voor de waarde van het huis.').waitFor();
   assert.equal(posts.length,before);
   assert.equal(await page.evaluate(()=>document.activeElement?.hasAttribute('data-heating-own-away')),true,'the field gets the focus');
   pass('nl: a value outside 5–25 °C is refused before saving');
   assert.deepEqual(errors,[]);
   await page.close();
  }
  // English: everyone away (the house value for every room, also the study) and the Overview's reasons.
  {
   const everyone={mode:'presence_away',persons:'away',away_by:'house',target_c:17};
   const status=heating([['woonkamer','Woonkamer',{mode:'presence_away',away_by:'house',target_c:17},17],['werkkamer','Werkkamer Jolien',everyone,17]]);
   status.away={...status.away,on:true,source:'presence',presence:'away'};
   const {page,errors}=await open(browser,{lang:'en',features:FEATURES,status});
   const {living,study}=await roomsPage(page);
   for(const card of [living,study])
    await card.locator('[data-heating-persons]').getByText('Now: everyone is away; every room uses the house away temperature (17.0 °C).').waitFor();
   await study.getByText("Temperature when this room's people are away (°C)").waitFor();
   pass('en: everyone away is the house value for every room');
   // The Overview: why each room is cooler.
   await page.goto('http://opth.test/');
   await page.waitForFunction(()=>document.querySelectorAll('.pd-room').length===2,null,{timeout:15000});
   await page.evaluate(()=>clearInterval(intervalID));
   const engine=heating([['woonkamer','Woonkamer',null,20],['werkkamer','Werkkamer Jolien',studyAway,16]]);
   await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
   await page.locator('.pd-room').nth(1).getByText("Away: this room's people are out").waitFor();
   await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),status);
   await page.locator('.pd-room').nth(1).getByText('Away: everyone is out').waitFor();
   pass('en: the Overview says whose absence lowers a room');
   assert.deepEqual(errors,[]);
   await page.close();
  }
  // Dutch Overview text.
  {
   const status=heating([['woonkamer','Woonkamer',null,20],['werkkamer','Werkkamer Jolien',studyAway,16]]);
   const {page,errors}=await open(browser,{lang:'nl',features:FEATURES,status});
   await page.waitForFunction(()=>document.querySelectorAll('.pd-room').length===2,null,{timeout:15000});
   await page.locator('.pd-room').nth(1).getByText('Afwezig: de mensen van deze ruimte zijn weg').waitFor();
   pass('nl: the Overview reason');
   assert.deepEqual(errors,[]);
   await page.close();
  }
  // Firmware without plan.room_away.v1 (rc.2): no field, no value sent; the old persons text stays.
  {
   const status=heating([['woonkamer','Woonkamer',null,20],['werkkamer','Werkkamer Jolien',{mode:'presence_away',persons:'away',target_c:15},15]]);
   const {page,errors,posts}=await open(browser,{lang:'en',features:['plan.levels.v1'],status});
   const {study}=await roomsPage(page);
   assert.equal(await page.locator('[data-heating-own-away]').count(),0);
   await study.locator('[data-heating-persons]').getByText('Now: everyone of this room is away; the room uses the away temperature.').waitFor();
   await study.locator('input').first().fill('Werkkamer');
   await save(page,/Rooms saved\. ✓ \d\d:\d\d/);
   assert(posts.at(-1).rooms.every(r=>!('away_centi_c' in r)),'older firmware gets no own away value');
   pass('en: firmware without the feature gets no field and no value');
   assert.deepEqual(errors,[]);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
