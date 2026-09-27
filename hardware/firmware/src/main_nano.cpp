// Call Clock firmware for the Arduino Nano (ATmega328, 16 MHz, 2 KB RAM, 1 KB EEPROM).
// Wiring of modules only; the logic is shared with the ESP32 build.
//
//   mock_station  → drives the fake call LED (demo only; never read by anything below)
//   light_sensor  → LDR on the call LED → OFF/ON/FLASH
//   entry_sensor  → doorway presence edge
//   call_clock    → pure state machine → call_on / entry / cancel / timeout
//   compact_log   → signs + streams each event to Serial ("EVT …") and keeps the last ~57 in EEPROM
//   display       → RGB LED / NeoPixel + buzzer (no OLED on the Nano)
//
// Differences from the ESP32 build (same event format, same verifier):
//   - no Wi-Fi/NTP: the USB bridge is the only uplink, so events made while it is not running are only
//     in EEPROM until the next `dump` (the bridge dumps on connect). More than ~57 offline → seq gap.
//   - no timezone rules: the bridge's time sync carries "tz_offset" (seconds east of UTC)
//   - no OLED, no flash filesystem
//
// Serial protocol (115200 baud) is the same as the ESP32's:
//   out:  EVT {json} | LOG {json} (reply to `dump`) | DBG …
//   in:   {"cmd":"time","epoch":1790000000,"tz_offset":-14400}
//         cal on | cal off | dump | status | clear YES | factory YES
#include <Arduino.h>
#include <EEPROM.h>
#include <string.h>

#include "call_clock.h"
#include "compact_log.h"
#include "config.h"
#include "crypto.h"
#include "display.h"
#include "entry_sensor.h"
#include "event_log.h"
#include "light_sensor.h"
#include "mock_station.h"
#include "timefmt.h"

class EepromStorage : public CcStorage {
 public:
  uint8_t read(uint16_t addr) override { return EEPROM.read(addr); }
  void write(uint16_t addr, uint8_t value) override { EEPROM.update(addr, value); }  // skips unchanged bytes
  uint16_t size() const override { return EEPROM.length(); }
};

class SerialSink : public CcSink {
 public:
  void write(const char* s, size_t n) override { Serial.write((const uint8_t*)s, n); }
};

static EepromStorage storage;
static SerialSink serial_sink;
static uint8_t key[32];
static CompactLog* event_log = nullptr;
static CallClock* call_clock = nullptr;
static LightSensor light;
static EntrySensor entry;
static bool calibrate = CALIBRATE;
static uint32_t next_cal_print_ms = 0;
static char cmd[72];  // the time command is ~60 chars
static uint8_t cmd_len = 0;

// Wall clock: set by the bridge. epoch now = sync_epoch + (millis() - sync_ms) / 1000.
static bool clock_set = false;
static uint32_t sync_epoch = 0, sync_ms = 0;
static int32_t tz_offset_s = DEFAULT_TZ_OFFSET_S;

static bool have_result = false, result_no_entry = false;
static uint32_t result_ms = 0;
static uint32_t calls_since_boot = 0;

// Stack headroom check: fill free RAM with a marker at boot; `status` reports how much was never touched.
// Anything under ~150 bytes after a few calls and a `dump` means the RAM budget is too tight.
extern uint8_t __heap_start;
extern void* __brkval;
static const uint8_t kPaint = 0xA5;

static const uint8_t* heap_top() { return __brkval ? (const uint8_t*)__brkval : &__heap_start; }

static void paint_free_ram() {
  uint8_t here;
  for (uint8_t* p = (uint8_t*)heap_top(); p < &here - 16; p++) *p = kPaint;
}

static uint16_t never_used_ram() {
  uint16_t n = 0;
  for (const uint8_t* p = heap_top(); *p == kPaint && p < (const uint8_t*)RAMEND; p++) n++;
  return n;
}

static uint32_t epoch_at(uint32_t ms) { return sync_epoch + (ms - sync_ms) / 1000UL; }

