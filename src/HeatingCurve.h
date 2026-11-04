#pragma once

#include <array>
#include <cstdint>
#include <cJSON.h>

namespace heating {

/// Pure heating curve interpolation — no hardware dependencies.
/// @param outdoorTemperature  outdoor temp in 1/100 °C (e.g. 570 = 5.7 °C)
/// @param heatingCurve        9-element array of heating temps in °C for outdoor axis [20,15,10,5,0,-5,-10,-15,-20]
/// @return heating temperature in 1/100 °C
inline int16_t calcHeatingTemperature(int16_t outdoorTemperature, std::array<uint8_t, 9> const &heatingCurve) {
	static constexpr std::array<int8_t, 9> hcOutdoorAxis{20, 15, 10, 5, 0, -5, -10, -15, -20};

	for (size_t idx = 0; idx < hcOutdoorAxis.size(); ++idx) {
		if (hcOutdoorAxis[idx] * 100 <= outdoorTemperature) {
			if (idx == 0) {
				return heatingCurve[idx] * 100;
			} else {
				float slope = static_cast<float>(heatingCurve[idx] - heatingCurve[idx - 1]) /
				              static_cast<float>(hcOutdoorAxis[idx] - hcOutdoorAxis[idx - 1]);
				float intercept = heatingCurve[idx - 1] * 100 - (slope * hcOutdoorAxis[idx - 1] * 100);
				return static_cast<int16_t>(slope * outdoorTemperature + intercept);
			}
		}
	}

	return heatingCurve[8] * 100;
}

/// The legacy boiler settings' "heatingCurve" (cfgboiler.json, POST /config/boiler): exactly nine
/// numbers of 0..100 °C for the outdoor axis above. Review R2-06: a longer list was copied past the
/// end of the array on the stack (at every boot). False, `out` unchanged: anything else.
inline bool readHeatingCurvePoints(const cJSON *array, std::array<uint8_t, 9> &out) {
	if (!cJSON_IsArray(array)) return false;
	std::array<uint8_t, 9> points{};
	size_t count = 0;
	for (const cJSON *item = array->child; item; item = item->next) {
		if (count == points.size() || !cJSON_IsNumber(item) || !(item->valuedouble >= 0 && item->valuedouble <= 100)) return false;
		points[count++] = static_cast<uint8_t>(item->valuedouble);
	}
	if (count != points.size()) return false;
	out = points;
	return true;
}

}
