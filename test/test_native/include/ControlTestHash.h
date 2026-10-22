#pragma once
#include <dlfcn.h>
#include <stdexcept>
#include <string>
#include <string_view>

// Test-only public OpenSSL SHA256 ABI. Runtime library already installed on the
// build host; no replacement cryptography implementation or firmware dependency.
inline std::string controlTestHash(std::string_view bytes) {
    using Fn=unsigned char *(*)(const unsigned char *,size_t,unsigned char *);
    static void *library=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);
    static Fn sha=library?reinterpret_cast<Fn>(dlsym(library,"SHA256")):nullptr;
    if(!sha) throw std::runtime_error("Native control tests require existing OpenSSL3 libcrypto");
    unsigned char hash[32];
    if(!sha(reinterpret_cast<const unsigned char *>(bytes.data()),bytes.size(),hash)) throw std::runtime_error("SHA256 failed");
    static constexpr char digits[]="0123456789abcdef";
    std::string out(64,'0');
    for(size_t i=0;i<32;++i) { out[2*i]=digits[hash[i]>>4]; out[2*i+1]=digits[hash[i]&15]; }
    return out;
}
