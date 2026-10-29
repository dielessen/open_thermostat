// EMS receive path fuzzer: UART bytes -> BreakFrameReader -> processTelegram
// prefilters -> EmsFrameQueue -> decodeTelegram (EmsTelegram::fromRawData and
// every host-buildable observer/processor the E32 runs on a received frame).
//
// Input: records [ctl][n bytes]. ctl bits 0..5 = n (bytes the UART driver
// buffers), bit 6 = recompute the CRC (byte n-2, before the BREAK 0x00) so the
// decoders are reached, bit 7 = an explicit DATA count byte follows ctl (models
// the reset/flush races BreakFrameReader handles). The FIFO is continuous:
// bytes not consumed by one BREAK remain for the next one, like the driver.
#include "fuzz_common.h"
#include "EMS/BreakFrameReader.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/DeviceVersion.h"
#include "EMS/EmsDeviceInventory.h"
#include "EMS/EmsEntityCatalog.h"
#include "EMS/EmsFrameQueue.h"
#include "EMS/EmsPoll.h"
#include "EMS/EmsTelegram.h"
#include "EMS/ForeignBoilerRequest.h"
#include "EMS/ManualBusIdentity.h"
#include "EMS/OutdoorTemperatureSample.h"
#include "EMS/RoomHeatObservation.h"
#include "EMS/UBADeviceVersion.h"
#include "EMS/UBAFactory.h"
#include "EMS/UBAInternalWeatherCompensatedMode.h"
#include "EMS/UBAMonitorFastPlus.h"
#include "EMS/UBAMonitorSlowPlus.h"
#include "EMS/UBAMonitorSlowPlus2.h"
#include "EMS/UBAMonitorWWPlus.h"
#include "EMS/UBAOutdoorTemp.h"
#include "EMS/UBAParameters.h"
#include "EMS/UBAParametersPlus.h"
#include "EMS/UBAParametersWWPlus.h"
#include "EMS/UBAProtocolVersion.h"
#include "EmsMetrics.h"
#include <deque>
#include <map>
#include <sstream>
#include <stdexcept>

namespace heating { std::shared_ptr<ib::logger::LoggerInterface> logger; }

namespace {
using namespace heating::ems;
constexpr uint8_t deviceId = 0x0B, boilerId = 0x08;

struct Fifo {
    std::deque<uint8_t> bytes;
    size_t read(uint8_t* dst, size_t n) {
        size_t got = 0;
        for (; got < n && !bytes.empty(); ++got) { dst[got] = bytes.front(); bytes.pop_front(); }
        return got;
    }
};

// EmsTelegram keeps getDataOffset protected; probe it through a subclass.
struct Probe : EmsTelegram { using EmsTelegram::EmsTelegram; using EmsTelegram::getDataOffset; };

template<class T> void logAs(const EmsTelegram& t, otfuzz::FormattingLogger& log) {
    // Same (layout-compatible) cast the production processors use.
    reinterpret_cast<const T*>(&t)->logData(log, 1);
}

struct Pipeline {
    otfuzz::FormattingLogger log;
    EmsFrameQueue<8> queue;
    EmsDeviceInventory inventory;
    ClassicBoilerMonitor monitor;
    EmsEntityObserver entities;
    ForeignBoilerRequest foreign;
    heating::control::TemperatureSample outdoor;
    RoomHeatObservation room{"0123456789abcdef"};
    std::map<uint16_t, std::function<void(const EmsTelegram&)>> processors;
    uint64_t now = 1000;
    std::unique_ptr<heating::ems::EmsMetrics> metrics;
    Pipeline() {
        metrics = std::make_unique<heating::ems::EmsMetrics>(
            [this](uint16_t type, std::function<void(const EmsTelegram&)> fn) { processors[type] = std::move(fn); },
            [this] { return now; }, "0123456789abcdef0123456789abcdef");
    }

