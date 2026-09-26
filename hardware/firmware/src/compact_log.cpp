#include "compact_log.h"

#include <stdio.h>
#include <string.h>

#include "config.h"
#include "crypto.h"
#include "timefmt.h"

static const uint8_t kMagic0 = 'C', kMagic1 = 'K', kVersion = 1;
enum : uint16_t { A_MAGIC = 0, A_VERSION = 2, A_ID = 3, A_BOOT = 5, A_START = 7, A_COUNT = 8, A_TAIL_SEQ = 9,
                  A_TAIL_PREV = 13 };

// 64 '0's without keeping a 65-byte literal in the Nano's RAM.
void CompactLog::genesis(char* hex) {
  memset(hex, '0', CC_HASH_HEX_LEN);
  hex[CC_HASH_HEX_LEN] = '\0';
}

CompactLog::CompactLog(CcStorage& storage, const char* device_id, const char* ccn, const uint8_t* key,
                       size_t key_len)
    : st_(storage), device_id_(device_id), ccn_(ccn), key_(key), key_len_(key_len) {
  uint16_t n = storage.size() > kHeader ? (storage.size() - kHeader) / kRecord : 0;
  capacity_ = n > 255 ? 255 : (uint8_t)n;
  genesis(head_);
}

void CompactLog::write_u16(uint16_t a, uint16_t v) {
  st_.write(a, v & 0xFF);
  st_.write(a + 1, v >> 8);
}
void CompactLog::write_u32(uint16_t a, uint32_t v) {
  for (uint8_t i = 0; i < 4; i++) st_.write(a + i, (uint8_t)(v >> (8 * i)));
}
uint16_t CompactLog::read_u16(uint16_t a) { return st_.read(a) | ((uint16_t)st_.read(a + 1) << 8); }
uint32_t CompactLog::read_u32(uint16_t a) {
  uint32_t v = 0;
  for (uint8_t i = 0; i < 4; i++) v |= (uint32_t)st_.read(a + i) << (8 * i);
  return v;
}

uint16_t CompactLog::id_check() const {
  // FNV-1a over device id, ccn and key, folded to 16 bits: a new identity or key starts a fresh log.
  uint32_t h = 2166136261UL;
  auto mix = [&h](const uint8_t* p, size_t n) {
    for (size_t i = 0; i < n; i++) {
      h ^= p[i];
      h *= 16777619UL;
    }
    h ^= 0xFF;
    h *= 16777619UL;
  };
  mix((const uint8_t*)device_id_, strlen(device_id_));
  mix((const uint8_t*)ccn_, strlen(ccn_));
  mix(key_, key_len_);
  return (uint16_t)(h ^ (h >> 16));
}

uint16_t CompactLog::slot_addr(uint8_t index) const {
  return kHeader + (uint16_t)((start_ + index) % capacity_) * kRecord;
}

void CompactLog::read_tail_prev(char* hex) {
  uint8_t b[32];
  for (uint8_t i = 0; i < 32; i++) b[i] = st_.read(A_TAIL_PREV + i);
  cc_to_hex(b, 32, hex);
}

void CompactLog::write_tail_prev(const char* hex) {
  uint8_t b[32];
  cc_from_hex(hex, b, 32);
  for (uint8_t i = 0; i < 32; i++) st_.write(A_TAIL_PREV + i, b[i]);
}

void CompactLog::write_header() {
  st_.write(A_START, start_);
  st_.write(A_COUNT, count_);
  write_u32(A_TAIL_SEQ, tail_seq_);
}

bool CompactLog::read_record(uint8_t index, CompactEvent* ev) {
  const uint16_t a = slot_addr(index);
  const uint8_t flags = st_.read(a);
  const uint8_t type = flags & 0x03, ne = (flags >> 2) & 0x03;
  if (ne == 3 || (flags & 0xE0)) return false;  // not something we wrote
  ev->type = (EventType)type;
  ev->no_entry = ne == 0 ? TRI_NULL : (int8_t)(ne - 1);
  ev->has_time = flags & 0x10;
  ev->nonce = read_u16(a + 1);
  ev->counter = read_u16(a + 3);
  ev->ms = read_u32(a + 5);
  const uint32_t w = st_.read(a + 9) | ((uint32_t)st_.read(a + 10) << 8) | ((uint32_t)st_.read(a + 11) << 16);
  ev->wait_ds = w == 0xFFFFFFUL ? -1 : (int32_t)w;
  ev->epoch = read_u32(a + 12);
  ev->tz_offset_s = (int32_t)(int8_t)st_.read(a + 16) * 900;
  return ev->counter <= 9999;
}

void CompactLog::write_record(uint8_t index, const CompactEvent& ev) {
  const uint16_t a = slot_addr(index);
  const uint8_t ne = ev.no_entry < 0 ? 0 : (uint8_t)(ev.no_entry + 1);
  st_.write(a, (uint8_t)((uint8_t)ev.type | (ne << 2) | (ev.has_time ? 0x10 : 0)));
  write_u16(a + 1, ev.nonce);
  write_u16(a + 3, ev.counter);
  write_u32(a + 5, ev.ms);
  const uint32_t w = ev.wait_ds < 0 ? 0xFFFFFFUL : (uint32_t)ev.wait_ds;
  st_.write(a + 9, w & 0xFF);
  st_.write(a + 10, (w >> 8) & 0xFF);
  st_.write(a + 11, (w >> 16) & 0xFF);
  write_u32(a + 12, ev.epoch);
  st_.write(a + 16, (uint8_t)(int8_t)(ev.tz_offset_s / 900));
}

