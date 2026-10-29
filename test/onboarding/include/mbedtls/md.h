#pragma once
// Fake ONLY for the native onboarding hardware tests (DeviceAccess). The E32
// build uses the pinned SDK mbedTLS; this is not a hash implementation.
struct mbedtls_md_info_t{int type;};
enum mbedtls_md_type_t{MBEDTLS_MD_NONE=0,MBEDTLS_MD_SHA256=6};
struct mbedtls_md_context_t{const mbedtls_md_info_t *info=nullptr;bool hmac=false;};
inline const mbedtls_md_info_t *mbedtls_md_info_from_type(mbedtls_md_type_t type){static const mbedtls_md_info_t sha256{MBEDTLS_MD_SHA256};return type==MBEDTLS_MD_SHA256?&sha256:nullptr;}
inline void mbedtls_md_init(mbedtls_md_context_t *ctx){*ctx={};}
inline int mbedtls_md_setup(mbedtls_md_context_t *ctx,const mbedtls_md_info_t *info,int hmac){ctx->info=info;ctx->hmac=hmac!=0;return info?0:-1;}
inline void mbedtls_md_free(mbedtls_md_context_t *ctx){*ctx={};}