    // EmsController::decodeTelegram without the ESP-only parts.
    void decode(uint8_t* data, uint8_t length) {
        if (length == 0) return;
        try {
            const auto telegram = EmsTelegram::fromRawData(data, length - 1);
            for (unsigned o = 0; o < 64; ++o) (void)reinterpret_cast<const Probe*>(&telegram)->getDataOffset(o, o & 7);
            inventory.observe(telegram, now);
            monitor.receive(telegram, now);
            entities.observe(telegram, now);
            foreign.observe(telegram, now);
            receiveOutdoorTemperature(outdoor, telegram, now);
            room.receive(now, telegram);
            (void)readDeviceVersion(telegram);
            telegram.logDebug(log, 1);
            (void)telegram.getRequestedDataSize();
            for (unsigned o = 0; o < 64; ++o) {
                (void)telegram.byteAt(o); (void)telegram.wordAt(o); (void)telegram.counterAt(o);
            }
            roundTrip(telegram);
            if (telegram.getOperationType() != EmsTelegram::READ && telegram.getSenderId() == boilerId) {
                const auto found = processors.find(telegram.getTypeId());
                if (found != processors.end()) found->second(telegram);
                switch (telegram.getTypeId()) {
                    case UBADeviceVersion::predefinedTypeId: logAs<UBADeviceVersion>(telegram, log); break;
                    case UBAFactory::predefinedTypeId: logAs<UBAFactory>(telegram, log); break;
                    case UBAInternalWeatherCompensatedMode::predefinedTypeId: logAs<UBAInternalWeatherCompensatedMode>(telegram, log); break;
                    case UBAMonitorFastPlus::predefinedTypeId: logAs<UBAMonitorFastPlus>(telegram, log); break;
                    case UBAMonitorSlowPlus::predefinedTypeId: logAs<UBAMonitorSlowPlus>(telegram, log); break;
                    case UBAMonitorSlowPlus2::predefinedTypeId: logAs<UBAMonitorSlowPlus2>(telegram, log); break;
                    case UBAMonitorWWPlus::predefinedTypeId: logAs<UBAMonitorWWPlus>(telegram, log); break;
                    case UBAOutdoorTemp::predefinedTypeId: logAs<UBAOutdoorTemp>(telegram, log); break;
                    case UBAParameters::predefinedTypeId: logAs<UBAParameters>(telegram, log); break;
                    case UBAParametersPlus::predefinedTypeId: logAs<UBAParametersPlus>(telegram, log); break;
                    case UBAParametersWWPlus::predefinedTypeId: logAs<UBAParametersWWPlus>(telegram, log); break;
                    case UBAProtocolVersion::predefinedTypeId: logAs<UBAProtocolVersion>(telegram, log); break;
                    default: break;
                }
            }
        } catch (const std::exception&) {
            // decodeTelegram catches std::exception: a rejected frame, not a crash.
        }
    }
    // A telegram the receive codec accepted must, when the encoder accepts it,
    // produce a frame that decodes to the same telegram (TX/RX symmetry).
    static void roundTrip(const EmsTelegram& t) {
        const auto raw = t.encodeToRawDataWithCRC();
        if (raw.empty()) return;
        const auto back = EmsTelegram::fromRawData(raw.data(), raw.size());
        if (back.getTypeId() != t.getTypeId() || back.getOffset() != t.getOffset()
            || back.getOperationType() != t.getOperationType() || back.dataSize() != t.dataSize()
            || back.getSenderId() != t.getSenderId() || back.getDestinationId() != t.getDestinationId())
            otfuzz::invariant("EMS encode/decode round trip changed the telegram");
    }

    // EmsController::processTelegram (E32 branch) prefilters, then the queue.
    void process(uint8_t* data, size_t size) {
        if (size == 0 || size > EmsRawFrame::capacity) otfuzz::invariant("BreakFrameReader delivered an impossible size");
        const auto length = static_cast<uint8_t>(size);
        (void)ManualBusIdentity::conflictingSource(data, length - 1, deviceId);
        if (length == 2 && EmsPoll::addressed(data[0], deviceId, data[1])) return;
        if (length < 7) return;
        if (!queue.push(data, length, now)) return;
        EmsRawFrame frame; uint64_t at = 0;
        while (queue.pop(frame, &at)) decode(frame.data.data(), frame.length);
    }
    void report() {
        std::ostringstream out;
        inventory.writeJSON(out, now);
        entities.writeJSON(out, now);
        monitor.writeJSON(out, now);
        monitor.writeReceptionJSON(out, now);
        monitor.writeLegacyStatus(out, now);
        for (size_t g = 0; g < 8; ++g) monitor.writeFieldGroup(out, now, g);
        for (size_t f = 0; f < entityFieldCount + 2; ++f) (void)entities.field(f, now);
        room.write(out, now);
        metrics->getMetrics(out);
        metrics->getRoomObservation(out);
    }
};
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    otfuzz::Reader in(data, size);
    Pipeline p;
    Fifo fifo;
    std::array<uint8_t, 33> buffer{}; // EmsBusUart::EmsMaxTelegramSize
    unsigned records = 0;
    while (!in.empty() && records++ < 64) {
        const uint8_t ctl = in.u8();
        const size_t n = ctl & 0x3F;
        const size_t counted = (ctl & 0x80) ? in.u8() : n;
        const auto bytes = in.bytes(n);
        std::string frame(bytes);
        if ((ctl & 0x40) && frame.size() >= 3)
            frame[frame.size() - 2] = static_cast<char>(EmsTelegram::calculateCRC(
                reinterpret_cast<const uint8_t*>(frame.data()), static_cast<uint8_t>(frame.size() - 2)));
        for (char c : frame) fifo.bytes.push_back(static_cast<uint8_t>(c));
        size_t got = 0;
        const auto result = BreakFrameReader::read(fifo, buffer.data(), buffer.size(), counted, got);
        if (got > buffer.size()) otfuzz::invariant("BreakFrameReader size beyond capacity");
        if (BreakFrameReader::deliverable(result)) {
            if (got != counted) otfuzz::invariant("deliverable frame size differs from DATA count");
            p.process(buffer.data(), got);
        }
        p.now += 997;
        if ((records & 7) == 0) p.report();
    }
    p.report();
    return 0;
}
