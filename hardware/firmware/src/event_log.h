// Tamper-evident event log: canonical JSON, SHA-256 hash chain, HMAC-SHA256 signature.
//
//   canonical = JSON of every field except "hash" and "sig", keys sorted, no spaces,
//               wait_s with exactly 1 decimal, null as null
//   hash      = SHA256(prev_hash_hex + canonical)            (genesis prev_hash = 64 zeros)
//   sig       = HMAC_SHA256(device_key, hash_hex)
//
// Must match hardware/eventlog.py byte for byte; test/test_call_clock and
// hardware/tests/test_eventlog.py share a fixed test vector.
//
// Tamper-EVIDENT, not tamper-proof: the key lives in flash. See hardware/DECISIONS.md.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "call_clock.h"

#define CC_HASH_HEX_LEN 64
#define CC_LINE_MAX 640

struct EventFields {
  uint32_t seq;
  const char* device_id;
  const char* ccn;
  const char* call_id;
  const char* event;
  const char* ts;      // ISO-8601 with offset, or nullptr → null (clock not set yet)
  uint32_t ms;         // ms since boot
  int32_t wait_ds;     // deciseconds, -1 → null
  int8_t no_entry;     // TRI_NULL → null
  int8_t night;        // TRI_NULL → null (clock not set yet)
  bool synthetic;
  const char* prev_hash;
};

// Where streamed output goes: a buffer, Serial, or nowhere (hash only).
class CcSink {
 public:
  virtual void write(const char* s, size_t n) = 0;
  void puts(const char* s);
};

// A sink into a fixed buffer. ok() is false if it overflowed.
class CcBufferSink : public CcSink {
 public:
  CcBufferSink(char* buf, size_t cap);
  void write(const char* s, size_t n) override;
  bool ok() const { return ok_; }
  size_t len() const { return len_; }

 private:
  char* buf_;
  size_t cap_;
  size_t len_ = 0;
  bool ok_ = true;
};

// Writes the canonical string minus its closing brace (streamed; no buffer needed).
void cc_canonical_body(const EventFields& f, CcSink& out);
// Writes the canonical string. Returns its length, or 0 if `cap` is too small.
size_t cc_canonical(const EventFields& f, char* out, size_t cap);
// hash_hex/sig_hex must hold 65 chars.
void cc_hash_and_sign(const char* prev_hash, const char* canonical, const uint8_t* key, size_t key_len,
                      char* hash_hex, char* sig_hex);
// Hash only (no output): used to replay a chain.
void cc_event_hash(const EventFields& f, char* hash_hex);
// Streams the full signed line (canonical with ,"hash":"…","sig":"…" before the closing brace) to `out`
// while hashing it. Never holds the line in RAM. hash_hex_out may be null.
void cc_stream_event(const EventFields& f, const uint8_t* key, size_t key_len, CcSink& out, char* hash_hex_out);
// Same, into a buffer. Returns the length, or 0 if `cap` is too small.
size_t cc_event_line(const EventFields& f, const uint8_t* key, size_t key_len, char* out, size_t cap,
                     char* hash_hex_out);

extern const char* const CC_GENESIS_HASH;

// Keeps the chain head (next seq, last hash) and turns CallEvents into signed JSON lines.
class EventChain {
 public:
  bool begin(const char* device_id, const char* ccn, const char* key_hex);
  void restore(uint32_t next_seq, const char* prev_hash);
  // Returns the line length (0 on failure) and advances the head.
  size_t append(const CallEvent& ev, const char* ts, int8_t night, char* line, size_t cap);

  uint32_t next_seq() const { return next_seq_; }
  const char* prev_hash() const { return prev_hash_; }

 private:
  const char* device_id_ = "";
  const char* ccn_ = "";
  uint8_t key_[64] = {0};
  size_t key_len_ = 0;
  uint32_t next_seq_ = 1;
  char prev_hash_[CC_HASH_HEX_LEN + 1] = {0};
};

#if defined(ESP_PLATFORM)
#include <Print.h>

// LittleFS persistence: /log.jsonl (one signed event per line) and /head.txt ("<next_seq> <prev_hash>").
// `clear` wipes the log but KEEPS the chain head, so the server still sees one unbroken chain.
// `factory` wipes both and starts a new chain at seq 1 (the server must forget this device too).
namespace event_store {
bool begin(EventChain& chain);  // mounts LittleFS (formatting on first boot) and restores the head
bool append(const char* line, const EventChain& chain);
void dump(Print& out);          // prints every stored line prefixed "LOG "
void clear();
void factory(EventChain& chain);
size_t count();
}  // namespace event_store
#endif
