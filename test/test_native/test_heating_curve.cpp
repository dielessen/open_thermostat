#include <gtest/gtest.h>
#include "HeatingCurve.h"
#include <memory>
#include <string>

class HeatingCurveTest : public ::testing::Test {
protected:
	// Example curve: at 20°C→20, 15°C→25, 10°C→30, 5°C→35, 0°C→45, -5°C→55, -10°C→65, -15°C→75, -20°C→80
	std::array<uint8_t, 9> curve = {{20, 25, 30, 35, 45, 55, 65, 75, 80}};
};

TEST_F(HeatingCurveTest, ExactAxisPoints) {
	EXPECT_EQ(heating::calcHeatingTemperature(2000, curve), 2000); // 20°C → 20°C
	EXPECT_EQ(heating::calcHeatingTemperature(1500, curve), 2500); // 15°C → 25°C
	EXPECT_EQ(heating::calcHeatingTemperature(1000, curve), 3000); // 10°C → 30°C
	EXPECT_EQ(heating::calcHeatingTemperature(500, curve), 3500);  //  5°C → 35°C
	EXPECT_EQ(heating::calcHeatingTemperature(0, curve), 4500);    //  0°C → 45°C
	EXPECT_EQ(heating::calcHeatingTemperature(-500, curve), 5500); // -5°C → 55°C
	EXPECT_EQ(heating::calcHeatingTemperature(-1000, curve), 6500); // -10°C → 65°C
	EXPECT_EQ(heating::calcHeatingTemperature(-1500, curve), 7500); // -15°C → 75°C
	EXPECT_EQ(heating::calcHeatingTemperature(-2000, curve), 8000); // -20°C → 80°C
}

TEST_F(HeatingCurveTest, InterpolationBetweenPoints) {
	// Between 20°C (→20) and 15°C (→25): slope = (25-20)/(15-20) = -1
	// At 17.5°C (1750): should be ~22.5°C (2250)
	EXPECT_EQ(heating::calcHeatingTemperature(1750, curve), 2250);

	// Between 0°C (→45) and -5°C (→55): slope = (55-45)/(-5-0) = -2
	// At -2.5°C (-250): should be 50°C (5000)
	EXPECT_EQ(heating::calcHeatingTemperature(-250, curve), 5000);
}

TEST_F(HeatingCurveTest, AboveMaxOutdoor) {
	EXPECT_EQ(heating::calcHeatingTemperature(2500, curve), 2000); // 25°C → 20°C
	EXPECT_EQ(heating::calcHeatingTemperature(3500, curve), 2000); // 35°C → 20°C
}

TEST_F(HeatingCurveTest, BelowMinOutdoor) {
	EXPECT_EQ(heating::calcHeatingTemperature(-2500, curve), 8000); // -25°C → 80°C
	EXPECT_EQ(heating::calcHeatingTemperature(-3000, curve), 8000); // -30°C → 80°C
}

TEST_F(HeatingCurveTest, FractionalOutdoorTemperature) {
	// 5.7°C = 570 — between 10°C (→30) and 5°C (→35)
	// slope = -1, intercept = 4000, result = -1 * 570 + 4000 = 3430
	EXPECT_EQ(heating::calcHeatingTemperature(570, curve), 3430);
}

TEST_F(HeatingCurveTest, FlatCurve) {
	std::array<uint8_t, 9> flat = {{40, 40, 40, 40, 40, 40, 40, 40, 40}};
	EXPECT_EQ(heating::calcHeatingTemperature(1500, flat), 4000);
	EXPECT_EQ(heating::calcHeatingTemperature(0, flat), 4000);
	EXPECT_EQ(heating::calcHeatingTemperature(-1500, flat), 4000);
}

// Review R2-06: cfgboiler.json's "heatingCurve" is copied into a 9-point array at every boot;
// a longer list wrote past it on the stack. Only exactly nine numbers of 0..100 are taken.
TEST(HeatingCurvePoints, OnlyExactlyNineNumbersInRangeAreTaken) {
	const auto points = [](const std::string &json, std::array<uint8_t, 9> &out) {
		std::unique_ptr<cJSON, decltype(&cJSON_Delete)> root(cJSON_Parse(json.c_str()), cJSON_Delete);
		return heating::readHeatingCurvePoints(root.get(), out);
	};
	const auto list = [](size_t n, const char *value = "50") {
		std::string json = "[";
		for (size_t i = 0; i < n; ++i) json += std::string(i ? "," : "") + value;
		return json + "]";
	};
	const std::array<uint8_t, 9> kept{{1, 2, 3, 4, 5, 6, 7, 8, 9}};
	std::array<uint8_t, 9> out = kept;
	ASSERT_TRUE(points("[30,30,37,46,55,63,72,75,75]", out));
	EXPECT_EQ(out, (std::array<uint8_t, 9>{{30, 30, 37, 46, 55, 63, 72, 75, 75}}));
	EXPECT_TRUE(points("[0,100,37.9,0,0,0,0,0,0]", out));
	EXPECT_EQ(out[1], 100); EXPECT_EQ(out[2], 37); // a fraction is cut like the old valueint
	for (const std::string &bad : {list(0), list(8), list(10), list(1000), list(9, "-1"), list(9, "300"), list(9, "100.5"),
	                              list(9, "\"40\""), list(9, "null"), list(9, "[40]"), std::string("{\"a\":1}"), std::string("40")}) {
		out = kept;
		EXPECT_FALSE(points(bad, out)) << bad.substr(0, 40);
		EXPECT_EQ(out, kept) << bad.substr(0, 40); // untouched, nothing written past nine
	}
	EXPECT_FALSE(heating::readHeatingCurvePoints(nullptr, out));
}
