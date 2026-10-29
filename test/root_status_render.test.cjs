// Execute actual shipped root scripts; DOM/jQuery boundary is explicit, not a browser claim.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const fixture=require('./fixtures/root-status-ems-metadata-only.json');
function rootPage(language='nl'){
 const html=fs.readFileSync(path.join(__dirname,'../data/html/index.html'),'utf8');
 class Element{
  querySelector(){return null;}
  constructor(){this.children=[];this.innerHTML='';this.classList={add(){}};}
  appendChild(x){this.children.push(x);return x;}
  append(x){this.children.push(x);}
 }
 const main=new Element();
 const document={createElement:()=>new Element(),createTextNode:x=>x,getElementById:()=>main,querySelectorAll:()=>[]};
 const jq=()=>({on(){},ready(){},css(){}});
 const context={document,$:jq};Object.assign(context,require('./helpers/ui-language.cjs')(language));vm.createContext(context);
 for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))
  vm.runInContext(script[1],context,{filename:'data/html/index.html',lineOffset:html.slice(0,script.index).split('\n').length-1});
 context.main=main;return context;
}
function rendered(element){return element.innerHTML+element.children.map(rendered).join('');}
test('actual metadata-only live status commits root and uptime instead of throwing',()=>{
 const p=rootPage();p.updateRooms(fixture);
 assert.equal(p.main.children.length,1);
 const html=rendered(p.main);assert.match(html,/actief sinds:/);assert.match(html,/22:29:24/);
 assert.doesNotMatch(html,/NaN|undefined|Infinity/);
});
test('missing/null/non-finite/non-numeric temperatures are unavailable, not zero or NaN',()=>{
 for(const warmWaterActive of [false,true])for(const value of [undefined,null,NaN,Infinity,-Infinity,'48.5']){
  const p=rootPage(),status={warmWaterActive,currentFlowTemperature:value,selectedFlowTemperature:value,currentWarmWaterTemperature:value,selectedWarmWaterTemperature:value};
  const html=p.showBoiler(status,{}).innerHTML;
  assert.doesNotMatch(html,/NaN|undefined|null|Infinity|<span>0\.0<\/span>|<span>48\.5<\/span>/);
 }
});
test('valid heating temperatures preserve deci-degree measured units and degree setpoint',()=>{
 const html=rootPage().showBoiler({warmWaterActive:false,currentFlowTemperature:432,selectedFlowTemperature:55},{boiler:false}).innerHTML;
 assert.match(html,/<span>43\.2<\/span>/);assert.match(html,/<span>55\.0<\/span>/);
});
test('valid zero and negative numeric temperatures are not hidden by truthiness checks',()=>{
 for(const value of [0,-5]){
  const html=rootPage().showBoiler({currentFlowTemperature:value*10,selectedFlowTemperature:value},{}).innerHTML;
  assert.equal((html.match(new RegExp('<span>'+value.toFixed(1).replace('.','\\.')+'<\\/span>','g'))||[]).length,2);
 }
});
test('DHW mode uses only DHW values and preserves partially available data',()=>{
 const p=rootPage();
 const html=p.showBoiler({warmWaterActive:true,currentWarmWaterTemperature:523,selectedWarmWaterTemperature:60,currentFlowTemperature:111,selectedFlowTemperature:22},{}).innerHTML;
 assert.match(html,/<span>52\.3<\/span>/);assert.match(html,/<span>60\.0<\/span>/);
 assert.doesNotMatch(html,/<span>11\.1<\/span>|<span>22\.0<\/span>/);
 const partial=p.showBoiler({warmWaterActive:true,currentWarmWaterTemperature:523,selectedFlowTemperature:22},{}).innerHTML;
 assert.match(partial,/<span>52\.3<\/span>/);assert.doesNotMatch(partial,/NaN|undefined|<span>22\.0<\/span>/);
});
test('managed root shows normal dashboard without resurrecting old local rooms',()=>{
 const p=rootPage();assert.equal(p.showBoiler({},{}),null);
 p.updateRooms({controlMode:'shadow',rooms:[{name:'OLD-GHOST'}]});
 assert.match(p.main.innerHTML,/Je verwarmingsinstallatie/);assert.match(p.main.innerHTML,/Home Assistant/);
 assert.doesNotMatch(p.main.innerHTML,/OLD-GHOST|shadow mode|NaN|undefined/);
 assert.match(p.main.innerHTML,/Wacht op regelstatus/);
});

