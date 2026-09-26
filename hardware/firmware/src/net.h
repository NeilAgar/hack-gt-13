// Optional Wi-Fi uplink + NTP. Default OFF (WIFI_ENABLED 0): the USB serial bridge is the primary path.
#pragma once

#include <stdint.h>

namespace net {
void begin();
void enqueue(const char* event_line);  // POSTs to API_URL when connected; small in-RAM retry queue
void poll(uint32_t now_ms);
}  // namespace net
