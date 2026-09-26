#include "event_log.h"

#include <stdio.h>
#include <string.h>

#include "crypto.h"

const char* const CC_GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

namespace {

// Tiny bounded string builder.
struct Buf {
  char* p;
  size_t cap;
  size_t len = 0;
  bool ok = true;
  Buf(char* p_, size_t cap_) : p(p_), cap(cap_) {
    if (cap) p[0] = '\0';
  }
  void raw(const char* s) {
    size_t n = strlen(s);
    if (len + n + 1 > cap) {
      ok = false;
      return;
    }
    memcpy(p + len, s, n + 1);
    len += n;
  }
  void str(const char* s) {  // JSON string with escaping
    raw("\"");
    char tmp[8];
    for (const char* c = s; *c; c++) {
      unsigned char u = (unsigned char)*c;
      if (u == '"' || u == '\\') {
        tmp[0] = '\\'; tmp[1] = (char)u; tmp[2] = 0;
        raw(tmp);
      } else if (u < 0x20) {
        snprintf(tmp, sizeof(tmp), "\\u%04x", u);
        raw(tmp);
      } else {
        tmp[0] = (char)u; tmp[1] = 0;
        raw(tmp);
      }
    }
    raw("\"");
  }
  void key(const char* k, bool first = false) {
    if (!first) raw(",");
    str(k);
    raw(":");
  }
  void u32(uint32_t v) {
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%lu", (unsigned long)v);
    raw(tmp);
  }
  void tri(int8_t v) { raw(v < 0 ? "null" : (v ? "true" : "false")); }
};

}  // namespace

size_t cc_canonical(const EventFields& f, char* out, size_t cap) {
  // Keys in sorted (byte) order. Keep in sync with CANONICAL_KEYS in hardware/eventlog.py.
  Buf b(out, cap);
  b.raw("{");
  b.key("call_id", true); b.str(f.call_id);
  b.key("ccn"); b.str(f.ccn);
  b.key("device_id"); b.str(f.device_id);
  b.key("event"); b.str(f.event);
  b.key("ms"); b.u32(f.ms);
  b.key("night"); b.tri(f.night);
  b.key("no_entry"); b.tri(f.no_entry);
  b.key("prev_hash"); b.str(f.prev_hash);
  b.key("seq"); b.u32(f.seq);
  b.key("synthetic"); b.raw(f.synthetic ? "true" : "false");
  b.key("ts");
  if (f.ts) b.str(f.ts); else b.raw("null");
  b.key("v"); b.raw("1");
  b.key("wait_s");
  if (f.wait_ds < 0) {
    b.raw("null");
  } else {
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%ld.%ld", (long)(f.wait_ds / 10), (long)(f.wait_ds % 10));
    b.raw(tmp);
  }
  b.raw("}");
  return b.ok ? b.len : 0;
}

void cc_hash_and_sign(const char* prev_hash, const char* canonical, const uint8_t* key, size_t key_len,
                      char* hash_hex, char* sig_hex) {
  static char msg[CC_HASH_HEX_LEN + CC_LINE_MAX];
  size_t ph = strlen(prev_hash), cl = strlen(canonical);
  if (ph + cl > sizeof(msg)) cl = sizeof(msg) - ph;  // cannot happen with CC_LINE_MAX-sized canonicals
  memcpy(msg, prev_hash, ph);
  memcpy(msg + ph, canonical, cl);
  uint8_t digest[32];
  cc_sha256((const uint8_t*)msg, ph + cl, digest);
  cc_to_hex(digest, 32, hash_hex);
  uint8_t mac[32];
  cc_hmac_sha256(key, key_len, (const uint8_t*)hash_hex, CC_HASH_HEX_LEN, mac);
  cc_to_hex(mac, 32, sig_hex);
}

