// The shipped week planner in Chromium with touch, mouse and keyboard: alone, on the E32 rooms page
// (simulated HTTP) and in the Home Assistant card (synthetic hass). No device, no live writes.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),assets=path.join(root,'data/html');
const frontend=path.join(root,'ha/config/custom_components/open_thermostat/frontend');
const editor=fs.readFileSync(path.join(assets,'week-editor.js'),'utf8');
const output=path.resolve(process.env.OPENTHERMOSTAT_WEEK_EVIDENCE||path.join(root,'out/week-editor-browser'));
const empty=()=>[[],[],[],[],[],[],[]];
const levelsOf=(c,a,n)=>({comfort:c,away:a,night:n});
const template=(l,work=true)=>{const W=[[390,l.comfort],[510,l.away],[1020,l.comfort],[1350,l.night]],H=[[420,l.comfort],[1350,l.night]],F=[[480,l.comfort],[1380,l.night]];
 return [...Array(5)].map(()=>(work?W:H).map(p=>[...p])).concat([F.map(p=>[...p]),F.map(p=>[...p])]);};
const T={nl:{work:'Werkdagen en weekend',warmer:'Comfort warmer',empty:/Nog geen programma/,copy:'Kopiëren',weekend:'Weekend',undo:'Ongedaan maken',text:'Geavanceerd: als tekst bewerken',apply:'Tekst toepassen',bad:'Regel 2 is niet te lezen: foo',split:'Blok splitsen',remove:'Schakeltijd verwijderen',later:'15 minuten later'},
 en:{work:'Workdays and weekend',warmer:'Comfort warmer',empty:/No program yet/,copy:'Copy',weekend:'Weekend',undo:'Undo',text:'Advanced: edit as text',apply:'Apply text',bad:'Line 2 cannot be read: foo',split:'Split block',remove:'Remove switch time',later:'15 minutes later'}};
// Every control a finger needs is at least 44 × 44 px; blocks are 48 px high and also reachable through the panel.
const targets=page=>page.evaluate(()=>{const r=document.querySelector('main')||document.body;const scope=n=>n.shadowRoot?[...n.shadowRoot.querySelectorAll('*')].flatMap(x=>[x,...scope(x)]):[];
 const all=[...r.querySelectorAll('*'),...[...r.querySelectorAll('*')].flatMap(scope)];
 return all.filter(e=>e.matches('.wpe button:not(.wpe-seg),.wpe select,.wpe input,.wpe summary,.wpe-bar')&&e.offsetParent).map(e=>{const b=e.getBoundingClientRect();
  return {k:e.getAttribute('data-k')||e.className||e.tagName,w:b.width,h:b.height,name:(e.getAttribute('aria-label')||e.textContent||e.closest('label')?.textContent||'').trim()};});});
