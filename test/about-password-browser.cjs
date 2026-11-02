// Actual root/Settings/About/login HTML and scripts with simulated HTTP; no device requests.
// The default password admin is a blocking step: every page leads to "Choose your own
// password" on the sign-in page (the E32 refuses every change until then), after signing
// in too; the new password never appears in the page text. With your own password About
// only points to Settings; old #about links still find the password.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(__dirname,'../out/about-password-browser');
const words={
 en:{title:'Choose your own password',notice:/still uses the default password admin\. Choose your own password first/,mismatch:'The two passwords are not the same.',short:'Use at least 8 characters.',moved:/under System → Password/},
 nl:{title:'Kies je eigen wachtwoord',notice:/gebruikt nog het standaardwachtwoord admin\. Kies eerst je eigen wachtwoord/,mismatch:'De twee wachtwoorden zijn niet gelijk.',short:'Gebruik minstens 8 tekens.',moved:/onder Systeem → Wachtwoord/}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [lang,width,defaultPassword] of [['en',1280,true],['nl',390,true],['en',1280,false]]){
  const page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(8000);const errors=[],posts=[],csrfs=[];let factory=defaultPassword,signedIn=!defaultPassword||lang!=='nl';
  page.on('pageerror',e=>errors.push(e.message));
  if(lang==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(p==='/auth/session')return signedIn?route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64),default_password:factory})})
    :route.fulfill({status:401,contentType:'application/json',body:'{"error":"authentication_required"}'});
   if(p==='/auth/login'){signedIn=true;return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,default_password:factory})});}
   if(p==='/auth/password'){posts.push(req.postDataJSON());csrfs.push(req.headers()['x-openthermostat-csrf']);factory=false;return route.fulfill({status:204,body:''});}
   if(p==='/login')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(assets,'login.html'))});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(req.method()!=='GET')return route.fulfill({status:405,body:''});
   const f=path.join(assets,p==='/'?'index.html':p);if(!f.startsWith(assets+'/')||!fs.existsSync(f))return route.fulfill({status:404,body:''});let body=fs.readFileSync(f);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  const card=page.locator('#settings-password'),notice=page.locator('#pw-default'),chip=page.locator('#pw-default-chip');
  const banner=page.locator('[data-dashboard-key="default-password"]');
  if(!defaultPassword){
   await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor({state:'attached'});
   // About points to the password on the Settings page.
   await page.evaluate(()=>loadNativePage('about'));const moved=page.locator('#about-password-moved');await moved.waitFor();
   assert.match(await moved.innerText(),words[lang].moved);await moved.locator('a').click();
   await card.waitFor();assert.equal(await page.evaluate(()=>location.hash),'#password');
   assert.equal(await card.evaluate(d=>d.open),true,'#password opens the card');
   assert.equal(await notice.isVisible(),false);assert.equal(await chip.isVisible(),false);
   assert.equal(await banner.count(),0);assert.equal(await page.locator('#pw-current').getAttribute('placeholder'),'');
   // Settings opened from the menu: the card stays closed while your own password is in use.
   await page.evaluate(()=>loadNativePage('network'));await card.waitFor();assert.equal(await card.evaluate(d=>d.open),false);
   assert.deepEqual(errors,[]);results.push({lang,width,default_password:false,result:'PASS'});await page.close();continue;
  }
  const step=page.locator('#choose-password');
  if(signedIn){
   // Already signed in with admin: any page leads straight to the step.
   await page.goto('http://opth.test/');await page.waitForURL('http://opth.test/login#password');
  }else{
   // Signing in with admin: the step follows at once, instead of the Overview.
   await page.goto('http://opth.test/login');await page.fill('#password','admin');await page.locator('#submit').click();
  }
  await step.waitFor();assert.equal(await page.locator('#sign-in').isVisible(),false);
  assert.equal((await step.locator('h2').innerText()).trim(),words[lang].title);
  assert.match(await step.innerText(),words[lang].notice);
  await page.fill('#new-password','short');await page.fill('#repeat-password','short');await page.locator('#save-password').click();
  assert.equal(await page.locator('#password-message').innerText(),words[lang].short);
  await page.fill('#new-password','correct horse 42');await page.fill('#repeat-password','correct horse 43');await page.locator('#save-password').click();
  assert.equal(await page.locator('#password-message').innerText(),words[lang].mismatch);assert.deepEqual(posts,[]);
  await page.fill('#repeat-password','correct horse 42');await page.locator('#save-password').click();
  await page.waitForURL('http://opth.test/');await page.locator('#auth-sign-out').waitFor({state:'attached'});
  assert.deepEqual(posts,[{current:'admin',new:'correct horse 42'}]);assert.deepEqual(csrfs,['a'.repeat(64)]);
  assert(!(await page.locator('body').innerText()).includes('correct horse 42'),'the new password is never shown');
  assert.equal(await banner.count(),0,'no reminder once the password is your own');
  assert.deepEqual(errors,[]);results.push({lang,width,default_password:true,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