void CompactLog::expand(const CompactEvent& ev, uint32_t seq, const char* prev_hash, Expanded* x) const {
  snprintf(x->call_id, sizeof(x->call_id), "%04x-%04u", (unsigned)ev.nonce, (unsigned)ev.counter);
  EventFields& f = x->f;
  f.seq = seq;
  f.device_id = device_id_;
  f.ccn = ccn_;
  f.call_id = x->call_id;
  f.event = event_type_name(ev.type);
  f.ms = ev.ms;
  f.wait_ds = ev.wait_ds;
  f.no_entry = ev.no_entry;
  f.synthetic = false;
  f.prev_hash = prev_hash;
  // Quantise the offset exactly as it will be stored, so the printed line and the dump agree.
  const int32_t off = ev.tz_offset_s / 900 * 900;
  if (ev.has_time) {
    cc_format_iso(ev.epoch, off, x->ts);
    const int h = cc_local_hour(ev.epoch, off);
    f.ts = x->ts;
    f.night = (h >= NIGHT_START_HOUR || h < NIGHT_END_HOUR) ? 1 : 0;
  } else {
    f.ts = nullptr;
    f.night = TRI_NULL;
  }
}

bool CompactLog::begin() {
  bool kept = capacity_ > 0 && st_.read(A_MAGIC) == kMagic0 && st_.read(A_MAGIC + 1) == kMagic1 &&
              st_.read(A_VERSION) == kVersion && read_u16(A_ID) == id_check();
  if (kept) {
    start_ = st_.read(A_START);
    count_ = st_.read(A_COUNT);
    tail_seq_ = read_u32(A_TAIL_SEQ);
    if (start_ >= capacity_ || count_ > capacity_ || tail_seq_ == 0) kept = false;
  }
  if (!kept) {  // blank, other device/key, or corrupt: start a new chain
    st_.write(A_MAGIC, kMagic0);
    st_.write(A_MAGIC + 1, kMagic1);
    st_.write(A_VERSION, kVersion);
    write_u16(A_ID, id_check());
    write_u16(A_BOOT, 0);
    start_ = count_ = 0;
    tail_seq_ = 1;
    genesis(head_);
    write_tail_prev(head_);
    write_header();
  }
  nonce_ = read_u16(A_BOOT) + 1;  // a new call_id prefix every boot
  write_u16(A_BOOT, nonce_);

  // Replay to find the head hash. Stop at the first record that doesn't decode.
  char prev[CC_HASH_HEX_LEN + 1];
  read_tail_prev(prev);
  for (uint8_t i = 0; i < count_; i++) {
    CompactEvent ev;
    if (!read_record(i, &ev)) {
      count_ = i;
      write_header();
      break;
    }
    Expanded x;
    expand(ev, tail_seq_ + i, prev, &x);
    cc_event_hash(x.f, prev);
  }
  memcpy(head_, prev, sizeof(head_));
  return kept;
}

void CompactLog::emit(const CompactEvent& ev, CcSink& out) {
  const CompactEvent* stored = &ev;
  CompactEvent quantised;
  if (ev.tz_offset_s % 900) {  // store (and sign) the offset in 15-minute steps
    quantised = ev;
    quantised.tz_offset_s = ev.tz_offset_s / 900 * 900;
    stored = &quantised;
  }
  Expanded x;
  expand(*stored, next_seq(), head_, &x);
  // Safe to write the new hash into head_: head_ (this event's prev_hash) is fully streamed and hashed
  // before the new hash is written. Saves a 65-byte buffer on the Nano.
  cc_stream_event(x.f, key_, key_len_, out, head_);  // print first: the line matters more than the copy

  if (capacity_ == 0) {
    tail_seq_++;
    return;
  }
  if (count_ == capacity_) evict_oldest();
  write_record(count_, *stored);  // record first, then the header that makes it visible
  count_++;
  write_header();
}

// Kept out of emit() so its buffers are not on the stack while an event is being signed.
__attribute__((noinline)) void CompactLog::evict_oldest() {
  // The oldest record's hash becomes the new tail_prev, so the chain stays unbroken.
  CompactEvent old;
  char prev[CC_HASH_HEX_LEN + 1];
  read_tail_prev(prev);
  read_record(0, &old);
  Expanded ox;
  expand(old, tail_seq_, prev, &ox);
  cc_event_hash(ox.f, prev);
  write_tail_prev(prev);
  start_ = (start_ + 1) % capacity_;
  count_--;
  tail_seq_++;
}

void CompactLog::dump(CcSink& out, const char* prefix) {
  char prev[CC_HASH_HEX_LEN + 1];
  read_tail_prev(prev);
  for (uint8_t i = 0; i < count_; i++) {
    CompactEvent ev;
    if (!read_record(i, &ev)) break;
    Expanded x;
    expand(ev, tail_seq_ + i, prev, &x);
    out.puts(prefix);
    cc_stream_event(x.f, key_, key_len_, out, prev);
    out.puts("\n");
  }
}

void CompactLog::clear() {
  tail_seq_ = next_seq();
  start_ = count_ = 0;
  write_tail_prev(head_);
  write_header();
}

void CompactLog::factory() {
  tail_seq_ = 1;
  start_ = count_ = 0;
  genesis(head_);
  write_tail_prev(head_);
  write_header();
}
