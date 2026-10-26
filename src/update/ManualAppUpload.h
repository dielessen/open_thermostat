#pragma once
#include <cstddef>
#include <string_view>

namespace heating::update {
// One synchronous WebServer request. Native end consumes its OTA handle on
// success AND failure. Boot selection is delayed until the final authenticated
// request handler, after the complete multipart body has been parsed.
class ManualAppUpload {
public:
    enum class Error { none, invalid_size, duplicate_file, not_started, begin_failed,
                       too_large, write_failed, incomplete, end_failed,
                       not_verified, select_failed, cancelled };
    template<class Backend> void reset(Backend &backend) {
        cancel(backend);
        *this = ManualAppUpload{};
    }
    template<class Backend> bool begin(Backend &backend, std::string_view text,
                                       size_t capacity) {
        if(error_!=Error::none) return false;
        if(seen_) return fail(backend, Error::duplicate_file);
        seen_=true;
        size_t size=0;
        if(text.empty() || !capacity) return fail(backend, Error::invalid_size);
        for(const char c:text) {
            if(c<'0' || c>'9' || size>capacity/10 ||
               (size==capacity/10 && size_t(c-'0')>capacity%10))
                return fail(backend, Error::invalid_size);
            size=size*10+size_t(c-'0');
        }
        if(!size) return fail(backend, Error::invalid_size);
        expected_=size;
        if(!backend.begin(size)) return fail(backend, Error::begin_failed);
        open_=true;
        return true;
    }
    template<class Backend> bool append(Backend &backend, const void *bytes, size_t size) {
        if(error_!=Error::none) return false;
        if(!open_) return fail(backend, Error::not_started);
        if(size>expected_-received_) return fail(backend, Error::too_large);
        // WebServer emits a final zero-length WRITE on exact chunk boundaries.
        if(!size) return true;
        if(!bytes || !backend.write(bytes,size)) return fail(backend, Error::write_failed);
        received_+=size;
        return true;
    }
    template<class Backend> bool finish(Backend &backend) {
        if(error_!=Error::none) return false;
        if(!open_) return fail(backend, Error::not_started);
        if(received_!=expected_) return fail(backend, Error::incomplete);
        open_=false; // esp_ota_end always consumes the native handle.
        if(!backend.end()) return fail(backend, Error::end_failed);
        verified_=true;
        return true;
    }
    template<class Backend> bool select(Backend &backend) {
        if(error_!=Error::none) return false;
        if(!verified_ || selected_) return fail(backend, Error::not_verified);
        if(!backend.select()) return fail(backend, Error::select_failed);
        selected_=true;
        return true;
    }
    template<class Backend> void cancel(Backend &backend) {
        if(seen_ && !selected_ && error_==Error::none) fail(backend, Error::cancelled);
        else if(open_) {backend.abort();open_=false;}
    }
    Error error() const {return error_;}
    size_t expected() const {return expected_;}
    size_t received() const {return received_;}
    bool selected() const {return selected_;}
    const char *reason() const {
        switch(error_) {
        case Error::none:return "none";
        case Error::invalid_size:return "invalid_size";
        case Error::duplicate_file:return "duplicate_file";
        case Error::not_started:return "not_started";
        case Error::begin_failed:return "begin_failed";
        case Error::too_large:return "too_large";
        case Error::write_failed:return "write_failed";
        case Error::incomplete:return "incomplete";
        case Error::end_failed:return "end_failed";
        case Error::not_verified:return "not_verified";
        case Error::select_failed:return "select_failed";
        case Error::cancelled:return "cancelled";
        }
        return "invalid_state";
    }
private:
    template<class Backend> bool fail(Backend &backend,Error error) {
        if(open_) {backend.abort();open_=false;}
        if(error_==Error::none) error_=error;
        return false;
    }
    size_t expected_=0,received_=0;
    bool seen_=false,open_=false,verified_=false,selected_=false;
    Error error_=Error::none;
};
}
