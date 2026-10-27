#include <cstdint>
#include <gtest/gtest.h>
namespace {
uint32_t httpTestNow;
uint32_t millis(){ return httpTestNow; }
enum {HC_NONE, HC_WAIT_READ, HC_WAIT_CLOSE};
struct FakeClient {
    bool connectedValue=true;
    unsigned bytes=0, stops=0;
    bool connected()const{return connectedValue;}
    unsigned available()const{return bytes;}
    void stop(){connectedValue=false;++stops;}
};
struct PinnedServerSurface {
    int _currentStatus=HC_WAIT_READ;
    uint32_t _statusChange=100;
    FakeClient _currentClient;
    unsigned calls=0;
    void handleClient(){++calls;if(!_currentClient.connected())_currentStatus=HC_NONE;}
};
}
#include "control/ResponsiveHttpServer.h"
using HttpServer=heating::control::ResponsiveHttpServer<PinnedServerSurface>;
TEST(HttpInitialWait, EmptyConnectionIsRetiredAtBoundaryAndSdkStillRuns){
    HttpServer s;httpTestNow=349;s.handleClient();EXPECT_EQ(s._currentClient.stops,0u);
    httpTestNow=350;s.handleClient();EXPECT_EQ(s._currentClient.stops,1u);EXPECT_EQ(s._currentStatus,HC_NONE);EXPECT_EQ(s.calls,2u);
}
TEST(HttpInitialWait, AvailableRequestDataIsNeverDiscardedForBeingOld){
    HttpServer s;s._currentClient.bytes=1;httpTestNow=10000;s.handleClient();EXPECT_EQ(s._currentClient.stops,0u);EXPECT_EQ(s.calls,1u);
}
TEST(HttpInitialWait, OtherStatesAndDisconnectedClientStayWithSdk){
    for(int state:{HC_NONE,HC_WAIT_CLOSE}){HttpServer s;s._currentStatus=state;httpTestNow=10000;s.handleClient();EXPECT_EQ(s._currentClient.stops,0u);}
    HttpServer s;s._currentClient.connectedValue=false;s.handleClient();EXPECT_EQ(s._currentClient.stops,0u);EXPECT_EQ(s._currentStatus,HC_NONE);
}
TEST(HttpInitialWait, ClockWrapStillAppliesTheSameDeadline){
    HttpServer s;s._statusChange=UINT32_MAX-99;httpTestNow=149;s.handleClient();EXPECT_EQ(s._currentClient.stops,0u);
    httpTestNow=150;s.handleClient();EXPECT_EQ(s._currentClient.stops,1u);
}
