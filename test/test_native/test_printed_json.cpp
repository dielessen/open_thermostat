#include "diagnostics/PrintedJson.h"
#include <gtest/gtest.h>
#include <cJSON.h>
#include <cstdlib>
#include <memory>
#include <set>
#include <string>
#include <string_view>
using heating::diagnostics::PrintedJson;
using heating::diagnostics::sendJson;
namespace {
// Stands in for the E32 PSRAM hook (main.cpp): every cJSON byte is tracked.
std::set<void*> live;
size_t hookAllocations=0,largest=0;
bool refuse=false;
void *external(size_t size){
    ++hookAllocations;if(size>largest)largest=size;
    if(refuse)return nullptr;
    void *p=std::malloc(size);if(p)live.insert(p);return p;
}
void release(void *p){if(p){live.erase(p);std::free(p);}}
struct ExternalJson {
    ExternalJson(){live.clear();hookAllocations=largest=0;refuse=false;cJSON_Hooks hooks{external,release};cJSON_InitHooks(&hooks);}
    ~ExternalJson(){cJSON_InitHooks(nullptr);}
};
struct FakeServer {
    int code=0;std::string_view type;std::string body;bool hookBuffer=false;
    // The printed text is freed after sendJson returns: inspect it while sending.
    void sendView(int c,std::string_view t,std::string_view b){
        code=c;type=t;body=b;hookBuffer=live.count(const_cast<char*>(b.data()))==1;
    }
};
using Json=std::unique_ptr<cJSON,decltype(&cJSON_Delete)>;
// A /status/heating-sized document (about 7 KB) made of many small nodes.
Json largeDocument(){
    Json root(cJSON_CreateObject(),cJSON_Delete);
    auto *rooms=cJSON_AddArrayToObject(root.get(),"rooms");
    for(int i=0;i<60;++i){
        auto *room=cJSON_CreateObject();cJSON_AddItemToArray(rooms,room);
        cJSON_AddStringToObject(room,"id",("room_"+std::to_string(i)).c_str());
        cJSON_AddStringToObject(room,"status","fallback");
        cJSON_AddNumberToObject(room,"temperature",20.25+i);
        cJSON_AddBoolToObject(room,"demand",i%2);
    }
    return root;
}
}
TEST(PrintedJson, LargeDocumentPrintBuffersComeOnlyFromTheHookNeverFromRealloc) {
    ExternalJson hooks;auto root=largeDocument();
    const size_t treeAllocations=hookAllocations;
    {
        PrintedJson text(root.get());ASSERT_TRUE(text);
        ASSERT_GT(text.view().size(),4096u); // above the SDK's always-internal limit
        // Custom hooks disable cJSON's realloc path: each growth step and the
        // final copy are fresh hook allocations, so none of the print buffers
        // can fall back to heap_caps_realloc_default's internal RAM.
        EXPECT_GT(hookAllocations,treeAllocations);
        EXPECT_GE(largest,text.view().size()+1);
        EXPECT_TRUE(live.count(const_cast<char*>(text.view().data())));
        const std::unique_ptr<char,decltype(&cJSON_free)> reference(cJSON_PrintUnformatted(root.get()),cJSON_free);
        EXPECT_EQ(text.view(),std::string_view(reference.get()));
    }
    root.reset();
    EXPECT_TRUE(live.empty()); // tree and text released through the same hook
}
TEST(PrintedJson, SendJsonWritesThePrintBufferInPlaceWithoutACopy) {
    ExternalJson hooks;auto root=largeDocument();FakeServer server;
    EXPECT_TRUE(sendJson(server,200,root.get()));
    EXPECT_EQ(server.code,200);EXPECT_EQ(server.type,"application/json");
    EXPECT_TRUE(server.hookBuffer); // the body handed to the server IS the hook's buffer
    EXPECT_GT(server.body.size(),4096u);
    root.reset();EXPECT_TRUE(live.empty());
}
TEST(PrintedJson, PrintFailureAnswersOneFixedBodyAndLeaksNothing) {
    ExternalJson hooks;auto root=largeDocument();
    refuse=true;
    FakeServer server;
    EXPECT_FALSE(sendJson(server,200,root.get()));
    EXPECT_EQ(server.code,503);EXPECT_EQ(server.body,"{\"error\":\"status_unavailable\"}");EXPECT_FALSE(server.hookBuffer);
    EXPECT_FALSE(sendJson(server,200,root.get(),"{\"error\":\"history_unavailable\"}"));
    EXPECT_EQ(server.body,"{\"error\":\"history_unavailable\"}");
    refuse=false;root.reset();EXPECT_TRUE(live.empty());
}
TEST(PrintedJson, MissingTreeNeverAllocatesOrSendsAPartialDocument) {
    ExternalJson hooks;FakeServer server;
    PrintedJson text(nullptr);EXPECT_FALSE(text);EXPECT_TRUE(text.view().empty());
    EXPECT_FALSE(sendJson(server,200,nullptr));
    EXPECT_EQ(server.code,503);EXPECT_EQ(hookAllocations,0u);
}
TEST(PrintedJson, SmallDocumentRoundTripsExactly) {
    ExternalJson hooks;FakeServer server;
    Json root(cJSON_CreateObject(),cJSON_Delete);cJSON_AddNumberToObject(root.get(),"latest",1641);
    {
        PrintedJson text(root.get());
        EXPECT_EQ(text.view(),"{\"latest\":1641}");
    }
    EXPECT_TRUE(sendJson(server,201,root.get()));EXPECT_EQ(server.code,201);
    root.reset();EXPECT_TRUE(live.empty());
}
