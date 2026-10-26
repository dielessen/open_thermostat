// Executes the shipped JS, with explicit DOM/network unit boundaries. Not a browser/device claim.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname,'../data/html');
const csrf='a'.repeat(64);
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
function client(handler) {
  const calls=[],redirects=[],events={},button={hidden:true,disabled:false,addEventListener:(n,f)=>events['button:'+n]=f};
  const context={Request,Response,Headers,URL,Promise,Error,console,Object,AbortController,setTimeout,clearTimeout};
  context.document={readyState:'loading',addEventListener:(n,f)=>events[n]=f,getElementById:()=>button};
  context.window={location:{href:'http://device/',origin:'http://device',replace:x=>redirects.push(x)},alert:()=>{},fetch:async(input,init)=>{
    calls.push({input,init});return handler(input,init,calls.length);
  }};
  Object.assign(context,require('./helpers/ui-language.cjs')('en'));vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'auth-client.js'),'utf8'),context);
  return {...context,calls,redirects,events,button};
}
test('concurrent API reads use one session read, never one challenge per asset',async()=>{
  const c=client((u)=>u==='/auth/session'?json({authenticated:true,csrf}):json({ok:true}));
  await Promise.all(['/status','/status/rooms','/config/device','/rooms.html'].map(u=>c.window.fetch(u)));
  assert.equal(c.calls.filter(x=>x.input==='/auth/session').length,1);assert.equal(c.calls.length,5);assert.equal(c.redirects.length,0);
});
test('same-origin POST and DELETE receive CSRF; reads do not',async()=>{
  const c=client((u)=>u==='/auth/session'?json({authenticated:true,csrf}):json({ok:true}));
  await c.window.fetch('/config/rooms',{method:'post',headers:{'Content-Type':'application/json','X-Test':'preserve'},body:'[]'});
  const h=c.calls[1].init.headers;assert.equal(h.get('X-OpenThermostat-CSRF'),csrf);assert.equal(h.get('X-Test'),'preserve');assert.equal(c.calls[1].init.body,'[]');
  await c.window.fetch('/config/programs/test',{method:'DELETE'});assert.equal(c.calls[2].init.headers.get('X-OpenThermostat-CSRF'),csrf);
  await c.window.fetch('/status');assert.equal(c.calls[3].init.headers,undefined);
});
test('Request headers and init overrides follow fetch precedence',async()=>{
  const c=client((u)=>u==='/auth/session'?json({authenticated:true,csrf}):json({ok:true}));
  const request=new Request('http://device/config/device',{method:'POST',headers:{'X-Request':'yes'},body:'{}'});
  await c.window.fetch(request);assert.equal(c.calls[1].init.headers.get('X-Request'),'yes');
  await c.window.fetch(request,{headers:{'X-Override':'yes'}});assert.equal(c.calls[2].init.headers.get('X-Override'),'yes');assert.equal(c.calls[2].init.headers.get('X-Request'),null);
});
test('external origins never receive session or CSRF data',async()=>{
  const c=client(()=>json({ok:true}));await c.window.fetch('https://external.test/resource',{method:'POST',body:'test'});
  assert.equal(c.calls.length,1);assert.equal(c.calls[0].init.headers,undefined);
});
test('unauthenticated session fails before mutation and redirects once',async()=>{
  const c=client(()=>json({error:'authentication_required'},401));
  const r=await Promise.allSettled([c.window.fetch('/config/rooms',{method:'POST'}),c.window.fetch('/status')]);
  assert.ok(r.every(x=>x.status==='rejected'));assert.equal(c.calls.length,1);assert.deepEqual(c.redirects,['/login']);
});
test('401 on concurrent actual requests never retries a mutation or leaks TypeError',async()=>{
  const c=client(u=>u==='/auth/session'?json({authenticated:true,csrf}):json({error:'expired'},401));
  const r=await Promise.all([c.window.fetch('/config/rooms',{method:'POST'}),c.window.fetch('/status')]);
  assert.ok(r.every(x=>x.status===401));assert.equal(c.calls.length,3);assert.deepEqual(c.redirects,['/login']);
});
test('transient network/503 failure is not logout and not unsafe automatic retry',async()=>{
  let fail=true;const c=client(u=>{if(u==='/auth/session')return json({authenticated:true,csrf});if(fail)throw Error('offline');return json({ok:true});});
  await assert.rejects(c.window.fetch('/config/rooms',{method:'POST'}));assert.equal(c.calls.length,2);assert.equal(c.redirects.length,0);
  fail=false;await c.window.fetch('/status');assert.equal(c.calls.length,3);
  const d=client(()=>json({},503));await assert.rejects(d.window.fetch('/config/device',{method:'POST'}));assert.equal(d.calls.length,1);assert.equal(d.redirects.length,0);
});
test('invalid session proof cannot authorize a mutation',async()=>{
  for(const data of [{authenticated:false,csrf},{authenticated:true,csrf:'short'},{authenticated:true}]){
    const c=client(()=>json(data));await assert.rejects(c.window.fetch('/config/device',{method:'POST'}));assert.equal(c.calls.length,1);
  }
});
test('explicit generic-server 404 keeps old UI compatible; E32 401 never falls back',async()=>{
  const c=client(u=>u==='/auth/session'?json({},404):json({ok:true}));await c.window.fetch('/config/rooms',{method:'POST'});
  assert.equal(c.calls[1].init.headers.get('X-OpenThermostat-CSRF'),null);assert.deepEqual(Object.keys(await c.window.OpenThermostatAuth.headers()),[]);
});
test('visible sign out calls protected logout once and redirects',async()=>{
  const c=client(u=>u==='/auth/session'?json({authenticated:true,csrf}):json({authenticated:false}));
  await c.events.DOMContentLoaded();assert.equal(c.button.hidden,false);await c.events['button:click']({preventDefault(){},stopPropagation(){}});
  assert.equal(c.calls[1].input,'/auth/logout');assert.equal(c.calls[1].init.method,'POST');assert.equal(c.calls[1].init.headers.get('X-OpenThermostat-CSRF'),csrf);assert.deepEqual(c.redirects,['/login']);
});
test('failed logout suppresses legacy menu navigation and remains usable without retry',async()=>{
  const c=client(u=>{if(u==='/auth/session')return json({authenticated:true,csrf});throw Error('offline');});
  await c.events.DOMContentLoaded();let stopped=0,prevented=0;
  await c.events['button:click']({preventDefault(){prevented++;},stopPropagation(){stopped++;}});
  assert.equal(stopped,1);assert.equal(prevented,1);assert.equal(c.button.disabled,false);assert.equal(c.calls.length,2);assert.equal(c.redirects.length,0);
});
test('expired jQuery fragment load redirects only for own-origin 401, not transient errors',async()=>{
  const c=client(()=>json({authenticated:true,csrf}));
  c.window.jQuery=()=>({ajaxError:f=>c.events.ajaxError=f});await c.events.DOMContentLoaded();
  c.events.ajaxError({}, {status:503}, {url:'rooms.html'});assert.equal(c.redirects.length,0);
  c.events.ajaxError({}, {status:401}, {url:'https://external.test/rooms.html'});assert.equal(c.redirects.length,0);
  c.events.ajaxError({}, {status:401}, {url:'room_management.html'});assert.deepEqual(c.redirects,['/login']);
});
function login(handler) {
  let submit;const redirects=[],calls=[];const button={disabled:false},message={textContent:''};
  const form={reportValidity:()=>true,elements:{username:{value:'admin'},password:{value:'test & symbol'}},addEventListener:(n,f)=>submit=f};
  const context={URLSearchParams,AbortController,setTimeout,clearTimeout,fetch:async(u,i)=>{calls.push([u,i]);return handler(u,i);},document:{getElementById:id=>({login:form,submit:button,message}[id])},window:{location:{replace:u=>redirects.push(u)}}};
  Object.assign(context,require('./helpers/ui-language.cjs')('en'));vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'login.js'),'utf8'),context);
  return {submit:()=>submit({preventDefault(){}}),redirects,calls,form,button,message};
}
test('login sends URL-encoded credentials in POST body only and clears field',async()=>{
  const c=login(()=>json({authenticated:true}));await c.submit();assert.equal(c.calls[0][0],'/auth/login');assert.equal(c.calls[0][1].method,'POST');
  assert.equal(new URLSearchParams(c.calls[0][1].body).get('password'),'test & symbol');assert.equal(c.form.elements.password.value,'');assert.deepEqual(c.redirects,['/']);
});
test('login credential failure/cooldown/capacity/network errors stay in form, no browser challenge loop',async()=>{
  for(const [status,data,expected] of [[401,{error:'invalid_credentials'},'not accepted'],[429,{error:'try_again_later'},'30 seconds'],[429,{error:'session_capacity'},'Four browsers'],[503,{},'could not sign']]){
    const c=login(()=>json(data,status));await c.submit();assert.ok(c.message.textContent.includes(expected));assert.equal(c.form.elements.password.value,'');assert.equal(c.button.disabled,false);assert.equal(c.redirects.length,0);assert.equal(c.calls.length,1);
  }
  const c=login(()=>{throw Error('offline')});await c.submit();assert.ok(c.message.textContent.includes('Cannot reach'));assert.equal(c.button.disabled,false);
});
test('all shipped standalone and inline scripts parse after async upload integration',()=>{
  for(const name of ['auth-client.js','login.js','setup.js'])new vm.Script(fs.readFileSync(path.join(root,name),'utf8'),{filename:name});
  for(const name of ['index.html','update.html']){
    const html=fs.readFileSync(path.join(root,name),'utf8');
    for(const script of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(script[1],{filename:name});
  }
});
