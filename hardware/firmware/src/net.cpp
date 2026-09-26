#include "net.h"

#include <Arduino.h>

#include "config.h"

#if WIFI_ENABLED
#include <HTTPClient.h>
#include <WiFi.h>

namespace net {
namespace {
const size_t kQueue = 16;
String queue[kQueue];
size_t q_head = 0, q_len = 0;
uint32_t next_try_ms = 0;
uint32_t backoff_ms = 1000;
}  // namespace

void begin() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTzTime(TZ_STRING, NTP_SERVER);  // the clock sets itself once Wi-Fi is up
  Serial.println("DBG wifi: connecting to " WIFI_SSID);
}

void enqueue(const char* line) {
  if (q_len == kQueue) {  // drop the oldest; it is still in /log.jsonl and the bridge can backfill
    q_head = (q_head + 1) % kQueue;
    q_len--;
  }
  queue[(q_head + q_len) % kQueue] = line;
  q_len++;
}

void poll(uint32_t now_ms) {
  if (q_len == 0 || WiFi.status() != WL_CONNECTED || (int32_t)(now_ms - next_try_ms) < 0) return;
  HTTPClient http;
  http.setTimeout(2000);
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(queue[q_head]);
  http.end();
  if (code >= 200 && code < 300) {
    queue[q_head] = String();
    q_head = (q_head + 1) % kQueue;
    q_len--;
    backoff_ms = 1000;
    next_try_ms = now_ms;
  } else {
    Serial.printf("DBG wifi: POST failed (%d), retry in %lu ms\n", code, (unsigned long)backoff_ms);
    next_try_ms = now_ms + backoff_ms;
    backoff_ms = backoff_ms < 30000 ? backoff_ms * 2 : 30000;
  }
}
}  // namespace net
#else
namespace net {
void begin() {}
void enqueue(const char*) {}
void poll(uint32_t) {}
}  // namespace net
#endif
