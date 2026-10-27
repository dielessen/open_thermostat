#pragma once
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
int lwip_socket(int,int,int);
int lwip_connect(int,const sockaddr*,socklen_t);
int lwip_fcntl(int,int,int);
int lwip_select(int,fd_set*,fd_set*,fd_set*,timeval*);
int lwip_getsockopt(int,int,int,void*,socklen_t*);
int lwip_setsockopt(int,int,int,const void*,socklen_t);
int lwip_close(int);
