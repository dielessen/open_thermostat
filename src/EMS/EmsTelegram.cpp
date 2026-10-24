#include "EmsTelegram.h"
#include <stdexcept>

namespace heating::ems {

uint16_t EmsTelegram::getTypeId() const {
	return typeId_;
}

uint8_t EmsTelegram::getSenderId() const {
	return source_ & 0x7F; // strip MSB
}

uint8_t EmsTelegram::getOffset() const {
	return offset_;
}

EmsTelegram::operation_t EmsTelegram::getOperationType() const {
	return operation_;
}

uint8_t EmsTelegram::getRequestedDataSize() const {
	if (data_.empty()) {
		return 0;
	}
	return data_[0];
}

void EmsTelegram::logDebug(ib::logger::LoggerInterface &log, ib::logger::LoggerInterface::LogFeatureType feature) const {
	if (log.isFeatureEnabled(feature)) {
		char opType = 'B';
		if (operation_ == operation_t::READ) {
			opType = 'R';
		} else if (operation_ == operation_t::READ_WITH_DATA) {
			opType = 'D';
		} else if (operation_ == operation_t::WRITE) {
			opType = 'W';
		}

		char dataStr[data_.size() * 2 + 1] = {0};
		for (size_t i = 0; i < data_.size(); ++i) {
			snprintf(dataStr + i * 2, sizeof(dataStr) - i * 2, "%2.2X", data_[i]);
		}

		DBGLOGFD((&log), feature, "(0x%X) -%c-> (0x%X), type: 0x%4.4X, offset: %d, dataLen: %d data: %s\n", source_, opType, destination_, typeId_, offset_, data_.size(), dataStr);
	}
}

uint16_t EmsTelegram::getTelegramTypeFromRaw(uint8_t *data, uint8_t length) {
    if (!data || length < 5) throw std::runtime_error("Short EMS header");
    if (data[2] != 0xFF) return data[2];
    const bool read = (data[1] & 0x80) != 0;
    if (length < (read ? 8 : 7)) throw std::runtime_error("Short EMS+ header");
    const size_t start = read ? 5 : 4;
    const uint32_t type = (data[start] << 8) + data[start + 1] + 256;
    if (type > 0xFFFF) throw std::runtime_error("Invalid EMS+ type");
    return static_cast<uint16_t>(type);
}

EmsTelegram EmsTelegram::fromRawData(const uint8_t *data, size_t length) {
    if (!data || length < 5 || length > 32) throw std::runtime_error("Invalid EMS frame length");
    const bool extended = data[2] == 0xFF;
    const bool read = data[1] != 0 && (data[1] & 0x80);
    if ((extended && length < (read ? 8u : 7u)) || (!extended && read && length != 6))
        throw std::runtime_error("Invalid EMS header length");
    if (data[length - 1] != calculateCRC(data, static_cast<uint8_t>(length - 1)))
        throw std::runtime_error("Bad CRC");
    const auto operation = data[1] == 0 ? BROADCAST : read ? READ : WRITE;
    const uint32_t type = !extended ? data[2] :
        (data[read ? 5 : 4] << 8) + data[read ? 6 : 5] + 256;
    if (type > 0xFFFF) throw std::runtime_error("Invalid EMS+ type");
    const size_t start = extended && !read ? 6 : 4;
    const size_t size = read ? 1 : length - start - 1;
    return EmsTelegram(operation, data[0], data[1], data[3], type,
                       std::vector<uint8_t>(data + start, data + start + size));
}

EmsTelegram EmsTelegram::getFromRawData(ib::logger::LoggerInterface &log,
    ib::logger::LoggerInterface::LogFeatureType verboseFeature, uint8_t *data, uint8_t length) {
    auto telegram = fromRawData(data, length);
    DBGLOGFD((&log), verboseFeature, "Got validated EMS raw len: %u from: %u\n", length, data[0]);
    return telegram;
}

std::vector<uint8_t> EmsTelegram::encodeToRawDataWithCRC() const {
	std::vector<uint8_t> rawData;
    static constexpr size_t maxRawTelegramLength = 32;
    const size_t headerLength = typeId_ > 0xFF ? 6 : 4;
    const bool read = operation_ == operation_t::READ;
    if ((read && data_.size() > 1)
        || (!read && data_.size() > maxRawTelegramLength - headerLength - 1)) return {};
    rawData.reserve(headerLength + (read ? 1 : data_.size()) + 1);

	rawData.push_back(source_ | 0x80); // 0
	rawData.push_back(destination_);   // 1
	if ((operation_ == operation_t::READ || operation_ == operation_t::READ_WITH_DATA) && destination_ != 0) {
		rawData[1] |= 0x80;
	}

	rawData.push_back(typeId_ > 0xFF ? 0xFF : typeId_); // 2 - typeId for EMS1 -  0xFF marker for EMS2
	rawData.push_back(offset_);							// 4

	if (typeId_ > 0xFF) {									 // EMS2
		if (operation_ == operation_t::READ) {				 // READ REQUEST
			rawData.push_back(data_.empty() ? 0 : data_[0]); // 4 message data - requested length
			rawData.push_back((typeId_ >> 8) - 1);			 // 5 // type, 1st byte, high-byte, subtract 0x100
			rawData.push_back(typeId_ & 0xFF);				 // 6// type, 2nd byte, low-byte
		} else {											 // write
			rawData.push_back((typeId_ >> 8) - 1);			 // 4
			rawData.push_back(typeId_ & 0xFF);				 // 5
			rawData.insert(rawData.end(), data_.begin(), data_.end());
		}
	} else {												 // EMS 1.0
		if (operation_ == operation_t::READ) {				 // READ REQUEST
			rawData.push_back(data_.empty() ? 0 : data_[0]); //  message data - requested length
		} else {
			rawData.insert(rawData.end(), data_.begin(), data_.end());
		}
	}

	rawData.push_back(calculateCRC(rawData.data(), rawData.size()));
	return rawData;
}

int8_t EmsTelegram::getDataOffset(uint8_t dataStart, uint8_t dataLen) const {
	if (offset_ > dataStart || dataStart - offset_ + dataLen > data_.size()) {
		return -1;
	}
	return dataStart - offset_;
}

uint8_t EmsTelegram::calculateCRC(const uint8_t *data, const uint8_t length) { // from EMS-ESP32
	uint8_t i = 0;
	uint8_t crc = 0;
	while (i < length) {
		crc = ems_crc_table[crc];
		crc ^= data[i++];
	}
	return crc;
}

} // namespace heating
