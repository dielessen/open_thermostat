#pragma once
// Native onboarding hardware boundary only; never a firmware entropy source.
namespace testCrypto {
inline bool entropyEnabled=false,seedFails=false,randomFails=false;
inline unsigned enables=0,disables=0,entropyCalls=0;
}
inline void bootloader_random_enable(){testCrypto::entropyEnabled=true;++testCrypto::enables;}
inline void bootloader_random_disable(){testCrypto::entropyEnabled=false;++testCrypto::disables;}
