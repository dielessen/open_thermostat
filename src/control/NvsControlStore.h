#pragma once
#include "ControlStore.h"
#include "ControlModelStorageReservation.h"
#include <nvs.h>
#include <esp_partition.h>
#include <utility>

namespace heating::control {
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
        if(err!=ESP_OK||size==0||size>ControlPartitionBudget::configBytes) { nvs_close(handle); return false; }
        // Allocation/read failure must close the live SDK handle and preserve
        // the caller's previous bytes. No retry or default replacement.
        struct Close {nvs_handle_t handle;~Close(){nvs_close(handle);}} close{handle};
        try {
            std::string loaded(size,'\0');
            err=nvs_get_blob(handle,"config",loaded.data(),&size);
            if(err!=ESP_OK||size!=loaded.size())return false;
            bytes=std::move(loaded);return true;
        } catch(...) {return false;}
    }
    bool save(std::string_view bytes) override {
        if(bytes.empty()||bytes.size()>ControlPartitionBudget::configBytes) return false;
        if(profile_==ControlStorageProfile::graph_shadow_v2) {
            nvs_stats_t stats{};
            const auto partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
            if(!partition||nvs_get_stats("nvs",&stats)!=ESP_OK
                ||!ControlPartitionBudget::permitsGraphWrite(
                    {partition->size,stats.total_entries,
                     stats.used_entries,stats.free_entries,true},bytes.size(),controlModelStorageReservation.current())) return false;
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

}
