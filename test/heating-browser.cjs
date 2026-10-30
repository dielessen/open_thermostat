// Real shipped rooms page with simulated HTTP: create the living room, save, show status.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const side=(heat_s,starts,min,max,mean)=>({heat_s,starts,flow_min_c:min,flow_max_c:max,flow_mean_c:mean});
const status={schema:1,revision:4,mode:'shadow',request:{heat:true,flow_c:36,reason:'heating'},
  rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'ha',temperature:20.4,setpoint:21,demand:true}],
  ble_sensors:[{id:'a4c138a3e8db',name:'Thermometer woonkamer',profile:'pvvx_thermometer',temperature:20.4,humidity:55.2,battery:87,age_s:12},
   {id:'a4c1389f0011',name:'Slaapkamer',profile:'pvvx_thermometer',temperature:null,humidity:null,battery:null,age_s:null}],
  // ShadowComparison::json(): today so far, then completed days (yesterday first); nulls where nothing heated or paired.
  shadow:{today:{day:'2026-10-28',s:36000,tado_unknown_s:600,e32:side(7200,4,31,42,36.4),tado:side(7800,5,35,45,39.2),both_s:6600,agree_s:33600,
    e32_only_s:600,tado_only_s:1200,flow_diff_mean_c:2.8,starts_paired:4,starts_within_5min:3,start_offset_mean_s:75,start_offset_max_s:420},
   days:[{day:'2026-10-27',s:86400,tado_unknown_s:0,e32:side(14400,6,30,44,37.1),tado:side(15000,7,34,46,40),both_s:13800,agree_s:84000,
     e32_only_s:600,tado_only_s:1800,flow_diff_mean_c:3.1,starts_paired:6,starts_within_5min:5,start_offset_mean_s:-40,start_offset_max_s:600},
    {day:'2026-10-26',s:3600,tado_unknown_s:3600,e32:side(0,0,null,null,null),tado:side(0,0,null,null,null),both_s:0,agree_s:0,
     e32_only_s:0,tado_only_s:0,flow_diff_mean_c:null,starts_paired:0,starts_within_5min:0,start_offset_mean_s:null,start_offset_max_s:null}]}};
