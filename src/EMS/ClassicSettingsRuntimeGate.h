#pragma once
namespace heating::ems {
struct ClassicSettingsRuntimeGate {
    struct Conditions {
        bool compiled=false,installationReviewed=false,emsEnabled=false,classic=false,transportReady=false;
        bool trialActive=false,configurationReadActive=false,updateAllowed=false;
    };
    static constexpr bool permitted(const Conditions& c){
        return c.compiled&&c.installationReviewed&&c.emsEnabled&&c.classic&&c.transportReady
            &&!c.trialActive&&!c.configurationReadActive&&c.updateAllowed;
    }
};
}
