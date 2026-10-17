// Board policy is tested in a separate translation unit with the actual flag.
#define OPENTHERMOSTAT_E32V2
#include "Board.h"
#include "Network.h"
#include <gtest/gtest.h>

TEST(E32V2, TransmissionAndAuxiliaryOutputsAreLocked) {
    EXPECT_FALSE(heating::board::emsTransmitAllowed);
    EXPECT_FALSE(heating::board::auxiliaryGpioAllowed);
    EXPECT_EQ(heating::board::emsRx, 4);
    EXPECT_EQ(heating::board::emsTx, 5);
}

TEST(E32V2, BusPinsDoNotOverlapEthernetFlashOrPsram) {
    const int reserved[] = {0, 15, 18, 19, 21, 22, 23, 25, 26, 27,
                            6, 7, 8, 9, 10, 11, 16, 17};
    for (int pin : reserved) {
        EXPECT_NE(pin, heating::board::emsRx);
        EXPECT_NE(pin, heating::board::emsTx);
    }
}

TEST(E32V2, NetworkSelectionAndRecovery) {
    using heating::NetworkInterface;
    using heating::chooseNetwork;
    EXPECT_EQ(chooseNetwork(false, false, false), NetworkInterface::none);
    EXPECT_EQ(chooseNetwork(false, false, true), NetworkInterface::wifi);
    EXPECT_EQ(chooseNetwork(true, false, true), NetworkInterface::wifi); // DHCP pending
    EXPECT_EQ(chooseNetwork(true, true, false), NetworkInterface::ethernet);
    EXPECT_EQ(chooseNetwork(true, true, true), NetworkInterface::ethernet);
    EXPECT_EQ(chooseNetwork(false, true, true), NetworkInterface::wifi); // stale IP, cable lost
    EXPECT_EQ(chooseNetwork(false, true, false), NetworkInterface::none);
    EXPECT_EQ(chooseNetwork(true, true, true), NetworkInterface::ethernet); // cable recovery
}
