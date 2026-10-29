// E32 24-hour charts (beta.19 item 20): GET /status/history drawn as inline SVG on the
// dashboard, in English and Dutch, light and dark, desktop and 360 px. Fixtures only.
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
// A full day: 288 committed points and the running one.
function history(){
 const n=289,wave=p=>Math.round(200+10*Math.sin(p/30));
 return {schema:1,available:true,period_s:300,capacity:288,bytes:12528,uptime_s:90000,points:n,partial:true,oldest_start_ago_s:288*300+120,
  rooms:[{id:'living',temperature:Array.from({length:n},(_,p)=>p===100?null:wave(p)),target:Array.from({length:n},(_,p)=>p%144<60?180:210)},
   {id:'bath',temperature:null,target:null}],
  flow:Array.from({length:n},(_,p)=>p%24<8?450+p%8*10:300),return:Array.from({length:n},(_,p)=>p%24<8?380:290),
  burner_pct:Array.from({length:n},(_,p)=>p%24<8?100:p%24===8?40:0),request:Array.from({length:n},(_,p)=>p%24<8?480:0),
  thermostat_request:Array.from({length:n},(_,p)=>p%24<9?500:0)};
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
  // The boiler: one degC axis for flow, return and both requests; the burner on its own strip.
  const boiler=page.locator('.pd-history');
  assert.deepEqual(await boiler.locator('.oth-legend span').allInnerTexts(),lang==='en'?['Flow','Return','E32 request','Thermostat request','Burner on (share of each 5 minutes)']:
   ['Aanvoer','Retour','Vraag van de E32','Vraag van de thermostaat','Brander aan (deel van elke 5 minuten)']);
  assert.equal(await boiler.locator('svg.oth-chart').count(),2);
  assert.match(await boiler.locator('path.oth-bars').getAttribute('d'),/^M[\d.]+,\d+V[\d.]+h[\d.]+V\d+z/);
  assert.match(await boiler.locator('.oth-summary').innerText(),lang==='en'?/Last 24 hours: flow 30\.0–52\.0 °C, burner on 35 % of the time\./:/Laatste 24 uur: aanvoer 30,0–52,0 °C, brander 35 % van de tijd aan\./);
  // Axis labels are clock times in the viewer's zone (13:00 Amsterdam = 12:00 UTC).
  const axis=await boiler.locator('svg.oth-chart').first().locator('text.oth-axis').allTextContents();
  assert(axis.includes('°C')&&axis.some(t=>/^(?:0[0-9]|1[0-9]|2[0-3]):00$/.test(t)),axis.join('|'));
  // Light and dark use their own validated steps.
  const stroke=await living.locator('path.oth-measured').evaluate(e=>getComputedStyle(e).stroke);
  assert.equal(stroke,scheme==='dark'?'rgb(35, 156, 138)':'rgb(0, 135, 111)');
  // Table fallback: hourly averages, newest first.
  await boiler.locator('.oth-table summary').click();
  const rows=await boiler.locator('.oth-table tbody tr').count();assert(rows>=24&&rows<=26,String(rows));
  assert.deepEqual(await boiler.locator('.oth-table thead th').allInnerTexts(),lang==='en'?['Time','Flow','Return','E32 request','Thermostat request','Burner on']:
   ['Tijd','Aanvoer','Retour','Vraag van de E32','Vraag van de thermostaat','Brander aan']);
  assert.match(await boiler.locator('.oth-table tbody tr').first().innerText(),/°C/);
  // Hover: a crosshair and a tooltip with the values at that time.
  const svg=boiler.locator('svg.oth-chart').first(),box=await svg.boundingBox();
  await page.mouse.move(box.x+box.width*0.6,box.y+box.height/2);
  const tip=boiler.locator('.oth-tip').first();await tip.waitFor({state:'visible'});
  assert.match(await tip.innerText(),lang==='en'?/\d\d:\d\d[\s\S]*Flow: \d+\.\d °C/:/\d\d:\d\d[\s\S]*Aanvoer: \d+,\d °C/);
  assert.equal(await svg.locator('.oth-cross').getAttribute('visibility'),'visible');
  await page.mouse.move(2,2);await tip.waitFor({state:'hidden'});
  // Phone width: nothing wider than the screen.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(shots)await page.screenshot({path:path.join(shots,`history-${lang}-${width}-${scheme}.png`),fullPage:true});
  // At most one history read a minute, on the regular 10 s poll.
  assert.equal(reads.length,1);
  await page.clock.runFor(10000);await page.waitForTimeout(50);assert.equal(reads.length,1);
  // Within a day of a restart the chart starts at the restart and says so.
  doc={...history(),uptime_s:3000,points:10,oldest_start_ago_s:3000,rooms:[{id:'living',temperature:Array(10).fill(205),target:Array(10).fill(210)}],
   flow:Array(10).fill(400),return:null,burner_pct:Array(10).fill(50),request:Array(10).fill(0),thermostat_request:null};
  await page.clock.runFor(60000);
  await page.waitForFunction(()=>/50 min/.test(document.querySelector('.pd-room .oth-summary')?.textContent||''),null,{timeout:5000});
  assert.match(await living.locator('.oth-summary').innerText(),lang==='en'?/^Since the restart 50 min ago: measured 20\.5 °C, target 21\.0 °C\./:/^Sinds de herstart 50 min geleden: gemeten 20,5 °C, doel 21,0 °C\./);
  assert.deepEqual(await boiler.locator('.oth-legend span').allInnerTexts(),lang==='en'?['Flow','Burner on (share of each 5 minutes)']:['Aanvoer','Brander aan (deel van elke 5 minuten)']);
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
