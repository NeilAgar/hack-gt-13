// Native Unity tests: pio test -e native
// Covers the pure call state machine, the light classifier, and the event hash chain
// (including the cross-language test vector shared with hardware/tests/test_eventlog.py).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unity.h>

#include <string>
#include <vector>

#include "call_clock.h"
#include "compact_log.h"
#include "crypto.h"
#include "event_log.h"
#include "light_sensor.h"
#include "timefmt.h"

void setUp() {}
void tearDown() {}

// ───────────── state machine ─────────────

static CallEvent evs[4];

static size_t step(CallClock& cc, uint32_t t, LightState l, bool entry = false) {
  return cc.update(t, l, entry, evs, 4);
}

void test_call_entry_cancel() {
  CallClock cc(0xa1b2, 7200000);
  TEST_ASSERT_EQUAL(0, step(cc, 0, LightState::OFF));
  TEST_ASSERT_EQUAL(1, step(cc, 1000, LightState::ON));
  TEST_ASSERT_EQUAL(EventType::CALL_ON, evs[0].type);
  TEST_ASSERT_EQUAL_STRING("a1b2-0001", evs[0].call_id);
  TEST_ASSERT_EQUAL(-1, evs[0].wait_ds);
  TEST_ASSERT_EQUAL(TRI_NULL, evs[0].no_entry);
  TEST_ASSERT_EQUAL(CallState::CALLING, cc.state());

  TEST_ASSERT_EQUAL(1, step(cc, 22400, LightState::ON, true));
  TEST_ASSERT_EQUAL(EventType::ENTRY, evs[0].type);
  TEST_ASSERT_EQUAL(214, evs[0].wait_ds);  // 21.4 s
  TEST_ASSERT_EQUAL(CallState::ATTENDED, cc.state());

  TEST_ASSERT_EQUAL(0, step(cc, 25000, LightState::ON, true));  // further entries ignored

  TEST_ASSERT_EQUAL(1, step(cc, 40000, LightState::OFF));
  TEST_ASSERT_EQUAL(EventType::CANCEL, evs[0].type);
  TEST_ASSERT_EQUAL(214, evs[0].wait_ds);
  TEST_ASSERT_EQUAL(0, evs[0].no_entry);
  TEST_ASSERT_EQUAL_STRING("a1b2-0001", evs[0].call_id);
  TEST_ASSERT_EQUAL(CallState::IDLE, cc.state());
}

void test_cancel_with_no_entry() {
  CallClock cc(0x00ff, 7200000);
  step(cc, 0, LightState::FLASH);  // FLASH counts as ON
  TEST_ASSERT_EQUAL(CallState::CALLING, cc.state());
  TEST_ASSERT_EQUAL(1, step(cc, 12000, LightState::OFF));
  TEST_ASSERT_EQUAL(EventType::CANCEL, evs[0].type);
  TEST_ASSERT_EQUAL(-1, evs[0].wait_ds);
  TEST_ASSERT_EQUAL(1, evs[0].no_entry);
}

void test_entry_while_idle_ignored_and_ids_increment() {
  CallClock cc(0x0001, 7200000);
  TEST_ASSERT_EQUAL(0, step(cc, 0, LightState::OFF, true));
  step(cc, 100, LightState::ON);
  step(cc, 200, LightState::OFF);
  TEST_ASSERT_EQUAL(1, step(cc, 300, LightState::ON));
  TEST_ASSERT_EQUAL_STRING("0001-0002", evs[0].call_id);
}

void test_call_and_entry_same_tick() {
  CallClock cc(0x0001, 7200000);
  TEST_ASSERT_EQUAL(2, step(cc, 500, LightState::ON, true));
  TEST_ASSERT_EQUAL(EventType::CALL_ON, evs[0].type);
  TEST_ASSERT_EQUAL(EventType::ENTRY, evs[1].type);
  TEST_ASSERT_EQUAL(0, evs[1].wait_ds);
}

