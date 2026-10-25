#include "control/BleDeviceSettings.h"
#include <gtest/gtest.h>
#include <string>
#include <stdexcept>
#include <vector>

namespace {
using namespace heating::control;
constexpr auto publicKey = "231d39c1d7cc1ab1aee224cd096db932"; // public protocol fixture, not a device secret
ControlJson json(std::string_view source) {
    auto result = parseControlJson(source, true);
    if (!result) throw std::runtime_error("invalid fixture JSON");
    return result;
}
std::string text(const cJSON* value) {
    std::unique_ptr<char, decltype(&cJSON_free)> data(cJSON_PrintUnformatted(value), cJSON_free);
    return data ? std::string(data.get()) : std::string{};
}
ControlJson baseline() { return json(R"({"mqtt":{"password":"fixture-broker","native_shadow_source":["fixture"]},"bt":{"scanTime":60,"scanInterval":60},"unknown":{"keep":true}})"); }
ControlJson request(const std::string& action = "set", const std::string& address = "54:48:E6:8F:80:A5") {
    return json(std::string(R"({"devices":[{"address":")") + address + R"(","profile":"shelly_ht_display","encryption":"bthome_v2","name":"Room – Zoë","key_action":")" + action + '"'
        + (action == "set" ? std::string(",\"bindkey\":\"") + publicKey + '"' : "") + "}]}");
}
ControlJson configured() {
    auto old = baseline(), patch = request();
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed = false;
    if (prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed) != BleSettingsError::none || !changed)
        throw std::runtime_error("failed fixture configuration");
    return candidate;
}
TEST(BleDeviceSettings, ReadingAnOldConfigurationCreatesNoDefaultAndNoMutation) {
    auto old = baseline(); const auto before = text(old.get()); ManagedBleBindings bindings;
    EXPECT_EQ(readManagedBleBindings(old.get(), bindings), BleSettingsError::none);
    EXPECT_EQ(bindings.count, 0); EXPECT_EQ(text(old.get()), before);
}
TEST(BleDeviceSettings, DurableCandidateRoundtripsAndPreservesOtherSettings) {
    auto old = baseline(), patch = request(); const auto before = text(old.get());
    ManagedBleBindings next, restored; ControlJson candidate(nullptr, cJSON_Delete); bool changed = false;
    ASSERT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::none);
    ASSERT_TRUE(changed); ASSERT_TRUE(candidate); EXPECT_EQ(text(old.get()), before);
    EXPECT_TRUE(cJSON_Compare(bleSetting(old.get(), "mqtt"), bleSetting(candidate.get(), "mqtt"), true));
    EXPECT_TRUE(cJSON_Compare(bleSetting(old.get(), "unknown"), bleSetting(candidate.get(), "unknown"), true));
    ASSERT_EQ(readManagedBleBindings(candidate.get(), restored), BleSettingsError::none);
    EXPECT_TRUE(next.same(restored)); ASSERT_EQ(restored.count, 1);
    EXPECT_TRUE(restored.devices[0].hasKey); EXPECT_EQ(std::string(restored.devices[0].name.data()), "Room – Zoë");
    auto publicData = publicManagedBleBindings(restored); ASSERT_TRUE(publicData);
    EXPECT_EQ(text(publicData.get()).find(publicKey), std::string::npos);
    EXPECT_EQ(text(publicData.get()).find("fixture-broker"), std::string::npos);
    EXPECT_TRUE(cJSON_IsFalse(bleSetting(cJSON_GetArrayItem(publicData.get(), 0), "control_qualified")));
}
TEST(BleDeviceSettings, KeepUsesTheExactAddressProfileAndEncryptionAndNoopDoesNotWrite) {
    auto old = configured(), patch = request("keep");
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed = true;
    ASSERT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::none);
    EXPECT_FALSE(changed); EXPECT_FALSE(candidate); EXPECT_TRUE(next.devices[0].hasKey);
    patch = request("keep", "54:48:E6:8F:80:A6");
    ASSERT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::none);
    EXPECT_TRUE(changed); EXPECT_FALSE(next.devices[0].hasKey);
}
TEST(BleDeviceSettings, ExplicitClearRemovesOnlyTheSelectedKeyAndNeverMutatesTheOldRoot) {
    auto old = configured(), patch = request("clear"); const auto before = text(old.get());
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed = false;
    ASSERT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::none);
    EXPECT_TRUE(changed); EXPECT_FALSE(next.devices[0].hasKey);
    EXPECT_EQ(text(candidate.get()).find(publicKey), std::string::npos); EXPECT_EQ(text(old.get()), before);
}
TEST(BleDeviceSettings, InvalidRowAlwaysDiscardsPartialCandidateAndKeys) {
    auto old = configured(), patch = request();
    auto items = cJSON_GetObjectItemCaseSensitive(patch.get(), "devices");
    auto bad = cJSON_Duplicate(cJSON_GetArrayItem(items, 0), true);
    cJSON_ReplaceItemInObjectCaseSensitive(bad, "address", cJSON_CreateString("not-an-address"));
    ASSERT_TRUE(cJSON_AddItemToArray(items, bad));
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed = true;
    EXPECT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::invalid_address);
    EXPECT_EQ(next.count, 0); EXPECT_FALSE(candidate); EXPECT_FALSE(changed);
    for (const auto& device : next.devices) EXPECT_TRUE(std::all_of(device.key.begin(),device.key.end(),[](auto b){return !b;}));
}
TEST(BleDeviceSettings, DuplicateAddressAndNinthSlotAreRejectedInsteadOfEvicting) {
    auto old = baseline(), patch = request(); auto items = cJSON_GetObjectItemCaseSensitive(patch.get(), "devices");
    ASSERT_TRUE(cJSON_AddItemToArray(items, cJSON_Duplicate(cJSON_GetArrayItem(items, 0), true)));
    ManagedBleBindings next; ControlJson candidate(nullptr, cJSON_Delete); bool changed;
    EXPECT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::duplicate_address);
    for (unsigned i = 2; i < 9; ++i) ASSERT_TRUE(cJSON_AddItemToArray(items, cJSON_Duplicate(cJSON_GetArrayItem(items, 0), true)));
    EXPECT_EQ(prepareManagedBleSettings(old.get(), patch.get(), next, candidate, changed), BleSettingsError::invalid_count);
}
TEST(BleDeviceSettings, NetworkReadbackHidesBindingsAndAnOlderFormRetainsThem) {
    auto old = configured(); ControlJson view(cJSON_Duplicate(old.get(), true), cJSON_Delete);
    redactManagedBleSettings(view.get()); EXPECT_EQ(text(view.get()).find(publicKey), std::string::npos);
    EXPECT_EQ(bleSetting(bleSetting(view.get(), "bt"), "devices"), nullptr);
    ASSERT_TRUE(retainManagedBleSettings(old.get(), view.get()));
    EXPECT_TRUE(cJSON_Compare(old.get(), view.get(), true));
    cJSON_DeleteItemFromObjectCaseSensitive(view.get(), "bt");
    ASSERT_TRUE(retainManagedBleSettings(old.get(), view.get())); EXPECT_TRUE(cJSON_Compare(old.get(), view.get(), true));
}
TEST(BleDeviceSettings, UnknownFutureBindingsArePreservedByNetworkRecoveryButNotInterpreted) {
    auto old = json(R"({"bt":{"scanTime":60,"devices":{"schema":99,"items":[],"unknown_secret":"fixture"}},"mqtt":{"password":"fixture"}})");
    auto form = json(R"({"bt":{"scanTime":30},"mqtt":{"password":"fixture"}})");
    ASSERT_TRUE(retainManagedBleSettings(old.get(), form.get()));
    EXPECT_TRUE(cJSON_Compare(bleSetting(bleSetting(old.get(),"bt"),"devices"),bleSetting(bleSetting(form.get(),"bt"),"devices"),true));
    ManagedBleBindings next; EXPECT_EQ(readManagedBleBindings(form.get(), next), BleSettingsError::invalid_shape);
    auto patch = json(R"({"devices":[]})"); ControlJson candidate(nullptr,cJSON_Delete); bool changed;
    EXPECT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::previous_config_invalid);
    patch = json(R"({"devices":[],"reset_invalid":true})");
    EXPECT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::none);
    EXPECT_TRUE(changed); EXPECT_EQ(next.count,0);
}
TEST(BleDeviceSettings, InvalidSecretsAndPrivilegeFieldsAreNeverStoredOrProjected) {
    const std::vector<std::pair<const char*,const char*>> bad{
        {"address", "00:00:00:00:00:00"}, {"address", "ff:ff:ff:ff:ff:ff"},
        {"profile", "shelly_blu_trv"}, {"encryption", "auto"}, {"bindkey", "short"},
        {"bindkey", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}, {"name", "\n"},
        {"name", "                                         "}, {"key_action", "guess"}};
    for (const auto& value : bad) {
        auto old=baseline(),patch=request();auto row=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(patch.get(),"devices"),0);
        cJSON_ReplaceItemInObjectCaseSensitive(row,value.first,cJSON_CreateString(value.second));
        ManagedBleBindings next;ControlJson candidate(nullptr,cJSON_Delete);bool changed;
        EXPECT_NE(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::none)<<value.first;
        EXPECT_FALSE(candidate);EXPECT_EQ(next.count,0);
    }
    auto old=baseline(),patch=request();auto row=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(patch.get(),"devices"),0);
    cJSON_AddBoolToObject(row,"control_qualified",true);
    ManagedBleBindings next;ControlJson candidate(nullptr,cJSON_Delete);bool changed;
    EXPECT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::invalid_shape);
}
TEST(BleDeviceSettings, ZeroAndOversizedInternalCountsCannotIndexOutsideTheFixedArray) {
    ManagedBleBindings bindings,other;ManagedBleAddress address{};
    EXPECT_EQ(bindings.find(address),nullptr);bindings.count=255;
    EXPECT_EQ(bindings.find(address),nullptr);EXPECT_FALSE(bindings.same(other));EXPECT_FALSE(bindings.sort());EXPECT_EQ(bindings.count,0);
}
TEST(BleDeviceSettings, PublicAndCommittedNamesAndKeysAreNeverTruncated) {
    auto old=baseline(),patch=request();auto row=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(patch.get(),"devices"),0);
    cJSON_ReplaceItemInObjectCaseSensitive(row,"name",cJSON_CreateString(std::string(40,'a').c_str()));
    ManagedBleBindings next;ControlJson candidate(nullptr,cJSON_Delete);bool changed;
    ASSERT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::none);
    EXPECT_EQ(std::strlen(next.devices[0].name.data()),40u);
    cJSON_ReplaceItemInObjectCaseSensitive(row,"name",cJSON_CreateString(std::string(41,'a').c_str()));
    EXPECT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::invalid_name);
}
}
TEST(BleDeviceSettings, PublicAndDurableProjectionRejectUnterminatedOrUnknownProfileDTOs) {
    auto b=ManagedBleBindings{};b.count=1;b.devices[0].address={1,2,3,4,5,6};b.devices[0].profile=ManagedBleProfile::shellyHtDisplay;
    b.devices[0].name.fill('x');EXPECT_FALSE(publicManagedBleBindings(b));EXPECT_FALSE(committedManagedBleBindings(b));
    b.devices[0].name.fill(0);b.devices[0].profile=static_cast<ManagedBleProfile>(255);EXPECT_FALSE(publicManagedBleBindings(b));EXPECT_FALSE(committedManagedBleBindings(b));
}
TEST(BleDeviceSettings, AllEightDevicesFitWhenOtherSettingsLeaveEnoughSpace) {
    auto old=baseline();auto patch=json("{\"devices\":[]}");auto rows=cJSON_GetObjectItemCaseSensitive(patch.get(),"devices");
    for(unsigned i=0;i<8;++i){auto one=request("clear");auto row=cJSON_DetachItemFromArray(cJSON_GetObjectItemCaseSensitive(one.get(),"devices"),0);const auto address="5448e68f80a"+std::to_string(i);cJSON_ReplaceItemInObjectCaseSensitive(row,"address",cJSON_CreateString(address.c_str()));ASSERT_TRUE(cJSON_AddItemToArray(rows,row));}
    ManagedBleBindings next;ControlJson candidate(nullptr,cJSON_Delete);bool changed=false;
    ASSERT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::none);EXPECT_EQ(next.count,8);EXPECT_LT(text(candidate.get()).size(),2048u);
}
TEST(BleDeviceSettings, SharedStorageLimitRejectsWholeCandidateAndPreservesExistingSettings) {
    auto old=baseline();for(unsigned i=0;i<4;++i)ASSERT_TRUE(cJSON_AddStringToObject(old.get(),("other"+std::to_string(i)).c_str(),std::string(440,'a').c_str()));const auto before=text(old.get());ASSERT_LT(before.size(),2048u);ASSERT_TRUE(parseControlJson(before,true));auto patch=request();
    ManagedBleBindings next;ControlJson candidate(nullptr,cJSON_Delete);bool changed=false;
    EXPECT_EQ(prepareManagedBleSettings(old.get(),patch.get(),next,candidate,changed),BleSettingsError::settings_too_large);EXPECT_FALSE(candidate);EXPECT_FALSE(changed);EXPECT_EQ(next.count,0);EXPECT_EQ(text(old.get()),before);
}
