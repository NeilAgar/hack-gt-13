#include "light_sensor.h"

#include "config.h"

LightConfig light_config_from_defines() {
  LightConfig c;
  c.ema_alpha = LIGHT_EMA_ALPHA;
  c.baseline_alpha = LIGHT_BASELINE_ALPHA;
  c.delta = LIGHT_DELTA;
  c.fixed_threshold = LDR_THRESHOLD;
  c.hysteresis = LDR_HYSTERESIS;
  c.on_hold_ms = LIGHT_ON_HOLD_MS;
  c.off_hold_ms = LIGHT_OFF_HOLD_MS;
  c.flash_window_ms = FLASH_WINDOW_MS;
  c.flash_min_transitions = FLASH_MIN_TRANSITIONS;
  return c;
}

float LightClassifier::threshold() const {
  return cfg_.fixed_threshold > 0 ? (float)cfg_.fixed_threshold : baseline_ + (float)cfg_.delta;
}

bool LightClassifier::flashing(uint32_t now_ms) const {
  size_t recent = 0;
  for (size_t i = 0; i < n_trans_; i++) {
    if (now_ms - transitions_[i] <= cfg_.flash_window_ms) recent++;
  }
  return recent >= cfg_.flash_min_transitions;
}

LightState LightClassifier::feed(uint32_t now_ms, int raw) {
  if (!primed_) {
    // Assume the light is off at boot: the first reading seeds both the EMA and the dark baseline.
    ema_ = baseline_ = (float)raw;
    primed_ = true;
    candidate_since_ = now_ms;
  }
  ema_ += cfg_.ema_alpha * ((float)raw - ema_);

  const float thr = threshold();
  const float half_h = cfg_.hysteresis / 2.0f;
  bool lit = lit_ ? (ema_ > thr - half_h) : (ema_ > thr + half_h);
  if (lit != lit_) {
    lit_ = lit;
    transitions_[trans_head_] = now_ms;
    trans_head_ = (trans_head_ + 1) % kMaxTransitions;
    if (n_trans_ < kMaxTransitions) n_trans_++;
  }
  // The adaptive baseline follows slow ambient drift, but only while the light is dark.
  if (!lit_ && out_ == LightState::OFF) baseline_ += cfg_.baseline_alpha * (ema_ - baseline_);

  const bool flash = flashing(now_ms);
  const bool active = lit_ || flash;  // a flashing light counts as ON, including its dark gaps
  if (active != candidate_active_) {
    candidate_active_ = active;
    candidate_since_ = now_ms;
  }
  const uint32_t held = now_ms - candidate_since_;
  if (candidate_active_ && held >= cfg_.on_hold_ms) {
    out_ = flash ? LightState::FLASH : LightState::ON;
  } else if (!candidate_active_ && held >= cfg_.off_hold_ms) {
    out_ = LightState::OFF;
  } else if (out_ != LightState::OFF && candidate_active_) {
    out_ = flash ? LightState::FLASH : LightState::ON;
  }
  return out_;
}

#if !defined(CALLCLOCK_NATIVE)
#include <Arduino.h>

void LightSensor::begin(int pin) {
  pin_ = pin;
#if defined(ESP_PLATFORM)
  analogReadResolution(12);
  analogSetPinAttenuation(pin_, ADC_11db);  // full 0–3.3 V range
#endif  // the Nano's ADC is fixed at 10 bits, 0–5 V
  pinMode(pin_, INPUT);
}

LightState LightSensor::poll(uint32_t now_ms) {
  if ((int32_t)(now_ms - next_sample_ms_) >= 0) {
    next_sample_ms_ = now_ms + 1000 / LIGHT_SAMPLE_HZ;
    raw_ = analogRead(pin_);
    cls_.feed(now_ms, raw_);
  }
  return cls_.state();
}
#endif