void test_timeout_then_rearm() {
  CallClock cc(0x0001, 10000);
  step(cc, 0, LightState::ON);
  TEST_ASSERT_EQUAL(0, step(cc, 9999, LightState::ON));
  TEST_ASSERT_EQUAL(1, step(cc, 10000, LightState::ON));
  TEST_ASSERT_EQUAL(EventType::TIMEOUT, evs[0].type);
  TEST_ASSERT_EQUAL(1, evs[0].no_entry);
  TEST_ASSERT_EQUAL(CallState::TIMED_OUT, cc.state());
  TEST_ASSERT_EQUAL(0, step(cc, 20000, LightState::ON, true));  // no events while timed out
  TEST_ASSERT_EQUAL(0, step(cc, 21000, LightState::OFF));       // silent re-arm
  TEST_ASSERT_EQUAL(CallState::IDLE, cc.state());
  TEST_ASSERT_EQUAL(1, step(cc, 22000, LightState::ON));
}

void test_millis_wraparound() {
  CallClock cc(0x0001, 7200000);
  step(cc, 0xFFFFF000u, LightState::ON);
  TEST_ASSERT_EQUAL(1, step(cc, 0x00000F00u, LightState::ON, true));  // 7936 ms later, after the wrap
  TEST_ASSERT_EQUAL(79, evs[0].wait_ds);
}

// ───────────── light classifier ─────────────

static LightConfig test_light_cfg() {
  LightConfig c;
  c.ema_alpha = 1.0f;  // no smoothing: makes the timing exact
  c.baseline_alpha = 0.001f;
  c.delta = 300;
  c.fixed_threshold = 0;
  c.hysteresis = 60;
  c.on_hold_ms = 300;
  c.off_hold_ms = 2000;
  c.flash_window_ms = 2000;
  c.flash_min_transitions = 3;
  return c;
}

void test_light_debounce_on_off() {
  LightClassifier lc(test_light_cfg());
  uint32_t t = 0;
  for (; t < 1000; t += 10) TEST_ASSERT_EQUAL(LightState::OFF, lc.feed(t, 500));
  // A 200 ms blip is not a call.
  for (; t < 1200; t += 10) TEST_ASSERT_EQUAL(LightState::OFF, lc.feed(t, 1500));
  for (; t < 3000; t += 10) lc.feed(t, 500);
  TEST_ASSERT_EQUAL(LightState::OFF, lc.state());
  // Held ON for ≥ 300 ms.
  uint32_t on_at = t;
  while (lc.feed(t, 1500) == LightState::OFF) t += 10;
  TEST_ASSERT_UINT32_WITHIN(20, 300, t - on_at);
  for (; t < 6000; t += 10) lc.feed(t, 1500);
  // OFF only after 2 s of dark.
  uint32_t off_at = t;
  while (lc.feed(t, 500) != LightState::OFF) t += 10;
  TEST_ASSERT_UINT32_WITHIN(20, 2000, t - off_at);
}

void test_light_flash_counts_as_on() {
  LightClassifier lc(test_light_cfg());
  uint32_t t = 0;
  for (; t < 1000; t += 10) lc.feed(t, 500);
  bool saw_flash = false, dropped = false;
  // 2 Hz flashing, 250 ms on / 250 ms off, for 6 s.
  for (int i = 0; i < 600; i++, t += 10) {
    int raw = ((t / 250) % 2) ? 1500 : 500;
    LightState s = lc.feed(t, raw);
    if (s == LightState::FLASH) saw_flash = true;
    if (saw_flash && s == LightState::OFF) dropped = true;
  }
  TEST_ASSERT_TRUE(saw_flash);
  TEST_ASSERT_FALSE(dropped);
}

void test_light_fixed_threshold() {
  LightConfig c = test_light_cfg();
  c.fixed_threshold = 2000;
  LightClassifier lc(c);
  uint32_t t = 0;
  for (; t < 1000; t += 10) lc.feed(t, 1900);  // above baseline+delta, below the fixed threshold
  TEST_ASSERT_EQUAL(LightState::OFF, lc.state());
  for (; t < 2000; t += 10) lc.feed(t, 2100);
  TEST_ASSERT_EQUAL(LightState::ON, lc.state());
}

