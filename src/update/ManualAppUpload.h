#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace heating::update {
// One synchronous WebServer request. Native end consumes its OTA handle on
// success AND failure. Boot selection is delayed until the final authenticated
// request handler, after the complete multipart body has been parsed.
//
// boardImage (the E32 V2 build): only an OpenThermostat image for this board,
// as the GitHub path requires (VerifiedOta.h): an ESP32 app header for the
// 16 MB flash and the build marker OT_E32V2_OTA_V1:<tag>:<commit>:<web sha>:END
// somewhere in the image. Without it the upload is aborted before esp_ota_end,
// so it is never validated, selected or booted.
class ManualAppUpload {
public:
    enum class Error { none, invalid_size, duplicate_file, not_started, begin_failed,
                       too_large, write_failed, incomplete, not_openthermostat, end_failed,
                       not_verified, select_failed, cancelled };
    static constexpr std::string_view markerPrefix = "OT_E32V2_OTA_V1:";
    // Prefix, tag (2..47 characters), ':', 40 hex, ':', 64 hex, ":END".
    static constexpr std::size_t markerMaxBytes = 16 + 47 + 1 + 40 + 1 + 64 + 4;
    ManualAppUpload() = default;
    explicit ManualAppUpload(bool boardImage) : boardImage_(boardImage) {}
    template<class Backend> void reset(Backend &backend) {
        cancel(backend);
        *this = ManualAppUpload{boardImage_};
    }
    // The complete build marker at the start of text, as VerifiedOta's manifest
    // marker() has it (ReleasePolicy.h validTag, 40 and 64 lowercase hex).
    static bool markerAt(std::string_view text) {
        if(text.substr(0,markerPrefix.size())!=markerPrefix) return false;
        text.remove_prefix(markerPrefix.size());
        const auto colon=text.find(':');
        if(colon==std::string_view::npos||colon<2||colon>=48||text[0]!='v'||text[1]<'0'||text[1]>'9') return false;
        for(char c:text.substr(0,colon))
            if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='-')) return false;
        text.remove_prefix(colon+1);
        const auto hex=[&](std::size_t n) {
            if(text.size()<n+1||text[n]!=':') return false;
            for(char c:text.substr(0,n)) if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
            text.remove_prefix(n+1); return true;
        };
        return hex(40)&&hex(64)&&text.substr(0,3)=="END";
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
        if(boardImage_) inspect(static_cast<const char*>(bytes),size);
        received_+=size;
        return true;
    }
    template<class Backend> bool finish(Backend &backend) {
        if(error_!=Error::none) return false;
        if(!open_) return fail(backend, Error::not_started);
        if(received_!=expected_) return fail(backend, Error::incomplete);
        // Still open: fail() aborts the native handle, so esp_ota_end never sees it.
        if(boardImage_ && (!markerFound_ || !boardHeader())) return fail(backend, Error::not_openthermostat);
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
        case Error::not_openthermostat:return "not_openthermostat_image";
        case Error::end_failed:return "end_failed";
        case Error::not_verified:return "not_verified";
        case Error::select_failed:return "select_failed";
        case Error::cancelled:return "cancelled";
        }
        return "invalid_state";
    }
private:
    // The ESP32 app header (byte 0 magic 0xE9, byte 3 high nibble 16 MB flash,
    // bytes 12-13 chip id ESP32) and a streaming search for the build marker.
    bool boardHeader() const {
        return header_[0]==0xe9 && (header_[3]>>4)==4 && header_[12]==0 && header_[13]==0;
    }
    void inspect(const char *bytes,std::size_t size) {
        for(std::size_t i=0;i<size&&received_+i<header_.size();++i) header_[received_+i]=uint8_t(bytes[i]);
        if(markerFound_) return;
        tail_.append(bytes,size);
        for(auto at=tail_.find(markerPrefix);at!=std::string::npos;at=tail_.find(markerPrefix,at+1))
            if(markerAt(std::string_view(tail_).substr(at))) { markerFound_=true; tail_.clear(); return; }
        // Keep what may still start a marker that ends in the next chunk.
        if(tail_.size()>markerMaxBytes) tail_.erase(0,tail_.size()-markerMaxBytes);
    }
    template<class Backend> bool fail(Backend &backend,Error error) {
        if(open_) {backend.abort();open_=false;}
        if(error_==Error::none) error_=error;
        return false;
    }
    size_t expected_=0,received_=0;
    bool seen_=false,open_=false,verified_=false,selected_=false;
    bool boardImage_=false,markerFound_=false;
    std::array<uint8_t,16> header_{};
    std::string tail_;
    Error error_=Error::none;
};
}
