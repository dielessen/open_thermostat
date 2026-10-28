// Shipped updater UI in Chromium; HTTP fixture is explicit, not real OTA proof.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../../data/html');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});let count=0;
 const pass=name=>{++count;console.log('PASS '+name);};let page,sim,errors;
 async function scene(language='nl',width=390){
  if(page)await page.close();page=await browser.newPage({viewport:{width,height:844}});errors=[];
  sim={installed:'v0.1.0-e32v2-alpha.2',phase:'idle',error:'',busy:false,can_check:true,boot_pending:false,reboot_required:false,reboot_scheduled:false,selected:'',rollback_available:false,received:0,total:0,releases:[],posts:[],accept:true,drop:false,confirm:true,dialogs:0,uploadStatus:200,navigations:0};
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{++sim.dialogs;return sim.confirm?d.accept():d.dismiss();});
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(p==='/updates/status'){
    sim.statusReads=(sim.statusReads||0)+1;
    if(sim.malformed)return route.fulfill({contentType:'application/json',json:{installed:'incomplete'}});
    if(sim.holdStatus){sim.holdStatus=false;const snapshot=JSON.parse(JSON.stringify(sim));sim.releaseStatus=()=>route.fulfill({contentType:'application/json',json:snapshot});return;}
    if(sim.drop)return route.abort();return route.fulfill({contentType:'application/json',json:sim});}
   if(p.startsWith('/updates/')){sim.posts.push({path:p,body:req.postDataJSON()});
    if(sim.holdCommand){sim.holdCommand=false;sim.releaseCommand=()=>route.fulfill({status:202,body:'Queued'});return;}
    return route.fulfill({status:sim.accept?202:409,body:sim.accept?'Queued':'Injected rejection'});}
   if(p==='/ota'||p==='/otafs'){sim.posts.push({path:p});return route.fulfill({status:sim.uploadStatus,body:sim.uploadStatus===200?'success':'Injected upload failure'});}
   if(p==='/'){++sim.navigations;return route.fulfill({contentType:'text/html',body:'<meta charset="utf-8"><script src="/ui-messages.js"></script><script src="/ui-language.js"></script><script src="/deps/jquery.min.js.gz"></script><script>const hostName="";function mainScreen(){}</script>'+fs.readFileSync(path.join(assets,'update.html'),'utf8')});}
   if(['/ui-language.js','/ui-messages.js'].includes(p))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(assets,p))});
   if(p==='/deps/jquery.min.js.gz')return route.fulfill({contentType:'text/javascript',body:zlib.gunzipSync(fs.readFileSync(path.join(assets,p)))});
   return route.fulfill({status:404,body:'not found'});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>document.getElementById('installedVersion').textContent.startsWith('v'));
 }
 try {
  await scene();assert.equal(await page.isDisabled('#installRelease'),true);assert.equal(sim.posts.length,0);pass('page shows installed version without checking or installing automatically');
  assert.match(await page.textContent('#updateCheckpoint'),/geen opgeslagen/);
  await page.click('#updateDiagnostics summary');
  sim.last_saved_checkpoint={attempt:7,from_version:'v0.1.0-e32v2-alpha.24',target_version:'v0.1.0-e32v2-alpha.26',stage:'boot_slot_selected',received:2565504,total:2565504,http_status:200};sim.reset_reason=3;
  await page.waitForFunction(()=>document.getElementById('updateCheckpoint').textContent.includes('poging: 7'));
  assert.match(await page.textContent('#updateCheckpoint'),/installatie niet bevestigd/);
  assert.equal(await page.locator('#updateDiagnostics').evaluate(el=>el.open),true);
  assert.equal(sim.posts.length,0);assert.equal(sim.dialogs,0);
  pass('saved checkpoint is read-only, translated, preserves expanded details and never claims installation success');
  sim.checkpoint_save_failed=true;
  await page.waitForFunction(()=>document.getElementById('updateCheckpoint').textContent.includes('kon niet worden opgeslagen'));
  assert.match(await page.textContent('#updateCheckpoint'),/oudere opgeslagen/);
  sim.checkpoint_save_failed=false;sim.last_saved_checkpoint=null;
  await page.waitForFunction(()=>document.getElementById('updateCheckpoint').textContent.includes('geen opgeslagen'));
  assert.equal(await page.locator('#updateDiagnostics').evaluate(el=>el.open),true);
  pass('failed or absent persistence is explicit and cannot retain an old rendered checkpoint');
  await page.click('#checkReleases');assert.equal(sim.posts[0].path,'/updates/check');pass('explicit check queues only the authenticated local device action');
  sim.phase='checked';sim.releases=[{tag:'v0.1.0-e32v2-alpha.3',prerelease:true},{tag:sim.installed,prerelease:true}];
  await page.waitForFunction(()=>document.getElementById('releaseChoice').options.length===2);assert.match(await page.textContent('#releaseChoice'),/testrelease/);pass('release choices visibly label prereleases and the installed version');
  sim.confirm=false;await page.click('#installRelease');assert.equal(sim.posts.length,1);pass('cancel install confirmation does not mutate the device');
  sim.confirm=true;await page.click('#installRelease');assert.deepEqual(sim.posts[1],{path:'/updates/install',body:{tag:'v0.1.0-e32v2-alpha.3'}});pass('install submits only the selected release tag, never arbitrary URL or factory file');
  sim.phase='downloading';sim.busy=true;sim.received=500;sim.total=1000;await page.waitForFunction(()=>document.getElementById('releaseProgress').value===500);
  assert.equal(await page.isDisabled('#checkReleases'),true);assert.equal(await page.isDisabled('#installRelease'),true);assert.equal(await page.isVisible('#restartRelease'),false);pass('observed byte progress fences duplicate work and premature restart');
  sim.phase='error';sim.busy=false;sim.error='Checksum mismatch';await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('Checksum mismatch'));assert.equal(await page.isVisible('#restartRelease'),false);pass('checksum failure cannot display an update-success/reboot action');
  sim.error='';sim.phase='ready_to_reboot';sim.reboot_required=true;sim.received=1000;await page.waitForFunction(()=>!document.getElementById('restartRelease').hidden);assert.equal(await page.isDisabled('#installRelease'),true);
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/updates/reboot')),page.click('#restartRelease')]);assert.equal(sim.posts.at(-1).path,'/updates/reboot');pass('older firmware without automatic-restart status retains manual restart fallback');
  sim.reboot_required=false;sim.phase='idle';sim.installed='v0.1.0-e32v2-alpha.3';await page.waitForFunction(()=>document.getElementById('installedVersion')?.textContent.endsWith('alpha.3'));
  assert.equal(await page.isDisabled('#installRelease'),true);pass('reconnect reads installed version and will not silently reinstall it');
  sim.drop=true;await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('niet bereikbaar'));assert.equal(await page.isDisabled('#checkReleases'),true);assert.equal(await page.isDisabled('#rollbackRelease'),true);sim.drop=false;await page.waitForFunction(()=>!document.getElementById('releaseStatus').textContent.includes('niet bereikbaar'));pass('network interruption is unconfirmed, then status polling recovers');
  sim.rollback_available=true;await page.waitForFunction(()=>!document.getElementById('rollbackRelease').hidden);sim.confirm=false;let before=sim.posts.length;await page.click('#rollbackRelease');assert.equal(sim.posts.length,before);
  sim.confirm=true;await page.click('#rollbackRelease');assert.equal(sim.posts.at(-1).path,'/updates/rollback');pass('previous firmware recovery is separate, explicit and cancellable');
  await scene();sim.can_check=false;sim.boot_pending=true;await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('opstart'));assert.equal(await page.isDisabled('#checkReleases'),true);pass('setup/no-time/boot-verification state explains why updating is unavailable');
  sim.can_check=true;sim.boot_pending=false;sim.phase='ready_to_reboot';sim.reboot_required=true;sim.accept=false;
  await page.waitForFunction(()=>!document.getElementById('restartRelease').hidden);await page.click('#restartRelease');await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('niet bevestigd'));assert.ok(!(await page.textContent('#releaseStatus')).includes('Herstart aangevraagd'));pass('rejected restart never claims the device is rebooting');
  await scene();sim.phase='ready_to_reboot';sim.reboot_required=true;sim.reboot_scheduled=true;sim.busy=true;sim.selected='v0.1.0-e32v2-alpha.4';
  await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('herstart automatisch'));
  assert.equal(await page.isVisible('#restartRelease'),false);assert.equal(await page.isDisabled('#installRelease'),true);assert.equal(sim.posts.length,0);assert.equal(sim.dialogs,0);
  pass('device-scheduled restart is visible without confirmation or browser reboot command');
  sim.drop=true;await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('Herstart bezig'));
  sim.drop=false;sim.installed='v0.1.0-e32v2-alpha.4';sim.reboot_required=false;sim.reboot_scheduled=false;sim.busy=false;sim.phase='idle';
  await page.waitForFunction(()=>document.getElementById('installedVersion')?.textContent.endsWith('alpha.4'));
  assert.equal(sim.navigations,2);assert.equal(sim.posts.length,0);pass('post-reboot status verifies target version and reloads matching shipped UI once');
  await scene();await page.setInputFiles('#FirmwarePath',{name:'firmware.bin',mimeType:'application/octet-stream',buffer:Buffer.from('test image fixture')});
  await page.click('#FirmwareSubmit');await page.waitForFunction(()=>document.getElementById('progressbar').textContent.includes('automatisch'));
  assert.equal(sim.dialogs,0);assert.deepEqual(sim.posts,[{path:'/ota'}]);assert.equal(await page.isDisabled('#FirmwareSubmit'),true);pass('successful manual app upload needs no second confirmation or reboot POST');
  sim.installed='v0.1.0-e32v2-alpha.4';await page.waitForFunction(()=>document.getElementById('installedVersion')?.textContent.endsWith('alpha.4'));assert.equal(sim.navigations,2);pass('manual app reconnect also refreshes the new UI after version readback');
  await scene();sim.uploadStatus=500;await page.setInputFiles('#FirmwarePath',{name:'firmware.bin',mimeType:'application/octet-stream',buffer:Buffer.from('bad fixture')});
  await page.click('#FirmwareSubmit');await page.waitForFunction(()=>!document.getElementById('FirmwareSubmit').disabled);
  assert.equal(sim.dialogs,1);assert.deepEqual(sim.posts,[{path:'/ota'}]);assert.ok(!(await page.textContent('#progressbar')).includes('automatisch'));pass('rejected app upload cannot claim automatic restart or issue a reboot command');
  await scene();sim.confirm=false;await page.selectOption('#FirmwareType','fs');await page.setInputFiles('#FirmwarePath',{name:'spiffs.bin',mimeType:'application/octet-stream',buffer:Buffer.from('filesystem fixture')});
  await page.click('#FirmwareSubmit');await page.waitForFunction(()=>!document.getElementById('FirmwareSubmit').disabled);
  assert.equal(sim.dialogs,1);assert.deepEqual(sim.posts,[{path:'/otafs'}]);pass('filesystem upload remains separate and does not acquire app automatic-restart semantics');
  await scene('en',320);await page.click('#updateDiagnostics summary');
  assert.match(await page.textContent('#updateCheckpoint'),/No saved update checkpoint/);
  sim.last_saved_checkpoint={attempt:1,from_version:sim.installed,target_version:'v0.1.0-e32v2-alpha.27',stage:'boot_slot_selected',received:1024,total:1024,http_status:200};
  await page.waitForFunction(()=>document.getElementById('updateCheckpoint').textContent.includes('Saved attempt: 1'));
  assert.match(await page.textContent('#updateCheckpoint'),/installation not confirmed/);
  assert.equal(sim.posts.length,0);assert.equal(sim.dialogs,0);
  pass('English update diagnostics use the same read-only semantics on a narrow screen');
  for(const language of ['nl','en']) {
   await scene(language,320);await page.click('#updateDiagnostics summary');
   sim.phase='error';sim.operation='check';sim.error='Could not connect to GitHub.';
   const descriptions={connection:language==='nl'?'Kan geen verbinding maken':'Could not connect',
    tls:language==='nl'?'beveiligde verbinding':'secure connection',
    http:language==='nl'?'HTTP-fout':'HTTP error',
    transfer:language==='nl'?'onderbroken of onvolledig':'interrupted or incomplete'};
   for(const kind of ['connection','tls','http','transfer']) {
    sim.download_error={kind,host:'github.com',http_status:kind==='http'?403:kind==='transfer'?200:0,client_code:kind==='http'?0:-1,secure_client_code:kind==='tls'?-9984:0};
    await page.waitForFunction(text=>document.getElementById('releaseStatus').textContent.includes(text),descriptions[kind]);
    assert.match(await page.textContent('#releaseStatus'),language==='nl'?/Updatecontrole mislukt:/ : /Update check failed:/);
    assert.equal(await page.isVisible('#updateDownloadError'),true);
    assert.match(await page.textContent('#updateDownloadError'),/github\.com/);
    if(kind==='tls')assert.match(await page.textContent('#updateDownloadError'),/-9984/);
    assert.equal(await page.textContent('#installedVersion'),'v0.1.0-e32v2-alpha.2');
    assert.equal(await page.isVisible('#restartRelease'),false);
    assert.equal(sim.posts.length,0);
   }
   sim.operation='install';
   await page.waitForFunction(text=>document.getElementById('releaseStatus').textContent.includes(text),language==='nl'?'Firmware-installatie mislukt:':'Firmware installation failed:');
   sim.error='';sim.phase='checked';sim.operation='check';sim.download_error=null;
   await page.waitForFunction(()=>document.getElementById('updateDownloadError').hidden);
   assert.equal(await page.textContent('#updateDownloadError'),'');
   sim.error='invalid diagnostics';sim.download_error={kind:'connection',host:'github.com/secret?token=value',http_status:0,client_code:-1,secure_client_code:0};
   await page.waitForFunction(()=>document.getElementById('checkReleases').disabled);
   assert.ok(!(await page.textContent('#updateDownloadError')).includes('secret'));
   assert.equal(sim.posts.length,0);assert.deepEqual(errors,[]);
   pass(language+' distinguishes failed catalog check from installation and hides invalid/stale transport diagnostics without commands');
  }
  for(const language of ['nl','en']) {
   await scene(language,320);await page.click('#updateDiagnostics summary');
   const stages=[['before_hash_verification',language==='nl'?'Vóór controle van de firmwarechecksum':'Before firmware checksum verification'],
    ['before_image_validation',language==='nl'?'Vóór de native imagevalidatie':'Before native image validation'],
    ['before_flash_readback',language==='nl'?'Vóór het onafhankelijk teruglezen van flash':'Before independent flash readback'],
    ['before_boot_slot_selection',language==='nl'?'nog niet gekozen':'not yet selected']];
   for(const [stage,text] of stages) {
    sim.last_saved_checkpoint={attempt:2,from_version:sim.installed,target_version:'v0.1.0-e32v2-alpha.34',stage,received:1024,total:1024,http_status:200};
    try {await page.waitForFunction(text=>document.getElementById('updateCheckpoint').textContent.includes(text),text);}
    catch(error){throw new Error(language+' '+stage+': '+await page.textContent('#updateCheckpoint')+'; pageerrors='+errors.join(','),{cause:error});}
    assert.equal(await page.locator('#updateDiagnostics').evaluate(el=>el.open),true);
    assert.equal(sim.posts.length,0);assert.equal(sim.dialogs,0);assert.deepEqual(errors,[]);
   }
   pass(language+' detailed saved verification stages remain read-only and distinguish preselection');
  }
  for(const language of ['nl','en']) {
   await scene(language,320);sim.malformed=true;
   await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes(document.cookie.includes('ot_ui_lang=nl')?'niet bereikbaar':'unreachable'));
   assert.equal(await page.isDisabled('#checkReleases'),true);assert.equal(await page.isDisabled('#installRelease'),true);
   sim.malformed=false;await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
   assert.equal(sim.posts.length,0);pass(language+' incomplete status blocks commands until a valid fresh status arrives');
  }
  await scene('en');sim.holdStatus=true;await page.waitForTimeout(1200);assert.equal(typeof sim.releaseStatus,'function');
  const releaseOldStatus=sim.releaseStatus;sim.holdStatus=true;
  await page.click('#checkReleases');assert.equal(await page.isDisabled('#checkReleases'),true);
  await releaseOldStatus();await page.waitForTimeout(1200);assert.equal(await page.isDisabled('#checkReleases'),true);
  assert.notEqual(sim.releaseStatus,releaseOldStatus);await sim.releaseStatus();
  await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
  assert.equal(sim.posts.length,1);pass('pre-command delayed status cannot unlock commands or cause a replay');
  await scene('en');sim.reboot_required=true;sim.reboot_scheduled=true;sim.selected='v0.1.0-e32v2-alpha.3';sim.busy=true;sim.phase='ready_to_reboot';
  await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('automatically'));
  sim.reboot_required=false;sim.busy=false;sim.installed=sim.selected;sim.phase='idle';sim.holdStatus=true;
  await page.waitForTimeout(1200);assert.equal(typeof sim.releaseStatus,'function');
  const navigations=sim.navigations;await page.evaluate(()=>document.getElementById('githubUpdate').remove());
  await sim.releaseStatus();await page.waitForTimeout(180);
  assert.equal(sim.navigations,navigations);assert.equal(sim.posts.length,0);
  pass('late post-reboot status cannot reload a page after leaving the updater');
  for(const language of ['nl','en']) {
   await scene(language);
   await page.evaluate(()=>{
    const original=window.fetch, schedule=window.setTimeout;
    window.setTimeout=(callback,delay,...args)=>schedule(callback,delay===10000?50:delay,...args);
    window.fetch=async (input,options)=>{
     if(input==='/updates/status'&&!window.bodyStalled){
      window.bodyStalled=true;
      return new Response(new ReadableStream({start(controller){
       options.signal.addEventListener('abort',()=>{window.bodyAborted=true;controller.error(new DOMException('Aborted','AbortError'));},{once:true});
      }}),{headers:{'Content-Type':'application/json'}});
     }
     return original(input,options);
    };
   });
   await page.waitForFunction(()=>window.bodyAborted===true,{},{timeout:4000});
   assert.equal(await page.isDisabled('#checkReleases'),true);
   await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
   assert.equal(sim.posts.length,0);assert.deepEqual(errors,[]);
   pass(language+' stalled status body times out, fences commands and recovers without replay');
  }
  async function visibility(value){await page.evaluate(value=>{Object.defineProperty(document,'visibilityState',{configurable:true,value});document.dispatchEvent(new Event('visibilitychange'));},value);}
  for(const language of ['nl','en']) {
   await scene(language);await visibility('hidden');const reads=sim.statusReads;
   await page.waitForTimeout(1250);assert.equal(sim.statusReads,reads);assert.equal(await page.isDisabled('#checkReleases'),true);
   await page.evaluate(()=>document.getElementById('checkReleases').onclick());assert.equal(sim.posts.length,0);
   sim.holdStatus=true;await visibility('visible');await page.waitForTimeout(150);
   assert.equal(sim.statusReads,reads+1);assert.equal(await page.isDisabled('#checkReleases'),true);
   await sim.releaseStatus();await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
   pass(language+' hidden updater pauses polling and requires a fresh status before resumed commands');
  }
  await scene('en');
  await page.evaluate(()=>{
   const original=window.fetch;window.stallNext=true;
   window.fetch=(input,options)=>{
    if(input==='/updates/status'&&window.stallNext){
     window.stallNext=false;window.bodyStarted=true;
     return Promise.resolve(new Response(new ReadableStream({start(controller){
      options.signal.addEventListener('abort',()=>{window.bodyAborted=true;controller.error(new DOMException('Aborted','AbortError'));},{once:true});
     }}),{headers:{'Content-Type':'application/json'}}));
    }
    return original(input,options);
   };
  });
  await page.waitForFunction(()=>window.bodyStarted===true);await visibility('hidden');
  await page.waitForFunction(()=>window.bodyAborted===true);const pausedReads=sim.statusReads;
  await page.waitForTimeout(1250);assert.equal(sim.statusReads,pausedReads);
  await visibility('visible');await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
  pass('hiding an updater aborts a stalled status body and resumes one read without a command');
  await page.evaluate(()=>{window.stallNext=true;window.bodyStarted=false;window.bodyAborted=false;});
  await page.waitForFunction(()=>window.bodyStarted===true);
  await page.evaluate(()=>document.getElementById('githubUpdate').remove());
  await page.waitForFunction(()=>window.bodyAborted===true&&window.UpdatesPage===null);
  const removedReads=sim.statusReads;await page.waitForTimeout(1250);
  assert.equal(sim.statusReads,removedReads);assert.equal(sim.posts.length,0);
  pass('leaving an updater releases its timer, visibility listener and in-flight status read');
  await scene('en');sim.holdCommand=true;
  await page.evaluate(()=>{const original=window.fetch;window.fetch=(input,options)=>{
   if(options?.method==='POST')options.signal.addEventListener('abort',()=>{window.commandAborted=true;},{once:true});
   return original(input,options);
  };});
  await page.click('#checkReleases');await visibility('hidden');await page.waitForTimeout(150);
  assert.equal(sim.posts.length,1);assert.equal(await page.evaluate(()=>!!window.commandAborted),false);
  await sim.releaseCommand();await page.waitForTimeout(150);
  const hiddenReads=sim.statusReads;await page.waitForTimeout(1100);assert.equal(sim.statusReads,hiddenReads);
  await visibility('visible');await page.waitForFunction(()=>!document.getElementById('checkReleases').disabled);
  assert.equal(sim.posts.length,1);assert.deepEqual(errors,[]);
  pass('visibility changes never abort or replay an explicitly submitted update command');
  // Browser release lookup: GitHub API (simulated) gives the digest; only the
  // exact downloaded firmware.bin of that release may be uploaded.
  await scene('nl');
  const crypto=require('node:crypto'),tag='v0.1.0-e32v2-beta.13';
  const firmware=Buffer.alloc(1200000,0x5a);Buffer.from('OT_E32V2_OTA_V1:'+tag+':'+'0'.repeat(40)+':'+'1'.repeat(64)+':END').copy(firmware,4096);
  const digest='sha256:'+crypto.createHash('sha256').update(firmware).digest('hex');
  let apiCalls=0;
  await page.route('https://api.github.com/**',route=>{++apiCalls;return route.fulfill({contentType:'application/json',headers:{'access-control-allow-origin':'*'},
   json:[{tag_name:'ha-v0.4.0b7',draft:false,assets:[]},{tag_name:tag,draft:false,assets:[{name:'firmware.bin',size:firmware.length,digest,browser_download_url:'https://github.com/x/y/releases/download/'+tag+'/firmware.bin'}]}]});});
  assert.equal(apiCalls,0,'opening the page never contacts GitHub');
  await page.click('#githubReleaseCheck');await page.waitForFunction(t=>document.getElementById('githubReleaseInfo').textContent.includes(t),tag);
  const wrong=Buffer.from(firmware);wrong[100]^=1;
  await page.setInputFiles('#FirmwarePath',{name:'firmware.bin',mimeType:'application/octet-stream',buffer:wrong});
  await page.waitForFunction(()=>/geblokkeerd/.test(document.getElementById('githubReleaseFile').textContent));
  const postsBefore=sim.posts.length,dialogs=sim.dialogs;await page.click("#FirmwareSubmit");
  await page.waitForFunction(d=>document.getElementById('FirmwareSubmit').disabled===false,dialogs);
  assert.equal(sim.posts.length,postsBefore,"a mismatching file is never uploaded");assert.equal(sim.dialogs,dialogs+1);
  await page.setInputFiles('#FirmwarePath',{name:'firmware.bin',mimeType:'application/octet-stream',buffer:firmware});
  await page.waitForFunction(()=>/Gecontroleerd/.test(document.getElementById('githubReleaseFile').textContent));
  assert.equal(apiCalls,1);assert.deepEqual(errors,[]);
  pass('GitHub release lookup verifies SHA-256, size and version marker before allowing an upload');
  console.log(count+' updater browser scenarios passed (simulated HTTP; no hardware OTA proof)');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
