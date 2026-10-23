#pragma once
#include "Board.h"
#include "DeviceAccess.h"
#include "DeviceNetworkSettings.h"
#include "SetupNetwork.h"
#include "control/HttpAccessPolicy.h"
#include "control/ManagedDeviceSettings.h"
#include "control/CaptivePortalPolicy.h"
#ifdef OPENTHERMOSTAT_E32V2
#include "EmbeddedWebAssets.h"
#include "control/StaticAssetRoute.h"
#include "update/GitHubUpdate.h"
#include "control/WebAuthSession.h"
#include "control/NativeSourceProvisioning.h"
#include <esp_system.h>
// Pinned Arduino WebServer verbose logging prints HTTP headers and form bodies.
// Never build the credential endpoint with that unredacted library trace enabled.
#if defined(CORE_DEBUG_LEVEL) && CORE_DEBUG_LEVEL >= 5
#error "E32 login requires CORE_DEBUG_LEVEL below 5: native HTTP verbose logs expose credentials"
#endif
#endif
#include "Logging.h"

#include <esp_ota_ops.h>
#include <esp_spi_flash.h>
#include <mbedtls/sha256.h>
#include <SPIFFS.h>
#include <WebServer.h>
#include <Wire.h>
#include <uri/UriBraces.h>
#include <cJSON.h>

#include "viewable_stringbuf.h"
#include "HeatingController.h"
#include "Filesystem.h"

#include "Network.h"
#include <algorithm>
#include <iomanip>
#include <array>
#include <cstring>
#include <memory>
#include <map>
#include <set>
#include <sstream>
#include <string_view>

namespace heating {

using namespace std::string_view_literals;
using namespace std::string_literals;

#ifdef OPENTHERMOSTAT_E32V2
class EmbeddedAssetUri final : public Uri {
public:
    EmbeddedAssetUri() : Uri("") {}
    Uri *clone() const override { return new EmbeddedAssetUri(); }
    bool canHandle(const String &requestUri, std::vector<String> &) override {
        return control::embeddedAssetPath(
            std::string_view(requestUri.c_str(),requestUri.length()),embedded::assets);
    }
};
#endif

class WebServerStringView : public WebServer {
public:
	WebServerStringView(uint16_t listenPort) : WebServer(listenPort) {

	}

	void sendView(int code, std::string_view content_type, std::string_view content) {
		String header;
		if (content.length() == 0) {
			log_w("content length is zero");
		}

		_prepareHeader(header, code, content_type.data(), content.length());
		_currentClientWrite(header.c_str(), header.length());

		if(content.length()) {
			sendContent(content.data(), content.length());
		}
	}

	void sendBytes(const char *bytes, size_t size) { _currentClientWrite(bytes, size); }
	void endResponse() { _finalizeResponse(); }

	HTTPUpload *getUpload() { return _currentUpload.get(); }
};

class REST {
public:
	REST(std::shared_ptr<ib::logger::LoggerInterface> log, HeatingController &controller, uint16_t listenPort) : log_(std::move(log)), listenPort_(listenPort), controller_(controller), server_(listenPort) {
		logFeature_ = log_->addFeature("REST");

		server_.enableCORS(false);
		server_.enableCrossOrigin(false);
		const char *headers[]{"Origin","Sec-Fetch-Site","Cookie","X-OpenThermostat-CSRF","Content-Type","If-Match"};
		server_.collectHeaders(headers,6);
#ifdef OPENTHERMOSTAT_E32V2
		route("/login",HTTP_GET,[this] { serveFile("/login.html"); });
		route("/auth/login",HTTP_POST,[this] { login(); });
		route("/auth/session",HTTP_GET,[this] { sessionStatus(); });
		route("/auth/logout",HTTP_POST,[this] { logout(); });
#endif

		route("/status/wifi", [this]() {
			DBGLOGFD(log_, logFeature_, "REST:wifiNetworks\n");

			ib::viewable_stringbuf payloadBuf;
			std::ostream payload(&payloadBuf);

			getWiFiNetworks(payload);
			server_.sendView(200, "application/json"sv, payloadBuf.view());
		});

		route("/status", [this]() { status(); });
		route("/status/boiler", [this]() { boilerStatus(); });
		route("/status/ems", [this]() { emsStatus(); });
		route("/status/ems/telemetry", HTTP_GET, [this]() {
			ib::viewable_stringbuf buf;
			std::ostream ss(&buf);
#ifdef OPENTHERMOSTAT_E32V2
			const auto operatorSession = requestToken();
			controller_.getEMSTelemetryStatus(ss, operatorSession.c_str());
#else
			controller_.getEMSTelemetryStatus(ss);
#endif
			server_.sendView(200, "application/json"sv, buf.view());
		});
#ifdef OPENTHERMOSTAT_E32V2
		route("/boiler/test/prepare", HTTP_POST, [this] { boilerTestAction("prepare"); });
		route("/boiler/test/start", HTTP_POST, [this] { boilerTestAction("start"); });
		route("/boiler/test/keepalive", HTTP_POST, [this] { boilerTestAction("keepalive"); });
		route("/boiler/test/stop", HTTP_POST, [this] { boilerTestAction("stop"); });
#endif
		route("/status/rooms", [this]() { roomsStatus(); });
		route("/status/devices", [this]() { devicesFound(); });
		route("/status/programs", HTTP_GET, [this]() { showPrograms(); }); // show available programs
		route("/status/version", [this]() { version(); });
		route("/params/boiler", [this]() { emsParams(); });


		route("/config/temporary", HTTP_POST, [this]() { temporaryOverride(); }); // GET/POST/DELETE name without .json, case sensitive

		route(UriBraces("/config/programs/{}"), [this]() { configPrograms(); }); // GET/POST/DELETE name without .json, case sensitive
		route("/config/rooms", [this]() { configRooms(); });
		route("/config/wifi", [this]() { configWiFi(); });
		route("/config/device", [this]() { configDevice(); });
		route("/config/boiler", [this]() { configBoiler(); });
		route("/config/hardware", [this]() { configHardware(); });
		route("/hardware/i2c/scan", HTTP_GET, [this]() { i2cScan(); });
		route("/hardware/test/gpio", HTTP_POST, [this]() { gpioTestStart(); });
		route("/hardware/test/gpio", HTTP_DELETE, [this]() { gpioTestStop(); });
		route("/config/debug", [this]() { configDebug(); });

		route("/config/program/current", [this]() { configProgramCurrent(); }); // get selected program
		route("/config/reboot", HTTP_POST, [this]() { configReboot(); });

		route("/ota", HTTP_POST, [this]() { handleOTAResponse(); }, [this]() { handleOTAUpdate(); });
		route("/otafs", HTTP_POST, [this]() { handleOTAResponse(); }, [this]() { handleOTAFFSUpdate(); });
		route("/recovery", HTTP_GET, [this]() { recovery(); });

#ifdef OPENTHERMOSTAT_E32V2
		route("/updates/status",HTTP_GET,[this] { server_.send(200,"application/json",update::status().c_str()); });
		route("/updates/check",HTTP_POST,[this] { server_.send(update::checkReleases()?202:409,"text/plain","Releasecontrole vereist thuisnetwerk, geldige tijd en een vrij updatesysteem"); });
		route("/updates/install",HTTP_POST,[this] {
			auto body=server_.arg("plain");auto root=control::parseControlJson(std::string_view(body.c_str(),body.length()),true);
			if(!root||!cJSON_IsObject(root.get())||cJSON_GetArraySize(root.get())!=1||!cJSON_IsString(cJSON_GetObjectItemCaseSensitive(root.get(),"tag"))) {server_.send(400,"text/plain","Eén gecontroleerde release-tag vereist");return;}
			server_.send(update::installRelease(cJSON_GetObjectItemCaseSensitive(root.get(),"tag")->valuestring)?202:409,"text/plain","Installatie vereist een gecontroleerde release en een vrij updatesysteem");
		});
		route("/updates/reboot",HTTP_POST,[this] { server_.send(update::requestReboot()?202:409,"text/plain","Herstart aangevraagd"); });
		route("/updates/rollback",HTTP_POST,[this] { server_.send(update::requestRollback()?202:409,"text/plain","Herstel vereist een vorige door native OTA gevalideerde firmware"); });
		route("/setup",HTTP_GET,[this] { serveFile("/setup.html"); });
		route("/setup/scan",HTTP_POST,[this] {
			if(!wifiAPMode||boardEthernetStarted) { server_.send(409,"text/plain","Open setup WiFi first"); return; }
			if(setupAttemptUntil) { server_.send(409,"text/plain","Connection attempt in progress"); return; }
			server_.send(startWifiScan()?202:503,"application/json",("{\"status\":\""+wifiScanState+"\"}").c_str());
		});
		route("/setup/scan",HTTP_GET,[this] {
			pollWifiScan();
			server_.send(200,"application/json",("{\"status\":\""+wifiScanState+"\",\"networks\":"+wifiScanRows+"}").c_str());
		});
		route("/setup/finish",HTTP_POST,[this] {
			if(!finishSetupWifi()) { server_.send(409,"text/plain","Finish requires a confirmed saved WiFi connection"); return; }
			server_.send(202,"application/json",("{\"close_after_ms\":"+std::to_string(setupCloseAt>networkNow()?setupCloseAt-networkNow():0)+"}").c_str());
		});
		route("/setup/status",HTTP_GET,[this] {
			auto root=control::objectJson();
			cJSON_AddStringToObject(root.get(),"status",setupResult.c_str());
			cJSON_AddBoolToObject(root.get(),"setup_active",wifiAPMode);
			cJSON_AddBoolToObject(root.get(),"connected",setupConnectionReady());
			cJSON_AddStringToObject(root.get(),"station_ip",WiFi.localIP().toString().c_str());
			cJSON_AddNumberToObject(root.get(),"station_port",listenPort_);
			cJSON_AddNumberToObject(root.get(),"close_after_ms",setupCloseAt>networkNow()?setupCloseAt-networkNow():0);
			cJSON_AddBoolToObject(root.get(),"closing",setupCloseAt!=0);
			cJSON_AddNumberToObject(root.get(),"remaining_seconds",wifiAPMode&&setupUntil>networkNow()?(setupUntil-networkNow())/1000:0);
			server_.send(200,"application/json",control::printJson(root.get()).c_str());
		});
		route("/setup/reenter",HTTP_POST,[this] { server_.send(requestSetupBoot()?202:503,"text/plain","Setup requested; controlled reboot to WiFi-only recovery"); });
		route("/setup/network",HTTP_POST,[this] { setupNetwork(); });
#endif
		route("/", HTTP_GET, [this]() { index(); });

		#ifdef OPENTHERMOSTAT_E32V2
        // The pinned WebServer logs an error BEFORE onNotFound(), even when
        // that fallback successfully serves a static file. Give real embedded
        // assets one explicit GET handler while retaining the same auth gate.
        route(EmbeddedAssetUri{},HTTP_GET,[this] { serveFile(server_.uri().c_str()); });
        #endif
		server_.onNotFound([this]() {
			if(!authorize()) return;
			serveFile(server_.uri().c_str());
		});
	}