function managed(overrides={}){
 return {controlMode:'shadow',ems:{currentFlowTemperature:432,selectedFlowTemperature:55,pressure:14,currentBurnerPower:0,outdoorTemperature:-550},
  control:{fresh:true,age_ms:125,captured_at_ms:10000,state:{boot_id:'boot-a',boiler_output_enabled:false,actuator_output_enabled:false,
   supervisor:{requested_heat:true,reason:'limits_unknown'},zones:[{zone_id:'aaaaaaaa',name:'Badkamer',temperature_centi_c:1925,target_centi_c:2100,demand:true,reason:'shadow_demand'}]}},...overrides};
}
test('compiled week support is explained separately from active state and cannot grant outputs',()=>{
 const p=rootPage(),control_build={schema:1,scope:'compiled_support_only',requires_local_source_selection:true,authorizes_physical_outputs:false,
  plans:[{contract:'control.plan.week.v1',minimum_zones:1,maximum_zones:2}]};
 p.updateRooms(managed({control_build,control:undefined}));
 assert.match(p.main.innerHTML,/maximaal 2 ruimtes/);
 assert.match(p.main.innerHTML,/nog niet dat Home Assistant gekoppeld is/);
 assert.match(p.main.innerHTML,/geen toestemming/);
 assert.match(p.main.innerHTML,/Geen actuele regelstatus/);
 assert.doesNotMatch(p.main.innerHTML,/Vraagt warmte|1 ruimte vraagt warmte|Aansturing is volgens de regeling vrijgegeven/);
});
test('old firmware and invalid compiled capability claims remain unknown and safely rendered',()=>{
 const p=rootPage();
 for(const control_build of [undefined,null,{schema:2},{schema:1,scope:'compiled_support_only',requires_local_source_selection:true,authorizes_physical_outputs:true,plans:[]}]){
  p.updateRooms(managed({control_build}));
  assert.match(p.main.innerHTML,/nog geen herkenbare softwareondersteuning/);
 }
 for(const maximum_zones of ['2',0,9,NaN,Infinity,'<img src=x onerror=alert(1)>']){
  p.updateRooms(managed({control_build:{schema:1,scope:'compiled_support_only',requires_local_source_selection:true,authorizes_physical_outputs:false,
   plans:[null,[],{contract:'control.plan.week.v1',minimum_zones:1,maximum_zones}]}}));
  assert.match(p.main.innerHTML,/complete weekprogramma per ruimte is niet bevestigd/);
  assert.doesNotMatch(p.main.innerHTML,/<img|NaN|Infinity/);
 }
});
test('managed view separates actual boiler units, computed demand and inhibited output',()=>{
 const p=rootPage();p.updateRooms(managed());const html=p.main.innerHTML;
 for(const text of ['43.2','1.4','0.0','-5.5','19.3','21.0','Badkamer','1 ruimte vraagt warmte','Geblokkeerd','geen bevestigde opdrachtentijdlijn'])assert.ok(html.includes(text),text);
 // The read-back setpoint is unreliable on Classic boilers and stays off the dashboard.
 assert.ok(!html.includes('55.0'),'read-back setpoint is not a dashboard value');
 assert.doesNotMatch(html,/NaN|undefined|Infinity/);
});
test('stale or missing controller readback cannot display old demand or local ghost rooms',()=>{
 for(const control of [undefined,{fresh:false,reason:'stale',state:managed().control.state},{fresh:true,state:null},{fresh:true,state:{zones:null}}]){
  const p=rootPage();p.updateRooms(managed({control,rooms:[{name:'GHOST',demand:true}]}));
  assert.doesNotMatch(p.main.innerHTML,/Badkamer|GHOST|1 ruimte vraagt warmte|Vraagt warmte/);
  assert.match(p.main.innerHTML,/Geen actuele regelstatus/);
 }
});
test('unknown telemetry never becomes zero while valid zero remains visible',()=>{
 const p=rootPage();p.updateRooms(managed({ems:{currentFlowTemperature:NaN,selectedFlowTemperature:'55',pressure:Infinity,currentBurnerPower:null}}));
 const facts=p.main.innerHTML.split('<section class="pd-panel">')[0];
 // Unreported values get no tile at all (only reliable reported values are shown).
 assert.equal((facts.match(/class="pd-fact"/g)||[]).length,0);assert.doesNotMatch(facts,/NaN|Infinity|55.0|0.0/);
 const zero=rootPage();zero.updateRooms(managed({ems:{currentBurnerPower:0}}));
 const zeroFacts=zero.main.innerHTML.split('<section class="pd-panel">')[0];
 assert.equal((zeroFacts.match(/class="pd-fact"/g)||[]).length,1,'A measured zero remains a visible tile');
 assert.equal(p.dashboardNumber(0,10,0,10),0);
 assert.equal(p.dashboardNumber(-10,10,-20,10),-1);
});
test('room names, reasons and boiler codes are text; malformed room rows are ignored',()=>{
 const status=managed();status.control.state.zones=[null,[],{zone_id:'<img src=x>',name:'<img src=x onerror=alert(1)>',reason:'<script>alert(1)</script>',demand:null}];
 status.ems.displayCode='<img onerror=alert(2)>';const p=rootPage();p.updateRooms(status);
 assert.doesNotMatch(p.main.innerHTML,/<img|<script|NaN|undefined/);assert.match(p.main.innerHTML,/&lt;img/);
 assert.equal(typeof p.dashboardReason('__proto__'),'string');assert.equal(typeof p.dashboardReason('constructor'),'string');
});
test('browser trend uses at most eight rooms and sixty distinct owner snapshots per boot',()=>{
 const p=rootPage(),status=managed();status.control.state.zones=Array.from({length:10},(_,i)=>({zone_id:i.toString(16).padStart(8,'0'),temperature_centi_c:2000,target_centi_c:2100}));
 for(let i=0;i<65;i++){status.control.captured_at_ms=i*2000;p.updateRooms(status);}
 assert.equal(Object.keys(p.installationHistory).length,8);
 for(const points of Object.values(p.installationHistory))assert.equal(points.length,60);
 p.updateRooms(status);assert.equal(p.installationHistory['00000000'].length,60);
 status.control.captured_at_ms+=16000;p.updateRooms(status);assert.equal(p.installationHistory['00000000'].length,1);
 status.control.state.boot_id='new';status.control.captured_at_ms=3;p.updateRooms(status);assert.equal(p.installationHistory['00000000'].length,1);
 status.control.state.zones=[];p.updateRooms(status);assert.equal(Object.keys(p.installationHistory).length,0);
});

