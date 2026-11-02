// Production NVS readers/writers, deterministic SDK boundary only.
#define OPENTHERMOSTAT_E32V2
#include "DeviceBluetoothSettings.h"
#include "DeviceNetworkSettings.h"
#include "control/NvsControlStore.h"
#include "LearnedStore.h"
#include "ReadinessStore.h"
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
    // A refusal opens nothing for write (an optional-record probe may read "ot_heating").
    const auto noWrite=[&]{const auto opens=testNvs::writeOpens;assert(!saveDeviceBluetoothSettings(privateSettings));assert(testNvs::writeOpens==opens);assert(testNvs::committed==allBefore);};
    testBluetoothStorage::missingPartition=true;noWrite();testBluetoothStorage::missingPartition=false;pass("missing partition rejected before namespace open");
    testBluetoothStorage::partitionBytes=40960;noWrite();testBluetoothStorage::partitionBytes=20480;pass("wrong partition geometry rejected before namespace open");
    testBluetoothStorage::failStats=true;noWrite();testBluetoothStorage::failStats=false;pass("unreadable fresh stats reject before namespace open");
    const auto statistics=testBluetoothStorage::stats;
    testBluetoothStorage::stats.used_entries=1;noWrite();testBluetoothStorage::stats=statistics;pass("inconsistent stats reject without rewriting any namespace");
    testBluetoothStorage::stats={629,1,630,4};noWrite();testBluetoothStorage::stats=statistics;pass("private data cannot consume control replacement and GC reserve");
    testNvs::committed["ot_heating"]["learned0"]=std::vector<unsigned char>(900,'L');const auto withLearned=testNvs::committed;
    testBluetoothStorage::stats={629,1,630,4};assert(!saveDeviceBluetoothSettings(privateSettings));testBluetoothStorage::stats=statistics;
    assert(testNvs::committed==withLearned&&testNvs::handles.empty());testNvs::committed=allBefore;
    pass("optional records are not erased when even all of them could not make the room");
    const auto queries=testBluetoothStorage::statsCalls;assert(saveDeviceBluetoothSettings(privateSettings));assert(testBluetoothStorage::statsCalls==queries+1);pass("each valid write uses fresh stats, not a cached budget");
    int modelOwner=0;assert(control::controlModelStorageReservation.claim(&modelOwner,{1,1,1}));
    const auto bytes=privateSettings.size()+1;
    // rc.2: the control record's replacement at its stored size plus an edit (none stored here).
    const auto controlEntries=control::ControlPartitionBudget::controlReplacementEntries(0,false);
    const auto minimum=3+control::ControlPartitionBudget::blobEntries(bytes)+controlEntries+control::ControlPartitionBudget::entriesPerPage;
    testBluetoothStorage::stats={630-minimum,minimum,630,4};
    assert(control::ControlPartitionBudget::permitsBluetoothWrite({20480,630,630-minimum,minimum,true},bytes,{},controlEntries));
    const auto modelOpens=testNvs::writeOpens;assert(!saveDeviceBluetoothSettings(privateSettings));assert(testNvs::writeOpens==modelOpens);pass("selected model checkpoints keep their reservation against Bluetooth writes");
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
    const auto controlOpens=testNvs::writeOpens;
    assert(!graph.save("changed"));assert(testNvs::writeOpens==controlOpens);
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
    // --- rc.2 learned-room review: the packed learned record, a control record that makes
    // room, the rollback's room and the unconfirmed boot (NvsOptionalRecords.h, LearnedStore.h).
    using B=control::ControlPartitionBudget;
    const auto entries=[](const char* space){size_t n=0;for(const auto& [k,v]:testNvs::committed[space])n+=2+(v.size()+31)/32;return n;};
    testNvs::committed.clear();control::graphControlStorage.store(false);
    testBluetoothStorage::baseline=198; // the owner's unit (beta.19 post-install capture)
    testNvs::committed["ot_heating"]["plan"]=std::vector<unsigned char>(930,'p');
    testNvs::committed["ot_bluetooth"]["settings"]=std::vector<unsigned char>(600,'b');
    testNvs::committed["ot_control"]["config"]=std::vector<unsigned char>(200,'c');
    testBluetoothStorage::baseline=198-entries("ot_heating")-entries("ot_bluetooth")-entries("ot_control");
    assert(testBluetoothStorage::usedEntries()==198);
    LearnedNvs learned;std::string back;
    const std::string part(1760,'L'); // the globals and 8 rooms of 6 bins (version 2 frames)
    assert(!learned.read(0,back));
    assert(learned.write(0,part)&&learned.read(0,back)&&back==part);
    assert(learned.write(1,std::string(600,'M'))&&learned.read(1,back)&&back.size()==600);
    assert(learned.erase(1)&&!learned.read(1,back)&&learned.erase(1));
    pass("the packed learned record is written, read back and erased under its own keys");
    // Replacing it needs only its growth (its old entries come back), never control's room.
    const auto reserve=[]{return B::controlReserveEntries(930,B::controlReplacementEntries(200,false));};
    assert(testBluetoothStorage::usedEntries()+reserve()<=630);
    assert(learned.write(0,std::string(4000,'L'))); // the owner's unit: even a full first part fits
    const auto grown=testNvs::committed;
    assert(!learned.write(1,std::string(4000,'M'))&&testNvs::committed==grown);
    assert(630-testBluetoothStorage::usedEntries()>=reserve());
    assert(learned.write(0,std::string(1800,'L'))); // shrinking always fits
    pass("a learned record that would take control's room is refused, the stored ones kept");
    // Earlier rc.2 builds: one key per frame, read and erased through the same backend.
    testNvs::committed["ot_heating"]["learned"]=std::vector<unsigned char>(240,'G');
    testNvs::committed["ot_heating"]["learned3"]=std::vector<unsigned char>(353,'R');
    assert(learned.readLegacy(0,back)&&back.size()==240&&learned.readLegacy(4,back)&&back.size()==353&&!learned.readLegacy(1,back));
    assert(learned.eraseLegacy(0)&&learned.eraseLegacy(4)&&learned.eraseLegacy(1)&&!testNvs::committed["ot_heating"].count("learned3"));
    pass("the per-frame keys of earlier rc.2 builds are read and erased");
    // A larger Home Assistant control record (rooms added) makes room for itself, the learned record first.
    testNvs::committed["ot_heating"]["readiness"]=std::vector<unsigned char>(176,'r');
    testNvs::committed["ot_heating"]["autotune"]=std::vector<unsigned char>(1421,'t');
    const auto evicted=optionalRecordEvictions().load();
    control::NvsControlStore plain;
    while(630-testBluetoothStorage::usedEntries()>=2+B::blobEntries(4000)+B::entriesPerPage)
        testNvs::committed["ot_other"][std::to_string(testNvs::committed["ot_other"].size())]=std::vector<unsigned char>(64,'x');
    assert(plain.save(std::string(4000,'c'))&&!plain.lastSaveRefused());
    assert(optionalRecordEvictions().load()>evicted&&!testNvs::committed["ot_heating"].count("learned_a"));
    assert(testNvs::committed["ot_heating"].count("autotune")&&testNvs::committed["ot_heating"].count("plan"));
    pass("a larger plain control record erases the learned record to make room, the knobs and the plan stay");
    // A graph profile keeps permitsGraphWrite's full margin: its save makes that room the same way.
    testNvs::committed.erase("ot_other");
    testNvs::committed["ot_heating"]["learned_a"]=std::vector<unsigned char>(3600,'L');
    while(B::permitsGraphWrite({20480,630,testBluetoothStorage::usedEntries(),630-testBluetoothStorage::usedEntries(),true},4000))
        testNvs::committed["ot_other"][std::to_string(testNvs::committed["ot_other"].size())]=std::vector<unsigned char>(64,'x');
    control::NvsControlStore graphStore(control::ControlStorageProfile::graph_shadow_v2);
    assert(control::graphControlStorage.load()&&controlReplacementEntries()==B::blobEntries(4096));
    assert(graphStore.save(std::string(4000,'g'))&&!testNvs::committed["ot_heating"].count("learned_a"));
    pass("a graph profile's control save makes its full margin from the optional records; the reserve follows the profile");
    control::graphControlStorage.store(false);testNvs::committed.erase("ot_other");
    testNvs::committed["ot_control"]["config"]=std::vector<unsigned char>(200,'c');
    // While the boot is unconfirmed (a bootloader rollback may follow) the previous firmware's ledger applies.
    const auto fits=[](){return optionalHeatingRecordFits("learned_a",3000);};
    testNvs::committed["ot_heating"].erase("learned_a");
    while(fits())testNvs::committed["ot_other"][std::to_string(testNvs::committed["ot_other"].size())]=std::vector<unsigned char>(64,'x');
    testNvs::committed["ot_other"].erase(std::to_string(testNvs::committed["ot_other"].size()-1));
    assert(fits());testBluetoothStorage::bootPending=true;assert(!fits());testBluetoothStorage::bootPending=false;assert(fits());
    pass("an unconfirmed boot keeps the previous firmware's room free of optional records");
    // A requested rollback: no optional record any more, and the previous firmware's room made.
    testNvs::committed.erase("ot_other");
    assert(learned.write(0,std::string(3000,'L'))&&ReadinessNvs::write(control::TakeoverReadiness::Stored{}));
    while(learned.write(1,std::string(testNvs::committed["ot_heating"].count("learned_b")?testNvs::committed["ot_heating"]["learned_b"].size()+200:200,'M'))){}
    const auto previousRoom=[]{return 630-testBluetoothStorage::usedEntries()>=B::previousFirmwareReserveEntries(930,600);};
    assert(!previousRoom());
    assert(prepareNvsForPreviousFirmware()&&previousRoom()&&optionalRecordsFrozen().load());
    assert(!learned.write(1,"x")&&!ReadinessNvs::write(control::TakeoverReadiness::Stored{}));
    assert(testNvs::committed["ot_heating"].count("plan")&&testNvs::committed["ot_bluetooth"].count("settings")&&testNvs::committed["ot_control"].count("config"));
    assert(B::permitsHeatingPlanWrite({20480,630,testBluetoothStorage::usedEntries(),630-testBluetoothStorage::usedEntries(),true},930+64));
    pass("before a rollback the optional records stop and make the previous firmware's plan-save room");
    optionalRecordsFrozen().store(false);
    testBluetoothStorage::baseline.reset();
    std::cout<<cases<<" storage cases PASS\n";
}
