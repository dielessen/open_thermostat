#ifdef OPENTHERMOSTAT_E32V2
#include "GitHubUpdate.h"
#include "VerifiedOta.h"
#include "EmbeddedWebAssets.h"
#include "DeviceAccess.h"
#include "Filesystem.h"
#include "Network.h"
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>
#include <atomic>
#include <mutex>
#include <vector>
#include <ctime>

namespace heating {extern bool wifiAPMode;}
namespace heating::update {
namespace {
struct Release {std::string tag;bool prerelease=false;};
struct State {std::string phase="idle",error,selected;uint32_t received=0,total=0;bool reboot=false;std::vector<Release> releases;};
State state;std::mutex stateMutex;
std::atomic<bool> working{false};std::atomic<uint32_t> rebootAt{0};
void phase(const std::string &name,const std::string &error="") {std::lock_guard<std::mutex> lock(stateMutex);state.phase=name;state.error=error;}
void progress(uint32_t count,uint32_t total){std::lock_guard<std::mutex> lock(stateMutex);state.received=count;state.total=total;}
bool pendingBoot() {esp_ota_img_states_t s;return esp_ota_get_state_partition(esp_ota_get_running_partition(),&s)==ESP_OK&&s==ESP_OTA_IMG_PENDING_VERIFY;}
const esp_partition_t *previous() {
    const auto p=esp_ota_get_next_update_partition(nullptr);esp_ota_img_states_t s;
    return p&&esp_ota_get_state_partition(p,&s)==ESP_OK&&s==ESP_OTA_IMG_VALID?p:nullptr;
}
bool ready() {return !wifiAPMode&&networkConnected()&&std::time(nullptr)>1700000000&&std::time(nullptr)<2082758400;}
class Sink:public Stream {
public:
    using Stream::write;
    size_t write(uint8_t c) override {return write(&c,1);}
    int available() override{return 0;} int read() override{return -1;} int peek() override{return -1;} void flush() override{}
};
class TextSink:public Sink {
public:
    using Sink::write;
    std::string bytes;size_t limit;
    explicit TextSink(size_t max):limit(max){}
    size_t write(const uint8_t *data,size_t size) override {if(size>limit-bytes.size())return 0;bytes.append(reinterpret_cast<const char*>(data),size);return size;}
};
// HTTPClient decodes chunked bodies into a bounded sink. Redirects are checked
// BEFORE connecting, never followed implicitly to an arbitrary host/scheme.
bool download(std::string url,Sink &sink,std::string &error,uint32_t exactSize=0) {
    if(!ready()){error="Verbind met thuiswifi en wacht op een geldige netwerktijd (NTP).";return false;}
    for(unsigned redirects=0;redirects<=4;++redirects) {
        if(!allowedDownloadUrl(url)){error="Onverwachte downloadlocatie geweigerd.";return false;}
        WiFiClientSecure client;client.setCACertBundle(embedded::caBundle);client.setHandshakeTimeout(15);
        HTTPClient http;http.setConnectTimeout(10000);http.setTimeout(10000);http.setReuse(false);
        http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);http.setUserAgent("OpenThermostat-E32V2");
        const char *headers[]={"Location"};http.collectHeaders(headers,1);
        if(!http.begin(client,url.c_str())){error="HTTPS kon niet worden gestart.";return false;}
        http.addHeader("Accept",exactSize?"application/octet-stream":"application/json");
        const int code=http.GET();
        if(code==301||code==302||code==303||code==307||code==308) {url=http.header("Location").c_str();http.end();continue;}
        if(code!=200){error="GitHub/HTTPS antwoord "+std::to_string(code)+"; controleer internet, tijd en API-limiet.";http.end();return false;}
        if(exactSize&&http.getSize()>=0&&uint32_t(http.getSize())!=exactSize){error="Downloadgrootte wijkt af van de release.";http.end();return false;}
        const int count=http.writeToStream(&sink);http.end();
        if(count<0||(exactSize&&uint32_t(count)!=exactSize)){error="Download afgebroken, te groot of onvolledig; oude firmware blijft geselecteerd.";return false;}
        return true;
    }
    error="Te veel downloadomleidingen.";return false;
}
bool text(const std::string &url,size_t limit,std::string &out,std::string &error) {
    TextSink sink(limit);if(!download(url,sink,error))return false;out=std::move(sink.bytes);return true;
}
std::string digest(const uint8_t *bytes,size_t size) {
    const char hexChars[]="0123456789abcdef";std::string result;result.reserve(size*2);
    for(size_t i=0;i<size;++i){result+=hexChars[bytes[i]>>4];result+=hexChars[bytes[i]&15];}return result;
}
struct NativeOta {
    const esp_partition_t *partition=nullptr;esp_ota_handle_t handle=0;bool open=false;
    mbedtls_sha256_context hash;
    NativeOta(){mbedtls_sha256_init(&hash);}~NativeOta(){abort();mbedtls_sha256_free(&hash);}
    bool begin(uint32_t size){
        partition=esp_ota_get_next_update_partition(nullptr);
        if(!partition||partition->size!=maxImageBytes||size>partition->size||
           (partition->address!=0x10000&&partition->address!=0x390000)||pendingBoot())return false;
        if(mbedtls_sha256_starts_ret(&hash,0)!=0||esp_ota_begin(partition,size,&handle)!=ESP_OK)return false;
        open=true;return true;
    }
    bool write(const uint8_t *data,size_t size){return open&&mbedtls_sha256_update_ret(&hash,data,size)==0&&esp_ota_write(handle,data,size)==ESP_OK;}
    bool hashMatches(const std::string &expected){uint8_t sum[32];return mbedtls_sha256_finish_ret(&hash,sum)==0&&digest(sum,32)==expected;}
    bool end(){if(!open)return false;open=false;return esp_ota_end(handle)==ESP_OK;}
    bool readbackMatches(uint32_t size,const std::string &expected){
        mbedtls_sha256_context readback;mbedtls_sha256_init(&readback);uint8_t sum[32],bytes[4096];
        bool ok=mbedtls_sha256_starts_ret(&readback,0)==0;
        for(uint32_t off=0;ok&&off<size;){const auto n=std::min<uint32_t>(sizeof(bytes),size-off);ok=esp_partition_read(partition,off,bytes,n)==ESP_OK&&mbedtls_sha256_update_ret(&readback,bytes,n)==0;off+=n;delay(1);}
        ok=ok&&mbedtls_sha256_finish_ret(&readback,sum)==0&&digest(sum,32)==expected;mbedtls_sha256_free(&readback);return ok;
    }
    bool select(){return esp_ota_set_boot_partition(partition)==ESP_OK;}
    void abort(){if(open){esp_ota_abort(handle);open=false;}}
};
class ImageSink:public Sink {
    VerifiedOta<NativeOta> &transfer_;uint32_t total_,started_=millis();
public:
    using Sink::write;
    ImageSink(VerifiedOta<NativeOta> &t,uint32_t size):transfer_(t),total_(size){}
    size_t write(const uint8_t *bytes,size_t size) override {
        if(uint32_t(millis()-started_)>600000||!transfer_.append(bytes,size))return 0;
        progress(transfer_.received(),total_);delay(1);return size;
    }
};
bool releaseList(std::vector<Release> &out,std::string &error) {
    std::string raw;if(!text(releaseApi,24576,raw,error))return false;
    auto root=releaseJson(raw);if(!root||!cJSON_IsArray(root.get())){error="Ongeldig of te groot GitHub-releaseantwoord.";return false;}
    std::vector<Release> candidates;
    for(auto r=root->child;r&&candidates.size()<2;r=r->next) {
        const auto tag=string(r,"tag_name");if(!validTag(tag)||cJSON_IsTrue(field(r,"draft")))continue;
        bool manifest=false,image=false;auto assets=field(r,"assets");
        if(cJSON_IsArray(assets))for(auto a=assets->child;a;a=a->next){manifest|=string(a,"name")=="e32v2-update.json";image|=string(a,"name")=="firmware.bin";}
        if(manifest&&image)candidates.push_back({tag,cJSON_IsTrue(field(r,"prerelease"))});
    }
    root.reset();raw.clear();raw.shrink_to_fit();
    for(const auto &candidate:candidates){std::string manifestBytes;Manifest m;
        if(!text(assetUrl(candidate.tag,"e32v2-update.json"),4096,manifestBytes,error))return false;
        if(parseManifest(manifestBytes,candidate.tag,m))out.push_back(candidate);
    }
    return true;
}
void execute(bool install) {
    std::string error,tag;
    {std::lock_guard<std::mutex> lock(stateMutex);tag=state.selected;}
    bool ok=false;
    if(!install) {
        std::vector<Release> releases;ok=releaseList(releases,error);
        if(ok){std::lock_guard<std::mutex> lock(stateMutex);state.releases=std::move(releases);state.phase="checked";}
    } else {
        std::string raw;Manifest manifest;
        if(text(assetUrl(tag,"e32v2-update.json"),4096,raw,error)&&parseManifest(raw,tag,manifest)) {
            progress(0,manifest.size);phase("downloading");NativeOta backend;VerifiedOta<NativeOta> transfer(backend,manifest);
            if(transfer.begin()) {
                ImageSink sink(transfer,manifest.size);
                if(download(assetUrl(tag,"firmware.bin"),sink,error,manifest.size)) {
                    phase("verifying");ok=transfer.finish();
                    if(ok){std::lock_guard<std::mutex> lock(stateMutex);state.phase="ready_to_reboot";state.reboot=true;}
                    else error="Firmwarecontrole, checksum of flash-readback mislukt; oude firmware blijft geselecteerd.";
                }
            } else error="Geen passende vrije OTA-partitie of huidige opstart nog niet bevestigd.";
        } else if(error.empty())error="Deze release past niet bij dit bord, instellingenformaat of updateformaat.";
    }
    if(!ok)phase("error",error);
    working.store(false);
}
void worker(void *argument){execute(argument!=nullptr);vTaskDelete(nullptr);}
bool start(bool install,const std::string &tag="") {
    if(busy()||!ready()||(install&&pendingBoot()))return false;
    {std::lock_guard<std::mutex> lock(stateMutex);if(state.reboot)return false;
      if(install&&(tag==embedded::version||!validTag(tag)||std::none_of(state.releases.begin(),state.releases.end(),[&](const Release &r){return r.tag==tag;})))return false;
      state.phase=install?"manifest":"checking";state.error.clear();state.selected=tag;state.received=state.total=0;}
    working.store(true);
    if(xTaskCreate(worker,"github-ota",12288,install?reinterpret_cast<void*>(1):nullptr,1,nullptr)!=pdPASS){working.store(false);phase("error","Onvoldoende geheugen voor updatecontrole.");return false;}
    return true;
}
}
bool busy(){return working.load()||rebootAt.load()!=0;}
bool staged(){std::lock_guard<std::mutex> lock(stateMutex);return state.reboot;}
bool mutationBlocked(std::string_view path){return mutationBlocked(path,busy(),staged(),pendingBoot());}
bool checkReleases(){return start(false);}
bool installRelease(const std::string &tag){return start(true,tag);}
bool requestReboot(){if(busy())return false;rebootAt.store(millis()+1000);return true;}
bool requestRollback(){
    if(busy()||pendingBoot())return false;const auto p=previous();if(!p||esp_ota_set_boot_partition(p)!=ESP_OK)return false;
    phase("rolling_back");rebootAt.store(millis()+1000);return true;
}
std::string status() {
    State snapshot;{std::lock_guard<std::mutex> lock(stateMutex);snapshot=state;}
    auto root=control::ControlJson(cJSON_CreateObject(),cJSON_Delete);
    cJSON_AddStringToObject(root.get(),"installed",embedded::version);cJSON_AddStringToObject(root.get(),"source_commit",embedded::source);
    cJSON_AddStringToObject(root.get(),"web_sha256",embedded::webSha);cJSON_AddStringToObject(root.get(),"repository",repository);
    cJSON_AddStringToObject(root.get(),"build_marker",embedded::imageMarker);
    cJSON_AddStringToObject(root.get(),"phase",snapshot.phase.c_str());cJSON_AddStringToObject(root.get(),"error",snapshot.error.c_str());
    cJSON_AddStringToObject(root.get(),"selected",snapshot.selected.c_str());cJSON_AddBoolToObject(root.get(),"busy",busy());
    cJSON_AddBoolToObject(root.get(),"can_check",ready()&&!busy()&&!snapshot.reboot);cJSON_AddBoolToObject(root.get(),"boot_pending",pendingBoot());
    cJSON_AddBoolToObject(root.get(),"reboot_required",snapshot.reboot);cJSON_AddBoolToObject(root.get(),"rollback_available",!pendingBoot()&&previous()!=nullptr);
    cJSON_AddNumberToObject(root.get(),"received",snapshot.received);cJSON_AddNumberToObject(root.get(),"total",snapshot.total);
    auto list=cJSON_AddArrayToObject(root.get(),"releases");for(const auto &r:snapshot.releases){auto entry=cJSON_CreateObject();cJSON_AddStringToObject(entry,"tag",r.tag.c_str());cJSON_AddBoolToObject(entry,"prerelease",r.prerelease);cJSON_AddItemToArray(list,entry);}
    char *raw=cJSON_PrintUnformatted(root.get());std::string result=raw?raw:"{}";cJSON_free(raw);return result;
}
void loop() {
    const auto now=millis();const auto reboot=rebootAt.load();if(reboot&&int32_t(now-reboot)>=0){ESP.restart();return;}
    static bool pending=pendingBoot();static uint32_t start=now,stable=0;
    if(!pending)return;
    if(networkConnected()&&deviceAccess.ready()&&filesystem.isMounted()&&embedded::imageMarker[0]) {
        if(!stable)stable=now;
        if(uint32_t(now-stable)>=20000&&esp_ota_mark_app_valid_cancel_rollback()==ESP_OK){pending=false;Serial.println("OTA boot confirmed: network, access, filesystem and embedded UI ready");}
    } else stable=0;
    if(pending&&uint32_t(now-start)>120000){Serial.println("OTA boot unconfirmed; restarting for native bootloader recovery");ESP.restart();}
}
}
#endif
