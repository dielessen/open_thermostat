// Home page (E32 rc.5) with simulated HTTP: "Water temperature by outdoor temperature" under Heating settings → Water
// temperature. The standard line (from the water temperature in hard frost) dashed and the current point from the
// status; the line learned for the house appears, solid with the gain as a band, once the slope is learned (or worked out
// from the house); the hard-frost point labelled; the crosshair by keyboard and pointer; the values as a table; the line
// of plain language; hidden without a curve. English on a desktop in light, Dutch on a phone in dark. Screenshots go to
// the evidence directory for the visual check. Waits on element state only.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),assets=path.join(root,'data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_HOUSE_CURVE_EVIDENCE||path.join(root,'out/house-curve-20261104'));
const plan={schema:1,revision:4,mode:'active',minimum_flow_c:28,maximum_flow_c:60,rooms:[
 {id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'climate.woonkamer'}],fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500},
 {id:'slaapkamer',name:'Slaapkamer',state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'sensor.slaapkamer'}],fallback_centi_c:1800,minimum_centi_c:500,maximum_centi_c:2500}]};
// A radiator house (55 °C at −10 °C: the standard slope 1.167) that learned 0.9; 6.5 °C outside, the curve asks 35 °C.
const curve=(extra={})=>({state:'applied',flow_c:35,base_c:34.1,slope:0.9,slope_source:'learned',design_flow_c:55,windows:6,last:'window_learned',...extra});
const fixture=()=>({schema:1,revision:4,mode:'active',request:{heat:true,flow_c:35,reason:'heating'},
 rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',status:'ok',temperature:20.6,setpoint:21,demand:true},
  {id:'slaapkamer',name:'Slaapkamer',state:'active',status:'ok',temperature:18,setpoint:18,demand:false}],
 ble_sensors:[],away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'},
 flow:{source:'curve',rule_flow_c:33,settings:{weather_curve:true,apply_learned:true,curve_design_flow_c:0},applied_flow_c:35,cap_c:60,
  curve:curve(),learned:{state:'not_ready',flow_c:null,room:'woonkamer'},optimum_start:{state:'none',room:null,start_utc:null}},
 learned:{schema:1,applied:true,status:'learning',outdoor_c:6.5,rooms:[]}});
const WORDS={
 en:{title:'Water temperature by outdoor temperature',legend:['Standard','Learned for your house','Now'],now:'6.5 °C outside → 35 °C',
  frost:['At −10 °C: 49 °C','8 °C cooler than standard'],standardFrost:['At −10 °C: 57 °C'],caption:/^The colder it is outside, the warmer the water\./,
  tip:['At 6.5 °C outside','34 °C','Learned for your house','38 °C','Standard'],next:'At 7.5 °C outside',outside:'Outside',
  off:'Weather compensation is off; the lines show what it would ask.',values:'Show the values'},
 nl:{title:'Watertemperatuur bij buitentemperatuur',legend:['Standaard','Geleerd voor je huis','Nu'],now:'6,5 °C buiten → 35 °C',
  frost:['Bij −10 °C: 49 °C','8 °C koeler dan standaard'],standardFrost:['Bij −10 °C: 57 °C'],caption:/^Hoe kouder het buiten is, hoe warmer het water\./,
  tip:['Bij 6,5 °C buiten','34 °C','Geleerd voor je huis','38 °C','Standaard'],next:'Bij 7,5 °C buiten',outside:'Buiten',
  off:'De weerafhankelijke regeling staat uit; de lijnen tonen wat hij zou vragen.',values:'Toon de waarden'}};
