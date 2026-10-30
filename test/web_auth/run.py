"""Exercise the exact REST login, session-status, password-change and logout
handlers with simulated HTTP/device boundaries.

No actual network, credentials, device operations or timing claims. The
password store is a fake here; test/onboarding/firmware.cpp runs DeviceAccess.
"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[2];source=(root/'src/REST.h').read_text();start=source.index('\tvoid login() {');method=source[start:source.index('\n\tvoid logout()',start)]
logout_start=source.index('\tvoid logout() {');logout=source[logout_start:source.index('\n#endif',logout_start)]
cjson=root/'.pio/libdeps/native/cJSON'
pre=r'''
#include "control/WebAuthSession.h"
#include "control/WebPassword.h"
#include <cassert>
#include <string>
#include <vector>
#include <utility>
#include <iostream>
using namespace heating;
struct String:std::string {using std::string::string;String(const std::string& s):std::string(s){};};
struct Server {
 std::vector<std::pair<String,String>> fields;std::string plain;int status=0;std::string body,retryAfter;
 int args(){return fields.size();}String argName(int i){return fields[i].first;}
 String arg(const char* key){if(std::string_view(key)=="plain")return String(plain);for(auto& f:fields)if(f.first==key)return f.second;return {};}
 String header(const char*){return "application/x-www-form-urlencoded";}
 template<class A,class B> void sendHeader(const A& name,const B& value){if(std::string_view(name)=="Retry-After")retryAfter=value;}
 void send(int code,const char*,const char* value){status=code;body=value;}
 void send(int code){status=code;body.clear();}
};
struct Device {
 std::string password="secret";bool factory=true,failStore=false;unsigned stores=0;
 bool verifyPassword(std::string_view p) const {return p==password;}
 bool defaultPassword() const {return factory;}
 bool storePassword(std::string_view p){++stores;if(failStore||control::WebPassword::checkNew(p)!=control::WebPassword::Length::ok)return false;password=std::string(p);factory=false;return true;}
} deviceAccess;
namespace heating::update {bool blocked=false;bool mutationBlocked(std::string_view path){assert(path=="/ota"||path=="/boiler/settings/write");return blocked;}}
struct Controller {bool active=false;unsigned settingsSyncs=0;std::string observe;uint64_t remainingSeen=999;bool boilerTestActive(){return active;}bool settingsWriting=false;bool boilerSettingsActive(){return settingsWriting;}void boilerSettingsSynchronize(const control::WebAuthSession& sessions,uint64_t now,bool){++settingsSyncs;remainingSeen=sessions.remainingMs(observe,now);}};
struct Fixture {
 Server server_;Controller controller_;control::WebAuthSession sessions_;unsigned entropy=0;bool failEntropy=false;String cookie;
 uint64_t nowMs=200;uint64_t networkNow(){return nowMs;}String requestToken(){return cookie;}
 bool randomToken(std::array<char,65>& t){if(failEntropy)return false;t.fill(entropy++%2?'b':'a');t[64]=0;return true;}
'''
post=r'''
};
std::string token(char c){return std::string(64,c);}
void fill(Fixture& f){f.controller_.observe=token('0');for(int i=0;i<4;++i)assert(f.sessions_.issue(token('0'+2*i),token('1'+2*i),100));}
void request(Fixture& f,bool recovery=true,const char* password="secret"){
 f.server_.fields={{"username","admin"},{"password",password}};if(recovery)f.server_.fields.push_back({"recover_sessions","1"});f.login();
}
void preserved(Fixture& f){assert(f.controller_.settingsSyncs==0);for(int i=0;i<4;++i)assert(f.sessions_.find(token('0'+2*i),201));}
// The caller holds session '0' (csrf '1'); three other browsers/HA hold 2, 4, 6.
void change(Fixture& f,const std::string& body){f.cookie=token('0');f.server_.plain=body;f.changePassword();}
std::string pair(const std::string& current,const std::string& next){return "{\"current\":\""+current+"\",\"new\":\""+next+"\"}";}
void unchanged(Fixture& f){assert(deviceAccess.password=="secret"&&deviceAccess.factory);preserved(f);}
void resetDevice(){deviceAccess=Device{};update::blocked=false;}
int main(){
 {Fixture f;fill(f);request(f,false);assert(f.server_.status==429);preserved(f);}
 {Fixture f;fill(f);request(f,true,"wrong");assert(f.server_.status==401);preserved(f);}
 {Fixture f;fill(f);for(int i=0;i<5;++i)request(f,true,"wrong");request(f);assert(f.server_.status==429);preserved(f);}
 {Fixture f;fill(f);f.controller_.active=true;request(f);assert(f.server_.status==409);preserved(f);}
 {Fixture f;fill(f);update::blocked=true;request(f);assert(f.server_.status==409);preserved(f);update::blocked=false;}
 // A full table evicts one session idle for 2 min, but never while a settings write depends on one.
 {Fixture f;fill(f);f.nowMs=100+120000;request(f,false);assert(f.server_.status==200);unsigned kept=0;for(int i=0;i<4;++i)kept+=f.sessions_.find(token('0'+2*i),f.nowMs)!=nullptr;assert(kept==3);}
 {Fixture f;fill(f);f.nowMs=100+120000;f.controller_.settingsWriting=true;request(f,false);assert(f.server_.status==429);for(int i=0;i<4;++i)assert(f.sessions_.find(token('0'+2*i),f.nowMs));}
 {Fixture f;fill(f);f.nowMs=100+120000;f.controller_.active=true;request(f,false);assert(f.server_.status==429);for(int i=0;i<4;++i)assert(f.sessions_.find(token('0'+2*i),f.nowMs));}
 {Fixture f;fill(f);f.failEntropy=true;request(f);assert(f.server_.status==503);preserved(f);}
 {Fixture f;fill(f);f.server_.fields={{"username","admin"},{"password","secret"},{"recover_sessions","false"}};f.login();assert(f.server_.status==400);preserved(f);}
 {Fixture f;fill(f);f.server_.fields={{"username","admin"},{"password","secret"},{"recover_sessions","1"},{"recover_sessions","1"}};f.login();assert(f.server_.status==400);preserved(f);}
 {Fixture f;fill(f);request(f);assert(f.server_.status==200);assert(f.controller_.settingsSyncs==1);assert(f.controller_.remainingSeen==0);for(int i=0;i<4;++i)assert(!f.sessions_.find(token('0'+2*i),201));assert(f.sessions_.csrf(token('a'),token('b'),201));}
 {Fixture f;fill(f);f.cookie=token('0');request(f,false);assert(f.server_.status==200);assert(f.controller_.settingsSyncs==1);assert(f.controller_.remainingSeen==0);assert(!f.sessions_.find(token('0'),201));}
 {Fixture f;f.cookie=token('a');f.controller_.observe=token('a');assert(f.sessions_.issue(token('a'),token('b'),100));f.logout();assert(f.server_.status==200);assert(f.controller_.settingsSyncs==1);assert(f.controller_.remainingSeen==0);assert(!f.sessions_.find(token('a'),201));}
 // GET /auth/session: exact JSON with the factory-password flag.
 {Fixture f;fill(f);f.cookie=token('0');f.sessionStatus();assert(f.server_.status==200);
  const auto expected=std::string("{\"authenticated\":true,\"csrf\":\"")+token('1')+"\",\"expires_in\":"+std::to_string(f.sessions_.remainingMs(token('0'),200)/1000)+",\"default_password\":true}";
  assert(f.server_.body==expected);deviceAccess.factory=false;f.sessionStatus();assert(f.server_.body.find(",\"default_password\":false}")!=std::string::npos);resetDevice();
  f.cookie=token('z');f.sessionStatus();assert(f.server_.status==401&&f.server_.body=="{\"error\":\"authentication_required\"}");}
 // POST /auth/password success: 204 without body, caller stays, everyone else signs in again.
 {Fixture f;fill(f);change(f,pair("secret","correct horse"));assert(f.server_.status==204&&f.server_.body.empty());
  assert(deviceAccess.password=="correct horse"&&!deviceAccess.factory);assert(f.sessions_.find(token('0'),201)&&f.sessions_.csrf(token('0'),token('1'),201));
  for(int i=1;i<4;++i){assert(!f.sessions_.find(token('0'+2*i),201));}assert(f.controller_.settingsSyncs==1);
  request(f,false,"secret");assert(f.server_.status==401);request(f,false,"correct horse");assert(f.server_.status==200);resetDevice();}
 // Length limits count characters: 8..64; 64 two-byte characters still fit the sign-in form.
 {Fixture f;fill(f);change(f,pair("secret","1234567"));assert(f.server_.status==400&&f.server_.body=="{\"error\":\"password_too_short\"}");unchanged(f);
  change(f,pair("secret",std::string(65,'x')));assert(f.server_.status==400&&f.server_.body=="{\"error\":\"password_too_long\"}");unchanged(f);
  std::string accents;for(int i=0;i<64;++i)accents+="\xc3\xa9";change(f,pair("secret",accents));assert(f.server_.status==204);
  f.server_.fields={{"username","admin"},{"password",String(accents)}};f.login();assert(f.server_.status==200);resetDevice();}
 {Fixture f;fill(f);change(f,pair("secret",std::string(64,'x')));assert(f.server_.status==204);resetDevice();}
 {Fixture f;fill(f);change(f,pair("secret","12345678"));assert(f.server_.status==204);resetDevice();}
 // Wrong current password: 403, counted with failed sign-ins; the shared limit then answers 429.
 {Fixture f;fill(f);change(f,pair("admin","correct horse"));assert(f.server_.status==403&&f.server_.body=="{\"error\":\"password_wrong\"}");unchanged(f);
  for(int i=0;i<4;++i){change(f,pair("nope","correct horse"));}change(f,pair("secret","correct horse"));
  assert(f.server_.status==429&&f.server_.body=="{\"error\":\"try_again_later\"}"&&f.server_.retryAfter=="30");unchanged(f);
  request(f,false);assert(f.server_.status==429);unchanged(f);resetDevice();}
 // Failed sign-ins also block a password change.
 {Fixture f;fill(f);for(int i=0;i<5;++i){request(f,false,"wrong");}change(f,pair("secret","correct horse"));assert(f.server_.status==429);unchanged(f);resetDevice();}
 // Malformed bodies never reach the password check.
 {Fixture f;fill(f);for(const std::string& body:{std::string(""),std::string("{}"),std::string("[]"),std::string("not json"),std::string("{\"current\":\"secret\"}"),
   std::string("{\"current\":\"secret\",\"new\":12345678}"),std::string("{\"current\":\"secret\",\"new\":\"correct horse\",\"x\":1}"),
   std::string("{\"current\":\"secret\",\"current\":\"secret\",\"new\":\"correct horse\"}"),std::string("{\"current\":\"secret\",\"new\":\"correct\\u0000horse\"}"),
   std::string("{\"current\":\"secret\",\"new\":\"correct horse\"} trailing")}){
   change(f,body);assert(f.server_.status==400&&f.server_.body=="{\"error\":\"invalid_password_request\"}");}
  unchanged(f);assert(deviceAccess.stores==0);resetDevice();}
 {Fixture f;fill(f);for(int i=0;i<6;++i){change(f,"{}");}change(f,pair("secret","correct horse"));assert(f.server_.status==204);resetDevice();}
 // An update in progress or a storage failure keeps the old password and every session.
 {Fixture f;fill(f);update::blocked=true;change(f,pair("secret","correct horse"));assert(f.server_.status==409&&f.server_.body=="{\"error\":\"password_change_busy\"}");update::blocked=false;unchanged(f);assert(deviceAccess.stores==0);resetDevice();}
 {Fixture f;fill(f);deviceAccess.failStore=true;change(f,pair("secret","correct horse"));assert(f.server_.status==503&&f.server_.body=="{\"error\":\"password_storage_failed\"}");deviceAccess.failStore=false;unchanged(f);resetDevice();}
 std::cout<<"PASS 25 actual login/session/password/logout handler scenarios: full capacity, idle eviction (not during a test or settings write), credentials, cooldown, active trial/update, entropy failure, malformed recovery, explicit success, session JSON, password change limits/shape/rate limit/invalidation/busy/storage\n";
}
'''
p=root/'out/session-recovery';p.mkdir(exist_ok=True);cpp=p/'login-handler.cpp';cpp.write_text(pre+method+logout+post)
subprocess.run(['gcc','-std=c11','-c',str(cjson/'cJSON.c'),'-o',str(p/'cjson.o')],check=True)
subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+str(root/'src'),'-I'+str(cjson),str(cpp),str(p/'cjson.o'),'-o',str(p/'login-handler')],check=True)
subprocess.run([str(p/'login-handler')],check=True)
