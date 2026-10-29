const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),load=require('./helpers/ui-language.cjs');
const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'data/html/ui-messages.js'),'utf8'),context);
// Home's own catalogue, then the page catalogue that index.html loads before the first other page.
const core={...context.window.OT_UI_MESSAGES};vm.runInContext(fs.readFileSync(path.join(root,'data/html/ui-messages-pages.js'),'utf8'),context);
const catalog=context.window.OT_UI_MESSAGES;
function flatten(value,prefix=''){return Object.fromEntries(Object.entries(value).flatMap(([k,v])=>typeof v==='object'?Object.entries(flatten(v,prefix+k+'.')):[[prefix+k,v]]));}
test('HA English fallback and Dutch catalogs have exact key and placeholder parity',()=>{
 const base=path.join(root,'ha/config/custom_components/open_thermostat');
 const en=JSON.parse(fs.readFileSync(path.join(base,'translations/en.json'))),nl=JSON.parse(fs.readFileSync(path.join(base,'translations/nl.json')));
 assert.deepEqual(en,JSON.parse(fs.readFileSync(path.join(base,'strings.json'))));
 const a=flatten(en),b=flatten(nl);assert.deepEqual(Object.keys(a).sort(),Object.keys(b).sort());
 for(const [k,v]of Object.entries(a)){assert.equal(typeof b[k],'string',k);assert(b[k].trim(),k);if(v!=='OpenThermostat')assert.notEqual(b[k],v,k+' must have an actual Dutch translation');assert.deepEqual((v.match(/\{[^}]+\}/g)||[]).sort(),(b[k].match(/\{[^}]+\}/g)||[]).sort(),k);}
});
test('all marked static E32 messages and literal calls have a Dutch catalog entry',()=>{
 for(const file of fs.readdirSync(path.join(root,'data/html')).filter(f=>/\.(?:html|js)$/.test(f)&&!f.startsWith('ui-'))){
  const s=fs.readFileSync(path.join(root,'data/html',file),'utf8');
  for(const m of s.matchAll(/(?:data-i18n(?:-title|-placeholder|-aria-label|-alt)?|data-hint)="([^"]*)"/g)){
   const key=m[1].replace(/&quot;/g,'"').replace(/&#x27;/g,"'").replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');assert(Object.hasOwn(catalog,key),file+': '+key);
  }
  for(const m of s.matchAll(/uiText\(((?:"(?:[^"\\]|\\.)*")|(?:'(?:[^'\\]|\\.)*'))\)/g)){
   const key=vm.runInNewContext(m[1]).trim().replace(/\s+/g,' ');assert(Object.hasOwn(catalog,key),file+': '+key);
  }
 }
});
test('Home, login and setup find their Dutch in ui-messages.js; the page catalogue only adds entries',()=>{
 const pages=context.window.OT_UI_PAGE_MESSAGES;assert(Object.keys(pages).length>0);
 for(const key of Object.keys(pages))assert(!Object.hasOwn(core,key),'ui-messages-pages.js repeats '+key);
 // Shown before ui-messages-pages.js loads (or without index.html): these keys must be in ui-messages.js.
 for(const file of ['index.html','auth-client.js','boiler-data.js','boiler-display.js','device-restart.js','history-chart.js','login.html','login.js','setup.html','setup.js']){
  const s=fs.readFileSync(path.join(root,'data/html',file),'utf8');
  for(const m of s.matchAll(/(?:data-i18n(?:-title|-placeholder|-aria-label|-alt)?|data-hint)="([^"]*)"/g)){
   const key=m[1].replace(/&quot;/g,'"').replace(/&#x27;/g,"'").replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
   assert(Object.hasOwn(core,key)||!Object.hasOwn(catalog,key),file+': move to ui-messages.js: '+key);
  }
  for(const m of s.matchAll(/uiText\(((?:"(?:[^"\\]|\\.)*")|(?:'(?:[^'\\]|\\.)*'))\)/g)){
   const key=vm.runInNewContext(m[1]).trim().replace(/\s+/g,' ');assert(Object.hasOwn(core,key)||!Object.hasOwn(catalog,key),file+': move to ui-messages.js: '+key);
  }
 }
});
test('English defaults, unsupported preference falls back, whitespace and HTML escaping are preserved',()=>{
 const en=load(),nl=load('nl'),other=load('de');
 assert.equal(en.uiText('Boiler test'),'Boiler test');assert.equal(nl.uiText('Boiler test'),'Keteltest');assert.equal(other.uiText('Boiler test'),'Boiler test');
 assert.equal(nl.uiText(' Room '),' Ruimte ');assert.equal(nl.uiText('New English message'),'New English message');
 assert.equal(nl.uiHtml('<p>Settings</p>'),'<p>Instellingen</p>');
 assert.equal(nl.uiHtml('<input value="Settings"><p>Settings</p>'),'<input value="Settings"><p>Instellingen</p>');
 assert.equal(nl.uiText('constructor'),'constructor');
});
