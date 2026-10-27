#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "ShadowController.h"
#include "ActuatorChannels.h"
#include "ControlUiSnapshot.h"
#include "DeviceDiagnostics.h"
#include "NativeSourceProvisioning.h"
#include "GraphSessionOwner.h"
#include "GraphControlStoreView.h"
#include "TopologyControlStoreView.h"
#include "GraphFloorControlStoreView.h"
#include "ControlPartitionBudget.h"
#include "NvsControlStore.h"
#include "Network.h"
#include "config.h"
#include "DeviceNetworkSettings.h"
#include "DeadlineWiFiClient.h"
#include "AsyncBrokerDns.h"
#include "PendingTcpConnect.h"
#include "ControllerRequestTelemetry.h"
#include <PubSubClient.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <nvs.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
#include <ctime>
#include <atomic>

namespace heating::control {
static_assert(ShadowController::maximumConfigBytes==ControlPartitionBudget::configBytes);
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
    // Trusted LOCAL qualification, never settings or a received capability.
    // No current product call supplies this factory. A session alone provides
    // no authority: its authorizesActuation() remains false.
    using ActuatorFactory=ActuatorChannels::Factory;
    using StatusSnapshot=std::function<void(std::ostream&)>;
    explicit ModernTransport(config::MqttConfig cfg,ShadowController::Metrics metrics={},
                             const GraphSourceProfile* graphProfile=nullptr,
                             const SeasonalControllerSource* seasonalSource=nullptr,
                             SeasonalControllerSource::Safety safety={},
                             const GraphControlHandoffSource* graphHandoff=nullptr,
                             const TopologyControlHandoffSource* topologyHandoff=nullptr,
                             const GraphFloorControlHandoffSource* floorBridge=nullptr,
                             const NativePlanInstallationSource* nativePlanSource=nullptr,
                             ShadowController::BoilerFields boilerFields={},
                             ActuatorFactory actuatorFactory={},StatusSnapshot controllerStatus={})
        :cfg_(std::move(cfg)),client_(network_),
         store_((graphProfile||graphHandoff||topologyHandoff||floorBridge||nativePlanSource||cfg_.nativeSourceRequested)?ControlStorageProfile::graph_shadow_v2:ControlStorageProfile::legacy_api1),
         controllerStatus_(std::move(controllerStatus)),graph_(graphProfile!=nullptr) {
        if(graph_&&actuatorFactory){valid_=false;return;}
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
        if(actuatorFactory) {
            actuatorChannels_=std::make_unique<ActuatorChannels>(std::move(actuatorFactory),
                [this](std::string_view binding,uint64_t now){return controller_->actuatorSessionContext(binding,now);},
                [this]{return valid_&&wasConnected_&&heating::networkConnected()&&client_.connected()&&clockValid();},
                monotonicMs,[this](std::string_view suffix,std::string_view raw,uint64_t deadline){
                    const auto topic=base_+std::string(suffix);
                    if(!actuatorChannels_||!network_.beginDeadlineWrite([this,deadline]{
                            return actuatorChannels_->beforeHandoff(deadline);
                        }))return false;
                    bool published=false,complete=false;
                    try {
                        published=client_.publish(topic.c_str(),
                            reinterpret_cast<const uint8_t*>(raw.data()),raw.size(),false);
                        complete=network_.finishDeadlineWrite();
                    }catch(...){network_.finishDeadlineWrite();actuatorChannels_->retire();network_.stop();throw;}
                    // Partial MQTT frames cannot be followed by another packet.
                    // Close the same socket without a further MQTT write/retry.
                    if(!published||!complete){actuatorChannels_->retire();network_.stop();return false;}
                    return true;
                });
        }
        client_.setCallback([this](char *topic,uint8_t *payload,unsigned int length) {
            const std::string_view full(topic);
            if(length>8192||full.substr(0,base_.size())!=base_) return;
            const auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
            const auto utc=std::time(nullptr);
            const auto suffix=full.substr(base_.size());
            if(suffix.substr(0,18)=="ha/actuator_grant/") {
                // PubSubClient's public callback has no retain metadata. The
                // channel instead requires its outstanding local request,
                // exact fresh session/sequence and original local deadline.
                // This route is not selected by the current product factory.
                if(actuatorChannels_)actuatorChannels_->receive(suffix,
                    std::string_view(reinterpret_cast<char *>(payload),length));
                return;
            }
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
        brokerDns_.cancel();
        brokerTcp_.cancel();
        retireActuators();
        ui_.clear();
        if(controller_)controller_->inhibitNativeSourceMutation();
        valid_=false;
        // Same native availability channel; no logging/private wire.
        if(client_.connected()) {
            client_.publish((base_+"fw/availability").c_str(),"offline",false);
            client_.disconnect();
        }
        network_.stop();
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
            retireActuators();
            cfg_.nativeSourceJson=selection;
            return true;
        } catch(...) {inhibitNativeSourceMutation();return false;}
    }
    void loop() {
        if(!controller_&&!graphController_) return;
        auto now=static_cast<uint64_t>(esp_timer_get_time()/1000);
        if(!valid_) {
            brokerDns_.cancel();
            brokerTcp_.cancel();
            network_.stop();
            // SOURCE lockout also disconnects its owner. It must not freeze an
            // already running local withdrawal deadline or attempt reconnect.
            if(controller_)controller_->tick(now,0,false);
            return;
        }
        if(!heating::networkConnected()||!client_.connected()) {
            if(wasConnected_) { retireActuators(); ui_.clear(); withOwner([](auto& owner){owner.disconnected();}); wasConnected_=false; }
            // Advance local withdrawal deadlines even if network/reconnect fails.
            // Offline owner ticks never publish or consult remote observers.
            withOwner([&](auto& owner){owner.tick(now,0,false);});
            if(!heating::networkConnected()) {brokerDns_.cancel();brokerTcp_.cancel();network_.stop();return;}
            if(now<nextConnect_)return;
            if(!brokerTcp_.started()) {
                network_.stop(); // Release the retired handle even while DNS waits.
                IPAddress address;
                if(!address.fromString(cfg_.brokerAddress.c_str())) {
                    if(!brokerDns_.started())brokerDns_.start(cfg_.brokerAddress,now);
                    const auto resolved=brokerDns_.poll(now);
                    if(resolved.state==AsyncBrokerDns::State::pending)return;
                    brokerDns_.cancel(); // Native DNS remains the only address cache.
                    if(resolved.state!=AsyncBrokerDns::State::ready) {nextConnect_=now+5000;return;}
                    address=resolved.ipv4;
                }
                client_.setServer(address,cfg_.brokerPort);
                brokerTcp_.start(static_cast<uint32_t>(address),cfg_.brokerPort,monotonicMs());
            }
            const auto state=brokerTcp_.poll(monotonicMs());
            if(state==PendingTcpConnect::State::pending)return;
            const auto connectDeadline=brokerTcp_.deadlineMs();
            const auto handoffAt=monotonicMs();
            const int socket=state==PendingTcpConnect::State::ready?brokerTcp_.take(handoffAt):-1;
            brokerTcp_.cancel();nextConnect_=monotonicMs()+5000;
            if(socket<0)return;
            if(!network_.adoptConnectedSocket(socket))return;
            // Allocation/scheduler delay during adoption cannot revive an
            // expired connect attempt or dispatch an MQTT CONNECT afterwards.
            const auto adoptedAt=monotonicMs();
            if(adoptedAt<handoffAt||adoptedAt>=connectDeadline){network_.stop();return;}
            // Public PubSubClient handshake on the ready SAME socket. Its
            // existing one-second CONNACK/read timeout remains separate.
            const auto id=cfg_.clientId.empty()?cfg_.base:cfg_.clientId;
            const auto willTopic=base_+"fw/availability";
            if(!client_.connect(id.c_str(),cfg_.username.c_str(),cfg_.password.c_str(),willTopic.c_str(),0,false,"offline",true)) return;
            bool subscriptions=true;
            for(auto suffix:{"ha/open_session","ha/heartbeat","ha/config","ha/observations","ha/user_command","ha/snapshot_request"}) {
                if(graph_&&(std::string_view(suffix)=="ha/observations"||std::string_view(suffix)=="ha/user_command"))continue;
                const auto topic=base_+suffix;
                subscriptions=client_.subscribe(topic.c_str(),0)&&subscriptions;
            }
            if(actuatorChannels_&&!actuatorChannels_->retired())
                subscriptions=client_.subscribe((base_+"ha/actuator_grant/+").c_str(),0)&&subscriptions;
            if(!subscriptions) { client_.disconnect(); return; }
            now=monotonicMs();
            withOwner([&](auto& owner){owner.connected(now);}); wasConnected_=true; nextDeviceDiagnostics_=0;
            client_.publish(willTopic.c_str(),"online",false);
        }
        const auto utc=std::time(nullptr);
        withOwner([&](auto& owner){owner.tick(now,utc,clockValid());});
        client_.loop();
        if(actuatorChannels_)actuatorChannels_->checkCurrent();
        // Observation only, on the existing native connection. Never control input.
        if(client_.connected() && now>=nextDeviceDiagnostics_) {
            nextDeviceDiagnostics_=now+15000;
            const auto bytes=deviceDiagnosticsJson(ESP.getFreeHeap(), ESP.getMinFreeHeap(),
                ESP.getMaxAllocHeap(), temperatureRead(), now/1000);
            client_.publish((base_+"fw/telemetry/device_status").c_str(),bytes.c_str(),false);
            if(controllerStatus_)try {
                std::ostringstream status;controllerStatus_(status);
                const auto command=controllerRequestTelemetry(status.str());
                if(!command.empty())client_.publish((base_+"fw/telemetry/controller_request").c_str(),command.c_str(),false);
            } catch(const std::exception&) { /* Missing status never supplies a command value. */ }
        }
    }
    // Internal callers use the SAME serialized task as loop(), never a REST,
    // MQTT command or a second task. No current product caller selects this.
    ActuatorChannel* actuatorChannel(std::string_view binding) {
        return actuatorChannels_?actuatorChannels_->get(binding):nullptr;
    }
private:
    static uint64_t monotonicMs(){return static_cast<uint64_t>(esp_timer_get_time()/1000);}
    void retireActuators(){
        if(actuatorChannels_)actuatorChannels_->retire();
    }
    template<class F>void withOwner(F&& action) {
        if(graphController_)action(*graphController_);
        else if(controller_)action(*controller_);
    }
    // Validated SNTP event in main sets this trust flag. A plausible cached or
    // manual wall time is not sufficient after boot; no RTC assumed on E32.
    static bool clockValid();
    config::MqttConfig cfg_; std::string base_,sourceNetworkBase_; // ephemeral bounded<2048, never logged/persisted.
    DeadlineWiFiClient network_; PubSubClient client_; NvsControlStore store_;
    StatusSnapshot controllerStatus_;
    AsyncBrokerDns brokerDns_;
    PendingTcpConnect brokerTcp_;
    std::unique_ptr<GraphControlStoreView> graphControlView_;
    std::unique_ptr<TopologyControlStoreView> topologyControlView_;
    std::unique_ptr<GraphFloorControlStoreView> floorControlView_;
    std::unique_ptr<ShadowController> controller_;
    std::unique_ptr<GraphSessionOwner> graphController_;
    ControlUiSnapshot ui_;
    uint64_t nextConnect_=0,nextDeviceDiagnostics_=0;
    std::atomic<bool> valid_{false},wasConnected_{false};
    bool graph_=false;
    std::unique_ptr<ActuatorChannels> actuatorChannels_;
};
}
#endif