// ───────────── crypto + chain ─────────────

void test_sha256_known_answer() {
  uint8_t d[32];
  char hex[65];
  cc_sha256((const uint8_t*)"abc", 3, d);
  cc_to_hex(d, 32, hex);
  TEST_ASSERT_EQUAL_STRING("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", hex);
  // RFC 4231 test case 2
  cc_hmac_sha256((const uint8_t*)"Jefe", 4, (const uint8_t*)"what do ya want for nothing?", 28, d);
  cc_to_hex(d, 32, hex);
  TEST_ASSERT_EQUAL_STRING("5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843", hex);
}

// CROSS-LANGUAGE TEST VECTOR. The same event, key and expected values are in
// hardware/tests/test_eventlog.py. If you change the format, change both.
static const char* VEC_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
static const char* VEC_CANONICAL =
    "{\"call_id\":\"a1b2-0007\",\"ccn\":\"115999\",\"device_id\":\"cc-01\",\"event\":\"entry\","
    "\"ms\":1234567,\"night\":false,\"no_entry\":null,"
    "\"prev_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\","
    "\"seq\":12,\"synthetic\":false,\"ts\":\"2026-09-26T14:03:22-04:00\",\"v\":1,\"wait_s\":21.4}";
static const char* VEC_HASH = "43fdb7fcba627e8662e1db8c2b3debd00c2aa4c80ddd6eb483e79bdaabe5934a";
static const char* VEC_SIG = "5cd1a4bc9bac4b3f8f72824b8ec0fe926aad8a8c6ea1030f1cea85eca35c274e";

void test_cross_language_vector() {
  EventFields f;
  f.seq = 12;
  f.device_id = "cc-01";
  f.ccn = "115999";
  f.call_id = "a1b2-0007";
  f.event = "entry";
  f.ts = "2026-09-26T14:03:22-04:00";
  f.ms = 1234567;
  f.wait_ds = 214;
  f.no_entry = TRI_NULL;
  f.night = 0;
  f.synthetic = false;
  f.prev_hash = CC_GENESIS_HASH;

  char buf[CC_LINE_MAX];
  TEST_ASSERT_TRUE(cc_canonical(f, buf, sizeof(buf)) > 0);
  TEST_ASSERT_EQUAL_STRING(VEC_CANONICAL, buf);

  uint8_t key[32];
  TEST_ASSERT_EQUAL(32, cc_from_hex(VEC_KEY_HEX, key, sizeof(key)));
  char hash[65], sig[65];
  cc_hash_and_sign(f.prev_hash, buf, key, 32, hash, sig);
  TEST_ASSERT_EQUAL_STRING(VEC_HASH, hash);
  TEST_ASSERT_EQUAL_STRING(VEC_SIG, sig);

  char line[CC_LINE_MAX];
  TEST_ASSERT_TRUE(cc_event_line(f, key, 32, line, sizeof(line), nullptr) > 0);
  TEST_ASSERT_NOT_NULL(strstr(line, VEC_HASH));
  TEST_ASSERT_NOT_NULL(strstr(line, VEC_SIG));
  TEST_ASSERT_EQUAL_CHAR('}', line[strlen(line) - 1]);
}

