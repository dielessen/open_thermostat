// The settings page's time-zone picker (data/html/network.html): which zone a
// stored POSIX TZ string shows. No browser: the zone table runs in a VM.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.resolve(__dirname,'../data/html/network.html'),'utf8');
const source=html.slice(html.indexOf('\tvar timeZones ='),html.indexOf('\tfunction showTimeZone('));
function picker(browserZone){
 const context={Intl:{DateTimeFormat:()=>({resolvedOptions:()=>({timeZone:browserZone})})}};
 vm.createContext(context);vm.runInContext(source+';this.posixZone=posixZone;',context);
 return context.posixZone;
}
test('the beta.17 default POSIX string shows Europe/Amsterdam, not Other',()=>{
 const beta17='CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00';
 assert.equal(picker('UTC')(beta17),'Europe/Amsterdam');
 assert.equal(picker('Europe/Amsterdam')(beta17),'Europe/Amsterdam');
 assert.equal(picker('Europe/Berlin')(beta17),'Europe/Berlin'); // the same rules: the browser's own zone first
});
test('known strings show their zone and unknown ones Other',()=>{
 const zone=picker('America/Chicago');
 assert.equal(zone('CET-1CEST,M3.5.0,M10.5.0/3'),'Europe/Amsterdam');
 assert.equal(zone('GMT0BST,M3.5.0/1,M10.5.0'),'Europe/London');
 assert.equal(zone('CST6CDT,M3.2.0,M11.1.0'),'America/Chicago');
 assert.equal(zone('<+0545>-5:45'),'custom');
 assert.equal(zone(''),'custom');
});
