#ifdef OPENTHERMOSTAT_E32V2
#include "GitHubUpdate.h"
#include "ReleaseCatalog.h"
#include "ReleaseCheckSchedule.h"
#include "IndexedReleaseCatalog.h"
#include "VerifiedOta.h"
#include "RestartTimer.h"
#include "DownloadTextBuffer.h"
#include "DownloadFailure.h"
#include "TlsAllocationPolicy.h"
#include "UpdateCheckpoint.h"
#include "EmbeddedWebAssets.h"
#include "DeviceAccess.h"
#include "Filesystem.h"
#include "Network.h"
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <esp_ota_ops.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include <nvs.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <mbedtls/sha256.h>
#include <atomic>
#include <mutex>
#include <vector>
#include <ctime>

#if !CONFIG_MBEDTLS_INTERNAL_MEM_ALLOC
#error "Review scoped TLS allocator for changed SDK memory configuration"
#endif
extern "C" void *__real_esp_mbedtls_mem_calloc(size_t count,size_t size);
namespace {
std::atomic<TaskHandle_t> updaterTlsTask{nullptr};
}
extern "C" void *__wrap_esp_mbedtls_mem_calloc(size_t count,size_t size) {
    const auto owner=updaterTlsTask.load();
    return heating::update::allocateTlsMemory(count,size,
        owner&&owner==xTaskGetCurrentTaskHandle(),
        __real_esp_mbedtls_mem_calloc,[](size_t n,size_t s)->void* {
            return heap_caps_calloc(n,s,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        });
}

namespace heating {extern bool wifiAPMode;}
namespace heating::update {
namespace {
struct State {std::string phase="idle",error,selected,operation="none";DownloadFailure downloadError;uint32_t received=0,total=0;bool reboot=false;std::vector<Release> releases;};
State state;std::mutex stateMutex;ReleaseCheckSchedule checkSchedule;
std::atomic<bool> working{false};RestartTimer rebootTimer;
struct CheckpointStorage {
    bool read(UpdateCheckpoint &value) {
        nvs_handle_t handle;
        if(nvs_open("ot_update_diag",NVS_READONLY,&handle)!=ESP_OK)return false;
        size_t size=0;
        bool ok=nvs_get_blob(handle,"last",nullptr,&size)==ESP_OK&&size==sizeof(value);
        if(ok)ok=nvs_get_blob(handle,"last",&value,&size)==ESP_OK&&size==sizeof(value);
        nvs_close(handle);return ok;
    }
    bool write(const UpdateCheckpoint &value) {
        nvs_handle_t handle;
        if(nvs_open("ot_update_diag",NVS_READWRITE,&handle)!=ESP_OK)return false;
        const bool ok=nvs_set_blob(handle,"last",&value,sizeof(value))==ESP_OK&&nvs_commit(handle)==ESP_OK;
        nvs_close(handle);return ok;
    }
};
CheckpointStorage checkpointStorage;
UpdateCheckpointJournal<CheckpointStorage> checkpointJournal(checkpointStorage);
std::mutex checkpointMutex;
void checkpoint(UpdateStage stage,int httpStatus) {
    uint32_t received,total;
    {std::lock_guard<std::mutex> lock(stateMutex);received=state.received;total=state.total;}
    std::lock_guard<std::mutex> lock(checkpointMutex);
    checkpointJournal.advance(stage,received,total,httpStatus);
}
void phase(const std::string &name,const std::string &error="") {std::lock_guard<std::mutex> lock(stateMutex);state.phase=name;state.error=error;}
void progress(uint32_t count,uint32_t total){std::lock_guard<std::mutex> lock(stateMutex);state.received=count;state.total=total;}
void failedDownload(const DownloadFailure &failure,std::string &error) {
    error=downloadFailureMessage(failure);
    std::lock_guard<std::mutex> lock(stateMutex);state.downloadError=failure;
}
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
    DownloadTextBuffer bytes;
    explicit TextSink(size_t max):bytes(max,[](size_t size)->void* {
        return heap_caps_malloc(size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    },heap_caps_free) {}
    size_t write(const uint8_t *data,size_t size) override {return bytes.append(data,size);}
};
// HTTPClient decodes chunked bodies into a bounded sink. Redirects are checked
// BEFORE connecting, never followed implicitly to an arbitrary host/scheme.
bool download(std::string url,Sink &sink,std::string &error,uint32_t exactSize=0,int *responseStatus=nullptr) {
    if(responseStatus)*responseStatus=0;
    if(!ready()){error="Verbind met thuiswifi en wacht op een geldige netwerktijd (NTP).";return false;}
    for(unsigned redirects=0;redirects<=4;++redirects) {
        if(!allowedDownloadUrl(url)){error="Onverwachte downloadlocatie geweigerd.";return false;}
        // An indexed-catalog miss can fall back to another request. A later
        // parse/validation error must not inherit that earlier HTTP failure.
        {std::lock_guard<std::mutex> lock(stateMutex);state.downloadError={};}
        WiFiClientSecure client;client.setCACertBundle(embedded::caBundle);client.setHandshakeTimeout(15);
        HTTPClient http;http.setConnectTimeout(10000);http.setTimeout(10000);http.setReuse(false);
        http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);http.setUserAgent("OpenThermostat-E32V2");
        const char *headers[]={"Location"};http.collectHeaders(headers,1);
        if(!http.begin(client,url.c_str())){error="HTTPS kon niet worden gestart.";return false;}
        http.addHeader("Accept",exactSize?"application/octet-stream":"application/json");
        const int code=http.GET();
        if(responseStatus)*responseStatus=code;
        if(code==301||code==302||code==303||code==307||code==308) {url=http.header("Location").c_str();http.end();continue;}
        if(code!=200){
            // HTTPClient maps connection failures to negative integers. Capture
            // the native TLS result BEFORE end() destroys the secure client.
            char ignored[64]{};const int tlsCode=code<0?client.lastError(ignored,sizeof(ignored)):0;
            failedDownload(downloadFailure(code,tlsCode,url),error);http.end();return false;
        }
        if(exactSize&&http.getSize()>=0&&uint32_t(http.getSize())!=exactSize){error="Downloadgrootte wijkt af van de release.";http.end();return false;}
        const int count=http.writeToStream(&sink);http.end();
        if(count<0||(exactSize&&uint32_t(count)!=exactSize)){failedDownload(downloadFailure(code,0,url,true,count),error);return false;}
        return true;
    }
    error="Te veel downloadomleidingen.";return false;
}
bool textResponse(const std::string &url,size_t limit,std::string &out,std::string &error,int &status) {
    status=0;TextSink sink(limit);
    if(!sink.bytes.ready()){error="Onvoldoende extern geheugen voor updatecontrole.";return false;}
    if(!download(url,sink,error,0,&status))return false;
    // download() has destroyed the TLS client before an internal JSON string
    // is created. No 32 KiB internal response reservation during handshakes.
    out=sink.bytes.text();return true;
}
bool text(const std::string &url,size_t limit,std::string &out,std::string &error) {
    int status=0;return textResponse(url,limit,out,error,status);
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
    // Keep flash-readback scratch out of execute()'s long-lived TLS frame.
    // The checksum covers the same complete image, independent of chunk size.
    [[gnu::noinline]] bool readbackMatches(uint32_t size,const std::string &expected){
        mbedtls_sha256_context readback;mbedtls_sha256_init(&readback);uint8_t sum[32],bytes[1024];
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
    const auto indexed=discoverIndexedReleases(textResponse,out,error);
    if(indexed==IndexedCatalogResult::Complete)return true;
    if(indexed==IndexedCatalogResult::Failed)return false;
    error.clear();return discoverReleases(text,out,error);
}
void execute(bool install) {
    std::string error,tag;
    {std::lock_guard<std::mutex> lock(stateMutex);tag=state.selected;}
    bool ok=false;
    if(!install) {
        std::vector<Release> releases;ok=releaseList(releases,error);
        if(ok){std::lock_guard<std::mutex> lock(stateMutex);state.releases=std::move(releases);state.phase="checked";}
    } else {
        {std::lock_guard<std::mutex> lock(checkpointMutex);
         checkpointJournal.begin(embedded::version,embedded::source,tag);}
        int httpStatus=0;
        std::string raw;Manifest manifest;
        if(textResponse(assetUrl(tag,"e32v2-update.json"),4096,raw,error,httpStatus)&&parseManifest(raw,tag,manifest)) {
            progress(0,manifest.size);phase("downloading");checkpoint(UpdateStage::Download,httpStatus);
            NativeOta backend;VerifiedOta<NativeOta> transfer(backend,manifest);
            if(transfer.begin()) {
                ImageSink sink(transfer,manifest.size);
                if(download(assetUrl(tag,"firmware.bin"),sink,error,manifest.size,&httpStatus)) {
                    phase("verifying");checkpoint(UpdateStage::Verify,httpStatus);
                    ok=transfer.finish([httpStatus](OtaVerificationStep step) {
                        switch(step) {
                        case OtaVerificationStep::Hash:checkpoint(UpdateStage::Hash,httpStatus);break;
                        case OtaVerificationStep::Image:checkpoint(UpdateStage::Image,httpStatus);break;
                        case OtaVerificationStep::Readback:checkpoint(UpdateStage::Readback,httpStatus);break;
                        case OtaVerificationStep::Select:checkpoint(UpdateStage::Selecting,httpStatus);break;
                        }
                    });
                    if(ok){checkpoint(UpdateStage::Selected,httpStatus);firmwareInstalled();}
                    else error="Firmwarecontrole, checksum of flash-readback mislukt; oude firmware blijft geselecteerd.";
                }
            } else error="Geen passende vrije OTA-partitie of huidige opstart nog niet bevestigd.";
        } else if(error.empty())error="Deze release past niet bij dit bord, instellingenformaat of updateformaat.";
        if(!ok)checkpoint(UpdateStage::Error,httpStatus);
    }
    if(!install){std::lock_guard<std::mutex> lock(stateMutex);checkSchedule.completed(millis(),ok);}
    if(!ok)phase("error",error);
}
void worker(void *argument){
    updaterTlsTask.store(xTaskGetCurrentTaskHandle());
    execute(argument!=nullptr);
    updaterTlsTask.store(nullptr);
    working.store(false);
    vTaskDelete(nullptr);
}
bool start(bool install,const std::string &tag="") {
    if(busy()||!ready()||pendingBoot())return false;
    if(!install){std::lock_guard<std::mutex> lock(stateMutex);if(!state.reboot&&state.phase=="checked"&&state.error.empty()&&checkSchedule.cached(millis()))return true;}
    bool expected=false;
    if(!working.compare_exchange_strong(expected,true))return false;
    {std::lock_guard<std::mutex> lock(stateMutex);if(state.reboot){working.store(false);return false;}
      if(install&&(tag==embedded::version||!validTag(tag)||std::none_of(state.releases.begin(),state.releases.end(),[&](const Release &r){return r.tag==tag;}))){working.store(false);return false;}
      state.phase=install?"manifest":"checking";state.operation=install?"install":"check";
      state.error.clear();state.downloadError={};state.selected=tag;state.received=state.total=0;}
    if(!install){std::lock_guard<std::mutex> lock(stateMutex);checkSchedule.attempted(millis());}
    if(xTaskCreate(worker,"github-ota",12288,install?reinterpret_cast<void*>(1):nullptr,1,nullptr)!=pdPASS){working.store(false);phase("error","Onvoldoende geheugen voor updatecontrole.");return false;}
    return true;
}
}
bool busy(){return working.load()||rebootTimer.pending();}
bool staged(){std::lock_guard<std::mutex> lock(stateMutex);return state.reboot;}
bool mutationBlocked(std::string_view path){return mutationBlocked(path,busy(),staged(),pendingBoot());}
bool checkReleases(){return start(false);}
bool installRelease(const std::string &tag){return start(true,tag);}
void firmwareInstalled(){
    // Called only after native validation and successful boot-slot selection.
    // Main loop restarts independently of browser polling, after response grace.
    std::lock_guard<std::mutex> lock(stateMutex);
    state.phase="ready_to_reboot";state.reboot=true;
    rebootTimer.schedule(millis());
}
bool requestReboot(){if(!manualRebootAllowed(busy(),pendingBoot()))return false;rebootTimer.schedule(millis(),1000);return true;}
bool requestRollback(){
    if(busy()||pendingBoot())return false;const auto p=previous();if(!p||esp_ota_set_boot_partition(p)!=ESP_OK)return false;
    {std::lock_guard<std::mutex> lock(stateMutex);state.operation="rollback";state.downloadError={};}
    phase("rolling_back");rebootTimer.schedule(millis(),1000);return true;
}
std::string availability() {
    std::lock_guard<std::mutex> lock(stateMutex);
    const auto latest=newerFirmwareRelease(embedded::version,state.releases);
    auto root=control::ControlJson(cJSON_CreateObject(),cJSON_Delete);
    cJSON_AddBoolToObject(root.get(),"known",checkSchedule.known());
    cJSON_AddBoolToObject(root.get(),"available",!latest.empty());
    cJSON_AddStringToObject(root.get(),"version",latest.c_str());
    cJSON_AddNumberToObject(root.get(),"interval_seconds",ReleaseCheckSchedule::intervalMs/1000);
    if(checkSchedule.known())cJSON_AddNumberToObject(root.get(),"checked_age_seconds",checkSchedule.age(millis())/1000);
    else cJSON_AddNullToObject(root.get(),"checked_age_seconds");
    char *raw=cJSON_PrintUnformatted(root.get());std::string result=raw?raw:"{}";cJSON_free(raw);return result;
}
std::string status() {
    State snapshot;{std::lock_guard<std::mutex> lock(stateMutex);snapshot=state;}
    auto root=control::ControlJson(cJSON_CreateObject(),cJSON_Delete);
    cJSON_AddStringToObject(root.get(),"installed",embedded::version);cJSON_AddStringToObject(root.get(),"source_commit",embedded::source);
    cJSON_AddStringToObject(root.get(),"web_sha256",embedded::webSha);cJSON_AddStringToObject(root.get(),"repository",repository);
    cJSON_AddStringToObject(root.get(),"build_marker",embedded::imageMarker);
    cJSON_AddStringToObject(root.get(),"phase",snapshot.phase.c_str());cJSON_AddStringToObject(root.get(),"error",snapshot.error.c_str());
    cJSON_AddStringToObject(root.get(),"operation",snapshot.operation.c_str());
    if(snapshot.error.empty()||std::string_view(snapshot.downloadError.kind)=="none"
        ||snapshot.error!=downloadFailureMessage(snapshot.downloadError))cJSON_AddNullToObject(root.get(),"download_error");
    else {
        auto failure=cJSON_AddObjectToObject(root.get(),"download_error");
        cJSON_AddStringToObject(failure,"kind",snapshot.downloadError.kind);
        cJSON_AddStringToObject(failure,"host",snapshot.downloadError.host);
        cJSON_AddNumberToObject(failure,"http_status",snapshot.downloadError.httpStatus);
        cJSON_AddNumberToObject(failure,"client_code",snapshot.downloadError.clientCode);
        cJSON_AddNumberToObject(failure,"secure_client_code",snapshot.downloadError.tlsCode);
    }
    cJSON_AddStringToObject(root.get(),"selected",snapshot.selected.c_str());cJSON_AddBoolToObject(root.get(),"busy",busy());
    cJSON_AddBoolToObject(root.get(),"can_check",ready()&&!busy()&&!snapshot.reboot&&!pendingBoot());cJSON_AddBoolToObject(root.get(),"boot_pending",pendingBoot());
    cJSON_AddBoolToObject(root.get(),"reboot_required",snapshot.reboot);cJSON_AddBoolToObject(root.get(),"rollback_available",!pendingBoot()&&previous()!=nullptr);
    cJSON_AddBoolToObject(root.get(),"reboot_scheduled",rebootTimer.pending());
    cJSON_AddNumberToObject(root.get(),"received",snapshot.received);cJSON_AddNumberToObject(root.get(),"total",snapshot.total);
    cJSON_AddNumberToObject(root.get(),"reset_reason",int(esp_reset_reason()));
    const auto running=esp_ota_get_running_partition(),boot=esp_ota_get_boot_partition();
    if(running)cJSON_AddNumberToObject(root.get(),"running_partition_address",running->address);
    if(boot)cJSON_AddNumberToObject(root.get(),"boot_partition_address",boot->address);
    {std::lock_guard<std::mutex> lock(checkpointMutex);
     const auto saved=checkpointJournal.saved();
     cJSON_AddBoolToObject(root.get(),"checkpoint_save_failed",checkpointJournal.saveFailed());
     if(!saved)cJSON_AddNullToObject(root.get(),"last_saved_checkpoint");
     else {
        auto record=cJSON_AddObjectToObject(root.get(),"last_saved_checkpoint");
        cJSON_AddStringToObject(record,"scope","native_https_install_only");
        cJSON_AddNumberToObject(record,"attempt",saved->attempt);
        cJSON_AddStringToObject(record,"stage",updateStageName(saved->stage));
        cJSON_AddStringToObject(record,"from_version",saved->fromVersion);
        cJSON_AddStringToObject(record,"from_source",saved->fromSource);
        cJSON_AddStringToObject(record,"target_version",saved->targetVersion);
        cJSON_AddNumberToObject(record,"received",saved->received);
        cJSON_AddNumberToObject(record,"total",saved->total);
        cJSON_AddNumberToObject(record,"http_status",saved->httpStatus);
     }}
    {std::lock_guard<std::mutex> lock(stateMutex);
     cJSON_AddBoolToObject(root.get(),"check_cached",state.phase=="checked"&&state.error.empty()&&!state.reboot&&checkSchedule.cached(millis()));
     cJSON_AddNumberToObject(root.get(),"automatic_check_interval_seconds",ReleaseCheckSchedule::intervalMs/1000);
     cJSON_AddNumberToObject(root.get(),"automatic_failure_retry_seconds",ReleaseCheckSchedule::failureRetryMs/1000);}
    auto list=cJSON_AddArrayToObject(root.get(),"releases");for(const auto &r:snapshot.releases){auto entry=cJSON_CreateObject();cJSON_AddStringToObject(entry,"tag",r.tag.c_str());cJSON_AddBoolToObject(entry,"prerelease",r.prerelease);cJSON_AddItemToArray(list,entry);}
    char *raw=cJSON_PrintUnformatted(root.get());std::string result=raw?raw:"{}";cJSON_free(raw);return result;
}
void loop(bool automaticAllowed) {
    const auto now=millis();if(rebootTimer.due(now,working.load())){ESP.restart();return;}
    static bool pending=pendingBoot();static uint32_t start=now,stable=0;
    if(!pending){
        bool due;
        {std::lock_guard<std::mutex> lock(stateMutex);
         due=checkSchedule.due(now,automaticAllowed&&!working.load()&&!rebootTimer.pending()&&!state.reboot);}
        if(due&&ready()&&!pendingBoot())checkReleases();
        return;
    }
    if(networkConnected()&&deviceAccess.ready()&&filesystem.isMounted()&&embedded::imageMarker[0]) {
        if(!stable)stable=now;
        if(uint32_t(now-stable)>=20000&&esp_ota_mark_app_valid_cancel_rollback()==ESP_OK){pending=false;Serial.println("OTA boot confirmed: network, access, filesystem and embedded UI ready");}
    } else stable=0;
    if(pending&&uint32_t(now-start)>120000){Serial.println("OTA boot unconfirmed; restarting for native bootloader recovery");ESP.restart();}
}
}
#endif
