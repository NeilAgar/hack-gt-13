// Doorway entry sensing. Produces a single "someone came in" edge with a 5 s refractory period.
// Presence only: no images, no audio, no identities. The sensor type is picked by ENTRY_SENSOR in config.h.
#pragma once

#include <stdint.h>

class EntrySensor {
 public:
  void begin(uint32_t now_ms);
  // Call every loop. True exactly once per new entry (rising edge, after refractory and warm-up).
  bool poll(uint32_t now_ms);
  // Seconds of PIR warm-up left (0 when ready or when the sensor needs no warm-up).
  uint32_t warmup_remaining_s(uint32_t now_ms) const;
  bool present() const { return level_; }
  const char* name() const;

 private:
  bool read_level();
  bool level_ = false;
  bool primed_ = false;
  uint32_t boot_ms_ = 0;
  uint32_t last_edge_ms_ = 0;
  bool has_edge_ = false;
};
