// OLED (SSD1306) + RGB/NeoPixel status light + optional buzzer.
// Wording rule: show "ARRIVED after", never anything that implies help or care was given.
#pragma once

#include <stdint.h>

#include "call_clock.h"

namespace display {

struct View {
  CallState state;
  uint32_t elapsed_ms;        // of the current call
  int32_t last_wait_ds;       // wait of the current/last call, -1 = nobody arrived
  bool have_result;           // a call finished recently
  bool result_no_entry;       // …and it was cancelled with no one entering
  uint32_t result_age_ms;
  uint32_t warmup_s;          // PIR warm-up left
  uint32_t calls_today;
  int32_t median_wait_ds;     // -1 = no arrivals yet
  bool clock_set;
  LightState light;
};

void begin();
// Cheap to call every loop: redraws the OLED at 5 Hz, updates the LED and buzzer every call.
void update(const View& v, uint32_t now_ms);

}  // namespace display
