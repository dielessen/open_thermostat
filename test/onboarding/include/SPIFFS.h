#pragma once
#include "Arduino.h"
constexpr int FILE_READ=0;
struct {String readString(){return "{\"hostname\":\"existing\",\"interface_mode\":\"ethernet\",\"mqtt\":{\"enabled\":false}}";} operator bool() const{return true;}} inline testFile;
struct {auto open(const char*,int){return testFile;}} inline SPIFFS;
