#pragma once
#include <cstddef>
#include <cassert>
#include "bootloader_random.h"
// Fake ONLY for existing native onboarding hardware tests. The real E32 build
// uses pinned SDK mbedTLS; these deterministic bytes are NOT a CSPRNG proof.
struct mbedtls_ctr_drbg_context{bool seeded=false;int reseedInterval=0;unsigned char next=0;};
inline void mbedtls_ctr_drbg_init(mbedtls_ctr_drbg_context *ctx){*ctx={};}
inline int mbedtls_ctr_drbg_seed(mbedtls_ctr_drbg_context *ctx,int (*entropy)(void*,unsigned char*,std::size_t),void *state,const unsigned char*,std::size_t){
    unsigned char sample[32]{};
    ctx->seeded=entropy(state,sample,sizeof(sample))==0&&!testCrypto::seedFails;
    return ctx->seeded?0:-1;
}
inline void mbedtls_ctr_drbg_set_reseed_interval(mbedtls_ctr_drbg_context *ctx,int interval){ctx->reseedInterval=interval;}
inline int mbedtls_ctr_drbg_random(void *state,unsigned char *out,std::size_t size){
    assert(!testCrypto::entropyEnabled);
    auto ctx=static_cast<mbedtls_ctr_drbg_context*>(state);
    if(!ctx->seeded||testCrypto::randomFails)return -1;
    for(std::size_t i=0;i<size;++i)out[i]=ctx->next++;
    return 0;
}
