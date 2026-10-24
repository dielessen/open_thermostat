#pragma once
#include "ReleasePolicy.h"
#include <cstring>
#include <type_traits>

namespace heating::update {
// One last SAVED checkpoint, not a command journal or proof of a rollback.
// No clocks, URLs, error strings, credentials or dynamically allocated payload.
enum class UpdateStage : uint32_t { Manifest=1, Download, Verify, Selected, Error };
struct UpdateCheckpoint {
    uint32_t schema=1, attempt=0;
    UpdateStage stage=UpdateStage::Manifest;
    uint32_t received=0, total=0;
    int32_t httpStatus=0;
    char fromVersion[48]{}, targetVersion[48]{}, fromSource[41]{};
    uint8_t reserved[3]{};
};
static_assert(std::is_trivially_copyable_v<UpdateCheckpoint>);
static_assert(sizeof(UpdateCheckpoint)==164);

inline const char *updateStageName(UpdateStage stage) {
    switch(stage) {
    case UpdateStage::Manifest:return "manifest";
    case UpdateStage::Download:return "downloading";
    case UpdateStage::Verify:return "verifying";
    case UpdateStage::Selected:return "boot_slot_selected";
    case UpdateStage::Error:return "error";
    }
    return "unknown";
}
template<size_t N> inline bool terminated(const char (&text)[N]) {
    return std::memchr(text,0,N)!=nullptr;
}
inline bool validCheckpoint(const UpdateCheckpoint &c) {
    return c.schema==1 && c.attempt!=0 &&
        c.stage>=UpdateStage::Manifest && c.stage<=UpdateStage::Error &&
        c.total<=maxImageBytes && c.received<=c.total &&
        c.httpStatus>=-32768 && c.httpStatus<=599 &&
        c.reserved[0]==0 && c.reserved[1]==0 && c.reserved[2]==0 &&
        terminated(c.fromVersion) && terminated(c.targetVersion) && terminated(c.fromSource) &&
        validTag(c.fromVersion) && validTag(c.targetVersion) && hex(c.fromSource,40);
}

// Storage uses one atomic native NVS blob. A failed write retains the previous
// saved checkpoint; the caller exposes save_failed rather than claiming success.
template<class Storage> class UpdateCheckpointJournal {
    Storage &storage_;
    UpdateCheckpoint saved_{};
    bool loaded_=false, available_=false, saveFailed_=false;
public:
    explicit UpdateCheckpointJournal(Storage &storage):storage_(storage){}
    void load() {
        if(loaded_)return;
        loaded_=true;
        UpdateCheckpoint candidate{};
        available_=storage_.read(candidate)&&validCheckpoint(candidate);
        if(available_)saved_=candidate;
    }
    bool begin(const std::string &from,const std::string &source,const std::string &target) {
        load();UpdateCheckpoint next{};
        next.attempt=available_?saved_.attempt+1:1;
        if(!next.attempt)next.attempt=1;
        if(!validTag(from)||!validTag(target)||!hex(source,40)){saveFailed_=true;return false;}
        std::memcpy(next.fromVersion,from.c_str(),from.size()+1);
        std::memcpy(next.targetVersion,target.c_str(),target.size()+1);
        std::memcpy(next.fromSource,source.c_str(),source.size()+1);
        return save(next);
    }
    bool advance(UpdateStage stage,uint32_t received,uint32_t total,int httpStatus) {
        load();if(!available_||saveFailed_)return false;
        auto next=saved_;next.stage=stage;next.received=received;
        next.total=total;next.httpStatus=httpStatus;return save(next);
    }
    const UpdateCheckpoint *saved(){load();return available_?&saved_:nullptr;}
    bool saveFailed()const{return saveFailed_;}
private:
    bool save(const UpdateCheckpoint &next) {
        if(!validCheckpoint(next)||!storage_.write(next)){saveFailed_=true;return false;}
        saved_=next;available_=true;saveFailed_=false;return true;
    }
};
}
