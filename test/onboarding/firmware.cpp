// Executes production SetupNetwork/DeviceAccess/WifiDiscovery functions. Only
// radio, monotonic clock, filesystem, NVS and RNG hardware APIs are deterministic fakes.
// Fake RNG lifecycle checks are not cryptographic/entropy or real-device proof.
#define OPENTHERMOSTAT_E32V2
#include "SetupNetwork.h"
#include <algorithm>
#include <cassert>
#include <iostream>
namespace heating {bool boardEthernetStarted=false,wifiAPMode=false;}
config::NetworkConfig testNetwork;
namespace config {WiFiConfig getWiFiConfig(){WiFiConfig cfg;heating::readSetupWifi(cfg);return cfg;}NetworkConfig getNetworkConfig(){return testNetwork;}}
using namespace heating;
int cases=0;
void pass(const char* name){++cases;std::cout<<"PASS "<<name<<'\n';}
void reset(){
 testNvs::committed.clear();testNvs::handles.clear();testNvs::failCommit.clear();testNvs::corruptRead.clear();
 WiFi={};testNow=1000;testNetwork={};boardEthernetStarted=false;wifiAPMode=false;
 setupUntil=setupAttemptUntil=setupCloseAt=setupJoinAt=0;setupCandidate={};setupResult="idle";
 setupDns={};setupDnsActive=false;setupSavedSsid.clear();setupCloseIP=IPAddress();
 setupRebootRequested=false;setupRestartHeld=false;wifiScanState="idle";wifiScanRows="[]";wifiScanStarted=0;
 deviceAccess={};deviceAccess.begin();
}
void ap(){assert(startSetupWifi());assert(WiFi.ap);assert(WiFi.bluetoothEnabled&&WiFi.getSleep()==WIFI_PS_MIN_MODEM);}
void join(){assert(trySetupWifi({"home","test-pass"}));testNow+=751;pollSetupWifi();}
void connected(){WiFi.connected=true;WiFi.ip=IPAddress(192,168,1,90);pollSetupWifi();}
int main(){
 reset();testNvs::committed["ot_access"]["secret"]={1,2,3};assert(deviceAccess.begin());
 assert(deviceAccess.defaultPassword()&&deviceAccess.verifyPassword("admin")&&!deviceAccess.verifyPassword("admin ")&&!deviceAccess.verifyPassword("")&&deviceAccess.setupPassword()=="openthermostat");assert(testNvs::committed["ot_access"]["secret"].size()==3);pass("requested defaults supersede old access secret without NVS erase");
 ap();assert(WiFi.modeValue==WIFI_AP_STA&&!WiFi.persist&&!WiFi.reconnect);assert(WiFi.apPassword=="openthermostat");pass("AP+STA established once before any scan/join");
 int modes=WiFi.modeChanges;assert(startWifiScan());assert(WiFi.scanAsync&&WiFi.scans==1);pollSetupWifi();assert(WiFi.modeChanges==modes&&WiFi.ap&&wifiScanRunning());assert(!trySetupWifi({"home","test-pass"}));pass("async scan keeps HTTP/radio mode and excludes concurrent join");
 WiFi.rows={{"a\"\\b",-40,6},{"",-30,1},{"second",-65,11}};WiFi.complete=3;pollSetupWifi();
 assert(wifiScanState=="done");auto parsed=cJSON_Parse(wifiScanRows.c_str());assert(parsed&&cJSON_GetArraySize(parsed)==2);assert(std::string(cJSON_GetObjectItem(cJSON_GetArrayItem(parsed,0),"ssid")->valuestring)=="a\"\\b");cJSON_Delete(parsed);pass("scan results serialize special SSIDs and skip hidden names");
 reset();ap();WiFi.complete=0;assert(startWifiScan());pollSetupWifi();assert(wifiScanState=="done"&&wifiScanRows=="[]");pass("empty scan is a successful empty result");
 reset();ap();WiFi.complete=WIFI_SCAN_FAILED;assert(!startWifiScan());assert(wifiScanState=="failed");pass("scan start error is not an empty success");
 reset();ap();assert(startWifiScan());testNow+=10001;pollSetupWifi();assert(wifiScanState=="failed"&&WiFi.ap);pass("bounded stuck scan leaves setup AP alive");
 reset();ap();auto before=testNow;assert(trySetupWifi({"hidden","test-pass"}));assert(WiFi.joins==0);pollSetupWifi();assert(WiFi.joins==0);assert(!startWifiScan());assert(!trySetupWifi({"other","test-pass"}));
 testNow=before+751;pollSetupWifi();assert(WiFi.joins==1&&WiFi.joined=="hidden"&&WiFi.ap&&WiFi.modeChanges==1);pass("join queued after response, scans/duplicate joins fenced");
 testNow+=30001;pollSetupWifi();assert(setupResult=="connection_failed"&&WiFi.ap&&setupAttemptUntil==0);config::WiFiConfig cfg;assert(!readSetupWifi(cfg));assert(!finishSetupWifi());pass("wrong password does not save or close setup");
 join();connected();assert(setupResult=="connected_saved"&&readSetupWifi(cfg)&&cfg.ssid=="home");assert(readDeviceNetworkSettings().find("existing")!=std::string::npos&&readDeviceNetworkSettings().find("wifi")!=std::string::npos);pass("retry saves WiFi with readback and preserves network settings");
 testNow+=11000;pollSetupWifi();assert(WiFi.ap&&setupCloseAt==0);assert(finishSetupWifi());pollSetupWifi();assert(WiFi.ap);testNow+=8001;pollSetupWifi();assert(!WiFi.ap&&WiFi.modeValue==WIFI_STA);pass("AP waits for page acknowledgement, then automatic finish closes after grace");
 auto durable=testNvs::committed;reset();testNvs::committed=durable;assert(readSetupWifi(cfg)&&cfg.ssid=="home");assert(readDeviceNetworkSettings().find("wifi")!=std::string::npos);pass("accepted WiFi and interface selection survive fresh runtime");
 reset();ap();testNvs::failCommit="ot_wifi";join();connected();assert(setupResult=="storage_error"&&WiFi.ap&&!finishSetupWifi());assert(!readSetupWifi(cfg));pass("NVS credential commit failure keeps recovery and rejects success");
 reset();ap();testNvs::failCommit="ot_network";join();connected();assert(setupResult=="storage_error"&&WiFi.ap&&!finishSetupWifi());pass("network-interface commit failure cannot claim handoff success");
 reset();ap();join();testNvs::corruptRead="ot_wifi";connected();assert(setupResult=="storage_error"&&WiFi.ap);pass("corrupt readback never claims saved connection");
 reset();ap();join();WiFi.connected=true;WiFi.ip={};pollSetupWifi();assert(setupResult=="connecting");pass("association without DHCP is not successful onboarding");
 reset();ap();join();WiFi.connected=true;WiFi.joined="different";WiFi.ip=IPAddress(192,168,1,1);pollSetupWifi();assert(setupResult=="connecting");pass("unrelated station connection cannot save candidate credentials");
 reset();boardEthernetStarted=true;assert(!startSetupWifi()&&!startWifiScan());assert(WiFi.modeValue==0);pass("Ethernet-clock guard prevents powering up WiFi");
 reset();ap();assert(!trySetupWifi({"","test-pass"})&&!trySetupWifi({"home","short"})&&!trySetupWifi({std::string(33,'x'),"test-pass"}));assert(trySetupWifi({"open",""}));pass("invalid lengths rejected and open-network manual entry supported");
 reset();ap();testNow=setupUntil+1;pollSetupWifi();assert(!WiFi.ap&&setupResult=="setup_expired");pass("bounded setup window closes normally");
 reset();ap();join();connected();assert(finishSetupWifi());testNow+=8001;pollSetupWifi();assert(!WiFi.ap&&setupResult=="connected_saved");
 WiFi.connected=false;WiFi.ip={};testNetwork.hostname="ot-test";ap();WiFi.reconnect=false;const int joins=WiFi.joins;testNow=setupUntil+1;pollSetupWifi();
 assert(!WiFi.ap&&setupResult=="setup_expired"&&WiFi.joins==joins+1&&WiFi.joined=="home"&&WiFi.hostname=="ot-test"&&WiFi.reconnect&&WiFi.modeValue==WIFI_STA);pass("expired setup rejoins the saved Wi-Fi at once");
 reset();ap();join();connected();assert(finishSetupWifi());testNow+=8001;pollSetupWifi();WiFi.connected=false;testNetwork.interfaceMode="ethernet";ap();
 {const int joins=WiFi.joins;testNow=setupUntil+1;pollSetupWifi();assert(setupResult=="setup_expired"&&WiFi.joins==joins);}pass("expired setup on Ethernet does not start Wi-Fi");
 reset();ap();join();connected();assert(finishSetupWifi());WiFi.connected=false;testNow+=8001;pollSetupWifi();assert(WiFi.ap&&setupCloseAt==0);pass("station loss during finish grace period preserves recovery AP");
 reset();ap();join();connected();assert(trySetupWifi({"wrong-new-network","test-pass"}));testNow+=751;pollSetupWifi();testNow+=30001;pollSetupWifi();assert(setupResult=="connection_failed"&&readSetupWifi(cfg)&&cfg.ssid=="home");pass("failed replacement preserves previously accepted credentials");
 reset();Serial.input="setup\n";pollSetupWifi();assert(setupRebootRequested);setupRebootRequested=false;assert(consumeSetupBoot()&&!consumeSetupBoot());pass("USB recovery flag is durable and one-shot");
 reset();setupRestartHeld=true;Serial.input="setup\n";pollSetupWifi();pollSetupWifi();assert(setupRebootRequested);setupRestartHeld=false;
 {bool restarted=false;try{pollSetupWifi();}catch(const std::runtime_error&){restarted=true;}assert(restarted);}pass("USB setup restart waits for an update or unconfirmed new firmware");
 reset();WiFi.sleepPolicy=WIFI_PS_NONE;ap();assert(WiFi.modeChanges==1);pass("setup selects BLE-compatible modem sleep before radio start even from disabled policy");
 assert(startWifiScan());WiFi.complete=0;pollSetupWifi();join();connected();assert(finishSetupWifi());testNow+=8001;pollSetupWifi();assert(!WiFi.ap&&WiFi.bluetoothEnabled&&WiFi.getSleep()==WIFI_PS_MIN_MODEM);pass("Bluetooth-compatible policy survives scan join and station handoff");
 reset();WiFi.modeOk=false;assert(!startSetupWifi()&&!wifiAPMode&&!WiFi.ap);pass("radio startup failure never advertises setup success");
 reset();WiFi.apOk=false;assert(!startSetupWifi()&&!wifiAPMode&&!WiFi.ap);pass("SoftAP startup failure never advertises setup success");
 reset();ap();assert(setupDns.active&&setupDns.ttl==0&&setupDns.port==53&&setupDns.domain=="*");assert(uint32_t(setupDns.resolved)==uint32_t(IPAddress(10,10,10,1)));pollSetupWifi();assert(setupDns.polls==1);pass("official wildcard DNS starts at setup IP with zero TTL and nonblocking poll");
 join();connected();assert(setupConnectionReady()&&finishSetupWifi());auto deadline=setupCloseAt;testNow+=2000;assert(finishSetupWifi()&&setupCloseAt==deadline);pollSetupWifi();assert(WiFi.ap&&setupDns.active);testNow=deadline+1;pollSetupWifi();assert(!WiFi.ap&&!setupDns.active&&!setupDnsActive&&setupCloseAt==0);auto polls=setupDns.polls;pollSetupWifi();assert(setupDns.polls==polls);pass("lost finish response is idempotent and DNS stops exactly with setup AP");
 reset();ap();testNow=setupUntil+1;pollSetupWifi();assert(!setupDns.active&&!setupDnsActive);pass("setup timeout also stops DNS");
 reset();setupDns.startOk=false;ap();assert(!setupDnsActive&&WiFi.ap);pollSetupWifi();assert(setupDns.polls==0);pass("DNS bind failure retains numeric-URL recovery without claiming DNS active");
 reset();ap();join();connected();assert(finishSetupWifi());WiFi.ip=IPAddress(192,168,1,91);testNow+=8001;pollSetupWifi();assert(WiFi.ap&&!setupCloseAt);assert(finishSetupWifi());testNow+=8001;pollSetupWifi();assert(!WiFi.ap);pass("DHCP address change cancels old deadline and requires a fresh page acknowledgement");
 reset();ap();join();connected();WiFi.joined="other";assert(!setupConnectionReady()&&!finishSetupWifi());pass("unrelated station cannot inherit saved-network success");
 deviceAccess={};testCrypto::seedFails=true;assert(!deviceAccess.begin()&&!deviceAccess.ready());assert(!testCrypto::entropyEnabled);pass("failed seed fails closed and always disables boot entropy");
 testCrypto::seedFails=false;deviceAccess={};assert(deviceAccess.begin());auto seeds=testCrypto::enables;auto entropyCalls=testCrypto::entropyCalls;unsigned char random[32]{};assert(deviceAccess.randomBytes(random,sizeof(random)));assert(deviceAccess.begin());assert(testCrypto::enables==seeds&&testCrypto::entropyCalls==entropyCalls&&!testCrypto::entropyEnabled);pass("runtime random and repeated begin never toggle or reseed boot entropy");
 testCrypto::randomFails=true;assert(!deviceAccess.randomBytes(random,sizeof(random)));testCrypto::randomFails=false;assert(deviceAccess.randomBytes(random,sizeof(random)));pass("native RNG failure is propagated rather than issuing random bytes");
 reset();assert(deviceAccess.storePassword("correct horse"));assert(!deviceAccess.defaultPassword()&&deviceAccess.verifyPassword("correct horse")&&!deviceAccess.verifyPassword("admin"));
 {auto stored=testNvs::committed["ot_access"]["web_pw"];assert(stored.size()==57&&std::string(stored.begin(),stored.begin()+4)=="OTPW");
  const std::string plain="correct";assert(std::search(stored.begin(),stored.end(),plain.begin(),plain.end())==stored.end());}
 pass("changed web password is stored only as a salted record and replaces admin");
 {auto durable=testNvs::committed;reset();testNvs::committed=durable;deviceAccess={};assert(deviceAccess.begin());assert(!deviceAccess.defaultPassword()&&deviceAccess.verifyPassword("correct horse")&&!deviceAccess.verifyPassword("admin"));}
 pass("changed web password survives a restart");
 assert(!deviceAccess.storePassword("short"));assert(deviceAccess.verifyPassword("correct horse"));
 testNvs::failCommit="ot_access";assert(!deviceAccess.storePassword("another long one"));testNvs::failCommit.clear();assert(deviceAccess.verifyPassword("correct horse")&&!deviceAccess.verifyPassword("another long one"));
 testCrypto::kdfFails=true;assert(!deviceAccess.verifyPassword("correct horse"));testCrypto::kdfFails=false;
 pass("short password, NVS commit failure and KDF failure never change or accept a password");
 Serial.input="password-reset\n";pollSetupWifi();assert(deviceAccess.defaultPassword()&&deviceAccess.verifyPassword("admin")&&!deviceAccess.verifyPassword("correct horse"));assert(!testNvs::committed["ot_access"].count("web_pw"));
 assert(deviceAccess.resetPassword());pass("USB password-reset restores the factory password and is idempotent");
 reset();testNvs::committed["ot_access"]["web_pw"]={'O','T','P','W',1};deviceAccess={};assert(deviceAccess.begin());assert(!deviceAccess.defaultPassword()&&!deviceAccess.verifyPassword("admin"));
 assert(deviceAccess.passwordState()==DeviceAccess::PasswordState::unreadable);Serial.input="password-reset\n";pollSetupWifi();assert(deviceAccess.verifyPassword("admin"));pass("unreadable stored password fails closed until USB password-reset");
 reset();testNvs::committed["ot_access"]["secret"]={1,2,3};deviceAccess={};assert(deviceAccess.begin()&&deviceAccess.defaultPassword());assert(deviceAccess.storePassword("correct horse"));assert(testNvs::committed["ot_access"]["secret"].size()==3);pass("password record leaves the legacy access secret untouched");
 std::cout<<cases<<" production-code scenarios passed (not RF/hardware proof)\n";
}
