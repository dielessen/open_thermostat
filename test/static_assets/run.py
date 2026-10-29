"""Compile the actual E32 authorization/static response branches against HTTP fakes.

Exercises policy ordering and response headers/body, not TCP timing or hardware.
"""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/REST.h").read_text()
start = source.index("\tbool staticAssetRequest()")
authorize = "#ifdef OPENTHERMOSTAT_E32V2\n" + source[start:source.index("\n#ifdef OPENTHERMOSTAT_E32V2\n\tcontrol::WebAuthSession", start)]
start = source.index("\tvoid serveFile(const char *serverPath)")
# The E32 branch is complete and returns before the generic SPIFFS fallback.
serve = source[start:source.index("\n#endif", start)] + "\n#endif\n}\n"
start = source.index("\tstd::pair<bool, const char *>getContentType")
mime = source[start:source.index("\n\tvoid handleOTA", start)]
start=source.index('route("/status/ems/telemetry"')
start=source.index('[this]() {',start)+len('[this]() {')
telemetry='void telemetry() {'+source[start:source.index('\n\t\t});',start)]+'\n}\n'
start=source.index('    diagnostics::ResponseBuffer jsonResponse_')
buffer_member=source[start:source.index('},heap_caps_free};',start)+len('},heap_caps_free};')]+'\n'
start=source.index('\tvoid status() {')
dashboard=source[start:source.index('\n\tvoid version()',start)]
pre = r'''
#define OPENTHERMOSTAT_E32V2
#define DBGLOGFD(...)
#include "control/StaticAssetRoute.h"
#include "control/StaticAssetPolicy.h"
#include "control/WebAuthSession.h"
#include "control/CaptivePortalPolicy.h"
#include "diagnostics/ResponseBuffer.h"
#include <atomic>
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <map>
#include <vector>
using namespace heating;
using namespace std::string_view_literals;
enum {HTTP_GET,HTTP_POST,HTTP_DELETE};
enum HTTPUploadStatus {UPLOAD_FILE_START,UPLOAD_FILE_WRITE,UPLOAD_FILE_END,UPLOAD_FILE_ABORTED}; // WebServer HTTPUpload
struct String:std::string {
 using std::string::string;
 String(const std::string& s):std::string(s){}
 String(unsigned n):std::string(std::to_string(n)){}
 bool endsWith(const char *s)const{return size()>=strlen(s)&&compare(size()-strlen(s),strlen(s),s)==0;}
};
struct IP {String toString()const{return "192.168.4.1";}bool operator==(IP)const{return false;}};
struct {IP softAPIP(){return {};}} WiFi;
bool wifiAPMode=false;
constexpr unsigned MALLOC_CAP_SPIRAM=1,MALLOC_CAP_8BIT=2;
bool refuseBuffer=false;unsigned bufferAllocations=0;
void *heap_caps_malloc(size_t size,unsigned caps){assert(size==65536);assert(caps==3);++bufferAllocations;return refuseBuffer?nullptr:std::malloc(size);}
void heap_caps_free(void *bytes){std::free(bytes);}
struct {bool available=true;bool ready(){return available;}} deviceAccess;
namespace heating::update {bool mutationBlocked(const char*){return false;}std::atomic<bool> httpUploadActive{false};}
namespace heating::embedded {
constexpr unsigned char raw[]="raw UI",packed[]={31,139,8,0,1,2,3};
constexpr char tag[]="\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"";
constexpr char gzipTag[]="\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"";
struct Asset {const char *path;const uint8_t *bytes;size_t size;const char *etag;const uint8_t *gzip;size_t gzipSize;const char *gzipEtag;};
constexpr Asset assets[]={{"/index.html",raw,sizeof(raw)-1,tag,packed,sizeof(packed),gzipTag},
 {"/ui-messages.js",raw,sizeof(raw)-1,tag,packed,sizeof(packed),gzipTag},
 {"/deps/lib.js.gz",packed,sizeof(packed),gzipTag,nullptr,0,nullptr}};
const Asset *find(const char *path){for(auto& a:assets)if(!strcmp(a.path,path))return &a;return nullptr;}
}
struct Server {
 String path="/index.html";int verb=HTTP_GET,status=0;std::string body,type;size_t contentLength=0;
 std::map<String,String> incoming;
 std::vector<std::pair<String,String>> outgoing;
 int method(){return verb;}String uri(){return path;}
 String header(const char *name){return incoming[name];}
 String hostHeader(){return "e32.test";}
 struct Socket {IP localIP(){return {};}};Socket client(){return {};}
 void sendHeader(String name,String value){outgoing.push_back({name,value});}
 void setContentLength(size_t size){contentLength=size;}
 bool cors=true;void enableCORS(bool value){cors=value;}
 void send(int code,const char *mime,const char *data){status=code;type=mime;body=data;}
 void sendView(int code,std::string_view mime,std::string_view data){status=code;type=mime;body=data;}
 std::string response(const char *name){std::string value;for(auto& h:outgoing)if(h.first==name){assert(value.empty());value=h.second;}return value;}
};
struct Controller {
 bool oversized=false,failStream=false;unsigned snapshots=0,statusSnapshots=0;
 bool boilerTestActive(){return false;}bool boilerSettingsActive(){return false;}bool modernMode(){return true;}
 void getEMSTelemetryStatus(std::ostream& out,const char*){++snapshots;if(oversized)out<<"{\"fields\":\""<<std::string(65537,'x')<<"\"}";else out<<"{\"fields\":{}}";}
 void getFullStatus(std::ostream& out){++statusSnapshots;if(oversized)out<<"{\"rooms\":\""<<std::string(65537,'x')<<"\"}";else out<<"{\"rooms\":[],\"controlMode\":\"shadow\",\"ems\":{\"selectedFlowTemperature\":50,\"currentFlowTemperature\":432}}";if(failStream)out.setstate(std::ios::badbit);}
};
struct Fixture {
 Server server_;Controller controller_;control::WebAuthSession sessions_;unsigned listenPort_=80;
 String cookie=std::string(64,'1');uint64_t now=1000;
 Fixture(){assert(sessions_.issue(cookie,std::string(64,'2'),now));}
 uint64_t networkNow(){return now;}String requestToken(){return cookie;}
 void get(const char *path="/index.html"){server_.path=path;if(authorize())serveFile(path);}
'''
post = r'''
};
int main(){
 {Fixture f;f.get();assert(f.server_.status==200);assert(f.server_.body=="raw UI");assert(f.server_.response("Cache-Control")=="private, no-cache");assert(f.server_.response("ETag")==embedded::tag);assert(f.server_.response("Content-Encoding").empty());assert(f.server_.response("Vary")=="Accept-Encoding");}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="gzip";f.get();assert(f.server_.status==200);assert(f.server_.body==std::string((const char*)embedded::packed,sizeof(embedded::packed)));assert(f.server_.response("Content-Encoding")=="gzip");assert(f.server_.response("ETag")==embedded::gzipTag);}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="gzip;q=0,*;q=1";f.get();assert(f.server_.body=="raw UI");}
 {Fixture f;f.server_.incoming["If-None-Match"]=embedded::tag;f.get();assert(f.server_.status==304);assert(f.server_.body.empty());assert(f.server_.contentLength==sizeof(embedded::raw)-1);assert(f.server_.response("ETag")==embedded::tag);assert(f.server_.response("Cache-Control")=="private, no-cache");}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="gzip";f.server_.incoming["If-None-Match"]="W/"+std::string(embedded::gzipTag);f.get();assert(f.server_.status==304);assert(f.server_.body.empty());assert(f.server_.contentLength==sizeof(embedded::packed));}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="gzip";f.server_.incoming["If-None-Match"]=embedded::tag;f.get();assert(f.server_.status==200);}
 {Fixture f;f.cookie="";f.server_.incoming["If-None-Match"]="*";f.get();assert(f.server_.status==303);assert(f.server_.response("Cache-Control")=="no-store");assert(f.server_.response("ETag").empty());}
 {Fixture f;f.now+=control::WebAuthSession::idleTimeoutMs;f.server_.incoming["If-None-Match"]="*";f.get();assert(f.server_.status==303);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.cookie="";f.server_.incoming["If-None-Match"]="*";f.get("/ui-messages.js");assert(f.server_.status==304);}
 {Fixture f;f.server_.path="/status";f.server_.incoming["If-None-Match"]="*";assert(f.authorize());assert(f.server_.response("Cache-Control")=="no-store");assert(f.server_.response("ETag").empty());}
 {Fixture f;f.server_.incoming["Origin"]="http://foreign.test";f.server_.incoming["If-None-Match"]="*";f.get();assert(f.server_.status==403);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.server_.verb=HTTP_POST;f.get();assert(f.server_.status==405);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;deviceAccess.available=false;f.get();deviceAccess.available=true;assert(f.server_.status==503);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.get("/missing.html");assert(f.server_.status==404);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.get("/deps/lib.js");assert(f.server_.status==200);assert(f.server_.response("Content-Encoding")=="gzip");}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="identity";f.get("/deps/lib.js.gz");assert(f.server_.status==406);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="identity;q=0,gzip;q=0";f.get();assert(f.server_.status==406);assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.server_.incoming["Accept-Encoding"]="identity;q=0,gzip";f.get();assert(f.server_.status==200);assert(f.server_.response("Content-Encoding")=="gzip");}
 {Fixture f;f.server_.path="/status/ems/telemetry";refuseBuffer=true;assert(f.authorize());f.telemetry();refuseBuffer=false;assert(f.server_.status==503);assert(f.controller_.snapshots==0);assert(f.server_.body=="{\"error\":\"telemetry_buffer_unavailable\"}");assert(f.server_.response("Cache-Control")=="no-store");}
 {Fixture f;f.server_.path="/status/ems/telemetry";f.controller_.oversized=true;assert(f.authorize());f.telemetry();assert(f.server_.status==503);assert(f.controller_.snapshots==1);assert(f.server_.body=="{\"error\":\"telemetry_response_too_large\"}");assert(f.jsonResponse_.view().empty());}
 {Fixture f;f.server_.path="/status/ems/telemetry";const auto before=bufferAllocations;for(int i=0;i<2;++i){f.server_.outgoing.clear();assert(f.authorize());f.telemetry();assert(f.server_.status==200);assert(f.server_.body=="{\"fields\":{}}");assert(f.server_.response("Cache-Control")=="no-store");}assert(bufferAllocations==before+1);assert(f.controller_.snapshots==2);}
 {Fixture f;f.server_.path="/status";refuseBuffer=true;assert(f.authorize());f.status();refuseBuffer=false;assert(f.server_.status==503);assert(f.controller_.statusSnapshots==0);assert(f.server_.body=="{\"error\":\"status_buffer_unavailable\"}");assert(f.server_.response("Cache-Control")=="no-store");assert(!f.server_.cors);}
 {Fixture f;f.server_.path="/status";f.controller_.oversized=true;assert(f.authorize());f.status();assert(f.server_.status==503);assert(f.controller_.statusSnapshots==1);assert(f.server_.body=="{\"error\":\"status_response_too_large\"}");assert(f.jsonResponse_.view().empty());}
 {Fixture f;f.server_.path="/status";f.controller_.failStream=true;assert(f.authorize());f.status();assert(f.server_.status==503);assert(f.server_.body=="{\"error\":\"status_response_too_large\"}");}
 {Fixture f;const auto before=bufferAllocations;for(int i=0;i<3;++i){f.server_.path="/status";f.server_.outgoing.clear();assert(f.authorize());f.status();assert(f.server_.status==200);assert(f.server_.body=="{\"rooms\":[],\"controlMode\":\"shadow\",\"ems\":{\"selectedFlowTemperature\":50,\"currentFlowTemperature\":432}}");assert(f.server_.response("Cache-Control")=="no-store");assert(!f.server_.cors);f.server_.path="/status/ems/telemetry";f.server_.outgoing.clear();assert(f.authorize());f.telemetry();assert(f.server_.status==200);assert(f.server_.body=="{\"fields\":{}}");}assert(bufferAllocations==before+1);assert(f.controller_.snapshots==3);assert(f.controller_.statusSnapshots==3);}
 std::cout<<"PASS 25 actual E32 response/authorization scenarios\n";
}
'''
out = Path(os.environ.get("OPENTHERMOSTAT_HTTP_RESPONSE_EVIDENCE",ROOT / "out/static-assets"))
out.mkdir(parents=True, exist_ok=True)
cpp = out / "handler.cpp"
cpp.write_text(pre + buffer_member + authorize + serve + mime + telemetry + dashboard + post)
subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-include", "cstring",
                "-I" + str(ROOT / "src"), str(cpp), "-o", str(out / "handler")], check=True)
subprocess.run([str(out / "handler")], check=True)
