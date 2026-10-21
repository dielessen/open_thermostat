#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "ShadowController.h"
#include "ControlPartitionBudget.h"
#include "Network.h"
#include "config.h"
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <nvs.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
#include <ctime>

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

// Product transport, using public PubSubClient API directly. This REPLACES the
// legacy connection when explicitly provisioned, not an extra bridge/client.
class ModernTransport {
public:
    explicit ModernTransport(config::MqttConfig cfg,ShadowController::Metrics metrics={}):cfg_(std::move(cfg)),client_(network_) {
        auto prefix=cfg_.base.empty()?"open_thermostat":cfg_.base;
        valid_=SessionAdmission::validId(prefix)&&SessionAdmission::validId(cfg_.adapterId)&&
            !cfg_.brokerAddress.empty()&&cfg_.brokerPort&& !cfg_.username.empty()&&!cfg_.password.empty();
        if(!valid_) return; // no anonymous control or fallback legacy writer
        base_=prefix+"/v1/";
        client_.setServer(cfg_.brokerAddress.c_str(),cfg_.brokerPort);
        client_.setKeepAlive(15); client_.setSocketTimeout(1);
        // Total packet budget: max payload8192 + bounded prefix/topic/header.
        if(!client_.setBufferSize(8448)) { valid_=false; return; }
        char mac[17]; snprintf(mac,sizeof(mac),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
        controller_=std::make_unique<ShadowController>(mac,randomControlId(),cfg_.adapterId,store_,sha256Hex,randomControlId,
            [this](std::string_view suffix,std::string_view payload) {
                const std::string topic=base_+std::string(suffix);
                // No raw wire logging: HA identity/config may be private.
                client_.publish(topic.c_str(),reinterpret_cast<const uint8_t *>(payload.data()),payload.size(),false);
            },std::move(metrics));
        client_.setCallback([this](char *topic,uint8_t *payload,unsigned int length) {
            const std::string_view full(topic);
            if(length>8192||full.substr(0,base_.size())!=base_) return;
            const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
            const auto utc=std::time(nullptr);
            controller_->receive(full.substr(base_.size()),
                std::string_view(reinterpret_cast<char *>(payload),length),now,utc,clockValid());
        });
    }
    void loop() {
        if(!valid_||!controller_) return;
        auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        if(!heating::networkConnected()||!client_.connected()) {
            if(wasConnected_) { controller_->disconnected(); wasConnected_=false; }
            if(!heating::networkConnected()||now<nextConnect_) return;
            nextConnect_=now+5000;
            const auto id=cfg_.clientId.empty()?cfg_.base:cfg_.clientId;
            const auto willTopic=base_+"fw/availability";
            if(!client_.connect(id.c_str(),cfg_.username.c_str(),cfg_.password.c_str(),willTopic.c_str(),0,false,"offline",true)) return;
            bool subscriptions=true;
            for(auto suffix:{"ha/open_session","ha/heartbeat","ha/config","ha/observations","ha/user_command","ha/snapshot_request"}) {
                const auto topic=base_+suffix;
                subscriptions=client_.subscribe(topic.c_str(),0)&&subscriptions;
            }
            if(!subscriptions) { client_.disconnect(); return; }
            controller_->connected(now); wasConnected_=true;
            client_.publish(willTopic.c_str(),"online",false);
        }
        const auto utc=std::time(nullptr);
        controller_->tick(now,utc,clockValid());
        client_.loop();
    }
private:
    // Validated SNTP event in main sets this trust flag. A plausible cached or
    // manual wall time is not sufficient after boot; no RTC assumed on E32.
    static bool clockValid();
    config::MqttConfig cfg_; std::string base_;
    WiFiClient network_; PubSubClient client_; NvsControlStore store_;
    std::unique_ptr<ShadowController> controller_;
    uint64_t nextConnect_=0;
    bool valid_=false,wasConnected_=false;
};
}
#endif
