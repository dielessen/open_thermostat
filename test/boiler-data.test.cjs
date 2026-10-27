const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../data/html/boiler-data.js'),'utf8');
function fixture(){
 const calls=[],timers=new Map(),events={};let timerId=0;
 const document={visibilityState:'visible',addEventListener:(name,fn)=>events[name]=fn};
 const context={window:{},document,AbortController,JSON,Set,Promise,Error,
  setTimeout:(fn,delay)=>{timers.set(++timerId,{fn,delay});return timerId;},clearTimeout:id=>timers.delete(id),
  fetch:(path,options)=>new Promise((resolve,reject)=>calls.push({path,options,resolve,reject}))};
 vm.runInNewContext(code,context);
 const data={fields:{temperature:{value:40,age_ms:10}},reception:{},transport:{}};
 const reply=async(index,value=data)=>{
  calls[index].resolve({ok:true,text:async()=>JSON.stringify(value)});
  await context.window.BoilerData.refresh();
 };
 return {api:context.window.BoilerData,calls,timers,data,reply,document,events};
}
test('Two consumers and overlapping refreshes share one read and one poll timer',async()=>{
 const f=fixture(),one=[],two=[],a=new AbortController(),b=new AbortController();
 f.api.subscribe((...x)=>one.push(x),{signal:a.signal});f.api.subscribe((...x)=>two.push(x),{signal:b.signal});
 const first=f.api.refresh();assert.equal(f.calls.length,1);await f.reply(0);await first;
 assert.equal(one.length,1);assert.equal(two.length,1);assert.equal(one[0][0],two[0][0]);
 assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].delay,5000);
 a.abort();assert.equal(f.timers.size,1);b.abort();assert.equal(f.timers.size,0);
 assert.equal(f.calls[0].options.cache,'no-store');assert.equal(f.calls[0].path,'/status/ems/telemetry');
});
test('Late response from a removed view cannot repaint or schedule the next view',async()=>{
 const f=fixture(),old=[],next=[],a=new AbortController();f.api.subscribe(x=>old.push(x),{signal:a.signal});
 a.abort();assert.equal(f.calls[0].options.signal.aborted,true);
 const stop=f.api.subscribe(x=>next.push(x));assert.equal(f.calls.length,2);
 f.calls[0].resolve({ok:true,text:async()=>JSON.stringify(f.data)});await new Promise(setImmediate);
 assert.equal(old.length,0);assert.equal(next.length,0);
 await f.reply(1);assert.equal(next.length,1);assert.equal(f.timers.size,1);stop();assert.equal(f.timers.size,0);
});
test('Failure clears the shared snapshot and does not retry the request immediately',async()=>{
 const f=fixture(),seen=[];const stop=f.api.subscribe((data,error)=>seen.push({data,error}));await f.reply(0);
 const job=f.api.refresh();f.calls[1].reject(Error('offline'));await job;
 assert.equal(seen.length,2);assert.equal(seen[1].data,null);assert.match(seen[1].error.message,/offline/);
 assert.equal(f.calls.length,2);assert.equal(f.timers.size,1);stop();
});
test('Oversized or over-budget responses cannot become the shared current state',async()=>{
 for(const body of ['x'.repeat(131073),JSON.stringify({fields:Object.fromEntries(Array.from({length:97},(_,i)=>[i,{}])),reception:{},transport:{}})]){
  const f=fixture(),seen=[];const stop=f.api.subscribe((data,error)=>seen.push({data,error}));
  f.calls[0].resolve({ok:true,text:async()=>body});await f.api.refresh();assert.equal(seen[0].data,null);assert(seen[0].error);stop();
 }
});
test('Hidden tabs pause polling and returning only reads a fresh snapshot',async()=>{
 const f=fixture(),seen=[];const stop=f.api.subscribe(x=>seen.push(x));await f.reply(0);
 f.document.visibilityState='hidden';f.events.visibilitychange();assert.equal(f.timers.size,0);
 await f.api.refresh();assert.equal(f.calls.length,1);
 f.document.visibilityState='visible';f.events.visibilitychange();assert.equal(f.calls.length,2);
 assert.equal(f.calls[1].options.method,undefined);await f.reply(1);stop();
});
