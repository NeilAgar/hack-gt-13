// Pure call-timing state machine. No Arduino headers, so it runs under `pio test -e native`.
//
// It sees only two things: the debounced state of the call light (read optically) and
// doorway entry edges. It measures "time until someone arrived", never "time to help".
#pragma once

#include <stddef.h>
#include <stdint.h>

enum class LightState : uint8_t { OFF = 0, ON = 1, FLASH = 2 };  // FLASH counts as ON

enum class CallState : uint8_t {
  IDLE = 0,      // light off, nothing to time
  CALLING = 1,   // light on, nobody has come in yet
  ATTENDED = 2,  // light still on, someone came in
  TIMED_OUT = 3  // exceeded MAX_CALL_S; waiting for the light to go off before re-arming
};

enum class EventType : uint8_t { CALL_ON = 0, ENTRY = 1, CANCEL = 2, TIMEOUT = 3 };

const char* event_type_name(EventType t);

// Tri-state bool for JSON: -1 = null.
static const int8_t TRI_NULL = -1;

struct CallEvent {
  EventType type;
  char call_id[12];   // "<boot nonce hex4>-<counter 4 digits>", e.g. "a1b2-0007"
  uint32_t ms;        // ms since boot at which the event happened
  int32_t wait_ds;    // time until someone arrived, in DECISECONDS (exact 1-decimal seconds); -1 = null
  int8_t no_entry;    // cancel/timeout only: 1 = nobody entered, 0 = someone did; TRI_NULL otherwise
};

class CallClock {
 public:
  CallClock(uint16_t boot_nonce, uint32_t max_call_ms);

  // Feed one tick. Returns how many events were written to `out` (at most `max_out`, ≤ 3 per tick).
  // Order inside one tick: light ON → call_on, then entry, then light OFF → cancel, then timeout.
  size_t update(uint32_t now_ms, LightState light, bool entry_edge, CallEvent* out, size_t max_out);

  CallState state() const { return state_; }
  // ms the current call has been running (0 when IDLE).
  uint32_t elapsed_ms(uint32_t now_ms) const;
  // Deciseconds until arrival of the current/last call, or -1 if nobody arrived.
  int32_t last_wait_ds() const { return wait_ds_; }
  uint32_t calls_started() const { return counter_; }

 private:
  void make_event(EventType t, uint32_t now_ms, CallEvent* e) const;

  uint16_t nonce_;
  uint32_t max_call_ms_;
  CallState state_ = CallState::IDLE;
  uint32_t counter_ = 0;
  uint32_t call_start_ms_ = 0;
  int32_t wait_ds_ = -1;
  char call_id_[12] = {0};
};

// Deciseconds between two ms timestamps, rounded half-up. Exact integer so C++ and Python agree.
int32_t ms_to_ds(uint32_t delta_ms);