void test_chain_links_and_nulls() {
  EventChain chain;
  TEST_ASSERT_TRUE(chain.begin("cc-01", "115999", VEC_KEY_HEX));
  TEST_ASSERT_EQUAL(1, chain.next_seq());
  TEST_ASSERT_EQUAL_STRING(CC_GENESIS_HASH, chain.prev_hash());

  CallEvent e;
  memset(&e, 0, sizeof(e));
  e.type = EventType::CALL_ON;
  strcpy(e.call_id, "beef-0001");
  e.ms = 5000;
  e.wait_ds = -1;
  e.no_entry = TRI_NULL;
  char line1[CC_LINE_MAX], line2[CC_LINE_MAX];
  TEST_ASSERT_TRUE(chain.append(e, nullptr, TRI_NULL, line1, sizeof(line1)) > 0);
  TEST_ASSERT_NOT_NULL(strstr(line1, "\"ts\":null"));
  TEST_ASSERT_NOT_NULL(strstr(line1, "\"night\":null"));
  TEST_ASSERT_NOT_NULL(strstr(line1, "\"wait_s\":null"));
  TEST_ASSERT_NOT_NULL(strstr(line1, "\"seq\":1,"));
  TEST_ASSERT_EQUAL(2, chain.next_seq());

  char first_hash[65];
  strcpy(first_hash, chain.prev_hash());
  e.type = EventType::CANCEL;
  e.wait_ds = 5;  // 0.5 s
  e.no_entry = 0;
  TEST_ASSERT_TRUE(chain.append(e, "2026-09-26T23:30:00-04:00", 1, line2, sizeof(line2)) > 0);
  TEST_ASSERT_NOT_NULL(strstr(line2, first_hash));  // prev_hash of #2 is hash of #1
  TEST_ASSERT_NOT_NULL(strstr(line2, "\"wait_s\":0.5"));
  TEST_ASSERT_NOT_NULL(strstr(line2, "\"night\":true"));
  TEST_ASSERT_NOT_NULL(strstr(line2, "\"no_entry\":false"));
}


// ───────────── Nano: time formatting without a time library ─────────────

void test_iso_format_matches_python() {
  // Expected strings from Python: datetime.fromtimestamp(e, timezone(timedelta(seconds=o))).isoformat()
  char buf[26];
  cc_format_iso(1790449402UL, -14400, buf);
  TEST_ASSERT_EQUAL_STRING("2026-09-26T15:03:22-04:00", buf);
  cc_format_iso(1790449402UL, 0, buf);
  TEST_ASSERT_EQUAL_STRING("2026-09-26T19:03:22+00:00", buf);
  cc_format_iso(1709251199UL, -14400, buf);  // leap day
  TEST_ASSERT_EQUAL_STRING("2024-02-29T19:59:59-04:00", buf);
  cc_format_iso(4102444799UL, 19800, buf);  // +05:30, year rollover
  TEST_ASSERT_EQUAL_STRING("2100-01-01T05:29:59+05:30", buf);
  TEST_ASSERT_EQUAL(15, cc_local_hour(1790449402UL, -14400));
  TEST_ASSERT_EQUAL(23, cc_local_hour(1790449402UL + 8 * 3600, -14400));
}

void test_parse_time_command() {
  uint32_t e = 0;
  int32_t off = -18000;
  TEST_ASSERT_TRUE(cc_parse_time_cmd("{\"cmd\": \"time\", \"epoch\": 1790449402, \"tz_offset\": -14400}", &e, &off));
  TEST_ASSERT_EQUAL_UINT32(1790449402UL, e);
  TEST_ASSERT_EQUAL(-14400, off);
  off = -18000;  // old bridge: no tz_offset → keep the default
  TEST_ASSERT_TRUE(cc_parse_time_cmd("{\"cmd\":\"time\",\"epoch\":4000000000}", &e, &off));
  TEST_ASSERT_EQUAL_UINT32(4000000000UL, e);  // past 2038: parsed as unsigned
  TEST_ASSERT_EQUAL(-18000, off);
  TEST_ASSERT_FALSE(cc_parse_time_cmd("{\"cmd\":\"time\",\"epoch\":12}", &e, &off));
  TEST_ASSERT_FALSE(cc_parse_time_cmd("{\"cmd\":\"dump\"}", &e, &off));
}

// ───────────── Nano: compact EEPROM log ─────────────

class RamStorage : public CcStorage {
 public:
  explicit RamStorage(uint16_t n) : bytes(n, 0xFF), writes(0) {}  // blank EEPROM reads 0xFF
  uint8_t read(uint16_t a) override { return bytes.at(a); }
  void write(uint16_t a, uint8_t v) override {
    if (bytes.at(a) != v) writes++;
    bytes.at(a) = v;
  }
  uint16_t size() const override { return (uint16_t)bytes.size(); }
  std::vector<uint8_t> bytes;
  unsigned writes;
};