// The table view: outdoor every 5 °C, the standard and the learned line within 28 °C (the plan) .. 60 °C (the request's cap).
const TABLE=[[-15,60,53],[-10,57,49],[-5,51,44],[0,46,40],[5,40,35],[10,34,31],[15,28,28],[20,28,28]];
const LINE={light:'rgb(0, 135, 111)',dark:'rgb(35, 156, 138)'},NOW={light:'rgb(181, 96, 12)',dark:'rgb(201, 122, 44)'};
const texts=list=>list.evaluateAll(l=>l.map(e=>e.textContent.replace(/\s+/g,' ').trim()));
// The labels stay inside the drawing and never cover each other or a point.
const tidy=svg=>svg.evaluate(s=>{const vb=s.viewBox.baseVal,box=e=>{const b=e.getBBox();return {k:e.dataset.label||e.dataset.point,l:b.x,r:b.x+b.width,t:b.y,b:b.y+b.height};};
 const labels=[...s.querySelectorAll('[data-label]')].map(box),points=[...s.querySelectorAll('[data-point]')].map(box),bad=[];
 const meet=(a,c)=>a.l<c.r&&c.l<a.r&&a.t<c.b&&c.t<a.b;
 labels.forEach((a,i)=>{if(a.l<0||a.t<0||a.r>vb.width||a.b>vb.height)bad.push(a.k+' leaves the drawing');
  labels.slice(i+1).forEach(c=>{if(meet(a,c))bad.push(a.k+' covers '+c.k);});points.forEach(p=>{if(meet(a,p))bad.push(a.k+' covers point '+p.k);});});
 return bad;});
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,scheme,lang] of [[1280,'light','en'],[390,'dark','nl']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme,locale:lang==='nl'?'nl-NL':'en-GB',timezoneId:'Europe/Amsterdam'}),errors=[];
  let status=fixture();
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async r=>{
   const p=new URL(r.request().url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'b'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(status);
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/flow')return json({weather_curve:true,apply_learned:true,curve_design_flow_c:0});
   if(p==='/week-editor.js')return r.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>{sessionStorage.removeItem('ot-rooms-edit');loadNativePage('house');});
  const words=WORDS[lang],figure=page.locator('[data-curve-chart]'),svg=figure.locator('svg[role=img]');
  // The latest status at once, not after the page's 10 s refresh.
  const push=()=>page.evaluate(async()=>{const s=await (await fetch('/status/heating')).json();document.getElementById('house-settings').dispatchEvent(new CustomEvent('heating-status',{detail:s}));});
  await svg.locator('[data-point=now]').waitFor();
  // The limits of the plan arrive on their own: the table settles at the plan's lowest water temperature.
  await page.waitForFunction(()=>[...document.querySelectorAll('[data-curve-table] tr:last-child td')].map(t=>t.textContent).join('|')==='20 °C|28 °C|28 °C');
  assert.equal(await figure.locator('figcaption').innerText(),words.title);
  assert.deepEqual(await texts(figure.locator('[data-curve-legend] li')),words.legend);
  assert.equal(await svg.locator('path[data-line=standard]').count(),1);assert.equal(await svg.locator('path[data-line=learned]').count(),1);
  assert.equal(await svg.locator('path.band').count(),1);
  assert.equal(await svg.locator('[data-label=now]').textContent(),words.now);
  assert.deepEqual(await svg.locator('[data-label=frost] tspan').allTextContents(),words.frost);
  assert.match(await figure.locator('.wc-caption').innerText(),words.caption);
  assert.equal(await figure.locator('[data-curve-off]').isVisible(),false);
  assert.deepEqual(await tidy(svg),[]);
  // 2 px lines (the standard dashed, the learned solid), ringed markers of at least 8 px, labels in the text colour,
  // the validated chart colours of each mode.
  const style=await svg.evaluate(s=>{const g=(q,p)=>getComputedStyle(s.querySelector(q))[p],text=getComputedStyle(document.getElementById('house-settings')).color;
   return {learned:g('path[data-line=learned]','stroke'),width:g('path[data-line=learned]','strokeWidth'),dash:g('path[data-line=standard]','strokeDasharray'),
    solid:g('path[data-line=learned]','strokeDasharray'),now:g('[data-point=now]','fill'),ring:g('[data-point=now]','strokeWidth'),label:g('[data-label=now]','fill'),text,
    r:s.querySelector('[data-point=now]').getAttribute('r')};});
  assert.equal(style.learned,LINE[scheme]);assert.equal(style.now,NOW[scheme]);assert.equal(style.width,'2px');assert.equal(style.ring,'2px');
  assert.notEqual(style.dash,'none');assert.equal(style.solid,'none');assert(Number(style.r)>=4);assert.equal(style.label,style.text);
  // The table view.
  await figure.locator('summary').click();
  // Open, the table fits the panel (a long header wraps).
  assert.equal(await figure.evaluate(f=>{const d=f.querySelector('.wc-values');return d.open&&d.scrollWidth<=d.clientWidth+1&&f.scrollWidth<=f.clientWidth+1;}),true,'the open table fits');
  const rows=await figure.locator('[data-curve-table] tr').evaluateAll(r=>r.map(x=>[...x.children].map(c=>c.textContent)));
  assert.deepEqual(rows,[[words.outside,...words.legend.slice(0,2)],...TABLE.map(([o,s,l])=>[String(o).replace('-','−')+' °C',s+' °C',l+' °C'])]);
  assert.equal(await figure.locator('summary').innerText(),words.values);
  // The crosshair: focus shows "now", the arrow keys step a degree; a pointer along the x axis reads the curve.
  await svg.focus();
  const tip=figure.locator('.wc-tip');await tip.waitFor();
  assert.deepEqual((await tip.innerText()).split('\n').map(s=>s.trim()).filter(Boolean),words.tip);
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(([next])=>document.querySelector('[data-curve-chart] .wc-tip-head').textContent===next,[words.next]);
  // The page's refresh redraws nothing that did not change, and keeps the crosshair where it was.
  await push();
  assert.equal(await figure.locator('.wc-tip-head').innerText(),words.next);
  await svg.evaluate(s=>s.blur());await tip.waitFor({state:'hidden'});
  const box=await svg.boundingBox();
  await page.mouse.move(box.x+box.width*0.4,box.y+box.height*0.45);await tip.waitFor();
  await page.mouse.move(box.x+box.width/2,box.y-40);await tip.waitFor({state:'hidden'});
  // Phone width first: nothing scrolls sideways.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  await figure.screenshot({path:path.join(out,`${lang}-${width}-${scheme}-learned.png`)});
  // Before the house is learned: the standard line alone (and "now"), no band.
  status.flow.curve=curve({slope:1.17,slope_source:'design'});await push();
  await svg.locator('path[data-line=learned]').waitFor({state:'detached'});
  assert.equal(await svg.locator('path[data-line=standard]').count(),1);assert.equal(await svg.locator('path.band').count(),0);
  assert.equal(await svg.locator('[data-point=now]').count(),1);
  assert.deepEqual(await svg.locator('[data-label=frost] tspan').allTextContents(),words.standardFrost);
  assert.deepEqual(await texts(figure.locator('[data-curve-legend] li')),[words.legend[0],words.legend[2]]);
  assert.deepEqual(await tidy(svg),[]);
  await figure.screenshot({path:path.join(out,`${lang}-${width}-${scheme}-standard.png`)});
  // Worked out from the house model (rc.5): drawn as the learned line too.
  status.flow.curve=curve({slope:0.75,slope_source:'house',windows:2});await push();
  await svg.locator('path[data-line=learned]').waitFor();
  // A cold day in a house that needs hot water: the steep lines fill the plot, and still every label keeps clear.
  status.learned.outdoor_c=-5;status.flow.cap_c=80;status.flow.curve=curve({flow_c:70,slope:1.9,design_flow_c:70});await push();
  await page.waitForFunction(()=>document.querySelector('[data-curve-chart] [data-label=now]')?.textContent.startsWith('−5 °C'));
  assert.deepEqual(await tidy(svg),[]);
  await figure.screenshot({path:path.join(out,`${lang}-${width}-${scheme}-cold.png`)});
  // Weather compensation off: the lines stay, as what it would ask.
  status.flow.curve=curve({state:'advice'});await push();
  await figure.locator('[data-curve-off]').waitFor();
  assert.equal(await figure.locator('[data-curve-off]').innerText(),words.off);
  // Firmware without the flow document: no chart at all.
  delete status.flow;await push();
  await figure.waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);
  results.push({width,scheme,lang,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify({results,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
