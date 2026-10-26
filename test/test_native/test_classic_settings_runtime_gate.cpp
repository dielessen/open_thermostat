#include "EMS/ClassicSettingsRuntimeGate.h"
#include "control/HttpAccessPolicy.h"
#ifndef OPENTHERMOSTAT_E32V2
#define OPENTHERMOSTAT_E32V2
#endif
#include "Board.h"
#include <gtest/gtest.h>
namespace {
using Gate=heating::ems::ClassicSettingsRuntimeGate;
TEST(ClassicSettingsRuntime, AttendedManualPermissionDoesNotEnableSettingsOrGeneralOutputs){
    EXPECT_FALSE(heating::board::emsSettingsTransmitAllowed);
    EXPECT_TRUE(heating::board::emsManualTestTransmitAllowed);
    EXPECT_FALSE(heating::board::emsTransmitAllowed);
    EXPECT_FALSE(Gate::permitted({}));
}
TEST(ClassicSettingsRuntime, AllMandatoryPhysicalAndSoftwareConditionsAreRequired){
    const Gate::Conditions reviewed{true,true,true,true,true,false,false,true};
    ASSERT_TRUE(Gate::permitted(reviewed));
    for(int missing=0;missing<6;++missing){auto c=reviewed;
        switch(missing){case 0:c.compiled=false;break;case 1:c.installationReviewed=false;break;
            case 2:c.emsEnabled=false;break;case 3:c.classic=false;break;case 4:c.transportReady=false;break;
            case 5:c.updateAllowed=false;break;}
        EXPECT_FALSE(Gate::permitted(c));
    }
}
TEST(ClassicSettingsRuntime, CommissioningOrConfigurationReadCannotShareSettingsWriter){
    Gate::Conditions c{true,true,true,true,true,false,false,true};
    c.trialActive=true;EXPECT_FALSE(Gate::permitted(c));c.trialActive=false;
    c.configurationReadActive=true;EXPECT_FALSE(Gate::permitted(c));
}
TEST(ClassicSettingsRuntime, ActiveSettingsBlockCompetingMutationsButPreserveLogoutStopAndIdempotency){
    using heating::control::boilerSettingsMutationBlocked;
    for(auto path:{"/updates/check","/updates/install","/updates/reboot","/updates/rollback","/ota","/otafs",
                   "/config/device","/config/reboot","/config/rooms","/boiler/test/prepare","/boiler/test/prepare_zero",
                   "/boiler/test/start","/boiler/test/read_configuration"}){
        EXPECT_TRUE(boilerSettingsMutationBlocked(path,true));EXPECT_FALSE(boilerSettingsMutationBlocked(path,false));
    }
    for(auto path:{"/auth/logout","/boiler/settings/write","/boiler/test/stop","/boiler/test/close_fault"})
        EXPECT_FALSE(boilerSettingsMutationBlocked(path,true));
}
}
