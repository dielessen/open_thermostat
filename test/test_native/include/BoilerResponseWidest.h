#pragma once
#include "control/BoilerResponse.h"
#include "control/LearnedState.h"
#include <cstdint>
#include <string>
// rc.5 (P1): BoilerResponse at its widest, for the payload bounds (the flow topic, the insight
// topic, the page): 65535 held targets today, eight rests of 1800 s, no ceiling for the outdoor
// now (null is wider than a number), 999.9 kW absorbed now, 19.999 kW per K and "not_driving".
// Built from a frame (BoilerResponse::stored()'s layout) and 1000 s of a steady 60 kW burn at 90
// degC with 3 K across, then 90 K across (the reported kW are capped at 999.9).
inline std::string widestBoilerFrame() {
    using heating::control::BoilerResponse;
    std::string f(BoilerResponse::frameBytes, '\0');
    f[0] = char(BoilerResponse::frameVersion); f[1] = BoilerResponse::frameKind; f[2] = char(BoilerResponse::payloadBytes);
    f[4 + 0] = char(195);                                       // product id
    f[4 + 1] = char(255);                                       // over-asked requests
    for (int b = 0; b < 6; ++b) { f[4 + 2 + b] = char(241); f[4 + 8 + b] = char(180); } // 80 degC, 6 h
    f[4 + 14] = char(8);                                        // eight rests
    for (int i = 0; i < 8; ++i) f[4 + 15 + i] = char(180);      // of 1800 s
    f[4 + 23] = char(5000 & 0xFF); f[4 + 24] = char(5000 >> 8);  // 5 kg/s
    f[4 + 25] = char(19999 & 0xFF); f[4 + 26] = char(19999 >> 8); // 19.999 kW per K
    f[4 + 30] = char(0x80);                                     // no local day yet
    f[4 + 31] = char(0xFF); f[4 + 32] = char(0xFF);             // 65535 held targets
    const uint32_t c = heating::control::LearnedState::crc(f.data(), f.size() - 4);
    for (int i = 0; i < 4; ++i) f[f.size() - 4 + i] = char(c >> (8 * i));
    return f;
}
inline heating::control::BoilerResponse widestBoilerResponse() {
    heating::control::BoilerResponse r;
    r.restore(widestBoilerFrame());
    heating::control::BoilerResponse::Sample s;
    s.ownRequest = false; s.burnerOn = true; s.hotWater = false; s.modulationPct = 100; s.nominalKw = 60;
    s.flowCentiC = 9000; s.returnCentiC = 8700;
    for (int k = 0; k < 100; ++k) { s.now += 10000; r.sample(s); }
    s.returnCentiC = 0; s.now += 10000; r.sample(s);
    return r;
}
