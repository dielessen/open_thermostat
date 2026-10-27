#pragma once
#include <cstdint>
using err_t=int;
using u8_t=uint8_t;
constexpr err_t ERR_OK=0,ERR_MEM=-1,ERR_ARG=-16,ERR_INPROGRESS=-5;
constexpr unsigned DNS_MAX_NAME_LENGTH=256,LWIP_DNS_ADDRTYPE_IPV4=0;
struct ip4_addr_t {uint32_t addr;};
struct ip_addr_t {ip4_addr_t ipv4{};bool isV4=true;};
inline bool IP_IS_V4(const ip_addr_t* ip){return ip->isV4;}
inline const ip4_addr_t* ip_2_ip4(const ip_addr_t* ip){return &ip->ipv4;}
inline uint32_t ip4_addr_get_u32(const ip4_addr_t* ip){return ip->addr;}
using dns_found_callback=void(*)(const char*,const ip_addr_t*,void*);
err_t dns_gethostbyname_addrtype(const char*,ip_addr_t*,dns_found_callback,void*,u8_t);
