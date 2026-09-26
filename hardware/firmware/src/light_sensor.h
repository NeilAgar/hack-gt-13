// Optical call-light sensing: an LDR taped over the call station's reassurance LED.
//
// LightClassifier is pure (native-testable): feed it raw ADC samples, it returns the debounced
// OFF / ON / FLASH state. LightSensor is the thin Arduino wrapper that samples the ADC at 100 Hz.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "call_clock.h"

struct LightConfig {
  float ema_alpha;
  float baseline_alpha;
  int delta;             // adaptive mode: threshold = baseline + delta
  int fixed_threshold;   // > 0 → use this instead of the adaptive threshold
  int hysteresis;        // raw counts
  uint32_t on_hold_ms;
  uint32_t off_hold_ms;
  uint32_t flash_window_ms;
  uint8_t flash_min_transitions;
};

class LightClassifier {
 public:
  explicit LightClassifier(const LightConfig& cfg) : cfg_(cfg) {}

  // One sample. Returns the debounced state.
  LightState feed(uint32_t now_ms, int raw);

  LightState state() const { return out_; }
  float smoothed() const { return ema_; }
  float baseline() const { return baseline_; }
  float threshold() const;
  bool lit() const { return lit_; }
  bool flashing(uint32_t now_ms) const;

 private:
  static const size_t kMaxTransitions = 8;  // FLASH needs 3 in the window; small for the Nano
  LightConfig cfg_;
  bool primed_ = false;
  float ema_ = 0;
  float baseline_ = 0;
  bool lit_ = false;                 // instantaneous (hysteresis only)
  uint32_t transitions_[kMaxTransitions] = {0};
  size_t n_trans_ = 0;
  size_t trans_head_ = 0;
  bool candidate_active_ = false;
  uint32_t candidate_since_ = 0;
  LightState out_ = LightState::OFF;
};

LightConfig light_config_from_defines();

#if !defined(CALLCLOCK_NATIVE)
class LightSensor {
 public:
  void begin(int pin);
  // Call every loop; samples at LIGHT_SAMPLE_HZ and returns the debounced state.
  LightState poll(uint32_t now_ms);
  int last_raw() const { return raw_; }
  const LightClassifier& classifier() const { return cls_; }

 private:
  int pin_ = -1;
  int raw_ = 0;
  uint32_t next_sample_ms_ = 0;
  LightClassifier cls_{light_config_from_defines()};
};
#endif
