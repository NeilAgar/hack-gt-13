#include "mock_station.h"

#include <Arduino.h>

#include "config.h"

namespace mock_station {
namespace {
// Module-private on purpose: nothing outside this file can see whether a call is "on".
bool call_latched = false;

struct Button {
  int pin;
  bool stable_pressed = false;
  bool last_raw = false;
  uint32_t changed_ms = 0;
  // True once per debounced press.
  bool pressed(uint32_t now_ms) {
    bool raw = digitalRead(pin) == LOW;  // INPUT_PULLUP: pressed = LOW
    if (raw != last_raw) {
      last_raw = raw;
      changed_ms = now_ms;
    }
    if (now_ms - changed_ms >= 30 && raw != stable_pressed) {
      stable_pressed = raw;
      return raw;
    }
    return false;
  }
};

Button call_btn{PIN_MOCK_CALL_BTN};
Button cancel_btn{PIN_MOCK_CANCEL_BTN};

void drive() {
  digitalWrite(PIN_MOCK_CALL_LED, call_latched ? HIGH : LOW);
  digitalWrite(PIN_DOME_LIGHT, call_latched ? HIGH : LOW);
}
}  // namespace

void begin() {
  pinMode(PIN_MOCK_CALL_BTN, INPUT_PULLUP);
  pinMode(PIN_MOCK_CANCEL_BTN, INPUT_PULLUP);
  pinMode(PIN_MOCK_CALL_LED, OUTPUT);
  pinMode(PIN_DOME_LIGHT, OUTPUT);
  drive();
}

void poll(uint32_t now_ms) {
  if (call_btn.pressed(now_ms)) call_latched = true;
  if (cancel_btn.pressed(now_ms)) call_latched = false;
  drive();
}
}  // namespace mock_station