class LinesSink : public CcSink {
 public:
  void write(const char* s, size_t n) override { cur.append(s, n); }
  std::string take() {
    std::string s = cur;
    cur.clear();
    return s;
  }
  std::string cur;
};

static uint8_t vec_key[32];

static CompactEvent cev(EventType t, uint16_t nonce, uint16_t counter, uint32_t ms, int32_t wait_ds, int8_t no_entry,
                        bool has_time, uint32_t epoch) {
  CompactEvent e;
  e.type = t;
  e.no_entry = no_entry;
  e.nonce = nonce;
  e.counter = counter;
  e.ms = ms;
  e.wait_ds = wait_ds;
  e.has_time = has_time;
  e.epoch = epoch;
  e.tz_offset_s = -14400;
  return e;
}

// Emits n events (call_on / entry / cancel cycles) and returns their lines.
static std::vector<std::string> emit_calls(CompactLog& log, int n, uint32_t epoch0) {
  std::vector<std::string> lines;
  LinesSink sink;
  for (int i = 0; i < n; i++) {
    const int call = i / 3 + 1, phase = i % 3;
    const uint32_t ms = 10000u + (uint32_t)i * 7000u;
    CompactEvent e = phase == 0   ? cev(EventType::CALL_ON, log.boot_nonce(), call, ms, -1, TRI_NULL, true, epoch0 + i * 7)
                     : phase == 1 ? cev(EventType::ENTRY, log.boot_nonce(), call, ms, 214, TRI_NULL, true, epoch0 + i * 7)
                                  : cev(EventType::CANCEL, log.boot_nonce(), call, ms, 214, 0, i % 2, epoch0 + i * 7);
    log.emit(e, sink);
    lines.push_back(sink.take());
  }
  return lines;
}

static std::vector<std::string> dump_lines(CompactLog& log) {
  LinesSink sink;
  log.dump(sink, "LOG ");
  std::vector<std::string> out;
  size_t pos = 0;
  const std::string& s = sink.cur;
  while (pos < s.size()) {
    size_t nl = s.find('\n', pos);
    std::string line = s.substr(pos, nl - pos);
    TEST_ASSERT_EQUAL_STRING("LOG ", line.substr(0, 4).c_str());
    out.push_back(line.substr(4));
    pos = nl + 1;
  }
  return out;
}

static std::string field(const std::string& line, const char* key) {
  std::string k = std::string("\"") + key + "\":";
  size_t p = line.find(k);
  TEST_ASSERT_TRUE(p != std::string::npos);
  p += k.size();
  size_t e = line.find_first_of(",}", p);
  std::string v = line.substr(p, e - p);
  if (!v.empty() && v[0] == '"') v = v.substr(1, v.size() - 2);
  return v;
}

void test_compact_log_matches_esp32_chain() {
  // The same event must produce byte-identical lines on the Nano (CompactLog) and the ESP32 (EventChain).
  cc_from_hex(VEC_KEY_HEX, vec_key, 32);
  RamStorage st(1024);
  CompactLog log(st, "cc-01", "115999", vec_key, 32);
  TEST_ASSERT_FALSE(log.begin());  // blank EEPROM → new log
  TEST_ASSERT_EQUAL(57, log.capacity());
  EventChain chain;
  chain.begin("cc-01", "115999", VEC_KEY_HEX);

  CallEvent ce;
  memset(&ce, 0, sizeof(ce));
  ce.type = EventType::ENTRY;
  snprintf(ce.call_id, sizeof(ce.call_id), "%04x-%04u", (unsigned)log.boot_nonce(), 7u);
  ce.ms = 1234567;
  ce.wait_ds = 214;
  ce.no_entry = TRI_NULL;
  char esp[CC_LINE_MAX];
  TEST_ASSERT_TRUE(chain.append(ce, "2026-09-26T15:03:22-04:00", 0, esp, sizeof(esp)) > 0);

  LinesSink sink;
  log.emit(cev(EventType::ENTRY, log.boot_nonce(), 7, 1234567, 214, TRI_NULL, true, 1790449402UL), sink);
  TEST_ASSERT_EQUAL_STRING(esp, sink.take().c_str());
  TEST_ASSERT_EQUAL_STRING(chain.prev_hash(), log.head_hash());
}