static void emit(const CallEvent& ev) {
  CompactEvent c;
  c.type = ev.type;
  c.no_entry = ev.no_entry;
  c.nonce = event_log->boot_nonce();
  c.counter = (uint16_t)(call_clock->calls_started() % 10000UL);  // the current call's number
  c.ms = ev.ms;
  c.wait_ds = ev.wait_ds;
  c.has_time = clock_set;
  c.epoch = clock_set ? epoch_at(ev.ms) : 0;
  c.tz_offset_s = tz_offset_s;
  Serial.print(F("EVT "));
  event_log->emit(c, serial_sink);
  Serial.print('\n');

  switch (ev.type) {
    case EventType::CALL_ON:
      calls_since_boot++;
      have_result = false;
      break;
    case EventType::ENTRY:
      break;
    case EventType::CANCEL:
    case EventType::TIMEOUT:
      have_result = true;
      result_no_entry = ev.no_entry == 1;
      result_ms = ev.ms;
      break;
  }
}

static void print_status() {
  Serial.print(F("DBG status device=" DEVICE_ID " ccn=" CCN " board=nano next_seq="));
  Serial.print(event_log->next_seq());
  Serial.print(F(" clock="));
  Serial.print(clock_set ? F("set") : F("unset"));
  Serial.print(F(" tz_offset="));
  Serial.print(tz_offset_s);
  Serial.print(F(" entry="));
  Serial.print(entry.name());
  Serial.print(F(" state="));
  Serial.print((int)call_clock->state());
  Serial.print(F(" stored="));
  Serial.print(event_log->count());
  Serial.print('/');
  Serial.print(event_log->capacity());
  Serial.print(F(" ram_never_used="));
  Serial.println(never_used_ram());
#if LIGHT_FROM_BUTTON
  Serial.println(F("DBG WARNING light source = BUTTON BYPASS (not the light sensor; not independent)"));
#endif
}

