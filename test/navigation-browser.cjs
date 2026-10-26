// Actual root/HTML scripts, delayed HTTP completion; no device commands.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(__dirname,'../out/navigation-browser');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(8000);const errors=[],requests=[];let held,resolveHeld,release=new Promise(r=>resolveHeld=r),finished;
  page.on('pageerror',e=>errors.push(e.message));
  const complete=new Promise(resolve=>finished=resolve);for(const event of ['requestfinished','requestfailed'])page.on(event,r=>{if(new URL(r.url()).pathname==='/ems_devices.html')finished();});
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(p==='/ems_devices.html'){held=route;resolveHeld();return;}
   if(p==='/status/ems/devices')return route.fulfill({contentType:'application/json',body:'{}'});
   const f=path.join(assets,p==='/'?'index.html':p);if(!f.startsWith(assets+'/')||!fs.existsSync(f))return route.fulfill({status:404,body:''});let body=fs.readFileSync(f);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor();
  await page.evaluate(()=>{window.navigationAttempt=loadNativePage('ems_devices');});await release;
  await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();
  await held.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(assets,'ems_devices.html'))}).catch(()=>{});await complete;
  await page.evaluate(()=>new Promise(r=>setTimeout(r,0)));await page.evaluate(()=>window.navigationAttempt);
  assert.equal(await page.locator('#about-heading').count(),1,'Late obsolete HTML must not replace About');
  assert.equal(await page.locator('#ems-devices').count(),0);
  assert.equal(requests.filter(r=>r.path==='/status/ems/devices').length,0,'Obsolete inline scripts must not execute');
  // Failed current page load is visible, and is not reported as success.
  await page.route('http://opth.test/about.html',r=>r.fulfill({status:503,body:'unavailable'}));
  assert.equal(await page.evaluate(()=>loadNativePage('about')),false);
  assert.match(await page.locator('#maincontainer').innerText(),/could not be loaded|kon niet worden geladen/);
  assert(!requests.some(r=>r.method!=='GET'));assert.deepEqual(errors,[]);
  results.push({width,result:'PASS',obsolete_scripts_executed:false});await page.close();
 }}finally{await browser.close();}
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
