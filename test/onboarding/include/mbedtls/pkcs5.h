#pragma once
#include <cstddef>
#include <cstdint>
#include "mbedtls/md.h"
// Fake ONLY for the native onboarding hardware tests: a deterministic FNV mix
// of password, salt and iteration count. NOT PBKDF2 and not cryptographic;
// test_web_password.cpp checks the record format against real PBKDF2.
namespace testCrypto {inline bool kdfFails=false;inline unsigned kdfCalls=0;}
inline int mbedtls_pkcs5_pbkdf2_hmac(mbedtls_md_context_t *ctx,const unsigned char *password,std::size_t plen,
    const unsigned char *salt,std::size_t slen,unsigned int iterations,uint32_t keyLength,unsigned char *out){
    ++testCrypto::kdfCalls;
    if(!ctx||!ctx->info||!ctx->hmac||testCrypto::kdfFails)return -1;
    for(uint32_t i=0;i<keyLength;++i){
        uint64_t h=1469598103934665603ULL^i^(uint64_t(iterations)<<32);
        for(std::size_t k=0;k<plen;++k)h=(h^password[k])*1099511628211ULL;
        for(std::size_t k=0;k<slen;++k)h=(h^salt[k])*1099511628211ULL;
        out[i]=static_cast<unsigned char>(h>>24);
    }
    return 0;
}
