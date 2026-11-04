// E32 24-hour charts (beta.19 item 20): GET /status/history drawn as inline SVG on the
// dashboard, in English and Dutch, light and dark, desktop and 360 px. Fixtures only.
// Hot water (beta.23): the owner's 31 Oct 2026 as 5-minute shares tapping and keeping warm.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),shots=process.env.OPENTHERMOSTAT_HISTORY_EVIDENCE||'';
function heating(){
 return {schema:1,revision:3,mode:'shadow',request:{heat:true,flow_c:45,reason:'demand'},ha_entities:[],ble_sensors:[],
  ha:{input_age_s:null,broker_connected:false},active:{state:'shadow',warnings:[],enabled:false},
  rooms:[
   {id:'living',name:'Living',state:'active',status:'ok',source:'a4c138000001',temperature:20.4,setpoint:21,setpoint_source:'schedule',demand:true},
   {id:'study',name:'Study <b>',state:'active',status:'ok',source:'a4c138000002',temperature:18,setpoint:19,setpoint_source:'fallback',demand:false}]};
}
// The owner's day (Home Assistant history, 10 s samples): the share of each 5 minutes (30 samples) with hot water
// in an episode the E32 counts as a tap, or as keeping warm.
const owner=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../ha/tests_native/fixtures/dhw_owner_20261031.json'),'utf8'));
function ownerDhw(){
 const episodes=owner.episodes.slice(),tap=Array(288).fill(0),warm=Array(288).fill(0);
 owner.samples.split(';').forEach((item,i)=>{
  const dhw=Number(item.split(',')[1]);
  while(episodes.length&&episodes[0][0]<i*10&&!dhw)episodes.shift();
  if(dhw&&episodes.length)(episodes[0][1]==='tapping'?tap:warm)[Math.floor(i/30)]++;
 });
 const pct=list=>list.map(c=>Math.round(c*100/30));
 return {tap:pct(tap),warm:pct(warm)};
}
const DHW=ownerDhw(),average=list=>Math.round(list.reduce((a,b)=>a+b,0)/list.length);
// A full day: 288 committed points and the running one.
function history(){
 const n=289,wave=p=>Math.round(200+10*Math.sin(p/30));
 return {schema:1,available:true,period_s:300,capacity:288,bytes:12528,uptime_s:90000,points:n,partial:true,oldest_start_ago_s:288*300+120,
  rooms:[{id:'living',temperature:Array.from({length:n},(_,p)=>p===100?null:wave(p)),target:Array.from({length:n},(_,p)=>p%144<60?180:210)},
   {id:'bath',temperature:null,target:null}],
  flow:Array.from({length:n},(_,p)=>p%24<8?450+p%8*10:300),return:Array.from({length:n},(_,p)=>p%24<8?380:290),
  burner_pct:Array.from({length:n},(_,p)=>p%24<8?100:p%24===8?40:0),request:Array.from({length:n},(_,p)=>p%24<8?480:0),
  thermostat_request:Array.from({length:n},(_,p)=>p%24<9?500:0),dhw_tap_pct:[...DHW.tap,null],dhw_reheat_pct:[...DHW.warm,null]};
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const [width,scheme] of [[1280,'light'],[360,'dark']]){
  const page=await browser.newPage({viewport:{width,height:900},timezoneId:'Europe/Amsterdam',colorScheme:scheme});
  let doc=history(),docStatus=200;const errors=[],reads=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   assert.equal(req.method(),'GET');
   if(pathname==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(pathname==='/status')return route.fulfill({json:{controlMode:'shadow',ems:{currentFlowTemperature:452},control:{}}});
   if(pathname==='/status/heating')return route.fulfill({json:heating()});
   if(pathname==='/status/history'){reads.push(Date.now());return route.fulfill({status:docStatus,json:doc});}
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.css(?:\.gz)?$/.test(pathname)?'text/css':/\.js(?:\.gz)?$/.test(pathname)?'application/javascript':'text/html'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.clock.install({time:new Date('2026-10-29T12:00:00Z')});
  await page.goto('http://opth.test/');
  await page.waitForFunction(()=>document.querySelector('.pd-room .oth')&&document.querySelector('.pd-history'),null,{timeout:15000});
  const living=page.locator('.pd-room').nth(0),study=page.locator('.pd-room').nth(1);
  // The room chart replaces the short live trend; a room without history keeps the live trend.
  assert.equal(await living.locator('svg.oth-chart').count(),1);assert.equal(await living.locator('.pd-trend').count(),0);
  assert.equal(await study.locator('.oth').count(),0);
  assert.match(await living.locator('path.oth-measured').getAttribute('d'),/^M[\d.]+,[\d.]+(L[\d.]+,[\d.]+)+M/); // a gap at the missing point
  assert.match(await living.locator('path.oth-target').getAttribute('d'),/^M[\d.]+,[\d.]+(L[\d.]+,[\d.]+){200,}$/);
  assert.match(await living.locator('.oth-summary').innerText(),lang==='en'?/Last 24 hours: measured 19\.0–21\.0 °C, target 18\.0–21\.0 °C\. Kept in the E32's memory since the last restart\./:
   /Laatste 24 uur: gemeten 19,0–21,0 °C, doel 18,0–21,0 °C\. Bewaard in het geheugen van de E32 sinds de laatste herstart\./);
  assert.equal(await living.locator('svg.oth-chart').getAttribute('role'),'img');
  assert.match(await living.locator('svg.oth-chart').getAttribute('aria-label'),/^Living: /);
  assert.deepEqual(await living.locator('.oth-legend span').allInnerTexts(),lang==='en'?['Measured','Target']:['Gemeten','Gewenst']);
  // rc.4 F7: room above and below the lines, so the target of 21.0 °C (a tick) does not sit on the edge of the plot.
  const edges=await living.locator('svg.oth-chart').evaluate(svg=>{
   const ys=[...svg.querySelectorAll('path.oth-line')].flatMap(p=>[...p.getAttribute('d').matchAll(/[ML][\d.]+,([\d.]+)/g)].map(m=>Number(m[1])));
   const grid=[...svg.querySelectorAll('line.oth-grid')].map(l=>Number(l.getAttribute('y1')));
   return {top:Math.min(...ys),bottom:Math.max(...ys),gridTop:Math.min(...grid),gridBottom:Math.max(...grid)};});
  assert(edges.top>edges.gridTop&&edges.bottom<edges.gridBottom,JSON.stringify(edges));
  // The boiler: one degC axis for flow, return and both requests; the burner on its own strip.
  const boiler=page.locator('.pd-history');
  assert.deepEqual(await boiler.locator('.oth-legend span').allInnerTexts(),lang==='en'?['Water to heating','Water back','E32 request','Thermostat request','Burner on (share of each 5 minutes)','Tapping','Keeping warm']:
   ['Water naar verwarming','Water terug','Vraag van de E32','Vraag van de thermostaat','Brander aan (deel van elke 5 minuten)','Tappen','Warmhouden']);
  assert.equal(await boiler.locator('svg.oth-chart').count(),3);
  assert.match(await boiler.locator('path.oth-bars').getAttribute('d'),/^M[\d.]+,\d+V[\d.]+h[\d.]+V\d+z/);
  // Hot water: tapping from the base, keeping warm stacked on it; one bar per 5 minutes with that kind.
  const dhwStrip=boiler.locator('svg.oth-chart').nth(2),bars=async c=>((await dhwStrip.locator('path.'+c).getAttribute('d')).match(/z/g)||[]).length;
  assert.equal(await bars('oth-tap'),DHW.tap.filter(Boolean).length);assert.equal(await bars('oth-warm'),DHW.warm.filter(Boolean).length);
  assert(DHW.warm.filter(Boolean).length>DHW.tap.filter(Boolean).length,'the owner keeps warm more often than taps');
  const fills=await dhwStrip.evaluate(svg=>['.oth-tap','.oth-warm'].map(c=>getComputedStyle(svg.querySelector(c)).fill));
  assert.notEqual(fills[0],fills[1]);assert.equal(fills[1],scheme==='dark'?'rgb(35, 156, 138)':'rgb(0, 135, 111)');
  const tapped=average(DHW.tap),warmed=average(DHW.warm);
  assert.match(await dhwStrip.getAttribute('aria-label'),lang==='en'?new RegExp(`^Hot water: tapping ${tapped} %, keeping warm ${warmed} % of the time$`):new RegExp(`^Warm water: tappen ${tapped} %, warmhouden ${warmed} % van de tijd$`));
  assert.match(await boiler.locator('.oth-summary').innerText(),lang==='en'?new RegExp(`Last 24 hours: water to heating 30\\.0–52\\.0 °C, burner on 35 % of the time, hot water: tapping ${tapped} %, keeping warm ${warmed} % of the time\\.`):
   new RegExp(`Laatste 24 uur: water naar verwarming 30,0–52,0 °C, brander 35 % van de tijd aan, warm water: tappen ${tapped} %, warmhouden ${warmed} % van de tijd\\.`));
  // Axis labels are clock times in the viewer's zone (13:00 Amsterdam = 12:00 UTC).
  const axis=await boiler.locator('svg.oth-chart').first().locator('text.oth-axis').allTextContents();
  assert(axis.includes('°C')&&axis.some(t=>/^(?:0[0-9]|1[0-9]|2[0-3]):00$/.test(t)),axis.join('|'));
  // Light and dark use their own validated steps.
  const stroke=await living.locator('path.oth-measured').evaluate(e=>getComputedStyle(e).stroke);
  assert.equal(stroke,scheme==='dark'?'rgb(35, 156, 138)':'rgb(0, 135, 111)');
  // Table fallback: hourly averages, newest first.
  await boiler.locator('.oth-table summary').click();
  const rows=await boiler.locator('.oth-table tbody tr').count();assert(rows>=24&&rows<=26,String(rows));
  assert.deepEqual(await boiler.locator('.oth-table thead th').allInnerTexts(),lang==='en'?['Time','Water to heating','Water back','E32 request','Thermostat request','Burner on','Tapping','Keeping warm']:
   ['Tijd','Water naar verwarming','Water terug','Vraag van de E32','Vraag van de thermostaat','Brander aan','Tappen','Warmhouden']);
  assert.match(await boiler.locator('.oth-table tbody tr').first().innerText(),/°C/);
  // Hover: a crosshair and a tooltip with the values at that time.
  const svg=boiler.locator('svg.oth-chart').first();await svg.scrollIntoViewIfNeeded();const box=await svg.boundingBox();
  await page.mouse.move(box.x+box.width*0.6,box.y+box.height/2);
  const tip=boiler.locator('.oth-tip').first();await tip.waitFor({state:'visible'});
  assert.match(await tip.innerText(),lang==='en'?/\d\d:\d\d[\s\S]*Water to heating: \d+\.\d °C/:/\d\d:\d\d[\s\S]*Water naar verwarming: \d+,\d °C/);
  assert.equal(await svg.locator('.oth-cross').getAttribute('visibility'),'visible');
  await page.mouse.move(2,2);await tip.waitFor({state:'hidden'});
  // The hot-water strip's tooltip: both shares at the busiest keep-warm slot.
  const slot=DHW.warm.indexOf(Math.max(...DHW.warm));await dhwStrip.scrollIntoViewIfNeeded();const strip=await dhwStrip.boundingBox();
  const at=await dhwStrip.evaluate((svg,slot)=>{const b=svg.getBoundingClientRect(),W=svg.viewBox.baseVal.width;return b.left+(30+(slot*300+30)/86400*(W-38))/W*b.width;},slot);
  await page.mouse.move(at,strip.y+strip.height/2);
  const dhwTip=boiler.locator('.oth-tip').nth(2);await dhwTip.waitFor({state:'visible'});
  assert.match(await dhwTip.innerText(),lang==='en'?new RegExp(`Tapping: ${DHW.tap[slot]} %[\\s\\S]*Keeping warm: ${DHW.warm[slot]} %`):new RegExp(`Tappen: ${DHW.tap[slot]} %[\\s\\S]*Warmhouden: ${DHW.warm[slot]} %`));
  await page.mouse.move(2,2);await dhwTip.waitFor({state:'hidden'});
  // Phone width: nothing wider than the screen.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(shots)await page.screenshot({path:path.join(shots,`history-${lang}-${width}-${scheme}.png`),fullPage:true});
  // At most one history read a minute, on the regular 10 s poll.
  assert.equal(reads.length,1);
  await page.clock.runFor(10000);await page.waitForTimeout(50);assert.equal(reads.length,1);
  // Within a day of a restart the chart starts at the restart and says so.
  doc={...history(),uptime_s:3000,points:10,oldest_start_ago_s:3000,rooms:[{id:'living',temperature:Array(10).fill(205),target:Array(10).fill(210)}],
   flow:Array(10).fill(400),return:null,burner_pct:Array(10).fill(50),request:Array(10).fill(0),thermostat_request:null,
   dhw_tap_pct:undefined,dhw_reheat_pct:undefined}; // firmware before beta.23: no hot-water keys
  await page.clock.runFor(60000);
  await page.waitForFunction(()=>/50 min/.test(document.querySelector('.pd-room .oth-summary')?.textContent||''),null,{timeout:5000});
  assert.match(await living.locator('.oth-summary').innerText(),lang==='en'?/^Since the restart 50 min ago: measured 20\.5 °C, target 21\.0 °C\./:/^Sinds de herstart 50 min geleden: gemeten 20,5 °C, doel 21,0 °C\./);
  assert.deepEqual(await boiler.locator('.oth-legend span').allInnerTexts(),lang==='en'?['Water to heating','Burner on (share of each 5 minutes)']:['Water naar verwarming','Brander aan (deel van elke 5 minuten)']);
  assert.equal(await boiler.locator('svg.oth-chart').count(),2); // firmware before beta.23: no hot-water strip
  // No memory on the E32, or a malformed document: no chart, the live view stays.
  doc={schema:1,available:false,period_s:300,capacity:288,bytes:12528,uptime_s:4000,reason:'memory_unavailable',points:0};
  await page.clock.runFor(60000);
  await page.waitForFunction(()=>!document.querySelector('.oth'),null,{timeout:5000});
  assert.equal(await page.locator('.pd-history').count(),0);
  doc={...history(),flow:[1,2,3]};
  await page.clock.runFor(60000);await page.waitForTimeout(50);assert.equal(await page.locator('.oth').count(),0);
  docStatus=503;doc={error:'history_unavailable'};
  await page.clock.runFor(60000);await page.waitForTimeout(50);assert.equal(await page.locator('.oth').count(),0);
  assert(reads.length>=4);
  assert.deepEqual(errors,[]);results.push({lang,width,scheme,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exit(1);});
