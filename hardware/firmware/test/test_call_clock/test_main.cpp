// Native Unity tests: pio test -e native
// Covers the pure call state machine, the light classifier, and the event hash chain
// (including the cross-language test vector shared with hardware/tests/test_eventlog.py).
#include <string.h>
#include <unity.h>

#include "call_clock.h"
#include "crypto.h"
#include "event_log.h"
#include "light_sensor.h"

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
  return UNITY_END();
}
