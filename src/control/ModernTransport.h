#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "ShadowController.h"
#include "ControlUiSnapshot.h"
#include "DeviceDiagnostics.h"
#include "NativeSourceProvisioning.h"
#include "GraphSessionOwner.h"
#include "GraphControlStoreView.h"
#include "TopologyControlStoreView.h"
#include "GraphFloorControlStoreView.h"
#include "ControlPartitionBudget.h"
#include "Network.h"
#include "config.h"
#include "DeviceNetworkSettings.h"
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <nvs.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
#include <ctime>
#include <atomic>

namespace heating::control {
inline std::string sha256Hex(std::string_view bytes) {
    unsigned char hash[32];
    if(mbedtls_sha256_ret(reinterpret_cast<const unsigned char *>(bytes.data()),bytes.size(),hash,0)!=0) return {};
    static constexpr char digits[]="0123456789abcdef";
    std::string out(64,'0');
    for(size_t i=0;i<32;++i) { out[2*i]=digits[hash[i]>>4]; out[2*i+1]=digits[hash[i]&15]; }
    return out;
}
inline std::string randomControlId() {
    unsigned char value[16]; esp_fill_random(value,sizeof(value));
    static constexpr char digits[]="0123456789abcdef";
    std::string out(32,'0');
    for(size_t i=0;i<16;++i) { out[2*i]=digits[value[i]>>4]; out[2*i+1]=digits[value[i]&15]; }
    return out;
}
class NvsControlStore final:public ControlStore {
public:
    explicit NvsControlStore(ControlStorageProfile profile=ControlStorageProfile::legacy_api1):profile_(profile) {}
    bool load(std::string &bytes) override {
        nvs_handle_t handle;
        auto err=nvs_open("ot_control",NVS_READONLY,&handle);
        if(err==ESP_ERR_NVS_NOT_FOUND) { bytes.clear(); return true; }
        if(err!=ESP_OK) return false;
        size_t size=0;
        err=nvs_get_blob(handle,"config",nullptr,&size);
        if(err==ESP_ERR_NVS_NOT_FOUND) { nvs_close(handle); bytes.clear(); return true; }
        if(err!=ESP_OK||size==0||size>ShadowController::maximumConfigBytes) { nvs_close(handle); return false; }
        bytes.resize(size); err=nvs_get_blob(handle,"config",bytes.data(),&size); nvs_close(handle);
        return err==ESP_OK&&size==bytes.size();
    }
    bool save(std::string_view bytes) override {
        if(bytes.empty()||bytes.size()>ShadowController::maximumConfigBytes) return false;
        if(profile_==ControlStorageProfile::graph_shadow_v2) {
            nvs_stats_t stats{};
            const auto partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
            if(!partition||nvs_get_stats("nvs",&stats)!=ESP_OK
                ||!ControlPartitionBudget::permitsGraphWrite(
                    {partition->size,stats.total_entries,
                     stats.used_entries,stats.free_entries,true},bytes.size())) return false;
        } else if(profile_!=ControlStorageProfile::legacy_api1) return false;
        nvs_handle_t handle;
        if(nvs_open("ot_control",NVS_READWRITE,&handle)!=ESP_OK) return false;
        auto err=nvs_set_blob(handle,"config",bytes.data(),bytes.size());
        if(err==ESP_OK) err=nvs_commit(handle);
        nvs_close(handle); return err==ESP_OK;
    }
private:
    ControlStorageProfile profile_;
};

// Source-owned reviewed pin, NOT a remotely supplied config/capability. No
// current settings/default factory supplies this; explicit use selects /v2/
// exclusively and enables the same-store conservative NVS graph preflight.
struct GraphSourceProfile {
    std::string controllerId,qualificationDigest;
};

// Product transport, using public PubSubClient API directly. This REPLACES the
// legacy connection when explicitly provisioned, not an extra bridge/client.
class ModernTransport {
public:
    explicit ModernTransport(config::MqttConfig cfg,ShadowController::Metrics metrics={},
                             const GraphSourceProfile* graphProfile=nullptr,
                             const SeasonalControllerSource* seasonalSource=nullptr,
                             SeasonalControllerSource::Safety safety={},
                             const GraphControlHandoffSource* graphHandoff=nullptr,
                             const TopologyControlHandoffSource* topologyHandoff=nullptr,
                             const GraphFloorControlHandoffSource* floorBridge=nullptr,
                             const NativePlanInstallationSource* nativePlanSource=nullptr,
                             ShadowController::BoilerFields boilerFields={})
        :cfg_(std::move(cfg)),client_(network_),
         store_((graphProfile||graphHandoff||topologyHandoff||floorBridge||nativePlanSource||cfg_.nativeSourceRequested)?ControlStorageProfile::graph_shadow_v2:ControlStorageProfile::legacy_api1),
         graph_(graphProfile!=nullptr) {
        char mac[17]; snprintf(mac,sizeof(mac),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
        std::unique_ptr<NativePlanInstallationSource> locallyProvisioned;
        if(cfg_.nativeSourceRequested) {
            if(!cfg_.modernShadow||graphProfile||seasonalSource||graphHandoff||topologyHandoff||floorBridge||nativePlanSource||safety) {
                valid_=false;return; // Ambiguous SOURCE selection never falls back.
            }
            locallyProvisioned=nativeSourceFromSavedDescriptor(cfg_.nativeSourceJson,mac,cfg_.adapterId,sha256Hex);
            if(!locallyProvisioned) {valid_=false;return;}
            nativePlanSource=locallyProvisioned.get();
            // Actual independent safety producer is not yet supported. Unknown
            // is deliberately UNKNOWN, not a timestamped synthetic all-safe flag.
            safety=[] {return SeasonalSafetySnapshot{};};
            try {
                const auto saved=heating::readDeviceNetworkSettings();
                const auto root=parseControlJson(std::string_view(saved.c_str(),saved.length()),true);
                const auto actual=root?field(root.get(),"mqtt"):nullptr;
                if(!actual||printJson(field(actual,"native_shadow_source"))!=cfg_.nativeSourceJson) {valid_=false;return;}
                const auto base=nativeSourceNetworkBase(root.get());
                sourceNetworkBase_=base?printJson(base.get()):std::string{};
                if(sourceNetworkBase_.empty()||sourceNetworkBase_.size()>=2048) {valid_=false;return;}
            } catch(...) {valid_=false;return;}
        }
        auto prefix=cfg_.base.empty()?"open_thermostat":cfg_.base;
        valid_=SessionAdmission::validId(prefix)&&SessionAdmission::validId(cfg_.adapterId)&&
            !cfg_.brokerAddress.empty()&&cfg_.brokerPort&& !cfg_.username.empty()&&!cfg_.password.empty();
        if(!valid_||(graphProfile&&seasonalSource)||(graphHandoff&&(!seasonalSource||graphProfile))
            ||(topologyHandoff&&(!seasonalSource||graphProfile||graphHandoff))
            ||(floorBridge&&(!seasonalSource||graphProfile||graphHandoff||topologyHandoff))
            ||(nativePlanSource&&(graphProfile||seasonalSource||graphHandoff||topologyHandoff||floorBridge))) {valid_=false;return;} // DATA2 cannot silently select control policy.
        base_=prefix+(graph_?"/v2/":"/v1/");
        client_.setServer(cfg_.brokerAddress.c_str(),cfg_.brokerPort);
        client_.setKeepAlive(15); client_.setSocketTimeout(1);
        // Total packet budget: max payload8192 + bounded prefix/topic/header.
        if(!client_.setBufferSize(8448)) { valid_=false; return; }
        const auto publish=[this](std::string_view suffix,std::string_view payload) {
            ui_.capture(suffix,payload,static_cast<uint64_t>(esp_timer_get_time()/1000));
            const std::string topic=base_+std::string(suffix);
            // Same one native connection; no raw private wire logging.
            client_.publish(topic.c_str(),reinterpret_cast<const uint8_t *>(payload.data()),payload.size(),false);
        };
        if(graph_) {
            if(graphProfile->controllerId!=mac||!hexString(graphProfile->qualificationDigest,64)) {
                valid_=false;return; // Explicitly selected API2 NEVER falls back1.
            }
            graphController_=std::make_unique<GraphSessionOwner>(mac,randomControlId(),cfg_.adapterId,
                graphProfile->qualificationDigest,store_,sha256Hex,randomControlId,publish);
        } else {
            ControlStore* selectedStore=&store_;
            if(graphHandoff) {
                graphControlView_=std::make_unique<GraphControlStoreView>(mac,cfg_.adapterId,store_,
                    sha256Hex,*graphHandoff,*seasonalSource);
                selectedStore=graphControlView_.get();
            }
            if(topologyHandoff) {
                topologyControlView_=std::make_unique<TopologyControlStoreView>(mac,cfg_.adapterId,store_,
                    sha256Hex,*topologyHandoff,*seasonalSource);
                selectedStore=topologyControlView_.get();
            }
            if(floorBridge) {
                floorControlView_=std::make_unique<GraphFloorControlStoreView>(mac,cfg_.adapterId,store_,
                    sha256Hex,*floorBridge,*seasonalSource);
                selectedStore=floorControlView_.get();
            }
            controller_=std::make_unique<ShadowController>(mac,randomControlId(),cfg_.adapterId,*selectedStore,
                sha256Hex,randomControlId,publish,std::move(metrics),seasonalSource,std::move(safety),nativePlanSource,std::move(boilerFields));
        }
        client_.setCallback([this](char *topic,uint8_t *payload,unsigned int length) {
            const std::string_view full(topic);
            if(length>8192||full.substr(0,base_.size())!=base_) return;
            const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
            const auto utc=std::time(nullptr);
            withOwner([&](auto& owner){owner.receive(full.substr(base_.size()),
                std::string_view(reinterpret_cast<char *>(payload),length),now,utc,clockValid());});
        });
    }
    void getUiStatus(std::ostream& out) const {
        ui_.write(out,static_cast<uint64_t>(esp_timer_get_time()/1000),valid_&&wasConnected_);
    }
    bool nativeSourceCurrent(std::string_view expected,std::string_view savedSettings) const {
        return valid_&&!graph_&&cfg_.nativeSourceRequested&&controller_&&controller_->nativeSourceSelected()
            &&cfg_.nativeSourceJson==expected&&nativeSourceNetworkStillCurrent(sourceNetworkBase_,savedSettings);
    }
    bool nativeSourceHotReady(std::string_view expected,std::string_view savedSettings) const {
        return nativeSourceCurrent(expected,savedSettings)&&controller_->nativeSourceReplaceable();
    }
    bool nativeSourceCanApply(std::string_view expected,std::string_view descriptor,std::string_view savedSettings) const {
        if(!nativeSourceHotReady(expected,savedSettings))return false;
        try {
            char mac[17];snprintf(mac,sizeof(mac),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
            const auto source=nativeSourceFromSavedDescriptor(descriptor,mac,cfg_.adapterId,sha256Hex);
            return source&&controller_->nativeSourceCanReplace(*source);
        } catch(...) {return false;}
    }
    void inhibitNativeSourceMutation() {
        ui_.clear();
        if(controller_)controller_->inhibitNativeSourceMutation();
        valid_=false;
        // Same native availability channel; no logging/private wire.
        if(client_.connected()) {
            client_.publish((base_+"fw/availability").c_str(),"offline",false);
            client_.disconnect();
        }
        wasConnected_=false;
    }
    bool applyNativeSource(std::string_view expected,std::string_view descriptor,std::string_view previousSettings) {
        if(!nativeSourceHotReady(expected,previousSettings)) {inhibitNativeSourceMutation();return false;}
        try {
            char mac[17];snprintf(mac,sizeof(mac),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
            const auto source=nativeSourceFromSavedDescriptor(descriptor,mac,cfg_.adapterId,sha256Hex);
            // Allocate prospective saved selection BEFORE touching current core.
            const std::string selection(descriptor);
            if(!source||!controller_->replaceNativeSource(*source,static_cast<uint64_t>(esp_timer_get_time()/1000))) {
                inhibitNativeSourceMutation();return false;
            }
            ui_.clear(); // Successful SOURCE replacement cannot expose the prior owner state.
            cfg_.nativeSourceJson=selection;
            return true;
        } catch(...) {inhibitNativeSourceMutation();return false;}
    }
    void loop() {
        if(!valid_||(!controller_&&!graphController_)) return;
        auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        if(!heating::networkConnected()||!client_.connected()) {
            if(wasConnected_) { ui_.clear(); withOwner([](auto& owner){owner.disconnected();}); wasConnected_=false; }
            // Advance local withdrawal deadlines even if network/reconnect fails.
            // Offline owner ticks never publish or consult remote observers.
            withOwner([&](auto& owner){owner.tick(now,0,false);});
            if(!heating::networkConnected()||now<nextConnect_) return;
            nextConnect_=now+5000;
            const auto id=cfg_.clientId.empty()?cfg_.base:cfg_.clientId;
            const auto willTopic=base_+"fw/availability";
            if(!client_.connect(id.c_str(),cfg_.username.c_str(),cfg_.password.c_str(),willTopic.c_str(),0,false,"offline",true)) return;
            bool subscriptions=true;
            for(auto suffix:{"ha/open_session","ha/heartbeat","ha/config","ha/observations","ha/user_command","ha/snapshot_request"}) {
                if(graph_&&(std::string_view(suffix)=="ha/observations"||std::string_view(suffix)=="ha/user_command"))continue;
                const auto topic=base_+suffix;
                subscriptions=client_.subscribe(topic.c_str(),0)&&subscriptions;
            }
            if(!subscriptions) { client_.disconnect(); return; }
            withOwner([&](auto& owner){owner.connected(now);}); wasConnected_=true; nextDeviceDiagnostics_=0;
            client_.publish(willTopic.c_str(),"online",false);
        }
        const auto utc=std::time(nullptr);
        withOwner([&](auto& owner){owner.tick(now,utc,clockValid());});
        client_.loop();
        // Observation only, on the existing native connection. Never control input.
        if(client_.connected() && now>=nextDeviceDiagnostics_) {
            nextDeviceDiagnostics_=now+15000;
            const auto bytes=deviceDiagnosticsJson(ESP.getFreeHeap(), ESP.getMinFreeHeap(),
                ESP.getMaxAllocHeap(), temperatureRead(), now/1000);
            client_.publish((base_+"fw/telemetry/device_status").c_str(),bytes.c_str(),false);
        }
    }
private:
    template<class F>void withOwner(F&& action) {
        if(graphController_)action(*graphController_);
        else if(controller_)action(*controller_);
    }
    // Validated SNTP event in main sets this trust flag. A plausible cached or
    // manual wall time is not sufficient after boot; no RTC assumed on E32.
    static bool clockValid();
    config::MqttConfig cfg_; std::string base_,sourceNetworkBase_; // ephemeral bounded<2048, never logged/persisted.
    WiFiClient network_; PubSubClient client_; NvsControlStore store_;
    std::unique_ptr<GraphControlStoreView> graphControlView_;
    std::unique_ptr<TopologyControlStoreView> topologyControlView_;
    std::unique_ptr<GraphFloorControlStoreView> floorControlView_;
    std::unique_ptr<ShadowController> controller_;
    std::unique_ptr<GraphSessionOwner> graphController_;
    ControlUiSnapshot ui_;
    uint64_t nextConnect_=0,nextDeviceDiagnostics_=0;
    std::atomic<bool> valid_{false},wasConnected_{false};
    bool graph_=false;
};
}
#endif
