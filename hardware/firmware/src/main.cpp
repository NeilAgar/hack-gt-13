// Call Clock firmware: wiring of modules only. Logic lives in the modules.
//
//   mock_station  → drives the fake call LED (demo only; never read by anything below)
//   light_sensor  → LDR on the call LED → OFF/ON/FLASH
//   entry_sensor  → doorway presence edge
//   call_clock    → pure state machine → call_on / entry / cancel / timeout
//   event_log     → signed, hash-chained JSON lines → Serial ("EVT …") + LittleFS
//   display, net  → OLED/LED/buzzer, optional Wi-Fi
//
// Serial protocol (115200 baud, one line each):
//   out:  EVT {json}   one signed event        LOG {json}  a stored event (reply to `dump`)
//         DBG …        human-readable debug
//   in:   {"cmd":"time","epoch":1790000000}    set the clock (the bridge sends this on connect)
//         cal on | cal off | dump | status | clear YES | factory YES | help
#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_random.h>
#include <sys/time.h>
#include <time.h>

#include "call_clock.h"
#include "config.h"
#include "display.h"
#include "entry_sensor.h"
#include "event_log.h"
#include "light_sensor.h"
#include "mock_station.h"
#include "net.h"

static CallClock* call_clock = nullptr;
static EventChain chain;
static LightSensor light;
static EntrySensor entry;
static bool calibrate = CALIBRATE;
static uint32_t next_cal_print_ms = 0;
static String cmd;

// Idle stats for the OLED: calls and waits since local midnight (or since boot without a clock).
static const size_t kMaxWaits = 128;
static int32_t waits_ds[kMaxWaits];
static size_t n_waits = 0;
static uint32_t calls_today = 0;
static int stats_yday = -1;
static bool have_result = false, result_no_entry = false;
static uint32_t result_ms = 0;

static bool clock_set() { return time(nullptr) > 1600000000; }

// ISO-8601 local time with a ±HH:MM offset, e.g. 2026-09-26T14:03:22-04:00. False if no clock.
static bool local_iso(char* out, size_t cap, int8_t* night) {
  if (!clock_set()) return false;
  time_t now = time(nullptr);
  struct tm lt;
  localtime_r(&now, &lt);
  char base[24], off[8];
  strftime(base, sizeof(base), "%Y-%m-%dT%H:%M:%S", &lt);
  strftime(off, sizeof(off), "%z", &lt);  // "-0400"
  snprintf(out, cap, "%s%c%c%c:%c%c", base, off[0], off[1], off[2], off[3], off[4]);
  *night = (lt.tm_hour >= NIGHT_START_HOUR || lt.tm_hour < NIGHT_END_HOUR) ? 1 : 0;
  return true;
}

static void roll_stats_day() {
  if (!clock_set()) return;
  time_t now = time(nullptr);
  struct tm lt;
  localtime_r(&now, &lt);
  if (lt.tm_yday != stats_yday) {
    stats_yday = lt.tm_yday;
    calls_today = 0;
    n_waits = 0;
  }
}

static int32_t median_wait_ds() {
  if (n_waits == 0) return -1;
  int32_t tmp[kMaxWaits];
  memcpy(tmp, waits_ds, n_waits * sizeof(int32_t));
  for (size_t i = 1; i < n_waits; i++)  // insertion sort: n ≤ 128
    for (size_t j = i; j > 0 && tmp[j - 1] > tmp[j]; j--) std::swap(tmp[j - 1], tmp[j]);
  return n_waits % 2 ? tmp[n_waits / 2] : (tmp[n_waits / 2 - 1] + tmp[n_waits / 2]) / 2;
}