static void handle_command(const char* line) {
  if (line[0] == '\0') return;
  if (line[0] == '{') {
    uint32_t epoch;
    int32_t off = tz_offset_s;
    if (!cc_parse_time_cmd(line, &epoch, &off)) {
      Serial.println(F("DBG bad command json (expected {\"cmd\":\"time\",\"epoch\":N,\"tz_offset\":S})"));
      return;
    }
    sync_epoch = epoch;
    sync_ms = millis();
    tz_offset_s = off / 900 * 900;  // stored in 15-minute steps
    clock_set = true;
    char ts[26];
    cc_format_iso(sync_epoch, tz_offset_s, ts);
    Serial.print(F("DBG time set "));
    Serial.println(ts);
    return;
  }
  if (strcmp(line, "cal on") == 0) {
    calibrate = true;
  } else if (strcmp(line, "cal off") == 0) {
    calibrate = false;
  } else if (strcmp(line, "dump") == 0) {
    event_log->dump(serial_sink, "LOG ");
    Serial.println(F("DBG dump end"));
  } else if (strcmp(line, "clear YES") == 0) {
    event_log->clear();
    Serial.print(F("DBG log cleared; chain continues at seq "));
    Serial.println(event_log->next_seq());
  } else if (strcmp(line, "factory YES") == 0) {
    event_log->factory();
    Serial.println(F("DBG factory reset: new chain from seq 1. Delete this device's rows on the server too."));
  } else if (strncmp(line, "clear", 5) == 0 || strncmp(line, "factory", 7) == 0) {
    Serial.println(F("DBG refusing: type 'clear YES' (wipe stored events, keep chain) or 'factory YES' (new chain)"));
  } else if (strcmp(line, "status") == 0) {
    print_status();
  } else {
    Serial.println(F("DBG commands: cal on|off, dump, status, clear YES, factory YES, {\"cmd\":\"time\",...}"));
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  {
    static const char key_hex_P[] PROGMEM = HMAC_KEY_HEX;  // stays in flash
    char key_hex[65];
    strncpy_P(key_hex, key_hex_P, sizeof(key_hex) - 1);
    key_hex[64] = '\0';
    if (strlen(key_hex) != 64 || cc_from_hex(key_hex, key, sizeof(key)) != sizeof(key)) {
      Serial.println(F("DBG error: HMAC_KEY_HEX must be 64 hex chars"));
    }
  }

  static CompactLog log(storage, DEVICE_ID, CCN, key, sizeof(key));
  event_log = &log;
  const bool kept = log.begin();  // replays up to 57 stored events to find the chain head (~1 s)
  static CallClock cc(log.boot_nonce(), MAX_CALL_S * 1000UL);
  call_clock = &cc;

  mock_station::begin();
  light.begin(PIN_LDR);
  entry.begin(millis());
  display::begin();

  Serial.print(F("DBG boot Call Clock (nano) device=" DEVICE_ID " ccn=" CCN " nonce="));
  Serial.print(log.boot_nonce(), HEX);
  Serial.print(F(" next_seq="));
  Serial.print(log.next_seq());
  Serial.print(F(" stored="));
  Serial.print(log.count());
  Serial.print('/');
  Serial.print(log.capacity());
  Serial.println(kept ? F(" (log kept)") : F(" (new log)"));
#if LIGHT_FROM_BUTTON
  Serial.println(F("DBG WARNING BYPASS BUILD: the call light is read from the button's LED pin, not the light sensor."));
  Serial.println(F("DBG WARNING This is not an independent measurement. Re-flash with -e nano once the sensor works."));
#else
  Serial.println(F("DBG boot with the call light OFF: the first LDR reading seeds the dark baseline"));
#endif
  paint_free_ram();
}

void loop() {
  const uint32_t now = millis();

  mock_station::poll(now);  // demo hardware only; shares nothing with what follows

#if LIGHT_FROM_BUTTON
  light.poll(now);  // keep sampling the LDR so `cal on` still shows it
  // BYPASS: read the mock call LED's pin directly instead of seeing it through the LDR (see config.h).
  const LightState ls = digitalRead(PIN_MOCK_CALL_LED) == HIGH ? LightState::ON : LightState::OFF;
#else
  const LightState ls = light.poll(now);
#endif
  const bool entered = entry.poll(now);
  CallEvent evs[3];  // at most call_on + entry + cancel in one tick
  const size_t n = call_clock->update(now, ls, entered, evs, 3);
  for (size_t i = 0; i < n; i++) emit(evs[i]);

  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      cmd[cmd_len] = '\0';
      handle_command(cmd);
      cmd_len = 0;
    } else if (cmd_len < sizeof(cmd) - 1) {
      cmd[cmd_len++] = c;
    }
  }

  if (calibrate && (int32_t)(now - next_cal_print_ms) >= 0) {
    next_cal_print_ms = now + CALIBRATE_PRINT_MS;
    const LightClassifier& lc = light.classifier();
    static const char* const names[] = {"OFF", "ON", "FLASH"};
    Serial.print(F("DBG raw="));
    Serial.print(light.last_raw());
    Serial.print(F(" ema="));
    Serial.print((int)lc.smoothed());
    Serial.print(F(" baseline="));
    Serial.print((int)lc.baseline());
    Serial.print(F(" threshold="));
    Serial.print((int)lc.threshold());
    Serial.print(F(" lit="));
    Serial.print(lc.lit() ? 1 : 0);
    Serial.print(F(" state="));
    Serial.print(names[(int)ls]);
    Serial.print(F(" entry="));
    Serial.println(entry.present() ? 1 : 0);
  }

  display::View v;
  v.state = call_clock->state();
  v.elapsed_ms = call_clock->elapsed_ms(now);
  v.last_wait_ds = call_clock->last_wait_ds();
  v.have_result = have_result;
  v.result_no_entry = result_no_entry;
  v.result_age_ms = now - result_ms;
  v.warmup_s = entry.warmup_remaining_s(now);
  v.calls_today = calls_since_boot;
  v.median_wait_ds = -1;
  v.clock_set = clock_set;
  v.light = ls;
  display::update(v, now);
}
