#pragma once
#include <ostream>
#include <string_view>

namespace heating::control {
// Stream a JSON string without allocating a second copy or changing stream
// formatting. Input is UTF-8; ASCII controls, quotes and backslashes are escaped.
inline std::ostream& writeJsonString(std::ostream& out, std::string_view value) {
    constexpr char digits[] = "0123456789abcdef";
    out.put('"');
    for (unsigned char byte : value) {
        if (byte == '"' || byte == '\\') {
            out.put('\\'); out.put(static_cast<char>(byte));
        } else if (byte < 0x20) {
            const char escaped[] = {'\\', 'u', '0', '0', digits[byte >> 4], digits[byte & 15]};
            out.write(escaped, sizeof(escaped));
        } else out.put(static_cast<char>(byte));
    }
    return out.put('"');
}
}