const week=[...Array(5)].map(()=>[[390,2050],[1320,1800]]).concat([[[480,2050],[720,2000],[1380,1800]],[[480,2050],[720,2000],[1380,1800]]]);
const pairs=dl=>dl.evaluate(e=>[...e.querySelectorAll('dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent]));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const width of [1280,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],posts=[],handovers=[],dialogs=[];
  let plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]},reject=null;
  // ActiveHeatGuard::json() plus the firmware gate; this firmware ships with it closed.
  const active=status.active={state:'shadow',command:{send:false,flow_c:0,why:'shadow'},last_sent:null,
   foreign_controller:{address:0x17,age_s:30},confirmation:null,warnings:[],enabled:false};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>{dialogs.push(d.message());d.accept();});
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(plan.rooms.length?status:{...status,rooms:[],request:{heat:false,flow_c:0,reason:'no_demand'}});
   if(p==='/config/heating/handover'){
    assert.equal(request.method(),'POST');assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    handovers.push(request.postDataJSON());
    if(!active.enabled)return json({error:'active_mode_not_released'},409);
    Object.assign(active,{state:'active',command:{send:true,flow_c:45,why:'heat_request'},last_sent:{flow_c:45,age_s:5},confirmation:{age_s:0}});
    return json(active);
   }
   if(p==='/config/heating'){
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));
     const body=request.postDataJSON();posts.push(body);
     if(reject){const r=reject;reject=null;return json({error:r.error},r.code);}
     if(body.revision!==plan.revision)return json({error:'plan_changed'},409);
     plan={...body,revision:plan.revision+1};
    }
    return json(plan);
   }
   // This test covers the switch-point list, the fallback without the visual planner (test/week-editor-browser.cjs).
   if(p==='/week-editor.js')return route.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('heating'));
  const root=page.locator('#heating-plan');
  await root.getByText('Begin met de woonkamer: geef hem een naam en kies de temperatuursensor.').waitFor();
  await root.locator('[data-heating-request]').getByText(/Berekende ketelvraag: uit/).waitFor();
  // Active control with the firmware gate closed: a notice, no switch-over buttons.
  const control=root.locator('[data-heating-active]'),takeover=control.locator('[data-heating-takeover]'),handback=control.locator('[data-heating-handback]');
  await control.getByText('Actieve regeling is in deze firmware niet ingeschakeld.').waitFor();
  assert.equal(await control.locator('[data-heating-active-state]').innerText(),'Schaduwmodus: je thermostaat regelt de ketel. · laatste vraag van je thermostaat 30 s geleden');
  assert.equal(await takeover.isVisible(),false);assert.equal(await handback.isVisible(),false);
  // The paired Bluetooth sensors are chosen in the room itself; there is no separate read-only list.
  assert.equal(await root.locator('[data-heating-ble]').count(),0);
  // Shadow comparison of today and the completed days.
  const shadow=root.locator('[data-heating-shadow]');
  assert.match(await shadow.innerText(),/Vergelijking met je thermostaat \(vandaag\)[\s\S]*Schaduwmodus: de E32 berekent zijn ketelvraag maar verstuurt die niet/);
  assert.deepEqual(await pairs(shadow.locator('[data-heating-shadow-today]')),[['Vergeleken tijd','10 u 0 min'],
   ['Stooktijd E32 / thermostaat','2 u 0 min / 2 u 10 min'],['Branderstarts E32 / thermostaat','4 / 5'],['Overeenstemming (beide aan of beide uit)','95 %'],
   ['Aanvoerbereik E32','31–42 °C (gemiddeld 36,4 °C)'],['Aanvoerbereik thermostaat','35–45 °C (gemiddeld 39,2 °C)'],
   ['Starts rond hetzelfde moment (±5 min)','3 / 5'],['Zonder thermostaatgegevens','10 min']]);
  const days=await shadow.locator('[data-heating-shadow-days] tr').evaluateAll(rows=>rows.map(r=>[...r.children].map(c=>c.textContent)));
  assert.deepEqual(days.map(r=>r.slice(1)),[['E32','Thermostaat','Overeenstemming','Starts E32 / thermostaat'],
   ['4 u 0 min','4 u 10 min','97 %','6 / 7'],['0 min','0 min','—','0 / 0']]);
  assert.match(days[1][0],/27-10/);assert.match(days[2][0],/26-10/);assert.equal(days[0][0],'Dag');
  // Read-only until unlocked: Home Assistant is the main editor; it is unreachable here, so unlocking is offered prominently.
  assert.match(await root.locator('[data-heating-lock]').innerText(),/Home Assistant is niet bereikbaar/);
  assert.equal(await root.locator('[data-heating-add]').isVisible(),false);
  // Newer firmware reports Home Assistant input freshness in /status/heating; it replaces the /status fallback.
  status.ha={input_age_s:30,broker_connected:true};
  await root.locator('[data-heating-lock]').getByText('Beheerd in Home Assistant · verbonden').waitFor({timeout:15000});
  delete status.ha; // the fixture is shared by both viewport passes
  await root.locator('[data-heating-unlock]').click();assert.match(dialogs.at(-1),/ook in Home Assistant[\s\S]*tot je dit tabblad sluit/);
  // The empty state carries the Add button; the one below the list appears once there are rooms.
  assert.equal(await root.locator('[data-heating-add]').isVisible(),false);
  await root.locator('[data-heating-add-first]').click();
  const card=root.locator('[data-heating-room]').last();
  // Next to the Bluetooth choice: how to pair a sensor (closed while sensors are paired), with a link to Sensors.
  const bleHelp=card.locator('[data-heating-ble-help]');
  assert.equal(await bleHelp.evaluate(d=>d.open),false);
  await bleHelp.locator('summary').click();
  assert.match(await bleHelp.innerText(),/Hoe voeg ik een Bluetooth-sensor toe\?[\s\S]*Zoek in de buurt[\s\S]*pvvx[\s\S]*BTHome[\s\S]*Home Assistant-entiteit/);
  assert.equal(await bleHelp.locator('a[href="#sensors"][data-page="bluetooth"]').count(),1);
  // A new room asks for heat once saved, and refuses to save without a source.
  assert.equal(await card.getByLabel('Status').inputValue(),'active');
  await root.locator('[data-heating-save]').click();
  await root.getByText('Nieuwe ruimte: Kies voor elke ruimte minstens één temperatuurbron.').waitFor();
  assert.equal(posts.length,0);
  await card.getByLabel('Naam').fill('Woonkamer');
  await card.getByLabel('Status').selectOption('active');
  await card.getByLabel('Verwarmingstype').selectOption('floor');
  const first=card.locator('[data-heating-source]').first();
  await first.getByLabel('Soort bron').selectOption('ha');await first.locator('input').fill('climate.woonkamer');
  await card.getByRole('button',{name:'Bron toevoegen'}).click();
  // Bluetooth sources come from the paired sensors, with their latest reading.
  const pick=card.locator('[data-heating-source]').nth(1).locator('[data-heating-ble-pick]');
  assert.deepEqual(await pick.locator('option').allInnerTexts(),['Kies een sensor','Thermometer woonkamer · 20,4 °C · batterij 87 %','Slaapkamer']);
  await pick.selectOption('a4c138a3e8db');
  // An empty extra row is not saved.
  await card.getByRole('button',{name:'Bron toevoegen'}).click();
  await card.getByLabel('Instelapparaat in Home Assistant (optioneel)').fill('climate.woonkamer');
  await root.locator('[data-heating-save]').click();
  await root.getByText('Ruimtes opgeslagen.').waitFor();
  assert.equal(posts.length,1);
  assert.deepEqual(posts[0],{schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',
   state:'active',inactive_until:0,emitter:'floor',sources:[{type:'ha',id:'climate.woonkamer'},{type:'ble',id:'a4c138a3e8db'}],
   setpoint_entity:'climate.woonkamer',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500,
   // Every room has a week program: a new one starts with "Workdays and weekend".
   schedule:[0,1,2,3,4,5,6].map(d=>d<5?[[390,2000],[510,1800],[1020,2000],[1350,1600]]:[[480,2000],[1380,1600]])}]});
  await root.locator('[data-heating-room="woonkamer"]>summary').getByText('Vraagt warmte').waitFor();
  // Floor heating with a 60 °C maximum: a warning, not a block.
  assert.equal(await root.locator('[data-heating-flow-warn]').isVisible(),true);
  // Same ranges as the firmware (RoomPlan): minimum 20–79, maximum 21–80 °C.
  assert.deepEqual(await root.locator('#heating-min-flow,#heating-max-flow').evaluateAll(f=>f.map(i=>[i.min,i.max])),[['20','79'],['21','80']]);
  assert.match(await root.locator('[data-heating-room="woonkamer"]>summary').innerText(),/^Woonkamer\s+Vraagt warmte\s+20,4 °C\s+Gewenst 21,0 °C\s+Gewenste temperatuur uit Home Assistant$/);
  assert.equal(await root.locator('[data-heating-room="woonkamer"]').getByLabel('Weekprogramma gebruiken').isChecked(),true,'a new room has a week program');
  await root.locator('[data-heating-request]').getByText('Berekende ketelvraag: 36 °C · Verwarmen').waitFor();
  // Home Assistant saved in between: the stale write is refused and the page reloads the plan.
  plan={...plan,revision:plan.revision+1,rooms:plan.rooms.map(r=>({...r,name:'Living',schedule:week}))};
  status.rooms[0].setpoint_source='schedule';
  await root.locator('[data-heating-save]').click();
  await root.getByText(/Het plan is elders gewijzigd/).waitFor();
  assert.equal(posts.at(-1).revision,5);
  const room=root.locator('[data-heating-room="woonkamer"]');
  assert.match(await room.locator(':scope>summary').innerText(),/^Living\s+Vraagt warmte\s+20,4 °C\s+Gewenst 21,0 °C\s+Gewenste temperatuur uit het weekprogramma$/);
  // Prefill of the Home Assistant week: weekdays differ from the weekend, so one row per day.
  await room.evaluate(e=>e.open=true);
  const program=room.locator('[data-heating-week]'),points=()=>program.locator('[data-heating-day]').evaluateAll(days=>days.map(d=>[d.querySelector('strong').textContent,
   ...[...d.querySelectorAll('[data-heating-point]')].map(p=>[...p.querySelectorAll('input')].map(i=>i.value).join(' '))]));
  assert.match(await program.locator('legend').innerText(),/^Weekprogramma \(gebruikt als Home Assistant geen gewenste temperatuur geeft\)$/);
  assert.equal(await program.getByLabel('Weekprogramma gebruiken').isChecked(),true);
  assert.equal(await program.getByLabel('Elke dag hetzelfde').isChecked(),false);
  assert.deepEqual(await points(),[...['ma','di','wo','do','vr'].map(d=>[d,'06:30 20.5','22:00 18']),...['za','zo'].map(d=>[d,'08:00 20.5','12:00 20','23:00 18'])]);
  status.rooms[0].setpoint_source='fallback';
  await root.locator('[data-heating-save]').click();
  await root.getByText('Ruimtes opgeslagen.').waitFor();
  assert.equal(posts.at(-1).revision,6);assert.equal(posts.at(-1).rooms[0].name,'Living');
  assert.deepEqual(posts.at(-1).rooms[0].schedule,week,'the week program survives a web save');
  await room.locator(':scope>summary').getByText(/vaste waarde zonder Home Assistant$/).waitFor();
  status.rooms[0].setpoint_source='ha';
  // Week program editor: saves re-render the cards, so wait for the new card and open it.
  const save=async text=>{await room.evaluate(e=>e.dataset.old='1');await root.locator('[data-heating-save]').click();await root.getByText(text).waitFor();
   await root.locator('[data-heating-room="woonkamer"]:not([data-old])').waitFor({state:'attached'});await room.evaluate(e=>e.open=true);};
  const refused=async text=>{const n=posts.length;await root.locator('[data-heating-save]').click();await root.getByText(text,{exact:true}).waitFor();return posts.length-n;};
  const fillPoint=async(i,time,temp)=>{const p=program.locator('[data-heating-point]').nth(i);await p.locator('input[type=time]').fill(time);await p.locator('input[type=number]').fill(temp);};
  await room.evaluate(e=>e.open=true);
  await program.getByLabel('Weekprogramma gebruiken').uncheck();
  assert.equal(await program.locator('[data-heating-point]').first().isVisible(),false,'editor hidden when off');
  await save('Ruimtes opgeslagen.');
  assert.equal('schedule' in posts.at(-1).rooms[0],false,'toggling off removes the schedule');
  assert.equal(await program.getByLabel('Weekprogramma gebruiken').isChecked(),false);
  // Create a same-every-day program; the points are entered out of order.
  await program.getByLabel('Weekprogramma gebruiken').check();
  assert.equal(await program.getByLabel('Elke dag hetzelfde').isChecked(),true);
  assert.deepEqual(await points(),[['Elke dag','07:00 20']],'seeded with the fallback setpoint');
  await fillPoint(0,'22:30','18.0');
  await program.getByRole('button',{name:'Schakelpunt toevoegen'}).click();await fillPoint(1,'06:30','20.5');
  // Client-side checks: duplicate time, outside the room limits, missing value; nothing is posted.
  await program.getByRole('button',{name:'Schakelpunt toevoegen'}).click();await fillPoint(2,'06:30','19');
  assert.equal(await refused('Living · Elke dag: twee schakelpunten hebben dezelfde tijd.'),0);
  await fillPoint(2,'12:00','26');
  assert.equal(await refused('Living · Elke dag: temperaturen moeten tussen het minimum 5,0 °C en maximum 25,0 °C van de ruimte liggen.'),0);
  await program.locator('[data-heating-point]').nth(2).locator('input[type=number]').fill('');
  assert.equal(await refused('Living · Elke dag: vul bij elk schakelpunt een tijd en een temperatuur in.'),0);
  await program.locator('[data-heating-point]').nth(2).getByRole('button',{name:'Verwijderen'}).click();
  for(let i=0;i<5;i++)await program.getByRole('button',{name:'Schakelpunt toevoegen'}).click();
  assert.equal(await program.locator('[data-heating-point]').count(),6,'at most 6 switch points per day');
  for(let i=0;i<4;i++)await program.locator('[data-heating-point]').last().getByRole('button',{name:'Verwijderen'}).click();
  // The E32 refuses: firmware errors become clear messages and the page keeps the edit.
  reject={code:413,error:'plan_too_large'};
  assert.equal(await refused('Het plan is te groot voor de E32: gebruik minder schakelpunten of ruimtes.'),1);
  reject={code:400,error:'invalid_schedule_limits'};
  assert.equal(await refused('De E32 weigerde het weekprogramma: elke temperatuur moet binnen het minimum en maximum van de ruimte liggen.'),1);
  reject={code:400,error:'invalid_schedule'};
  assert.equal(await refused('De E32 weigerde het weekprogramma: maximaal 6 schakelpunten per dag, elk op een andere tijd.'),1);
  reject={code:400,error:'duplicate_source'};
  assert.equal(await refused('Een sensor staat twee keer in dezelfde ruimte.'),1);
  reject={code:400,error:'invalid_emitter'};
  assert.equal(await refused('De E32 weigerde het ruimteplan. Laad de pagina opnieuw en probeer het nog eens. (invalid_emitter)'),1);
  await save('Ruimtes opgeslagen.');
  const daily=[[390,2050],[1350,1800]];
  assert.deepEqual(posts.at(-1).rooms[0].schedule,Array(7).fill(daily));
  assert.equal(await program.getByLabel('Elke dag hetzelfde').isChecked(),true,'seven equal days prefill as same every day');
  assert.deepEqual(await points(),[['Elke dag','06:30 20.5','22:30 18']]);
  // Switch to one row per day and change Saturday only.
  await program.getByLabel('Elke dag hetzelfde').uncheck();
  assert.deepEqual(await points(),['ma','di','wo','do','vr','za','zo'].map(d=>[d,'06:30 20.5','22:30 18']));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll with the week open');
  await fillPoint(10,'08:00','20.5');
  await save('Ruimtes opgeslagen.');
  assert.deepEqual(posts.at(-1).rooms[0].schedule,[daily,daily,daily,daily,daily,[[480,2050],[1350,1800]],daily]);
  assert.equal(await program.getByLabel('Elke dag hetzelfde').isChecked(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Gate open (lead's release): the owner confirms the tado is disconnected; the plan goes active first.
  active.enabled=true;
  await root.locator('[data-heating-save]').click();await takeover.waitFor();
  assert.equal(posts.at(-1).mode,'shadow','saving rooms keeps the plan mode');
  assert.equal(await control.locator('[data-heating-active-gate]').isVisible(),false);
  await takeover.click();
  await control.getByText('Bevestigd. De E32 neemt de ketel binnen een minuut over.').waitFor();
  assert.match(dialogs.at(-1),/^Bevestig dat je huidige thermostaat van de ketel is losgekoppeld\./);
  assert.equal(posts.at(-1).mode,'active');assert.deepEqual(handovers,[{thermostat_disconnected:true}]);
  await control.getByText('De E32 regelt de ketel. · Ketelvraag: 45 °C · laatst verzonden 5 s geleden · laatste vraag van een andere regelaar 30 s geleden').waitFor();
  assert.equal(await takeover.isVisible(),false);assert.equal(await handback.isVisible(),true);
  await root.locator('[data-heating-save]').click();await root.getByText('Ruimtes opgeslagen.').waitFor();
  assert.equal(posts.at(-1).mode,'active','saving rooms keeps the plan mode');
  // Hand back: the plan goes shadow; the firmware sends zero for a minute. Here the tado was seen again too.
  Object.assign(active,{state:'stopping',command:{send:true,flow_c:0,why:'stop_zero'},confirmation:null,warnings:['foreign_controller']});
  await handback.click();
  await control.getByText('Teruggegeven. De E32 vraagt de ketel één minuut lang nul. Sluit daarna je thermostaat weer aan op de ketel.').waitFor();
  assert.equal(posts.at(-1).mode,'shadow');assert.equal(handovers.length,1);
  await control.getByText(/^Stoppen: de E32 vraagt de ketel één minuut lang nul\. · Ketelvraag: uit/).waitFor();
  assert.deepEqual(await control.locator('[data-heating-active-warnings] li').allInnerTexts(),
   ['Een andere regelaar (je thermostaat?) stuurt nog ketelvragen. Koppel die los van de ketel en bevestig daarna opnieuw.']);
  assert.equal(await handback.isVisible(),false);assert.equal(await takeover.isVisible(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll with active control');
  // An E32 that never had Home Assistant input opens unlocked, with a calm note instead of a warning.
  await page.evaluate(()=>sessionStorage.removeItem('ot-rooms-edit'));
  status.ha={input_age_s:null,broker_connected:false};
  await page.evaluate(()=>loadNativePage('heating'));
  await root.locator('[data-heating-lock]').getByText('Niet gekoppeld aan Home Assistant — je stelt de ruimtes hier in.').waitFor();
  assert.equal(await root.locator('[data-heating-unlock]').isVisible(),false);
  assert.equal(await root.locator('[data-heating-add]').isVisible(),true);
  assert.equal(await root.locator('[data-heating-lock]').getAttribute('class'),'alert ot-actions alert-info');
  delete status.ha;
  assert.deepEqual(errors,[]);
  results.push({width,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
