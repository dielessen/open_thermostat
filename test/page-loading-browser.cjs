// Real shipped scripts in Chromium; local HTTP/cache fixture, no E32 commands.
const {chromium}=require('playwright-core');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const zlib=require('node:zlib'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(process.env.OPENTHERMOSTAT_PAGE_LOADING_EVIDENCE||path.join(__dirname,'../out/page-loading-browser'));
const hash=body=>'"'+crypto.createHash('sha256').update(body).digest('hex')+'"';
const fixture={controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}};
const telemetry={reception:{state:'classic_reports_received'},transport:{enabled:true},
 inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:2,age_ms:100,product_id:211,version:'2.3',brand_id:1,untracked_types:0,telegram_types:[2,24]}]},
 fields:{measured_flow_temperature:{value:30,unit:'degC',state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:100}},
 test:{schema:1,boot_id:'000000000000002a',revision:0,state_sequence:0,observed_at_ms:100,available:true,owned:false,
 phase:'idle',blocked_reason:'',can_prepare:true,can_start:false,can_stop:false,reported_stop_confirmed:false,
 limits:{minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,operator_lease_ms:5000}}};
(async()=>{
 const requests=[],errors=[],results=[];
 let holdReference=false,releaseReference,failReference=false,failBluetooth=false,revision='';
 const server=http.createServer(async(req,res)=>{
  const p=new URL(req.url,'http://localhost').pathname,row={path:p,method:req.method,status:0,bytes:0};requests.push(row);
  const send=(code,type,body,headers={})=>{row.status=code;row.bytes=Buffer.byteLength(body);res.writeHead(code,{'Content-Type':type,...headers});res.end(body);};
  if(req.method!=='GET')return send(405,'text/plain','unexpected mutation');
  if(p==='/auth/session')return send(200,'application/json',JSON.stringify({authenticated:true,csrf:'a'.repeat(64)}),{'Cache-Control':'no-store'});
  if(p==='/status/ems/telemetry')return send(200,'application/json',JSON.stringify(telemetry),{'Cache-Control':'no-store'});
  if(p==='/status')return send(200,'application/json',JSON.stringify(fixture),{'Cache-Control':'no-store'});
  if(p==='/config/boiler-display')return send(200,'application/json','{"model":"none"}',{'Cache-Control':'no-store'});
  if(p==='/ems-metadata.js'){
   if(holdReference)await new Promise(resolve=>releaseReference=resolve);
   if(failReference){failReference=false;return send(503,'text/plain','reference unavailable',{'Cache-Control':'no-store'});}
  }
  if(p==='/bluetooth.js'&&failBluetooth){failBluetooth=false;return send(503,'text/plain','retry on next visit',{'Cache-Control':'no-store'});}
  const file=path.join(assets,p==='/'?'index.html':p);
  if(!file.startsWith(assets+'/')||!fs.existsSync(file)||!fs.statSync(file).isFile())
   return send(404,'text/plain','missing',{'Cache-Control':'no-store'});
  const type=/\.js(?:\.gz)?$/.test(file)?'text/javascript':/\.css\.gz$/.test(file)?'text/css':'text/html';
  let body=fs.readFileSync(file),gzip=p.endsWith('.gz');
  if(p==='/about.html'&&revision)body=Buffer.concat([body,Buffer.from('<!--'+revision+'-->')]);
  if(!gzip&&body.length>=1024&&['text/javascript','text/html','text/css'].includes(type)&&req.headers['accept-encoding']?.includes('gzip')){
   body=zlib.gzipSync(body);gzip=true;
  }
  const etag=hash(body),headers={'Cache-Control':'private, no-cache','ETag':etag,'Vary':'Accept-Encoding','Content-Length':body.length};
  if(gzip)headers['Content-Encoding']='gzip';
  return send(req.headers['if-none-match']===etag?304:200,type,req.headers['if-none-match']===etag?'':body,headers);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));const start=requests.length;
   await page.goto(base+'/');await page.locator('.product-dashboard').waitFor();
   await page.locator('[data-bluetooth-settings]:not([hidden])').waitFor({state:'attached'});
   const cold=requests.slice(start),coldBytes=cold.reduce((sum,r)=>sum+r.bytes,0);
   for(const unused of ['/ems-metadata.js','/ems-devices.js','/bluetooth.js','/system-log.js','/deps/chart.umd.js.gz'])
    assert(!cold.some(r=>r.path===unused),'Home must not load '+unused);
   assert(coldBytes<160000,'Cold Home payload budget exceeded: '+coldBytes);
   await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();
   await page.evaluate(()=>loadNativePage('about'));
   assert(requests.slice(start).some(r=>r.path==='/about.html'&&r.status===304),'Revisit revalidates without retransmitting HTML');
   revision='new build';await page.evaluate(()=>loadNativePage('about'));
   assert.equal(requests.filter(r=>r.path==='/about.html').at(-1).status,200,'Changed bytes invalidate cache');revision='';
   const beforeReload=requests.length;
   await page.reload();await page.locator('.product-dashboard').waitFor();
   const reload=requests.slice(beforeReload);
   assert(reload.some(r=>r.path==='/ui-messages.js'&&r.status===304));
   assert(reload.some(r=>r.path==='/status'&&r.status===200),'Live state is read again');
   assert(reload.some(r=>r.path==='/auth/session'&&r.status===200),'Session is checked again');
   // An arbitrarily slow catalogue must not delay the actual test controls.
   holdReference=true;releaseReference=undefined;
   await page.evaluate(()=>loadNativePage('boiler_trial'));
   await page.locator('[data-test-prepare]').waitFor();
   await page.waitForFunction(()=>document.querySelector('script[src="/ems-metadata.js"]'));
   await new Promise((resolve,reject)=>{const until=Date.now()+5000;const poll=()=>releaseReference?resolve():Date.now()>until?reject(Error('reference request missing')):setTimeout(poll,10);poll();});
   const beforeLeaving=requests.length;
   await page.evaluate(()=>loadNativePage('about'));holdReference=false;releaseReference();
   await page.waitForFunction(()=>!!window.OT_EMS_METADATA);
   assert.equal(await page.locator('#boiler-test').count(),0);
   assert(!requests.slice(beforeLeaving).some(r=>r.path==='/ems_devices.html'),'Obsolete panel must not fetch/mount after navigation');
   await page.evaluate(()=>loadNativePage('boiler_test'));await page.locator('#ems-devices').waitFor();
   assert.equal(requests.slice(start).filter(r=>r.path==='/ems-devices.js').length,1);
   failBluetooth=true;
   assert.equal(await page.evaluate(()=>loadNativePage('bluetooth')),false);
   assert.equal(await page.evaluate(()=>loadNativePage('bluetooth')),true,'Failed lazy script can be retried');
   await page.locator('#bluetooth-page').waitFor();
   assert(!requests.slice(start).some(r=>r.method!=='GET'));
   results.push({width,result:'PASS',cold_payload_bytes:coldBytes,cold_requests:cold.length,
    revalidated_ui_bytes:reload.filter(r=>r.status===304).length,controls_mount_before_reference:true});
   await context.close();
  }
  // A missing optional catalogue keeps the entity panel available, then retries
  // with full metadata on the next visit without reloading its controller.
  const context=await browser.newContext(),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/');await page.locator('.product-dashboard').waitFor();failReference=true;
  await page.evaluate(()=>loadNativePage('boiler_test'));await page.locator('#ems-devices').waitFor();
  assert.equal(await page.evaluate(()=>!!window.OT_EMS_METADATA),false);
  assert.equal(await page.locator('[data-field="measured_flow_temperature"]').count(),1);
  await page.evaluate(()=>loadNativePage('about'));await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-address="8"] > summary').filter({hasText:'EasyControl Adapter'}).waitFor();
  await context.close();assert.deepEqual(errors,[]);
 }finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify({scope:'Browser/cache fixture; no physical timing claim',results,errors},null,2));
 console.log(JSON.stringify({results,optional_reference_retry:'PASS',errors}));
})().catch(error=>{console.error(error);process.exitCode=1;});
