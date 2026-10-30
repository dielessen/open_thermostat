// Actual root/About HTML and scripts with simulated HTTP; no device requests.
// The default password admin is shown as a clear prompt (Overview and About),
// disappears after a change, and the password never appears in the page text.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(__dirname,'../out/about-password-browser');
const words={
 en:{notice:/This E32 still uses the default password admin\. Choose your own below/,overview:/still uses the default password/,changed:/Password changed\./},
 nl:{notice:/Deze E32 gebruikt nog het standaardwachtwoord admin\. Kies hieronder een eigen wachtwoord/,overview:/gebruikt nog het standaardwachtwoord/,changed:/Wachtwoord gewijzigd\./}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const [lang,width,defaultPassword] of [['en',1280,true],['nl',390,true],['en',1280,false]]){
  const page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(8000);const errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  if(lang==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64),default_password:defaultPassword})});
   if(p==='/auth/password'){posts.push(req.postDataJSON());return route.fulfill({contentType:'application/json',body:'{"ok":true}'});}
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(req.method()!=='GET')return route.fulfill({status:405,body:''});
   const f=path.join(assets,p==='/'?'index.html':p);if(!f.startsWith(assets+'/')||!fs.existsSync(f))return route.fulfill({status:404,body:''});let body=fs.readFileSync(f);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor({state:'attached'});
  const banner=page.locator('[data-dashboard-key="default-password"]');
  if(defaultPassword){await banner.waitFor();assert.match(await banner.innerText(),words[lang].overview);}
  await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();
  const notice=page.locator('#pw-default');
  if(!defaultPassword){
   await page.locator('#about-password-card').waitFor();assert.equal(await notice.isVisible(),false);
   assert.equal(await banner.count(),0);assert.equal(await page.locator('#pw-current').getAttribute('placeholder'),null);
   assert.deepEqual(errors,[]);results.push({lang,width,default_password:false,result:'PASS'});await page.close();continue;
  }
  await notice.waitFor();assert.match(await notice.innerText(),words[lang].notice);
  assert.equal(await page.locator('#pw-current').getAttribute('placeholder'),'admin');
  await page.fill('#pw-current','admin');await page.fill('#pw-new','correct horse 42');await page.fill('#pw-repeat','correct horse 42');
  await page.locator('#password-form button[type=submit]').click();
  await page.waitForFunction(()=>document.getElementById('pw-default').hidden===true);
  assert.match(await page.locator('#pw-status').innerText(),words[lang].changed);
  assert.deepEqual(posts,[{current:'admin',new:'correct horse 42'}]);
  assert.equal(await page.locator('#pw-current').getAttribute('placeholder'),'');
  assert(!(await page.locator('body').innerText()).includes('correct horse 42'),'the new password is never shown');
  assert.equal(await page.evaluate(()=>window.otDefaultPassword),false);
  assert.deepEqual(errors,[]);results.push({lang,width,default_password:true,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