	void restart() {
		server_.stop();
		server_.begin();
	}

	void handle() {
		server_.handleClient();
	}

private:
	void route(const Uri &uri, HTTPMethod method, WebServer::THandlerFunction handler) {
		#ifdef OPENTHERMOSTAT_E32V2
		server_.on(uri,method,[this,handler] { if(authorize()) handler(); });
#else
		server_.on(uri,method,handler);
#endif
	}
	void route(const Uri &uri, WebServer::THandlerFunction handler) { route(uri,HTTP_ANY,handler); }
	void route(const Uri &uri, HTTPMethod method, WebServer::THandlerFunction handler, WebServer::THandlerFunction upload) {
		#ifdef OPENTHERMOSTAT_E32V2
		server_.on(uri,method,[this,handler] { if(authorize()) handler(); },upload);
#else
		server_.on(uri,method,handler,upload);
#endif
	}
	bool authorize(bool responseHeaders=true) {
#ifdef OPENTHERMOSTAT_E32V2
		// Upload callbacks run for every chunk. WebServer appends sendHeader()
		// calls until the response, so headers belong to the final route gate.
		if(responseHeaders) {
			server_.sendHeader("Cache-Control","no-store");
			server_.sendHeader("X-Content-Type-Options","nosniff");
			server_.sendHeader("X-Frame-Options","DENY");
		}
		const auto method=server_.method()==HTTP_GET?"GET":server_.method()==HTTP_POST?"POST":server_.method()==HTTP_DELETE?"DELETE":"OTHER";
		String canonical=WiFi.softAPIP().toString();
		if(listenPort_!=80) canonical+=":"+String(listenPort_);
		String host=server_.hostHeader();
		if(listenPort_==80&&host==canonical+":80") host=canonical;
		const auto portal=control::portalAccess(wifiAPMode,server_.client().localIP()==WiFi.softAPIP(),host.c_str(),canonical.c_str(),server_.uri().c_str(),method);
		if(portal==control::PortalAccess::Redirect) {
			server_.sendHeader("Location","http://"+canonical+"/setup"); server_.send(302,"text/plain","OpenThermostat WiFi setup"); return false;
		}
		if(!control::allowedHttpMethod(server_.uri().c_str(),method)) { server_.send(405,"text/plain","Method not allowed"); return false; }
		if(!control::sameOrigin(server_.header("Origin").c_str(),server_.hostHeader().c_str(),server_.header("Sec-Fetch-Site").c_str())) {
			server_.send(403,"text/plain","Origin rejected"); return false;
		}
		if(!deviceAccess.ready()) { server_.send(503,"text/plain","Local access initialization failed"); return false; }
		// The only public LAN paths are the login form/bootstrap and explicit credential exchange.
		// Never issue WWW-Authenticate: browsers must not maintain a competing HTTP-auth cache.
		if(control::publicAuthResource(server_.uri().c_str())) return true;
		const auto token=requestToken();
		const auto decision=control::webAuthDecision(sessions_,server_.uri().c_str(),method,token.c_str(),
			server_.header("X-OpenThermostat-CSRF").c_str(),networkNow(),portal==control::PortalAccess::Setup);
		if(decision==control::WebAuthDecision::redirect_login){
			server_.sendHeader("Location","/login");server_.send(303,"text/plain","Sign in to OpenThermostat");return false;
		}
		if(decision==control::WebAuthDecision::authentication_required){server_.send(401,"application/json","{\"error\":\"authentication_required\"}");return false;}
		if(decision==control::WebAuthDecision::csrf_required){server_.send(403,"application/json","{\"error\":\"csrf_required\"}");return false;}
		if(server_.method()!=HTTP_GET&&update::mutationBlocked(server_.uri().c_str())) {
			server_.send(409,"text/plain","Wacht tot de GitHub-update is afgerond en herstart eerst");return false;
		}
		if(server_.method()!=HTTP_GET&&control::boilerTestMutationBlocked(server_.uri().c_str(),controller_.boilerTestActive())) {
			server_.send(409,"text/plain","Stop de ketelproef en controleer de terugmelding voor deze wijziging"); return false;
		}
		if(controller_.modernMode()&&control::legacyControlWrite(server_.uri().c_str(),method)) {
			server_.send(409,"text/plain","HA-managed shadow mode: legacy control writer disabled"); return false;
		}
#endif
		return true;
	}
#ifdef OPENTHERMOSTAT_E32V2
	control::WebAuthSession sessions_;
	String requestToken() {
		const auto cookie=server_.header("Cookie");
		const auto token=control::WebAuthSession::cookieToken(std::string_view(cookie.c_str(),cookie.length()));
		return token.empty()?String():String(token.data(),token.size());
	}
	static bool randomToken(std::array<char,65> &token) {
		std::array<uint8_t,32> bytes{};
		if(!deviceAccess.randomBytes(bytes.data(),bytes.size()))return false;
		constexpr char hex[]="0123456789abcdef";
		for(size_t i=0;i<bytes.size();++i){token[i*2]=hex[bytes[i]>>4];token[i*2+1]=hex[bytes[i]&15];}
		return true;
	}
	void login() {
		const auto now=networkNow();
		if(!sessions_.loginAllowed(now)){server_.sendHeader("Retry-After","30");server_.send(429,"application/json","{\"error\":\"try_again_later\"}");return;}
		// Form decoding uses the existing native WebServer parser. No raw password in URLs/logs.
		bool usernameSeen=false,passwordSeen=false,shape=server_.args()==2;
		for(int i=0;i<server_.args();++i){
			const auto name=server_.argName(i);
			if(name=="username"&&!usernameSeen)usernameSeen=true;
			else if(name=="password"&&!passwordSeen)passwordSeen=true;
			else shape=false;
		}
		const auto username=server_.arg("username"),password=server_.arg("password");
		if(!shape||!usernameSeen||!passwordSeen||username.length()>64||password.length()>128||
		   server_.header("Content-Type")!="application/x-www-form-urlencoded"){
			server_.send(400,"application/json","{\"error\":\"invalid_login_request\"}");return;
		}
		if(username!="admin"||!control::WebAuthSession::equal(std::string_view(password.c_str(),password.length()),deviceAccess.password())){
			sessions_.loginFailed(now);server_.send(401,"application/json","{\"error\":\"invalid_credentials\"}");return;
		}
		std::array<char,65> token{},proof{};
		if(!randomToken(token)||!randomToken(proof)){server_.send(503,"application/json","{\"error\":\"session_unavailable\"}");return;}
		const auto old=requestToken();
		const auto *session=sessions_.issue(token.data(),proof.data(),now,old.c_str());
		if(!session){server_.send(429,"application/json","{\"error\":\"session_capacity\"}");return;}
		sessions_.loginSucceeded();
		server_.sendHeader("Set-Cookie",String("OTSESSION=")+session->token.data()+"; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800");
		server_.send(200,"application/json","{\"authenticated\":true}");
	}
	void sessionStatus() {
		const auto token=requestToken();const auto now=networkNow();
		const auto *session=sessions_.find(token.c_str(),now);
		if(!session){server_.send(401,"application/json","{\"error\":\"authentication_required\"}");return;}
		const auto response=std::string("{\"authenticated\":true,\"csrf\":\"")+session->csrf.data()+"\",\"expires_in\":"+std::to_string((session->until-now)/1000)+"}";
		server_.send(200,"application/json",response.c_str());
	}
	void logout() {
		const auto token=requestToken();sessions_.revoke(token.c_str());
		server_.sendHeader("Set-Cookie","OTSESSION=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0");
		server_.send(200,"application/json","{\"authenticated\":false}");
	}
#endif
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	uint16_t listenPort_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};

