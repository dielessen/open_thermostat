// Actual presentation persistence helper; fault injection at the native NVS API.
#include "BoilerDisplay.h"
#include <cassert>
#include <cstring>
#include <iostream>
namespace {
std::optional<std::string> stored;
int opens=0, closes=0, writes=0, commits=0;
bool openError=false, readError=false, writeError=false, commitError=false;
}
int nvs_open(const char* name,int mode,nvs_handle_t* handle) {
    assert(std::strcmp(name,"ot_display")==0);
    if(openError)return 2;
    if(mode==NVS_READONLY&&!stored)return ESP_ERR_NVS_NOT_FOUND;
    ++opens;*handle=1;return ESP_OK;
}
int nvs_get_str(nvs_handle_t,const char* key,char* result,size_t* size) {
    assert(std::strcmp(key,"boiler")==0);
    if(readError)return 2;
    if(!stored)return ESP_ERR_NVS_NOT_FOUND;
    if(*size<stored->size()+1)return 2;
    std::memcpy(result,stored->c_str(),stored->size()+1);*size=stored->size()+1;return ESP_OK;
}
int nvs_set_str(nvs_handle_t,const char* key,const char* value) {
    assert(std::strcmp(key,"boiler")==0);++writes;
    if(writeError)return 2;
    stored=value;return ESP_OK;
}
int nvs_commit(nvs_handle_t) {++commits;return commitError?2:ESP_OK;}
void nvs_close(nvs_handle_t) {++closes;}
int main() {
    using namespace heating;
    assert(readBoilerDisplayModel()=="none"&&writes==0&&commits==0);
    assert(saveBoilerDisplayModel("nefit-ecomline-classic"));
    // Reconstruct from storage without any retained caller/browser state.
    assert(readBoilerDisplayModel()=="nefit-ecomline-classic");
    const auto previous=stored;const auto count=writes;
    assert(!saveBoilerDisplayModel("unreviewed-model")&&writes==count&&stored==previous);
    commitError=true;assert(!saveBoilerDisplayModel("none"));commitError=false;
    writeError=true;const auto committed=commits;
    assert(!saveBoilerDisplayModel("none")&&commits==committed);writeError=false;
    readError=true;assert(!readBoilerDisplayModel());
    assert(!saveBoilerDisplayModel("none"));readError=false;
    stored="unknown-corrupt-model";assert(!readBoilerDisplayModel());
    stored=std::string(100,'x');assert(!readBoilerDisplayModel());
    openError=true;assert(!readBoilerDisplayModel());assert(!saveBoilerDisplayModel("none"));openError=false;
    assert(saveBoilerDisplayModel("none")&&readBoilerDisplayModel()=="none");
    assert(opens==closes);
    std::cout<<"PASS original NVS presentation helper: persistence/readback, rejected values, SDK faults, closed handles\n";
}
