#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <utility>

namespace heating::control {
// A synchronous write scope, not a queue or a client. Check is the SAME owner's
// current availability/monotonic deadline fence; send must be one NONBLOCKING
// handoff. Partial/failed/late IO is never retried in this scope.
class DeadlineWrite {
public:
    using Check=std::function<bool()>;
    DeadlineWrite()=default;
    DeadlineWrite(const DeadlineWrite&)=delete;
    DeadlineWrite& operator=(const DeadlineWrite&)=delete;
    bool begin(Check check) {
        if(active_||busy_){failed_=true;return false;}
        if(!check)return false;
        check_=std::move(check);active_=true;failed_=false;wrote_=false;return true;
    }
    bool active()const{return active_;}
    bool finish() {
        if(busy_){failed_=true;return false;}
        const bool complete=active_&&!failed_&&wrote_;
        busy_=true;active_=false;check_={};busy_=false;
        return complete&&!failed_;
    }
    template<class Send>size_t write(const uint8_t* bytes,size_t size,Send&& send) {
        if(!active_||failed_)return 0;
        if(busy_||(!bytes&&size)){failed_=true;return 0;}
        busy_=true;
        struct Exit{bool& busy;~Exit(){busy=false;}} exit{busy_};
        size_t written=0;
        try {
            if(!check_()||failed_){failed_=true;return 0;}
            if(!size)return 0;
            wrote_=true;
            written=send(bytes,size);
            if(written>size){failed_=true;return 0;}
            if(written!=size)failed_=true;
            // A successful syscall may have returned after its original budget.
            // Preserve actual byte count; finish() reports the uncertain scope.
            if(!check_())failed_=true;
            return written;
        }catch(...){failed_=true;return written<=size?written:0;}
    }
private:
    Check check_;
    bool active_=false,busy_=false,failed_=false,wrote_=false;
};
}
