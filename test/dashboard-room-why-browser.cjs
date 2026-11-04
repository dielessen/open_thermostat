// E32 overview (rc.4, F3): per room why it heats or not, who is home, an open contact and the valves, in the words of
// Home Assistant's Reason sensor; and (F4) at most two status chips on a phone, the rest under "Who controls the boiler?".
// Against isolated HTTP fixtures. Shipped index.html and assets; no device connection.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_ROOM_WHY_EVIDENCE||path.join(__dirname,'../out/dashboard-room-why-browser'));
const until=Math.round(Date.parse('2026-11-02T21:30:00Z')/1000);
const room=(id,extra)=>({id,name:id[0].toUpperCase()+id.slice(1),state:'active',status:'ok',source:'a4c138000001',
 temperature:20.6,setpoint:22.5,setpoint_source:'schedule',demand:false,...extra});
function heating(){
 return {schema:1,revision:4,mode:'active',request:{heat:true,flow_c:45,reason:'heating'},ha_entities:[],ble_sensors:[],
  ha:{input_age_s:8,broker_connected:true},active:{state:'active',warnings:[],enabled:true},burner:{starts_last_hour:1,activity:'heating'},
  away:{on:false,source:'none',target_c:16,until:null,presence:'home',mode:'auto',room_presence:true},
  trv:{output:true,flow_offset_c:0,rooms:[{room:'guest',control:true,degraded:false,single_source:false,
   valves:[{name:'Guest left',model:'sonoff_trvzb',health:'ok',position_pct:30},{name:'Guest right',model:'sonoff_trvzb',health:'ok',position_pct:50}]}]},
  rooms:[
   room('living',{demand:true,comfort:{mode:'program',persons:'home'}}),
   room('kitchen',{setpoint:8,comfort:{mode:'window_open',window:'open',target_c:8}}),
   room('bedroom',{temperature:18.4,setpoint:18,comfort:{mode:'presence_away',persons:'away',target_c:18}}),
   room('study',{state:'inactive',status:'inactive',source:null,temperature:null,setpoint:null}),
   room('bath',{demand:true,setpoint:24,comfort:{mode:'boost',override:'boost',target_c:24,until}}),
   room('hall',{demand:true,comfort:{mode:'program',window:'pending'}}),
   room('attic',{status:'lost',source:null,temperature:null}),
   room('guest',{temperature:21.2,setpoint:21})]};
}
const EN={living:/^Heating: 20\.6 → 22\.5 °C$/,kitchen:/^Paused: a window or door is open$/,bedroom:/^Away: nobody of this room is home \(18 °C\)$/,
 study:/^Frost protection only \(room off\)$/,bath:/^Boost until /,hall:/^A window or door is open: the room pauses soon$/,
 attic:/^No measurement: this room does not ask for heat$/,guest:/^Warm enough: 21\.2 °C \(target 21 °C\)$/};
const NL={living:/^Verwarmt: 20,6 → 22,5 °C$/,kitchen:/^Gepauzeerd: er staat een raam of deur open$/,bedroom:/^Afwezig: niemand van deze ruimte is thuis \(18 °C\)$/,
 study:/^Alleen vorstbeveiliging \(ruimte uit\)$/,bath:/^Boost tot /,hall:/^Er staat een raam of deur open: de ruimte pauzeert zo$/,
 attic:/^Geen meting: deze ruimte vraagt geen warmte$/,guest:/^Warm genoeg: 21,2 °C \(gewenst 21 °C\)$/};
