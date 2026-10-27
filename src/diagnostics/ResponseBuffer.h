#pragma once
#include <cstddef>
#include <cstring>
#include <streambuf>
#include <string_view>

namespace heating::diagnostics {
// A single HTTP owner reuses one fixed buffer. Allocation is explicit so E32
// can keep large JSON bodies in PSRAM without changing global allocation policy.
// An allocation failure/overflow invalidates the entire response, not just its
// suffix. Nothing is streamed to the client until serialization has succeeded.
class ResponseBuffer final : public std::streambuf {
public:
    using Allocate=void*(*)(size_t);
    using Release=void(*)(void*);
    static constexpr size_t maximumCapacity=65536;
    ResponseBuffer(size_t capacity,Allocate allocate,Release release)
        :capacity_(capacity),allocate_(allocate),release_(release) {}
    ResponseBuffer(const ResponseBuffer&)=delete;
    ResponseBuffer& operator=(const ResponseBuffer&)=delete;
    ~ResponseBuffer() override {if(bytes_)release_(bytes_);}
    bool reset() {
        failed_=true;setp(nullptr,nullptr);
        if(!capacity_||capacity_>maximumCapacity||!allocate_||!release_)return false;
        if(!bytes_)bytes_=static_cast<char*>(allocate_(capacity_));
        if(!bytes_)return false;
        setp(bytes_,bytes_+capacity_);failed_=false;return true;
    }
    bool failed()const{return failed_;}
    std::string_view view()const {
        return !failed_&&bytes_?std::string_view(bytes_,size_t(pptr()-pbase())):std::string_view{};
    }
protected:
    std::streamsize xsputn(const char *data,std::streamsize count) override {
        if(count==0)return 0;
        if(failed_||count<0||!data||!bytes_||static_cast<size_t>(count)>size_t(epptr()-pptr())) {
            failed_=true;return 0;
        }
        std::memcpy(pptr(),data,static_cast<size_t>(count));
        pbump(static_cast<int>(count));return count;
    }
    int_type overflow(int_type value=traits_type::eof()) override {
        if(!failed_&&traits_type::eq_int_type(value,traits_type::eof()))return traits_type::not_eof(value);
        failed_=true;return traits_type::eof();
    }
private:
    const size_t capacity_;
    Allocate allocate_;
    Release release_;
    char *bytes_=nullptr;
    bool failed_=true;
};
}
