#pragma once
#include "ReleasePolicy.h"
#include <array>
#include <cstring>
namespace heating::update {
enum class OtaVerificationStep { Hash, Image, Readback, Select };
// Executes the same commit gate on host and board; backend owns native SHA/OTA.
template<class Backend> class VerifiedOta {
    Backend &backend_; Manifest manifest_; uint32_t received_=0;
    std::string tail_;std::array<uint8_t,32> header_{};bool started_=false,failed_=false,selected_=false,markerFound_=false,finishing_=false;
public:
    VerifiedOta(Backend &b,const Manifest &m):backend_(b),manifest_(m){}
    ~VerifiedOta(){if(started_&&!selected_)backend_.abort();}
    bool begin(){if(started_||manifest_.size<1024||manifest_.size>maxImageBytes)return false;started_=backend_.begin(manifest_.size);return started_;}
    bool append(const uint8_t *bytes,size_t size) {
        if(!started_||failed_||selected_||!size||size>manifest_.size-received_) {failed_=true;return false;}
        for(size_t i=0;i<size&&received_+i<header_.size();++i)header_[received_+i]=bytes[i];
        if(!backend_.write(bytes,size)){failed_=true;return false;}
        const auto marker=manifest_.marker();
        tail_.append(reinterpret_cast<const char*>(bytes),size);
        markerFound_=markerFound_||tail_.find(marker)!=std::string::npos;
        if(tail_.size()>marker.size())tail_.erase(0,tail_.size()-marker.size());
        received_+=size;return true;
    }
    bool finish() {return finish([](OtaVerificationStep){});}
    template<class Observer> bool finish(Observer before) {
        if(finishing_){failed_=true;return false;}
        if(!started_||failed_||selected_||received_!=manifest_.size||!markerFound_||header_[0]!=0xe9||
           (header_[3]>>4)!=4||header_[12]!=0||header_[13]!=0) return false;
        finishing_=true;
        struct Exit {bool& finishing;~Exit(){finishing=false;}} exit{finishing_};
        // No boot selection before exact length, board marker, streaming hash,
        // native image validation AND an independent partition SHA readback.
        // Finite diagnostic observations immediately BEFORE each backend call.
        // They never replace a gate or assert that its operation completed.
        auto observe=[&](OtaVerificationStep step) {
            try{before(step);return !failed_;}catch(...){failed_=true;return false;}
        };
        if(!observe(OtaVerificationStep::Hash)||!backend_.hashMatches(manifest_.sha256)||
           !observe(OtaVerificationStep::Image)||!backend_.end()||
           !observe(OtaVerificationStep::Readback)||!backend_.readbackMatches(manifest_.size,manifest_.sha256)||
           !observe(OtaVerificationStep::Select)||!backend_.select()) {failed_=true;return false;}
        selected_=true;return true;
    }
    uint32_t received() const{return received_;}
};
}
