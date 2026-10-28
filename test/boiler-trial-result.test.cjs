const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../data/html/boiler_test.html'),'utf8');
const policy=source.split('// BEGIN trial result policy:')[1].split('\n').slice(1).join('\n').split('// END trial result policy')[0];
const context=vm.createContext({});vm.runInContext(policy,context);
const progress=()=>({schema:1,requested_temperature_reported:true,heating_operation_reported:true,duration_completed:true,requested_duration_s:600,end_reason:'heat_deadline'});
const completed=()=>({phase:'completed',reported_stop_confirmed:true,zero_frames:2,positive_frames:601,zero_only:false,progress:progress()});
test('passed requires a completed full heat trial and every server observation',()=>{
 assert.equal(context.trialOutcome(completed()),'passed');
 // Classic boilers keep the read-back setpoint at 0: CH operation decides.
 {const status=completed();status.progress.requested_temperature_reported=false;assert.equal(context.trialOutcome(status),'passed');}
 for(const key of ['heating_operation_reported']){
  const status=completed();status.progress[key]=false;assert.equal(context.trialOutcome(status),'unconfirmed',key);
 }
 for(const phase of ['idle','baseline','ready','heating','stopping'])assert.equal(context.trialOutcome({...completed(),phase}),'running');
 for(const phase of ['fault','closed'])assert.equal(context.trialOutcome({...completed(),phase}),'failed');
});
test('a stopped test without a positive command or without heat feedback never passes heating',()=>{
 const status=completed();status.positive_frames=0;assert.equal(context.trialOutcome(status),'not_heated');
 status.zero_only=true;assert.equal(context.trialOutcome(status),'zero_passed');
 status.reported_stop_confirmed=false;assert.equal(context.trialOutcome(status),'unconfirmed');
});
test('old firmware, missing or malformed progress remains unknown',()=>{
 for(const value of [undefined,null,{}, {...progress(),schema:2},{...progress(),requested_temperature_reported:'true'},
  {...progress(),heating_operation_reported:1},{...progress(),duration_completed:undefined},
  {...progress(),requested_duration_s:-1},{...progress(),requested_duration_s:601},{...progress(),requested_duration_s:1.5},
  {...progress(),end_reason:null}])assert.equal(context.trialOutcome({...completed(),progress:value}),'unconfirmed');
 assert.equal(context.trialOutcome(null),'unavailable');
});
test('early stop or missing duration completion is reported as partial, including after reopen',()=>{
 for(const patch of [{duration_completed:false},{end_reason:'explicit_stop'},{end_reason:'operator_lease_expired'},
  {end_reason:'proving_conditions_lost'},{requested_duration_s:0}]){
  const status=completed();Object.assign(status.progress,patch);assert.equal(context.trialOutcome(status),'partial');
  assert.equal(context.trialOutcome(JSON.parse(JSON.stringify(status))),'partial');
 }
});
test('missing, unsafe or fabricated counters cannot count as transmission or reported stop',()=>{
 for(const key of ['positive_frames','zero_frames'])for(const value of [undefined,null,-1,1.5,'1',true,NaN,Infinity,Number.MAX_SAFE_INTEGER+1]){
  const status=completed();status[key]=value;assert.equal(context.trialOutcome(status),'unconfirmed',key+': '+value);
 }
 assert.equal(context.trialOutcome({...completed(),zero_frames:0}),'unconfirmed');
 assert.equal(context.trialOutcome({...completed(),reported_stop_confirmed:false}),'unconfirmed');
});
