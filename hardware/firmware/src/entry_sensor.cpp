#include "entry_sensor.h"

#include <Arduino.h>

#include "config.h"

#if ENTRY_SENSOR == ENTRY_LD2410_UART
// Minimal HLK-LD2410 parser for its default "basic" reporting frames:
//   F4 F3 F2 F1 | len(2, LE) | 0x02 0xAA | target_state | … | 0x55 0x00 | F8 F7 F6 F5
// target_state: 0 = nobody, 1 = moving, 2 = stationary, 3 = both. We only need "anyone there?".
// (Vendored instead of pulling ncmreynolds/ld2410 to keep dependencies minimal.)
static HardwareSerial& radar = Serial2;
static uint8_t frame[64];
static size_t frame_len = 0;
static bool radar_present = false;

static void radar_poll() {
  static const uint8_t HEAD[4] = {0xF4, 0xF3, 0xF2, 0xF1};
  while (radar.available()) {
    uint8_t b = (uint8_t)radar.read();
    if (frame_len < 4) {
      frame_len = (b == HEAD[frame_len]) ? frame_len + 1 : (b == HEAD[0] ? 1 : 0);
      if (frame_len) frame[frame_len - 1] = b;
      continue;
    }
    if (frame_len < sizeof(frame)) frame[frame_len++] = b;
    if (frame_len >= 6) {
      size_t len = frame[4] | (frame[5] << 8);
      size_t total = 4 + 2 + len + 4;
      if (len > sizeof(frame) - 10) {  // garbage length: resync
        frame_len = 0;
        continue;
      }
      if (frame_len == total) {
        const uint8_t* d = frame + 6;
        if ((d[0] == 0x02 || d[0] == 0x01) && d[1] == 0xAA) radar_present = d[2] != 0;
        frame_len = 0;
      }
    }
  }
}
#endif

void EntrySensor::begin(uint32_t now_ms) {
  boot_ms_ = now_ms;
#if ENTRY_SENSOR == ENTRY_PIR || ENTRY_SENSOR == ENTRY_LD2410_OUT
  pinMode(PIN_ENTRY, INPUT_PULLDOWN);  // HC-SR501 / LD2410 OUT drive actively; pull-down keeps a
                                       // disconnected pin from floating into phantom entries
#elif ENTRY_SENSOR == ENTRY_REED
#if REED_INTERNAL_PULLUP
  pinMode(PIN_REED, INPUT_PULLUP);
#else
  pinMode(PIN_REED, INPUT);  // GPIO35 has no internal pull-up: external 10k to 3V3 required
#endif
#elif ENTRY_SENSOR == ENTRY_LD2410_UART
  radar.begin(LD2410_BAUD, SERIAL_8N1, PIN_LD2410_RX, PIN_LD2410_TX);
#endif
}

bool EntrySensor::read_level() {
#if ENTRY_SENSOR == ENTRY_PIR || ENTRY_SENSOR == ENTRY_LD2410_OUT
  return digitalRead(PIN_ENTRY) == HIGH;
#elif ENTRY_SENSOR == ENTRY_REED
  return digitalRead(PIN_REED) == HIGH;  // switch to GND closed by the magnet; HIGH = door opened
#elif ENTRY_SENSOR == ENTRY_LD2410_UART
  radar_poll();
  return radar_present;
#else
  return false;
#endif
}

uint32_t EntrySensor::warmup_remaining_s(uint32_t now_ms) const {
#if ENTRY_SENSOR == ENTRY_PIR
  uint32_t since = now_ms - boot_ms_;
  return since >= PIR_WARMUP_MS ? 0 : (PIR_WARMUP_MS - since + 999) / 1000;
#else
  (void)now_ms;
  return 0;
#endif
}

bool EntrySensor::poll(uint32_t now_ms) {
  bool level = read_level();
  bool rising = level && !level_;
  level_ = level;
  if (!primed_) {  // never treat the level at boot as an entry
    primed_ = true;
    return false;
  }
  if (!rising || warmup_remaining_s(now_ms) > 0) return false;
  if (has_edge_ && now_ms - last_edge_ms_ < ENTRY_REFRACTORY_MS) return false;
  has_edge_ = true;
  last_edge_ms_ = now_ms;
  return true;
}

const char* EntrySensor::name() const {
#if ENTRY_SENSOR == ENTRY_PIR
  return "PIR";
#elif ENTRY_SENSOR == ENTRY_LD2410_OUT
  return "LD2410 OUT";
#elif ENTRY_SENSOR == ENTRY_LD2410_UART
  return "LD2410 UART";
#elif ENTRY_SENSOR == ENTRY_REED
  return "REED";
#else
  return "NONE";
#endif
}
