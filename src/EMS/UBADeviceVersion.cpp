#include "UBADeviceVersion.h"
#include "DeviceVersion.h"
#include "Logging.h"

namespace heating::ems {

void UBADeviceVersion::logData(ib::logger::LoggerInterface &log, ib::logger::LoggerInterface::LogFeatureType feature) const {
	DBGLOGFD((&log), feature, "Version, offset: %u, size: %zu\n", unsigned(offset_), data_.size());
	// [EmsControl] (0x88) -W-> (0x19), type: 0x0002, offset: 0, dataLen: 12 data: EA 05 06 00 00 00 00 00 00 01 02 68

    const auto version=readDeviceVersion(*this);
    if(!version)return;
    if(version->brand) {
        DBGLOGFD((&log),feature,"Version vendorId: %u\n",unsigned(*version->brand));
    }
    DBGLOGFD((&log),feature,"Version productId: %u\n",unsigned(version->product));
    DBGLOGFD((&log),feature,"Version major: %u\n",unsigned(version->major));
    DBGLOGFD((&log),feature,"Version minor: %u\n",unsigned(version->minor));

}

}