test('bounded UTF-8 room label decoding preserves names and rejects malformed wire labels',()=>{
 const p=rootPage();
 for(const name of ['Badkamer','Zoë 🚀','<img src=x onerror=alert(1)>'])
  assert.equal(p.dashboardRoomName({name_utf8_hex:Buffer.from(name,'utf8').toString('hex')},0),name);
 for(const encoded of ['','00','0a','c080','zz','61'.repeat(81)])
  assert.equal(p.dashboardRoomName({name_utf8_hex:encoded},0),'Ruimte 1');
 assert.equal(p.dashboardRoomName({name:'Existing label'},1),'Existing label');
});

test('cached update notice hides unknown/current data and escapes or rejects external tags',()=>{
 const p=rootPage();
 assert.equal(p.dashboardUpdateNotice(undefined),'');
 assert.equal(p.dashboardUpdateNotice({known:false,available:true,version:'v9'}),'');
 assert.equal(p.dashboardUpdateNotice({known:true,available:false,version:'v9'}),'');
 assert.equal(p.dashboardUpdateNotice({known:true,available:true,version:'<img src=x>'}),'');
 const html=p.dashboardUpdateNotice({known:true,available:true,version:'v0.1.0-e32v2-alpha.99'});
 assert.match(html,/Firmware-update beschikbaar:/);assert.match(html,/Update bekijken/);
 assert.match(html,/data-page="update"/);assert.doesNotMatch(html,/fetch|installRelease|updates\/check/);
});

