// Real shipped rooms page with simulated HTTP: the radiator valves block of a room (beta.24, /config/heating/trv).
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const week=[...Array(7)].map(()=>[[390,2050],[1320,1800]]);
const room={id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'climate.woonkamer'}],
  setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500,schedule:week};
const valve=(name,extra={})=>({name,model:'bosch_bth_ra',health:'ok',position_pct:40,battery_pct:85,setpoint_c:21,...extra});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{for(const [width,withValves] of [[1280,true],[320,true],[1280,false]]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],posts=[];
  const plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[room]};
  // A Zigbee2MQTT valve and one Home Assistant drives (ha_climate: its climate entity, health HA's to judge).
  let record={schema:1,base_topic:'zigbee2mqtt',rooms:[{room:'woonkamer',control:false,valves:[{name:'Kraan woonkamer',model:'bosch_bth_ra'},
    {name:'climate.trv_woonkamer',model:'ha_climate'}]}]};
  let trv={output:false,flow_offset_c:0,rooms:[{room:'woonkamer',control:false,degraded:false,single_source:true,
    valves:[valve('Kraan woonkamer',{health:'low_battery',battery_pct:18}),{name:'climate.trv_woonkamer',model:'ha_climate',health:'unknown'}]}]};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json({schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},
     rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',status:'ok',source:'climate.woonkamer',temperature:20.4,setpoint:21,demand:false}],
     ble_sensors:[],ha_entities:['climate.woonkamer'],...(withValves?{trv}:{})});
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/trv'){
    if(!withValves)return route.fulfill({status:404,body:''});   // firmware before beta.24
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));
     const body=request.postDataJSON();posts.push(body);record=body;
     trv={...trv,rooms:body.rooms.map(r=>({room:r.room,control:r.control,degraded:false,single_source:true,
       valves:r.valves.map(v=>v.model==='ha_climate'?{name:v.name,model:v.model,health:'unknown'}:valve(v.name,{model:v.model}))}))};
    }
    return json({...record,features:['actuator.output.v1'],models:[],status:trv});
   }
   if(p==='/week-editor.js')return route.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('heating'));
  const root=page.locator('#heating-plan'),card=root.locator('[data-heating-room="woonkamer"]');
  await card.waitFor();
  await card.locator(':scope > summary').click();
  if(!withValves){
   // Older firmware: no valve block, no request for valves beyond the one GET, the rest of the card unchanged.
   await card.getByText('Ramen en deuren',{exact:true}).first().waitFor();
   assert.equal(await card.locator('[data-heating-valves]').count(),0);
   assert.deepEqual(errors,[]);await page.close();continue;
  }
  // Managed in Home Assistant (locked): the short summary names the valves and their live state.
  await card.locator('.hp-brief').getByText(/Kraan woonkamer, climate\.trv_woonkamer · niet aangestuurd · Kraan woonkamer: Batterij bijna leeg, open 40 %; climate\.trv_woonkamer: Aangestuurd door Home Assistant/).waitFor();
  await root.locator('[data-heating-unlock]').click();
  const block=card.locator('[data-heating-valves]');
  await card.getByRole('heading',{name:'Radiatorkranen'}).waitFor();
  // Live state: the valve, its health chip, position and battery.
  const live=block.locator('[data-heating-valve-state="Kraan woonkamer"]');
  await live.getByText('Batterij bijna leeg').waitFor();
  assert.match(await live.innerText(),/open 40 % · batterij 18 %/);
  // The Home Assistant valve: driven by HA, shown read-only (no name field, no model, no remove).
  assert.match(await block.locator('[data-heating-valve-state="climate.trv_woonkamer"]').innerText(),/Aangestuurd door Home Assistant/);
  const haRow=block.locator('[data-heating-valve-ha]');
  assert.match(await haRow.innerText(),/climate\.trv_woonkamer[\s\S]*Climate-entiteit in Home Assistant \(in te stellen in Home Assistant\)/);
  assert.equal(await haRow.locator('input, select, button').count(),0);
  // Valve control is off until switched on; no single-source hint while it is off.
  const control=block.locator('[data-heating-valve-control]');
  assert.equal(await control.isChecked(),false);
  assert.equal(await block.locator('[data-heating-valve-hint]').count(),0);
  // A name Zigbee2MQTT would not have is refused here, before anything is sent.
  await block.locator('[data-heating-valve-add]').click();
  const rows=block.locator('[data-heating-valve]');
  assert.equal(await rows.count(),3);
  await rows.nth(2).locator('input').fill('kraan#raam');
  await block.locator('[data-heating-valve-save]').click();
  await block.getByText(/Gebruik de Zigbee2MQTT-naam van de kraan/).waitFor();
  assert.equal(posts.length,0);
  // Two Zigbee2MQTT valves, control switched on: one POST with only this room's record, the HA valve kept.
  await rows.nth(2).locator('input').fill('Kraan raam');
  await rows.nth(2).locator('select').selectOption('sonoff_trvzb');
  await control.check();
  await block.locator('[data-heating-valve-save]').click();
  await block.getByText(/Kranen opgeslagen\./).waitFor();
  assert.deepEqual(posts,[{schema:1,base_topic:'zigbee2mqtt',rooms:[{room:'woonkamer',control:true,
    valves:[{name:'Kraan woonkamer',model:'bosch_bth_ra'},{name:'climate.trv_woonkamer',model:'ha_climate'},{name:'Kraan raam',model:'sonoff_trvzb'}]}]}]);
  // The next status shows both valves and, with control on and one source, the sensor hint.
  await block.locator('[data-heating-valve-state="Kraan raam"]').waitFor({timeout:15000});
  await block.locator('[data-heating-valve-hint]').waitFor();
  // Editing valves never marks the room plan as changed.
  assert.equal(await root.locator('[data-heating-dirty]').isVisible(),false);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  assert(overflow<=0,'no horizontal scroll at '+width+' px: '+overflow);
  assert.deepEqual(errors,[]);
  await page.close();
 }}finally{await browser.close();}
 console.log('heating valves browser: ok');
})().catch(e=>{console.error(e);process.exit(1);});