void test_compact_log_dump_reproduces_lines_and_chain() {
  RamStorage st(1024);
  CompactLog log(st, "cc-01", "115999", vec_key, 32);
  log.begin();
  std::vector<std::string> lines = emit_calls(log, 9, 1790449402UL);
  std::vector<std::string> dumped = dump_lines(log);
  TEST_ASSERT_EQUAL(9, (int)dumped.size());
  for (size_t i = 0; i < lines.size(); i++) TEST_ASSERT_EQUAL_STRING(lines[i].c_str(), dumped[i].c_str());
  TEST_ASSERT_EQUAL_STRING("1", field(lines[0], "seq").c_str());
  TEST_ASSERT_EQUAL_STRING(CC_GENESIS_HASH, field(lines[0], "prev_hash").c_str());
  for (size_t i = 1; i < lines.size(); i++)
    TEST_ASSERT_EQUAL_STRING(field(lines[i - 1], "hash").c_str(), field(lines[i], "prev_hash").c_str());
  TEST_ASSERT_EQUAL_STRING("false", field(lines[0], "synthetic").c_str());
  // Event 2 was made before a time sync (has_time false): ts and night are null.
  TEST_ASSERT_EQUAL_STRING("null", field(lines[2], "ts").c_str());
  TEST_ASSERT_EQUAL_STRING("null", field(lines[2], "night").c_str());
  TEST_ASSERT_EQUAL_STRING("2026-09-26T15:03:22-04:00", field(lines[0], "ts").c_str());
  TEST_ASSERT_EQUAL_STRING("false", field(lines[0], "night").c_str());
}

void test_compact_log_survives_reboot() {
  RamStorage st(1024);
  std::string head;
  uint16_t nonce1;
  {
    CompactLog log(st, "cc-01", "115999", vec_key, 32);
    log.begin();
    nonce1 = log.boot_nonce();
    emit_calls(log, 5, 1790449402UL);
    head = log.head_hash();
  }
  CompactLog again(st, "cc-01", "115999", vec_key, 32);  // power cycle
  TEST_ASSERT_TRUE(again.begin());
  TEST_ASSERT_EQUAL(nonce1 + 1, again.boot_nonce());  // new call_id prefix every boot
  TEST_ASSERT_EQUAL_UINT32(6, again.next_seq());
  TEST_ASSERT_EQUAL_STRING(head.c_str(), again.head_hash());
  LinesSink sink;
  again.emit(cev(EventType::CALL_ON, again.boot_nonce(), 1, 50, -1, TRI_NULL, false, 0), sink);
  std::string line = sink.take();
  TEST_ASSERT_EQUAL_STRING(head.c_str(), field(line, "prev_hash").c_str());
  TEST_ASSERT_EQUAL_STRING("null", field(line, "ts").c_str());
  TEST_ASSERT_EQUAL_STRING("null", field(line, "night").c_str());
}

void test_compact_log_ring_evicts_without_breaking_chain() {
  RamStorage st(CompactLog::kHeader + 4 * CompactLog::kRecord);  // room for 4 events
  CompactLog log(st, "cc-01", "115999", vec_key, 32);
  log.begin();
  TEST_ASSERT_EQUAL(4, log.capacity());
  std::vector<std::string> lines = emit_calls(log, 11, 1790449402UL);
  std::vector<std::string> dumped = dump_lines(log);
  TEST_ASSERT_EQUAL(4, (int)dumped.size());
  for (int i = 0; i < 4; i++) TEST_ASSERT_EQUAL_STRING(lines[7 + i].c_str(), dumped[i].c_str());
  // The oldest kept event still links to the evicted one's hash.
  TEST_ASSERT_EQUAL_STRING(field(lines[6], "hash").c_str(), field(dumped[0], "prev_hash").c_str());
  CompactLog again(st, "cc-01", "115999", vec_key, 32);
  TEST_ASSERT_TRUE(again.begin());
  TEST_ASSERT_EQUAL_UINT32(12, again.next_seq());
  TEST_ASSERT_EQUAL_STRING(field(lines[10], "hash").c_str(), again.head_hash());
  if (const char* path = getenv("CC_NANO_DUMP")) {  // manual cross-check with hardware/tools/verify_log.py
    FILE* f = fopen(path, "w");
    for (auto& l : lines) fprintf(f, "%s\n", l.c_str());
    fclose(f);
  }
}

