// Production NVS readers/writers, deterministic SDK boundary only.
#define OPENTHERMOSTAT_E32V2
#include "DeviceBluetoothSettings.h"
#include "DeviceNetworkSettings.h"
#include "control/NvsControlStore.h"
#include <cassert>
#include <iostream>
#include <string>
using namespace heating;
bool failConfigAllocation=false;
int main() {
    (void)ESP;
    const std::string key="231d39c1d7cc1ab1aee224cd096db932"; // public protocol fixture
    const std::string network="{\"hostname\":\"fixture\",\"mqtt\":{\"enabled\":false}}";
    const std::string privateSettings="{\"bt\":{\"devices\":{\"schema\":1,\"items\":[[\"5448e68f80a5\",1,1,\""+key+"\",\"Room\"]]}}}";
    unsigned cases=0;const auto pass=[&](const char* label){++cases;std::cout<<"PASS "<<label<<'\n';};
    testNvs::committed.clear();testNvs::handles.clear();testNvs::failCommit.clear();testNvs::corruptRead.clear();testNvs::failOpen.clear();
    assert(readDeviceBluetoothSettings()=="{\"bt\":{}}");assert(testNvs::committed.empty());assert(testNvs::handles.empty());pass("missing read creates no namespace or default write");
    assert(saveDeviceNetworkSettings(String(network.c_str())));assert(saveDeviceBluetoothSettings(privateSettings));
    assert(readDeviceBluetoothSettings()==privateSettings);assert(readDeviceNetworkSettings()==String(network.c_str()));
    assert(std::string(readDeviceNetworkSettings().c_str()).find(key)==std::string::npos);pass("older network reader cannot return the private bindkey");
    testNvs::failOpen="ot_bluetooth";assert(readDeviceBluetoothSettings().empty());pass("NVS open error is unknown, never a default fallback");
    assert(!saveDeviceBluetoothSettings("{\"bt\":{}}"));testNvs::failOpen.clear();assert(readDeviceBluetoothSettings()==privateSettings);pass("NVS write-open error preserves old private data");
    const auto before=testNvs::committed;assert(saveDeviceNetworkSettings(String("{\"hostname\":\"changed\"}")));
    assert(testNvs::committed.at("ot_bluetooth")==before.at("ot_bluetooth"));assert(readDeviceBluetoothSettings()==privateSettings);pass("ordinary network write preserves private configuration and key");
    const auto networkBefore=testNvs::committed.at("ot_network");testNvs::failCommit="ot_bluetooth";
    assert(!saveDeviceBluetoothSettings("{\"bt\":{}}"));assert(readDeviceBluetoothSettings()==privateSettings);assert(testNvs::committed.at("ot_network")==networkBefore);pass("commit refusal preserves previous private blob and network bytes");
    testNvs::failCommit.clear();testNvs::corruptRead="ot_bluetooth";
    assert(!saveDeviceBluetoothSettings("{\"bt\":{}}"));testNvs::corruptRead.clear();assert(readDeviceBluetoothSettings()=="{\"bt\":{}}");pass("ambiguous committed write reports failure rather than claiming the old settings");
    assert(!saveDeviceBluetoothSettings(""));assert(!saveDeviceBluetoothSettings(std::string(2048,'x')));assert(!saveDeviceBluetoothSettings(std::string("{}\0secret",9)));pass("write bounds and embedded NUL rejected");
    assert(saveDeviceBluetoothSettings(std::string(2047,'x')));assert(readDeviceBluetoothSettings().size()==2047);pass("exact 2048-byte blob including terminator fits storage boundary");
    auto& blob=testNvs::committed["ot_bluetooth"]["settings"];blob.back()='x';assert(readDeviceBluetoothSettings().empty());pass("missing terminator has no fallback");
    blob={'{','}',0,'s',0};assert(readDeviceBluetoothSettings().empty());pass("embedded terminator has no truncated fallback");
    blob.resize(2049,'x');assert(readDeviceBluetoothSettings().empty());pass("oversized stored blob has no fallback");
    blob={'x',0};assert(readDeviceBluetoothSettings().empty());pass("undersized stored blob has no fallback");
    testNvs::committed["ot_bluetooth"].erase("settings");assert(readDeviceBluetoothSettings()=="{\"bt\":{}}");assert(testNvs::handles.empty());pass("missing key in existing namespace is read-only empty selection");
    assert(testNvs::committed.at("ot_network")==networkBefore);pass("all private failure cases preserve the unrelated network store");
    const auto allBefore=testNvs::committed;
    const auto noWrite=[&]{const auto opens=testNvs::openCalls;assert(!saveDeviceBluetoothSettings(privateSettings));assert(testNvs::openCalls==opens);assert(testNvs::committed==allBefore);};
    testBluetoothStorage::missingPartition=true;noWrite();testBluetoothStorage::missingPartition=false;pass("missing partition rejected before namespace open");
    testBluetoothStorage::partitionBytes=40960;noWrite();testBluetoothStorage::partitionBytes=20480;pass("wrong partition geometry rejected before namespace open");
    testBluetoothStorage::failStats=true;noWrite();testBluetoothStorage::failStats=false;pass("unreadable fresh stats reject before namespace open");
    const auto statistics=testBluetoothStorage::stats;
    testBluetoothStorage::stats.used_entries=1;noWrite();testBluetoothStorage::stats=statistics;pass("inconsistent stats reject without rewriting any namespace");
    testBluetoothStorage::stats={629,1,630,4};noWrite();testBluetoothStorage::stats=statistics;pass("private data cannot consume control replacement and GC reserve");
    const auto queries=testBluetoothStorage::statsCalls;assert(saveDeviceBluetoothSettings(privateSettings));assert(testBluetoothStorage::statsCalls==queries+1);pass("each valid write uses fresh stats, not a cached budget");
    int modelOwner=0;assert(control::controlModelStorageReservation.claim(&modelOwner,{1,1,1}));
    const auto bytes=privateSettings.size()+1;
    const auto minimum=3+control::ControlPartitionBudget::blobEntries(bytes)+control::ControlPartitionBudget::blobEntries(4096)+control::ControlPartitionBudget::entriesPerPage;
    testBluetoothStorage::stats={630-minimum,minimum,630,4};
    assert(control::ControlPartitionBudget::permitsBluetoothWrite({20480,630,630-minimum,minimum,true},bytes));
    const auto modelOpens=testNvs::openCalls;assert(!saveDeviceBluetoothSettings(privateSettings));assert(testNvs::openCalls==modelOpens);pass("selected model checkpoints keep their reservation against Bluetooth writes");
    control::controlModelStorageReservation.release(&modelOwner);assert(saveDeviceBluetoothSettings(privateSettings));testBluetoothStorage::stats=statistics;pass("only the actual model owner's release removes its future checkpoint reservation");
    control::NvsControlStore graph(control::ControlStorageProfile::graph_shadow_v2);
    std::string config="existing";
    assert(graph.load(config)&&config.empty());pass("missing control namespace remains read-only and creates no defaults");
    testBluetoothStorage::stats=statistics;
    assert(graph.save(std::string(4096,'c')));assert(graph.load(config)&&config==std::string(4096,'c'));
    pass("extracted production control store preserves exact maximum-size roundtrip");
    config="preserved";failConfigAllocation=true;
    assert(!graph.load(config));failConfigAllocation=false;
    assert(config=="preserved"&&testNvs::handles.empty());pass("control allocation failure closes SDK handle and preserves caller bytes");
    assert(control::controlModelStorageReservation.claim(&modelOwner,{1,1,1}));
    testBluetoothStorage::stats={366,264,630,4};
    const auto controlOpens=testNvs::openCalls;
    assert(!graph.save("changed"));assert(testNvs::openCalls==controlOpens);
    pass("actual graph store preserves a live model owner's future checkpoint quota");
    control::controlModelStorageReservation.release(&modelOwner);
    assert(graph.save("changed"));assert(graph.load(config)&&config=="changed");
    pass("actual graph store allows writes after the same resource owner's release");
    testBluetoothStorage::stats=statistics;
    const auto durableBefore=testNvs::committed;const auto invalidOpens=testNvs::openCalls;
    control::NvsControlStore invalid(static_cast<control::ControlStorageProfile>(99));
    assert(!invalid.save("bad")&&!graph.save("")&&!graph.save(std::string(4097,'x')));
    assert(testNvs::openCalls==invalidOpens&&testNvs::committed==durableBefore);
    pass("unknown control profile and invalid sizes create no write namespace");
    testNvs::failCommit="ot_control";assert(!graph.save("replacement"));testNvs::failCommit.clear();
    assert(testNvs::committed==durableBefore&&testNvs::handles.empty());
    pass("failed control commit preserves old control and unrelated stores");
    testBluetoothStorage::failStats=true;const auto statsOpens=testNvs::openCalls;
    assert(!graph.save("replacement"));testBluetoothStorage::failStats=false;
    testBluetoothStorage::missingPartition=true;assert(!graph.save("replacement"));testBluetoothStorage::missingPartition=false;
    assert(testNvs::openCalls==statsOpens&&testNvs::committed==durableBefore);
    pass("unknown live control storage statistics refuse before opening for write");
    testNvs::committed["ot_control"]["config"].resize(4097,'x');config="preserved";
    assert(!graph.load(config)&&config=="preserved"&&testNvs::handles.empty());
    testNvs::committed=durableBefore;
    pass("oversized persisted control blob is rejected without losing caller bytes");
    std::cout<<cases<<" storage cases PASS\n";
}