test('all canonical dashboard reason, source and mode labels have English and Dutch coverage',()=>{
 const en=rootPage('en'),nl=rootPage('nl');
 for(const map of ['dashboardReasonLabels','dashboardTargetLabels','dashboardComfortLabels']){
  for(const [key,label] of Object.entries(en[map])){
   assert.equal(en.uiText(label),label,key);
   if(label!=='Boost')assert.notEqual(nl.uiText(label),label,key);
   assert.equal(typeof nl.uiText(label),'string');
  }
 }
 assert.equal(en.dashboardReason('window_open'),'Heating paused by window/door status');
 assert.equal(en.dashboardReason('window_state_unknown'),'Waiting for valid window/door reports');
 for(const key of ['__proto__','constructor','toString',null,[],{},'<img>'])
  assert.equal(en.dashboardReason(key),'View the explanation in Home Assistant');
});

test('room context describes owner-reported targets and chosen mode without granting outputs',()=>{
 const p=rootPage('en'),status=managed(),row=status.control.state.zones[0];
 Object.assign(row,{demand:false,target_centi_c:null,target_source:'window',comfort_mode:'boost',override_remaining_ms:599999,reason:'window_open'});
 p.updateRooms(status);
 for(const text of ['Window/door contact pause','Selected mode','Boost','Time left when reported','10 min','Heating paused by window/door status'])
  assert.ok(p.main.innerHTML.includes(text),text);
 assert.match(p.main.innerHTML,/No request/);assert.match(p.main.innerHTML,/Blocked/);
 assert.equal(row.demand,false);assert.equal(row.target_centi_c,null);
 assert.equal(status.control.state.boiler_output_enabled,false);assert.equal(status.control.state.actuator_output_enabled,false);
 const old=managed();p.updateRooms(old);assert.doesNotMatch(p.main.innerHTML,/pd-room-context/);
 for(const fresh of [false,undefined,'true']){
  status.control.fresh=fresh;p.updateRooms(status);assert.doesNotMatch(p.main.innerHTML,/pd-room-context|Badkamer|10 min/);
 }
});

test('reported durations remain finite, rounded up and bounded by their existing mode contracts',()=>{
 const p=rootPage('en');
 for(const [ms,text] of [[1,'1 s'],[59000,'59 s'],[59999,'1 min'],[60000,'1 min'],[3599999,'1 h'],[3660000,'1 h 1 min'],[86400000,'24 h']]){
  const html=p.dashboardRoomContext({target_source:'temporary',override_remaining_ms:ms});assert.match(html,new RegExp('<dd>'+text+'</dd>'));
 }
 for(const remaining of [0,-1,1.5,86400001,NaN,Infinity,'60000',true,null,undefined])
  assert.doesNotMatch(p.dashboardRoomContext({target_source:'temporary',override_remaining_ms:remaining}),/Time left/);
 assert.match(p.dashboardRoomContext({comfort_mode:'boost',override_remaining_ms:14400000}),/4 h/);
 assert.doesNotMatch(p.dashboardRoomContext({comfort_mode:'boost',override_remaining_ms:14400001}),/Time left/);
 assert.doesNotMatch(p.dashboardRoomContext({target_source:'base',override_remaining_ms:60000}),/Time left/);
 // Selected boost can keep its original finite timer while contacts inhibit its effective target.
 assert.match(p.dashboardRoomContext({target_source:'window',comfort_mode:'boost',override_remaining_ms:60000}),/1 min/);
});

