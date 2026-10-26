// Stubs for Arduino-dependent symbols
#include <gtest/gtest.h>
#include "Logging.h"

namespace heating {
std::shared_ptr<ib::logger::LoggerInterface> logger;
}

// Compile the actual production scheduling helpers; only SDK boundaries are stubbed.
#include "../../src/RoomConfig.cpp"

int main(int argc, char **argv) {
	::testing::InitGoogleTest(&argc, argv);
	return RUN_ALL_TESTS();
}
