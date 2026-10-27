#pragma once
#include <sys/socket.h>
#include <unistd.h>
inline int lwip_close(int socket){return ::close(socket);}
