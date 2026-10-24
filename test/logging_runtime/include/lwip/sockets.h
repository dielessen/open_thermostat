#pragma once
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
inline bool fail_socket=false,fail_send=false;
inline unsigned send_calls=0;
inline int lwip_socket(int a,int b,int c){return fail_socket?-1:socket(a,b,c);}
inline int lwip_fcntl(int fd,int cmd,int flags){return fcntl(fd,cmd,flags);}
inline int lwip_close(int fd){return close(fd);}
inline int lwip_sendto(int fd,const void* bytes,size_t length,int flags,const sockaddr* to,socklen_t size){++send_calls;return fail_send?-1:int(sendto(fd,bytes,length,flags,to,size));}
