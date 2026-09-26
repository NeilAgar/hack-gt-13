// Compact, EEPROM-backed event log for boards without a filesystem (Arduino Nano, 1 KB EEPROM).
//
// Each event is stored in 17 bytes (type, no_entry, call_id parts, ms, wait, time, UTC offset).
// Every other field is fixed (device_id, ccn, synthetic:false) or derivable (seq, prev_hash, night, ts),
// so `dump` rebuilds the EXACT signed lines the device printed, byte for byte, and the bridge can
// backfill them (the server is idempotent on device_id + seq).
//
// EEPROM layout:
//   0  'C''K' magic        2  version            3  id check (device id + ccn + key)
//   5  boot counter (u16)  7  ring start index   8  record count
//   9  tail_seq (u32): seq of the oldest stored record (or the next seq when empty)
//  13  tail_prev (32 bytes): prev_hash of the oldest stored record (or the head hash when empty)
//  45  records, 17 bytes each: 57 on a 1 KB EEPROM
// When full, the oldest record is evicted; its hash becomes the new tail_prev, so the chain never breaks.
// Pure C++ (no Arduino headers): tested natively with a fake EEPROM.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "call_clock.h"
#include "event_log.h"

class CcStorage {
 public:
  virtual uint8_t read(uint16_t addr) = 0;
  virtual void write(uint16_t addr, uint8_t value) = 0;  // implementations should skip unchanged bytes
  virtual uint16_t size() const = 0;
};

struct CompactEvent {
  EventType type;
  int8_t no_entry;      // TRI_NULL, 0 or 1
  uint16_t nonce;       // call_id = "<nonce hex4>-<counter 4 digits>"
  uint16_t counter;     // 0..9999
  uint32_t ms;          // ms since boot
  int32_t wait_ds;      // deciseconds, -1 = null
  bool has_time;        // false → ts and night are null
  uint32_t epoch;       // UTC seconds
  int32_t tz_offset_s;  // seconds east of UTC; stored in 15-minute steps
};

class CompactLog {
 public:
  static const uint16_t kHeader = 45;
  static const uint8_t kRecord = 17;

  CompactLog(CcStorage& storage, const char* device_id, const char* ccn, const uint8_t* key, size_t key_len);

  // Formats the EEPROM if it is blank or belongs to another device/key, bumps the boot counter and
  // replays the stored records to find the chain head. Returns true if an existing log was kept.
  bool begin();

  uint16_t boot_nonce() const { return nonce_; }
  uint32_t next_seq() const { return tail_seq_ + count_; }
  const char* head_hash() const { return head_; }
  uint8_t count() const { return count_; }
  uint8_t capacity() const { return capacity_; }

  // Signs the event, streams its line to `out` (no prefix, no newline) and stores it.
  void emit(const CompactEvent& ev, CcSink& out);
  // Streams every stored event as "<prefix><line>\n", oldest first.
  void dump(CcSink& out, const char* prefix);
  // Forget stored events but keep the chain (the server still sees one unbroken chain).
  void clear();
  // Start a new chain at seq 1 (the server must forget this device too).
  void factory();

 private:
  struct Expanded {
    char call_id[12];
    char ts[26];
    EventFields f;
  };
  void expand(const CompactEvent& ev, uint32_t seq, const char* prev_hash, Expanded* x) const;
  bool read_record(uint8_t index, CompactEvent* ev);
  void write_record(uint8_t index, const CompactEvent& ev);
  void evict_oldest();
  static void genesis(char* hex);
  void write_header();
  void read_tail_prev(char* hex);
  void write_tail_prev(const char* hex);
  uint16_t id_check() const;
  uint16_t slot_addr(uint8_t index) const;
  void write_u16(uint16_t a, uint16_t v);
  void write_u32(uint16_t a, uint32_t v);
  uint16_t read_u16(uint16_t a);
  uint32_t read_u32(uint16_t a);

  CcStorage& st_;
  const char* device_id_;
  const char* ccn_;
  const uint8_t* key_;
  size_t key_len_;
  uint8_t capacity_;
  uint8_t start_ = 0;
  uint8_t count_ = 0;
  uint16_t nonce_ = 0;
  uint32_t tail_seq_ = 1;
  char head_[CC_HASH_HEX_LEN + 1];
};