static void emit(const CallEvent& ev) {
  char ts[32];
  int8_t night = TRI_NULL;
  const bool has_ts = local_iso(ts, sizeof(ts), &night);
  static char line[CC_LINE_MAX];
  if (chain.append(ev, has_ts ? ts : nullptr, night, line, sizeof(line)) == 0) {
    Serial.println("DBG error: event line overflow");
    return;
  }
  Serial.print("EVT ");
  Serial.println(line);
  if (!event_store::append(line, chain)) Serial.println("DBG error: LittleFS append failed");
  net::enqueue(line);

  roll_stats_day();
  switch (ev.type) {
    case EventType::CALL_ON:
      calls_today++;
      have_result = false;
      break;
    case EventType::ENTRY:
      if (n_waits < kMaxWaits) waits_ds[n_waits++] = ev.wait_ds;
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
  Serial.printf("DBG status device=%s ccn=%s next_seq=%lu clock=%s entry=%s state=%d stored=%u\n", DEVICE_ID,
                CCN, (unsigned long)chain.next_seq(), clock_set() ? "set" : "unset", entry.name(),
                (int)call_clock->state(), (unsigned)event_store::count());
}

static void handle_command(String line) {
  line.trim();
  if (line.length() == 0) return;
  if (line[0] == '{') {
    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) {
      Serial.println("DBG bad json command");
      return;
    }
    if (doc["cmd"] == "time") {
      int64_t epoch = doc["epoch"] | (int64_t)0;
      if (epoch < 1600000000) {
        Serial.println("DBG time: epoch looks wrong, ignored");
        return;
      }
      struct timeval tv = {(time_t)epoch, 0};
      settimeofday(&tv, nullptr);
      char ts[32];
      int8_t night;
      local_iso(ts, sizeof(ts), &night);
      Serial.printf("DBG time set %s\n", ts);
      roll_stats_day();
    }
    return;
  }
  if (line == "cal on") {
    calibrate = true;
  } else if (line == "cal off") {
    calibrate = false;
  } else if (line == "dump") {
    event_store::dump(Serial);
    Serial.println("DBG dump end");
  } else if (line == "clear YES") {
    event_store::clear();
    Serial.printf("DBG log cleared; chain continues at seq %lu\n", (unsigned long)chain.next_seq());
  } else if (line == "factory YES") {
    event_store::factory(chain);
    Serial.println("DBG factory reset: new chain from seq 1. Delete this device's rows on the server too.");
  } else if (line.startsWith("clear") || line.startsWith("factory")) {
    Serial.println("DBG refusing: type 'clear YES' (wipe local log, keep chain) or 'factory YES' (new chain)");
  } else if (line == "status") {
    print_status();
  } else {
    Serial.println("DBG commands: cal on|off, dump, status, clear YES, factory YES, {\"cmd\":\"time\",\"epoch\":N}");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  setenv("TZ", TZ_STRING, 1);
  tzset();

  const uint16_t nonce = (uint16_t)(esp_random() & 0xFFFF);  // makes call_ids unique across reboots
  static CallClock cc(nonce, MAX_CALL_S * 1000UL);
  call_clock = &cc;

  if (!chain.begin(DEVICE_ID, CCN, HMAC_KEY_HEX)) Serial.println("DBG error: HMAC_KEY_HEX is not valid hex");
  if (!event_store::begin(chain)) Serial.println("DBG error: LittleFS mount failed; events are serial-only");

  mock_station::begin();
  light.begin(PIN_LDR);
  entry.begin(millis());
  display::begin();
  net::begin();

  Serial.printf("DBG boot Call Clock device=%s ccn=%s nonce=%04x next_seq=%lu entry=%s demo=%d\n", DEVICE_ID, CCN,
                nonce, (unsigned long)chain.next_seq(), entry.name(), DEMO_MODE);
  Serial.println("DBG boot with the call light OFF: the first LDR reading seeds the dark baseline");
}

void loop() {
  const uint32_t now = millis();

  mock_station::poll(now);  // demo hardware only; shares nothing with what follows

  const LightState ls = light.poll(now);
  const bool entered = entry.poll(now);
  CallEvent evs[4];
  const size_t n = call_clock->update(now, ls, entered, evs, 4);
  for (size_t i = 0; i < n; i++) emit(evs[i]);

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      handle_command(cmd);
      cmd = "";
    } else if (cmd.length() < 200) {
      cmd += c;
    }
  }

  if (calibrate && (int32_t)(now - next_cal_print_ms) >= 0) {
    next_cal_print_ms = now + CALIBRATE_PRINT_MS;
    const LightClassifier& lc = light.classifier();
    static const char* names[] = {"OFF", "ON", "FLASH"};
    Serial.printf("DBG raw=%d ema=%.0f baseline=%.0f threshold=%.0f lit=%d state=%s entry=%d\n", light.last_raw(),
                  lc.smoothed(), lc.baseline(), lc.threshold(), lc.lit() ? 1 : 0, names[(int)ls],
                  entry.present() ? 1 : 0);
  }

  display::View v;
  v.state = call_clock->state();
  v.elapsed_ms = call_clock->elapsed_ms(now);
  v.last_wait_ds = call_clock->last_wait_ds();
  v.have_result = have_result;
  v.result_no_entry = result_no_entry;
  v.result_age_ms = now - result_ms;
  v.warmup_s = entry.warmup_remaining_s(now);
  v.calls_today = calls_today;
  v.median_wait_ds = median_wait_ds();
  v.clock_set = clock_set();
  v.light = ls;
  display::update(v, now);

  net::poll(now);
  delay(1);
}