test('vacation end is explicit UTC within the firmware domain and never inferred from browser time',()=>{
 const p=rootPage('en'),until=Date.parse('2026-10-28T17:30:00Z')/1000;
 assert.match(p.dashboardRoomContext({comfort_mode:'vacation',vacation_until_utc:until}),/2026-10-28 17:30:00 UTC/);
 for(const value of [0,946684799,4102444800,until+0.5,String(until),true,null,Infinity,NaN])
  assert.doesNotMatch(p.dashboardRoomContext({comfort_mode:'vacation',vacation_until_utc:value}),/Reported vacation end/);
 for(const mode of ['auto','boost','away',undefined])
  assert.doesNotMatch(p.dashboardRoomContext({comfort_mode:mode,vacation_until_utc:until}),/Reported vacation end/);
});

test('optional context accepts only known labels and never turns malformed metadata into HTML',()=>{
 const p=rootPage('en');
 for(const value of ['__proto__','constructor','toString','<img src=x onerror=alert(1)>',true,{},[],null,undefined])
  assert.equal(p.dashboardRoomContext({target_source:value,comfort_mode:value,override_remaining_ms:value,vacation_until_utc:value}),'');
 assert.match(p.dashboardRoomContext({target_source:'off'}),/No effective target/);
 assert.match(p.dashboardRoomContext({comfort_mode:'frost',target_source:'frost'}),/Frost/);
 assert.doesNotMatch(p.dashboardRoomContext({comfort_mode:'frost',target_source:'frost'}),/protection|confirmed|enabled/i);
});

test('retired dashboard response bodies cannot replace a resumed owner or release its pending read',async()=>{
 const p=rootPage('en'),bodies=[];
 p.document.getElementById=id=>id==='maincontainer'?p.main:null;
 Object.assign(p,{AbortController,setTimeout,clearTimeout,hostName:'',validateResponse:x=>x,
  fetch:async()=>({json:()=>new Promise((resolve,reject)=>bodies.push({resolve,reject}))})});
 p.document.visibilityState='visible';
 const settle=()=>new Promise(setImmediate);
 p.showRooms();await settle();const retired=p.statusPoll;
 p.document.visibilityState='hidden';p.stopDashboardRead();assert.equal(retired.signal.aborted,true);
 p.document.visibilityState='visible';p.showRooms();await settle();const resumed=p.statusPoll;
 assert.notEqual(resumed,retired);
 bodies[0].resolve(managed());await settle();
 assert.equal(p.statusPoll,resumed);assert.equal(p.lastLoadedStatus,undefined);
 const newest=managed();newest.control.state.zones[0].name='Current owner';bodies[1].resolve(newest);await settle();
 assert.equal(p.statusPoll,null);assert.equal(p.lastLoadedStatus,newest);assert.match(p.main.innerHTML,/Current owner/);
 // A late rejection after retirement must not render an error over the new page.
 p.showRooms();await settle();p.stopDashboardRead();bodies[2].reject(Error('retired read'));await settle();
 assert.match(p.main.innerHTML,/Current owner/);assert.doesNotMatch(p.main.innerHTML,/dashboard-poll-error/);
});

test('a response body that ignores the dashboard deadline cannot commit after abort',async()=>{
 const p=rootPage('en');let deadline,body;
 Object.assign(p,{AbortController,hostName:'',validateResponse:x=>x,
  setTimeout:fn=>{deadline=fn;return 1;},clearTimeout(){},fetch:async()=>({json:()=>new Promise(resolve=>body=resolve)})});
 p.document.visibilityState='visible';p.showRooms();await new Promise(setImmediate);
 const request=p.statusPoll;deadline();assert.equal(request.signal.aborted,true);
 body(managed());await new Promise(setImmediate);
 assert.equal(p.lastLoadedStatus,undefined);assert.equal(p.statusPoll,null);assert.equal(p.main.innerHTML,'');
});
