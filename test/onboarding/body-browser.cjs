// Actual setup/translation assets over loopback HTTP. Hold status/scan/finish
// bodies after headers; WiFi and AP operations are finite in-memory fixtures.
const {chromium}=require('playwright-core');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../../data/html'),home='http://192.0.2.90/';
(async()=>{
 let mode='status',held=false,aborted=0,releaseBody,phase='ready',closing=false;
 const calls={status:0,scanReads:0,scanPosts:0,network:0,finish:0};
 const server=http.createServer((req,res)=>{
  const p=new URL(req.url,'http://localhost').pathname;
  const json=(value,code=200)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  const stream=(kind,value)=>{
   if(mode!==kind||held)return false;held=true;
   res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.write('{');
   res.on('close',()=>{if(!res.writableEnded)++aborted;});releaseBody=()=>res.end(JSON.stringify(value).slice(1));return true;
  };
  if(p==='/setup/status'){
   ++calls.status;const data={status:phase,connected:phase==='connected_saved',station_ip:phase==='connected_saved'?'192.0.2.90':'0.0.0.0',station_port:80,
    setup_active:true,remaining_seconds:880,closing,close_after_ms:closing?3000:0};
   if(!stream('status',data))json(data);return;
  }
  if(p==='/setup/scan'){
   if(req.method==='POST'){++calls.scanPosts;res.writeHead(202,{'Content-Type':'text/plain'});res.end('Scan requested');return;}
   ++calls.scanReads;const data={status:'done',networks:[{ssid:'Fixture network',rssi:-45}]};if(!stream('scan',data))json(data);return;
  }
  if(p==='/setup/network'){
   ++calls.network;req.resume();phase='connecting';res.writeHead(202,{'Content-Type':'text/plain'});res.end('Connecting; settings are saved only after successful connection');return;
  }
  if(p==='/setup/finish'){
   ++calls.finish;closing=true;if(!stream('finish',{close_after_ms:9000}))json({close_after_ms:3000},202);return;
  }
  if(['/setup.html','/setup.js','/ui-messages.js','/ui-language.js'].includes(p)){
   res.writeHead(200,{'Content-Type':p.endsWith('.js')?'application/javascript':'text/html'});res.end(fs.readFileSync(path.join(assets,p)));return;
  }
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const scenario of ['status','scan','finish']){
  mode=scenario;held=false;aborted=0;releaseBody=undefined;closing=false;phase=mode==='finish'?'connected_saved':'ready';
  Object.keys(calls).forEach(k=>calls[k]=0);
  const page=await browser.newPage({viewport:{width:390,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const url=route.request().url();if(url===home)return route.fulfill({contentType:'text/html',body:'<h1>Simulated home-network destination</h1>'});
   return new URL(url).origin===base?route.continue():route.abort();
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:base}]);await page.clock.install();await page.goto(base+'/setup.html');
  for(let i=0;i<200&&!releaseBody;++i)await page.waitForTimeout(10);assert.equal(typeof releaseBody,'function');
  await page.waitForTimeout(50);await page.clock.runFor(5100);
  for(let i=0;i<200&&!aborted;++i)await page.waitForTimeout(10);
  assert.equal(aborted,1,'setup body deadline must remain active after headers');assert.equal(page.url(),base+'/setup.html');
  assert.equal(calls.scanPosts,1);assert.equal(calls.network,0);
  releaseBody();await page.waitForTimeout(25);await page.clock.runFor(1100);
  if(mode==='finish'){
   await page.waitForFunction(()=>/seconds|seconden/.test(document.getElementById('transition')?.textContent),null,{timeout:5000});
   assert.equal(calls.finish,1,'status readback must recover an accepted finish without replay');assert.equal(calls.status,2);
   assert.equal(await page.locator('#home').getAttribute('href'),home);await page.clock.runFor(5100);await page.waitForURL(home);
   assert.equal(calls.finish,1);
  }else{
   await page.waitForFunction(()=>document.getElementById('networks')?.options.length===2,null,{timeout:5000});
   assert.equal(await page.locator('#connect').isEnabled(),true);assert.equal(calls.finish,0);assert.equal(calls.status,2);
   assert.equal(calls.scanReads,mode==='scan'?2:1);
   if(mode==='status'){
    // Ordinary network submission still accepts its existing text response.
    await page.locator('#ssid').fill('fixture-network');await page.locator('#password').fill('fixture-password');await page.locator('#connect').click();
    for(let i=0;i<200&&!calls.network;++i)await page.waitForTimeout(10);assert.equal(calls.network,1);
    await page.waitForTimeout(50);assert.match(await page.locator('#status').textContent(),/Testing connection|Verbinding wordt getest/);
   }
  }
  assert.deepEqual(errors,[]);results.push({lang,scenario:mode,result:'PASS',actualStreamedBodyAbort:true,scanPosts:calls.scanPosts,
   finishPosts:calls.finish,networkPosts:calls.network,homeNavigation:mode==='finish'?'simulated_intercept_only':'none'});await page.close();
 }}finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
 const out=path.resolve(process.env.OPENTHERMOSTAT_SETUP_BODY_EVIDENCE||path.join(__dirname,'../../out/setup-body-deadline-20261027'));
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({scope:'Loopback HTTP and intercepted destination; no device/WiFi actions',results},null,2)+'\n');console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
