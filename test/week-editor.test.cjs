// The shared week planner's pure parts: program text identical to the HA options flow, levels, templates.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'data/html/week-editor.js'),'utf8');
const context={window:{}};vm.createContext(context);vm.runInContext(source,context);
const W=context.window.OTWeekEditor,plain=x=>JSON.parse(JSON.stringify(x));
const week=[...Array(5)].map(()=>[[390,2050],[1350,1800]]).concat([[[480,2050],[1380,1800]],[[480,2050],[1380,1800]]]);
test('HA and E32 ship the same planner file',()=>{
 assert.equal(fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-editor.js'),'utf8'),source);
 assert(!source.includes('\r'));
});
test('program text matches e32_room_flow.format_program in English and Dutch',()=>{
 // Same fixtures as ha/tests_native/test_e32_room_flow.py::test_program_text_round_trips_and_accepts_dutch_days.
 assert.equal(W.format(week,'en'),'mon-fri: 06:30 20.5; 22:30 18\nsat-sun: 08:00 20.5; 23:00 18');
 assert.equal(W.format(week,'nl'),'ma-vr: 06:30 20,5; 22:30 18\nza-zo: 08:00 20,5; 23:00 18');
 assert.equal(W.format(Array(7).fill([[420,2025]]),'en'),'07:00 20.25');
 assert.equal(W.format([[[420,2000]],[],[[420,2000]],[],[],[[420,2000]],[[420,2000]]],'en'),'mon,wed,sat-sun: 07:00 20');
 assert.equal(W.format(Array(7).fill([]),'en'),'');
});
test('program text parses like e32_room_flow.parse_program, with its errors and line numbers',()=>{
 assert.deepEqual(plain(W.parse('mon-fri: 06:30 20.5; 22:30 18\nsat-sun: 08:00 20.5; 23:00 18',500,3000)),week);
 assert.deepEqual(plain(W.parse('ma-vr: 06:30 20,5, 22:30 18\nza,zo: 08.00 20,5; 23:00 18',500,3000)),week);
 assert.deepEqual(plain(W.parse('Maandag: 7:00 21\n',500,3000)),[[[420,2100]],[],[],[],[],[],[]]);
 assert.deepEqual(plain(W.parse('sun-mon: 07:00 21',500,3000)),[[[420,2100]],[],[],[],[],[],[[420,2100]]],'ranges wrap around the week');
 assert.deepEqual(plain(W.parse('',500,3000)),Array(7).fill([]));
 const error=(text,min=500,max=3000)=>{try{W.parse(text,min,max);}catch(e){return plain(e);}assert.fail('accepted '+text);};
 assert.deepEqual(error('mon: 07:00 21\nfoo: 08:00 20'),{key:'bad',line:2,text:'foo: 08:00 20'});
 assert.equal(error('mon: 07:00 21\nmon: 08:00 20').key,'bad','a day twice');
 assert.equal(error('mon: 24:00 21').key,'bad');assert.equal(error('mon: 07:00 21 x').key,'bad');assert.equal(error('mon: 07:00 21; 07:00 20').key,'bad');
 assert.equal(error('mon: 07:00 26',500,2500).key,'outside');
 assert.equal(error('mon: 01:00 20; 02:00 20; 03:00 20; 04:00 20; 05:00 20; 06:00 20; 07:00 20').key,'many');
 for(const w of [week,Array(7).fill([[0,1650],[390,2050],[510,1800],[1020,2050],[1350,1650]]),[[[60,1700]],[],[],[[1439,2200]],[],[],[]]])
  for(const lang of ['en','nl'])assert.deepEqual(plain(W.parse(W.format(w,lang),500,3000)),w,'round trip '+lang);
});
test('°F at the edge only: shown like the options flow, read back to centi °C',()=>{
 const w=[[[420,2000],[1350,1700]],[],[],[],[],[],[]];
 // e32_room_flow.format_program(w, 'en', '°F') gives the same text (shown: one decimal).
 assert.equal(W.format(w,'en',true),'mon: 07:00 68; 22:30 62.6');assert.equal(W.format(w,'nl',true),'ma: 07:00 68; 22:30 62,6');
 assert.deepEqual(plain(W.parse('mon: 07:00 68; 22:30 62.6',500,3000,true)),w);
 // A whole °F is stored to 0.01 °C, so it shows again as typed.
 assert.deepEqual(plain(W.parse('mon: 07:00 69; 22:30 61',500,3000,true))[0],[[420,2056],[1350,1611]]);
 assert.equal(W.format([[[420,2056],[1350,1611]],[],[],[],[],[],[]],'en',true),'mon: 07:00 69; 22:30 61');
 for(let f=41;f<=95;f++)assert.equal(W.format(plain(W.parse('mon: 07:00 '+f,500,3500,true)),'en',true),'mon: 07:00 '+f,String(f));
 assert.equal((()=>{try{W.parse('mon: 07:00 90',500,3000,true);}catch(e){return e.key;}})(),'outside','limits stay in °C (90 °F = 32.2 °C)');
 assert.equal(W.format(w,'en'),'mon: 07:00 20; 22:30 17','°C stays the default');
});
test('inferred levels (older firmware, the migration) follow the program and stay distinct; templates use them',()=>{
 // "Away" became Eco in beta.23; the inference is unchanged.
 assert.deepEqual(plain(W.infer(week,500,3000)),{comfort:2050,eco:1950,night:1800});
 assert.deepEqual(plain(W.infer([[[390,2050],[510,1700],[1020,2050],[1350,1600]],[],[],[],[],[],[]],500,3000)),{comfort:2050,eco:1700,night:1600});
 assert.deepEqual(plain(W.infer(Array(7).fill([]),500,3000)),{comfort:2000,eco:1800,night:1600});
 assert.deepEqual(plain(W.LEVELS),['comfort','eco','night']);
 const tight=plain(W.infer(Array(7).fill([]),1900,2000));assert.equal(new Set(Object.values(tight)).size,3,JSON.stringify(tight));
 for(const [key,days] of Object.entries(W.TEMPLATES)){
  assert.equal(days.length,7,key);
  const w=days.map(d=>d.map(([m,l])=>[m,{comfort:2050,night:1600,eco:1800}[l]]));
  assert(W.valid(w),key);assert(w.every(d=>d.length&&d.length<=6),key);
  assert.equal(w[6][w[6].length-1][1],1600,key+': the week ends at night, so Monday starts at night');
 }
 assert.equal(W.valid([[[480,2000],[480,1900]],[],[],[],[],[],[]]),false);assert.equal(W.valid([[]]),false);
});
test('stored levels mark every point; equal levels and any order are fine',()=>{
 const levels={comfort:2100,eco:1850,night:1850},w=[[[390,2100],[510,1850],[1020,2100],[1350,1850]],[[390,2100],[1350,1850]],[],[],[],[[480,2050]],[]];
 // The stored digits decide between equal temperatures (Eco and Night are both 18.5 °C here).
 const m=plain(W.marked(w,levels,'1213.13....0.'));
 assert.deepEqual(m[0],[[390,2100,'comfort'],[510,1850,'eco'],[1020,2100,'comfort'],[1350,1850,'night']]);
 assert.deepEqual(m[5],[[480,2050]],'an own temperature has no level');
 assert.equal(W.markText(m),'1213.13....0.');
 // Digits that do not fit the program or the levels are ignored: the first level with the temperature wins.
 for(const bad of ['1213.13....1.','12.13....0.','1213.13....0','1214.13....0.',null,undefined,42])
  assert.equal(W.markText(W.marked(w,levels,bad)),'1212.12....0.',String(bad));
 // Night may be warmer than Comfort.
 assert.equal(W.markText(W.marked([[[420,1900],[1320,2300]],[],[],[],[],[],[]],{comfort:1900,eco:1700,night:2300},'13......')),'13......');
 assert(W.valid(m),'points with a level are valid');assert.equal(W.valid([[[480,2000,'away']],[],[],[],[],[],[]]),false);
});