	void showPrograms() {
		DBGLOGFD(log_, logFeature_, "showPrograms\n");

		ib::viewable_stringbuf payloadBuf;
		std::ostream ss(&payloadBuf);

		ss << "[";
		File path = SPIFFS.open("/programs");
		bool first = true;
		while (path) {
			using namespace std::string_view_literals;
			static constexpr auto jsonExtension = ".json"sv;

			auto file = path.openNextFile();
			if (!file) {
				break;
			}
			DBGLOGFD(log_, logFeature_, "showPrograms '%s'\n", file.name());

			if (file.isDirectory()) {
				DBGLOGFD(log_, logFeature_, "showPrograms skip directory: %s\n", file.name());
				continue;
			}

			std::string name = file.name();
			auto pos = name.find(jsonExtension);
			if (pos == std::string::npos) {
				DBGLOGFD(log_, logFeature_, "showPrograms skip non-json: %s\n", file.name());
				continue;
			}
			name = name.substr(0, name.length() - jsonExtension.length());

			if (first) {
				ss << "\"" << name << "\"";
				first = false;
			} else {
				ss << ", \"" << name << "\"";
			}
		}

		path.close();
		ss << "]";
		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void configProgramCurrent() {
		DBGLOGFD(log_, logFeature_, "configProgramCurrent method: %d\n", server_.method());

		switch (server_.method()) {
			case HTTP_GET: {
				File file = SPIFFS.open("/cfg/cfgprogram.json", FILE_READ);
				if (!file) {
					DBGLOGFD(log_, logFeature_, "configProgramCurrent missing config");
					server_.send(500, "text/plain", "Missing config");
					return;
				}
				server_.streamFile(file, "application/json");
				file.close();
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(500, "text/plain", "missing body");
					return;
				}
				auto body = server_.arg("plain");

				auto program = config::parseProgram(body.c_str());
				if (program.empty()) {
					DBGLOGFD(log_, logFeature_, "configProgramCurrent error parsing program\n");
					server_.send(400, "text/html", "Program parsing failure. Config not modified");
					return;
				}

				std::string filename = "/programs/" + program + ".json";

				if (!SPIFFS.exists(filename.c_str())) {
					DBGLOGFD(log_, logFeature_, "Received new program configuration: '%s'. Program does not exists!\n", program.c_str());
					server_.send(400, "text/html", "Program does not exists. Config not modified");
					return;
				}

				DBGLOGFD(log_, logFeature_, "Received new program configuration: '%s'\n", program.c_str());
				File file = SPIFFS.open("/cfg/cfgprogram.json", FILE_WRITE);
				if (!file) {
					server_.send(500, "text/html", "Filesystem failure. Unable to write program.");
					return;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();

				server_.send(204);
				controller_.reloadConfiguration();
				break;
			}
			default:
				server_.sendHeader("Allow", "GET, POST");
				server_.send(405);
				break;
		}


	}

	void configReboot() {
		DBGLOGFD(log_, logFeature_, "configReboot\n");
		server_.send(200);
		server_.stop();
		ESP.restart();
	}

	void boilerStatus() {
		DBGLOGFD(log_, logFeature_, "boilerStatus\n");

		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);

		controller_.getBoilerStatus(payload);

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void emsStatus() {
		DBGLOGFD(log_, logFeature_, "emsStatus\n");

		ib::viewable_stringbuf payloadBuf;
		std::ostream ss(&payloadBuf);
		controller_.getEMSStatus(ss);

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}
#ifdef OPENTHERMOSTAT_E32V2
	void boilerTestAction(std::string_view action) {
		const auto type = server_.header("Content-Type");
		const auto body = server_.arg("plain");
		if ((type != "application/json" && !type.startsWith("application/json;")) || body.length() > 256) {
			server_.send(400,"application/json","{\"accepted\":false,\"error\":\"invalid_request\"}"); return;
		}
		const auto operatorSession = requestToken();
		ib::viewable_stringbuf buf; std::ostream ss(&buf);
		const auto code = controller_.boilerTestAction(action,
			std::string_view(body.c_str(),body.length()), operatorSession.c_str(), ss);
		server_.sendView(code,"application/json"sv,buf.view());
	}
#endif

	void emsParams() {
		DBGLOGFD(log_, logFeature_, "emsParams\n");
		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);
		controller_.getEMSBoilerParams(payload);

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void status() {
		DBGLOGFD(log_, logFeature_, "status\n");
		server_.enableCORS(false);
		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);
		controller_.getFullStatus(payload);

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void version() {
		DBGLOGFD(log_, logFeature_, "version\n");

		const esp_app_desc_t *app = esp_ota_get_app_description();

		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);
		payload << '{';
		payload << "\"project\": \""sv << app->project_name << "\","sv;
#ifdef OPENTHERMOSTAT_E32V2
		payload << "\"version\": \""sv << embedded::version << "\","sv;
		payload << "\"source\": \""sv << embedded::source << "\","sv;
		payload << "\"web_sha256\": \""sv << embedded::webSha << "\","sv;
#else
		payload << "\"version\": \""sv << app->version << "\","sv;
#endif
		payload << "\"date\": \""sv << app->date << "\","sv;
		payload << "\"time\": \""sv << app->time << "\","sv;
		payload << "\"idf\": \""sv << app->idf_ver << "\","sv;
		payload << "\"sha256\": \""sv;
		for (size_t i = 0; i < sizeof(app->app_elf_sha256); ++i) {
			payload << std::hex << std::setw(2) << std::setfill('0') << (int)app->app_elf_sha256[i];
		}
		payload << "\"}";

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void roomsStatus() {
		if(controller_.modernMode()) { server_.send(200,"application/json","[]"); return; }
		DBGLOGFD(log_, logFeature_, "roomsStatus\n");
		server_.enableCORS(false);

		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);
		controller_.getRoomsStatus(payload);

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void devicesFound() {
		DBGLOGFD(log_, logFeature_, "devicesFound\n");
		ib::viewable_stringbuf payloadBuf;
		std::ostream payload(&payloadBuf);
		controller_.getDevicesFound(payload);
		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

#ifdef OPENTHERMOSTAT_E32V2
	void setupNetwork() {
		auto body=server_.arg("plain");
		if(body.length()==0||body.length()>768||body.indexOf("\\u0000")>=0) { server_.send(400,"text/plain","Invalid setup payload"); return; }
		control::ControlJson root(cJSON_ParseWithLengthOpts(body.c_str(),body.length()+1,nullptr,true),cJSON_Delete);
		if(!root||!control::exactFields(root.get(),{"ssid","password"})||!cJSON_IsString(control::field(root.get(),"ssid"))||!cJSON_IsString(control::field(root.get(),"password"))) {
			server_.send(400,"text/plain","SSID and password required"); return;
		}
		config::WiFiConfig cfg{control::stringField(root.get(),"ssid"),control::stringField(root.get(),"password")};
		if(setupAttemptUntil||wifiScanRunning()) { server_.send(409,"text/plain","Wait for the scan or connection attempt to finish"); return; }
		if(!trySetupWifi(cfg)) { server_.send(400,"text/plain","Open setup WiFi first; check SSID/password lengths"); return; }
		server_.send(202,"text/plain","Connecting; settings are saved only after successful connection");
	}
#endif
	void configWiFi() {
#ifdef OPENTHERMOSTAT_E32V2
		if(server_.method()==HTTP_POST) {
			if(boardEthernetStarted) { server_.send(409,"text/plain","Use POST /setup/reenter before WiFi setup; Ethernet must stop first"); return; }
			if(!wifiAPMode) { server_.send(409,"text/plain","Use POST /setup/reenter, then connect to setup WiFi"); return; }
			setupNetwork(); return;
		}
#endif
		DBGLOGFD(log_, logFeature_, "configWiFi METHOD %d\n", server_.method());

		switch (server_.method()) {
			default:
			case HTTP_GET: {
				ib::viewable_stringbuf payloadBuf;
				std::ostream payload(&payloadBuf);
				getWiFiSSID(payload);
				server_.sendView(200, "application/json"sv, payloadBuf.view());
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					break;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					break;
				}

				File file = SPIFFS.open("/cfg/cfgwifi.json", FILE_WRITE);
				if (!file) {
					server_.send(500, "text/plain", "Internal server error. Can't save wifi settings.");
					break;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();
				server_.send(201);
				break;
			}
		}

	}

	void configDevice() {
#ifdef OPENTHERMOSTAT_E32V2
		auto saved=readDeviceNetworkSettings();
		auto previous=control::parseControlJson(std::string_view(saved.c_str(),saved.length()),true);
		if(server_.method()==HTTP_GET) {
			if(!previous||!cJSON_IsObject(previous.get())) { server_.send(500,"text/plain","Invalid saved network settings"); return; }
            std::array<char,65> nonce{};
            if(!randomToken(nonce)) { server_.send(503,"text/plain","Readback token unavailable"); return; }
            const auto tag=sessions_.settingsReadback(requestToken().c_str(),
                control::sha256Hex(std::string_view(saved.c_str(),saved.length())),nonce.data(),networkNow());
            if(tag.empty()) { server_.send(503,"text/plain","Readback token unavailable"); return; }
            server_.sendHeader("ETag",String("\"")+tag.data()+"\"");
			for(auto pair:{std::make_pair("mqtt","password"),std::make_pair("openweather","appid")}) {
				auto section=cJSON_GetObjectItemCaseSensitive(previous.get(),pair.first);
				if(cJSON_IsObject(section)) { cJSON_DeleteItemFromObjectCaseSensitive(section,pair.second); cJSON_AddStringToObject(section,pair.second,""); }
			}

            auto mq=cJSON_GetObjectItemCaseSensitive(previous.get(),"mqtt");
            if(cJSON_IsObject(mq)) {
                char id[17];snprintf(id,sizeof(id),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
                cJSON_AddStringToObject(mq,"native_source_device_id",id);
                const auto localSource=control::field(mq,"native_shadow_source");
                cJSON_AddBoolToObject(mq,"native_source_live_apply",
                    localSource&&!cJSON_IsNull(localSource)&&controller_.nativeSourceHotReady(control::printJson(localSource),std::string_view(saved.c_str(),saved.length())));
            }
			server_.send(200,"application/json",control::printJson(previous.get()).c_str()); return;
		}
        // Existing local forms remain compatible. The HA link client sends the
        // exact GET ETag, fencing all persisted settings (including secrets)
        // before any merge/save; a stale read must never overwrite another edit.
        if(server_.hasHeader("If-Match")&&!sessions_.settingsReadbackMatches(requestToken().c_str(),
                server_.header("If-Match").c_str(),
                control::sha256Hex(std::string_view(saved.c_str(),saved.length())),networkNow())) {
            server_.send(412,"application/json","{\"error\":\"device_settings_changed\"}");return;
        }
		auto body=server_.arg("plain");
		auto candidate=control::parseControlJson(std::string_view(body.c_str(),body.length()),true);
		if(!candidate||!cJSON_IsObject(candidate.get())) { server_.send(400,"text/plain","Invalid bounded network settings"); return; }
        const auto sourceApply=control::field(candidate.get(),"native_source_apply");
        if(sourceApply&&!cJSON_IsBool(sourceApply)) {server_.send(400,"text/plain","Invalid source-only apply request");return;}
        const bool sourceOnly=cJSON_IsTrue(sourceApply);
        cJSON_DeleteItemFromObjectCaseSensitive(candidate.get(),"native_source_apply"); // transient, NEVER a stored authority.
		auto mode=control::stringField(candidate.get(),"interface_mode");
		if(!mode.empty()&&mode!="wifi"&&mode!="ethernet") { server_.send(400,"text/plain","Select wifi or ethernet"); return; }
		auto mq=cJSON_GetObjectItemCaseSensitive(candidate.get(),"mqtt");
		auto oldMq=previous?control::field(previous.get(),"mqtt"):nullptr;
        if(cJSON_IsObject(mq)) {
            cJSON_DeleteItemFromObjectCaseSensitive(mq,"native_source_device_id");
            cJSON_DeleteItemFromObjectCaseSensitive(mq,"native_source_live_apply");
        }
        if(!control::retainNativeSourceSetting(oldMq,mq)) {
            server_.send(400,"text/plain","Saved SOURCE profile must be retained or explicitly cleared");return;
        }
		if(cJSON_IsObject(mq)&&control::stringField(mq,"password").empty()&&oldMq) {
			bool sameBroker=control::stringField(mq,"brokerAddress")==control::stringField(oldMq,"brokerAddress")&&
				control::stringField(mq,"username")==control::stringField(oldMq,"username")&&
				control::integerField(mq,"brokerPort",1,65535)&&control::integerField(oldMq,"brokerPort",1,65535)&&
				control::uintField(mq,"brokerPort")==control::uintField(oldMq,"brokerPort");
			if(sameBroker) { cJSON_DeleteItemFromObjectCaseSensitive(mq,"password"); cJSON_AddStringToObject(mq,"password",control::stringField(oldMq,"password").c_str()); }
			else if(cJSON_IsTrue(control::field(mq,"enabled"))) { server_.send(400,"text/plain","Enter a password when changing broker or username"); return; }
		}
		auto weather=cJSON_GetObjectItemCaseSensitive(candidate.get(),"openweather");
		auto oldWeather=previous?control::field(previous.get(),"openweather"):nullptr;
		if(cJSON_IsObject(weather)&&oldWeather&&control::stringField(weather,"appid").empty()) {
			cJSON_DeleteItemFromObjectCaseSensitive(weather,"appid"); cJSON_AddStringToObject(weather,"appid",control::stringField(oldWeather,"appid").c_str());
		}
        if(!control::managedWeatherChangeAllowed(controller_.modernMode(),oldWeather,weather)) {
            server_.send(409,"text/plain","HA-managed mode: legacy weather settings are read-only"); return;
        }
		if(mq&&cJSON_IsTrue(control::field(mq,"modern_shadow"))&&
			(!control::SessionAdmission::validId(control::stringField(mq,"adapter_id"))||
			(cJSON_IsTrue(control::field(mq,"enabled"))&&(!control::integerField(mq,"brokerPort",1,65535)||control::stringField(mq,"username").empty()||control::stringField(mq,"password").empty())))) {
			server_.send(400,"text/plain","Shadow mode needs adapter ID and dedicated broker credentials"); return;
		}

        if(!control::nativeSourceReplacementAllowed(oldMq,mq)) {
            server_.send(409,"text/plain","SOURCE replacement requires a separately supported plan migration; previous settings retained");return;
        }
        const auto nativeSource=mq?control::field(mq,"native_shadow_source"):nullptr;
        if(!sourceOnly&&control::nativeSourceNeedsExplicitApply(oldMq,mq)) {
            server_.send(409,"text/plain","Existing SOURCE replacement uses the explicit source-only action; general network save does not stage another profile for reboot");return;
        }
        if(nativeSource&&!cJSON_IsNull(nativeSource)) {
            char controllerId[17];snprintf(controllerId,sizeof(controllerId),"e32_%012llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
            if(!control::nativeSourceSettingValid(mq,controllerId,control::sha256Hex)) {
                server_.send(400,"text/plain","Invalid or unsupported local shadow SOURCE profile; no physical qualification");return;
            }
        }
		const String encoded(control::printJson(candidate.get()).c_str());
		if(!control::nativeNetworkSettingsBytesFit(std::string_view(encoded.c_str(),encoded.length()))) { server_.send(413,"text/plain","Persisted network settings exceed 2048 bytes"); return; }
        const auto oldSource=oldMq?control::field(oldMq,"native_shadow_source"):nullptr;
        const auto expectedSource=oldSource?control::printJson(oldSource):std::string{};
        if(sourceOnly) {
            if(!control::nativeSourceOnlySettingsChange(previous.get(),candidate.get())
                ||!controller_.nativeSourceCurrent(expectedSource,std::string_view(saved.c_str(),saved.length()))) {
                server_.send(409,"text/plain","Live SOURCE update requires the current local native profile and unchanged network/device settings");return;
            }
            if(cJSON_Compare(oldSource,nativeSource,true)) {
                server_.send(200,"text/plain","Current local SOURCE already selected; no save, control reset or reboot");return;
            }
            if(!controller_.nativeSourceCanApply(expectedSource,control::printJson(nativeSource),
                    std::string_view(saved.c_str(),saved.length()))) {
                server_.send(409,"text/plain","SOURCE lineage does not match the actual current durable plan; read back and resolve pending/conflict before selection");return;
            }
        }
		if(!saveDeviceNetworkSettings(encoded)) {
            if(sourceOnly)controller_.inhibitNativeSourceMutation(); // ambiguous commit: never operate old policy.
            server_.send(500,"text/plain",sourceOnly?
                "SOURCE durability not confirmed; control blocked; read back before recovery":
                "Network settings durability not confirmed; read back before retry");return;
        }
        if(sourceOnly) {
            if(!controller_.applyNativeSource(expectedSource,control::printJson(nativeSource),std::string_view(saved.c_str(),saved.length()))) {
                server_.send(503,"text/plain","SOURCE settings saved but runtime selection failed; control blocked; read back before recovery");return;
            }
            server_.send(201,"text/plain","Local SOURCE selected without device restart; previous config is readback-only until explicit new plan apply/readback");return;
        }
		server_.send(201,"text/plain","Saved and verified; restart to apply network settings");
#else

		DBGLOGFD(log_, logFeature_, "configDevice METHOD %d\n", server_.method());

		switch (server_.method()) {
			default:
			case HTTP_GET: {
				File file = SPIFFS.open("/cfg/cfgnetwork.json", FILE_READ);
				if (!file) {
					server_.send(404, "text/plain", "FileNotFound");
					return;
				}
				server_.streamFile(file, "application/json");
				file.close();
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					break;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					break;
				}

				File file = SPIFFS.open("/cfg/cfgnetwork.json", FILE_WRITE);
				if (!file) {
					DBGLOGFD(log_, logFeature_, "configDevice. Can't open config file for write.\n");
					server_.send(500, "text/plain", "Internal server error. Can't save device settings.");
					break;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();
				server_.send(201);
				break;
			}
		}
	#endif
	}

	void configHardware() {
		DBGLOGFD(log_, logFeature_, "configHardware METHOD %d\n", server_.method());

		switch (server_.method()) {
			default:
			case HTTP_GET: {
				File file = SPIFFS.open("/cfg/cfgpins.json", FILE_READ);
				if (!file) {
					server_.send(404, "text/plain", "FileNotFound");
					return;
				}
				server_.streamFile(file, "application/json");
				file.close();
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					break;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					break;
				}

				File file = SPIFFS.open("/cfg/cfgpins.json", FILE_WRITE);
				if (!file) {
					DBGLOGFD(log_, logFeature_, "configHardware. Can't open config file for write.\n");
					server_.send(500, "text/plain", "Internal server error. Can't save hardware settings.");
					break;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();
				server_.send(201);
				break;
			}
		}
	}

	void i2cScan() {
		if constexpr (!board::auxiliaryGpioAllowed) {
			server_.send(403, "text/plain", "E32V2: auxiliary GPIO/I2C hardware is locked");
			return;
		}
		DBGLOGFD(log_, logFeature_, "i2cScan\n");

		// Known I2C device address ranges (helpers for frontend labeling)
		struct KnownRange {
			uint8_t from;
			uint8_t to;
			const char *type;
		};
		static constexpr KnownRange ranges[] = {
			{0x20, 0x27, "pcf8574"},  // PCF8574 GPIO expanders
			{0x20, 0x27, "mcp23017"}, // MCP23017 GPIO expanders (same address range)
			{0x38, 0x3F, "pcf8574a"}, // PCF8574A variants
			{0x50, 0x57, "eeprom"},   // I2C EEPROMs (AT24Cx family)
			{0x68, 0x69, "rtc"},      // RTC modules (DS1307 / DS3231 common addresses)
		};

		ib::viewable_stringbuf payloadBuf;
		std::ostream ss(&payloadBuf);
		ss << "[";
		bool first = true;

		for (uint8_t addr = 0x03; addr < 0x78; ++addr) {
			Wire.beginTransmission(addr);
			if (Wire.endTransmission() == 0) {
				const char *guessedType = "unknown";
				for (auto const &r : ranges) {
					if (addr >= r.from && addr <= r.to) {
						guessedType = r.type;
						break;
					}
				}
				if (!first)
					ss << ",";
				first = false;
				ss << "{\"address\":" << static_cast<int>(addr) << ",\"type\":\"" << guessedType << "\"}";
			}
		}
		ss << "]";

		server_.sendView(200, "application/json"sv, payloadBuf.view());
	}

	void gpioTestStart() {
		if constexpr (!board::auxiliaryGpioAllowed) {
			server_.send(403, "text/plain", "E32V2: auxiliary GPIO/I2C hardware is locked");
			return;
		}
		DBGLOGFD(log_, logFeature_, "gpioTestStart\n");

		if (!server_.hasArg("plain")) {
			server_.send(400, "text/plain", "Missing body");
			return;
		}
		auto body = server_.arg("plain");
		if (body.isEmpty()) {
			server_.send(400, "text/plain", "Empty body");
			return;
		}

		std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(body.c_str()), &cJSON_Delete);
		if (!root) {
			server_.send(400, "text/plain", "Invalid JSON");
			return;
		}

		auto durationObj = cJSON_GetObjectItem(root.get(), "duration");
		if (!durationObj || !cJSON_IsNumber(durationObj) || durationObj->valueint <= 0 || durationObj->valueint > 3600) {
			server_.send(400, "text/plain", "Invalid duration (1-3600s)");
			return;
		}
		uint32_t duration = durationObj->valueint;

		auto boilerObj = cJSON_GetObjectItem(root.get(), "boiler");
		bool boilerState = boilerObj && cJSON_IsTrue(boilerObj);

		auto valvesArr = cJSON_GetObjectItem(root.get(), "valves");
		std::vector<bool> valveStates;
		if (valvesArr && cJSON_IsArray(valvesArr)) {
			int size = cJSON_GetArraySize(valvesArr);
			for (int i = 0; i < size; ++i) {
				auto item = cJSON_GetArrayItem(valvesArr, i);
				valveStates.push_back(cJSON_IsTrue(item));
			}
		}

		DBGLOGFD(log_, logFeature_, "gpioTestStart boiler: %d, valves: %zu, duration: %ds\n", boilerState, valveStates.size(), duration);
		controller_.startManualGpioTest(boilerState, valveStates, duration);
		server_.send(200, "text/plain", "OK");
	}

	void gpioTestStop() {
		DBGLOGFD(log_, logFeature_, "gpioTestStop\n");
		controller_.stopManualGpioTest();
		server_.send(200, "text/plain", "OK");
	}

	void configDebug() {
		DBGLOGFD(log_, logFeature_, "configDebug METHOD %d\n", server_.method());

		switch (server_.method()) {
			default:
			case HTTP_GET: {
				std::unique_ptr<cJSON, decltype(&cJSON_Delete)> features(cJSON_CreateObject(), &cJSON_Delete);
				for (auto const &[id, name] : log_->getRegisteredFeatures()) {
					if (!cJSON_HasObjectItem(features.get(), name.c_str())) {
						cJSON_AddBoolToObject(features.get(), name.c_str(), log_->isFeatureEnabled(id));
					}
				}
				std::unique_ptr<char, decltype(&cJSON_free)> payload(cJSON_PrintUnformatted(features.get()), &cJSON_free);
				server_.send(200, "application/json", payload.get());
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					return;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					return;
				}

				config::setDebugOptionsFromJson(body.c_str());
				DBGLOGFD(log_, logFeature_, "configDebug. Flags set.\n");

				File file = SPIFFS.open("/cfg/cfgdebug.json", FILE_WRITE);
				if (!file) {
					DBGLOGFD(log_, logFeature_, "configDebug. Can't open config file for write.\n");
					server_.send(500, "text/plain", "Internal server error. Can't save hardware settings.");
					break;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();

				DBGLOGFD(log_, logFeature_, "configDebug. Flags stored.\n");
				server_.send(201);
				break;
			}

		}
	}


	void configBoiler() {
		DBGLOGFD(log_, logFeature_, "configBoiler METHOD %d\n", server_.method());

		switch (server_.method()) {
			default:
			case HTTP_GET: {
				File file = SPIFFS.open("/cfg/cfgboiler.json", FILE_READ);
				if (!file) {
					server_.send(404, "text/plain", "FileNotFound");
					return;
				}
				server_.streamFile(file, "application/json");
				file.close();
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					break;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					break;
				}

				File file = SPIFFS.open("/cfg/cfgboiler.json", FILE_WRITE);
				if (!file) {
					DBGLOGFD(log_, logFeature_, "configBoiler. Can't open config file for write.\n");
					server_.send(500, "text/plain", "Internal server error. Can't save boiler settings.");
					break;
				}
				file.write((uint8_t *)body.c_str(), body.length());
				file.close();
				server_.send(201);
				break;
			}
		}
	}

	void temporaryOverride() {
		if (!server_.hasArg("plain")) {
			server_.send(204);
			return;
		}
		auto body = server_.arg("plain");
		if (body.isEmpty()) {
			server_.send(204);
			return;
		}

		std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(body.c_str()), &cJSON_Delete);

		auto obj = cJSON_GetObjectItem(root.get(), "temperature");
		if (!obj || obj->type != cJSON_Number) {
			DBGLOGFD(log_, logFeature_, "temporaryOverride bad request: '%s'\n", body.c_str());
			server_.send(400, "text/html", "Bad request. Missing temperature.");
			return;
		}
		auto temperature = obj->valueint;

		obj = cJSON_GetObjectItem(root.get(), "validSeconds");
		if (!obj || obj->type != cJSON_Number) {
			DBGLOGFD(log_, logFeature_, "temporaryOverride bad request: '%s'\n", body.c_str());
			server_.send(400, "text/html", "Bad request. Missing time.");
			return;
		}
		auto validSeconds = obj->valueint;

		obj = cJSON_GetObjectItem(root.get(), "roomName");
		if (!obj || obj->type != cJSON_String) {
			DBGLOGFD(log_, logFeature_, "temporaryOverride bad request: '%s'\n", body.c_str());
			server_.send(400, "text/html", "Bad request. Missing room name.");
			return;
		}
		auto roomName = obj->valuestring;

		DBGLOGFD(log_, logFeature_, "temporaryOverride '%s' temp: %d secs: %d\n", roomName, temperature, validSeconds);

		if (!controller_.setRoomTemporaryTemperature(roomName, temperature, validSeconds)) {
			std::ostringstream error;
			error << "Room " << roomName << " not found";
			std::string errorStr = error.str();
			server_.send(404, "text/plain", errorStr.c_str());
			return;
		}
		server_.send(201);
	}

	static bool validRoomId(std::string const &id) {
		return id.size() == 8 && id.find_first_not_of("0123456789abcdef") == std::string::npos;
	}

	using RoomValves = std::map<std::string, std::set<std::string>>;

	static bool parseRoomCatalog(cJSON *root, RoomValves &rooms) {
		if (!cJSON_IsArray(root)) return false;
		std::set<std::string> names;
		std::set<std::string> availableValves;
		auto pins = config::getValvePins();
		for (size_t i = 0; i < pins.size(); ++i) {
			availableValves.insert(std::to_string(i));
			if (!pins[i].label.empty()) availableValves.insert(pins[i].label);
		}
		for (auto item = root->child; item; item = item->next) {
			auto id = cJSON_GetObjectItemCaseSensitive(item, "id");
			auto name = cJSON_GetObjectItemCaseSensitive(item, "name");
			auto sensor = cJSON_GetObjectItemCaseSensitive(item, "sensor");
			auto valves = cJSON_GetObjectItemCaseSensitive(item, "valves");
			if (!cJSON_IsObject(item) || !cJSON_IsString(id) || !validRoomId(id->valuestring) || !cJSON_IsString(name) || !name->valuestring[0] || !names.insert(name->valuestring).second || !cJSON_IsString(sensor) || !cJSON_IsArray(valves)) return false;
			std::set<std::string> roomValves;
			for (auto valve = valves->child; valve; valve = valve->next) {
				std::string value;
				if (cJSON_IsString(valve)) value = valve->valuestring;
				else if (cJSON_IsNumber(valve) && valve->valuedouble == valve->valueint && valve->valueint >= 0) value = std::to_string(valve->valueint);
				else return false;
				if (!availableValves.count(value) || !roomValves.emplace(value).second) return false;
			}
			if (!rooms.emplace(id->valuestring, std::move(roomValves)).second) return false;
		}
		return true;
	}

	static bool readRoomCatalog(RoomValves &rooms) {
		File file = SPIFFS.open("/cfg/rooms.json", FILE_READ);
		if (!file) return false;
		std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(file.readString().c_str()), &cJSON_Delete);
		file.close();
		return root && parseRoomCatalog(root.get(), rooms);
	}

