"""Execute exact REST app-upload methods with mocked native OTA/HTTP boundaries.

No network, flash, watchdog or real WebServer timing claims. The pinned native
parser's synchronous request boundary is verified separately in the audit.
"""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'out/manual-ota-rest-test'
out.mkdir(parents=True, exist_ok=True)
source = (root / 'src/REST.h').read_text()

def section(start, end):
    a = source.index(start)
    return source[a:source.index(end, a)]

methods = '\n'.join([
    section('\tvoid handle() {', '\nprivate:'),
    section('\tvoid handleOTAUpdate() {', '\n\tvoid handleOTAFFSUpdate()'),
    section('\tstruct AppOtaBackend {', '\n\tstruct OTAUpload {'),
])
head = r'''
#define OPENTHERMOSTAT_E32V2
#include "update/ManualAppUpload.h"
#include "control/WebAuthSession.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>
using namespace std::string_literals;
using namespace std::string_view_literals;
#define DBGLOGFI(...) ((void)0)
using esp_err_t=int;
using esp_ota_handle_t=unsigned;
constexpr int ESP_OK=0;
struct esp_partition_t {size_t size=8;};
struct Native {
    esp_partition_t partition;
    bool partitionAvailable=true,beginOk=true,writeOk=true,endOk=true,selectOk=true;
    int begins=0,writes=0,ends=0,selects=0,aborts=0,reboots=0,yields=0;
    bool open=false,settingsBlocked=false;
    size_t eraseSize=0;
} native;
void delay(unsigned ms){assert(ms==1);++native.yields;}
const esp_partition_t *esp_ota_get_next_update_partition(void*) {return native.partitionAvailable?&native.partition:nullptr;}
int esp_ota_begin(const esp_partition_t *p,size_t n,unsigned *h) {
    assert(p);++native.begins;native.eraseSize=n;
    if(!native.beginOk)return -1;
    assert(!native.open);native.open=true;*h=1;return 0;
}
int esp_ota_write(unsigned h,const void*,size_t) {assert(h==1&&native.open);++native.writes;return native.writeOk?0:-2;}
int esp_ota_end(unsigned h) {assert(h==1&&native.open);native.open=false;++native.ends;return native.endOk?0:-3;}
int esp_ota_set_boot_partition(const esp_partition_t *p) {assert(p&&!native.open);++native.selects;return native.selectOk?0:-4;}
int esp_ota_abort(unsigned h) {assert(h==1&&native.open);native.open=false;++native.aborts;return 0;}
namespace heating::update {
void firmwareInstalled(){++native.reboots;native.settingsBlocked=true;}
bool mutationBlocked(std::string_view path){assert(path=="/boiler/settings/write");return native.settingsBlocked;}
}
using namespace heating;
struct String:std::string {using std::string::string;};
enum {UPLOAD_FILE_START,UPLOAD_FILE_WRITE,UPLOAD_FILE_END,UPLOAD_FILE_ABORTED};
struct HTTPUpload {int status=UPLOAD_FILE_START;size_t currentSize=0;char buf[8]={};};
struct Server {
    HTTPUpload current;
    String declared="8",path="/ota";
    std::function<void()> callback;
    std::vector<int> statuses;
    std::vector<std::string> bodies;
    HTTPUpload &upload(){return current;}
    String arg(const char*){return declared;}
    String uri(){return path;}
    void handleClient(){if(callback)callback();}
    void sendView(int status,std::string_view,std::string_view body){statuses.push_back(status);bodies.emplace_back(body);}
};
struct Controller {
    std::vector<bool> settingsPermission;
    void boilerSettingsSynchronize(const control::WebAuthSession&,uint64_t now,bool allowed){
        assert(now==1000);settingsPermission.push_back(allowed);
    }
};
struct REST {
    Server server_;Controller controller_;control::WebAuthSession sessions_;
    uint64_t networkNow(){return 1000;}
    bool authorized=true;
    bool authorize(bool=true){return authorized;}
    struct {bool success=false;int error=0;std::string errorMessage;} ota_;
'''
tail = r'''
};
int cases=0;
void pass(const char *name){++cases;std::cout<<"PASS "<<name<<'\n';}
void event(REST &r,int type,size_t size=0){r.server_.current.status=type;r.server_.current.currentSize=size;r.handleOTAUpdate();}
void finalHandler(REST &r){if(r.authorize())r.handleOTAResponse();}
void data(REST &r){event(r,UPLOAD_FILE_START);event(r,UPLOAD_FILE_WRITE,8);event(r,UPLOAD_FILE_END);}
int main(){
    {
        native={};REST r;r.server_.callback=[&]{data(r);assert(native.selects==0);finalHandler(r);};r.handle();
        assert(native.eraseSize==8&&native.ends==1&&native.selects==1&&native.reboots==1&&native.yields==native.writes&&native.writes==1);
        assert(r.server_.statuses==std::vector<int>{200}&&!native.open&&native.aborts==0);
        assert(r.controller_.settingsPermission==std::vector<bool>({true,false}));
        pass("exact production callbacks select only at final handler and schedule restart only after success");
        r.server_.callback=[&]{finalHandler(r);};r.handle();
        assert(r.server_.statuses.back()==500&&native.selects==1&&native.reboots==1);
        assert(r.controller_.settingsPermission==std::vector<bool>({true,false,false,false}));
        pass("next empty request cannot select a stale successful upload");
    }
    for(const char *size:{"","0","-1","8x","9","99999999999999999999999999"}) {
        native={};REST r;r.server_.declared=size;r.server_.callback=[&]{data(r);finalHandler(r);};r.handle();
        assert(native.begins==0&&native.selects==0&&native.reboots==0&&r.server_.statuses.back()==500);
    }
    pass("malformed or oversized declared length rejected before native erase");
    for(int received:{7,9}) {
        native={};REST r;r.server_.callback=[&]{event(r,UPLOAD_FILE_START);event(r,UPLOAD_FILE_WRITE,received);event(r,UPLOAD_FILE_END);finalHandler(r);};r.handle();
        assert(native.ends==0&&native.selects==0&&native.reboots==0&&native.aborts==1&&!native.open&&r.server_.statuses.back()==500);
    }
    pass("truncated or excess body cancels without boot selection");
    for(int fault=0;fault<4;++fault) {
        native={};native.beginOk=fault!=0;native.writeOk=fault!=1;native.endOk=fault!=2;native.selectOk=fault!=3;
        REST r;r.server_.callback=[&]{data(r);finalHandler(r);};r.handle();
        assert(!native.open&&native.reboots==0&&r.server_.statuses.back()==500);
        assert(native.aborts==(fault==1?1:0));assert(native.selects==(fault==3?1:0));
    }
    pass("begin/write/end/select failures clean exact handle lifetime and never schedule restart");
    for(int loss=0;loss<3;++loss) {
        native={};REST r;r.server_.callback=[&]{
            event(r,UPLOAD_FILE_START);
            if(loss==0)r.authorized=false;
            event(r,UPLOAD_FILE_WRITE,8);
            if(loss==1)r.authorized=false;
            event(r,UPLOAD_FILE_END);
            if(loss==2)r.authorized=false;
            finalHandler(r);
        };r.handle();assert(!native.open&&native.selects==0&&native.reboots==0);
        assert(native.aborts==(loss==2?0:1));
    }
    pass("authorization lost during writing, validation or final gate cannot commit");
    for(bool complete:{false,true}) {
        native={};REST r;r.server_.callback=[&]{
            event(r,UPLOAD_FILE_START);if(complete){event(r,UPLOAD_FILE_WRITE,8);event(r,UPLOAD_FILE_END);}
        };r.handle();assert(!native.open&&native.selects==0&&native.reboots==0);
        assert(native.aborts==(complete?0:1));
    }
    pass("parser disconnect/failure releases incomplete handle and never selects validated image");
    {
        native={};REST r;r.server_.callback=[&]{data(r);data(r);finalHandler(r);};r.handle();
        assert(native.begins==1&&native.selects==0&&native.reboots==0&&r.server_.statuses.back()==500);
        pass("second multipart file cannot replace or commit first image");
    }
    {
        native={};REST r;r.server_.callback=[&]{event(r,UPLOAD_FILE_START);event(r,UPLOAD_FILE_ABORTED);event(r,UPLOAD_FILE_END);finalHandler(r);};r.handle();
        assert(native.aborts==1&&!native.open&&native.ends==0&&native.selects==0);
        pass("abort event is terminal and cannot revive at end callback");
    }
    {
        native={};native.partitionAvailable=false;REST r;r.server_.callback=[&]{data(r);finalHandler(r);};r.handle();
        assert(native.begins==0&&native.selects==0&&native.reboots==0&&r.server_.statuses.back()==500);
        pass("missing inactive partition never erases or selects");
    }
    {
        native={};REST r;r.server_.path="/otafs";r.ota_.success=true;
        r.server_.callback=[&]{r.handleOTAResponse();};r.handle();
        assert(r.server_.statuses.back()==200&&native.begins==0&&native.selects==0&&native.reboots==0);
        pass("filesystem response retains success without application restart");
    }
    std::cout<<cases<<" production REST boundary scenarios passed\n";
}
'''
cpp = out / 'rest_upload.cpp'
cpp.write_text(head + methods + tail)
exe = out / 'rest_upload'
subprocess.run([os.environ.get('CXX', 'g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-I'+str(root/'src'), str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
