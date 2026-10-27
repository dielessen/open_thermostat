// Shipped auth/translation modules; real loopback HTTP with a streamed body held
// after headers. No device requests and no real configuration mutations.
const {chromium}=require('playwright-core');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
(async()=>{
 let sessionReads=0,abortedBodies=0,hold=true,releaseBody;const api=[];
 const server=http.createServer((req,res)=>{
  const p=new URL(req.url,'http://localhost').pathname;
  const json=value=>{res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  if(p==='/auth/session'){
   ++sessionReads;
   if(hold){
    res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.write('{"authenticated":true,"csrf":"');
    res.on('close',()=>{if(!res.writableEnded)++abortedBodies;});
    releaseBody=()=>res.end('a'.repeat(64)+'"}');return;
   }
   return json({authenticated:true,csrf:'a'.repeat(64)});
  }
  if(p.startsWith('/fixture/')){
   let body='';req.on('data',part=>body+=part);req.on('end',()=>{api.push({path:p,method:req.method,csrf:req.headers['x-openthermostat-csrf'],body});json({ok:true});});return;
  }
  if(p==='/'){
   res.writeHead(200,{'Content-Type':'text/html'});res.end('<meta charset="utf-8"><script src="/ui-messages.js"></script><script src="/ui-language.js"></script><script defer src="/auth-client.js"></script><body><button id="auth-sign-out" hidden>Sign out</button></body>');return;
  }
  if(['/auth-client.js','/ui-messages.js','/ui-language.js'].includes(p)){
   res.writeHead(200,{'Content-Type':'application/javascript'});res.end(fs.readFileSync(path.join(assets,p)));return;
  }
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl']){
  sessionReads=abortedBodies=0;api.length=0;hold=true;releaseBody=undefined;
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:base}]);await page.clock.install();await page.goto(base+'/');
  for(let i=0;i<200&&!releaseBody;++i)await page.waitForTimeout(10);assert.equal(typeof releaseBody,'function');
  await page.evaluate(()=>{
   window.authOutcomes=null;
   Promise.allSettled([fetch('/fixture/read'),fetch('/fixture/other'),fetch('/fixture/change',{method:'POST',body:'must-not-replay'})])
    .then(rows=>window.authOutcomes=rows.map(r=>({status:r.status,error:r.reason?.message})));
  });
  await page.clock.runFor(9000);assert.equal(await page.evaluate(()=>authOutcomes),null);assert.equal(api.length,0);assert.equal(sessionReads,1);
  await page.clock.runFor(1100);await page.waitForFunction(()=>authOutcomes!==null,null,{timeout:5000});
  const outcomes=await page.evaluate(()=>authOutcomes);assert.equal(outcomes.length,3);
  assert(outcomes.every(r=>r.status==='rejected'&&/Session check unavailable|Sessiecontrole niet beschikbaar/.test(r.error)));
  for(let i=0;i<200&&!abortedBodies;++i)await page.waitForTimeout(10);assert.equal(abortedBodies,1);
  assert.equal(page.url(),base+'/');assert.equal(api.length,0);assert.equal(sessionReads,1);
  hold=false;releaseBody();await page.waitForTimeout(50);assert.equal(api.length,0);
  assert.equal(await page.evaluate(async()=>{const r=await fetch('/fixture/read');return (await r.json()).ok;}),true);
  assert.equal(sessionReads,2);assert.equal(api.length,1);assert.equal(api[0].method,'GET');
  assert.equal(await page.evaluate(async()=>{const r=await fetch('/fixture/change',{method:'POST',body:'explicit-new-action'});return (await r.json()).ok;}),true);
  assert.equal(sessionReads,2);assert.equal(api.length,2);assert.equal(api[1].csrf,'a'.repeat(64));assert.equal(api[1].body,'explicit-new-action');
  assert.equal(api.filter(r=>r.method==='POST').length,1);assert.deepEqual(errors,[]);
  results.push({lang,result:'PASS',actualStreamedBodyAbort:true,sharedSessionReadsBeforeTimeout:1,queuedRequestsRejected:3,
   queuedMutationsDispatched:0,redirects:0,nextExplicitReadRecovers:true,onlyNewExplicitMutationSent:true});await page.close();
 }}finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
 const out=path.resolve(process.env.OPENTHERMOSTAT_AUTH_BODY_EVIDENCE||path.join(__dirname,'../out/auth-body-deadline-20261027'));
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({scope:'Real loopback HTTP and shipped auth modules; no E32 requests',results},null,2)+'\n');console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