	static bool validProgram(cJSON *root, RoomValves const &rooms) {
		if (!cJSON_IsArray(root)) return false;
		std::set<std::string> used;
		for (auto item = root->child; item; item = item->next) {
			auto id = cJSON_GetObjectItemCaseSensitive(item, "room_id");
			if (!cJSON_IsObject(item) || !cJSON_IsString(id) || !rooms.count(id->valuestring) || !used.insert(id->valuestring).second) return false;
			for (auto field : {"base_temp", "temp_margin_up", "temp_margin_down"}) {
				if (!cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(item, field))) return false;
			}
			auto enabled = cJSON_GetObjectItemCaseSensitive(item, "enabled");
			if (!cJSON_IsTrue(enabled) && !cJSON_IsFalse(enabled)) return false;
			auto temperatures = cJSON_GetObjectItemCaseSensitive(item, "temperatures");
			if (temperatures && !cJSON_IsArray(temperatures)) return false;
			for (auto temp = temperatures ? temperatures->child : nullptr; temp; temp = temp->next) {
				if (!cJSON_IsObject(temp)) return false;
				auto overrideValves = cJSON_GetObjectItemCaseSensitive(temp, "valves");
				if (overrideValves && !cJSON_IsArray(overrideValves)) return false;
				for (auto valve = overrideValves ? overrideValves->child : nullptr; valve; valve = valve->next) {
					std::string value;
					if (cJSON_IsString(valve)) value = valve->valuestring;
					else if (cJSON_IsNumber(valve) && valve->valuedouble == valve->valueint && valve->valueint >= 0) value = std::to_string(valve->valueint);
					else return false;
					if (!rooms.at(id->valuestring).count(value)) return false;
				}
			}
		}
		return true;
	}

	void configRooms() {
		switch (server_.method()) {
			case HTTP_GET: {
				File file = SPIFFS.open("/cfg/rooms.json", FILE_READ);
				if (!file) { server_.send(404, "text/plain", "Room catalog not found"); return; }
				server_.streamFile(file, "application/json");
				file.close();
				return;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) { server_.send(400, "text/plain", "Missing room catalog"); return; }
				auto body = server_.arg("plain");
				std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(body.c_str()), &cJSON_Delete);
				if (!root || !cJSON_IsArray(root.get())) { server_.send(400, "text/plain", "Invalid room catalog"); return; }
				RoomValves rooms;
				if (!parseRoomCatalog(root.get(), rooms)) { server_.send(400, "text/plain", "Invalid room catalog"); return; }
				File dir = SPIFFS.open("/programs");
				while (dir) {
					File file = dir.openNextFile();
					if (!file) break;
					if (file.isDirectory()) continue;
					std::string filename = file.name();
					if (filename.size() < 5 || filename.substr(filename.size() - 5) != ".json") continue;
					std::unique_ptr<cJSON, decltype(&cJSON_Delete)> program(cJSON_Parse(file.readString().c_str()), &cJSON_Delete);
					if (!program || !validProgram(program.get(), rooms)) {
						server_.send(409, "text/plain", ("Room catalog conflicts with program '" + filename + "'. Remove missing rooms from that program and save it first.").c_str()); return;
					}
				}
				File file = SPIFFS.open("/cfg/rooms.json", FILE_WRITE);
				if (!file || file.write(reinterpret_cast<uint8_t const *>(body.c_str()), body.length()) != body.length()) { server_.send(500, "text/plain", "Could not save room catalog"); return; }
				file.close();
				controller_.reloadConfiguration();
				server_.send(205);
				return;
			}
			case HTTP_OPTIONS:
				server_.sendHeader("Allow", "OPTIONS, GET, POST");
				server_.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
				server_.send(204);
				return;
			default:
				server_.send(405, "text/plain", "Method not allowed");
				return;
		}
	}

	void configPrograms() {
		auto programName = server_.pathArg(0);
		if (programName.indexOf("..") >= 0 || programName.indexOf('/') >= 0 || programName.indexOf('\\') >= 0) {
			server_.send(400, "text/plain", "Invalid program name");
			return;
		}
		String filename = "/programs/" + programName + ".json";

		DBGLOGFD(log_, logFeature_, "configPrograms for '%s' METHOD %d\n", filename.c_str(), server_.method());

		switch (server_.method()) {
			case HTTP_GET: {
				if (!SPIFFS.exists(filename)) {
					server_.send(404, "text/plain", "Program " + server_.pathArg(0) + " not found");
					break;
				}

				DBGLOGFD(log_, logFeature_, "Reading config for '%s'\n", filename.c_str());
				File file = SPIFFS.open(filename, FILE_READ);
				server_.streamFile(file, "application/json");
				file.close();
				break;
			}
			case HTTP_POST: {
				if (!server_.hasArg("plain")) {
					server_.send(204);
					break;
				}
				auto body = server_.arg("plain");
				if (body.isEmpty()) {
					server_.send(204);
					break;
				}

				RoomValves rooms;
				std::unique_ptr<cJSON, decltype(&cJSON_Delete)> program(cJSON_Parse(body.c_str()), &cJSON_Delete);
				if (!readRoomCatalog(rooms) || !validProgram(program.get(), rooms)) {
					server_.send(400, "text/plain", "Invalid program or unknown room ID");
					break;
				}
				DBGLOGFD(log_, logFeature_, "Received program: '%s'\n", filename.c_str());
				File file = SPIFFS.open(filename, FILE_WRITE);
				if (!file) {
					server_.send(500, "text/plain", "Failed to open file for writing");
					break;
				}
				if (file.write(reinterpret_cast<uint8_t const *>(body.c_str()), body.length()) != body.length()) {
					file.close();
					server_.send(500, "text/plain", "Incomplete program write; reload and verify configuration");
					break;
				}
				file.close();

				auto currentProgram = config::getCurrentProgram();
				if (currentProgram == server_.pathArg(0).c_str()) {
					DBGLOGFD(log_, logFeature_, "Program reloaded: '%s'\n", filename.c_str());
					controller_.reloadConfiguration();
					server_.send(205);
					return;
				}
				server_.send(204);
				break;
			}
			case HTTP_DELETE: {
				if (!SPIFFS.exists(filename)) {
					server_.send(404, "text/plain", "Program " + server_.pathArg(0) + " not found");
					break;
				}
				if (SPIFFS.remove(filename)) {
					server_.send(204);
				} else {
					server_.send(500, "text/plain", "Internal server error during removing program " + server_.pathArg(0));
				}
				break;
			}
			case HTTP_OPTIONS:
				server_.sendHeader("Allow", "OPTIONS, GET, POST, DELETE");
				server_.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE");

				server_.send(204);
				break;
			default:
				server_.send(501, "text/plain", "Not implemented");
				break;
		}

	}

	void index() {
#ifdef OPENTHERMOSTAT_E32V2
		if(wifiAPMode) { server_.sendHeader("Location","/setup"); server_.send(302); return; }
#endif
		if (!filesystem.isMounted()) {
			recovery();
			return;
		}
		serveFile("/index.html");
	}

	void recovery() {
		static constexpr auto page = R"html(<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenThermostat recovery</title><script src="/auth-client.js"></script><style>body{font-family:sans-serif;max-width:42rem;margin:3rem auto;padding:0 1rem}button,input{font-size:1rem;margin:.5rem 0;padding:.6rem}progress{width:100%}</style></head>
<body><h1>OpenThermostat recovery</h1><p>Select the SPIFFS image built for this device. Keep the device powered until verification finishes.</p>
<input id="file" type="file" accept=".bin"><button id="upload">Upload filesystem</button><progress id="progress" max="100" value="0"></progress><pre id="status"></pre>
<script>
const button=document.getElementById('upload'),file=document.getElementById('file'),progress=document.getElementById('progress'),status=document.getElementById('status');
button.onclick=async()=>{if(!file.files.length){status.textContent='Select spiffs.bin first.';return}button.disabled=true;status.textContent='Uploading and verifying...';const data=new FormData();data.append('size',file.files[0].size);data.append('file',file.files[0]);const xhr=new XMLHttpRequest();xhr.open('POST','/otafs');try{const headers=window.OpenThermostatAuth?await window.OpenThermostatAuth.headers():{};for(const [name,value] of Object.entries(headers))xhr.setRequestHeader(name,value)}catch(error){button.disabled=false;status.textContent='Sign in again before uploading.';return}xhr.upload.onprogress=e=>{if(e.lengthComputable)progress.value=Math.round(e.loaded/e.total*100)};xhr.onload=()=>{button.disabled=false;status.textContent=xhr.status===200?'Update verified. Reboot the device.':'Update failed: '+xhr.responseText};xhr.onerror=()=>{button.disabled=false;status.textContent='Network error. The update was not confirmed.'};xhr.onabort=()=>{button.disabled=false;status.textContent='Upload aborted.'};xhr.timeout=300000;xhr.ontimeout=()=>{button.disabled=false;status.textContent='Upload timed out.'};xhr.send(data)};
</script></body></html>)html"sv;
		server_.sendView(200, "text/html"sv, page);
	}

	void serveFile(const char *serverPath) {
#ifdef OPENTHERMOSTAT_E32V2
		if(!control::safeStaticPath(serverPath)) { server_.send(400,"text/plain","Invalid path"); return; }
		const auto *asset=embedded::find(serverPath);String assetPath=serverPath;
		if(!asset){assetPath+=".gz";asset=embedded::find(assetPath.c_str());}
		if(asset){
			if(assetPath.endsWith(".gz"))server_.sendHeader("Content-Encoding","gzip");
			server_.sendView(200,getContentType(assetPath).second,std::string_view(reinterpret_cast<const char*>(asset->bytes),asset->size));return;
		}
#endif
		DBGLOGFD(log_, logFeature_, "Request for: '%s'\n", serverPath);

		String path = "/html";
		path += serverPath;

		if (!SPIFFS.exists(path)) {
			path += ".gz";
		}

		if (!SPIFFS.exists(path)) {
			server_.send(404, "text/plain", "FileNotFound");
			return;
		}
		File file = SPIFFS.open(path, FILE_READ);
		if (!file) {
			server_.send(500, "text/plain", "Internal Server Error. Can't open file.");
			return;
		}

		auto content = getContentType(path);

		if (content.first) {
			server_.sendHeader("Cache-Control", "max-age=3600");
			server_.sendHeader("Cache-Control", "private");
		}

		server_.streamFile(file, content.second);
		file.close();
	}

	std::pair<bool, const char *>getContentType(String path) {
		if (path.endsWith("css")) {
			return {false, "text/css"};
		} else if (path.endsWith("css.gz")) {
			return {false, "text/css"};
		} else if (path.endsWith("js")) {
			return {false, "text/javascript"};
		} else if (path.endsWith("js.gz")) {
			return {false, "text/javascript"};
		} else if (path.endsWith("png")) {
			return {true, "image/png"};
		} else if (path.endsWith("jpg")) {
			return {true, "image/jpeg"};
		} else if (path.endsWith("html.gz")) {
			return {false, "text/html"};
		} else if (path.endsWith("html")) {
			return {false, "text/html"};
		} else {
			return {true, "text/plain"};
		}
	}

	void handleOTAUpdate() {
		HTTPUpload &upload = server_.upload();
		if(upload.status==UPLOAD_FILE_START) ota_=OTAUpload{};
		if(!authorize(false)) {ota_.success=false;ota_.error=ESP_ERR_INVALID_STATE;ota_.errorMessage="Upload not authorized or updater busy";return;}

		if (upload.status == UPLOAD_FILE_START) {
			auto size = server_.arg("size");
			long fileSize = atol(size.c_str());

			DBGLOGFD(log_, logFeature_, "handleOTA START '%s', totalSize: '%zu'\n", upload.filename.c_str(), fileSize);

			ota_ = OTAUpload{};

			ota_.partition = esp_ota_get_next_update_partition(NULL);
			if (!ota_.partition) {
				DBGLOGFD(log_, logFeature_, "OTA partition not found\n");
				ota_.errorMessage = "OTA partition not found"sv;
				ota_.error = -1;
				return;
			}

			if (fileSize > 0 && fileSize > ota_.partition->size) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate Partition size %zu smaller than binary file %zu!\n", ota_.partition->size, fileSize);
				ota_.errorMessage = "Partition smaller than file"sv;
				ota_.error = -1;
				return;
			}


			DBGLOGFD(log_, logFeature_, "handleOTA Found partition '%s', size: %d, encrypted: %d\n", ota_.partition->label, ota_.partition->size, ota_.partition->encrypted);

			DBGLOGFD(log_, logFeature_, "Beginning OTA\n");

			if (esp_ota_mark_app_valid_cancel_rollback() != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "Beginning OTA: esp_ota_mark_app_valid_cancel_rollback failed\n");
			}

			ota_.error = esp_ota_begin(ota_.partition, OTA_SIZE_UNKNOWN, &ota_.handle);
			if (ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "Beginning OTA failed!\n");
				return;
			}
			ota_.started = true;

			DBGLOGFD(log_, logFeature_, "Beginning OTA handle: %d\n", ota_.handle);
		} else if (upload.status == UPLOAD_FILE_WRITE) {
			if (!ota_.started || ota_.error != ESP_OK) {
				if (!ota_.writeErrorReported) {
					DBGLOGFD(log_, logFeature_, "handleOTA writing skipped, OTA error: %d\n", ota_.error);
					ota_.writeErrorReported = true;
				}
				return;
			}

			DBGLOGFD(log_, logFeature_, "handleOTA writing to OTA handle %d, size: %zu\n", ota_.handle, upload.currentSize);

			ota_.error = esp_ota_write(ota_.handle, upload.buf, upload.currentSize);
			if (ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "handleOTA writing to OTA handle %d, size: %zu FAILED, error: %d\n", ota_.handle, upload.currentSize, ota_.error);
				esp_ota_abort(ota_.handle);
				return;
			}
		} else if (upload.status == UPLOAD_FILE_END) {
			if (!ota_.started || ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "handleOTA upload end, error: %d\n", ota_.error);
				return;
			}

			DBGLOGFD(log_, logFeature_, "handleOTA ending OTA\n");

			ota_.error = esp_ota_end(ota_.handle);
			if (ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "handleOTA finalizing OTA handle %d, FAILED, error: %d\n", ota_.handle, ota_.error);
				return;
			}

			DBGLOGFD(log_, logFeature_, "handleOTA setting boot partition\n");

			ota_.error = esp_ota_set_boot_partition(ota_.partition);
			if (ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "handleOTA setting boot partition FAILED, error: %d\n", ota_.error);
				return;
			}
			ota_.success = true;

		} else if (upload.status == UPLOAD_FILE_ABORTED) {
			if (!ota_.started) {
				DBGLOGFD(log_, logFeature_, "handleOTA upload aborted, OTA not started. Error: %d\n", ota_.error);
				return;
			}
			DBGLOGFD(log_, logFeature_, "handleOTA ABORTED\n");
			esp_ota_abort(ota_.handle);
		}
	}

	void handleOTAResponse() {
		auto ctype = "text/plain"sv;
		if (ota_.success) {
			server_.sendView(200, ctype, "success"sv);
#ifdef OPENTHERMOSTAT_E32V2
			// This response is shared with SPIFFS; only a selected app schedules
			// automatic restart, after the HTTP response has been sent.
			if(server_.uri()=="/ota") update::firmwareInstalled();
#endif
		} else {
			ib::viewable_stringbuf payloadBuf;
			std::ostream ss(&payloadBuf);
			ss << "Failure: ";
			ss << ota_.errorMessage << " (" << ota_.error << ')';
			server_.sendView(500, ctype, payloadBuf.view());
		}
	}

	void handleOTAFFSUpdate() {
		HTTPUpload &upload = server_.upload();
		if(upload.status==UPLOAD_FILE_START) ota_=OTAUpload{};
		if(!authorize(false)) {ota_.success=false;ota_.error=ESP_ERR_INVALID_STATE;ota_.errorMessage="Upload not authorized or updater busy";return;}

		if (upload.status == UPLOAD_FILE_START) {
			auto size = server_.arg("size");
			size_t fileSize = strtoull(size.c_str(), nullptr, 10);

			DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate START '%s', totalSize: '%zu'\n", upload.filename.c_str(), fileSize);

			ota_ = OTAUpload{};
			ota_.partition = filesystem.updatePartition();
			if (!ota_.partition) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate partition not found\n");
				ota_.errorMessage = "FS partition not found"sv;
				ota_.error = -1;
				return;
			}

			DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate Found partition '%s', size: %d, encrypted: %d\n", ota_.partition->label, ota_.partition->size, ota_.partition->encrypted);

			if (fileSize == 0 || fileSize != ota_.partition->size) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate Partition size %zu differs from binary file %zu!\n", ota_.partition->size, fileSize);
				ota_.errorMessage = "FS image size must equal partition size"sv;
				ota_.error = -1;
				return;
			}

			ota_.expectedSize = fileSize;
			ota_.dualFilesystem = filesystem.hasDualPartitions();
			mbedtls_sha256_init(&ota_.checksum);
			if (mbedtls_sha256_starts_ret(&ota_.checksum, 0) != 0) {
				ota_.error = ESP_FAIL;
				ota_.errorMessage = "FS checksum initialization failed"sv;
				return;
			}
			ota_.checksumStarted = true;
			filesystem.beginSinglePartitionUpdate();
			ota_.started = true;
		} else if (upload.status == UPLOAD_FILE_WRITE) {
			if (!ota_.started || ota_.error != ESP_OK) {
				if (!ota_.writeErrorReported) {
					DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate writing skipped, OTA error: %d\n", ota_.error);
					ota_.writeErrorReported = true;
				}
				return;
			}
			if (ota_.offset > ota_.expectedSize || upload.currentSize > ota_.expectedSize - ota_.offset) {
				ota_.error = ESP_ERR_INVALID_SIZE;
				ota_.errorMessage = "FS upload exceeds partition size"sv;
				return;
			}

			auto writeEnd = ota_.offset + upload.currentSize;
			auto eraseEnd = (writeEnd + SPI_FLASH_SEC_SIZE - 1) & ~(SPI_FLASH_SEC_SIZE - 1);
			if (eraseEnd > ota_.erasedUntil) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate erasing SPIFFS offset: %zu, size: %zu\n", ota_.erasedUntil, eraseEnd - ota_.erasedUntil);
				ota_.error = esp_partition_erase_range(ota_.partition, ota_.erasedUntil, eraseEnd - ota_.erasedUntil);
				if (ota_.error != ESP_OK) {
					ota_.errorMessage = "FS partition erase failure"sv;
					return;
				}
				ota_.erasedUntil = eraseEnd;
			}

			DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate writing SPIFFS offset: %zu, size: %zu\n", ota_.offset, upload.currentSize);
			ota_.error = esp_partition_write(ota_.partition, ota_.offset, upload.buf, upload.currentSize);
			if (ota_.error != ESP_OK) {
				ota_.errorMessage = "FS partition write error"sv;
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate Failed to write SPIFFS partition: %d\n", ota_.error);
				return;
			}
			if (mbedtls_sha256_update_ret(&ota_.checksum, upload.buf, upload.currentSize) != 0) {
				ota_.error = ESP_FAIL;
				ota_.errorMessage = "FS checksum update failed"sv;
				return;
			}
			ota_.offset += upload.currentSize;
		} else if (upload.status == UPLOAD_FILE_END) {
			if (!ota_.started || ota_.error != ESP_OK) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate upload end, error: %d\n", ota_.error);
				finishFilesystemChecksum();
				return;
			}
			if (ota_.offset != ota_.expectedSize) {
				ota_.error = ESP_ERR_INVALID_SIZE;
				ota_.errorMessage = "FS upload is incomplete"sv;
				if (!ota_.dualFilesystem) filesystem.restoreActive();
				finishFilesystemChecksum();
				return;
			}
			std::array<unsigned char, 32> uploadChecksum{};
			if (!ota_.checksumStarted || mbedtls_sha256_finish_ret(&ota_.checksum, uploadChecksum.data()) != 0) {
				finishFilesystemChecksum();
				ota_.error = ESP_FAIL;
				ota_.errorMessage = "FS checksum finalization failed"sv;
				return;
			}
			finishFilesystemChecksum();
			if (!verifyPartitionChecksum(ota_.partition, ota_.expectedSize, uploadChecksum)) {
				ota_.error = ESP_ERR_INVALID_CRC;
				ota_.errorMessage = "FS checksum verification failed"sv;
				DBGLOGFI(log_, logFeature_, "handleOTAFFSUpdate SHA-256 read-back verification FAILED for partition '%s'\n", ota_.partition->label);
				if (!ota_.dualFilesystem) filesystem.restoreActive();
				return;
			}
			DBGLOGFI(log_, logFeature_, "handleOTAFFSUpdate SHA-256 read-back verification passed for partition '%s'\n", ota_.partition->label);
			std::string validationResult;
			if (!filesystem.validateAndSelectUpdate(ota_.partition, validationResult)) {
				ota_.error = ESP_ERR_INVALID_STATE;
				ota_.errorMessage = "FS image validation or slot selection failed"sv;
				DBGLOGFI(log_, logFeature_, "handleOTAFFSUpdate final validation FAILED: %s\n", validationResult.c_str());
				return;
			}
			DBGLOGFI(log_, logFeature_, "handleOTAFFSUpdate final validation passed: %s\n", validationResult.c_str());
			ota_.success = true;
		} else if (upload.status == UPLOAD_FILE_ABORTED) {
			if (!ota_.started) {
				DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate upload aborted. Not started. Error: %d\n", ota_.error);
				return;
			}
			DBGLOGFD(log_, logFeature_, "handleOTAFFSUpdate ABORTED\n");
			ota_.error = ESP_FAIL;
			ota_.errorMessage = "FS upload aborted"sv;
			finishFilesystemChecksum();
			if (!ota_.dualFilesystem) filesystem.restoreActive();
		}
	}

	void finishFilesystemChecksum() {
		if (!ota_.checksumStarted) return;
		mbedtls_sha256_free(&ota_.checksum);
		ota_.checksumStarted = false;
	}

	bool verifyPartitionChecksum(const esp_partition_t *partition, size_t size, const std::array<unsigned char, 32> &expected) {
		std::unique_ptr<uint8_t[]> buffer(new (std::nothrow) uint8_t[SPI_FLASH_SEC_SIZE]);
		if (!buffer) return false;

		mbedtls_sha256_context checksum;
		mbedtls_sha256_init(&checksum);
		if (mbedtls_sha256_starts_ret(&checksum, 0) != 0) {
			mbedtls_sha256_free(&checksum);
			return false;
		}

		for (size_t offset = 0; offset < size; offset += SPI_FLASH_SEC_SIZE) {
			auto chunkSize = std::min(static_cast<size_t>(SPI_FLASH_SEC_SIZE), size - offset);
			if (esp_partition_read(partition, offset, buffer.get(), chunkSize) != ESP_OK ||
				mbedtls_sha256_update_ret(&checksum, buffer.get(), chunkSize) != 0) {
				mbedtls_sha256_free(&checksum);
				return false;
			}
			delay(0);
		}

		std::array<unsigned char, 32> actual{};
		auto result = mbedtls_sha256_finish_ret(&checksum, actual.data());
		mbedtls_sha256_free(&checksum);
		return result == 0 && std::memcmp(actual.data(), expected.data(), actual.size()) == 0;
	}

	struct OTAUpload {
		bool started = false;
		bool success = false;
		const esp_partition_t *partition = nullptr;
		size_t offset = 0;
		size_t expectedSize = 0;
		size_t erasedUntil = 0;
		esp_ota_handle_t handle = 0;
		esp_err_t error = ESP_OK;
		std::string errorMessage;
		bool writeErrorReported = false;
		bool dualFilesystem = false;
		bool checksumStarted = false;
		mbedtls_sha256_context checksum{};
	} ota_;

	HeatingController &controller_;
	WebServerStringView server_;

};

}
