// Real root/fragment/auth/language scripts; bounded isolated HTTP fixtures.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(process.env.OPTH_LOG_EVIDENCE||'out/logging-20261024/browser');
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [lang,width]of [['en',1440],['nl',1440],['en',320],['nl',320]]){
  const page=await browser.newPage({viewport:{width,height:1000},acceptDownloads:true}),errors=[],requests=[];
  let settings={syslog_enabled:false,server:'',port:514,syslog_level:3,web_level:3,mark_interval_s:0,syslog_esp:true,syslog_ems:true},failSave=false,logReads=0,boot=123,latest=2;const cursors=[];
  let loopIntervals={schema:1,samples:42,sampled_at_ms:70000,last_ms:12,maximum_ms:1750,intervals_ge_100_ms:3,intervals_ge_500_ms:2,intervals_ge_1000_ms:1,window_ms:10000,window_samples:30,window_maximum_ms:750};
  let rows=[{sequence:1,uptime_ms:1000,level:3,source:'esp',feature:'App',message:'ready'},
    {sequence:2,uptime_ms:2000,level:2,source:'ems',feature:'EMS',message:'<img src="https://foreign.test/x"> fault'}];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   requests.push({path:p,method:req.method(),csrf:req.headers()['x-openthermostat-csrf'],origin:url.origin});
   if(url.origin!=='http://opth.test')return route.abort();
   const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/status/logs'){
    ++logReads;const after=Number(url.searchParams.get('after')||0);cursors.push(after);
    latest=Math.max(latest,...rows.map(r=>r.sequence));
    return json({boot,latest,loop_intervals:loopIntervals,oldest:rows[0]?.sequence||0,retained:rows.length,overwritten:4,truncated:1,redacted:2,syslog_dropped:3,syslog_sent:5,contention_dropped:0,previous_boot:{reset_reason:4,wifi_lost_restarts:0,bluetooth_silent_restarts:0,network_dead_restarts:3,previous:{uptime_s:600,minimum_free_heap_bytes:40000,loop_stack_minimum_bytes:2000,last_request:'/status',loop_phase:'idle',supervisor_restart:'network_dead'}},runtime:{free_internal_bytes:90000,minimum_free_internal_bytes:60000,largest_internal_block_bytes:40000,atomics_in_psram:2,stack_minimum_bytes:{loop:1200},nvs:null},records:rows.filter(r=>r.sequence>after).slice(0,8)});
   }
   if(p==='/logs/clear'){assert.equal(req.method(),'POST');rows=[];return json({});}
   if(p==='/config/logging'){
    if(req.method()==='POST'){
     if(failSave)return route.fulfill({status:503,body:'unconfirmed'});
     settings=req.postDataJSON();
    }
    return json(settings);
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.evaluate(()=>loadNativePage('system_log'));
  await page.locator('#log-save:enabled').waitFor();
  assert.equal(await page.locator('#log-source').inputValue(),'esp');
  await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent.includes('ready'));
  assert(!(await page.locator('#log-lines').innerText()).includes('fault'));
  await page.locator('#log-source').selectOption('all');
  await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent.includes('fault'));
  assert.equal(await page.locator('#log-lines img').count(),0);
  assert.match(await page.locator('#log-counters').innerText(),lang==='nl'?/Overschreven: 4/:/Overwritten: 4/);
  await page.locator('#system-log details').evaluate(element=>element.open=true);
  assert.match(await page.locator('#log-loop-timing').textContent(),lang==='nl'?/Langste interval sinds opstarten: 1750 ms/:/Longest interval since boot: 1750 ms/);
  assert.match(await page.locator('#log-loop-timing').textContent(),/750 ms/);
  // network_dead restarts back off too: the series number is shown, and an atomic in PSRAM is a reportable fault.
  assert.match(await page.locator('#log-previous-boot').textContent(),lang==='nl'?/herstart 3 op rij/:/restart 3 in a row/);
  assert.match(await page.locator('[data-log-atomics-warning]').textContent(),lang==='nl'?/^Interne controle: 2 variabelen in extern RAM/:/^Internal check: 2 variables in external RAM/);
  assert.equal(requests.filter(r=>r.path.includes('performance')).length,0);
  // The view filter never saves settings or changes collection/cursors.
  const writesBeforeFilter=requests.filter(r=>r.method==='POST').length;
  await page.locator('#log-source').selectOption('ems');
  assert((await page.locator('#log-lines').innerText()).includes('fault'));
  assert(!(await page.locator('#log-lines').innerText()).includes('[App]'));
  await page.locator('#log-source').selectOption('esp');
  assert((await page.locator('#log-lines').innerText()).includes('ready'));
  assert(!(await page.locator('#log-lines').innerText()).includes('fault'));
  await page.locator('#log-source').selectOption('all');
  assert.equal(requests.filter(r=>r.method==='POST').length,writesBeforeFilter);
  // A valid prefix followed by a malformed row must consume no cursor.
  rows.push({sequence:3,uptime_ms:3000,level:3,feature:'App',message:'valid prefix'},
    {sequence:4,uptime_ms:4000,level:9,feature:'App',message:'corrected suffix'});
  await page.waitForFunction(()=>/unavailable|niet beschikbaar/.test(document.querySelector('#log-status')?.textContent));
  assert.match(await page.locator('#log-loop-timing').textContent(),lang==='nl'?/niet beschikbaar/:/unavailable/);
  assert(!(await page.locator('#log-lines').innerText()).includes('valid prefix'));
  const invalidReadCount=logReads;rows[3].level=3;loopIntervals=undefined; // Older firmware remains usable.
  await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent.includes('corrected suffix'));
  assert.equal(cursors[invalidReadCount],2,'malformed batch advanced the incremental cursor');
  assert.equal((await page.locator('#log-lines').innerText()).split('valid prefix').length-1,1);
  assert.match(await page.locator('#log-loop-timing').textContent(),lang==='nl'?/niet beschikbaar/:/unavailable/);
  await page.locator('#log-pause').click();const paused=logReads;
  await page.waitForTimeout(2300);assert.equal(logReads,paused);
  await page.locator('#log-search').fill('EMS');assert(!((await page.locator('#log-lines').innerText()).includes('ready')));
  const downloadPromise=page.waitForEvent('download');await page.locator('#log-download').click();
  const download=await downloadPromise;assert.equal(download.suggestedFilename(),'openthermostat-system-log.txt');
  const exported=fs.readFileSync(await download.path(),'utf8');assert(exported.includes('EMS')&&!exported.includes('[App]'));
  await page.locator('#log-search').fill('');
  await page.locator('#log-enabled').check();await page.locator('#log-server').fill('192.168.1.10');await page.locator('#log-port').fill('5514');
  await page.locator('#log-mark').fill('600');await page.locator('#log-web-level').selectOption('4');
  await page.locator('#log-syslog-esp').uncheck();
  await page.locator('#log-save').click();
  await page.waitForFunction(()=>/saved and verified|opgeslagen en gecontroleerd/.test(document.querySelector('#log-settings-status')?.textContent));
  assert.equal(settings.port,5514);assert.equal(settings.server,'192.168.1.10');assert.equal(settings.web_level,4);
  assert.equal(settings.syslog_esp,false);assert.equal(settings.syslog_ems,true);
  // Both sources can be enabled, independently of the EMS-only web view.
  await page.locator('#log-source').selectOption('ems');
  await page.locator('#log-syslog-esp').check();await page.locator('#log-save').click();
  await page.waitForFunction(()=>/saved and verified|opgeslagen en gecontroleerd/.test(document.querySelector('#log-settings-status')?.textContent));
  assert.equal(settings.syslog_esp,true);assert.equal(settings.syslog_ems,true);
  await page.locator('#log-source').selectOption('all');
  failSave=true;await page.locator('#log-port').fill('5515');await page.locator('#log-save').click();
  await page.waitForFunction(()=>/could not be confirmed|niet bevestigd/.test(document.querySelector('#log-settings-status')?.textContent));
  assert.equal(await page.locator('#log-port').inputValue(),'5515');assert.equal(settings.port,5514);
  assert(await page.locator('#log-save').isDisabled());
  const writesBeforeRetry=requests.filter(r=>r.path==='/config/logging'&&r.method==='POST').length;
  await page.evaluate(()=>document.querySelector('#log-settings').requestSubmit());
  assert.equal(requests.filter(r=>r.path==='/config/logging'&&r.method==='POST').length,writesBeforeRetry);
  page.once('dialog',dialog=>dialog.accept());await page.locator('#log-clear').click();await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent==='');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,lang+'-'+width+'.png'),fullPage:true});
  if(lang==='en'&&width===1440){
   ++boot;latest=1;rows=[{sequence:1,uptime_ms:100,level:3,feature:'App',message:'after restart'}];
  }
  await page.locator('#log-pause').click();
  if(lang==='en'&&width===1440)await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent.includes('after restart'));
  else await page.waitForTimeout(100);
  const readsBeforeLeave=logReads;await page.evaluate(()=>mainScreen());await page.waitForTimeout(2300);assert.equal(logReads,readsBeforeLeave);
  assert(requests.filter(r=>r.method==='POST').every(r=>['/config/logging','/logs/clear'].includes(r.path)&&r.csrf==='a'.repeat(64)));
  assert(!requests.some(r=>r.origin!=='http://opth.test'));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',pause_filter_download:true,save_readback_failure_draft:true,uncertain_save_no_replay:true,atomic_incremental_batches:true,no_background_poll_after_navigation:true,no_control_writes:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'BROWSER.json'),JSON.stringify({result:'PASS',scope:'Real web assets with isolated HTTP fixtures, no live controller',profiles:results},null,2)+'\n');console.log(JSON.stringify({result:'PASS',profiles:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