void test_compact_log_clear_factory_and_identity() {
  RamStorage st(1024);
  {
    CompactLog log(st, "cc-01", "115999", vec_key, 32);
    log.begin();
    emit_calls(log, 4, 1790449402UL);
    std::string head = log.head_hash();
    log.clear();  // local copy gone, chain continues
    TEST_ASSERT_EQUAL(0, log.count());
    TEST_ASSERT_EQUAL_UINT32(5, log.next_seq());
    TEST_ASSERT_EQUAL_STRING(head.c_str(), log.head_hash());
    TEST_ASSERT_EQUAL(0, (int)dump_lines(log).size());
    LinesSink sink;
    log.emit(cev(EventType::CALL_ON, log.boot_nonce(), 9, 1, -1, TRI_NULL, false, 0), sink);
    TEST_ASSERT_EQUAL_STRING(head.c_str(), field(sink.take(), "prev_hash").c_str());
    log.factory();
    TEST_ASSERT_EQUAL_UINT32(1, log.next_seq());
    TEST_ASSERT_EQUAL_STRING(CC_GENESIS_HASH, log.head_hash());
  }
  {
    CompactLog log(st, "cc-01", "115999", vec_key, 32);
    log.begin();
    emit_calls(log, 3, 1790449402UL);
  }
  CompactLog other(st, "cc-02", "115999", vec_key, 32);  // different device on the same EEPROM
  TEST_ASSERT_FALSE(other.begin());
  TEST_ASSERT_EQUAL(0, other.count());
  TEST_ASSERT_EQUAL_UINT32(1, other.next_seq());
}

void test_compact_log_rejects_corrupt_record() {
  RamStorage st(1024);
  {
    CompactLog log(st, "cc-01", "115999", vec_key, 32);
    log.begin();
    emit_calls(log, 6, 1790449402UL);
  }
  st.bytes[CompactLog::kHeader + 3 * CompactLog::kRecord] = 0xFF;  // 4th record's flags garbled
  CompactLog again(st, "cc-01", "115999", vec_key, 32);
  again.begin();
  TEST_ASSERT_EQUAL(3, again.count());  // keeps what decodes; the server shows the gap
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_call_entry_cancel);
  RUN_TEST(test_cancel_with_no_entry);
  RUN_TEST(test_entry_while_idle_ignored_and_ids_increment);
  RUN_TEST(test_call_and_entry_same_tick);
  RUN_TEST(test_timeout_then_rearm);
  RUN_TEST(test_millis_wraparound);
  RUN_TEST(test_light_debounce_on_off);
  RUN_TEST(test_light_flash_counts_as_on);
  RUN_TEST(test_light_fixed_threshold);
  RUN_TEST(test_sha256_known_answer);
  RUN_TEST(test_cross_language_vector);
  RUN_TEST(test_chain_links_and_nulls);
  RUN_TEST(test_iso_format_matches_python);
  RUN_TEST(test_parse_time_command);
  RUN_TEST(test_compact_log_matches_esp32_chain);
  RUN_TEST(test_compact_log_dump_reproduces_lines_and_chain);
  RUN_TEST(test_compact_log_survives_reboot);
  RUN_TEST(test_compact_log_ring_evicts_without_breaking_chain);
  RUN_TEST(test_compact_log_clear_factory_and_identity);
  RUN_TEST(test_compact_log_rejects_corrupt_record);
  return UNITY_END();
}
