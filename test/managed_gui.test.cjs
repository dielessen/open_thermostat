// Actual shipped inline JS. Explicit DOM/HTTP boundary; NOT a browser/device claim.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function page(){
 const loads=[],scripts=[],calls=[],alerts=[],values={},checks={};
 const weatherInputs=[{disabled:false},{disabled:false}];
 const main={innerHTML:'',textContent:''},weather={hidden:true,style:{},querySelectorAll:()=>weatherInputs},note={hidden:false};
 const menus=Array.from({length:4},()=>({hidden:true}));
 const document={
  querySelectorAll:()=>menus,
  getElementById:id=>id==='LegacyWeatherSettings'?weather:id==='LegacyWeatherNotice'?note:main,
  createElement:()=>({children:[],classList:{add(){}},appendChild(x){this.children.push(x);}}),
  createTextNode:x=>x,
  head:{appendChild:x=>scripts.push(x)}
 };
 const jq=selector=>({on(){},ready(){},css(){},load(name){loads.push(name);main.innerHTML='PAGE:'+name;},
  val(...args){if(args.length){values[selector]=args[0];return this;}return values[selector]??'';},
  prop(key,...args){if(args.length){checks[selector+key]=args[0];return this;}return checks[selector+key]??false;},
  attr(){return this;},each(){},addClass(){},removeClass(){}});
 const context={document,$:jq,console,clearInterval(){},setInterval(){},setTimeout,clearTimeout,AbortController,URL,Promise,
  fetch:async(input,init={})=>{calls.push({input,init});return new Response('{}',{status:201});},
  alert:x=>alerts.push(x),confirm:()=>false,window:{addEventListener(){},location:{hash:''}}};
 Object.assign(context,require('./helpers/ui-language.cjs')('en'));vm.createContext(context);
 function run(name){
  const html=fs.readFileSync(path.join(__dirname,'../data/html',name),'utf8');
  for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))
   vm.runInContext(script[1],context,{filename:name});
  return html;
 }
 const html=run('index.html');
 return {context,main,menus,loads,scripts,calls,alerts,values,checks,weather,weatherInputs,note,html,run};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('mode is read-only until explicit legacy; HA-managed never loads duplicate editor',async()=>{
 const p=page();assert.equal(p.context.controlUiMode,'unknown');
 p.context.applyControlMode({controlMode:'legacy'});assert(p.menus.every(x=>!x.hidden));
 p.context.applyControlMode({controlMode:'shadow'});assert(p.menus.every(x=>x.hidden));
 for(const name of ['program','room_management','curve','hardware','room_setup','rooms']){
  assert.equal(await p.context.loadNativePage(name),false);
 }
 assert.equal(p.loads.length,0);assert.match(p.main.innerHTML,/Home Assistant/);
 for(const name of ['network','update','about'])assert.equal(await p.context.loadNativePage(name),true);
 assert.deepEqual(p.loads,['network.html','update.html','about.html']);
 p.context.applyControlMode({controlMode:'unknown'});assert(p.menus.every(x=>x.hidden));
});
test('root does not load Chart; legacy curve deduplicates on-demand dependency',async()=>{
 const p=page();
 assert.doesNotMatch(p.html,/<script[^>]+src="deps\/chart\.umd\.js\.gz"/);
 p.context.applyControlMode({controlMode:'legacy'});
 const a=p.context.loadNativePage('curve'),b=p.context.loadNativePage('curve');
 await tick();assert.equal(p.scripts.length,1);assert.equal(p.scripts[0].src,'deps/chart.umd.js.gz');
 p.context.Chart=class {};p.scripts[0].onload();
 assert.deepEqual(await Promise.all([a,b]),[false,true]);
 assert.deepEqual(p.loads,['curve.html']);
 assert.equal(await p.context.loadNativePage('curve'),true);
 assert.equal(p.scripts.length,1);
});
test('dependency failure is recoverable GET-only and late chart cannot replace another page',async()=>{
 const p=page();p.context.applyControlMode({controlMode:'legacy'});
 const first=p.context.loadNativePage('curve');await tick();p.scripts[0].onerror();
 assert.equal(await first,false);assert.match(p.main.textContent,/could not be loaded/);
 const second=p.context.loadNativePage('curve');await tick();
 assert.equal(p.scripts.length,2);
 await p.context.loadNativePage('network');
 p.context.Chart=class {};p.scripts[1].onload();
 assert.equal(await second,false);assert.deepEqual(p.loads,['network.html']);
 assert.equal(p.calls.length,0);
});
test('late status poll cannot replace a newly opened form',async()=>{
 const p=page();p.context.applyControlMode({controlMode:'legacy'});
 let resolve;
 p.context.fetch=()=>new Promise(r=>resolve=r);
 p.context.showRooms();
 await p.context.loadNativePage('network');
 resolve(new Response(JSON.stringify({controlMode:'legacy'}),{status:200}));
 await tick();await tick();
 assert.equal(p.main.innerHTML,'PAGE:network.html');
});
test('network saves preserve hidden legacy weather and do not manufacture missing section',async()=>{
 const p=page();p.run('network.html');p.context.validateForm=()=>true;
 p.context.applyControlMode({controlMode:'shadow'});
 const saved={enabled:true,appid:'',latitude:'0',longitude:'1',interval:60};
 p.context.loadedNetworkSettings={openweather:saved};
 p.values['#DeviceHostname']='controller';
 p.values['#DeviceOWMLat']='changed';
 p.context.saveDeviceSettings();await tick();
 let body=JSON.parse(p.calls[0].init.body);
 assert.deepEqual(body.openweather,saved);assert.equal(body.hostname,'controller');
 assert.equal(p.calls[0].init.method,'post');assert.equal(p.calls[0].input,'/config/device');
 p.context.loadedNetworkSettings={};
 p.context.saveDeviceSettings();await tick();
 body=JSON.parse(p.calls[1].init.body);assert.equal('openweather' in body,false);
});
test('weather editor follows actual runtime mode, legacy edits remain supported',async()=>{
 const p=page();p.run('network.html');p.context.validateForm=()=>true;
 p.context.applyControlMode({controlMode:'shadow'});await p.context.updateWeatherEditorVisibility();
 assert.equal(p.weather.hidden,true);assert.equal(p.weather.style.display,'none');
 assert(p.weatherInputs.every(x=>x.disabled));
 p.context.applyControlMode({controlMode:'legacy'});await p.context.updateWeatherEditorVisibility();
 assert.equal(p.weather.hidden,false);assert.equal(p.note.hidden,true);
 assert(p.weatherInputs.every(x=>!x.disabled));
 p.context.loadedNetworkSettings={openweather:{enabled:true}};
 p.checks['#DeviceOWMEnabledchecked']=false;
 p.context.saveDeviceSettings();await tick();
 assert.equal(JSON.parse(p.calls[0].init.body).openweather.enabled,false);
});
test('saving before settings load never overwrites stored values with defaults',()=>{
 const p=page();p.run('network.html');p.context.validateForm=()=>true;
 p.context.saveDeviceSettings();assert.equal(p.calls.length,0);
 assert.match(p.alerts[0],/Load device settings/);
});

test('network/update/about recovery remain accessible when mode/status is unavailable',async()=>{
 const p=page();
 p.context.fetch=async()=>{throw Error('status unavailable');};
 for(const name of ['network','update','about'])assert.equal(await p.context.loadNativePage(name),true);
 assert.deepEqual(p.loads,['network.html','update.html','about.html']);
 assert.equal(await p.context.loadNativePage('curve'),false);
 assert.match(p.main.textContent,/could not be loaded/);
});
