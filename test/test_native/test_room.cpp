#include <gtest/gtest.h>
#include "CircularBuffer.h"
#include "Room.h"
#include <chrono>
#include <tuple>
#include <optional>

// ============================================================================
// Temperature Average / CircularBuffer Tests
// ============================================================================

using steady_clock = std::chrono::steady_clock;
using temperatureData_t = std::tuple<steady_clock::time_point, int16_t>;

// Reimplementation of getAverageTemperature logic for testing without Arduino deps
static std::optional<int16_t> calcAverageTemperature(ib::CircularBuffer<temperatureData_t, 10> const &data, std::chrono::minutes maxAge) {
	int32_t avgTemp = 0;
	auto currentTime = steady_clock::now();
	size_t validSamples = 0;

	for (size_t i = 0; i < data.size(); i++) {
		auto sampleTime = std::get<0>(data.get(i));
		if (currentTime - sampleTime <= maxAge) {
			validSamples++;
			avgTemp += std::get<1>(data.get(i));
		}
	}

	if (validSamples == 0) {
		return std::nullopt;
	}

	avgTemp /= validSamples;
	return static_cast<int16_t>(avgTemp);
}

TEST(AverageTemperatureTest, SingleSample) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	buf.push({steady_clock::now(), 2250});

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	ASSERT_TRUE(result.has_value());
	EXPECT_EQ(result.value(), 2250);
}

TEST(AverageTemperatureTest, MultipleSamples) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	auto now = steady_clock::now();

	buf.push({now, 2200});
	buf.push({now, 2300});
	buf.push({now, 2400});

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	ASSERT_TRUE(result.has_value());
	EXPECT_EQ(result.value(), 2300);
}

TEST(AverageTemperatureTest, OldSamplesFiltered) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	auto now = steady_clock::now();

	buf.push({now - std::chrono::minutes(10), 1000});
	buf.push({now, 2500});

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	ASSERT_TRUE(result.has_value());
	EXPECT_EQ(result.value(), 2500);
}

TEST(AverageTemperatureTest, AllSamplesExpired) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	auto now = steady_clock::now();

	buf.push({now - std::chrono::minutes(10), 2000});
	buf.push({now - std::chrono::minutes(5), 2100});

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	EXPECT_FALSE(result.has_value());
}

TEST(AverageTemperatureTest, EmptyBuffer) {
	ib::CircularBuffer<temperatureData_t, 10> buf;

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	EXPECT_FALSE(result.has_value());
}

TEST(AverageTemperatureTest, NoOverflowWithManySamples) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	auto now = steady_clock::now();

	for (int i = 0; i < 10; i++) {
		buf.push({now, 3000});
	}

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	ASSERT_TRUE(result.has_value());
	EXPECT_EQ(result.value(), 3000);
}

TEST(AverageTemperatureTest, BufferWraparound) {
	ib::CircularBuffer<temperatureData_t, 10> buf;
	auto now = steady_clock::now();

	for (int i = 0; i < 15; i++) {
		buf.push({now, static_cast<int16_t>(2000 + i * 10)});
	}

	auto result = calcAverageTemperature(buf, std::chrono::minutes(3));
	ASSERT_TRUE(result.has_value());
	// Last 10: 2050..2140, average = 2095
	EXPECT_EQ(result.value(), 2095);
}

// ============================================================================
// TemporaryOverride Tests
// ============================================================================

// Use the production monotonic override, rather than a second implementation.
using TemporaryOverride = heating::Room::TemporaryOverride;

TEST(TemporaryOverrideTest, IsValidImmediately) {
	TemporaryOverride ov(2500, 60);
	EXPECT_TRUE(ov.isValid());
	EXPECT_EQ(ov.getTemperature(), 2500);
	EXPECT_GT(ov.getSecondsLeft(), 55u);
	EXPECT_LE(ov.getSecondsLeft(), 60u);
}

TEST(TemporaryOverrideTest, ZeroLifetime) {
	TemporaryOverride ov(2500, 0);
	EXPECT_FALSE(ov.isValid());
	EXPECT_EQ(ov.getSecondsLeft(), 0u);
}
