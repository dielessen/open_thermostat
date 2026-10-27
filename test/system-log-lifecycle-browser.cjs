// Real navigation/auth/log modules, isolated HTTP only; no device actions.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 const results=[];
 try{for(const lang of ['en','nl']){
  const page=await browser.newPage({viewport:{width:390,height:900}}),errors=[],failed=[];
  let reads=0,configReads=0,writes=0,holdLog=false,holdSave=false;
  const logGates=[],saveGates=[];
  let settings={syslog_enabled:false,server:'',port:514,syslog_level:3,web_level:3,mark_interval_s:0,syslog_esp:true,syslog_ems:false};
  let metrics={schema:1,samples:42,sampled_at_ms:70000,last_ms:12,maximum_ms:1750,intervals_ge_100_ms:3,intervals_ge_500_ms:2,intervals_ge_1000_ms:1,window_ms:10000,window_samples:30,window_maximum_ms:750};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('requestfailed',request=>failed.push({path:new URL(request.url()).pathname,method:request.method()}));
  await page.addInitScript(()=>{
   window.__fixtureVisibility='visible';
   Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__fixtureVisibility});
   const native=window.setTimeout;
   window.setTimeout=(fn,ms,...args)=>native(fn,window.__shortLogTimeout&&ms===5000?50:ms,...args);
  });
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;
   if(url.origin!=='http://opth.test')return route.abort();
   const json=async data=>{try{await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});}catch(error){if(!request.failure())throw error;}};
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/status/logs'){
    ++reads;const answer={boot:123,latest:1,records:Number(url.searchParams.get('after')||0)<1?[{sequence:1,uptime_ms:1000,level:3,feature:'App',message:'ready'}]:[],loop_intervals:metrics};
    if(holdLog){holdLog=false;await new Promise(resolve=>logGates.push(resolve));}
    return json(answer);
   }
   if(p==='/config/logging'){
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));++writes;
     const candidate=request.postDataJSON();
     if(holdSave){holdSave=false;await new Promise(resolve=>saveGates.push(resolve));}
     settings=candidate;
    }else ++configReads;
    return json(settings);
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':/\.css(?:\.gz)?$/.test(p)?'text/css':'text/html',body});
  });
  const visibility=async value=>page.evaluate(v=>{window.__fixtureVisibility=v;document.dispatchEvent(new Event('visibilitychange'));},value);
  const until=async predicate=>{for(let i=0;i<200&&!predicate();++i)await page.waitForTimeout(25);assert(predicate(),'fixture condition timed out');};
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.evaluate(()=>loadNativePage('system_log'));
  await page.locator('#log-save:enabled').waitFor();
  await page.waitForFunction(()=>document.querySelector('#log-loop-timing')?.textContent.includes('1750 ms'));
  await visibility('hidden');const hiddenReads=reads;
  await page.waitForTimeout(2300);assert.equal(reads,hiddenReads);
  // Bad optional timing must not hide valid logs or inject markup.
  metrics={...metrics,maximum_ms:'<img src=x onerror=alert(1)>'};
  await visibility('visible');await until(()=>reads>hiddenReads);
  await page.waitForFunction(()=>/unavailable|niet beschikbaar/.test(document.querySelector('#log-loop-timing')?.textContent));
  assert.equal(await page.locator('#log-status').textContent(),'');assert.equal(await page.locator('#log-loop-timing img').count(),0);
  assert((await page.locator('#log-lines').textContent()).includes('ready'));metrics={...metrics,maximum_ms:1750};
  // Visibility aborts a pending GET; resuming creates exactly one fresh read.
  holdLog=true;await until(()=>logGates.length===1);
  await visibility('hidden');await until(()=>failed.some(x=>x.path==='/status/logs'));
  const abortedReads=reads;logGates.shift()();await page.waitForTimeout(100);assert.equal(reads,abortedReads);
  await visibility('visible');await until(()=>reads>abortedReads);
  await page.waitForFunction(()=>document.querySelector('#log-loop-timing')?.textContent.includes('1750 ms'));
  assert.equal(reads,abortedReads+1);
  // A true deadline reports failure and retains the normal two-second backoff.
  holdLog=true;await page.evaluate(()=>window.__shortLogTimeout=true);
  await until(()=>logGates.length===1);
  await page.waitForFunction(()=>/unavailable|niet beschikbaar/.test(document.querySelector('#log-status')?.textContent));
  const timedOutReads=reads;await page.waitForTimeout(200);assert.equal(reads,timedOutReads);
  await page.evaluate(()=>window.__shortLogTimeout=false);logGates.shift()();
  await until(()=>reads>timedOutReads);await page.waitForFunction(()=>document.querySelector('#log-status')?.textContent==='');
  // Submitted settings writes survive hide/navigation; retired pages do not
  // perform follow-up verification reads or replay the mutation.
  holdSave=true;await page.locator('#log-port').fill('5514');await page.locator('#log-save').click();
  await until(()=>saveGates.length===1);await visibility('hidden');
  await page.evaluate(()=>mainScreen());const beforeRelease=configReads;
  saveGates.shift()();await until(()=>settings.port===5514);await page.waitForTimeout(100);
  assert.equal(configReads,beforeRelease);assert.equal(writes,1);
  assert(!failed.some(x=>x.path==='/config/logging'&&x.method==='POST'));
  const beforeHiddenMount=reads;await page.evaluate(()=>loadNativePage('system_log'));
  await page.locator('#log-save:enabled').waitFor();await page.waitForTimeout(150);
  assert.equal(reads,beforeHiddenMount);assert.equal(await page.locator('#log-port').inputValue(),'5514');
  await visibility('visible');await until(()=>reads>beforeHiddenMount);assert.equal(writes,1);
  await page.evaluate(()=>mainScreen());const leftReads=reads;
  await page.waitForTimeout(2300);assert.equal(reads,leftReads);
  assert.deepEqual(errors,[]);await page.close();
  results.push({lang,result:'PASS',hiddenStopsAndAbortsReads:true,deadlineBackoff:true,submittedPostSurvivesNavigation:true,noRetiredReadbackOrReplay:true,optionalMetricsFailClosed:true});
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
