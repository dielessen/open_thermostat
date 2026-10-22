// Actual delivered auth/restart JS, explicit DOM/network boundary, no device calls.
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=name=>fs.readFileSync(path.join(__dirname,'../data/html',name),'utf8');
function page({confirm=true,busy=false,pending=false,scheduled=false,status=202,legacy=false,fail=false,unauthed=false,malformed=false}={}){
 const events={},calls=[],redirects=[],proof='b'.repeat(64);
 const buttons={restart:{hidden:true,disabled:false,addEventListener:(n,f)=>events.click=f},status:{textContent:''}};
 const context={AbortController,Request,Response,Headers,URL,Object,Promise,Error,setTimeout,clearTimeout,console};
 context.document={readyState:'loading',addEventListener:(n,f)=>(events[n]??=[]).push(f),getElementById:id=>({'device-restart':buttons.restart,'device-restart-status':buttons.status}[id])};
 context.window={location:{href:'http://device/',origin:'http://device',replace:u=>redirects.push(u)},confirm:()=>confirm,alert(){},fetch:async(input,init={})=>{
  calls.push({path:input,method:init.method||'GET',headers:init.headers});
  if(input==='/auth/session')return new Response(JSON.stringify({authenticated:!unauthed,csrf:proof}),{status:legacy?404:unauthed?401:200});
  if(input==='/updates/status')return new Response(JSON.stringify(malformed?{}:{busy,boot_pending:pending,reboot_scheduled:scheduled}),{status:200});
  if(input==='/updates/reboot'){if(fail)throw Error('Network failure');return new Response('',{status});}
  throw Error('Unexpected request');
 }};
 vm.createContext(context);
 vm.runInContext(source('auth-client.js'),context);vm.runInContext(source('device-restart.js'),context);
 return {buttons,calls,redirects,events,async ready(){await Promise.all(events.DOMContentLoaded.map(f=>f()));},async click(){let stopped=0,prevented=0;await events.click({preventDefault(){prevented++;},stopPropagation(){stopped++;}});assert.equal(stopped,1);assert.equal(prevented,1);}};
}
test('visible English restart control outside collapsed menu and not a submit/reset',()=>{
 const html=source('index.html');assert.match(html,/<button type="button"[^>]*id="device-restart"[^>]*>Restart device<\/button>/);
 assert(html.indexOf('id="device-restart"')<html.indexOf('id="navbarNavDropdown"'));
 assert.match(html,/src="\/device-restart.js" defer/);
});
test('cancel confirmation sends no status/restart mutation and preserves page',async()=>{
 const p=page({confirm:false});await p.ready();assert.equal(p.buttons.restart.hidden,false);await p.click();
 assert.equal(p.calls.length,1);assert.equal(p.buttons.restart.disabled,false);assert.equal(p.buttons.status.textContent,'');
});
test('confirmed click makes exactly one native POST with session CSRF and no config write',async()=>{
 const p=page();await p.ready();await p.click();await p.click();
 assert.deepEqual(p.calls.map(c=>[c.path,c.method]),[['/auth/session','GET'],['/updates/status','GET'],['/updates/reboot','POST']]);
 assert.equal(p.calls[2].headers.get('X-OpenThermostat-CSRF'),'b'.repeat(64));
 assert.equal(p.buttons.restart.disabled,true);assert.match(p.buttons.status.textContent,/Restart requested/);
});
test('busy/pending/scheduled/malformed status fails closed before POST',async()=>{
 for(const options of [{busy:true},{pending:true},{scheduled:true},{malformed:true}]){
  const p=page(options);await p.ready();await p.click();assert.equal(p.calls.filter(c=>c.method==='POST').length,0);
  assert.match(p.buttons.status.textContent,/Wait until/);assert.equal(p.buttons.restart.disabled,false);
 }
});
test('409 or uncertain failed POST is never replayed and does not claim restart success',async()=>{
 for(const options of [{status:409},{status:403},{status:401},{fail:true}]){
  const p=page(options);await p.ready();await p.click();assert.equal(p.calls.filter(c=>c.method==='POST').length,1);
  assert.equal(p.buttons.restart.disabled,false);assert.doesNotMatch(p.buttons.status.textContent,/Restart requested/);
 }
});
test('generic legacy or missing session never exposes restart or gains auth bypass',async()=>{
 for(const options of [{legacy:true},{unauthed:true}]){
  const p=page(options);await p.ready();assert.equal(p.buttons.restart.hidden,true);assert.equal(p.events.click,undefined);
  assert.equal(p.calls.length,1);
 }
});
