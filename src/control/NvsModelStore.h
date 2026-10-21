#pragma once
// SOURCE construction ONLY. Not imported/selected by ModernTransport or main.
// Low-level backend for the existing modelstores/gate, NOT a checkpoint caller.
#include "ControlStore.h"
#include "ModelResourceGate.h"
#include <nvs.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>

namespace heating::control {
inline bool modelSha256(std::string_view bytes,ModelDigest& out) {
    unsigned char hash[32]{};
    if(mbedtls_sha256_ret(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size(),hash,0)!=0) {
        out.fill(0);return false;
    }
    static constexpr char digits[]="0123456789abcdef";
    for(size_t i=0;i<32;++i){out[2*i]=digits[hash[i]>>4];out[2*i+1]=digits[hash[i]&15];}
    return true;
}

class NvsModelStore;
class NvsModelProvider {
public:
    // SOURCE-owned plan, not decoded from capabilities/GUI/config/telemetry.
    explicit NvsModelProvider(ModelResourcePlan plan):gate_(plan),models_(plan.models) {
        if(plan.profile!=ModelResourceProfile::e32_nvs_shadow_v1||!gate_.healthy()
            ||gate_.required().nvsEntries>=ControlPartitionBudget::totalEntries) {fail();return;}
        if(owner_) {owner_->fail();fail();return;}
        owner_=this;selected_=true;
    }
    ~NvsModelProvider(){fail();if(owner_==this)owner_=nullptr;}
    NvsModelProvider(const NvsModelProvider&)=delete;
    NvsModelProvider& operator=(const NvsModelProvider&)=delete;
    ModelResourceGate& gate(){return gate_;}
    bool healthy()const{return selected_&&owner_==this&&gate_.healthy();}
    bool fail(){gate_.fail();return false;}
private:
    friend class NvsModelStore;
    static constexpr const char* nameSpace="ot_models_v1"; // NEVER ot_control/config
    static constexpr const char* keys[3][8]={
        {"warm_0","warm_1","warm_2","warm_3","warm_4","warm_5","warm_6","warm_7"},
        {"coast_0","coast_1","coast_2","coast_3","coast_4","coast_5","coast_6","coast_7"},
        {"curve_0","curve_1","curve_2","curve_3","curve_4","curve_5","curve_6","curve_7"}};
    bool claim(uint8_t zone,ModelKind kind) {
        if(!healthy()||!gate_.owns(zone,kind))return fail();
        const size_t at=static_cast<size_t>(kind)*8+zone;
        if(claims_[at])return fail();
        claims_[at]=true;return true; // no reuse/refund during this provider lifetime
    }
    ControlPartitionStats stats() {
        if(!healthy())return {};
        nvs_stats_t s{};
        const auto partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
        if(!partition||nvs_get_stats("nvs",&s)!=ESP_OK) {fail();return {};}
        ControlPartitionStats result{partition->size,s.total_entries,s.used_entries,s.free_entries,true};
        if(result.partitionBytes!=ControlPartitionBudget::partitionBytes||!result.totalEntries||
            result.totalEntries>ControlPartitionBudget::totalEntries||result.usedEntries>result.totalEntries||
            result.freeEntries>result.totalEntries||result.usedEntries!=result.totalEntries-result.freeEntries) {
            fail();return {};
        }
        return result;
    }
    bool permit(size_t bytes) {
        const auto current=stats();
        // Original ledger reserves config/network namespaces. This additional
        // model namespace must ALSO fit; reserve one more entry, never enlarge quota.
        const auto freeRequired=3+ControlPartitionBudget::blobEntries(ControlPartitionBudget::configBytes)
            +ControlPartitionBudget::entriesPerPage+ControlPartitionBudget::modelEntries(models_);
        if(!healthy()||!ControlPartitionBudget::permitsGraphWrite(current,bytes,models_)
            ||current.freeEntries<freeRequired)return fail();
        return true;
    }
    inline static NvsModelProvider* owner_=nullptr;
    ModelResourceGate gate_;
    ControlModelReservation models_;
    std::array<bool,24> claims_{};
    bool selected_=false;
};
class NvsModelStore final:public ControlStore {
public:
    NvsModelStore(NvsModelProvider& provider,uint8_t zone,ModelKind kind)
        :provider_(provider),key_(nullptr),maximum_(ModelResourceGate::codecBytes(kind)) {
        if(provider_.claim(zone,kind))key_=NvsModelProvider::keys[static_cast<size_t>(kind)][zone];
    }
    NvsModelStore(const NvsModelStore&)=delete;
    NvsModelStore& operator=(const NvsModelStore&)=delete;
    // Unbounded API deliberately unavailable, including empty/config-key access.
    bool load(std::string&)override{return provider_.fail();}
    bool save(std::string_view)override{return provider_.fail();}
    ControlPartitionStats modelPartitionStats()const override{return provider_.stats();}
    bool loadBounded(std::string& out,size_t maximum)override {
        if(!key_||!provider_.healthy())return false;
        if(maximum!=maximum_||out.capacity()>2*maximum_)return provider_.fail();
        // A bounded read/readback is an IO operation too: require current
        // partition evidence, without demanding write quota for a read.
        const auto current=provider_.stats();
        if(!current.valid||!provider_.healthy())return false;
        nvs_handle_t handle{};
        auto err=nvs_open(NvsModelProvider::nameSpace,NVS_READONLY,&handle);
        if(err==ESP_ERR_NVS_NOT_FOUND){if(!provider_.healthy())return false;out.clear();return true;} // no namespace creation
        if(err!=ESP_OK)return provider_.fail();
        struct Close {nvs_handle_t h;~Close(){nvs_close(h);}} close{handle};
        if(!provider_.healthy())return false;
        size_t bytes=0;
        err=nvs_get_blob(handle,key_,nullptr,&bytes);
        if(err==ESP_ERR_NVS_NOT_FOUND){if(!provider_.healthy())return false;out.clear();return true;}
        if(!provider_.healthy()||err!=ESP_OK||!bytes||bytes>maximum_)return provider_.fail(); // BEFORE resize/copy
        try {out.resize(bytes);}catch(...){return provider_.fail();}
        size_t actual=bytes;
        err=nvs_get_blob(handle,key_,out.data(),&actual);
        if(err!=ESP_OK||actual!=bytes){out.clear();return provider_.fail();}
        return provider_.healthy();
    }
    bool saveBounded(std::string_view bytes,size_t maximum)override {
        if(!key_||!provider_.healthy())return false;
        if(maximum!=maximum_||bytes.empty()||bytes.size()>maximum_)return provider_.fail();
        // nvs_open RW may allocate a namespace entry: quota is checked before it.
        if(!provider_.permit(bytes.size()))return false;
        nvs_handle_t handle{};
        if(nvs_open(NvsModelProvider::nameSpace,NVS_READWRITE,&handle)!=ESP_OK)return provider_.fail();
        struct Close {nvs_handle_t h;~Close(){nvs_close(h);}} close{handle};
        // Charge CURRENT namespace/other writes immediately before blob mutation.
        if(!provider_.permit(bytes.size()))return false;
        if(nvs_set_blob(handle,key_,bytes.data(),bytes.size())!=ESP_OK||!provider_.healthy())return provider_.fail();
        if(nvs_commit(handle)!=ESP_OK)return provider_.fail(); // ambiguous: NEVER retry/erase
        return provider_.healthy();
        // Existing Thermal/Coast/CurveModelStore performs its one exact bounded
        // readback. No duplicate backend readback, quota clock or scheduler here.
    }
private:
    NvsModelProvider& provider_;
    const char* key_;
    size_t maximum_;
};
// One provider's bookkeeping + a backend fit even ONE existing per-slot allowance.
// Gate/model/codec/SHA workspace are charged separately by original resource plan.
static_assert(sizeof(NvsModelStore)+sizeof(NvsModelProvider)-sizeof(ModelResourceGate)
    <=ModelResourceGate::backendResidentAllowance,"NVS backend accounting drift");
}