const touch=async(page,client,box,dx)=>{const x=box.x+box.width/2,y=box.y+box.height/2;
 await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
 for(let i=1;i<=8;i++)await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+dx*i/8,y}]});
 await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});};
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{
  // 1. The planner alone: every interaction, both languages, phone and desktop, light and dark.
  for(const width of [360,1280])for(const lang of ['nl','en'])for(const theme of ['light','dark']){
   const t=T[lang],page=await browser.newPage({viewport:{width,height:900},isMobile:width<720,hasTouch:true,colorScheme:theme}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.setContent('<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;padding:0 16px;font:15px system-ui;background:'+(theme==='dark'?'#162124;color:#e3eeef':'#fff')+'}</style><main></main>');
   await page.addScriptTag({content:editor});
   await page.evaluate(lang=>{window.changes=[];window.ed=OTWeekEditor.mount(document.querySelector('main'),{week:[[],[],[],[],[],[],[]],min:500,max:3000,lang,onChange:w=>changes.push(w)});},lang);
   const main=page.locator('main'),week=()=>page.evaluate(()=>ed.get()),last=()=>page.evaluate(()=>changes.at(-1));
   await main.getByText(t.empty).waitFor();
   assert.equal(await main.locator('.wpe-seg').count(),7,'one empty block per day');
   // Template: the levels fill it in (no program yet: comfort 20, away 18, night 16).
   await main.locator('select').selectOption({label:t.work});
   assert.deepEqual(await week(),template(levelsOf(2000,1800,1600)));
   assert.deepEqual(await last(),await week(),'every change reaches the host');
   // A level changes every block of that level.
   await main.getByRole('button',{name:t.warmer}).click();await main.getByRole('button',{name:t.warmer}).click();
   let l=levelsOf(2100,1800,1600);assert.deepEqual(await week(),template(l));
   // Tap Tuesday's away block and make it comfort: equal neighbours merge.
   await main.locator('[data-k="seg1-510"]').click({force:true});
   await main.locator('[data-k="set-comfort"]').click();
   let w=await week();assert.deepEqual(w[1],[[390,2100],[1350,1600]]);
   // Split it again: the second half becomes away, then remove that switch time.
   await main.locator('[data-k="seg1-390"]').click({force:true});await main.getByRole('button',{name:t.split}).click();
   w=await week();assert.deepEqual(w[1],[[390,2100],[870,1800],[1350,1600]]);
   assert.equal(await main.locator('.wpe-seg.wpe-on').getAttribute('data-k'),'seg1-870','the new block is selected');
   await main.getByRole('button',{name:t.remove}).click();
   w=await week();assert.deepEqual(w[1],[[390,2100],[1350,1600]]);
   // Exact time: +15 minutes and a typed time.
   await main.locator('[data-k="seg0-390"]').click({force:true});await main.getByRole('button',{name:t.later}).click();
   assert.deepEqual((await week())[0][0],[405,2100]);
   await main.locator('[data-k="time"]').fill('06:10');await main.locator('[data-k="time"]').press('Enter');await main.locator('[data-k="time"]').blur().catch(()=>{});
   await page.waitForFunction(()=>ed.get()[0][0][0]===370);
   await main.locator('[data-k="close"]').click();
   // Drag Monday's 17:00 line two hours later by touch (snaps to 15 minutes); a tap moves nothing.
   const client=await page.context().newCDPSession(page),bar=await main.locator('.wpe-bar').first().boundingBox();
   const handle=main.locator('.wpe-bar').first().locator('.wpe-h').nth(2);
   await touch(page,client,await handle.boundingBox(),0);
   assert.equal((await week())[0][2][0],1020,'a tap on a line is not a move');
   await touch(page,client,await main.locator('.wpe-bar').first().locator('.wpe-h').nth(2).boundingBox(),bar.width*2/24);
   assert.deepEqual((await week())[0][2],[1140,2100]);
   // A drag is limited by the neighbouring switch times.
   await touch(page,client,await main.locator('.wpe-bar').first().locator('.wpe-h').nth(2).boundingBox(),bar.width*10/24);
   assert((await week())[0][2][0]<1350,'never past the next switch time');
   // Copy Monday to the weekend, then undo.
   const before=await week();
   await main.locator('[data-k="day0"]').click();await main.getByRole('button',{name:t.weekend,exact:true}).click();
   await main.getByRole('button',{name:t.copy,exact:true}).click();
   w=await week();assert.deepEqual(w[5],w[0]);assert.deepEqual(w[6],w[0]);assert.deepEqual(w[4],before[4]);
   await main.getByRole('button',{name:t.undo}).click();assert.deepEqual(await week(),before);
   // Keyboard: Tab reaches the blocks, Enter opens the panel and focus stays on the block.
   await main.locator('[data-k="seg2-1020"]').focus();await page.keyboard.press('Enter');
   assert.equal(await main.locator('.wpe-panel').count(),1);
   assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('data-k')),'seg2-1020');
   await page.keyboard.press('Tab');assert(await page.evaluate(()=>!!document.activeElement.closest('.wpe')));
   // Advanced text view: the existing program syntax, with errors per line.
   await main.getByText(t.text).click();
   const area=main.locator('textarea');assert.match(await area.inputValue(),lang==='nl'?/^ma: 06:10 21; /:/^mon: 06:10 21; /);
   await area.fill(lang==='nl'?'ma-vr: 07:00 21; 22:00 17\nfoo':'mon-fri: 07:00 21; 22:00 17\nfoo');await main.getByRole('button',{name:t.apply}).click();
   await main.getByText(t.bad).waitFor();assert.equal(await area.inputValue(),lang==='nl'?'ma-vr: 07:00 21; 22:00 17\nfoo':'mon-fri: 07:00 21; 22:00 17\nfoo','the draft is kept');
   await area.fill(lang==='nl'?'ma-vr: 07:00 21; 22:00 17\nza-zo: 08:00 21; 23:00 17':'mon-fri: 07:00 21; 22:00 17\nsat-sun: 08:00 21; 23:00 17');await main.getByRole('button',{name:t.apply}).click();
   assert.deepEqual(await week(),[...Array(5)].map(()=>[[420,2100],[1320,1700]]).concat([[[480,2100],[1380,1700]],[[480,2100],[1380,1700]]]));
   assert.equal(await main.locator('.wpe-seg.lv-custom').count(),0,'a new program text brings its own levels');
   // Preview: one step line per block with a hover text; a day separator per midnight.
   assert((await main.locator('svg title').count())>=14);
   // Accessibility: names, touch targets, no horizontal scroll at 360 px, theme colours.
   const sizes=await targets(page);
   assert(sizes.length>20);for(const s of sizes){assert(s.name,'unnamed control '+s.k);assert(s.w>=44&&s.h>=44,JSON.stringify(s));}
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll');
   const comfort=await main.locator('.wpe-seg.lv-comfort').first().evaluate(e=>getComputedStyle(e).backgroundColor);
   assert.equal(comfort,theme==='dark'?'rgb(217, 89, 38)':'rgb(235, 104, 52)');
   await page.screenshot({path:path.join(output,`planner-${width}-${lang}-${theme}.png`),fullPage:true});
   await page.evaluate(()=>{document.querySelector('.wpe').dataset.theme='light';});
   assert.equal(await main.locator('.wpe-seg.lv-comfort').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(235, 104, 52)','a host theme wins over the system');
   assert.deepEqual(errors,[]);await client.detach();await page.close();
   results.push({part:'planner',width,lang,theme,controls:sizes.length});
  }
  // 2. The E32 rooms page: the planner writes the switch points the page saves; Home does not load it.
  for(const width of [1280,360]){
   const page=await browser.newPage({viewport:{width,height:900},hasTouch:true}),errors=[],posts=[],requests=[];
   const given=template(levelsOf(2050,1950,1800),false);
   let plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'radiator',
    sources:[{type:'ha',id:'climate.woonkamer'}],setpoint_entity:'',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500,schedule:given}]};
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('http://opth.test/**',async route=>{
    const request=route.request(),p=new URL(request.url()).pathname,json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    requests.push(p);
    if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
    if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
    if(p==='/status/heating')return json({schema:1,revision:plan.revision,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'fallback',temperature:20.4,setpoint:21,demand:false}],ble_sensors:[],ha:{input_age_s:null,broker_connected:false},active:{state:'shadow',warnings:[],enabled:false}});
    if(p==='/config/heating'){if(request.method()==='POST'){const body=request.postDataJSON();posts.push(body);plan={...body,revision:plan.revision+1};}return json(plan);}
    const file=path.join(assets,p==='/'?'index.html':p);
    if(!file.startsWith(assets+path.sep)&&!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
    let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
    return route.fulfill({contentType:/\.js(\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
   });
   await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
   await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
   await page.waitForTimeout(300);
   assert(!requests.includes('/week-editor.js'),'Home does not load the planner');
   await page.evaluate(()=>loadNativePage('heating'));
   const room=page.locator('[data-heating-room="woonkamer"]');await room.waitFor();await room.evaluate(e=>e.open=true);
   const planner=room.locator('[data-heating-planner]');await planner.locator('.wpe-seg').first().waitFor();
   assert.equal(await room.locator('[data-heating-point]').first().isVisible(),false,'the list is the hidden fallback');
   assert.equal(await planner.getByRole('button',{name:'Comfort warmer'}).isVisible(),true,'Dutch planner');
   // Levels come from the program: 20.5 comfort, 18 night, 19.5 away; the template uses them.
   await planner.locator('select').selectOption({label:'Werkdagen en weekend'});
   await page.screenshot({path:path.join(output,`e32-rooms-${width}.png`),fullPage:true});
   await page.locator('[data-heating-save]').click();await page.getByText('Ruimtes opgeslagen.').waitFor();
   assert.deepEqual(posts.at(-1).rooms[0].schedule,template(levelsOf(2050,1950,1800)));
   assert.equal(posts.at(-1).revision,4);
   // A same-every-day program goes through the page's own "same every day" path unchanged.
   await room.evaluate(e=>e.open=true);
   await page.locator('[data-heating-room="woonkamer"] [data-heating-planner] select').selectOption({label:'Elke dag hetzelfde'});
   await page.locator('[data-heating-save]').click();await page.getByText('Ruimtes opgeslagen.').waitFor();
   assert.deepEqual(posts.at(-1).rooms[0].schedule,Array(7).fill([[420,2050],[1350,1800]]));
   // Week program off, saved; turning it on again starts from "Workdays and weekend" at the room's target (21 °C).
   await room.evaluate(e=>e.open=true);
   await room.getByLabel('Weekprogramma gebruiken').uncheck();
   await page.locator('[data-heating-save]').click();await page.getByText('Ruimtes opgeslagen.').waitFor();
   assert.equal('schedule' in posts.at(-1).rooms[0],false);
   await room.evaluate(e=>e.open=true);await room.getByLabel('Weekprogramma gebruiken').check();
   await room.locator('[data-heating-planner] .wpe-seg.lv-away').first().waitFor();
   await page.locator('[data-heating-save]').click();await page.getByText('Ruimtes opgeslagen.').waitFor();
   assert.deepEqual(posts.at(-1).rooms[0].schedule,template(levelsOf(2100,1850,1600)));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll');
   assert.deepEqual(errors,[]);await page.close();results.push({part:'e32',width,posts:posts.length});
  }
  const haCard=async(width,lang,dark,imperial=false,{getFail=null,cardUrl=null}={})=>{
   const page=await browser.newPage({viewport:{width,height:1000},hasTouch:true}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('http://ha.test/**',route=>{const p=new URL(route.request().url()).pathname;
    if(p==='/')return route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width, initial-scale=1"><body style="margin:0;font:15px system-ui"><main></main></body>'});
    if(p==='/open_thermostat/week-editor-0.4.0b12.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(frontend,'week-editor.js'))});
    if(p==='/card.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(frontend,'e32-week-card.js'))});
    return route.fulfill({status:404,body:''});});
   await page.goto('http://ha.test/');await page.addScriptTag({url:'/card.js',type:'module'});
   const rooms=[{id:'woonkamer',name:'Woonkamer',minimum_centi_c:1000,maximum_centi_c:2400,fallback_centi_c:2000,setpoint_entity:'climate.woonkamer',schedule:null},
    {id:'zolder',name:'Zolder',minimum_centi_c:500,maximum_centi_c:2500,fallback_centi_c:1800,setpoint_entity:'',schedule:[[[420,2000],[1350,1700]],[],[],[],[],[],[]]}];
   await page.evaluate(({rooms,lang,dark,imperial,getFail,cardUrl})=>{window.calls=[];window.fail=null;let state=structuredClone(rooms);
    const card=window.card=document.createElement('openthermostat-e32-week');card.setConfig({entry_id:'entry'});document.querySelector('main').append(card);
    card.hass={language:lang,config:{unit_system:{temperature:imperial?'°F':'°C'}},locale:{language:lang},themes:{darkMode:dark},callWS:async r=>{calls.push(structuredClone(r));
     if(r.type==='open_thermostat/e32_week/get'){if(getFail){const f=getFail;getFail=null;throw {code:f};}return {revision:4,rooms:structuredClone(state),...(cardUrl?{card_url:cardUrl}:{})};}
     if(r.type!=='open_thermostat/e32_week/save')throw {code:'unexpected'};
     if(fail){const f=fail;fail=null;throw {code:f};}
     state=state.map(x=>x.id===r.room_id?{...x,schedule:r.schedule}:x);return {revision:5,rooms:structuredClone(state)};}};},{rooms,lang,dark,imperial,getFail,cardUrl});
   return {page,errors,rooms};
  };
  // 3. The Home Assistant card: rooms as tabs, save with the loaded program as the guard, errors in plain words.
  for(const [width,lang,dark] of [[390,'nl',true],[1280,'en',false]]){
   const {page,errors,rooms}=await haCard(width,lang,dark);
   const card=page.locator('openthermostat-e32-week');await card.locator('.wpe-seg').first().waitFor();
   const T2=lang==='nl'?{save:'Opslaan op E32',saved:'Opgeslagen op de E32.',changed:/elders gewijzigd/,remove:'Weekprogramma verwijderen',tpl:'Thuiswerken',follows:/volgt climate.woonkamer/}
    :{save:'Save to E32',saved:'Saved on the E32.',changed:/changed elsewhere/,remove:'Remove week program',tpl:'Working from home',follows:/follows climate.woonkamer/};
   assert.equal(await card.locator('.wpe').getAttribute('data-theme'),dark?'dark':'light');
   await card.getByText(T2.follows).waitFor();
   assert.equal(await card.getByRole('button',{name:T2.save}).isDisabled(),true,'nothing to save yet');
   await card.locator('.wpe select').selectOption({label:T2.tpl});
   await card.getByRole('button',{name:T2.save}).click();await card.getByText(T2.saved).waitFor();
   let save=await page.evaluate(()=>calls.at(-1));
   assert.deepEqual([save.room_id,save.expected],['woonkamer',null]);
   assert.deepEqual(save.schedule,template(levelsOf(2000,1800,1600),false));
   // The second room: its draft survives switching tabs; a refused save keeps the draft and explains why.
   await card.getByRole('tab',{name:'Zolder'}).click();
   assert.equal(await card.getByRole('tab',{name:'Zolder'}).getAttribute('aria-selected'),'true');
   await card.locator('[data-k="seg0-420"]').click({force:true});await card.locator('[data-k="set-night"]').click();
   await card.getByRole('tab',{name:'Woonkamer'}).click();await card.getByRole('tab',{name:'Zolder'}).click();
   assert.equal(await card.getByRole('button',{name:T2.save}).isDisabled(),false,'the draft survived the tab switch');
   await page.evaluate(()=>{fail='week_changed';});
   await card.getByRole('button',{name:T2.save}).click();await card.getByText(T2.changed).waitFor();
   assert.equal(await card.getByRole('button',{name:T2.save}).isDisabled(),false);
   await card.getByRole('button',{name:T2.save}).click();await card.getByText(T2.saved).waitFor();
   save=await page.evaluate(()=>calls.at(-1));
   assert.deepEqual(save.expected,rooms[1].schedule,'the loaded program guards the save');
   await card.getByRole('button',{name:T2.remove}).click();await card.getByRole('button',{name:T2.save}).click();await card.getByText(T2.saved).waitFor();
   assert.equal((await page.evaluate(()=>calls.at(-1))).schedule,null,'removing the program sends no schedule');
   const sizes=await page.evaluate(()=>[...card.shadowRoot.querySelectorAll('button,select,input')].filter(e=>e.offsetParent&&!e.classList.contains('wpe-seg')).map(e=>{const b=e.getBoundingClientRect();return [e.textContent||e.getAttribute('aria-label'),b.width,b.height];}));
   for(const [name,w,h] of sizes)assert(w>=44&&h>=44,name+' '+w+'x'+h);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll');
   await page.screenshot({path:path.join(output,`ha-card-${width}-${lang}.png`),fullPage:true});
   assert.deepEqual(errors,[]);await page.close();results.push({part:'ha',width,lang,dark});
  }
  // 4. Home Assistant in imperial units: °F on screen and in the text view, the saved program stays in °C.
  for(const lang of ['en','nl']){
   const {page,errors}=await haCard(390,lang,false,true),card=page.locator('openthermostat-e32-week');
   await card.locator('.wpe-seg').first().waitFor();await card.getByRole('tab',{name:'Zolder'}).click();
   await card.getByText(/^Comfort 68 °F$/).waitFor();await card.getByText(lang==='nl'?/^Nacht 62,6 °F$/:/^Night 62.6 °F$/).waitFor();
   await card.getByText(lang==='nl'?'Geavanceerd: als tekst bewerken':'Advanced: edit as text').click();
   assert.equal(await card.locator('textarea').inputValue(),lang==='nl'?'ma: 07:00 68; 22:30 62,6':'mon: 07:00 68; 22:30 62.6');
   await card.getByText(lang==='nl'?/Temperaturen in °F\./:/Temperatures in °F\./).waitFor();
   // One step warmer is 1 °F: 69 °F = 20.56 °C.
   await card.getByRole('button',{name:'Comfort warmer'}).click();await card.getByText(/^Comfort 69 °F$/).waitFor();
   // An own temperature typed in °F.
   await card.locator('[data-k="seg0-1350"]').click({force:true});
   await card.locator('[data-k="own"]').fill('61');await card.locator('[data-k="own"]').press('Enter');
   await card.getByRole('button',{name:lang==='nl'?'Opslaan op E32':'Save to E32'}).click();
   await card.getByText(lang==='nl'?/Opgeslagen op de E32\./:/Saved on the E32\./).waitFor();
   assert.deepEqual((await page.evaluate(()=>calls.at(-1))).schedule,[[[420,2056],[1350,1611]],[],[],[],[],[],[]],'stored in centi °C');
   // A program typed in °F is stored in °C.
   await card.getByText(lang==='nl'?'Geavanceerd: als tekst bewerken':'Advanced: edit as text').click();
   const area=card.locator('textarea');await area.fill(lang==='nl'?'ma-vr: 06:30 70; 22:00 60,8':'mon-fri: 06:30 70; 22:00 60.8');
   await card.getByRole('button',{name:lang==='nl'?'Tekst toepassen':'Apply text'}).click();
   await card.getByRole('button',{name:lang==='nl'?'Opslaan op E32':'Save to E32'}).click();
   await card.getByText(lang==='nl'?/Opgeslagen op de E32\./:/Saved on the E32\./).waitFor();
   assert.deepEqual((await page.evaluate(()=>calls.at(-1))).schedule,[...Array(5)].map(()=>[[390,2111],[1320,1600]]).concat([[],[]]));
   await page.screenshot({path:path.join(output,`ha-card-fahrenheit-${lang}.png`),fullPage:true});
   assert.deepEqual(errors,[]);await page.close();results.push({part:'ha-fahrenheit',lang});
  }
  // 5. Not ready yet (HA starting, E32 not connected): "Waiting for the E32…", never a dead card; a page left
  //    open over an update asks for a reload (Ctrl+F5) but keeps working.
  for(const lang of ['en','nl']){
   const W=lang==='nl'?{wait:'Wachten op de E32…',why:/probeert het vanzelf opnieuw/,reload:'Opnieuw laden',outdated:/bijgewerkt\. Laad de pagina opnieuw \(Ctrl\+F5\)/}
    :{wait:'Waiting for the E32…',why:/tries again by itself/,reload:'Reload',outdated:/was updated\. Reload the page \(Ctrl\+F5\)/};
   let {page,errors}=await haCard(390,lang,false,false,{getFail:'not_ready'}),card=page.locator('openthermostat-e32-week');
   await card.getByText(W.wait).waitFor();await card.getByText(W.why).waitFor();
   assert.equal(await page.evaluate(()=>card._retry!==null),true,'a retry is scheduled');
   await page.screenshot({path:path.join(output,`ha-card-waiting-${lang}.png`),fullPage:true});
   assert.equal(await card.getByRole('button',{name:W.reload}).isVisible(),true,'the user can also try at once');
   // Off screen (another view): no timer; back on screen: it tries again at once and shows the planner.
   await page.evaluate(()=>card.remove());assert.equal(await page.evaluate(()=>card._retry),null,'no timer after removal');
   await page.evaluate(()=>document.querySelector('main').append(card));await card.locator('.wpe-seg').first().waitFor();
   assert.equal(await card.getByText(W.wait).count(),0);
   assert.deepEqual(errors,[]);await page.close();
   ({page,errors}=await haCard(390,lang,false,false,{cardUrl:'/open_thermostat/e32-week-card-0.0.0.js'}));card=page.locator('openthermostat-e32-week');
   await card.locator('.wpe-seg').first().waitFor();await card.getByText(W.outdated).waitFor();
   await page.screenshot({path:path.join(output,`ha-card-outdated-${lang}.png`),fullPage:true});
   assert.deepEqual(errors,[]);await page.close();
   ({page,errors}=await haCard(390,lang,false,false,{cardUrl:'/card.js'}));card=page.locator('openthermostat-e32-week');
   await card.locator('.wpe-seg').first().waitFor();assert.equal(await card.getByText(W.outdated).count(),0,'the served module: no notice');
   assert.deepEqual(errors,[]);await page.close();results.push({part:'ha-waiting',lang});
  }
  // 6. Another dashboard card (a HACS resource) replaces window.customElements after our modules ran, with a
  //    scoped-registry polyfill whose get() does not see earlier definitions (the owner's HA, 30 Oct 2026):
  //    every OpenThermostat card element is defined again in the registry in use, without errors.
  {
   const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('http://ha.test/**',route=>{const p=new URL(route.request().url()).pathname;
    if(p==='/')return route.fulfill({contentType:'text/html',body:'<body><main></main></body>'});
    if(p==='/card.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(frontend,'e32-week-card.js'))});
    if(p==='/planner.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(frontend,'week-planner.js'))});
    return route.fulfill({status:404,body:''});});
   await page.goto('http://ha.test/');
   await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
   await page.addScriptTag({url:'/card.js',type:'module'});await page.addScriptTag({url:'/planner.js',type:'module'});
   const names=['openthermostat-e32-week','openthermostat-room-editor-v42','openthermostat-week-planner','openthermostat-room-editor'];
   await page.waitForFunction(names=>names.every(n=>customElements.get(n)),names);
   const replace=()=>page.evaluate(()=>{const h=new Map(),waits=new Map();
    const fake={h,define(n,c){if(h.has(n))throw new DOMException('already defined','NotSupportedError');h.set(n,{g:c});(waits.get(n)||[]).forEach(r=>r(c));},
     get(n){const t=h.get(n);return t==null?void 0:t.g;},whenDefined(n){return h.has(n)?Promise.resolve(h.get(n).g):new Promise(r=>waits.set(n,[...(waits.get(n)||[]),r]));}};
    const define=fake.define;fake.define=function(e,t,i){fake.get(e)||define.call(fake,e,t,i);};
    Object.defineProperty(window,'customElements',{value:fake,configurable:true});});
   await replace();
   assert.equal(await page.evaluate(()=>customElements.get('openthermostat-e32-week')),undefined,'the polyfill hides earlier definitions');
   await page.waitForFunction(names=>names.every(n=>typeof customElements.get(n)==='function'),names,{timeout:5000});
   // Replaced again much later: the next navigation inside Home Assistant defines them again.
   await replace();await page.evaluate(()=>window.dispatchEvent(new Event('location-changed')));
   assert.deepEqual(await page.evaluate(names=>names.filter(n=>typeof customElements.get(n)!=='function'),names),[]);
   assert.deepEqual(errors,[]);await page.close();results.push({part:'ha-registry-replaced'});
  }
 }finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify({status:'PASS',results},null,2)+'\n');
 console.log(JSON.stringify({status:'PASS',cases:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
