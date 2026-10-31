// Diagnostics console on the System log page: real page/auth/language scripts, isolated HTTP fixtures.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(process.env.OPTH_LOG_EVIDENCE||'out/diagnostics-console/browser');
const CSRF='a'.repeat(64);
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [lang,width]of [['en',1440],['nl',1440],['en',320],['nl',320]]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],requests=[],logTimes=[];
  const nl=lang==='nl';
  // 60 history records: more than two pages of 24, read one after another without the 2 s wait.
  const rows=Array.from({length:60},(_,i)=>({sequence:i+1,uptime_ms:1000+i,level:3,source:'esp',feature:'App',message:'line '+(i+1)}));
  let endIdle={status:200,body:{ended:2}};
  const diagnostics={schema:1,uptime_s:3600,memory:{free_internal_bytes:90000,free_psram_bytes:3900000,total_psram_bytes:4194304},
    tasks:{count:21,stack_minimum_bytes:{loop:3692}},nvs:{used_entries:198,free_entries:432,total_entries:630,namespaces:9},
    mqtt:{connected:true,stalled_disconnects:0},sessions:[{age_s:60,idle_s:0,expires_in_s:1800,current:true}],
    restarts:{reset_reason:3},log:{capacity:512,in_psram:true,retained:60}};
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   requests.push({path:p,search:url.search,method:req.method(),csrf:req.headers()['x-openthermostat-csrf'],origin:url.origin});
   if(url.origin!=='http://opth.test')return route.abort();
   const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
   if(p==='/auth/session')return json({authenticated:true,csrf:CSRF});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/config/logging')return json({syslog_enabled:false,server:'',port:514,syslog_level:3,web_level:3,mark_interval_s:0,syslog_esp:true,syslog_ems:false});
   if(p==='/status/logs'){
    const tail=url.searchParams.get('tail');
    if(tail!==null){assert(!url.searchParams.has('after'));return json({boot:1,latest:60,records:rows.slice(-Number(tail)),more:false});}
    logTimes.push(Date.now());
    const after=Number(url.searchParams.get('after')||0),page_=rows.filter(r=>r.sequence>after).slice(0,24);
    return json({boot:1,latest:60,records:page_,more:page_.length===24&&page_[23].sequence<60});
   }
   if(p==='/status/diagnostics'){
    const section=url.searchParams.get('section');
    if(!section)return json(diagnostics);
    assert(Object.hasOwn(diagnostics,section),'only known sections are requested: '+section);
    return json({schema:1,uptime_s:3600,[section]:diagnostics[section]});
   }
   if(p==='/status/version')return json({version:'v0.1.0-e32v2-beta.21'});
   if(p==='/diagnostics/sessions/end-idle'){assert.equal(req.method(),'POST');return json(endIdle.body,endIdle.status);}
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.evaluate(()=>loadNativePage('system_log'));
  // The whole 60-record history arrives in three reads; the second follows the first at once.
  await page.waitForFunction(()=>document.querySelector('#log-lines')?.textContent.includes('line 60'));
  assert(logTimes.length>=3);
  assert(logTimes[1]-logTimes[0]<2000,'a full page with more records is followed without the 2 s wait');
  assert.equal(requests.filter(r=>r.path==='/status/logs'&&r.search==='?after=24').length,1);
  assert.equal(requests.filter(r=>r.path==='/status/logs'&&r.search==='?after=48').length,1);
  // Console traffic only: the log view keeps polling /status/logs?after=… in the background.
  const consoleRequests=()=>requests.filter(r=>!(r.path==='/status/logs'&&r.search.startsWith('?after='))).length;
  const output_=page.locator('#diag-output'),run=async command=>{
   await page.locator('#diag-command').fill(command);await page.locator('#diag-run').click();
  };
  assert.equal(await page.locator('#diag-console h2').innerText(),nl?'Diagnoseconsole':'Diagnostics console');
  // help lists every command locally, without a request.
  const before=consoleRequests();await run('help');
  await page.waitForFunction(()=>document.querySelector('#diag-output')?.textContent.includes('boiler-profile'));
  for(const name of ['status','memory','tasks','nvs','mqtt','sessions','restarts','bluetooth','rooms','log'])assert((await output_.innerText()).includes(name),name);
  assert.match(await output_.innerText(),nl?/De laatste N logregels/:/The last N log lines/);
  assert.equal(consoleRequests(),before,'help reads nothing');
  // A known section is one GET of the whitelisted endpoint.
  await run('memory');
  await page.waitForFunction(()=>document.querySelector('#diag-output')?.textContent.includes('free_psram_bytes'));
  assert.equal(requests.filter(r=>r.path==='/status/diagnostics'&&r.search==='?section=memory').length,1);
  await run('  STATUS ');
  await page.waitForFunction(()=>document.querySelector('#diag-output')?.textContent.includes('"in_psram": true'));
  // Unknown commands, arguments and bad log sizes are refused before any request.
  for(const bad of ['reboot','memory now','nvs erase','log 500','log -1','log x','rm -rf /','log 2 3']){
   const count=consoleRequests();await run(bad);
   await page.waitForFunction(()=>/Unknown command|Onbekend commando|from 1 to 100|van 1 tot 100/.test(document.querySelector('#diag-output')?.textContent));
   assert.equal(consoleRequests(),count,bad+' sent a request');
   await page.evaluate(()=>{document.querySelector('#diag-output').textContent='';});
  }
  await run('log 3');
  await page.waitForFunction(()=>document.querySelector('#diag-output')?.textContent.includes('line 60'));
  assert.equal(requests.filter(r=>r.path==='/status/logs'&&r.search==='?tail=3').length,1);
  assert.deepEqual((await output_.innerText()).split('\n').map(l=>l.replace(/^.*\] /,'')),['line 58','line 59','line 60']);
  // Copy needs a secure context; here it says so instead of failing silently.
  await page.locator('#diag-copy').click();
  await page.waitForFunction(()=>/Copy failed|Kopiëren mislukt|Output copied|Uitvoer gekopieerd/.test(document.querySelector('#diag-action-status')?.textContent));
  // End idle sessions: cancelled sends nothing; confirmed is one POST with the CSRF proof.
  const posts=()=>requests.filter(r=>r.method==='POST');
  page.once('dialog',d=>d.dismiss());await page.locator('#diag-end-idle').click();
  await page.locator('#diag-end-idle:enabled').waitFor();assert.equal(posts().length,0);
  page.once('dialog',d=>d.accept());await page.locator('#diag-end-idle').click();
  await page.waitForFunction(()=>/ended: 2|beëindigd: 2/.test(document.querySelector('#diag-action-status')?.textContent));
  assert.equal(posts().length,1);assert.equal(posts()[0].path,'/diagnostics/sessions/end-idle');assert.equal(posts()[0].csrf,CSRF);
  endIdle={status:429,body:{error:'try_again_later'}};
  await page.locator('#diag-end-idle:enabled').waitFor();page.once('dialog',d=>d.accept());await page.locator('#diag-end-idle').click();
  await page.waitForFunction(()=>/few seconds|paar seconden/.test(document.querySelector('#diag-action-status')?.textContent));
  endIdle={status:409,body:{error:'settings_write_active'}};
  await page.locator('#diag-end-idle:enabled').waitFor();page.once('dialog',d=>d.accept());await page.locator('#diag-end-idle').click();
  await page.waitForFunction(()=>/firmware update is in progress|firmware-update/.test(document.querySelector('#diag-action-status')?.textContent));
  assert.equal(posts().length,3,'every answer came from exactly one request; none replayed');
  // Restart is the System menu's confirmed restart; cancelling sends nothing.
  assert(await page.locator('#diag-restart').isVisible());
  page.once('dialog',d=>d.dismiss());await page.locator('#diag-restart').click();
  await page.locator('#diag-restart:enabled').waitFor();
  assert.equal(requests.filter(r=>r.path==='/updates/reboot').length,0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  await page.screenshot({path:path.join(output,lang+'-'+width+'.png'),fullPage:true});
  assert(posts().every(r=>r.path==='/diagnostics/sessions/end-idle'&&r.csrf===CSRF));
  assert(!requests.some(r=>r.origin!=='http://opth.test'));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'BROWSER.json'),JSON.stringify({result:'PASS',scope:'Diagnostics console with isolated HTTP fixtures, no live controller',profiles:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',profiles:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
