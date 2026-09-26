#include "event_log.h"

#include <stdio.h>
#include <string.h>

#include "crypto.h"

#if defined(__AVR__)
#include <avr/pgmspace.h>
#define CC_P(s) PSTR(s)  // keep JSON keys and constants in flash: the Nano has 2 KB of RAM
#else
#define CC_P(s) (s)
#endif

const char* const CC_GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

void CcSink::puts(const char* s) { write(s, strlen(s)); }

CcBufferSink::CcBufferSink(char* buf, size_t cap) : buf_(buf), cap_(cap) {
  if (cap_) buf_[0] = '\0';
}

void CcBufferSink::write(const char* s, size_t n) {
  if (!ok_ || len_ + n + 1 > cap_) {
    ok_ = false;
    return;
  }
  memcpy(buf_ + len_, s, n);
  len_ += n;
  buf_[len_] = '\0';
}

namespace {

// Streams JSON pieces to a sink. Arguments of raw_P()/key() are CC_P() literals (flash on AVR).
struct Writer {
  CcSink& out;
  void raw(const char* s) { out.puts(s); }
  void raw_P(const char* p) {
#if defined(__AVR__)
    char chunk[16];
    size_t n = 0;
    for (char c; (c = (char)pgm_read_byte(p++)) != 0;) {
      chunk[n++] = c;
      if (n == sizeof(chunk)) {
        out.write(chunk, n);
        n = 0;
      }
    }
    if (n) out.write(chunk, n);
#else
    out.puts(p);
#endif
  }
  void str(const char* s) {  // JSON string with escaping
    raw_P(CC_P("\""));
    for (const char* c = s; *c; c++) {
      unsigned char u = (unsigned char)*c;
      if (u == '"' || u == '\\') {
        char esc[2] = {'\\', (char)u};
        out.write(esc, 2);
      } else if (u < 0x20) {
        static const char hex[] = "0123456789abcdef";
        char esc[6] = {'\\', 'u', '0', '0', hex[u >> 4], hex[u & 15]};
        out.write(esc, 6);
      } else {
        out.write((const char*)c, 1);
      }
    }
    raw_P(CC_P("\""));
  }
  // `k` must be a CC_P() literal. Keys never need escaping.
  void key(const char* k, bool first = false) {
    raw_P(first ? CC_P("\"") : CC_P(",\""));
    raw_P(k);
    raw_P(CC_P("\":"));
  }
  void u32(uint32_t v) {  // no snprintf: saves stack on the Nano
    char tmp[11];
    size_t i = sizeof(tmp);
    do {
      tmp[--i] = (char)('0' + v % 10);
      v /= 10;
    } while (v);
    out.write(tmp + i, sizeof(tmp) - i);
  }
  void tri(int8_t v) { raw_P(v < 0 ? CC_P("null") : (v ? CC_P("true") : CC_P("false"))); }
};

// Tees everything into a SHA-256 on its way to `out`.
class HashingSink : public CcSink {
 public:
  explicit HashingSink(CcSink* out) : out_(out) {}
  void write(const char* s, size_t n) override {
    sha.update(s, n);
    if (out_) out_->write(s, n);
  }
  CcSha256 sha;

 private:
  CcSink* out_;
};

// Hashes prev_hash + canonical, streaming the canonical body to `out` (may be null).
void hash_canonical(const EventFields& f, CcSink* out, char* hash_hex) {
  HashingSink hs(out);
  hs.sha.update(f.prev_hash, CC_HASH_HEX_LEN);
  cc_canonical_body(f, hs);
  hs.sha.update("}", 1);  // the canonical string's closing brace is hashed but not printed here
  uint8_t digest[32];
  hs.sha.finish(digest);
  cc_to_hex(digest, 32, hash_hex);
}

void sign_hex(const uint8_t* key, size_t key_len, const char* hash_hex, char* sig_hex) {
  uint8_t mac[32];
  cc_hmac_sha256(key, key_len, (const uint8_t*)hash_hex, CC_HASH_HEX_LEN, mac);
  cc_to_hex(mac, 32, sig_hex);
}

}  // namespace