size_t cc_event_line(const EventFields& f, const uint8_t* key, size_t key_len, char* out, size_t cap,
                     char* hash_hex_out) {
  size_t n = cc_canonical(f, out, cap);
  if (n == 0) return 0;
  char hash_hex[CC_HASH_HEX_LEN + 1], sig_hex[CC_HASH_HEX_LEN + 1];
  cc_hash_and_sign(f.prev_hash, out, key, key_len, hash_hex, sig_hex);
  // Replace the closing brace with the hash and signature.
  const size_t extra = strlen(",\"hash\":\"\",\"sig\":\"\"}") + 2 * CC_HASH_HEX_LEN;
  if (n - 1 + extra + 1 > cap) return 0;
  n = n - 1 + (size_t)snprintf(out + n - 1, cap - (n - 1), ",\"hash\":\"%s\",\"sig\":\"%s\"}", hash_hex, sig_hex);
  if (hash_hex_out) memcpy(hash_hex_out, hash_hex, CC_HASH_HEX_LEN + 1);
  return n;
}

bool EventChain::begin(const char* device_id, const char* ccn, const char* key_hex) {
  device_id_ = device_id;
  ccn_ = ccn;
  key_len_ = cc_from_hex(key_hex, key_, sizeof(key_));
  restore(1, CC_GENESIS_HASH);
  return key_len_ > 0 && strlen(key_hex) == 2 * key_len_;
}

void EventChain::restore(uint32_t next_seq, const char* prev_hash) {
  next_seq_ = next_seq;
  strncpy(prev_hash_, prev_hash, CC_HASH_HEX_LEN);
  prev_hash_[CC_HASH_HEX_LEN] = '\0';
}

size_t EventChain::append(const CallEvent& ev, const char* ts, int8_t night, char* line, size_t cap) {
  EventFields f;
  f.seq = next_seq_;
  f.device_id = device_id_;
  f.ccn = ccn_;
  f.call_id = ev.call_id;
  f.event = event_type_name(ev.type);
  f.ts = ts;
  f.ms = ev.ms;
  f.wait_ds = ev.wait_ds;
  f.no_entry = ev.no_entry;
  f.night = night;
  f.synthetic = false;  // a physical device never emits synthetic events
  f.prev_hash = prev_hash_;
  char hash_hex[CC_HASH_HEX_LEN + 1];
  size_t n = cc_event_line(f, key_, key_len_, line, cap, hash_hex);
  if (n == 0) return 0;
  next_seq_++;
  memcpy(prev_hash_, hash_hex, sizeof(prev_hash_));
  return n;
}

#if !defined(CALLCLOCK_NATIVE)
#include <FS.h>
#include <LittleFS.h>

namespace event_store {

static const char* LOG_PATH = "/log.jsonl";
static const char* HEAD_PATH = "/head.txt";

bool begin(EventChain& chain) {
  if (!LittleFS.begin(true)) return false;  // true = format the partition on first boot
  File f = LittleFS.open(HEAD_PATH, "r");
  if (!f) return true;  // brand-new device: genesis
  String s = f.readString();
  f.close();
  unsigned long seq = 0;
  char hash[CC_HASH_HEX_LEN + 1] = {0};
  if (sscanf(s.c_str(), "%lu %64s", &seq, hash) == 2 && strlen(hash) == CC_HASH_HEX_LEN && seq >= 1) {
    chain.restore((uint32_t)seq, hash);
  }
  return true;
}

static void write_head(const EventChain& chain) {
  File h = LittleFS.open(HEAD_PATH, "w");
  if (!h) return;
  h.printf("%lu %s\n", (unsigned long)chain.next_seq(), chain.prev_hash());
  h.close();
}

bool append(const char* line, const EventChain& chain) {
  File f = LittleFS.open(LOG_PATH, "a");
  if (!f) return false;
  f.print(line);
  f.print('\n');
  f.close();
  write_head(chain);
  return true;
}

void dump(Print& out) {
  File f = LittleFS.open(LOG_PATH, "r");
  if (!f) return;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length()) {
      out.print("LOG ");
      out.println(line);
    }
  }
  f.close();
}

size_t count() {
  File f = LittleFS.open(LOG_PATH, "r");
  if (!f) return 0;
  size_t n = 0;
  while (f.available()) {
    if (f.read() == '\n') n++;
  }
  f.close();
  return n;
}

void clear() { LittleFS.remove(LOG_PATH); }

void factory(EventChain& chain) {
  LittleFS.remove(LOG_PATH);
  LittleFS.remove(HEAD_PATH);
  chain.restore(1, CC_GENESIS_HASH);
}

}  // namespace event_store
#endif
