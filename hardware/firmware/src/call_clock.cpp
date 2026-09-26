#include "call_clock.h"

#include <stdio.h>
#include <string.h>

const char* event_type_name(EventType t) {
  switch (t) {
    case EventType::CALL_ON: return "call_on";
    case EventType::ENTRY: return "entry";
    case EventType::CANCEL: return "cancel";
    case EventType::TIMEOUT: return "timeout";
  }
  return "unknown";
}

int32_t ms_to_ds(uint32_t delta_ms) { return (int32_t)((delta_ms + 50u) / 100u); }

CallClock::CallClock(uint16_t boot_nonce, uint32_t max_call_ms)
    : nonce_(boot_nonce), max_call_ms_(max_call_ms) {}

uint32_t CallClock::elapsed_ms(uint32_t now_ms) const {
  if (state_ == CallState::IDLE) return 0;
  return now_ms - call_start_ms_;  // unsigned arithmetic survives the 49-day millis() wrap
}

void CallClock::make_event(EventType t, uint32_t now_ms, CallEvent* e) const {
  memset(e, 0, sizeof(*e));
  e->type = t;
  strncpy(e->call_id, call_id_, sizeof(e->call_id) - 1);
  e->ms = now_ms;
  e->wait_ds = -1;
  e->no_entry = TRI_NULL;
}

size_t CallClock::update(uint32_t now_ms, LightState light, bool entry_edge, CallEvent* out,
                         size_t max_out) {
  size_t n = 0;
  const bool lit = light != LightState::OFF;

  // IDLE → CALLING on light ON.
  if (state_ == CallState::IDLE && lit) {
    counter_++;
    snprintf(call_id_, sizeof(call_id_), "%04x-%04u", (unsigned)nonce_, (unsigned)(counter_ % 10000u));
    call_start_ms_ = now_ms;
    wait_ds_ = -1;
    state_ = CallState::CALLING;
    if (n < max_out) make_event(EventType::CALL_ON, now_ms, &out[n++]);
  }

  // CALLING → ATTENDED on the first entry. Later entries are ignored.
  if (state_ == CallState::CALLING && entry_edge) {
    wait_ds_ = ms_to_ds(now_ms - call_start_ms_);
    state_ = CallState::ATTENDED;
    if (n < max_out) {
      make_event(EventType::ENTRY, now_ms, &out[n]);
      out[n++].wait_ds = wait_ds_;
    }
  }

  // CALLING|ATTENDED → IDLE on light OFF.
  if ((state_ == CallState::CALLING || state_ == CallState::ATTENDED) && !lit) {
    if (n < max_out) {
      make_event(EventType::CANCEL, now_ms, &out[n]);
      out[n].wait_ds = wait_ds_;
      out[n++].no_entry = (state_ == CallState::CALLING) ? 1 : 0;
    }
    state_ = CallState::IDLE;
  }

  // Safety: a call running longer than MAX_CALL_S emits `timeout` and stops timing.
  if ((state_ == CallState::CALLING || state_ == CallState::ATTENDED) &&
      now_ms - call_start_ms_ >= max_call_ms_) {
    if (n < max_out) {
      make_event(EventType::TIMEOUT, now_ms, &out[n]);
      out[n].wait_ds = wait_ds_;
      out[n++].no_entry = (state_ == CallState::CALLING) ? 1 : 0;
    }
    state_ = CallState::TIMED_OUT;
  }

  // TIMED_OUT re-arms silently once the light finally goes off.
  if (state_ == CallState::TIMED_OUT && !lit) state_ = CallState::IDLE;

  return n;
}
