// Execute actual shipped root scripts; DOM/jQuery boundary is explicit, not a browser claim.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const fixture=require('./fixtures/root-status-ems-metadata-only.json');
function rootPage(){
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
 const context={document,$:jq};Object.assign(context,require('./helpers/ui-language.cjs')('nl'));vm.createContext(context);
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
 assert.doesNotMatch(p.main.innerHTML,/Vraagt warmte|1 vragen warmte|Aansturing is volgens de regeling vrijgegeven/);
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
  assert.match(p.main.innerHTML,/complete kamerweekprogramma is niet bevestigd/);
  assert.doesNotMatch(p.main.innerHTML,/<img|NaN|Infinity/);
 }
});
test('managed view separates actual boiler units, computed demand and inhibited output',()=>{
 const p=rootPage();p.updateRooms(managed());const html=p.main.innerHTML;
 for(const text of ['43.2','55.0','1.4','0.0','-5.5','19.3','21.0','Badkamer','1 vragen warmte','Geblokkeerd','geen bevestigde opdrachtentijdlijn'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/NaN|undefined|Infinity/);
});
test('stale or missing controller readback cannot display old demand or local ghost rooms',()=>{
 for(const control of [undefined,{fresh:false,reason:'stale',state:managed().control.state},{fresh:true,state:null},{fresh:true,state:{zones:null}}]){
  const p=rootPage();p.updateRooms(managed({control,rooms:[{name:'GHOST',demand:true}]}));
  assert.doesNotMatch(p.main.innerHTML,/Badkamer|GHOST|1 vragen warmte|Vraagt warmte/);
  assert.match(p.main.innerHTML,/Geen actuele regelstatus/);
 }
});
test('unknown telemetry never becomes zero while valid zero remains visible',()=>{
 const p=rootPage();p.updateRooms(managed({ems:{currentFlowTemperature:NaN,selectedFlowTemperature:'55',pressure:Infinity,currentBurnerPower:null}}));
 const facts=p.main.innerHTML.split('<section class="pd-panel">')[0];
 assert.equal((facts.match(/Niet beschikbaar/g)||[]).length,4);assert.doesNotMatch(facts,/NaN|Infinity|55.0|0.0/);
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
