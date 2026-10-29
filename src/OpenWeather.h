#pragma once

#include "config.h"
#include "Logging.h"
#include "control/WeatherObservation.h"
#include "control/BoundedJson.h"
#include <HTTPClient.h>
#include <esp_timer.h>
#include <ctime>
#include <cJSON.h>
#include <memory>
#include <mutex>

namespace heating {

namespace openweather {

static void fetchTask(void *pvParameters);
}

class OpenWeather {
public:
	ib::logger::LoggerInterface::LogFeatureType getLogFeature() const { return logFeature_; }
	std::shared_ptr<ib::logger::LoggerInterface> getLogger() const { return log_; }
	OpenWeather(std::shared_ptr<ib::logger::LoggerInterface> log, config::OpenWeatherConfig config) : log_(std::move(log)), config_(std::move(config)), query_(buildQuery()), lastFetch_(0) {
		if (log_) {
			logFeature_ = log_->addFeature("OpenWeather");
		}
		DBGLOGFD(log_, logFeature_, "Configuration. Enabled: %d interval: %d\n", config_.enabled, config_.interval);
	}

	void operate() {
		if (!config_.enabled) {
			return;
		}

		auto now = millis();
		// Elapsed time by unsigned subtraction: stays correct across the millis() wrap (49.7 days).
		if (lastFetch_ > 0 && now - lastFetch_ < static_cast<unsigned long>(config_.interval) * 1000ul) {
			unsigned long timeToWait = static_cast<unsigned long>(config_.interval * 1000);
			DBGLOGFD(log_, logFeature_, "Interval: %ld\n", timeToWait);
			timeToWait = timeToWait - (now - lastFetch_);
			DBGLOGFD(log_, logFeature_, "Waiting for interval (%ds) last: %ld, now: %ld, still need to wait for: %ld ms \n", config_.interval, lastFetch_, now, timeToWait);
			return;
		}

		DBGLOGFD(log_, logFeature_, "Requesting temperature, last: %ld, now: %ld\n", lastFetch_, now);
		lastFetch_ = now;

		xTaskCreate(heating::openweather::fetchTask, "OWTask", 2500, this, 1, NULL);
	}

	std::string getStatus() const {
		std::lock_guard<std::mutex> lock(mutex_);

		if (payload_.isEmpty()) {
			return "{}";
		}
		return {payload_.c_str(), payload_.length()};
	}

	struct Outdoor {
		bool valid = false;
		int16_t temp = 0;
		uint8_t humidity = 0;
		uint16_t pressure = 0;
		uint64_t date = 0;
	};

	std::optional<int16_t> getTemperature() {
		std::unique_lock<std::mutex> lock(mutex_);
		return temperatureSample_.value(static_cast<uint64_t>(esp_timer_get_time()/1000));
	}

private:
	std::shared_ptr<ib::logger::LoggerInterface> log_;
	ib::logger::LoggerInterface::LogFeatureType logFeature_{};
	void parsePayload(String const &payload) {
		outdoor_.valid = false;
		// Parsed on the small OpenWeather task stack: a shallow document only.
		std::unique_ptr<cJSON, decltype(&cJSON_Delete)> data(control::parseNestedJson(payload, false, 6));

		auto main = cJSON_GetObjectItem(data.get(), "main");
		if (!main || main->type != cJSON_Object ||
		    !control::receiveWeatherObservation(temperatureSample_,data.get(),std::time(nullptr),
		                                       static_cast<uint64_t>(esp_timer_get_time()/1000))) {
			temperatureSample_.unavailable();
			DBGLOGFD(log_, logFeature_, "Error, missing main\n", nullptr);
			return;
		}

		auto accepted = temperatureSample_.value(static_cast<uint64_t>(esp_timer_get_time()/1000));
		if (!accepted) return;
		outdoor_.temp = *accepted;
		outdoor_.pressure = static_cast<int16_t>(json::getInt(main, "pressure"));
		outdoor_.humidity = static_cast<uint8_t>(json::getInt(main, "humidity"));
		outdoor_.date = json::getInt(data.get(), "dt");
		outdoor_.valid = true;
	}

	void getData() {
		std::unique_lock<std::mutex> lock(mutex_);
		if (getDataInProgress_) {
			DBGLOGFD(log_, logFeature_, "getData already in progress\n");
			return;
		}
		getDataInProgress_ = true;
		lock.unlock();

		http_.begin(query_.c_str());
		int httpResponseCode = http_.GET();
		if (httpResponseCode > 0) {
			auto payload = http_.getString();

			lock.lock();
			payload_ = std::move(payload);
			DBGLOGFD(log_, logFeature_, "Content size: %d. Response: %d\n", http_.getSize(), httpResponseCode);
			if (payload_.length() > 0) {
				parsePayload(payload_);
				DBGLOGFD(log_, logFeature_, "Date: %ld Temp: %f, Humidity: %d%% Pressure: %d hPa\n", static_cast<unsigned long>(outdoor_.date), static_cast<float>(outdoor_.temp) / 100, static_cast<int>(outdoor_.humidity), static_cast<int>(outdoor_.pressure));
			}
			lock.unlock();

		}
		else {
			DBGLOGFD(log_, logFeature_, "Error code %d\n", httpResponseCode);
		}
		http_.end();
		lock.lock();
		getDataInProgress_ = false;
	}

	std::string buildQuery() {
		return "http://api.openweathermap.org/data/2.5/weather?lat=" + config_.latitude + "&lon=" + config_.longitude + "&appid=" + config_.appid + "&units=metric";
	}

	HTTPClient http_;
	config::OpenWeatherConfig config_;
	std::string query_;
	unsigned long lastFetch_;
	Outdoor outdoor_;
	control::WeatherObservation temperatureSample_;
	String payload_;
	mutable std::mutex mutex_;
	bool getDataInProgress_ = false;
	friend void heating::openweather::fetchTask(void *pvParameters);


};

namespace openweather {
static void fetchTask(void *pvParameters) {
	auto ow = reinterpret_cast<OpenWeather *>(pvParameters);
	ow->getData();
	DBGLOGFD(ow->getLogger(), ow->getLogFeature(), "Free memory %d/%d (minimum was: %d) MaxAlloc: %d MinPeekStack: %d UpTime: %lds\n", ESP.getFreeHeap(), ESP.getHeapSize(), ESP.getMinFreeHeap(), ESP.getMaxAllocHeap(), uxTaskGetStackHighWaterMark(nullptr), millis()/1000);
	vTaskDelete(NULL);
}
}

}