void cc_canonical_body(const EventFields& f, CcSink& out) {
  // Keys in sorted (byte) order. Keep in sync with CANONICAL_KEYS in hardware/eventlog.py.
  Writer b{out};
  b.raw_P(CC_P("{"));
  b.key(CC_P("call_id"), true); b.str(f.call_id);
  b.key(CC_P("ccn")); b.str(f.ccn);
  b.key(CC_P("device_id")); b.str(f.device_id);
  b.key(CC_P("event")); b.str(f.event);
  b.key(CC_P("ms")); b.u32(f.ms);
  b.key(CC_P("night")); b.tri(f.night);
  b.key(CC_P("no_entry")); b.tri(f.no_entry);
  b.key(CC_P("prev_hash")); b.str(f.prev_hash);
  b.key(CC_P("seq")); b.u32(f.seq);
  b.key(CC_P("synthetic")); b.raw_P(f.synthetic ? CC_P("true") : CC_P("false"));
  b.key(CC_P("ts"));
  if (f.ts) b.str(f.ts); else b.raw_P(CC_P("null"));
  b.key(CC_P("v")); b.raw_P(CC_P("1"));
  b.key(CC_P("wait_s"));
  if (f.wait_ds < 0) {
    b.raw_P(CC_P("null"));
  } else {
    b.u32((uint32_t)f.wait_ds / 10);
    b.raw_P(CC_P("."));
    b.u32((uint32_t)f.wait_ds % 10);
  }
}

size_t cc_canonical(const EventFields& f, char* out, size_t cap) {
  CcBufferSink sink(out, cap);
  cc_canonical_body(f, sink);
  sink.puts("}");
  return sink.ok() ? sink.len() : 0;
}

void cc_hash_and_sign(const char* prev_hash, const char* canonical, const uint8_t* key, size_t key_len,
                      char* hash_hex, char* sig_hex) {
  CcSha256 sha;
  sha.update(prev_hash, strlen(prev_hash));
  sha.update(canonical, strlen(canonical));
  uint8_t digest[32];
  sha.finish(digest);
  cc_to_hex(digest, 32, hash_hex);
  sign_hex(key, key_len, hash_hex, sig_hex);
}

void cc_event_hash(const EventFields& f, char* hash_hex) { hash_canonical(f, nullptr, hash_hex); }

void cc_stream_event(const EventFields& f, const uint8_t* key, size_t key_len, CcSink& out, char* hash_hex_out) {
  char local_hash[CC_HASH_HEX_LEN + 1];
  char* hash_hex = hash_hex_out ? hash_hex_out : local_hash;
  hash_canonical(f, &out, hash_hex);
  uint8_t mac[32];
  cc_hmac_sha256(key, key_len, (const uint8_t*)hash_hex, CC_HASH_HEX_LEN, mac);
  Writer w{out};
  w.raw_P(CC_P(",\"hash\":\""));
  out.write(hash_hex, CC_HASH_HEX_LEN);
  w.raw_P(CC_P("\",\"sig\":\""));
  char hex[9];
  for (uint8_t i = 0; i < 32; i += 4) {  // hex in small pieces instead of a second 65-byte buffer
    cc_to_hex(mac + i, 4, hex);
    out.write(hex, 8);
  }
  w.raw_P(CC_P("\"}"));
}

size_t cc_event_line(const EventFields& f, const uint8_t* key, size_t key_len, char* out, size_t cap,
                     char* hash_hex_out) {
  CcBufferSink sink(out, cap);
  cc_stream_event(f, key, key_len, sink, hash_hex_out);
  return sink.ok() ? sink.len() : 0;
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

#if defined(ESP_PLATFORM)
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