const luminance=rgb=>{const [r,g,b]=rgb.match(/\d+(\.\d+)?/g).slice(0,3).map(Number);return (0.2126*r+0.7152*g+0.0722*b)/255;};
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const [width,scheme] of [[1280,'light'],[390,'dark'],[320,'light']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme});let engine=heating();const requests=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;requests.push({path:pathname,method:req.method()});
   if(pathname==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(pathname==='/status')return route.fulfill({json:{controlMode:'shadow',ems:{},control:{}}});
   if(pathname==='/status/heating')return route.fulfill({json:engine});
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.css(?:\.gz)?$/.test(pathname)?'text/css':/\.js(?:\.gz)?$/.test(pathname)?'application/javascript':'text/html'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');
  await page.waitForFunction(()=>document.querySelectorAll('.pd-room .pd-why').length===8,null,{timeout:15000});
  await page.evaluate(()=>clearInterval(intervalID));  // the test drives every later state itself
  const rooms=page.locator('.pd-room'),words=lang==='en'?EN:NL,why=i=>rooms.nth(i).locator('.pd-why').innerText();
  const order=engine.rooms.map(r=>r.id);
  for(const [i,id] of order.entries())assert.match(await why(i),words[id],lang+' '+id);
  assert.deepEqual(await page.locator('.pd-why').evaluateAll(n=>n.map(x=>x.dataset.why)),
   ['heating','window_open','room_away','off','boost','window_pending','no_measurement','warm_enough']);
  // The why line replaces the "requests heat" chip; a lost measurement is said once, not twice.
  assert.equal(await page.locator('.pd-room .ot-chip').count(),0);
  // Icons: the room's own persons (home, away), else the house; an open or pending contact.
  const icon=(i,attr)=>rooms.nth(i).locator('['+attr+']').getAttribute(attr);
  assert.equal(await icon(0,'data-presence'),'room_home');assert.equal(await icon(2,'data-presence'),'room_away');
  assert.equal(await icon(7,'data-presence'),'house_home');
  assert.equal(await icon(1,'data-window'),'open');assert.equal(await icon(5,'data-window'),'pending');
  assert.equal(await rooms.nth(0).locator('[data-window]').count(),0);
  assert.equal(await rooms.nth(0).locator('[data-presence]').getAttribute('aria-label'),lang==='en'?'Someone of this room is home':'Iemand van deze ruimte is thuis');
  assert.equal(await rooms.nth(1).locator('[data-window]').getAttribute('title'),lang==='en'?'Window or door open':'Raam of deur open');
  // Valves: the mean opening, only for a room with valves; an off room shows no temperatures.
  assert.equal(await page.locator('[data-valves]').count(),1);
  assert.equal(await rooms.nth(7).locator('[data-valves]').innerText(),lang==='en'?'Radiator valves open: 40 %':'Radiatorkranen open: 40 %');
  assert.equal(await rooms.nth(3).locator('.pd-room-temperatures').count(),0);
  assert.equal(await rooms.nth(3).locator('.pd-room-off a').count(),1);
  // F4: what the boiler does and who controls it as chips; on a phone at most two, the rest in one line further down.
  const chips=await page.locator('.pd-status .ot-chips .ot-chip').allInnerTexts(),more=page.locator('[data-dashboard-key="more-status"]');
  if(width<=560){
   assert.equal(chips.length,2,JSON.stringify(chips));assert.match(await more.textContent(),/Home Assistant: /);
  }else{assert.equal(chips.length,3,JSON.stringify(chips));assert.equal(await more.count(),0);}
  assert.equal(chips[1],lang==='en'?'The E32 controls the boiler':'De E32 regelt de ketel');
  // Light and dark: the bar follows the theme; no horizontal scroll at phone width.
  const bg=await rooms.nth(1).locator('.pd-why').evaluate(n=>getComputedStyle(n).backgroundColor);
  assert(scheme==='dark'?luminance(bg)<0.3:luminance(bg)>0.7,scheme+' '+bg);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`ROOM-WHY-${lang}-${width}-${scheme}.png`),fullPage:true});
  // Smart warm-up heats early for the next program step: said once, in the why line (HA's warm_up reason).
  const next=Math.round(Date.now()/1000)+3600;
  engine.learned={plans:{rooms:[{id:'living',optimum_start:{reason:'planned',predicted_start_utc:next-5400,lead_minutes:90,start_now:true,applies:true,estimate:false,
   reachable:true,next_switch:{utc:next,target_c:21}}}]}};
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  const clock=await page.evaluate(t=>new Date(t*1000).toLocaleTimeString(OpenThermostatLanguage.locale,{hour:'2-digit',minute:'2-digit'}),next);
  assert.equal(await why(0),(lang==='en'?'Smart warm-up: heating early for {t} (21 °C)':'Slim opwarmen: nu al verwarmen voor {t} (21 °C)').replace('{t}',clock));
  assert.equal(await page.locator('.pd-why[data-why="warm_up"]').count(),1);
  assert.equal(await rooms.nth(0).locator('.pd-warmup').count(),0,'the Smart warm-up line is not said twice');
  delete engine.learned;
  // The boiler takes over: a room that wants heat waits; in shadow mode it only wants heat.
  engine.burner.activity='tapping';await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(0),lang==='en'?/^Waiting: the boiler is making hot water$/:/^Wacht: de ketel maakt warm water$/);
  assert.match(await why(7),words.guest);  // no heat wanted: hot water is no reason
  engine.burner.activity='idle';engine.request.reason='minimum_off';await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(0),lang==='en'?/^Waiting: minimum boiler pause$/:/^Wacht: minimale ketelpauze$/);
  engine.mode='shadow';await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(0),lang==='en'?/^Wants heat: 20\.6 → 22\.5 °C$/:/^Vraagt warmte: 20,6 → 22,5 °C$/);
  // rc.3 names who is away (away_by): the room's own persons, or the whole house although its persons are home.
  engine.rooms[2].comfort={mode:'presence_away',persons:'home',away_by:'room',target_c:17};
  engine.rooms[7].comfort={mode:'presence_away',persons:'away',away_by:'house',target_c:16};
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(2),lang==='en'?/^Away: nobody of this room is home \(17 °C\)$/:/^Afwezig: niemand van deze ruimte is thuis \(17 °C\)$/);
  assert.match(await why(7),lang==='en'?/^Away: everyone is away \(16 °C\)$/:/^Afwezig: iedereen is weg \(16 °C\)$/);
  engine.rooms[2].comfort={mode:'presence_away',persons:'away',target_c:18};
  // Away for the whole house: the house icon and the away temperature.
  Object.assign(engine.away,{on:true,source:'presence',presence:'away'});engine.rooms[7].comfort={mode:'presence_away',target_c:16};
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(7),lang==='en'?/^Away: everyone is away \(16 °C\)$/:/^Afwezig: iedereen is weg \(16 °C\)$/);
  assert.equal(await icon(7,'data-presence'),'house_away');
  engine.rooms[7].comfort={mode:'away',target_c:15,until};await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.match(await why(7),lang==='en'?/^Holiday until .+ \(15 °C\)$/:/^Vakantie tot .+ \(15 °C\)$/);
  // Odd or hostile values: no icon, no markup, no made-up valve.
  engine=heating();Object.assign(engine.rooms[0],{name:'<img src=x onerror=alert(1)>',comfort:{mode:'<b>x</b>',persons:'<img>',window:'<i>'}});
  engine.away.presence='<img>';engine.trv.rooms[0].valves=[{name:'x',position_pct:'50'},null];
  await page.evaluate(s=>updateRooms({controlMode:'shadow',ems:{},control:{},heating:s}),engine);
  assert.equal(await page.locator('.pd-room img, .pd-room b, .pd-room i').count(),0);
  assert.equal(await page.locator('[data-presence]').count(),1);  // only the bedroom's own persons; the house is unknown
  assert.equal(await rooms.nth(0).locator('[data-presence], [data-window]').count(),0);
  assert.equal(await page.locator('[data-valves]').count(),0);
  assert.match(await why(0),lang==='en'?/^Heating: /:/^Verwarmt: /);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  assert.deepEqual(errors,[]);results.push({language:lang,width,scheme,status:'PASS',rooms:8});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'isolated_shipped_assets_no_device_requests',results},null,2)+'\n');
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
