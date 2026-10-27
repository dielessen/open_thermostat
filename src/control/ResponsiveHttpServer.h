#pragma once
#include <cstdint>

namespace heating::control {
// The pinned single-client WebServer otherwise gives an empty preconnection
// five seconds, blocking every queued request, including trial supervision.
// Only bound waiting for the FIRST byte. Parsing bodies and uploads remains
// entirely with the SDK; no accepted request or transaction is interrupted.
template<class Server>
class ResponsiveHttpServer : public Server {
public:
    using Server::Server;
    static constexpr uint32_t initialDataWaitMs = 250;

    void handleClient() {
        if (this->_currentStatus == HC_WAIT_READ
            && static_cast<uint32_t>(millis() - this->_statusChange) >= initialDataWaitMs
            && this->_currentClient.connected()
            && this->_currentClient.available() == 0) {
            this->_currentClient.stop();
        }
        // Let the SDK retire the stopped client and clear its request state.
        Server::handleClient();
    }
};
}
