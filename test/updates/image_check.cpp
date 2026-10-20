// Drives the production commit gate with an actual release app. Flash/boot are
// host fakes; OpenSSL supplies an independent SHA256 implementation.
#include "update/VerifiedOta.h"
#include <openssl/sha.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <cassert>
using namespace heating::update;
std::string read(const char *path){std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};}
std::string hash(const std::vector<uint8_t> &bytes){uint8_t sum[32];SHA256(bytes.data(),bytes.size(),sum);const char h[]="0123456789abcdef";std::string s;for(auto c:sum){s+=h[c>>4];s+=h[c&15];}return s;}
struct HostFlash {
 std::vector<uint8_t> bytes;unsigned selected=0;bool damageReadback=false;
 bool begin(uint32_t n){bytes.reserve(n);return true;}
 bool write(const uint8_t *p,size_t n){bytes.insert(bytes.end(),p,p+n);return true;}
 bool hashMatches(const std::string &expected){return hash(bytes)==expected;}
 bool end(){return true;}
 bool readbackMatches(uint32_t n,const std::string &expected){auto stored=bytes;if(damageReadback)stored.back()^=1;return stored.size()==n&&hash(stored)==expected;}
 bool select(){++selected;return true;}
 void abort(){}
};
int main(int argc,char **argv){
 assert(argc==3||argc==4);if(argc==4)assert(releaseJson(read(argv[3])));auto raw=read(argv[1]),image=read(argv[2]);auto doc=heating::control::parseControlJson(raw,true);assert(doc);
 Manifest m;assert(parseManifest(raw,string(doc.get(),"version"),m));assert(image.size()==m.size);unsigned passed=0;
 for(int fault=0;fault<5;++fault){HostFlash flash;flash.damageReadback=fault==3;auto bytes=image;auto manifest=m;
  if(fault==1)bytes.back()^=1;if(fault==2)bytes.resize(bytes.size()-1);if(fault==4)manifest.webSha[0]=manifest.webSha[0]=='a'?'b':'a';
  {VerifiedOta<HostFlash> transfer(flash,manifest);assert(transfer.begin());
   for(size_t off=0;off<bytes.size();){const auto n=std::min<size_t>(1460,bytes.size()-off);assert(transfer.append(reinterpret_cast<const uint8_t*>(bytes.data()+off),n));off+=n;}
   assert(transfer.finish()==(fault==0));assert(flash.selected==(fault==0?1u:0u));}
  ++passed;
 }
 std::cout<<passed<<" actual-image production-gate/OpenSSL scenarios PASS; not real flash/boot proof\n";
}
