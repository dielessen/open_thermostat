// Execute actual shipped root scripts; DOM/jQuery boundary is explicit, not a browser claim.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const fixture=require('./fixtures/root-status-ems-metadata-only.json');
function rootPage(){
 const html=fs.readFileSync(path.join(__dirname,'../data/html/index.html'),'utf8');
 class Element{
  constructor(){this.children=[];this.innerHTML='';this.classList={add(){}};}
  appendChild(x){this.children.push(x);return x;}
  append(x){this.children.push(x);}
 }
 const main=new Element();
 const document={createElement:()=>new Element(),createTextNode:x=>x,getElementById:()=>main,querySelectorAll:()=>[]};
 const jq=()=>({on(){},ready(){},css(){}});
 const context={document,$:jq};vm.createContext(context);
 for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))
  vm.runInContext(script[1],context,{filename:'data/html/index.html',lineOffset:html.slice(0,script.index).split('\n').length-1});
 return {...context,main};
}
function rendered(element){return element.innerHTML+element.children.map(rendered).join('');}
test('actual metadata-only live status commits root and uptime instead of throwing',()=>{
 const p=rootPage();p.updateRooms(fixture);
 assert.equal(p.main.children.length,1);
 const html=rendered(p.main);assert.match(html,/uptime:/);assert.match(html,/22:29:24/);
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
test('empty EMS and existing shadow-mode root behavior are preserved',()=>{
 const p=rootPage();assert.equal(p.showBoiler({},{}),null);
 p.updateRooms({controlMode:'shadow'});
 assert.match(p.main.innerHTML,/Home Assistant-managed shadow mode/);assert.match(p.main.innerHTML,/Home Assistant/);
});
