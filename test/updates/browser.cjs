// Shipped updater UI in Chromium; HTTP fixture is explicit, not real OTA proof.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../../data/html');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});let count=0;
 const pass=name=>{++count;console.log('PASS '+name);};let page,sim,errors;
 async function scene(){
  if(page)await page.close();page=await browser.newPage({viewport:{width:390,height:844}});errors=[];
  sim={installed:'v0.1.0-e32v2-alpha.2',phase:'idle',error:'',busy:false,can_check:true,boot_pending:false,reboot_required:false,rollback_available:false,received:0,total:0,releases:[],posts:[],accept:true,drop:false,confirm:true};
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>sim.confirm?d.accept():d.dismiss());
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(p==='/updates/status'){if(sim.drop)return route.abort();return route.fulfill({contentType:'application/json',json:sim});}
   if(p.startsWith('/updates/')){sim.posts.push({path:p,body:req.postDataJSON()});return route.fulfill({status:sim.accept?202:409,body:sim.accept?'Queued':'Injected rejection'});}
   if(p==='/')return route.fulfill({contentType:'text/html',body:'<script src="/deps/jquery.min.js.gz"></script><script>const hostName="";function mainScreen(){}</script>'+fs.readFileSync(path.join(assets,'update.html'),'utf8')});
   if(p==='/deps/jquery.min.js.gz')return route.fulfill({contentType:'text/javascript',body:zlib.gunzipSync(fs.readFileSync(path.join(assets,p)))});
   return route.fulfill({status:404,body:'not found'});
  });
  await page.goto('http://opth.test/');await page.waitForFunction(()=>document.getElementById('installedVersion').textContent.startsWith('v'));
 }
 try {
  await scene();assert.equal(await page.isDisabled('#installRelease'),true);assert.equal(sim.posts.length,0);pass('page shows installed version without checking or installing automatically');
  await page.click('#checkReleases');assert.equal(sim.posts[0].path,'/updates/check');pass('explicit check queues only the authenticated local device action');
  sim.phase='checked';sim.releases=[{tag:'v0.1.0-e32v2-alpha.3',prerelease:true},{tag:sim.installed,prerelease:true}];
  await page.waitForFunction(()=>document.getElementById('releaseChoice').options.length===2);assert.match(await page.textContent('#releaseChoice'),/testrelease/);pass('release choices visibly label prereleases and the installed version');
  sim.confirm=false;await page.click('#installRelease');assert.equal(sim.posts.length,1);pass('cancel install confirmation does not mutate the device');
  sim.confirm=true;await page.click('#installRelease');assert.deepEqual(sim.posts[1],{path:'/updates/install',body:{tag:'v0.1.0-e32v2-alpha.3'}});pass('install submits only the selected release tag, never arbitrary URL or factory file');
  sim.phase='downloading';sim.busy=true;sim.received=500;sim.total=1000;await page.waitForFunction(()=>document.getElementById('releaseProgress').value===500);
  assert.equal(await page.isDisabled('#checkReleases'),true);assert.equal(await page.isDisabled('#installRelease'),true);assert.equal(await page.isVisible('#restartRelease'),false);pass('observed byte progress fences duplicate work and premature restart');
  sim.phase='error';sim.busy=false;sim.error='Checksum mismatch';await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('Checksum mismatch'));assert.equal(await page.isVisible('#restartRelease'),false);pass('checksum failure cannot display an update-success/reboot action');
  sim.error='';sim.phase='ready_to_reboot';sim.reboot_required=true;sim.received=1000;await page.waitForFunction(()=>!document.getElementById('restartRelease').hidden);assert.equal(await page.isDisabled('#installRelease'),true);
  await page.click('#restartRelease');assert.equal(sim.posts.at(-1).path,'/updates/reboot');pass('verified update requires explicit restart and blocks further flashing');
  sim.reboot_required=false;sim.phase='idle';sim.installed='v0.1.0-e32v2-alpha.3';await page.waitForFunction(()=>document.getElementById('installedVersion').textContent.endsWith('alpha.3'));
  assert.equal(await page.isDisabled('#installRelease'),true);pass('reconnect reads installed version and will not silently reinstall it');
  sim.drop=true;await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('niet bereikbaar'));sim.drop=false;await page.waitForFunction(()=>!document.getElementById('releaseStatus').textContent.includes('niet bereikbaar'));pass('network interruption is unconfirmed, then status polling recovers');
  sim.rollback_available=true;await page.waitForFunction(()=>!document.getElementById('rollbackRelease').hidden);sim.confirm=false;let before=sim.posts.length;await page.click('#rollbackRelease');assert.equal(sim.posts.length,before);
  sim.confirm=true;await page.click('#rollbackRelease');assert.equal(sim.posts.at(-1).path,'/updates/rollback');pass('previous firmware recovery is separate, explicit and cancellable');
  await scene();sim.can_check=false;sim.boot_pending=true;await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('opstart'));assert.equal(await page.isDisabled('#checkReleases'),true);pass('setup/no-time/boot-verification state explains why updating is unavailable');
  sim.can_check=true;sim.boot_pending=false;sim.phase='ready_to_reboot';sim.reboot_required=true;sim.accept=false;
  await page.waitForFunction(()=>!document.getElementById('restartRelease').hidden);await page.click('#restartRelease');await page.waitForFunction(()=>document.getElementById('releaseStatus').textContent.includes('niet bevestigd'));assert.ok(!(await page.textContent('#releaseStatus')).includes('Herstart aangevraagd'));pass('rejected restart never claims the device is rebooting');
  assert.deepEqual(errors,[]);console.log(count+' updater browser scenarios passed (simulated HTTP; no hardware OTA proof)');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
