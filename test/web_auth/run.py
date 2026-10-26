"""Exercise the exact REST login handler with simulated HTTP/device boundaries.

No actual network, credentials, device operations or timing claims.
"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[2];source=(root/'src/REST.h').read_text();start=source.index('\tvoid login() {');method=source[start:source.index('\n\tvoid sessionStatus()',start)]
pre=r'''
#include "control/WebAuthSession.h"
#include <cassert>
#include <string>
#include <vector>
#include <utility>
#include <iostream>
using namespace heating;
struct String:std::string {using std::string::string;String(const std::string& s):std::string(s){};};
struct Server {
 std::vector<std::pair<String,String>> fields;int status=0;std::string body;
 int args(){return fields.size();}String argName(int i){return fields[i].first;}
 String arg(const char* key){for(auto& f:fields)if(f.first==key)return f.second;return {};}
 String header(const char*){return "application/x-www-form-urlencoded";}
 template<class A,class B> void sendHeader(const A&,const B&){}
 void send(int code,const char*,const char* value){status=code;body=value;}
};
struct Device {std::string_view password(){return "secret";}} deviceAccess;
namespace heating::update {bool blocked=false;bool mutationBlocked(std::string_view path){assert(path=="/ota");return blocked;}}
struct Controller {bool active=false;bool boilerTestActive(){return active;}};
struct Fixture {
 Server server_;Controller controller_;control::WebAuthSession sessions_;unsigned entropy=0;bool failEntropy=false;
 uint64_t networkNow(){return 200;}String requestToken(){return {};}
 bool randomToken(std::array<char,65>& t){if(failEntropy)return false;t.fill(entropy++%2?'b':'a');t[64]=0;return true;}
'''
post=r'''
};
std::string token(char c){return std::string(64,c);}
void fill(Fixture& f){for(int i=0;i<4;++i)assert(f.sessions_.issue(token('0'+2*i),token('1'+2*i),100));}
void request(Fixture& f,bool recovery=true,const char* password="secret"){
 f.server_.fields={{"username","admin"},{"password",password}};if(recovery)f.server_.fields.push_back({"recover_sessions","1"});f.login();
}
void preserved(Fixture& f){for(int i=0;i<4;++i)assert(f.sessions_.find(token('0'+2*i),201));}
int main(){
 {Fixture f;fill(f);request(f,false);assert(f.server_.status==429);preserved(f);}
 {Fixture f;fill(f);request(f,true,"wrong");assert(f.server_.status==401);preserved(f);}
 {Fixture f;fill(f);for(int i=0;i<5;++i)request(f,true,"wrong");request(f);assert(f.server_.status==429);preserved(f);}
 {Fixture f;fill(f);f.controller_.active=true;request(f);assert(f.server_.status==409);preserved(f);}
 {Fixture f;fill(f);update::blocked=true;request(f);assert(f.server_.status==409);preserved(f);update::blocked=false;}
 {Fixture f;fill(f);f.failEntropy=true;request(f);assert(f.server_.status==503);preserved(f);}
 {Fixture f;fill(f);f.server_.fields={{"username","admin"},{"password","secret"},{"recover_sessions","false"}};f.login();assert(f.server_.status==400);preserved(f);}
 {Fixture f;fill(f);f.server_.fields={{"username","admin"},{"password","secret"},{"recover_sessions","1"},{"recover_sessions","1"}};f.login();assert(f.server_.status==400);preserved(f);}
 {Fixture f;fill(f);request(f);assert(f.server_.status==200);for(int i=0;i<4;++i)assert(!f.sessions_.find(token('0'+2*i),201));assert(f.sessions_.csrf(token('a'),token('b'),201));}
 std::cout<<"PASS 9 actual login handler scenarios: full capacity, credentials, cooldown, active trial/update, entropy failure, malformed recovery, explicit success\n";
}
'''
p=root/'out/session-recovery';p.mkdir(exist_ok=True);cpp=p/'login-handler.cpp';cpp.write_text(pre+method+post)
subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+str(root/'src'),str(cpp),'-o',str(p/'login-handler')],check=True)
subprocess.run([str(p/'login-handler')],check=True)
